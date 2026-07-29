---
name: prompire
description: Use when delegating substantial coding work, recovering from an agent run that drifted or gamed its checks, or writing a checkable agent brief.
---

# Prompire

Compile a one-line request into the smallest brief that can be *checked*. The output is
short. If it grew long, it failed.

## Primary workflow

### Prepare

After writing `.prompire/<slug>.yaml`, prepare the handoff:

```bash
prompire prepare .prompire/<slug>.yaml --target generic
```

### Hand off — Prompire does not launch the agent

Hand the generated prompt to any coding agent.

### Verify scope and acceptance

After the agent stops, run the combined verdict:

```bash
prompire verify .prompire/<slug>.yaml
```

Review the generated checklist.

### Close explicitly

Close the guard after review:

```bash
prompire close .prompire/<slug>.yaml
```

## Diagnostic commands

### Combined verdict

The CLI runs the measured baseline, lint, generic rendering, guard activation, strict
scope check, acceptance verification, and deactivation. Use `prompire verify` for the
combined scope and acceptance verdict.

### Individual tools

The scripts below are individual diagnostic commands for inspecting one stage; they
are not a second handoff workflow.

`$PROMPIRE` below is this directory — wherever this skill is installed, which differs
per host and per personal/repository install (`references/hosts.md` lists them).
Substitute it; do not assume one host's path.

| | |
|---|---|
| `lint_brief.py brief.yaml` | is the brief shippable? |
| `baseline.py brief.yaml` | what does each criterion say on untouched HEAD? |
| `check_scope.py brief.yaml --activate` | arm the guard (run *before* the agent starts) |
| `check_scope.py brief.yaml` | did the agent stay inside the boundary? (run after) |
| `render_brief.py brief.yaml --target X` | the prompt and the checklist |

## When not to use this

One-file edits, a bug you can describe in a sentence, anything you'd finish faster than
the brief. This is for work you're delegating and won't watch.

## Diagnostic internals

1. **Read the request. Do not interview.** Infer everything you can from the repo — test
   command, package manager, layout, conventions. Ask at most **two** questions, only
   for a field you cannot infer and cannot default. The one usually worth asking: *what
   command tells us this worked?*

2. **Write the brief** to `.prompire/<slug>.yaml` (repo-local, gitignored). Every
   field is inferred, answered, or absent — never invented. Especially never invent an
   acceptance command. If you cannot name one, write `acceptance: []`, let the lint
   fail, and say the brief is not ready and why.

3. **Measure the baseline:**
   ```
   python3 $PROMPIRE/baseline.py .prompire/<slug>.yaml --write
   ```
   It runs each command on HEAD, refuses the ones that are destructive, interactive,
   repo-writing or environment-dependent, and appends the `baseline:` block **and the
   `base_rev` the next two steps both need** — always use `--write`, since a block pasted
   by hand is a block that can be typed rather than measured, and one without `base_rev`
   fails `B16` at the next step anyway. Drop `--write` only to preview.
   Never write a status it did not produce. A criterion that is red today needs
   `transition: flip` (turning it green is the goal) or `transition: hold` (it is
   known-red and must stay exactly as measured). An undeclared red criterion is the
   failure this step exists to catch: the agent can never satisfy it, and afterwards
   nobody can tell breakage from pre-existing rot.

4. **Lint it:**
   ```
   python3 $PROMPIRE/lint_brief.py .prompire/<slug>.yaml
   ```
   Exit 0 = shippable. Fix errors and re-run. Warnings are judgment calls — resolve them
   or say out loud why you're accepting them. Never edit the linter to make a brief pass.

5. **Render** for the target the user named (`claude`, `codex`, `copilot`, `agents.md`,
   `claude.md`, `checklist`; default: `generic,checklist`).

6. **Arm the guard — before the agent starts, not after:**
   ```
   python3 $PROMPIRE/check_scope.py .prompire/<slug>.yaml --activate
   ```
   This is the step that makes the verdict worth anything, and it is the one that is easy
   to skip because nothing fails without it. It copies the brief's `base_rev` and a
   sha256 of the whole file into `.prompire/ACTIVE`, outside the brief the agent can
   edit. While that pointer stands, changing any byte of the brief — a wider `scope`, one
   more `dirty_baseline` entry, a `base_rev` re-stamped at a commit that already contains
   the work — makes `check_scope.py` produce **no verdict at all** instead of a
   favourable one. Skip it and the brief is the only record of where the work started,
   which means one Write buys a clean run. The primary lifecycle uses `prompire close`.
   Direct `--deactivate` is for diagnosing cleanup; it leaves a tombstone on purpose.

7. **Hand over both artifacts**: the prompt for the agent, and the checklist for the
   human. After the agent stops, run `prompire verify` for the combined strict scope and
   acceptance verdict. When diagnosing the scope stage directly, the checklist's first
   line — `check_scope.py` — catches an out-of-scope edit or a weakened test, and it has
   to be run by the reviewer, not by the agent. Reviewers use `--strict`, which turns
   review flags into exit 1 — including an uncorroborated base, so a run nobody armed
   fails the check rather than merely annotating it. If `--strict` is red only on a
   `repin` finding, that means a guard was disarmed somewhere in this repo's past — read
   `.prompire/ACTIVE.tombstones`, and if you accept it, re-run with the
   `--ack-disarms <digest>` the finding printed. It does not go away on its own, and a
   fresh disarm invalidates the acknowledgement again.

