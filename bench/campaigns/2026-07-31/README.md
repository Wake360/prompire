# Campaign 2026-07-31

Raw rows for the first campaign run against the repaired instrument. Kept here, outside
the gitignored `bench/results/`, because the previous campaign's rows were left there and
no longer exist — every number from it is now testimony that cannot be re-checked.

## Provenance

Every row carries `prompire_rev: 3f1d802+dirty`. No tracked file differed from `3f1d802`
at any point during the campaign — `git status --porcelain` showed only untracked entries
throughout. The `+dirty` flag was raised by `PROMPIRE-VERDIKT.md` and
`prompting_proposal.md`, which predate the campaign, and by this directory itself. The
flag is doing its job; it just cannot distinguish untracked scratch from edited source.

80 rows, one `prompt_sha` per (task, variant) pair, one rev throughout.

## Files

| file | status | contents |
|---|---|---|
| `runA.jsonl` | pre-registered | `no_acceptance` × {T05, T06} × 5 |
| `runB.jsonl` | pre-registered | `plus_acceptance`, `plus_bounds` × {T02, T04, T05, T06} × 5 |
| `runC.jsonl` | pre-registered | `current` × {T05, T06} × 5 — contemporaneous control |
| `runD-posthoc-bare.jsonl` | **post-hoc, not pre-registered** | `bare` × {T02, T04, T05, T06} × 5 |

`runD` was added after Run B's results were seen. It is not a test of a new hypothesis:
it re-establishes the floor every other arm is read against, because the original `bare`
data is gone. It is filed separately and labelled so no later reader mistakes it for part
of the registered protocol.

`PINNED_AT` records the commit the campaign was pinned to.

## Reading the rows

    python3 bench/report.py bench/campaigns/2026-07-31/runB.jsonl

Do not pool the files: `report.py` keys populations on `(prompt_sha, model, prompire_rev)`
and will render `MIXED` and exit 2 rather than average across arms.
