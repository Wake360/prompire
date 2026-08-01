# Project Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate agent-assisted drafting and tighten command output, CI references, test diagnostics, status discovery, and documentation.

**Architecture:** Keep the current top-level CLI and the existing schema, policy, and host-adapter seams. Add one private context-managed module inside `prompire.py` for disposable draft snapshots, one private command-display formatter, and one injectable seam in the test runner. Each remaining change stays at its current interface.

**Tech Stack:** Python 3.11+, standard library, PyYAML, Git, GitHub Actions YAML, the repository's existing subprocess-based test harness.

## Global Constraints

- Preserve exit codes: `0` clean, `1` finding, `2` could not decide.
- Preserve Python 3.11+ support on macOS, Linux, and Windows.
- Add no runtime dependency and no brief-schema field.
- Preserve the user's existing unstaged `README.md` changes.
- Do not change `brief_common.py`, `hook_policy.py`, or any host adapter.
- Write the regression test before each behavior change.
- Keep every task independently testable and commit it separately.
- Final verification: `python3 tests/run_all.py --quiet` exits `0`, all thirteen suites show `pass`, and `git diff --check` prints nothing.

---

## File Map

- `prompire.py`: draft snapshot lifecycle, displayed command quoting, optional status path.
- `tests/cli.py`: draft isolation, command display, and status interface regressions.
- `tests/run_all.py`: bounded suite execution and elapsed-time reporting.
- `tests/runner.py`: isolated tests for the test runner itself.
- `tests/docs.py`: reject mutable third-party GitHub Action references.
- `.github/workflows/tests.yml`: pin checkout and setup-python.
- `.github/workflows/prompire.yml`: pin checkout; keep the local action path.
- `.github/actions/prompire-verify/action.yml`: pin setup-python and upload-artifact.
- `references/maintaining.md`: list and document the thirteenth test suite.
- `README.md`: preserve the current edit, document disposable drafting, rewrap prose.
- `SKILL.md`: replace the old post-run mutation-check claim.
- `references/hosts.md`: replace the Antigravity `git status` snapshot description.

---

### Task 1: Run drafting agents in a disposable Git-visible snapshot

**Files:**
- Modify: `prompire.py:409-480`
- Modify: `tests/cli.py:48-51`
- Modify: `tests/cli.py:281-298`

**Interfaces:**
- Consumes: `root: pathlib.Path` returned by `repo_root()` and the existing `_rmtree(root)` cleanup function.
- Produces: `draft_snapshot(root: pathlib.Path)` context manager yielding a temporary `pathlib.Path` repository.
- Preserves: `run_draft_agent(argv, prompt, root)` and `agent_argv(entry, prompt, root)` signatures.

- [ ] **Step 1: Extend the CLI test launcher to accept a test-specific environment**

Change the helper to merge overrides without mutating the suite-global `ENV`:

```python
def run(*args, cwd=None, env=None):
    child_env = dict(ENV, **(env or {}))
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=child_env,
                          cwd=None if cwd is None else str(cwd))
```

- [ ] **Step 2: Replace the old mutation-refusal case with a failing isolation case**

Replace `draft refuses when the agent changed the repository` with a case that starts
with three distinct source states and lets the fake agent overwrite each name:

```python
@case("draft agent writes only inside a disposable snapshot")
def _(repo, checks):
    root = pathlib.Path(repo)
    cart = root / "src" / "cart.py"
    cart.write_text("dirty source\n", encoding="utf-8")
    (root / ".gitignore").write_text(".prompire/\n__pycache__/\n.env\n",
                                      encoding="utf-8")
    ignored = root / ".env"
    ignored.write_text("source secret\n", encoding="utf-8")
    note = root / "notes.txt"
    note.write_text("source note\n", encoding="utf-8")
    (root / "fake_agent.py").write_text(
        "import pathlib, sys\n"
        "sys.stdin.read()\n"
        "assert pathlib.Path('src/cart.py').read_text() == 'dirty source\\n'\n"
        "pathlib.Path('src/cart.py').write_text('agent cart\\n')\n"
        "pathlib.Path('.env').write_text('agent secret\\n')\n"
        "pathlib.Path('notes.txt').write_text('agent note\\n')\n"
        "sys.stdout.write('goal: x\\nscope: [src/cart.py]\\n')\n",
        encoding="utf-8")
    cmd = f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} fake_agent.py"
    temp_root = root / "draft-temp"
    temp_root.mkdir()
    result = run("draft", "Improve the cart", "--agent-cmd", cmd,
                 "--out", root / ".prompire" / "agent.yaml", cwd=root,
                 env={"TMPDIR": str(temp_root), "TMP": str(temp_root),
                      "TEMP": str(temp_root)})

    checks.equal(result.returncode, 0, "snapshot draft exit")
    checks.equal(cart.read_text(encoding="utf-8"), "dirty source\n",
                 "tracked dirty source stays unchanged")
    checks.equal(ignored.read_text(encoding="utf-8"), "source secret\n",
                 "ignored source stays unchanged")
    checks.equal(note.read_text(encoding="utf-8"), "source note\n",
                 "untracked source stays unchanged")
    checks.equal(list(temp_root.iterdir()), [], "draft snapshot is removed")
```

