#!/usr/bin/env python3
"""Transaction tests for the top-level CLI.

Run: python3 tests/cli.py
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = ROOT / "prompire.py"
sys.path.insert(0, str(HERE))

import fixtures  # noqa: E402


CASES = []
ENV = os.environ.copy()


def case(name):
    def decorate(fn):
        CASES.append((name, fn))
        return fn
    return decorate


class Checks:
    def __init__(self):
        self.fails = []

    def ok(self, condition, message):
        if not condition:
            self.fails.append(message)

    def equal(self, got, want, message):
        self.ok(got == want, f"{message}: got {got!r}, want {want!r}")


def run(*args):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True, env=ENV)


def brief(repo, name="task", extra=""):
    path = pathlib.Path(repo) / ".prompire" / f"{name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""\
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
""" + extra + "autonomy: ask\n", encoding="utf-8")
    return path


def prepared(repo, name="task", *extra):
    path = brief(repo, name)
    result = run("prepare", path, *extra)
    if result.returncode != 0:
        raise AssertionError(f"prepare failed: {result.stdout}{result.stderr}")
    return path


def json_out(result):
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(f"stdout is not one JSON object: {result.stdout!r}") from error


@case("prepare writes baseline, prompt, checklist, then ACTIVE")
def _(repo, checks):
    path = brief(repo)
    result = run("prepare", path, "--target", "codex")
    checks.equal(result.returncode, 0, "prepare exit")
    text = path.read_text(encoding="utf-8")
    checks.ok("baseline:" in text and "base_rev:" in text,
              "prepare must write the measured baseline before arming")
    checks.ok(path.with_name("task.codex.md").is_file(), "prepare must write the prompt")
    checks.ok(path.with_name("task.checklist.md").is_file(), "prepare must write checklist")
    active = (pathlib.Path(repo) / ".prompire" / "ACTIVE")
    checks.ok(active.is_file(), "prepare must arm after the artifacts exist")
    checks.ok(active.read_text(encoding="utf-8").startswith(".prompire/task.yaml\n"),
              "ACTIVE must name the prepared brief")
    output = result.stdout.replace("\\", "/")
    checks.ok(f"prompire verify {path.as_posix()}" in output,
              "prepare must print the next verification command")


@case("prepare does not arm when baseline fails")
def _(repo, checks):
    path = brief(repo, extra="    expect: unexpected outcome\n")
    result = run("prepare", path)
    checks.equal(result.returncode, 1, "baseline failure exit")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
              "a failed baseline must not arm the guard")


@case("prepare does not arm when lint fails")
def _(repo, checks):
    path = brief(repo, extra="scope: []\n")
    result = run("prepare", path)
    checks.equal(result.returncode, 1, "lint failure exit")
    checks.ok("baseline:" in path.read_text(encoding="utf-8"),
              "lint follows the baseline write")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
              "a failed lint must not arm the guard")


@case("prepare returns structured exit 2 outside a git repository")
def _(repo, checks):
    outside = pathlib.Path(repo).parent / "outside-prepare"
    path = brief(outside)
    result = run("prepare", path, "--json")
    checks.equal(result.returncode, 2, "repository discovery refusal exit")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {}
        checks.ok(False, f"repository discovery stdout must be JSON: {result.stdout!r}")
    checks.equal(data.get("status"), "refused", "repository discovery JSON status")
    checks.ok("not inside a git repository" in data.get("message", ""),
              "repository discovery refusal must retain the cause")
    checks.ok("Traceback" not in result.stderr, "repository discovery must not traceback")


@case("status returns structured exit 2 outside a git repository")
def _(repo, checks):
    outside = pathlib.Path(repo).parent / "outside-status"
    path = brief(outside)
    result = run("status", path, "--json")
    checks.equal(result.returncode, 2, "status repository discovery refusal exit")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {}
        checks.ok(False, f"status discovery stdout must be JSON: {result.stdout!r}")
    checks.equal(data.get("status"), "refused", "status repository discovery JSON status")
    checks.ok("not inside a git repository" in data.get("message", ""),
              "status refusal must retain the cause")
    checks.ok("Traceback" not in result.stderr, "status discovery must not traceback")


