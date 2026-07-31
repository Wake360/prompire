# Behavioural benchmark

Golden snapshots prove the renderer returns the same bytes. They cannot say
whether a prompt makes an agent's work better. This benchmark measures that the
only way it can be measured: run the task, then look at the repo from outside —
the same verify_acceptance + check_scope pair a human would run. Nothing the
agent prints is trusted.

## Anatomy

A cell is task × variant × agent:

- **task** — a brief in `bench/tasks/*.yaml`, written against the fixture repo
  in `tests/fixtures.py`, without a `baseline:` block: `bench/run.py` measures
  it with `baseline.py --write` and arms the pin with `--activate` before every
  cell. The brief lives at `.prompire/brief.yaml` inside the repo, so the brief
  itself never trips the scope check.
- **variant** — a prompt renderer in `bench/variants.py`. `current` is what
  `render_brief.py` produces today; every other entry is a hypothesis. A
  variant that does not beat `current` across the matrix does not move into
  the renderer. `no_state`, `no_guard`, `no_bounds` and `no_acceptance` are
  ablations — each
  removes exactly one thing the brief adds, so the matrix says which *part*
  earns its tokens rather than only whether the brief as a whole does.
  An ablation whose factor is stored in the brief removes it from the file on
  disk as well as from the prompt; `no_guard`'s factor is a rendered sentence
  the brief never stores, so it hands the file over unchanged.
  The rendered prompt names `.prompire/brief.yaml`, and that file is
  readable: a variant that dropped the criteria from the text while leaving
  them in the file would have handed the agent their address instead of
  removing them. `bench/variants.py`'s `BRIEF_EDITS` is what each variant
  writes there, and `bench/run.py` restores the author's brief before
  measuring, so the criteria and the boundary judged at the end are always
  the author's.
  `no_state` keeps the commands but drops their measured red/green/frozen
  labels: it renders the control and deletes each criterion's trailing
  parenthetical for every label `render_brief.state_of` can emit, raising if
  none matched rather than silently returning the control. `STATE_NOTES` in
  `bench/variants.py` must list every label `render_brief.state_of` can
  return, and `tests/bench.py` asserts that set equality in both directions.
  Miss one and a brief that renders it keeps its label while the other
  notes still match, so `hits` stays nonzero and the no-op guard never
  fires. `no_guard` drops the sentence announcing the external diff check.
  `no_bounds` drops `scope`, `forbidden` and every sentence pointing back
  at them, while leaving the external check intact — a path named in
  `goal` or `manual_checks` survives on purpose, since cutting it would
  ablate a second factor. `no_bounds` also necessarily removes the
  consequence clause "A file changed outside the list above fails it." —
  the clause names a list the ablation deletes, so it cannot survive
  coherently. It keeps the announcement that an external check runs,
  which is `no_guard`'s factor; the two ablations therefore overlap only
  on the consequence clause, and the announcement is removed by
  `no_guard` alone. `tests/bench.py` asserts that split. Read a
  `no_bounds` result as "no declared allowlist, still told it is
  checked", not as "no enforcement mentioned".
  `no_acceptance` drops the criteria and their header, keeping goal, boundary
  and autonomy — the first live matrix showed half of what a naked request
  loses is the contract (which string `total_line()` must render, what the
  extracted function is called), and no other ablation removes it. An
  ablation that removes nothing scores like the control and reads as "this
  factor does not matter", which is the one result the experiment must never
  fabricate. Most text cuts raise when they match nothing, but not all: the
  "listed paths are the whole boundary" tail `no_bounds` removes is declared
  optional, because autonomy `manual` and the undeclared-autonomy sentence
  carry no such tail. What actually protects the property is
  `ABLATION_CONTRACT` in `tests/bench.py` — every phrase an ablation owns
  must be absent from its render and present in some control render, so a cut
  that stopped matching fails there instead of scoring.
  `bare` is the opposite control: the goal line alone, the
  request as it would have arrived without Prompire. It answers whether the
  brief earns the tokens it costs, and the comparison is fair because both
  variants are measured from outside against the *author's* brief — only what
  the agent was told differs. Against `scripted:*` agents every variant scores
  alike, because a scripted write-set ignores its prompt; variants only
  separate under a live agent.
  The ablations above are subtractive: each removes one factor from the
  complete brief and asks whether the rest still carries the task — that
  measures necessity. `plus_acceptance` and `plus_bounds` are additive:
  each starts from `bare` and adds back exactly one factor, which
  measures sufficiency. The two can both come back negative without
  contradiction — that is what redundancy looks like, and it is why a
  subtractive-only matrix cannot tell "this factor does nothing" apart
  from "another factor covers for it".
  `plus_acceptance` keeps the acceptance criteria as the renderer writes
  them, including the measured-state parenthetical on each command
  (`fails today; must pass when you are done` and the rest of
  `STATE_NOTES`). A positive result therefore supports "the criteria
  block, measured state included, was sufficient" — not "the commands
  alone were". Separating those two needs a further variant that nothing
  in this plan builds.
