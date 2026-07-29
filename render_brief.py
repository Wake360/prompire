#!/usr/bin/env python3
"""Render a linted brief for one of the handover targets.

Usage: python3 render_brief.py brief.yaml [--target generic,checklist] [--words]
Targets: claude | generic | codex | copilot | agents.md | claude.md | checklist
Exit 0 = rendered, 1 = a prompt target exceeded the 250-word budget, 2 = unreadable.

Target semantics and the wording rules: references/rendering.md. The renderer is
deterministic — same brief, same bytes — so `tests/golden/` can pin every target.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from brief_common import (
    BriefError,
    acceptance_entries,
    as_list,
    baseline_map,
    effective_transition,
    entry_key,
    load_brief,
    norm_cmd,
    norm_cwd,
    tests_policy_of,
)

TARGETS = ("claude", "generic", "codex", "copilot", "agents.md", "claude.md", "checklist")
WORD_BUDGET = 250
PROMPT_TARGETS = ("claude", "generic", "codex", "copilot")

SKILL_DIR = pathlib.Path(__file__).resolve().parent


def skill_path(name):
    """`~/...` when the skill lives under home, so a rendered checklist is portable and
    a golden file does not pin one machine's home directory."""
    p = SKILL_DIR / name
    try:
        return "~/" + str(p.relative_to(pathlib.Path.home()))
    except ValueError:
        return str(p)

AUTONOMY_LINE = {
    # None of these may authorise a write outside `scope`. "Ask first" is not a route
    # out of the boundary — a wider scope is an edit to the brief.
    "manual": "Produce a plan and stop. Do not edit any file.",
    "ask": "Ask before any step that is risky or hard to undo. The listed paths are the "
           "whole boundary: widening it needs a revised brief, not a yes in chat.",
    "auto": "Run unattended on {rollback}. The listed paths are the whole boundary: "
            "widening it needs a revised brief, not a yes in chat.",
}
TESTS_LINE = {
    "immutable": "Do not create, edit, rename or delete any test file.",
    "named": "The only test files you may change: {editable}. Every other test file is "
             "frozen.",
    "authoring": "Repairing the tests is the task; you may change {editable}. What "
                 "judges the result is {oracle}, not the suite you are editing.",
}


def tests_sentence(brief):
    policy = tests_policy_of(brief)
    if not policy:
        return ""
    return TESTS_LINE[policy].format(
        editable=", ".join(str(t) for t in as_list(brief.get("tests_editable"))) or "(none listed)",
        oracle=str(brief.get("oracle") or "an external check"))


def autonomy_sentence(brief):
    a = str(brief.get("autonomy") or "").strip().lower()
    if a not in AUTONOMY_LINE:
        return "Autonomy was not declared; do not write anything until it is."
    return AUTONOMY_LINE[a].format(rollback=str(brief.get("rollback") or "a scratch branch"))


def state_of(brief, entry):
    """How this criterion reads today, from the measured baseline — never from the
    author's optimism. Returns (short_label, long_label)."""
    b = baseline_map(brief).get(entry_key(entry))
    t = effective_transition(entry, b)
    status = str((b or {}).get("status") or "").strip().lower()
    evidence = str((b or {}).get("evidence") or "").strip()
    reason = str((b or {}).get("reason") or "").strip()
    if t == "flip":
        if status == "not_runnable":
            return ("cannot run yet; must pass when you are done",
                    f"could not run on HEAD ({reason or 'no reason recorded'}) — this is "
                    "the one that must end green")
        return ("fails today; must pass when you are done",
                "was FAILING before the work — this is the one that must end green")
    if t == "hold":
        return ("must stay exactly as measured — do not 'fix' it",
                f"must stay exactly as measured ({evidence or 'no evidence recorded'}) — "
                "do not 'fix' it. A different result is a regression even if it looks better")
    if status == "pass":
        return ("green today; keep it green", "was green; must still be green")
    if not b:
        return ("no baseline recorded", "no baseline was recorded — this box cannot tell "
                                        "you what the agent changed")
    return ("must pass", f"baseline: {status or 'unrecorded'}")


def criteria_lines(brief, long=False):
    out = []
    for a in acceptance_entries(brief):
        cmd = norm_cmd(a.get("cmd"))
        cwd = norm_cwd(a.get("cwd"))
        where = f" (in {cwd}/)" if cwd != "." else ""
        short, longer = state_of(brief, a)
        out.append((f"`{cmd}`{where} → {a.get('expect')}", longer if long else short))
    return out


def numbered(brief):
    return [f"{i}. {cmd} ({note})"
            for i, (cmd, note) in enumerate(criteria_lines(brief), 1)]


def _bullets(title, items, prefix="- "):
    if not items:
        return []
    return [title] + [f"{prefix}{i}" for i in items] + [""]


