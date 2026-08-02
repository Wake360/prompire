#!/usr/bin/env python3
"""Transaction tests for the top-level CLI.

Run: python3 tests/cli.py
"""
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

import yaml

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


def run(*args, cwd=None, env=None):
    child_env = dict(ENV, **(env or {}))
    return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8",
                          env=child_env,
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
            capture_output=True, text=True, encoding="utf-8", env=ENV,
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
    result = run("draft", "Add a health endpoint", "--out", ".prompire/task brief.yaml", cwd=repo)
    checks.equal(result.returncode, 0, "draft exit")
    checks.ok("'" in result.stdout or '"' in result.stdout,
              "draft confirmation quotes the path with spaces")
    path = pathlib.Path(repo) / ".prompire" / "task brief.yaml"
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


def fake_agent(repo, reply):
    """An --agent-cmd stand-in: ignores the drafting prompt, prints a canned reply."""
    (pathlib.Path(repo) / "fake_agent.py").write_text(
        "import sys\nsys.stdin.read()\n"
        "sys.stdout.write(open('fake_reply.txt', encoding='utf-8').read())\n",
        encoding="utf-8")
    (pathlib.Path(repo) / "fake_reply.txt").write_text(reply, encoding="utf-8")
    return f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} fake_agent.py"


@case("draft --agent-cmd delegates, then marks the boundary and the judge")
def _(repo, checks):
    (pathlib.Path(repo) / "package.json").write_text(
        '{"scripts": {"test": "node test.js"}}', encoding="utf-8")
    cmd = fake_agent(repo, """```yaml
# confirmed by the agent itself
goal: Sharpen the cart maths and keep the table readable.
scope: [src/cart.py, src/mystery.py]
forbidden: [tests/**]
tests_policy: authoring
acceptance:
  - cmd: npm test
    expect: exit 0
  - cmd: sh scripts/made-up.sh
autonomy: auto
manual_checks: [the table still reads well]
```
""")
    result = run("draft", "Improve the cart", "--agent-cmd", cmd,
                 "--out", ".prompire/agent.yaml", cwd=repo)
    checks.equal(result.returncode, 0, "draft exit")
    text = (pathlib.Path(repo) / ".prompire" / "agent.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()

    def line_with(fragment):
        return next((li for li in lines if fragment in li), "")

    checks.ok("Sharpen the cart maths" in text, "the agent's sharpened goal must be kept")
    checks.ok("prompire:unconfirmed" in line_with("src/cart.py"),
              "an agent-proposed boundary entry must carry the marker")
    checks.ok("nothing tracked" in line_with("src/mystery.py"),
              "a boundary entry matching no tracked file must say so")
    checks.ok("detected from package.json scripts.test" in line_with("npm test"),
              "an evidenced command must carry its evidence")
    checks.ok("agent-proposed" in line_with("made-up"),
              "an unevidenced command must be named as the agent's own claim")
    checks.equal(text.count("expect: exit 0"), 2,
                 "an entry without expect must get the exit 0 default")
    checks.ok("prompire:unconfirmed" in line_with("tests_policy: authoring"),
              "relaxed test protection must carry the marker")
    checks.ok("autonomy: ask" in text and "autonomy: auto" not in text,
              "a draft always asks, whatever the agent proposed")
    checks.ok("confirmed by the agent itself" not in text,
              "the agent's own comments must not survive into the draft")
    checks.ok("tests/**" in text, "forbidden must be carried over")
    checks.ok("the table still reads well" in text, "manual_checks must be carried over")
    blocked = run("prepare", pathlib.Path(repo) / ".prompire" / "agent.yaml", cwd=repo)
    checks.equal(blocked.returncode, 2, "prepare must refuse an unconfirmed agent draft")


@case("draft --agent-cmd falls back to the sentence and to empty acceptance")
def _(repo, checks):
    cmd = fake_agent(repo, "scope: [src/cart.py]\n")
    result = run("draft", "Improve the cart", "--agent-cmd", cmd,
                 "--out", ".prompire/agent.yaml", cwd=repo)
    checks.equal(result.returncode, 0, "draft exit")
    text = (pathlib.Path(repo) / ".prompire" / "agent.yaml").read_text(encoding="utf-8")
    checks.ok("Improve the cart" in text,
              "a reply without a goal must fall back to the request sentence")
    checks.ok("acceptance: []" in text and "prompire:unconfirmed" in text,
              "a reply without acceptance must state the absence, unconfirmed")


@case("draft --agent-cmd refuses output it cannot verify as a brief")
def _(repo, checks):
    out = pathlib.Path(repo) / ".prompire" / "agent.yaml"
    replies = {
        "prose": "You should widen the scope and trust me.\n",
        "measured baseline": "goal: x\nbaseline: []\n",
        "unknown key": "goal: x\nplot_twist: 1\n",
        "malformed acceptance": "goal: x\nacceptance:\n  - expect: exit 0\n",
    }
    for label, reply in replies.items():
        cmd = fake_agent(repo, reply)
        result = run("draft", "Improve the cart", "--agent-cmd", cmd,
                     "--out", str(out), cwd=repo)
        checks.equal(result.returncode, 2, f"{label} must be refused")
        checks.ok(not out.exists(), f"{label} must not leave a file behind")
    checks.ok("baseline" in run("draft", "x", "--agent-cmd", fake_agent(
        repo, "goal: x\nbaseline: []\n"), "--out", str(out), cwd=repo).stdout,
        "a drafted baseline refusal must say what was refused")

    (pathlib.Path(repo) / "fake_agent.py").write_text(
        "import sys\nsys.exit(3)\n", encoding="utf-8")
    cmd = f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} fake_agent.py"
    failed = run("draft", "Improve the cart", "--agent-cmd", cmd,
                 "--out", str(out), cwd=repo)
    checks.equal(failed.returncode, 2, "a failing agent must be a refusal")
    checks.ok(not out.exists(), "a failing agent must not leave a file behind")
    missing = run("draft", "Improve the cart", "--agent-cmd",
                  "prompire-no-such-binary-xyz", "--out", str(out), cwd=repo)
    checks.equal(missing.returncode, 2, "a missing agent binary must be a refusal")


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
    # The agent records where it ran, by absolute path: an empty temp root at the end
    # is equally true of a snapshot that was never made there, so the emptiness check
    # only means "removed" once this one says a snapshot was really made there.
    where = root / "agent-cwd.txt"
    (root / "fake_agent.py").write_text(
        "import os, pathlib, sys\n"
        "sys.stdin.read()\n"
        f"pathlib.Path({where.as_posix()!r}).write_text(os.getcwd())\n"
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
    ran_in = where.read_text(encoding="utf-8").strip() if where.exists() else ""
    checks.ok(bool(ran_in) and pathlib.Path(ran_in).resolve().is_relative_to(
        temp_root.resolve()), f"the agent must run in a snapshot under {temp_root}, "
        f"not in {ran_in or '(nothing recorded)'}")
    checks.equal(list(temp_root.iterdir()), [], "draft snapshot is removed")


@case("draft snapshot re-targets the symlinks it carries and drops the rest")
def _(repo, checks):
    # A symlink recreated verbatim points back out of the snapshot: an ordinary
    # relative write by the agent then lands wherever the link aims, which for an
    # absolute target is the caller's own checkout.
    root = pathlib.Path(repo)
    outside = root.parent / (root.name + "-outside")
    outside.mkdir(exist_ok=True)
    (outside / "outside.txt").write_text("outside secret\n", encoding="utf-8")
    for name in ("secret_abs.txt", "secret_rel.txt", "secret_dotdot.txt"):
        (root / name).write_text("source secret\n", encoding="utf-8")
    (root / "deep").mkdir(exist_ok=True)
    links = {
        "abs_in.txt": root / "secret_abs.txt",         # absolute, resolves inside
        "rel_in.txt": pathlib.Path("secret_rel.txt"),  # relative, resolves inside
        "deep/dotdot_in.txt": pathlib.Path("..") / "secret_dotdot.txt",
        "dangling_in.txt": pathlib.Path("absent_in.txt"),
        "dir_in": pathlib.Path("src"),                 # symlink to a directory inside
        "abs_out.txt": outside / "outside.txt",        # resolves outside
        "dangling_out.txt": outside / "absent_out.txt",
        "mid.txt": outside / "outside.txt",
        "two_hop.txt": pathlib.Path("mid.txt"),        # inside, but escapes in two hops
    }
    try:
        for name, target in links.items():
            (root / name).symlink_to(target)
    except (NotImplementedError, OSError):
        return
    subprocess.run(["git", "-c", "user.email=t@example", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", "add", "-A"],
                   cwd=str(root), check=True, capture_output=True)

    carried = ("abs_in.txt", "rel_in.txt", "deep/dotdot_in.txt", "dangling_in.txt")
    dropped = ("abs_out.txt", "dangling_out.txt", "mid.txt", "two_hop.txt")
    report = root / "link-report.txt"
    (root / "fake_agent.py").write_text(
        "import json, pathlib, sys\n"
        "sys.stdin.read()\n"
        f"carried = {list(carried)!r}\n"
        f"dropped = {list(dropped)!r}\n"
        "seen = {}\n"
        "for name in carried + dropped:\n"
        "    seen[name] = pathlib.Path(name).is_symlink()\n"
        "    pathlib.Path(name).write_text('agent wrote ' + name + '\\n')\n"
        "seen['dir_in'] = pathlib.Path('dir_in').is_symlink()\n"
        "pathlib.Path('dir_in/inside.py').write_text('agent wrote through dir\\n')\n"
        f"pathlib.Path({report.as_posix()!r}).write_text(json.dumps(seen))\n"
        "sys.stdout.write('goal: x\\nscope: [src/cart.py]\\n')\n",
        encoding="utf-8")
    cmd = f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} fake_agent.py"
    out = root / ".prompire" / "agent.yaml"
    result = run("draft", "Improve the cart", "--agent-cmd", cmd, "--out", out, cwd=root)
    checks.equal(result.returncode, 0,
                 f"draft exit beside symlinks: {result.stdout}{result.stderr}")
    checks.ok(out.exists(), "the draft must still be written")

    for name in ("secret_abs.txt", "secret_rel.txt", "secret_dotdot.txt"):
        checks.equal((root / name).read_text(encoding="utf-8"), "source secret\n",
                     f"a link inside the repo must not carry a write into {name}")
    checks.equal((outside / "outside.txt").read_text(encoding="utf-8"),
                 "outside secret\n", "a link out of the repo must not carry a write")
    for absent in (root / "absent_in.txt", outside / "absent_out.txt",
                   root / "src" / "inside.py"):
        checks.ok(not absent.exists(),
                  f"the agent must not create {absent} in the source checkout")

    seen = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    for name in carried + ("dir_in",):
        # Kept, but re-aimed at the snapshot's own copy — including a link that dangles
        # there, since the decision is where the target resolves, not whether it exists.
        checks.equal(seen.get(name), True, f"{name} must reach the agent as a symlink")
    for name in dropped:
        checks.equal(seen.get(name), False,
                     f"{name} resolves outside the repository and must not be carried")


@case("draft snapshots a repo holding a submodule and a nested checkout")
def _(repo, checks):
    # `git ls-files` reports both as one *directory* entry: a gitlink under --cached, a
    # nested checkout under --others. Copying either as a file is an OSError, which the
    # draft turns into a refusal — every repo with a submodule would lose agent drafting.
    root = pathlib.Path(repo)

    def git(*command, cwd):
        subprocess.run(["git", "-c", "user.email=t@example", "-c", "user.name=t",
                        "-c", "commit.gpgsign=false", *command],
                       cwd=str(cwd), check=True, capture_output=True)

    nested = root / "nested"
    nested.mkdir()
    (nested / "inner.txt").write_text("inner\n", encoding="utf-8")
    git("init", "-q", cwd=nested)
    sub = root / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("sub\n", encoding="utf-8")
    git("init", "-q", cwd=sub)
    git("add", "-A", cwd=sub)
    git("commit", "-qm", "sub", cwd=sub)
    head = subprocess.run(["git", "-C", str(sub), "rev-parse", "HEAD"],
                          capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{head},sub", cwd=root)

    out = root / ".prompire" / "agent.yaml"
    # The snapshot deliberately carries neither: a submodule's contents belong to its
    # own repository, and a nested checkout is not this repository's to copy.
    (root / "fake_agent.py").write_text(
        "import pathlib, sys\n"
        "sys.stdin.read()\n"
        "assert not pathlib.Path('sub').exists()\n"
        "assert not pathlib.Path('nested').exists()\n"
        "sys.stdout.write('goal: x\\nscope: [src/cart.py]\\n')\n",
        encoding="utf-8")
    cmd = f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} fake_agent.py"
    result = run("draft", "Improve the cart", "--agent-cmd", cmd,
                 "--out", out, cwd=root)
    checks.equal(result.returncode, 0,
                 f"draft exit beside a submodule: {result.stdout}{result.stderr}")
    checks.ok(out.exists(), "the draft must still be written")


@case("draft snapshot does not run the caller's global git hooks")
def _(repo, checks):
    # The snapshot's own commit is machinery, not the caller's commit. A global
    # `core.hooksPath` or `init.templateDir` — what `pre-commit init-templatedir`
    # writes — would otherwise run the caller's hooks against a synthetic tree, and a
    # hook that exits non-zero would make agent drafting impossible on that machine.
    root = pathlib.Path(repo)
    home = root / "fake-home"
    marker = root / "hook-ran.txt"
    body = f"#!/bin/sh\necho ran >> {marker.as_posix()}\nexit 1\n"
    for rel in ("hooks/pre-commit", "hooks/post-commit", "template/hooks/pre-commit"):
        hook = home / rel
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(body, encoding="utf-8")
        hook.chmod(0o755)
    (home / ".gitconfig").write_text(
        f"[core]\n\thooksPath = {(home / 'hooks').as_posix()}\n"
        f"[init]\n\ttemplateDir = {(home / 'template').as_posix()}\n", encoding="utf-8")
    out = root / ".prompire" / "agent.yaml"
    (root / "fake_agent.py").write_text(
        "import sys\nsys.stdin.read()\n"
        "sys.stdout.write('goal: x\\nscope: [src/cart.py]\\n')\n", encoding="utf-8")
    cmd = f"{shlex.quote(pathlib.Path(sys.executable).as_posix())} fake_agent.py"
    # A synthetic HOME is how git is made to read that config; it also hides a PyYAML
    # installed under the real home, so the child is told where to find it again.
    site = str(pathlib.Path(yaml.__file__).resolve().parent.parent)
    path = os.pathsep.join([site] + ([ENV["PYTHONPATH"]] if ENV.get("PYTHONPATH") else []))
    result = run("draft", "Improve the cart", "--agent-cmd", cmd, "--out", out,
                 cwd=root, env={"HOME": str(home), "PYTHONPATH": path,
                                "GIT_CONFIG_GLOBAL": str(home / ".gitconfig")})
    checks.equal(result.returncode, 0,
                 f"draft exit under a failing global hook: {result.stdout}{result.stderr}")
    checks.ok(not marker.exists(), "no hook of the caller's may run for the snapshot")
    checks.ok(out.exists(), "the draft must still be written")


@case("draft agent flags are validated before anything runs")
def _(repo, checks):
    unknown = run("draft", "x", "--agent", "gemini", cwd=repo)
    checks.equal(unknown.returncode, 2, "unknown --agent must be refused")
    checks.ok("claude" in unknown.stdout and "codex" in unknown.stdout,
              "the refusal must name the known agents")
    sys.path.insert(0, str(ROOT))
    try:
        from prompire import DRAFT_AGENTS
    finally:
        sys.path.remove(str(ROOT))
    argv = DRAFT_AGENTS.get("codex", [])
    checks.ok("read-only" in argv,
              "the codex drafting invocation must keep the sandbox read-only")
    checks.ok("--ignore-user-config" in argv,
              "the codex drafting invocation must not load personal instructions")
    checks.ok("antigravity" in unknown.stdout,
              "the refusal must name the antigravity agent too")
    agy_argv = DRAFT_AGENTS.get("antigravity", [])
    checks.ok("{prompt}" in agy_argv and "{root}" in agy_argv,
              "the antigravity invocation must carry both placeholders — agy reads "
              "neither the prompt from stdin nor an untrusted cwd as a workspace")
    sys.path.insert(0, str(ROOT))
    try:
        from prompire import agent_argv, draft_snapshot
    finally:
        sys.path.remove(str(ROOT))
    snapshot_path = None
    try:
        with draft_snapshot(pathlib.Path(repo)) as made:
            snapshot_path = made
            raise RuntimeError("stop inside snapshot")
    except RuntimeError:
        pass
    checks.ok(snapshot_path is not None and not snapshot_path.exists(),
              "snapshot cleanup runs when draft processing raises")
    sub, feed = agent_argv(["agy", "-p", "{prompt}", "--add-dir", "{root}"],
                           "draft this", pathlib.Path(repo))
    checks.equal(sub, ["agy", "-p", "draft this", "--add-dir",
                       str(pathlib.Path(repo))],
                 "placeholders must be substituted verbatim")
    checks.equal(feed, "", "an embedded prompt must not also arrive on stdin")
    sub, feed = agent_argv(["claude", "-p"], "draft this", pathlib.Path(repo))
    checks.equal(feed, "draft this", "a stdin host still gets the prompt on stdin")
    both = run("draft", "x", "--agent", "claude", "--agent-cmd", "echo", cwd=repo)
    checks.equal(both.returncode, 2, "--agent with --agent-cmd must be refused")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "task.yaml").exists(),
              "a refused draft must not write the default brief")


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
    original = path.read_bytes()
    result = run("prepare", path)
    checks.equal(result.returncode, 1, "lint failure exit")
    checks.ok(path.read_bytes() == original,
              "a failed prepare leaves the brief as it found it — the measured "
              "block must not survive the failure")
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
    defaulted = run("status", "--json", cwd=outside)
    checks.equal(defaulted.returncode, 2, "default status outside a repo refuses")
    checks.equal(json_out(defaulted).get("status"), "refused",
                 "default status refusal is structured")


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
    before = path.read_bytes()
    prompt = path.with_name("task.generic.md")
    checklist = path.with_name("task.checklist.md")
    checklist.mkdir()
    result = run("prepare", path)
    checks.equal(result.returncode, 2, "artifact write refusal exit")
    checks.ok(path.read_bytes() == before,
              "a failed artifact write must put the brief's bytes back — the "
              "baseline stage already stamped the measured block by here")
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


