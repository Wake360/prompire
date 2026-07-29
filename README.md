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

## Host-neutral workflow

```bash
prompire prepare .prompire/task.yaml --target generic
# give .prompire/task.generic.md to any coding agent
prompire verify .prompire/task.yaml
# review .prompire/task.checklist.md
prompire close .prompire/task.yaml
```

The CLI does not launch an agent. Claude Code and Copilot CLI hooks are optional
early-warning adapters; the final git-diff check is host-neutral.

## Two layers, neither sufficient alone

**A PreToolUse hook** refuses an out-of-scope write before it lands. It is cheap and
early, and it is evadable by design: on Claude Code (`hook_scope_guard.py`) it sees
`Write`, `Edit`, `MultiEdit` and `NotebookEdit`; on GitHub Copilot CLI
(`hook_copilot_guard.py`) it sees `create`, `edit`, `str_replace_editor` and
`apply_patch`. On neither host does it see the shell — not `Bash`, not `powershell`. It
is a speed bump against accidental and lazy scope drift. It is not a sandbox and must
not be described as prevention.

**`check_scope.py`** reads the real git diff after the agent stops. This is the
authority, because git sees the write whatever tool made it. It needs no cooperation
from the agent and there is nothing the agent can add to its own acceptance block to
satisfy it.

The hook exists because a violation caught before it lands costs nothing to undo. The
checker exists because the hook can be walked around. Running only the hook gives you a
guard with a documented hole; running only the checker gives you a post-mortem. The
design is both.

Two hosts, one boundary: both adapters are thin protocol shims over `hook_policy.py`,
which is the only caller of the `boundary_verdict`/`tests_verdict` that `check_scope.py`
also calls. A second interpretation of `scope` is the one thing that split must never
grow. Install locations and hook configuration for both hosts: `references/hosts.md`.

## The guarantee

> `check_scope.py`'s verdict cannot be bought by editing the brief — under stated
> conditions. `--activate` records the brief's declared `base_rev` and a sha256 of the
> whole file in `.prompire/ACTIVE`; while that pointer stands, changing any byte of the
> brief, or checking a different brief, produces no verdict at all (exit 2) rather than a
> favourable one. A `--base` that disagrees with the pin is the one exception, and it is
> deliberate: a human choosing the comparison range wins, so the run still produces a
> verdict, labelled `base given on the command line` and carrying a REVIEW that names both
> revisions. That is not a hole the agent can reach — `--base` is an argument the person
> running the check types, not a field in the brief. That holds when three
> things are true: the guard was armed on that brief **before the work began**, it has not
> been disarmed since, and the agent's writes go through the tools the PreToolUse hook
> watches. Read the base-source label on the summary line, because it says which of them
> applied. `pin` means the verdict used the brief that was armed, at the base it declared
> then — no more: arming after the work is already committed yields a `pin` that vouches
> for the brief, not for where the work started. `repin` means the pointer was written
> after a `--deactivate` — or while the disarm log was not a readable file — and because any
> disarm anywhere in the repo makes every later arm
> a `repin`, it corroborates nothing on its own; read `.prompire/ACTIVE.tombstones`
> against the current pin and `git diff` between the two bases to see what the re-arm moved
> past. `repin` is also what you get while the disarm log is not a readable file, which is
> deliberate. `base uncorroborated` means the only record of where the work started is the field
> the agent could edit — and that is the state the documented workflow produces today if
> you skip `--activate`, in which the tool is an advisory diff-classifier and one Write to
> the brief (a wider `scope`, one `dirty_baseline` entry, a `base_rev` re-stamped at a
> commit that already contains the work) buys a clean verdict. None of it binds an agent
> with shell access: every record here is a file. The guarantee is that evasion stops being
> a silent one-field edit and becomes a named act in the transcript. Two more things now
> hold unconditionally, whether or not a guard is armed anywhere in the repo:
> `.prompire/ACTIVE` and `.prompire/ACTIVE.tombstones` cannot be written by
> `Write`/`Edit`/`MultiEdit`/`NotebookEdit`, at any depth or spelling, so neither a `pin`
> nor the disarm history behind a `repin` can be forged or erased by the same four tools
> the rest of this guarantee already covers.