def render_prompt(brief, brief_path, flavour):
    """claude / generic — one prose block. codex gets the same content as sections."""
    lines = []
    goal = str(brief.get("goal") or "").strip()
    if flavour == "codex":
        lines += ["## Task", goal, ""]
        lines += _bullets("## Files you may edit", [str(s) for s in as_list(brief.get("scope"))])
        lines += _bullets("## Never touch", [str(f) for f in as_list(brief.get("forbidden"))])
        lines += _bullets("## Keep true", [str(c) for c in as_list(brief.get("constraints"))])
        lines += ["## Verify"]
    else:
        lines += [goal, ""]
        lines += _bullets("Files you may edit:",
                          [str(s) for s in as_list(brief.get("scope"))])
        lines += _bullets("Never touch:", [str(f) for f in as_list(brief.get("forbidden"))])
        lines += _bullets("Keep true:", [str(c) for c in as_list(brief.get("constraints"))])
        lines += ["Done when all of these hold:"]
    lines += numbered(brief)
    lines.append("")
    if flavour == "copilot":
        manual = [str(m) for m in as_list(brief.get("manual_checks"))]
        lines += _bullets("No command covers these; a human confirms them:", manual)
    ts = tests_sentence(brief)
    if ts:
        lines += [ts, ""]
    if brief.get("plan_first"):
        lines += ["Write the plan first and get it approved before editing anything.", ""]
    lines += [autonomy_sentence(brief), ""]
    rel = brief_path if flavour != "generic" else "the brief"
    if flavour == "copilot":
        lines += ["A preToolUse hook may refuse an out-of-scope file write before it "
                  "lands; it does not see shell commands. After you stop, the real git "
                  f"diff is checked from outside with `check_scope.py {rel}`. A file "
                  "changed outside the list above fails it. Do not edit the brief or "
                  "Prompire's state files."]
    else:
        lines += [f"After you stop, the diff is checked from outside with `check_scope.py "
                  f"{rel}`. A file changed outside the list above fails it."]
    ctx = str(brief.get("context") or "").strip()
    if ctx:
        lines += ["", ctx]
    return "\n".join(lines).rstrip() + "\n"


def render_durable(brief, heading):
    """AGENTS.md / CLAUDE.md — only what outlives this one task.

    No goal, no scope, no autonomy, no baseline: those describe a task that will be done
    next week, and a stale task in a repo-durable file is worse than no file.
    """
    lines = [heading, ""]
    lines += _bullets("## Never touch", [str(f) for f in as_list(brief.get("forbidden"))])
    lines += _bullets("## Keep true", [str(c) for c in as_list(brief.get("constraints"))])
    ts = tests_sentence(brief)
    if ts:
        lines += ["## Tests", ts, ""]
    verify = [f"- `{norm_cmd(a.get('cmd'))}` → {a.get('expect')}"
              for a in acceptance_entries(brief)
              if effective_transition(a, baseline_map(brief).get(entry_key(a))) != "hold"]
    if verify:
        lines += ["## Verify", *verify, ""]
    lines += ["<!-- The task-specific half of the brief is deliberately absent here: it "
              "expires, and a stale task in a durable file is worse than no file. -->"]
    return "\n".join(lines).rstrip() + "\n"


def render_checklist(brief, brief_path):
    slug = pathlib.Path(brief_path).stem
    guard = f"python3 {skill_path('check_scope.py')} {brief_path}"
    lines = [f"# Checklist — {slug}", "",
             "Run from the repo root. Every box is something you can see for yourself.",
             "",
             f"- [ ] `{guard}`",
             "      → `0 violation(s)`. Checks the scope, the forbidden paths and the "
             "tests policy",
             "        against the real diff. Independent of anything the agent reported.",
             ""]
    for cmd, note in criteria_lines(brief, long=True):
        lines.append(f"- [ ] {cmd}")
        lines.append(f"      → {note}")
    manual = [str(m) for m in as_list(brief.get("manual_checks"))]
    if manual:
        lines += ["", "Manual — no command covers these:"]
        lines += [f"- [ ] {m}" for m in manual]
    policy = tests_policy_of(brief)
    if policy in ("named", "authoring"):
        lines += ["", "Read yourself — the guard cannot judge it:",
                  f"- [ ] the diff of {', '.join(str(t) for t in as_list(brief.get('tests_editable'))) or 'the test files'} "
                  "still asserts what it did before"]
    lines += ["", "If any box is unchecked, the task is not done regardless of what the "
              "agent reported."]
    return "\n".join(lines).rstrip() + "\n"


def render(brief, brief_path, target):
    if target in PROMPT_TARGETS:
        return render_prompt(brief, brief_path, target)
    if target == "agents.md":
        return render_durable(brief, "# AGENTS.md — durable rules for this repo")
    if target == "claude.md":
        return render_durable(brief, "<!-- Prompire: append to CLAUDE.md. Nothing here "
                                     "expires with the task. -->")
    if target == "checklist":
        return render_checklist(brief, brief_path)
    raise BriefError(f"unknown target `{target}` — one of: " + " | ".join(TARGETS))


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2
    targets = ["generic", "checklist"]
    if "--target" in argv:
        targets = [t.strip() for t in argv[argv.index("--target") + 1].split(",") if t.strip()]
    try:
        brief = load_brief(args[0])
        outs = [(t, render(brief, args[0], t)) for t in targets]
    except BriefError as e:
        print(str(e))
        return 2

    over = 0
    for i, (t, text) in enumerate(outs):
        if len(outs) > 1:
            print(("\n" if i else "") + f"===== {t} =====")
        print(text, end="")
        if t in PROMPT_TARGETS:
            n = len(text.split())
            if "--words" in argv:
                print(f"[{n} words]", file=sys.stderr)
            if n > WORD_BUDGET:
                over += 1
                print(f"[{t}: {n} words, budget {WORD_BUDGET} — cut the brief, not the "
                      "checks]", file=sys.stderr)
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