@case("displayed next commands quote brief paths")
def _(repo, checks):
    sys.path.insert(0, str(ROOT))
    import prompire
    original = prompire.os.name
    try:
        prompire.os.name = "posix"
        checks.equal(prompire.display_command(["prompire", "verify", "task brief.yaml"]),
                     "prompire verify 'task brief.yaml'", "POSIX command")
        prompire.os.name = "nt"
        checks.equal(prompire.display_command(["prompire", "verify", "task brief.yaml"]),
                     'prompire verify "task brief.yaml"', "Windows command")
    finally:
        prompire.os.name = original
        sys.path.remove(str(ROOT))


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
    checks.equal(data["scope"]["base_source"], None,
                 "this is the unarmed state the base_source gate exists to keep blocked")


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


@case("a violation blocks acceptance even when the only review is non-blocking")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/violation-named.yaml", """\
goal: Fix the cart total and repair its test.
scope: [src/cart.py]
forbidden: []
tests_policy: named
tests_editable: [tests/test_total.py]
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/violation-named.ran').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    result = run("prepare", path)
    checks.equal(result.returncode, 0, "prepare exit")
    ran = pathlib.Path(repo) / ".prompire" / "violation-named.ran"
    checks.ok(ran.exists(), "prepare's baseline run proves the sentinel mechanism works")
    ran.unlink(missing_ok=True)
    fixtures.write(repo, "src/outside.py", "value = 1\n")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(result.returncode, 1, "violation exit")
    checks.equal(data["scope"]["violations"], 1, "the out-of-scope write is a violation")
    checks.equal(data["acceptance"]["status"], "not_run",
                 "a violation must keep acceptance blocked whatever reviews accompany it")
    checks.ok(not ran.exists(), "the acceptance command must not have executed")


