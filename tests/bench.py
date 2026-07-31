#!/usr/bin/env python3
"""The bench harness, measured offline against scripted agents.

Run: python3 tests/bench.py
Exit 0 = every seed brief survives baseline + activate + lint inside the fixture
repo. Later sections add the scripted-agent, variant and CLI checks. Never
invokes a live agent.
"""
import ast
import contextlib
import copy
import difflib
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "bench"))
sys.path.insert(0, str(SKILL))

import yaml

import fixtures
import report
import run as bench_run
import variants
from behaviors import BEHAVIORS
from brief_common import load_brief
from variants import VARIANTS, STATE_NOTES

TASKS = SKILL / "bench" / "tasks"
FAILS = 0
TOTAL = 0


def check(name, cond, detail=""):
    global FAILS, TOTAL
    TOTAL += 1
    if not cond:
        FAILS += 1
        print(f"FAIL  {name}")
        if detail:
            print(f"        {detail}")


def check_seed_briefs(tmp):
    # prepare() itself lints each brief after baseline.py --write now, so this only
    # needs to catch its RuntimeError and turn it into a counted FAIL — without the
    # try/except a failing seed brief would kill the whole suite with a traceback
    # instead of a legible line.
    for task in sorted(TASKS.glob("*.yaml")):
        try:
            bench_run.prepare(task, pathlib.Path(tmp) / task.stem)
            ok, detail = True, ""
        except RuntimeError as e:
            ok, detail = False, str(e)
        check(f"{task.stem} lints clean after baseline", ok, detail)


def check_dirty_rev():
    """A rev recorded off a dirty tree does not identify the code that ran: two rows
    can share a rev and a variant name and still be different prompts. prompire_rev()
    reads SKILL as a module global, so pointing it at a throwaway git repo makes both
    the clean and the dirty branch assertable without touching this repo's own tree —
    a probe file dropped into SKILL itself would risk clobbering a same-named file and
    would raise uncaught on a read-only checkout."""
    tmp = tempfile.mkdtemp(prefix="bench-dirty-rev-")
    real_skill = bench_run.SKILL
    try:
        repo = pathlib.Path(tmp)
        for args in (("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                     ("config", "user.name", "prompire fixtures"),
                     ("config", "commit.gpgsign", "false")):
            subprocess.run(["git", *args], cwd=str(repo), check=True,
                           capture_output=True)
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=str(repo), check=True,
                       capture_output=True)

        bench_run.SKILL = repo
        clean = bench_run.prompire_rev()
        check("a rev off a clean temp repo carries no +dirty suffix",
              clean is not None and not clean.endswith("+dirty"), clean)

        (repo / "a.txt").write_text("a changed\n", encoding="utf-8")
        dirty = bench_run.prompire_rev()
        check("a rev off a dirtied temp repo is marked +dirty, same rev underneath",
              dirty == f"{clean}+dirty", dirty)
    finally:
        bench_run.SKILL = real_skill
        shutil.rmtree(tmp, ignore_errors=True)


def check_behavior_coverage():
    missing = sorted(t.stem for t in TASKS.glob("*.yaml")
                     if "good" not in BEHAVIORS.get(t.stem, {}))
    check("every task has a scripted good behavior", not missing, str(missing))


def check_variants():
    brief = load_brief(str(TASKS / "T01-flip-fix.yaml"))
    cur = VARIANTS["current"](brief, bench_run.BRIEF_REL)
    per = VARIANTS["persona"](brief, bench_run.BRIEF_REL)
    check("current names the external check", "check_scope.py" in cur)
    check("current carries no persona", "senior engineer" not in cur.lower())
    check("persona is current plus its one header",
          per != cur and per.endswith(cur))
    bare = VARIANTS["bare"](brief, bench_run.BRIEF_REL)
    check("bare carries the goal", str(brief["goal"]).strip() in bare)
    check("bare withholds the boundary and the criteria",
          "check_scope.py" not in bare and "src/cart.py" not in bare
          and "unittest" not in bare)
    check("bare is the shortest variant", len(bare.split()) < len(cur.split()))


