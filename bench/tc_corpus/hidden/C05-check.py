"""Hidden check for C05 (tomlkit): comma-first array insertion must not double separators.

Run from the repository root:  python3 hidden/C05-check.py
Exit 0 when every hidden fact holds, 1 otherwise.
"""

import sys


sys.path.insert(0, ".")

from tomlkit import parse  # noqa: E402


COMMA_FIRST = """a = [
      1 # one
     ,2
    ]
"""

COMMA_LAST = """a = [
    1,
    2,
]
"""

failures = []


def check(name, source, mutate, expected):
    doc = parse(source)
    mutate(doc["a"])
    rendered = doc.as_string()
    try:
        reparsed = parse(rendered)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{name}: rendered array does not re-parse ({exc!r}): {rendered!r}")
        return
    if list(reparsed["a"]) != expected:
        failures.append(f"{name}: expected {expected}, got {list(reparsed['a'])}: {rendered!r}")
        return
    if reparsed.as_string() != rendered:
        failures.append(f"{name}: does not round-trip: {rendered!r}")


# Fact 1: appending to a comma-first array keeps the output parseable.
check("comma-first append", COMMA_FIRST, lambda a: a.append(99), [1, 2, 99])

# Fact 2: inserting at a middle index into a comma-first array does the same.
check("comma-first middle insert", COMMA_FIRST, lambda a: a.insert(1, 99), [1, 99, 2])

# Fact 3: inserting at the front copies a comma-less indent and must keep its
# own trailing separator.
check("comma-first front insert", COMMA_FIRST, lambda a: a.insert(0, 0), [0, 1, 2])

# Fact 3b: the two inserts compose on the same array.
doc = parse(COMMA_FIRST)
doc["a"].insert(1, 99)
doc["a"].insert(0, 0)
rendered = doc.as_string()
try:
    if list(parse(rendered)["a"]) != [0, 1, 99, 2]:
        failures.append(f"comma-first compound insert: got {list(parse(rendered)['a'])}")
except Exception as exc:  # noqa: BLE001
    failures.append(f"comma-first compound insert: does not re-parse ({exc!r}): {rendered!r}")

# Fact 4: ordinary comma-last arrays are untouched by the fix.
check("comma-last append", COMMA_LAST, lambda a: a.append(99), [1, 2, 99])
check("comma-last middle insert", COMMA_LAST, lambda a: a.insert(1, 99), [1, 99, 2])
check("single-line insert", "a = [1, 2]\n", lambda a: a.insert(1, 99), [1, 99, 2])

if failures:
    for line in failures:
        print("FAIL:", line)
    sys.exit(1)

print("OK: all hidden facts hold")
sys.exit(0)
