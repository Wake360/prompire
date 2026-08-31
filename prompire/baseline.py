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


SHELL_OPERATORS = frozenset((";", "&&", "||", "|", "&", "(", ")", ">", "<", ">>"))


def shell_segments(cmd):
    """The token list of each simple command in `cmd`, split on shell separators
    that are **not** inside quotes.

    Quoting has to be respected in both directions. Splitting a `-c "import x;
    raise ..."` payload at its inner `;` loses the command entirely, which is how
    the workspace probe stopped seeing the very shape it exists to catch; and a
    `more` inside a quoted string must not land in executable position, which is
    the E1 pager false positive. Physical lines are joined until they lex, so a
    quoted string spanning newlines stays one token."""
    segments, pending, heredoc = [], "", None
    lines = shell_text(cmd).splitlines() or [""]
    for line in lines:
        # A heredoc body is data the shell feeds to a command, not a command:
        # `grep -q hi <<'EOF'` / `less is more` / `EOF` must not put `less` in
        # executable position (adversarial review, Reviewer C — the same
        # false-positive shape as E1's `more`).
        if heredoc is not None:
            if line.strip() == heredoc:
                heredoc = None
            continue
        opener = re.search(r"<<-?\s*(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z_]\w*))", line)
        if opener:
            heredoc = next(g for g in opener.groups() if g is not None)
        candidate = f"{pending}\n{line}" if pending else line
        try:
            lexer = shlex.shlex(candidate, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            pending = candidate  # an unbalanced quote continues on the next line
            continue
        pending = ""
        current = []
        for token in tokens:
            if token in SHELL_OPERATORS:
                if current:
                    segments.append(current)
                current = []
            else:
                current.append(token)
        if current:
            segments.append(current)
    return segments


def _leading(tokens):
    """(environment assignments, index of the word in executable position)."""
    assignments, index = [], 0
    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            assignments.append(token)
            index += 1
            continue
        if token.replace("\\", "/").rsplit("/", 1)[-1].lower() in COMMAND_PREFIXES:
            index += 1
            continue
        break
    return assignments, index


def _command_words(cmd):
    """The word in executable position of each simple command in a shell line."""
    words = []
    for tokens in shell_segments(cmd):
        _, index = _leading(tokens)
        if index < len(tokens):
            words.append(tokens[index].replace("\\", "/").rsplit("/", 1)[-1].lower())
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


def shell_text(cmd):
    """The command as the shell will read it, with line continuations spliced.

    `run_one` executes the raw `cmd`, so everything that decides whether it is
    safe to run has to read the same bytes. Scanning the whitespace-normalised
    spelling instead let a two-character edit hide the command from the guards:
    `r\\<newline>m -rf x` normalises to `r\\ m -rf x`, which matches nothing, and
    splices in the shell to `rm -rf x`, which is what actually ran (adversarial
    review, Reviewer C). Splicing first is what the shell itself does."""
    return re.sub(r"\\\n", "", str(cmd or ""))


def classify(entry):
    """Why this command will not be run on HEAD, or None if it is safe to run."""
    cmd = shell_text(entry.get("cmd"))
    req = [str(r).strip().lower() for r in as_list(entry.get("requires")) if str(r).strip()]
    if req:
        return f"declared requires: {', '.join(sorted(set(req)))}"
    m = DESTRUCTIVE.search(cmd)
    if m:
        return f"destructive command (`{m.group(0).strip()}`); not run for a baseline"
    hit = interactive_hit(cmd)
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
    """Top-level package names this checkout itself defines: a directory holding an
    __init__.py — or any .py at all, which is a PEP 420 namespace package, the
    layout most prone to install-vs-workspace shadowing — at the repo root, under
    src/, or the same pair under the entry's cwd (monorepos). Existence of the name
    is what creates the shadowing hazard.

    A name here is a candidate, not a finding: the probe only refuses when that name
    is also importable AND resolves outside the checkout, so a directory that merely
    looks like a package (`tests/`, `docs/`) costs nothing."""
    names = set()
    for base in (root, root / "src", cwd, cwd / "src"):
        try:
            children = list(base.iterdir()) if base.is_dir() else []
        except OSError:
            children = []
        for child in children:
            if not child.is_dir():
                continue
            try:
                if (child / "__init__.py").is_file() or any(child.glob("*.py")):
                    names.add(child.name)
            except OSError:
                continue
    return names


def _flag_value(args, index, flag):
    """The value of `-m`/`-c` at `args[index]`, separated or joined (`-mpytest`)."""
    tok = args[index]
    if tok == flag:
        return args[index + 1] if index + 1 < len(args) else None
    if tok.startswith(flag) and len(tok) > len(flag):
        return tok[len(flag):]
    return None


def _segment_targets(args, packages):
    """Which workspace packages this interpreter's arguments would exercise."""
    for i in range(len(args)):
        module = _flag_value(args, i, "-m")
        if module is not None:
            top = module.split(".")[0]
            if top in TEST_RUNNER_MODULES:
                return sorted(packages)  # the repo's suite exercises the repo
            return [top] if top in packages else []
        code = _flag_value(args, i, "-c")
        if code is not None:
            return sorted(p for p in packages
                          if re.search(rf"\b{re.escape(p)}\b", code))
    return []


def _probe_plans(entry, packages):
    """Every (env assignments, interpreter, packages) this command would exercise.

    Whole segments, not just the first token: an inline `PYTHONPATH=… python3 …`
    (the literal shape that mis-measured E1's T05), an `env`/`nohup` wrapper, and a
    `python3` after `&&` or a pipe each reach the same import, and reading only
    `argv[0]` missed all three. The leading assignments are carried into the probe
    so a command that points itself at an installed copy is asked in the environment
    it actually creates."""
    plans = []
    for tokens in shell_segments(entry.get("cmd")):
        assignments, index = _leading(tokens)
        if index >= len(tokens):
            continue
        interp = tokens[index]
        if not PYTHON_INTERP.match(interp.replace("\\", "/").rsplit("/", 1)[-1]):
            continue
        targets = _segment_targets(tokens[index + 1:], packages)
        if targets:
            plans.append((tuple(assignments), interp, targets))
    return plans


def import_origin(interp, package, cwd, assignments=()):
    """Where `import <package>` under this interpreter resolves, or None when the
    probe is inconclusive (interpreter missing, package not importable at all).

    `assignments` are the command's own leading environment assignments, replayed
    verbatim so a command that points itself at an installed copy is asked in the
    environment it builds for itself rather than in ours."""
    key = (tuple(assignments), interp, package, str(cwd))
    if key not in _PROBE_CACHE:
        code = (f"import {package}, os; print(os.path.abspath((getattr({package}, "
                f"'__file__', None) or (list(getattr({package}, '__path__', [])) "
                f"or [''])[0]) or ''))")
        probe = " ".join([*assignments, interp, "-c", f'"{code}"'])
        try:
            # Through the shell like the measurement itself, so PATH and the inline
            # assignments resolve exactly as they will for the acceptance command.
            r = subprocess.run(probe, shell=True, cwd=str(cwd),
                               capture_output=True, encoding="utf-8",
                               errors="replace", timeout=30)
            out = (r.stdout or "").strip().splitlines()
            _PROBE_CACHE[key] = out[-1] if r.returncode == 0 and out else None
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
    real_root = os.path.realpath(root)
    for assignments, interp, targets in _probe_plans(entry, packages):
        for package in targets:
            origin = import_origin(interp, package, cwd, assignments)
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
    except Exception:
        # Any failure to read the value back — a YAMLError, or a tag constructor
        # raising a bare KeyError — means it does not round-trip as this string,
        # so quote it. Failing toward quoting is the direction that preserves it.
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
