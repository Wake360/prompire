"""Hidden check for C08 (sortedcontainers: update() tie ordering).

Run from the repository root:  python3 hidden/C08-check.py
Exits 0 only if every hidden fact holds.

Every assertion compares update() against the same values fed in one at a time
through add(), which is the reference ordering.
"""

import sys

sys.path.insert(0, ".")

from sortedcontainers import SortedKeyList, SortedList  # noqa: E402

failures = []


def check(label, condition):
    if not condition:
        failures.append(label)


def by_add(cls, existing, new, **kwargs):
    ref = cls(**kwargs)
    for val in existing:
        ref.add(val)
    for val in new:
        ref.add(val)
    return ref


modulo = lambda val: val % 10  # noqa: E731

# ---------------------------------------------------------------- fact 1
# SortedKeyList.update puts new values whose key ties with existing values
# after those existing values, exactly where add() would put them.
skl = SortedKeyList([10, 20], key=modulo)
skl.update([30, 40])
ref = by_add(SortedKeyList, [10, 20], [30, 40], key=modulo)
check("fact1: SortedKeyList.update order %r != add order %r" % (list(skl), list(ref)),
      list(skl) == list(ref))

skl = SortedKeyList([1, 11, 21], key=modulo)
skl.update([31, 41])
ref = by_add(SortedKeyList, [1, 11, 21], [31, 41], key=modulo)
check("fact1: SortedKeyList.update order (single key) %r != add order %r"
      % (list(skl), list(ref)), list(skl) == list(ref))

# ---------------------------------------------------------------- fact 2
# SortedList.update does the same for values that merely compare equal.
sl = SortedList([1.0, 2.0])
sl.update([1, 2])
ref = by_add(SortedList, [1.0, 2.0], [1, 2])
check("fact2: SortedList.update types %r != add types %r"
      % ([type(v).__name__ for v in sl], [type(v).__name__ for v in ref]),
      [type(v).__name__ for v in sl] == [type(v).__name__ for v in ref])

# ---------------------------------------------------------------- fact 3
# In-place addition shares the same code path and must agree.
skl = SortedKeyList([10, 20], key=modulo)
skl += [30, 40]
ref = by_add(SortedKeyList, [10, 20], [30, 40], key=modulo)
check("fact3: SortedKeyList += order %r != add order %r" % (list(skl), list(ref)),
      list(skl) == list(ref))

sl = SortedList([1.0, 2.0])
sl += [1, 2]
ref = by_add(SortedList, [1.0, 2.0], [1, 2])
check("fact3: SortedList += types %r != add types %r"
      % ([type(v).__name__ for v in sl], [type(v).__name__ for v in ref]),
      [type(v).__name__ for v in sl] == [type(v).__name__ for v in ref])

# ---------------------------------------------------------------- fact 4
# The ordering holds for a bulk update as well, not only for a handful of
# values. sortedcontainers takes a different (rebuild) path once the incoming
# batch is large relative to the container.
existing = list(range(0, 600, 2))
new = list(range(1200))
skl = SortedKeyList(existing, key=modulo)
skl.update(new)
ref = by_add(SortedKeyList, existing, new, key=modulo)
check("fact4: SortedKeyList bulk update order differs from add order",
      list(skl) == list(ref))

existing_f = [float(val) for val in range(300)]
new_i = list(range(1500))
sl = SortedList(existing_f)
sl.update(new_i)
ref = by_add(SortedList, existing_f, new_i)
check("fact4: SortedList bulk update order differs from add order",
      [type(v).__name__ for v in sl] == [type(v).__name__ for v in ref])

# ---------------------------------------------------------------- fact 5
# Whatever path is taken, the container is still sorted and internally
# consistent afterwards.
try:
    skl._check()
    sl._check()
except Exception as exc:  # noqa: BLE001
    failures.append("fact5: _check() raised %s: %r" % (type(exc).__name__, exc))

check("fact5: bulk-updated SortedKeyList is not sorted by key",
      [modulo(v) for v in skl] == sorted(modulo(v) for v in skl))
check("fact5: bulk-updated SortedList is not sorted", list(sl) == sorted(sl))
check("fact5: bulk-updated SortedKeyList has the wrong length",
      len(skl) == len(existing) + len(new))

if failures:
    for f in failures:
        print("FAIL", f)
    sys.exit(1)

print("OK: all hidden facts hold")
sys.exit(0)