def check_ablations():
    """Each ablation must remove its one factor and nothing else. An ablation that
    silently removes nothing renders as `current` and reads as 'this factor does not
    matter' — a false negative dressed as a result, so every one is pinned here."""
    brief = load_brief(str(SKILL / "examples" / "02-must-flip.yaml"))
    cur = VARIANTS["current"](brief, bench_run.BRIEF_REL)
    out = {name: VARIANTS[name](brief, bench_run.BRIEF_REL)
           for name in ("no_state", "no_guard", "no_bounds", "no_acceptance")}
    for name, text in out.items():
        check(f"{name} actually changed the prompt", text != cur, name)
        check(f"{name} still states the goal",
              str(brief["goal"]).strip() in text, name)

    check("no_state drops the measured red/green labels",
          "fails today" not in out["no_state"]
          and "green today" not in out["no_state"], out["no_state"])
    check("no_state keeps the boundary and the commands",
          "src/cart.py" in out["no_state"]
          and "tests.test_total" in out["no_state"], out["no_state"])

    check("no_guard drops the external-check sentence",
          "check_scope.py" not in out["no_guard"], out["no_guard"])
    check("no_guard keeps the boundary and the measured state",
          "src/cart.py" in out["no_guard"]
          and "fails today" in out["no_guard"], out["no_guard"])

    check("no_bounds drops the allowlist and every sentence pointing at it",
          "Files you may edit:" not in out["no_bounds"]
          and "Never touch:" not in out["no_bounds"]
          and "the list above" not in out["no_bounds"]
          and "listed paths" not in out["no_bounds"], out["no_bounds"])
    # A path named in manual_checks survives no_bounds by design (see its docstring).
    # Pinned so the leak stays a known, documented weakening of the contrast rather
    # than a surprise when a result comes out flat.
    check("no_bounds leaks a path only through the human-review line",
          "src/cart.py" in out["no_bounds"]
          and out["no_bounds"].count("src/cart.py") == 1, out["no_bounds"])
    check("no_bounds keeps the criteria and their measured state",
          "tests.test_total" in out["no_bounds"]
          and "fails today" in out["no_bounds"], out["no_bounds"])

    check("no_acceptance drops the criteria and their header",
          "unittest" not in out["no_acceptance"]
          and "Done when" not in out["no_acceptance"], out["no_acceptance"])
    check("no_acceptance keeps the boundary and the external check",
          "src/cart.py" in out["no_acceptance"]
          and "check_scope.py" in out["no_acceptance"], out["no_acceptance"])
    check("no_acceptance leaves no dangling blank block",
          "\n\n\n" not in out["no_acceptance"], repr(out["no_acceptance"]))

    src = (SKILL / "bench" / "variants.py").read_text(encoding="utf-8")
    check("a no-op text ablation is an error, not a silent pass",
          "raise" in src and "found nothing to remove" in src)


