#!/usr/bin/env python3
"""Run every suite. Exit 0 only if all of them pass.

Run: python3 tests/run_all.py [--quiet]
"""
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
SUITES = (
    "battery.py",
    "e2e.py",
    "examples.py",
    "golden.py",
    "docs.py",
    "hook.py",
    "encoding.py",
    "verify.py",
    "bench.py",
    "cli.py",
    "runner.py",
    "package.py",
    "ci.py",
)
SUITE_TIMEOUT = 900


def _captured_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def run_suite(path, timeout):
    started = time.monotonic()
    try:
        result = subprocess.run([sys.executable, str(path)], capture_output=True,
                                text=True, encoding="utf-8", timeout=timeout)
        return {"returncode": result.returncode, "stdout": result.stdout,
                "stderr": result.stderr,
                "seconds": time.monotonic() - started, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": 1, "stdout": _captured_text(exc.stdout),
                "stderr": _captured_text(exc.stderr),
                "seconds": time.monotonic() - started, "timed_out": True}


def main(suites=SUITES, here=HERE, timeout=SUITE_TIMEOUT, argv=None):
    args = sys.argv if argv is None else argv
    quiet = "--quiet" in args
    results = []
    for suite in suites:
        result = run_suite(here / suite, timeout)
        results.append((suite, result))
        if not quiet or result["returncode"]:
            print(f"===== {suite} =====")
            if result["stdout"].strip():
                print(result["stdout"].rstrip())
            if result["stderr"].strip():
                print(result["stderr"].rstrip())
            if result["timed_out"]:
                print(f"timed out after {timeout:g}s")
    print("\n===== summary =====")
    for suite, result in results:
        mark = "pass" if result["returncode"] == 0 else "FAIL"
        suffix = " timeout" if result["timed_out"] else ""
        print(f"{mark}  {suite}  {result['seconds']:.1f}s{suffix}")
    return 1 if any(result["returncode"] for _, result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
