#!/usr/bin/env python3
"""Role prompts and reply parsing for the task compiler (`prompire compile`).

Two model roles exist: the Resolver, which investigates the repository and
synthesizes a candidate specification, and the Breaker, which receives that
specification in a fresh context and tries to construct a wrong implementation
the specification would accept. Every reply is parsed as data — sizes clamped,
shapes validated, unknown keys refused — because a role's output is untrusted
until the orchestrator has measured or falsified it.
"""
import json
import re

import yaml

MAX_REQUIREMENTS = 12
MAX_QUESTIONS = 4
MAX_SCOPE = 12
MAX_CONSTRAINTS = 8
MAX_PROBE_BYTES = 32_000
MAX_WRITE_BYTES = 200_000
MAX_WRITE_FILES = 8

REQUIREMENT_KINDS = ("behavioral", "regression", "boundary")

RESOLVER_PROMPT = """\
You are the Resolver stage of a task compiler. A human wrote one short coding
request for this repository. Your job is to resolve what the task actually
requires — not to implement it, and not to interview the human.

Request: {request}

Work in this order:
1. Intent: restate to yourself what observable outcome the request asks for.
   Do not embellish it.
2. Gap analysis: list what you would need to know to delegate this safely —
   current behavior, sibling code paths, error semantics, boundary cases,
   compatibility expectations.
3. Investigate: answer those gaps from THIS repository. Read the
   implementation, its callers, sibling paths, existing tests, docs, git
   history. Run read-only commands (imports, the test runner, small scripts)
   to observe actual behavior. Do not summarize the repository; chase only
   your open questions. You are in a disposable copy — nothing you write here
   survives — but keep the tree clean anyway so your own probes are honest.
4. Reproduce: for a behavioral bug or change, demonstrate the missing
   behavior on the current checkout. A task-specific observation that FAILS
   today is worth more than a green test suite.
5. Synthesize the specification below.

Requirements must be MATERIAL: the behaviors a correct implementation cannot
skip, including the ones the request left unstated but the repository
evidences (sibling units, both signs, all precisions, every affected code
path — not just the example in the request). Do not pad with obvious noise.

Each behavioral requirement needs at least one probe case: a small executable
check that FAILS on the current checkout and will pass when the requirement
is met. Boundary/regression requirements get cases that pass today and must
keep passing. Write all cases into ONE python probe file:
- each case is a function `case_<name>()` that raises AssertionError (with a
  short message) on violation and returns normally otherwise;
- module-level main: `python3 <file> <case_name>` runs one case, no argument
  runs all; exit 0 on success, 1 on any failure;
- pure observation only: import the code under test from the repository and
  assert on behavior. No subprocess, no network, no writes outside
  tempfile.TemporaryDirectory. Keep it under 200 lines.
- the file will run from the repository root with the repository on sys.path
  via `sys.path.insert(0, '.')` which YOU must include at the top.

Ask a question ONLY when two materially different specifications both remain
plausible after investigation and choosing one would change observable
behavior or API. Never ask what the repository can answer. A question must
name the concrete alternatives.

Answer with ONE yaml document and nothing else — no prose before or after,
no code fences:

requirements:
  - id: R1
    text: <one sentence, the requirement itself>
    kind: behavioral | regression | boundary
    evidence:
      - <file:line or observed-behavior note, 1-4 entries>
    cases: [<case function names covering this requirement>]
scope:
  - path: <file the work may edit; exact paths, never `.`>
    reason: <why>
    new: false | true
forbidden: []            # paths that must not change, or []
constraints: []          # optional; each: {text: <observable fact that must
                         # stay true>, requirement: <Rn it restates>}
tests_policy: immutable  # relax only if the request itself is about tests
tests_editable: []       # only with named/authoring
regression:              # existing suite commands this repo evidences; [] if none
  - cmd: <command>
    reason: <where the repo declares it>
probe_file: |
  <the python source described above>
questions: []            # only material irreducible decisions; each:
                         # {id: Q1, text: <question>, options: [<A>, <B>],
                         #  default: <the option you would pick and why>}
notes: <at most three sentences on the shape of the spec, for the record>
"""

