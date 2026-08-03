import pathlib
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

assert data["project"]["requires-python"] == ">=3.11"
assert data["project"]["scripts"]["prompire"] == "prompire:entrypoint"
assert data["project"]["dependencies"] == ["PyYAML>=6"]

# Every host adapter in the tree ships in the package, or none should: a pip user
# reading references/hosts.md must never find that their host's adapter is the one
# the wheel left out. 0.9.0 shipped without hook_antigravity_guard exactly this way.
adapters = {p.stem for p in ROOT.glob("hook_*.py")}
shipped = set(data["tool"]["setuptools"]["py-modules"])
assert adapters <= shipped, f"adapters missing from py-modules: {adapters - shipped}"

# A PyPI page that cannot reach the repository strands the install docs.
urls = data["project"]["urls"]
for key in ("Homepage", "Repository", "Issues", "Documentation", "Changelog"):
    assert key in urls, f"[project.urls] missing {key}"
    assert urls[key].startswith("https://github.com/Wake360/prompire"), urls[key]

# The data-files table must ship exactly what the tree holds — the same rule
# the adapter check above enforces for py-modules: a reference or example
# added later must fail here, not silently stay out of the wheel.
data_files = data["tool"]["setuptools"]["data-files"]
assert data_files["share/prompire"] == ["SKILL.md"]
for target, source_dir, pattern in (
        ("share/prompire/references", "references", "*.md"),
        ("share/prompire/examples", "examples", "*.yaml"),
        ("share/prompire/examples/hooks", "examples/hooks", "*.json")):
    expected = sorted(
        p.relative_to(ROOT).as_posix() for p in (ROOT / source_dir).glob(pattern))
    assert sorted(data_files[target]) == expected, (target, expected)

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

    result = subprocess.run(
        [str(command), "--version"],
        cwd=tmp,
        capture_output=True,
        text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == data["project"]["version"], result.stdout

    for shipped in ("share/prompire/SKILL.md",
                    "share/prompire/references/threat-model.md",
                    "share/prompire/examples/worked-example.yaml"):
        assert (env / shipped).is_file(), f"installed venv is missing {shipped}"

with tempfile.TemporaryDirectory() as tmp:
    built = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", tmp,
         str(ROOT)],
        capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next(pathlib.Path(tmp).glob("prompire-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    prefix = f"prompire-{data['project']['version']}.data/data/"
    for target, files in data_files.items():
        for f in files:
            member = prefix + target + "/" + pathlib.PurePosixPath(f).name
            assert member in names, f"wheel is missing {member}"
