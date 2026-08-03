---
title: Compiler v2 — work done and results
tags: [prompire, compiler, e1, e2, report]
date: 2026-08-03
source: implementation session on branch compiler-v2, 21a83b2..08ca412
related: [docs/compiler-v2.md, docs/compiler-v1.md, references/schema.md]
---

# Compiler v2 — work done and results

A bounded implementation task: fix the implementation defects E1 exposed, preserve the
verifier's authority, and leave a frozen treatment suitable for a new experiment. No
feature was added, the product was not repositioned, and E2 was not run. E1's verdict —
keep Prompire verifier-first — stands unchanged.

`docs/compiler-v2.md` is the reference note on the resulting semantics. This file is the
record of the work: what was reproduced, what was changed, what the adversarial review
broke, and what the evidence actually supports.

## Result

**Compiler v2 is ready for E2.** All five E1 defects are reproduced and closed, each
with a regression test that fails on the old behaviour. Five fresh-context adversarial
reviewers then attacked the frozen revision; four found real defects, including one
regression that the v2 work had itself introduced. Every confirmed finding that amounts
to an equivalent of an E1 defect is closed. The full suite passes.

Frozen revision: **`08ca412064e9f2a6132f96ccaff7dc850a3328c1`**, version **0.12.0**, on
branch `compiler-v2`. Not tagged, not published. Starting point was `21a83b2` (0.11.0).

## What E1 said, and what this task was allowed to do

E1 rejected the compiler thesis on the preregistered contract-quality and trust gates:
3 of 8 compiled contracts passed a gate requiring 7 of 8, substantively 2 of 8, plus
demonstrated trust failures. The headline `COMPILED 0/8` execution result was *not* the
grounds for rejection and is not treated as one here — it was confounded by delivered
contract behaviour, since every compiled brief carried `plan_first: true` and every
headless session stopped to ask for plan approval. A labelled exploratory arm with the
same prompts plus a scripted "Proceed." solved 12 of 14 cells, which is exploratory
evidence only and is not promoted here.

So the work was scoped to the demonstrated defects. No semantic repo summaries, no
embeddings, no new schema fields, no LLM judge in the verifier, no broader redesign.

## The five defects

### V2-1 — `plan_first` was an unreviewed field that decided execution mode

All eight E1 compile agents copied `plan_first: true` from the skill example. The field
carried no confirmation marker by the product's own schema, and the renderer turned it
into *"Get the plan approved before editing anything."* One unconfirmed compiler-authored
line therefore determined the execution mode of every task.

`plan_first` is now confirmation-required: a proposal's value comes back marked and
listed in the `unconfirmed:` ledger, so `prepare`, `lint` (B18) and `--activate` all
refuse until a human clears it. It must be a real boolean — a truthy string such as
`"false"` is refused at the proposal parse and errors under B8 in a hand-written brief —
and the renderer emits the approval stop only for a literal `true`. B10 no longer demands
a plan gate at `autonomy: manual`, which never writes and so already separates planning
from execution.

The execution-mode state machine is written down in `references/schema.md`: `autonomy`
is who acts, `plan_first` is one extra mid-run stop that requires an operator present.
The two are no longer conflated.

### V2-2 — a manual check's mere existence defeated B17

B17 exists to refuse a measured contract that cannot tell untouched HEAD from done. In
E1 a non-empty `manual_checks` suppressed it, so T05 and T08 produced contracts reading
pass / pass / pass across HEAD, the gold write-set and a wrong write-set, yet linted
shippable and armed.

A manual check now carries done-ness only in the spelling `- done: <text>`, and that
spelling is refused inside compiler proposals — it is written by the human editing the
confirmed brief, not proposed by a model and waved through. Plain strings remain review
notes and carry nothing. A malformed mapping is a lint error rather than a guess about
authority.

The constraint that this must not become "all green acceptance = error" is respected:
`hold`, `before_after` over a command that prints something, and flip criteria are
unchanged, and battery cases assert that legitimate preserve-behaviour tasks still lint
clean.

### V2-3 — the renderer delivered a different command than the brief declared

Three of seven delivered E1 prompts carried acceptance criteria that could never execute,
because multi-line commands were flattened into one invalid line. The contract-quality
gate scored the YAML, so delivered quality was worse than recorded.

Execution and rendering are now verbatim. `run_one` executes the brief's exact `cmd`
text; `(cmd, cwd)` keying stays whitespace-normalised so baselines still match their
criteria. Every renderer target shows a command as a fenced block whenever its raw text
differs from the display spelling at all — a newline, a doubled space inside quotes, a
tab, U+2028 — with a fence sized to outrun any backtick run the command contains.

### V2-4 — the prompt budget was discovered after the money was spent

