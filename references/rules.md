# The rules — what each one catches, and what it cannot

Rule ids are stable. Where each comes from is `grounding.md`; a rule that cannot be
traced there gets deleted, not weakened. Field meanings are `schema.md`.

| id | rule | severity |
|---|---|---|
| B1 | `goal` exists | error |
| B2 | goal is one sentence, ≤30 words, one task | error (sequenced goal: warn) |
| B3 | no vague terms in `goal` or `expect` | error (in `constraints`: warn) |
| B4 | an `acceptance` block exists | error |
| B5 | criteria are `cmd` + `expect`, unique on `(cmd, cwd)`, with a well-formed `cwd`, `timeout`, `requires`, `transition` | error (unrunnable-looking cmd, unreadable `expect`, unknown `requires`: warn) |
| B6 | `scope` exists, is not the whole tree, is repo-relative | error (whole top-level directory: warn) |
| B7 | a test-suite criterion is only a judge if the tests are pinned — see below | error |
| B8 | `autonomy` is one of three words; `auto` needs `rollback` and a runnable criterion | error |
| B9 | destructive verbs require `manual` or `ask` | error |
| B10 | a wide task needs `plan_first: true` | error |
| B11 | constraints do not contradict each other, the goal, or the scope | error (duplicate constraint: warn) — *inference, not a quoted passage* |
| B12 | unknown keys | warn — *no book source; schema hygiene* |
| B13 | `forbidden` is present (`[]` counts) | warn |
| B14 | behaviour-preserving work compares before and after | warn |
| B15 | every criterion carries a measured baseline, and one that is not green today declares which transition it is making | error (missing baseline, missing evidence, unverifiable criterion: warn) |
| B16 | `base_rev` is present and names a fixed commit SHA, not `HEAD` or a branch | error |
| B17 | once the baseline is measured, something distinguishes untouched HEAD from done: a criterion that flips, or a declared carrier of done-ness — `hold`, `before_after`, or `manual_checks` | error — *inference, not a quoted passage* |
| B18 | no `# prompire:unconfirmed` marker and no `unconfirmed:` ledger block remains | error — *no book source; the confirmation contract made visible* |

## B7 — the Goodhart rule, in three arrangements

"Make the suite green" is a proxy for "make the code correct". An agent that may edit
the tests will vibrate next to the ball: weaken the assertion, add a skip, delete the
case. `tests_policy` names which arrangement this task is in, and `check_scope.py`
enforces it against the real diff — the agent cannot satisfy it by adding a command to
its own acceptance block.

| policy | the agent may | mechanically enforced | needs `tests_editable` | needs `oracle` |
|---|---|---|---|---|
| `immutable` | nothing under a test path | any test file added, edited, renamed or deleted is a violation | — | — |
| `named` | edit only the listed test paths | every other test file is frozen | yes | — |
| `authoring` | rewrite the listed suites — repairing them *is* the task | only that the edits stay inside the listed paths | yes | yes |

Declaring nothing, on a brief whose acceptance runs a test runner, is error
`B7 proxy-criterion`. The old spelling — `tests/**` in `forbidden`, a "do not modify
tests" constraint, or a `git diff --stat -- tests/` criterion — still counts, and means
`immutable`.

### What is mechanical

`check_scope.py` reports these as VIOLATION. They are text facts about a diff:

- a test file was added, modified, renamed or deleted when the policy forbids it;
- the diff adds a literal disabling marker — `@unittest.skip`, `@pytest.mark.skip`,
  `pytest.mark.xfail`, `it.only`, `describe.skip`, `t.Skip(`, `@Ignore`, and the rest of
  `SKIP_MARKERS` in `brief_common.py`;
- a file outside `scope`, or inside `forbidden`, changed at all.

### What is not

**No checker here claims to detect a semantically weakened test.** `assertEqual(x, 6)`
becoming `assertIsNotNone(x)` is a deletion plus an addition — caught under `immutable`
and `named` (as a REVIEW), but under `authoring` it is invisible and is meant to be:
rewriting assertions is the task. That is why
`authoring` requires an `oracle` and always emits a REVIEW flag telling a human to read
the test diff. A heuristic that guessed at assertion strength would fail both ways and
would be trusted anyway, which is worse than a flag that says "read this".

Two more honest gaps:

- A `hold` criterion pinned only on an exit code does not notice the suite going from
  three failures to seven. Add `before_after: true` on a command whose stdout carries
  the detail if that matters.
- The guard sees the diff, not the run. A test that passes because of an environment
  change rather than a code change looks identical to it.

## B15 — what the baseline is for

B4 forces the brief to name a criterion. B15 forces it to know what that criterion said
before the work. `pytest -q → exit 0` carries no information if the suite was already
red: the agent cannot reach it, and afterwards a reviewer cannot tell "the agent broke
this" from "this was broken on arrival". The three transitions in `schema.md` are the
three answers, and `not_runnable` + a reason is the fourth: *we do not know, and here is
why we do not know*. Missing evidence beats a guessed pass.

`baseline.py` is what produces the block. It refuses to run a command that is
destructive, interactive, repo-writing, or declared environment-dependent, and it
refuses to measure anything at all on a dirty tree unless the dirt is declared in
`dirty_baseline`.

## B16 — a moving or absent base_rev defeats check_scope.py

