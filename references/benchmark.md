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
  the renderer.
- **agent** — `scripted:<behavior>` (deterministic write-sets from
  `bench/behaviors.py`; the only kind CI ever runs) or a live CLI (`claude`).

Metrics per run (one JSONL row): acceptance passed/failed/not_run, check_scope
exit, changed test files, wall seconds, prompt word count, and — when the
agent's CLI reports them — turns, tokens and the model id. Every row also
carries its provenance: a timestamp, the Prompire commit (`prompire_rev`) and a
sha256 prefix of the exact prompt text (`prompt_sha`). Rows whose `prompt_sha`
or `model` differ are different populations — never average across them.
`bench/report.py` renders the matrix; a run is SOLVED only when the acceptance
is green AND check_scope exits 0. An agent that greens the acceptance by
editing a frozen test shows up as SCOPE, not ok. Live agents are stochastic:
one run per cell is noise, so real comparisons use `--repeats N` and the report
renders such cells as their solved rate ("3/5") instead of a single mark.

## Running

    python3 tests/bench.py                             # harness self-test, scripted only
    python3 bench/run.py                               # scripted good across all tasks
    python3 bench/run.py --agents claude --repeats 5   # live run; costs minutes and money
    python3 bench/report.py bench/results/run.jsonl

Live runs execute an autonomous agent with edit permissions inside a throwaway
temp repo. `--permission-mode acceptEdits` is deliberate; do not raise it to
`--dangerously-skip-permissions` unless you are watching the run. Live cells
are never part of tests/run_all.py or CI.

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
