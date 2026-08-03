#!/usr/bin/env python3
"""End-to-end fixtures: real git repos, real commands, real diffs.

Run: python3 tests/e2e.py [--verbose]
Exit 0 = every case holds.

The battery next door proves the linter fires on the right substrings. This file
proves the skill works: that a baseline is measured rather than guessed, that the guard
rejects an out-of-scope edit and a weakened test without the agent's cooperation, and
that a brief survives compile → lint → baseline → render.
"""
import hashlib
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
sys.path.insert(0, str(HERE))

import fixtures  # noqa: E402

VERBOSE = "--verbose" in sys.argv
CASES = []


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

    def rules(self, data, must_err=(), must_warn=(), must_not=()):
        errs = {f["rule"].split()[0] for f in data["findings"] if f["severity"] == "error"}
        warns = {f["rule"].split()[0] for f in data["findings"] if f["severity"] == "warn"}
        detail = {f["rule"] for f in data["findings"]}
        for r in must_err:
            self.ok(r in errs, f"expected error {r}, got {sorted(detail)}")
        for r in must_warn:
            self.ok(r in warns, f"expected warning {r}, got {sorted(detail)}")
        for r in must_not:
            self.ok(r not in errs | warns, f"{r} fired but should not: {sorted(detail)}")


def tool(name, *args):
    r = subprocess.run([sys.executable, str(SKILL / name)] + [str(a) for a in args],
                       capture_output=True, text=True, encoding="utf-8")
    return r


def lint(path):
    r = tool("lint_brief.py", path, "--json")
    if r.returncode == 2:
        raise AssertionError(f"lint could not read the brief: {r.stdout}{r.stderr}")
    return json.loads(r.stdout)


def guard(path, *extra):
    r = tool("check_scope.py", path, "--json", *extra)
    if r.returncode == 2:
        raise AssertionError(f"guard failed: {r.stdout}{r.stderr}")
    return json.loads(r.stdout)


def base(path, *extra):
    r = tool("baseline.py", path, "--json", *extra)
    return r


def cli(repo, *args, env=None):
    """Run the prompire CLI itself inside the fixture repo — P3's behavior lives
    in the orchestration, not in any one child tool. `env` is merged over the
    caller's environment and inherited by the child tools prompire spawns."""
    return subprocess.run([sys.executable, str(SKILL / "prompire.py"), *map(str, args)],
                          cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8",
                          env=None if env is None else {**os.environ, **env})


def p3_brief(repo, name, body):
    """A brief for `prepare` flows: written verbatim, never base_rev-stamped —
    prepare's own baseline --write must find the measured fields absent."""
    p = pathlib.Path(repo) / ".prompire" / f"{name}.yaml"
    p.parent.mkdir(exist_ok=True)
    p.write_text(body.lstrip(), encoding="utf-8")
    return p


def brief(repo, name, body):
    """Write a brief. Stamps `base_rev` at the fixture repo's HEAD when the body does
    not already carry one — these fixtures are about scope/tests_policy/acceptance
    shape, not about base_rev, and B16 would otherwise fire on every one of them."""
    p = pathlib.Path(repo) / ".prompire" / f"{name}.yaml"
    p.parent.mkdir(exist_ok=True)
    text = body.lstrip()
    if not re.search(r"^base_rev:", text, re.M):
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
        if head:
            text = text.rstrip("\n") + f"\nbase_rev: {head}\n"
    p.write_text(text, encoding="utf-8")
    return p


def measured(repo, name, body):
    """Write a brief, measure its baseline for real, splice the block back in."""
    p = brief(repo, name, body)
    r = base(p)
    data = json.loads(r.stdout)
    sys.path.insert(0, str(SKILL))
    import baseline as bl
    block = bl.render_block(data["results"], data["base_rev"])
    p.write_text(p.read_text(encoding="utf-8").rstrip("\n") + "\n" + block + "\n",
                 encoding="utf-8")
    return p, data


def violations(g):
    return [f for f in g["findings"] if f["kind"] == "VIOLATION"]


# --------------------------------------------------------------------------- cases

@case("missing-acceptance-is-the-finding")
def _(repo, c):
    p = brief(repo, "no-acceptance", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: []
acceptance: []
autonomy: ask
""")
    c.rules(lint(p), must_err=["B4"])
    c.ok(tool("lint_brief.py", p).returncode == 1, "a brief with no criteria must not ship")


@case("ordinary-green-baseline")
def _(repo, c):
    p, data = measured(repo, "green", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
manual_checks:
  - the diff adds count() to src/cart.py
autonomy: ask
""")
    c.ok(data["results"][0]["status"] == "pass",
         f"a green suite must record pass, got {data['results'][0]}")
    c.ok("exit 0" in data["results"][0]["evidence"], "evidence must carry the exit code")
    lr = lint(p)
    c.ok(lr["errors"] == 0 and lr["warnings"] == 0,
         f"a measured green brief is clean, got {lr['findings']}")


@case("red-criterion-must-flip")
def _(repo, c):
    body = """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
"""
    p, data = measured(repo, "flip", body)
    c.ok(data["results"][0]["status"] == "fail",
         f"test_total fails on HEAD, got {data['results'][0]}")
    lr = lint(p)
    c.ok(lr["errors"] == 0, f"a declared flip is legal: {lr['findings']}")

    # the same brief without the declaration is the failure B15 exists to catch
    p2, _ = measured(repo, "flip-undeclared", body.replace("    transition: flip\n", ""))
    c.rules(lint(p2), must_err=["B15"])


