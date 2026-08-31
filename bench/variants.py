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
sys.path.insert(0, str(SKILL / "prompire"))

from brief_common import as_list, glob_re, norm_path
from render_brief import (autonomy_sentence, render_durable, render_prompt,
                          tests_sentence)


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


def _cut_block(text, header):
    """Drop a rendered `header` line and the `- ` bullets under it.

    `_cut_lines` cannot do this: the bullets do not carry the header's words, so
    cutting by marker would leave a headless list. Refuses a no-op for the same
    reason `_cut` does — a header the renderer has since reworded must be loud.
    """
    lines = text.splitlines()
    try:
        i = lines.index(header)
    except ValueError:
        raise RuntimeError(f"ablation found no block to remove: {header!r}")
    j = i + 1
    while j < len(lines) and lines[j].startswith("- "):
        j += 1
    out = "\n".join(lines[:i] + lines[j:])
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


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


# Host-duplication ablations. Each removes something a coding agent's *own* system
# prompt already says, so the question is not "does this factor matter" but "does
# Prompire have to spend words on it". A cut that costs nothing here is a cut the
# renderer can take; a cut that costs anything is proof the host's version was not
# doing the work. Read the pre-registration in bench/campaigns/ before the numbers.

ASK_CLAUSE = "Ask before any risky or hard-to-undo step. "


def no_ask_clause(brief, brief_path):
    """The autonomy sentence without its first half.

    Claude Code and Codex both carry a near-verbatim equivalent in their own system
    prompts (Opus 5's harness paragraph, Sonnet 5's "Executing actions with care",
    Codex's "Destructive Actions"). What stays is the second half — "The listed paths
    are the whole boundary: widening it needs a revised brief, not a yes in chat" —
    which those prompts do not duplicate but contradict: Sonnet 5 says the confirm-first
    default "can be changed by user instructions", Codex that it "makes informed
    assumptions". Only briefs at `ask` render the clause, so `_cut` raises on any other
    autonomy rather than scoring a no-op as a result.
    """
    return _cut(current(brief, brief_path), ASK_CLAUSE)


def _literal_prefix(pattern):
    """The directory prefix a glob cannot escape upwards — everything before its first
    wildcard, trimmed back to a path boundary. `''` means "could be anywhere"."""
    p = norm_path(pattern).rstrip("/")
    cut = min((p.index(c) for c in "*?[" if c in p), default=None)
    if cut is None:
        return p
    head = p[:cut]
    return head.rsplit("/", 1)[0] if "/" in head else ""


def _could_overlap(scope_pat, forbidden_pat):
    """Could one path match both patterns? Conservative: only a provable no is a no."""
    a, b = _literal_prefix(scope_pat), _literal_prefix(forbidden_pat)
    if not a or not b or a == b or a.startswith(b + "/") or b.startswith(a + "/"):
        return True
    return bool(glob_re(scope_pat).match(b) or glob_re(forbidden_pat).match(a))


def redundant_forbidden(brief):
    """`forbidden` entries no `scope` pattern can reach — already refused by the
    allowlist, so the rendered `Never touch:` line only restates the boundary.

    This lives here and not in `brief_common.py` on purpose. It is a claim about what
    the *prompt* needs to say, not about where the boundary is, and a helper sitting
    next to `boundary_verdict` would read as one `check_scope.py` honours.
    """
    scope = [str(s) for s in as_list(brief.get("scope")) if str(s).strip()]
    return [str(f) for f in as_list(brief.get("forbidden")) if str(f).strip()
            and not any(_could_overlap(s, f) for s in scope)]


