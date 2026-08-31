# Continuous integration

The local check has one weakness no amount of care in the tool can fix: it is run by the
person who wants it to be green, and only when they remember. The Action moves the same
verdict to a place where the check runs whether or not anyone asks, and where the base it
compares against is chosen by git rather than by a field in the brief.

## What it does

```yaml
name: prompire
on: [pull_request]
jobs:
  scope:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write    # only needed for `comment: true`
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
      - uses: Wake360/prompire/.github/actions/prompire-verify@v0.13.0
        with:
          comment: 'true'
          artifact-name: prompire
```

It finds the brief committed under `.prompire/`, computes `git merge-base HEAD
origin/<base branch>`, runs `check_scope.py` against that revision, writes a job summary
and one annotation per finding, and fails the step when the verdict is not clean. The two
inputs above are optional: they also post that summary as a comment and upload it, the
JSON verdict and the brief as an artifact.

Put it first, before anything installs dependencies or builds. `check_scope.py` reads
untracked files as additions, so a build directory that is not in `.gitignore` becomes a
change outside `scope`.

## Committing the brief

The Action reads the brief out of the checkout, so the brief has to be in the repository:

```
.prompire/*
!.prompire/*.yaml
```

Briefs are tracked; `ACTIVE`, `ACTIVE.tombstones` and the rendered prompt and checklist
are not. One brief per pull request — the Action refuses when it finds two, because it
reads the whole difference between the merge-base and the head and cannot attribute that
to more than one of them.

## What the base means here

Locally, `--activate` writes a pin outside the brief so that `base_rev` cannot be
re-stamped after the fact. In CI that pin is unreachable: `.prompire/ACTIVE` is not
committed, and a fresh checkout has none. It is not needed. The base comes from
`git merge-base`, so `base_rev` is not consulted at all and re-stamping it buys nothing.
Every run is labelled `base given on the command line`.

`merge-base`, not `github.event.pull_request.base.sha`: the event's SHA is the base
branch's tip when the webhook fired, so diffing against it reports every commit the base
branch has gained since the branch point as a change belonging to this pull request, and
gives a different answer on every re-run. The merge-base does not move while the base
branch only moves forward.

## Inputs

| | |
|---|---|
| `brief` | Which brief. Empty discovers the single `.prompire/*.yaml`. |
| `base` | A revision to diff against, when the event's is not the one you want. |
| `strict` | Treat REVIEW findings as failures. Default off — see below. |
| `acceptance` | Also run the brief's acceptance commands. Default off — see below. |
| `acceptance-fail-on` | `failed`, or `any` to also fail when a command was refused. |
| `on-missing-brief` | `skip` (default) or `fail`. |
| `annotations` | Emit `::error`/`::warning` per finding. |
| `fail` | Fail the step on a non-clean verdict. Turn off to read the outputs instead. |
| `comment` | Post the summary as one pull-request comment. Default off — see below. |
| `artifact-name` | Upload the run's audit trail under this name. Empty (default) uploads nothing. |
| `python-version` | For `actions/setup-python`, or `system`. |

Outputs: `verdict` (`clean`, `findings`, `indeterminate`, `skipped`), `exit-code`,
`violations`, `reviews`, `base`, `base-source`, `brief`, `json`, `brief-file`,
`summary-file`, and the three `acceptance-*` counts.

`strict` is off by default because `tests_policy: named` and `authoring` each raise a
REVIEW unconditionally — that is the flag saying no checker can tell a repaired assertion
from a weakened one. Under `strict` a brief with either policy can never go green, so
turn it on only for briefs whose tests are `immutable`.

## The comment and the artifact

`comment: 'true'` posts the job summary — the same markdown, verbatim — as a comment on
the pull request, and edits that one comment on every later run instead of adding
another. The job needs `permissions: pull-requests: write`; without it the step fails.
It runs only on `pull_request`. On `pull_request_target` the step is skipped outright,
and with `acceptance` the run refuses before it gets that far.

Two limits are worth knowing before turning it on. A pull request from a fork gets a
read-only token whatever `permissions` says, so the step skips itself there rather than
fail an otherwise clean job; the job summary and the artifact still carry the verdict. And
the comment is one `gh pr comment --edit-last --create-if-none` call, which needs gh 2.63
or newer; GitHub-hosted runners are well past that, an old self-hosted image may not be,
and there is no fallback path.

`artifact-name` uploads three files, all of them written by the run itself into the
runner's temporary directory: the summary markdown, the raw `check_scope.py` JSON, and the
runner's own copy of the brief. That is the run's audit trail — what was claimed, what was
measured against it, and what the verdict was — readable after the logs have aged out.
Nothing is uploaded out of the workspace, and no path the brief itself names reaches the
upload step: a brief's filename is written by whoever opened the pull request, and a
filename can hold a newline. A refused run has no JSON and no copy to upload and uploads
the summary alone.

Both steps run after the verify step has already failed the job, because a failing verdict
is the one worth carrying out. The failure still propagates: the comment and the upload do
not turn the check green. If the run produced no report at all — a crash before the runner
wrote anything, not a refusal, which still writes one — both steps stand down instead of
failing a second time over a missing file, and a sticky comment from an earlier run stays
as it was, beside the red check.

## Failing closed

The PreToolUse hook fails open. It runs on every write on the machine, and a guard that
breaks unrelated sessions gets uninstalled. None of that reasoning transfers here: the
Action runs only in a repository that installed it, only on pull requests, and its output
is read as a verdict. So it fails closed. A base that will not resolve, a brief that will
not parse, two briefs, an ambiguous merge-base — each produces no verdict and a red
check, never a green one.

The one case that is neither is a repository with no brief at all. That reports `skipped`
and does not fail, because the repository made no claim; a green tick there would read as
a diff that was checked.

A shallow checkout is the common misconfiguration. The Action tries one `--unshallow`
before giving up, and when that fails it says `fetch-depth: 0` in its own words —
`git rev-parse --verify --quiet` returns nothing on stderr, so the refusal it would
otherwise pass on is blank.

## What it does not do

The Action checks a pull request against a brief the pull request itself contains. It
fixes one thing the local run cannot: the base comes from `git merge-base`, so
re-stamping `base_rev` buys nothing. Everything else in the brief is still written by
whoever wrote the change — a wider `scope`, one `dirty_baseline` entry, or
`tests_policy: authoring` each produce a clean verdict, and a brief added by the pull
request draws no flag at all, because the brief-changed REVIEW fires on a modification
and not on an addition. Read the brief in the diff alongside the annotations.

It checks the whole difference between the merge-base and the head, so it is right only
when the pull request is one task. A branch carrying two tasks reports the second one's
work as violations of the first one's brief, and every violation it prints is then
somebody else's correct work. In a repository that squash-merges, a branch cut from a
previously merged branch has its merge-base below the squash commit, which brings the
earlier task's changes into range; nothing in the Action detects that.

Acceptance commands are off by default and run through the shell as written. Turning them
on runs code from the pull request on the runner, and the results are compared against
the `baseline:` block in the same pull request's brief. Do not turn it on for pull
requests from forks. On `pull_request_target` the Action refuses outright, because there
the runner holds a write-scoped token and the repository's secrets.

Findings are path-level. Annotations carry a file but no line, because the checker never
established one.
