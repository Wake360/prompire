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

from render_brief import render_prompt, autonomy_sentence, tests_sentence


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


def _cut_lines(text, marker):
    """Drop every rendered line carrying `marker`, and refuse a no-op for the same
    reason `_cut` does."""
    kept = [line for line in text.splitlines() if marker not in line]
    if len(kept) == len(text.splitlines()):
        raise RuntimeError(f"ablation found nothing to remove: {marker!r}")
    out = "\n".join(kept)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


def _drop(brief, *keys):
    out = copy.deepcopy(brief)
    for key in keys:
        out.pop(key, None)
    return out


# Every note render_brief.state_of can put in a criterion's trailing parenthetical.
# Dropping the `baseline:` block instead would substitute "(no baseline recorded)" —
# an ablation that ADDS a signal current never carries is not an ablation.
STATE_NOTES = ("fails today; must pass when done",
               "cannot run yet; must pass when done",
               "green today; keep it green",
               "must stay exactly as measured — do not 'fix' it",
               "no baseline recorded",
               "must pass")


def no_state(brief, brief_path):
    """Criteria without their measured state: the commands stay, the flip/hold/green
    labels go. Isolates what measuring HEAD before the work buys."""
    text = current(brief, brief_path)
    hits = 0
    for note in STATE_NOTES:
        marker = f" ({note})"
        hits += text.count(marker)
        text = text.replace(marker, "")
    if not hits:
        raise RuntimeError("ablation found no state note to remove")
    return text


def no_guard(brief, brief_path):
    """The brief without the sentence announcing the external diff check. Isolates
    whether telling the agent it is checked from outside changes what it does."""
    return _cut_lines(current(brief, brief_path), "check_scope.py")


def no_acceptance(brief, brief_path):
    """The brief without executable criteria: goal, boundary and autonomy stay, the
    commands and their header go. Isolates what stating how success is judged buys.

    The first live matrix is why this exists. Half of what a naked request lost was
    the boundary — it edited frozen tests — but the other half was the contract: it
    never learned that `total_line()` must render `'total: 4'`, or that the extracted
    function is called `fmt_row`. Those failures belong to the criteria, and no other
    ablation removes them.
    """
    return _cut_lines(current(_drop(brief, "acceptance"), brief_path),
                      "Done when all of these hold:")


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


# Additive variants — the sufficiency counterparts to the ablations above. Each is
# `bare` plus exactly one section, built by subtraction from `current` rather than
# hand-written prose, so a surviving section is byte-identical to `current`'s and any
# result reads as "this factor, alone" rather than "this particular short prompt".

def _bare_plus(stripped, brief_path):
    """Render what survives, then cut the sentences the renderer emits regardless of
    which keys are present. Autonomy cannot be dropped by key: a missing `autonomy`
    substitutes "Autonomy was not declared; do not write anything until it is." — an
    ablation that swaps one instruction for another has removed nothing. Most keys are
    safe to drop plainly; `tests_policy` is not always one of them — `legacy_pinned`
    (brief_common.py) infers "immutable" from a `forbidden` entry that looks like a test
    path, so `plus_bounds`, which keeps `forbidden`, still renders the prohibition after
    the key is gone. Cut it as text too, the same way autonomy is, when it survives."""
    text = current(stripped, brief_path)
    text = _cut_lines(text, "check_scope.py")
    text = _cut_lines(text, autonomy_sentence(stripped))
    ts = tests_sentence(stripped)
    if ts:
        text = _cut_lines(text, ts)
    return text


def plus_acceptance(brief, brief_path):
    """goal + the criteria block, nothing else. The sufficiency counterpart to
    no_acceptance: does stating how success is judged, alone, lift bare off the floor?"""
    return _bare_plus(_drop(brief, "scope", "forbidden", "constraints", "manual_checks",
                            "tests_policy"), brief_path)


def plus_bounds(brief, brief_path):
    """goal + the declared allowlist, nothing else. `tests_policy` goes too: it renders
    its own prohibition and is a separate field, so keeping it would make this variant
    goal + two boundary factors. The renderer emits "Done when all of these hold:" even
    with no `acceptance` to number underneath it — the same header no_acceptance already
    has to cut for the same reason — so it goes too, as text, not by key."""
    text = _bare_plus(_drop(brief, "acceptance", "constraints", "manual_checks",
                            "tests_policy"), brief_path)
    return _cut_lines(text, "Done when all of these hold:")


VARIANTS = {"current": current, "persona": persona, "bare": bare,
            "no_state": no_state, "no_guard": no_guard, "no_bounds": no_bounds,
            "no_acceptance": no_acceptance,
            "plus_acceptance": plus_acceptance, "plus_bounds": plus_bounds}


def _strip_state(brief):
    out = _drop(brief, "baseline")
    for entry in out.get("acceptance") or []:
        if isinstance(entry, dict):
            entry.pop("transition", None)
    return out


# What each variant puts on disk at .prompire/brief.yaml. The rendered prompt discloses
# that path, so a variant whose prompt drops a factor while the file keeps it has not
# ablated anything — the agent can just read it. A variant absent here hands over the
# author's brief unchanged. bench/run.py restores the author's brief before measuring.
BRIEF_EDITS = {
    "bare": lambda b: {"goal": b.get("goal")},
    "no_bounds": lambda b: _drop(b, "scope", "forbidden"),
    # `baseline` goes with `acceptance`: every baseline entry quotes the command it
    # measured, so a brief that drops the criteria and keeps the baseline still spells
    # them out on disk. The rendered no_acceptance prompt carries neither.
    "no_acceptance": lambda b: _drop(b, "acceptance", "baseline"),
    "no_state": _strip_state,
    # `autonomy` is dropped on disk because the prompt cut removes its sentence;
    # leaving the key would let an agent recover from the file what the variant
    # removed from the text.
    "plus_acceptance": lambda b: _drop(b, "scope", "forbidden", "constraints",
                                       "manual_checks", "tests_policy", "autonomy"),
    # `baseline` goes with `acceptance` here too, for the same reason it does in
    # no_acceptance above: every baseline entry quotes the command it measured, so
    # keeping it on disk after dropping `acceptance` would still spell out the
    # criteria's contract strings for a variant whose prompt withholds them.
    "plus_bounds": lambda b: _drop(b, "acceptance", "baseline", "constraints",
                                   "manual_checks", "tests_policy", "autonomy"),
}
