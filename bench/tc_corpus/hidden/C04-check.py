"""Hidden check for C04 (boltons IndexedSet out-of-range scalar indexing).

Run from the repository root:  python3 hidden/C04-check.py
Exits 0 only if every hidden fact holds.
"""
import sys

sys.path.insert(0, '.')

from boltons.setutils import IndexedSet

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


def raises_index_error(fn, message=None):
    try:
        fn()
    except IndexError as ie:
        return message is None or message in str(ie)
    except Exception:
        return False
    return False


def punched():
    """A 9-element IndexedSet carrying one dead slot."""
    iset = IndexedSet(range(10))
    iset.pop(2)
    return iset


# fact 1: a scalar index past either end raises instead of wrapping
s = IndexedSet(range(5))
check('f1.neg-past-end', raises_index_error(lambda: s[-6]))
check('f1.far-neg-past-end', raises_index_error(lambda: s[-10]))
check('f1.pos-past-end', raises_index_error(lambda: s[5]))
check('f1.empty', raises_index_error(lambda: IndexedSet()[0]))
check('f1.valid-neg', s[-1] == 4 and s[-5] == 0)
check('f1.valid-pos', s[0] == 0 and s[4] == 4)

# fact 2: pop() rejects an out-of-range index and removes nothing
p = IndexedSet(range(5))
check('f2.pop-neg-raises', raises_index_error(lambda: p.pop(-6)))
check('f2.pop-neg-no-removal', list(p) == [0, 1, 2, 3, 4])
q = punched()
check('f2.pop-neg-raises-with-dead', raises_index_error(lambda: q.pop(-15)))
check('f2.pop-neg-no-removal-with-dead', list(q) == [0, 1, 3, 4, 5, 6, 7, 8, 9])
check('f2.pop-valid-still-works', punched().pop(-2) == 8)

# fact 3: out of range reports IndexedSet's own message, from pop as well as
# from subscripting
check('f3.getitem-message',
      raises_index_error(lambda: IndexedSet(range(5))[7],
                         'IndexedSet index out of range'))
check('f3.pop-pos-message',
      raises_index_error(lambda: IndexedSet(range(5)).pop(7),
                         'IndexedSet index out of range'))
check('f3.pop-neg-message',
      raises_index_error(lambda: IndexedSet(range(5)).pop(-7),
                         'IndexedSet index out of range'))
check('f3.pop-pos-message-with-dead',
      raises_index_error(lambda: punched().pop(9),
                         'IndexedSet index out of range'))

# fact 4: the bounds are the apparent (post-removal) ones, not the length of
# the backing list
d = punched()
check('f4.neg-bound-with-dead', raises_index_error(lambda: d[-10]))
check('f4.pos-bound-with-dead', raises_index_error(lambda: d[9]))
check('f4.last-valid-neg-with-dead', d[-9] == 0)
check('f4.last-valid-pos-with-dead', d[8] == 9)
check('f4.pop-bound-with-dead', raises_index_error(lambda: punched().pop(9)))

# fact 5: every in-range index still agrees with the equivalent list, including
# across several dead intervals
multi = IndexedSet(range(100))
for victim in (5, 20, 40, 60, 80):
    multi.discard(victim)
ref = list(multi)
check('f5.dead-intervals-present', len(multi.dead_indices) == 5)
check('f5.agrees-with-list',
      all(multi[i] == ref[i] for i in range(-len(ref), len(ref))))
check('f5.neg-bound-multi', raises_index_error(lambda: multi[-len(ref) - 1]))
check('f5.pos-bound-multi', raises_index_error(lambda: multi[len(ref)]))

if failures:
    print('FAIL: ' + ', '.join(failures))
    sys.exit(1)
print('OK')
sys.exit(0)
