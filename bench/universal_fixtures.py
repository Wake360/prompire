import json
import os
import pathlib
import subprocess
import sys


COMMON = {
    ".gitignore": "__pycache__/\n*.pyc\n.pytest_cache/\n",
}

PROJECTS = {
    "relay-service": {
        **COMMON,
        "README.md": """# Relay service

UploadClient sends upload payloads through the injected transport. Transient
transport failures are safe to retry for at most three total attempts. Permanent
validation failures are returned immediately.

post_job implements POST /jobs. API errors use an error object and callers may send
Idempotency-Key when job creation must be safe to repeat.
""",
        "relay/__init__.py": "",
        "relay/client.py": """class TransientError(RuntimeError):
    pass


class PermanentError(RuntimeError):
    pass


class UploadClient:
    def __init__(self, transport):
        self.transport = transport

    def upload(self, payload):
        return self.transport.send(payload)
""",
        "relay/store.py": """class JobStore:
    def __init__(self):
        self.jobs = []

    def create(self, payload):
        job = {"id": len(self.jobs) + 1, "payload": payload}
        self.jobs.append(job)
        return job
""",
        "relay/api.py": """def post_job(payload, headers, store):
    if not isinstance(payload, dict):
        return {"status": 400, "body": {"error": "invalid payload"}}
    job = store.create(payload)
    return {"status": 201, "body": job}
""",
        "tests/test_relay.py": """import unittest

from relay.api import post_job
from relay.client import UploadClient
from relay.store import JobStore


class Transport:
    def send(self, payload):
        return {"sent": payload}


class RelayTests(unittest.TestCase):
    def test_upload_success(self):
        self.assertEqual(UploadClient(Transport()).upload("x"), {"sent": "x"})

    def test_job_creation(self):
        result = post_job({"name": "x"}, {}, JobStore())
        self.assertEqual(result["status"], 201)


if __name__ == "__main__":
    unittest.main()
""",
    },
    "ledger-data": {
        **COMMON,
        "README.md": """# Ledger data tools

User records are persisted as JSON arrays. Files created by older releases contain
integer IDs and must remain readable during representation migrations.

The event converter currently emits one JSON array. New export formats must preserve
event order, Unicode text, null values, and the existing JSON output.
""",
        "ledger/__init__.py": "",
        "ledger/users.py": """import json


def load_users(path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_users(path, users):
    path.write_text(json.dumps(users), encoding="utf-8")


def create_user(path, name):
    users = load_users(path)
    identifier = max((user["id"] for user in users), default=0) + 1
    user = {"id": identifier, "name": name}
    users.append(user)
    save_users(path, users)
    return user


def get_user(path, identifier):
    return next((user for user in load_users(path) if user["id"] == identifier), None)
""",
        "ledger/events.py": """import json


def export_events(events, format="json"):
    if format != "json":
        raise ValueError(f"unsupported format: {format}")
    return json.dumps(events, ensure_ascii=False)
""",
        "tests/test_ledger.py": """import json
import pathlib
import tempfile
import unittest

from ledger.events import export_events
from ledger.users import create_user


class LedgerTests(unittest.TestCase):
    def test_create_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            user = create_user(pathlib.Path(tmp) / "users.json", "Ada")
            self.assertEqual(user["name"], "Ada")

    def test_json_export(self):
        self.assertEqual(json.loads(export_events([{"a": 1}])), [{"a": 1}])


if __name__ == "__main__":
    unittest.main()
""",
    },
    "forge-cli": {
        **COMMON,
        "README.md": """# Foo

Foo is a small operator CLI. users list is used by scripts as well as humans.
Human diagnostics go to stderr; machine-readable modes write only their payload to
stdout. Plugin discovery is needed only by the plugins command and currently makes
ordinary startup slow.
""",
        "forge/__init__.py": "",
        "forge/config.py": "DEFAULT_WAIT = 30\n",
        "forge/registry.py": """import os
import pathlib
import time


def discover_plugins():
    time.sleep(0.15)
    marker = os.environ.get("FORGE_DISCOVERY_MARKER")
    if marker:
        pathlib.Path(marker).write_text("discovered", encoding="utf-8")
    return ["core", "audit"]


PLUGINS = discover_plugins()
""",
        "forge/cli.py": """import argparse

from .registry import PLUGINS


USERS = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Lin"}]


def build_parser():
    parser = argparse.ArgumentParser(prog="forge")
    commands = parser.add_subparsers(dest="command", required=True)
    users = commands.add_parser("users")
    users.add_subparsers(dest="users_command", required=True).add_parser("list")
    commands.add_parser("plugins")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "users":
        print("ID  NAME")
        for user in USERS:
            print(f"{user['id']}   {user['name']}")
    else:
        for plugin in PLUGINS:
            print(plugin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
""",
        "tests/test_forge.py": """import contextlib
import io
import unittest

from forge.cli import main


class ForgeTests(unittest.TestCase):
    def test_users_table(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["users", "list"]), 0)
        self.assertIn("Ada", output.getvalue())


if __name__ == "__main__":
    unittest.main()
""",
    },
    "ops-kit": {
        **COMMON,
        "README.md": """# Ops kit

Deployments use DeployConfig.health_url as their service readiness endpoint.
The rollout is healthy only after a 200 response. The deployment runner should poll
the existing health probe up to three times and fail the deployment if it never passes.
""",
        "ops/__init__.py": "",
        "ops/config.py": """from dataclasses import dataclass


@dataclass(frozen=True)
class DeployConfig:
    health_url: str = "http://localhost:8080/healthz"
""",
        "ops/health.py": """def is_healthy(probe, url):
    response = probe(url)
    return response.status == 200
""",
        "ops/deploy.py": """def deploy(release, runner, probe, config):
    runner.rollout(release)
    return True
""",
        "tests/test_ops.py": """import unittest

from ops.config import DeployConfig
from ops.deploy import deploy


class Runner:
    def __init__(self):
        self.releases = []

    def rollout(self, release):
        self.releases.append(release)


class Response:
    status = 200


class OpsTests(unittest.TestCase):
    def test_rollout_runs(self):
        runner = Runner()
        self.assertTrue(deploy("v2", runner, lambda url: Response(), DeployConfig()))
        self.assertEqual(runner.releases, ["v2"])


if __name__ == "__main__":
    unittest.main()
""",
    },
    "reporting-ui": {
        **COMMON,
        "README.md": """# Reporting dashboard

The CSV exporter receives rows as dictionaries. Column order follows the first row,
and None is exported as an empty field. The dashboard supports desktop browsers and
must remain usable at a 360px mobile viewport without removing desktop information.
""",
        "reporting/__init__.py": "",
        "reporting/csv_export.py": """def export_csv(rows):
    if not rows:
        return ""
    columns = list(rows[0])
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join("" if row.get(key) is None else str(row.get(key))
                              for key in columns))
    return "\\n".join(lines) + "\\n"
""",
        "web/dashboard.html": """<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="dashboard.css">
</head>
<body>
  <header><h1>Revenue</h1><nav><a href="#month">Month</a><a href="#year">Year</a><button>Export report</button></nav></header>
  <main>
    <section class="cards"><article>$42k<br><small>Revenue</small></article><article>318<br><small>Orders</small></article></section>
    <section class="chart">Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec</section>
    <table><tr><th>Region</th><th>Owner</th><th>Revenue</th><th>Orders</th></tr><tr><td>Europe</td><td>Ada</td><td>$18k</td><td>92</td></tr></table>
  </main>
</body>
</html>
""",
        "web/dashboard.css": """* { box-sizing: border-box; }
body { margin: 0; font: 16px system-ui; color: #1c2430; }
header { display: flex; justify-content: space-between; align-items: center; padding: 24px; }
nav { display: flex; gap: 20px; align-items: center; }
main { padding: 24px; }
.cards { display: grid; grid-template-columns: repeat(2, 240px); gap: 20px; }
.cards article { padding: 20px; border: 1px solid #ccd3dc; }
.chart { width: 900px; height: 220px; margin: 24px 0; background: #eef2f6; padding: 24px; word-spacing: 35px; }
table { width: 900px; border-collapse: collapse; }
th, td { padding: 12px; border-bottom: 1px solid #ccd3dc; text-align: left; }
""",
        "tests/test_csv.py": """import unittest

from reporting.csv_export import export_csv


class CsvTests(unittest.TestCase):
    def test_basic_rows(self):
        self.assertEqual(export_csv([{"name": "Ada", "count": 2}]),
                         "name,count\\nAda,2\\n")


if __name__ == "__main__":
    unittest.main()
""",
    },
    "image-cli": {
        **COMMON,
        "README.md": """# Image tools

Create the first command as python -m image_tools.cli INPUT OUTPUT. It should use
Pillow, infer the output format from the output suffix, preserve dimensions, replace
existing output files, and report invalid input on stderr with a non-zero exit.
""",
        "pyproject.toml": """[project]
name = "image-tools"
version = "0.1.0"
dependencies = ["Pillow>=10"]
requires-python = ">=3.11"
""",
        "image_tools/__init__.py": "",
        "tests/__init__.py": "",
        "tests/test_project.py": """import unittest


class ProjectTests(unittest.TestCase):
    def test_package_exists(self):
        import image_tools
        self.assertIsNotNone(image_tools)


if __name__ == "__main__":
    unittest.main()
""",
    },
}