@case("an indeterminate scope run never executes the acceptance command")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/no-base.yaml", """\
goal: Keep an unmeasured brief from authorizing commands.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/no-base.ran').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    result = run("verify", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 2, "no base means no verdict")
    checks.equal(data.get("status"), "indeterminate", "exit-2 JSON shape")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "no-base.ran").exists(),
              "exit 2 must short-circuit before any command runs")


@case("editing the armed brief's acceptance command yields no verdict and no execution")
def _(repo, checks):
    path = prepared(repo)
    old_cmd = '''python -c "print('ok')"'''
    new_cmd = ('''python -c "import pathlib; '''
               '''pathlib.Path('.prompire/edited.ran').write_text('x')"''')
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(old_cmd, new_cmd), encoding="utf-8")
    result = run("verify", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 2, "an edited armed brief must produce no verdict")
    checks.equal(data.get("status"), "indeterminate", "refusal shape")
    checks.ok(not (pathlib.Path(repo) / ".prompire" / "edited.ran").exists(),
              "the rewritten acceptance command must never execute")


@case("a symlink review keeps acceptance unexecuted")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/symlinked.yaml", """\
goal: Add an alias module next to cart.
scope: [src/cart.py, src/alias.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/symlinked.ran').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    result = run("prepare", path)
    checks.equal(result.returncode, 0, "prepare exit")
    ran = pathlib.Path(repo) / ".prompire" / "symlinked.ran"
    checks.ok(ran.exists(), "prepare's baseline run proves the sentinel mechanism works")
    ran.unlink(missing_ok=True)
    (pathlib.Path(repo) / "src" / "alias.py").symlink_to("cart.py")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(result.returncode, 1, "symlink review exit")
    checks.equal(data["scope"]["violations"], 0,
                 "an in-scope symlink is a review, not a violation")
    checks.ok(any(f["kind"] == "REVIEW" and "symlink" in f["message"]
                  for f in data["scope"]["findings"]),
              "the symlink review must be present")
    checks.equal(data["scope"]["base_source"], "pin", "the run is otherwise corroborated")
    checks.equal(data["acceptance"]["status"], "not_run",
                 "a symlink review must keep blocking acceptance")
    checks.ok(not ran.exists(), "the acceptance command must not have executed")


@case("a named tests policy gathers acceptance evidence and keeps the review")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/named-evidence.yaml", """\
goal: Fix the cart total and repair its test.
scope: [src/cart.py]
forbidden: []
tests_policy: named
tests_editable: [tests/test_total.py]
acceptance:
  - cmd: python -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/named-evidence.ran').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    result = run("prepare", path)
    checks.equal(result.returncode, 0, "prepare exit")
    ran = pathlib.Path(repo) / ".prompire" / "named-evidence.ran"
    ran.unlink(missing_ok=True)
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8").replace(
        "return sum(items) - 1", "return sum(items)"), encoding="utf-8")
    test = pathlib.Path(repo) / "tests" / "test_total.py"
    test.write_text(test.read_text(encoding="utf-8") + "\n# repaired with the fix\n",
                    encoding="utf-8")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(data["scope"]["violations"], 0, "a legitimate run has no violations")
    checks.equal(data["scope"]["base_source"], "pin", "the run is corroborated")
    checks.ok(any("tests_policy `named`" in f["message"]
                  for f in data["scope"]["findings"]), "the policy review must remain")
    checks.ok(data["acceptance"].get("status") != "not_run",
              "acceptance evidence must be gathered")
    checks.equal(data["acceptance"].get("passed"), 2, "both acceptance commands pass")
    checks.ok(ran.exists(), "the acceptance command must actually have executed")
    checks.equal(result.returncode, 1, "the review must still fail the strict run")


