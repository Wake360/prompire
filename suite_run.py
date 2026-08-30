#!/usr/bin/env python3
"""Replay the admitted suite with a candidate and diff it against a baseline.

The user-facing output is always a comparison between two result sets. A run
with no stored baseline and no --as-baseline is refused before any fixture
executes; the per-candidate result set under results/ is a debug dump, not the
product surface. The manifest is read, never written: replay cannot change
suite membership, and the reserve slice is a report block, not a tuning input.

Exit 0 = comparison rendered or baseline stored, every fixture measured;
1 = rendered/stored but at least one fixture errored; 2 = refusal, nothing ran.
"""
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

from suite import MANIFEST_REL, PIN_BRANCH, SUITE_REL, Rejection

HERE = pathlib.Path(__file__).resolve().parent
RESULTS_REL = ".prompire/suite/results"
BASELINE_REL = ".prompire/suite/baseline.json"
DETERMINISTIC = ("patch", "noop")
LIVE = ("claude", "codex", "antigravity")
CANDIDATE_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _bench():
    """bench/run.py and bench/report.py, importable only beside a source
    checkout — the wheel ships suite_run.py but not bench/, so a missing bench
    is a named refusal, not an ImportError traceback."""
    if not (HERE / "bench" / "run.py").is_file():
        raise Rejection("bench-unavailable",
                        "suite run replays through bench/run.py, which is not "
                        "beside this install; run from a Prompire checkout")
    for p in (str(HERE / "bench"), str(HERE / "tests"), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import report as bench_report
    import run as bench_run
    return bench_run, bench_report


def load_manifest(root):
    path = root / MANIFEST_REL
    if not path.is_file():
        raise Rejection("no-suite", f"no suite manifest at {MANIFEST_REL}; "
                        "admit a run with `prompire suite add` first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Rejection("no-suite", f"{MANIFEST_REL} does not parse: {exc}")
    if (not isinstance(data, dict) or not isinstance(data.get("fixtures"), list)
            or not isinstance(data.get("reserve"), list)
            or not data["fixtures"]):
        raise Rejection("no-suite", f"{MANIFEST_REL} holds no admitted fixtures")
    return data


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False)
    try:
        with handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(handle.name, path)
    except OSError:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise


def run_fixture(root, fixture_id, variant, agent, bench_run):
    fdir = root / SUITE_REL / "fixtures" / fixture_id
    record = json.loads((fdir / "record.json").read_text(encoding="utf-8"))
    brief_rel = str(record["brief"])
    base = str(record["base"])
    brief_bytes = (fdir / "brief.yaml").read_bytes()
    t0 = time.monotonic()
    stats = {"agent_exit": 0, "model": None, "turns": None,
             "tokens_in": None, "tokens_out": None, "cost_usd": None}
    with tempfile.TemporaryDirectory(prefix="prompire-suite-run-") as tmp:
        ws = pathlib.Path(tmp) / "ws"
        cloned = subprocess.run(
            ["git", "clone", "-q", "-b", PIN_BRANCH,
             str(fdir / "base.bundle"), str(ws)], capture_output=True)
        if cloned.returncode != 0:
            raise RuntimeError("the pinned bundle does not restore: "
                               + cloned.stderr.decode("utf-8", "replace").strip())
        head = subprocess.run(["git", "-C", str(ws), "rev-parse", "HEAD"],
                              capture_output=True)
        if not head.stdout.decode("utf-8", "replace").strip().startswith(base):
            raise RuntimeError("the restored workspace is not at the recorded base")
        if agent == "patch":
            patch_bytes = (fdir / "patch.bin").read_bytes()
            if patch_bytes:
                applied = subprocess.run(
                    ["git", "-C", str(ws), "apply", "--binary"],
                    input=patch_bytes, capture_output=True)
                if applied.returncode != 0:
                    raise RuntimeError(
                        "the pinned patch does not apply at the pinned base: "
                        + applied.stderr.decode("utf-8", "replace").strip())
        # For a tracked brief the recorded bytes equal the post-patch content
        # (brief_sha256 was taken from the final tree), so writing them after
        # `git apply` is byte-neutral — writing them before it would break the
        # patch's own brief hunk, the trap suite.gate() documents.
        target = ws / brief_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(brief_bytes)
        armed = subprocess.run(
            [sys.executable, str(HERE / "check_scope.py"), brief_rel,
             "--activate"], cwd=str(ws), capture_output=True, text=True,
            encoding="utf-8")
        if armed.returncode != 0:
            raise RuntimeError("could not arm the guard in the restored "
                               f"workspace: {armed.stdout}{armed.stderr}".strip())
        tampered = []
        if agent not in DETERMINISTIC:
            from brief_common import load_brief
            prompt = bench_run.VARIANTS[variant](load_brief(str(target)),
                                                 brief_rel)
            guarded = (brief_rel, ".prompire/ACTIVE")
            author = {p: (ws / p).read_bytes() for p in guarded}
            stats = bench_run.run_agent(agent, prompt, ws, fixture_id)
            tampered = sorted(p for p in guarded if not (ws / p).is_file()
                              or (ws / p).read_bytes() != author[p])
            for p in guarded:
                (ws / p).parent.mkdir(parents=True, exist_ok=True)
                (ws / p).write_bytes(author[p])
        row = dict(stats)
        row["tampered"] = tampered
        row.update(bench_run.measure(ws, base, brief_rel=brief_rel))
    row["seconds"] = round(time.monotonic() - t0, 2)
    return row


def execute(root, manifest, variant, agent, bench_run):
    outcomes, errors = {}, []
    for fx in manifest["fixtures"]:
        fixture_id = str(fx["id"])
        try:
            outcomes[fixture_id] = run_fixture(root, fixture_id, variant,
                                               agent, bench_run)
            state = "ok "
        except Exception as exc:
            outcomes[fixture_id] = {"error": str(exc)}
            errors.append(fixture_id)
            state = "ERR"
        print(f"{state}  {fixture_id[:12]} × {variant} × {agent}",
              file=sys.stderr)
    return outcomes, errors


def _green(outcome):
    a = outcome.get("acceptance") or {}
    return (a.get("passed", 0) >= 1 and a.get("failed") == 0
            and a.get("not_run") == 0)


SLICES = (("acceptance", _green),
          ("scope", lambda o: o.get("scope_exit") == 0),
          ("gamed", lambda o: not o.get("tampered")))


def compare(baseline, current, reserve_ids, bench_report):
    def mk(result_set, fixture_id):
        outcome = result_set["outcomes"].get(fixture_id)
        if outcome is None:
            return "ERR"
        return bench_report.mark(dict(outcome, agent=result_set["agent"]))

    ids = sorted(set(baseline["outcomes"]) | set(current["outcomes"]))
    fixtures = {i: {"baseline": mk(baseline, i), "candidate": mk(current, i),
                    "reserve": i in reserve_ids} for i in ids}
    slices, moved = {"main": {}, "reserve": {}}, []
    for block in ("main", "reserve"):
        block_ids = [i for i in ids
                     if (i in reserve_ids) == (block == "reserve")]
        for name, good in SLICES:
            entry = {"baseline": 0, "candidate": 0,
                     "regressed": [], "improved": [], "unmeasured": []}
            for i in block_ids:
                b = baseline["outcomes"].get(i) or {"error": "absent"}
                c = current["outcomes"].get(i) or {"error": "absent"}
                if b.get("error") or c.get("error"):
                    entry["unmeasured"].append(i)
                    continue
                was, now = good(b), good(c)
                entry["baseline"] += was
                entry["candidate"] += now
                if was and not now:
                    entry["regressed"].append(i)
                if now and not was:
                    entry["improved"].append(i)
            slices[block][name] = entry
            if entry["regressed"] or entry["improved"]:
                moved.append(f"{block}.{name}")
    return fixtures, slices, moved


def _render_compared(payload):
    print(f"suite v{payload['suite_version']} "
          f"(manifest {payload['content_sha256'][:12]}) — "
          f"{payload['candidate']['id']} ({payload['candidate']['agent']}) "
          f"vs baseline {payload['baseline']['id']} "
          f"({payload['baseline']['agent']})")
    print("fixture\tbaseline\tcandidate")
    for fixture_id, marks in sorted(payload["fixtures"].items()):
        tag = " (reserve)" if marks["reserve"] else ""
        print(f"{fixture_id[:12]}{tag}\t{marks['baseline']}\t{marks['candidate']}")
    for block, label in (("main", "main"), ("reserve", "reserve (never tuned)")):
        counts = payload["slices"][block]
        total = len([1 for m in payload["fixtures"].values()
                     if m["reserve"] == (block == "reserve")])
        print(f"{label} — {total} fixture{'s' if total != 1 else ''}")
        for name, entry in counts.items():
            line = f"  {name:<11}{entry['baseline']} -> {entry['candidate']}"
            if entry["regressed"]:
                line += "  regressed: " + " ".join(
                    i[:12] for i in entry["regressed"])
            if entry["improved"]:
                line += "  improved: " + " ".join(
                    i[:12] for i in entry["improved"])
            if entry["unmeasured"]:
                line += "  unmeasured: " + " ".join(
                    i[:12] for i in entry["unmeasured"])
            print(line)
    print("moved: " + ", ".join(payload["moved"]) if payload["moved"]
          else "no slice movement")
    if payload["errors"]:
        print("errored fixtures: " + " ".join(i[:12] for i in payload["errors"]))


def _report(payload, json_mode):
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    elif payload["status"] == "rejected":
        print(f"rejected: {payload['reason']} — {payload['message']}")
    elif payload["status"] == "baseline-stored":
        n = payload["fixture_count"]
        line = (f"baseline stored: {payload['candidate']['id']} over suite "
                f"v{payload['suite_version']} "
                f"(manifest {payload['content_sha256'][:12]}), "
                f"{n} fixture{'s' if n != 1 else ''}")
        if payload["errors"]:
            line += (", " + str(len(payload["errors"])) + " errored: "
                     + " ".join(i[:12] for i in payload["errors"]))
        print(line)
    else:
        _render_compared(payload)


def run(root, candidate, variant, agent, as_baseline, json_mode):
    try:
        if not CANDIDATE_RE.fullmatch(candidate):
            raise Rejection("bad-candidate",
                            "a candidate id names a stored result set: "
                            "letters, digits, dot, dash, underscore, ≤64 chars")
        if agent not in DETERMINISTIC and agent not in LIVE \
                and not agent.startswith("scripted:"):
            raise Rejection("unknown-agent",
                            f"unknown agent {agent!r} — patch, noop, "
                            "scripted:<behavior>, claude, codex or antigravity")
        bench_run, bench_report = _bench()
        if variant not in bench_run.VARIANTS:
            raise Rejection("unknown-variant",
                            f"unknown variant {variant!r} — one of: "
                            + ", ".join(sorted(bench_run.VARIANTS)))
        manifest = load_manifest(root)
        baseline = None
        if not as_baseline:
            baseline_path = root / BASELINE_REL
            if not baseline_path.is_file():
                raise Rejection("no-baseline",
                                f"no stored baseline at {BASELINE_REL}; run "
                                "`prompire suite run <candidate> --as-baseline`"
                                " first — a lone scorecard is not a comparison")
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            if baseline.get("content_sha256") != manifest["content_sha256"]:
                raise Rejection("suite-changed",
                                "the stored baseline was measured over a "
                                "different suite (manifest content hash "
                                "differs); re-run --as-baseline over the "
                                "current suite")
    except Rejection as exc:
        _report({"status": "rejected", "reason": exc.reason,
                 "message": str(exc)}, json_mode)
        return exc.code
    outcomes, errors = execute(root, manifest, variant, agent, bench_run)
    result_set = {"candidate": candidate, "variant": variant, "agent": agent,
                  "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "prompire_rev": bench_run.prompire_rev(),
                  "suite_version": manifest["suite_version"],
                  "content_sha256": manifest["content_sha256"],
                  "outcomes": outcomes}
    _write_json(root / RESULTS_REL / f"{candidate}.json", result_set)
    descr = {k: result_set[k] for k in ("variant", "agent", "ts")}
    if as_baseline:
        _write_json(root / BASELINE_REL, result_set)
        _report({"status": "baseline-stored",
                 "candidate": dict(descr, id=candidate),
                 "suite_version": manifest["suite_version"],
                 "content_sha256": manifest["content_sha256"],
                 "fixture_count": len(outcomes), "errors": errors}, json_mode)
        return 1 if errors else 0
    reserve_ids = {str(i) for i in manifest["reserve"]}
    fixtures, slices, moved = compare(baseline, result_set, reserve_ids,
                                      bench_report)
    _report({"status": "compared",
             "suite_version": manifest["suite_version"],
             "content_sha256": manifest["content_sha256"],
             "candidate": dict(descr, id=candidate),
             "baseline": {"id": baseline.get("candidate"),
                          "variant": baseline.get("variant"),
                          "agent": baseline.get("agent"),
                          "ts": baseline.get("ts")},
             "fixtures": fixtures, "slices": slices, "moved": moved,
             "errors": errors}, json_mode)
    return 1 if errors else 0
