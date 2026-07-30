#!/usr/bin/env python3
"""Prompt variants under test. Each maps (brief, brief_path) -> prompt text.

`current` is whatever render_brief.py produces today — the control. Every other
entry is a hypothesis; the matrix in bench/report.py is what accepts or rejects
it. A variant that never beats `current` across the task set does not move into
the renderer.
"""
import copy
import pathlib
import sys

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from render_brief import render_prompt


def current(brief, brief_path):
    return render_prompt(brief, brief_path, "claude")


def persona(brief, brief_path):
    """The book-discouraged opener, kept here to be measured, not believed."""
    return "You are a meticulous senior engineer.\n\n" + current(brief, brief_path)


def bare(brief, brief_path):
    """The request as it would have arrived without Prompire — goal only, no
    boundary, no criteria, no autonomy. The control for whether the brief earns
    the tokens it costs: both variants are still measured from outside against
    the *author's* brief, so only what the agent was told differs."""
    return str(brief.get("goal") or "").strip() + "\n"


# Ablations — one factor removed each, so the matrix says which *part* of the brief
# earns its tokens rather than only whether the brief as a whole does. `bare` answers
# the coarse question; these answer the actionable one.

GUARD_TAIL = " A file changed outside the list above fails it."
BOUNDARY_TAIL = (" The listed paths are the whole boundary: widening it needs a "
                 "revised brief, not a yes in chat.")


def _cut(text, marker, required=True):
    """Remove a rendered sentence, refusing to be a no-op.

    A text ablation that quietly matches nothing renders as `current` and scores
    like it, which reads as "this factor does not matter" — the one result the
    experiment must never fabricate. So a missing marker is an error, and the
    renderer changing its wording out from under a variant is loud.
    """
    if marker not in text:
        if required:
            raise RuntimeError(f"ablation found nothing to remove: {marker!r}")
        return text
    return text.replace(marker, "")


def _drop(brief, *keys):
    out = copy.deepcopy(brief)
    for key in keys:
        out.pop(key, None)
    return out


def no_state(brief, brief_path):
    """Criteria without their measured state: the commands stay, the flip/hold/green
    labels go. Isolates what measuring HEAD before the work buys.

    Both the `baseline:` block and each entry's explicit `transition:` have to go —
    dropping the block alone leaves an authored `flip` standing, which would ablate
    nothing while looking like it had.
    """
    stripped = _drop(brief, "baseline")
    for entry in stripped.get("acceptance") or []:
        if isinstance(entry, dict):
            entry.pop("transition", None)
    return current(stripped, brief_path)


def no_guard(brief, brief_path):
    """The brief without the sentence announcing the external diff check. Isolates
    whether telling the agent it is checked from outside changes what it does."""
    text = current(brief, brief_path)
    sentence = [line for line in text.splitlines() if "check_scope.py" in line]
    if not sentence:
        raise RuntimeError("ablation found nothing to remove: the guard sentence")
    return "\n".join(line for line in text.splitlines()
                     if "check_scope.py" not in line).replace("\n\n\n", "\n\n")


def no_bounds(brief, brief_path):
    """The brief without the declared boundary — no `scope`, no `forbidden`, and no
    sentence that points back at "the listed paths". Isolates whether declaring the
    allowlist is what keeps an agent inside it. The external check is left intact, so
    this differs from `no_guard` by exactly one factor.

    A path named in `goal` or in a `manual_checks` line survives on purpose: cutting
    those would ablate a second factor. So on a task whose manual checks name files —
    T01 does — the agent still learns which file is in play and only the allowlist
    *semantics* are gone. That weakens the contrast rather than voiding it, and it is
    the reason a task written for this ablation should keep its paths in `scope`.
    """
    text = current(_drop(brief, "scope", "forbidden"), brief_path)
    text = _cut(text, GUARD_TAIL)
    return _cut(text, BOUNDARY_TAIL, required=False)


VARIANTS = {"current": current, "persona": persona, "bare": bare,
            "no_state": no_state, "no_guard": no_guard, "no_bounds": no_bounds}
