#!/usr/bin/env python3
"""Task compiler orchestrator: short request in, delegation-ready contract out.

The model resolves and attacks the specification; this module is the part that
is trusted, and it earns that by re-measuring everything load-bearing itself:

- every probe case is executed by the orchestrator on an untouched copy of the
  checkout — behavioral cases must FAIL there (reproduction), regression cases
  must pass;
- the Breaker's counterexample is not an opinion: its write-set is applied to a
  fresh copy and the oracle is run; only an oracle that goes green on a wrong
  implementation counts as a confirmed weakness;
- execution-control fields (`autonomy`, `plan_first`, `rollback`) are set here,
  deterministically, and are never model-authored;
- the goal is the user's sentence verbatim, never a model rewrite.

A decision earns `compiler-established` status only from those mechanical
obligations. Whatever remains materially ambiguous is emitted as a marked
question through the existing draft gate, so `prepare`/`lint`/`--activate`
refuse it exactly as they refuse any unconfirmed draft. The verifier is not
modified anywhere on this path.
"""
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

import yaml

import baseline
import compile_prompts
import render_brief
from brief_common import DRAFT_LEDGER, DRAFT_MARKER, norm_cmd, utf8_stdio

PYTHON = "python" if os.name == "nt" else "python3"
PROBE_DIR = ".prompire/probes"
CASE_DEF = re.compile(r"^def (case_[A-Za-z0-9_]+)\(", re.M)
PROBE_TIMEOUT = 120
ROLE_TIMEOUT = 1200
MAX_RESOLVER_ATTEMPTS = 2
MAX_QUESTIONS_ASKED = 2

# Hosts a compile role can run on. The resolver and breaker need to read and
# to execute read-only commands inside their disposable snapshot, so unlike
# DRAFT_AGENTS these entries grant tool use; the snapshot absorbs writes and
# is discarded. An absolute path the model composes still reaches the machine
# — same documented limit as agent-assisted drafting.
ROLE_AGENTS = {
    "claude": ["claude", "-p", "--setting-sources", "project",
               "--output-format", "json", "--allowedTools",
               "Bash,Read,Glob,Grep", "--max-turns", "80"],
}

# Text that must not reach the delivered prompt from a model-authored line: the
# E1 stall class (an approval stop smuggled into prose) and the marker text
# itself. A derived constraint matching this is demoted to a human decision —
# it fails toward review, never toward authority.
EXEC_CONTROL = re.compile(
    r"\bplan\b|\bapprov|\bconfirm|\bpermission\b|\bwait\b|\bpause\b|\bstop\b|"
    r"\bask\b|\bhalt\b|\bdo not (start|begin|proceed)\b|prompire:",
    re.I)

# A probe observes; it does not reach out or mutate. Deny the imports and calls
# that would let model-authored probe code act on the machine instead of
# asserting on the repository. Coarse on purpose: a legitimate probe that trips
# this is rewritten by the resolver, and the failure direction is refusal.
PROBE_DENY = re.compile(
    r"\bsubprocess\b|\bos\.system\b|\bos\.exec|\bos\.spawn|\bos\.popen\b|"
    r"\bshutil\.rmtree\b|\bsocket\b|\burllib\b|\brequests\b|\bhttpx\b|"
    r"\bhttp\.client\b|\bftplib\b|\bsmtplib\b|\bctypes\b|\bos\.remove\b|"
    r"\bos\.unlink\b|\bos\.rename\b|\b__import__\b|\beval\s*\(|\bexec\s*\(",
    re.I)


class CompileError(Exception):
    """The compiler cannot continue this run; the message says why."""


def fill(template, **values):
    # not str.format: the role templates carry literal YAML braces
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def _now():
    return time.monotonic()


class Meter:
    """Every model invocation and probe run, on the record (cost is product)."""

    def __init__(self):
        self.sessions = []
        self.probe_runs = 0
        self.started = _now()

    def record(self, role, seconds, exit_code, usage, cost):
        self.sessions.append({"role": role, "seconds": round(seconds, 1),
                              "exit": exit_code, "usage": usage, "cost": cost})

    def summary(self):
        tokens_in = sum((s["usage"] or {}).get("input_tokens", 0) or 0
                        for s in self.sessions)
        tokens_out = sum((s["usage"] or {}).get("output_tokens", 0) or 0
                         for s in self.sessions)
        cost = sum(s["cost"] or 0 for s in self.sessions)
        return {"model_calls": len(self.sessions),
                "tokens_in": tokens_in, "tokens_out": tokens_out,
                "cost_usd": round(cost, 4) if cost else None,
                "probe_runs": self.probe_runs,
                "wall_seconds": round(_now() - self.started, 1),
                "sessions": self.sessions}