@case("known-red-test-must-stay-red")
def _(repo, c):
    p, data = measured(repo, "hold", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_legacy
    expect: exit 1 — the one known failure, unchanged
    transition: hold
autonomy: ask
""")
    c.ok(data["results"][0]["status"] == "pass",
         "expect: exit 1 is met on HEAD, so the recorded status is pass — `status` says "
         "whether the command met its own expect, not whether the suite was green")
    lr = lint(p)
    c.ok(lr["errors"] == 0 and lr["warnings"] == 0, f"hold + evidence is clean: {lr['findings']}")
    out = tool("render_brief.py", p, "--target", "checklist").stdout
    c.ok("do not" in out.lower() and "exactly as measured" in out,
         "the checklist must tell the human not to 'fix' a held criterion")


@case("criterion-not-runnable-until-implementation-exists")
def _(repo, c):
    p, data = measured(repo, "notyet", """
goal: Add src/render/text.py rendering the report rows.
scope: [src/render/]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python3 -c "import text; print(text.render([]))"
    cwd: src/render
    expect: exit 0
    transition: flip
autonomy: ask
""")
    e = data["results"][1]
    c.ok(e["status"] == "not_runnable", f"a missing cwd is not_runnable, got {e}")
    c.ok("does not exist" in e["reason"], f"the reason must say why: {e}")
    lr = lint(p)
    c.ok(lr["errors"] == 0, f"not_runnable + flip is legal: {lr['findings']}")

    # not_runnable without a declared flip cannot tell success from the starting state
    p2 = brief(repo, "notyet-green", pathlib.Path(p).read_text(encoding="utf-8").replace(
        "    transition: flip\n", ""))
    c.rules(lint(p2), must_warn=["B15"])


@case("behaviour-preserving-refactor-needs-before-after")
def _(repo, c):
    p = brief(repo, "refactor-bare", """
goal: Extract report rendering from src/report.py into src/render/text.py.
scope: [src/report.py, src/render/]
forbidden: [tests/**]
plan_first: true
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    c.rules(lint(p), must_warn=["B14"])

    p2, data = measured(repo, "refactor", """
goal: Extract report rendering from src/report.py into src/render/text.py.
scope: [src/report.py, src/render/]
forbidden: [tests/**]
plan_first: true
tests_policy: immutable
acceptance:
  - cmd: python3 -m src.report
    expect: exit 0, output identical to the baseline digest
    before_after: true
autonomy: ask
""")
    c.rules(lint(p2), must_not=["B14"])
    c.ok("sha256:" in data["results"][0]["evidence"],
         f"before_after must record a digest: {data['results'][0]}")


@case("monorepo-command-runs-from-a-subdirectory")
def _(repo, c):
    p, data = measured(repo, "monorepo", """
goal: Add a version field to the api status payload.
scope: [services/api/handler.py]
forbidden: [tests/**, services/api/tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q api.tests.test_handler
    cwd: services
    expect: exit 0
manual_checks:
  - the diff adds the version field
autonomy: ask
""")
    c.ok(data["results"][0]["status"] == "pass",
         f"the suite only runs from services/, got {data['results'][0]}")
    lr = lint(p)
    c.ok(lr["errors"] == 0 and lr["warnings"] == 0, f"clean: {lr['findings']}")
    # the same command without cwd cannot resolve the package
    p2, d2 = measured(repo, "monorepo-nocwd", """
goal: Add a version field to the api status payload.
scope: [services/api/handler.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q api.tests.test_handler
    expect: exit 0
autonomy: ask
""")
    c.ok(d2["results"][0]["status"] == "fail",
         "without cwd the same command fails — which is why cwd is part of the key")
    c.rules(lint(p2), must_err=["B15"])


@case("destructive-and-credential-commands-are-never-executed")
def _(repo, c):
    _, data = measured(repo, "unsafe", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: rm -rf build && python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: curl -sf https://api.example.invalid/health
    expect: exit 0
    requires: [network, credentials]
    transition: flip
  - cmd: git commit -am wip
    expect: exit 0
    transition: flip
autonomy: ask
""")
    kinds = [(r["status"], r.get("reason", "")) for r in data["results"]]
    c.ok(kinds[0][0] == "not_runnable" and "destructive" in kinds[0][1],
         f"rm -rf must not run: {kinds[0]}")
    c.ok(kinds[1][0] == "not_runnable" and "requires" in kinds[1][1],
         f"a declared requirement must not run: {kinds[1]}")
    c.ok(kinds[2][0] == "not_runnable" and "writes to the repository" in kinds[2][1],
         f"a repo-writing command must not run: {kinds[2]}")
    c.ok((pathlib.Path(repo) / "src/cart.py").exists(), "the repo must be untouched")
    c.ok(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                        capture_output=True, text=True, encoding="utf-8").stdout.strip() == "",
         "measuring a baseline must not dirty the tree")


@case("dirty-tree-is-refused-then-declared")
def _(repo, c):
    (pathlib.Path(repo) / "src/cart.py").write_text(
        (pathlib.Path(repo) / "src/cart.py").read_text(encoding="utf-8") + "\n# local scratch\n",
        encoding="utf-8")
    p = brief(repo, "dirty", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    r = base(p)
    c.ok(r.returncode == 2 and "not clean" in r.stdout,
         f"a dirty tree must refuse to produce a baseline: {r.stdout[:200]}")

    p2 = brief(repo, "dirty-declared", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
dirty_baseline: [src/cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    r2 = base(p2, "--allow-dirty")
    c.ok(r2.returncode == 0, f"a declared dirty file lets the run proceed: {r2.stdout[:200]}")
    g = guard(p2)
    c.ok(not violations(g), f"pre-existing dirt is not the agent's edit: {g['findings']}")


@case("out-of-scope-edit-is-rejected")
def _(repo, c):
    p = brief(repo, "scope", """
goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [src/report.py]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    c.ok(not violations(guard(p)), "an untouched tree is clean")

    fixtures.write(repo, "src/cart.py", "def count(items):\n    return len(items)\n")
    c.ok(not violations(guard(p)), "an in-scope edit passes")

    fixtures.write(repo, "src/util.py", "X = 1\n")
    g = guard(p)
    c.ok(any("src/util.py" in v["path"] for v in violations(g)),
         f"a new file outside scope is a violation: {g['findings']}")

    fixtures.write(repo, "src/report.py", "# gutted\n")
    g = guard(p)
    c.ok(any("src/report.py" in v["path"] and "forbidden" in v["message"]
             for v in violations(g)),
         f"a forbidden path is a violation: {g['findings']}")

    # committing the work does not hide it
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "agent work"],
                   capture_output=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD~1"],
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()
    g = guard(p, "--base", head)
    c.ok(len(violations(g)) >= 2,
         f"committed out-of-scope work is still caught with --base: {g['findings']}")


@case("forbidden-case-variant-still-caught")
def _(repo, c):
    """I2: `matches_any`/`glob_re` compared pattern to path as plain strings, and
    `Path.resolve()` does not canonicalise case on macOS — APFS/HFS+ fold case by
    default. `scope: [src/**]` covers `src/GOLDEN/x.txt` because `**` matches any
    spelling of a directory name; `forbidden: [src/golden/**]` used to miss it, because
    the literal segment `golden` was compared case-sensitively. On a folding volume the
    two paths are the SAME directory, so this used to let an agent write straight into
    a directory the brief names as forbidden, just by pressing shift. This is the
    check_scope.py half of the fix; tests/hook.py pins the PreToolUse half of the same
    brief shape.
    """
    # Ground truth computed independently of brief_common.fs_fold — the function under
    # test. Importing fs_fold and branching the assertion on its own return value would
    # make a bug IN that function invisible here: a wrongly-False answer flips this
    # assertion to the "must not flag" branch and the case passes while the guard is
    # wide open (Task 14 fix round 1, I1 — this is exactly the shape that let C1's race
    # slip past this test the first time; tests/hook.py already computed ground truth
    # independently and caught nothing wrong here for that reason).
    def _fs_folds_ground_truth(root):
        probe = pathlib.Path(root) / "e2e-fold-probe.tmp"
        probe.write_text("x", encoding="utf-8")
        try:
            return (pathlib.Path(root) / "E2E-FOLD-PROBE.tmp").exists()
        finally:
            probe.unlink()

    p = brief(repo, "case-fold", """
goal: Refactor helpers under src/.
scope: [src/**]
forbidden: [src/golden/**]
tests_policy: immutable
acceptance:
  - cmd: "true"
    expect: exit 0
autonomy: ask
""")
    fixtures.write(repo, "src/GOLDEN/x.txt", "peek\n")
    g = guard(p)
    case_folds = _fs_folds_ground_truth(pathlib.Path(repo))
    if case_folds:
        c.ok(any("src/GOLDEN/x.txt" in v["path"] and "forbidden" in v["message"]
                 for v in violations(g)),
             f"a case-variant of a forbidden path is still caught: {g['findings']}")
    else:
        c.ok(not any("src/GOLDEN/x.txt" in v["path"] and "forbidden" in v["message"]
                     for v in violations(g)),
             "a genuinely case-sensitive volume must not flag a different directory as "
             f"forbidden: {g['findings']}")


@case("test-weakening-attacks-are-rejected")
def _(repo, c):
    p = brief(repo, "pin", """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
""")
    attacks = {
        "delete": lambda: (pathlib.Path(repo) / "tests/test_total.py").unlink(),
        "skip": lambda: fixtures.write(repo, "tests/test_total.py", '''import unittest

from src.cart import total


class TestTotal(unittest.TestCase):
    @unittest.skip("flaky")
    def test_total_sums(self):
        self.assertEqual(total([1, 2, 3]), 6)
'''),
        "narrow": lambda: fixtures.write(repo, "tests/test_total.py", '''import unittest

from src.cart import total


class TestTotal(unittest.TestCase):
    def test_total_sums(self):
        self.assertTrue(total([1, 2, 3]) is not None)
'''),
        "rename": lambda: (pathlib.Path(repo) / "tests/test_total.py").rename(
            pathlib.Path(repo) / "tests/test_total_disabled.py"),
        "empty": lambda: fixtures.write(repo, "tests/test_total.py", ""),
    }
    for name, attack in attacks.items():
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "tests"],
                       capture_output=True)
        for stray in pathlib.Path(repo, "tests").glob("test_total_disabled.py"):
            stray.unlink()
        attack()
        g = guard(p)
        c.ok(violations(g), f"the `{name}` attack must be rejected: {g['findings']}")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "tests"],
                   capture_output=True)
    for stray in pathlib.Path(repo, "tests").glob("test_total_disabled.py"):
        stray.unlink()


@case("named-and-authoring-policies-bound-which-tests-move")
def _(repo, c):
    p = brief(repo, "named", """
goal: Update the cart suite for the new count() helper.
scope: [src/cart.py]
forbidden: []
tests_policy: named
tests_editable: [tests/test_cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    c.ok(lint(p)["errors"] == 0, "named + tests_editable is legal")
    fixtures.write(repo, "tests/test_cart.py", '''import unittest

from src.cart import add


class TestAdd(unittest.TestCase):
    def test_add_appends(self):
        self.assertEqual(add([1], 2), [1, 2])

    def test_add_keeps_order(self):
        self.assertEqual(add([1, 2], 3), [1, 2, 3])
''')
    g = guard(p)
    c.ok(not violations(g), f"the named file may change: {g['findings']}")
    c.ok(any(f["kind"] == "REVIEW" for f in g["findings"]),
         "a human still has to read that diff, and the guard must say so")

    # a skip marker is a VIOLATION even inside an editable file — `named` permits
    # rewriting the listed tests, not disabling them (SKIP_MARKERS, check_scope.py)
    fixtures.write(repo, "tests/test_cart.py",
                   (pathlib.Path(repo) / "tests/test_cart.py").read_text(encoding="utf-8") + '''

class TestSkipped(unittest.TestCase):
    @unittest.skip("later")
    def test_nothing(self):
        pass
''')
    g = guard(p)
    c.ok(any("disabling marker" in v["message"] for v in violations(g)),
         f"a skip marker in a named-editable file is still a violation: {g['findings']}")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "tests"],
                   capture_output=True)

    fixtures.write(repo, "tests/test_legacy.py", "import unittest\n")
    g = guard(p)
    c.ok(any("not listed in `tests_editable`" in v["message"] for v in violations(g)),
         f"an unnamed test file is still pinned: {g['findings']}")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "tests"],
                   capture_output=True)

    p2 = brief(repo, "named-nolist", """
goal: Update the cart suite for the new count() helper.
scope: [src/cart.py]
tests_policy: named
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    c.rules(lint(p2), must_err=["B7"])

    p3 = brief(repo, "authoring", """
goal: Replace the legacy encoding suite with tests that assert the current behaviour.
scope: [tests/test_legacy.py]
tests_policy: authoring
tests_editable: [tests/test_legacy.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_legacy
    expect: exit 0
    transition: flip
autonomy: ask
""")
    lr = lint(p3)
    c.rules(lr, must_err=["B7"])  # no oracle: nothing outside the edited suite judges it
    p4 = brief(repo, "authoring-oracle", pathlib.Path(p3).read_text(encoding="utf-8").replace(
        "tests_policy: authoring",
        "tests_policy: authoring\noracle: golden/report.txt, reviewed by the maintainer"))
    lr4 = lint(p4)
    c.ok(lr4["errors"] == 0, f"authoring + oracle is legal: {lr4['findings']}")
    c.rules(lr4, must_warn=["B7"])  # and it says out loud that a human must read it

    # under `authoring` a skip marker is a REVIEW, not a VIOLATION — repairing the
    # suite is the task, and check_scope.py downgrades it precisely there
    fixtures.write(repo, "tests/test_legacy.py",
                   (pathlib.Path(repo) / "tests/test_legacy.py").read_text(encoding="utf-8") + '''

class TestSkipped(unittest.TestCase):
    @unittest.skip("later")
    def test_nothing(self):
        pass
''')
    g4 = guard(p4)
    c.ok(not violations(g4), f"a skip marker under authoring is not a violation: {g4['findings']}")
    c.ok(any("disabling marker" in f["message"] and f["kind"] == "REVIEW"
             for f in g4["findings"]),
         f"...but it still draws a REVIEW naming the marker: {g4['findings']}")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "tests"],
                   capture_output=True)


@case("full-workflow-compile-lint-baseline-render")
def _(repo, c):
    p, data = measured(repo, "workflow", """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
forbidden: [tests/**, golden/**]
constraints:
  - the report output stays byte-identical
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python3 -m unittest -q tests.test_legacy
    expect: exit 1 — the one known failure, unchanged
    transition: hold
manual_checks:
  - read the diff of src/cart.py and confirm nothing else moved
autonomy: ask
""")
    statuses = [r["status"] for r in data["results"]]
    c.ok(statuses == ["fail", "pass", "pass"], f"measured statuses: {statuses}")
    lr = lint(p)
    c.ok(lr["errors"] == 0 and lr["warnings"] == 0, f"clean brief: {lr['findings']}")

    prompt = tool("render_brief.py", p, "--target", "claude").stdout
    c.ok(len(prompt.split()) <= 250, f"prompt is {len(prompt.split())} words")
    c.ok("must pass when done" in prompt, "the flip must be visible in the prompt")
    c.ok("keep it green" in prompt, "the green criterion must be visible as such")
    c.ok("do not 'fix' it" in prompt, "the held criterion must be visible as such")
    c.ok("outside" in prompt and "revised brief" in prompt,
         "the prompt must not offer a way to widen scope by asking")

    # the agent does the work
    fixtures.write(repo, "src/cart.py", '''"""A tiny cart."""


def add(items, item):
    return list(items) + [item]


def total(items):
    return sum(items)
''')
    c.ok(not violations(guard(p)), "the honest fix passes the guard")
    for cmd, want in [("python3 -m unittest -q tests.test_total", 0),
                      ("python3 -m unittest -q tests.test_cart", 0),
                      ("python3 -m unittest -q tests.test_legacy", 1)]:
        rc = subprocess.run(cmd, shell=True, cwd=str(repo), capture_output=True).returncode
        c.ok(rc == want, f"after the fix `{cmd}` should exit {want}, got {rc}")

    # ...and the cheat does not
    fixtures.write(repo, "src/cart.py", "def add(items, item):\n    return list(items) + [item]\n"
                                        "\n\ndef total(items):\n    return sum(items) - 1\n")
    fixtures.write(repo, "tests/test_total.py", '''import unittest


class TestTotal(unittest.TestCase):
    def test_total_sums(self):
        self.assertTrue(True)
''')
    g = guard(p)
    c.ok(violations(g), "editing the test to reach the criterion must be caught")
    rc = subprocess.run("python3 -m unittest -q tests.test_total", shell=True,
                        cwd=str(repo), capture_output=True).returncode
    c.ok(rc == 0, "the cheat does satisfy the acceptance command — which is the point: "
                  "the toolchain alone cannot tell, the guard can")


@case("shared-boundary-verdicts")
def _(repo, c):
    """The hook and check_scope.py must read the same boundary from the same brief."""
    sys.path.insert(0, str(SKILL))
    from brief_common import boundary_verdict, tests_verdict
    b = {"scope": ["src/**"], "forbidden": ["src/secret.py", "docs/**"],
         "tests_policy": "named", "tests_editable": ["tests/test_cart.py"]}

    # Boundary verdict cases
    c.ok(boundary_verdict(b, "src/cart.py") is None, "in scope")

    # Full tuple assertions for boundary_verdict (catches message mutations)
    verdict_forbidden = boundary_verdict(b, "docs/readme.md")
    c.ok(verdict_forbidden == ("forbidden",
                               "changed a forbidden path (matches `docs/**`)",
                               "revert it; `forbidden` wins over `scope`"),
         f"forbidden verdict is byte-identical: {verdict_forbidden}")

    verdict_outside = boundary_verdict(b, "elsewhere/x.py")
    c.ok(verdict_outside == ("outside-scope",
                             "changed outside `scope`",
                             "revert it, or revise the brief and re-run the baseline — a scope "
                             "change is an edit to the brief, not a confirmation in chat"),
         f"outside-scope verdict is byte-identical: {verdict_outside}")

    c.ok(boundary_verdict(b, ".prompire/notes.md") is None,
         "always allowed")

    # Explicit policy parameter (required for Task 7)
    c.ok(boundary_verdict(b, "src/cart.py", policy="named") is None,
         "explicit policy parameter works")

    # dirty_baseline case
    b_dirty = {"scope": ["src/**"], "dirty_baseline": ["src/dirty.py"],
               "tests_policy": "named"}
    c.ok(boundary_verdict(b_dirty, "src/dirty.py") is None,
         "dirty_baseline path is skipped")

    # Task 14 fix round 1, N1: dirty_baseline and brief_path were NFC-folded (via
    # norm_path) but NOT case-folded, so a case-variant spelling of a declared
    # dirty_baseline path — the same file on a folding filesystem — was reported as an
    # `outside-scope` VIOLATION instead of skipped. Fail-safe direction (an extra
    # finding, not a missed one), but wrong given `fold` says the volume folds case; a
    # caller that passes NO_FOLD (the default, unchanged) still gets the old exact-case
    # behaviour, so this is deliberately gated on `fold` explicitly saying so.
    #
    # `scope: ["other/**"]` here, deliberately NOT `src/**`: a scope glob would itself
    # match a case variant once `fold` says the volume folds case (that's the Task 14
    # base fix, already covered above), which would make this assertion pass for the
    # wrong reason. `src/dirty.py` must be reachable ONLY through the dirty_baseline
    # exemption for this to isolate the N1 fix specifically.
    b_dirty2 = {"scope": ["other/**"], "dirty_baseline": ["src/dirty.py"],
                "tests_policy": "named"}
    c.ok(boundary_verdict(b_dirty2, "src/DIRTY.py", fold=(True, False)) is None,
         "dirty_baseline matches a case-variant spelling when the volume folds case")
    c.ok(boundary_verdict(b_dirty2, "src/DIRTY.py")[0] == "outside-scope",
         "…but NOT under the NO_FOLD default — never more permissive without `fold`")

    # brief_path case
    c.ok(boundary_verdict(b, ".prompire/notes.yaml", brief_path=".prompire/notes.yaml") is None,
         "brief_path itself is always allowed")

    # Isolated from ALWAYS_ALLOWED (which already covers `.prompire/**`
    # case-insensitively via glob_re's own IGNORECASE): a brief tracked at the repo
    # root, outside `scope` and outside `.prompire/`, so only the brief_path branch
    # itself can be responsible for a None verdict here.
    c.ok(boundary_verdict(b, "SPEC.yaml", brief_path="spec.yaml", fold=(True, False)) is None,
         "brief_path matches a case-variant spelling when the volume folds case")
    c.ok(boundary_verdict(b, "SPEC.yaml", brief_path="spec.yaml")[0] == "outside-scope",
         "…but NOT under the NO_FOLD default — never more permissive without `fold`")

    # Test verdict cases
    c.ok(tests_verdict(b, "src/cart.py") is None, "not a test path")
    c.ok(tests_verdict(b, "tests/test_cart.py") is None, "named and listed")

    # Full tuple assertion (catches message mutations)
    verdict = tests_verdict(b, "tests/test_other.py")
    c.ok(verdict == ("tests-unnamed",
                     "test file changed but is not listed in `tests_editable`",
                     "only the named test paths may change"),
         f"tests-unnamed verdict is byte-identical: {verdict}")

    # immutable case (undeclared defaults to immutable)
    b_immutable = {"scope": ["src/**"]}
    verdict_imm = tests_verdict(b_immutable, "tests/test_x.py")
    c.ok(verdict_imm[0] == "tests-immutable",
         "undeclared policy defaults to immutable")


@case("brief-edited-after-the-baseline")
def _(repo, c):
    """A brief edited after the baseline is a brief nobody has re-read."""
    body = """goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
"""
    # Tracked on purpose, and at .prompire/ specifically (normally gitignored in the
    # fixture — see .gitignore in fixtures.py) so this case also guards the C3 ordering:
    # the brief-path branch must run before the ignored/ALWAYS_ALLOWED skip, or a brief
    # under .prompire/ (which matches ALWAYS_ALLOWED) would never reach it. A brief
    # tracked at the repo root would pass this case even with the branches reordered,
    # which is why it moved here. `git add -f` overrides the .gitignore for this path.
    p = fixtures.write(repo, ".prompire/spec.yaml", body)
    fixtures.git(repo, "add", "-f", "--", ".prompire/spec.yaml")
    fixtures.git(repo, "commit", "-qm", "track the brief")
    # the brief carries no base_rev of its own here — pass the commit that already has
    # it tracked explicitly, so the guard diffs the *next* edit (status M), not the
    # file's own first appearance (status A, which the brief-path branch ignores)
    tracked = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, encoding="utf-8").stdout.strip()
    p.write_text(p.read_text(encoding="utf-8") + "notes: widened after the fact\n",
                 encoding="utf-8")
    g = guard(p, "--base", tracked)
    reviews = [f for f in g["findings"] if f["kind"] == "REVIEW"]
    c.ok(any("brief itself changed" in f["message"] for f in reviews),
         f"no REVIEW for a brief edited after the baseline: {g['findings']}")
    c.ok(not violations(g),
         f"editing the brief is a REVIEW, not a VIOLATION: {violations(g)}")


@case("brief-deleted-after-the-baseline")
def _(repo, c):
    """A brief deleted mid-run is at least as suspect as one edited — status D.

    No shipped entry point reaches this branch today, and the docstring should not
    pretend otherwise. main() calls load_brief on the same path it later diffs, so a
    brief absent from disk fails to load before check() ever runs (exit 2 — a louder
    signal than a REVIEW anyway). The PreToolUse hook does not reach it either: it calls
    boundary_verdict/tests_verdict per write and never calls check() at all.

    The branch is kept, not deleted, because the only way to reach it is a caller holding
    an already-parsed brief, and the deliberate decision was NOT to make main() such a
    caller by falling back to `git show <base>:<brief>`: digest_of() returns None for a
    path that is gone, and both the armed-digest refusal in armed_verdict() and main()'s
    own before/after digest comparison are conditioned on a digest existing. Reading a
    deleted brief out of git would hand the whole pointer guarantee a hole in order to
    close a coverage gap. This case is what keeps the branch correct until a caller with
    a parsed brief in hand actually appears.
    """
    sys.path.insert(0, str(SKILL))
    import check_scope
    from brief_common import load_brief
    body = """goal: Add a count() helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
"""
    p = fixtures.write(repo, ".prompire/spec-del.yaml", body)
    fixtures.git(repo, "add", "-f", "--", ".prompire/spec-del.yaml")
    fixtures.git(repo, "commit", "-qm", "track the brief")
    loaded = load_brief(p)
    p.unlink()
    findings = check_scope.check(loaded, pathlib.Path(repo), "HEAD", ".prompire/spec-del.yaml")
    reviews = [f for f in findings if f["kind"] == "REVIEW"]
    c.ok(any("brief itself was deleted" in f["message"] for f in reviews),
         f"no REVIEW for a brief deleted after the baseline: {findings}")
    c.ok(not [f for f in findings if f["kind"] == "VIOLATION"],
         f"deleting the brief is a REVIEW, not a VIOLATION: {findings}")


@case("rename-out-of-tests-is-still-caught-immutable")
def _(repo, c):
    """A rename out of the test tree must not lose its VIOLATION under `immutable`.

    tests_verdict's own is_test_path gate looks at the destination only; the rename's
    destination (src/helper.py) is not a test path even though its origin was. The gate
    at the call site already establishes test-ness from path-or-origin, so it must pass
    is_test=True through — this is the regression a prior round of this task shipped.
    """
    p = brief(repo, "rename-immutable", """
goal: Add a count() helper to src/cart.py.
scope: [src/, tests/]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    subprocess.run(["git", "-C", str(repo), "mv", "tests/test_total.py", "src/helper.py"],
                   capture_output=True)
    g = guard(p)
    c.ok(any("src/helper.py" in v["path"] and "immutable" in v["message"]
             for v in violations(g)),
         f"a test file renamed out of tests/ must still violate `immutable`: {g['findings']}")


@case("rename-out-of-tests-is-still-caught-named")
def _(repo, c):
    """Same evasion under `named`: the rename's destination is not the named path either."""
    p = brief(repo, "rename-named", """
goal: Update the cart suite for the new count() helper.
scope: [src/, tests/]
forbidden: []
tests_policy: named
tests_editable: [tests/test_cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    subprocess.run(["git", "-C", str(repo), "mv", "tests/test_total.py", "src/helper.py"],
                   capture_output=True)
    g = guard(p)
    c.ok(any("src/helper.py" in v["path"] and "not listed in `tests_editable`" in v["message"]
             for v in violations(g)),
         f"a test file renamed out of tests/ must still violate `named`: {g['findings']}")


@case("activate-and-deactivate")
def _(repo, c):
    """The pointer is a file contract: the brief's repo-relative path on line 1, the base
    it declared when the guard was armed on line 2, or the whole file absent."""
    p = brief(repo, "spec", """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
""")
    ptr = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    r = tool("check_scope.py", p, "--activate")
    c.ok(r.returncode == 0, f"--activate exited {r.returncode}: {r.stdout}{r.stderr}")
    # --activate cannot know whether any host hook is installed, so it must not
    # promise pre-write refusal unconditionally. It may describe what a hook does
    # only as conditional on one being installed.
    c.ok("are refused before they happen" not in r.stdout,
         f"--activate still claims unconditional pre-write refusal: {r.stdout}")
    c.ok("hook" in r.stdout and "does not install a hook" in r.stdout,
         f"--activate must say pre-write refusal depends on an installed hook: "
         f"{r.stdout}")
    c.ok(ptr.is_file(), "--activate wrote no pointer")
    if ptr.is_file():
        raw = ptr.read_bytes()
        lines = raw.decode("utf-8").splitlines()
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
        # Line 1 alone is what the hook reads; the records below it must never change
        # that. Asserted on raw bytes: read_text() applies universal-newline translation
        # and splitlines() splits on CR as well, so between them this assertion passed
        # for a pointer whose first line ended `\r\n` — i.e. it did not actually pin the
        # format it claims to pin. The pointer is a byte format two separate parsers
        # agree on; only bytes can tell `\n` from `\r\n`.
        c.ok(raw.split(b"\n")[0] == b".prompire/spec.yaml",
             f"pointer line 1 is not exactly the brief path: {raw!r}")
        c.ok(f"base_rev {head}" in lines[1:],
             f"--activate did not pin the declared base: {lines[1:]}")
        c.ok(any(ln.startswith("sha256 ") for ln in lines[1:]),
             f"--activate did not record the brief's digest: {lines[1:]}")
    r = tool("check_scope.py", p, "--deactivate")
    c.ok(r.returncode == 0 and not ptr.exists(),
         f"--deactivate left the pointer behind: {r.stdout}{r.stderr}")
    q = brief(repo, "noscope", "goal: no scope here\nacceptance: []\n")
    c.ok(tool("check_scope.py", q, "--activate").returncode == 2,
         "--activate accepted a brief with no `scope` — there is no boundary to arm")
    # Test flag-before-path ordering: --deactivate /path/to/brief should work regardless of order
    p2 = brief(repo, "spec2", """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
acceptance: []
autonomy: ask
""")
    # Activate the first one
    tool("check_scope.py", p, "--activate")
    # Deactivate with flag-before-path order
    r = tool("check_scope.py", "--deactivate", p2)
    c.ok(r.returncode == 0 and not ptr.exists(),
         f"--deactivate with flag-first order should remove the pointer: {r.stdout}{r.stderr}")


@case("active-brief-query-matches-activation")
def _(repo, c):
    sys.path.insert(0, str(SKILL))
    from check_scope import active_brief

    p, _ = measured(repo, "status", """
goal: Keep the cart behavior unchanged.
scope: [src/cart.py]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")

    c.ok(active_brief(pathlib.Path(repo)) is None, "nothing is active before arming")
    armed = tool("check_scope.py", p, "--activate")
    c.ok(armed.returncode == 0, armed.stdout + armed.stderr)
    c.ok(active_brief(pathlib.Path(repo)) == ".prompire/status.yaml",
         "the query returns the brief the guard enforces")

    dead = pathlib.Path(repo) / ".prompire" / "missing.yaml"
    (pathlib.Path(repo) / ".prompire" / "ACTIVE").write_text(
        ".prompire/missing.yaml\n", encoding="utf-8")
    c.ok(not dead.exists() and active_brief(pathlib.Path(repo)) is None,
         "a pointer to an unreadable brief is not a live guard")


@case("no-base-and-no-flag-refuses-a-verdict")
def _(repo, c):
    """Fix round 2: a brief that never sees lint_brief.py (or is hand-edited after)
    must not let check_scope.py fall back to HEAD silently — that is the identical
    hole B16 exists to close, just reached by skipping the linter instead of the
    field. Written directly, bypassing brief()'s test-fixture convenience stamp, so
    the brief genuinely carries no `base_rev`."""
    p = pathlib.Path(repo) / ".prompire" / "nobase.yaml"
    p.parent.mkdir(exist_ok=True)
    p.write_text("""
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
autonomy: ask
""".lstrip(), encoding="utf-8")

    r = tool("check_scope.py", p, "--json")
    c.ok(r.returncode == 2,
         f"no base_rev and no --base must refuse to run, got {r.returncode}: "
         f"{r.stdout}{r.stderr}")
    c.ok("baseline.py" in (r.stdout + r.stderr),
         f"the refusal must point at baseline.py: {r.stdout}{r.stderr}")
    c.ok(not r.stdout.strip().startswith("{"),
         f"a refusal must not also print a JSON verdict: {r.stdout}")

    # an explicit --base is a human's deliberate choice and stays authoritative, even
    # though HEAD is exactly the moving ref B16 rejects when it comes from the brief
    r2 = tool("check_scope.py", p, "--base", "HEAD", "--json")
    c.ok(r2.returncode == 0,
         f"an explicit --base must be honored regardless of shape: {r2.stdout}{r2.stderr}")


RESTAMP_BRIEF = """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
forbidden: [golden/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
base_rev: {base}
"""


def _spec(repo, base, extra=""):
    return fixtures.write(repo, ".prompire/spec.yaml",
                          RESTAMP_BRIEF.format(base=base).lstrip() + extra)


NAMED_BRIEF = """
goal: Update the cart suite for the new count() helper.
scope: [src/cart.py]
forbidden: [golden/**]
tests_policy: named
tests_editable: [tests/test_cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
base_rev: {base}
"""


def _spec_named(repo, base):
    """Same shape as `_spec`, but `tests_policy: named` — which prints its own REVIEW
    unconditionally (`check()`'s catch-all for `named`/`authoring`) whether or not a
    test file actually moved. Used where a case needs a second REVIEW that has nothing
    to do with the tombstone log, to prove an ack does not cover it too."""
    return fixtures.write(repo, ".prompire/named.yaml",
                          NAMED_BRIEF.format(base=base).lstrip())


def _tamper(repo, msg="work, committed by the agent", commit=True):
    """The agent edits a forbidden path. Committing it is what makes the bypass possible
    at all: `base_rev` can only be moved to a commit that already contains the work."""
    fixtures.write(repo, "golden/report.txt", "apples: 3\npears: 5\nTAMPERED\n")
    if commit:
        fixtures.git(repo, "add", "--", "golden/report.txt")
        fixtures.git(repo, "commit", "-qm", msg)
        return fixtures.git(repo, "rev-parse", "HEAD").strip()
    return None


def _repin(repo):
    """Arm `spec.yaml`, launder a forbidden edit past the base, `--deactivate`, and
    re-`--activate` — the standard way this suite puts a brief into the `repin` state,
    shared by every `--ack-disarms` case below."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    new = _tamper(repo)
    _spec(repo, new)
    tool("check_scope.py", p, "--deactivate")
    tool("check_scope.py", p, "--activate")
    return p


def _tomb_digest(repo):
    tomb = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    return hashlib.sha256(tomb.read_bytes()).hexdigest()


def _refused(c, r, *must_contain):
    out = r.stdout + r.stderr
    c.ok(r.returncode == 2, f"expected no verdict (exit 2), got {r.returncode}: {out}")
    c.ok("violation(s)" not in out and "inside the declared boundary" not in out,
         f"a refusal must not also hand out a verdict: {out}")
    for s in must_contain:
        c.ok(s in out, f"refusal does not mention {s!r}: {out}")


@case("re-stamped-base_rev-is-refused-by-the-pin")
def _(repo, c):
    """The brief is a file the agent can edit, so it cannot be the only record of the
    boundary or the base. `--activate` copies both out to `.prompire/ACTIVE` while
    they are still honest; a later disagreement produces no verdict at all, instead of
    the empty-diff `0 violation(s)` this used to hand out."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    c.ok(tool("check_scope.py", p, "--activate").returncode == 0, "--activate failed")

    new = _tamper(repo)
    _spec(repo, new)
    _refused(c, tool("check_scope.py", p), head, new)
    # `--base` does not buy a verdict out of an armed pointer that disagrees — it chooses
    # the revision, not the brief. Disarming does, and that leaves a tombstone.
    _refused(c, tool("check_scope.py", p, "--base", head), head)
    tool("check_scope.py", p, "--deactivate")
    g = guard(p, "--base", head)
    c.ok(any("golden/report.txt" in v["path"] for v in violations(g)),
         f"the forbidden edit must still be visible against the pinned base: {g['findings']}")


@case("editing-any-other-field-is-refused-too")
def _(repo, c):
    """`base_rev` was never the only field worth buying. `dirty_baseline` is skipped
    unconditionally, so appending one entry turns a real violation into "every change is
    inside the declared boundary" — no commit, no re-stamp, one Write. The record kept at
    `--activate` is a digest of the whole brief for exactly this reason."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    _tamper(repo, commit=False)

    g = guard(p)
    c.ok(any("golden/report.txt" in v["path"] for v in violations(g)),
         f"the honest run must see the forbidden edit: {g['findings']}")

    _spec(repo, head, extra="dirty_baseline: [golden/report.txt]\n")
    _refused(c, tool("check_scope.py", p), "dirty_baseline")


@case("a-brief-committed-without-a-base_rev-corroborates-nothing")
def _(repo, c):
    """The blob at `base` is only evidence if it says something. A brief committed with
    no `base_rev` at all — trivially arranged by committing the work and a field-less
    brief together — says nothing about where any work started, and calling that
    corroboration is worse than calling it nothing: it suppresses the flag that would
    otherwise fire."""
    body = RESTAMP_BRIEF.format(base="").rstrip()[:-len("base_rev:")].rstrip() + "\n"
    p = fixtures.write(repo, ".prompire/spec.yaml", body.lstrip())
    fixtures.write(repo, "golden/report.txt", "apples: 3\npears: 5\nTAMPERED\n")
    fixtures.git(repo, "add", "-f", "--", "golden/report.txt", ".prompire/spec.yaml")
    fixtures.git(repo, "commit", "-qm", "work and a field-less brief in one commit")
    new = fixtures.git(repo, "rev-parse", "HEAD").strip()
    _spec(repo, new)

    g = guard(p)
    c.ok(g["base_source"] is None,
         f"a field-less committed brief is not corroboration: {g['base_source']!r}")
    c.ok(any("nothing outside the brief corroborates" in f["message"]
             for f in g["findings"] if f["kind"] == "REVIEW"),
         f"the uncorroborated flag must still fire: {g['findings']}")


@case("a-reusable-brief-slot-is-a-review-not-a-refusal")
def _(repo, c):
    """A tracked brief at a stable path is a slot, not a one-shot: task B honestly
    re-stamps `base_rev` in the same file task A used, and the copy committed at B's base
    still carries A's value. That is byte-identical to tampering, and git cannot tell
    them apart — so history raises a flag and the pin stays the only authority. The
    remediation must not offer `--base A` either: that folds task A's work into B's
    diff."""
    a = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, a)
    fixtures.git(repo, "add", "-f", "--", ".prompire/spec.yaml")
    fixtures.git(repo, "commit", "-qm", "task A: track the brief")
    b = fixtures.git(repo, "rev-parse", "HEAD").strip()
    _spec(repo, b)          # task B, honestly starting from where A ended

    r = tool("check_scope.py", p)
    c.ok(r.returncode != 2, f"an honest reusable slot must not be refused: {r.stdout}")
    g = guard(p)
    reviews = [f["message"] for f in g["findings"] if f["kind"] == "REVIEW"]
    c.ok(any("reusable slot" in m for m in reviews),
         f"history disagreement must be flagged for a human: {g['findings']}")
    c.ok(not any(f"--base {a}" in m for m in reviews),
         f"the flag must not recommend a --base that folds in the earlier task: {reviews}")


@case("deactivate-and-re-arm-cannot-launder-a-bought-base")
def _(repo, c):
    """`--deactivate && --activate` is two commands and no Bash. Without a tombstone it
    re-pins whatever the brief now claims and reports it under the strongest label this
    tool prints. The honest user and the evader take the identical path, so the answer is
    not to refuse it but to record it: a pin written over a tombstone is a `repin`, and a
    repin corroborates nothing."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    new = _tamper(repo)
    _spec(repo, new)
    tool("check_scope.py", p, "--deactivate")
    r = tool("check_scope.py", p, "--activate")
    c.ok(r.returncode == 0, f"re-arming after a deactivate must be allowed: {r.stdout}")

    g = guard(p)
    c.ok(g["base_source"] == "repin",
         f"a laundered pin must not report as `pin`: {g['base_source']!r}")
    c.ok(any("after a `--deactivate`" in f["message"] for f in g["findings"]),
         f"the re-arm must be visible in the findings: {g['findings']}")
    tomb = (pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones").read_text(encoding="utf-8")
    c.ok(".prompire/spec.yaml" in tomb and head in tomb,
         f"the tombstone must record what was disarmed: {tomb!r}")


@case("forged-pointer-omitting-repin-still-reports-repin")
def _(repo, c):
    """Task 19, Fix B — the C1 variant the task 17 review named directly: `.prompire/
    ACTIVE` is a plaintext file `--activate` writes with a `repin` line only when
    `any_disarm(root)` says a disarm happened, and that is exactly the shape a bare
    Write can recreate from scratch. A forged pointer naming this brief, at the base it
    currently declares, with a matching sha256 and NO `repin` line, used to read as a
    clean first arm to a `corroborate()` that trusted the pointer's own claim over the
    tombstone log sitting untouched right beside it. It must not: the log is the
    independent record, and it says a disarm happened here."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    new = _tamper(repo)
    _spec(repo, new)
    tool("check_scope.py", p, "--deactivate")
    tomb = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    c.ok(tomb.read_text(encoding="utf-8").strip() != "",
         "sanity: the tombstone log must be non-empty for this case to test anything")

    # Forge the pointer directly — never through `--activate`, so no `repin` line —
    # the same three-line shape (brief path, base_rev, sha256) a bare Write produces,
    # matching this brief exactly at the base it currently declares.
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    (pathlib.Path(repo) / ".prompire" / "ACTIVE").write_text(
        f".prompire/spec.yaml\nbase_rev {new}\nsha256 {sha}\n", encoding="utf-8")

    g = guard(p)
    c.ok(g["base_source"] == "repin",
         f"a forged pointer omitting `repin` must still report `repin`, not `pin`, once "
         f"the tombstone log is non-empty: {g['base_source']!r}")
    c.ok(tool("check_scope.py", p, "--strict").returncode == 1,
         "a forged clean-looking pin must not let --strict exit 0 on an unacknowledged "
         "disarm")


@case("ack-disarms-absent-strict-still-red")
def _(repo, c):
    """The old behaviour survives: an unacknowledged repin still fails `--strict`.
    `--ack-disarms` is opt-in, not a default amnesty."""
    p = _repin(repo)
    c.ok(tool("check_scope.py", p, "--strict").returncode == 1,
         "a repin with no --ack-disarms must still fail --strict")


@case("ack-disarms-correct-digest-clears-strict")
def _(repo, c):
    """A digest matching the tombstone log as it stands clears `--strict` — but the
    finding it silences is still printed, not suppressed."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    c.ok(r.returncode == 0,
         f"a matching --ack-disarms must clear --strict: {r.returncode} {r.stdout}")
    c.ok("REVIEW" in r.stdout and "written after a `--deactivate`" in r.stdout,
         f"the repin REVIEW must still print even when acknowledged: {r.stdout}")


@case("ack-disarms-does-not-promote-repin-to-pin")
def _(repo, c):
    """The anti-laundering pin: an acknowledged repin is still reported as `repin`,
    never relabelled `pin`. A future refactor that promotes the label on ack must fail
    this case, not the `--strict` exit code, which would stay 0 either way."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    g = guard(p, "--ack-disarms", digest[:12])
    c.ok(g["base_source"] == "repin",
         f"an acknowledged repin must not relabel as `pin`: {g['base_source']!r}")
    c.ok(g.get("ack_disarms_bound") is True,
         f"--json must expose that the acknowledgement bound: {g}")


@case("ack-disarms-wrong-digest-refuses")
def _(repo, c):
    """A digest that does not match the tombstone log refuses a verdict outright —
    it must not fall back to an unacknowledged repin verdict."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    wrong = ("0" if digest[0] != "0" else "1") + digest[1:12]
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", wrong)
    c.ok(r.returncode == 2,
         f"a mismatched digest must refuse a verdict: {r.returncode} {r.stdout}")
    c.ok(digest in r.stdout,
         f"the refusal must print the current digest so the reviewer can re-run: {r.stdout}")
    c.ok("violation(s)" not in r.stdout,
         f"a refusal must not also hand out a verdict: {r.stdout}")


@case("ack-disarms-invalidated-by-a-later-disarm")
def _(repo, c):
    """The headline property: acknowledging the tombstone log as it reads now must not
    survive one more `--deactivate`. If only one case in this file matters, it is this
    one — everything else is bookkeeping around it."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    c.ok(r.returncode == 0, f"the first acknowledgement must bind: {r.stdout}")

    tool("check_scope.py", p, "--deactivate")
    tool("check_scope.py", p, "--activate")
    r2 = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    c.ok(r2.returncode == 2,
         f"the same digest must not survive a later --deactivate: "
         f"{r2.returncode} {r2.stdout}")


@case("ack-disarms-inert-without-a-tombstone")
def _(repo, c):
    """A fresh checkout has no `.prompire/` at all — it is gitignored. `--ack-disarms`
    there must not refuse; it must say it did nothing and continue to a normal verdict."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", "abcdefabcdef")
    c.ok(r.returncode == 0,
         f"--ack-disarms with no tombstone log must be inert, not a refusal: "
         f"{r.returncode} {r.stdout}")
    c.ok("nothing to acknowledge" in r.stdout,
         f"the inert case must say so out loud: {r.stdout}")
    g = guard(p, "--ack-disarms", "abcdefabcdef")
    c.ok(g.get("ack_disarms_bound") is False,
         f"an inert ack must not report as bound: {g}")


@case("ack-disarms-does-not-cover-a-violation")
def _(repo, c):
    """The ack covers a REVIEW, not a VIOLATION. A real out-of-scope edit must still
    fail --strict (and the plain exit code) under a correct acknowledgement."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    fixtures.write(repo, "src/other.py", "y = 1\n")   # outside `scope: [src/cart.py]`
    r = tool("check_scope.py", p, "--ack-disarms", digest[:12])
    c.ok(r.returncode == 1,
         f"a real VIOLATION must still fail under a correct ack: {r.returncode} {r.stdout}")
    c.ok("VIOLATION" in r.stdout and "src/other.py" in r.stdout,
         f"the violation must still be named: {r.stdout}")


@case("ack-disarms-scoped-to-the-repin-finding-only")
def _(repo, c):
    """The ack is scoped to the repin finding, not to strictness generally: a second,
    unrelated REVIEW (`tests_policy: named`'s unconditional human-read flag) must still
    fail --strict even once the repin note is acknowledged."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec_named(repo, head)
    tool("check_scope.py", p, "--activate")
    new = _tamper(repo)
    _spec_named(repo, new)
    tool("check_scope.py", p, "--deactivate")
    tool("check_scope.py", p, "--activate")
    digest = _tomb_digest(repo)

    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    c.ok(r.returncode == 1,
         f"an unrelated REVIEW must still fail --strict under an ack scoped to the "
         f"repin finding: {r.returncode} {r.stdout}")
    g = guard(p, "--ack-disarms", digest[:12])
    c.ok(g["reviews"] == 2,
         f"both the repin note and the named-policy note must be present: "
         f"{g['findings']}")


@case("ack-disarms-does-not-bind-an-uncorroborated-base")
def _(repo, c):
    """The `source == "repin"` scoping is what keeps an acknowledgement of *disarms*
    from also silencing a base *nobody corroborated at all* — a condition security
    review found unpinned (I1): flip that check to `if ack_bound:` and this is the case
    that goes red. One more `--deactivate` with no re-`--activate` leaves the guard
    unarmed, so the run reads `base_source: null`, not `repin` — and a digest that
    matches the tombstone log must not clear --strict there."""
    p = _repin(repo)
    tool("check_scope.py", p, "--deactivate")
    digest = _tomb_digest(repo)

    g = guard(p, "--ack-disarms", digest[:12])
    c.ok(g["base_source"] is None,
         f"this run must be uncorroborated, not repin: {g['base_source']!r}")
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    c.ok(r.returncode == 1,
         f"a matching ack must not silence an uncorroborated base: "
         f"{r.returncode} {r.stdout}")


@case("ack-disarms-rejects-an-11-character-digest")
def _(repo, c):
    """The 12-character floor is load-bearing (I2): security review found deleting the
    shape check, or loosening it to a 1-character floor, keeps all six suites green — a
    short-enough prefix binds by coincidence with no grinding required. Pin the floor
    directly: one character short of it must refuse, not degrade to a shorter match."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:11])
    c.ok(r.returncode == 2,
         f"an 11-character digest must refuse, not bind: {r.returncode} {r.stdout}")
    c.ok("violation(s)" not in r.stdout,
         f"a refusal must not also hand out a verdict: {r.stdout}")


@case("ack-disarms-rejects-a-missing-value")
def _(repo, c):
    """`--ack-disarms` as the last argv token, with no value following it, must not
    become the empty string and match every tombstone log via `str.startswith("")`
    (I2) — the same shape check that guards the 11-character case must catch this."""
    p = _repin(repo)
    r = tool("check_scope.py", p, "--strict", "--ack-disarms")
    c.ok(r.returncode == 2,
         f"a missing --ack-disarms value must refuse, not bind: {r.returncode} {r.stdout}")
    c.ok("violation(s)" not in r.stdout,
         f"a refusal must not also hand out a verdict: {r.stdout}")


@case("ack-disarms-does-not-bind-an-unwritable-tombstone-log")
def _(repo, c):
    """I3: a `--deactivate` that cannot append to the log still turns the guard off
    (correct — it fails toward disarming) but leaves the log's bytes, and therefore its
    digest, unchanged. Without a guard, a stale acknowledgement would still match after
    a real second disarm the acknowledgement never saw. The fix refuses instead of
    binding to a log that can no longer prove a future disarm would move the digest."""
    p = _repin(repo)
    digest = _tomb_digest(repo)
    tomb = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    mode = tomb.stat().st_mode
    tomb.chmod(0o444)
    try:
        tool("check_scope.py", p, "--deactivate")     # a real second disarm; log unwritable
        tool("check_scope.py", p, "--activate")
        c.ok(_tomb_digest(repo) == digest,
             f"the log must genuinely be unwritable for this case to test anything: "
             f"{_tomb_digest(repo)} vs {digest}")
        r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
        c.ok(r.returncode == 2,
             f"a stale ack against an unwritable log must refuse, not bind: "
             f"{r.returncode} {r.stdout}")
        c.ok("violation(s)" not in r.stdout,
             f"a refusal must not also hand out a verdict: {r.stdout}")
    finally:
        tomb.chmod(mode)   # restore write access so the fixture repo can be torn down


def _write_legacy_tombstone(repo, line="old-spec.yaml deadbeefdeadbeef deadbeefdeadbeef "
                                        "2026-01-01T00:00:00\n"):
    """Plant a non-empty `.agent-brief/ACTIVE.tombstones` — the disarm log's address
    from before the 0.4.0 rename, and where every pre-rename repo's real history
    already sits. Never written through the tool itself: no version of this tool ever
    wrote to that path, so a direct write is the only honest way to fixture it."""
    legacy = pathlib.Path(repo) / ".agent-brief" / "ACTIVE.tombstones"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(line, encoding="utf-8")
    return legacy


@case("legacy-tombstone-log-forces-repin-on-first-arm")
def _(repo, c):
    """Task 20's headline property. A repo that used this tool before the rename has
    its disarm history at `.agent-brief/ACTIVE.tombstones`, not the current
    `.prompire/ACTIVE.tombstones` — which does not exist yet in this repo at all, the
    ordinary shape of a fresh checkout post-upgrade. `any_disarm()` has to read the
    legacy path too, or the very first `--activate` after the upgrade reports a clean
    `pin` over a genuine past disarm: the hole this task exists to close."""
    legacy = _write_legacy_tombstone(repo)
    c.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones").is_file(),
         "sanity: no CURRENT-name log may exist yet, or this proves nothing")

    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    r = tool("check_scope.py", p, "--activate")
    c.ok(r.returncode == 0 and "repin" in r.stdout.lower(),
         f"an arm over a non-empty legacy log must report repin, not pin: {r.stdout}")

    g = guard(p)
    c.ok(g["base_source"] == "repin",
         f"base_source must be repin from the legacy log alone: {g['base_source']!r}")
    c.ok(legacy.is_file(), "sanity: the legacy file itself must not have been touched")


@case("ack-disarms-refuses-while-a-legacy-log-is-present")
def _(repo, c):
    """A leftover `.agent-brief/ACTIVE.tombstones` means the repo's disarm history is
    split across two files, and no single digest can speak for a set that is not one
    log yet. `--ack-disarms` must refuse outright — even a digest that genuinely
    matches the current log, "any digest" per the brief — and its message must name
    both halves of the fix: append, then delete."""
    p = _repin(repo)
    legacy = _write_legacy_tombstone(repo)
    digest = _tomb_digest(repo)   # a real, matching digest of the CURRENT log
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    out = r.stdout + r.stderr
    c.ok(r.returncode == 2,
         f"--ack-disarms must refuse while a legacy log exists, even with a matching "
         f"digest: {r.returncode} {out}")
    c.ok("append" in out.lower() and "delete" in out.lower(),
         f"the refusal must name both the append and the delete: {out}")
    c.ok(str(legacy) in out, f"the refusal must name the legacy path itself: {out}")


@case("a-jammed-legacy-tombstone-log-is-tampering-not-a-crash")
def _(repo, c):
    """The sibling of `a-jammed-tombstone-log-is-tampering-not-a-crash`, at the legacy
    address: a directory planted at `.agent-brief/ACTIVE.tombstones` must refuse a
    verdict exactly like one at the current path, not crash — `any_disarm()` reads
    both now, so an obstruction at either one is the same "unreadable" answer."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    legacy_dir = pathlib.Path(repo) / ".agent-brief" / "ACTIVE.tombstones"
    legacy_dir.mkdir(parents=True)

    r = tool("check_scope.py", p)
    c.ok(r.returncode == 2 and "Traceback" not in r.stderr,
         f"a jammed legacy log must refuse a verdict, not crash: {r.returncode} "
         f"{r.stderr[:200]}")
    c.ok("violation(s)" not in r.stdout,
         f"a refusal must not also hand out a verdict: {r.stdout}")
    c.ok(str(legacy_dir) in (r.stdout + r.stderr),
         f"the refusal should name the actual offending path: {r.stdout}{r.stderr}")


@case("ack-disarms-binds-again-after-the-legacy-migration")
def _(repo, c):
    """Once the legacy log's contents are appended into the current one and the legacy
    file deleted — the fix `--ack-disarms` itself prints above — the repo has exactly
    one tombstone log again, and `--ack-disarms` works normally against its digest."""
    p = _repin(repo)
    legacy = _write_legacy_tombstone(repo)

    current = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    with open(current, "a", encoding="utf-8") as f:
        f.write(legacy.read_text(encoding="utf-8"))
    legacy.unlink()

    c.ok(not legacy.exists(), "sanity: the migration must have removed the legacy file")
    digest = _tomb_digest(repo)
    r = tool("check_scope.py", p, "--strict", "--ack-disarms", digest[:12])
    c.ok(r.returncode == 0,
         f"--ack-disarms must bind again once the migration is done: {r.returncode} "
         f"{r.stdout}{r.stderr}")


@case("renaming-the-brief-cannot-launder-a-bought-base-either")
def _(repo, c):
    """The tombstone must key on a disarm having happened, not on which path was
    disarmed — the path is the part the evader chooses. Copy the armed brief to a new
    name with `base_rev` re-stamped (one Write `.prompire/**` allows), disarm the old
    name, arm the new one, and a path-keyed check calls it a first arm and prints `pin`
    with zero flags: a cleaner result than the direct re-arm this replaced.

    It is also the incentive that matters. Under path keying, revising a brief in place
    cost `repin` forever while renaming it restored a full `pin`, so the cheapest honest
    path was the attack. Both cost the same now.
    """
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    new = _tamper(repo)
    q = fixtures.write(repo, ".prompire/spec2.yaml",
                       RESTAMP_BRIEF.format(base=new).lstrip())
    tool("check_scope.py", p, "--deactivate")
    r = tool("check_scope.py", q, "--activate")
    c.ok(r.returncode == 0, f"arming a differently-named brief must be allowed: {r.stdout}")

    g = guard(q)
    c.ok(g["base_source"] == "repin",
         f"a re-arm under a new name must not report as `pin`: {g['base_source']!r}")
    c.ok(any("after a `--deactivate`" in f["message"] for f in g["findings"]),
         f"the re-arm must be visible in the findings: {g['findings']}")
    c.ok(tool("check_scope.py", q, "--strict").returncode == 1,
         "--strict must not exit 0 on a base a re-arm is the only record of")


@case("a-jammed-tombstone-log-is-tampering-not-a-crash")
def _(repo, c):
    """A directory where the log file belongs used to be one allowed Write that killed
    the record permanently: `--deactivate` died on IsADirectoryError without disarming,
    the operator cleared the jam by hand, and the next arm printed the strongest label.

    The hook refuses that write now, but the state can also predate the guard, so nothing
    downstream may assume it away: `--deactivate` still turns the guard off, the run
    produces no verdict at all rather than a traceback, and "cannot read the log" counts
    as at least as suspect as a recorded disarm — never as a clean slate."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    (pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones").mkdir()

    r = tool("check_scope.py", p)
    c.ok(r.returncode == 2 and "Traceback" not in r.stderr,
         f"a jammed log must refuse a verdict, not crash: {r.returncode} {r.stderr[:200]}")
    c.ok("violation(s)" not in r.stdout,
         f"a refusal must not also hand out a verdict: {r.stdout}")

    r = tool("check_scope.py", p, "--deactivate")
    c.ok(r.returncode == 0 and "Traceback" not in r.stderr,
         f"--deactivate must survive a jammed log: {r.returncode} {r.stderr[:200]}")
    c.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
         "--deactivate left the guard armed, so the operator's way out is wedged")

    r = tool("check_scope.py", p, "--activate")
    c.ok("repin" in r.stdout.lower(),
         f"an arm over an unreadable log must not claim a first pin: {r.stdout}")


@case("the-brief-changing-mid-read-refuses")
def _(repo, c):
    """The digest is taken either side of the parse so the bytes a verdict is read from
    are the bytes it attests to. Nothing else in the suite fails if that comparison is
    deleted, so it is pinned here directly — the two reads are forced to disagree."""
    import io
    from contextlib import redirect_stdout
    sys.path.insert(0, str(SKILL))
    import check_scope
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    real, seen = check_scope.digest_of, []

    def flaky(path):
        seen.append(path)
        return real(path) if len(seen) > 1 else "0" * 64

    check_scope.digest_of = flaky
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            rc = check_scope.main(["check_scope.py", str(p)])
    finally:
        check_scope.digest_of = real
    c.ok(rc == 2, f"a brief that changes mid-read must produce no verdict, got {rc}")
    c.ok("changed while this check was reading it" in out.getvalue(),
         f"the refusal must say what happened: {out.getvalue()}")
    c.ok("violation(s)" not in out.getvalue(),
         f"a refusal must not also hand out a verdict: {out.getvalue()}")


@case("a-sibling-brief-cannot-step-around-the-armed-one")
def _(repo, c):
    """`.prompire/**` is always inside the boundary, so copying the active brief and
    widening the copy is one allowed Write. Checking that copy must not quietly produce a
    verdict with the real pin not binding."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    _tamper(repo, commit=False)
    q = fixtures.write(repo, ".prompire/wide.yaml",
                       p.read_text(encoding="utf-8").replace("forbidden: [golden/**]", "")
                       .replace("scope: [src/cart.py]", 'scope: ["**"]'))
    _refused(c, tool("check_scope.py", q), ".prompire/spec.yaml")
    # nor does `--base` get one: it chooses the revision, not which brief is in force
    _refused(c, tool("check_scope.py", q, "--base", head), ".prompire/spec.yaml")
    tool("check_scope.py", p, "--deactivate")
    c.ok(tool("check_scope.py", q).returncode != 2,
         "with the guard off, any brief may be checked again")


@case("the-pointer-parses-the-same-on-both-sides")
def _(repo, c):
    """The hook strips before splitting lines. If this side does not, a pointer with one
    leading blank line leaves the guard armed while the pin silently stops binding —
    armed-looking and unpinned is the stealthiest of the available states, so the two
    parsers must agree. Also: a pointer with no readable path is garbage, not a record,
    and must not lock `--activate` out of the repo forever."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    ptr = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    ptr.write_text("\n" + ptr.read_text(encoding="utf-8"), encoding="utf-8")
    new = _tamper(repo)
    _spec(repo, new)
    _refused(c, tool("check_scope.py", p), head)

    ptr.write_text("base_rev deadbeefdeadbeef\n", encoding="utf-8")   # no path line
    _spec(repo, head)
    r = tool("check_scope.py", p, "--activate")
    c.ok(r.returncode == 0,
         f"a path-less pointer must not lock activation out: {r.stdout}{r.stderr}")


@case("an-uncorroborated-base-is-flagged-not-swallowed")
def _(repo, c):
    """Neither record exists — guard unarmed, brief gitignored — which is the ordinary
    case, so this must stay a run that produces a verdict. What it must not do is present
    the base as checked. `--strict` is the reviewer-facing invocation: it turns the flag
    into a non-zero exit."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    g = guard(p)
    c.ok(g["base_source"] is None, f"base_source should be null, got {g['base_source']!r}")
    c.ok(any("nothing outside the brief corroborates" in f["message"]
             for f in g["findings"] if f["kind"] == "REVIEW"),
         f"an uncorroborated base must be flagged: {g['findings']}")
    r = tool("check_scope.py", p)
    c.ok(r.returncode == 0 and "uncorroborated" in r.stdout,
         f"the summary line must say how the base was established: {r.stdout}")
    c.ok(tool("check_scope.py", p, "--strict").returncode == 1,
         "--strict must not exit 0 on a base nothing corroborates")

    tool("check_scope.py", p, "--activate")
    g = guard(p)
    c.ok(g["base_source"] == "pin", f"base_source should be pin, got {g['base_source']!r}")
    c.ok(not [f for f in g["findings"] if "corroborates" in f["message"]],
         f"a pinned base must not still be flagged as uncorroborated: {g['findings']}")


@case("re-arming-cannot-quietly-replace-the-pin")
def _(repo, c):
    """The record is only worth what replacing it costs. Re-running `--activate` after
    the brief moved, or arming a second brief over the top, would each overwrite it with
    the brief's current claim — so both are refused, and the way out is `--deactivate`,
    which is a named act that leaves a tombstone."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    new = _tamper(repo)
    _spec(repo, new)

    r = tool("check_scope.py", p, "--activate")
    c.ok(r.returncode == 2 and head in r.stdout,
         f"re-arming after a re-stamp must be refused: exit {r.returncode}: {r.stdout}")
    ptr = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    c.ok(f"base_rev {head}" in ptr.read_text(encoding="utf-8"),
         f"the refused re-arm still moved the pin: {ptr.read_text(encoding='utf-8')!r}")

    q = fixtures.write(repo, ".prompire/other.yaml",
                       RESTAMP_BRIEF.format(base=new).lstrip())
    r = tool("check_scope.py", q, "--activate")
    c.ok(r.returncode == 2 and "already active" in r.stdout,
         f"arming a second brief over a live record must be refused: {r.stdout}")
    c.ok(f"base_rev {head}" in ptr.read_text(encoding="utf-8"),
         f"a second brief overwrote the first one's pin: {ptr.read_text(encoding='utf-8')!r}")

    c.ok(tool("check_scope.py", p, "--deactivate").returncode == 0 and not ptr.exists(),
         "--deactivate must remain the way out")


@case("an-unreadable-tombstone-log-is-not-a-clean-slate")
def _(repo, c):
    """The sibling of the jammed-directory case, for the shape `Path.exists()` lies about.

    A directory at the log's path is caught because `exists()` says True and the read
    then fails. The shape `exists()` actively lies about is one where `stat()` itself
    errors — a symlink loop is the reproducible one — because `Path.exists()` swallows
    that OSError and answers False. False here means "no disarm was ever recorded", so
    an unreachable record used to earn a full `pin`, the strongest label this tool
    prints, handed out precisely because nothing could be read. `any_disarm` reads the
    file rather than asking whether it is there, so every unreadable shape lands on
    "unreadable". Note a mode-000 file is NOT this case: `stat()` needs no read
    permission, so `exists()` answers True there and the old code was already right.

    Reaching this state needs a shell, like the jammed-directory case next door. Also
    like it, the state can predate the guard, so nothing downstream may assume it away.
    """
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")
    tool("check_scope.py", p, "--deactivate")
    log = pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones"
    c.ok(log.is_file() and log.read_text(encoding="utf-8").strip() != "",
         "the disarm was not recorded, so this case cannot test what it claims to")
    log.unlink()
    log.symlink_to("ACTIVE.tombstones")     # points at itself: ELOOP on open and on stat
    c.ok(not log.exists(), "the loop did not make Path.exists() answer False")

    r = tool("check_scope.py", p, "--activate")
    c.ok("Traceback" not in r.stderr,
         f"an unreadable log must not crash --activate: {r.stderr[:200]}")
    c.ok("repin" in (r.stdout + r.stderr).lower(),
         f"an unreadable log was read as a clean slate: {r.stdout}{r.stderr}")


@case("baseline-writes-a-block-that-reads-back-as-what-it-measured")
def _(repo, c):
    """Two ways the printed `baseline:` block used to stop describing the run.

    `cmd: no` is a real command on a repo with a `no` script, and YAML 1.1 resolves a
    bare `no` to the boolean False — so the block re-read as a boolean and every
    consumer downstream compared it against the brief's string and called it drift.
    And `dirty()` skipped the brief's own directory by a literal `.prompire/` prefix,
    which only matches when the brief sits at the git root: vendored one directory down,
    writing the brief made its own baseline refuse to run."""
    sys.path.insert(0, str(SKILL))
    import yaml as _yaml

    import baseline as bl
    for cmd in ("no", "yes", "off", "null", "007", "make test"):
        block = bl.render_block(
            [{"cmd": cmd, "cwd": ".", "status": "pass", "evidence": "exit 0"}], "abc1234")
        got = _yaml.safe_load(block)["baseline"][0]["cmd"]
        c.ok(got == cmd, f"`cmd: {cmd}` re-read as {got!r} ({type(got).__name__})")

    nested = pathlib.Path(repo) / "vendor" / "skill" / ".prompire"
    nested.mkdir(parents=True)
    (nested / "spec.yaml").write_text("goal: x\n", encoding="utf-8")
    c.ok("vendor/skill/.prompire/spec.yaml" not in bl.dirty(pathlib.Path(repo), set()),
         "a brief one directory down still dirties its own baseline")
    (pathlib.Path(repo) / "vendor" / "skill" / "note.md").write_text("x", encoding="utf-8")
    c.ok("vendor/skill/note.md" in bl.dirty(pathlib.Path(repo), set()),
         "the skip swallowed an ordinary file next to the brief")


@case("a-short-and-a-full-sha-for-one-commit-do-not-disagree")
def _(repo, c):
    """`--base $(git rev-parse HEAD)` naming the pinned commit is not a disagreement.

    `baseline.py` stamps a 12-character short SHA, and the pin/`--base` comparison was a
    literal string compare — so the obvious thing a reviewer types, the full SHA of the
    very commit that is pinned, was reported as "the two disagree" and under `--strict`
    became exit 1. A spurious flag is worse than a missing one: it trains the operator to
    read this particular REVIEW as noise, and its whole job is to be believed on the day
    the two really do differ. So both halves are asserted here — the equal case must be
    silent, and the genuinely different case must still speak."""
    head_full = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head_full[:12])          # the short form baseline.py would stamp
    tool("check_scope.py", p, "--activate")

    g = guard(p, "--base", head_full)
    notes = [f for f in g["findings"] if "disagree" in f["message"]]
    c.ok(not notes, f"a short and a full SHA for one commit were called a disagreement: {notes}")

    r = tool("check_scope.py", p, "--base", head_full, "--strict")
    c.ok(r.returncode == 0,
         f"--strict exited {r.returncode} on a base that matches the pin: {r.stdout}")

    fixtures.write(repo, "src/cart.py",
                   (pathlib.Path(repo) / "src/cart.py").read_text(encoding="utf-8") + "\n# later\n")
    fixtures.git(repo, "add", "--", "src/cart.py")
    fixtures.git(repo, "commit", "-qm", "a second commit to point --base at")
    g2 = guard(p, "--base", fixtures.git(repo, "rev-parse", "HEAD").strip())
    c.ok([f for f in g2["findings"] if "disagree" in f["message"]],
         f"a genuinely different base must still be flagged: {g2['findings']}")


# ------------------------------------------------ GitHub Copilot CLI, on real repos

COPILOT_HOOK = str(SKILL / "hook_copilot_guard.py")


def copilot_hook(repo, tool_name, args, cwd=None):
    """One Copilot CLI `preToolUse` call, as a real subprocess on a real repo."""
    payload = json.dumps({"sessionId": "e2e", "timestamp": 0, "cwd": str(cwd or repo),
                          "toolName": tool_name, "toolArgs": args})
    return subprocess.run([sys.executable, COPILOT_HOOK], input=payload,
                          capture_output=True, text=True, encoding="utf-8")


def _denial(c, r, *must_contain):
    """A Copilot denial is exit 0 plus one JSON object — never a non-zero exit.

    Copilot CLI reads a crash or any non-zero exit from a command `preToolUse` hook as a
    denial of its own, so a hook that refused by exiting 2 would look identical to a
    hook that crashed. The difference matters: one is a decision the brief made, the
    other is Prompire being broken, and Prompire being broken is required to allow.
    """
    c.ok(r.returncode == 0,
         f"a Copilot denial must still exit 0, got {r.returncode}: {r.stderr[:200]}")
    c.ok(not r.stderr.strip(), f"the hook wrote to stderr: {r.stderr[:200]}")
    try:
        decision = json.loads(r.stdout)
    except ValueError:
        c.ok(False, f"denial is not valid JSON: {r.stdout[:200]!r}")
        return {}
    c.ok(decision.get("permissionDecision") == "deny",
         f"expected a deny decision, got {decision}")
    for s in must_contain:
        c.ok(s in decision.get("permissionDecisionReason", ""),
             f"denial reason does not mention {s!r}: {decision}")
    return decision


@case("copilot-hook-and-the-checker-draw-one-boundary")
def _(repo, c):
    """The early guard and the post-hoc authority must not be two opinions.

    The Copilot adapter is a different protocol, not a different boundary: it calls the
    same `boundary_verdict` that `check_scope.py` calls against the real diff
    afterwards. So the same path must draw a refusal before the write and a VIOLATION
    after it — and the second one is what the verdict rests on, since the first can be
    walked around."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")

    _denial(c, copilot_hook(repo, "create",
                            {"path": "golden/report.txt", "content": "x"}), "forbidden")
    c.ok(not copilot_hook(repo, "edit", {"path": "src/cart.py"}).stdout.strip(),
         "an in-scope edit must reach Copilot's normal permission flow, not a denial")

    # The write happens anyway — the hook is a speed bump, and this is what the
    # authority sees.
    fixtures.write(repo, "golden/report.txt", "apples: 3\npears: 5\nTAMPERED\n")
    g = guard(p)
    c.ok(any("golden/report.txt" in v["path"] and "forbidden" in v["message"]
             for v in violations(g)),
         f"the checker must flag the same path the hook refused: {g['findings']}")


@case("copilot-shell-writes-bypass-the-hook-and-the-git-diff-catches-them")
def _(repo, c):
    """The documented gap, reproduced rather than asserted in prose.

    `bash` and `powershell` are deliberately not matched: reading a command line for the
    files it will touch is a much weaker claim than reading a diff, and a guard that
    pretends otherwise is worse than one with a stated hole. So the identical
    out-of-scope path must be refused under `create` and pass untouched under `bash`,
    and `check_scope.py` must still see the file the shell actually wrote."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")

    _denial(c, copilot_hook(repo, "create", {"path": "src/other.py"}), "outside `scope`")
    shell = copilot_hook(repo, "bash", {"command": "echo x > src/other.py"})
    c.ok(shell.returncode == 0 and not shell.stdout.strip(),
         f"a shell call must pass untouched, not be claimed as checked: {shell.stdout!r}")

    subprocess.run("echo x > src/other.py", shell=True, cwd=str(repo), check=True)
    g = guard(p)
    c.ok(any("src/other.py" in v["path"] for v in violations(g)),
         f"the git diff must catch the write the hook never saw: {g['findings']}")


@case("copilot-multi-file-patch-is-judged-whole")
def _(repo, c):
    """A tool call is atomic, so a patch is judged on every file it names.

    The first file here is squarely in `scope`; the second is `forbidden`. A guard that
    answered from the first path would approve the whole patch, and the forbidden write
    would land with the hook's blessing. The refusal must name the offending path, not
    the innocent one."""
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    p = _spec(repo, head)
    tool("check_scope.py", p, "--activate")

    patch = ("*** Begin Patch\n"
             "*** Update File: src/cart.py\n@@\n-    return sum(items) - 1\n"
             "+    return sum(items)\n"
             "*** Update File: golden/report.txt\n@@\n-apples: 3\n+apples: 4\n"
             "*** End Patch\n")
    decision = _denial(c, copilot_hook(repo, "apply_patch", {"input": patch}),
                       "forbidden")
    c.ok("golden/report.txt" in decision.get("permissionDecisionReason", ""),
         f"the refusal must name the offending file, not the first one: {decision}")
    c.ok("src/cart.py" not in decision.get("permissionDecisionReason", ""),
         f"the refusal must not blame the in-scope file: {decision}")

    # A patch whose every file is inside the boundary is not refused.
    ok_patch = ("*** Begin Patch\n*** Update File: src/cart.py\n@@\n-a\n+b\n"
                "*** End Patch\n")
    r = copilot_hook(repo, "apply_patch", {"input": ok_patch})
    c.ok(r.returncode == 0 and not r.stdout.strip(),
         f"an entirely in-scope patch must not be refused: {r.stdout!r}")


@case("the-copilot-workflow-end-to-end")
def _(repo, c):
    """measure -> lint -> render copilot -> activate -> work -> --strict, on one repo.

    The same six commands the Claude workflow runs, with one different `--target`. What
    this pins is that nothing about the host changed the order or the meaning: the
    baseline is still measured before the work, `--activate` still happens before the
    agent starts, and `--strict` is still the human's check afterwards."""
    p, data = measured(repo, "copilot-flow", """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
forbidden: [golden/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
""")
    c.ok(any(r["status"] == "fail" for r in data["results"]),
         f"sanity: the flip criterion must be red on HEAD: {data['results']}")
    c.ok(not lint(p)["findings"] or all(f["severity"] != "error"
                                        for f in lint(p)["findings"]),
         f"the brief must lint clean before it is armed: {lint(p)['findings']}")

    r = tool("render_brief.py", p, "--target", "copilot")
    c.ok(r.returncode == 0,
         f"the copilot target must render inside the word budget: {r.stdout}{r.stderr}")
    c.ok("check_scope.py" in r.stdout and "preToolUse" in r.stdout,
         f"the copilot prompt must name both layers: {r.stdout}")

    c.ok(tool("check_scope.py", p, "--activate").returncode == 0, "arming must succeed")

    # The agent works, inside the boundary. The hook agrees; then the real diff does.
    c.ok(not copilot_hook(repo, "edit", {"path": "src/cart.py"}).stdout.strip(),
         "the in-scope edit must not be refused")
    _denial(c, copilot_hook(repo, "create", {"path": "golden/report.txt"}), "forbidden")
    fixtures.write(repo, "src/cart.py",
                   (pathlib.Path(repo) / "src/cart.py").read_text(encoding="utf-8")
                   .replace("return sum(items) - 1", "return sum(items)"))

    strict = tool("check_scope.py", p, "--strict")
    c.ok(strict.returncode == 0,
         f"--strict must be clean on an armed, in-scope run: {strict.stdout}{strict.stderr}")
    c.ok(guard(p)["base_source"] == "pin",
         f"the base must be corroborated by the pin, not merely uncontradicted: "
         f"{guard(p)['base_source']!r}")


@case("a path git cannot decode as utf-8 still gets a verdict")
def _(repo, c):
    """The one case where the decoder is load-bearing rather than merely tidy.

    git stores path *bytes*, so a repository can carry a name that is not valid UTF-8 in
    any encoding, and `git diff --name-status -z` hands those bytes straight back. Decoded
    with the locale's codec — which is what `text=True` does — that raised
    `UnicodeDecodeError` *inside* subprocess, so the post-hoc authority answered a real
    violation with a traceback; naming utf-8 without naming `errors=` then moved the same
    crash to the `print()`. Exit 1 with the path escaped is the only acceptable answer:
    this tool's vocabulary is 0/1/2 and a stack trace is none of them.

    The entry goes in through the index because no mainstream filesystem will hold the
    name — which is also why this case is the only place either half is exercised.
    """
    if os.name == "nt":
        return          # git for Windows will not put these bytes in an index entry
    weird = b"src/we\xffird.py"
    blob = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                          input=b"leak\n", capture_output=True, check=True).stdout.strip()
    added = subprocess.run(["git", "-C", str(repo), "update-index", "--add",
                            b"--cacheinfo", b"100644," + blob + b"," + weird],
                           capture_output=True)
    c.ok(added.returncode == 0,
         f"sanity: the undecodable path must reach the index, else this case proves "
         f"nothing: {added.stderr!r}")
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "undecodable"],
                   capture_output=True, check=True)

    # The file is in that commit but never in the working tree, so it reads as a deletion
    # outside `scope` — a finding the guard has to be able to name.
    p = brief(repo, "undecodable", """
goal: Touch nothing but the cart.
scope: [src/cart.py]
autonomy: ask
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
""")
    r = tool("check_scope.py", p, "--json")
    c.ok(r.returncode == 1,
         f"an undecodable path must be a verdict, not a crash: exit {r.returncode} "
         f"{r.stdout}{r.stderr}")
    c.ok("Traceback" not in r.stderr, f"the guard must not raise: {r.stderr}")
    paths = [f["path"] for f in json.loads(r.stdout)["findings"]]
    c.ok(weird.decode("utf-8", "surrogateescape") in paths,
         f"the path must round-trip byte-for-byte, not be flattened into one that names "
         f"a different file: {paths}")

    prose = tool("check_scope.py", p)
    c.ok(prose.returncode == 1 and "Traceback" not in prose.stderr,
         f"reporting the same verdict as prose must not raise either: exit "
         f"{prose.returncode} {prose.stderr}")


@case("gitignored-paths-are-outside-the-checker-evidence")
def _(repo, c):
    """The documented truth boundary, pinned. The checker's evidence is `git diff`
    against the pinned base plus `git status --untracked-files=all`, and both exclude
    gitignored paths — so a write under an ignored directory draws no finding at all.
    references/threat-model.md carries this as a limitation row; this case keeps that
    row, and the qualified wording in README.md and references/hosts.md, describing
    the code. If ignored paths ever become visible, the path-set semantics changed
    and the docs went from truthful to overcautious — both need a deliberate
    decision, not a drive-by."""
    gi = pathlib.Path(repo) / ".gitignore"
    gi.write_text(gi.read_text(encoding="utf-8") + "vendor/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "ignore vendor"],
                   capture_output=True)
    p = brief(repo, "spec", """
goal: Fix the off-by-one in src/cart.total().
scope: [src/cart.py]
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
""")
    tool("check_scope.py", p, "--activate")
    evil = pathlib.Path(repo) / "vendor" / "evil.sh"
    evil.parent.mkdir()
    evil.write_text("#!/bin/sh\necho pwned\n", encoding="utf-8")
    g = guard(p)
    c.ok(g["violations"] == 0 and g["reviews"] == 0,
         f"an ignored path must stay outside the diff authority: {g['findings']}")
    r = tool("check_scope.py", p, "--strict")
    c.ok(r.returncode == 0,
         f"--strict must exit 0 when only an ignored path was written: "
         f"{r.stdout}{r.stderr}")


@case("p3-failed-lint-restores-the-brief-bytes-exactly-and-retry-works")
def _(repo, c):
    """R5, reproduced and closed: prepare runs baseline --write before lint, so a
    lint failure used to leave the measured base_rev/baseline block behind and
    baseline.py then refused the corrected retry. The restore is byte-level —
    comments, ordering, whitespace, the CRLF line below — not a reserialization."""
    p = pathlib.Path(repo) / ".prompire" / "p3-restore.yaml"
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(
        b"# operator note \xe2\x80\x94 must survive a failed prepare\r\n"
        b"goal: Add a count helper to src/cart.py.\n"
        b"scope: []\n"
        b"tests_policy: immutable\n"
        b'acceptance:\n  - cmd: python3 -c "pass"\n    expect: exit 0\n'
        b"manual_checks:\n  - the diff adds the count helper\n"
        b"autonomy: ask\n")
    original = p.read_bytes()

    r = cli(repo, "prepare", ".prompire/p3-restore.yaml")
    c.ok(r.returncode == 1,
         f"lint must fail this prepare: {r.returncode} {r.stdout}{r.stderr}")
    c.ok(p.read_bytes() == original,
         f"a failed prepare must restore the brief byte-for-byte: {p.read_bytes()!r}")
    c.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
         "a failed prepare must not arm")
    c.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE.tombstones").exists(),
         "a failed prepare must not cost a tombstone")

    p.write_bytes(original.replace(b"scope: []", b"scope: [src/cart.py]"))
    retry = cli(repo, "prepare", ".prompire/p3-restore.yaml")
    c.ok(retry.returncode == 0,
         f"correcting the actual error must be enough — no manual stripping of "
         f"base_rev/baseline: {retry.returncode} {retry.stdout}{retry.stderr}")
    text = p.read_text(encoding="utf-8")
    c.ok("base_rev:" in text and "baseline:" in text,
         "the successful retry measures and writes the block")


@case("p3-dirty-tree-refuses-prepare-before-anything-runs")
def _(repo, c):
    """The refusal comes first, so nothing gets a chance to write. An untracked
    file at the repo root makes prepare refuse before the baseline stage runs,
    and both that file and the brief come through byte-identical — there is no
    stage output to restore because no stage ran."""
    payload = fixtures.write(repo, "payload.bin",
                             "sentinel bytes the tool must not touch\n")
    p = p3_brief(repo, "p3-payload", """
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
acceptance:
  - cmd: python3 -c "pass"
    expect: exit 0
manual_checks:
  - the diff adds the count helper
autonomy: ask
""")
    original = p.read_bytes()
    r = cli(repo, "prepare", ".prompire/p3-payload.yaml")
    c.ok(r.returncode == 2,
         f"a dirty tree must refuse prepare: {r.returncode} {r.stdout}{r.stderr}")
    c.ok("payload.bin" in (r.stdout + r.stderr), "the refusal must name the dirt")
    c.ok(payload.read_text(encoding="utf-8")
         == "sentinel bytes the tool must not touch\n",
         "the pre-existing payload must survive byte-for-byte")
    c.ok(p.read_bytes() == original, "a refused prepare must not touch the brief")


@case("p3-successful-activation-is-never-rolled-back")
def _(repo, c):
    """The commit point: after --activate succeeds, the measured block stays and
    the pointer's digest attests to the brief exactly as armed — so any later
    rollback would be observable here as a digest mismatch (exit 2)."""
    p = p3_brief(repo, "p3-commit", """
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
tests_policy: immutable
acceptance:
  - cmd: python3 -c "pass"
    expect: exit 0
manual_checks:
  - the diff adds the count helper
autonomy: ask
""")
    r = cli(repo, "prepare", ".prompire/p3-commit.yaml")
    c.ok(r.returncode == 0, f"prepare: {r.returncode} {r.stdout}{r.stderr}")
    armed = p.read_bytes()
    c.ok(b"base_rev:" in armed and b"baseline:" in armed,
         "the committed transaction keeps the measured block")
    ptr = (pathlib.Path(repo) / ".prompire" / "ACTIVE").read_text(encoding="utf-8")
    sha = next(ln.split()[1] for ln in ptr.splitlines() if ln.startswith("sha256 "))
    c.ok(sha == hashlib.sha256(armed).hexdigest(),
         "the pointer's digest must attest to the brief exactly as armed")
    v = cli(repo, "verify", ".prompire/p3-commit.yaml", "--json")
    c.ok(v.returncode == 0,
         f"the armed task must verify cleanly right away: {v.stdout}{v.stderr}")


@case("p3-activation-that-commits-then-fails-is-not-rolled-back")
def _(repo, c):
    """The `--activate` child's exit code is not a witness for the commit.
    check_scope writes `.prompire/ACTIVE` inside the guard-state lock, so a
    failure to release that lock — anything that drops a file into the lock
    directory, a kill, an OOM — reports nonzero for an activation that already
    landed. Restoring the brief there breaks the digest the pointer attests to
    and wedges the repo at exit 2 until a tombstone-costing `--deactivate`.

    The failure is injected, not raced: a `sitecustomize.py` on PYTHONPATH makes
    `rmdir` fail for the lock directory, and only inside the `--activate` child.
    A flaky security test is worse than none."""
    inject = pathlib.Path(repo) / ".prompire" / "inject"
    inject.mkdir(parents=True, exist_ok=True)
    (inject / "sitecustomize.py").write_text('''
import sys
if "--activate" in sys.argv:
    import pathlib
    real = pathlib.Path.rmdir

    def patched(self):
        if self.name == "ACTIVE.lock":
            raise OSError("injected: guard-state lock could not be released")
        return real(self)

    pathlib.Path.rmdir = patched
'''.lstrip(), encoding="utf-8")

    p = p3_brief(repo, "p3-wedge", """
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
tests_policy: immutable
acceptance:
  - cmd: python3 -c "pass"
    expect: exit 0
manual_checks:
  - the diff adds the count helper
autonomy: ask
""")
    r = cli(repo, "prepare", ".prompire/p3-wedge.yaml",
            env={"PYTHONPATH": str(inject)})
    c.ok(r.returncode != 0,
         f"the injected lock-release failure must surface: "
         f"{r.returncode} {r.stdout}{r.stderr}")

    armed = p.read_bytes()
    c.ok(b"base_rev:" in armed and b"baseline:" in armed,
         "an activation that committed must not be rolled back by a failure "
         "reported after the pointer was written")
    pointer = pathlib.Path(repo) / ".prompire" / "ACTIVE"
    c.ok(pointer.exists(), "the injection must leave the pointer written")
    if pointer.exists():
        sha = next((ln.split()[1] for ln in
                    pointer.read_text(encoding="utf-8").splitlines()
                    if ln.startswith("sha256 ")), None)
        c.ok(sha == hashlib.sha256(armed).hexdigest(),
             "the pointer's digest must still attest to the brief on disk")
    v = cli(repo, "verify", ".prompire/p3-wedge.yaml", "--json")
    c.ok(v.returncode != 2,
         f"the repo must not be wedged at exit 2 by a digest the tool itself "
         f"broke: {v.returncode} {v.stdout}{v.stderr}")


@case("p3-activation-that-fails-before-committing-is-rolled-back")
def _(repo, c):
    """The other side of the same question. When `--activate` dies before the
    pointer is written there is no commit to protect, so the transaction owes
    the user the brief it started with — otherwise the measured block sits in a
    file no pointer attests to, and the corrected retry has to strip it by hand.

    Injected the same way as the wedge case, one call earlier: a
    `sitecustomize.py` on PYTHONPATH makes `mkdir` fail for the guard-state lock
    directory, and only inside the `--activate` child. Acquiring that lock is
    the first thing activation does, so the failure is unambiguously before the
    pointer write."""
    inject = pathlib.Path(repo) / ".prompire" / "inject"
    inject.mkdir(parents=True, exist_ok=True)
    (inject / "sitecustomize.py").write_text('''
import sys
if "--activate" in sys.argv:
    import pathlib
    real = pathlib.Path.mkdir

    def patched(self, *args, **kwargs):
        if self.name == "ACTIVE.lock":
            raise OSError("injected: guard-state lock could not be acquired")
        return real(self, *args, **kwargs)

    pathlib.Path.mkdir = patched
'''.lstrip(), encoding="utf-8")

    p = p3_brief(repo, "p3-precommit", """
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
tests_policy: immutable
acceptance:
  - cmd: python3 -c "pass"
    expect: exit 0
manual_checks:
  - the diff adds the count helper
autonomy: ask
""")
    original = p.read_bytes()
    r = cli(repo, "prepare", ".prompire/p3-precommit.yaml",
            env={"PYTHONPATH": str(inject)})
    c.ok(r.returncode == 2,
         f"the injected lock-acquire failure must surface as the activate "
         f"stage's failure: {r.returncode} {r.stdout}{r.stderr}")
    c.ok("activate" in (r.stdout + r.stderr),
         f"the report must name the stage that failed: {r.stdout}{r.stderr}")
    c.ok(not (pathlib.Path(repo) / ".prompire" / "ACTIVE").exists(),
         "the injection must fail before any pointer is written")
    c.ok(p.read_bytes() == original,
         "an activation that never committed must leave the brief exactly as "
         "prepare found it — no pointer attests to the measured block, so the "
         "block must not survive either")

    retry = cli(repo, "prepare", ".prompire/p3-precommit.yaml")
    c.ok(retry.returncode == 0,
         f"the restored brief must be preparable again without hand-editing: "
         f"{retry.returncode} {retry.stdout}{retry.stderr}")


@case("p3-standalone-baseline-still-refuses-to-overwrite")
def _(repo, c):
    """Prepare became transactional; the standalone tool did not become
    overwriteable. The refusal at baseline.py's --write is a preserved
    invariant, and the measured brief's bytes survive the refusal."""
    p, _ = measured(repo, "p3-measured", """
goal: Add a count helper to src/cart.py.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
autonomy: ask
""")
    before = p.read_bytes()
    r = tool("baseline.py", p, "--write")
    c.ok(r.returncode == 1 and "refused" in r.stdout,
         f"an already measured brief must refuse --write: {r.returncode} {r.stdout}")
    c.ok(p.read_bytes() == before, "the refusal must not touch the brief")


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="prompire-e2e-"))
    fails = 0
    for name, fn in CASES:
        repo = tmp / name
        fixtures.build(repo)
        c = Checks()
        try:
            fn(repo, c)
        except Exception as e:  # a crash is a failing case, not a crashed run
            c.fails.append(f"raised {type(e).__name__}: {e}")
        ok = not c.fails
        fails += 0 if ok else 1
        print(f"{'pass' if ok else 'FAIL'}  {name}")
        for f in c.fails:
            print(f"        {f}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} end-to-end cases pass")
    if not VERBOSE:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"repos kept at {tmp}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