- **agent** — `scripted:<behavior>` (deterministic write-sets from
  `bench/behaviors.py`; the only kind CI ever runs) or a live CLI (`claude`).

Metrics per run (one JSONL row): acceptance passed/failed/not_run, check_scope
exit, changed test files, wall seconds, prompt word count, and — when the
agent's CLI reports them — turns, tokens, cost and the model id. `tokens_in`
sums the cached and uncached input fields: the CLI's `usage.input_tokens` alone
counts only the uncached remainder and reads near zero on a cached run.
`model` is joined from the keys of `modelUsage`, which is where the CLI records
what actually ran — there is no top-level `model` field. Every row also
carries its provenance: a timestamp, the Prompire commit (`prompire_rev`) and a
sha256 prefix of the exact prompt text (`prompt_sha`). Rows whose `prompt_sha`
or `model` differ are different populations — never average across them.
`bench/report.py` renders the matrix; a run is SOLVED only when the acceptance
is green AND check_scope exits 0. An agent that greens the acceptance by
editing a frozen test shows up as SCOPE, not ok, and one that edited the brief
or the pin shows up as GAMED — `tampered` lists what it touched — even if that
same run also crashed on the way out. A `bench/run.py` exception row, or a
live `claude` row that crashed or never reported a model, reads ERR instead:
an empty diff there means the run never happened, not that the prompt failed.
Live agents are stochastic: one run per cell is noise, so real comparisons use
`--repeats N`, and the report renders such cells as their solved rate among
the rows that actually ran ("4/4≥0.51 E1" for a cell of 5 with one ERR),
naming any SCOPE/FAIL/GAMED/ERR rows alongside it rather than folding them
into the count; a cell where every rep crashed prints "no attempts", never a
`0/0` that could be misread as a measured zero. The per-arm footer beneath the
matrix uses the same denominator — every non-ERR row for that variant×agent —
so it can never disagree with the cell marks above it. A cell whose rows
disagree on `(prompt_sha, model, prompire_rev)` — an error row does not
count, since it has no population to belong to — renders as `MIXED` instead
of a mark; the rest of the matrix and the per-arm footer still render, and
the run exits 2 with the offending cells named at the bottom.

## What the first campaigns support

The `current` vs `bare` matrix (6 tasks × 5 repeats, 30/30 vs 13/30) stands as
a lower bound on the gap, not as a measurement of it. Those cells ran before
any variant edited the brief on disk, so a `bare` cell left the complete
author brief at `.prompire/brief.yaml`: undisclosed by the prompt, but found
by any agent that lists the repo. That could only have helped `bare` —
`current` is the control and discloses the file deliberately — so the true
gap is at least the measured one and the headline conclusion survives. Its
failure split stands too — `bare` went out of scope on T02 and T04 and missed
the contract on T05 and T06.

The single-factor ablation matrix on T05 (`no_state`, `no_guard`,
`no_bounds` all 5/5 against `bare` 0/5) does not support "no single factor
is necessary". Two of those arms — `no_state` and `no_bounds` — disclosed
the path to a file still carrying every ablated field, and `no_state` at
that time substituted a placeholder rather than deleting the labels. The
prompt names that path on the `check_scope.py` line alone, which is the
line `no_guard` cuts. `no_guard` 5/5 is the one arm unaffected by the
leak — it removes the path along with the sentence — and it says the guard
announcement was not what carried T05.

Per-cell repeats measure stability, not a sampling distribution: a cell
re-runs the same prompt bytes against the same fixture, so the only thing
varying across a cell's repeats is the agent. Comparisons need variation
across tasks, not more repeats on one. An earlier version of this section
supported that with "every cell observed so far has been 5/5 or 0/5"; six
cells of 5 or 0 cannot total 13, so the claim is withdrawn rather than
repaired — the point above does not rest on it.

