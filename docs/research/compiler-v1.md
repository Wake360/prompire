---
title: Safe task compiler v1
tags: [prompire, compiler, trust-boundary]
date: 2026-08-03
source: implementation session on master, commits 1179433..21a83b2
related: [references/schema.md, references/rules.md, references/benchmark.md]
---

# Safe task compiler v1

What was built, why each piece exists, and what it is still not allowed to claim.

Starting point: `a597fcd` on `master`, post-P5. End state: seven commits,
`e0ea899..21a83b2`. Version in the tree moved to 0.11.0. Nothing was tagged or
published.

## The problem this addresses

The verifier was the proven half of Prompire. The benchmark shows what a
hand-authored contract does to an agent; it never measured Prompire producing
that contract. Three different drafting paths existed — a deterministic
heuristic, `draft --agent`, and the skill writing YAML directly — with different
schema coverage and different confirmation semantics. The skill path, the only
one that could express a real task, had no confirmation gate at all.

Underneath that sat a reproduced defect: a brief whose only acceptance criterion
was green on untouched HEAD and unrelated to the goal linted clean, prepared,
armed, and `verify` printed `clean` on a repository nobody had touched. The
verdict was unforgeable by the agent and entirely forgeable by the brief. A
compiler does not extend the verifier — it moves the one unverified authority
step from a human to a model. That is a trust change, so the gate had to exist
before the compiler did.

## What exists now

```
short request
    ↓
compiler backend (deterministic | host model | proposal file)
    ↓  untrusted YAML
one parser — measured fields refused, model comments dropped, unknown keys refused
    ↓
repository corroboration
    ↓
one serializer — markers on every authority-sensitive line, plus the ledger
    ↓
human clears both records
    ↓
prepare: baseline, lint, render, arm
    ↓
agent → verifier (unchanged)
```

Three frontends, one gate:

- `prompire draft "<request>"` — deterministic, no model. Proposes only
  acceptance commands the repository evidences.
- `draft --agent claude|codex|antigravity`, or `--agent-cmd <any CLI>` — a host
  model reads a disposable snapshot and answers with YAML.
- `draft --proposal <file|->` — new. Any host or skill writes the proposal
  itself and compiles it through the same validation and serialization.
  `SKILL.md` now routes the skill path here, which is what makes the three
  surfaces one product instead of three.

## Trust architecture

| class | fields | enforced by |
|---|---|---|
| propose, human confirms | `scope`, `forbidden`, `constraints`, relaxed `tests_policy`, `tests_editable`, `oracle`, each `acceptance` entry with `expect`/`requires`/`transition`/`before_after`/`cwd`/`timeout` named on its marked line, `manual_checks`, `context` | marker + ledger; `prepare`, `lint` (B18) and `--activate` all refuse |
| propose, no marker | `goal`, `plan_first`, `rollback` | the ordinary lint rules |
| clamped | `autonomy` | a draft always says `ask` |
| measured, never proposed | `baseline`, `base_rev`, `dirty_baseline` | a proposal carrying one is rejected outright |

Corroboration — a scope entry matching a tracked path, a command a config file
declares — is counted and reported but lowers no gate. Existence is not
permission: that a file is tracked says nothing about whether it is the right
boundary.

The classification lives in `references/schema.md` so a future change has to
argue with it rather than drift past it.

## The two confirmation records

Confirmation is the *absence* of a record, and there are two of them because they
fail differently.

`# prompire:unconfirmed` comments are what a human reads. The `unconfirmed:`
block is the same set of decisions stored as data. The block exists because
adversarial review armed a six-decision draft — a relaxed `tests_policy` among
them — by running it through one `yaml.safe_load`/`safe_dump`. That is all a
formatter, `yq -y .`, an editor plugin, or an agent asked to tidy the brief
does. Comments are the one part of a YAML file no round-trip preserves; the
block survives, and every gate refuses while it stands.

## New lint rules

**B17 — vacuous acceptance** (error). Once the baseline is measured, something
must distinguish untouched HEAD from done. Passes silently when the brief
declares a carrier: a criterion that flips, one that `hold`s, a `before_after`
comparison over a command that actually printed something, or a `manual_checks`
entry. Fires only after measurement — before it, B15 owns the gap.

Two escapes were removed after review found them reachable:

- a behavior-preserving word in the `goal`, because `goal` is the one field a
  compiler writes freely and no marker covers. `fix the off-by-one in total()
  and rename the helper` linted clean and verified clean on an untouched tree.
- a `before_after` digest over empty output, which reproduces on an untouched
  tree, on the work, and on any wrong work alike. `python -m unittest -q` on a
  passing suite is exactly that shape.

**B18 — unconfirmed draft** (error). Lint used to print "brief is shippable"
over a marker that `prepare` would refuse one command later. It now errors on
either record, and `check_scope.py --activate` refuses too — the confirmation
gate was one command deep and is now three.

## Schema coverage

Compilable now, and not before: `tests_policy: named`/`authoring` with
`tests_editable` and `oracle`, preserve-behavior refactors, new-file tasks,
monorepo `cwd`, plan-gated wide tasks, and tasks needing `context` or
`rollback`. The old eight-key whitelist made three lint rules unsatisfiable from
a compiler's own output, so the modal delegated task was structurally lint-red.

## Read-only drafting, enforced

A drafting run only reads. The disposable snapshot is now audited after the
agent exits — against its worktree *and* against the commit recorded before the
run, so an agent that commits its writes away does not hide them either. A run
that wrote anything is refused with the paths named. The writes are discarded
with the snapshot; they are not repaired, because a repaired write is a
contract violation nobody sees.

