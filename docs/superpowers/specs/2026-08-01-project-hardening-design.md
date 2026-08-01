# Project Hardening Design

## Goal

Close the drafting-isolation gap and improve command output, CI integrity, test-runner
diagnostics, status usability, and README accuracy without changing Prompire's brief
schema or enforcement model.

## Scope

The work has six independently reviewable changes:

1. Isolate every agent-assisted draft from the source repository.
2. Render copy-paste commands correctly on POSIX and Windows.
3. Pin third-party GitHub Actions by full commit SHA.
4. Give each test suite a timeout and report its duration.
5. Let `prompire status` resolve the current repository without a brief argument.
6. Finish the current README edit and document the resulting behavior.

The existing `brief_common` to `hook_policy` to host-adapter seams remain unchanged.
No package-layout refactor, schema field, dependency, or new hook is included.

## Draft isolation

`prompire draft --agent` and `prompire draft --agent-cmd` will run the selected process
inside a temporary repository snapshot instead of the source checkout. The snapshot
will contain the source checkout's current Git-visible files: tracked files in their
current working-tree state and untracked, non-ignored files. Deleted tracked files stay
absent. Symlinks remain symlinks and executable files retain their executable bit.

The snapshot will contain fresh Git metadata and one synthetic commit so repository-aware
agents can inspect paths and history without reaching the source checkout. Ignored files
and the source `.git` directory will not be copied. The host process receives the
snapshot as its working directory, and `{root}` expands to the snapshot path.

The snapshot is removed after success, refusal, non-zero agent exit, timeout, or malformed
output. Cleanup failure must not replace the agent result or mutate the source checkout.
The existing before/after `git status` comparison becomes unnecessary and is removed.

This design protects the source tree structurally. It does not claim to sandbox network,
credentials, or paths outside the snapshot that an arbitrary command can reach.

## Command rendering

A small internal formatter will accept an argument vector and return a command for human
copy-paste. It will use `shlex.join` on POSIX and `subprocess.list2cmdline` on Windows.
Prepared, drafted, and other next-step output will use this formatter. Commands passed to
subprocesses remain argument vectors and do not pass through the formatter.

## CI action pinning

Third-party `uses:` entries in the ordinary test and Prompire workflows will use full
commit SHAs, with the release tag retained in an inline comment. The already-pinned
publish workflow is the model. Local `./.github/actions/prompire-verify` usage remains a
local path.

## Test-runner diagnostics

`tests/run_all.py` will define one timeout for each suite invocation. A timed-out suite
will be recorded as `FAIL`, later suites will still run, and the summary will identify
the timeout. Each suite and summary row will include elapsed seconds. Output remains
captured so passing suites stay quiet under `--quiet`; failed and timed-out suites print
their available output.

The timeout is a runner safety limit, not a performance assertion. It will be set high
enough for the current macOS, Linux, and Windows CI matrix.

## Status interface

The `status` positional argument becomes optional and defaults to `.`. When supplied, it
keeps its current behavior: the path is used only to locate the repository. Text and JSON
output shapes and exit codes remain unchanged.

## Documentation

The current uncommitted README changes are user-owned and must be preserved. The work will
rewrap the long sentence in the "What this is not" section and update drafting text to say
that agent-assisted drafting runs in a disposable Git-visible snapshot. Documentation
must not imply that ignored files are copied or that arbitrary commands are sandboxed from
the rest of the machine.

## Testing

Tests will be written before each behavior change.

- CLI tests will prove that a drafting agent can mutate its snapshot but cannot change an
  already-dirty source file, an ignored source file, or an untracked source file.
- CLI tests will prove cleanup after success, failure, timeout, and malformed output.
- CLI tests will pin POSIX and Windows display quoting without executing the displayed
  string.
- CLI tests will cover `prompire status`, `prompire status .`, and JSON output.
- A new `tests/runner.py` suite will drive the runner with short synthetic suites to
  prove timeout continuation and duration reporting without waiting for the production
  timeout. `tests/run_all.py` and the maintaining guide will list this thirteenth suite.
- Documentation tests will require full-SHA third-party action references in all workflows.
- The full existing suite remains the final regression gate.

## Success criteria

`python3 tests/cli.py`, `python3 tests/docs.py`, and the focused test-runner regression
tests exit 0 after their corresponding changes. `python3 tests/run_all.py --quiet` exits
0 and prints `pass` for all thirteen suites. `git diff --check` prints nothing. Only the
files named by the implementation plan and the user's existing README edit change.
