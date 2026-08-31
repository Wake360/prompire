#!/usr/bin/env python3
"""Snapshot every renderer target against every canonical example.

Run: python3 tests/golden.py [--regenerate]
Exit 0 = every rendered target is byte-identical to its snapshot and obeys the
wording rules that are easy to lose in an edit.

Snapshots live in tests/golden/<example>.<target>.txt. Regenerate deliberately, then
read the diff: a renderer change that quietly authorises a write outside scope, or
drops the flip/hold distinction, looks exactly like a formatting tweak in a diff stat.
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
GOLDEN = HERE / "golden"
EXAMPLES = SKILL / "examples"
TARGETS = ("claude", "generic", "codex", "copilot", "agents.md", "claude.md", "checklist")
WORD_BUDGET = 250
PROMPTS = ("claude", "generic", "codex", "copilot")

# Phrases that must never reach a rendered prompt: each one tells an agent that the
# boundary is negotiable in conversation.
BANNED = (
    "ask before each step that writes outside scope",
    "ask before writing outside",
    "confirm before writing outside",
    "unless you ask",
    "if you need to touch other files",
    "you may edit other files",
    "feel free",
    "as needed",
    "use your judgement",
    "you are an expert",
    "you are a senior",
)


def render(example, target):
    # relative path, run from the skill dir: a snapshot must not pin one machine's home
    r = subprocess.run([sys.executable, "prompire/render_brief.py",
                        f"examples/{pathlib.Path(example).name}", "--target", target],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(SKILL))
    if r.returncode == 2:
        raise AssertionError(f"render failed: {r.stdout}{r.stderr}")
    # the checklist names the guard by its install path, and the skill has two homes
    # (canonical and the git-tracked mirror). Pin that the guard is invoked, not where
    # this copy happens to live.
    return re.sub(r"\S*check_scope\.py", "<SKILL>/check_scope.py", r.stdout)


def wording_checks(name, target, text):
    problems = []
    low = text.lower()
    for phrase in BANNED:
        if phrase in low:
            problems.append(f"contains banned wording: {phrase!r}")
    if target in PROMPTS:
        n = len(text.split())
        if n > WORD_BUDGET:
            problems.append(f"{n} words, budget {WORD_BUDGET}")
        if "check_scope.py" not in text:
            problems.append("no mention of the external scope check")
        if "revised brief" not in text:
            problems.append("does not say a wider scope needs a revised brief")
        # The pin turns any edit of the brief into *no verdict*, and the hook refuses
        # writes to the state files on every host. That is true of all four prompt
        # targets, so all four have to say it.
        if "Prompire's state files" not in text:
            problems.append("does not tell the agent to leave the brief and the state "
                            "files alone")
    if target in PROMPTS and name in ("02-must-flip", "worked-example"):
        if "human review" not in low:
            problems.append("manual_checks must reach every prompt target")
    if target in PROMPTS and name == "worked-example":
        if "<context>" not in text or "</context>" not in text:
            problems.append("context must be delimited as data, not instructions")
    if name == "05-multiline-acceptance":
        # E1: the renderer flattened multi-line commands into invalid one-liners.
        # Every target that shows the command must show it verbatim — newlines and
        # the doubled space inside the quotes intact.
        if 'STATUS="cart  ok"\ntest "$STATUS" = "cart  ok"' not in text:
            problems.append("multi-line command flattened or reflowed — the rendered "
                            "command must be the brief's command verbatim")
    if target in ("agents.md", "claude.md"):
        for leaked in ("## Task", "autonomy", "baseline:", "Files you may edit"):
            if leaked.lower() in low:
                problems.append(f"durable file leaked task-only content: {leaked!r}")
    if target == "checklist":
        if "check_scope.py" not in text:
            problems.append("checklist must start from the independent scope check")
        if "[ ]" not in text:
            problems.append("checklist has no boxes")
    return problems


def preview_drift_checks():
    """The compile-time budget preview must reuse the renderer, not approximate it.

    For every example: strip the measured block, run the preview, and compare with
    the actual rendered word count. A flip criterion is previewed at its longest
    state label ("cannot run yet…", 7 words) while a measured flip may read "fails
    today…" (6), so the preview may exceed the real count by at most one word per
    flip — and must never undercount, because undercounting is exactly the E1
    failure: a contract confirmed at length that could not be rendered."""
    sys.path.insert(0, str(SKILL / "prompire"))
    import yaml
    from brief_common import acceptance_entries, effective_transition
    from render_brief import PROMPT_TARGETS, preview_counts, render
    problems = []
    for ex in sorted(EXAMPLES.glob("*.yaml")):
        brief = yaml.safe_load(ex.read_text(encoding="utf-8"))
        unmeasured = {k: v for k, v in brief.items()
                      if k not in ("baseline", "base_rev", "dirty_baseline")}
        flips = sum(1 for a in acceptance_entries(brief)
                    if effective_transition(a) == "flip")
        counts = preview_counts(unmeasured, str(ex))
        for target in PROMPT_TARGETS:
            actual = len(render(brief, str(ex), target).split())
            drift = counts[target] - actual
            if not 0 <= drift <= flips:
                problems.append(f"{ex.stem}.{target}: preview {counts[target]} vs "
                                f"rendered {actual} (allowed 0..+{flips})")
    return problems


def main():
    regen = "--regenerate" in sys.argv
    GOLDEN.mkdir(exist_ok=True)
    examples = sorted(EXAMPLES.glob("*.yaml"))
    if not examples:
        print("no examples — run tests/examples.py --regenerate first")
        return 1
    fails = 0
    for ex in examples:
        for target in TARGETS:
            name = f"{ex.stem}.{target.replace('.', '_')}.txt"
            snap = GOLDEN / name
            text = render(ex, target)
            problems = wording_checks(ex.stem, target, text)
            if regen:
                snap.write_text(text, encoding="utf-8")
            elif not snap.exists():
                problems.append("no snapshot — run with --regenerate")
            elif snap.read_text(encoding="utf-8") != text:
                problems.append("differs from the snapshot")
            fails += 1 if problems else 0
            if problems:
                print(f"FAIL  {name}")
                for p in problems:
                    print(f"        {p}")
    total = len(examples) * len(TARGETS)
    if regen:
        print(f"wrote {total} snapshots to {GOLDEN.relative_to(SKILL)}")
        return 0
    drift = preview_drift_checks()
    for p in drift:
        print(f"FAIL  budget-preview  {p}")
    fails += len(drift)
    print(f"{total - fails}/{total} renderer snapshots match"
          + ("" if drift else " and the budget preview tracks the renderer"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
