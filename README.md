# Prompire

A verifiable contract for work you delegate to a coding agent.

Before the work starts, the request is compiled into a brief that can be *checked*: a
bounded `scope`, a `forbidden` list, acceptance criteria that are commands rather than
adjectives, a baseline measured on the untouched repo, and a `tests_policy` saying
which test files may move. The base commit is pinned outside the brief. After the agent
stops, Prompire reads the real git diff — not the agent's report — and says whether the
work stayed inside what was declared and whether the acceptance commands now pass. The
verdict needs no cooperation from the agent.

The problem it addresses is delegation without verification: work handed to an
agent drifts, and "done" arrives as a claim rather than a measurement. In
Prompire's own committed benchmark, 9 of 20 runs given the goal sentence alone
changed a test file — caught from the git diff, not from anything the agent
reported — while 0 of 160 runs that carried some part of a brief left the
scope the author's brief declared. The design also takes a sharper threat
seriously: an agent graded on a suite it can edit, or on a diff whose starting
point it gets to declare, holds its own grading surface. Prompire pins both
before the work starts. That threat is why the pin exists; no run in any
benchmark arm changed the brief or the pin.

```bash
prompire prepare .prompire/task.yaml --target generic
prompire verify .prompire/task.yaml
prompire close .prompire/task.yaml
```

