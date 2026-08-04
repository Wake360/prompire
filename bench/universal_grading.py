import json
import os
import pathlib
import subprocess
import sys

from universal_fixtures import run_visible_tests, write_files


HIDDEN_CHECKS = {
    "retries": r'''
from relay.client import PermanentError, TransientError, UploadClient

class Transport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
    def send(self, payload):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

t = Transport([TransientError("a"), TransientError("b"), "ok"])
assert UploadClient(t).upload("x") == "ok"
assert t.calls == 3
t = Transport([PermanentError("stop"), "wrong"])
try:
    UploadClient(t).upload("x")
except PermanentError:
    pass
else:
    raise AssertionError("permanent error was retried or swallowed")
assert t.calls == 1
t = Transport([TransientError("1"), TransientError("2"), TransientError("3"), "wrong"])
try:
    UploadClient(t).upload("x")
except TransientError:
    pass
else:
    raise AssertionError("retry limit was not enforced")
assert t.calls == 3
''',
    "idempotency": r'''
from relay.api import post_job
from relay.store import JobStore

store = JobStore()
first = post_job({"name": "a"}, {"Idempotency-Key": "same"}, store)
second = post_job({"name": "a"}, {"Idempotency-Key": "same"}, store)
third = post_job({"name": "b"}, {"Idempotency-Key": "other"}, store)
fourth = post_job({"name": "c"}, {}, store)
assert first["status"] == 201
assert second["status"] in (200, 201)
assert second["body"]["id"] == first["body"]["id"]
assert third["body"]["id"] != first["body"]["id"]
assert fourth["body"]["id"] != third["body"]["id"]
assert len(store.jobs) == 3
''',
    "uuids": r'''
import json
import pathlib
import tempfile
import uuid
from ledger.users import create_user, get_user, load_users

with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp) / "users.json"
    path.write_text(json.dumps([{"id": 7, "name": "old"}]), encoding="utf-8")
    user = create_user(path, "new")
    assert isinstance(user["id"], str)
    assert str(uuid.UUID(user["id"])) == user["id"]
    assert get_user(path, 7)["name"] == "old"
    assert get_user(path, user["id"])["name"] == "new"
    assert load_users(path)[0]["id"] == 7
''',
    "jsonl": r'''
import json
from ledger.events import export_events

events = [{"text": "žluťoučký", "value": None}, {"text": "line", "value": 2}]
assert json.loads(export_events(events)) == events
payload = export_events(events, format="jsonl")
lines = payload.splitlines()
assert len(lines) == 2
assert [json.loads(line) for line in lines] == events
''',
    "cli_json": r'''
import json
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "forge.cli", "users", "list", "--json"],
    capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stderr
assert result.stderr == ""
assert json.loads(result.stdout) == [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Lin"}]
table = subprocess.run(
    [sys.executable, "-m", "forge.cli", "users", "list"],
    capture_output=True, text=True, encoding="utf-8")
assert table.returncode == 0
assert "ID  NAME" in table.stdout and "Ada" in table.stdout
''',
    "startup": r'''
import os
import pathlib
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    marker = pathlib.Path(tmp) / "marker"
    env = dict(os.environ, FORGE_DISCOVERY_MARKER=str(marker))
    imported = subprocess.run(
        [sys.executable, "-c", "import forge.cli"], env=env,
        capture_output=True, text=True, encoding="utf-8")
    assert imported.returncode == 0, imported.stderr
    assert not marker.exists(), "ordinary import performed plugin discovery"
    plugins = subprocess.run(
        [sys.executable, "-m", "forge.cli", "plugins"], env=env,
        capture_output=True, text=True, encoding="utf-8")
    assert plugins.returncode == 0, plugins.stderr
    assert marker.exists()
    assert "core" in plugins.stdout
''',
    "health": r'''
from ops.config import DeployConfig
from ops.deploy import deploy

class Runner:
    def __init__(self): self.releases = []
    def rollout(self, release): self.releases.append(release)
class Response:
    def __init__(self, status): self.status = status

calls = []
statuses = iter([503, 503, 200])
def probe(url):
    calls.append(url)
    return Response(next(statuses))
runner = Runner()
config = DeployConfig("https://service.test/ready")
assert deploy("v2", runner, probe, config) is True
assert calls == [config.health_url] * 3
assert runner.releases == ["v2"]

calls.clear()
try:
    deploy("v3", Runner(), lambda url: (calls.append(url), Response(503))[1], config)
except Exception:
    pass
else:
    raise AssertionError("deployment succeeded after failed health checks")
assert calls == [config.health_url] * 3
''',
    "image_cli": r'''
import pathlib
import subprocess
import sys
import tempfile
from PIL import Image

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    source = tmp / "source.png"
    target = tmp / "target.webp"
    Image.new("RGB", (13, 7), "red").save(source)
    result = subprocess.run(
        [sys.executable, "-m", "image_tools.cli", str(source), str(target)],
        capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    with Image.open(target) as converted:
        assert converted.size == (13, 7)
        assert converted.format == "WEBP"
    source.write_text("not an image", encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, "-m", "image_tools.cli", str(source), str(target)],
        capture_output=True, text=True, encoding="utf-8")
    assert failed.returncode != 0
    assert failed.stderr.strip()
''',
    "csv": r'''
import csv
import io
from reporting.csv_export import export_csv

rows = [
    {"name": "Ada, Jr.", "note": "line 1\nline 2", "quote": 'say "hi"', "empty": None},
    {"name": "Lin", "note": "ok", "quote": "none", "empty": ""},
]
payload = export_csv(rows)
parsed = list(csv.DictReader(io.StringIO(payload)))
assert parsed == [
    {"name": "Ada, Jr.", "note": "line 1\nline 2", "quote": 'say "hi"', "empty": ""},
    {"name": "Lin", "note": "ok", "quote": "none", "empty": ""},
]
''',
    "rename_readme": r'''
from pathlib import Path

text = Path("README.md").read_text(encoding="utf-8")
assert "Foo" not in text
assert text.count("Bar") == 2
''',
    "rename_config": r'''
from pathlib import Path
import forge.config as config

text = Path("forge/config.py").read_text(encoding="utf-8")
assert "DEFAULT_WAIT" not in text
assert config.DEFAULT_TIMEOUT == 30
''',
}


