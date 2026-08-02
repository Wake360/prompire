# Prompire

A verifiable contract for work you delegate to a coding agent.

Before the work starts, the request is compiled into a brief that can be *checked*: a
bounded `scope`, a `forbidden` list, acceptance criteria that are commands rather than
adjectives, a baseline measured on the untouched repo, and a `tests_policy` saying
which test files may move. The base commit is pinned outside the brief. After the agent
stops, Prompire reads the real git diff — not the agent's report — and says whether the
work stayed inside what was declared and whether the acceptance commands now pass. The
verdict needs no cooperation from the agent.

The problem it addresses is narrow and specific: an agent that is graded on a test suite
it can edit will, sooner or later, edit the suite. So will one that is graded on a diff
whose starting point it gets to declare. Everything here follows from taking that
seriously.

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

## Install the CLI

```bash
pipx install prompire
# or
uv tool install prompire
```

Prompire supports Python 3.11+ on macOS, Linux, and Windows.

## Primary workflow

This workflow is host-neutral and works with any coding agent.

Optional step 0: `prompire draft "one sentence"` writes a draft brief to
`.prompire/task.yaml`. The heuristic is deterministic, not a model — it proposes an
acceptance command only where the repo evidences one (`package.json` `scripts.test`, a
pytest config, a `Makefile` `test:` target, `Cargo.toml`, `go.mod`), and states the
absence rather than inventing a command. `--agent claude`, `--agent codex`, `--agent
antigravity` — or any CLI via `--agent-cmd`, drafting prompt on stdin, brief on
stdout — delegates the drafting to a host model that can read the repo. The reply is
parsed as data and re-serialized: the model's own comments are dropped, `baseline` and
`base_rev` are refused as measured rather than drafted, and the boundary, every
acceptance command and any relaxed `tests_policy` come back marked
`# prompire:unconfirmed` however confident the model sounded. Agent-assisted drafting
runs in a disposable repository containing the checkout's current tracked and untracked,
non-ignored files. The agent can inspect and change that snapshot. A symlink is carried
only when its target resolves inside the repository, re-aimed there at the snapshot's own
copy, so a path the agent addresses relative to its workspace cannot reach the source
checkout through one. Ignored files, submodules and nested checkouts are not copied. This
isolates ordinary repository writes; it does not sandbox network, credentials, or an
absolute path the agent composes for itself elsewhere on the machine. Read every
`# prompire:unconfirmed` line, fix it, then delete the marker: `prompire prepare` refuses
while one remains.
Under Claude Code, Copilot CLI, Codex CLI or Antigravity CLI the host model fills this
step instead, following `SKILL.md`.

### Prepare

```bash
prompire prepare .prompire/task.yaml --target generic
```

This measures the baseline, lints the brief, renders the prompt, and arms the guard —
from here on, editing the brief yields no verdict rather than a favourable one.

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

The first cross-agent matrix (2026-08-01): six tasks, five repetitions each, on Claude
Code, Codex CLI and Antigravity CLI. None of the 90 runs left its declared scope,
changed a test file, or touched the brief or the pin. Acceptance differed by host —
claude and codex 30/30, antigravity behind — so the honest claim is that the work is
equally *checked* everywhere, not equally *good* everywhere. Design and reading rules:
`references/benchmark.md`.

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

`.prompire/` belongs in `.gitignore`. The briefs are local task specs, and the
guard's state files (`ACTIVE`, `ACTIVE.tombstones`) are not history.

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
