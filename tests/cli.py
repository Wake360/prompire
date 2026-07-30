#!/usr/bin/env python3
"""Transaction tests for the top-level CLI.

Run: python3 tests/cli.py
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

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


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True, env=ENV,
                          cwd=None if cwd is None else str(cwd))


def run_with_replaced_tools(args, replacements):
    with tempfile.TemporaryDirectory(prefix="prompire-cli-tools-") as tmp:
        tool_root = pathlib.Path(tmp)
        for name in ("prompire.py", "check_scope.py", "brief_common.py"):
            shutil.copy2(ROOT / name, tool_root / name)
        for name, body in replacements.items():
            (tool_root / name).write_text(body, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(tool_root / "prompire.py"), *map(str, args)],
            capture_output=True, text=True, env=ENV,
        )


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


@case("draft writes an unconfirmed brief and prepare refuses it as-is")
def _(repo, checks):
    result = run("draft", "Add a health endpoint", "--out", ".prompire/task.yaml", cwd=repo)
    checks.equal(result.returncode, 0, "draft exit")
    path = pathlib.Path(repo) / ".prompire" / "task.yaml"
    text = path.read_text(encoding="utf-8")
    checks.ok("Add a health endpoint" in text, "the sentence must become the goal")
    checks.ok("prompire:unconfirmed" in text, "open items must be visibly unconfirmed")
    blocked = run("prepare", path)
    checks.equal(blocked.returncode, 2, "prepare must refuse an unconfirmed draft")
    confirmed = text.replace("# prompire:unconfirmed", "# confirmed")
    path.write_text(confirmed, encoding="utf-8")
    # scope [] and an empty acceptance still fall over on lint — but with lint's own
    # verdict, not a draft refusal; the gate must not eat the lint result
    after = run("prepare", path)
    checks.ok("draft not confirmed" not in after.stdout + after.stderr,
              "removing the markers must clear the draft gate")


@case("draft proposes only commands the repo evidences")
def _(repo, checks):
    (pathlib.Path(repo) / "package.json").write_text(
        '{"scripts": {"test": "node test.js"}}', encoding="utf-8")
    run("draft", "Tighten input validation", "--out", ".prompire/task.yaml", cwd=repo)
    text = (pathlib.Path(repo) / ".prompire" / "task.yaml").read_text(encoding="utf-8")
    checks.ok("npm test" in text, "the detected script must be proposed")
    checks.ok("detected from package.json scripts.test" in text,
              "every proposal must carry its evidence")


@case("draft invents nothing when the repo evidences nothing")
def _(repo, checks):
    run("draft", "Do the thing", "--out", ".prompire/task.yaml", cwd=repo)
    text = (pathlib.Path(repo) / ".prompire" / "task.yaml").read_text(encoding="utf-8")
    checks.ok("no test command detected" in text, "absence must be stated, not filled")
    checks.ok("npm test" not in text and "pytest" not in text,
              "no invented acceptance commands")


@case("draft refuses to overwrite an existing brief")
def _(repo, checks):
    path = brief(repo)
    before = path.read_bytes()
    result = run("draft", "Another task", "--out", str(path), cwd=repo)
    checks.equal(result.returncode, 2, "draft must not clobber an existing brief")
    checks.equal(path.read_bytes(), before, "the existing brief must keep its bytes")
    checks.ok("already exists" in result.stdout, "the refusal must name the collision")

    planted = pathlib.Path(repo) / ".prompire" / "planted.yaml"
    try:
        planted.symlink_to(pathlib.Path(repo) / "src" / "cart.py")
    except (NotImplementedError, OSError):
        return
    dangling = pathlib.Path(repo) / ".prompire" / "dangling.yaml"
    dangling.symlink_to(pathlib.Path(repo) / "src" / "absent.py")
    for target in (planted, dangling):
        outcome = run("draft", "Another task", "--out", str(target), cwd=repo)
        checks.equal(outcome.returncode, 2, f"draft must refuse the {target.name} symlink")
    checks.ok(not (pathlib.Path(repo) / "src" / "absent.py").exists(),
              "draft must not write through a dangling symlink")


@case("draft defaults to the repo root, wherever it is run from")
def _(repo, checks):
    inner = pathlib.Path(repo) / "src" / "deep"
    inner.mkdir(parents=True, exist_ok=True)
    result = run("draft", "Add a health endpoint", cwd=inner)
    checks.equal(result.returncode, 0, "draft exit")
    root_brief = pathlib.Path(repo) / ".prompire" / "task.yaml"
    checks.ok(root_brief.exists(),
              "the default brief must land where the Action looks for it — the repo root")
    checks.ok(not (inner / ".prompire").exists(),
              "a brief under the working directory is invisible to CI")
    # An --out the caller typed keeps its cwd-relative meaning; only the default moves.
    typed = run("draft", "Another task", "--out", ".prompire/typed.yaml", cwd=inner)
    checks.equal(typed.returncode, 0, "explicit --out exit")
    checks.ok((inner / ".prompire" / "typed.yaml").exists(),
              "an explicit --out must not be silently relocated")


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


@case("prepare survives a non-ASCII goal end to end")
def _(repo, checks):
    # Regression: write_text()/read_text() default to the locale encoding when
    # `encoding=` is omitted — cp1252 on Windows, which raises on this Czech text.
    # baseline.py writes the measured `baseline:` block back into the brief
    # (baseline.py --write), so a non-ASCII `goal` must survive that round trip.
    path = brief(repo, extra="")
    text = path.read_text(encoding="utf-8").replace(
        "goal: Add a count helper to src/cart.py.",
        "goal: Přidej validaci IČO do src/cart.py.")
    path.write_text(text, encoding="utf-8")
    result = run("prepare", path)
    checks.equal(result.returncode, 0,
                 f"prepare on a non-ASCII goal: {result.stdout}{result.stderr}")
    after = path.read_text(encoding="utf-8")
    checks.ok("Přidej validaci IČO" in after,
              "the non-ASCII goal must survive baseline.py's write-back")
    active = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    checks.ok(active.is_file(), "prepare must still arm the guard")


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


@case("prepare replaces a prompt symlink without writing its target")
def _(repo, checks):
    path = brief(repo)
    target = fixtures.write(repo, ".prompire/symlink-target", "keep me\n")
    prompt = path.with_name("task.generic.md")
    try:
        prompt.symlink_to(target)
    except (NotImplementedError, OSError):
        return

    result = run("prepare", path)

    checks.equal(result.returncode, 0, "prepare exit")
    checks.equal(target.read_text(encoding="utf-8"), "keep me\n",
                 "prompt generation must not follow a planted symlink")
    checks.ok(prompt.is_file() and not prompt.is_symlink(),
              "the artifact entry must replace the symlink")


@case("prepare replaces a checklist hardlink without writing its target")
def _(repo, checks):
    path = brief(repo)
    target = fixtures.write(repo, ".prompire/hardlink-target", "keep me\n")
    checklist = path.with_name("task.checklist.md")
    os.link(target, checklist)

    result = run("prepare", path)

    checks.equal(result.returncode, 0, "prepare exit")
    checks.equal(target.read_text(encoding="utf-8"), "keep me\n",
                 "checklist generation must not write through a planted hardlink")
    checks.ok(checklist.is_file() and not os.path.samefile(target, checklist),
              "the artifact entry must replace the hardlink")


@case("prepare defaults to generic")
def _(repo, checks):
    path = prepared(repo)
    checks.ok(path.with_name("task.generic.md").is_file(), "default prompt is generic")
    checks.ok(not path.with_name("task.claude.md").exists(), "default must not select claude")


@case("prepare writes a host-portable scope command for paths with spaces")
def _(repo, checks):
    path = prepared(repo, "task with spaces")
    checklist = path.with_name("task with spaces.checklist.md")
    first_box = next(
        line for line in checklist.read_text(encoding="utf-8").splitlines()
        if line.startswith("- [ ] `")
    )
    if os.name == "nt":
        command = f'prompire scope "{path}" --strict'
    else:
        command = f"prompire scope '{path}' --strict"
    checks.equal(first_box, f"- [ ] `{command}`",
                 "CLI checklist must use the installed command and quote the brief")


@case("verify stops before acceptance on a strict scope finding")
def _(repo, checks):
    path = prepared(repo)
    fixtures.write(repo, "src/outside.py", "value = 1\n")
    result = run("verify", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 1, "verification failure exit")
    checks.ok("scope" in data and "acceptance" in data,
              "verification JSON must include both child verdicts")
    checks.equal(data["scope"]["violations"], 1, "scope violation count")
    checks.equal(data["acceptance"]["status"], "not_run",
                 "acceptance must not run after a strict scope finding")


@case("verify includes acceptance-side writes in the final scope verdict")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/acceptance-write.yaml", """\
goal: Keep generated files inside the declared boundary.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "import pathlib; flag=pathlib.Path('.prompire/run-acceptance'); flag.exists() and pathlib.Path('outside.py').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    prepared_result = run("prepare", path)
    checks.equal(prepared_result.returncode, 0, "prepare exit")
    fixtures.write(repo, ".prompire/run-acceptance", "run\n")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(result.returncode, 1, "acceptance-side scope violation exit")
    checks.ok((pathlib.Path(repo) / "outside.py").is_file(),
              "the fixture acceptance command must make the post-check observable")
    checks.equal(data["acceptance"]["passed"], 1, "acceptance command result")
    checks.equal(data["scope"]["violations"], 1,
                 "final scope verdict must include the acceptance-side write")


