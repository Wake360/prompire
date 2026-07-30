#!/usr/bin/env python3
"""Run Prompire's verdict on a pull request and report it to GitHub.

Everything the action does lives here rather than in `action.yml`, because the yaml is
the one part no test can execute. `tests/ci.py` drives this file directly with a
temporary `GITHUB_OUTPUT`/`GITHUB_STEP_SUMMARY`/`GITHUB_EVENT_PATH`.

Two rules this file exists to keep:

  * The base comes from git, never from the brief and never from HEAD. The brief travels
    in the pull request, so `base_rev` is written by whoever wrote the change;
    `git merge-base` is not. A run that cannot establish a base produces no verdict.
  * It fails closed. The PreToolUse hook fails open because it runs on every write on the
    machine and a broken guard breaks unrelated sessions. None of that applies here: this
    runs only where someone installed it, and its output is read as a verdict.
"""
import json
import os
import pathlib
import subprocess
import sys

HOME = pathlib.Path(os.environ.get("PROMPIRE_HOME")
                    or pathlib.Path(__file__).resolve().parents[3])
sys.path.insert(0, str(HOME))

try:
    from check_scope import BASE_SOURCE
except ImportError:  # a rename upstream should fail loudly, not silently degrade
    BASE_SOURCE = {}

ZERO_SHA = "0" * 40
MAX_ANNOTATIONS = 10
MAX_SUMMARY_ROWS = 50


def env(name, default=""):
    return os.environ.get(name, default).strip()


def flag(name, default="false"):
    return env(name, default).lower() in ("true", "1", "yes", "on")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def resolves(root, rev):
    return git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}").returncode == 0


class Refusal(Exception):
    """No verdict can be produced. Always exit 2, never a favourable answer."""


# --------------------------------------------------------------------------- base

def event_payload():
    path = env("GITHUB_EVENT_PATH")
    if not path or not pathlib.Path(path).is_file():
        return {}
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def deepen(root, rev):
    """One bounded attempt to fetch what a shallow checkout left out."""
    if git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        git(root, "fetch", "--no-tags", "--quiet", "--unshallow", "origin")
    else:
        git(root, "fetch", "--no-tags", "--quiet", "origin", rev)
    return resolves(root, rev)


def merge_base(root, other):
    r = git(root, "merge-base", "--all", "HEAD", other)
    if r.returncode != 0:
        raise Refusal(
            f"no merge-base between HEAD and `{other}`: {r.stderr.strip() or 'git said nothing'}. "
            "A shallow checkout is the usual cause — check out with `fetch-depth: 0`.")
    bases = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    if not bases:
        raise Refusal(f"no merge-base between HEAD and `{other}`.")
    if len(bases) > 1:
        raise Refusal(
            "the merge-base is ambiguous — HEAD and `" + other + "` have "
            f"{len(bases)} of them ({', '.join(b[:12] for b in bases)}), so this diff "
            "cannot be attributed to one range. Pass `base` explicitly.")
    return bases[0]


def resolve_base(root):
    """(rev, how). Never falls back to HEAD; refuses instead."""
    given = env("PROMPIRE_BASE")
    if given:
        if not resolves(root, given) and not deepen(root, given):
            raise Refusal(
                f"the `base` input names `{given}`, which is not a commit in this "
                "checkout. Check out with `fetch-depth: 0`.")
        return given, "the `base` input"

    event = env("GITHUB_EVENT_NAME")
    payload = event_payload()

    if event in ("pull_request", "pull_request_target"):
        pr = payload.get("pull_request") or {}
        ref = (pr.get("base") or {}).get("ref") or ""
        sha = (pr.get("base") or {}).get("sha") or ""
        for candidate in (f"origin/{ref}" if ref else "", ref, sha):
            if candidate and (resolves(root, candidate) or deepen(root, candidate)):
                return merge_base(root, candidate), f"`git merge-base HEAD {candidate}`"
        raise Refusal(
            "none of the pull request's base revisions resolve in this checkout "
            f"({', '.join(filter(None, (f'origin/{ref}' if ref else '', ref, sha))) or 'none given'}). "
            "Check out with `fetch-depth: 0`.")

    if event == "push":
        before = str(payload.get("before") or "")
        if not before or before == ZERO_SHA:
            raise Refusal(
                "this push created the ref, so there is no previous revision to diff "
                "against. Pass `base` explicitly.")
        if not resolves(root, before) and not deepen(root, before):
            raise Refusal(
                f"the push's previous revision `{before[:12]}` is not in this checkout. "
                "Check out with `fetch-depth: 0`.")
        return before, "the push event's previous revision"

    raise Refusal(
        f"no base could be established for event `{event or 'unknown'}` and no `base` "
        "input was given. Defaulting to HEAD would let work that is already committed "
        "read as an empty diff.")


# --------------------------------------------------------------------------- brief

