#!/usr/bin/env python3
import json
import pathlib
import re
import sys

from baseline import classify, run_one
from brief_common import (
    BriefError,
    acceptance_entries,
    baseline_map,
    effective_transition,
    entry_key,
    load_brief,
    norm_cmd,
    utf8_stdio,
)
from check_scope import RepoError, repo_root

DIGEST = re.compile(r"\bsha256:([0-9a-f]{12})\b")


def expected_digest(entry):
    match = DIGEST.search(str((entry or {}).get("evidence") or ""))
    return match.group(1) if match else None


def verify(path: str) -> dict:
    brief = load_brief(path)
    root = repo_root(pathlib.Path(path).resolve().parent)
    before = baseline_map(brief)
    results = []

    for acceptance in acceptance_entries(brief):
        reason = classify(acceptance)
        current = ({"status": "not_runnable", "reason": reason}
                   if reason else run_one(root, acceptance))
        baseline = before.get(entry_key(acceptance))
        transition = effective_transition(acceptance, baseline)
        ok = current.get("status") == "pass"

        want_digest = expected_digest(baseline)
        got_digest = expected_digest(current)
        reason = current.get("reason")
        if acceptance.get("before_after"):
            if want_digest is None:
                ok = False
                reason = "before_after baseline is missing its expected sha256 digest"
            else:
                ok = ok and got_digest == want_digest

        results.append({
            "cmd": norm_cmd(acceptance.get("cmd")),
            "transition": transition,
            "status": current.get("status"),
            "ok": ok,
            "evidence": current.get("evidence"),
            "reason": reason,
            "expected_digest": want_digest,
            "actual_digest": got_digest,
        })

    return {
        "brief": str(path),
        "passed": sum(1 for result in results if result["ok"]),
        "failed": sum(1 for result in results
                      if not result["ok"] and result["status"] != "not_runnable"),
        "not_run": sum(1 for result in results
                       if result["status"] == "not_runnable"),
        "results": results,
    }


def report_error(message, json_mode):
    if json_mode:
        print(json.dumps({"status": "indeterminate", "error": message},
                         ensure_ascii=False))
    else:
        print(message)
    return 2


def main(argv: list[str]) -> int:
    # Every acceptance command is echoed back next to its PASS/FAIL, so a command line
    # naming a non-ASCII path or printing non-ASCII output reaches this stdout verbatim.
    utf8_stdio()
    json_mode = "--json" in argv
    args = [arg for arg in argv[1:] if not arg.startswith("--")]
    if not args:
        return report_error("usage: verify_acceptance.py brief.yaml [--json]", json_mode)
    try:
        result = verify(args[0])
    except (BriefError, RepoError, UnicodeDecodeError) as error:
        return report_error(str(error), json_mode)

    if json_mode:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for result_row in result["results"]:
            mark = "PASS" if result_row["ok"] else (
                "NOT RUN" if result_row["status"] == "not_runnable" else "FAIL")
            print(f"{mark} {result_row['cmd']}")

    return 0 if result["results"] and result["passed"] == len(result["results"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
