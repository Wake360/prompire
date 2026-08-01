# Maintaining this skill

Nothing here is needed to *use* the skill. It is for changing it.

## Layout

```
SKILL.md              when to use it, the workflow, the shape, the hard rules
prompire.py           CLI: prepare, verify, and close
brief_common.py       schema helpers every tool shares: loading, keys, transitions, globs
lint_brief.py         is the brief shippable
baseline.py           measure each criterion on untouched HEAD
check_scope.py        did the agent stay inside the boundary (run after the agent)
render_brief.py       prompt and checklist targets
verify_acceptance.py  run the declared acceptance criteria
pyproject.toml        package metadata and the `prompire` command
hook_policy.py        the host-neutral hook core: which paths, which roots, which verdict
hook_scope_guard.py   Claude Code PreToolUse adapter — stderr + exit 2
hook_copilot_guard.py GitHub Copilot CLI preToolUse adapter — stdout JSON decision
hook_antigravity_guard.py  Antigravity CLI PreToolUse adapter — stdout JSON decision
references/
  schema.md           the authoritative field list — one definition per field
  rules.md            what each rule catches, and what it cannot
  rendering.md        target-by-target output rules
  hosts.md            Claude Code and Copilot CLI: install, hooks, failure semantics
  grounding.md        the book passage behind each rule
  maintaining.md      this file
examples/             five briefs; baselines measured, not written
  hooks/              hook configurations per hook host; tests/docs.py parses each one
tests/
  battery.py          adversarial YAML cases: which rule ids fire, as errors or warnings
  e2e.py              real git repos, real commands, real diffs
  examples.py         regenerates and verifies examples/
  golden.py           renderer snapshots + the wording rules
  hook.py             every hook adapter, as subprocesses, on throwaway repos
  verify.py           acceptance verifier integration cases
  cli.py              prepare, verify, and close integration cases
  runner.py           suite timeout, continuation, and timing output
  package.py          installed CLI packaging checks
  fixtures.py         builds the throwaway repo the last three measure against
  docs.py             the docs and the code still agree
  run_all.py          all of the above
```

## Run everything

```
python3 tests/run_all.py
```

Exit 0 = every suite passes. Individually:

```
python3 tests/battery.py       adversarial linter cases
python3 tests/e2e.py           end-to-end workflows and attacks (builds temp git repos)
python3 tests/examples.py      examples lint clean and reproduce their baselines
python3 tests/golden.py        renderer snapshots
python3 tests/hook.py          the hook adapters: blocked vs allowed vs neutral
python3 tests/encoding.py      every tool's stdout is utf-8 under a cp1252 console
python3 tests/verify.py        acceptance verifier integration cases
python3 tests/cli.py           prepare, verify, and close integration cases
python3 tests/runner.py        run-all timeout and duration reporting
python3 tests/package.py       installed CLI packaging checks
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

`tests/hook.py` asserts the adapters agree (`cp-both-hosts-read-one-boundary`,
`agy-three-hosts-read-one-boundary`): for
the same repo and the same path, Claude Code's exit code and Copilot's decision must
match. If a change makes that case fail, the change put a second opinion somewhere.

The hosts fail in different directions and the adapters are not interchangeable:
Claude Code and Antigravity CLI let a call through on a crash, Copilot CLI denies on
one. `hook_copilot_guard.py` therefore never exits non-zero, and neither JSON-speaking
adapter ever emits its host's allow decision — an allow would skip a permission flow
this guard has no standing to skip. All of it is pinned in `tests/hook.py`; none of it
is a style choice. The full matrix is in `references/hosts.md`.

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

## The copies

**The git repository is canonical.** Work happens there and the history lives there.
Everything else is downstream and is overwritten by a sync, so a change made anywhere
else is a change waiting to be deleted.

```
<repo>                              canonical — edit here, commit here
~/.claude/skills/prompire/          installed skill, Claude Code
~/.copilot/skills/prompire/         installed skill, GitHub Copilot CLI
~/.gemini/config/skills/prompire/   installed skill, Antigravity CLI
~/LifeOS/scripts/prompire/          older mirror, from before the repo existed
```

This inverted once already. The canonical copy used to be `~/.claude/skills/prompire/`,
with the LifeOS mirror existing purely to give the skill a git history — a job the
repository now does. Both installs and the mirror are downstream of the repo today, and
a sync run in the old direction would overwrite the repository with a stale install.
Check which way you are pointing before running any of these.

Push the repo out to every install after a change lands:

```
rsync -a --delete <repo>/ ~/.claude/skills/prompire/ \
  --exclude __pycache__ --exclude .git --exclude .github --exclude .gitignore \
  --exclude CLAUDE.md --exclude .prompire --exclude .agent-brief
rsync -a --delete <repo>/ ~/.copilot/skills/prompire/ \
  --exclude __pycache__ --exclude .git --exclude .github --exclude .gitignore \
  --exclude CLAUDE.md --exclude .prompire --exclude .agent-brief
rsync -a --delete <repo>/ ~/.gemini/config/skills/prompire/ \
  --exclude __pycache__ --exclude .git --exclude .github --exclude .gitignore \
  --exclude CLAUDE.md --exclude .prompire --exclude .agent-brief
```

Then confirm each matches:

```
diff -r <repo> ~/.claude/skills/prompire \
  -x __pycache__ -x .git -x .github -x .gitignore -x CLAUDE.md
```

Four of those excludes are the repository's own scaffolding, which an installed skill has
no use for: `.git`, `.github`, `.gitignore`, `CLAUDE.md`.

**`--exclude .prompire` and `--exclude .agent-brief` are not tidiness.** `--delete` would
otherwise remove whatever state a destination is carrying — briefs, and in the worst case
an `ACTIVE.tombstones` recording that a guard was once disarmed. A disarm log a sync can
erase is not a log, and `any_disarm()` reads both directory names. The LifeOS mirror is
carrying seven dogfood briefs under `.prompire/` right now; without these two excludes the
command above deletes them.

After syncing, run the suite from the destination, not only from the repo — that is what
proves the install is complete rather than merely recent:

```
python3 ~/.claude/skills/prompire/tests/run_all.py
```

`tests/ci.py` prints `skipped` there — the GitHub Action ships with the repository,
never with an install. Every other suite must actually pass.

Never edit an install or the mirror directly. The next sync deletes the change, silently.
