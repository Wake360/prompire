#!/usr/bin/env python3
"""Keep the docs and the code from drifting apart.

Run: python3 tests/docs.py
Exit 0 = every enforced rule is traceable and documented, and the shape in SKILL.md is
the shape the tools accept.

The point of this file: a rule that quietly loses its grounding, or a schema field that
exists only in the linter, is exactly the kind of thing nothing else notices.
"""
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

# Every label check_scope.py can print for where the base came from. The label is most of
# what a verdict is worth, so SKILL.md has to say what each one means; `None`'s prose is
# the one the reader sees, not the key.
BASE_SOURCE_LABELS = [k for k in BASE_SOURCE if k] + ["base uncorroborated"]

TOOLS = ("lint_brief.py", "baseline.py", "check_scope.py", "render_brief.py",
         "brief_common.py")


def read(rel):
    return (SKILL / rel).read_text(encoding="utf-8")


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
