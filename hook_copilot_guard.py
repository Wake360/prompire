#!/usr/bin/env python3
"""GitHub Copilot CLI preToolUse adapter: refuse a file write the active brief's
boundary does not allow.

Protocol only. The decision is `hook_policy.verdict_for()`, the same call
`hook_scope_guard.py` makes for Claude Code and the same `boundary_verdict` /
`tests_verdict` `check_scope.py` makes afterwards. There is no Copilot interpretation of
`scope` in this file, and there must never be one.

## Why this cannot just reuse the Claude adapter

The two hosts disagree about what a failing hook means, in opposite directions:

- Claude Code: exit 2 blocks and hands stderr to the agent, exit 0 allows. Every other
  outcome — a crash, a traceback, exit 1 — allows. Prompire's guard is *required* to
  fail open on its own trouble, so Claude Code's convention already matches the
  requirement and `hook_scope_guard.py` needs no translation.
- Copilot CLI: a command `preToolUse` hook is fail-CLOSED. A crash, exit 2, or any other
  non-zero exit denies the tool call. A guard that runs on every write on the machine
  and denies whenever it has a bug is a guard that gets uninstalled within the hour —
  and the fail-open rule is not a convenience, it is what keeps every degradation
  pointing away from enforcing something nobody decided.

So this adapter translates explicitly, and the translation is the whole file:

    definite Prompire violation  -> exit 0, one JSON object, permissionDecision "deny"
    everything else              -> exit 0, empty stdout

"Everything else" means every one of: an in-scope path, no brief armed, an irrelevant
tool, no repository, an unreadable or malformed brief, a payload this file cannot
interpret, a patch it cannot parse, and any unexpected exception. All of them are the
same answer, and that answer is *not* `permissionDecision: "allow"`. Allowing is a
decision this hook has no standing to make: it would skip the permission prompt Copilot
would otherwise show the operator, which is a real approval bought with our silence.
Emitting nothing lets the call continue through Copilot's normal permission flow, where
the human still gets asked. Never widen this to "allow" to make a test read better.

Nothing is written to stdout until the decision is final, so an exception thrown halfway
through cannot leave a truncated JSON object on the wire — Copilot would fail to parse
it, and an unparseable decision from a fail-closed host is a denial nobody intended.

## What this does not cover

`bash` and `powershell` are deliberately not matched. A shell write bypasses this
adapter exactly as it bypasses the Claude one; `check_scope.py` on the real git diff is
what sees it afterwards. Do not add shell interception here — inspecting a command line
for the files it will touch is a different and much weaker claim than reading a diff,
and pretending otherwise is worse than the documented gap.
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))


# Path arguments, by tool. Every key here is a documented field, not a guess from a
# name:
#
#   `path`          — GitHub's own preToolUse example reads `.toolArgs | .path` for the
#                     `create` and `edit` tools (docs.github.com, "Using hooks with
#                     GitHub Copilot CLI for predictable, policy-compliant execution").
#   `file_path`     — the VS Code / Claude-compatible spelling, which is what a
#                     PascalCase `PreToolUse` entry reusing a Claude-format hook sends;
#                     it is the field `hook_scope_guard.py` has always read.
#   `notebook_path` — the same, for the Claude `NotebookEdit` shape.
#   `input`/`patch` — the patch envelope for `apply_patch`; OpenAI's apply_patch tool
#                     takes the whole envelope as a single string argument.
#
# A tool call whose arguments contain none of the keys its entry names is a shape this
# file does not know, and an unknown shape is answered with silence, never with a
# verdict. See `paths_of`.
PATH_KEYS = ("path", "file_path", "notebook_path")
PATCH_KEYS = ("input", "patch")

# Copilot CLI runtime tool names that change files, and the Claude-compatible names the
# same calls carry under a PascalCase `PreToolUse` entry (docs.github.com, hooks
# reference, "Runtime tool -> Claude tool name"):
#
#     create                                  -> Write
#     edit, str_replace_editor, apply_patch    -> Edit
#
# `view`, `grep`, `rg`, `glob`, `web_fetch`, `web_search`, `ask_user`, `update_todo` and
# `task` do not write files and are not listed. `bash` and `powershell` do, and are
# deliberately not listed — see the module docstring.
#
# Split in two because the hook-config matcher has to name one set or the other, and a
# tool added here but not to the matcher is a tool the hook is never invoked for at all
# — a silent hole that looks exactly like support. `tests/docs.py` compares
# `RUNTIME_FILE_TOOLS` against the matchers in `examples/hooks/` so the two cannot drift.
RUNTIME_FILE_TOOLS = ("create", "edit", "str_replace_editor", "apply_patch")
CLAUDE_FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
FILE_TOOLS = RUNTIME_FILE_TOOLS + CLAUDE_FILE_TOOLS

# `str_replace_editor` carries the operation in `command` (the Anthropic text-editor
# shape it is named after: view | create | str_replace | insert | undo_edit). Only
# `view` reads without writing; everything else, including `undo_edit`, changes the file
# at `path`. An unrecognised command is not assumed to be harmless — it falls through to
# the ordinary path extraction and is judged like any other write.
EDITOR_READ_COMMANDS = ("view",)

_PATCH_HEADERS = ("*** Add File: ", "*** Update File: ", "*** Delete File: ",
                  "*** Move to: ")


def parse_patch(text):
    """Every path a V4A patch envelope would add, update, rename or delete — or None if
    this string is not an envelope this function can read.

    None is the important return. A patch we cannot parse is a set of file changes we
    cannot enumerate, and the honest answer to "is any of them out of scope?" is then "I
    do not know", which this adapter renders as silence. Guessing from the first
    recognisable path would be worse than not looking: a multi-file patch whose second
    file is forbidden would read as compliant.

    Headers are matched at column 0, never on a stripped line. V4A content lines are
    prefixed with a space, `+` or `-`, so a context line that happens to quote
    `*** Update File: secrets.env` — a diff of this very docstring would — stays content
    and does not become a path the guard then refuses. Over-collecting is not the safe
    direction here: it refuses writes the brief actually permits, which is how a guard
    earns its uninstall.
    """
    if "*** Begin Patch" not in text:
        return None
    paths = []
    for line in text.splitlines():
        for prefix in _PATCH_HEADERS:
            if line.startswith(prefix):
                p = line[len(prefix):].strip()
                if p:
                    paths.append(p)
    # `*** Move to:` names the destination and the preceding `*** Update File:` the
    # source; both are collected, because a rename out of `scope` and a rename into
    # `forbidden` are each a change the brief has something to say about.
    return paths or None


def paths_of(tool_name, args):
    """Every path this tool call would create, replace, rename, delete or modify, as
    strings, or an empty list when this call names none we can identify.

    An empty list is not "no paths were touched" — it is "this shape is not one this
    adapter can read", and the caller turns it into silence rather than a verdict.
    """
    if tool_name == "str_replace_editor":
        command = args.get("command")
        if isinstance(command, str) and command in EDITOR_READ_COMMANDS:
            return []
    if tool_name == "apply_patch":
        for key in PATCH_KEYS:
            raw = args.get(key)
            if isinstance(raw, str) and raw:
                parsed = parse_patch(raw)
                if parsed:
                    return parsed
                # A patch argument that is present but unreadable stops here rather than
                # falling through to `path`: a call that carries an envelope is a
                # multi-file call, and answering it from one incidental path field would
                # be exactly the partial reading `parse_patch` refuses to do.
                return []
    return [v for v in (args.get(k) for k in PATH_KEYS) if isinstance(v, str) and v]


def read_payload(raw):
    """(tool_name, args, cwd) from either documented preToolUse payload shape, or None
    if this is not a payload this adapter can act on.

    Two shapes, per the hooks reference: the native camelCase event
    (`toolName`/`toolArgs`, no event-name field) and the PascalCase VS Code-compatible
    one (`hook_event_name: "PreToolUse"`, `tool_name`/`tool_input`). Both are accepted;
    the camelCase spelling wins if a payload somehow carries both, since it is the
    native one.

    `toolArgs` is accepted as an object *and* as a JSON-encoded string. The reference
    types it as an object, and GitHub's own worked example parses it with a second `jq`
    call because it arrives as a string ("Because toolArgs is a JSON string, your script
    must parse it before reading fields"). Both are real; reading only one of them would
    make this adapter silently blind on whichever host version disagrees with it.
    """
    if not isinstance(raw, dict):
        return None
    event = raw.get("hook_event_name")
    if event is not None and event != "PreToolUse":
        return None
    tool_name = next((v for v in (raw.get("toolName"), raw.get("tool_name"))
                      if isinstance(v, str) and v), None)
    if tool_name is None:
        return None
    args = _as_args(raw.get("toolArgs"))
    if args is None:
        args = _as_args(raw.get("tool_input"))
    if args is None:
        return None
    cwd = raw.get("cwd")
    # No cwd, no verdict. A relative `path` cannot be resolved without it, and resolving
    # it against this process's own cwd would judge a file in a directory nobody named.
    if not isinstance(cwd, str) or not cwd:
        return None
    return tool_name, args, cwd


def _as_args(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def deny_reason(rel, rule, message, fix, contract_line):
    """The Claude adapter's three sentences, on one line.

    Same words on both hosts on purpose, and `contract_line` comes from
    `hook_policy.CONTRACT_LINE` rather than being repeated here — the wording is the part
    an agent reads and acts on, and a second copy is how the two hosts' explanations
    quietly stop agreeing. Only the framing differs: Claude Code takes this on stderr
    with exit 2, Copilot CLI takes it in `permissionDecisionReason`. Deterministic to the
    byte, so tests can pin it.
    """
    text = f"BLOCKED by Prompire scope guard [{rule}]: {rel} — {message}"
    if fix:
        text += f" -> {fix}"
    return f"{text}. {contract_line}"


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
    tool_name, args, cwd = payload
    state["cwd"] = cwd
    if tool_name not in FILE_TOOLS:
        return ""
    paths = paths_of(tool_name, args)
    if not paths:
        return ""

    import hook_policy

    targets = []
    for p in paths:
        path = pathlib.Path(p)
        targets.append(path if path.is_absolute() else pathlib.Path(cwd) / path)
    verdict = hook_policy.verdict_for(targets, cwd)
    if not verdict:
        return ""
    return json.dumps({"permissionDecision": "deny",
                       "permissionDecisionReason": deny_reason(
                           *verdict, contract_line=hook_policy.CONTRACT_LINE)})


def _emit(out):
    """Write the decision, and never let anything about stdout become a non-zero exit.

    Copilot reads any non-zero exit as a denial, so a refusal produced by trouble with
    the output stream is a refusal nobody decided on — the one thing this adapter exists
    to make impossible. Two distinct ways stdout can be unusable, and they raise
    different things:

    - **Closed pipe** (Copilot stopped reading; a killed session). The write raises
      `BrokenPipeError`, and so does Python's own flush at interpreter exit — which
      prints `Exception ignored on flushing sys.stdout` to stderr and exits **120**.
    - **Closed descriptor** (fd 1 closed outright, `>&-`). Python sets `sys.stdout` to
      `None`, so `sys.stdout.write` raises `AttributeError` — not an `OSError` at all.
      This one fires on the NEUTRAL path too, since the flush below runs whether or not
      there is anything to write, so it would have denied ordinary in-scope writes.

    Hence `except Exception` rather than an enumerated tuple, which is the correct shape
    exactly here and nowhere else in this file: the function's whole contract is that no
    failure of it may reach the exit code, and enumerating the failures is how the
    second one got missed the first time. Guarding the write alone is also not enough —
    the interpreter flushes again on the way out, outside every `try` in this module — so
    on failure fd 1 is pointed at the null device, making that final flush a no-op it
    cannot fail.

    `json.dumps` escapes non-ASCII, so today's decision is pure ASCII and encodes under
    any code page. The reconfigure below is therefore defence for the next person who
    reaches for `ensure_ascii=False` to make a path readable, not a fix for a live bug —
    and it is lazy and swallowed for the same reasons as `hook_scope_guard.block()`: a
    module-scope `brief_common` import would drag in PyYAML and make
    `hook_policy`'s unconditional `.prompire/ACTIVE` verdicts depend on it.

    It is also behind `if out:` rather than run unconditionally. This function is called on
    the neutral path too — with `out == ""`, on every file write in every Copilot session —
    and importing `brief_common` there would pay for PyYAML exactly where `hook_policy`
    goes out of its way not to. Nothing is printed on that path, so there is nothing to
    reconfigure for.
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
        # Fails open on its own trouble, exactly like the Claude adapter — but here that
        # takes an explicit exit 0 and an empty stdout, because Copilot CLI reads a
        # crash or any non-zero exit as a denial. `hook_policy` is imported inside
        # `decide()` for the same reason: an ImportError at module scope would escape
        # this handler entirely and deny every file write in every Copilot session on
        # the machine.
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