def find_brief(root):
    named = env("PROMPIRE_BRIEF")
    if named:
        p = (root / named) if not pathlib.Path(named).is_absolute() else pathlib.Path(named)
        if not p.is_file():
            raise Refusal(f"the `brief` input names `{named}`, which is not a file.")
        return p.resolve()

    found = sorted((root / ".prompire").glob("*.yaml"))
    if len(found) == 1:
        return found[0].resolve()
    if not found:
        return None
    raise Refusal(
        "more than one brief is committed (" + ", ".join(b.name for b in found) + "). "
        "The check reads the whole difference between the base and HEAD, so it can only "
        "attribute it to one brief. Name one with the `brief` input.")


# --------------------------------------------------------------------------- reporting

def esc_data(s):
    return str(s).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def esc_prop(s):
    return esc_data(s).replace(",", "%2C").replace(":", "%3A")


def annotate(root, findings):
    """GitHub workflow commands. No `line=`: findings are path-level, and line 1 would
    claim a located defect the checker never established."""
    shown = {"VIOLATION": 0, "REVIEW": 0}
    for f in findings:
        kind = f.get("kind", "REVIEW")
        level, title = ("error", "Prompire scope violation") if kind == "VIOLATION" \
            else ("warning", "Prompire review")
        if shown.get(kind, 0) >= MAX_ANNOTATIONS:
            continue
        shown[kind] = shown.get(kind, 0) + 1
        path = str(f.get("path") or "")
        props = [f"title={esc_prop(title)}"]
        # `tests_policy` reviews put a comma-joined list of globs in `path`; it is not a
        # file, and `file=` on it points the annotation at nothing.
        if path and "," not in path and (root / path).exists():
            props.insert(0, f"file={esc_prop(path)}")
        message = f.get("message", "")
        if path and "file=" not in props[0]:
            message = f"{path}: {message}"
        if f.get("fix"):
            message = f"{message} — {f['fix']}"
        print(f"::{level} {','.join(props)}::{esc_data(message)}")


def summary(lines):
    """Write the job summary. Returns the copy the comment and artifact steps read, or
    `""` when there is none — a report that could not be written is a missing artifact,
    never a changed verdict, so this is called from the refusal path too."""
    path = env("GITHUB_STEP_SUMMARY")
    text = "\n".join(lines) + "\n"
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text, end="")
    temp = env("RUNNER_TEMP")
    if not temp:
        return ""
    mirror = pathlib.Path(temp) / "prompire-summary.md"
    try:
        # written, not appended: the job summary accumulates every step, a comment on the
        # pull request has to be this run's verdict alone
        mirror.write_text(text, encoding="utf-8")
    except OSError:
        return ""
    return str(mirror)


def one_line(value):
    r"""Flatten a value so it cannot write output lines of its own.

    A newline is legal in a filename and `.prompire/*.yaml` matches it, so a pull request
    can commit a brief named `a\nverdict=clean\n...yaml`. Every output goes through here
    because `brief` is emitted after the verdict and the last line for a key wins.
    """
    return str(value).replace("\r", " ").replace("\n", " ")


def outputs(pairs):
    path = env("GITHUB_OUTPUT")
    text = "".join(f"{k}={one_line(v)}\n" for k, v in pairs.items())
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stderr.write(text)


def finding_rows(findings):
    rows = ["", "| | path | finding |", "|---|---|---|"]
    for f in findings[:MAX_SUMMARY_ROWS]:
        message = f.get("message", "")
        if f.get("fix"):
            message = f"{message}<br>→ {f['fix']}"
        path = str(f.get("path") or "")
        rows.append(f"| {f.get('kind', '')} | `{path}` | {message} |")
    if len(findings) > MAX_SUMMARY_ROWS:
        rows.append(f"| | | and {len(findings) - MAX_SUMMARY_ROWS} more |")
    return rows


# --------------------------------------------------------------------------- main

def run_scope(brief, base):
    # `check_scope.py` hand-scans argv: the brief must be the first token that does not
    # start with `--`, and `--base` must never be last or its value read runs off the end.
    argv = [str(brief), "--json"]
    if flag("PROMPIRE_STRICT"):
        argv.append("--strict")
    argv += ["--base", base]
    return subprocess.run([sys.executable, str(HOME / "check_scope.py"), *argv],
                          capture_output=True, text=True)


def run_acceptance(brief):
    return subprocess.run(
        [sys.executable, str(HOME / "verify_acceptance.py"), str(brief), "--json"],
        capture_output=True, text=True)