GOLD_FILES = {
    "retries": {
        "relay/client.py": '''class TransientError(RuntimeError):
    pass


class PermanentError(RuntimeError):
    pass


class UploadClient:
    def __init__(self, transport):
        self.transport = transport

    def upload(self, payload):
        for attempt in range(3):
            try:
                return self.transport.send(payload)
            except TransientError:
                if attempt == 2:
                    raise
''',
    },
    "idempotency": {
        "relay/store.py": '''class JobStore:
    def __init__(self):
        self.jobs = []
        self.idempotent_jobs = {}

    def create(self, payload, idempotency_key=None):
        if idempotency_key is not None and idempotency_key in self.idempotent_jobs:
            return self.idempotent_jobs[idempotency_key]
        job = {"id": len(self.jobs) + 1, "payload": payload}
        self.jobs.append(job)
        if idempotency_key is not None:
            self.idempotent_jobs[idempotency_key] = job
        return job
''',
        "relay/api.py": '''def post_job(payload, headers, store):
    if not isinstance(payload, dict):
        return {"status": 400, "body": {"error": "invalid payload"}}
    key = headers.get("Idempotency-Key")
    job = store.create(payload, idempotency_key=key)
    return {"status": 201, "body": job}
''',
    },
    "uuids": {
        "ledger/users.py": '''import json
import uuid


def load_users(path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_users(path, users):
    path.write_text(json.dumps(users), encoding="utf-8")


def create_user(path, name):
    users = load_users(path)
    user = {"id": str(uuid.uuid4()), "name": name}
    users.append(user)
    save_users(path, users)
    return user


def get_user(path, identifier):
    return next((user for user in load_users(path) if user["id"] == identifier), None)
''',
    },
    "jsonl": {
        "ledger/events.py": '''import json


def export_events(events, format="json"):
    if format == "json":
        return json.dumps(events, ensure_ascii=False)
    if format == "jsonl":
        return "\\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    raise ValueError(f"unsupported format: {format}")
''',
    },
    "cli_json": {
        "forge/registry.py": '''import os
import pathlib
import time


def discover_plugins():
    time.sleep(0.15)
    marker = os.environ.get("FORGE_DISCOVERY_MARKER")
    if marker:
        pathlib.Path(marker).write_text("discovered", encoding="utf-8")
    return ["core", "audit"]
''',
        "forge/cli.py": '''import argparse
import json

from .registry import discover_plugins


USERS = [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Lin"}]


def build_parser():
    parser = argparse.ArgumentParser(prog="forge")
    commands = parser.add_subparsers(dest="command", required=True)
    users = commands.add_parser("users")
    listing = users.add_subparsers(dest="users_command", required=True).add_parser("list")
    listing.add_argument("--json", action="store_true")
    commands.add_parser("plugins")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "users":
        if args.json:
            print(json.dumps(USERS))
        else:
            print("ID  NAME")
            for user in USERS:
                print(f"{user['id']}   {user['name']}")
    else:
        for plugin in discover_plugins():
            print(plugin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    },
    "startup": {
        "forge/registry.py": '''import os
import pathlib
import time


def discover_plugins():
    time.sleep(0.15)
    marker = os.environ.get("FORGE_DISCOVERY_MARKER")
    if marker:
        pathlib.Path(marker).write_text("discovered", encoding="utf-8")
    return ["core", "audit"]
''',
        "forge/cli.py": '''import argparse

from .registry import discover_plugins


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
        for plugin in discover_plugins():
            print(plugin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    },
    "health": {
        "ops/deploy.py": '''from .health import is_healthy


def deploy(release, runner, probe, config):
    runner.rollout(release)
    for _ in range(3):
        if is_healthy(probe, config.health_url):
            return True
    raise RuntimeError("deployment health check failed")
''',
    },
    "image_cli": {
        "image_tools/cli.py": '''import argparse
import pathlib
import sys

from PIL import Image


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args(argv)
    try:
        with Image.open(args.input) as image:
            image.save(pathlib.Path(args.output))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    },
    "csv": {
        "reporting/csv_export.py": '''import csv
import io


def export_csv(rows):
    if not rows:
        return ""
    output = io.StringIO(newline="")
    columns = list(rows[0])
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
''',
    },
    "mobile_blind": {
        "web/dashboard.css": '''* { box-sizing: border-box; }
body { margin: 0; font: 16px system-ui; color: #1c2430; }
header { display: flex; justify-content: space-between; align-items: center; padding: 24px; }
nav { display: flex; gap: 20px; align-items: center; }
main { padding: 24px; }
.cards { display: grid; grid-template-columns: repeat(2, 240px); gap: 20px; }
.cards article { padding: 20px; border: 1px solid #ccd3dc; }
.chart { width: 900px; height: 220px; margin: 24px 0; background: #eef2f6; padding: 24px; word-spacing: 35px; }
table { width: 900px; border-collapse: collapse; }
th, td { padding: 12px; border-bottom: 1px solid #ccd3dc; text-align: left; }
@media (max-width: 600px) {
  header { align-items: flex-start; flex-direction: column; gap: 16px; padding: 16px; }
  nav { flex-wrap: wrap; gap: 12px; }
  main { padding: 16px; }
  .cards { grid-template-columns: 1fr; }
  .chart { width: 100%; overflow-x: auto; }
  table { min-width: 600px; }
  main { overflow-x: auto; }
}
''',
    },
    "rename_readme": {
        "README.md": '''# Bar

Bar is a small operator CLI. users list is used by scripts as well as humans.
Human diagnostics go to stderr; machine-readable modes write only their payload to
stdout. Plugin discovery is needed only by the plugins command and currently makes
ordinary startup slow.
''',
    },
    "rename_config": {"forge/config.py": "DEFAULT_TIMEOUT = 30\n"},
}


def _run_hidden(root, grader):
    if grader == "mobile_blind":
        html = (pathlib.Path(root) / "web/dashboard.html").read_text(encoding="utf-8")
        css = (pathlib.Path(root) / "web/dashboard.css").read_text(encoding="utf-8")
        checks = {
            "viewport": "width=device-width" in html,
            "responsive_rule": "@media" in css and "max-width" in css,
            "overflow_handling": "overflow" in css,
        }
        return all(checks.values()), json.dumps(checks, sort_keys=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(root))
    result = subprocess.run(
        [sys.executable, "-c", HIDDEN_CHECKS[grader]], cwd=root,
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
    details = (result.stdout + result.stderr).strip()
    return result.returncode == 0, details


def grade_repository(root, grader):
    visible = run_visible_tests(root)
    hidden_pass, hidden_details = _run_hidden(root, grader)
    return {
        "success": visible.returncode == 0 and hidden_pass,
        "visible_pass": visible.returncode == 0,
        "visible_output": (visible.stdout + visible.stderr).strip(),
        "hidden_pass": hidden_pass,
        "hidden_output": hidden_details,
    }


def apply_gold_solution(root, grader):
    write_files(root, GOLD_FILES[grader])