@case("an authoring policy with a skip marker still gathers acceptance evidence")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/authoring-evidence.yaml", """\
goal: Author a regression test for the total helper.
scope: [src/cart.py]
forbidden: []
tests_policy: authoring
tests_editable: [tests/test_total.py]
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/authoring-evidence.ran').write_text('x')"
    expect: exit 0
oracle: human review
autonomy: ask
""")
    result = run("prepare", path)
    checks.equal(result.returncode, 0, "prepare exit")
    ran = pathlib.Path(repo) / ".prompire" / "authoring-evidence.ran"
    ran.unlink(missing_ok=True)
    test = pathlib.Path(repo) / "tests" / "test_total.py"
    test.write_text(test.read_text(encoding="utf-8").replace(
        "    def test_total_sums(self):",
        "    @unittest.skip(\"wip\")\n    def test_total_sums(self):"),
        encoding="utf-8")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(data["scope"]["violations"], 0, "authoring edits are not violations")
    checks.equal(data["scope"]["reviews"], 2, "policy review plus skip-marker review")
    checks.equal(data["acceptance"].get("passed"), 1, "acceptance evidence gathered")
    checks.ok(ran.exists(), "the acceptance command must actually have executed")
    checks.equal(result.returncode, 1, "the reviews must still fail the strict run")


@case("the brief-changed review on a tracked brief does not block acceptance evidence")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/tracked.yaml", """\
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/tracked.ran').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    fixtures.git(repo, "add", "-f", str(path))
    fixtures.git(repo, "commit", "-qm", "track the brief before measuring")
    result = run("prepare", path)
    checks.equal(result.returncode, 0, "prepare exit")
    ran = pathlib.Path(repo) / ".prompire" / "tracked.ran"
    ran.unlink(missing_ok=True)
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")

    result = run("verify", path, "--json")
    data = json_out(result)

    checks.equal(data["scope"]["violations"], 0, "the in-scope edit is legal")
    checks.equal(data["scope"]["base_source"], "pin", "the run is corroborated")
    checks.ok(any("the brief itself changed since the base revision" in f["message"]
                  for f in data["scope"]["findings"]),
              "prepare's own baseline write must have raised the brief-changed review")
    checks.equal(data["acceptance"].get("passed"), 1, "acceptance evidence gathered")
    checks.ok(ran.exists(), "the acceptance command must actually have executed")
    checks.equal(result.returncode, 1, "the review must still fail the strict run")


