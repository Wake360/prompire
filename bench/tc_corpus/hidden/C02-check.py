"""Hidden check for C02 (python-tabulate: trailing whitespace in asciidoc output).

Run from the repository root:  python3 hidden/C02-check.py
Exit 0 = all hidden facts hold, exit 1 = at least one violated.
"""

import sys

sys.path.insert(0, ".")

from tabulate import tabulate  # noqa: E402

NUM_LAST = ([["spam", 42], ["eggs", 451]], ["item", "qty"])
TEXT_LAST = ([[42, "spam"], [451, "eggs"]], ["qty", "item"])

failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}:\n  expected {want!r}\n  got      {got!r}")


def no_trailing_ws(name, text):
    for i, line in enumerate(text.split("\n")):
        if line != line.rstrip():
            failures.append(f"{name}: line {i} ends with whitespace: {line!r}")


# F1: data lines carry no trailing whitespace.
# F2: the header line carries no trailing whitespace either.
# F3: the padding inside the line is untouched (cells keep their one-space
#     padding and stay aligned to the full column width).
check(
    "F1/F2/F3 headers, numeric last column",
    tabulate(NUM_LAST[0], NUM_LAST[1], tablefmt="asciidoc"),
    '[cols="<8,>7",options="header"]\n|====\n'
    "| item   |   qty\n| spam   |    42\n| eggs   |   451\n|====",
)

# F4: also holds when the last column is left-aligned text, not just numbers.
check(
    "F3/F4 headers, text last column",
    tabulate(TEXT_LAST[0], TEXT_LAST[1], tablefmt="asciidoc"),
    '[cols=">7,<8",options="header"]\n|====\n'
    "|   qty | item\n|    42 | spam\n|   451 | eggs\n|====",
)

# F5: also holds for headerless tables.
check(
    "F3/F5 headerless",
    tabulate(NUM_LAST[0], tablefmt="asciidoc"),
    '[cols="<6,>5"]\n|====\n| spam |  42\n| eggs | 451\n|====',
)

# Sweep: no line of any asciidoc table may end with whitespace.
sweep = [
    ("num last, headers", dict(tabular_data=NUM_LAST[0], headers=NUM_LAST[1])),
    ("text last, headers", dict(tabular_data=TEXT_LAST[0], headers=TEXT_LAST[1])),
    ("num last, headerless", dict(tabular_data=NUM_LAST[0])),
    ("text last, headerless", dict(tabular_data=TEXT_LAST[0])),
    (
        "centered last column",
        dict(
            tabular_data=NUM_LAST[0],
            headers=NUM_LAST[1],
            colalign=("center", "center"),
        ),
    ),
    (
        "ragged text column",
        dict(tabular_data=[["a", "xxxxxxxx"], ["bb", "y"]], headers=["k", "v"]),
    ),
]
for name, kwargs in sweep:
    no_trailing_ws(name, tabulate(tablefmt="asciidoc", **kwargs))

if failures:
    for f in failures:
        print("FAIL", f)
    sys.exit(1)

print("OK: all hidden facts hold")
sys.exit(0)