None of the numbers in this section can be re-checked. Each campaign wrote
its rows to `bench/results/`, which is gitignored, and no copy survives, so
the per-task split behind 13/30 cannot be recovered and everything here is
testimony. Commit or archive a campaign's JSONL somewhere outside
`bench/results/` before the tree is cleaned; that is exactly how the first
campaign's rows evaporated.

## The 2026-07-31 campaign

The first campaign measured by the repaired instrument. Rows are kept in
`bench/campaigns/2026-07-31/`, so unlike everything above, all of it can be
re-checked. Runs A, B and C were pre-registered before any of them ran; the
`bare` arm was added afterwards and is filed and labelled separately.

                     current  bare   no_acceptance  plus_acceptance  plus_bounds
    T02 hold-preserv.    -     1/5         -              5/5             5/5
    T04 monorepo-cwd     -     0/5         -              5/5             5/5
    T05 forbidden-temp. 5/5    0/5        0/5             5/5             0/5
    T06 extract-module  5/5    0/5        0/5             5/5             0/5

On the contract tasks the acceptance criteria are both necessary and
sufficient, closed from four sides: remove them and it is 0/5, supply them
alone and it is 5/5, supply the allowlist alone and it is 0/5, supply
everything and it is 5/5.

On the boundary tasks the predicted mirror image did not appear — both single
factors carry the task. Read `plus_acceptance` there as coupled, not as bounds
being redundant: T02's criteria run the frozen suites `tests.test_cart` and
`tests.test_legacy`, and T04's import `api.handler`, which is that task's
entire `scope`. On both, the criteria block states the boundary in the course
of stating the contract. The pre-registration anticipated this for T02; it
holds for T04 as well.

`plus_bounds` dissociates cleanly: 5/5 where `bare` fails by leaving the
allowlist, 0/5 where `bare` fails by missing the contract. An allowlist
repairs scope violations and does nothing for contract misses.

The failure modes are what make the table mean anything. All nine scope
violations in the campaign belong to `bare`, and every one is on T02 or T04;
no other arm left its boundary in any of the eighty runs. On T05 and T06,
`bare`, `no_acceptance` and `plus_bounds` all fail identically — in scope,
one acceptance criterion of two. `bare`'s split therefore reproduces the
older testimony that it "went out of scope on T02 and T04 and missed the
contract on T05 and T06", this time from rows that still exist.

Sixteen cells of twenty were uniform across their five repeats; T02 × `bare`
split 1/5 and is the reason the earlier blanket claim about uniformity was
withdrawn rather than repaired. Uniformity is common here, not a property to
lean on.

## Running

    python3 tests/bench.py                             # harness self-test, scripted only
    python3 bench/run.py                               # scripted good across all tasks
    python3 bench/run.py --agents claude --repeats 5   # live run; costs minutes and money
    python3 bench/report.py bench/results/run.jsonl

Live runs are not sandboxed, and the temp repo should not be read as one. It
bounds what the *harness* sets up, not what the agent can reach: the cell runs
as you, with your environment and the CLI's own credentials, and an agent that
writes an absolute path or a `..` writes there. No Prompire hook is active
inside a cell either — a fixture repo carries no project settings, and
`--setting-sources project` deliberately excludes the guard installed in your
user settings — so enforcement is entirely post-hoc. `--permission-mode
acceptEdits` auto-accepts file edits and leaves every other tool to the CLI's
defaults; do not raise it to `--dangerously-skip-permissions`. Measuring means
executing code the agent wrote: the acceptance commands run over the agent's
source, in your account. Task briefs are executed input for the same reason, so
point `--tasks` only at briefs you wrote. Live cells are never part of
tests/run_all.py or CI.

Against a gaming agent the harness snapshots `.prompire/brief.yaml` and
`.prompire/ACTIVE` before the agent starts and restores both before measuring,
so the criteria and the boundary are the author's whatever the agent did to
them, and any such edit marks the row GAMED. What remains unverifiable is only
what no local tool can verify — that the agent did not reach outside the repo
while it ran.

Live cells run `claude` with `--setting-sources project`, so the user-level
CLAUDE.md, behaviour profile and skills stay out of the measurement — the
benchmark compares prompts, not one machine's personal instructions. The cell
still inherits the CLI's auth and default model; whatever model actually ran is
recorded in the row's `model` field.

## Growing the set

The target is 15–30 tasks. Add one per category gap, and one per real
production failure: when an agent games a brief in the wild, reduce the episode
to a task brief plus a write-set in `bench/behaviors.py`, so the failure stays
measurable forever. A new task needs exactly three things — the brief (no
baseline block), a `good` write-set, and `python3 tests/bench.py` green.
