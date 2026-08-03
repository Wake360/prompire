#!/usr/bin/env python3
"""Measure every acceptance command on untouched HEAD and print the `baseline:` block.

Usage: python3 baseline.py brief.yaml [--write] [--allow-dirty] [--json]
Exit 0 = every criterion got a recorded observation, 1 = at least one could not be
classified and needs a human, 2 = the brief or the repository could not be read.

Nothing here guesses. A command is either run in this invocation and reported with the
exit code it produced, or it is classified `not_runnable` with the reason it was not
run. A command whose `expect` this tool cannot read is reported as unclassified and
left out of the block — an empty slot is worth more than a plausible `pass`.

Classification is conservative, not a sandbox: it refuses commands that look
destructive, interactive, environment-dependent or repo-writing. It cannot make an
arbitrary shell command safe, so read the block it prints before trusting it.

Trust boundary: an acceptance `cmd` is a shell command line by definition — pipes and
redirects are part of the schema — so it is executed through the shell as written. The
brief is a local file you wrote. Never run this against a brief from someone else.
"""
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import yaml

from brief_common import (
    ALWAYS_ALLOWED,
    DEFAULT_TIMEOUT,
    BriefError,
    acceptance_entries,
    as_list,
    effective_transition,
    load_brief,
    matches_any,
    norm_cmd,
    norm_cwd,
    utf8_stdio,
)

DESTRUCTIVE = re.compile(
    r"\brm\s+-[rf]|\bdrop\s+(table|database)\b|\btruncate\s+table\b|push\s+--?f|"
    r"git\s+reset\s+--hard|git\s+clean\s+-\w*[fd]|\bdeploy\b|terraform\s+apply|"
    r"kubectl\s+(apply|delete)|npm\s+publish|cargo\s+publish|alembic\s+upgrade|"
    r"prisma\s+migrate\s+deploy|flyway\s+migrate|\bmkfs\b|\bdd\s+if=", re.I)
# Tools that are interactive when *executed* — matched only in command position
# (see `_command_words`), never as an argument. E1's T06 baseline refused
# `stubtest more_itertools.more more_itertools.recipes` as "interactive (`more`)":
# a pager name inside a module path is a string, not a pager.
INTERACTIVE_TOOLS = frozenset(
    ("vi", "vim", "nano", "emacs", "less", "more", "top", "htop", "ssh", "sudo",
     "su", "watch"))
# Flags and idioms that mean interactive/long-running wherever they appear.
INTERACTIVE_FLAGS = re.compile(
    r"--interactive\b|\bgit\s+rebase\s+-i|\bread\s+-p|\bgh\s+auth\s+login|--watch\b",
    re.I)
# Wrappers that pass execution through to the next word on the line.
COMMAND_PREFIXES = frozenset(("env", "command", "nohup", "time", "exec", "xargs"))


def _command_words(cmd):
    """The word in executable position of each simple command in a shell line.

    Split on the shell's command separators, then take the first word of each
    segment that is not an environment assignment or a pass-through wrapper.
    This does not parse quoting — a separator inside a quoted string still
    splits — which errs toward one extra candidate word, never a missed one."""
    words = []
    for segment in re.split(r"\|\||&&|;|\||\$\(|`|\n", str(cmd)):
        for token in segment.strip().split():
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", token):
                continue
            name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
            if name in COMMAND_PREFIXES:
                continue
            words.append(name)
            break
    return words


def interactive_hit(cmd):
    """Why this command counts as interactive, or None."""
    m = INTERACTIVE_FLAGS.search(str(cmd))
    if m:
        return m.group(0).strip()
    for word in _command_words(cmd):
        if word in INTERACTIVE_TOOLS:
            return word
    return None
WRITES_REPO = re.compile(
    r"git\s+(commit|checkout|switch|apply|stash|merge|rebase|cherry-pick|add)\b|"
    r"\bsed\s+-i|\b(pip|npm|yarn|pnpm|bun|cargo|go)\s+(install|add|get)\b|"
    r"\bblack\s+(?!--check)|\bruff\s+format\s+(?!--check|--diff)|\bprettier\s+--write|"
    r"\bisort\s+(?!--check)|\bcodemod\b|\b\w+\s*>\s*\S|\btee\b", re.I)
NETWORKY = re.compile(r"\bcurl\b|\bwget\b|\bhttpie?\b|localhost|127\.0\.0\.1|https?://", re.I)

EXPECT_EXIT = re.compile(r"exit\s*(?:code\s*)?(?:==\s*)?(\d+)", re.I)
EXPECT_NONZERO = re.compile(r"exit\s*!=\s*0|non-?zero\s*exit|exit\s*(?:code\s*)?non-?zero", re.I)
EXPECT_EMPTY = re.compile(r"\bempty\s*(output|stdout)?\b|\bno\s+(output|matches|lines)\b", re.I)