@case("prepare refuses before mutation when another brief is active")
def _(repo, checks):
    prepared(repo, "live")
    candidate = brief(repo, "candidate")
    before = hashlib.sha256(candidate.read_bytes()).hexdigest()
    result = run("prepare", candidate)
    after = hashlib.sha256(candidate.read_bytes()).hexdigest()
    checks.equal(result.returncode, 2, "active-brief refusal exit")
    checks.equal(after, before, "candidate bytes must stay unchanged before refusal")
    checks.ok("already active" in result.stdout, "refusal must explain the live brief")


@case("prepare does not arm when an artifact write fails")
def _(repo, checks):
    path = brief(repo)
    prompt = path.with_name("task.generic.md")
    checklist = path.with_name("task.checklist.md")
    checklist.mkdir()
    result = run("prepare", path)
    checks.equal(result.returncode, 2, "artifact write refusal exit")
    checks.ok(prompt.is_file(), "prompt write must precede the failing checklist write")
    checks.ok(checklist.is_dir(), "failed artifact destination must remain untouched")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
              "artifact write failure must happen before activation")


@case("prepare defaults to generic")
def _(repo, checks):
    path = prepared(repo)
    checks.ok(path.with_name("task.generic.md").is_file(), "default prompt is generic")
    checks.ok(not path.with_name("task.claude.md").exists(), "default must not select claude")


@case("verify aggregates strict scope and acceptance findings")
def _(repo, checks):
    path = prepared(repo)
    fixtures.write(repo, "src/outside.py", "value = 1\n")
    result = run("verify", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 1, "verification failure exit")
    checks.ok("scope" in data and "acceptance" in data,
              "verification JSON must include both child verdicts")
    checks.equal(data["scope"]["violations"], 1, "scope violation count")
    checks.equal(data["acceptance"]["failed"], 0, "acceptance still passes")


@case("verify returns 2 when scope cannot decide")
def _(repo, checks):
    path = brief(repo)
    result = run("verify", path)
    checks.equal(result.returncode, 2, "indeterminate scope exit")
    checks.ok("no base to check against" in result.stdout,
              "scope must explain why no verdict was produced")


@case("close deactivates and leaves a tombstone")
def _(repo, checks):
    path = prepared(repo)
    result = run("close", path)
    active = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    tombstone = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    checks.equal(result.returncode, 0, "close exit")
    checks.ok(not active.exists(), "close must remove the active pointer")
    checks.ok(tombstone.is_file() and ".prompire/task.yaml" in tombstone.read_text(),
              "close must retain a tombstone")


@case("close refuses a brief that is not active")
def _(repo, checks):
    live = prepared(repo, "live")
    candidate = brief(repo, "candidate")
    active = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    before = active.read_bytes()
    result = run("close", candidate)
    checks.equal(result.returncode, 2, "mismatched close exit")
    checks.ok(active.exists(), "mismatched close must preserve ACTIVE")
    after = active.read_bytes() if active.exists() else None
    checks.equal(after, before, "mismatched close must preserve ACTIVE bytes")
    active_text = active.read_text(encoding="utf-8") if active.exists() else ""
    checks.ok(active_text.startswith(".prompire/live.yaml\n"),
              "mismatched close must leave the live brief active")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones").exists(),
              "mismatched close must not record a deactivation")
    output = result.stdout.replace("\\", "/")
    checks.ok(live.relative_to(repo).as_posix() in output,
              "mismatched close must identify the active brief")


@case("status reports active, repin, and inactive states")
def _(repo, checks):
    path = prepared(repo)
    active = json_out(run("status", path, "--json"))
    checks.equal(active["status"], "active", "initial status")
    checks.ok(active["base"], "active status includes base")
    closed = run("close", path)
    checks.equal(closed.returncode, 0, "close before inactive status")
    inactive = json_out(run("status", path, "--json"))
    checks.equal(inactive["status"], "inactive", "inactive status")
    again = run("prepare", path)
    checks.equal(again.returncode, 1, "prepare refuses to overwrite an already measured brief")
    # Re-arm through the existing low-level tool after the derived prompt workflow has
    # deliberately refused to overwrite the brief's measured baseline.
    armed = subprocess.run([sys.executable, str(ROOT / "check_scope.py"), str(path), "--activate"],
                           capture_output=True, text=True)
    checks.equal(armed.returncode, 0, "low-level rearm")
    repin = json_out(run("status", path, "--json"))
    checks.equal(repin["status"], "repin", "rearmed status")