BREAKER_PROMPT = """\
You are the Breaker stage of a task compiler, in a fresh context. A candidate
specification was compiled for the short request below. Your single objective:
find the simplest PLAUSIBLE WRONG implementation that would still satisfy the
specification's acceptance checks.

Request: {request}

Candidate requirements:
{requirements}

Acceptance oracle (every probe case below must pass, plus these commands):
{oracle}

The probe file is at {probe_rel} in this repository copy. Read it. Run it.
You may modify the repository here freely — it is a disposable copy — to
develop and test your counterexample.

A counterexample is a write-set that:
- a hurried but plausible developer could genuinely produce for this request
  (special-casing the reported example, fixing one code path but not its
  sibling, one sign, one precision, one locale, the wrapper but not the
  direct API, changing tests instead of behavior — derive what fits THIS
  task, do not apply that list mechanically);
- makes EVERY acceptance check above pass (verify this yourself by running
  the probe file and the commands);
- violates behavior the request, read faithfully, actually requires.

Also write a counter-probe: one python case function proving the violation —
it must FAIL under your write-set, and describe behavior a correct
implementation would satisfy. Same conventions as the probe file (sys.path
insert, case_* function, assertions).

Do not critique prose, style, or architecture. Do not invent requirements the
task cannot support. If after honest attempts every plausible wrong
implementation is caught by the oracle, say so.

Answer with ONE yaml document, no fences, no prose:

verdict: counterexample | no_counterexample
attempted:
  - <attack class you tried, one line each, 2-8 entries>
counterexample:          # only when verdict: counterexample
  description: <one sentence — what the wrong implementation does>
  writes:
    <repo-relative path>: |
      <full new content of that file>
  counter_probe: |
    <python source: sys.path insert + one case_<name> function + main>
  counter_case: <the case function name>
"""

REFINE_PROMPT = """\
You are the Resolver stage of a task compiler, continuing after an
adversarial round. Your previous candidate specification for the request
below was defeated: a wrong implementation passed every acceptance check.

Request: {request}

Your previous specification:
{previous}

Confirmed weakness (the orchestrator verified this mechanically):
{weakness}

Counter-probe that demonstrated the violation:
{counter_probe}

Strengthen the specification so this class of wrong implementation fails —
generalize; do not only pin the single counterexample. Adopt or adapt the
counter-probe case if it is honest. Keep everything that was already right.
Re-answer with the SAME yaml document format as before (requirements, scope,
forbidden, constraints, tests_policy, tests_editable, regression, probe_file,
questions, notes) — the complete revised specification, not a delta.
"""


FENCE = re.compile(r"^\s*```[^\n]*\n(.*?)^\s*```\s*$", re.S | re.M)


def _fenced_blocks(text):
    """Every fenced block's body, outermost-first. A role that leads with a
    sentence and then fences its whole document is the common shape — five of
    eight evaluated compiles died on exactly that, because stripping only a
    fence on line 1 left the opening fence inside the parsed text."""
    return [match.group(1) for match in FENCE.finditer(str(text or ""))]


def _strip_fences(text):
    lines = str(text or "").strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


RESERVED_ITEM = re.compile(r"^(\s*-\s+)([`@].*)$")


def _quote_reserved_items(text):
    """A list item starting with a backtick or `@` is a YAML reserved
    indicator, and a model writing markdown-flavored prose produces exactly
    that. Quote only such lines; everything else stays byte-identical."""
    out = []
    for line in text.splitlines():
        match = RESERVED_ITEM.match(line)
        if match:
            out.append(match.group(1) + json.dumps(match.group(2)))
        else:
            out.append(line)
    return "\n".join(out)


def _load_yaml(text):
    """A role reply parsed as data; None with a reason when it is not."""
    raw = _strip_fences(text)
    trouble = "the reply is not YAML"
    data = None
    # Models lead with a sentence, fence the document, or start a list item
    # with a reserved indicator. Each recovery is tried in turn; the reply is
    # data, and none of these rewrites can add or change a value — they only
    # find where the document begins and quote an indicator character.
    attempts = [raw, _quote_reserved_items(raw)]
    for body in _fenced_blocks(text):
        attempts.append(body)
        attempts.append(_quote_reserved_items(body))
    match = re.search(r"^(requirements|verdict):", raw, re.M)
    if match:
        attempts.append(_quote_reserved_items(raw[match.start():]))
    for candidate in attempts:
        try:
            data = yaml.safe_load(candidate)
        except yaml.YAMLError as exc:
            trouble = f"the reply is not YAML: {exc}"
            continue
        except Exception as exc:
            # a tag whose constructor fails raises outside YAMLError
            return None, f"the reply carries a YAML tag that cannot be read: {exc!r}"
        if isinstance(data, dict):
            return data, None
    if data is not None:
        return None, "the reply is not a YAML mapping"
    return None, trouble