`check_scope.py` diffs the real change against `base_rev`. A brief without one names no
starting commit, and the only base left is `HEAD` — which is the hole: an agent can commit
its own work before the guard runs, which moves `HEAD` to include that work, which makes
the diff against `HEAD` empty. A guard that defaulted there would exit 0 and report "every
change is inside the declared boundary" — true of an empty diff, meaningless as a review
of what actually happened.

Both halves of that are closed as of 0.2.0, and they are closed in different places.
`check_scope.py` **never falls back to `HEAD`**: with no usable base it prints `no base to
check against …` and produces no verdict (exit 2). B16 is the other half — it moves the
same failure to lint time, where the fix is one command instead of a puzzling refusal
after the agent has already run.

A blank field is not the only way to get there. `base_rev: HEAD`, `base_rev: main`, or
any other branch name or symbolic ref reproduces the identical failure with one extra
step: the agent (or a human copy-pasting a template) writes a value that *looks* pinned
but still names wherever the ref points at the moment the guard runs, not where the work
started. The first version of this rule only checked that `base_rev` held a
git-ref-shaped string, which let `HEAD` and branch names straight through — the property
that actually closes the hole is that the value cannot move, so B16 requires a 7–40
character hex commit SHA and rejects everything else, including well-formed refs.

`baseline.py` writes `base_rev` into every `baseline:` block it produces, stamped at the
commit it measured from — a 12-character short SHA, not a ref. Short, not full, which is
why `check_scope.py` resolves both sides through `git rev-parse` before deciding whether
an explicit `--base` disagrees with the pin: a 12-character and a 40-character spelling of
one commit are one commit, and a string compare called them different. A brief built the documented way —
`baseline.py --write`, then lint — never lacks one or carries a moving one. Only a
hand-written brief, or one edited after the fact, can. (Where HEAD is unborn — before a
repo's first commit, or on a fresh `git checkout --orphan` branch — there is no commit to
stamp, so `baseline.py` refuses rather than writing a placeholder that its own linter
would then reject.)

### What B16 cannot check: the brief is still the agent's to rewrite

A fixed SHA is not the same as an honest one. The brief is a YAML file the agent edits,
so the bypass survives the rule with one extra command: commit the work, `git rev-parse
HEAD`, write that SHA into `base_rev`. It lints clean — it *is* a fixed commit SHA — and
the diff against it is empty, because the work is inside it. No rule that reads only the
brief can tell that apart from an honest stamp, which is why this one is not a lint rule
at all.

And `base_rev` is not even the field worth the most. `dirty_baseline` paths are skipped
unconditionally, so appending one entry excuses a violation with no commit and no
re-stamp; a wider `scope` excuses all of them at once. Any guarantee of the form "the
verdict cannot be bought by editing the brief" has to cover the whole file.

`check_scope.py` therefore checks the brief against records it does not control, and
produces **no verdict at all** when one of them disagrees:

| record | where | covers | binds when |
|---|---|---|---|
| the digest | `.prompire/ACTIVE`, written by `--activate` | every byte of the brief | the guard was armed |
| the pin | `.prompire/ACTIVE`, written by `--activate` | `base_rev` | the guard was armed |
| the history | the brief's committed copy at `base_rev` | `base_rev`, weakly | the brief is tracked there |

The pointer is protected by the hook at any depth, along with `ACTIVE.tombstones`, which
`--deactivate` appends to: without it, `--deactivate && --activate` re-pins whatever the
brief now claims and reports it under the strongest label the tool prints. **Any** re-arm
in a repo where a guard has ever been disarmed is reported as `repin`, not `pin`, and
corroborates nothing. Any, not just a re-arm of the same path: the path is what an evader
picks, so copying the armed brief to a new name with `base_rev` re-stamped would
otherwise read as a first arm. It is also the honest user's incentive — with per-path
keying, revising a brief in place cost `repin` while renaming it restored a full `pin`,
which teaches the attack. While a guard is armed
the pointer, not the argument list, decides which brief a verdict is about — `--base`
chooses the revision, `--deactivate` is the way out, and both are on the record.

The history is the weak one, and deliberately never refuses. A brief cannot honestly
name, as the commit it started from, a commit whose tree already carried a *different*
base — unless the brief is a reusable slot at a stable path, and then a second honest
task re-stamps that field exactly as tampering would. Nothing in git separates those, so
it raises a REVIEW and leaves the judgment to a reader. An absent `base_rev` in that copy
is not agreement either: a brief committed without one says nothing about where any work
started.

None of this is universal. `.prompire/` is gitignored in the documented layout, so
the history is usually absent, and the digest and pin only exist once somebody arms the
guard. **Unarmed, `check_scope.py` is advisory**: it says so on its summary line and
raises a REVIEW rather than presenting the base as checked, and `--strict` — the
reviewer-facing invocation — turns that flag into a non-zero exit. Every record is a
file, so a shell command still overwrites it; what they buy is that evasion stops being
a silent one-line edit and becomes an act with a name.

## B3 — the vague-term list

Bare substring matching once flagged "report CLI" as a port and "modernize-py" as vague,
so the list is matched on word boundaries with a tail rule per pattern. A vague word in
`goal` or `expect` is an error, because those are the things being checked; in
`constraints` or `notes` it is a warning, because there it is commentary.