@case("low-level subcommands preserve their underlying exit codes")
def _(repo, checks):
    for command, script in (("baseline", "baseline.py"), ("lint", "lint_brief.py"),
                            ("render", "render_brief.py"), ("scope", "check_scope.py")):
        direct = subprocess.run([sys.executable, str(ROOT / script)], capture_output=True, text=True)
        forwarded = run(command)
        checks.equal(forwarded.returncode, direct.returncode,
                     f"{command} must preserve its underlying exit code")


@case("low-level subcommands forward help verbatim")
def _(repo, checks):
    for command, script in (("baseline", "baseline.py"), ("lint", "lint_brief.py"),
                            ("render", "render_brief.py"), ("scope", "check_scope.py")):
        direct = subprocess.run([sys.executable, str(ROOT / script), "--help"],
                                capture_output=True, text=True)
        forwarded = run(command, "--help")
        checks.equal(forwarded.returncode, direct.returncode,
                     f"{command} --help exit must come from the underlying script")
        checks.equal(forwarded.stdout, direct.stdout,
                     f"{command} --help stdout must come from the underlying script")
        checks.equal(forwarded.stderr, direct.stderr,
                     f"{command} --help stderr must come from the underlying script")


@case("low-level subcommands preserve 0, 1, 2 and option forwarding")
def _(repo, checks):
    good = brief(repo, "good")
    measured = subprocess.run([sys.executable, str(ROOT / "baseline.py"), str(good), "--write"],
                              capture_output=True, text=True)
    checks.equal(measured.returncode, 0, "good fixture baseline")
    bad = brief(repo, "bad", extra="scope: []\n")
    probes = (
        ("lint", "lint_brief.py", (good, "--json")),
        ("lint", "lint_brief.py", (bad, "--json")),
        ("baseline", "baseline.py", ()),
    )
    for command, script, arguments in probes:
        direct = subprocess.run([sys.executable, str(ROOT / script), *map(str, arguments)],
                                capture_output=True, text=True)
        forwarded = run(command, *arguments)
        checks.equal(forwarded.returncode, direct.returncode,
                     f"{command} {arguments} exit must be preserved")
        checks.equal(forwarded.stdout, direct.stdout,
                     f"{command} {arguments} stdout must be preserved")
        checks.equal(forwarded.stderr, direct.stderr,
                     f"{command} {arguments} stderr must be preserved")


@case("json mode emits one parseable object and no prose")
def _(repo, checks):
    path = brief(repo)
    result = run("prepare", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 0, "JSON prepare exit")
    checks.equal(data["status"], "prepared", "JSON prepared status")
    checks.equal(result.stderr, "", "JSON mode must not emit child prose to stderr")


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        tool_dir = root / "bin"
        tool_dir.mkdir()
        if os.name == "nt":
            (tool_dir / "python.cmd").write_text(f'"{sys.executable}" %*\n', encoding="utf-8")
        else:
            (tool_dir / "python").symlink_to(sys.executable)
        ENV["PATH"] = str(tool_dir) + os.pathsep + ENV["PATH"]
        for name, fn in CASES:
            repo = fixtures.build(root / name.replace(" ", "-"))
            checks = Checks()
            try:
                fn(repo, checks)
            except Exception as error:
                checks.fails.append(f"unexpected exception: {error}")
            if checks.fails:
                failures += 1
                print(f"FAIL  {name}")
                for failure in checks.fails:
                    print(f"      {failure}")
            else:
                print(f"PASS  {name}")
    print(f"{len(CASES) - failures}/{len(CASES)} CLI cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