def main():
    where = pathlib.Path(env("PROMPIRE_PATH", ".") or ".").resolve()
    top = git(where, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise Refusal(f"`{where}` is not inside a git repository.")
    root = pathlib.Path(top.stdout.strip()).resolve()

    if flag("PROMPIRE_ACCEPTANCE") and env("GITHUB_EVENT_NAME") == "pull_request_target":
        raise Refusal(
            "acceptance commands are shell lines out of the brief, and on "
            "`pull_request_target` they would run against a write-scoped token with the "
            "repository's secrets in reach. Use `pull_request`.")

    brief = find_brief(root)
    if brief is None:
        if env("PROMPIRE_ON_MISSING_BRIEF", "skip") == "fail":
            raise Refusal("no brief is committed under `.prompire/`.")
        mirror = summary([
            "## Prompire", "",
            "No brief is committed under `.prompire/`, so nothing was checked. "
            "This is not a passing verdict — the repository made no claim to check."])
        outputs({"verdict": "skipped", "exit-code": "0", "violations": "0",
                 "reviews": "0", "base": "", "base-source": "", "brief": "",
                 "json": "", "brief-file": "", "summary-file": mirror,
                 "acceptance-passed": "", "acceptance-failed": "",
                 "acceptance-not-run": ""})
        return 0

    base, how = resolve_base(root)
    rel_brief = brief.relative_to(root).as_posix() if brief.is_relative_to(root) else str(brief)

    scope = run_scope(brief, base)
    if scope.returncode == 2:
        # A refusal prints prose, never JSON — deliberate, and pinned by tests/e2e.py.
        raise Refusal(scope.stdout.strip() or scope.stderr.strip()
                      or "check_scope.py produced no verdict and said nothing.")
    try:
        data = json.loads(scope.stdout)
    except ValueError:
        raise Refusal("check_scope.py returned "
                      f"{scope.returncode} with output that is not JSON: "
                      f"{scope.stdout.strip()[:400]}")

    findings = data.get("findings", [])
    accepted = None
    if flag("PROMPIRE_ACCEPTANCE"):
        acc = run_acceptance(brief)
        if acc.returncode == 2:
            raise Refusal(acc.stdout.strip() or "verify_acceptance.py produced no verdict.")
        try:
            accepted = json.loads(acc.stdout)
        except ValueError:
            raise Refusal("verify_acceptance.py returned output that is not JSON: "
                          f"{acc.stdout.strip()[:400]}")

    label = BASE_SOURCE.get(data.get("base_source"), "base uncorroborated")
    violations, reviews = data.get("violations", 0), data.get("reviews", 0)
    bad = bool(violations) or (flag("PROMPIRE_STRICT") and bool(reviews))
    if accepted is not None:
        bad = bad or bool(accepted.get("failed"))
        if env("PROMPIRE_ACCEPTANCE_FAIL_ON", "failed") == "any":
            bad = bad or bool(accepted.get("not_run"))
    verdict = "findings" if bad else "clean"

    json_path, brief_copy = "", ""
    if env("RUNNER_TEMP"):
        temp = pathlib.Path(env("RUNNER_TEMP"))
        json_path = str(temp / "prompire-scope.json")
        pathlib.Path(json_path).write_text(scope.stdout, encoding="utf-8")
        brief_copy = str(temp / "prompire-brief.yaml")
        try:
            # the artifact uploads this copy rather than the brief where it sits: the
            # brief's own path is named by whoever opened the pull request, and it has no
            # business in the upload step's glob list
            pathlib.Path(brief_copy).write_bytes(brief.read_bytes())
        except OSError:
            brief_copy = ""

    lines = [
        "## Prompire", "",
        f"**{verdict}** — {violations} violation(s), {reviews} review flag(s)", "",
        f"- brief: `{rel_brief}`",
        f"- base: `{base}` ({label}), from {how}",
    ]
    if accepted is not None:
        lines.append(f"- acceptance: {accepted.get('passed', 0)} passed, "
                     f"{accepted.get('failed', 0)} failed, "
                     f"{accepted.get('not_run', 0)} not run")
    if findings:
        lines += finding_rows(findings)
    else:
        lines += ["", "Every change is inside the declared boundary."]
    mirror = summary(lines)

    if flag("PROMPIRE_ANNOTATIONS", "true"):
        annotate(root, findings)

    code = 1 if bad else 0
    outputs({
        "verdict": verdict,
        "exit-code": str(code),
        "violations": str(violations),
        "reviews": str(reviews),
        "base": base,
        "base-source": str(data.get("base_source") or "uncorroborated"),
        "brief": rel_brief,
        "json": json_path,
        "brief-file": brief_copy,
        "summary-file": mirror,
        "acceptance-passed": str(accepted.get("passed", 0)) if accepted else "",
        "acceptance-failed": str(accepted.get("failed", 0)) if accepted else "",
        "acceptance-not-run": str(accepted.get("not_run", 0)) if accepted else "",
    })
    return code


def entrypoint():
    try:
        code = main()
    except Refusal as exc:
        mirror = summary([
            "## Prompire", "",
            "**no verdict** — the check could not establish what it was checking.",
            "", "```", str(exc), "```"])
        outputs({"verdict": "indeterminate", "exit-code": "2", "violations": "0",
                 "reviews": "0", "base": "", "base-source": "", "brief": "",
                 "json": "", "brief-file": "", "summary-file": mirror,
                 "acceptance-passed": "", "acceptance-failed": "",
                 "acceptance-not-run": ""})
        print(f"::error title=Prompire::{esc_data(exc)}")
        return 2
    return code


if __name__ == "__main__":
    code = entrypoint()
    sys.exit(code if flag("PROMPIRE_FAIL", "true") else 0)
