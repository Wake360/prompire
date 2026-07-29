# Host-Neutral Prompire CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one cross-platform `prompire` command that prepares and verifies briefs without launching or controlling a coding agent.

**Architecture:** Keep the existing Python scripts as the authority for baseline measurement, linting, rendering, and scope enforcement. Add a small orchestration module that calls those tools in a fixed order, plus a verifier that runs safe acceptance commands after the agent stops. Package the root modules as an installable Python CLI while retaining every current script entry point.

**Tech Stack:** Python 3.11+, standard library, PyYAML 6+, setuptools, GitHub Actions.

## Global Constraints

- Support macOS, Linux, and Windows.
- Do not launch, supervise, or select a coding agent.
- Do not duplicate scope, tests-policy, baseline, or rendering semantics.
- Preserve all current script entry points and renderer output.
- Preserve exit codes: `0` means success, `1` means a finding, and `2` means no trustworthy decision could be made.
- Arm `.prompire/ACTIVE` only after baseline, lint, rendering, and artifact writes succeed.
- Never deactivate automatically. Closing a guard must remain an explicit action that leaves a tombstone.
- Keep prompt targets at the existing 250-word limit.
- Use `generic` as the default host-neutral render target.
- Do not add dependencies beyond PyYAML and packaging tools.

---

## File Map

### Create

- `prompire.py` — console entry point, argument parsing, tool orchestration, artifact writing.
- `verify_acceptance.py` — post-work execution and evaluation of acceptance commands.
- `pyproject.toml` — package metadata and the `prompire` console script.
- `agents/openai.yaml` — Codex skill-list metadata.
- `tests/cli.py` — transactional CLI and low-level passthrough tests.
- `tests/verify.py` — acceptance-verifier tests.
- `tests/package.py` — source-tree and installed-entry-point smoke tests.

### Modify

- `check_scope.py` — expose a read-only active-brief query used by CLI preflight.
- `tests/e2e.py` — pin the read-only active-brief query against real repositories.
- `tests/run_all.py` — include the three new test suites.
- `.github/workflows/tests.yml` — add macOS and Windows coverage.
- `SKILL.md` — make the two-command workflow primary.
- `README.md` — add installation and host-neutral quickstart.
- `references/hosts.md` — distinguish the universal CLI from optional host hooks.
- `references/maintaining.md` — document new files and release checks.
- `tests/docs.py` — require the CLI commands and metadata to stay documented.
- `VERSION` — release as `0.6.0`.
- `CHANGELOG.md` — record the CLI, packaging, compatibility, and limits.

---

### Task 1: Expose Read-Only Guard Status

**Files:**

- Modify: `check_scope.py:128-220`
- Modify: `tests/e2e.py`

**Interfaces:**

- Consumes: `read_pointer(root)`, `_loads(path)`.
- Produces: `active_brief(root: pathlib.Path) -> str | None`.
- Invariant: the query uses the same definition of “live guard” as `activate()`.

- [ ] **Step 1: Write the failing end-to-end case**

Add this case near the existing activation cases in `tests/e2e.py`:

```python
@case("active-brief-query-matches-activation")
def _(repo, c):
    sys.path.insert(0, str(SKILL))
    from check_scope import active_brief

    p, _ = measured(repo, "status", """
goal: Keep the cart behavior unchanged.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")

    c.ok(active_brief(pathlib.Path(repo)) is None, "nothing is active before arming")
    armed = tool("check_scope.py", p, "--activate")
    c.ok(armed.returncode == 0, armed.stdout + armed.stderr)
    c.ok(active_brief(pathlib.Path(repo)) == ".prompire/status.yaml",
         "the query returns the brief the guard enforces")

    dead = pathlib.Path(repo) / ".prompire" / "missing.yaml"
    (pathlib.Path(repo) / ".prompire" / "ACTIVE").write_text(
        ".prompire/missing.yaml\n", encoding="utf-8")
    c.ok(not dead.exists() and active_brief(pathlib.Path(repo)) is None,
         "a pointer to an unreadable brief is not a live guard")
```