def _clean_list(value, limit, what):
    items = value if isinstance(value, list) else ([] if value is None else [value])
    if len(items) > limit:
        return None, f"too many {what} ({len(items)} > {limit})"
    return items, None


CASE_NAME = re.compile(r"^case_[A-Za-z0-9_]+$")
SAFE_REL_PATH = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/\-]*$")


def _valid_rel_path(path):
    p = str(path).strip().replace("\\", "/")
    if not p or p.startswith("/") or ".." in p.split("/") or not SAFE_REL_PATH.match(p):
        return None
    return p


def parse_resolver_reply(text):
    """(spec, error). spec is the validated resolver output, sizes clamped."""
    data, trouble = _load_yaml(text)
    if trouble:
        return None, trouble
    spec = {}
    reqs, trouble = _clean_list(data.get("requirements"), MAX_REQUIREMENTS,
                                "requirements")
    if trouble:
        return None, trouble
    if not reqs:
        return None, "no requirements"
    seen_ids = set()
    spec["requirements"] = []
    for item in reqs:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            return None, "a requirement without text"
        rid = str(item.get("id") or "").strip() or f"R{len(spec['requirements']) + 1}"
        if rid in seen_ids:
            return None, f"duplicate requirement id {rid}"
        seen_ids.add(rid)
        kind = str(item.get("kind") or "behavioral").strip().lower()
        if kind not in REQUIREMENT_KINDS:
            return None, f"requirement {rid} has unknown kind `{kind}`"
        cases = [str(c).strip() for c in (item.get("cases") or []) if str(c).strip()]
        bad = [c for c in cases if not CASE_NAME.match(c)]
        if bad:
            return None, f"requirement {rid} names invalid case(s): {', '.join(bad)}"
        spec["requirements"].append({
            "id": rid,
            "text": " ".join(str(item["text"]).split()),
            "kind": kind,
            "evidence": [str(e).strip() for e in (item.get("evidence") or [])][:4],
            "cases": cases,
        })
    scope_items, trouble = _clean_list(data.get("scope"), MAX_SCOPE, "scope entries")
    if trouble:
        return None, trouble
    spec["scope"] = []
    for item in scope_items:
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict):
            return None, "a scope entry that is neither a path nor a mapping"
        path = _valid_rel_path(item.get("path"))
        if not path or path == ".":
            return None, f"scope entry `{item.get('path')}` is not a usable path"
        spec["scope"].append({"path": path,
                              "reason": " ".join(str(item.get("reason") or "").split()),
                              "new": bool(item.get("new"))})
    if not spec["scope"]:
        return None, "no scope"
    forbidden = []
    for item in (data.get("forbidden") or []):
        path = _valid_rel_path(item)
        if path:
            forbidden.append(path)
    spec["forbidden"] = forbidden[:MAX_SCOPE]
    constraints, trouble = _clean_list(data.get("constraints"), MAX_CONSTRAINTS,
                                       "constraints")
    if trouble:
        return None, trouble
    spec["constraints"] = []
    for item in constraints:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        spec["constraints"].append({
            "text": " ".join(str(item["text"]).split()),
            "requirement": str(item.get("requirement") or "").strip(),
        })
    policy = str(data.get("tests_policy") or "immutable").strip().lower()
    if policy not in ("immutable", "named", "authoring"):
        return None, f"unknown tests_policy `{policy}`"
    spec["tests_policy"] = policy
    editable = []
    for item in (data.get("tests_editable") or []):
        path = _valid_rel_path(item)
        if path:
            editable.append(path)
    spec["tests_editable"] = editable[:MAX_SCOPE]
    spec["regression"] = []
    for item in (data.get("regression") or [])[:4]:
        if isinstance(item, str):
            item = {"cmd": item}
        if isinstance(item, dict) and str(item.get("cmd") or "").strip():
            spec["regression"].append({
                "cmd": " ".join(str(item["cmd"]).split()),
                "reason": " ".join(str(item.get("reason") or "").split()),
            })
    probe = str(data.get("probe_file") or "")
    if not probe.strip():
        return None, "no probe_file"
    if len(probe.encode("utf-8")) > MAX_PROBE_BYTES:
        return None, "probe_file too large"
    spec["probe_file"] = probe
    questions, trouble = _clean_list(data.get("questions"), MAX_QUESTIONS, "questions")
    if trouble:
        return None, trouble
    spec["questions"] = []
    for item in questions:
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            continue
        options = [" ".join(str(o).split()) for o in (item.get("options") or [])
                   if str(o).strip()]
        spec["questions"].append({
            "id": str(item.get("id") or f"Q{len(spec['questions']) + 1}").strip(),
            "text": " ".join(str(item["text"]).split()),
            "options": options[:4],
            "default": " ".join(str(item.get("default") or "").split()),
        })
    spec["notes"] = " ".join(str(data.get("notes") or "").split())
    named_cases = {c for r in spec["requirements"] for c in r["cases"]}
    missing = [c for c in sorted(named_cases)
               if f"def {c}(" not in spec["probe_file"]]
    if missing:
        return None, "cases named but not defined in probe_file: " + ", ".join(missing)
    behavioral = [r for r in spec["requirements"] if r["kind"] == "behavioral"]
    if behavioral and not any(r["cases"] for r in behavioral):
        return None, "behavioral requirements but no behavioral probe cases"
    return spec, None


