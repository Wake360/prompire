# Agent hosts

Prompire runs as an agent skill on **Claude Code**, on **GitHub Copilot CLI**, on
**Codex CLI** and on **Antigravity CLI**. The brief, the linter, the baseline, the
checker and the boundary are the same on all of them. What differs is where the skill
is installed, which renderer target you hand the agent, and how a pre-write hook
reports a refusal — Claude Code, Copilot CLI and Antigravity CLI differ enough about
that to need three adapters, and Codex CLI has no hook adapter at all: there, the
post-hoc checker is the entire enforcement.

Copilot support here is **CLI only**. Copilot cloud agent is not supported: it loads
hooks only from `.github/hooks/*.json` on the default branch, and nothing in this tree
has been run or tested against it. Do not configure Prompire for it on the strength of
the CLI instructions below.

Antigravity support is **CLI only** for the same reason: the Antigravity IDE and the
Antigravity 2.0 desktop app load customizations from their own roots, and nothing in
this tree has been run or tested against either. Everything below about Antigravity
was measured against `agy` 1.1.8 on 2026-08-01.

## Host support matrix

| Surface | Any agent | Claude Code | Copilot CLI | Codex CLI | Antigravity CLI |
|---|---:|---:|---:|---:|---:|
| Generic rendered prompt | yes | yes | yes | yes | yes |
| Post-run git diff verdict | yes | yes | yes | yes | yes |
| Pre-write hook | no | yes | yes | no | yes |
| Agent launching | no | no | no | no | no |

Agent launching means the work itself: Prompire never starts the agent that edits the
repo. `prompire draft --agent claude`, `--agent codex`, `--agent antigravity` (or
`--agent-cmd`) does run a host CLI once, but only to propose a draft brief — the reply
is re-serialized with `prompire:unconfirmed` markers, and the handoff below stays
manual. The codex drafting invocation runs `codex exec` under its read-only sandbox
with the user config ignored; drafting reads the repo and must never write it.
Headless `agy` has no read-only mode at all, so `draft` snapshots `git status` around
every agent run — any host's, `--agent-cmd` included — and refuses the draft if the
tree changed.

## Primary workflow

This workflow is the same for any agent and host.

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

## One tree, one boundary

```
brief_common.py            the schema and the boundary — boundary_verdict, tests_verdict
hook_policy.py             the host-neutral hook core: which paths, which roots, which verdict
hook_scope_guard.py        Claude Code adapter — stdin JSON in, stderr + exit 2 out
hook_copilot_guard.py      Copilot CLI adapter — stdin JSON in, stdout JSON decision out
hook_antigravity_guard.py  Antigravity CLI adapter — stdin JSON in, stdout JSON decision out
check_scope.py             the authority, afterwards, on the real git diff
```

Every adapter calls `hook_policy.verdict_for()`, which calls the same
`boundary_verdict` and `tests_verdict` that `check_scope.py` calls. There is no second
interpretation of `scope` in this tree and there must never be one: an adapter is
allowed to know its host's wire format and nothing else. If you find yourself deciding
what a path means inside an adapter, the decision belongs in `brief_common.py`.

## Installing the skill

The skill is one directory — `SKILL.md`, the scripts and `references/`. Install it once
per place you want it discoverable. **Do not copy the scripts into several source
directories to serve several hosts**; a second copy is a second thing to keep in sync,
and the mirror in `references/maintaining.md` is already as much duplication as this tree
tolerates.

Personal, available in every repository you open:

```
~/.claude/skills/prompire/          Claude Code
~/.copilot/skills/prompire/         Copilot CLI
~/.codex/skills/prompire/           Codex CLI
~/.gemini/config/skills/prompire/   Antigravity CLI, its documented global root
~/.agents/skills/prompire/          Copilot CLI and Codex CLI, host-neutral location
```

Repository, committed and available to everyone who clones it:

```
.claude/skills/prompire/        Claude Code
.github/skills/prompire/        Copilot CLI
.agents/skills/prompire/        Copilot CLI, Codex CLI and Antigravity CLI — host-neutral
```

Antigravity walks from the working directory up to the repository root for `.agents/`,
so the host-neutral repository location serves it with no extra copy; discovery from
there was verified live (the skill's name and description appear in the model's skill
list).

A repository install is the right choice when the briefs are part of how the project is
worked on and you want every contributor's agent to compile them the same way. A personal
install is the right choice when it is your habit rather than the project's rule. If both
exist, both are discovered; they are the same skill, so that is harmless, but keep one of
them authoritative so a stale copy cannot answer first.