TASKS = (
    {"id": "U01", "request": "add retries", "project": "relay-service",
     "surface": "service", "specificity": "LOW", "grader": "retries",
     "expected_paths": ["relay/client.py"]},
    {"id": "U02", "request": "add an idempotency key to POST /jobs",
     "project": "relay-service", "surface": "api", "specificity": "MEDIUM",
     "grader": "idempotency", "expected_paths": ["relay/api.py", "relay/store.py"]},
    {"id": "U03", "request": "migrate users to UUIDs", "project": "ledger-data",
     "surface": "database", "specificity": "LOW", "grader": "uuids",
     "expected_paths": ["ledger/users.py"]},
    {"id": "U04", "request": "add JSONL export to the event converter",
     "project": "ledger-data", "surface": "data", "specificity": "MEDIUM",
     "grader": "jsonl", "expected_paths": ["ledger/events.py"]},
    {"id": "U05", "request": "add JSON output to the users list command",
     "project": "forge-cli", "surface": "cli", "specificity": "MEDIUM",
     "grader": "cli_json", "expected_paths": ["forge/cli.py"]},
    {"id": "U06", "request": "speed up startup", "project": "forge-cli",
     "surface": "performance", "specificity": "LOW", "grader": "startup",
     "expected_paths": ["forge/registry.py", "forge/cli.py", "forge/__init__.py"]},
    {"id": "U07", "request": "add deployment health checks", "project": "ops-kit",
     "surface": "automation", "specificity": "LOW", "grader": "health",
     "expected_paths": ["ops/deploy.py", "ops/health.py"]},
    {"id": "U08", "request": "build a small CLI for converting images",
     "project": "image-cli", "surface": "greenfield_cli", "specificity": "LOW",
     "grader": "image_cli", "expected_paths": ["image_tools/cli.py"]},
    {"id": "U09", "request": "fix CSV export", "project": "reporting-ui",
     "surface": "bugfix", "specificity": "LOW", "grader": "csv",
     "expected_paths": ["reporting/csv_export.py"]},
    {"id": "U10", "request": "make dashboard better on mobile",
     "project": "reporting-ui", "surface": "frontend", "specificity": "MEDIUM",
     "grader": "mobile_blind", "expected_paths": ["web/dashboard.html", "web/dashboard.css"]},
    {"id": "U11", "request": "rename Foo to Bar in README.md", "project": "forge-cli",
     "surface": "documentation", "specificity": "HIGH", "grader": "rename_readme",
     "expected_paths": ["README.md"]},
    {"id": "U12", "request": "rename DEFAULT_WAIT to DEFAULT_TIMEOUT in forge/config.py",
     "project": "forge-cli", "surface": "refactor", "specificity": "HIGH",
     "grader": "rename_config", "expected_paths": ["forge/config.py"]},
)


def task_by_id(task_id):
    return next(task for task in TASKS if task["id"] == task_id)


def write_files(root, files):
    root = pathlib.Path(root)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_repository(root, task_id):
    root = pathlib.Path(root)
    task = task_by_id(task_id)
    write_files(root, PROJECTS[task["project"]])
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run([
        "git", "-c", "user.name=Prompire Benchmark",
        "-c", "user.email=benchmark@prompire", "-c", "commit.gpgsign=false",
        "commit", "-qm", "seed benchmark project"], cwd=root, check=True)
    return root


def run_visible_tests(root):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(root))
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=root, capture_output=True, text=True, encoding="utf-8", env=env)


def changed_paths(root):
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=root,
        check=True, capture_output=True, text=True, encoding="utf-8")
    return [line for line in result.stdout.splitlines() if line]


def task_manifest():
    return json.loads(json.dumps(TASKS))
