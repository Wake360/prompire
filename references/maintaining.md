# Maintaining this skill

Nothing here is needed to *use* the skill. It is for changing it.

## Layout

```
SKILL.md              when to use it, the workflow, the shape, the hard rules
brief_common.py       schema helpers every tool shares: loading, keys, transitions, globs
lint_brief.py         is the brief shippable
baseline.py           measure each criterion on untouched HEAD
check_scope.py        did the agent stay inside the boundary (run after the agent)
render_brief.py       prompt and checklist targets
hook_policy.py        the host-neutral hook core: which paths, which roots, which verdict
hook_scope_guard.py   Claude Code PreToolUse adapter — stderr + exit 2
hook_copilot_guard.py GitHub Copilot CLI preToolUse adapter — stdout JSON decision
references/
  schema.md           the authoritative field list — one definition per field
  rules.md            what each rule catches, and what it cannot
  rendering.md        target-by-target output rules
  hosts.md            Claude Code and Copilot CLI: install, hooks, failure semantics
  grounding.md        the book passage behind each rule
  maintaining.md      this file
examples/             five briefs; baselines measured, not written
  hooks/              hook configurations for both hosts; tests/docs.py parses each one
tests/
  battery.py          adversarial YAML cases: which rule ids fire, as errors or warnings
  e2e.py              real git repos, real commands, real diffs
  examples.py         regenerates and verifies examples/
  golden.py           renderer snapshots + the wording rules
  hook.py             both hook adapters, as subprocesses, on throwaway repos
  fixtures.py         builds the throwaway repo the last three measure against
  docs.py             the docs and the code still agree
  run_all.py          all of the above
```

## Run everything

```
python3 ~/.claude/skills/prompire/tests/run_all.py
```

Exit 0 = every suite passes. Individually:

```
python3 tests/battery.py       adversarial linter cases
python3 tests/e2e.py           end-to-end workflows and attacks (builds temp git repos)
python3 tests/examples.py      examples lint clean and reproduce their baselines
python3 tests/golden.py        renderer snapshots
python3 tests/hook.py          both hook adapters: blocked vs allowed vs neutral
python3 tests/docs.py          rule ids, schema keys and docs are consistent
```

`tests/e2e.py --verbose` keeps the temp repos so you can look at a failing diff.

## Changing the hook

The boundary lives in `brief_common.py` and the walk lives in `hook_policy.py`. An
adapter knows its host's wire format and nothing else — the moment one of them decides
what a path *means*, there are two interpretations of `scope` in the tree and they will
diverge. So:

1. A boundary rule changes in `brief_common.py`, never in an adapter. Both hooks and
   `check_scope.py` pick it up together, which is the point.
2. Which paths a tool call touches, which roots govern, and how a path is resolved
   change in `hook_policy.py`. Both hosts pick it up together.
3. Only payload parsing and the shape of the answer belong in an adapter.

`tests/hook.py` asserts the two adapters agree (`cp-both-hosts-read-one-boundary`): for
the same repo and the same path, Claude Code's exit code and Copilot's decision must
match. If a change makes that case fail, the change put a second opinion somewhere.

The two hosts fail in opposite directions and the adapters are not interchangeable:
Claude Code lets a call through on a crash, Copilot CLI denies on one. `hook_copilot_
guard.py` therefore never exits non-zero and never emits `permissionDecision: "allow"`.
Both properties are pinned in `tests/hook.py`; neither is a style choice. The full
matrix is in `references/hosts.md`.

## Changing a rule

1. Read `grounding.md` first. Every enforced rule traces to a passage there;
   `tests/docs.py` fails if a rule id in `lint_brief.py` has no entry. If you cannot
   trace a rule, delete it — do not soften it.
2. Never edit the linter to make a real brief pass. That inverts the tool.
3. Add the adversarial case to `tests/battery.py` *before* the code, with the rule ids
   that must fire as errors, as warnings, and not at all. The cases exist because bare
   substring matching once flagged "report CLI" as a port and "modernize-py" as vague.
4. If the change touches behaviour rather than wording, add an `tests/e2e.py` case: the
   battery only proves the linter's opinion of a string.
5. Re-run everything. Regenerate snapshots deliberately:
   `python3 tests/golden.py --regenerate`, then read the diff — a renderer change that
   quietly authorises an out-of-scope write looks like a formatting tweak in a diff stat.
6. If the fixture repo changes, `python3 tests/examples.py --regenerate` re-measures the
   examples. Their `base_rev` is stable because `tests/fixtures.py` pins the commit
   dates; the durations in `evidence` will drift, which is expected.

## Adding a schema field

Don't, unless a fixture fails without it. If you must: `brief_common.py` key sets first,
then `references/schema.md`, then the linter, then a battery case, then the renderer.
Fields that exist "in case someone needs it" are how the brief grows long, which is the
failure mode the whole skill is arranged against.

## The brief-path REVIEW in check_scope.py

`check()` flags the brief's own path with a REVIEW when it changed (M/R) or was deleted
(D) since `base` — a brief nobody has re-read is a brief the acceptance block can't be
trusted against. That branch runs *before* the `dirty_baseline`/`ALWAYS_ALLOWED` skip on
purpose: a brief listed in its own `dirty_baseline` and then edited still draws the
REVIEW. That's deliberate, not an oversight — `dirty_baseline` exists to excuse
pre-existing dirt in *other* files, not to let a brief exempt its own edits from being
noticed. Only visible when the brief is tracked; a brief under a gitignored
`.prompire/` never shows up in the diff at all, which is why the PreToolUse hook
(Task 9) has to protect it directly instead.

The `D` half of that branch has **no caller today**, and the code says so rather than
implying one. `main()` loads the brief from the same path it later diffs, so a deleted
brief exits 2 before `check()` runs, and the hook never calls `check()` at all. Making
`main()` reach it would mean reading the brief back with `git show <base>:<brief>` — and
a brief that is not on disk has no digest, so `armed_verdict`'s digest refusal and
`main()`'s own before/after digest comparison both go quiet. That is a hole traded for a
coverage gap, so the branch stays reachable only from a caller that already holds a
parsed brief, pinned by `tests/e2e.py`'s `brief-deleted-after-the-baseline`.

## The mirror

The canonical copy is `~/.claude/skills/prompire/`. `~/LifeOS/scripts/prompire/`
is a git-tracked mirror so the skill has a history. After editing the canonical copy:

```
rsync -a --delete ~/.claude/skills/prompire/ ~/LifeOS/scripts/prompire/ \
  --exclude __pycache__
```

Then confirm they match:

```
diff -r ~/.claude/skills/prompire ~/LifeOS/scripts/prompire -x __pycache__
```

Never edit the mirror directly — the next rsync deletes the change.