`SKILL.md` is a valid Agent Skill for every host above as it stands — YAML frontmatter
with `name` and `description`, then the workflow. No host needs a host-specific copy of
it, and there isn't one. `agents/openai.yaml` carries the interface metadata OpenAI
hosts read — display name, short description, default prompt — and is inert everywhere
else.

### Naming the scripts in instructions

Nothing rendered for Copilot may hardcode `~/.claude/skills/prompire/`. Resolve the
commands one of three ways, in order of preference:

1. **Script-relative.** From inside the skill directory the tools are plain filenames:
   `python3 baseline.py .prompire/task.yaml --write`. Every script inserts its own
   directory on `sys.path`, so they run correctly from any working directory as long as
   the path you type reaches them.
2. **The actual skill directory**, whichever of the locations above you installed into.
3. **Separate examples per host**, clearly labelled, when a document has to show a
   literal path — which is what this file does below.

## Diagnostic commands

### Combined verdict

Use `prompire verify` for the combined scope and acceptance verdict on every host. These
individual scripts diagnose one stage; they are not a host-specific handoff workflow.

### Individual tools

| Command | Diagnostic purpose |
|---|---|
| `python3 baseline.py BRIEF --write` | inspect baseline measurement |
| `python3 lint_brief.py BRIEF` | inspect brief validation |
| `python3 render_brief.py BRIEF --target copilot` | inspect a host-specific rendering target |
| `python3 check_scope.py BRIEF --activate` | inspect guard activation |
| `python3 check_scope.py BRIEF --strict` | inspect the strict git-diff verdict |
| `python3 check_scope.py BRIEF --deactivate` | inspect guard cleanup |

Direct `--activate` must run before the agent starts. Direct `--strict` is the human
reviewer's, not the agent's. The primary CLI lifecycle performs those stages through
`prompire prepare`, `prompire verify`, and `prompire close`.

## Installing the hook — Claude Code

`~/.claude/settings.json`, matching the four watched write tools
(`examples/hooks/claude-user.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/skills/prompire/hook_scope_guard.py"
          }
        ]
      }
    ]
  }
}
```

Remove it by deleting the `PreToolUse` entry.

The hook is optional and machine-wide: once installed it runs on every `Write`/`Edit` in
every project, and does nothing at all in a repository with no armed brief.

**Cost**: about 75 ms per watched write, dominated by Python interpreter startup, paid on
every `Write`/`Edit`/`MultiEdit`/`NotebookEdit` on the machine whether or not any brief
is armed. Measured on an Intel MacBook, median of 12 runs: 74 ms in a repository with
nothing armed, 85 ms in one with a brief armed and the boundary actually evaluated.
Nothing is paid on reads, searches, or `Bash`.

## Installing the hook — GitHub Copilot CLI

Copilot uses a different file, a different schema, and a different way of saying no.

**Where the file goes.** Any of these; all discovered sources are combined and every
matching hook entry runs, so a repository hook and a user hook both fire.

```
.github/hooks/prompire.json                      repository — committed, applies to everyone
~/.copilot/hooks/prompire.json                   user — macOS/Linux
%USERPROFILE%\.copilot\hooks\prompire.json       user — Windows
$COPILOT_HOME/hooks/prompire.json                user — when COPILOT_HOME is set
```

Two more sources exist and are worth knowing about because they explain a hook you did
not install: inline entries in `.github/copilot/settings.json`,
`.github/copilot/settings.local.json` or `~/.copilot/settings.json`, and hooks
contributed by plugins. A machine-wide policy directory
(`/etc/github-copilot/policy.d/*.json`, or `C:\ProgramData\GitHub\Copilot\policy.d\`) is
loaded first and is an administrator's, not yours.

**User-level, native camelCase event** (`examples/hooks/copilot-user.json`):

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "matcher": "create|edit|str_replace_editor|apply_patch",
        "bash": "python3 \"$HOME/.copilot/skills/prompire/hook_copilot_guard.py\"",
        "powershell": "python \"$env:USERPROFILE\\.copilot\\skills\\prompire\\hook_copilot_guard.py\"",
        "timeoutSec": 15
      }
    ]
  }
}
```

**Repository-level** (`examples/hooks/copilot-repo.json`) — same entry, pointing at a
repository install:

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "matcher": "create|edit|str_replace_editor|apply_patch",
        "bash": "python3 \"$(git rev-parse --show-toplevel)/.github/skills/prompire/hook_copilot_guard.py\"",
        "powershell": "python \"$(git rev-parse --show-toplevel)/.github/skills/prompire/hook_copilot_guard.py\"",
        "timeoutSec": 15
      }
    ]
  }
}
```

**PascalCase, reusing a Claude-format entry** (`examples/hooks/copilot-pascalcase.json`)
— useful when you already keep one hook list in Claude's tool vocabulary and would
rather not maintain two:

```json
{
  "version": 1,
  "hooks": {
    "PreToolUse": [
      {
        "type": "command",
        "matcher": "Edit|Write",
        "bash": "python3 \"$HOME/.copilot/skills/prompire/hook_copilot_guard.py\"",
        "powershell": "python \"$env:USERPROFILE\\.copilot\\skills\\prompire\\hook_copilot_guard.py\"",
        "timeoutSec": 15
      }
    ]
  }
}
```

`Edit|Write` is Copilot's own mapping of the four file-changing tools: `create` matches
`Write`, and `edit`, `str_replace_editor` and `apply_patch` all match `Edit`. The adapter
reads both payload spellings, so either event name works; pick one.

**A single cross-platform `command`.** The `command` field is a fallback used when
neither `bash` nor `powershell` is given, and it is run by whichever shell the platform
supplies — so the quoting has to be valid in both. That is only reliable when the path
contains no spaces and needs no variable expansion:

```json
{ "type": "command", "matcher": "create|edit|str_replace_editor|apply_patch",
  "command": "python3 /opt/prompire/hook_copilot_guard.py", "timeoutSec": 15 }
