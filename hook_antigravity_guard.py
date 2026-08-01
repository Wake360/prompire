#!/usr/bin/env python3
"""Antigravity CLI PreToolUse adapter: refuse a file write the active brief's boundary
does not allow.

Protocol only. The decision is `hook_policy.verdict_for()`, the same call
`hook_scope_guard.py` makes for Claude Code and `hook_copilot_guard.py` makes for GitHub
Copilot CLI, and the same `boundary_verdict` / `tests_verdict` `check_scope.py` makes
afterwards. There is no Antigravity interpretation of `scope` in this file, and there
must never be one.

## The wire format

Antigravity (`agy`) hooks read one JSON object on stdin and answer with one on stdout,
protojson camelCase throughout. A `PreToolUse` payload carries the call as
`toolCall: {name, args}` plus session metadata; the session's roots arrive as
`workspacePaths`, a list — there is no `cwd` field. A refusal is a JSON object whose
`decision` is `deny`, with a `reason` the host quotes back to the model verbatim.

## The failure direction — measured, not assumed

Antigravity fails OPEN on hook trouble, like Claude Code and unlike Copilot CLI.
Measured against agy 1.1.8 (2026-08-01), not read off a docs page: a hook that crashes
(`sh -c "exit 1"`) lets the write proceed, a hook whose stdout is not a decision JSON
lets it proceed, a hook that outlives its timeout lets it proceed, and a valid deny
decision blocks it with the reason surfaced to the model. So the native convention
already matches the fail-open requirement this guard carries everywhere; this adapter
still exits 0 and logs its own trouble, so a crash leaves a mark in
`.prompire/hook-errors.log` instead of looking exactly like a compliant agent.

Neutral is empty stdout, never a decision of `allow`. Antigravity's `allow` skips its
own permission flow for the call, which is an approval this hook has no standing to
grant — the same reason the Copilot adapter never emits its own allow. Silence leaves
the call wherever the host's normal flow would have taken it.

## What this does not cover

`run_command` is deliberately not matched. A shell write bypasses this adapter exactly
as `bash` bypasses the other two; `check_scope.py` on the real git diff is what sees it
afterwards. Do not add shell interception here — inspecting a command line for the
files it will touch is a much weaker claim than reading a diff.

`delete_directory`, `move`, `edit_notebook` and the browser/notebook step families are
also unmatched, for a narrower reason: their argument shapes are unattested — no public
per-tool schema exists, and none has appeared in a captured payload. A guard that
guessed at an argument key would answer questions it cannot read. Every one of those
operations still meets `check_scope.py`, because git sees the change whatever tool made
it.
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# The file-writing tools this adapter watches, and the one argument that names their
# target. Every entry is attested, not guessed from a name: captured agy 1.1.8
# PreToolUse payloads carry `TargetFile` (an absolute path, both times observed) for
# `write_to_file` ({TargetFile, CodeContent, Overwrite, ...}) and
# `replace_file_content` ({TargetFile, TargetContent, ReplacementContent, ...}), and
# the binary's own prompt text names `multi_replace_file_content` as the same editing
# family as `replace_file_content`. A tool call whose arguments carry no string
# `TargetFile` is a shape this file does not know, and an unknown shape is answered
# with silence, never with a verdict.
FILE_TOOLS = ("write_to_file", "replace_file_content", "multi_replace_file_content")
TARGET_KEY = "TargetFile"


def read_payload(raw):
    """(tool_name, args, workspace_paths) from a PreToolUse payload, or None if this is
    not a payload this adapter can act on.

    `workspacePaths` is required the same way `cwd` is required by the Copilot adapter:
    it is the session's own root, and `verdict_for` needs it to keep an agent bound by
    repo A's brief from escaping into repo B. A payload without one usable workspace
    path draws silence, not a verdict computed against a directory nobody named.
    """
    if not isinstance(raw, dict):
        return None
    call = raw.get("toolCall")
    if not isinstance(call, dict):
        return None
    tool_name = call.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    args = call.get("args")
    if not isinstance(args, dict):
        return None
    workspaces = raw.get("workspacePaths")
    if not isinstance(workspaces, list):
        return None
    workspaces = [w for w in workspaces if isinstance(w, str) and w]
    if not workspaces:
        return None
    return tool_name, args, workspaces


def decide(state):
    """The decision as a string to write to stdout — `""` for neutral. Writes nothing
    itself, so a later exception cannot leave a half-emitted JSON object behind."""
    try:
        raw = json.loads(sys.stdin.read())
    except ValueError:
        return ""
    payload = read_payload(raw)
    if payload is None:
        return ""
    tool_name, args, workspaces = payload
    if tool_name not in FILE_TOOLS:
        return ""
    target = args.get(TARGET_KEY)
    if not isinstance(target, str) or not target:
        return ""
    path = pathlib.Path(target)
    # Only an absolute target is judged. Every captured payload carries one, and the
    # host's rule for resolving a relative spelling is not documented anywhere this
    # file could cite — resolving it against a workspace path of this adapter's own
    # choosing would judge a file in a directory nobody named. Silence, not a guess.
    if not path.is_absolute():
        return ""

    import hook_policy

    # Each workspace path is a root the session is bound by; any one of them drawing a
    # verdict refuses the whole call, and the target's own repo is checked inside
    # `verdict_for` regardless of which workspace the loop is on.
    for workspace in workspaces:
        state["cwd"] = workspace
        verdict = hook_policy.verdict_for([path], workspace)
        if verdict:
            return json.dumps({"decision": "deny",
                               "reason": hook_policy.deny_reason(*verdict)})
    return ""


def _emit(out):
    """Write the decision without letting stdout trouble grow a side effect.

    Antigravity proceeds on a non-zero exit (measured — see the module docstring), so
    unlike the Copilot adapter this guard's exit code cannot deny anything by accident.
    What a broken stdout could still do is put a traceback on stderr on every watched
    write in every session, which is noise an operator reads as breakage. Same two
    failure shapes as the Copilot `_emit` — a closed pipe raising BrokenPipeError at
    the write or at interpreter-exit flush, and a closed descriptor raising
    AttributeError because `sys.stdout` is None — and the same containment: catch
    everything, and point fd 1 at the null device so the interpreter's own final flush
    cannot fail either.
    """
    if out:
        try:
            from brief_common import utf8_stdio
            utf8_stdio()
        except Exception:
            pass
    try:
        if out:
            sys.stdout.write(out + "\n")
        sys.stdout.flush()
    except Exception:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
        except Exception:
            pass


def main():
    state = {}
    try:
        out = decide(state)
    except Exception:
        # Fails open on its own trouble, exactly like the other two adapters.
        # `hook_policy` is imported inside `decide()` for the same reason as in the
        # Copilot adapter: an ImportError at module scope would escape this handler
        # entirely, and although Antigravity would still let the call proceed, it
        # would do so with a traceback on stderr and no diagnostic trail.
        try:
            import hook_policy
            hook_policy.log_exception(state.get("cwd"))
        except Exception:
            pass
        return 0
    _emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