@case("verify does not run acceptance for an uncorroborated brief")
def _(repo, checks):
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    path = fixtures.write(repo, ".prompire/uncorroborated.yaml", f"""\
goal: Keep an uncorroborated brief from authorizing commands.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('acceptance-ran').write_text('x')"
    expect: exit 0
base_rev: {head}
baseline:
  - cmd: python -c "import pathlib; pathlib.Path('acceptance-ran').write_text('x')"
    status: pass
    evidence: exit 0, 0 line(s) stdout, 0.0s
autonomy: ask
""")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(result.returncode, 1, "uncorroborated strict-scope exit")
    checks.ok(not (pathlib.Path(repo) / "acceptance-ran").exists(),
              "acceptance must not run before the current brief is corroborated")
    checks.equal(data["scope"]["reviews"], 1, "uncorroborated review count")
    checks.equal(data["acceptance"]["status"], "not_run",
                 "JSON must explain that acceptance did not run")


@case("verify returns 2 when scope cannot decide")
def _(repo, checks):
    path = brief(repo)
    result = run("verify", path)
    checks.equal(result.returncode, 2, "indeterminate scope exit")
    checks.ok("no base to check against" in result.stdout,
              "scope must explain why no verdict was produced")


@case("verify maps invalid acceptance child results to structured exit 2")
def _(repo, checks):
    path = prepared(repo)
    replacements = (
        ("unexpected exit", "print('{}')\nraise SystemExit(7)\n"),
        ("malformed JSON", "print('not-json')\n"),
        ("non-object JSON", "print('[]')\n"),
    )
    if os.name != "nt":
        replacements += (
            ("signal", "import os\nimport signal\nos.kill(os.getpid(), signal.SIGTERM)\n"),
        )

    for label, child in replacements:
        result = run_with_replaced_tools(
            ("verify", path, "--json"),
            {"verify_acceptance.py": child},
        )
        checks.equal(result.returncode, 2, f"{label} exit")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            data = {}
            checks.ok(False, f"{label} stdout must be one JSON object: {result.stdout!r}")
        checks.equal(data.get("status"), "indeterminate", f"{label} JSON status")
        checks.equal(data.get("stage"), "acceptance", f"{label} JSON stage")
        checks.ok("Traceback" not in result.stderr, f"{label} must not traceback")