## Reading the verdict

Every run prints how the base was established, and that label is most of what the
verdict is worth:

- **`pin`** — the guard was armed on this brief at this base and has not been disarmed
  since. This is the only label that is trust. Even it says no more than it says: arming
  after the work is already committed yields a `pin` that vouches for the brief, not for
  where the work started.
- **`repin`** — the pointer was written after a `--deactivate`. Any disarm anywhere in
  the repo makes every later arm a `repin`, so on its own it corroborates nothing. Read
  `.prompire/ACTIVE.tombstones` against the current pin, and `git diff` between the
  two bases, to see what the re-arm moved past. A non-empty tombstone file means read the
  transcript. `--ack-disarms <digest>` (matching a prefix of the tombstone log's sha256,
  printed by the finding itself) stops this finding alone from failing `--strict` — it
  stays labelled `repin`, still prints, and a later `--deactivate` invalidates the
  acknowledgement by changing the digest.
- **`base uncorroborated`** — nobody armed the guard, so the only record of where the
  work started is the field the agent could edit. `--strict` fails on this.
- **`--base`** — a human chose the comparison on the command line.

## The shape

Mandatory: `goal`, `scope`, `acceptance`, `autonomy`. `baseline` is a warning when
absent and an error when wrong — mandatory in practice, since step 3 produces it.
Everything else earns its place. Field-by-field semantics, including every edge case:
**`references/schema.md`**.

```yaml
goal: <one imperative sentence, max 30 words>
scope: [<paths the agent may edit — never `.`>]
forbidden: [<paths that are off limits; `[]` means you considered it and nothing is>]
constraints: [<what must stay true; observable, not adjectival>]
tests_policy: immutable   # immutable | named | authoring
acceptance:               # the toolchain is the judge — cmd + expect, always
  - cmd: <the command you would actually run>
    expect: <exit 0 | exit 1 | empty output | …>
    transition: green     # green (default) | flip (red→green) | hold (freeze as measured)
    cwd: <subdirectory, for a monorepo>
    before_after: true    # its output must reproduce the baseline digest
baseline:                 # written by baseline.py, never by hand
  - cmd: <same cmd, same cwd>
    status: pass          # pass | fail | not_runnable — did it meet its own `expect`?
    evidence: <exit code and the number that mattered>
autonomy: ask             # manual = propose only | ask = confirm risky steps | auto
plan_first: true
rollback: <branch or worktree — required for autonomy: auto>
manual_checks: [<what only a human can confirm>]
```

A lint-clean brief in this exact shape, with baselines that were measured rather than
written, is `examples/worked-example.yaml`. Four more in `examples/` show one shape
each: a green criterion, one that must flip, one that must hold, one that cannot run
until the code exists.

## Hard rules

- **Never invent an acceptance criterion** to make the brief look complete. A missing
  criterion is the finding.
- **Never write a `baseline` status you did not measure.** A guessed `pass` is worse
  than no baseline at all: it converts an unreachable criterion into a signed-off one.
- **Never widen `scope` because it would be convenient**, and never render wording that
  lets an agent widen it by asking. A scope change is an edit to the brief.
- **Never edit `lint_brief.py` to silence a finding on a real brief.** Fix the brief, or
  argue the rule down against `references/grounding.md` and delete it deliberately.
- **Never revise an armed brief in place.** `--deactivate`, edit, re-measure the
  baseline, `--activate`. The refusal you get for editing an armed brief is the feature,
  not an obstacle to route around, and the re-arm is recorded as a `repin` so the
  revision is visible instead of silent.
- **The rendered prompt stays short** (~250 words, enforced). Long professional-looking
  prompts that don't improve outcomes are the failure mode this skill exists to avoid.

## The rules

Sixteen rules, ids `B1`–`B16`, each traced to a book passage. Four carry the weight:

- **B4** — no acceptance block, no brief. Refusing to emit one is the most valuable
  thing this skill does.
- **B15** — every criterion carries what it said *before* the work. A score without its
  baseline is not a result.
- **B7** — a green suite only means something if the suite could not be edited into
  being green. `tests_policy` says which of the three arrangements applies, and
  `check_scope.py` enforces it against the real diff. This is the one that earns the
  skill; everything else is hygiene.
- **B16** — a brief must name the commit its work started from, and it has to be a
  commit. Without it an agent that commits its own work hands the checker a base that
  already contains it, and an empty diff reads as a compliant one.

Full table with what each rule can and cannot catch: **`references/rules.md`**.
Where each one comes from: **`references/grounding.md`**.
Renderer targets and wording rules: **`references/rendering.md`**.
Tests, and how to change a rule safely: **`references/maintaining.md`**.
Running on Claude Code and GitHub Copilot CLI: **`references/hosts.md`**.
