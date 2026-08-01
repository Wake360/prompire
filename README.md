# Prompire

Compile a request into the smallest brief that can be *checked* — a bounded `scope`, a
`forbidden` list, acceptance criteria that are commands rather than adjectives, a
baseline measured before the work starts, and a `tests_policy` saying which test files
may move. Then check the real git diff afterwards.

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
`# prompire:unconfirmed` however confident the model sounded. A draft run that changed
the repository is refused outright — a drafting agent only reads, and `draft` checks
`git status` afterwards rather than trusting that. Read every `# prompire:unconfirmed`
line, fix it, then delete the marker: `prompire prepare` refuses while one remains.
Under Claude Code, Copilot CLI, Codex CLI or Antigravity CLI the host model fills this
step instead, following `SKILL.md`.

### Prepare

```bash
prompire prepare .prompire/task.yaml --target generic
```

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

## Limitations

The hook does not watch the shell — not `Bash` or `powershell` on the Claude Code
adapter (`hook_scope_guard.py`) or the Copilot CLI one (`hook_copilot_guard.py`), not
`run_command` on the Antigravity CLI one (`hook_antigravity_guard.py`) — an agent with
shell access can write anywhere the hook would otherwise refuse. It is a speed bump
against accidental drift, not a sandbox. The authority is `check_scope.py` reading the
git diff after the agent stops, because git sees a write whatever tool made it. Install
locations for every adapter: `references/hosts.md`. Every other known gap — symlink and
casefold edge cases, log forgeability, alarm fatigue with two briefs on one branch, what
one `--deactivate` does to `--strict` forever — is measured and explained in
`references/threat-model.md`.

## What this is not

It is not a sandbox, not a permission system, and not a substitute for reading the diff.
`tests_policy: named` and `authoring` both end in a REVIEW flag saying so out loud,
because no checker can tell a repaired assertion from a weakened one. It does not judge
whether the work is good — only whether it stayed inside what was declared, and whether
what was declared was pinned before the work began.

## Documentation

- `SKILL.md` — the workflow, the brief shape, the hard rules.
- `references/hosts.md` — running on Claude Code, GitHub Copilot CLI, Codex CLI and
  Antigravity CLI: install locations, hook configuration, the failure-semantics table.
- `references/threat-model.md` — the two-layer design, the guarantee, and the full
  limitations table.
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
