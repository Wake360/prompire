#!/usr/bin/env python3
import argparse
import contextlib
import io
import json
import pathlib
import subprocess
import sys

from check_scope import active_brief, read_pointer, repo_root

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = {
    "baseline": "baseline.py",
    "lint": "lint_brief.py",
    "render": "render_brief.py",
    "scope": "check_scope.py",
    "acceptance": "verify_acceptance.py",
}
PROMPT_TARGETS = ("generic", "claude", "codex", "copilot")


def run_tool(name, *args):
    return subprocess.run(
        [sys.executable, str(HERE / TOOLS[name]), *map(str, args)],
        capture_output=True,
        text=True,
    )


def emit_process(result):
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def report_refusal(message, json_mode=False):
    if json_mode:
        print(json.dumps({"status": "refused", "message": message}, ensure_ascii=False))
    else:
        print(f"refused: {message}")
    return 2


def report_stage(stage, result, json_mode):
    if json_mode:
        print(json.dumps({"status": "failed", "stage": stage,
                          "exit_code": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr},
                         ensure_ascii=False))
        return result.returncode
    print(f"{stage} failed:", file=sys.stderr)
    return emit_process(result)


def report_prepared(brief, prompt, checklist, target, json_mode):
    next_command = f"prompire verify {brief}"
    if json_mode:
        print(json.dumps({"status": "prepared", "brief": str(brief),
                          "prompt": str(prompt), "checklist": str(checklist),
                          "target": target, "next": next_command}, ensure_ascii=False))
    else:
        print(f"prepared {brief}")
        print(f"prompt: {prompt}")
        print(f"checklist: {checklist}")
        print(next_command)
    return 0


def child_json(result):
    return json.loads(result.stdout)


def report_verification(scope, acceptance, json_mode):
    scope_data = child_json(scope)
    acceptance_data = child_json(acceptance)
    code = 1 if scope.returncode == 1 or acceptance.returncode == 1 else 0
    if json_mode:
        print(json.dumps({"scope": scope_data, "acceptance": acceptance_data},
                         ensure_ascii=False))
    else:
        print("scope:")
        print(scope.stdout, end="")
        print("acceptance:")
        print(acceptance.stdout, end="")
        if scope.stderr:
            print(scope.stderr, end="", file=sys.stderr)
        if acceptance.stderr:
            print(acceptance.stderr, end="", file=sys.stderr)
    return code


def prepare(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    brief = pathlib.Path(args.brief)
    root = repo_root(brief.resolve().parent)
    live = active_brief(root)
    if live:
        return report_refusal(
            f"`{live}` is already active; run `prompire close {live}` first",
            json_mode=args.json,
        )

    measured = run_tool("baseline", brief, "--write")
    if measured.returncode:
        return report_stage("baseline", measured, args.json)

    linted = run_tool("lint", brief, "--json")
    if linted.returncode:
        return report_stage("lint", linted, args.json)

    prompt = run_tool("render", brief, "--target", args.target)
    if prompt.returncode:
        return report_stage("render", prompt, args.json)

    checklist = run_tool("render", brief, "--target", "checklist")
    if checklist.returncode:
        return report_stage("render", checklist, args.json)

    prompt_path = brief.with_name(f"{brief.stem}.{args.target}.md")
    checklist_path = brief.with_name(f"{brief.stem}.checklist.md")
    try:
        prompt_path.write_text(prompt.stdout, encoding="utf-8")
        checklist_path.write_text(checklist.stdout, encoding="utf-8")
    except OSError as exc:
        return report_refusal(f"could not write artifacts: {exc}", args.json)

    armed = run_tool("scope", brief, "--activate")
    if armed.returncode:
        return report_stage("activate", armed, args.json)

    return report_prepared(
        brief=brief,
        prompt=prompt_path,
        checklist=checklist_path,
        target=args.target,
        json_mode=args.json,
    )


def verify(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    scope_args = [args.brief, "--strict", "--json"]
    if args.ack_disarms:
        scope_args += ["--ack-disarms", args.ack_disarms]
    scope = run_tool("scope", *scope_args)
    if scope.returncode == 2:
        return report_stage("scope", scope, args.json)

    acceptance = run_tool("acceptance", args.brief, "--json")
    if acceptance.returncode == 2:
        return report_stage("acceptance", acceptance, args.json)

    return report_verification(scope, acceptance, args.json)


def close(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra))
    return emit_process(run_tool("scope", args.brief, "--deactivate"))


def status(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    root = repo_root(pathlib.Path(args.brief).resolve().parent)
    live = active_brief(root)
    if not live:
        data = {"status": "inactive"}
    else:
        pointer = read_pointer(root)
        data = {"status": "repin" if pointer["repin"] else "active",
                "brief": live, "base": pointer["base_rev"]}
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    elif data["status"] == "inactive":
        print("inactive")
    else:
        print(f"{data['status']} {data['brief']} {data['base'] or '-'}")
    return 0


def passthrough(name):
    def handler(args, extra):
        return emit_process(run_tool(name, *extra))
    return handler


def build_parser():
    parser = argparse.ArgumentParser(prog="prompire")
    commands = parser.add_subparsers(dest="command", required=True)

    prepared = commands.add_parser("prepare")
    prepared.add_argument("brief")
    prepared.add_argument("--target", choices=PROMPT_TARGETS, default="generic")
    prepared.add_argument("--json", action="store_true")
    prepared.set_defaults(handler=prepare)

    verified = commands.add_parser("verify")
    verified.add_argument("brief")
    verified.add_argument("--ack-disarms")
    verified.add_argument("--json", action="store_true")
    verified.set_defaults(handler=verify)

    closed = commands.add_parser("close")
    closed.add_argument("brief")
    closed.set_defaults(handler=close)

    stated = commands.add_parser("status")
    stated.add_argument("brief")
    stated.add_argument("--json", action="store_true")
    stated.set_defaults(handler=status)

    for name in ("baseline", "lint", "render", "scope"):
        low = commands.add_parser(name)
        low.set_defaults(handler=passthrough(name))
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    return args.handler(args, extra)


def entrypoint():
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
