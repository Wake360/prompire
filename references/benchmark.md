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
  the renderer. `bare` is the opposite control: the goal line alone, the
  request as it would have arrived without Prompire. It answers whether the
  brief earns the tokens it costs, and the comparison is fair because both
  variants are measured from outside against the *author's* brief — only what
  the agent was told differs. Against `scripted:*` agents every variant scores
  alike, because a scripted write-set ignores its prompt; variants only
  separate under a live agent.
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
or the pin shows up as GAMED — `tampered` lists what it touched. Live agents are
stochastic:
one run per cell is noise, so real comparisons use `--repeats N` and the report
renders such cells as their solved rate ("3/5") instead of a single mark.

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
