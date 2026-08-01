#!/usr/bin/env python3
import contextlib
import io
import pathlib
import tempfile

import run_all


def main():
    with tempfile.TemporaryDirectory(prefix="prompire-runner-") as tmp:
        root = pathlib.Path(tmp)
        (root / "slow.py").write_text(
            "import time\nprint('started', flush=True)\ntime.sleep(10)\n",
            encoding="utf-8")
        sentinel = root / "fast-ran"
        (root / "fast.py").write_text(
            "import pathlib\n"
            f"pathlib.Path({str(sentinel)!r}).write_text('yes')\n",
            encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_all.main(suites=("slow.py", "fast.py"), here=root,
                                timeout=0.1, argv=["--quiet"])
        text = output.getvalue()
        assert code == 1, text
        assert sentinel.read_text() == "yes"
        assert "FAIL  slow.py" in text and "timeout" in text
        assert "pass  fast.py" in text
        assert "s" in next(line for line in text.splitlines() if "fast.py" in line)
    print("3/3 runner cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