Read that paragraph before relying on any of this. In particular: the workflow produces
the *weakest* state unless you run `--activate` before the agent starts, and the base
source printed on every summary line is the only way to tell which state you got.

## Diagnostic commands

```bash
# 1. write .prompire/<slug>.yaml — see SKILL.md for the shape
python3 baseline.py .prompire/task.yaml --write     # measures, writes base_rev + baseline
python3 lint_brief.py .prompire/task.yaml           # exit 0 = shippable
python3 render_brief.py .prompire/task.yaml --target claude

# 2. arm the guard, THEN launch the agent
python3 check_scope.py .prompire/task.yaml --activate

# 3. after the agent stops — you run this, not the agent
python3 check_scope.py .prompire/task.yaml --strict
python3 check_scope.py .prompire/task.yaml --deactivate
```

`.prompire/` belongs in `.gitignore`. The briefs are local task specs, and the
guard's state files (`ACTIVE`, `ACTIVE.tombstones`) are not history.

## Installing the hook — Claude Code and GitHub Copilot CLI

The hook is optional and machine-wide: once installed it runs on every `Write`/`Edit` in
every project, and does nothing at all in a repository with no armed brief. On Claude
Code, add to `~/.claude/settings.json`:

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

**Cost**: about 75 ms per watched write, dominated by Python interpreter startup, paid on
every `Write`/`Edit`/`MultiEdit`/`NotebookEdit` on the machine whether or not any brief
is armed. Measured on an Intel MacBook, median of 12 runs: 74 ms in a repository with
nothing armed, 85 ms in one with a brief armed and the boundary actually evaluated.
Nothing is paid on reads, searches, or `Bash`.

**If the hook has a bug, nothing blocks.** It fails open on its own trouble — a missing
repo, an unreadable brief, a parse error, an unexpected exception — because it runs in
every unrelated session on the machine, and a guard that breaks unrelated sessions gets
uninstalled. Every degradation is toward not enforcing. A bug therefore surfaces as a
write that should have been refused and wasn't, which `check_scope.py` catches
afterwards. It fails closed only on a definite verdict.

To remove it, delete the `PreToolUse` entry from `~/.claude/settings.json`.

### GitHub Copilot CLI

Copilot uses its own hook file and its own way of saying no. User-level example
(`examples/hooks/copilot-user.json`):

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

**It never exits non-zero.** Copilot CLI treats a crash or any non-zero exit from a
command `preToolUse` hook as a denial, the opposite of the fail-open behaviour this guard
needs. So `hook_copilot_guard.py` always exits 0: a definite violation is exit 0 plus one
`{"permissionDecision":"deny",…}` object on stdout, and everything else — including its
own trouble — is exit 0 with empty stdout, leaving the call in Copilot's normal
permission flow rather than silently approving it. Full install locations, both payload
shapes, and the complete failure-semantics table: `references/hosts.md`.

## Limitations

These are known, reproduced, and stated here rather than in a footnote. None is a
surprise to the design; each is a place where the tool's claim stops.