```

Prefer the explicit `bash`/`powershell` pair anywhere a home directory is involved.
`$HOME` and `$env:USERPROFILE` do not mean the same thing to the same shell, and a
mis-quoted command is a hook that never runs — which fails silently in the direction of
no enforcement. The `bash` line above is POSIX `bash`; the `powershell` line is
PowerShell syntax (`$env:` expansion, backslash separators) and is what runs on Windows.
It uses `python` rather than `python3`, which is the launcher name a Windows install
normally provides.

**Removing it.** Delete the file, or the `preToolUse` entry inside it. To turn every hook
off at once without deleting anything, set `"disableAllHooks": true` in the same file.

**Checking Copilot found it.** There is no documented `list-hooks` command, so verify by
behaviour rather than by introspection, in a scratch repository:

1. `python3 check_scope.py BRIEF --activate` with a brief whose `scope` excludes some
   path — say `scratch.txt`.
2. Ask Copilot to create `scratch.txt`.
3. A configured hook shows the refusal, quoting `BLOCKED by Prompire scope guard`. No
   refusal means the hook did not run: check the file is valid JSON (`python3 -m
   json.tool < .github/hooks/prompire.json`), that `bash` scripts are executable if you
   pointed at a wrapper rather than at Python, and that the path in `bash`/`powershell`
   actually resolves.
4. You can also run the adapter by hand, which needs no Copilot at all:

   ```bash
   echo '{"cwd":"'"$PWD"'","toolName":"create","toolArgs":{"path":"scratch.txt"}}' \
     | python3 hook_copilot_guard.py
   ```

   A denial prints one JSON object; anything allowed or unknown prints nothing. Either
  way it exits 0.

## Installing the hook — Antigravity CLI

Antigravity configures hooks in a `hooks.json` at the root of a customization
directory — named hook groups, not Copilot's flat schema, and no `version` field.

**Where the file goes.** Both locations verified against agy 1.1.8:

```
.agents/hooks.json                  repository — committed, applies to everyone
~/.gemini/config/hooks.json         user — Antigravity's global customization root
```

**Repository-level** (`examples/hooks/antigravity-repo.json`) — the hook command runs
with its working directory set to the directory containing `hooks.json`, so a
repository install at `.agents/skills/prompire/` is reachable with a relative path:

```json
{
  "prompire": {
    "PreToolUse": [
      {
        "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "python3 skills/prompire/hook_antigravity_guard.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

**User-level** (`examples/hooks/antigravity-user.json`) — same entry, pointing at a
global install; `~` is expanded by the host:

```json
{
  "prompire": {
    "PreToolUse": [
      {
        "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.gemini/config/skills/prompire/hook_antigravity_guard.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

The matcher is a regex over tool names and must name exactly the tools the adapter
reads — a tool the adapter handles but the matcher omits is a tool the hook is never
invoked for at all. `run_command` is deliberately absent; see the gap section at the
end of this file.

**Removing it.** Delete the file, or set `"enabled": false` inside the `prompire`
entry.

**Checking Antigravity found it.** Same behavioural check as Copilot, in a scratch
repository: arm a brief whose `scope` excludes some path, ask `agy` to create that
path, and expect the model to quote `BLOCKED by Prompire scope guard`. The adapter can
also be run by hand, no Antigravity needed:

```bash
echo '{"workspacePaths":["'"$PWD"'"],"toolCall":{"name":"write_to_file","args":{"TargetFile":"'"$PWD"'/scratch.txt"}}}' \
  | python3 hook_antigravity_guard.py
```

A denial prints one JSON object; anything allowed or unknown prints nothing. Either
way it exits 0.

## Codex CLI — no hook, checker only

There is no pre-write hook adapter for Codex CLI, deliberately. Codex constrains
model-run commands with its own sandbox (`read-only`, `workspace-write`), and that
boundary is the workspace, not the brief: inside the repository it allows any write the
`scope` forbids. Nothing in Codex's hook surface has been evaluated against the
fail-open requirement below, so no adapter ships until one is. What enforces the brief
under Codex is the same thing that enforces it against `bash` on the other hosts —
`check_scope.py` reading the real git diff afterwards, which needs no cooperation from
the host at all.

The lifecycle is the standard one with the `codex` renderer target:

```bash
prompire draft "one sentence" --agent codex      # optional; codex exec, read-only
prompire prepare .prompire/task.yaml --target codex
codex exec --sandbox workspace-write - < .prompire/task.codex.md
prompire verify .prompire/task.yaml
prompire close .prompire/task.yaml
```

Skill discovery was verified against codex-cli 0.146.0: the loader reads
`~/.codex/skills/`, `~/.agents/skills/` and the repository's `.agents/skills/`. The
full lifecycle above, drafting included, was run live against the same version on
2026-08-01.

## Why there are three adapters: the hosts fail in different directions

| | Claude Code | GitHub Copilot CLI | Antigravity CLI |
|---|---|---|---|
| Refuse | exit 2, reason on stderr | exit 0, `{"permissionDecision":"deny","permissionDecisionReason":…}` on stdout | exit 0, `{"decision":"deny","reason":…}` on stdout |
| Allow through | exit 0 | exit 0, empty stdout | exit 0, empty stdout |
| Hook crashes | call proceeds | **call is denied** | call proceeds |
| Hook exits non-zero | call proceeds | **call is denied** | call proceeds |
| Hook times out | call proceeds | call proceeds | call proceeds |

Every Antigravity cell was measured against agy 1.1.8 on 2026-08-01, not read off a
docs page: a `sh -c "exit 1"` hook, an `echo not-json` hook and a hook sleeping past
its `timeout` each let a `write_to_file` proceed; a valid deny decision blocked it,
with the reason quoted back to the model verbatim.

Prompire's hook is required to fail open on its own trouble — a missing repo, an
unreadable brief, a parse error, an unexpected exception. It runs on every watched write
in every project on the machine, and a guard that breaks unrelated sessions gets
uninstalled, which protects nothing. Claude Code's convention already matches that
requirement, and so does Antigravity's; Copilot CLI's is the reverse of both. So
`hook_copilot_guard.py` translates explicitly, and never exits non-zero:

- **A definite violation** — exit 0, one JSON object, `permissionDecision: "deny"`, with
  a reason naming the path and the rule.
- **Everything else** — exit 0, empty stdout. That covers an in-scope path, no brief
  armed, an irrelevant tool, no repository, an unreadable or malformed brief, a payload
  or patch the adapter cannot interpret, and any unexpected exception.

Neutral is deliberately **not** `permissionDecision: "allow"`. Allowing would skip the
permission prompt Copilot would otherwise show the operator — a real approval bought with
the hook's silence, granted for the reason that the hook did not understand the question.
Emitting nothing leaves the call in Copilot's normal permission flow, where the human is
still asked.

`hook_antigravity_guard.py` answers in the same two shapes — a deny decision or
silence, exit 0 both ways — for the same reasons: Antigravity's `allow` skips the
host's own permission flow for the call, an approval this hook has no standing to
grant, and although a crash would fail open natively, an adapter that exits 0 and logs
its own trouble leaves a mark instead of looking exactly like a compliant agent.

Diagnostics go to `.prompire/hook-errors.log` on all three hosts, same file and same
limitations: agent-writable, truncatable and forgeable, so it is a diagnostic trail and
not an audit log. The audit trail is `check_scope.py` plus git history.

## What the Copilot adapter reads

**Payload shapes.** Both documented ones. The native camelCase `preToolUse` event
(`sessionId`, `timestamp`, `cwd`, `toolName`, `toolArgs`) and the PascalCase
VS Code-compatible one (`hook_event_name: "PreToolUse"`, `session_id`, `timestamp`,
`cwd`, `tool_name`, `tool_input`). `toolArgs` is accepted both as an object and as a
JSON-encoded string, because both occur — the reference types it as an object and
GitHub's own worked example parses it with a second `jq` call.

**Tools and the arguments they are read from.**

| Tool | Claude name | Paths read from |
|---|---|---|
| `create` | `Write` | the path keys |
| `edit` | `Edit` | the path keys |
| `str_replace_editor` | `Edit` | the path keys; `command: view` is a read and draws no verdict |
| `apply_patch` | `Edit` | the patch envelope in `input` or `patch` — every `*** Add File:`, `*** Update File:`, `*** Delete File:` and `*** Move to:` header. Falls back to the path keys only when neither key carries a string |
| `Write`, `Edit`, `MultiEdit`, `NotebookEdit` | — | the path keys |

"The path keys" is one set, `path` / `file_path` / `notebook_path`, and every tool above
is read with all three rather than with a per-tool subset. That is deliberate and it is
the safe direction: a tool that grows a second path field, or a host that spells one
differently from its documentation, is still seen. It does mean the adapter will read a
`notebook_path` out of a `create` call — no such payload exists today, and if one
appears it is judged rather than missed.

Every path is resolved against the payload's `cwd`, normalised through the same
`norm_path`/`_as_written` logic the Claude adapter uses, checked against the
unconditional state-file protection first, then against the active brief's boundary and
tests policy. A tool call is atomic: if any affected path draws a definite violation, the
whole call is refused, and the reason names the offending path rather than the first one.

**What draws no verdict.** A patch that cannot be parsed, a tool whose argument shape
contains none of the keys above, a payload without `cwd`, an unknown tool. All of them
are silence, never a guess. A multi-file patch is not approved because its first path was
allowed, and an operation the adapter does not recognise is not reported as checked.

## What the Antigravity adapter reads

**Payload shape.** One JSON object on stdin, protojson camelCase: the call as
`toolCall: {name, args}`, the session's roots as `workspacePaths` — a list; there is
no `cwd` field. Every workspace path is checked as a governing root and the target's
own repository is checked regardless, so an agent bound by one workspace's brief
cannot escape into another repository; any verdict refuses the whole call.

**Tools and the argument they are read from.**

| Tool | Paths read from |
|---|---|
| `write_to_file` | `TargetFile` |
| `replace_file_content` | `TargetFile` |
| `multi_replace_file_content` | `TargetFile` |

`TargetFile` is attested by captured payloads (agy 1.1.8), which carry it as an
absolute path; `multi_replace_file_content` is named by the host's own prompt text as
the same editing family as `replace_file_content`. Only an absolute `TargetFile` is
judged: the host's rule for resolving a relative spelling is not documented, and
resolving it against a workspace path of the adapter's own choosing would judge a file
nobody named.

**What draws no verdict.** A payload without a usable `workspacePaths`, a relative or
missing `TargetFile`, an unknown tool, malformed stdin. All of them are silence, never
a guess — and never an allow, which would skip the host's own permission flow for the
call.

**Unmatched file-changing operations.** `delete_directory`, `move` and notebook edits
change files but are not matched: their argument shapes are unattested — no public
per-tool schema, never observed in a captured payload — and a guard that guessed at
them would answer questions it cannot read. Every one of them still meets
`check_scope.py`, because git sees the change whatever tool made it.

## What the hook does not cover, on any hook host

`bash`, `powershell` and `run_command` are deliberately not matched, and must not be. A
shell write bypasses the early guard entirely; `check_scope.py` on the real git diff is
what sees it afterwards, because git sees the write whatever tool made it. This is the
two-layer design, not an oversight — see the limitations table in
`references/threat-model.md`, which applies unchanged to Copilot and Antigravity.
Inspecting a command line for the files it will touch is a much weaker claim than
reading a diff, and a guard that made it would be worse than one with a stated hole.

The hook is not a sandbox and not a permission system. Nothing here binds an agent with
shell access. The reviewer still runs `check_scope.py BRIEF --strict` after the agent
stops, and that is where the guarantee lives.
