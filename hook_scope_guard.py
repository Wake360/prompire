#!/usr/bin/env python3
"""Claude Code PreToolUse adapter: refuse a write the active brief's boundary does not
allow.

Claude Code feeds the tool call in as JSON on stdin. Exit 2 blocks the call and returns
stderr to the agent; exit 0 lets it through.

This file is protocol only. The decision — which paths a brief speaks for, and what the
boundary means — lives in `hook_policy.verdict_for()`, shared byte-for-byte with the
GitHub Copilot CLI adapter next door, which in turn calls the same `boundary_verdict`
and `tests_verdict` that `check_scope.py` calls afterwards. There is exactly one
interpretation of `scope` in this tree and it is not in here.

This is the half of B7 that needs neither the agent's cooperation nor a post-mortem.
check_scope.py is still the authority afterwards: it sees the whole diff, this sees one
path before it is written.

Fails open, deliberately. It runs on every Write and Edit in every project on the
machine, so a missing repo, an unreadable brief or a parse error exits 0 rather than
bricking an unrelated session. It fails closed only on a definite verdict.
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import hook_policy

WATCHED = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def target_of(tool_input, cwd):
    """The path this call would write, or None if the payload names none.

    None also covers a `file_path` that isn't a string: `pathlib.Path()` raises TypeError
    on one, and an uncaught exception here fails the whole call open by way of `main()`.
    A defined branch is better than a crash, and open is the right answer for this one —
    no write tool executes a non-string path, so there is no write to judge.

    The two keys are checked independently rather than chained with `or`, so a truthy
    non-string in the first cannot mask a real path in the second. Today no such payload
    reaches a hook — every watched tool's schema declares `additionalProperties: false` —
    but that is the schemas' doing, not this function's, and a laxer write tool added to
    WATCHED would otherwise turn it into a live fail-open on a real write.
    """
    paths = [v for v in (tool_input.get("file_path"), tool_input.get("notebook_path"))
             if isinstance(v, str) and v]
    if not paths:
        return None
    p = pathlib.Path(paths[0])
    return p if p.is_absolute() else pathlib.Path(cwd) / p


def block(rel, rule, message, fix):
    sys.stderr.write(f"BLOCKED by Prompire scope guard [{rule}]: {rel}\n{message}\n")
    if fix:
        sys.stderr.write(f"-> {fix}\n")
    sys.stderr.write(hook_policy.CONTRACT_LINE + "\n")
    return 2


def decide(state):
    data = json.load(sys.stdin)
    if data.get("tool_name") not in WATCHED:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    state["cwd"] = cwd
    target = target_of(data.get("tool_input") or {}, cwd)
    if target is None:
        return 0
    verdict = hook_policy.verdict_for([target], cwd)
    return block(*verdict) if verdict else 0


def main():
    state = {}
    try:
        return decide(state)
    except Exception:
        # Fails open on its own trouble, by design — see the module docstring. A bug
        # here is also caught loudly by check_scope.py, which shares the verdict
        # functions; log_exception is the signal for this half specifically.
        hook_policy.log_exception(state.get("cwd"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