def classify(entry):
    """Why this command will not be run on HEAD, or None if it is safe to run."""
    cmd = norm_cmd(entry.get("cmd"))
    req = [str(r).strip().lower() for r in as_list(entry.get("requires")) if str(r).strip()]
    if req:
        return f"declared requires: {', '.join(sorted(set(req)))}"
    m = DESTRUCTIVE.search(cmd)
    if m:
        return f"destructive command (`{m.group(0).strip()}`); not run for a baseline"
    # The raw text, not the normalised one: a newline is a command separator, so
    # `foo\nmore x` puts `more` in executable position and normalising first would
    # hide that from the command-position scan.
    hit = interactive_hit(str(entry.get("cmd") or ""))
    if hit:
        return f"interactive or long-running (`{hit}`)"
    m = WRITES_REPO.search(cmd)
    if m:
        return f"writes to the repository (`{m.group(0).strip()}`); HEAD must stay untouched"
    m = NETWORKY.search(cmd)
    if m:
        return (f"needs a service or the network (`{m.group(0).strip()}`) — declare "
                "`requires: [network]` or `[services]` if that is intended")
    return None


# --- workspace-consistency probe (E1, T05) ---------------------------------------
# The compiled T05 contract's baseline was measured against the system site-packages
# copy of the library — which already contained the upstream fix — so a green
# baseline signed off code nobody was modifying. When a command exercises a package
# this checkout itself defines, the import must resolve into this checkout; if it
# resolves elsewhere, the measurement describes the wrong code and is refused as
# unclassified rather than recorded. Deliberately narrow: explicit python/py
# interpreters only, and only imports the evidence ties to the repo's own packages.
# A bare `pytest`/`tox` entry point, or a script argument, is not probed — their
# interpreter is not knowable from the command line, and guessing would probe the
# wrong environment.

PYTHON_INTERP = re.compile(r"^(python(\d+(\.\d+)?)?|py)(\.exe)?$", re.I)
TEST_RUNNER_MODULES = ("pytest", "unittest")
_PROBE_CACHE = {}


def workspace_packages(root, cwd):
    """Top-level package names this checkout itself defines: a directory with an
    __init__.py at the repo root, under src/, or the same pair under the entry's
    cwd (monorepos). Existence of the name is what creates the shadowing hazard."""
    names = set()
    for base in (root, root / "src", cwd, cwd / "src"):
        try:
            children = list(base.iterdir()) if base.is_dir() else []
        except OSError:
            children = []
        for child in children:
            if child.is_dir() and (child / "__init__.py").is_file():
                names.add(child.name)
    return names


def _probe_plan(entry, packages):
    """(interpreter, package names to probe), or None when the command gives no
    evidence of exercising a workspace package through an explicit interpreter."""
    raw = str(entry.get("cmd") or "")
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    name = tokens[0].replace("\\", "/").rsplit("/", 1)[-1]
    if not PYTHON_INTERP.match(name):
        return None
    args = tokens[1:]
    for i, tok in enumerate(args):
        if tok == "-m" and i + 1 < len(args):
            module = args[i + 1].split(".")[0]
            if module in TEST_RUNNER_MODULES:
                # the repo's own suite exercises the repo's own packages
                return tokens[0], sorted(packages)
            if module in packages:
                return tokens[0], [module]
            return None
        if tok == "-c" and i + 1 < len(args):
            named = sorted(p for p in packages
                           if re.search(rf"\b{re.escape(p)}\b", args[i + 1]))
            return (tokens[0], named) if named else None
    return None


def import_origin(interp, package, cwd):
    """Where `import <package>` under this interpreter resolves, or None when the
    probe is inconclusive (interpreter missing, package not importable at all)."""
    key = (interp, package, str(cwd))
    if key not in _PROBE_CACHE:
        code = (f"import {package}, os; print(os.path.abspath((getattr({package}, "
                f"'__file__', None) or (list(getattr({package}, '__path__', [])) "
                f"or [''])[0]) or ''))")
        try:
            # Through the shell like the measurement itself, so PATH resolves the
            # interpreter token the same way the acceptance command will.
            r = subprocess.run(f'{interp} -c "{code}"', shell=True, cwd=str(cwd),
                               capture_output=True, encoding="utf-8",
                               errors="replace", timeout=30)
            out = (r.stdout or "").strip()
            _PROBE_CACHE[key] = out if r.returncode == 0 and out else None
        except (subprocess.TimeoutExpired, OSError):
            _PROBE_CACHE[key] = None
    return _PROBE_CACHE[key]