- [ ] **Step 3: Run the CLI suite and verify the new test fails for the old reason**

Run: `python3 tests/cli.py`

Expected: exit `1`; `draft agent writes only inside a disposable snapshot` fails because
the source files were changed or because the old status comparison refuses the draft.

- [ ] **Step 4: Add the snapshot context manager**

Add `contextlib` to the imports. Replace `repo_state()` with this private implementation:

```python
def _git_visible_paths(root):
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others",
         "--exclude-standard", "-z"],
        capture_output=True,
    )
    if listed.returncode:
        message = listed.stderr.decode("utf-8", "replace").strip()
        raise OSError(message or "git could not list the repository files")
    return [pathlib.Path(os.fsdecode(raw))
            for raw in listed.stdout.split(b"\0") if raw]


def _copy_snapshot_entry(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        target.symlink_to(os.readlink(source), target_is_directory=source.is_dir())
    else:
        shutil.copy2(source, target)


@contextlib.contextmanager
def draft_snapshot(root):
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix="prompire-draft-"))
    try:
        for rel in _git_visible_paths(root):
            source = root / rel
            if os.path.lexists(source):
                _copy_snapshot_entry(source, snapshot / rel)
        commands = (
            ["git", "init", "-q"],
            ["git", "add", "-A"],
            ["git", "-c", "user.email=draft@prompire",
             "-c", "user.name=prompire-draft", "-c", "commit.gpgsign=false",
             "commit", "--allow-empty", "-qm", "draft snapshot"],
        )
        for command in commands:
            subprocess.run(command, cwd=str(snapshot), check=True,
                           capture_output=True)
        yield snapshot
    finally:
        _rmtree(snapshot)
```

Do not decode the NUL-delimited Git path list with `errors="replace"`; `os.fsdecode`
preserves undecodable filesystem bytes with the platform's surrogate policy.

- [ ] **Step 5: Route the agent process through the snapshot**

In `draft()`, delete the `before = repo_state(root)` / `after = repo_state(root)` block.
Build host arguments only after the snapshot exists, so `{root}` points at the disposable
repository:

```python
try:
    with draft_snapshot(root) as agent_root:
        if args.agent:
            argv, feed = agent_argv(DRAFT_AGENTS[args.agent], prompt, agent_root)
        else:
            argv, feed = shlex.split(args.agent_cmd), prompt
        if not argv:
            return report_refusal("--agent-cmd is empty")
        answered, trouble = run_draft_agent(argv, feed, agent_root)
except (OSError, subprocess.CalledProcessError) as exc:
    return report_refusal(f"could not build the draft snapshot: {exc}")
```

Keep `agent_draft_text(args.sentence, data, root)` pointed at the source root. Its
acceptance detection and tracked-path notes describe the source checkout, not the
synthetic snapshot commit.

- [ ] **Step 6: Add direct cleanup coverage for exceptional exits**

Import `draft_snapshot` in the existing internal-function test block and add:

```python
snapshot_path = None
try:
    with draft_snapshot(pathlib.Path(repo)) as made:
        snapshot_path = made
        raise RuntimeError("stop inside snapshot")
except RuntimeError:
    pass
checks.ok(snapshot_path is not None and not snapshot_path.exists(),
          "snapshot cleanup runs when draft processing raises")
```

