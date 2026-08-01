# Campaign 2026-08-01 — first cross-agent matrix

The first campaign to run more than one live host. `d87769c` added `codex` and
`antigravity` beside `claude`; this is the measurement that addition exists for.

## Pre-registration

Written before any cell ran. One arm per host, full task set:
`current` × {T01…T06} × 5, live `claude`, `codex` and `antigravity`, 90 cells.

What is registered as an expectation and what is not:

- **claude** — `current` has taken T05 and T06 at 5/5 twice (runC of
  2026-07-31 on the old wording, runA of 2026-08-01 on the current wording).
  Expectation: it stays at ceiling there. T01–T03 have no prior live rows;
  those cells are first measurements.
- **codex, antigravity** — no prior rows anywhere except one adapter smoke
  each on T01 (codex solved it; agy missed the flip criterion). Every cell is
  a first measurement. No prediction is registered; the campaign is
  exploratory for these hosts, and its reading rule is registered instead:
  a red codex or agy cell is evidence about that host under this prompt,
  not about the prompt's wording, until an ablation arm for that host
  separates the two.

CLI versions: claude 2.1.220, codex-cli 0.146.0, agy 1.1.9. Neither codex nor
agy reports which model ran (`references/benchmark.md`); their configured
defaults were left untouched for the duration of the campaign, which is the
strongest population statement available for those rows.

## Files

| file | status | contents |
|---|---|---|
| `runA.jsonl` | pre-registered | `current` × {T01…T06} × {claude, codex, antigravity} × 5 |

## Result

(unfilled until the run completes)
