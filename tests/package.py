import pathlib
import subprocess
import sys
import tempfile
import tomllib
import venv

ROOT = pathlib.Path(__file__).resolve().parent.parent
data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

assert data["project"]["requires-python"] == ">=3.11"
assert data["project"]["scripts"]["prompire"] == "prompire:entrypoint"
assert data["project"]["dependencies"] == ["PyYAML>=6"]

for cmd in (
    [sys.executable, str(ROOT / "prompire.py"), "--help"],
    [sys.executable, "-m", "prompire", "--help"],
):
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "prepare" in result.stdout
    assert "verify" in result.stdout

with tempfile.TemporaryDirectory() as tmp:
    env = pathlib.Path(tmp) / "venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env)
    scripts = env / ("Scripts" if sys.platform == "win32" else "bin")
    python = scripts / ("python.exe" if sys.platform == "win32" else "python")
    command = scripts / ("prompire.exe" if sys.platform == "win32" else "prompire")

    installed = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(ROOT)],
        capture_output=True,
        text=True, encoding="utf-8",
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    result = subprocess.run(
        [str(command), "--help"],
        cwd=tmp,
        capture_output=True,
        text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "prepare" in result.stdout
    assert "verify" in result.stdout