All eight E1 briefs exceeded the 250-word renderer budget, and nothing said so until
handoff. T06 exhausted its entire confirmation budget and never produced an executable
prompt at all.

`prompire draft` now previews every prompt target before confirmation begins, and reports
an overrun with per-section word attribution. The preview calls the real renderer over a
provisional baseline synthesised from each criterion's declared transition, so there is
no second budget calculation that can drift from the first; a golden test asserts the
preview tracks the real render and can never undercount. The 250-word budget is
unchanged, `prepare` still refuses, and the preview measures nothing, executes nothing,
and truncates nothing.

### V2-5 — a baseline measured an installed package instead of the workspace

E1's T05 baseline ran against the system site-packages copy of click, which already
contained the upstream fix. The contract was signed off against code nobody was
modifying.

Before measuring, `baseline.py` now asks where an import resolves when a command
exercises a package this checkout itself defines. It reads every simple command in the
line — quote-aware, past inline environment assignments and `env`/`nohup`-style wrappers,
through `&&` and pipes, accepting joined `-mpytest` and `-c"…"` spellings — and replays
the command's own environment assignments into the probe, so a command that points itself
at an installed copy is asked in the environment it builds for itself. Packages defined
without `__init__.py` (PEP 420) count, since that layout is the most prone to shadowing.
If the import resolves outside the checkout the criterion is refused as unclassified and
needs a human, rather than being measured.

Legitimate cases are untouched: a workspace copy that shadows an installed one measures
honestly, and an import of a dependency the repository does not define runs normally.
Entry points whose interpreter cannot be known from the command line — bare `pytest` or
`tox`, `make test`, a shell script, `uv run`, `coverage run` — are not probed. That is
the honest limit of a check that refuses to become a dependency resolver, and it is
documented rather than papered over.

## The `more` heuristic

E1's T06 baseline refused `stubtest more_itertools.more more_itertools.recipes` as
"interactive (`more`)" because the pager list matched a substring inside an argument. A
pager is interactive where a shell would execute it, not where it appears in a module
path. The check now matches command position only — the first word of each simple
command, past environment assignments and pass-through wrappers, with separators found
outside quotes and heredoc bodies skipped. `--interactive`, `--watch` and `git rebase -i`
still match anywhere. A differential fuzz of 65 commands against 0.11.0 confirmed the
change is strictly permissive: nothing is newly refused.

## GOLD verifier mismatch — the separate investigation

E1 recorded Prompire `verify` red on 4 of 16 GOLD cells the held-out grader scored
SOLVED. These were not folded into the compiler work. Classified against current
semantics:

| cells | cause | classification |
|---|---|---|
| T06 gold rep1, rep2 | the `more` false positive refused two `-c` probes importing `more_itertools` | ENVIRONMENT / HARNESS — a classifier false positive, on the verify path because the classifier is shared |
| T07 gold rep1, rep2 | the gold brief put a file path in `requires`, which disabled its only executable criterion, plus the expected authoring-policy REVIEW flag | EXPECTED REVIEW / POLICY DIFFERENCE for the flag, and a brief-authoring error for the rest |

Neither is Prompire rejecting good work, and neither is a verifier trust defect. Both
corrections were bounded: the classifier fix above, and `B5 unknown-requires` promoted
from warning to error, since any `requires` entry makes both `baseline.py` and `verify`
refuse to run the command — so an out-of-vocabulary value silently converts a criterion
into one that never executes. `check_scope.py` verdict semantics, the pin and the digest
were not touched.

## Tested against the E1 artefacts

The frozen E1 evidence in `~/prompire-e1` was read, never modified, and used only to
reproduce defects — no task names, repo names, hidden acceptance or gold patches were
hard-coded anywhere.

- The compiled **T05** and **T08** briefs, which armed under v1, now lint B17-red with
  the message naming the manual checks as notes rather than a completion condition.
- The compiled **T06** brief additionally fails the new manual-check shape rule.
- The compiled **T03** multi-line command renders as a verbatim fenced block instead of
  being flattened.
- The **T08** proposal, replayed through `draft --proposal`, returns `plan_first` marked
  and ledgered, and the render preview reports the over-budget targets (259 and 251 words
  against the 250 budget) with per-section attribution — before any confirmation.
- The real **T06 gold** commands, including `stubtest more_itertools.more …`, now
  classify as runnable.

## Adversarial review

Five fresh-context reviewers attacked the frozen revision with no stake in the outcome.
Four found real defects. This is the part of the work that changed the most.