- [ ] **Step 2: Run the case and confirm the missing interface**

Run:

```bash
python3 tests/e2e.py
```

Expected: exit `1`; `active-brief-query-matches-activation` fails because `active_brief` cannot be imported.

- [ ] **Step 3: Add the shared query**

Add below `_loads()` in `check_scope.py`:

```python
def active_brief(root):
    """The repo-relative brief enforced by the live pointer, or None."""
    cur = read_pointer(root)
    rel = cur["brief"]
    return rel if rel and _loads(pathlib.Path(root) / rel) else None
```

Replace the first live-pointer condition in `activate()`:

```python
    live = active_brief(root)
    if live and live != rel_brief:
        print(f"refused: `{live}` is already active here, and arming a second "
              "brief would overwrite what was recorded for it.\nrun `check_scope.py "
              "--deactivate` first — turning a guard off is meant to leave a trace")
        return 2
```

Do not change same-brief pin comparison or pointer-writing behavior.

- [ ] **Step 4: Run enforcement tests**

Run:

```bash
python3 tests/e2e.py
python3 tests/hook.py
```

Expected:

- `58/58 end-to-end cases pass`.
- `172/172 hook cases` pass.

- [ ] **Step 5: Commit**

```bash
git add check_scope.py tests/e2e.py
git commit -m "refactor: expose active brief status"
```

---

### Task 2: Add Post-Work Acceptance Verification

**Files:**

- Create: `verify_acceptance.py`
- Create: `tests/verify.py`

**Interfaces:**

- Consumes: `load_brief()`, `acceptance_entries()`, `baseline_map()`, `entry_key()`, `effective_transition()`, `baseline.classify()`, `baseline.run_one()`, `check_scope.repo_root()`.
- Produces: `verify(path: str) -> dict` and `main(argv: list[str]) -> int`.
- JSON result:

```json
{
  "brief": ".prompire/task.yaml",
  "passed": 2,
  "failed": 1,
  "not_run": 0,
  "results": []
}
```

- [ ] **Step 1: Write verifier cases**

Create `tests/verify.py` using the existing `tests.fixtures` helpers. Cover:

```python
CASES = (
    "green criterion remains green",
    "flip criterion passes after the fix",
    "failed criterion returns exit 1",
    "unsafe criterion is not executed",
    "unreadable brief returns exit 2",
    "before_after digest mismatch returns exit 1",
)
```

For the unsafe case, use:

```yaml
acceptance:
  - cmd: python -c "open('should-not-exist', 'w').write('x')"
    expect: exit 0
    requires: [writes-repo]
```

Assert that `should-not-exist` does not exist after verification.

For digest comparison, record a baseline whose evidence contains:

```text
exit 0, 1 line(s) stdout, 0.0s, sha256:2cf24dba5fb0
```

Then change the command output and assert that the result names the expected and actual digest.

- [ ] **Step 2: Run the new suite and confirm it fails**

Run:

```bash
python3 tests/verify.py
```

Expected: nonzero exit because `verify_acceptance.py` does not exist.

- [ ] **Step 3: Implement the verifier**

Create `verify_acceptance.py` with these public functions:

```python
#!/usr/bin/env python3
import json
import pathlib
import re
import sys

from baseline import classify, run_one
from brief_common import (
    BriefError,
    acceptance_entries,
    baseline_map,
    effective_transition,
    entry_key,
    load_brief,
    norm_cmd,
)
from check_scope import RepoError, repo_root

DIGEST = re.compile(r"\bsha256:([0-9a-f]{12})\b")


def expected_digest(entry):
    match = DIGEST.search(str((entry or {}).get("evidence") or ""))
    return match.group(1) if match else None


