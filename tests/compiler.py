#!/usr/bin/env python3
"""Tests for the task compiler orchestrator (`prompire compile`).

Every case runs the real loop — snapshots, probe measurement, breaker
verification, emission — with scripted role replies (tests/fake_roles.py), so
the orchestrator's mechanical obligations are exercised without a model.

Run: python3 tests/compiler.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import fixtures  # noqa: E402
import compile_task  # noqa: E402
import compile_prompts  # noqa: E402
from brief_common import DRAFT_LEDGER, DRAFT_MARKER  # noqa: E402

CASES = []


def case(name):
    def decorate(fn):
        CASES.append((name, fn))
        return fn
    return decorate


class Checks:
    def __init__(self):
        self.fails = []

    def ok(self, condition, message):
        if not condition:
            self.fails.append(message)

    def equal(self, got, want, message):
        self.ok(got == want, f"{message}: got {got!r}, want {want!r}")


def compile_with(repo, scenario, request="fix total() so it returns the sum",
                 rounds=2):
    state_file = pathlib.Path(tempfile.mkstemp(prefix="fake-state-")[1])
    os.environ["FAKE_SCENARIO"] = scenario
    os.environ["FAKE_STATE"] = str(state_file)
    try:
        role_cmd = f'"{sys.executable}" "{HERE / "fake_roles.py"}"'
        milestones = []
        state, payload = compile_task.compile_request(
            request, repo, "task", role_cmd=role_cmd,
            max_breaker_rounds=rounds, log=milestones.append)
        counts = {}
        if state_file.is_file():
            for line in state_file.read_text().splitlines():
                key, _, value = line.partition("=")
                counts[key] = int(value or 0)
        return state, payload, counts, milestones
    finally:
        state_file.unlink(missing_ok=True)
        os.environ.pop("FAKE_SCENARIO", None)
        os.environ.pop("FAKE_STATE", None)


@case("weak spec is broken, strengthened, then survives — READY")
def _(repo, c):
    state, payload, counts, milestones = compile_with(
        repo, "ready-after-strengthen")
    c.equal(state, "READY", "state")
    c.equal(counts.get("breaker"), 2, "breaker ran twice")
    c.equal(counts.get("refiner"), 1, "one refinement round")
    rounds = payload["rounds"]
    c.ok(rounds and rounds[0]["confirmed"], "round 1 weakness confirmed")
    c.ok(len(rounds) == 2 and not rounds[1]["confirmed"],
         "round 2 found nothing")
    text = payload["brief_text"]
    c.ok(DRAFT_MARKER not in text, "READY brief carries no markers")
    c.ok(f"{DRAFT_LEDGER}:" not in text, "READY brief carries no ledger block")
    brief = yaml.safe_load(text)
    c.equal(brief["goal"].strip(), "fix total() so it returns the sum",
            "goal is the user's sentence verbatim")
    c.equal(brief["autonomy"], "ask", "autonomy set deterministically")
    c.ok("plan_first" not in brief, "no model-authored plan gate")
    flips = [a for a in brief["acceptance"] if a.get("transition") == "flip"]
    c.equal(len(flips), 1, "one flip criterion")
    c.ok("hashlib.sha256" in flips[0]["cmd"], "probe digest pinned in the cmd")
    c.ok("case_total_general" in payload["probe_source"],
         "strengthened probe adopted")
    ledger = payload["ledger"]
    c.equal(ledger["state"], "READY", "ledger state")
    c.ok(any(d["status"] == "compiler-established"
             for d in ledger["decisions"]), "established decision recorded")
    c.ok(ledger["cost"]["model_calls"] >= 4, "cost recorded")


@case("the emitted contract runs end to end and catches tampering")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "ready-after-strengthen")
    c.equal(state, "READY", "state")
    probe_path = repo / payload["probe_rel"]
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    with open(probe_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload["probe_source"])
    brief = yaml.safe_load(payload["brief_text"])
    flip_cmd = next(a["cmd"] for a in brief["acceptance"]
                    if a.get("transition") == "flip")
    on_head = subprocess.run(flip_cmd, shell=True, cwd=str(repo),
                             capture_output=True, text=True)
    c.ok(on_head.returncode != 0, "flip criterion is red on untouched HEAD")
    (repo / "src" / "cart.py").write_text(
        "def add(items, item):\n    return list(items) + [item]\n\n\n"
        "def total(items):\n    return sum(items)\n", encoding="utf-8")
    fixed = subprocess.run(flip_cmd, shell=True, cwd=str(repo),
                           capture_output=True, text=True)
    c.equal(fixed.returncode, 0, "flip criterion green after the real fix")
    probe_path.write_text(probe_path.read_text(encoding="utf-8")
                          .replace("== 3", "== 2"), encoding="utf-8")
    tampered = subprocess.run(flip_cmd, shell=True, cwd=str(repo),
                              capture_output=True, text=True)
    c.ok(tampered.returncode != 0, "edited probe fails the digest check")
    c.ok("probe-tampered" in (tampered.stderr + tampered.stdout),
         "tampering is named")


@case("a probe green on HEAD cannot become a contract")
def _(repo, c):
    state, payload, counts, _m = compile_with(repo, "vacuous-probe", rounds=1)
    c.equal(state, "INSUFFICIENT_SPEC", "state")
    c.ok("HEAD" in str(payload.get("reason", "")) or "behavioral"
         in str(payload.get("reason", "")), "reason names the vacuity")


@case("one material question — NEEDS_DECISION with a marked line")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "one-question")
    c.equal(state, "NEEDS_DECISION", "state")
    c.equal(len(payload["questions"]), 1, "one question")
    text = payload["brief_text"]
    c.ok(DRAFT_MARKER in text, "the question line is marked")
    data = yaml.safe_load(text)
    c.ok(DRAFT_LEDGER in data, "the unconfirmed ledger survives a round-trip")
    c.ok(any("DECIDE Q1" in str(item) for item in data.get("constraints", [])),
         "the question is in the contract, not only in chat")


@case("three material questions — not a compilable request")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "three-questions")
    c.equal(state, "INSUFFICIENT_SPEC", "state")
    c.ok("material decisions" in str(payload.get("reason")), "reason says why")


@case("a relaxed tests_policy the request never asked for becomes a question")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "relax-tests-policy")
    c.equal(state, "NEEDS_DECISION", "state")
    c.ok(any("tests_policy" in q["text"] for q in payload["questions"]),
         "the question names the policy")
    data = yaml.safe_load(payload["brief_text"])
    c.ok("tests_policy" not in data or data["tests_policy"] == "immutable",
         "the emitted policy stays immutable meanwhile")


@case("an execution-control constraint never reaches the prompt unconfirmed")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "stall-constraint")
    c.equal(state, "READY", "state")
    text = payload["brief_text"]
    c.ok("plan approval" not in text, "the stall sentence is not in the brief")
    c.ok("add() keeps returning a new list" in text,
         "the probe-backed constraint is")


@case("a probe that reaches for subprocess is refused")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "denied-probe", rounds=1)
    c.equal(state, "INSUFFICIENT_SPEC", "state")
    c.ok("forbidden operations" in str(payload.get("reason")),
         "reason names the deny rule")


@case("a breaker counterexample the oracle catches is not a weakness")
def _(repo, c):
    state, payload, counts, _m = compile_with(repo, "breaker-uncaught",
                                              rounds=1)
    c.equal(state, "READY", "state")
    rounds = payload["rounds"]
    c.ok(rounds and not rounds[0]["confirmed"],
         "unverified counterexample not confirmed")
    c.equal(counts.get("refiner"), None, "no refinement was spent on it")


@case("a breaker that answers garbage does not sink the run")
def _(repo, c):
    state, payload, _counts, _m = compile_with(repo, "breaker-garbage",
                                               rounds=1)
    c.equal(state, "READY", "state")
    c.equal(payload["rounds"][0]["verdict"], "error", "the round is recorded")


@case("a resolver that answers garbage twice is INSUFFICIENT")
def _(repo, c):
    state, payload, counts, _m = compile_with(repo, "resolver-garbage")
    c.equal(state, "INSUFFICIENT_SPEC", "state")
    c.equal(counts.get("resolver"), 2, "the resolver got its retry")
    c.ok("resolver reply unusable" in str(payload.get("reason")), "reason")


@case("the CLI writes brief, probe and ledger, and prepare accepts READY")
def _(repo, c):
    state_file = pathlib.Path(tempfile.mkstemp(prefix="fake-state-")[1])
    env = os.environ.copy()
    env["FAKE_SCENARIO"] = "unbreakable-round-one"
    env["FAKE_STATE"] = str(state_file)
    role_cmd = f'"{sys.executable}" "{HERE / "fake_roles.py"}"'
    done = subprocess.run(
        [sys.executable, str(ROOT / "prompire.py"), "compile",
         "fix total() so it returns the sum", "--slug", "task",
         "--role-cmd", role_cmd, "--json"],
        cwd=str(repo), capture_output=True, text=True, env=env)
    state_file.unlink(missing_ok=True)
    c.equal(done.returncode, 0, "compile exit for READY")
    data = json.loads(done.stdout)
    c.equal(data["status"], "ready", "json status")
    c.ok((repo / ".prompire" / "task.yaml").is_file(), "brief written")
    c.ok((repo / ".prompire" / "probes" / "task.py").is_file(), "probe written")
    c.ok((repo / ".prompire" / "task.ledger.yaml").is_file(), "ledger written")
    prepared = subprocess.run(
        [sys.executable, str(ROOT / "prompire.py"), "prepare",
         ".prompire/task.yaml"],
        cwd=str(repo), capture_output=True, text=True)
    c.equal(prepared.returncode, 0,
            f"prepare accepts the READY contract: {prepared.stdout}"
            f"{prepared.stderr}")


@case("parser refuses the shapes that burned E2")
def _(repo, c):
    spec, err = compile_prompts.parse_resolver_reply("```yaml\nrequirements: []\n```")
    c.ok(err == "no requirements", "empty requirements named")
    _spec, err = compile_prompts.parse_resolver_reply("just prose, no yaml")
    c.ok(err is not None, "prose refused")
    _spec, err = compile_prompts.parse_resolver_reply(
        "requirements:\n  - id: R1\n    text: t\n    cases: [case_x]\n"
        "scope: [{path: a.py}]\nprobe_file: |\n  pass\n")
    c.ok("not defined" in str(err), "undefined case names refused")
    _res, err = compile_prompts.parse_breaker_reply(
        "verdict: counterexample\nattempted: [x]\ncounterexample:\n"
        "  writes: {'../../etc/evil': 'x'}\n"
        "  counter_probe: |\n    def case_a(): pass\n  counter_case: case_a\n")
    c.ok("not a safe relative path" in str(err), "path escape refused")
    reply = ("requirements:\n  - id: R1\n    text: t\n    kind: behavioral\n"
             "    cases: []\nscope: [{path: a.py}]\n"
             "probe_file: |\n  x = 1\nquestions: []\n")
    _spec, err = compile_prompts.parse_resolver_reply(reply)
    c.ok("no behavioral probe cases" in str(err),
         "behavioral requirements need at least one case")


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        tool_dir = root / "bin"
        tool_dir.mkdir()
        if os.name == "nt":
            (tool_dir / "python.cmd").write_text(
                f'@"{sys.executable}" %*\n', encoding="utf-8")
        else:
            (tool_dir / "python").symlink_to(sys.executable)
        os.environ["PATH"] = str(tool_dir) + os.pathsep + os.environ["PATH"]
        for name, fn in CASES:
            repo = fixtures.build(root / name.replace(" ", "-")[:40])
            checks = Checks()
            try:
                fn(repo, checks)
            except Exception as error:
                checks.fails.append(f"unexpected exception: {error!r}")
            if checks.fails:
                failures += 1
                print(f"FAIL  {name}")
                for failure in checks.fails:
                    print(f"      {failure}")
            else:
                print(f"PASS  {name}")
    print(f"{len(CASES) - failures}/{len(CASES)} compiler cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