@case("a repin review gathers acceptance evidence and the ack still clears strict")
def _(repo, checks):
    def task_brief(name):
        return fixtures.write(repo, f".prompire/{name}.yaml", f"""\
goal: Task {name} on the cart module.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "import pathlib; pathlib.Path('.prompire/{name}.ran').write_text('x')"
    expect: exit 0
autonomy: ask
""")
    first = task_brief("first")
    checks.equal(run("prepare", first).returncode, 0, "first prepare exit")
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8").replace(
        "return sum(items) - 1", "return sum(items)"), encoding="utf-8")
    checks.equal(run("verify", first).returncode, 0, "first cycle verifies clean")
    fixtures.git(repo, "add", "-A")
    fixtures.git(repo, "commit", "-qm", "task first, reviewed and committed")
    checks.equal(run("close", first).returncode, 0, "close exit")

    second = task_brief("second")
    checks.equal(run("prepare", second).returncode, 0, "second prepare exit")
    ran = pathlib.Path(repo) / ".prompire" / "second.ran"
    ran.unlink(missing_ok=True)
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")

    result = run("verify", second, "--json")
    data = json_out(result)

    checks.equal(data["scope"]["base_source"], "repin", "the second cycle is a repin")
    checks.equal(data["scope"]["violations"], 0, "the in-scope edit is legal")
    checks.equal(data["acceptance"].get("passed"), 1, "acceptance evidence gathered")
    checks.ok(ran.exists(), "the acceptance command must actually have executed")
    checks.equal(result.returncode, 1, "the unacknowledged repin must still fail strict")

    tomb = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    digest = hashlib.sha256(tomb.read_bytes()).hexdigest()[:12]
    ran.unlink(missing_ok=True)
    acked = run("verify", second, "--ack-disarms", digest, "--json")
    acked_data = json_out(acked)
    checks.equal(acked.returncode, 0, "the acknowledged repin clears strict, as today")
    checks.equal(acked_data["acceptance"].get("passed"), 1,
                 "acceptance runs on the acked path")
    checks.ok(ran.exists(), "acceptance executed on the acked path too")


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
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=ENV,
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
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=ENV,
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
    defaulted = json_out(run("status", "--json", cwd=repo))
    checks.equal(defaulted, active, "status without a path uses cwd")
    explicit_dir = json_out(run("status", ".", "--json", cwd=repo))
    checks.equal(explicit_dir, active, "status accepts an explicit directory")
    closed = run("close", path)
    checks.equal(closed.returncode, 0, "close before inactive status")
    inactive = json_out(run("status", path, "--json"))
    checks.equal(inactive["status"], "inactive", "inactive status")
    again = run("prepare", path)
    checks.equal(again.returncode, 1, "prepare refuses to overwrite an already measured brief")
    # Re-arm through the existing low-level tool after the derived prompt workflow has
    # deliberately refused to overwrite the brief's measured baseline.
    armed = subprocess.run([sys.executable, str(ROOT / "check_scope.py"), str(path), "--activate"],
                           capture_output=True, text=True, encoding="utf-8")
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
        direct = subprocess.run([sys.executable, str(ROOT / script)],
                                capture_output=True, text=True, encoding="utf-8")
        forwarded = run(command)
        checks.equal(forwarded.returncode, direct.returncode,
                     f"{command} must preserve its underlying exit code")


