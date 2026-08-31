# Recorded runs and the suite

The suite turns verdicts `verify` has already produced into a private, replayable
bench: fixtures pinned from real work, a stored baseline, and every later run
reported as a comparison against it. Nothing here grades a single diff — that is
`verify`'s job — and nothing here asks the agent anything.

## The run record

`prompire verify --record` appends the verdict to `.prompire/runs.jsonl`, one
JSON object per line: the same `scope` and `acceptance` objects `--json` prints,
under an envelope carrying a timestamp, a `run_id`, the repo-relative brief path
and its sha256, the base revision, the sha256 of `git diff --binary` against
that base, and the exit code. Only a run that reached a verdict writes a row —
an indeterminate run or a refusal writes nothing — and a store that cannot be
written warns on stderr without changing the verdict. `.prompire/**` is always
inside the boundary, so the store never trips a later scope check.

## Admission: `prompire suite add <run>`

`<run>` is a `run_id` from the store, a unique prefix of one (8+ characters), or
`last`. Admission is a two-sided gate, checked by re-execution in a workspace
cloned from a pinned bundle: the recorded acceptance must **fail at the pinned
base** and **pass with the recorded patch applied**. A fixture that cannot fail
measures nothing, so a task already green at base is rejected by name.

The base is pinned as a self-contained git bundle (via the temporary branch
`prompire-suite-pin`), so the fixture replays even after the repository's own
history moves on. `--reserve` places the fixture in the reserve slice (below).

A rejection prints `rejected: <reason> — <message>` and exits 2; nothing
half-written is left behind. The reasons:

| reason | meaning |
|---|---|
| `missing-record` | no run store, or no run matches the selector |
| `brief-changed` | the brief no longer hashes to what the run recorded |
| `missing-patch` | the tree has moved past the record; the diff cannot be reconstructed |
| `pin-failure` | the pin branch already exists, or the bundle could not be built |
| `not-runnable` | the recorded acceptance cannot be re-executed |
| `green-at-base` | acceptance already passes at the pinned base — the fixture cannot fail |
| `fail-at-patch` | acceptance does not pass even with the recorded patch |
| `already-admitted` | this run is in the manifest |

Exit 1 is reserved for one outcome: the fixture was pinned but the manifest
could not be updated — fixture landed, manifest behind.

The manifest (`.prompire/suite/manifest.json`) is versioned and content-hashed
over its fixtures and reserve membership. Any hand edit changes the hash and a
later `suite run` refuses with `suite-changed`.

## Replay: `prompire suite run <candidate>`

`<candidate>` names the result set (letters, digits, dot, dash, underscore,
≤64 chars). Every admitted fixture is cloned from its pinned bundle and run
through the bench machinery: `--agent patch` applies the pinned fix (the
deterministic ceiling), `noop` changes nothing (the floor), `scripted:<behavior>`
runs a scripted bench agent, and `claude`, `codex` or `antigravity` replay live.
`--variant` selects a prompt variant from `bench/variants.py`; a variant that
edits the brief or plants repository files cannot be replayed faithfully and is
refused.

The first run stores a baseline with `--as-baseline`. Every later run prints a
diff between two result sets — a run with no stored baseline and no
`--as-baseline` is refused before any fixture executes. A replay never writes
the manifest: it cannot admit, drop, or move a fixture.

Refusals exit 2 and nothing runs: `bad-candidate`, `unknown-agent`,
`unknown-variant`, `unreplayable-variant`, `bench-unavailable` (the replay goes
through `bench/run.py`, which ships with a checkout, not with a wheel — run from
a checkout), `no-suite`, `no-baseline`, `suite-changed`. Exit 0 = comparison
rendered or baseline stored with every fixture measured; exit 1 = rendered or
stored, but at least one fixture errored.

## Slices and the reserve

Results are sliced three ways — `acceptance` (the recorded commands pass),
`scope` (the run stayed inside the boundary), `gamed` (grading surfaces
untouched) — each reported for the `main` block and, separately, for the
`reserve` block. A fixture that errors is `ERR` and unmeasured: it never counts
as movement in any slice.

The reserve is the slice you never tune against. Its membership is fixed at
admission (`suite add --reserve`), recorded in the content-hashed manifest, and
a replay cannot change it. It exists to answer one question the main slice
cannot: whether an improvement on the fixtures you iterated on transfers to
fixtures you did not. Read it; do not optimize for it — a reserve that has been
tuned against is just a second main slice.