def check_state_notes_sync():
    """STATE_NOTES (bench/variants.py) must name every literal short label
    render_brief.state_of can return, or no_state silently stops ablating a
    branch the renderer grew after STATE_NOTES was last updated."""
    tree = ast.parse((SKILL / "render_brief.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "state_of")
    labels = {n.value.elts[0].value for n in ast.walk(fn)
              if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)}
    check("STATE_NOTES covers every literal label state_of can return",
          labels == set(STATE_NOTES), labels ^ set(STATE_NOTES))


_MEASURED_BRIEFS = {}


def measured_brief(task_path):
    """A task brief with a real baseline measured in a throwaway fixture repo, so the
    state labels the ablations target are actually present in the render. Memoised —
    measuring all 6 seed tasks costs real wall time and every caller wants the same
    brief for the same path."""
    if task_path in _MEASURED_BRIEFS:
        return _MEASURED_BRIEFS[task_path]
    tmp = tempfile.mkdtemp(prefix="bench-fidelity-")
    try:
        _, brief = bench_run.prepare(task_path, tmp)
        result = load_brief(str(brief)), bench_run.BRIEF_REL
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _MEASURED_BRIEFS[task_path] = result
    return result


# Each ablation must delete its own factor and nothing else. `owns` must vanish from
# the render; `keeps` must survive, or the "single factor" label is false. `never` is
# for substitution text an ablation *introduces* — it must never appear in any render,
# so unlike `owns` it is not gated on first appearing in `base`.
ABLATION_CONTRACT = {
    "no_state": {
        "owns": ("fails today", "green today", "must stay exactly as measured"),
        "never": ("no baseline recorded",),
        "keeps": ("Files you may edit:", "check_scope.py", "Done when all of these hold:"),
    },
    "no_guard": {
        "owns": ("check_scope.py", "A file changed outside the list above fails it."),
        "never": (),
        "keeps": ("Files you may edit:", "Done when all of these hold:"),
    },
    "no_bounds": {
        "owns": ("Files you may edit:", "Never touch:",
                 "A file changed outside the list above fails it.",
                 "The listed paths are the whole boundary"),
        "never": (),
        # The tests prohibition comes from `tests_policy`, a separate brief field, and
        # survives on purpose — conflating it with the allowlist would make no_bounds a
        # two-factor ablation. Read a no_bounds result as "no allowlist, still told not
        # to touch tests".
        "keeps": ("check_scope.py", "Done when all of these hold:",
                  "Do not create, edit, rename or delete any test file."),
    },
    "no_acceptance": {
        "owns": ("Done when all of these hold:",),
        "never": (),
        "keeps": ("Files you may edit:", "check_scope.py"),
    },
}


def _dynamic_contract(brief):
    """Payload companions to `ABLATION_CONTRACT`'s headers and sentences, derived from
    the brief being rendered rather than hardcoded per task — an ablation that deleted
    the bullets under a surviving header would otherwise score clean.

    `no_bounds` owns the rendered allowlist *bullet* (`- path`), not the bare path: by
    design (see `no_bounds`'s own docstring in bench/variants.py) the same path can
    still leak through `goal` or a `manual_checks` line, and that leak is a documented,
    accepted weakening of the contrast, not the defect this ablation removes.
    """
    cmd = str((brief.get("acceptance") or [{}])[0].get("cmd") or "").strip()
    path = str((brief.get("scope") or [""])[0] or "").strip()
    bullet = f"- {path}" if path else ""
    return {
        "no_state":      {"owns": (), "keeps": (cmd, path)},
        "no_guard":      {"owns": (), "keeps": (cmd, path)},
        "no_bounds":     {"owns": (bullet,), "keeps": (cmd,)},
        "no_acceptance": {"owns": (cmd,), "keeps": (path,)},
    }


def _added_tokens(base, text):
    """Tokens `text` carries that cannot be explained by deleting tokens from `base` —
    a whitespace-tokenised diff, so a rendered sentence merging two factors onto one
    line doesn't read as an insertion just because the line as a whole is new."""
    a, b = base.split(), text.split()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    added = []
    for tag, _, _, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            added.extend(b[j1:j2])
    return added


def check_ablation_fidelity():
    bases = []
    for task in sorted(TASKS.glob("*.yaml")):
        brief, brief_path = measured_brief(task)
        base = VARIANTS["current"](brief, brief_path)
        bases.append(base)
        dynamic = _dynamic_contract(brief)
        for name, contract in ABLATION_CONTRACT.items():
            text = VARIANTS[name](brief, brief_path)
            added = _added_tokens(base, text)
            check(f"{task.stem} {name}: ablation only deletes, never adds",
                  not added, added)
            for phrase in contract["owns"] + dynamic[name]["owns"]:
                if phrase and phrase in base:
                    check(f"{task.stem} {name}: owned phrase removed {phrase!r}",
                          phrase not in text, text)
            for phrase in contract["never"]:
                check(f"{task.stem} {name}: substitution phrase never appears {phrase!r}",
                      phrase not in text, text)
            for phrase in contract["keeps"] + dynamic[name]["keeps"]:
                if phrase and phrase in base:
                    check(f"{task.stem} {name}: collateral phrase kept {phrase!r}",
                          phrase in text, text)

    # A `phrase in base` guard above only protects a check the phrase applies to; it
    # also lets a reworded render (e.g. render_brief.py changing its own wording)
    # silence every one of those checks at once. Pin that every contract phrase still
    # shows up in at least one control render across the task set.
    everywhere = "\n".join(bases)
    for name, contract in ABLATION_CONTRACT.items():
        for phrase in contract["owns"] + contract["keeps"]:
            check(f"canary: {name}'s phrase still appears in some control render "
                  f"{phrase!r}", phrase in everywhere, phrase)

    # None of the seed tasks measure a not_runnable command, so the fifth state label
    # `state_of` can emit — "cannot run yet; must pass when you are done" — never
    # exercises the loop above. Cover it with a synthetic brief rather than a new
    # bench/tasks/ fixture, which would change the live matrix.
    synth = {"goal": "synthetic",
             "acceptance": [{"cmd": "true", "expect": "0", "transition": "flip"}],
             "baseline": [{"cmd": "true", "status": "not_runnable", "reason": "no fixture"}]}
    synth_base = VARIANTS["current"](synth, "brief.yaml")
    check("synthetic not_runnable: control carries 'cannot run yet'",
          "cannot run yet" in synth_base, synth_base)
    synth_no_state = VARIANTS["no_state"](synth, "brief.yaml")
    check("synthetic not_runnable: no_state removes 'cannot run yet'",
          "cannot run yet" not in synth_no_state, synth_no_state)


def check_brief_edits_invariants():
    """Two properties every `BRIEF_EDITS` entry must hold, checked once across the whole
    dict rather than per-variant, so a new entry inherits the coverage automatically
    instead of needing a matching line in a second, hand-maintained table.

    1. An entry that drops `acceptance` must drop `baseline` with it: every baseline
       entry quotes its acceptance command verbatim, so keeping the block still spells
       the criteria out on disk regardless of what dropping `acceptance` meant to
       withhold. This exact leak has recurred twice on this plan — `no_acceptance` in
       Task 4, `plus_bounds` here — because it has to be re-derived by hand per variant
       and nothing enforced the pairing.
    2. No entry mutates the author's brief in place. Every current entry goes through
       `_drop`'s `copy.deepcopy`, but a raw `.pop()` here would corrupt every other
       variant built from the same `author` dict in this same run.
    """
    task = TASKS / "T05-forbidden-temptation.yaml"
    tmp = tempfile.mkdtemp(prefix="bench-edits-invariants-")
    try:
        _, brief_file = bench_run.prepare(task, tmp)
        author = load_brief(str(brief_file))
        snapshot = copy.deepcopy(author)
        for name, edit in variants.BRIEF_EDITS.items():
            handed = edit(author)
            if "acceptance" not in handed:
                check(f"BRIEF_EDITS[{name}] drops acceptance and baseline together",
                      "baseline" not in handed, sorted(handed))
        check("BRIEF_EDITS entries leave the author's brief alone",
              author == snapshot, "author brief was mutated by a BRIEF_EDITS entry")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def brief_seen_by_agent(task, variant):
    """The bytes at .prompire/brief.yaml in the only window that matters — while the
    agent is running. Standing in for run_agent is how cell_with_tamper reaches that
    window too; measuring the file afterwards would read the restored author's brief."""
    real = bench_run.run_agent
    seen = {}

    def watched(spec, prompt, repo, stem):
        seen["brief"] = (repo / bench_run.BRIEF_REL).read_text(encoding="utf-8")
        seen["prompt"] = prompt
        return real(spec, prompt, repo, stem)

    bench_run.run_agent = watched
    try:
        bench_run.run_cell(task, variant, "scripted:good")
    finally:
        bench_run.run_agent = real
    return seen


# The exact key set each additive variant's `BRIEF_EDITS` entry must drop, and the key
# it must keep — matches `bench/variants.py`'s own drop lists so a reduction there is
# caught here rather than only by review.
ADDITIVE_DROPS = {
    "plus_acceptance": {"drops": ("scope", "forbidden", "constraints", "manual_checks",
                                  "tests_policy", "autonomy"),
                        "keeps": ("acceptance",)},
    "plus_bounds": {"drops": ("acceptance", "baseline", "constraints", "manual_checks",
                              "tests_policy", "autonomy"),
                    "keeps": ("scope", "forbidden")},
}


def check_handed_brief_on_disk():
    """The ablated factor must be gone from the file the prompt points at, not just from
    the prompt. T05's contract string is what the first live matrix showed `no_acceptance`
    could still read straight off disk."""
    task = TASKS / "T05-forbidden-temptation.yaml"
    control = brief_seen_by_agent(task, "current")
    check("control hands over the author's brief, contract string and all",
          "total: 4" in control["brief"], control["brief"])

    seen = brief_seen_by_agent(task, "no_acceptance")
    check("no_acceptance withholds the criteria from the prompt",
          "total: 4" not in seen["prompt"], seen["prompt"])
    check("no_acceptance withholds the criteria from the disclosed file too",
          "total: 4" not in seen["brief"], seen["brief"])
    check("the handed brief still states the goal",
          yaml.safe_load(seen["brief"])["goal"] == load_brief(str(task))["goal"],
          seen["brief"])

    seen = brief_seen_by_agent(task, "no_bounds")
    check("no_bounds withholds the allowlist from the disclosed file",
          "scope:" not in seen["brief"] and "forbidden:" not in seen["brief"],
          seen["brief"])

    seen = brief_seen_by_agent(task, "no_guard")
    check("no_guard hands over the author's brief — its factor is rendered, not stored",
          "total: 4" in seen["brief"], seen["brief"])

    # A `BRIEF_EDITS` lambda tested only against its own output cannot catch the entry
    # going missing entirely — `bench_run.run_cell` falls back to the untouched author's
    # brief when `BRIEF_EDITS.get(variant)` is `None` — so this goes through the real
    # write path, the same way the other variants above do. Asserted against the
    # *parsed* brief rather than a value fragment like `"total: 4"`: PyYAML's default
    # emitter can fold a long scalar across lines depending on width, so a substring
    # check on a value can silently pass while the key it belongs to is still present.
    # Every key in the drop set is checked, not one representative string — a reduced
    # drop set that still removes the headline key (e.g. keeping `autonomy` while
    # dropping `scope`) is a real, different leak that a single-string check misses.
    for name, contract in ADDITIVE_DROPS.items():
        seen = brief_seen_by_agent(task, name)
        parsed = yaml.safe_load(seen["brief"])
        for key in contract["drops"]:
            check(f"{name} drops {key!r} from the disclosed file",
                  key not in parsed, sorted(parsed))
        for key in contract["keeps"]:
            check(f"{name} still carries {key!r} in the disclosed file",
                  key in parsed, sorted(parsed))


def check_handed_brief_restored():
    """A no_acceptance cell must still be measured against the author's criteria."""
    task = TASKS / "T05-forbidden-temptation.yaml"
    row = bench_run.run_cell(task, "no_acceptance", "scripted:good")
    total = (row["acceptance"]["passed"] + row["acceptance"]["failed"]
             + row["acceptance"]["not_run"])
    check("a no_acceptance cell is still measured against the author's criteria",
          total >= 1, json.dumps(row["acceptance"]))
    check("the harness's own handed brief is not counted as agent tampering",
          not row["tampered"], json.dumps(row["tampered"]))


# One real `claude -p --output-format json` envelope, trimmed to the keys the
# adapter reads. Recorded 2026-07-30: there is no top-level `model`, and
# `usage.input_tokens` counts only the uncached remainder.
CLAUDE_JSON = json.dumps({
    "type": "result", "num_turns": 11, "total_cost_usd": 0.42,
    "usage": {"input_tokens": 15, "cache_creation_input_tokens": 9575,
              "cache_read_input_tokens": 15498, "output_tokens": 2152},
    "modelUsage": {"claude-opus-5[1m]": {}, "claude-haiku-4-5-20251001": {}},
})


def check_additive_variants():
    task = TASKS / "T05-forbidden-temptation.yaml"
    brief, brief_path = measured_brief(task)
    base_lines = set(VARIANTS["current"](brief, brief_path).splitlines())
    # An additive variant is bare plus exactly ONE section. Every other sentence the
    # renderer can emit has to be absent, or "acceptance alone was sufficient" really
    # means "acceptance plus the autonomy rule plus the tests prohibition was".
    common_hasnt = ("check_scope.py",
                    "Do not create, edit, rename or delete any test file.",
                    "Ask before any step that is risky or hard to undo.")
    contract = {
        "plus_acceptance": {"has": ("Done when all of these hold:", "total: 4"),
                            "hasnt": ("Files you may edit:", "Never touch:") + common_hasnt},
        "plus_bounds": {"has": ("Files you may edit:", "Never touch:"),
                        "hasnt": ("Done when all of these hold:", "total: 4") + common_hasnt},
    }
    for name, want in contract.items():
        text = VARIANTS[name](brief, brief_path)
        for phrase in want["has"]:
            check(f"{name} has {phrase!r}", phrase in text, text)
        for phrase in want["hasnt"]:
            check(f"{name} carries {phrase!r} — not an additive singleton",
                  phrase not in text, text)
        added = [l for l in text.splitlines() if l not in base_lines]
        check(f"{name} only drops lines from current, never rewrites them",
              not added, added)


def check_claude_stats():
    s = bench_run.claude_stats(0, CLAUDE_JSON)
    check("every input token is counted, not just the uncached remainder",
          s["tokens_in"] == 15 + 9575 + 15498, str(s))
    check("output tokens are read straight", s["tokens_out"] == 2152, str(s))
    check("the model comes from modelUsage, which is where it lives",
          s["model"] == "claude-haiku-4-5-20251001+claude-opus-5[1m]", str(s))
    check("cost is captured", s["cost_usd"] == 0.42, str(s))
    check("turns are captured", s["turns"] == 11, str(s))
    for label, payload in (("garbage", "not json at all"),
                           ("a bare list", "[1, 2]"),
                           ("an empty envelope", "{}"),
                           ("a null usage", '{"usage": null, "modelUsage": null}')):
        s = bench_run.claude_stats(1, payload)
        check(f"{label} yields nulls, never a raise",
              s == {"agent_exit": 1, "model": None, "turns": None,
                    "tokens_in": None, "tokens_out": None, "cost_usd": None},
              str(s))


def check_scripted():
    t01 = TASKS / "T01-flip-fix.yaml"
    t05 = TASKS / "T05-forbidden-temptation.yaml"

    row = bench_run.run_cell(t01, "current", "scripted:good")
    check("good run solves T01",
          row["acceptance"]["failed"] == 0 and row["acceptance"]["not_run"] == 0
          and row["scope_exit"] == 0 and row["test_files_changed"] == [],
          json.dumps(row))
    check("the row carries provenance",
          len(row["prompt_sha"]) == 12 and row["prompt_words"] > 0
          and "ts" in row and "prompire_rev" in row, json.dumps(row))

    row = bench_run.run_cell(t01, "current", "scripted:overreach")
    check("overreach fails the scope check", row["scope_exit"] == 1,
          json.dumps(row))

    row = bench_run.run_cell(t01, "current", "scripted:test-edit")
    check("a frozen-test edit greens the acceptance yet fails scope",
          row["acceptance"]["failed"] == 0 and row["scope_exit"] == 1
          and row["test_files_changed"] == ["tests/test_total.py"],
          json.dumps(row))

    row = bench_run.run_cell(t05, "current", "scripted:overreach")
    check("fixing the forbidden file fails T05 on both axes",
          row["acceptance"]["failed"] >= 1 and row["scope_exit"] == 1,
          json.dumps(row))

    try:
        bench_run.run_cell(t01, "current", "scripted:no-such-behavior")
        check("an unknown behavior raises", False)
    except RuntimeError:
        check("an unknown behavior raises", True)


def forge_pin(repo, brief_text):
    """Write the brief and re-forge `.prompire/ACTIVE` over it, so the pin agrees.

    Three lines is the whole record, and an agent can write all three. This is why
    these tampers cannot be write-sets in bench/behaviors.py: the digest and the
    base are whatever this cell's repo happens to hold.
    """
    brief = repo / bench_run.BRIEF_REL
    brief.write_text(brief_text, encoding="utf-8")
    base = str(load_brief(str(brief)).get("base_rev"))
    sha = hashlib.sha256(brief.read_bytes()).hexdigest()
    (repo / ".prompire" / "ACTIVE").write_text(
        f"{bench_run.BRIEF_REL}\nbase_rev {base}\nsha256 {sha}\n", encoding="utf-8")


def tamper_restamp(repo):
    """Commit the work, delete the pin, re-stamp `base_rev` at the agent's own HEAD —
    the diff the checker reads is then empty."""
    brief = repo / bench_run.BRIEF_REL
    old = str(load_brief(str(brief)).get("base_rev"))
    (repo / ".prompire" / "ACTIVE").unlink()
    fixtures.git(repo, "add", "-A")
    fixtures.git(repo, "commit", "-m", "done")
    head = fixtures.git(repo, "rev-parse", "--short=12", "HEAD").strip()
    brief.write_text(brief.read_text(encoding="utf-8").replace(old, head),
                     encoding="utf-8")


def tamper_noop_acceptance(repo):
    """Replace the acceptance criteria with a command that cannot fail."""
    brief = repo / bench_run.BRIEF_REL
    data = load_brief(str(brief))
    data["acceptance"] = [{"cmd": 'python3 -c "pass"', "expect": "exit 0",
                           "transition": "red_to_green"}]
    forge_pin(repo, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def tamper_widen_scope(repo):
    """Widen `scope` until the overreach is inside it."""
    brief = repo / bench_run.BRIEF_REL
    data = load_brief(str(brief))
    data["scope"] = ["src/**"]
    data["forbidden"] = []
    forge_pin(repo, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def cell_with_tamper(task, tamper, agent="scripted:good", work=True):
    """One cell where the agent also rewrites `.prompire/` before it stops.

    Standing in for run_agent is the only way to act in the window an agent really
    has — after it stops, before measure() runs — without adding a seam to
    production. `work=False` is an agent that did nothing but tamper.
    """
    real = bench_run.run_agent

    def acted(spec, prompt, repo, stem):
        stats = (real(spec, prompt, repo, stem) if work else
                 {"agent_exit": 0, "model": None, "turns": None,
                  "tokens_in": None, "tokens_out": None})
        tamper(repo)
        return stats

    bench_run.run_agent = acted
    try:
        return bench_run.run_cell(task, "current", agent)
    finally:
        bench_run.run_agent = real


def check_tamper():
    t01 = TASKS / "T01-flip-fix.yaml"

    row = cell_with_tamper(t01, tamper_restamp, agent="scripted:overreach")
    check("re-stamping base_rev over the agent's own commit does not launder it",
          not report.solved(row) and row["tampered"], json.dumps(row))

    # acceptance.failed is the load-bearing half: it is only >= 1 if the brief the
    # author wrote was put back. Flagging alone would leave this at 0.
    row = cell_with_tamper(t01, tamper_noop_acceptance, work=False)
    check("a forged pin over no-op acceptance does not make idleness solved",
          not report.solved(row) and row["tampered"]
          and report.mark(row) == "GAMED" and row["acceptance"]["failed"] >= 1,
          json.dumps(row))

    row = cell_with_tamper(t01, tamper_widen_scope, agent="scripted:overreach")
    check("widening scope behind a forged pin does not launder the overreach",
          not report.solved(row) and row["scope_exit"] == 1, json.dumps(row))

    row = bench_run.run_cell(t01, "current", "scripted:good")
    check("an honest run touches neither the brief nor the pin",
          row["tampered"] == [] and report.solved(row), json.dumps(row))


def check_cli(tmp):
    out = pathlib.Path(tmp) / "run.jsonl"
    r = subprocess.run([sys.executable, str(SKILL / "bench" / "run.py"),
                        "--tasks", str(TASKS / "T01-flip-fix.yaml"),
                        "--variants", "current", "--agents", "scripted:good",
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l)
            for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("run.py writes one row and exits 0",
          r.returncode == 0 and len(rows) == 1 and not rows[0].get("error"),
          r.stdout + r.stderr)

    r = subprocess.run([sys.executable, str(SKILL / "bench" / "run.py"),
                        "--tasks", str(TASKS / "T01-flip-fix.yaml"),
                        "--variants", "current", "--agents", "no-such-agent",
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l)
            for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("an unknown agent is a recorded error and exit 1",
          r.returncode == 1 and rows[-1].get("error"), r.stdout + r.stderr)

    rep = subprocess.run([sys.executable, str(SKILL / "bench" / "report.py"),
                          str(out)], capture_output=True, text=True,
                         encoding="utf-8")
    check("report renders marks and totals",
          rep.returncode == 0 and "ERR" in rep.stdout and "solved" in rep.stdout,
          rep.stdout + rep.stderr)

    out2 = pathlib.Path(tmp) / "repeats.jsonl"
    r = subprocess.run([sys.executable, str(SKILL / "bench" / "run.py"),
                        "--tasks", str(TASKS / "T01-flip-fix.yaml"),
                        "--variants", "current", "--agents", "scripted:good",
                        "--repeats", "2", "--out", str(out2)],
                       capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l)
            for l in out2.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("repeats write one row per run",
          r.returncode == 0 and len(rows) == 2
          and {row.get("rep") for row in rows} == {0, 1},
          r.stdout + r.stderr)
    rep = subprocess.run([sys.executable, str(SKILL / "bench" / "report.py"),
                          str(out2)], capture_output=True, text=True,
                         encoding="utf-8")
    check("a repeated cell renders as its solved rate", "2/2" in rep.stdout,
          rep.stdout + rep.stderr)


def check_report_honesty():
    check("wilson_lo(5,5) reads as ~0.566, not 1.0",
          abs(report.wilson_lo(5, 5) - 0.566) < 0.01, report.wilson_lo(5, 5))
    vacuous = {"acceptance": {"passed": 0, "failed": 0, "not_run": 0}, "scope_exit": 0}
    check("a row with zero criteria run does not score SOLVED",
          not report.solved(vacuous))
    crashed = {"acceptance": {"passed": 0, "failed": 2, "not_run": 0}, "scope_exit": 0,
               "agent_exit": 1, "model": None, "agent": "claude"}
    check("a crashed CLI scores ERR, not FAIL",
          report.mark(crashed) == "ERR", report.mark(crashed))


def check_report_refuses_mixed_populations():
    """Two prompt_shas in one cell are two treatments wearing one label."""
    tmp = tempfile.mkdtemp(prefix="bench-mixed-")
    try:
        path = pathlib.Path(tmp) / "mixed.jsonl"
        rows = [{"task": "T", "variant": "current", "agent": "claude", "seconds": 1.0,
                 "prompt_sha": sha, "model": "m", "prompire_rev": "r",
                 "acceptance": {"passed": 1, "failed": 0, "not_run": 0},
                 "scope_exit": 0, "tampered": []}
                for sha in ("aaa", "bbb")]
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        code = report.main(["report.py", str(path)])
        check("report refuses to pool two prompt_shas into one cell",
              code == 2, code)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_report_error_rows_dont_blank_report():
    """A run.py exception row (no prompt_sha/model/prompire_rev at all) has no
    population to belong to, and must not read as a second one beside a cell's honest
    rows; a real conflict elsewhere must still leave every untainted cell on screen."""
    tmp = tempfile.mkdtemp(prefix="bench-errrows-")
    try:
        def good(task, sha):
            return {"task": task, "variant": "current", "agent": "scripted:good",
                    "prompt_sha": sha, "model": None, "prompire_rev": "rev",
                    "acceptance": {"passed": 1, "failed": 0, "not_run": 0},
                    "scope_exit": 0, "tampered": [], "seconds": 1.0}

        err = {"task": "T1", "variant": "current", "agent": "scripted:good",
               "error": "timeout", "rep": 4}
        clean_rows = [good("T1", "sha") for _ in range(4)] + [err]
        path = pathlib.Path(tmp) / "clean.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in clean_rows), encoding="utf-8")
        code = report.main(["report.py", str(path)])
        check("an error row beside otherwise-consistent good rows is not a "
              "population mismatch", code == 0, code)

        mixed_rows = clean_rows + [good("T2", "aaa"), good("T2", "bbb")]
        path2 = pathlib.Path(tmp) / "mixed.jsonl"
        path2.write_text("\n".join(json.dumps(r) for r in mixed_rows), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code2 = report.main(["report.py", str(path2)])
        out = buf.getvalue()
        check("a real population conflict in one cell still exits 2", code2 == 2, code2)
        check("the untainted cell still renders next to the offending one",
              "T1" in out and "4/4" in out, out)
        check("the offending cell is marked rather than the whole report going dark",
              "MIXED" in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_report_err_not_solved():
    row = {"acceptance": {"passed": 1, "failed": 0, "not_run": 0}, "scope_exit": 0,
           "agent": "claude", "agent_exit": 1, "model": None, "tampered": []}
    check("a green-acceptance row from a crashed CLI reads ERR, not ok",
          report.mark(row) == "ERR", report.mark(row))
    check("mark() and solved() cannot disagree — solved() is defined off mark()",
          not report.solved(row), report.mark(row))


def check_report_gamed_outranks_err():
    row = {"acceptance": {"passed": 0, "failed": 1, "not_run": 0}, "scope_exit": 1,
           "agent": "claude", "agent_exit": 1, "model": None,
           "tampered": [".prompire/brief.yaml"]}
    check("a row that both crashed and rewrote the brief/pin reads GAMED, not ERR",
          report.mark(row) == "GAMED", report.mark(row))


def check_report_attempted_denominator():
    good = {"acceptance": {"passed": 1, "failed": 0, "not_run": 0}, "scope_exit": 0,
            "agent": "scripted:good", "tampered": []}
    crashed = {"acceptance": {"passed": 0, "failed": 0, "not_run": 0}, "scope_exit": 0,
               "agent": "claude", "agent_exit": 1, "model": None, "tampered": []}
    m = report.cell_mark([good, good, good, good, crashed])
    check("an ERR row leaves the attempted cell — denominator drops to 4, not 5",
          m.startswith("4/4"), m)
    check("the dropped ERR row is still visible in the cell's own breakdown",
          "E1" in m, m)


def check_report_all_err_cell():
    crashed = {"acceptance": {"passed": 0, "failed": 0, "not_run": 0}, "scope_exit": 0,
               "agent": "claude", "agent_exit": 1, "model": None, "tampered": []}
    m = report.cell_mark([crashed, crashed, crashed])
    check("a cell with zero attempted runs prints no rate or bound, just the count",
          "/" not in m and "≥" not in m, m)
    check("the all-ERR cell still names how many crashed",
          "E3" in m, m)


def check_report_footer_excludes_err():
    """The footer's `n/n runs solved` must count the same denominator as the cell
    marks above it — otherwise the two numbers on one screen answer different
    questions while sharing a label."""
    tmp = tempfile.mkdtemp(prefix="bench-footer-")
    try:
        good = {"task": "T1", "variant": "current", "agent": "claude",
                "prompt_sha": "sha", "model": "m", "prompire_rev": "rev",
                "acceptance": {"passed": 1, "failed": 0, "not_run": 0},
                "scope_exit": 0, "tampered": [], "seconds": 1.0}
        # Same population as `good` (prompt_sha/model/prompire_rev unchanged) — only
        # agent_exit trips the crash rule. A differing model would also trip the
        # population-mismatch guard, which is a separate concern from this test.
        crashed = {"task": "T1", "variant": "current", "agent": "claude",
                   "prompt_sha": "sha", "model": "m", "prompire_rev": "rev",
                   "acceptance": {"passed": 0, "failed": 0, "not_run": 0},
                   "scope_exit": 0, "agent_exit": 1, "tampered": [], "seconds": 1.0}
        rows = [good, good, good, good, crashed]
        path = pathlib.Path(tmp) / "footer.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report.main(["report.py", str(path)])
        out = buf.getvalue()
        check("the footer excludes the ERR row from its denominator too",
              "4/4 runs solved" in out, out)
        check("the footer does not also print the stale 4/5 count",
              "4/5 runs solved" not in out, out)
        check("one ERR row beside a consistent population is not a mismatch",
              code == 0, code)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    with tempfile.TemporaryDirectory(prefix="prompire-bench-test-") as tmp:
        check_seed_briefs(tmp)
        check_cli(tmp)
    check_dirty_rev()
    check_behavior_coverage()
    check_variants()
    check_ablations()
    check_state_notes_sync()
    check_claude_stats()
    check_scripted()
    check_tamper()
    check_ablation_fidelity()
    check_additive_variants()
    check_brief_edits_invariants()
    check_handed_brief_on_disk()
    check_handed_brief_restored()
    check_report_honesty()
    check_report_refuses_mixed_populations()
    check_report_error_rows_dont_blank_report()
    check_report_err_not_solved()
    check_report_gamed_outranks_err()
    check_report_attempted_denominator()
    check_report_all_err_cell()
    check_report_footer_excludes_err()
    print(f"{TOTAL - FAILS}/{TOTAL} bench harness checks pass")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