@case("Windows Python shim does not echo acceptance commands")
def _(repo, checks):
    if os.name != "nt":
        return
    result = subprocess.run(
        ["python", "-c", "print('ok')"], capture_output=True, text=True,
        encoding="utf-8", env=ENV)
    checks.equal(result.returncode, 0, "Windows Python shim exit")
    checks.equal(result.stdout, "ok\n",
                 "Windows command echo must not alter acceptance stdout")


@case("low-level subcommands forward help verbatim")
def _(repo, checks):
    for command, script in (("baseline", "baseline.py"), ("lint", "lint_brief.py"),
                            ("render", "render_brief.py"), ("scope", "check_scope.py")):
        direct = subprocess.run([sys.executable, str(ROOT / script), "--help"],
                                capture_output=True, text=True, encoding="utf-8")
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
                              capture_output=True, text=True, encoding="utf-8")
    checks.equal(measured.returncode, 0, "good fixture baseline")
    bad = brief(repo, "bad", extra="scope: []\n")
    probes = (
        ("lint", "lint_brief.py", (good, "--json")),
        ("lint", "lint_brief.py", (bad, "--json")),
        ("baseline", "baseline.py", ()),
    )
    for command, script, arguments in probes:
        direct = subprocess.run([sys.executable, str(ROOT / script), *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8")
        forwarded = run(command, *arguments)
        checks.equal(forwarded.returncode, direct.returncode,
                     f"{command} {arguments} exit must be preserved")
        checks.equal(forwarded.stdout, direct.stdout,
                     f"{command} {arguments} stdout must be preserved")
        checks.equal(forwarded.stderr, direct.stderr,
                     f"{command} {arguments} stderr must be preserved")


@case("demo cleanup makes a read-only file writable before removing it")
def _(repo, checks):
    # Regression: `shutil.rmtree(..., ignore_errors=True)` leaves a demo repo behind
    # on Windows, where every object under `.git/objects` is created read-only and
    # Windows (unlike POSIX, where deletion is a directory-permission question) refuses
    # to unlink a read-only file. `_make_tree_writable` is the fix; tested directly
    # (checking the mode bit, not deletion) because POSIX lets a naive rmtree remove a
    # read-only file regardless, so an rmtree-level test alone would not have caught
    # this.
    sys.path.insert(0, str(ROOT))
    import importlib
    prompire_mod = importlib.import_module("prompire")
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "readonly.txt"
        target.write_text("x", encoding="utf-8")
        target.chmod(0o444)
        prompire_mod._make_tree_writable(pathlib.Path(tmp))
        checks.ok(os.access(target, os.W_OK), "the file must be writable afterward")


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
    checks.ok("acceptance: not run" in low,
              "the caught violation must keep acceptance unexecuted")
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
    path = brief(repo, "task brief")
    result = run("prepare", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 0, "JSON prepare exit")
    checks.equal(data["status"], "prepared", "JSON prepared status")
    checks.equal(result.stderr, "", "JSON mode must not emit child prose to stderr")
    checks.ok("task brief.yaml" in data["next"], "JSON next command keeps the path")
    quoted = f'"{path}"' if os.name == "nt" else f"'{path}'"
    checks.ok(quoted in data["next"], "JSON next command quotes the path")


@case("verify --json emits one canonical object for clean and violation runs")
def _(repo, checks):
    path = prepared(repo)
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")
    clean = run("verify", path, "--json")
    data = json_out(clean)
    checks.equal(clean.returncode, 0, "clean JSON exit")
    checks.equal(sorted(data), ["acceptance", "scope"], "top-level JSON keys")
    checks.equal(sorted(data["scope"]),
                 ["ack_disarms_bound", "base", "base_source", "findings",
                  "reviews", "violations"], "scope JSON keys")
    checks.equal(sorted(data["acceptance"]),
                 ["brief", "failed", "not_run", "passed", "results"],
                 "acceptance JSON keys")
    checks.equal(clean.stdout, json.dumps(data, ensure_ascii=False) + "\n",
                 "clean JSON is one canonical line, byte for byte")
    checks.equal(clean.stderr, "", "clean JSON emits no stderr")

    fixtures.write(repo, "src/outside.py", "value = 1\n")
    caught = run("verify", path, "--json")
    data = json_out(caught)
    checks.equal(caught.returncode, 1, "violation JSON exit")
    checks.equal(data["acceptance"],
                 {"status": "not_run", "reason": "strict scope preflight did not pass"},
                 "blocked preflight acceptance shape")
    checks.equal(caught.stdout, json.dumps(data, ensure_ascii=False) + "\n",
                 "violation JSON is one canonical line, byte for byte")


@case("verify --json keeps the reviews-plus-acceptance shape canonical")
def _(repo, checks):
    path = fixtures.write(repo, ".prompire/json-review.yaml", """\
goal: Fix the cart total and repair its test.
scope: [src/cart.py]
forbidden: []
tests_policy: named
tests_editable: [tests/test_total.py]
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
autonomy: ask
""")
    checks.equal(run("prepare", path).returncode, 0, "prepare exit")
    result = run("verify", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 1, "review JSON exit")
    checks.equal(data["scope"]["reviews"], 1, "review count")
    checks.equal(data["acceptance"]["passed"], 1, "acceptance evidence in JSON")
    checks.equal(result.stdout, json.dumps(data, ensure_ascii=False) + "\n",
                 "review JSON is one canonical line, byte for byte")


@case("verify --json keeps the indeterminate and refusal shapes canonical")
def _(repo, checks):
    path = brief(repo)  # never prepared: no base -> exit 2
    result = run("verify", path, "--json")
    data = json_out(result)
    checks.equal(result.returncode, 2, "indeterminate JSON exit")
    checks.equal(sorted(data),
                 ["exit_code", "message", "stage", "status", "stderr", "stdout"],
                 "indeterminate JSON keys")
    checks.equal(data["status"], "indeterminate", "indeterminate status")
    checks.equal(data["stage"], "scope", "indeterminate stage")
    checks.equal(result.stdout, json.dumps(data, ensure_ascii=False) + "\n",
                 "indeterminate JSON is one canonical line, byte for byte")

    refused = run("verify", path, "--bogus", "--json")
    data = json_out(refused)
    checks.equal(refused.returncode, 2, "refusal JSON exit")
    checks.equal(data, {"status": "refused",
                        "message": "unrecognized arguments: --bogus"},
                 "refusal JSON shape")
    checks.equal(refused.stdout, json.dumps(data, ensure_ascii=False) + "\n",
                 "refusal JSON is one canonical line, byte for byte")


@case("verify human mode leads with clean or caught and prints no child JSON")
def _(repo, checks):
    path = prepared(repo)
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")
    clean = run("verify", path)
    checks.equal(clean.returncode, 0, "clean exit")
    checks.equal(clean.stdout,
                 'clean\nacceptance: PASS python -c "print(\'ok\')"\n',
                 "clean verdict leads and carries the acceptance evidence")
    checks.ok("{" not in clean.stdout, "no raw child JSON in human mode")

    fixtures.write(repo, "src/outside.py", "value = 1\n")
    one = run("verify", path)
    checks.equal(one.returncode, 1, "one-violation exit")
    checks.equal(one.stdout, (
        "caught: 1 violation\n"
        "VIOLATION src/outside.py: changed outside `scope`\n"
        "          → revert it, or revise the brief and re-run the baseline — a scope "
        "change is an edit to the brief, not a confirmation in chat\n"
        "acceptance: not run — strict scope preflight did not pass\n"),
        "one violation is caught, named, and acceptance stays blocked")
    checks.ok("{" not in one.stdout, "no raw child JSON in human mode")

    fixtures.write(repo, "src/outside2.py", "value = 2\n")
    two = run("verify", path)
    checks.equal(two.returncode, 1, "two-violation exit")
    checks.equal(two.stdout.splitlines()[0], "caught: 2 violations",
                 "the plural verdict counts every violation")
    checks.ok("VIOLATION src/outside.py: changed outside `scope`" in two.stdout
              and "VIOLATION src/outside2.py: changed outside `scope`" in two.stdout,
              "both violations stay named")


@case("verify human mode says caught when acceptance did not pass, never violation")
def _(repo, checks):
    regress = ("python -c \"import pathlib,sys; "
               "sys.exit(1 if pathlib.Path('.prompire/kill').exists() else 0)\"")
    path = fixtures.write(repo, ".prompire/regress.yaml", f"""\
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: {regress}
    expect: exit 0
autonomy: ask
""")
    checks.equal(run("prepare", path).returncode, 0, "prepare exit")
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")
    fixtures.write(repo, ".prompire/kill", "regress\n")

    result = run("verify", path)
    checks.equal(result.returncode, 1, "acceptance failure exit")
    checks.equal(result.stdout, (
        "caught: acceptance did not pass\n"
        f"acceptance: FAIL {regress}\n"),
        "an acceptance failure is caught by name, with the failing command")
    checks.ok("violation" not in result.stdout.lower(),
              "a failed test is never miscounted as a scope violation")


@case("verify human mode says no verdict on exit 2, with the child's own reason")
def _(repo, checks):
    unprepared = brief(repo)  # no base_rev, never activated
    result = run("verify", unprepared)
    checks.equal(result.returncode, 2, "no-base exit")
    checks.equal(result.stdout.splitlines()[0],
                 "no verdict: scope produced no trustworthy result",
                 "the no-verdict headline leads")
    checks.ok("no base to check against" in result.stdout,
              "the child's reason and remedy survive")
    for word in ("caught", "review:", "clean"):
        checks.ok(word not in result.stdout,
                  f"an indeterminate run must not read as {word!r}")

    edited = prepared(repo, "edited")
    edited.write_text(
        edited.read_text(encoding="utf-8").replace("print('ok')", "print('no')"),
        encoding="utf-8")
    result = run("verify", edited)
    checks.equal(result.returncode, 2, "edited-armed-brief exit")
    checks.equal(result.stdout.splitlines()[0],
                 "no verdict: scope produced no trustworthy result",
                 "the edited armed brief also reads as no verdict")
    checks.ok("the brief changed since the guard was armed" in result.stdout,
              "the reason names the changed brief")


@case("verify human mode keeps REVIEW top-level over a passing acceptance")
def _(repo, checks):
    named = """\
goal: Fix the cart total and repair its test.
scope: [src/cart.py]
forbidden: []
tests_policy: named
tests_editable: [tests/test_total.py]
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
autonomy: ask
"""
    path = fixtures.write(repo, ".prompire/named.yaml", named)
    checks.equal(run("prepare", path).returncode, 0, "prepare exit")
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")

    result = run("verify", path)
    checks.equal(result.returncode, 1, "review exit stays non-zero")
    checks.equal(result.stdout, (
        "review: 1 flag — needs a human\n"
        "REVIEW    tests/test_total.py: tests_policy `named` lets test files change; "
        "no checker can tell a repaired assertion from a weakened one\n"
        "          → read the test diff yourself\n"
        "acceptance: PASS python -c \"print('ok')\"\n"),
        "the review verdict leads and the acceptance pass is separate evidence")
    checks.ok("clean" not in result.stdout,
              "a passing acceptance must not launder the review into clean")


@case("verify human mode surfaces an acceptance failure above surviving reviews")
def _(repo, checks):
    regress = ("python -c \"import pathlib,sys; "
               "sys.exit(1 if pathlib.Path('.prompire/kill').exists() else 0)\"")
    path = fixtures.write(repo, ".prompire/named-regress.yaml", f"""\
goal: Fix the cart total and repair its test.
scope: [src/cart.py]
forbidden: []
tests_policy: named
tests_editable: [tests/test_total.py]
acceptance:
  - cmd: {regress}
    expect: exit 0
autonomy: ask
""")
    checks.equal(run("prepare", path).returncode, 0, "prepare exit")
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")
    fixtures.write(repo, ".prompire/kill", "regress\n")

    result = run("verify", path)
    checks.equal(result.returncode, 1, "combined failure exit")
    checks.equal(result.stdout.splitlines()[0], "caught: acceptance did not pass",
                 "a run with a red acceptance is not merely reviews-only")
    checks.ok("REVIEW    tests/test_total.py: tests_policy `named`" in result.stdout,
              "the review flag stays visible under the acceptance failure")
    checks.ok(f"acceptance: FAIL {regress}" in result.stdout,
              "the failing command is named")


@case("verify human mode makes the repin acknowledgement discoverable, never automatic")
def _(repo, checks):
    def task_brief(name):
        return fixtures.write(repo, f".prompire/{name}.yaml", """\
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
autonomy: ask
""")
    first = task_brief("first")
    checks.equal(run("prepare", first).returncode, 0, "first prepare exit")
    cart = pathlib.Path(repo) / "src" / "cart.py"
    cart.write_text(cart.read_text(encoding="utf-8").replace(
        "return sum(items) - 1", "return sum(items)"), encoding="utf-8")
    checks.equal(run("verify", first).returncode, 0, "first cycle verifies clean")
    fixtures.git(repo, "add", "-A")
    fixtures.git(repo, "commit", "-qm", "task first, reviewed and committed")
    checks.equal(run("close", first).returncode, 0, "close exit")

    second = task_brief("second")
    checks.equal(run("prepare", second).returncode, 0, "second prepare exit")
    cart.write_text(cart.read_text(encoding="utf-8")
                    + "\n\ndef count(items):\n    return len(items)\n",
                    encoding="utf-8")

    result = run("verify", second)
    tomb = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    digest = hashlib.sha256(tomb.read_bytes()).hexdigest()[:12]
    checks.equal(result.returncode, 1, "unacked repin exit")
    checks.equal(result.stdout.splitlines()[0], "review: 1 flag — needs a human",
                 "the repin review is the top-level verdict")
    checks.ok('acceptance: PASS python -c "print(\'ok\')"' in result.stdout,
              "the P2 acceptance evidence stays visible under the review")
    checks.equal(result.stdout.rstrip("\n").splitlines()[-1],
                 f"acknowledge with: prompire verify {second} --ack-disarms {digest}",
                 "the remedy is the exact existing command, digest included")
    checks.ok("clean" not in result.stdout, "an unacked repin is never clean")

    acked = run("verify", second, "--ack-disarms", digest)
    checks.equal(acked.returncode, 0, "the acknowledged repin clears strict, as today")
    checks.equal(acked.stdout.splitlines()[0], "clean",
                 "the acknowledged result is rendered as the authority it is")
    checks.ok("Acknowledged:" in acked.stdout,
              "the structured result still carries the acked review, so it is shown")
    checks.ok("acknowledge with:" not in acked.stdout,
              "no remedy line once the acknowledgement is bound")


@case("verify human mode never implies acceptance evidence the gate withheld")
def _(repo, checks):
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    path = fixtures.write(repo, ".prompire/uncorroborated.yaml", f"""\
goal: Keep an uncorroborated brief from authorizing commands.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
base_rev: {head}
baseline:
  - cmd: python -c "print('ok')"
    status: pass
    evidence: exit 0, 1 line(s) stdout, 0.0s
autonomy: ask
""")
    result = run("verify", path)
    checks.equal(result.returncode, 1, "uncorroborated exit")
    checks.equal(result.stdout.splitlines()[0], "review: 1 flag — needs a human",
                 "the unarmed state is a review, not a caught or a clean")
    checks.ok("acceptance: not run — strict scope preflight did not pass"
              in result.stdout, "withheld acceptance is stated as not run")
    checks.ok("PASS" not in result.stdout and "FAIL" not in result.stdout,
              "no acceptance rows may be implied when nothing executed")

    linked = fixtures.write(repo, ".prompire/symlinked.yaml", """\
goal: Add an alias module next to cart.
scope: [src/cart.py, src/alias.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python -c "print('ok')"
    expect: exit 0
autonomy: ask
""")
    checks.equal(run("prepare", linked).returncode, 0, "symlink-case prepare exit")
    try:
        (pathlib.Path(repo) / "src" / "alias.py").symlink_to("cart.py")
    except (NotImplementedError, OSError):
        return
    result = run("verify", linked)
    checks.equal(result.returncode, 1, "symlink review exit")
    checks.equal(result.stdout.splitlines()[0], "review: 1 flag — needs a human",
                 "the symlink review is the top-level verdict")
    checks.ok("acceptance: not run — strict scope preflight did not pass"
              in result.stdout, "a symlink review keeps acceptance visibly not run")


@case("--version prints the package version and exits 0")
def _(repo, checks):
    result = run("--version", cwd=repo)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    checks.equal(result.returncode, 0, "--version exit code")
    checks.equal(result.stdout.strip(), version, "--version output vs VERSION")
    checks.equal(pyproject["project"]["version"], version,
                 "pyproject.toml vs VERSION")


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