def workspace_mismatch(root, entry):
    """Why this measurement would describe an installed copy instead of this
    checkout, or None. Only fires on positive evidence: the repo defines the
    package, the command exercises it, and the import resolves outside the repo."""
    cwd = root / norm_cwd(entry.get("cwd"))
    packages = workspace_packages(root, cwd)
    if not packages:
        return None
    plan = _probe_plan(entry, packages)
    if not plan:
        return None
    interp, targets = plan
    real_root = os.path.realpath(root)
    for package in targets:
        origin = import_origin(interp, package, cwd)
        if origin and not os.path.realpath(origin).startswith(real_root + os.sep):
            return (f"`import {package}` under `{interp}` resolves to {origin} — "
                    "outside this workspace, so the measurement would describe an "
                    "installed copy, not the checkout under modification. Point the "
                    "command at the workspace copy (install it editable, or fix the "
                    "interpreter/PYTHONPATH), then re-run")
    return None


def verdict(expect, rc, stdout):
    """pass/fail from the recognised `expect` forms, or None when it is prose."""
    e = str(expect or "").strip().lower()
    if not e:
        return None
    if EXPECT_NONZERO.search(e):
        return "pass" if rc != 0 else "fail"
    m = EXPECT_EXIT.search(e)
    if m:
        return "pass" if rc == int(m.group(1)) else "fail"
    if EXPECT_EMPTY.search(e):
        return "pass" if stdout.strip() == "" else "fail"
    return None


def run_one(root, entry):
    cmd = norm_cmd(entry.get("cmd"))
    # What runs is the brief's command verbatim, not the whitespace-normalised
    # display/keying form: newlines and doubled spaces inside quotes are shell
    # syntax, and E1 showed a flattened multi-line command is a *different*
    # command — three delivered contracts carried criteria that could never
    # execute as communicated. `cmd` stays the normalised spelling for display
    # and for the (cmd, cwd) key the baseline block and renderer match on.
    script = str(entry.get("cmd") or "")
    cwd = root / norm_cwd(entry.get("cwd"))
    timeout = entry.get("timeout") if isinstance(entry.get("timeout"), int) else DEFAULT_TIMEOUT
    if not cwd.is_dir():
        return {"status": "not_runnable", "reason": f"cwd `{norm_cwd(entry.get('cwd'))}` "
                "does not exist"}
    t0 = time.time()
    try:
        # A test suite's own output, so UTF-8 with `replace`: the goals and assertions in
        # this repo's fixtures are Czech, the locale default would decode them as cp1252
        # on Windows, and a suite that prints a byte nobody can decode must still be
        # measurable — `evidence` is a line count and an exit code, not a transcript.
        r = subprocess.run(script, shell=True, cwd=str(cwd), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "not_runnable",
                "reason": f"timed out after {timeout}s"}
    except OSError as e:
        return {"status": "not_runnable", "reason": f"could not start: {e}"}
    dt = time.time() - t0
    out = r.stdout or ""
    lines = len(out.splitlines())
    ev = f"exit {r.returncode}, {lines} line(s) stdout, {dt:.1f}s"
    if entry.get("before_after"):
        ev += ", sha256:" + hashlib.sha256(out.encode("utf-8", "replace")).hexdigest()[:12]
    v = verdict(entry.get("expect"), r.returncode, out)
    tail = (r.stderr or out).strip().splitlines()
    if v is None:
        return {"status": None, "evidence": ev,
                "reason": f"`expect: {str(entry.get('expect'))[:40]}` is not one of the "
                          "forms this tool reads (exit N, exit != 0, empty output)",
                "tail": tail[-1][:120] if tail else ""}
    return {"status": v, "evidence": ev, "tail": tail[-1][:120] if tail else ""}


def dirty(root, ignored):
    """Working-tree paths that are not HEAD, minus the ones the brief already declared.

    The brief's own directory is skipped at ANY depth, via the same globs check_scope.py
    uses. A literal `.prompire/` prefix test only holds when the brief sits at the git
    root: for a skill vendored into a subdirectory — `scripts/prompire/.prompire/`
    here — git reports the nested path and the prefix never matches, so writing the brief
    made its own baseline refuse to run. It only ever looked correct because the directory
    is normally gitignored and so never reaches this list at all.
    """
    out = []
    r = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1",
                        "--untracked-files=all"], capture_output=True,
                       encoding="utf-8", errors="surrogateescape")
    for line in r.stdout.splitlines():
        p = line[3:].split(" -> ")[-1].strip()
        if p and p not in ignored and not matches_any(ALWAYS_ALLOWED, p):
            out.append(p)
    return out


def _reads_back_as_str(s):
    """Would this unquoted scalar parse back as the same string?

    YAML 1.1 resolves a bare `no`, `off`, `y`, `null`, `~`, `007` or `1e3` to a boolean,
    None or a number. `cmd: no` is a real command on a repo with a `no` script, and it
    re-read as `False` — which every consumer downstream then compared against the
    brief's own `cmd` string and reported as drift. Round-tripping the value is the test;
    an enumerated keyword blacklist is one YAML revision away from being wrong.
    """
    try:
        return yaml.safe_load(s) == s
    except yaml.YAMLError:
        return False