The context manager has one `finally` path, so agent failure, timeout, malformed YAML,
and successful output all use the same cleanup mechanism.

- [ ] **Step 7: Run focused and full regression tests**

Run: `python3 tests/cli.py`

Expected: exit `0`; `43/43 CLI cases pass` because this task replaces one case and adds
its exceptional-cleanup assertion to an existing case.

Run: `python3 tests/encoding.py`

Expected: exit `0`; final line `0 failure(s)`.

- [ ] **Step 8: Commit the isolated drafting change**

```bash
git add prompire.py tests/cli.py
git commit -m "fix: isolate agent-assisted drafting"
```

---

### Task 2: Quote every displayed next-step command

**Files:**
- Modify: `prompire.py:156-167`
- Modify: `prompire.py:483-486`
- Modify: `tests/cli.py:187-235`
- Modify: `tests/cli.py:914-921`

**Interfaces:**
- Produces: `display_command(argv: list[str]) -> str`.
- Consumes: only human-facing argument vectors; subprocess execution remains unchanged.

- [ ] **Step 1: Add failing POSIX, Windows, text, and JSON assertions**

Import `prompire` in a small test case and pin both platform renderings:

```python
@case("displayed next commands quote brief paths")
def _(repo, checks):
    sys.path.insert(0, str(ROOT))
    try:
        import prompire
        original = prompire.os.name
        prompire.os.name = "posix"
        checks.equal(prompire.display_command(["prompire", "verify", "task brief.yaml"]),
                     "prompire verify 'task brief.yaml'", "POSIX command")
        prompire.os.name = "nt"
        checks.equal(prompire.display_command(["prompire", "verify", "task brief.yaml"]),
                     'prompire verify "task brief.yaml"', "Windows command")
    finally:
        prompire.os.name = original
        sys.path.remove(str(ROOT))
```

In `json mode emits one parseable object and no prose`, replace `brief(repo)` with
`brief(repo, "task brief")`, then assert:

```python
checks.ok("task brief.yaml" in data["next"], "JSON next command keeps the path")
checks.ok("'task brief.yaml'" in data["next"] or '"task brief.yaml"' in data["next"],
          "JSON next command quotes the path")
```

In `draft writes an unconfirmed brief and prepare refuses it as-is`, change both the
`--out` value and `path` to `.prompire/task brief.yaml`, then add:

```python
checks.ok("'" in result.stdout or '"' in result.stdout,
          "draft confirmation quotes the path with spaces")
```

- [ ] **Step 2: Run the CLI suite and verify the quoting assertions fail**

Run: `python3 tests/cli.py`

Expected: exit `1`; the new case fails because `display_command` does not exist and the
current next command contains an unquoted path.

- [ ] **Step 3: Implement one command-display formatter and use it twice**

Add near the reporting functions:

```python
def display_command(argv):
    parts = [str(part) for part in argv]
    return (subprocess.list2cmdline(parts) if os.name == "nt"
            else shlex.join(parts))
```

Change `report_prepared()` to:

```python
next_command = display_command(["prompire", "verify", brief])
```

Change the draft confirmation to:

```python
next_command = display_command(["prompire", "prepare", out])
print(f"confirm every `# {DRAFT_MARKER}` line, then: {next_command}")
```

- [ ] **Step 4: Run the focused tests**

Run: `python3 tests/cli.py`

Expected: exit `0`; all CLI cases pass.

- [ ] **Step 5: Commit the command rendering change**

```bash
git add prompire.py tests/cli.py
git commit -m "fix: quote displayed CLI commands"
```

---

### Task 3: Make `prompire status` default to the current repository

**Files:**
- Modify: `prompire.py:723-729`
- Modify: `prompire.py:782-785`
- Modify: `tests/cli.py:418-432`
- Modify: `tests/cli.py:730-748`

**Interfaces:**
- Consumes: optional `args.brief: str`, defaulting to `.`.
- Preserves: existing text and JSON result objects.

- [ ] **Step 1: Add failing default-path cases**

Extend `status reports active, repin, and inactive states` immediately after preparation:

```python
defaulted = json_out(run("status", "--json", cwd=repo))
checks.equal(defaulted, active, "status without a path uses cwd")
explicit_dir = json_out(run("status", ".", "--json", cwd=repo))
checks.equal(explicit_dir, active, "status accepts an explicit directory")
```

Extend the outside-repository case:

```python
defaulted = run("status", "--json", cwd=outside)
checks.equal(defaulted.returncode, 2, "default status outside a repo refuses")
```

- [ ] **Step 2: Run the CLI suite and verify argument parsing fails**

Run: `python3 tests/cli.py`

Expected: exit `1`; the default-path assertions fail because `brief` is required.

- [ ] **Step 3: Make the positional optional and distinguish directories from files**

Change parser construction to:

```python
stated.add_argument("brief", nargs="?", default=".")
```

Change repository discovery in `status()` to:

```python
candidate = pathlib.Path(args.brief)
start = candidate.resolve() if candidate.is_dir() else candidate.resolve().parent
try:
    root = repo_root(start)