Python 3 and PyYAML. Nothing else — no service, no key, no network. The underlying
scripts remain documented under [Diagnostic commands](#diagnostic-commands).

A sandbox bounds where an agent can technically reach. Prompire bounds what one task
allowed it to change, and defines how done is recognized. The two compose; neither
replaces the other.

## What a catch looks like

`prompire demo` builds a throwaway repo and walks the workflow above through a clean run
and a caught violation. This is one real run (invoked in this checkout as
`python3 prompire.py demo`):

```
demo repo: /private/var/folders/45/h3sq302j7z71ff4vs24zlz1c0000gn/T/prompire-demo-46zql2iy
     greeting.py — the one file the brief lets the agent touch
     check.py — its test, run as `python3 check.py`
the brief the agent is held to:
     goal: Change the greeting word in greeting.py.
     scope:
       - greeting.py
     autonomy: ask
     acceptance:
       - cmd: python3 check.py
         expect: exit 0
     manual_checks:
       - greeting.py no longer says hello
1. prepare: measure the acceptance command on untouched HEAD, lint the brief,
   render the prompt, pin the base commit.
     armed: prompt and checklist rendered, base commit pinned
2. the agent does what it was asked: greeting.py now says "ahoj".
     scope: 0 violation(s) against base b842a4a455bc
     acceptance: python3 check.py — pass
     clean (exit 0)
3. the same agent drifts and also writes secrets.cfg, which the brief
   never allowed.
     violation: secrets.cfg — changed outside `scope`
     scope: 1 violation(s) against base b842a4a455bc
     acceptance: not run — strict scope preflight did not pass
     caught (exit 1)
the violation above was read out of the real git diff against the pinned base —
the agent was never asked, so nothing it could claim would hide the extra file.
```

The verdict in step 3 comes from the real git diff against the pinned base. It needs no
cooperation from the agent — nothing it could claim would hide the extra file.

## Measured, not asserted

The prompts and the checks are benchmarked, not assumed. Task briefs run through live
agents in throwaway repos and are scored from outside by the same `verify_acceptance` +
`check_scope` pair a human would run; nothing the agent prints is trusted. The
campaigns are pre-registered and their raw rows are committed under `bench/campaigns/`.

Drift is the measured failure mode. Across the committed campaigns, 20 runs
were handed the goal sentence alone — no brief — and 9 of 20 changed a test
file; scored from outside against the author's brief, the checker caught all
nine. 0 of 160 runs that carried some part of a brief left the scope the
author's brief declared. No run in any arm, briefed or bare, tampered with
the brief or the pin — a bound on what was observed, not proof of what agents
do; manipulation of the grading surface is the threat the pinned contract
exists to make evident.

The first cross-agent matrix (2026-08-01): six tasks, five repetitions each, on
Claude Code, Codex CLI and Antigravity CLI. None of the 90 runs left its
declared scope, changed a test file, or touched the brief or the pin.
Acceptance differed by host — claude and codex 30/30, antigravity 23/30 — so
the honest claim is that the work is equally *checked* everywhere, not equally
*good* everywhere. Design and reading rules: `references/benchmark.md`; raw
rows: `bench/campaigns/`.

## Install the CLI

```bash
pipx install prompire
# or
uv tool install prompire
```

Prompire supports Python 3.11+ on macOS, Linux, and Windows. The package:
https://pypi.org/project/prompire/.

## Primary workflow

This workflow is host-neutral and works with any coding agent.

Optional step 0: `prompire draft "one sentence"` writes a draft brief to
`.prompire/task.yaml`. The heuristic is deterministic, not a model — it proposes an
acceptance command only where the repo evidences one (`package.json` `scripts.test`, a
pytest config, a `Makefile` `test:` target, `Cargo.toml`, `go.mod`), and states the
absence rather than inventing a command. `--agent claude`, `--agent codex`, `--agent
antigravity` — or any CLI via `--agent-cmd`, drafting prompt on stdin, brief on
stdout — delegates the drafting to a host model that can read the repo. `--proposal <file|->`
takes an already-written YAML proposal instead of invoking a model — any host or skill
can compile through it. Every model-assisted route flows through the same gate: the
reply is parsed as data and re-serialized, the model's own comments are dropped,
`baseline` and `base_rev` are refused as measured rather than drafted, and the
boundary, every acceptance command, any relaxed `tests_policy`, the deny-list, the
constraints, the manual checks and any `context` come back marked
`# prompire:unconfirmed` — and listed in an `unconfirmed:` block, which is the record
that survives a YAML round-trip when the comments do not — however confident the model
sounded. Agent-assisted drafting
runs in a disposable repository containing the checkout's current tracked and untracked,
non-ignored files. Drafting is read-only: a run that writes to that snapshot is refused,
the written paths are named, and no draft is produced — the writes are discarded with
the snapshot. A symlink is carried
only when its target resolves inside the repository, re-aimed there at the snapshot's own
copy, so a path the agent addresses relative to its workspace cannot reach the source
checkout through one. Ignored files, submodules and nested checkouts are not copied. This
isolates ordinary repository writes; it does not sandbox network, credentials, or an
absolute path the agent composes for itself elsewhere on the machine. Read every
`# prompire:unconfirmed` line, fix it, delete the marker, then delete the
`unconfirmed:` block: `prompire prepare`, `lint` and arming all refuse while either
record remains.
Under Claude Code, Copilot CLI, Codex CLI or Antigravity CLI the host model fills this
step instead, following `SKILL.md` — writing a proposal and feeding it through the same
`--proposal` gate.

### Prepare

```bash
prompire prepare .prompire/task.yaml --target generic
```

This measures the baseline, lints the brief, renders the prompt, and arms the guard —
from here on, editing the brief yields no verdict rather than a favourable one.

`prepare` runs your acceptance commands on the untouched repo to measure the
baseline. It does not exempt what they generate: an interpreter cache or build
directory not covered by `.gitignore` is ordinary git evidence and will surface
in the verdict. Ignore such paths before preparing.

### Hand off — Prompire does not launch the agent

Give `.prompire/task.generic.md` to the coding agent.

### Verify scope and acceptance

After the agent stops:

```bash
prompire verify .prompire/task.yaml
```

Review `.prompire/task.checklist.md`.

### Close explicitly

After review:

```bash
prompire close .prompire/task.yaml
```

Claude Code and Copilot CLI hooks are optional early-warning adapters; the final
git-diff check is host-neutral.

## The second task in the same repository

One brief file per task — `prepare` refuses to overwrite a measured
`baseline:` block, and the Action expects one brief per pull request. `close`
disarms the guard and records the disarm in `.prompire/ACTIVE.tombstones`;
from then on, every later arm in that repository is a `repin`, and `verify`
flags it while still gathering the evidence:

    review: 1 flag — needs a human
    REVIEW    .prompire/task2.yaml: `base_rev: …` is pinned in .prompire/ACTIVE,
              but that pin was written after a `--deactivate` …
    acceptance: PASS python3 check.py
    acknowledge with: prompire verify .prompire/task2.yaml --ack-disarms 917b94f2

The flag is not an error. A disarm is the one event that could launder a
rewritten brief, so the record never clears itself; what you acknowledge is
that you read the tombstone log and accept what it says. Re-run with the
printed `--ack-disarms` digest and the verdict is `clean` — and the next
disarm changes the digest, so an acknowledgement never carries forward.

## What a verify verdict means

Every `prompire verify` run leads with one line:

- `clean` — exit 0. Nothing outside the boundary changed, no flag is open
  that you have not acknowledged, and the acceptance commands pass.
- `caught: N violation(s)` — exit 1. Something changed outside the declared
  scope. Acceptance is not run on a violated boundary.
- `caught: acceptance did not pass` — exit 1. The boundary held but an
  acceptance command did not meet its expectation.
- `review: N flag(s) — needs a human` — exit 1. Nothing was violated, but a
  finding no checker can settle (a `named`/`authoring` tests policy, a re-armed
  guard) is waiting on your judgment. When the base is corroborated and every
  open flag is one the checker recognizes as evidence-only, the acceptance
  evidence is still gathered and printed beside the flag.
- `no verdict: <reason>` — exit 2. The run could not produce a trustworthy
  result — an armed brief was edited, a base is missing — and the output names
  the next command where one exists.

`prompire verify --json` emits the raw structured result instead; its shape is
unchanged from 0.9.1.

## Where briefs live

State files and rendered artifacts — `ACTIVE`, `ACTIVE.tombstones`, the prompt,
the checklist — are never history: keep them ignored. The briefs themselves
depend on how you verify:

```
.prompire/*
!.prompire/*.yaml
```

Working locally, briefs may stay untracked — drop the `!` line and ignore the
whole directory. With the GitHub Action, the brief is the contract CI checks
the pull request against, so it must be committed: the two lines above, one
brief per pull request (`references/ci.md`).

## Diagnostic commands

### Combined verdict

Use `prompire verify` for the combined scope and acceptance verdict. The commands below
diagnose individual stages; they are not an alternative handoff workflow.

### Individual tools

```bash
python3 baseline.py .prompire/task.yaml --write
python3 lint_brief.py .prompire/task.yaml
python3 render_brief.py .prompire/task.yaml --target generic
python3 check_scope.py .prompire/task.yaml --activate
python3 check_scope.py .prompire/task.yaml --strict
python3 check_scope.py .prompire/task.yaml --deactivate
```

## Limitations

The hook does not watch the shell — not `Bash` or `powershell` on the Claude Code
adapter (`hook_scope_guard.py`) or the Copilot CLI one (`hook_copilot_guard.py`), not
`run_command` on the Antigravity CLI one (`hook_antigravity_guard.py`) — an agent with
shell access can write anywhere the hook would otherwise refuse. It is a speed bump
against accidental drift, not a sandbox. The authority is `check_scope.py` reading the
git diff after the agent stops: it sees every git-visible change whatever tool made it,
and nothing more — a write under a gitignored path never enters the evidence it reads.
The hook does not consult gitignore, so a watched-tool write to an ignored out-of-scope
path is still refused early; a shell write to one evades both layers. Install
locations for every adapter: `references/hosts.md`. Every other known gap — symlink and
casefold edge cases, log forgeability, alarm fatigue with two briefs on one branch, what
one `--deactivate` does to `--strict` forever — is measured and explained in
`references/threat-model.md`.

## What this is not

It is not a sandbox, not a permission system, and not a substitute for reading the diff.
`tests_policy: named` and `authoring` both end in a REVIEW flag saying so out loud,
because no checker can tell a repaired assertion from a weakened one. It is not a
prompt generator either — the rendered prompt exists so the contract can be handed
over, and it is capped at ~250 words: on the benchmark's contract tasks it was the
acceptance criteria, not the wording around them, that carried the outcome. It does not
judge whether the work is good — only whether it stayed inside what was declared, and
whether what was declared was pinned before the work began.

## Documentation

- `SKILL.md` — the workflow, the brief shape, the hard rules.
- `references/hosts.md` — running on Claude Code, GitHub Copilot CLI, Codex CLI and
  Antigravity CLI: install locations, hook configuration, the failure-semantics table.
- `references/threat-model.md` — the two-layer design, the guarantee, and the full
  limitations table.
- `references/benchmark.md` — the behavioural benchmark: cells, variants, ablations,
  and how a campaign is read.
- `references/ci.md` — the GitHub Action: what the base means in CI, and what the
  Action cannot check.
- `references/schema.md` — every field, every edge case.
- `references/rules.md` — the sixteen lint rules and what each can and cannot catch.
- `references/grounding.md` — where each rule comes from.
- `references/rendering.md` — renderer targets and wording rules.
- `references/maintaining.md` — tests, and how to change a rule safely.
- `examples/` — five briefs, one shape each; `worked-example.yaml` is the canonical one.

## Licence

MIT. See `LICENSE`.
