"""Hidden check for C01 (python-tabulate: github format alignment colons).

Run from the repository root:  python3 hidden/C01-check.py
Exit 0 = all hidden facts hold, exit 1 = at least one violated.
"""

import sys

sys.path.insert(0, ".")

from tabulate import tabulate  # noqa: E402

TABLE = [["spam", 42], ["eggs", 451], ["bacon", 0]]
HEADERS = ["item", "qty"]

failures = []


def segments(line):
    if not (line.startswith("|") and line.endswith("|")):
        raise AssertionError(f"not a table line: {line!r}")
    return line[1:-1].split("|")


def kind(seg):
    left = seg.startswith(":")
    right = seg.endswith(":")
    if left and right:
        return "center"
    if right:
        return "right"
    if left:
        return "left"
    return "none"


def kinds(line):
    return [kind(s) for s in segments(line)]


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: expected {want!r}, got {got!r}")


# F1: a numeric column is marked right-aligned in the separator row.
# F2: a text column is marked left-aligned in the separator row.
out = tabulate(TABLE, HEADERS, tablefmt="github").split("\n")
check("F1/F2 separator under header", kinds(out[1]), ["left", "right"])

# F3: explicit colalign values are honoured in the separator row.
out = tabulate(
    TABLE, HEADERS, tablefmt="github", colalign=("center", "left")
).split("\n")
check("F3 colalign center/left", kinds(out[1]), ["center", "left"])

out = tabulate(
    TABLE, HEADERS, tablefmt="github", colalign=("right", "center")
).split("\n")
check("F3 colalign right/center", kinds(out[1]), ["right", "center"])

# F4: with no headers the top border line carries the alignment colons too.
out = tabulate(TABLE, tablefmt="github").split("\n")
check("F4 headerless top line", kinds(out[0]), ["left", "right"])

# F5: github output is identical to pipe output for the same input.
cases = [
    dict(tabular_data=TABLE, headers=HEADERS),
    dict(tabular_data=TABLE),
    dict(tabular_data=TABLE, headers=HEADERS, colalign=("center", "left")),
    dict(tabular_data=[["a", 1.5], ["bb", 22.25]], headers=["x", "y"]),
    dict(tabular_data=[[]], headers=[]),
]
for i, kw in enumerate(cases):
    gh = tabulate(tablefmt="github", **kw)
    pipe = tabulate(tablefmt="pipe", **kw)
    if gh != pipe:
        failures.append(f"F5 case {i}: github output differs from pipe\n{gh!r}\n{pipe!r}")

if failures:
    for f in failures:
        print("FAIL", f)
    sys.exit(1)

print("OK: all hidden facts hold")
sys.exit(0)
