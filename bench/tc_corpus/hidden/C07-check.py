"""Hidden check for C07 (parse: zero-precision float fields).

Run from the repository root:  python3 hidden/C07-check.py
Exits 0 only if every hidden fact holds.
"""

import sys
from decimal import Decimal

sys.path.insert(0, ".")

import parse  # noqa: E402

failures = []


def check(label, condition):
    if not condition:
        failures.append(label)


def call(fmt, string):
    """parse.parse, turning an internal blow-up into a checkable value."""
    try:
        return parse.parse(fmt, string)
    except Exception as exc:  # noqa: BLE001
        failures.append("raised %s: parse(%r, %r) -> %r" % (type(exc).__name__, fmt, string, exc))
        return None


# Fact 1: a zero-precision float field matches a number written with no
# decimal point, and yields a float.
r = call("{:.0f}", "20")
check("fact1: '{:.0f}' does not match '20'", r is not None)
if r is not None:
    check("fact1: '{:.0f}' on '20' is not float 20.0",
          type(r[0]) is float and r[0] == 20.0)

r = call("value is {:.0f}", "value is 7")
check("fact1: embedded '{:.0f}' does not match '7'", r is not None and r[0] == 7.0)

# Fact 2: the Decimal-producing sibling type behaves the same way.
r = call("{:.0F}", "20")
check("fact2: '{:.0F}' does not match '20'", r is not None)
if r is not None:
    check("fact2: '{:.0F}' on '20' is not Decimal('20')",
          isinstance(r[0], Decimal) and r[0] == Decimal("20"))

# Fact 3: negative numbers are matched too.
# (The Decimal type code carries a pre-existing, unrelated limitation: it is not
# in the numeric-sign list, so it never matches a leading sign. Not asserted.)
r = call("{:.0f}", "-20")
check("fact3: '{:.0f}' does not match '-20'", r is not None and r[0] == -20.0)

# Fact 4: every other precision, and no precision at all, still demands a
# decimal point.
check("fact4: '{:.2f}' wrongly matches '20'", call("{:.2f}", "20") is None)
check("fact4: '{:.2F}' wrongly matches '20'", call("{:.2F}", "20") is None)
check("fact4: '{:.1f}' wrongly matches '20'", call("{:.1f}", "20") is None)
check("fact4: '{:f}' wrongly matches '20'", call("{:f}", "20") is None)
check("fact4: '{:F}' wrongly matches '20'", call("{:F}", "20") is None)

# Fact 5: a zero-precision field composes with other fields in the same format
# string -- fields that follow it still line up with their own values.
r = call("{:.0f} {}", "20 x")
check("fact5: '{:.0f} {}' on '20 x' is not (20.0, 'x')",
      r is not None and list(r.fixed) == [20.0, "x"])
r = call("{:.0f} {:d}", "20 7")
check("fact5: '{:.0f} {:d}' on '20 7' is not (20.0, 7)",
      r is not None and list(r.fixed) == [20.0, 7])
r = call("{:.0F} {}", "20 x")
check("fact5: '{:.0F} {}' on '20 x' does not yield 'x' as the second field",
      r is not None and list(r.fixed) == [Decimal("20"), "x"])

# Guard: ordinary decimal parsing is untouched.
r = call("{:.2f}", "20.55")
check("guard: '{:.2f}' no longer matches '20.55'", r is not None and r[0] == 20.55)
r = call("{:f}", "-20.5")
check("guard: '{:f}' no longer matches '-20.5'", r is not None and r[0] == -20.5)

if failures:
    for f in failures:
        print("FAIL", f)
    sys.exit(1)

print("OK: all hidden facts hold")
sys.exit(0)
