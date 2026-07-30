#!/usr/bin/env python3
"""Acceptance verifier integration tests. Run: python3 tests/verify.py."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL))

import fixtures  # noqa: E402
from verify_acceptance import main, verify  # noqa: E402


ENV = os.environ.copy()
CASES = (
    "green criterion remains green",
    "flip criterion passes after the fix",
    "failed criterion returns exit 1",
    "unsafe criterion is not executed",
    "unreadable brief returns exit 2",
    "before_after digest mismatch returns exit 1",
    "before_after missing digest returns exit 1",
)


def brief(repo, name, body):
    return fixtures.write(repo, f".prompire/{name}.yaml", body.lstrip())


def run_cli(path, *args):
    return subprocess.run([sys.executable, str(SKILL / "verify_acceptance.py"),
                           str(path), *args], capture_output=True, text=True,
                          encoding="utf-8", env=ENV)


def green_brief():
    return """
goal: Keep the cart add behavior unchanged.
scope: [src/cart.py]
acceptance:
  - cmd: python -m unittest -q tests.test_cart
    expect: exit 0
baseline:
  - cmd: python -m unittest -q tests.test_cart
    status: pass
    evidence: exit 0, 0 line(s) stdout, 0.0s
"""


# Break caught: treating a passing post-work command as a failed acceptance result.
def test_green_criterion_remains_green():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        repo = fixtures.build(pathlib.Path(tmp) / "repo")
        path = brief(repo, "green", green_brief())

        result = verify(str(path))
        cli = run_cli(path, "--json")

        assert result["passed"] == 1, result
        assert result["failed"] == 0, result
        assert result["results"][0]["status"] == "pass", result
        assert cli.returncode == 0, cli.stdout + cli.stderr
        assert json.loads(cli.stdout)["passed"] == 1, cli.stdout


# Break caught: ignoring a red baseline after the implementation makes its test pass.
def test_flip_criterion_passes_after_the_fix():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        repo = fixtures.build(pathlib.Path(tmp) / "repo")
        path = brief(repo, "flip", """
goal: Fix the cart total arithmetic.
scope: [src/cart.py]
acceptance:
  - cmd: python -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
baseline:
  - cmd: python -m unittest -q tests.test_total
    status: fail
    evidence: exit 1, 0 line(s) stdout, 0.0s
""")
        cart = repo / "src/cart.py"
        cart.write_text(cart.read_text(encoding="utf-8").replace(
            "return sum(items) - 1", "return sum(items)"), encoding="utf-8")

        result = verify(str(path))

        assert result["passed"] == 1, result
        assert result["results"][0]["transition"] == "flip", result
        assert result["results"][0]["status"] == "pass", result


# Break caught: returning success when a required acceptance command still fails.
def test_failed_criterion_returns_exit_1():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        repo = fixtures.build(pathlib.Path(tmp) / "repo")
        path = brief(repo, "failed", """
goal: Fix the cart total arithmetic.
scope: [src/cart.py]
acceptance:
  - cmd: python -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
baseline:
  - cmd: python -m unittest -q tests.test_total
    status: fail
    evidence: exit 1, 0 line(s) stdout, 0.0s
""")

        result = verify(str(path))
        cli = run_cli(path)

        assert result["failed"] == 1, result
        assert result["results"][0]["status"] == "fail", result
        assert cli.returncode == 1, cli.stdout + cli.stderr
        assert "FAIL" in cli.stdout, cli.stdout


# Break caught: running a criterion that baseline.classify() has refused as unsafe.
def test_unsafe_criterion_is_not_executed():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        repo = fixtures.build(pathlib.Path(tmp) / "repo")
        path = brief(repo, "unsafe", """
goal: Keep the fixture repository unchanged.
scope: [src/cart.py]
acceptance:
  - cmd: python -c "open('should-not-exist', 'w').write('x')"
    expect: exit 0
    requires: [writes-repo]
baseline:
  - cmd: python -c "open('should-not-exist', 'w').write('x')"
    status: not_runnable
    reason: "declared requires: writes-repo"
