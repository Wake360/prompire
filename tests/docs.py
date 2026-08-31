#!/usr/bin/env python3
"""Keep the docs and the code from drifting apart.

Run: python3 tests/docs.py
Exit 0 = every enforced rule is traceable and documented, and the shape in SKILL.md is
the shape the tools accept.

The point of this file: a rule that quietly loses its grounding, or a schema field that
exists only in the linter, is exactly the kind of thing nothing else notices.
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import tokenize
import tomllib

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "prompire"))

from brief_common import (  # noqa: E402
    ACCEPTANCE_KEYS,
    BASELINE_KEYS,
    TESTS_POLICIES,
    TOP_KEYS,
    TRANSITIONS,
)
from check_scope import BASE_SOURCE  # noqa: E402
from hook_antigravity_guard import (  # noqa: E402
    FILE_TOOLS as AGY_FILE_TOOLS,
    TARGET_KEY as AGY_TARGET_KEY,
)
from hook_copilot_guard import (  # noqa: E402
    CLAUDE_FILE_TOOLS,
    PATCH_KEYS,
    PATH_KEYS,
    RUNTIME_FILE_TOOLS,
)
from render_brief import TARGETS  # noqa: E402

# Every label check_scope.py can print for where the base came from. The label is most of
# what a verdict is worth, so SKILL.md has to say what each one means; `None`'s prose is
# the one the reader sees, not the key.
BASE_SOURCE_LABELS = [k for k in BASE_SOURCE if k] + ["base uncorroborated"]

TOOLS = ("lint_brief.py", "baseline.py", "check_scope.py", "render_brief.py",
         "brief_common.py")

# The host adapters and the core they share. Listed separately from TOOLS because
# these are not part of the compile→lint→measure→render workflow SKILL.md walks through;
# they are the enforcement half, and `references/hosts.md` is where they are explained.
HOOKS = ("hook_policy.py", "hook_scope_guard.py", "hook_copilot_guard.py",
         "hook_antigravity_guard.py")

# Claims this project does not get to make about itself. `check_scope.py` reads a git
# diff and the hook is an evadable speed bump over four tool names; neither is a
# sandbox, and every one of these words has crept into a README describing something
# weaker. "not a sandbox" is fine and stays — these are the assertion forms only.
OVERCLAIMS = ("sandboxed", "fully secure", "cannot be bypassed", "cannot bypass",
              "tamper-proof", "tamperproof", "unbypassable", "impossible to bypass",
              "guarantees prevention", "prevents all")

PROSE = ("README.md", "SKILL.md", "references/hosts.md", "references/rendering.md",
         "references/rules.md", "references/schema.md", "references/maintaining.md",
         "references/ci.md", "references/threat-model.md")

EXPECTED_INTERFACE = {
    "display_name": "Prompire",
    "short_description": "Create checkable briefs for coding agents",
    "default_prompt": (
        "Use $prompire to turn this coding request into a measured, bounded brief."
    ),
}

PRIMARY_WORKFLOWS = (
    ("SKILL.md", "Primary workflow"),
    ("README.md", "Primary workflow"),
    ("references/hosts.md", "Primary workflow"),
)

PRIMARY_PHASES = (
    "Prepare",
    "Hand off — Prompire does not launch the agent",
    "Verify scope and acceptance",
    "Close explicitly",
)

DIAGNOSTIC_PHASES = (
    "Combined verdict",
    "Individual tools",
)

DIAGNOSTIC_TOOLS = (
    "baseline.py",
    "lint_brief.py",
    "render_brief.py",
    "check_scope.py",
)


def read(rel):
    return (SKILL / rel).read_text(encoding="utf-8")


def markdown_section(text, heading, level=2):
    marks = "#" * level
    match = re.search(
        rf"^{marks} {re.escape(heading)}\s*\n"
        rf"(.*?)(?=^#{{1,{level}}}\s|\Z)",
        text,
        re.M | re.S,
    )
    return match.group(1) if match else None


def shell_commands(section):
    blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", section, re.S)
    return [
        line.strip()
        for block in blocks
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def cli_problems():
    out = []
    for rel, heading in PRIMARY_WORKFLOWS:
        text = read(rel)
        section = markdown_section(text, heading)
        if section is None:
            out.append(f"{rel} has no `## {heading}` section")
            section = ""

        headings = re.findall(r"^### (.+?)\s*$", section, re.M)
        if headings != list(PRIMARY_PHASES):
            out.append(
                f"{rel}'s primary workflow phases are {headings!r}, expected "
                f"{list(PRIMARY_PHASES)!r}"
            )
        else:
            phase_bodies = [
                markdown_section(section, phase, level=3)
                for phase in PRIMARY_PHASES
            ]
            commands = [shell_commands(body) for body in phase_bodies]
            expected = (
                re.compile(
                    r"^prompire prepare (\.prompire/\S+\.yaml) --target generic$"
                ),
                None,
                re.compile(r"^prompire verify (\.prompire/\S+\.yaml)$"),
                re.compile(r"^prompire close (\.prompire/\S+\.yaml)$"),
            )
            matches = [
                pattern.fullmatch(phase_commands[0])
                if pattern is not None and len(phase_commands) == 1
                else None
                for pattern, phase_commands in zip(expected, commands)
            ]
            if commands[1]:
                out.append(f"{rel}'s handoff phase must not run Prompire")
            if any(
                    pattern is not None and match is None
                    for pattern, match in zip(expected, matches)):
                out.append(
                    f"{rel}'s lifecycle commands are not in their exact prepare, "
                    "verify, and close phases"
                )
            elif len({match.group(1) for match in matches if match}) != 1:
                out.append(f"{rel}'s primary workflow uses different brief paths")

        diagnostic = markdown_section(text, "Diagnostic commands")
        if diagnostic is None:
            out.append(f"{rel} has no `## Diagnostic commands` section")
            continue
        headings = re.findall(r"^### (.+?)\s*$", diagnostic, re.M)
        if headings != list(DIAGNOSTIC_PHASES):
            out.append(
                f"{rel}'s diagnostic phases are {headings!r}, expected "
                f"{list(DIAGNOSTIC_PHASES)!r}"
            )
            continue
        combined = markdown_section(diagnostic, DIAGNOSTIC_PHASES[0], level=3)
        individual = markdown_section(diagnostic, DIAGNOSTIC_PHASES[1], level=3)
        if "prompire verify" not in combined:
            out.append(f"{rel}'s combined verdict phase does not name `prompire verify`")
        if rel == "SKILL.md" and re.search(r"\bdeactivation\b", combined, re.I):
            out.append(
                "SKILL.md's combined verdict implies deactivation; only explicit "
                "`prompire close` may deactivate"
            )
        for tool in DIAGNOSTIC_TOOLS:
            if tool not in individual:
                out.append(f"{rel}'s individual tools phase never names `{tool}`")

    try:
        pyproject = tomllib.loads(read("pyproject.toml"))
    except tomllib.TOMLDecodeError as exc:
        out.append(f"pyproject.toml is invalid TOML: {exc}")
    else:
        entrypoint = pyproject.get("project", {}).get("scripts", {}).get("prompire")
        if entrypoint != "prompire:entrypoint":
            out.append(
                "pyproject.toml must expose `project.scripts.prompire` as "
                "`prompire:entrypoint`"
            )

    metadata_path = SKILL / "agents" / "openai.yaml"
    if not metadata_path.is_file():
        out.append("missing agents/openai.yaml")
    else:
        try:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            out.append(f"agents/openai.yaml is invalid YAML: {exc}")
        else:
            if metadata != {"interface": EXPECTED_INTERFACE}:
                out.append(
                    "agents/openai.yaml must contain exactly the required interface "
                    f"metadata, got {metadata!r}"
                )
    return out


def enforced_rule_ids():
    src = read("prompire/lint_brief.py")
    return sorted({m.group(1) for m in re.finditer(r'(?:err|warn)\(\s*"(B\d+)\s', src)},
                  key=lambda r: int(r[1:]))


def skill_shape():
    """The yaml block in SKILL.md, with the placeholder values stripped out."""
    block = re.search(r"```yaml\n(.*?)```", read("SKILL.md"), re.S)
    if not block:
        return None
    text = re.sub(r"<[^>\n]*>", "placeholder", block.group(1))
    return yaml.safe_load(text)


ENFORCED_RULE_COUNT = 18  # exact, not a floor — a deletion must fail this, not slide under it

NUMBER_WORDS = {n: w for n, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
     "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
     "seventeen", "eighteen", "nineteen", "twenty"))}


def prose_rule_count(text):
    """The rule count SKILL.md states in prose, spelled out, or None if it says none.

    SKILL.md said "Fifteen rules, ids `B1`–`B15`" for as long as there were sixteen. The
    count in the code was already pinned exactly; the sentence a reader actually reads
    was not pinned to anything, which is the only reason it could drift.
    """
    m = re.search(r"^(\w+) rules, ids `B1`", text, re.M | re.I)
    if not m:
        return None
    word = m.group(1).lower()
    return next((n for n, w in NUMBER_WORDS.items() if w == word), -1)


def release_problems():
    """VERSION, the newest CHANGELOG heading and README's own claim must agree.

    A release whose changelog was not updated is the ordinary way a version number stops
    meaning anything, and nothing else here would notice: no test reads a version, so it
    can be bumped in one file and left in the other indefinitely.
    """
    out = []
    for f in ("README.md", "CHANGELOG.md", "VERSION", "pyproject.toml"):
        if not (SKILL / f).is_file():
            out.append(f"missing {f}")
    if out:
        return out
    version = read("VERSION").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        out.append(f"VERSION is `{version}`, not a MAJOR.MINOR.PATCH number")
    heads = re.findall(r"^##\s*\[?(\d+\.\d+\.\d+)\]?", read("CHANGELOG.md"), re.M)
    if not heads:
        out.append("CHANGELOG.md has no `## <version>` heading")
    elif heads[0] != version:
        out.append(f"VERSION says {version}, but the newest CHANGELOG.md entry is "
                   f"{heads[0]} — one of them was not updated")
    try:
        pyproject = tomllib.loads(read("pyproject.toml"))
    except tomllib.TOMLDecodeError as exc:
        out.append(f"pyproject.toml is invalid TOML: {exc}")
    else:
        project_version = pyproject.get("project", {}).get("version")
        if project_version != version:
            out.append(
                f"pyproject.toml project.version says {project_version}, but VERSION "
                f"and the current CHANGELOG.md heading say {version}"
            )
    return out


def release_version_regression_problems():
    global SKILL
    original = SKILL
    try:
        with tempfile.TemporaryDirectory(prefix="prompire-release-check-") as tmp:
            SKILL = pathlib.Path(tmp)
            (SKILL / "README.md").write_text("fixture\n", encoding="utf-8")
            (SKILL / "VERSION").write_text("1.2.3\n", encoding="utf-8")
            (SKILL / "CHANGELOG.md").write_text(
                "## 1.2.3 — 2026-07-29\n", encoding="utf-8")
            (SKILL / "pyproject.toml").write_text(
                "[project]\nversion = \"9.9.9\"\n", encoding="utf-8")
            findings = release_problems()
    finally:
        SKILL = original
    if any("project.version" in finding for finding in findings):
        return []
    return ["release consistency does not detect a mismatched pyproject project.version"]


def host_problems():
    """Two hosts, one boundary — and the prose has to keep saying so.

    Everything checked here is a place where adding host support quietly half-lands: a
    renderer target nothing documents, an adapter shipped but never explained, a tool
    the code reads and the docs never mention. None of it is visible in a diff stat.
    """
    if not (SKILL / "references/hosts.md").is_file():
        return ["missing references/hosts.md — the host matrix has nowhere to live"]
    hosts = read("references/hosts.md")
    out = []

    rendering = read("references/rendering.md")
    for t in TARGETS:
        if f"`{t}`" not in rendering:
            out.append(f"render_brief.py offers the `{t}` target, which "
                       "references/rendering.md never describes")

    for name in HOOKS:
        if not (SKILL / "prompire" / name).exists():
            out.append(f"missing {name}")
        elif name not in hosts:
            out.append(f"{name} ships but references/hosts.md never names it")

    for t in RUNTIME_FILE_TOOLS + CLAUDE_FILE_TOOLS:
        if f"`{t}`" not in hosts:
            out.append(f"hook_copilot_guard.py reads the `{t}` tool, but hosts.md does "
                       "not list it as supported")
    for k in PATH_KEYS + PATCH_KEYS:
        if f"`{k}`" not in hosts:
            out.append(f"hook_copilot_guard.py reads the `{k}` argument, which hosts.md "
                       "does not document")
    for t in AGY_FILE_TOOLS:
        if f"`{t}`" not in hosts:
            out.append(f"hook_antigravity_guard.py reads the `{t}` tool, but hosts.md "
                       "does not list it as supported")
    if f"`{AGY_TARGET_KEY}`" not in hosts:
        out.append(f"hook_antigravity_guard.py reads the `{AGY_TARGET_KEY}` argument, "
                   "which hosts.md does not document")

    for loc in ("~/.claude/skills/prompire/", "~/.copilot/skills/prompire/",
                ".github/skills/prompire/", ".claude/skills/prompire/",
                ".agents/skills/prompire/", ".github/hooks/", "~/.copilot/hooks/",
                "%USERPROFILE%\\.copilot\\hooks\\", "$COPILOT_HOME/hooks/",
                "~/.gemini/config/skills/prompire/", ".agents/hooks.json",
                "~/.gemini/config/hooks.json"):
        if loc not in hosts:
            out.append(f"references/hosts.md does not document the `{loc}` location")

    # The shell gap is load-bearing prose, not a footnote: the hook's whole claim is
    # bounded by it, and a hosts doc that stops saying so is a hosts doc that overclaims.
    for phrase in ("`bash`", "`powershell`", "check_scope.py", "--activate", "--strict"):
        if phrase not in hosts:
            out.append(f"references/hosts.md never mentions {phrase} — it has to, or the "
                       "hook reads as more than it is")
    if "cloud agent" not in hosts.lower():
        out.append("references/hosts.md must say whether Copilot cloud agent is supported")
    return out


def hook_config_problems():
    """Every shipped hook configuration parses, and its matcher covers exactly the tools
    the adapter actually reads.

    The matcher is the silent half of this feature. A tool the adapter handles but the
    matcher omits is a tool the hook is never invoked for at all — indistinguishable from
    support, right up until the write lands.
    """
    d = SKILL / "examples" / "hooks"
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if not files:
        return ["examples/hooks/ has no hook configurations to validate"]
    hosts = read("references/hosts.md") if (SKILL / "references/hosts.md").is_file() else ""
    out = []
    for f in files:
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            out.append(f"examples/hooks/{f.name} is not valid JSON: {e}")
            continue
        if f"examples/hooks/{f.name}" not in hosts:
            out.append(f"examples/hooks/{f.name} ships but hosts.md never points at it")
        if f.name.startswith("antigravity"):
            # Antigravity's schema has no top-level `hooks` object: named hook groups,
            # each mapping event names to matcher groups. Validated on its own terms.
            out += _antigravity_config_problems(f, cfg)
            continue
        if not isinstance(cfg, dict) or not isinstance(cfg.get("hooks"), dict):
            out.append(f"examples/hooks/{f.name} has no `hooks` object")
            continue
        if not f.name.startswith("copilot"):
            continue
        if cfg.get("version") != 1:
            out.append(f"examples/hooks/{f.name} must declare hook config `version: 1`, "
                       f"got {cfg.get('version')!r}")
        for event, entries in cfg["hooks"].items():
            if event not in ("preToolUse", "PreToolUse"):
                out.append(f"examples/hooks/{f.name} configures `{event}`; Prompire is a "
                           "pre-tool-use guard only")
                continue
            for entry in entries:
                tokens = {t for t in str(entry.get("matcher", "")).split("|") if t}
                want = (set(RUNTIME_FILE_TOOLS) if event == "preToolUse"
                        else {"Write", "Edit"})
                if tokens != want:
                    out.append(f"examples/hooks/{f.name} matches {sorted(tokens)} on "
                               f"`{event}`, but the adapter reads {sorted(want)} — a tool "
                               "the matcher omits is one the hook never runs for")
                if tokens & {"bash", "powershell", "Bash"}:
                    out.append(f"examples/hooks/{f.name} configures a shell tool. Shell "
                               "writes are not intercepted; claiming otherwise in a "
                               "shipped config is worse than the documented gap")
                for key in ("bash", "powershell", "command"):
                    cmd = entry.get(key)
                    if cmd and "hook_copilot_guard.py" not in cmd:
                        out.append(f"examples/hooks/{f.name}'s `{key}` does not invoke "
                                   "hook_copilot_guard.py")
    return out


def _antigravity_config_problems(f, cfg):
    """One named group per file, PreToolUse only, the matcher naming exactly the tools
    the adapter reads, the command invoking the adapter. Same reasoning as the Copilot
    checks: a matcher that omits a handled tool is a silent hole, and a matcher that
    names the shell claims an interception that does not happen."""
    out = []
    if not isinstance(cfg, dict) or not cfg or not all(
            isinstance(group, dict) for group in cfg.values()):
        return [f"examples/hooks/{f.name} is not a mapping of named hook groups"]
    for group_name, group in cfg.items():
        for event, entries in group.items():
            if event == "enabled":
                continue
            if event != "PreToolUse":
                out.append(f"examples/hooks/{f.name} configures `{event}` in "
                           f"`{group_name}`; Prompire is a pre-tool-use guard only")
                continue
            for entry in entries:
                tokens = {t for t in str(entry.get("matcher", "")).split("|") if t}
                if tokens != set(AGY_FILE_TOOLS):
                    out.append(f"examples/hooks/{f.name} matches {sorted(tokens)}, but "
                               f"the adapter reads {sorted(AGY_FILE_TOOLS)} — a tool "
                               "the matcher omits is one the hook never runs for")
                if tokens & {"run_command", "bash", "powershell"}:
                    out.append(f"examples/hooks/{f.name} configures a shell tool. Shell "
                               "writes are not intercepted; claiming otherwise in a "
                               "shipped config is worse than the documented gap")
                for handler in entry.get("hooks", []) or [{}]:
                    cmd = handler.get("command")
                    if not cmd or "hook_antigravity_guard.py" not in cmd:
                        out.append(f"examples/hooks/{f.name}'s command does not invoke "
                                   "hook_antigravity_guard.py")
    return out


def overclaim_problems():
    """The project's own stance, enforced against the project's own prose.

    README.md spends a whole paragraph saying what the guarantee is *not*, and
    references/threat-model.md carries the limitations table so the claim stops where
    the evidence does. One confident adjective in a later edit undoes that, and nothing
    else in this suite would notice.
    """
    out = []
    for rel in PROSE:
        if not (SKILL / rel).is_file():
            continue
        low = read(rel).lower()
        for word in OVERCLAIMS:
            if word in low:
                out.append(f"{rel} claims `{word}` — this tool is an evadable hook plus a "
                           "diff reader, and says so everywhere else")
    return out


def truth_boundary_problems():
    """The checker's coverage claim must carry its own limit wherever it appears.

    `check_scope.py`'s evidence is `git diff` plus `git status --untracked-files=all`,
    and both exclude gitignored paths — reproduced: a file planted under an ignored
    `vendor/` draws exit 0 with zero findings. So prose may say a change is seen
    "whatever tool made it" only on a line that also says the coverage is of
    git-visible changes. Line-scoped on purpose: the qualification a reader gets is
    the one in the sentence they are reading, not one three paragraphs away.
    """
    out = []
    for rel in PROSE:
        if not (SKILL / rel).is_file():
            continue
        for n, line in enumerate(read(rel).splitlines(), 1):
            if "whatever tool made it" in line and "git-visible" not in line:
                out.append(f"{rel}:{n} claims changes are seen whatever tool made "
                           "them, without the git-visible qualification — gitignored "
                           "paths are outside the checker's evidence, and the line "
                           "making the claim has to say so")
    return out


def truth_boundary_regression_problems():
    global SKILL
    original = SKILL
    try:
        with tempfile.TemporaryDirectory(prefix="prompire-truth-boundary-") as tmp:
            SKILL = pathlib.Path(tmp)
            (SKILL / "README.md").write_text(
                "git sees the write whatever tool made it\n", encoding="utf-8")
            findings = truth_boundary_problems()
    finally:
        SKILL = original
    if findings:
        return []
    return ["truth-boundary check does not detect an unqualified coverage claim"]


BINARY_MODES = {"rb", "wb", "ab", "rb+", "wb+", "ab+", "r+b", "w+b", "a+b", "xb", "x+b"}


def tracked_py():
    # An installed copy has no `.git` — the sync ships the same tracked `*.py`
    # set minus the repo scaffolding, so a glob scans the same files there.
    listed = subprocess.run(
        ["git", "-C", str(SKILL), "ls-files", "*.py"], capture_output=True,
        encoding="utf-8")
    if listed.returncode == 0:
        return listed.stdout.splitlines()
    return sorted(p.relative_to(SKILL).as_posix()
                  for p in SKILL.rglob("*.py") if "__pycache__" not in p.parts)


def tokens_of(rel):
    with open(SKILL / rel, "rb") as f:
        return list(tokenize.tokenize(f.readline))


def kwargs_of(tokens, i):
    """The keyword names passed directly to the call whose `(` is at `tokens[i + 1]`,
    plus the index of its closing paren. Only depth 1, so a keyword belonging to a
    nested call is not credited to this one."""
    depth = 0
    names = set()
    j = i + 1
    while j < len(tokens):
        t = tokens[j]
        if t.type == tokenize.OP and t.string == "(":
            depth += 1
        elif t.type == tokenize.OP and t.string == ")":
            depth -= 1
            if depth == 0:
                break
        elif (depth == 1 and t.type == tokenize.NAME and j + 1 < len(tokens)
              and tokens[j + 1].type == tokenize.OP and tokens[j + 1].string == "="):
            names.add(t.string)
        j += 1
    return names, j


def decoder_problems():
    """No tracked `*.py` file may capture a child's output as text without an explicit
    `encoding=`.

    `text=True` (and `universal_newlines=True`) decode the child's stdout and stderr
    with the *locale* encoding, the same defaulting bug as `open()` without
    `encoding=` — so on Windows a `git diff --name-status` naming a non-ASCII path
    comes back either mojibake (cp1252 decodes almost every byte, silently) or as a
    `UnicodeDecodeError`. In `check_scope.py` the first corrupts a verdict and the
    second replaces one with a traceback, and this tool's vocabulary for "could not
    decide" is exit 2, not a stack trace. git speaks UTF-8, so `encoding="utf-8"` is
    the right decoder rather than a workaround; each site picks its own `errors=`.

    A call that omits every text-mode keyword captures bytes and is left alone — that
    is a deliberate choice, not a defaulted one.
    """
    problems = []
    for rel in tracked_py():
        tokens = tokens_of(rel)
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if (tok.type == tokenize.NAME and tok.string in ("run", "Popen", "check_output")
                    and i + 1 < len(tokens) and tokens[i + 1].type == tokenize.OP
                    and tokens[i + 1].string == "("
                    and i >= 2 and tokens[i - 1].string == "."
                    and tokens[i - 2].string == "subprocess"):
                names, end = kwargs_of(tokens, i)
                if names & {"text", "universal_newlines"} and "encoding" not in names:
                    problems.append(f"{rel}:{tok.start[0]}: `subprocess.{tok.string}(...)` "
                                    "decodes the child's output with no `encoding=` — "
                                    "that is the locale encoding, which is not UTF-8 on "
                                    "Windows")
                i = end
            i += 1
    return problems


def encoding_problems():
    """No tracked `*.py` file may do text I/O without an explicit `encoding=`.

    `write_text()`/`read_text()`/`open()` fall back to the *locale* encoding when
    `encoding=` is omitted — cp1252 on Windows, which raises on any non-ASCII text
    (Czech goals in the fixtures, non-ASCII repo paths, ...). This is a source scan
    rather than a run under `-X warn_default_encoding` because the bug is a missing
    keyword argument, not a runtime code path — a scan catches every call regardless
    of whether a test happens to exercise it with non-ASCII bytes. Tokenizing (rather
    than a line-based regex) is what keeps this from firing on a comment or docstring
    that merely mentions `write_text()`, or on a YAML fixture string containing
    `python -c "...write_text('x')..."` as command text a test runs.
    """
    problems = []
    for rel in tracked_py():
        path = SKILL / rel
        with open(path, "rb") as f:
            tokens = list(tokenize.tokenize(f.readline))

        call_names = {"write_text", "read_text", "open"}
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if (tok.type == tokenize.NAME and tok.string in call_names
                    and i + 1 < len(tokens)
                    and tokens[i + 1].type == tokenize.OP
                    and tokens[i + 1].string == "("):
                # skip os.open(...) — flags-based, not text-mode I/O
                if (tok.string == "open" and i >= 2
                        and tokens[i - 1].type == tokenize.OP and tokens[i - 1].string == "."
                        and tokens[i - 2].type == tokenize.NAME and tokens[i - 2].string == "os"):
                    i += 1
                    continue
                depth = 0
                j = i + 1
                has_encoding = False
                has_binary_mode = False
                while j < len(tokens):
                    t = tokens[j]
                    if t.type == tokenize.OP and t.string == "(":
                        depth += 1
                    elif t.type == tokenize.OP and t.string == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    elif depth == 1 and t.type == tokenize.NAME and t.string == "encoding":
                        has_encoding = True
                    elif (depth == 1 and t.type == tokenize.STRING
                          and t.string.strip("'\"") in BINARY_MODES):
                        has_binary_mode = True
                    j += 1
                if not has_encoding and not has_binary_mode:
                    problems.append(f"{rel}:{tok.start[0]}: `{tok.string}(...)` has no "
                                    "`encoding=` — defaults to the locale encoding, "
                                    "which is not UTF-8 on Windows")
                i = j
            i += 1
    return problems


def _walk_uses(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "uses" and isinstance(v, str):
                out.append(v)
            else:
                _walk_uses(v, out)
    elif isinstance(node, list):
        for item in node:
            _walk_uses(item, out)


def action_pin_problems():
    out = []
    pinned = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
    docker_pinned = re.compile(r"^docker://[^@\s]+@sha256:[0-9a-f]{64}$")
    paths = set((SKILL / ".github").rglob("*.yml"))
    paths.update((SKILL / ".github").rglob("*.yaml"))
    for path in sorted(paths):
        rel = path.relative_to(SKILL).as_posix()
        refs = []
        _walk_uses(yaml.safe_load(path.read_text(encoding="utf-8")), refs)
        for ref in refs:
            if ref.startswith("./"):
                continue
            if pinned.fullmatch(ref) or docker_pinned.fullmatch(ref):
                continue
            out.append(f"{rel} uses mutable third-party action `{ref}`")
    return out


def brief_lifecycle_problems():
    """One lifecycle rule everywhere: state files ignored always, briefs
    tracked when the Action reads them. README said the opposite of ci.md for
    two releases and nothing noticed."""
    out = []
    for rel in ("README.md", "references/ci.md"):
        text = read(rel)
        if ".prompire/*" not in text or "!.prompire/*.yaml" not in text:
            out.append(f"{rel} does not show the brief-tracking ignore pattern")
    if "belongs in `.gitignore`" in read("README.md"):
        out.append("README.md reverted to the one-rule gitignore claim; the "
                   "brief-tracking rule depends on whether CI reads the brief")
    if "references/ci.md" not in read("SKILL.md"):
        out.append("SKILL.md never points at references/ci.md, so the tracked-"
                   "brief half of the lifecycle is undiscoverable from the skill")
    return out


def verdict_vocabulary_problems():
    """verify's four verdict states and the repin remedy must be explained in
    README with the exact strings render_human_verdict prints."""
    readme = read("README.md")
    out = []
    for token in ("`clean`", "`caught: ", "`review: ", "needs a human",
                  "`no verdict", "--ack-disarms"):
        if token not in readme:
            out.append(f"README.md never explains {token!r} — verify prints it "
                       "and the reader has to be able to classify the line")
    return out


def benchmark_claim_problems():
    """Every quantitative benchmark claim in README recomputes from the
    committed rows, so a number cannot silently outlive its evidence."""
    rows = []
    for path in sorted((SKILL / "bench" / "campaigns").glob("*/run*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        return ["bench/campaigns/ holds no rows — README's numbers have no source"]
    bare = [r for r in rows if r["variant"] == "bare"]
    briefed = [r for r in rows if r["variant"] != "bare"]
    caught = sum(1 for r in bare
                 if r["test_files_changed"] and r["scope_exit"] == 1)
    drifted = sum(1 for r in briefed if r["scope_exit"] != 0)
    tampered = sum(1 for r in rows if r["tampered"])
    readme = read("README.md")
    out = []
    for phrase in (f"{caught} of {len(bare)}", f"{drifted} of {len(briefed)}"):
        if phrase not in readme:
            out.append(f"README.md does not carry the recomputed figure "
                       f"`{phrase}` — either the prose or the rows changed")
    if tampered == 0 and "tamper" not in readme.lower():
        out.append("README.md stopped saying what was (not) observed about "
                   "tampering; the design threat needs its measured status")
    if tampered != 0:
        out.append(f"{tampered} tampered row(s) exist; README's zero-tamper "
                   "wording is stale and every tamper claim must be rewritten")
    return out


def ci_pin_problems():
    """The ci.md example pins the Action at the release this repo is at."""
    version = read("VERSION").strip()
    pins = re.findall(r"prompire-verify@v(\d+\.\d+\.\d+)", read("references/ci.md"))
    if not pins:
        return ["references/ci.md shows no pinned prompire-verify version"]
    return [f"references/ci.md pins prompire-verify@v{pin}, but this release "
            f"is {version}" for pin in pins if pin != version]


def main():
    problems = []
    rules = enforced_rule_ids()
    if len(rules) != ENFORCED_RULE_COUNT:
        problems.append(f"expected {ENFORCED_RULE_COUNT} rule ids in lint_brief.py, found "
                        f"{len(rules)}: {rules}")

    skill = read("SKILL.md")
    stated = prose_rule_count(skill)
    if stated != len(rules):
        problems.append(f"SKILL.md says there are {stated} rules; {len(rules)} are "
                        "enforced — the sentence a reader reads must match the code")
    if f"`B1`–`B{len(rules)}`" not in skill and f"`B1`-`B{len(rules)}`" not in skill:
        problems.append(f"SKILL.md does not give the rule id range as B1-B{len(rules)}")

    # The documented workflow decides which guarantee a user actually gets. Without
    # --activate it produces the weakest one (`base uncorroborated`), in which one Write
    # to the brief buys a clean verdict — so the strongest state the tool has would be
    # opt-in and undiscoverable. This is a doc defect that no other test can see.
    for claim, why in (
            ("--activate", "the workflow would produce an uncorroborated base"),
            ("--deactivate", "nothing would tell the user how to disarm"),
            ("--strict", "reviewers run it, and it turns an uncorroborated base into "
                         "exit 1")):
        if claim not in skill:
            problems.append(f"SKILL.md never mentions `{claim}` — {why}")
    for label in BASE_SOURCE_LABELS:
        if f"`{label}`" not in skill:
            problems.append(f"SKILL.md never explains the `{label}` base-source label, "
                            "which check_scope.py prints on every run")

    grounding, rulesdoc, schema = read("references/grounding.md"), \
        read("references/rules.md"), read("references/schema.md")
    for r in rules:
        if not re.search(rf"\b{r}\b", grounding):
            problems.append(f"{r} is enforced but has no entry in grounding.md — trace "
                            "it or delete the rule")
        if not re.search(rf"\|\s*{r}\s*\|", rulesdoc):
            problems.append(f"{r} is enforced but missing from the rules.md table")

    shape = skill_shape()
    if shape is None:
        problems.append("SKILL.md has no yaml shape block")
    else:
        for k in shape:
            if k not in TOP_KEYS:
                problems.append(f"SKILL.md shape uses `{k}`, which the tools would drop")
        for k in ("goal", "scope", "acceptance", "autonomy", "baseline"):
            if k not in shape:
                problems.append(f"SKILL.md shape omits the mandatory key `{k}`")
        for entry in shape.get("acceptance") or []:
            for k in entry:
                if k not in ACCEPTANCE_KEYS:
                    problems.append(f"SKILL.md acceptance entry uses unknown key `{k}`")
        for entry in shape.get("baseline") or []:
            for k in entry:
                if k not in BASELINE_KEYS:
                    problems.append(f"SKILL.md baseline entry uses unknown key `{k}`")

    for k in sorted(TOP_KEYS | ACCEPTANCE_KEYS | BASELINE_KEYS):
        if not re.search(rf"`{re.escape(k)}`", schema):
            problems.append(f"schema.md never defines `{k}`")
    for v in TESTS_POLICIES + TRANSITIONS:
        if not re.search(rf"`{v}`", schema):
            problems.append(f"schema.md never defines the value `{v}`")

    # the personal mirror note belongs to the maintainer file, not the runtime workflow
    if "rsync" in read("SKILL.md"):
        problems.append("SKILL.md carries mirror-maintenance instructions again")
    if "rsync" not in read("references/maintaining.md"):
        problems.append("maintaining.md lost the mirror sync command")

    problems += release_problems()
    problems += release_version_regression_problems()
    problems += cli_problems()
    problems += host_problems()
    problems += hook_config_problems()
    problems += overclaim_problems()
    problems += truth_boundary_problems()
    problems += truth_boundary_regression_problems()
    problems += encoding_problems()
    problems += decoder_problems()
    problems += action_pin_problems()
    problems += brief_lifecycle_problems()
    problems += verdict_vocabulary_problems()
    problems += benchmark_claim_problems()
    problems += ci_pin_problems()

    skill_md = read("SKILL.md")
    for rel, name in (("README.md", "hook_copilot_guard.py"),
                      ("README.md", "references/hosts.md"),
                      ("SKILL.md", "references/hosts.md")):
        if name not in read(rel):
            problems.append(f"{rel} never points at {name} — a second host nobody can "
                            "find is not supported")
    # SKILL.md is the one file BOTH hosts read, so a command in it that names one host's
    # install path is a command the other host's user cannot run — `~/.copilot/skills/`
    # and `.github/skills/` are equally valid homes. The tools table says `$PROMPIRE` is
    # the skill directory; the commands have to use it.
    if "~/.claude/skills/prompire/" in skill_md:
        problems.append("SKILL.md hardcodes `~/.claude/skills/prompire/`, which is one "
                        "host's install path — both hosts read this file, so use the "
                        "`$PROMPIRE` placeholder the tools table defines")
    if "--target copilot" not in skill_md and "`copilot`" not in skill_md:
        problems.append("SKILL.md does not offer the `copilot` render target, so the "
                        "workflow it documents cannot be followed on that host")

    for t in TOOLS:
        if not (SKILL / "prompire" / t).exists():
            problems.append(f"missing tool {t}")
    for t in TOOLS[:4]:
        if f"`{t}" not in read("SKILL.md") and t not in read("SKILL.md"):
            problems.append(f"SKILL.md never mentions {t}")

    for p in problems:
        print(f"FAIL  {p}")
    print(f"\n{len(rules)} enforced rules, {len(problems)} inconsistenc"
          f"{'y' if len(problems) == 1 else 'ies'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