def verify(path):
    brief = load_brief(path)
    root = repo_root(pathlib.Path(path).resolve().parent)
    before = baseline_map(brief)
    results = []

    for acceptance in acceptance_entries(brief):
        reason = classify(acceptance)
        current = ({"status": "not_runnable", "reason": reason}
                   if reason else run_one(root, acceptance))
        baseline = before.get(entry_key(acceptance))
        transition = effective_transition(acceptance, baseline)
        ok = current.get("status") == "pass"

        want_digest = expected_digest(baseline)
        got_digest = expected_digest(current)
        if acceptance.get("before_after") and want_digest:
            ok = ok and got_digest == want_digest

        results.append({
            "cmd": norm_cmd(acceptance.get("cmd")),
            "transition": transition,
            "status": current.get("status"),
            "ok": ok,
            "evidence": current.get("evidence"),
            "reason": current.get("reason"),
            "expected_digest": want_digest,
            "actual_digest": got_digest,
        })

    return {
        "brief": str(path),
        "passed": sum(1 for result in results if result["ok"]),
        "failed": sum(1 for result in results
                      if not result["ok"] and result["status"] != "not_runnable"),
        "not_run": sum(1 for result in results
                       if result["status"] == "not_runnable"),
        "results": results,
    }
```

Implement `main(argv)` so:

- Missing or unreadable input returns `2`.
- `--json` prints only the JSON object.
- Text output prints one `PASS`, `FAIL`, or `NOT RUN` line per command.
- Any `FAIL` or `NOT RUN` returns `1`.
- An empty acceptance list returns `1`, even though the linter should already reject it.

Do not execute entries refused by `baseline.classify()`.

- [ ] **Step 4: Run verifier and regression tests**

Run:

```bash
python3 tests/verify.py
python3 tests/e2e.py
python3 tests/battery.py
```

Expected:

- All verifier cases pass.
- `58/58 end-to-end cases pass`.
- `45/45 cases pass`.

- [ ] **Step 5: Commit**

```bash
git add verify_acceptance.py tests/verify.py
git commit -m "feat: verify acceptance after agent work"
```

---

### Task 3: Add the Transactional CLI

**Files:**

- Create: `prompire.py`
- Create: `tests/cli.py`

**Interfaces:**

- Consumes: the existing script entry points plus `active_brief()` and `verify_acceptance.py`.
- Produces:

```text
prompire prepare BRIEF [--target generic|claude|codex|copilot] [--json]
prompire verify BRIEF [--ack-disarms DIGEST] [--json]
prompire close BRIEF
prompire status BRIEF [--json]
prompire baseline ...
prompire lint ...
prompire render ...
prompire scope ...
```

- Artifact names: `<brief-stem>.<target>.md` and `<brief-stem>.checklist.md`, beside the brief.

- [ ] **Step 1: Write CLI transaction tests**

Create `tests/cli.py`. Use temporary git repositories and subprocesses. Add these cases:

```text
prepare writes baseline, prompt, checklist, then ACTIVE
prepare does not arm when baseline fails
prepare does not arm when lint fails
prepare refuses before mutation when another brief is active
prepare defaults to generic
verify aggregates strict scope and acceptance findings
verify returns 2 when scope cannot decide
close deactivates and leaves a tombstone
status reports active, repin, and inactive states
low-level subcommands preserve their underlying exit codes
json mode emits one parseable object and no prose
```

In the “another brief is active” case, hash the candidate brief before and after the failed command and assert the bytes are unchanged.

- [ ] **Step 2: Run the CLI suite and confirm it fails**

Run:

```bash
python3 tests/cli.py
```

Expected: nonzero exit because `prompire.py` does not exist.

- [ ] **Step 3: Implement process isolation and parsing**

Create `prompire.py` with:

```python
#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import pathlib
import subprocess
import sys

from check_scope import active_brief, read_pointer, repo_root

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = {
    "baseline": "baseline.py",
    "lint": "lint_brief.py",
    "render": "render_brief.py",
    "scope": "check_scope.py",
    "acceptance": "verify_acceptance.py",
}
PROMPT_TARGETS = ("generic", "claude", "codex", "copilot")