**Reviewer A — contract vacuity.** Confirmed the V2-2 fix held (plain manual strings, the
`done:` spelling through a proposal, and every key-spelling trick were blocked), then
found two *other* carriers that carry nothing and that a compiler can propose: a `hold`
over "exit 0, nothing printed", which is the state of any command that does nothing, and
a `flip` with no baseline entry, which is a claim nobody measured and which an untouched
tree satisfies. Both are closed — a `hold` over a known *failure* still counts, and an
unmeasured flip is now a B15 error.

**Reviewer B — execution mode.** `plan_first` held against every spelling attempted.
But the fix was field-specific rather than class-specific: `goal` reached the delivered
prompt unmarked, and a plan-approval sentence placed there reproduced the E1 stall end to
end, past the new gate. `rollback` was likewise unmarked and is interpolated into the
autonomy sentence once a brief is raised to unattended autonomy — which B8 steers the
operator toward. Both are now confirmation-required, and the schema states the rule as a
class: anything the compiler writes into the prompt is confirmed. A request carried
through verbatim stays unmarked, because those are already the human's words. An
independent second run of this reviewer also found an unhandled `!!bool "1"` crash
(below).

**Reviewer C — render fidelity.** The most severe finding, and a regression the v2 work
had itself introduced: `classify` was still scanning the whitespace-normalised command
while `run_one` executed the raw one. A two-character edit exploited the gap —
`r\`+newline+`m -rf x` normalises to `r\ m -rf x`, matches no guard, and splices in the
shell to `rm -rf x`, which then ran during a baseline. The same divergence hid `git add`
from the repo-writing guard. The classifier now reads the raw text with continuations
spliced, exactly as the shell splices them, and skips heredoc bodies — scanning those had
put `less` back into executable position, the E1 pager shape again. This reviewer also
showed the fidelity invariant broke for any whitespace difference, not just newlines, and
that a triple-backtick line inside a command closed its own rendered fence.

**Reviewer D — environment.** The workspace probe read only `argv[0]`, so five ordinary
command shapes drove straight through it and measured the installed copy green: an inline
`PYTHONPATH=… python3 -c` (the literal T05 shape), an `env` wrapper, a `&&` chain, a
joined `-mpytest`, and PEP 420 namespace layouts. All closed by the segment-aware parsing
described above. The reviewer also confirmed no over-refusal on the three legitimate
cases.

**Reviewer E — verifier regression.** Found no unexplained drift: `check_scope.py` and
`verify_acceptance.py` are byte-identical to 0.11.0 and 14 armed scenarios diffed
identical. It correctly caught the changelog overstating verbatim execution as
"multi-line only" — it changes single-line verdicts too, in both directions, for briefs
armed before 0.12.0. That claim was corrected rather than defended, and a migration note
added.

One further defect came out of the review round: a YAML tag whose *constructor* fails —
`!!bool "1"` raises a bare `KeyError`, not a `YAMLError` — was caught by nothing, so
`lint`, `baseline`, `render` and `check_scope` each died with a traceback and exit **1**.
In this repository 1 is the code for "found a finding", so a tool that crashed was
indistinguishable from one that reached a verdict. All four now report exit 2, and
`draft --proposal` refuses the tag instead of crashing with an empty `--json` stdout that
its caller has to parse.

## Verifier regression

`check_scope.py` and `verify_acceptance.py` are byte-identical to 0.11.0, and 14 armed
scenarios produced identical JSON under both revisions. They are not, however,
behaviourally frozen, and the report states this exactly rather than resting on the file
hashes: both reach changed code through shared modules, in three places.

1. `load_brief` now reports a brief carrying an unconstructable YAML tag as unreadable,
   so `check_scope` exits 2 where it previously crashed and exited 1. Strictly the safe
   direction, and the only `check_scope` exit code that moved.
2. The interactive-command match is strictly more permissive (the 65-command fuzz found
   nothing newly refused).
3. Verbatim execution, which `verify_acceptance` inherits by importing `run_one`.

The third carries the one migration in this release. A brief armed before 0.12.0 whose
command contains collapsible whitespace was measured against the collapsed spelling, so
its recorded evidence — a `before_after` digest especially — describes a different
program than 0.12.0 will run. Such a brief must be re-measured: `--deactivate`,
`baseline.py --write`, `--activate`. Nothing detects this automatically, because the
pointer carries no tool version. That is a known gap, stated rather than hidden.

The new workspace probe is *not* on the verify path — it is called only from
`baseline.py`'s own entry point — so no previously-passing acceptance cell newly refuses.
The scope guard, the pin, the digest and every `check_scope.py` verdict are unmoved.

## Tests

`python3 tests/run_all.py` — 13 suites, all pass, exit 0.

| suite | result |
|---|---|
| battery | 64/64 |
| e2e | 73/73 |
| examples | 6/6 |
| golden | 42/42 snapshots, plus the budget-preview drift check |
| docs | 18 enforced rules, 0 inconsistencies |
| hook | 217/217 |
| encoding | 0 failures |
| verify | 7/7 |
| bench | 649/649 |
| cli | 78/78 |
| runner, package, ci | pass, pass, 27/27 |

`prompire demo` exits 0. The offline compile harness runs clean: `bench/compile.py
--backend gold` scores 3/3 discriminating with the fail/pass/fail triple intact, and
`--backend deterministic` exits 0. No paid E2 cells were run.

Every fix followed the same order: reproduce with a failing test, watch it fail for the
right reason, make the smallest change, watch it pass. The new coverage:

- **battery** — `plan-first-string-is-an-error`, `wide-manual-run-needs-no-plan-gate`,
  `manual-check-strings-do-not-carry-doneness`, `manual-done-declaration-carries-doneness`,
  `authoring-oracle-manual-strings-still-vacuous`,
  `manual-check-shape-must-be-string-or-done`, `hold-over-silent-success-carries-nothing`
  and its known-red counterpart, `flip-without-a-baseline-entry-is-not-a-discriminator`,
  and `unknown-requires` promoted to an error.
- **e2e** — `pager-lookalike-arguments-are-not-interactive`,
  `multi-line-and-quoted-commands-execute-verbatim`,
  `single-line-commands-whose-whitespace-matters-render-verbatim`,
  `a-command-containing-backticks-cannot-break-its-rendered-block`,
  `the-safety-classifier-reads-what-the-shell-will-run`,
  `a-yaml-tag-the-loader-cannot-construct-is-unreadable-not-a-verdict`, and
  `baseline-refuses-to-measure-an-installed-copy-as-the-workspace` covering five command
  shapes against a deliberately ambiguous environment with a competing installed copy.
- **cli** — the over-budget preview before confirmation, `plan_first` as an execution-mode
  decision, a compiler-written `goal` and `rollback` as decisions, and the unconstructable
  tag refused with its JSON contract intact.
- **golden** — a new `05-multiline-acceptance` example locks verbatim rendering across all
  seven targets, and a drift test proves the budget preview cannot diverge from the real
  renderer.

## Known gaps

Left open deliberately, and relevant to E2:

- Entry points whose interpreter is not knowable from the command line are not
  workspace-probed.
- A `before_after` digest over *constant* output still counts as a carrier. The empty case
  is refused and a `hold` over silent success is refused, but no digest can prove its
  command reads anything the work changes. This is the same honest limit as a `done:`
  declaration: a preservation-shaped carrier records that a human judgment decides; it
  does not mechanically discriminate.
- A hand-written brief with `base_rev` but no `baseline:` block skips B17 entirely, since
  the rule only judges a measured brief. Deleting the block is cheaper than defeating the
  rule.
- `constraints`, `forbidden`, `manual_checks` and `tests_editable` carry one marker and
  one ledger entry per list, not per item.
- `draft`'s printed decision count is inflatable by compiler-authored content that
  contains the marker text. The ledger is authoritative and is not forgeable this way, and
  both failure directions are closed.
- B10 can still be steered by a compiler-chosen refactor word in the goal or a fourth
  scope entry; both fields are now confirmed decisions, but `draft` gives no compile-time
  warning that the goal it just wrote will force a plan gate.
- A brief armed before 0.12.0 may need re-measuring (see above).

## What may and may not be claimed

Allowed:

> Compiler v2 fixes the specific contract-quality, delivery and environment defects found
> by E1 and is ready for a new experiment.

Not allowed, and nothing in this work supports them: that compiled contracts improve or
worsen agent outcomes, that humans specify less with the compiler, that compiled contracts
catch wrong implementations, or that E1 was overturned. E1's product decision — keep
Prompire verifier-first, with the compiler as a drafting helper — stands. Nothing here
repositions the project as a task compiler.

## E2 readiness

The treatment is frozen at `08ca412`. Any later change to it creates a new experimental
population and is a different experiment.

E2 must not repeat E1's main population flaw, in which the ≤15-word requests were authored
with knowledge of the upstream fixes and encoded the identifying diagnosis for five of six
fix-parent tasks. The population that matters is genuinely underspecified short requests
whose relevant semantics are discoverable from the repository but not already embedded in
the request — "Fix custom prompt validation when input is hidden", not "Preserve the exact
Click BadParameter formatting path when hide_input is true". E1 could not measure the
compiler on that population, which is precisely where a compiler would earn its keep.

E2 also needs a `plan_first`-aware execution protocol. E1's freezing rule put that arm out
of scope; v2 makes an unattended run's plan gate a reviewed decision rather than a silent
default, which is the variable E2 exists to test.

## Single next action

> Run E2 on genuinely underspecified requests.
