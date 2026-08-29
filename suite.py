#!/usr/bin/env python3
"""Promote recorded verify runs into pinned, gate-checked suite fixtures.

The two-sided gate (in spirit from lab/e3 validate_task.py): a run is a
fixture only if its brief's acceptance commands do NOT all pass at the pinned
base and DO all pass with the recorded patch applied. A task that is already
green at base discriminates nothing and is refused by name.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time

from baseline import classify, run_one
from brief_common import BriefError, acceptance_entries, load_brief, norm_cmd

RUNS_REL = ".prompire/runs.jsonl"
SUITE_REL = ".prompire/suite"
MANIFEST_REL = ".prompire/suite/manifest.json"
PIN_BRANCH = "prompire-suite-pin"


class Rejection(Exception):
    """A named admission failure. code 1 = the gate measured a "no";
    code 2 = admission could not be measured at all."""

    def __init__(self, reason, message, code=2):
        super().__init__(message)
        self.reason = reason
        self.code = code


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _git(root, *args, **kwargs):
    return subprocess.run(["git", "-C", str(root), *map(str, args)],
                          capture_output=True, **kwargs)


def find_run(root, selector):
    store = root / RUNS_REL
    if not store.is_file():
        raise Rejection("missing-record", f"no run store at {RUNS_REL}; "
                        "run `prompire verify <brief> --record` first")
    rows = []
    with open(store, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("run_id"):
                rows.append(row)
    if not rows:
        raise Rejection("missing-record", f"{RUNS_REL} holds no readable run")
    if selector == "last":
        return rows[-1]
    matches = [r for r in rows if str(r["run_id"]) == selector
               or (len(selector) >= 8 and str(r["run_id"]).startswith(selector))]
    ids = {str(m["run_id"]) for m in matches}
    if not matches:
        raise Rejection("missing-record", f"no recorded run matches `{selector}`")
    if len(ids) > 1:
        raise Rejection("missing-record",
                        f"`{selector}` matches {len(ids)} runs; give more of the id")
    return matches[-1]


def verify_inputs(root, row):
    """The row's brief and patch must still be reproducible from the live tree —
    the fixture pins bytes, and bytes the tree no longer produces are not the
    recorded run."""
    brief_rel = str(row.get("brief") or "")
    try:
        brief_bytes = (root / brief_rel).read_bytes()
    except OSError:
        raise Rejection("brief-changed",
                        f"`{brief_rel}` cannot be read; the recorded brief is gone")
    if _sha256(brief_bytes) != row.get("brief_sha256"):
        raise Rejection("brief-changed",
                        f"`{brief_rel}` no longer matches the recorded brief_sha256")
    base = row.get("base")
    if not base:
        raise Rejection("missing-patch", "the recorded run carries no pinned base")
    diff = _git(root, "diff", "--binary", base)
    if diff.returncode != 0:
        raise Rejection("missing-patch",
                        "git could not rebuild the diff against the recorded base")
    if _sha256(diff.stdout) != row.get("patch_sha256"):
        raise Rejection("missing-patch", "the working tree no longer produces the "
                        "recorded patch_sha256; re-verify with --record and add that run")
    return brief_bytes, str(base), diff.stdout


def pin_bundle(root, base, bundle_path):
    """A self-contained bundle holding <base> under PIN_BRANCH, so the fixture
    restores byte-for-byte even after the source history rewrites. The scratch
    branch exists only inside this call and is refused if it already exists."""
    if _git(root, "rev-parse", "--verify", "--quiet",
            f"refs/heads/{PIN_BRANCH}").returncode == 0:
        raise Rejection("pin-failure", f"branch `{PIN_BRANCH}` already exists; it is "
                        "the suite's scratch ref — delete or rename it first")
    made = _git(root, "branch", "-f", PIN_BRANCH, base)
    if made.returncode != 0:
        raise Rejection("pin-failure", "could not pin the base: "
                        + made.stderr.decode("utf-8", "replace").strip())
    try:
        bundled = _git(root, "bundle", "create", bundle_path, PIN_BRANCH)
        if bundled.returncode != 0:
            raise Rejection("pin-failure", "could not bundle the base: "
                            + bundled.stderr.decode("utf-8", "replace").strip())
    finally:
        _git(root, "branch", "-D", PIN_BRANCH)


def _run_side(ws, entries):
    results = []
    for entry in entries:
        reason = classify(entry)
        if reason:
            raise Rejection("not-runnable",
                            f"`{norm_cmd(entry.get('cmd'))}` cannot run "
                            f"mechanically: {reason}")
        measured = dict(run_one(ws, entry))
        measured["cmd"] = norm_cmd(entry.get("cmd"))
        results.append(measured)
    return results


def gate(bundle_path, base, brief_bytes, patch_bytes):
    """Fail-at-pin, pass-at-patch, measured in a workspace restored from the
    pinned bundle itself — so the stored artifact is proven restorable."""
    with tempfile.TemporaryDirectory(prefix="prompire-suite-gate-") as tmp:
        tmp_path = pathlib.Path(tmp)
        ws = tmp_path / "ws"
        cloned = subprocess.run(
            ["git", "clone", "-q", "-b", PIN_BRANCH, str(bundle_path), str(ws)],
            capture_output=True)
        if cloned.returncode != 0:
            raise Rejection("pin-failure", "the pinned bundle does not restore: "
                            + cloned.stderr.decode("utf-8", "replace").strip())
        head = _git(ws, "rev-parse", "HEAD")
        # `base` is `baseline.py`'s 12-char short SHA (head[:12]), never the full
        # 40-char one `rev-parse HEAD` returns, so this checks a prefix, not equality.
        if not head.stdout.decode("utf-8", "replace").strip().startswith(base):
            raise Rejection("pin-failure",
                            "the restored workspace is not at the recorded base")
        # The recorded brief is measured from its own bytes, staged outside the
        # workspace: writing it into `ws` before `git apply` would, for a brief
        # tracked in git, overwrite the very file the recorded patch has a hunk
        # for — the hunk's context expects the pristine base content, not the
        # already-final content, and `git apply` fails on an untouched patch.
        brief_tmp = tmp_path / "brief.yaml"
        brief_tmp.write_bytes(brief_bytes)
        try:
            entries = acceptance_entries(load_brief(str(brief_tmp)))
        except BriefError as exc:
            raise Rejection("not-runnable", f"the recorded brief does not load: {exc}")
        if not entries:
            raise Rejection("green-at-base", "the brief declares no acceptance "
                            "commands; nothing can discriminate", code=1)
        at_pin = _run_side(ws, entries)
        if all(r.get("status") == "pass" for r in at_pin):
            raise Rejection("green-at-base", "every acceptance command already "
                            "passes at the pinned base", code=1)
        if patch_bytes:
            applied = subprocess.run(["git", "-C", str(ws), "apply", "--binary"],
                                     input=patch_bytes, capture_output=True)
            if applied.returncode != 0:
                raise Rejection("pin-failure", "the recorded patch does not apply "
                                "at the pinned base: "
                                + applied.stderr.decode("utf-8", "replace").strip())
        at_patch = _run_side(ws, entries)
        if not all(r.get("status") == "pass" for r in at_patch):
            raise Rejection("fail-at-patch", "acceptance does not pass with the "
                            "recorded patch applied", code=1)
        return at_pin, at_patch


def _report(payload, json_mode):
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    elif payload["status"] == "added":
        print(f"admitted {payload['fixture']} — suite v{payload['suite_version']}, "
              f"manifest {payload['content_sha256'][:12]}")
    else:
        print(f"rejected: {payload['reason']} — {payload['message']}")


def _manifest_hash(data):
    body = {"fixtures": data["fixtures"], "reserve": data["reserve"]}
    return _sha256(json.dumps(body, sort_keys=True,
                              ensure_ascii=False).encode("utf-8"))


def update_manifest(root, row, reserve, fixture_dir, added_ts):
    path = root / MANIFEST_REL
    data = {"suite_version": 0, "fixtures": [], "reserve": []}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    data["fixtures"].append({
        "id": str(row["run_id"]),
        "brief": str(row["brief"]),
        "base": str(row["base"]),
        "brief_sha256": row["brief_sha256"],
        "patch_sha256": row["patch_sha256"],
        "bundle_sha256": _sha256((fixture_dir / "base.bundle").read_bytes()),
        "added": added_ts,
    })
    if reserve:
        data["reserve"].append(str(row["run_id"]))
    data["suite_version"] += 1
    data["content_sha256"] = _manifest_hash(data)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except OSError:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise
    return data["suite_version"], data["content_sha256"]


def add(root, selector, reserve, json_mode):
    try:
        row = find_run(root, selector)
        fixture_id = str(row["run_id"])
        fixtures_dir = root / SUITE_REL / "fixtures"
        final_dir = fixtures_dir / fixture_id
        if final_dir.exists():
            raise Rejection("already-admitted",
                            f"fixture {fixture_id} already exists; admitting it "
                            "again would overwrite a pinned fixture")
        brief_bytes, base, patch_bytes = verify_inputs(root, row)
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        staging = pathlib.Path(tempfile.mkdtemp(prefix=".staging-",
                                                dir=fixtures_dir))
        try:
            (staging / "record.json").write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            (staging / "brief.yaml").write_bytes(brief_bytes)
            (staging / "patch.bin").write_bytes(patch_bytes)
            pin_bundle(root, base, staging / "base.bundle")
            at_pin, at_patch = gate(staging / "base.bundle", base,
                                    brief_bytes, patch_bytes)
            (staging / "gate.json").write_text(
                json.dumps({"at_pin": at_pin, "at_patch": at_patch},
                           ensure_ascii=False) + "\n", encoding="utf-8")
            os.rename(staging, final_dir)
            version, content = update_manifest(
                root, row, reserve, final_dir, time.strftime("%Y-%m-%dT%H:%M:%S"))
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    except Rejection as exc:
        _report({"status": "rejected", "reason": exc.reason, "message": str(exc)},
                json_mode)
        return exc.code
    except OSError as exc:
        # A plain filesystem failure (e.g. something already occupying where
        # fixtures/ must go) is not a measured gate "no" — exit 1 is reserved
        # for that — so it is reported as a rejection, not left to traceback.
        _report({"status": "rejected", "reason": "pin-failure", "message": str(exc)},
                json_mode)
        return 2
    _report({"status": "added", "fixture": fixture_id, "suite_version": version,
             "content_sha256": content, "reserve": bool(reserve)}, json_mode)
    return 0
