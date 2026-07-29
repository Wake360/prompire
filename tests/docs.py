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
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL))

from brief_common import (  # noqa: E402
    ACCEPTANCE_KEYS,
    BASELINE_KEYS,
    TESTS_POLICIES,
    TOP_KEYS,
    TRANSITIONS,
)
from check_scope import BASE_SOURCE  # noqa: E402
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

# The two host adapters and the core they share. Listed separately from TOOLS because
# these are not part of the compile→lint→measure→render workflow SKILL.md walks through;
# they are the enforcement half, and `references/hosts.md` is where they are explained.
HOOKS = ("hook_policy.py", "hook_scope_guard.py", "hook_copilot_guard.py")

# Claims this project does not get to make about itself. `check_scope.py` reads a git
# diff and the hook is an evadable speed bump over four tool names; neither is a
# sandbox, and every one of these words has crept into a README describing something
# weaker. "not a sandbox" is fine and stays — these are the assertion forms only.
OVERCLAIMS = ("sandboxed", "fully secure", "cannot be bypassed", "cannot bypass",
              "tamper-proof", "tamperproof", "unbypassable", "impossible to bypass",
              "guarantees prevention", "prevents all")

PROSE = ("README.md", "SKILL.md", "references/hosts.md", "references/rendering.md",
         "references/rules.md", "references/schema.md", "references/maintaining.md")


def read(rel):
    return (SKILL / rel).read_text(encoding="utf-8")


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


def enforced_rule_ids():
    src = read("lint_brief.py")
    return sorted({m.group(1) for m in re.finditer(r'(?:err|warn)\(\s*"(B\d+)\s', src)},
                  key=lambda r: int(r[1:]))


def skill_shape():
    """The yaml block in SKILL.md, with the placeholder values stripped out."""
    block = re.search(r"```yaml\n(.*?)```", read("SKILL.md"), re.S)
    if not block:
        return None
    text = re.sub(r"<[^>\n]*>", "placeholder", block.group(1))
    return yaml.safe_load(text)


ENFORCED_RULE_COUNT = 16  # exact, not a floor — a deletion must fail this, not slide under it

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
    for f in ("README.md", "CHANGELOG.md", "VERSION"):
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
    return out


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
        if not (SKILL / name).exists():
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

    for loc in ("~/.claude/skills/prompire/", "~/.copilot/skills/prompire/",
                ".github/skills/prompire/", ".claude/skills/prompire/",
                ".agents/skills/prompire/", ".github/hooks/", "~/.copilot/hooks/",
                "%USERPROFILE%\\.copilot\\hooks\\", "$COPILOT_HOME/hooks/"):
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


def overclaim_problems():
    """The project's own stance, enforced against the project's own prose.

    README.md spends a whole paragraph saying what the guarantee is *not*, and the
    limitations table exists so the claim stops where the evidence does. One confident
    adjective in a later edit undoes that, and nothing else in this suite would notice.
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
    problems += cli_problems()
    problems += host_problems()
    problems += hook_config_problems()
    problems += overclaim_problems()

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
        if not (SKILL / t).exists():
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