@case("prepare maps an unexpected child exit to structured exit 2")
def _(repo, checks):
    path = brief(repo)
    result = run_with_replaced_tools(
        ("prepare", path, "--json"),
        {"baseline.py": "raise SystemExit(7)\n"},
    )

    checks.equal(result.returncode, 2, "prepare unexpected-child exit")
    data = json_out(result)
    checks.equal(data.get("status"), "indeterminate", "prepare JSON status")
    checks.equal(data.get("stage"), "baseline", "prepare JSON stage")
    checks.equal(data.get("exit_code"), 7, "prepare must retain the child exit")


@case("close deactivates and leaves a tombstone")
def _(repo, checks):
    path = prepared(repo)
    result = run("close", path)
    active = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    tombstone = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    checks.equal(result.returncode, 0, "close exit")
    checks.ok(not active.exists(), "close must remove the active pointer")
    checks.ok(tombstone.is_file() and ".prompire/task.yaml" in tombstone.read_text(encoding="utf-8"),
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


@case("close checks identity inside the guarded deactivation")
def _(repo, checks):
    requested = prepared(repo, "requested")
    replacement = brief(repo, "replacement")
    state = pathlib.Path(repo) / ".prompire"
    active = state / "ACTIVE"
    lock = state / "ACTIVE.lock"
    lock.mkdir()
    process = subprocess.Popen(
        [sys.executable, str(CLI), "close", str(requested)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV,
    )
    time.sleep(1)
    waiting = process.poll() is None
    active.write_text(".prompire/replacement.yaml\n", encoding="utf-8")
    lock.rmdir()
    stdout, stderr = process.communicate(timeout=15)

    checks.ok(waiting, "close must wait for the guard-state lock")
    checks.equal(process.returncode, 2, "replaced-pointer close exit")
    checks.ok(active.is_file(), "close must preserve the replacement pointer")
    checks.ok(active.read_text(encoding="utf-8").startswith(
        ".prompire/replacement.yaml\n"),
        "close must not remove a brief that replaced the requested one")
    checks.ok(not (state / "ACTIVE.tombstones").exists(),
              "a refused close must not record a deactivation")
    checks.ok(replacement.relative_to(repo).as_posix() in (stdout + stderr).replace("\\", "/"),
              "the refusal must identify the replacement brief")


@case("activation honors the guard-state lock")
def _(repo, checks):
    path = brief(repo)
    state = pathlib.Path(repo) / ".prompire"
    active = state / "ACTIVE"
    lock = state / "ACTIVE.lock"
    lock.mkdir()
    process = subprocess.Popen(
        [sys.executable, str(CLI), "scope", str(path), "--activate"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV,
    )
    time.sleep(1)
    waiting = process.poll() is None
    armed_while_locked = active.exists()
    lock.rmdir()
    stdout, stderr = process.communicate(timeout=15)

    checks.ok(waiting, "activation must wait for the guard-state lock")
    checks.ok(not armed_while_locked, "activation must not write ACTIVE while locked")
    checks.equal(process.returncode, 0, "activation exit")
    checks.ok(active.read_text(encoding="utf-8").startswith(".prompire/task.yaml\n"),
              f"activation must arm after release: {stdout}{stderr}")


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


@case("invalid UTF-8 active briefs follow the unreadable-guard policy")
def _(repo, checks):
    invalid = pathlib.Path(repo) / ".prompire" / "invalid.yaml"
    invalid.write_bytes(b"\xff")
    active = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    active.write_text(".prompire/invalid.yaml\n", encoding="utf-8")

    status_result = run("status", invalid, "--json")
    close_result = run("close", invalid)
    activation_result = run("scope", invalid, "--activate")
    candidate = brief(repo, "candidate")
    prepare_result = run("prepare", candidate)

    checks.equal(status_result.returncode, 0, "status exit")
    try:
        status_data = json.loads(status_result.stdout)
    except json.JSONDecodeError:
        status_data = {}
        checks.ok(False, f"status stdout must be JSON: {status_result.stdout!r}")
    checks.equal(status_data.get("status"), "inactive",
                 "an undecodable brief is not a live guard")
    checks.equal(close_result.returncode, 2, "close refusal exit")
    checks.equal(activation_result.returncode, 2, "invalid activation exit")
    checks.equal(prepare_result.returncode, 0,
                 "prepare may replace a pointer the hook cannot enforce")
    for name, result in (
            ("status", status_result),
            ("close", close_result),
            ("activation", activation_result),
            ("prepare", prepare_result)):
        checks.ok("Traceback" not in result.stderr,
                  f"{name} must not leak a decode traceback")
    checks.ok(active.read_text(encoding="utf-8").startswith(
        ".prompire/candidate.yaml\n"),
        "prepare must replace the dead pointer with the prepared brief")


@case("low-level subcommands preserve their underlying exit codes")
def _(repo, checks):
    for command, script in (("baseline", "baseline.py"), ("lint", "lint_brief.py"),
                            ("render", "render_brief.py"), ("scope", "check_scope.py")):
        direct = subprocess.run([sys.executable, str(ROOT / script)], capture_output=True, text=True)
        forwarded = run(command)
        checks.equal(forwarded.returncode, direct.returncode,
                     f"{command} must preserve its underlying exit code")


@case("Windows Python shim does not echo acceptance commands")
def _(repo, checks):
    if os.name != "nt":
        return
    result = subprocess.run(
        ["python", "-c", "print('ok')"], capture_output=True, text=True, env=ENV)
    checks.equal(result.returncode, 0, "Windows Python shim exit")
    checks.equal(result.stdout, "ok\n",
                 "Windows command echo must not alter acceptance stdout")


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


@case("demo cleanup clears a read-only file before removing it")
def _(repo, checks):
    # Regression: `shutil.rmtree(..., ignore_errors=True)` leaves a demo repo behind
    # on Windows, where every object under `.git/objects` is created read-only and
    # Windows (unlike POSIX, where deletion is a directory-permission question) refuses
    # to unlink a read-only file. `_clear_readonly_and_retry` is the onerror hook that
    # fixes that; tested directly because POSIX would let the naive rmtree pass here
    # even without the fix, so an rmtree-level test alone would not have caught this.
    sys.path.insert(0, str(ROOT))
    import importlib
    prompire_mod = importlib.import_module("prompire")
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "readonly.txt"
        target.write_text("x", encoding="utf-8")
        target.chmod(0o444)
        prompire_mod._clear_readonly_and_retry(os.remove, str(target), None)
        checks.ok(not target.exists(), "the handler must clear read-only and retry")


@case("demo removes its throwaway repo even with a read-only file inside")
def _(repo, checks):
    sys.path.insert(0, str(ROOT))
    import importlib
    prompire_mod = importlib.import_module("prompire")
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "demo-like"
        root.mkdir()
        locked = root / "objects" / "ab"
        locked.mkdir(parents=True)
        locked_file = locked / "cdef0123"
        locked_file.write_text("blob", encoding="utf-8")
        locked_file.chmod(0o444)
        prompire_mod._rmtree(root)
        checks.ok(not root.exists(), "_rmtree must remove a tree containing a "
                  "read-only file, not just the writable parts")


@case("demo shows a clean pass and a caught violation, then cleans up")
def _(repo, checks):
    result = run("demo", cwd=repo)
    checks.equal(result.returncode, 0, f"demo exit ({result.stdout}{result.stderr})")
    low = result.stdout.lower()
    checks.ok("violation" in low, "demo must show the caught out-of-scope write")
    checks.ok("clean" in low or "0 violation" in low,
              "demo must also show the in-scope change passing")
    checks.ok("secrets.cfg" in low, "demo must name the file that drifted out of scope")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
              "demo must not touch the caller's repo state")
    scratch = [line.split(": ", 1)[1] for line in result.stdout.splitlines()
               if line.startswith("demo repo: ")]
    checks.equal(len(scratch), 1, "demo must name its throwaway repo once")
    if scratch:
        checks.ok(not pathlib.Path(scratch[0]).exists(),
                  "demo must remove its throwaway repo without --keep")


@case("demo refuses unrecognized arguments")
def _(repo, checks):
    result = run("demo", "--wat", cwd=repo)
    checks.equal(result.returncode, 2, "demo refusal exit")
    checks.ok("refused" in result.stdout, "the refusal must be legible")


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
            (tool_dir / "python.cmd").write_text(
                f'@"{sys.executable}" %*\n', encoding="utf-8")
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
