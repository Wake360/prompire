"""Hidden check for C06 (tomlkit): unicode escapes must contain hex digits only.

Run from the repository root:  python3 hidden/C06-check.py
Exit 0 when every hidden fact holds, 1 otherwise.
"""

import sys


sys.path.insert(0, ".")

import tomlkit  # noqa: E402
from tomlkit.exceptions import InvalidUnicodeValueError  # noqa: E402


failures = []


def expect_rejected(content, label):
    try:
        value = tomlkit.parse(content)["a"]
    except InvalidUnicodeValueError:
        return
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{label}: raised {type(exc).__name__} instead of InvalidUnicodeValueError")
        return
    failures.append(f"{label}: accepted {content!r}, produced {value!r}")


def expect_value(content, expected, label):
    try:
        value = tomlkit.parse(content)["a"]
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{label}: {content!r} raised {type(exc).__name__}: {exc}")
        return
    if value != expected:
        failures.append(f"{label}: {content!r} produced {value!r}, expected {expected!r}")


# Fact 1: an underscore among the hex digits is rejected.
expect_rejected(r'a = "\u12_3"', "underscore in \\u")
expect_rejected(r'a = "\u1_23"', "underscore in \\u (other position)")

# Fact 2: whitespace among the digits is rejected (int() would strip it).
expect_rejected(r'a = "\u 123"', "space in \\u")

# Fact 3: a sign character is rejected (int() would honour it).
expect_rejected(r'a = "\u+123"', "plus in \\u")
expect_rejected(r'a = "\u-123"', "minus in \\u")

# Fact 4: the 8-digit \U form is checked the same way.
expect_rejected(r'a = "\U0010_FFFF"', "underscore in \\U")
expect_rejected(r'a = "\U0000_0041"', "underscore in \\U (leading zeros)")
expect_rejected(r'a = "\U    0041"', "spaces in \\U")
expect_rejected(r'a = "\U+0000041"', "plus in \\U")

ESC = 'a = "' + chr(92)  # a TOML basic string opening plus a backslash

# Fact 5: valid escapes still decode, in either digit case, and already-invalid
# input still fails through the parser's own error.
expect_value(ESC + 'u00e9"', 'é', 'lowercase hex \\u')
expect_value(ESC + 'u00E9"', 'é', 'uppercase hex \\u')
expect_value(r'a = "\U0001F600"', "\U0001f600", "uppercase hex \\U")
expect_value(r'a = "\U0001f600"', "\U0001f600", "lowercase hex \\U")
expect_value(r'a = "A\U00000042"', "AB", "adjacent escapes")
expect_rejected(r'a = "\u12g3"', "non-hex letter")
expect_rejected(r'a = "\ud800"', "surrogate \\u")
expect_rejected(r'a = "\U0000D800"', "surrogate \\U")

if failures:
    for line in failures:
        print("FAIL:", line)
    sys.exit(1)

print("OK: all hidden facts hold")
sys.exit(0)
