#!/usr/bin/env python3
"""Every tool's stdout is UTF-8, whatever code page the caller's console is set to.

Run: python3 tests/encoding.py
Exit 0 = every tool printed decodable UTF-8 and exited with a code the docs list.

Each case runs a tool as a child with `PYTHONIOENCODING=cp1252` on input carrying Czech
text. That is not an exotic setting: a *redirected* stream on Windows encodes with the
ANSI code page, normally cp1252, and `capture_output=True` — how every caller in this
tree runs these tools — always redirects. cp1252 cannot spell `č`, and it cannot spell
the em dash the linter's own messages use either.

So a tool that lets the platform choose the encoding of its own stdout fails one of two
ways. Either it emits a byte no UTF-8 reader can decode (the em dash becomes the single
byte 0x97, and the caller's strict decode raises instead of parsing a verdict), or it
dies with `UnicodeEncodeError` while *printing a verdict it had already reached*.

The second is why this needs its own suite. A crash on the way out exits 1, and in this
tree exit 1 means "found a finding" — so a tool that died is indistinguishable, from the
outside, from a tool that decided. Checking the exit code alone cannot catch that, which
is why every case also asserts the bytes decode and that no traceback reached stderr.
Those two are the only evidence a caller has that an exit code means what it says.

The hook cases pin the fail direction instead. `hook_scope_guard.py` may not stop
enforcing because it could not spell a path (it did: the write went through), and
`hook_copilot_guard.py` may never exit non-zero, because Copilot CLI reads any non-zero
exit as a denial of a write nobody decided to deny.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
ACTION = SKILL / ".github" / "actions" / "prompire-verify"
sys.path.insert(0, str(HERE))

import fixtures  # noqa: E402

# Two things cp1252 has no code point for, in the two places they actually turn up: a
# path git will report back to us, and prose a verdict quotes.
CZ_PATH = "src/účty.py"
CZ_TEXT = "Opravit český účet"

FAILS = []


def ok(cond, name, detail=""):
    if cond:
        print(f"pass  {name}")
    else:
        print(f"FAIL  {name}" + (f": {detail}" if detail else ""))
        FAILS.append(name)


def show(blob, limit=400):
    return blob[-limit:].decode("utf-8", "backslashreplace").replace("\n", " | ")


def emits_utf8(name, argv, *, stdin=b"", cwd=None, allowed=(0, 1, 2), json_mode=False,
               expect_exit=None, env_extra=None):
    """Run one tool the way Windows runs it, and check what came back off the wire.

    Deliberately captures *bytes* — decoding in the parent with `text=True` would either
    hide the bug behind a replacement character or raise inside `subprocess`, and the
    thing under test is precisely which bytes the child chose to write.
    """
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONDONTWRITEBYTECODE="1")
    env.update(env_extra or {})
    r = subprocess.run([str(a) for a in argv], input=stdin, capture_output=True,
                       cwd=None if cwd is None else str(cwd), env=env)

    ok(b"Traceback" not in r.stderr, f"{name}: reached its exit without a traceback",
       show(r.stderr))
    for label, blob in (("stdout", r.stdout), ("stderr", r.stderr)):
        try:
            blob.decode("utf-8")
            ok(True, f"{name}: {label} decodes as utf-8")
        except UnicodeDecodeError as e:
            ok(False, f"{name}: {label} decodes as utf-8", f"{e} — {show(blob)}")
    if expect_exit is None:
        ok(r.returncode in allowed, f"{name}: exit {r.returncode} is one of {allowed}")
    else:
        ok(r.returncode == expect_exit,
           f"{name}: exit {r.returncode} == {expect_exit}", show(r.stderr))
    if json_mode:
        try:
            json.loads(r.stdout.decode("utf-8"))
            ok(True, f"{name}: stdout parses as json")
        except Exception as e:
            ok(False, f"{name}: stdout parses as json",
               f"{type(e).__name__}: {e} ({len(r.stdout)} bytes of stdout)")
    return r


def tool(name, *args):
    return [sys.executable, str(SKILL / name), *args]


# ---------------------------------------------------------------- briefs on disk only

NO_ACCEPTANCE = """goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
autonomy: ask
base_rev: 0123456789abcdef0123456789abcdef01234567
"""

CZECH_GOAL = f"""goal: {CZ_TEXT} v src/cli/report.py — jeden soubor, nic víc.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: 0123456789abcdef0123456789abcdef01234567
"""

CZECH_KEY = """goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: 0123456789abcdef0123456789abcdef01234567
českýklíč: 1
"""


def brief_cases(tmp):
    """lint_brief.py and render_brief.py need no repository, only a file to read."""
    def put(name, body):
        p = pathlib.Path(tmp) / f"{name}.yaml"
        p.write_text(body, encoding="utf-8")
        return p

    # The em dash lives in the linter's *own* B4 message, so this case carries no
    # non-ASCII input at all — the tool supplies the unencodable character itself.
    emits_utf8("lint/em-dash-in-its-own-message",
               tool("lint_brief.py", put("plain", NO_ACCEPTANCE), "--json"),
               json_mode=True)
    emits_utf8("lint/em-dash-in-its-own-message-text",
               tool("lint_brief.py", put("plain2", NO_ACCEPTANCE)))

    emits_utf8("lint/czech-goal-json",
               tool("lint_brief.py", put("goal", CZECH_GOAL), "--json"), json_mode=True)
    emits_utf8("lint/czech-goal-text",
               tool("lint_brief.py", put("goal2", CZECH_GOAL)))

    # The inversion worth the most: an unknown Czech key is quoted back in the finding,
    # so the tool dies while reporting and exits 1 — the code for "found a finding" —
    # after printing nothing at all.
    emits_utf8("lint/czech-unknown-key-json",
               tool("lint_brief.py", put("key", CZECH_KEY), "--json"), json_mode=True)
    emits_utf8("lint/czech-unknown-key-text",
               tool("lint_brief.py", put("key2", CZECH_KEY)))

    for target in ("claude", "generic", "codex", "agents.md", "claude.md", "checklist"):
        emits_utf8(f"render/czech-goal-{target}",
                   tool("render_brief.py", put("r", CZECH_GOAL), "--target", target))


# ------------------------------------------------------------------ repo-backed tools

def repo_cases(tmp):
    root = fixtures.build(pathlib.Path(tmp) / "repo")
    head = fixtures.git(root, "rev-parse", "HEAD").strip()

    # A tracked file whose *name* cp1252 cannot spell, so every tool that reports on the
    # diff has to print a path it cannot encode.
    fixtures.write(root, CZ_PATH, "def účet():\n    return 1\n")
    fixtures.git(root, "add", "-A")
    fixtures.git(root, "commit", "-qm", "czech path on HEAD")
    head = fixtures.git(root, "rev-parse", "HEAD").strip()

    brief = root / ".prompire" / "cz.yaml"
    brief.write_text(f"""goal: {CZ_TEXT} v {CZ_PATH} — jeden soubor.