def run_tool(name, *args):
    return subprocess.run(
        [sys.executable, str(HERE / TOOLS[name]), *map(str, args)],
        capture_output=True,
        text=True,
    )


def emit_process(result):
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode
```

Use `argparse` subparsers for the five primary commands. Forward unparsed arguments only for `baseline`, `lint`, `render`, and `scope`.

Define:

```python
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    return args.handler(args, extra)


def entrypoint():
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
```

- [ ] **Step 4: Implement `prepare`**

Implement this exact order:

```python
def prepare(args, extra):
    brief = pathlib.Path(args.brief)
    root = repo_root(brief.resolve().parent)
    live = active_brief(root)
    if live:
        return report_refusal(
            f"`{live}` is already active; run `prompire close {live}` first",
            json_mode=args.json,
        )

    measured = run_tool("baseline", brief, "--write")
    if measured.returncode:
        return report_stage("baseline", measured, args.json)

    linted = run_tool("lint", brief, "--json")
    if linted.returncode:
        return report_stage("lint", linted, args.json)

    prompt = run_tool("render", brief, "--target", args.target)
    if prompt.returncode:
        return report_stage("render", prompt, args.json)

    checklist = run_tool("render", brief, "--target", "checklist")
    if checklist.returncode:
        return report_stage("render", checklist, args.json)

    prompt_path = brief.with_name(f"{brief.stem}.{args.target}.md")
    checklist_path = brief.with_name(f"{brief.stem}.checklist.md")
    try:
        prompt_path.write_text(prompt.stdout, encoding="utf-8")
        checklist_path.write_text(checklist.stdout, encoding="utf-8")
    except OSError as exc:
        return report_refusal(f"could not write artifacts: {exc}", args.json)

    armed = run_tool("scope", brief, "--activate")
    if armed.returncode:
        return report_stage("activate", armed, args.json)

    return report_prepared(
        brief=brief,
        prompt=prompt_path,
        checklist=checklist_path,
        target=args.target,
        json_mode=args.json,
    )
```

`report_prepared()` must print the exact next command:

```text
prompire verify <brief>
```

The two generated artifacts are derived files and may be overwritten on a later successful preparation. The brief and guard state may not be overwritten.

- [ ] **Step 5: Implement `verify`, `close`, and `status`**

`verify` runs both checks unless either returns exit `2`:

```python
scope_args = [args.brief, "--strict", "--json"]
if args.ack_disarms:
    scope_args += ["--ack-disarms", args.ack_disarms]
scope = run_tool("scope", *scope_args)
if scope.returncode == 2:
    return report_stage("scope", scope, args.json)

acceptance = run_tool("acceptance", args.brief, "--json")
if acceptance.returncode == 2:
    return report_stage("acceptance", acceptance, args.json)

return report_verification(scope, acceptance, args.json)
```

`report_verification()` returns `1` if either child returns `1`; otherwise `0`. Its JSON contains both parsed child objects under `scope` and `acceptance`.

`close` forwards:

```text
check_scope.py BRIEF --deactivate
```

`status` is read-only. It prints:

- `inactive` when `active_brief(root)` is `None`.
- `active` with the brief and base when a live pointer has `repin: false`.
- `repin` with the brief and base when `repin: true`.

- [ ] **Step 6: Run CLI and existing workflow tests**

Run:

```bash
python3 tests/cli.py
python3 tests/e2e.py
python3 tests/golden.py
```

Expected:

- Every CLI case passes.
- `58/58 end-to-end cases pass`.
- `35/35 renderer snapshots match`.

- [ ] **Step 7: Commit**

```bash
git add prompire.py tests/cli.py
git commit -m "feat: add transactional prompire CLI"
```

---

### Task 4: Package the CLI Without Moving Existing Modules

**Files:**

- Create: `pyproject.toml`
- Create: `tests/package.py`
- Modify: `tests/run_all.py:10-12`

**Interfaces:**

- Produces the console entry point `prompire = prompire:entrypoint`.
- Supports `python -m prompire`.
- Keeps direct commands such as `python3 baseline.py` working.

- [ ] **Step 1: Write packaging smoke tests**

Create `tests/package.py` to assert:

```python
import pathlib
import subprocess
import sys
import tempfile
import tomllib
import venv

