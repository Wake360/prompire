---
title: Compiler v2 — E1 defect closure
tags: [prompire, compiler, e1, e2, trust-boundary]
date: 2026-08-03
source: implementation session on branch compiler-v2, commit 691ee16
related: [docs/compiler-v1.md, references/schema.md, references/rules.md]
---

# Compiler v2 — E1 defect closure

E1 rejected Compiler v1 on its preregistered contract-quality and trust gates, and
named five reproducible implementation defects. Compiler v2 closes exactly those
five, adds no capability, and leaves the verifier's authority intact. No E2 was run
and no outcome is claimed. This note records what changed and confirms the treatment
is ready to be tested on a different population.

Starting point: `21a83b2` (v1, 0.11.0). End state: `691ee16` on `compiler-v2`,
version 0.12.0. Not tagged, not published.

## The five defects and their fixes

**V2-1 — plan_first delivery / trust.** In E1 all eight compile agents copied
`plan_first: true` from the skill example, the field carried no confirmation marker,
and the renderer turned it into "Get the plan approved before editing anything." — a
hard stop that made every one-shot headless session stall. `plan_first` is now in the
confirmation-required class: a proposal's `plan_first` returns marked
`# prompire:unconfirmed` and listed in the `unconfirmed:` ledger, so `prepare`, `lint`
(B18) and `--activate` all refuse until a human clears it. It must be a real boolean —
a truthy string like `"false"` is refused at the proposal parse, and B8 errors on it
in a hand-written brief — and the renderer emits the approval stop only for a literal
`true`. B10 (a wide task needs a plan gate) no longer fires at `autonomy: manual`,
which never writes and so already decouples planning from execution. The execution-mode
state machine is documented in `references/schema.md`: `autonomy` is who acts,
`plan_first` is one extra mid-run stop that requires an operator present.

**V2-2 — B17 manual_checks vacuity.** E1's T05 and T08 armed with every criterion
green on untouched HEAD because any non-empty `manual_checks` suppressed B17. A manual
check now carries done-ness only in the human-written `done:` spelling
(`- done: <text>`); a plain string is a review note that carries nothing. `prompire
draft` rejects a proposal whose manual entries are not plain strings, so the
declaration cannot be proposed by a model and rubber-stamped in — it is written by the
human editing the confirmed brief. A malformed `manual_checks` mapping (anything other
than exactly `done: <non-empty text>`) is a lint error rather than a silent guess.
Preserve-behavior tasks stay expressible: `hold`, a `before_after` over a command that
prints something, and flip criteria are unchanged.

**V2-3 — renderer command fidelity.** E1's renderer flattened multi-line acceptance
commands into invalid one-liners, so 3 of 7 delivered prompts carried a criterion that
could never execute, and the measured baseline ran a different command than the brief
declared. `baseline.run_one` now executes the brief's verbatim `cmd` text (the
`(cmd, cwd)` key stays whitespace-normalised, so baselines still match), and every
renderer target shows a multi-line command as a fenced verbatim block introduced by
"the command below". The command measured, communicated, and verified are one command.

**V2-4 — early budget gate.** E1's eight briefs all blew the 250-word render budget,
discovered only at handoff; T06 spent its whole confirmation budget without ever
producing a prompt. `prompire draft` now previews every prompt target through
`render_brief.preview_counts()` — the renderer itself over a provisional baseline
synthesized from each criterion's declared transition, so there is no second budget
arithmetic to drift (a golden test asserts the preview tracks the real render within
the one-word-per-flip slack and never undercounts). Over-budget is reported with
per-section word attribution before any confirmation effort is spent. The 250-word
budget is unchanged, `prepare` still refuses over-budget, and the preview measures and
executes nothing.

**V2-5 — workspace vs installed package.** E1's T05 baseline was measured against the
system site-packages copy of click, which already contained the upstream fix, so a
false green signed off code nobody was modifying. `baseline.py` now probes, before
measuring, where an import resolves when a command exercises a package this checkout
itself defines (an explicit `python`/`py` importing it via `-c`/`-m`, or `-m pytest` /
`-m unittest` in a repo that defines packages). If it resolves outside the checkout the
criterion is refused as unclassified (exit 1, needs a human) rather than measured. A
workspace copy that shadows an installed one, and imports of dependencies the repo does
not define, are untouched. A bare `pytest`/`tox` entry point is not probed — its
interpreter is not knowable from the command line — and that gap is documented rather
than guessed at.

## Baseline heuristic — the `more` false positive

E1's T06 baseline refused `stubtest more_itertools.more more_itertools.recipes` as
"interactive (`more`)" because the pager list matched the substring `more` inside an
argument. The heuristic now matches command position only — the first word of each
segment after a pipe / `;` / `&&`, past env-assignments and pass-through wrappers — so
a pager name in a module path or a quoted string is not interactive, while an actual
pager, `--interactive`, `--watch`, and `git rebase -i` still are.