scope:
  - {CZ_PATH}
forbidden:
  - golden/**
acceptance:
  - cmd: python3 -c "print('český účet')"
    expect: exit 0
autonomy: ask
base_rev: {head}
""", encoding="utf-8")

    emits_utf8("baseline/czech-brief-json",
               tool("baseline.py", brief, "--json"), cwd=root, json_mode=True)
    emits_utf8("baseline/czech-brief-text", tool("baseline.py", brief), cwd=root)
    emits_utf8("verify-acceptance/czech-cmd-json",
               tool("verify_acceptance.py", brief, "--json"), cwd=root, json_mode=True)
    emits_utf8("verify-acceptance/czech-cmd-text",
               tool("verify_acceptance.py", brief), cwd=root)

    # In scope: the Czech path is named in a clean verdict.
    fixtures.write(root, CZ_PATH, "def účet():\n    return 2\n")
    emits_utf8("check-scope/czech-path-in-scope-json",
               tool("check_scope.py", brief, "--json", "--base", head),
               cwd=root, json_mode=True)
    emits_utf8("check-scope/czech-path-in-scope-text",
               tool("check_scope.py", brief, "--base", head), cwd=root)
    # Through the wrapper: `scope` re-emits check_scope.py's JSON, so a path the child
    # already escaped for its own stdout has to survive being printed a second time.
    emits_utf8("prompire/scope-czech-path-json",
               tool("prompire.py", "scope", str(brief), "--json", "--base", head),
               cwd=root, json_mode=True)

    # Out of scope: the same path is named in a VIOLATION.
    out_of_scope = "docs/účel.md"
    fixtures.write(root, out_of_scope, "účel\n")
    emits_utf8("check-scope/czech-path-violation-json",
               tool("check_scope.py", brief, "--json", "--base", head),
               cwd=root, json_mode=True)
    emits_utf8("check-scope/czech-path-violation-text",
               tool("check_scope.py", brief, "--base", head), cwd=root)

    return root, brief, head


# ------------------------------------------------------- the two hooks, and the runner

def hook_cases(tmp):
    """Both hooks must keep degrading toward *not* enforcing, cp1252 or not.

    A hook that cannot spell the path it wanted to complain about has still reached a
    verdict. Losing it to an encoding error is a silent stop to enforcement, which is
    what `check-scope` catches afterwards — but the hook is supposed to catch it first.
    """
    root = fixtures.build(pathlib.Path(tmp) / "hookrepo")
    brief = root / ".prompire" / "cz.yaml"
    head = fixtures.git(root, "rev-parse", "HEAD").strip()
    brief.write_text(f"""goal: {CZ_TEXT} v src/cart.py.
scope:
  - src/cart.py
forbidden:
  - golden/**
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
autonomy: ask
base_rev: {head}
""", encoding="utf-8")
    subprocess.run(tool("check_scope.py", brief, "--activate"), cwd=str(root),
                   capture_output=True, check=True)

    blocked = str(root / "docs" / "účel.md")     # outside scope, unspellable in cp1252
    allowed = str(root / "src" / "cart.py")

    payload = json.dumps({"tool_name": "Write", "cwd": str(root),
                          "tool_input": {"file_path": blocked}}).encode("utf-8")
    emits_utf8("hook-scope-guard/czech-path-still-blocks",
               tool("hook_scope_guard.py"), stdin=payload, cwd=root, expect_exit=2)

    payload_ok = json.dumps({"tool_name": "Write", "cwd": str(root),
                             "tool_input": {"file_path": allowed}}).encode("utf-8")
    emits_utf8("hook-scope-guard/in-scope-still-allows",
               tool("hook_scope_guard.py"), stdin=payload_ok, cwd=root, expect_exit=0)

    # Copilot CLI denies on any non-zero exit, so this one is exit 0 in both directions
    # and the decision rides on stdout.
    cop = json.dumps({"toolName": "create", "cwd": str(root),
                      "toolArgs": {"path": blocked}}).encode("utf-8")
    r = emits_utf8("hook-copilot-guard/czech-path-denies-on-stdout",
                   tool("hook_copilot_guard.py"), stdin=cop, cwd=root, expect_exit=0)
    try:
        decision = json.loads(r.stdout.decode("utf-8"))
        ok(decision.get("permissionDecision") == "deny",
           "hook-copilot-guard/czech-path-denies-on-stdout: decision is deny",
           r.stdout.decode("utf-8", "backslashreplace"))
    except Exception as e:
        ok(False, "hook-copilot-guard/czech-path-denies-on-stdout: decision is deny",
           f"{type(e).__name__}: {e} ({len(r.stdout)} bytes)")


def runner_cases(tmp, root, head):
    """The GitHub Action's runner prints the same verdict into a log and a summary."""
    work = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    out_file, sum_file = work / "output", work / "summary"
    out_file.touch()
    sum_file.touch()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PROMPIRE_", "GITHUB_", "RUNNER_"))}
    env.update({"PROMPIRE_HOME": str(SKILL), "PROMPIRE_PATH": str(root),
                "PROMPIRE_BASE": head, "GITHUB_OUTPUT": str(out_file),
                "GITHUB_STEP_SUMMARY": str(sum_file), "GITHUB_EVENT_NAME": "push",
                "RUNNER_TEMP": str(work)})
    emits_utf8("action-runner/czech-path-in-annotations",
               [sys.executable, str(ACTION / "runner.py")], cwd=root, env_extra=env)
    for label, f in (("GITHUB_OUTPUT", out_file), ("GITHUB_STEP_SUMMARY", sum_file)):
        blob = f.read_bytes()
        try:
            blob.decode("utf-8")
            ok(True, f"action-runner: {label} is utf-8")
        except UnicodeDecodeError as e:
            ok(False, f"action-runner: {label} is utf-8", f"{e} — {show(blob)}")


def main():
    tmp = tempfile.mkdtemp(prefix="prompire-encoding-")
    keep = "--verbose" in sys.argv
    try:
        brief_cases(tmp)
        root, brief, head = repo_cases(tmp)
        hook_cases(tmp)
        runner_cases(tmp, root, head)
    finally:
        if keep:
            print(f"\nkept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print(f"  {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
