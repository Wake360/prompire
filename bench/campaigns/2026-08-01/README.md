# Campaign 2026-08-01 — wording confirmation

The renderer's wording was tightened after the 2026-07-31 campaign (commit
`32250a2`), so that campaign's table is evidence about the old wording. This
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

10/10 solved: `current` × T05 5/5, `current` × T06 5/5 (Wilson lower bound
0.57 each, same as runC). The hypothesis holds — the tightened wording still
carries both contract tasks — so the 2026-07-31 control replicates under the
current renderer. The ablation arms remain statements about the old wording.

## Provenance

Every row carries `prompire_rev: 2bc4414+dirty` — the pre-registration commit
under its pre-rewrite name. Later on 2026-08-01 an internal document was
removed from the repository's whole history, rewriting every commit from the
removal point forward: `2bc4414` is now `ce198e9`, and its tree differs from
what ran only by the removed document, which no measured tool reads. The rows
keep the name they recorded; `PINNED_AT` names the rewritten commit, because
the old name can no longer be checked out. The `+dirty` flag was raised by
this directory's own then-untracked `PINNED_AT` and rows, and by the untracked
`PROMPIRE-VERDIKT.md` and `prompting_proposal.md` that predate the campaign;
no tracked file differed from the pinned tree at any point. One model set
(`claude-haiku-4-5-20251001+claude-opus-5[1m]`), one `prompt_sha` per task,
no row tampered.
