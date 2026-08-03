#!/usr/bin/env python3
"""Lint an agent brief. Rules and their book sources: references/grounding.md.
Field-by-field schema: references/schema.md. Rule semantics: references/rules.md.

Usage: python3 lint_brief.py brief.yaml [--json]
Exit 0 = no errors (warnings allowed), 1 = at least one error, 2 = brief unreadable.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from brief_common import (
    ACCEPTANCE_KEYS,
    AUTONOMY,
    BASELINE_KEYS,
    BASELINE_STATUS,
    DRAFT_LEDGER,
    DRAFT_MARKER,
    REQUIRES_VOCAB,
    TESTS_POLICIES,
    TOP_KEYS,
    TRANSITIONS,
    BriefError,
    acceptance_entries,
    as_list,
    baseline_map,
    effective_transition,
    entry_key,
    glob_re,
    is_test_path,
    legacy_pinned,
    load_brief,
    manual_check_entries,
    norm_cmd,
    tests_policy_of,
    utf8_stdio,
)

VAGUE = [
    "properly", "correctly", "clean up", "cleanly", "robust", "best practice",
    "as needed", "as appropriate", "where appropriate", "if necessary", "etc.",
    "improve", "optimize", "enhance", "better", "nicer", "modern", "idiomatic",
    "production-ready", "appropriate", "reasonable", "sensible", "gracefully",
    "as you see fit", "make sure it works", "various", "several", "some kind of",
    "nice", "clean", "tidy", "readable", "simple", "elegant",
    "správně", "pořádně", "hezky", "lépe", "vylepši", "zlepši", "vyčisti",
    "moderní", "rozumně", "dle potřeby", "atd.", "nějak", "případně",
]
# first token of an acceptance cmd that means it is prose, not a command
NL_FIRST = {"the", "a", "an", "all", "it", "code", "tests", "test", "build",
            "everything", "no", "there", "ensure", "verify", "check", "make",
            "should", "must", "app", "project", "output", "user", "behavior",
            "kód", "testy", "aplikace", "vše", "nic", "musí", "mělo"}
DESTRUCTIVE = [
    "rm -rf", "rm -r", "drop table", "drop database", "truncate table",
    "push --force", "push -f", "force-push", "git reset --hard", "git clean -fd",
    "deploy", "terraform apply", "kubectl apply", "npm publish", "cargo publish",
    "alembic upgrade", "prisma migrate deploy", "flyway migrate",
]
TEST_RUNNERS = ["pytest", "unittest", "npm test", "npm run test", "yarn test",
                "pnpm test", "jest", "vitest", "cargo test", "go test", "mvn test",
                "gradle test", "rspec", "phpunit", "dotnet test", "bun test"]
BIG_TASK = ["refactor", "refaktor", "migrate", "migrac", "rewrite", "přepiš",
            "redesign", "port ", "upgrade", "modernize", "extract", "split",
            "restructure", "rename across", "overhaul"]
BEHAVIOR_PRESERVING = ["refactor", "refaktor", "port ", "upgrade", "migrate",
                       "rename", "extract", "restructure", "modernize"]
COMPARE = ["golden", "snapshot", "baseline", "diff", "before", "expected/",
           "fixtures/", "approval", "cmp", "hash", "checksum"]
# an `expect` a human can read two ways is not a check — "everything green" fails this
OBSERVABLE = ["exit", "empty", "match", "json", "==", "!=", "count", "list", "output",
              "zero", "error", "warning", "prints", "contains", "diff", "line", "byte",
              "pass", "fail", "identical", "unchanged", "same",
              "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]


def _rx(terms, tail):
    """Match terms on word boundaries. Bare substrings misfire: "report CLI" contains
    "port ", "modernize-py" contains "modern"."""
    parts = []
    for t in terms:
        p = (r"\b" if re.match(r"\w", t) else "") + re.escape(t)
        if re.search(r"\w$", t):
            p += tail
        parts.append(p)
    return re.compile("|".join(parts), re.I)


# whole words only — "modern" must not match "modernize-py"
VAGUE_RX = _rx(VAGUE, r"\b")
# stems allowed ("migrac" + "e"), identifiers not ("upgrade-tool")
BIG_RX = _rx(BIG_TASK, r"(?![-_.]\w)")
PRESERVE_RX = _rx(BEHAVIOR_PRESERVING, r"(?![-_.]\w)")
# "deploy" should also catch "deployment"
DESTRUCTIVE_RX = _rx(DESTRUCTIVE, "")

findings = []


def add(sev, rule, msg, fix=""):
    findings.append({"severity": sev, "rule": rule, "message": msg, "fix": fix})


def err(rule, msg, fix=""):
    add("error", rule, msg, fix)


def warn(rule, msg, fix=""):
    add("warn", rule, msg, fix)


def text_of(v):
    return " ".join(str(x) for x in as_list(v)).lower()


def vague_hits(s):
    return sorted({m.group(0).lower() for m in VAGUE_RX.finditer(s)})


def bad_path(p):
    """Scope and forbidden entries are repo-relative. Absolute paths and `..` escapes
    silently move the boundary the guard is supposed to enforce."""
    s = str(p).strip()
    if s.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", s) or s.startswith("~"):
        return "absolute"
    if ".." in s.split("/"):
        return "escapes the repo"
    return None


def check_goal(b, goal, gl):
    if not goal:
        err("B1 missing-goal", "no `goal` — a task is defined by its goal and constraints",
            "one imperative sentence, max 30 words")
        return
    words = len(goal.split())
    sentences = len([s for s in re.split(r"[.!?](?:\s|$)", goal) if s.strip()])
    if words > 30:
        err("B2 goal-too-long", f"goal is {words} words — that is a plan, not a goal",
            "cut to one sentence; move the rest into constraints or split the brief")
    if sentences > 1:
        err("B2 goal-multi-sentence", f"goal has {sentences} sentences — likely 2+ tasks",
            "one brief per task; split it")
    if re.search(r"\b(and then|,? then|afterwards|poté|a pak)\b|,\s+and\b|,\s+a\s", gl):
        warn("B2 goal-sequenced", "goal describes a sequence — probably two briefs")


def check_acceptance(b, acceptance):
    """B4/B5: the acceptance block exists, every entry is a runnable command with an
    observable expectation, and no two entries collide on the (cmd, cwd) key that the
    baseline and the renderer use to match them."""
    keys = []
    if not acceptance:
        err("B4 no-acceptance", "no `acceptance` block — nothing decides whether this is done",
            "add at least one cmd/expect pair; if you cannot name one, the brief is not ready")
    for i, a in enumerate(acceptance, 1):
        if not isinstance(a, dict):
            err("B5 acceptance-prose", f"acceptance[{i}] is prose: \"{str(a)[:70]}\"",
                "use `- cmd: <command>` + `expect: <observable result>`")
            continue
        for k in a:
            if k not in ACCEPTANCE_KEYS:
                warn("B12 unknown-key", f"acceptance[{i}] has unknown key `{k}`")
        cmd = norm_cmd(a.get("cmd"))
        expect = str(a.get("expect") or "").strip()
        if not cmd:
            err("B5 acceptance-no-cmd", f"acceptance[{i}] has no `cmd`")
            continue
        key = entry_key(a)
        if key in keys:
            err("B5 duplicate-acceptance",
                f"acceptance[{i}] `{cmd[:50]}` repeats an earlier entry (same cmd and cwd)",
                "one entry per command — the baseline matches entries on (cmd, cwd) and "
                "cannot tell duplicates apart")
        keys.append(key)

        cwd = a.get("cwd")
        if cwd is not None:
            reason = bad_path(cwd)
            if reason:
                err("B5 acceptance-cwd", f"acceptance[{i}] cwd `{cwd}` is {reason}",
                    "cwd is relative to the repo root")
        timeout = a.get("timeout")
        if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
            err("B5 acceptance-timeout", f"acceptance[{i}] timeout `{timeout}` is not a "
                "positive whole number of seconds")
        for r in as_list(a.get("requires")):
            if str(r).strip().lower() not in REQUIRES_VOCAB:
                # any requires entry makes baseline AND verify refuse to run the
                # command, so a typo here silently converts the criterion into one
                # nothing ever executes (E1: a gold brief shipped a file path in
                # `requires` and its only pytest criterion never ran again)
                err("B5 unknown-requires", f"acceptance[{i}] requires `{r}` — not one of "
                    + " | ".join(REQUIRES_VOCAB),
                    "a declared requirement disables execution by design; name one "
                    "of the known environment needs, or delete the entry so the "
                    "command runs")
        t = str(a.get("transition") or "").strip().lower()
        if t and t not in TRANSITIONS:
            err("B5 bad-transition", f"acceptance[{i}] transition `{t}` — must be "
                + " | ".join(TRANSITIONS))
        if a.get("must_flip") is not None:
            warn("B15 legacy-must-flip",
                 f"acceptance[{i}] uses `must_flip` — renamed to `transition`",
                 "replace `must_flip: true` with `transition: flip`")

        first = cmd.split()[0].lower().strip("`'\"")
        if first in NL_FIRST:
            err("B5 acceptance-not-a-command", f"acceptance[{i}] `{cmd[:60]}` reads as prose",
                "the toolchain is the evaluator — give the command you would actually run")
        elif len(cmd.split()) >= 4 and not any(t.startswith("-") for t in cmd.split()) \
                and "/" not in cmd and "." not in cmd \
                and "\n" not in str(a.get("cmd") or "") and "=" not in cmd:
            # a multi-line block or an assignment is shell syntax, not prose
            warn("B5 acceptance-maybe-prose", f"acceptance[{i}] `{cmd[:60]}` may not be runnable")
        if not expect:
            err("B5 acceptance-no-expect", f"acceptance[{i}] has no `expect`",
                "e.g. `exit 0`, `empty output`, `count == 0`")
        else:
            for w in vague_hits(expect):
                err("B3 vague-expect", f"acceptance[{i}] expects \"{w}\" — not observable")
            if not any(k in expect.lower() for k in OBSERVABLE):
                warn("B5 expect-not-observable",
                     f"acceptance[{i}] expects \"{expect[:40]}\" — hard to read off the terminal",
                     "say the exit code, the count, or the exact text")
    return keys


def check_baseline(b, acceptance, keys):
    """B15: every criterion carries the value it had before the work started, and a
    criterion that is not green today says which of the three things it is doing —
    flipping to green, holding where it is, or not measurable yet."""
    baseline = b.get("baseline")
    if baseline is not None and not isinstance(baseline, list):
        err("B15 baseline-not-a-list", "`baseline` must be a list of cmd/status entries")
        baseline = None
    baseline = as_list(baseline)
    by_key = {}
    for i, e in enumerate(baseline, 1):
        if not isinstance(e, dict):
            err("B15 baseline-prose", f"baseline[{i}] is not an entry: \"{str(e)[:60]}\"",
                "use `- cmd: <the acceptance command>` + `status: pass | fail | not_runnable`")
            continue
        for k in e:
            if k not in BASELINE_KEYS:
                warn("B12 unknown-key", f"baseline[{i}] has unknown key `{k}`")
        cmd = norm_cmd(e.get("cmd"))
        status = str(e.get("status") or "").strip().lower()
        if not cmd:
            err("B15 baseline-no-cmd", f"baseline[{i}] has no `cmd`")
            continue
        if e.get("must_flip") is not None:
            warn("B15 legacy-must-flip",
                 f"baseline[{i}] uses `must_flip` — it moved to the acceptance entry",
                 "put `transition: flip` on the matching acceptance entry; the baseline "
                 "records what was measured, the acceptance records what must change")
        if status not in BASELINE_STATUS:
            err("B15 baseline-status",
                f"baseline[{i}] status is {status or 'missing'} — must be "
                + " | ".join(BASELINE_STATUS),
                "run the command on untouched HEAD and record what it actually did; if it "
                "cannot be run, say `not_runnable` and give a `reason`")
            continue
        key = entry_key(e)
        if key not in keys:
            err("B15 baseline-orphan",
                f"baseline[{i}] `{cmd[:50]}` is not one of the acceptance commands",
                "baseline entries mirror acceptance commands verbatim, including `cwd`")
            continue
        if key in by_key:
            err("B15 duplicate-baseline", f"baseline[{i}] `{cmd[:50]}` recorded twice")
            continue
        by_key[key] = e
        if status == "not_runnable" and not str(e.get("reason") or "").strip():
            err("B15 baseline-no-reason",
                f"baseline[{i}] `{cmd[:50]}` is not_runnable with no `reason`",
                "say why it could not run: the code does not exist yet, it needs "
                "credentials, it writes to the repo, it timed out")

    for a in acceptance:
        key = entry_key(a)
        cmd = key[0] if key else ""
        e = by_key.get(key)
        t = effective_transition(a, e)
        if e is None:
            if baseline:
                warn("B15 baseline-gap", f"`{cmd[:50]}` has no baseline entry")
            if t == "hold":
                err("B15 hold-without-baseline",
                    f"`{cmd[:50]}` must hold its current state but that state was "
                    "never measured",
                    "run it on HEAD and record status + evidence, or drop the criterion")
            continue
        status = str(e.get("status") or "").strip().lower()
        evidence = str(e.get("evidence") or "").strip()
        # `status` answers one question: did the command meet its own `expect` on
        # untouched HEAD. A known-red suite is written `expect: exit 1` and passes here.
        if status == "fail" and t == "green":
            err("B15 red-baseline", f"`{cmd[:50]}` does not meet its `expect` before the "
                "work starts",
                "narrow the command to what this task actually fixes, or add "
                "`transition: flip` (making it meet the expect is the goal); if it is "
                "known-red and must stay that way, write the expect that describes today "
                "— `exit 1` — and mark it `transition: hold`")
        elif status == "pass" and t == "flip":
            warn("B15 pointless-flip",
                 f"`{cmd[:50]}` already meets its `expect` but is marked `transition: flip`")
        elif status == "fail" and t == "hold":
            err("B15 hold-not-met",
                f"`{cmd[:50]}` is marked `hold` but does not meet its own `expect` today",
                "`hold` freezes the measured state, so the expect must describe that "
                "state — if the suite exits 1 today, write `expect: exit 1`")
        elif status == "not_runnable" and t == "hold":
            err("B15 hold-unmeasured",
                f"`{cmd[:50]}` cannot be run, so there is no state for it to hold",
                "use `transition: flip` if implementing it makes the command runnable")
        elif status == "not_runnable" and t == "green":
            warn("B15 unverified-baseline",
                 f"`{cmd[:50]}` was never run on HEAD ({e.get('reason')})",
                 "it cannot tell the agent's work from the state it started in; mark it "
                 "`transition: flip` if it is expected to become runnable, or move it to "
                 "`manual_checks`")
        if status in ("pass", "fail") and not evidence:
            warn("B15 no-evidence", f"`{cmd[:50]}` records a status with no `evidence`",
                 "one line: exit code and the number that mattered")
        if t == "hold" and not evidence:
            err("B15 hold-without-evidence",
                f"`{cmd[:50]}` must stay unchanged but the baseline records no `evidence`",
                "\"unchanged\" needs something to compare against: exit code plus the "
                "failure count, or an output digest")
        if a.get("before_after") and not evidence:
            err("B15 before-after-no-evidence",
                f"`{cmd[:50]}` is a before/after comparison with no baseline `evidence`",
                "record the output digest on HEAD; `baseline.py` writes it for you")

    if acceptance and not baseline:
        warn("B15 no-baseline", "no `baseline` — no acceptance command was run on HEAD first",
             "run each one before the work starts; a criterion that is already red cannot "
             "tell you the agent succeeded")


def check_scope_fields(b, scope, forbidden):
    """B6/B13: the scope is an allowlist, `forbidden` is a denylist that wins over it."""
    if not scope:
        err("B6 unbounded-scope", "no `scope` — the agent may touch anything",
            "list the paths or globs it may edit")
    for s in scope:
        s = str(s).strip()
        reason = bad_path(s)
        if reason:
            err("B6 scope-path", f"scope entry `{s}` is {reason}",
                "scope entries are repo-relative")
            continue
        if s in {".", "./", "/", "*", "**", "**/*"}:
            err("B6 unbounded-scope", f"scope entry `{s}` is the whole tree",
                "name the directories that actually change")
        elif re.fullmatch(r"[\w.-]+/(\*\*?/?\*?)?", s):
            warn("B6 wide-scope", f"scope entry `{s}` is a whole top-level directory",
                 "narrow to the files or subpackages that change")
    for f in forbidden:
        reason = bad_path(f)
        if reason:
            err("B6 forbidden-path", f"forbidden entry `{f}` is {reason}")
    if b.get("forbidden") is None:
        warn("B13 no-forbidden", "no `forbidden` list — nothing is explicitly off-limits",
             "write `forbidden: []` to say you considered it and nothing is")
    for s in scope:
        for f in forbidden:
            if bad_path(s) or bad_path(f):
                continue
            if glob_re(f).match(str(s).strip().rstrip("/")):
                err("B11 forbidden-shadows-scope",
                    f"forbidden `{f}` covers the whole scope entry `{s}`",
                    "the agent has nowhere to write; narrow one of them")


def check_tests_policy(b, acceptance):
    """B7 — the Goodhart rule. A green suite only means something if the suite could
    not be edited into being green. `tests_policy` says which of the three arrangements
    applies; `check_scope.py` is what enforces it."""
    cmds = [norm_cmd(a.get("cmd")) for a in acceptance]
    runs_tests = [c for c in cmds if any(r in c.lower() for r in TEST_RUNNERS)]
    declared = str(b.get("tests_policy") or "").strip().lower()
    editable = as_list(b.get("tests_editable"))
    oracle = str(b.get("oracle") or "").strip()

    if b.get("tests_policy") is not None and declared not in TESTS_POLICIES:
        err("B7 bad-tests-policy",
            f"tests_policy `{b.get('tests_policy')}` — must be " + " | ".join(TESTS_POLICIES))
        declared = ""

    if runs_tests and not declared and not legacy_pinned(b):
        err("B7 proxy-criterion",
            f"`{runs_tests[0][:50]}` is the only judge, and the tests are editable",
            "declare `tests_policy: immutable` (or named | authoring) so "
            "check_scope.py enforces it; the old spelling — tests/** in forbidden — "
            "still works")

    policy = tests_policy_of(b)
    if policy in ("named", "authoring") and not editable:
        err("B7 no-editable-tests",
            f"tests_policy `{policy}` without `tests_editable`",
            "list the exact test paths this task may change; everything else stays pinned")
    if policy not in ("named", "authoring") and editable:
        warn("B7 unused-editable",
             f"`tests_editable` is set but tests_policy is `{policy or 'undeclared'}`",
             "tests_editable only applies to `named` and `authoring`")
    for p in editable:
        if bad_path(p):
            err("B7 editable-path", f"tests_editable entry `{p}` is {bad_path(p)}")
        elif not is_test_path(p) and not str(p).rstrip("/*").endswith(("test", "tests", "spec")):
            warn("B7 editable-not-a-test",
                 f"tests_editable entry `{p}` does not look like a test path",
                 "tests_editable widens the test pin only; ordinary files belong in `scope`")
    if policy == "authoring" and not oracle:
        err("B7 no-oracle",
            f"tests_policy `{policy}` without `oracle`",
            "name what judges the work when the tests themselves are the deliverable: a "
            "mutation run, a golden fixture, a hidden suite, a named human review")
    if policy == "authoring":
        warn("B7 authoring-needs-review",
             "tests_policy `authoring` — no mechanical check can tell a repaired test "
             "from a weakened one",
             "a human reads the test diff; put that in `manual_checks`")


def check_discrimination(b, acceptance):
    """B17: once the baseline is measured, something must distinguish the untouched
    tree from done — otherwise `verify` prints `clean` on a repo nobody touched.
    Judged only after measurement: before it, transitions are claims B15 has not
    tested, and firing on an unmeasured brief would flag every draft twice."""
    measured = baseline_map(b)
    if not acceptance or not measured:
        return

    def discriminates(a):
        e = measured.get(entry_key(a))
        if effective_transition(a, e) != "flip":
            return False
        # a declared flip the baseline already meets moves nothing (B15 warns it)
        return str((e or {}).get("status") or "").strip().lower() != "pass"

    if any(discriminates(a) for a in acceptance):
        return
    # A declared preservation shape is the acknowledgment: `hold`, `before_after` and
    # `manual_checks` each record, in the file, that a no-op passes acceptance and a
    # human judges done-ness. Warning over that declaration would restate it.
    #
    # A behavior-preserving *word in the goal* is not one of them. It used to be, and
    # that made the escape reachable by the one field a compiler writes freely and
    # nobody confirms: "fix the off-by-one and rename the helper" linted clean and
    # verified clean on an untouched tree. A refactor states its evidence like every
    # other task — a before/after comparison, a held criterion, or the human check
    # that decides it.
    def compares(a):
        """A before/after comparison carries done-ness only if it compares something.
        `python -m unittest -q` on a passing suite prints nothing, so its digest is
        the digest of empty output: it reproduces on an untouched tree, on the work,
        and on any wrong work alike."""
        if not a.get("before_after"):
            return False
        evidence = str((measured.get(entry_key(a)) or {}).get("evidence") or "")
        empty = re.search(r"\b0 line\(s\) stdout", evidence)
        if empty:
            warn("B17 empty-comparison",
                 f"`{(entry_key(a) or ('', ''))[0][:50]}` is marked `before_after` but "
                 "printed nothing on HEAD — an output digest over no output reproduces "
                 "whatever the agent does",
                 "compare a command that prints the behaviour you are preserving, or "
                 "let a `hold` criterion or a manual check carry done-ness")
        return not empty

    # A manual check that merely exists is not a carrier: E1's T05 and T08 armed
    # with acceptance green on untouched HEAD because any non-empty manual_checks
    # silenced this rule — and the compiler writes those lines freely. Only the
    # `done:` spelling counts, and only a human can write it (`prompire draft`
    # rejects it in a proposal), so the declaration cannot be rubber-stamped in.
    holds = any(effective_transition(a, measured.get(entry_key(a))) == "hold"
                for a in acceptance)
    manual_done = any(carries for _, carries, _ in manual_check_entries(b))
    if not (holds or any(compares(a) for a in acceptance) or manual_done):
        has_manual = bool(as_list(b.get("manual_checks")))
        err("B17 vacuous-acceptance",
            "every criterion already passes on untouched HEAD, so `verify` says "
            "`clean` on a repo nobody touched"
            + (" — the manual checks are notes, not a completion condition"
               if has_manual else ""),
            "add a criterion that fails today and flips (`transition: flip`), a "
            "`before_after` comparison, or — if a human judgment really is what "
            "decides done — respell that one manual check `- done: <text>` "
            "yourself; that declaration is yours to write, not the compiler's")


def check(b):
    goal = str(b.get("goal") or "").strip()
    scope = as_list(b.get("scope"))
    forbidden = as_list(b.get("forbidden"))
    constraints = as_list(b.get("constraints"))
    acceptance = as_list(b.get("acceptance"))
    autonomy = str(b.get("autonomy") or "").strip().lower()
    gl = goal.lower()

    for k in b:
        if k not in TOP_KEYS:
            warn("B12 unknown-key", f"unknown key `{k}` — the renderer will drop it")

    check_goal(b, goal, gl)

    # B3 vague language (AIE ch.5: explain without ambiguity)
    for w in vague_hits(goal):
        err("B3 vague-goal", f"goal contains vague term \"{w}\"",
            "replace with the observable difference you want")
    for c in constraints:
        for w in vague_hits(str(c)):
            warn("B3 vague-constraint", f"constraint \"{str(c)[:60]}\" leans on \"{w}\"")

    # manual_checks entries are strings (notes) or `done: <text>` (the human's
    # completion-condition declaration, B17). Any other mapping is a guess about
    # authority this linter refuses to make.
    for text, _, well_formed in manual_check_entries(b):
        if not well_formed:
            err("B17 manual-check-shape",
                f"manual_checks entry `{text[:60]}` is neither a plain string nor "
                "`done: <text>`",
                "a review note is a plain string; the declaration that this judgment "
                "decides done is spelled `- done: <text>`")

    keys = check_acceptance(b, acceptance)
    good = acceptance_entries(b)
    cmds = [k[0] for k in keys if k]
    check_baseline(b, good, keys)
    check_discrimination(b, good)
    check_scope_fields(b, scope, forbidden)
    check_tests_policy(b, good)

    # B8 autonomy is declared and matched by a rollback (BAA autonomy slider)
    if autonomy not in AUTONOMY:
        err("B8 autonomy-undeclared",
            f"`autonomy` is {autonomy or 'missing'} — must be manual | ask | auto",
            "manual = agent proposes only; ask = confirms each risky step; auto = runs alone")
    if autonomy == "auto":
        if not str(b.get("rollback") or "").strip():
            err("B8 auto-without-rollback", "autonomy: auto with no `rollback`",
                "name the branch or worktree that makes this undoable")
        if not cmds:
            err("B8 auto-without-check", "autonomy: auto with no executable acceptance")

    # B8 also owns the other execution-mode field: a non-boolean `plan_first` is a
    # YAML accident ("false" is a truthy string), and the renderer must never turn
    # an accident into a hard approval stop
    if b.get("plan_first") is not None and not isinstance(b.get("plan_first"), bool):
        err("B8 plan-first-not-bool",
            f"`plan_first: {b.get('plan_first')}` is not a boolean — a quoted "
            "string here is truthy by accident, and rendering it would stop the "
            "agent for plan approval nobody chose",
            "write `plan_first: true`, or delete the line")

    # B9 destructive verbs need a human in the loop (AIE ch.6; BAA least privilege)
    haystack = " ".join([gl, text_of(constraints), text_of(b.get("notes")), " ".join(cmds).lower()])
    hit = DESTRUCTIVE_RX.search(haystack)
    if hit and autonomy not in {"manual", "ask"}:
        err("B9 destructive-unguarded",
            f"brief involves `{hit.group(0)}` at autonomy `{autonomy or 'undeclared'}`",
            "set autonomy: ask, or move the operation out of the brief")

    # B10 decouple planning from execution when the task is big (AIE ch.6).
    # `autonomy: manual` already decouples them completely — the run produces a plan
    # and never writes — so demanding a mid-run approval stop there is incoherent.
    big = BIG_RX.search(goal)
    if (big or len(scope) > 3) and not b.get("plan_first") and autonomy != "manual":
        err("B10 no-plan-gate",
            "wide task ({}) without `plan_first: true`".format(
                f"goal says '{big.group(0)}'" if big else f"{len(scope)} scope entries"),
            "make the agent produce a plan and stop; a 1000-step plan burns hours before "
            "you notice it is going nowhere")

    # B14 behavior-preserving work needs a before/after comparison (AM: error amplification)
    if PRESERVE_RX.search(goal) and not any(a.get("before_after") for a in good) and \
            not any(any(k in c.lower() for k in COMPARE) for c in cmds):
        warn("B14 no-behavior-check",
             "goal preserves behavior but nothing compares before/after",
             "mark the comparing criterion `before_after: true` — baseline.py records its "
             "output digest on HEAD and the same command must reproduce it")

    # B11 constraints that fight each other or repeat
    seen = {}
    for c in constraints:
        k = re.sub(r"[^a-z0-9á-ž ]", "", str(c).lower()).strip()
        if k in seen:
            warn("B11 duplicate-constraint", f"constraint repeated: \"{str(c)[:60]}\"")
        seen[k] = True
    ct = text_of(constraints)
    if re.search(r"no new (dependenc|packag|librar)|žádné nové (závislost|balíč)", ct) and \
            re.search(r"\b(add|install|use|přidej|nainstaluj)\b.{0,25}"
                      r"(dependenc|package|librar|balíč|závislost)", gl + " " + ct):
        err("B11 contradiction", "brief both forbids and requires a new dependency")
    if re.search(r"(do not|don'?t|no).{0,20}(change|break|modify).{0,20}(public )?api|"
                 r"neměň.{0,20}api", ct) and re.search(r"\brename\b|přejmenuj", gl):
        err("B11 contradiction", "goal renames while constraints freeze the public API",
            "say which names are internal, or drop the constraint")

    # `dirty_baseline` is what check_scope.py forgives; it is not a place to park work
    for p in as_list(b.get("dirty_baseline")):
        if bad_path(p):
            err("B6 dirty-baseline-path", f"dirty_baseline entry `{p}` is {bad_path(p)}")
    rev = str(b.get("base_rev") or "").strip()
    if not rev:
        err("B16 missing-base-rev",
            "no `base_rev` — so this brief names no commit its work started from, and "
            "the only base left to diff against is HEAD, which an agent that commits its "
            "own work moves along with it: the diff comes back empty and an empty diff "
            "reads as every change being inside scope. check_scope.py refuses to produce "
            "a verdict at all rather than default there (exit 2); this rule moves that "
            "failure here, where one command fixes it",
            "run baseline.py --write before work starts; it always stamps base_rev at "
            "the commit it measured from")
    elif not re.fullmatch(r"[0-9a-fA-F]{7,40}", rev):
        err("B16 moving-base-rev",
            f"`base_rev: {rev[:30]}` is not a fixed commit — a branch name or `HEAD` "
            "names wherever the ref happens to point when check_scope.py runs, not "
            "where the work started, so it is exactly as defeatable as leaving "
            "`base_rev` unset",
            "use the SHA baseline.py wrote (`git rev-parse HEAD` before work started), "
            "not a branch name or a symbolic ref")
    if autonomy == "manual" and str(b.get("rollback") or "").strip():
        warn("B8 rollback-unused", "autonomy: manual never writes, so `rollback` is unused")


def main():
    # Findings quote the brief back — an unknown key, a vague phrase — and the messages
    # themselves are written with em dashes, so this tool cannot print at all under a
    # cp1252 stdout. Before the first `print`, because that is the one it would die on.
    utf8_stdio()
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    path = sys.argv[1]
    try:
        brief = load_brief(path)
    except BriefError as e:
        print(str(e))
        return 2

    # B18 — the marker is a decision not yet made. Read from the raw bytes, because
    # it lives in comments the YAML parse above already dropped.
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raw = ""
    markers = raw.count(f"# {DRAFT_MARKER}")
    if markers:
        err("B18 unconfirmed-draft",
            f"{markers} `# {DRAFT_MARKER}` line(s) remain — this is a draft, "
            "not a brief",
            "read each marked line, fix it, delete the marker; `prepare` refuses "
            "while one remains")
    listed = [str(item) for item in as_list(brief.get(DRAFT_LEDGER))] \
        if DRAFT_LEDGER in brief else []
    if DRAFT_LEDGER in brief:
        err("B18 unconfirmed-draft",
            f"the `{DRAFT_LEDGER}:` block still lists "
            + (", ".join(listed) or "decisions the compiler made"),
            "this block is the confirmation record that survives a YAML round-trip, "
            "which the comment markers do not; read each decision, then delete the "
            "block")

    check(brief)
    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warn"]

    if "--json" in sys.argv:
        print(json.dumps({"errors": len(errors), "warnings": len(warns),
                          "findings": findings}, ensure_ascii=False, indent=2))
    else:
        for f in errors + warns:
            mark = "ERROR" if f["severity"] == "error" else " WARN"
            print(f"{mark}  [{f['rule']}] {f['message']}")
            if f["fix"]:
                print(f"        → {f['fix']}")
        print(f"\n{len(errors)} error(s), {len(warns)} warning(s) — {path}")
        if not errors:
            print("brief is shippable" + (" (warnings are judgment calls)" if warns else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