except RepoError as exc:
    return report_refusal(str(exc), args.json)
```

This keeps a nonexistent explicit brief path anchored at its parent while letting the
default `.` start discovery inside the current repository.

- [ ] **Step 4: Run focused tests**

Run: `python3 tests/cli.py`

Expected: exit `0`; all CLI cases pass.

- [ ] **Step 5: Commit the status interface change**

```bash
git add prompire.py tests/cli.py
git commit -m "feat: default status to current repository"
```

---

### Task 4: Bound test-suite execution and report durations

**Files:**
- Create: `tests/runner.py`
- Modify: `tests/run_all.py:1-47`
- Modify: `references/maintaining.md:26-43`
- Modify: `references/maintaining.md:44-65`

**Interfaces:**
- Produces: `run_suite(path: pathlib.Path, timeout: float) -> dict` with keys
  `returncode`, `stdout`, `stderr`, `seconds`, and `timed_out`.
- Produces: injectable `main(suites=SUITES, here=HERE, timeout=SUITE_TIMEOUT, argv=None)`.
- Sets: `SUITE_TIMEOUT = 900` seconds for production runs.

- [ ] **Step 1: Write the isolated runner regression suite**

Create `tests/runner.py`:

```python
#!/usr/bin/env python3
import contextlib
import io
import pathlib
import tempfile

import run_all