Still outside the audit, and documented as such: a write under a path the
snapshot's own `.gitignore` covers, and an absolute path the agent composes for
itself. Bounding those is a sandbox's job.

## Instrumentation and the offline harness

`draft` prints how many decisions need confirmation and how many facts the
repository corroborated. `--json` adds the backend, the counts and wall time.

`bench/compile.py` runs the compile half of E1 without a paid execution arm.
Per task: fresh fixture repo, a backend fed only the short request, a mechanical
blind-confirm that clears both records and logs how many human decisions that
stood in for, the real baseline and lint tools, then the **discrimination
triple** — the compiled acceptance run on untouched HEAD, on the gold write-set,
and on a plausible-but-insufficient wrong one. A behavioral contract should read
fail / pass / fail.

Classification per row: `rejected`, `discriminating`, `manual-semantic`, or
`preservation-only`.

Current results, gold backend (the gold brief's own fields through the same
gate — a ceiling, not a product arm):

```
discriminating  T01-flip-fix              triple=fail/pass/fail  missing=0 invented=0
discriminating  T05-forbidden-temptation  triple=fail/pass/fail  missing=0 invented=0
discriminating  T06-extract-module        triple=fail/pass/fail  missing=0 invented=0
```

The hidden gold contract and both write-sets stay outside the repository the
compiler inspects, and `tests/bench.py` asserts they cannot be found in it. That
is isolation of the fixture tree, not a sandbox: a backend with filesystem
access to this checkout can read `bench/tasks/` for itself. The docstring says
so rather than overclaiming.

## Adversarial results

The eight required attacks, run live end to end:

| # | attack | result |
|---|---|---|
| 1 | irrelevant green acceptance | blocked — B17 at prepare; also measured in the harness |
| 2 | invented `npm test` | blocked — marked as the model's own claim; blind-confirmed it still fails B7 |
| 3 | model self-confirmation | blocked — comments never survive the parse |
| 4 | injected measured fields | blocked — all three refused by name |
| 5 | broad scope convenience | blocked — marked and disclosed; B6 at prepare |
| 6 | test-policy relaxation | blocked — policy, editable list and oracle each marked |
| 7 | repository mutation while drafting | blocked — audited both ways, refused with paths named |
| 8 | hidden verifier regression | none found |

A fresh-context adversarial reviewer found four further defects, all fixed and
pinned by tests: comment-only confirmation state (the round-trip laundering
above), unmarked acceptance sub-keys, the goal-word B17 escape, and the
commit-to-hide gap in the snapshot audit. What it could not break: the YAML
scalar quoting, marker forgery or neutralization, non-string scalars, key
casing, anchors and tags, `context` block-scalar escape, CRLF and unicode
marker evasion at all three gates, and snapshot symlink containment.

## Verifier regression

None. The only verifier-module edits are a shared constant in
`brief_common.py` and one refusal in `check_scope.py --activate`, placed before
`activate()` runs. A regression reviewer armed briefs on the pre-change tree and
ran the new verifier against them: `verify`, `check_scope --strict --json` and
`verify_acceptance --json` were diff-identical, for clean and violation
scenarios alike. Renderer goldens 35/35, with only the one example that gained a
manual check moving.

The new refusal closed a hole rather than opening one: a marker-laden draft
could previously be armed through the low-level tool.

## Tests

`python3 tests/run_all.py` — 13 suites, all pass. Battery 56/56 (9 new B17/B18
cases), e2e 66/66, examples 5/5, golden 35/35, docs 18 rules with 0
inconsistencies, hook 217/217, encoding, verify 7/7, bench 649/649 (including
the compile-harness self-tests), cli 74/74 (7 new compiler cases), runner,
package, ci 27/27. `prompire demo` exits 0.

## Commits

```
1179433  lint: B17 refuses a measured brief nothing can flip; B18 keeps markers un-shippable
d6d096e  compiler: one proposal gate for every frontend, full draft schema, read-only enforced
cee1a1a  bench: offline compiler-stage harness — request in, scored contract out
d91b361  changelog: 0.11.0
58f1372  draft: carry a list-valued context as lines; sharper overwrite and dirty-tree advice
67d54f1  compiler: confirmation state survives a YAML round-trip; three B17 escapes closed
21a83b2  lint: a before/after digest over empty output carries nothing
```

## What may be claimed

Prompire can propose a repository-grounded task contract from a short request,
separate what the repository corroborates from what a model judged, require
explicit human confirmation for every authority-sensitive decision in a form
that survives reserialization, refuse a contract that cannot tell an untouched
repository from a finished one, and hand the confirmed result to an unchanged
verifier.

## What may not be claimed

> Humans specify less and agents perform better.

Also forbidden until E1 runs: that compiled contracts match authored ones in
quality, that confirming costs less than authoring, and any repositioning of the
project as a task compiler. Verifier-first positioning stands.

## Known gaps, deliberately left

- A gitignored write inside the drafting snapshot evades the audit, the same way
  it evades the checker's evidence.
- `bench/compile.py` isolates the fixture tree, not the filesystem.
- The deterministic backend infers little on a repository with no test
  configuration — it says so rather than inventing a command, but the human then
  authors both decisions.
- Lint findings surface at `prepare`, not at `draft`, so a human can confirm
  markers on a brief that a rule will reject a moment later.

## Next

Run E1.
