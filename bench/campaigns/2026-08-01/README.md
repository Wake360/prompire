# Campaign 2026-08-01 — wording confirmation

The renderer's wording was tightened after the 2026-07-31 campaign (commit
`0a1e39b`), so that campaign's table is evidence about the old wording. This
campaign re-runs the contemporaneous control under the new wording.

## Pre-registration

Written before any cell ran. One arm, replicating runC of 2026-07-31 exactly
except for the renderer revision: `current` × {T05, T06} × 5, live `claude`.
Hypothesis: the tightened wording still carries both contract tasks — runC
gave 5/5 on each. A miss on either task is a wording regression and blocks
reading the 2026-07-31 conclusions as statements about the current renderer.

This is a control replication, not a full re-run: the ablation arms
(`bare`, `no_acceptance`, `plus_acceptance`, `plus_bounds`) are not repeated,
so the necessity/sufficiency reading of 2026-07-31 stays tied to the old
wording until someone re-runs those arms too.

## Files

| file | status | contents |
|---|---|---|
| `runA.jsonl` | pre-registered | `current` × {T05, T06} × 5 |

## Result

(unfilled until the run completes)