def no_redundant_forbidden(brief, brief_path):
    """`current` minus the `forbidden` entries the allowlist already covers.

    `tests_policy` stays, so on a brief that freezes its tests this removes the
    restatement and not the prohibition — the isolated factor is the redundancy itself.
    The prediction registered before the first cell was that this one loses:
    T05-forbidden-temptation names `src/cart.py` in `forbidden` precisely because it is
    the trap, and it is disjoint from `scope`, so this variant is what stops naming it.
    """
    drop = redundant_forbidden(brief)
    if not drop:
        raise RuntimeError("ablation found no redundant forbidden entry to remove")
    text = current(brief, brief_path)
    for entry in drop:
        text = _cut_lines(text, f"- {entry}")
    if len(drop) == len([f for f in as_list(brief.get("forbidden")) if str(f).strip()]):
        text = _cut_lines(text, "Never touch:")
    return text


def durable_dedupe(brief, brief_path):
    """`current` minus everything a durable AGENTS.md / CLAUDE.md already carries.

    Both hosts inject that file at a priority the pasted prompt cannot reach — Codex
    verbatim into its `USER_INSTRUCTIONS` block, Claude Code into the system prompt
    under a header that calls the contents overriding — so the copies in the prompt are
    strictly weaker duplicates of themselves. `render_durable` decides what is durable;
    this cuts exactly that set, and `bench/run.py`'s REPO_EDITS puts the file in the
    repo, because ablating the text without installing the file measures a shorter
    prompt rather than a deduplicated one.
    """
    text = current(brief, brief_path)
    if as_list(brief.get("forbidden")):
        text = _cut_block(text, "Never touch:")
    if as_list(brief.get("constraints")):
        text = _cut_block(text, "Keep true:")
    ts = tests_sentence(brief)
    if ts:
        text = _cut_lines(text, ts)
    return text


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
            "plus_acceptance": plus_acceptance, "plus_bounds": plus_bounds,
            "no_ask_clause": no_ask_clause,
            "no_redundant_forbidden": no_redundant_forbidden,
            "durable_dedupe": durable_dedupe}


def _keep_forbidden(brief, kept):
    """`forbidden: []` is not the same brief as one without the key — drop it empty."""
    out = copy.deepcopy(brief)
    if kept:
        out["forbidden"] = kept
    else:
        out.pop("forbidden", None)
    return out


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
    # `autonomy: ask` is the enum the cut clause is rendered from, so it goes with the
    # clause. The half the variant keeps survives verbatim in the prompt, so nothing
    # the agent is still meant to know leaves with the key.
    "no_ask_clause": lambda b: _drop(b, "autonomy"),
    # Only the entries the prompt stopped naming. The rest of `forbidden` stays, and
    # measurement restores the author's file anyway — the boundary judged afterwards is
    # the full one, which is exactly the claim under test: the allowlist already covers
    # these, so withholding them should cost nothing.
    "no_redundant_forbidden": lambda b: _keep_forbidden(
        b, [f for f in as_list(b.get("forbidden"))
            if str(f) not in redundant_forbidden(b)]),
    # No edit for durable_dedupe on purpose: the durable file REPO_FILES installs is
    # where those rules now live, so the agent is *supposed* to be able to find them.
}


def _durable_files(brief):
    """AGENTS.md and CLAUDE.md carrying what `durable_dedupe` cut out of the prompt.

    Both, not one: `render_durable` emits the same rules under either heading
    (references/rendering.md), and writing both means the variant does not silently
    become a test of which host reads which filename.
    """
    return {"AGENTS.md": render_durable(brief, "# AGENTS.md — durable rules for "
                                               "this repo"),
            "CLAUDE.md": render_durable(brief, "<!-- Prompire: append to CLAUDE.md. "
                                               "Nothing here expires with the task. -->")}


# Files a variant needs sitting in the repo before the agent starts, as
# {relative path: contents}. bench/run.py writes and commits them inside `prepare()`,
# ahead of `baseline.py --write`, so they land inside `base_rev` — a durable file
# committed after the base would show up in the diff as the agent's own out-of-scope
# write. Writing is run.py's job; this module stays pure text.
REPO_FILES = {"durable_dedupe": _durable_files}