## GOLD verifier mismatch investigation

E1 recorded Prompire `verify` red on 4 of 16 GOLD cells the held-out grader scored
SOLVED. Classified against current semantics, all four are explained and none is a
verifier trust defect:

| cell(s) | cause | classification |
|---|---|---|
| T06 gold rep1, rep2 | the `more` INTERACTIVE false positive refused two `-c` probes importing `more_itertools` | ENVIRONMENT/HARNESS — a baseline-classifier false positive, fixed (the shared classifier is on the verify path too); confirmed the real E1 commands now classify runnable |
| T07 gold rep1, rep2 | the gold brief put a file path (`tests/test_orderedset.py`) in `requires`, which disabled its only executable criterion; plus the expected authoring-policy REVIEW flag | EXPECTED REVIEW/POLICY DIFFERENCE (the REVIEW is correct authoring behavior) + a brief-authoring error now caught at lint (B5 unknown-requires is an error) |

The verify red on T06/T07 was not Prompire rejecting good work: it was a classifier
false positive (T06) and a malformed gold brief that silenced its own check (T07). The
two mechanical corrections were made in the shared classifier and at lint respectively,
each with the regression direction pinned by a test. No change was made to
`check_scope.py` verdict semantics, the pin, or the digest.

## Verifier regression

The only verifier-path edits are the two shared-classifier corrections above:
`baseline.py`'s INTERACTIVE match (command-position, not substring) and `run_one`'s
verbatim execution (which changes behavior only for a multi-line command — a single
line is byte-identical after normalisation). `verify_acceptance.py` imports
`classify` and `run_one` and inherits both; it does NOT call the new
`workspace_mismatch` probe, so no previously-passing acceptance cell newly refuses on
the armed path. `check_scope.py` is unchanged. The scope guard, pin, digest, tombstone
and repin semantics did not move.

## Tests

`python3 tests/run_all.py` — 13 suites, all green (battery 61, e2e 69, examples 6,
golden 42 + budget-preview drift, docs 18 rules / 0 inconsistencies, hook, encoding,
verify 7, bench 649, cli 76, runner, package, ci). New regression coverage:

- battery: plan_first-not-bool (B8), wide-manual-run-needs-no-plan-gate (B10),
  manual-check-strings-do-not-carry-doneness, manual-done-declaration-carries-doneness,
  authoring-oracle-manual-strings-still-vacuous, manual-check-shape-must-be-string-or-done,
  unknown-requires now an error.
- cli: over-budget-proposal-surfaced-at-draft, plan_first-execution-mode decision,
  non-boolean plan_first refused.
- e2e: pager-lookalike-arguments-are-not-interactive, multi-line-and-quoted-commands-
  execute-verbatim, baseline-refuses-to-measure-an-installed-copy-as-the-workspace.
- golden: 05-multiline-acceptance example locks verbatim rendering across all targets;
  preview_counts vs real render pinned.

Additionally, the frozen E1 artifacts were replayed against the v2 tools: the compiled
T05/T08 briefs now lint B17-red (vacuous acceptance no longer suppressed), the compiled
T03 multi-line command renders as a verbatim block, the T08 proposal round-trips through
`draft` with `plan_first` marked and the over-budget preview surfaced, and the real T06
gold commands classify runnable.

## What may be claimed

> Compiler v2 fixes the specific contract-quality, delivery and environment defects
> found by E1 and is ready for a new experiment.

Nothing stronger. Still forbidden until E2 runs: that compiled contracts improve or
worsen agent outcomes, that humans specify less with the compiler, that E1 was
overturned. E1's verdict — keep Prompire verifier-first — stands; this note does not
reposition the product.

## E2 readiness

Compiler v2 is a frozen treatment at `691ee16`. Any later change to it creates a new
experimental population and is a different experiment.

E2 must not repeat E1's main population flaw, where the ≤15-word requests encoded the
identifying diagnosis of the hidden fix for 5 of 6 fix-parent tasks. The intended E2
population is genuinely underspecified short requests whose relevant task semantics are
discoverable from the repository but not already embedded in the request — e.g. "Fix
custom prompt validation when input is hidden" rather than "Preserve the exact Click
BadParameter formatting path when hide_input is true". The compiler's value, if any, is
on that population; E1 could not measure it.

E2 also needs a `plan_first`-aware execution protocol: the frozen freezing rule put a
`plan_first: false` primary arm out of scope for E1, and v2's confirmation model now
makes an unattended run's plan gate a reviewed decision rather than a silent default —
which is exactly the variable E2 exists to test.

## Single next action

Run E2 on genuinely underspecified requests.