""")

        result = verify(str(path))

        assert result["not_run"] == 1, result
        assert result["results"][0]["status"] == "not_runnable", result
        assert not (repo / "should-not-exist").exists(), result


# Break caught: accepting a missing or unreadable brief as a normal failed verdict.
def test_unreadable_brief_returns_exit_2():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        missing = pathlib.Path(tmp) / "missing.yaml"
        invalid_utf8 = pathlib.Path(tmp) / "invalid-utf8.yaml"
        invalid_utf8.write_bytes(b"\xff")

        assert main(["verify_acceptance.py", str(missing)]) == 2
        cli = run_cli(missing)
        assert cli.returncode == 2, cli.stdout + cli.stderr
        cli = run_cli(invalid_utf8)
        assert cli.returncode == 2, cli.stdout + cli.stderr
        assert "Traceback" not in cli.stderr, cli.stderr
        json_results = (
            run_cli(missing, "--json"),
            run_cli(invalid_utf8, "--json"),
            subprocess.run(
                [sys.executable, str(SKILL / "verify_acceptance.py"), "--json"],
                capture_output=True, text=True, encoding="utf-8", env=ENV,
            ),
        )
        for result in json_results:
            assert result.returncode == 2, result.stdout + result.stderr
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as error:
                raise AssertionError(
                    f"--json error output is not one object: {result.stdout!r}"
                ) from error
            assert payload["status"] == "indeterminate", payload
            assert payload["error"], payload
            assert result.stderr == "", result.stderr


# Break caught: treating changed before/after output as valid when its digest changed.
def test_before_after_digest_mismatch_returns_exit_1():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        repo = fixtures.build(pathlib.Path(tmp) / "repo")
        path = brief(repo, "digest", """
goal: Preserve the generated output.
scope: [src/report.py]
acceptance:
  - cmd: python -c "print('changed')"
    expect: exit 0
    before_after: true
baseline:
  - cmd: python -c "print('changed')"
    status: pass
    evidence: exit 0, 1 line(s) stdout, 0.0s, sha256:2cf24dba5fb0
""")

        result = verify(str(path))
        cli = run_cli(path, "--json")

        row = result["results"][0]
        assert result["failed"] == 1, result
        assert row["expected_digest"] == "2cf24dba5fb0", row
        assert row["actual_digest"] != row["expected_digest"], row
        assert cli.returncode == 1, cli.stdout + cli.stderr
        payload = json.loads(cli.stdout)
        assert payload["results"][0]["expected_digest"] == "2cf24dba5fb0", payload
        assert payload["results"][0]["actual_digest"] != "2cf24dba5fb0", payload


def test_before_after_missing_digest_returns_exit_1():
    with tempfile.TemporaryDirectory(prefix="prompire-verify-") as tmp:
        repo = fixtures.build(pathlib.Path(tmp) / "repo")
        path = brief(repo, "missing-digest", """
goal: Preserve the generated output.
scope: [src/report.py]
acceptance:
  - cmd: python -c "print('stable')"
    expect: exit 0
    before_after: true
baseline:
  - cmd: python -c "print('stable')"
    status: pass
    evidence: exit 0, 1 line(s) stdout, 0.0s
""")

        result = verify(str(path))
        cli = run_cli(path, "--json")

        row = result["results"][0]
        assert result["failed"] == 1, result
        assert row["ok"] is False, row
        assert row["expected_digest"] is None, row
        assert "missing" in str(row["reason"]).lower(), row
        assert "digest" in str(row["reason"]).lower(), row
        assert cli.returncode == 1, cli.stdout + cli.stderr


def main_test():
    tests = (
        test_green_criterion_remains_green,
        test_flip_criterion_passes_after_the_fix,
        test_failed_criterion_returns_exit_1,
        test_unsafe_criterion_is_not_executed,
        test_unreadable_brief_returns_exit_2,
        test_before_after_digest_mismatch_returns_exit_1,
        test_before_after_missing_digest_returns_exit_1,
    )
    failures = []
    with tempfile.TemporaryDirectory(prefix="prompire-verify-tools-") as directory:
        tool_dir = pathlib.Path(directory)
        if os.name == "nt":
            (tool_dir / "python.cmd").write_text(
                f'@"{sys.executable}" %*\n', encoding="utf-8")
        else:
            (tool_dir / "python").symlink_to(sys.executable)
        ENV["PATH"] = str(tool_dir) + os.pathsep + ENV["PATH"]
        old_path = os.environ["PATH"]
        os.environ["PATH"] = ENV["PATH"]
        try:
            for name, test in zip(CASES, tests):
                try:
                    test()
                    print(f"PASS  {name}")
                except AssertionError as error:
                    failures.append((name, str(error)))
                    print(f"FAIL  {name}: {error}")
        finally:
            os.environ["PATH"] = old_path
    print(f"{len(tests) - len(failures)}/{len(tests)} verifier cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main_test())