def main():
    with tempfile.TemporaryDirectory(prefix="prompire-runner-") as tmp:
        root = pathlib.Path(tmp)
        (root / "slow.py").write_text(
            "import time\nprint('started', flush=True)\ntime.sleep(10)\n",
            encoding="utf-8")
        sentinel = root / "fast-ran"
        (root / "fast.py").write_text(
            "import pathlib\n"
            f"pathlib.Path({str(sentinel)!r}).write_text('yes')\n",
            encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_all.main(suites=("slow.py", "fast.py"), here=root,
                                timeout=0.1, argv=["--quiet"])
        text = output.getvalue()
        assert code == 1, text
        assert sentinel.read_text() == "yes"
        assert "FAIL  slow.py" in text and "timeout" in text
        assert "pass  fast.py" in text
        assert "s" in next(line for line in text.splitlines() if "fast.py" in line)
    print("3/3 runner cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add `runner.py` to `SUITES` and confirm the old runner fails it**

Insert `"runner.py"` before `"package.py"` in `tests/run_all.py`.

Run: `python3 tests/runner.py`

Expected: non-zero exit because the old `main()` does not accept injected suites,
directory, timeout, or argv.

- [ ] **Step 3: Implement bounded suite execution**

Add `time`, set `SUITE_TIMEOUT = 900`, and implement:

```python
def _captured_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def run_suite(path, timeout):
    started = time.monotonic()
    try:
        result = subprocess.run([sys.executable, str(path)], capture_output=True,
                                text=True, encoding="utf-8", timeout=timeout)
        return {"returncode": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr,
                "seconds": time.monotonic() - started, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": 1, "stdout": _captured_text(exc.stdout),
                "stderr": _captured_text(exc.stderr),
                "seconds": time.monotonic() - started, "timed_out": True}
```

Refactor `main()` without changing its no-argument CLI:

```python
def main(suites=SUITES, here=HERE, timeout=SUITE_TIMEOUT, argv=None):
    args = sys.argv if argv is None else argv
    quiet = "--quiet" in args
    results = []
    for suite in suites:
        result = run_suite(here / suite, timeout)
        results.append((suite, result))
        if not quiet or result["returncode"]:
            print(f"===== {suite} =====")
            if result["stdout"].strip():
                print(result["stdout"].rstrip())
            if result["stderr"].strip():
                print(result["stderr"].rstrip())
            if result["timed_out"]:
                print(f"timed out after {timeout:g}s")
    print("\n===== summary =====")
    for suite, result in results:
        mark = "pass" if result["returncode"] == 0 else "FAIL"
        suffix = " timeout" if result["timed_out"] else ""
        print(f"{mark}  {suite}  {result['seconds']:.1f}s{suffix}")
    return 1 if any(result["returncode"] for _, result in results) else 0
```

- [ ] **Step 4: Run the new runner suite**

Run: `python3 tests/runner.py`

Expected: exit `0`; output `3/3 runner cases pass`.

- [ ] **Step 5: Document the thirteenth suite**

Add `runner.py` to the `tests/` layout block in `references/maintaining.md`:

```text
  runner.py           suite timeout, continuation, and timing output
```

Add its standalone command to the individual suite list:

```text
python3 tests/runner.py        run-all timeout and duration reporting
```

- [ ] **Step 6: Run the complete runner once**

Run: `python3 tests/run_all.py --quiet`

Expected: exit `0`; thirteen summary rows start with `pass`, each ends with a duration
such as `0.4s`, and one row is `pass  runner.py`.

- [ ] **Step 7: Commit the runner diagnostics change**

```bash
git add tests/run_all.py tests/runner.py references/maintaining.md
git commit -m "test: bound suite execution and report timing"
```

---

### Task 5: Pin every third-party GitHub Action reference

**Files:**
- Modify: `tests/docs.py:579-718`
- Modify: `.github/workflows/tests.yml:19-20`
- Modify: `.github/workflows/tests.yml:33-34`
- Modify: `.github/workflows/prompire.yml:11`
- Modify: `.github/actions/prompire-verify/action.yml:84`
- Modify: `.github/actions/prompire-verify/action.yml:113`

**Interfaces:**
- Produces: `action_pin_problems() -> list[str]` inside the documentation consistency suite.
- Enforces: local `./` references are allowed; every external `owner/repo@ref` uses forty lowercase hexadecimal characters.

- [ ] **Step 1: Add a failing documentation consistency check**

Add this function to `tests/docs.py`:

```python
def action_pin_problems():
    out = []
    pattern = re.compile(r"^\s*(?:-\s*)?uses:\s+(\S+)", re.M)
    pinned = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
    paths = set((SKILL / ".github").rglob("*.yml"))
    paths.update((SKILL / ".github").rglob("*.yaml"))
    for path in sorted(paths):
        rel = path.relative_to(SKILL).as_posix()
        for ref in pattern.findall(path.read_text(encoding="utf-8")):
            if ref.startswith("./"):
                continue
            if not pinned.fullmatch(ref):
                out.append(f"{rel} uses mutable third-party action `{ref}`")
    return out
```

Append `problems += action_pin_problems()` in `main()` beside the other documentation
consistency checks.

- [ ] **Step 2: Run the docs suite and verify all mutable references are named**

Run: `python3 tests/docs.py`

Expected: exit `1`; findings name `actions/checkout@v7`, `actions/setup-python@v7`, and
`actions/upload-artifact@v7`. The local `./.github/actions/prompire-verify` reference is
not reported.

- [ ] **Step 3: Pin checkout and setup-python using the already-reviewed publish SHAs**

Replace every remaining `actions/checkout@v7` under `.github/` with:

```yaml
uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7
```

Replace every remaining `actions/setup-python@v7` under `.github/` with:

```yaml
uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7
```

Preserve each file's existing indentation and list marker.

- [ ] **Step 4: Pin upload-artifact v7.0.0**

In `.github/actions/prompire-verify/action.yml`, replace the mutable reference with the
signed v7.0.0 release commit:

```yaml
uses: actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f  # v7.0.0
```

- [ ] **Step 5: Run documentation and CI wiring tests**

Run: `python3 tests/docs.py`

Expected: exit `0`; final output contains `0 inconsistencies`.

Run: `python3 tests/ci.py`

Expected: exit `0`; `27/27 cases pass`.

- [ ] **Step 6: Commit the pinned action references**

```bash
git add tests/docs.py .github/workflows/tests.yml .github/workflows/prompire.yml .github/actions/prompire-verify/action.yml
git commit -m "ci: pin all third-party actions"
```

---

### Task 6: Align user and maintainer documentation with the implemented behavior

**Files:**
- Modify: `README.md:43-60`
- Modify: `README.md:182-191`
- Modify: `SKILL.md:20-29`
- Modify: `references/hosts.md:32-38`

**Interfaces:**
- Consumes: the behavior delivered by Tasks 1-5.
- Produces: documentation that makes no stronger isolation claim than the code provides.

- [ ] **Step 1: Replace the old `git status` claim in the README**

Preserve the user's surrounding README edits. Replace the sentences at current lines
55-58 with:

```markdown
Agent-assisted drafting runs in a disposable repository containing the checkout's
current tracked and untracked, non-ignored files. The agent can inspect and change that
snapshot, but those writes do not land in the source checkout. Ignored files are not
copied. This isolates ordinary repository writes; it does not sandbox network,
credentials, or explicitly addressed paths elsewhere on the machine. Read every
`# prompire:unconfirmed` line, fix it, then delete the marker: `prompire prepare`
refuses while one remains.
```

- [ ] **Step 2: Rewrap the existing long README sentence without changing its meaning**

Change current lines 188-191 to:

```markdown
over, and it is capped at ~250 words: on the benchmark's contract tasks it was the
acceptance criteria, not the wording around them, that carried the outcome. It does not
judge whether the work is good — only whether it stayed inside what was declared, and
whether what was declared was pinned before the work began.
```

- [ ] **Step 3: Align the skill and host reference**

Replace the `SKILL.md` mutation-refusal sentence with:

```markdown
Agent-assisted drafting runs against a disposable Git-visible snapshot, not the source
checkout. The snapshot excludes ignored files and is removed after the agent exits.
```

Replace the Antigravity paragraph in `references/hosts.md` with:

```markdown
Headless `agy` has no read-only mode. `draft` therefore runs it in the same disposable
Git-visible snapshot used for every drafting host. Writes made relative to its workspace
land in the snapshot, which is removed after the run; this is isolation of the checkout,
not a machine-wide sandbox.
```

- [ ] **Step 4: Run documentation checks and inspect the README diff**

Run: `python3 tests/docs.py`

Expected: exit `0`; final output contains `0 inconsistencies`.

Run: `git diff --check`

Expected: exit `0` with no output.

Run: `git diff -- README.md SKILL.md references/hosts.md`

Expected: the user's existing README additions remain; only the obsolete drafting claim
and long-line wrapping change within them. `SKILL.md` and `hosts.md` describe the same
snapshot limits.

- [ ] **Step 5: Commit the documentation alignment**

```bash
git add README.md SKILL.md references/hosts.md
git commit -m "docs: explain isolated agent drafting"
```

---

### Task 7: Final verification

**Files:**
- Verify only; no planned edits.

**Interfaces:**
- Consumes: all six completed task commits.
- Produces: an evidence-backed release-ready verdict.

- [ ] **Step 1: Run the full suite**

Run: `python3 tests/run_all.py --quiet`

Expected: exit `0`; the summary contains thirteen `pass` rows, including
`pass  runner.py`, and no `FAIL` rows.

- [ ] **Step 2: Check whitespace and the exact worktree scope**

Run: `git diff --check HEAD~6..HEAD`

Expected: exit `0` with no output.

Run: `git status --short`

Expected: no unexpected files. If the README documentation commit deliberately included
the user's pre-existing edit, the worktree is clean because that edit is now part of
Task 6's reviewed commit.

- [ ] **Step 3: Review the final commit sequence**

Run: `git log -7 --oneline`

Expected: six implementation commits after the plan/design history, in this order:

```text
docs: explain isolated agent drafting
ci: pin all third-party actions
test: bound suite execution and report timing
feat: default status to current repository
fix: quote displayed CLI commands
fix: isolate agent-assisted drafting
```

- [ ] **Step 4: Stop on any mismatch**

Do not claim completion if a suite fails, a timeout occurs, `git diff --check` prints a
path, or `git status --short` names an unreviewed file. Fix the responsible task, rerun
its focused command, then repeat Steps 1-3.