ROOT = pathlib.Path(__file__).resolve().parent.parent
data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

assert data["project"]["requires-python"] == ">=3.11"
assert data["project"]["scripts"]["prompire"] == "prompire:entrypoint"
assert data["project"]["dependencies"] == ["PyYAML>=6"]

for cmd in (
    [sys.executable, str(ROOT / "prompire.py"), "--help"],
    [sys.executable, "-m", "prompire", "--help"],
):
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "prepare" in result.stdout
    assert "verify" in result.stdout

with tempfile.TemporaryDirectory() as tmp:
    env = pathlib.Path(tmp) / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env)
    scripts = env / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    command = scripts / ("prompire.exe" if sys.platform == "win32" else "prompire")

    installed = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps",
         "--no-build-isolation", str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    result = subprocess.run(
        [str(command), "--help"],
        cwd=tmp,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "prepare" in result.stdout
    assert "verify" in result.stdout
```

- [ ] **Step 2: Run the smoke test and confirm it fails**

Run:

```bash
python3 tests/package.py
```

Expected: nonzero exit because `pyproject.toml` does not exist.

- [ ] **Step 3: Add package metadata**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "prompire"
version = "0.6.0"
description = "Compile coding-agent requests into checkable briefs."
readme = "README.md"
requires-python = ">=3.11"
license = {file = "LICENSE"}
dependencies = ["PyYAML>=6"]

[project.scripts]
prompire = "prompire:entrypoint"

[tool.setuptools]
py-modules = [
  "prompire",
  "baseline",
  "brief_common",
  "check_scope",
  "hook_policy",
  "hook_scope_guard",
  "hook_copilot_guard",
  "lint_brief",
  "render_brief",
  "verify_acceptance",
]
```

Do not move the current modules into a package in this release. Moving them would combine distribution work with an unrelated import migration.

- [ ] **Step 4: Add suites to the master runner**

Change `tests/run_all.py`:

```python
SUITES = (
    "battery.py",
    "e2e.py",
    "examples.py",
    "golden.py",
    "docs.py",
    "hook.py",
    "verify.py",
    "cli.py",
    "package.py",
)
```

- [ ] **Step 5: Run package and full tests**

Run:

```bash
python3 tests/package.py
python3 tests/run_all.py --quiet
```

Expected:

- Package smoke test exits `0`.
- The summary lists nine passing suites.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/package.py tests/run_all.py
git commit -m "build: package prompire as a Python CLI"
```

---

### Task 5: Prove the Workflow on macOS, Linux, and Windows

**Files:**

- Modify: `.github/workflows/tests.yml`
- Modify: `tests/cli.py`

**Interfaces:**

- Full security suite remains pinned on Linux and macOS.
- Cross-platform CLI workflow runs on all three operating systems.

- [ ] **Step 1: Remove platform-specific commands from CLI fixtures**

In `tests/cli.py`, use acceptance commands that work under the GitHub Actions Python setup:

```yaml
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
```

Use `pathlib` for paths. Do not assert slash direction in user-facing paths; normalize with:

```python
text.replace("\\", "/")
```

- [ ] **Step 2: Expand the workflow**

Replace `.github/workflows/tests.yml` with:

```yaml
name: tests
on: [push, pull_request]

jobs:
  full:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ["3.11", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install PyYAML
      - run: python tests/run_all.py

  cli-windows:
    runs-on: windows-latest
    strategy:
      matrix:
        python: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install PyYAML
      - run: python tests/battery.py
      - run: python tests/golden.py
      - run: python tests/docs.py
      - run: python tests/verify.py
      - run: python tests/cli.py
      - run: python tests/package.py
```

Do not claim that the host hooks are Windows-tested by this job. It verifies the universal CLI, not host hook installation.

- [ ] **Step 3: Run the local platform-independent suites**

Run:

```bash
python3 tests/battery.py
python3 tests/golden.py
python3 tests/docs.py
python3 tests/verify.py
python3 tests/cli.py
python3 tests/package.py
```

Expected: every command exits `0`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml tests/cli.py
git commit -m "ci: test the CLI across desktop platforms"
```

---

### Task 6: Make the Two-Command Path the Product Surface

**Files:**

- Create: `agents/openai.yaml`
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `references/hosts.md`
- Modify: `references/maintaining.md`
- Modify: `tests/docs.py`

**Interfaces:**

- Primary workflow:

```text
prompire prepare .prompire/task.yaml --target generic
prompire verify .prompire/task.yaml
```

- Existing script workflow remains documented as the diagnostic path.

- [ ] **Step 1: Add failing documentation assertions**

Extend `tests/docs.py` with:

```python
def cli_problems():
    out = []
    skill = read("SKILL.md")
    readme = read("README.md")
    pyproject = read("pyproject.toml")

    for command in ("prompire prepare", "prompire verify", "prompire close"):
        if command not in skill:
            out.append(f"SKILL.md does not document `{command}`")
        if command not in readme:
            out.append(f"README.md does not document `{command}`")

    if 'prompire = "prompire:entrypoint"' not in pyproject:
        out.append("pyproject.toml does not expose the prompire command")

    metadata = SKILL / "agents" / "openai.yaml"
    if not metadata.is_file():
        out.append("missing agents/openai.yaml")
    return out
```

Call `cli_problems()` from the existing problem aggregation.

- [ ] **Step 2: Run the docs suite and confirm it fails**

Run:

```bash
python3 tests/docs.py
```

Expected: exit `1`, naming undocumented commands and missing `agents/openai.yaml`.

- [ ] **Step 3: Add Codex discovery metadata**

Create `agents/openai.yaml`:

```yaml
interface:
  display_name: "Prompire"
  short_description: "Create checkable briefs for coding agents"
  default_prompt: "Use $prompire to turn this coding request into a measured, bounded brief."
```

- [ ] **Step 4: Rewrite the top of `SKILL.md` around the CLI**

Keep the YAML frontmatter limited to `name` and `description`. Rewrite the description to begin with its trigger:

```yaml
---
name: prompire
description: Use when delegating substantial coding work, recovering from an agent run that drifted or gamed its checks, or writing a checkable agent brief. Turns a short request into bounded scope, executable acceptance criteria, a measured baseline, declared autonomy, a rendered prompt, and an independent post-run verdict.
---
```

Replace the current multi-script opening with:

````markdown
## Primary workflow

After writing `.prompire/<slug>.yaml`:

```bash
prompire prepare .prompire/<slug>.yaml --target generic
```

Hand the generated prompt to any coding agent. Prompire does not launch it.

After the agent stops:

```bash
prompire verify .prompire/<slug>.yaml
```

Review the generated checklist, then close the guard explicitly:

```bash
prompire close .prompire/<slug>.yaml
```
````

Retain the existing detailed workflow below under `## Diagnostic commands`. Do not delete the explanation of `pin`, `repin`, `base uncorroborated`, or `--base`.

- [ ] **Step 5: Add installation and universal workflow to `README.md`**

Add:

````markdown
## Install the CLI

```bash
pipx install prompire
# or
uv tool install prompire
```

Prompire supports Python 3.11+ on macOS, Linux, and Windows.

## Host-neutral workflow

```bash
prompire prepare .prompire/task.yaml --target generic
# give .prompire/task.generic.md to any coding agent
prompire verify .prompire/task.yaml
# review .prompire/task.checklist.md
prompire close .prompire/task.yaml
```

The CLI does not launch an agent. Claude Code and Copilot CLI hooks are optional early-warning adapters; the final git-diff check is host-neutral.
````

- [ ] **Step 6: Update host and maintenance references**

In `references/hosts.md`, add a host matrix with these exact claims:

| Surface | Any agent | Claude Code | Copilot CLI |
|---|---:|---:|---:|
| Generic rendered prompt | yes | yes | yes |
| Post-run git diff verdict | yes | yes | yes |
| Pre-write hook | no | yes | yes |
| Agent launching | no | no | no |

In `references/maintaining.md`, add `prompire.py`, `verify_acceptance.py`, `pyproject.toml`, and the three new suites to the layout and test command list.

- [ ] **Step 7: Run skill and docs validation**

Run:

```bash
python3 tests/docs.py
python3 /Users/filipvachek/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

Expected:

- `16 enforced rules, 0 inconsistencies`.
- `Skill is valid!`.

- [ ] **Step 8: Commit**

```bash
git add agents/openai.yaml SKILL.md README.md references/hosts.md references/maintaining.md tests/docs.py
git commit -m "docs: make the host-neutral CLI the primary workflow"
```

---

### Task 7: Release and Final Verification

**Files:**

- Modify: `VERSION`
- Modify: `CHANGELOG.md`

**Interfaces:**

- Releases version `0.6.0`.
- Records that the YAML schema and existing script commands remain compatible.

- [ ] **Step 1: Add the release entry**

Set `VERSION` to:

```text
0.6.0
```

Add the first changelog heading:

```markdown
## 0.6.0 — 2026-07-29

**Prompire now has a host-neutral, cross-platform command.**

### Added

- `prompire prepare`, which measures, lints, renders, writes artifacts, and arms in that order.
- `prompire verify`, which combines the strict git-diff verdict with post-work acceptance checks.
- `prompire status` and `prompire close`.
- `pipx`, `uv tool`, and `python -m prompire` entry points.
- CLI workflow coverage for macOS, Linux, and Windows.

### Compatibility

- Existing YAML briefs are unchanged.
- Existing Python script entry points remain supported.
- Existing renderer output remains byte-identical.

### Limits

- The CLI does not launch or supervise agents.
- Generic hosts do not receive a pre-write hook. They receive the rendered contract and the post-run git-diff verdict.
- Commands declared unsafe or environment-dependent are reported as `NOT RUN`; Prompire does not execute them automatically.
```

- [ ] **Step 2: Run the complete local verification**

Run:

```bash
python3 tests/run_all.py
python3 /Users/filipvachek/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
git diff --check
```

Expected:

- All nine suites pass.
- `Skill is valid!`.
- `git diff --check` prints no output and exits `0`.

- [ ] **Step 3: Inspect generated output**

In a temporary git repository, prepare a measured brief:

```bash
python3 /Users/filipvachek/prompire/prompire.py prepare .prompire/task.yaml --target generic
```

Confirm:

- `.prompire/task.yaml` contains measured `base_rev` and `baseline`.
- `.prompire/task.generic.md` is at most 250 words.
- `.prompire/task.checklist.md` starts with the independent scope check.
- `.prompire/ACTIVE` exists only after both artifacts exist.
- The final line names `prompire verify .prompire/task.yaml`.

- [ ] **Step 4: Commit**

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: release prompire 0.6.0"
```

---

## Final Success Criteria

Run:

```bash
python3 tests/run_all.py
python3 /Users/filipvachek/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
git diff --check
```

Check:

- Nine test suites report `pass`.
- The skill validator prints `Skill is valid!`.
- `git diff --check` prints nothing.
- `prompire prepare` never writes `.prompire/ACTIVE` after a failed baseline, lint, render, or artifact write.
- `prompire verify` returns nonzero for scope violations, test-policy findings, failed acceptance commands, or acceptance commands it safely refuses to run.
- `prompire close` is the only high-level command that deactivates the guard.
- Existing direct script commands and golden renderer snapshots are unchanged.
- CI passes on macOS, Linux, and Windows.
