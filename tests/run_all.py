#!/usr/bin/env python3
"""Run every suite. Exit 0 only if all of them pass.

Run: python3 tests/run_all.py [--quiet]
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SUITES = (
    "battery.py",
    "e2e.py",
    "examples.py",
    "golden.py",
    "docs.py",
    "hook.py",
    "verify.py",
    "cli.py",
    "package.py",
    "ci.py",
)


def main():
    quiet = "--quiet" in sys.argv
    results = []
    for s in SUITES:
        r = subprocess.run([sys.executable, str(HERE / s)], capture_output=True, text=True)
        results.append((s, r.returncode))
        if not quiet or r.returncode:
            print(f"===== {s} =====")
            print(r.stdout.rstrip())
            if r.stderr.strip():
                print(r.stderr.rstrip())
    print("\n===== summary =====")
    for s, rc in results:
        print(f"{'pass' if rc == 0 else 'FAIL'}  {s}")
    failed = [s for s, rc in results if rc]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