def yaml_str(s):
    s = str(s)
    return s if not re.search(r"[:#\-{}\[\],&*?|>%@`\"']|^\s|\s$", s) \
        and _reads_back_as_str(s) \
        else '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_block(results, head):
    lines = [f"base_rev: {head}", "baseline:"]
    for r in results:
        if r["status"] is None:
            lines.append(f"  # {r['cmd']} — {r.get('reason', 'not classified')}")
            if r.get("evidence"):
                lines.append(f"  #   observed: {r['evidence']}")
            continue
        lines.append(f"  - cmd: {yaml_str(r['cmd'])}")
        if r["cwd"] != ".":
            lines.append(f"    cwd: {yaml_str(r['cwd'])}")
        lines.append(f"    status: {r['status']}")
        if r.get("evidence"):
            lines.append(f"    evidence: {yaml_str(r['evidence'])}")
        if r["status"] == "not_runnable":
            lines.append(f"    reason: {yaml_str(r['reason'])}")
    return "\n".join(lines)


def main(argv):
    # `dirty()` names working-tree paths straight out of git — see check_scope.py's main.
    utf8_stdio()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2
    path = pathlib.Path(args[0])
    try:
        brief = load_brief(str(path))
    except BriefError as e:
        print(str(e))
        return 2
    r = subprocess.run(["git", "-C", str(path.resolve().parent), "rev-parse", "--show-toplevel"],
                       capture_output=True, encoding="utf-8", errors="surrogateescape")
    if r.returncode != 0:
        print(f"{path} is not inside a git repository")
        return 2
    root = pathlib.Path(r.stdout.strip())
    h = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                       capture_output=True, encoding="utf-8", errors="surrogateescape")
    if h.returncode != 0 or not h.stdout.strip():
        # Before the first commit there is no HEAD to name. Falling back to the literal
        # string "HEAD" used to write a base_rev that is a moving ref by construction —
        # rejected by B16, so the brief failed its own linter, and worse it is the exact
        # value check_scope.py must never diff against.
        print("this repository has no commits yet, so there is no commit for `base_rev` "
              "to name. Make the first commit, then re-run: a base that is not a commit "
              "is a base an agent's own commits can move.")
        return 2
    head = h.stdout.strip()[:12]

    ignored = {str(p) for p in as_list(brief.get("dirty_baseline"))}
    d = dirty(root, ignored)
    if d and "--allow-dirty" not in argv:
        print("the working tree is not clean — a baseline measured here is not HEAD:")
        for p in d[:20]:
            print(f"  {p}")
        print("\ncommit or stash, or list these under `dirty_baseline:` in the brief and "
              "re-run with --allow-dirty; an untracked build artifact (`__pycache__/`, "
              "a build directory) belongs in .gitignore instead")
        return 2

    results = []
    for a in acceptance_entries(brief):
        cmd, cwd = norm_cmd(a.get("cmd")), norm_cwd(a.get("cwd"))
        why = classify(a)
        if why:
            res = {"status": "not_runnable", "reason": why}
        else:
            mismatch = workspace_mismatch(root, a)
            # unclassified (exit 1), not a recorded status: a number measured
            # against the wrong copy is worse than no number at all
            res = ({"status": None, "reason": mismatch} if mismatch
                   else run_one(root, a))
        res.update({"cmd": cmd, "cwd": cwd, "transition": effective_transition(a)})
        results.append(res)

    unclassified = [r for r in results if r["status"] is None]
    if "--json" in argv:
        print(json.dumps({"base_rev": head, "results": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = r["status"] or "UNCLASSIFIED"
            print(f"{mark:13s} {r['cmd'][:60]}")
            for k in ("evidence", "reason", "tail"):
                if r.get(k):
                    print(f"              {k}: {r[k]}")
        print("\n--- paste into the brief ---")
        print(render_block(results, head))
        if unclassified:
            print(f"\n{len(unclassified)} command(s) ran but could not be classified. Read "
                  "the output above and record the status yourself, or rewrite `expect` as "
                  "`exit 0` / `exit != 0` / `empty output`.")

    if "--write" in argv:
        text = path.read_text(encoding="utf-8")
        if re.search(r"^(baseline|base_rev):", text, re.M):
            print("\n--write refused: the brief already has a `baseline:` or `base_rev:` "
                  "block. Replace it by hand so nothing measured is silently overwritten.")
            return 1
        path.write_text(text.rstrip("\n") + "\n" + render_block(results, head) + "\n",
                        encoding="utf-8")
        print(f"\nwrote the block to {path}")
    return 1 if unclassified else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
