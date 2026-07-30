#!/usr/bin/env python3
"""The GitHub Action: real repos, real runner, real annotations.

Run: python3 tests/ci.py [--verbose]
Exit 0 = every case holds.

Two layers, because they have different honesty. `action.yml` is wiring no test can
execute without a runner, so it is only parsed and cross-checked. `runner.py` holds every
decision — which base, which brief, what fails closed — and is driven here for real,
against fixture repos, with a temporary GITHUB_OUTPUT/GITHUB_STEP_SUMMARY/GITHUB_EVENT_PATH.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
ACTION = SKILL / ".github" / "actions" / "prompire-verify"
sys.path.insert(0, str(HERE))

import fixtures  # noqa: E402

VERBOSE = "--verbose" in sys.argv
CASES = []

# The convention the Action depends on: briefs are tracked, guard state is not.
TRACKED_BRIEFS = ".prompire/*\n!.prompire/*.yaml\n__pycache__/\n"

BRIEF = """
goal: Fix the off-by-one in total().
scope:
  - src/cart.py
forbidden:
  - golden/**
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
"""


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


class Checks:
    def __init__(self):
        self.fails = []

    def ok(self, cond, msg):
        if not cond:
            self.fails.append(msg)


def git(root, *args):
    return fixtures.git(root, *args)


def commit(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD").strip()


def repo(tmp, brief_body=BRIEF, name="task", commit_brief=True):
    """A fixture repo whose `.prompire/*.yaml` is tracked. Returns (root, head)."""
    root = fixtures.build(pathlib.Path(tmp) / "repo")
    fixtures.write(root, ".gitignore", TRACKED_BRIEFS)
    if commit_brief and brief_body is not None:
        write_brief(root, name, brief_body)
    head = commit(root, "tracked briefs")
    return root, head


def write_brief(root, name, body):
    p = pathlib.Path(root) / ".prompire" / f"{name}.yaml"
    p.parent.mkdir(exist_ok=True)
    text = body.lstrip()
    if not re.search(r"^base_rev:", text, re.M):
        head = git(root, "rev-parse", "HEAD").strip()
        text = text.rstrip("\n") + f"\nbase_rev: {head[:12]}\n"
    p.write_text(text, encoding="utf-8")
    return p


def run(root, tmp, event=None, event_name="", **inputs):
    """Drive runner.py the way the composite step does.

    Returns an object with .code, .out, .outputs (parsed GITHUB_OUTPUT) and .summary.
    """
    work = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    out_file, sum_file = work / "output", work / "summary"
    out_file.touch()
    sum_file.touch()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PROMPIRE_", "GITHUB_", "RUNNER_"))}
    env.update({
        "PROMPIRE_HOME": str(SKILL),
        "PROMPIRE_PATH": str(root),
        "GITHUB_OUTPUT": str(out_file),
        "GITHUB_STEP_SUMMARY": str(sum_file),
        "GITHUB_EVENT_NAME": event_name,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    if event is not None:
        payload = work / "event.json"
        payload.write_text(json.dumps(event), encoding="utf-8")
        env["GITHUB_EVENT_PATH"] = str(payload)
    for k, v in inputs.items():
        env["PROMPIRE_" + k.upper().replace("-", "_")] = str(v)

    r = subprocess.run([sys.executable, str(ACTION / "runner.py")],
                       capture_output=True, text=True, env=env, cwd=str(root))

    class Result:
        code = r.returncode
        out = r.stdout
        err = r.stderr
        outputs = dict(
            line.split("=", 1)
            for line in out_file.read_text(encoding="utf-8").splitlines() if "=" in line)
        summary = sum_file.read_text(encoding="utf-8")
    return Result


def errors(res):
    return [ln for ln in res.out.splitlines() if ln.startswith("::error")]


def warnings(res):
    return [ln for ln in res.out.splitlines() if ln.startswith("::warning")]


# --------------------------------------------------------------------------- cases

@case("clean-in-scope-change-passes")
def _(tmp, c):
    root, head = repo(tmp)
    fixtures.write(root, "src/cart.py", "def total(items):\n    return sum(items)\n")
    commit(root, "fix the off-by-one")
    r = run(root, tmp, base=head)
    c.ok(r.code == 0, f"expected exit 0, got {r.code}: {r.out}{r.err}")
    c.ok(r.outputs.get("verdict") == "clean", f"verdict was {r.outputs.get('verdict')}")
    c.ok(not errors(r), f"a clean run must not annotate an error: {errors(r)}")
    c.ok(head[:12] in r.summary or head in r.summary,
         f"the summary must name the base it used:\n{r.summary}")


@case("out-of-scope-change-fails-and-annotates")
def _(tmp, c):
    root, head = repo(tmp)
    fixtures.write(root, "src/report.py", "# touched\n")
    commit(root, "edit outside scope")
    r = run(root, tmp, base=head)
    c.ok(r.code == 1, f"expected exit 1, got {r.code}: {r.out}{r.err}")
    c.ok(r.outputs.get("violations") == "1", f"violations={r.outputs.get('violations')}")
    c.ok(any("file=src/report.py" in e for e in errors(r)),
         f"expected an annotation on src/report.py: {errors(r)}")


@case("forbidden-path-is-a-violation")
def _(tmp, c):
    root, head = repo(tmp)
    fixtures.write(root, "golden/report.txt", "apples: 4\npears: 5\n")
    commit(root, "rewrite the golden file")
    r = run(root, tmp, base=head)
    c.ok(r.code == 1, f"expected exit 1, got {r.code}")
    c.ok(any("golden/report.txt" in e for e in errors(r)),
         f"expected an annotation on the forbidden path: {errors(r)}")


@case("uncommitted-work-counts-too")
def _(tmp, c):
    root, head = repo(tmp)
    fixtures.write(root, "src/report.py", "# not committed\n")
    r = run(root, tmp, base=head)
    c.ok(r.code == 1, "an uncommitted out-of-scope write is still a violation")


@case("brief-edited-after-the-base-is-a-review")
def _(tmp, c):
    root, head = repo(tmp)
    p = pathlib.Path(root) / ".prompire" / "task.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace(
        "  - src/cart.py", "  - src/cart.py\n  - src/report.py"), encoding="utf-8")
    commit(root, "widen the scope")
    r = run(root, tmp, base=head)
    c.ok(r.code == 0, f"a review alone must not fail a default run, got {r.code}")
    c.ok(any(".prompire/task.yaml" in w for w in warnings(r)),
         f"expected a review annotation on the brief: {warnings(r)}")
    strict = run(root, tmp, base=head, strict="true")
    c.ok(strict.code == 1, f"--strict must fail on that review, got {strict.code}")


@case("brief-added-by-the-diff-draws-nothing")
def _(tmp, c):
    # Documents a real gap rather than a feature: check_scope.py flags M/R/D on the
    # brief and lets A fall through, which is the shape of every first pull request.
    root, head = repo(tmp, brief_body=None, commit_brief=False)
    write_brief(root, "task", BRIEF)
    commit(root, "add the brief")
    r = run(root, tmp, base=head)
    c.ok(r.code == 0, f"expected exit 0, got {r.code}: {r.out}")
    c.ok(not any(".prompire" in w for w in warnings(r)),
         "an added brief draws no finding today; if this starts failing the gap was "
         f"closed and this case should become the opposite assertion: {warnings(r)}")


@case("tests-policy-review-carries-no-file")
def _(tmp, c):
    root, head = repo(tmp, brief_body=BRIEF.replace(
        "tests_policy: immutable",
        "tests_policy: named\ntests_editable:\n  - tests/test_total.py\n"
        "  - tests/test_cart.py"))
    r = run(root, tmp, base=head)
    c.ok(r.code == 0, f"the unconditional tests_policy review must not fail a default "
                      f"run, got {r.code}: {r.out}")
    marks = [w for w in warnings(r) if "tests_policy" in w]
    c.ok(marks, f"expected the tests_policy review: {warnings(r)}")
    c.ok(all("file=" not in w for w in marks),
         f"a comma-joined glob list is not a file and must not carry file=: {marks}")
    strict = run(root, tmp, base=head, strict="true")
    c.ok(strict.code == 1, "--strict is red by construction for `named` — if this "
                           "changes, the action.yml description is now wrong")


@case("missing-brief-skips-and-never-passes-silently")
def _(tmp, c):
    root, head = repo(tmp, brief_body=None, commit_brief=False)
    r = run(root, tmp, base=head)
    c.ok(r.code == 0, f"skip is the default, got {r.code}")
    c.ok(r.outputs.get("verdict") == "skipped",
         f"verdict must be `skipped`, not `clean`: {r.outputs}")
    c.ok("not a passing verdict" in r.summary,
         f"the summary must say a skip is not a pass:\n{r.summary}")
    hard = run(root, tmp, base=head, on_missing_brief="fail")
    c.ok(hard.code == 2, f"on-missing-brief: fail must refuse, got {hard.code}")


@case("two-briefs-refuse-and-name-both")
def _(tmp, c):
    root, head = repo(tmp)
    write_brief(root, "second", BRIEF)
    commit(root, "a second brief")
    r = run(root, tmp, base=head)
    c.ok(r.code == 2, f"expected a refusal, got {r.code}")
    c.ok("task.yaml" in r.summary and "second.yaml" in r.summary,
         f"both briefs must be named:\n{r.summary}")
    c.ok(r.outputs.get("verdict") == "indeterminate", f"{r.outputs}")
    picked = run(root, tmp, base=head, brief=".prompire/second.yaml")
    c.ok(picked.code == 0, f"naming one must resolve it, got {picked.code}: {picked.out}")


@case("no-base-refuses-and-never-diffs-against-head")
def _(tmp, c):
    root, _ = repo(tmp)
    fixtures.write(root, "src/report.py", "# out of scope\n")
    commit(root, "out of scope")
    r = run(root, tmp)
    c.ok(r.code == 2, f"no event and no base input must refuse, got {r.code}")
    c.ok(r.outputs.get("violations") == "0",
         "a refusal reports no findings — it never diffed against anything")
    c.ok("HEAD" in r.summary, f"the refusal must say why HEAD is not a fallback:\n{r.summary}")


@case("base-that-is-not-a-commit-refuses")
def _(tmp, c):
    root, _ = repo(tmp)
    r = run(root, tmp, base="deadbeefdeadbeef")
    c.ok(r.code == 2, f"expected a refusal, got {r.code}")
    c.ok("fetch-depth: 0" in r.summary,
         f"the refusal must name the checkout setting that causes it:\n{r.summary}")


@case("shallow-clone-deepens-rather-than-guessing")
def _(tmp, c):
    root, head = repo(tmp)
    fixtures.write(root, "src/cart.py", "def total(items):\n    return sum(items)\n")
    commit(root, "fix")
    shallow = pathlib.Path(tmp) / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth=1", root.as_uri(), str(shallow)],
                   capture_output=True, text=True)
    if not (shallow / ".git").exists():
        return  # git refused a local shallow clone; nothing to assert
    r = run(shallow, tmp, base=head)
    c.ok(r.code == 0, f"one --unshallow is allowed to rescue the run, got {r.code}: "
                      f"{r.summary}")
    c.ok(r.outputs.get("base") == head,
         f"and it must land on the base that was asked for: {r.outputs.get('base')}")


@case("shallow-clone-with-no-remote-refuses-with-its-own-message")
def _(tmp, c):
    root, head = repo(tmp)
    fixtures.write(root, "src/report.py", "# out of scope\n")
    commit(root, "out of scope")
    shallow = pathlib.Path(tmp) / "cut-off"
    subprocess.run(["git", "clone", "-q", "--depth=1", root.as_uri(), str(shallow)],
                   capture_output=True, text=True)
    if not (shallow / ".git").exists():
        return
    git(shallow, "remote", "remove", "origin")
    r = run(shallow, tmp, base=head)
    c.ok(r.code == 2, f"a base it cannot reach must refuse, got {r.code}")
    c.ok("fetch-depth: 0" in r.summary,
         f"the message must be the action's own — git's is empty here:\n{r.summary}")
    c.ok(r.outputs.get("violations") == "0",
         "and it must not have diffed against anything")


@case("pull-request-event-uses-the-merge-base")
def _(tmp, c):
    root, head = repo(tmp)
    git(root, "checkout", "-q", "-b", "feature")
    fixtures.write(root, "src/cart.py", "def total(items):\n    return sum(items)\n")
    commit(root, "fix on the branch")
    # main moves on after the branch was cut; the merge-base must not follow it
    git(root, "checkout", "-q", "master")
    fixtures.write(root, "src/report.py", "# unrelated work on the base branch\n")
    moved = commit(root, "unrelated work on master")
    git(root, "checkout", "-q", "feature")
    event = {"pull_request": {"base": {"ref": "master", "sha": moved}}}
    r = run(root, tmp, event=event, event_name="pull_request")
    c.ok(r.code == 0,
         f"the base branch moving must not turn its work into this PR's violations, "
         f"got {r.code}: {r.out}")
    c.ok(r.outputs.get("base", "").startswith(head[:12]),
         f"expected the merge-base {head[:12]}, got {r.outputs.get('base')}")


@case("push-event-onto-a-new-ref-refuses")
def _(tmp, c):
    root, _ = repo(tmp)
    r = run(root, tmp, event={"before": "0" * 40}, event_name="push")
    c.ok(r.code == 2, f"a created ref has no previous revision, got {r.code}")


@case("acceptance-is-off-until-asked-for")
def _(tmp, c):
    root, head = repo(tmp)
    r = run(root, tmp, base=head)
    c.ok(r.outputs.get("acceptance-passed") == "",
         f"acceptance must not run by default: {r.outputs}")
    on = run(root, tmp, base=head, acceptance="true")
    c.ok(on.outputs.get("acceptance-passed") == "1",
         f"expected one passing criterion: {on.outputs} {on.out}")
    c.ok(on.code == 0, f"expected exit 0, got {on.code}: {on.out}")


@case("acceptance-not-run-is-a-choice")
def _(tmp, c):
    root, head = repo(tmp, brief_body=BRIEF.replace(
        "  - cmd: python3 -m unittest -q tests.test_cart\n    expect: exit 0",
        "  - cmd: curl https://example.invalid/health\n    expect: exit 0"))
    lenient = run(root, tmp, base=head, acceptance="true")
    c.ok(lenient.outputs.get("acceptance-not-run") == "1",
         f"a networky command must be refused, not run: {lenient.outputs}")
    c.ok(lenient.code == 0, f"acceptance-fail-on: failed ignores it, got {lenient.code}")
    strict = run(root, tmp, base=head, acceptance="true", acceptance_fail_on="any")
    c.ok(strict.code == 1, f"acceptance-fail-on: any must fail on it, got {strict.code}")


@case("pull-request-target-with-acceptance-refuses")
def _(tmp, c):
    root, head = repo(tmp)
    r = run(root, tmp, base=head, acceptance="true",
            event={"pull_request": {"base": {"ref": "master", "sha": head}}},
            event_name="pull_request_target")
    c.ok(r.code == 2, f"expected a refusal, got {r.code}")
    c.ok("pull_request" in r.summary, f"the refusal must name the fix:\n{r.summary}")


@case("a-refusal-emits-no-json-and-parses-none")
def _(tmp, c):
    root, _ = repo(tmp)
    r = run(root, tmp, base="deadbeefdeadbeef")
    c.ok(not r.out.strip().startswith("{"),
         f"check_scope.py refuses in prose; the runner must not pretend otherwise: {r.out}")
    c.ok("Traceback" not in r.err, f"a refusal must not surface as a crash: {r.err}")


@case("annotation-text-is-escaped")
def _(tmp, c):
    sys.path.insert(0, str(ACTION))
    import runner
    c.ok(runner.esc_data("a%b\nc") == "a%25b%0Ac", runner.esc_data("a%b\nc"))
    c.ok(runner.esc_prop("a,b:c") == "a%2Cb%3Ac", runner.esc_prop("a,b:c"))
    c.ok(runner.esc_prop("100%") == "100%25", runner.esc_prop("100%"))


@case("action-yml-wiring-matches-the-runner")
def _(tmp, c):
    import yaml
    spec = yaml.safe_load((ACTION / "action.yml").read_text(encoding="utf-8"))
    c.ok(spec["runs"]["using"] == "composite", "the action must stay composite")
    steps = spec["runs"]["steps"]
    ids = {s.get("id") for s in steps}
    inputs = set(spec["inputs"])

    referenced = set()
    for step in steps:
        for value in list(step.get("env", {}).values()) + [step.get("run", ""),
                                                           str(step.get("if", ""))]:
            referenced |= set(re.findall(r"inputs\.([a-z0-9-]+)", str(value)))
    c.ok(referenced <= inputs,
         f"action.yml reads inputs it does not declare: {sorted(referenced - inputs)}")
    c.ok(inputs <= referenced,
         f"action.yml declares inputs nothing reads: {sorted(inputs - referenced)}")

    for name, out in spec["outputs"].items():
        step = re.findall(r"steps\.([a-z0-9-]+)\.outputs", str(out["value"]))
        c.ok(all(s in ids for s in step),
             f"output `{name}` names a step that does not exist: {step}")

    verify = [s for s in steps if s.get("id") == "verify"][0]
    c.ok("runner.py" in verify["run"], "the verify step must invoke runner.py")
    env_names = set(verify["env"])
    used = set(re.findall(r'env\("(PROMPIRE_[A-Z_]+)"',
                          (ACTION / "runner.py").read_text(encoding="utf-8")))
    used -= {"PROMPIRE_HOME"}  # test-only seam, never set by action.yml
    c.ok(used <= env_names,
         f"runner.py reads env action.yml never sets: {sorted(used - env_names)}")


@case("the-runner-outputs-every-key-action-yml-promises")
def _(tmp, c):
    import yaml
    spec = yaml.safe_load((ACTION / "action.yml").read_text(encoding="utf-8"))
    root, head = repo(tmp)
    r = run(root, tmp, base=head)
    for name in spec["outputs"]:
        c.ok(name in r.outputs, f"action.yml promises output `{name}`, runner.py "
                                f"never wrote it: {sorted(r.outputs)}")


# --------------------------------------------------------------------------- main

def main():
    failed = []
    for name, fn in CASES:
        tmp = tempfile.mkdtemp(prefix="prompire-ci-")
        c = Checks()
        try:
            fn(tmp, c)
        except Exception as exc:  # a crashing case is a failing case
            c.fails.append(f"{type(exc).__name__}: {exc}")
        if c.fails:
            failed.append(name)
            print(f"FAIL  {name}")
            for f in c.fails:
                print(f"      {f}")
        else:
            print(f"pass  {name}")
        if VERBOSE:
            print(f"      kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(CASES) - len(failed)}/{len(CASES)} cases pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
