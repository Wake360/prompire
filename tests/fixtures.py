#!/usr/bin/env python3
"""Build a throwaway git repo the end-to-end tests and the examples measure against.

Everything here runs on the standard library: `python3 -m unittest` is a real test
runner, so B7 fires on it exactly as it would on pytest, and the fixtures need no
installed packages to reproduce.

The repo it builds, on HEAD:
  src/cart.py            add() and total(); total() has an off-by-one
  src/report.py          renders a report; golden/report.txt is its current output
  tests/test_cart.py     passes
  tests/test_total.py    FAILS — the off-by-one; a `flip` criterion
  tests/test_legacy.py   FAILS — known-red, nobody is fixing it; a `hold` criterion
  services/api/          a second package with its own tests, for the monorepo case
"""
import os
import pathlib
import subprocess
import sys

FILES = {
    "src/__init__.py": "",
    "src/cart.py": '''"""A tiny cart. total() is off by one on purpose."""


def add(items, item):
    return list(items) + [item]


def total(items):
    return sum(items) - 1
''',
    "src/report.py": '''"""Deterministic report rendering — golden/report.txt is its output."""
import sys


def render(rows):
    return "\\n".join(f"{name}: {n}" for name, n in rows)


if __name__ == "__main__":
    sys.stdout.write(render([("apples", 3), ("pears", 5)]) + "\\n")
''',
    "tests/__init__.py": "",
    "tests/test_cart.py": '''import unittest

from src.cart import add


class TestAdd(unittest.TestCase):
    def test_add_appends(self):
        self.assertEqual(add([1], 2), [1, 2])
''',
    "tests/test_total.py": '''import unittest

from src.cart import total


class TestTotal(unittest.TestCase):
    def test_total_sums(self):
        self.assertEqual(total([1, 2, 3]), 6)
''',
    "tests/test_legacy.py": '''import unittest


class TestLegacy(unittest.TestCase):
    """Known-red since the 2019 import. Nobody is fixing it this quarter."""

    def test_legacy_encoding(self):
        self.assertEqual("cafe\\u0301", "caf\\u00e9")
''',
    "golden/report.txt": "apples: 3\npears: 5\n",
    "services/api/__init__.py": "",
    "services/api/handler.py": '''def status():
    return {"ok": True}
''',
    "services/api/tests/__init__.py": "",
    # imported as `api.…`, so this suite only runs with cwd=services — that is the
    # monorepo case the schema's `cwd` exists for
    "services/api/tests/test_handler.py": '''import unittest

from api.handler import status


class TestStatus(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(status()["ok"])
''',
    "services/__init__.py": "",
    ".gitignore": ".prompire/\n__pycache__/\n",
    "README.md": "Fixture repo for Prompire end-to-end tests.\n",
}


# Fixed authorship + dates, so the fixture commit hash is the same on every machine.
# The examples record it as `base_rev`, and a churning hash would make them look edited.
ENV = dict(os.environ, GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00",
           GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00",
           GIT_AUTHOR_NAME="prompire fixtures", GIT_COMMITTER_NAME="prompire fixtures",
           GIT_AUTHOR_EMAIL="fixture@example.invalid",
           GIT_COMMITTER_EMAIL="fixture@example.invalid")


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, env=ENV)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def build(dest):
    """Create the repo at `dest` and commit it. Returns the path."""
    root = pathlib.Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    for rel, body in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    git(root, "init", "-q")  # no -b: git 2.28 and older reject it
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "prompire fixtures")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture repo on HEAD")
    (root / ".prompire").mkdir(exist_ok=True)
    return root


def write(root, rel, body):
    p = pathlib.Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "/tmp/prompire-fixture"))
