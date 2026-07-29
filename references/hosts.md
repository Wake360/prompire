# Agent hosts

Prompire runs as an agent skill on **Claude Code** and on **GitHub Copilot CLI**. The
brief, the linter, the baseline, the checker and the boundary are the same on both. What
differs is where the skill is installed, which renderer target you hand the agent, and
how the PreToolUse hook reports a refusal — and the third one differs enough to need two
adapters.

Copilot support here is **CLI only**. Copilot cloud agent is not supported: it loads
hooks only from `.github/hooks/*.json` on the default branch, and nothing in this tree
has been run or tested against it. Do not configure Prompire for it on the strength of
the CLI instructions below.

## Host support matrix

| Surface | Any agent | Claude Code | Copilot CLI |
|---|---:|---:|---:|
| Generic rendered prompt | yes | yes | yes |
| Post-run git diff verdict | yes | yes | yes |
| Pre-write hook | no | yes | yes |
| Agent launching | no | no | no |

## Primary workflow

Before handoff, run `prompire prepare`. Prompire does not launch or control the agent.
After the agent stops, `prompire verify` gives the combined scope and acceptance
verdict. Review the generated checklist, then close the guard.

```bash
prompire prepare .prompire/task.yaml --target generic
prompire verify .prompire/task.yaml
prompire close .prompire/task.yaml
```

## One tree, one boundary

```
brief_common.py        the schema and the boundary — boundary_verdict, tests_verdict
hook_policy.py         the host-neutral hook core: which paths, which roots, which verdict
hook_scope_guard.py    Claude Code adapter — stdin JSON in, stderr + exit 2 out
hook_copilot_guard.py  Copilot CLI adapter — stdin JSON in, stdout JSON decision out
check_scope.py         the authority, afterwards, on the real git diff
```

Both adapters call `hook_policy.verdict_for()`, which calls the same `boundary_verdict`
and `tests_verdict` that `check_scope.py` calls. There is no second interpretation of
`scope` in this tree and there must never be one: an adapter is allowed to know its
host's wire format and nothing else. If you find yourself deciding what a path means
inside an adapter, the decision belongs in `brief_common.py`.

## Installing the skill

The skill is one directory — `SKILL.md`, the scripts and `references/`. Install it once
per place you want it discoverable. **Do not copy the scripts into several source
directories to serve several hosts**; a second copy is a second thing to keep in sync,
and the mirror in `references/maintaining.md` is already as much duplication as this tree
tolerates.

Personal, available in every repository you open:

```
~/.claude/skills/prompire/      Claude Code
~/.copilot/skills/prompire/     Copilot CLI
~/.agents/skills/prompire/      Copilot CLI, host-neutral location
```

Repository, committed and available to everyone who clones it:

```
.claude/skills/prompire/        Claude Code
.github/skills/prompire/        Copilot CLI
.agents/skills/prompire/        both, host-neutral location
```

A repository install is the right choice when the briefs are part of how the project is
worked on and you want every contributor's agent to compile them the same way. A personal
install is the right choice when it is your habit rather than the project's rule. If both
exist, both are discovered; they are the same skill, so that is harmless, but keep one of
them authoritative so a stale copy cannot answer first.

`SKILL.md` is a valid Agent Skill for both hosts as it stands — YAML frontmatter with
`name` and `description`, then the workflow. Neither host needs a host-specific copy of
it, and there isn't one.

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

Use `prompire verify` for the combined scope and acceptance verdict on every host. These
individual scripts diagnose one stage; they are not a host-specific handoff workflow.

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

## Why there are two adapters: the hosts fail in opposite directions

| | Claude Code | GitHub Copilot CLI |
|---|---|---|
| Refuse | exit 2, reason on stderr | exit 0, `{"permissionDecision":"deny","permissionDecisionReason":…}` on stdout |
| Allow through | exit 0 | exit 0, empty stdout |
| Hook crashes | call proceeds | **call is denied** |
| Hook exits non-zero | call proceeds | **call is denied** |
| Hook times out | call proceeds | call proceeds |

Prompire's hook is required to fail open on its own trouble — a missing repo, an
unreadable brief, a parse error, an unexpected exception. It runs on every watched write
in every project on the machine, and a guard that breaks unrelated sessions gets
uninstalled, which protects nothing. Claude Code's convention already matches that
requirement; Copilot CLI's is the reverse of it. So `hook_copilot_guard.py` translates
explicitly, and never exits non-zero:

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

Diagnostics go to `.prompire/hook-errors.log`, same file and same limitations as on
Claude Code: agent-writable, truncatable and forgeable, so it is a diagnostic trail and
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

## What the hook does not cover, on either host

`bash` and `powershell` are deliberately not matched, and must not be. A shell write
bypasses the early guard entirely; `check_scope.py` on the real git diff is what sees it
afterwards, because git sees the write whatever tool made it. This is the two-layer
design, not an oversight — see the limitations table in `README.md`, which applies
unchanged to Copilot. Inspecting a command line for the files it will touch is a much
weaker claim than reading a diff, and a guard that made it would be worse than one with a
stated hole.

The hook is not a sandbox and not a permission system. Nothing here binds an agent with
shell access. The reviewer still runs `check_scope.py BRIEF --strict` after the agent
stops, and that is where the guarantee lives.
