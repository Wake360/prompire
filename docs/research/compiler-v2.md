---
title: Compiler v2 — E1 defect closure
tags: [prompire, compiler, e1, e2, trust-boundary]
date: 2026-08-03
source: implementation session on branch compiler-v2, frozen at the commit named below
related: [compiler-v1.md, references/schema.md, references/rules.md]
---

# Compiler v2 — E1 defect closure

E1 rejected Compiler v1 on its preregistered contract-quality and trust gates, and
named five reproducible implementation defects. Compiler v2 closes exactly those
five, adds no capability, and leaves the verifier's authority intact. No E2 was run
and no outcome is claimed. This note records what changed and confirms the treatment
is ready to be tested on a different population.

Starting point: `21a83b2` (v1, 0.11.0). End state: `compiler-v2` at version 0.12.0
— `691ee16` closed the five E1 defects, and two further commits closed what five
adversarial reviewers then found. Not tagged, not published.

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

Adversarial review then showed this fix was field-specific: the same stall walked in
through `goal`, which the compiler rewrites freely and which is line 1 of every
rendered prompt, and `rollback`, which the renderer interpolates into the autonomy
sentence once a brief is raised to unattended autonomy. Both are now
confirmation-required too. The rule is the class, not the field: anything the
compiler writes into the prompt is confirmed. A request carried through verbatim —
the user's own sentence, when the compiler proposed no goal — stays unmarked,
because those are already the human's words.

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
renderer target shows a command as a fenced verbatim block introduced by "the command
below" whenever its raw text differs from the display spelling at all — a newline, a
doubled space inside quotes, a tab, U+2028 — with a fence that outruns any backticks
the command carries. The command measured, communicated, and verified are one command.