def role_argv(agent, role_cmd):
    if role_cmd:
        argv = shlex.split(role_cmd)
        if not argv:
            raise CompileError("--role-cmd is empty")
        return argv
    if agent not in ROLE_AGENTS:
        known = ", ".join(sorted(ROLE_AGENTS))
        raise CompileError(f"unknown role agent `{agent}`; known: {known} — "
                           "or spell the command with --role-cmd")
    return list(ROLE_AGENTS[agent])


def parse_host_reply(stdout):
    """(text, usage, cost). claude -p --output-format json wraps the reply;
    anything else is taken as the reply itself."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return stdout, None, None
    if isinstance(data, dict) and "result" in data:
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        cost = data.get("total_cost_usd")
        return str(data.get("result") or ""), usage, (
            cost if isinstance(cost, (int, float)) else None)
    return stdout, None, None


def run_role(role, prompt, workdir, argv, meter):
    started = _now()
    try:
        done = subprocess.run(argv, input=prompt, cwd=str(workdir),
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=ROLE_TIMEOUT)
    except FileNotFoundError:
        raise CompileError(f"role command not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        meter.record(role, _now() - started, None, None, None)
        raise CompileError(f"{role} did not answer within {ROLE_TIMEOUT}s")
    text, usage, cost = parse_host_reply(done.stdout)
    meter.record(role, _now() - started, done.returncode, usage, cost)
    if done.returncode:
        tail = (done.stderr or done.stdout or "").strip().splitlines()
        raise CompileError(f"{role} exited {done.returncode}"
                           + (f": {tail[-1][:200]}" if tail else ""))
    return text


# --- probes -----------------------------------------------------------------


def probe_cases(source):
    return CASE_DEF.findall(source)


def probe_lint(source):
    """Reasons this probe source may not run on this machine; empty is clean."""
    findings = []
    hits = sorted(set(PROBE_DENY.findall(source)))
    if hits:
        findings.append("probe uses forbidden operations: "
                        + ", ".join(h.strip() for h in hits))
    try:
        compile(source, "<probe>", "exec")
    except SyntaxError as exc:
        findings.append(f"probe does not parse: {exc}")
    return findings


def run_probe_case(tree, probe_rel, case, meter):
    """One case, executed exactly as the contract will execute it."""
    meter.probe_runs += 1
    try:
        done = subprocess.run([PYTHON, probe_rel] + ([case] if case else []),
                              cwd=str(tree), capture_output=True,
                              encoding="utf-8", errors="replace",
                              timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"case": case, "status": "timeout"}
    except OSError as exc:
        return {"case": case, "status": "error", "detail": str(exc)[:200]}
    tail = ((done.stderr or done.stdout or "").strip().splitlines() or [""])[-1]
    return {"case": case, "status": "pass" if done.returncode == 0 else "fail",
            "exit": done.returncode, "tail": tail[:200]}


def write_probe(tree, slug, source):
    rel = f"{PROBE_DIR}/{slug}.py"
    path = pathlib.Path(tree) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline pinned: the acceptance command hashes these exact bytes, and a
    # platform newline translation would change them under the digest
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(source)
    return rel


def regression_entry(cmd):
    return {"cmd": cmd, "expect": "exit 0"}


def check_regression_cmd(tree, cmd, meter):
    """Classify-guarded, workspace-checked, run on the untouched tree."""
    entry = regression_entry(cmd)
    why = baseline.classify(entry)
    if why:
        return {"cmd": cmd, "status": "refused", "detail": why}
    mismatch = baseline.workspace_mismatch(pathlib.Path(tree), entry)
    if mismatch:
        return {"cmd": cmd, "status": "refused", "detail": mismatch}
    meter.probe_runs += 1
    result = baseline.run_one(pathlib.Path(tree), entry)
    return {"cmd": cmd, "status": result.get("status"),
            "detail": result.get("reason") or result.get("evidence")}


def measure_spec(root, slug, spec, meter, snapshot_ctx):
    """The orchestrator's own reading of the candidate spec on untouched HEAD.

    Returns a measurement dict; raises nothing — a broken probe is a result.
    Behavioral cases must fail here (that is the reproduction), regression and
    boundary cases must pass, and the dispatch must be honest (an unknown case
    name must not exit 0).
    """
    findings = probe_lint(spec["probe_file"])
    if findings:
        return {"ok": False, "reason": "; ".join(findings), "cases": {},
                "regression": []}
    defined = probe_cases(spec["probe_file"])
    named = {c for r in spec["requirements"] for c in r["cases"]}
    undefined = sorted(named - set(defined))
    if undefined:
        return {"ok": False, "cases": {}, "regression": [],
                "reason": "cases named but not defined: " + ", ".join(undefined)}
    with snapshot_ctx(root) as (tree, _rev):
        probe_rel = write_probe(tree, slug, spec["probe_file"])
        cases = {}
        for case in defined:
            cases[case] = run_probe_case(tree, probe_rel, case, meter)
        honest = run_probe_case(tree, probe_rel, "case_prompire_no_such_case",
                                meter)
        regression = [check_regression_cmd(tree, r["cmd"], meter)
                      for r in spec["regression"]]
    kinds = {}
    for r in spec["requirements"]:
        for c in r["cases"]:
            kinds[c] = r["kind"]
    wrong_on_head = []
    flip_cases, hold_cases = [], []
    for case, result in cases.items():
        kind = kinds.get(case, "behavioral")
        if kind == "behavioral":
            if result["status"] == "fail":
                flip_cases.append(case)
            else:
                wrong_on_head.append(
                    f"{case}: behavioral but {result['status']} on HEAD")
        else:
            if result["status"] == "pass":
                hold_cases.append(case)
            else:
                wrong_on_head.append(
                    f"{case}: {kind} but {result['status']} on HEAD")
    if honest["status"] == "pass":
        wrong_on_head.append("probe exits 0 for an unknown case name")
    good_regression = [r for r in regression if r["status"] == "pass"]
    return {
        "ok": not wrong_on_head and bool(flip_cases),
        "reason": ("; ".join(wrong_on_head) if wrong_on_head
                   else ("no behavioral case fails on HEAD — nothing "
                         "distinguishes untouched from done"
                         if not flip_cases else "")),
        "cases": cases,
        "flip_cases": sorted(flip_cases),
        "hold_cases": sorted(hold_cases),
        "regression": regression,
        "regression_ok": [r["cmd"] for r in good_regression],
    }


# --- breaker verification ---------------------------------------------------


def apply_writes(tree, writes):
    changed = False
    for rel, content in writes.items():
        path = pathlib.Path(tree) / rel
        before = None
        if path.is_file():
            before = path.read_text(encoding="utf-8", errors="replace")
        if before != content:
            changed = True
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return changed


def verify_counterexample(root, slug, spec, measurement, breaker, meter,
                          snapshot_ctx):
    """Did the claimed wrong implementation really pass the oracle?

    Mechanical, in a fresh copy: apply the write-set, run every probe case and
    every usable regression command. The weakness is confirmed only when the
    oracle is fully green there; the counter-probe is then run to record the
    demonstrated violation.
    """
    ce = breaker["counterexample"]
    with snapshot_ctx(root) as (tree, _rev):
        probe_rel = write_probe(tree, slug, spec["probe_file"])
        if not apply_writes(tree, ce["writes"]):
            return {"confirmed": False,
                    "reason": "write-set does not change the tree"}
        oracle = {}
        for case in measurement["flip_cases"] + measurement["hold_cases"]:
            oracle[case] = run_probe_case(tree, probe_rel, case, meter)
        regression = [check_regression_cmd(tree, cmd, meter)
                      for cmd in measurement["regression_ok"]]
        failed = ([c for c, r in oracle.items() if r["status"] != "pass"]
                  + [r["cmd"] for r in regression if r["status"] != "pass"])
        if failed:
            return {"confirmed": False, "oracle": oracle,
                    "reason": "oracle caught it: " + ", ".join(failed[:4])}
        counter_rel = write_probe(tree, f"{slug}-counter", ce["counter_probe"])
        counter = run_probe_case(tree, counter_rel, ce["counter_case"], meter)
    if probe_lint(ce["counter_probe"]):
        return {"confirmed": False,
                "reason": "counter-probe fails the probe lint"}
    if counter["status"] != "fail":
        return {"confirmed": False, "oracle": oracle,
                "reason": f"counter-probe did not demonstrate a violation "
                          f"({counter['status']})"}
    return {"confirmed": True, "oracle": oracle, "counter": counter,
            "description": ce["description"]}


# --- emission ---------------------------------------------------------------


def integrity_cmd(probe_rel, digest):
    payload = ("import hashlib,runpy,sys;"
               f"p='{probe_rel}';"
               "d=hashlib.sha256(open(p,'rb').read()).hexdigest();"
               f"assert d=='{digest}','probe-tampered';"
               "sys.argv=[p];runpy.run_path(p,run_name='__main__')")
    return f'{PYTHON} -c "{payload}"'


def constraint_established(item, spec):
    """A derived constraint reaches the prompt unconfirmed only when a probe
    case observes the requirement it restates and its text carries no
    execution-control content."""
    if EXEC_CONTROL.search(item["text"]):
        return False
    backing = next((r for r in spec["requirements"]
                    if r["id"] == item["requirement"]), None)
    return bool(backing and backing["cases"])


def emit_brief(request, slug, spec, digest, probe_rel, questions):
    """The contract text. Marked lines exist exactly where a human decision
    remains; everything else earned its absence of a marker mechanically."""
    ledger_labels = []
    lines = ["goal: |"]
    lines += [f"  {line}".rstrip() for line in request.strip().splitlines()] or ["  ."]
    lines.append("scope:")
    for entry in spec["scope"]:
        lines.append(f"  - {yaml_scalar(entry['path'])}")
    if spec["forbidden"]:
        lines.append("forbidden:")
        lines += [f"  - {yaml_scalar(p)}" for p in spec["forbidden"]]
    else:
        lines.append("forbidden: []")
    established = [c["text"] for c in spec["constraints"]
                   if constraint_established(c, spec)]
    pending = [q for q in questions]
    if established or pending:
        lines.append("constraints:")
        for text in established:
            lines.append(f"  - {yaml_scalar(text)}")
        for q in pending:
            options = "; ".join(f"{chr(65 + i)}: {o}"
                                for i, o in enumerate(q["options"]))
            body = f"DECIDE {q['id']}: {q['text']}"
            if options:
                body += f" ({options})"
            label = f"question {q['id']}"
            ledger_labels.append(label)
            lines.append(
                f"  - {yaml_scalar(body)}  # {DRAFT_MARKER} — replace this "
                "line with the decided behavior, then delete this marker")
    lines.append(f"tests_policy: {spec['tests_policy']}")
    if spec["tests_policy"] != "immutable" and spec["tests_editable"]:
        lines.append("tests_editable:")
        lines += [f"  - {yaml_scalar(p)}" for p in spec["tests_editable"]]
    lines.append("acceptance:")
    lines.append(f"  - cmd: {yaml_scalar(integrity_cmd(probe_rel, digest))}")
    lines.append("    expect: exit 0")
    lines.append("    transition: flip")
    for cmd in spec.get("regression_ok", []):
        lines.append(f"  - cmd: {yaml_scalar(cmd)}")
        lines.append("    expect: exit 0")
    lines.append("autonomy: ask")
    if ledger_labels:
        head = [f"# Draft — a question remains. Read every `# {DRAFT_MARKER}` "
                "line, decide it, delete",
                f"# the marker, then delete the `{DRAFT_LEDGER}:` block. "
                "prepare refuses until then.",
                f"{DRAFT_LEDGER}:"]
        head += [f"  - {yaml_scalar(label)}" for label in ledger_labels]
        lines = head + lines
    return "\n".join(lines) + "\n"


def yaml_scalar(value):
    text = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True,
                          width=2 ** 20).strip()
    return text[:-4].strip() if text.endswith("\n...") else text


def write_ledger(path, record):
    path.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False,
                                   width=120), encoding="utf-8")


def build_ledger(request, state, spec, measurement, rounds, questions, meter):
    decisions = []
    for r in spec["requirements"]:
        covered = [c for c in r["cases"]]
        breaker_note = None
        for rnd in rounds:
            if rnd.get("confirmed"):
                breaker_note = f"strengthened after round {rnd['round']}"
        decisions.append({
            "id": r["id"], "claim": r["text"], "kind": r["kind"],
            "class": "derived", "evidence": r["evidence"],
            "cases": covered,
            "status": "compiler-established" if covered else "recorded",
            "breaker": breaker_note,
        })
    for q in questions:
        decisions.append({"id": q["id"], "claim": q["text"],
                          "class": "decision", "options": q["options"],
                          "status": "human-decision-required"})
    return {
        "request": request,
        "state": state,
        "decisions": decisions,
        "measurement": {
            "flip_cases": measurement.get("flip_cases", []),
            "hold_cases": measurement.get("hold_cases", []),
            "regression_ok": measurement.get("regression_ok", []),
            "cases": measurement.get("cases", {}),
        },
        "breaker_rounds": rounds,
        "cost": meter.summary(),
    }


# --- the compile run --------------------------------------------------------


def validate_final(root, slug, brief_text, probe_source, snapshot_ctx):
    """Would `prepare` accept this contract? Asked in a copy, before claiming
    READY: baseline --write, lint, render budget — the real tools, not a
    reimplementation."""
    here = pathlib.Path(__file__).resolve().parent
    with snapshot_ctx(root) as (tree, _rev):
        write_probe(tree, slug, probe_source)
        brief = pathlib.Path(tree) / ".prompire" / f"{slug}.yaml"
        brief.parent.mkdir(parents=True, exist_ok=True)
        brief.write_text(brief_text, encoding="utf-8")
        for tool, args in (("baseline.py", ["--write"]), ("lint_brief.py", [])):
            done = subprocess.run(
                [sys.executable, str(here / tool), str(brief)] + args,
                cwd=str(tree), capture_output=True, encoding="utf-8",
                errors="replace")
            if done.returncode:
                return (f"{tool} exit {done.returncode}: "
                        + (done.stdout + done.stderr).strip()[-400:])
        data = yaml.safe_load(brief.read_text(encoding="utf-8"))
        counts = render_brief.preview_counts(data, str(brief))
        over = {t: n for t, n in counts.items() if n > render_brief.WORD_BUDGET}
        if over:
            return "render budget exceeded: " + ", ".join(
                f"{t} {n}/{render_brief.WORD_BUDGET}" for t, n in over.items())
    return None


def compile_request(request, root, slug, agent="claude", role_cmd=None,
                    max_breaker_rounds=2, snapshot_ctx=None, log=print):
    """The full loop. Returns (state, payload)."""
    if snapshot_ctx is None:
        from prompire import draft_snapshot as snapshot_ctx
    meter = Meter()
    argv = role_argv(agent, role_cmd)
    root = pathlib.Path(root)

    spec = None
    trouble = None
    with snapshot_ctx(root) as (tree, _rev):
        for attempt in range(MAX_RESOLVER_ATTEMPTS):
            prompt = fill(compile_prompts.RESOLVER_PROMPT, request=request)
            if trouble:
                prompt += ("\nYour previous reply was rejected: "
                           f"{trouble}. Answer again, one yaml document only.")
            reply = run_role("resolver", prompt, tree, argv, meter)
            spec, trouble = compile_prompts.parse_resolver_reply(reply)
            if spec:
                break
    if spec is None:
        return "INSUFFICIENT_SPEC", {
            "reason": f"resolver reply unusable: {trouble}",
            "cost": meter.summary()}
    log("✓ specification candidate resolved "
        f"({len(spec['requirements'])} requirements)")

    rounds = []
    measurement = None
    for round_no in range(1, max_breaker_rounds + 2):
        measurement = measure_spec(root, slug, spec, meter, snapshot_ctx)
        if not measurement["ok"]:
            # one repair pass through the refine prompt; a spec that cannot
            # produce a red reproduction is not a contract
            if round_no > max_breaker_rounds:
                return "INSUFFICIENT_SPEC", {
                    "reason": f"measurement failed: {measurement['reason']}",
                    "cost": meter.summary()}
            weakness = ("the orchestrator could not establish the probe on "
                        f"the untouched checkout: {measurement['reason']}")
            spec = refine(request, spec, weakness, "", root, argv, meter,
                          snapshot_ctx)
            if spec is None:
                return "INSUFFICIENT_SPEC", {
                    "reason": f"refinement failed after: {weakness}",
                    "cost": meter.summary()}
            continue
        log(f"✓ reproduced on HEAD ({len(measurement['flip_cases'])} failing "
            f"case(s)); {len(measurement['regression_ok'])} regression "
            "command(s) green")
        spec["regression_ok"] = measurement["regression_ok"]
        if round_no > max_breaker_rounds:
            break
        breaker_result, verified = attack(request, root, slug, spec,
                                          measurement, argv, meter,
                                          snapshot_ctx)
        record = {"round": round_no,
                  "attempted": breaker_result["attempted"]
                  if breaker_result else [],
                  "verdict": breaker_result["verdict"]
                  if breaker_result else "error",
                  "confirmed": bool(verified and verified.get("confirmed"))}
        if verified:
            record["detail"] = verified.get("description") or verified.get("reason")
        rounds.append(record)
        if not (verified and verified["confirmed"]):
            log("✓ stress-tested: no plausible wrong implementation passed "
                f"(round {round_no})")
            break
        log(f"✗ specification too weak (round {round_no}): "
            f"{verified['description']} — strengthening")
        ce = breaker_result["counterexample"]
        spec2 = refine(request, spec,
                       f"a wrong implementation passed every check: "
                       f"{verified['description']}",
                       ce["counter_probe"], root, argv, meter, snapshot_ctx)
        if spec2 is None:
            return "INSUFFICIENT_SPEC", {
                "reason": "refinement failed after a confirmed weakness",
                "rounds": rounds, "cost": meter.summary()}
        spec = spec2

    material = list(spec["questions"][:compile_prompts.MAX_QUESTIONS])
    if spec["tests_policy"] != "immutable" and not re.search(
            r"\btests?\b", request, re.I):
        # relaxing test protection is authority the request itself must carry
        material.append({
            "id": f"Q{len(material) + 1}",
            "text": (f"the compiler proposes tests_policy: "
                     f"{spec['tests_policy']} but the request does not "
                     "mention tests — allow test edits?"),
            "options": ["keep tests immutable", "allow the named test paths"],
            "default": ""})
        spec["tests_policy"] = "immutable"
        spec["tests_editable"] = []
    if len(material) > MAX_QUESTIONS_ASKED:
        return "INSUFFICIENT_SPEC", {
            "reason": f"{len(material)} material decisions remain — this "
                      "request is a product-design task, not a compilable one",
            "questions": material, "rounds": rounds, "cost": meter.summary()}

    probe_source = spec["probe_file"]
    digest = hashlib.sha256(probe_source.encode("utf-8")).hexdigest()
    probe_rel = f"{PROBE_DIR}/{slug}.py"
    brief_text = emit_brief(request, slug, spec, digest, probe_rel, material)
    # validation runs on the established core — the questions are marked lines
    # the human will replace, and lint (B18) rightly refuses a marked draft
    core_text = (emit_brief(request, slug, spec, digest, probe_rel, [])
                 if material else brief_text)
    failure = validate_final(root, slug, core_text, probe_source, snapshot_ctx)
    if failure:
        return "INSUFFICIENT_SPEC", {
            "reason": f"final validation failed: {failure}",
            "rounds": rounds, "cost": meter.summary()}

    state = "READY" if not material else "NEEDS_DECISION"
    ledger = build_ledger(request, state, spec, measurement, rounds,
                          material, meter)
    return state, {"brief_text": brief_text, "probe_source": probe_source,
                   "probe_rel": probe_rel, "questions": material,
                   "ledger": ledger, "rounds": rounds,
                   "cost": meter.summary()}


def attack(request, root, slug, spec, measurement, argv, meter, snapshot_ctx):
    """One breaker round in a fresh context; (breaker_result, verification)."""
    oracle_cmds = [f"{PYTHON} {PROBE_DIR}/{slug}.py  # all cases"]
    oracle_cmds += measurement["regression_ok"]
    prompt = fill(compile_prompts.BREAKER_PROMPT,
                  request=request,
                  requirements=compile_prompts.render_requirements(spec),
                  oracle=compile_prompts.render_oracle(oracle_cmds),
                  probe_rel=f"{PROBE_DIR}/{slug}.py")
    with snapshot_ctx(root) as (tree, _rev):
        write_probe(tree, slug, spec["probe_file"])
        try:
            reply = run_role("breaker", prompt, tree, argv, meter)
        except CompileError as exc:
            return None, {"confirmed": False, "reason": str(exc)}
    result, trouble = compile_prompts.parse_breaker_reply(reply)
    if trouble:
        return None, {"confirmed": False,
                      "reason": f"breaker reply unusable: {trouble}"}
    if result["verdict"] == "no_counterexample":
        return result, {"confirmed": False, "reason": "no counterexample"}
    verified = verify_counterexample(root, slug, spec, measurement, result,
                                     meter, snapshot_ctx)
    return result, verified


def refine(request, spec, weakness, counter_probe, root, argv, meter,
           snapshot_ctx):
    prompt = fill(compile_prompts.REFINE_PROMPT,
                  request=request,
                  previous=compile_prompts.render_spec_for_refine(spec),
                  weakness=weakness,
                  counter_probe=counter_probe or "(none)")
    with snapshot_ctx(root) as (tree, _rev):
        try:
            reply = run_role("refiner", prompt, tree, argv, meter)
        except CompileError:
            return None
    revised, trouble = compile_prompts.parse_resolver_reply(reply)
    return revised if not trouble else None