def parse_breaker_reply(text):
    """(result, error). result: {verdict, attempted, counterexample|None}."""
    data, trouble = _load_yaml(text)
    if trouble:
        return None, trouble
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in ("counterexample", "no_counterexample"):
        return None, f"unknown breaker verdict `{data.get('verdict')}`"
    attempted = [" ".join(str(a).split()) for a in (data.get("attempted") or [])
                 if str(a).strip()][:8]
    result = {"verdict": verdict, "attempted": attempted, "counterexample": None}
    if verdict == "no_counterexample":
        return result, None
    ce = data.get("counterexample")
    if not isinstance(ce, dict):
        return None, "verdict counterexample but no counterexample mapping"
    writes = ce.get("writes")
    if not isinstance(writes, dict) or not writes:
        return None, "a counterexample needs a non-empty write-set"
    if len(writes) > MAX_WRITE_FILES:
        return None, f"write-set too large ({len(writes)} files)"
    clean_writes = {}
    total = 0
    for path, content in writes.items():
        rel = _valid_rel_path(path)
        if not rel:
            return None, f"write-set path `{path}` is not a safe relative path"
        body = str(content if content is not None else "")
        total += len(body.encode("utf-8"))
        clean_writes[rel] = body
    if total > MAX_WRITE_BYTES:
        return None, "write-set too large"
    counter_probe = str(ce.get("counter_probe") or "")
    counter_case = str(ce.get("counter_case") or "").strip()
    if not counter_probe.strip() or not CASE_NAME.match(counter_case):
        return None, "a counterexample needs a counter_probe and a valid counter_case"
    if f"def {counter_case}(" not in counter_probe:
        return None, f"counter_case {counter_case} is not defined in counter_probe"
    if len(counter_probe.encode("utf-8")) > MAX_PROBE_BYTES:
        return None, "counter_probe too large"
    result["counterexample"] = {
        "description": " ".join(str(ce.get("description") or "").split()),
        "writes": clean_writes,
        "counter_probe": counter_probe,
        "counter_case": counter_case,
    }
    return result, None


def render_requirements(spec):
    lines = []
    for r in spec["requirements"]:
        cases = f" [cases: {', '.join(r['cases'])}]" if r["cases"] else ""
        lines.append(f"- {r['id']} ({r['kind']}): {r['text']}{cases}")
    return "\n".join(lines)


def render_oracle(acceptance_cmds):
    return "\n".join(f"- {cmd}" for cmd in acceptance_cmds) or "- (probe cases only)"


def render_spec_for_refine(spec):
    doc = {k: spec[k] for k in ("requirements", "scope", "forbidden", "constraints",
                                "tests_policy", "tests_editable", "regression",
                                "questions", "notes")}
    doc["probe_file"] = spec["probe_file"]
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100)
