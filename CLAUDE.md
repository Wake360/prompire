# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Prompire is a Claude Code *skill* (`SKILL.md` + five Python 3 scripts + a PreToolUse
hook). It compiles a request into a YAML brief that can be checked — bounded `scope`,
executable acceptance criteria, a baseline measured before the work — and then checks the
real git diff afterwards. Only dependency is PyYAML. No service, no network, no key.

Read `SKILL.md` for the workflow and the brief shape, `README.md` for the summary and
`references/threat-model.md` for the full threat model and stated limitations, and
`references/maintaining.md` before changing anything. Those are the spec; this file only
says how to work in the tree.

## Commands

```bash
python3 tests/run_all.py            # every suite; exit 0 only if all pass
python3 tests/battery.py            # adversarial linter cases (which rule ids fire)
python3 tests/e2e.py                # real temp git repos, real commands, real diffs
python3 tests/e2e.py --verbose      # keeps the temp repos so a failing diff is readable
python3 tests/examples.py           # examples/ lint clean and reproduce their baselines
python3 tests/golden.py             # renderer snapshots + wording rules
python3 tests/hook.py               # PreToolUse guard: blocked (exit 2) vs allowed (exit 0)
python3 tests/encoding.py           # every tool's stdout is utf-8 under a cp1252 console
python3 tests/docs.py               # rule ids, schema keys and prose still agree
```

There is no per-case filter — run the suite. Snapshot regeneration is deliberate and
must be diff-read, never rubber-stamped:

```bash
python3 tests/golden.py --regenerate     # then read the diff
python3 tests/examples.py --regenerate   # re-measures examples against tests/fixtures.py
```

CI (`.github/workflows/tests.yml`) runs `python tests/run_all.py` on Python 3.11 and 3.13.

## Architecture

`brief_common.py` is the schema layer every tool imports: key sets (`TOP_KEYS`,
`ACCEPTANCE_KEYS`, `BASELINE_KEYS`), enums (`AUTONOMY`, `TRANSITIONS`,
`TESTS_POLICIES`), path globbing (`glob_re`, `norm_path`, `is_test_path`), case-folding
probes (`fs_fold`), and the two verdict functions — `boundary_verdict` and
`tests_verdict` — that decide whether one path is inside the brief. Both `check_scope.py`
and `hook_scope_guard.py` call those same two functions, so the hook and the checker
cannot disagree about what the boundary means. Change a boundary rule here, not in a
caller.

Four tools sit on top: `lint_brief.py` (rules `B1`–`B16`, exit 0/1/2),
`baseline.py` (runs each acceptance command on untouched HEAD, refuses destructive /
interactive / repo-writing / networky ones, writes the `baseline:` block *and*
`base_rev`), `render_brief.py` (targets `claude`, `generic`, `codex`, `agents.md`,
`claude.md`, `checklist`; prompts are capped at `WORD_BUDGET = 250`), and
`check_scope.py` (the post-hoc authority).

The enforcement is two layers on purpose. `hook_scope_guard.py` is a PreToolUse hook
watching `Write|Edit|MultiEdit|NotebookEdit` — early, cheap, and evadable, since it does
not see `Bash`. It **fails open on its own trouble** (missing repo, unreadable brief,
parse error, unexpected exception) because it runs on every write on the machine; every
degradation must be toward not enforcing, and it fails closed only on a definite verdict.
Preserve that property in any change to it. `check_scope.py` reads the real git diff
afterwards and needs no cooperation from the agent — that is where a real guarantee can
live.

The trust story is the pin. `--activate` writes `base_rev` plus a sha256 of the whole
brief into `.prompire/ACTIVE`, outside the brief; while it stands, any byte changed in
the brief yields *no verdict* (exit 2) rather than a favourable one. `--deactivate`
leaves a tombstone in `.prompire/ACTIVE.tombstones`, and any disarm anywhere in the repo
makes every later arm a `repin` forever — `--strict --ack-disarms <digest>` is the
reviewer's escape hatch, valid only for the log exactly as it stands. `BASE_SOURCE` in
`check_scope.py` enumerates every label a run can print (`pin`, `repin`, `--base`, and
the `None` case rendered as `base uncorroborated`); `tests/docs.py` fails if `SKILL.md`
stops explaining one of them. The hook also refuses writes to `ACTIVE` and
`ACTIVE.tombstones` at any depth or spelling — that check is unconditional and does not
depend on a brief being armed.

Exit codes are load-bearing everywhere: 0 clean, 1 finding, 2 could-not-decide. A tool
that cannot establish a base never falls back to HEAD.

## Working rules

Adversarial case first, in `tests/battery.py` (linter opinion) or `tests/e2e.py`
(behaviour), then the code. The battery only proves the linter's opinion of a string;
anything touching enforcement needs an e2e case.

Every enforced rule traces to a passage in `references/grounding.md`, and `tests/docs.py`
fails if a rule id in `lint_brief.py` has no entry. If a rule cannot be traced, delete it
deliberately — do not soften it. Never edit `lint_brief.py` to make a real brief pass;
that inverts the tool.

Don't add schema fields unless a fixture fails without one. Order if you must:
`brief_common.py` key sets, `references/schema.md`, linter, battery case, renderer.

Prose and code are tested against each other. Editing `SKILL.md`, `references/rules.md`
or `references/schema.md` without the other can turn `tests/docs.py` red, and so can
editing the code.

## Copies of this tree

`~/.claude/skills/prompire/` is the installed skill and `~/LifeOS/scripts/prompire/` is
the rsync mirror described in `references/maintaining.md`. This repository is the
published copy of the same tree (it adds `.github/` and `.gitignore`). Edits here do not
reach the installed skill or the mirror — sync deliberately, and never edit the mirror
directly.