| Limitation | Why it is acceptable |
|---|---|
| **`Bash` is not watched**, so the hook is a speed bump against accidental and lazy scope drift, not a sandbox. Verified: an identical out-of-scope write is blocked via `Write` and allowed via `Bash`. | An agent holding `Bash` can write any file anyway, and `check_scope.py` on the real git diff sees the write whatever tool made it — that is the two-layer design, not an oversight. The honest caveat: "an agent with Bash could do it anyway" covers only the agent that *holds* Bash. It does not cover the common configuration where Bash prompts for approval while `Write`/`Edit` are auto-accepted, and it does not cover the no-adversary case of a stale `ACTIVE` sitting in a checked-out repo while the operator believes the guard is armed. |
| **`hook-errors.log` is agent-writable**, truncatable, and forgeable — a newline inside a `file_path` injects a line. | It is a diagnostic trail, not an audit log. The audit trail is `check_scope.py` plus git history. Reaching the disarmed state it records needs Bash, and with Bash the file is erasable regardless. |
| **A symlinked `.prompire` directory defeats the pointer shape check** (`src/.prompire -> src/x`, after which `Write src/x/ACTIVE` is allowed and the planted pointer goes live). | Creating the symlink needs Bash. Unlike the other Bash plants this one *survives* the pointer rule rather than bypassing it, which is why it is listed separately rather than folded into the row above. |
| **A hand-written `ACTIVE` containing `../..`** loads a brief from outside the root: `norm_path` strips leading `./` and slashes, not `..`. | No watched tool can write such a pointer — the depth-agnostic shape check blocks every spelling, confirmed against 11 attempts. Writing pointers is `--activate`'s business. |
| **A rename-out VIOLATION names only the destination**, so it does not say which test vanished. | Cosmetic. Byte-identity with the pre-refactor checker was a hard constraint when the checker was rewired, and changing the message was out of scope there. |
| **`rel.lower()`/`casefold` adequacy for the two ASCII literals is filesystem-dependent.** | Probed: on APFS, `active` and `AcTiVe` fold onto `ACTIVE` and are blocked; Turkish dotless ı, fullwidth forms, the Kelvin sign, a trailing dot and a trailing space each create a *distinct* file and cannot clobber the real one. The brief-identity check does not use string comparison at all — it uses device+inode identity. |
| **An `apply_patch` envelope the Copilot adapter cannot parse draws no verdict at all.** | The adapter refuses to guess which files an unreadable patch touches — a partial read would let a multi-file patch's second, out-of-scope file ride in on the first file's approval. `check_scope.py` on the resulting git diff is what catches it instead. |

Two more, from operating it rather than from attacking it:

**One brief, one contiguous range, one worktree.** Two briefs running concurrently on one
branch cross-attribute: each reports the other's properly-governed work as violations of
its own boundary. Confirmed at both the working-tree and the commit level during this
project's own dogfooding, where one run reported eight violations of which all eight were
correct and none were misconduct. The failure mode is alarm fatigue — an operator who
sees eight violations that are all somebody else's work stops reading the output. The
guard has no concept of a second brief, and giving it one would mean teaching it which
commits belong to whom, which is the thing git already answers if each brief gets its own
range.

**Filesystem obstruction of `.prompire/` state** — a directory planted where a state
file belongs, a read-only mount, a symlink redirecting the write — lands as a refusal, or
in the narrowest remaining corners as a traceback, rather than as a considered message.
All of them fail closed: none produces a favourable verdict from a watched tool.

**One legitimate `--deactivate` used to make `--strict` red forever** — every later arm
in the repo reports `repin`, by design, and nothing reversed that. The cost was that
`--strict` stopped being believed on a repo with one honest disarm in its past, which is
the same as not running it. `--strict --ack-disarms <digest>` (0.3.0) is the fix: a
reviewer who has read `.prompire/ACTIVE.tombstones` and accepts what is in it can name
a prefix of the log's current sha256 and stop that one `repin` finding from failing
`--strict` — the finding still prints, the base is still labelled `repin`, never `pin`.
The acknowledgement is good for the log exactly as it stood when given: one more
`--deactivate` changes the log's bytes and the digest with it, so the same acknowledgement
stops matching and `--strict` goes red again until a fresh one names the new log. None of
this binds an agent with shell access, same as everything else here — it is a way for a
human reviewer to stop re-litigating a disarm they have already read, not a lock on
anything a shell can write around.

## What this is not

It is not a sandbox, not a permission system, and not a substitute for reading the diff.
`tests_policy: named` and `authoring` both end in a REVIEW flag saying so out loud,
because no checker can tell a repaired assertion from a weakened one. It does not judge
whether the work is good — only whether it stayed inside what was declared, and whether
what was declared was pinned before the work began.

## Documentation

- `SKILL.md` — the workflow, the brief shape, the hard rules.
- `references/hosts.md` — running on Claude Code and GitHub Copilot CLI: install
  locations, hook configuration, the failure-semantics table.
- `references/schema.md` — every field, every edge case.
- `references/rules.md` — the sixteen lint rules and what each can and cannot catch.
- `references/grounding.md` — where each rule comes from.
- `references/rendering.md` — renderer targets and wording rules.
- `references/maintaining.md` — tests, and how to change a rule safely.
- `examples/` — five briefs, one shape each; `worked-example.yaml` is the canonical one.

## Licence

MIT. See `LICENSE`.