Verbatim execution opened one gap of its own, found by adversarial review rather than
by E1: the safety classifier was still reading the normalised spelling, so a
`\`-newline splice (`r\<newline>m -rf x`) matched no guard and ran as `rm -rf x`
during a baseline. `classify` now reads the raw text with continuations spliced, as
the shell splices them, and skips heredoc bodies — a heredoc body is data, and
scanning it had put `less` back in executable position, the E1 pager shape again.

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
itself defines. It reads every simple command in the line — quote-aware, past inline
env assignments and `env`/`nohup`-style wrappers, through `&&` and pipes, accepting
joined `-mpytest`/`-c"…"` spellings — and replays the command's own env assignments
into the probe, so a command that points itself at an installed copy is asked in the
environment it builds for itself. A package the repo defines with no `__init__.py`
(PEP 420, the layout most prone to shadowing) counts too. If the import resolves
outside the checkout the criterion is refused as unclassified (exit 1, needs a human)
rather than measured. A workspace copy that shadows an installed one, and imports of
dependencies the repo does not define, are untouched. Entry points whose interpreter
is not knowable from the command line — bare `pytest`/`tox`, `make test`, a shell
script, `uv run`, `coverage run` — are not probed; that gap is documented rather than
guessed at, and it is the honest limit of a check that refuses to become a dependency
resolver.

## Baseline heuristic — the `more` false positive

E1's T06 baseline refused `stubtest more_itertools.more more_itertools.recipes` as
"interactive (`more`)" because the pager list matched the substring `more` inside an
argument. The heuristic now matches command position only — the first word of each
simple command, past env-assignments and pass-through wrappers, with separators found
outside quotes and heredoc bodies skipped — so a pager name in a module path, a quoted
string or a heredoc is not interactive, while an actual pager, `--interactive`,
`--watch`, and `git rebase -i` still are. A differential fuzz of 65 commands against
0.11.0 found the change strictly permissive: no command is newly refused.

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

## Adversarial review

Five fresh-context reviewers attacked the frozen `691ee16`. Four found real
defects; every confirmed finding that is an equivalent of an E1 defect is closed,
each with its reproduction pinned by a test.

- **A, contract vacuity** — two compiler-proposable equivalents of the
  `manual_checks` escape: a `hold` over "exit 0, nothing printed" (the state of
  any trivial command) and a `flip` with no baseline entry (a claim nobody
  measured, satisfied by an untouched tree). Both closed. It also confirmed the
  V2-2 fix itself held: plain manual strings, the `done:` spelling through a
  proposal, and every key-spelling trick were blocked.
- **B, execution mode** — `plan_first` held against every attack, but showed the
  fix was field-specific: `goal` (line 1 of every prompt, rewritten freely by the
  compiler) and `rollback` (interpolated into the autonomy sentence) reached the
  agent unmarked, and a plan-approval instruction in `goal` reproduced the E1
  stall past the new gate. Both now confirmation-required; the rule is the class,
  not the field.
- **C, render fidelity** — the most severe finding, and a regression verbatim
  execution itself introduced: `classify` scanned the normalised command while
  `run_one` executed the raw one, so `r\<newline>m -rf x` matched no guard and
  ran as `rm -rf x` during a baseline. The classifier now reads the spliced raw
  text as the shell does, and skips heredoc bodies. Verbatim block rendering now
  triggers on any divergence from the display spelling (doubled space, tab,
  U+2028), not only newlines, and the fence outruns backticks in its content.
- **D, environment** — the workspace probe read only `argv[0]`, so an inline
  `PYTHONPATH=… python3 -c` (the literal T05 shape), an `env` wrapper, a `&&`
  chain, a joined `-mpytest` and PEP 420 namespace layouts all measured the
  installed copy green. Segment parsing is now quote-aware and shared with the
  interactive check, and the probe replays the command's own env assignments.
- **E, verifier regression** — `check_scope.py` and `verify_acceptance.py` are
  byte-identical to 0.11.0 and 14 armed scenarios diffed identical. It correctly
  caught the changelog overstating verbatim execution as multi-line-only; the
  claim is corrected and a migration note added (below).

## Verifier regression

A brief armed before 0.12.0 whose command carries collapsible whitespace was
measured against the collapsed spelling, so its recorded evidence — a
`before_after` digest especially — describes a different program than 0.12.0 will
run. Re-measure such a brief (`--deactivate`, `baseline.py --write`, `--activate`)
rather than trusting the old block; nothing detects this for you, because the
pointer carries no tool version. This is the one direction in which a
previously-clean armed brief can turn red.

The verify path changes in exactly three places, all through shared modules —
`check_scope.py` and `verify_acceptance.py` are themselves byte-identical to
0.11.0. `load_brief` now reports a brief carrying a YAML tag the loader cannot
construct as unreadable, so `check_scope` exits 2 where it previously crashed with
a traceback and exit 1; since 1 is this repo's code for a real finding, that is
strictly the safe direction and the only `check_scope` exit code that moved. The
other two are the shared-classifier corrections above:
`baseline.py`'s INTERACTIVE match (command-position, not substring) and `run_one`'s
verbatim execution (which changes behavior only for a multi-line command — a single
line is byte-identical after normalisation). `verify_acceptance.py` imports
`classify` and `run_one` and inherits both; it does NOT call the new
`workspace_mismatch` probe, so no previously-passing acceptance cell newly refuses on
the armed path. `check_scope.py` is unchanged. The scope guard, pin, digest, tombstone
and repin semantics did not move.

## Tests

`python3 tests/run_all.py` — 13 suites, all green (battery 64, e2e 72, examples 6,
golden 42 + budget-preview drift, docs 18 rules / 0 inconsistencies, hook, encoding,
verify 7, bench 649, cli 77, runner, package, ci). New regression coverage:

- battery: plan_first-not-bool (B8), wide-manual-run-needs-no-plan-gate (B10),
  manual-check-strings-do-not-carry-doneness, manual-done-declaration-carries-doneness,
  authoring-oracle-manual-strings-still-vacuous, manual-check-shape-must-be-string-or-done,
  unknown-requires now an error.
- cli: over-budget-proposal-surfaced-at-draft, plan_first-execution-mode decision,
  non-boolean plan_first refused.
- e2e: pager-lookalike-arguments-are-not-interactive, multi-line-and-quoted-commands-
  execute-verbatim, baseline-refuses-to-measure-an-installed-copy-as-the-workspace
  (including the inline-env, env-prefix, chained, and joined-flag spellings),
  the-safety-classifier-reads-what-the-shell-will-run,
  single-line-commands-whose-whitespace-matters-render-verbatim,
  a-command-containing-backticks-cannot-break-its-rendered-block.
- battery: hold-over-silent-success-carries-nothing (and its known-red counterpart),
  flip-without-a-baseline-entry-is-not-a-discriminator.
- cli: a-compiler-written-goal-and-rollback-are-decisions-not-furniture.
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

## Known gaps, deliberately left

- Entry points whose interpreter is not knowable from the command line (bare
  `pytest`/`tox`, `make test`, a shell script, `uv run`, `coverage run`) are not
  workspace-probed. Closing this means resolving arbitrary Python environments,
  which is explicitly not what this check is.
- A `before_after` digest over *constant* output still counts as a carrier. The
  empty-output case is refused and a `hold` over silent success is refused, but no
  digest can prove its command reads anything the work changes. Same honest limit
  as a `done:` declaration: a preservation-shaped carrier records that a human
  judgment decides, it does not mechanically discriminate.
- A brief with `base_rev` but no `baseline:` block never comes from `prepare`, but
  a hand-edited one skips B17 entirely, because the rule only judges a measured
  brief. Deleting the block is cheaper than defeating the rule.
- `manual_checks` items, `constraints`, `forbidden` and `tests_editable` carry one
  marker and one ledger entry per *list*, not per item, so one deletion confirms an
  arbitrary volume of compiler-authored instruction text.
- `draft`'s printed "N decisions to confirm" counts marker strings in the file, so
  compiler-authored content that contains the marker text inflates it, and leaves
  `prepare` refusing until a human edits that text. The `unconfirmed:` ledger is the
  authoritative record and is not forgeable this way; the count is display only, and
  both failure directions are closed.
- B10 can still be steered: a compiler-chosen refactor word in the `goal`, or a
  fourth `scope` entry, makes lint demand `plan_first: true`. Both fields are now
  confirmed decisions, but `draft` gives no compile-time warning that the goal it
  just wrote will force a plan gate — unlike the word-budget preview, which does.
- A brief armed before 0.12.0 needs re-measuring if its command carries
  collapsible whitespace (see above); nothing forces or detects that.

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
