"""Hidden check for C03 (boltons OrderedMultiDict vs plain mapping equality).

Run from the repository root:  python3 hidden/C03-check.py
Exits 0 only if every hidden fact holds.
"""
import importlib.util
import sys

sys.path.insert(0, '.')

from boltons.dictutils import OrderedMultiDict as OMD

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


def load_standalone_urlutils():
    """Load boltons/urlutils.py as a top-level module.

    urlutils.py is published for single-file vendoring: its relative imports
    are guarded, so loaded outside the package it falls back to its own
    bundled OrderedMultiDict instead of the one in dictutils.
    """
    spec = importlib.util.spec_from_file_location(
        '_vendored_urlutils', 'boltons/urlutils.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if mod.OrderedMultiDict.__module__ != '_vendored_urlutils':
        raise RuntimeError('did not load the bundled OrderedMultiDict')
    return mod


# fact 1: a plain mapping with a different value is not equal
check('f1.differing-value', (OMD([('a', 1)]) == {'a': 2}) is False)
check('f1.differing-value-multi',
      (OMD([('a', 1), ('b', 2)]) == {'a': 1, 'b': 99}) is False)
check('f1.differing-value-dup-key',
      (OMD([('a', 1), ('a', 3)]) == {'a': 1}) is False)

# fact 2: an equal plain mapping is still equal, including values that are
# equal without being the same object
check('f2.equal-mapping', (OMD([('a', 1)]) == {'a': 1}) is True)
check('f2.equal-distinct-objects',
      (OMD([('a', [1, 2])]) == {'a': [1, 2]}) is True)
check('f2.equal-distinct-strings',
      (OMD([('k', ''.join('ab' * 40))]) == {'k': 'ab' * 40}) is True)
check('f2.equal-mapping-two-keys',
      (OMD([('a', 1), ('b', 2)]) == {'a': 1, 'b': 2}) is True)

# fact 3: a key the other mapping lacks is still unequal
check('f3.missing-key', (OMD([('a', 1)]) == {'b': 1}) is False)
check('f3.length-mismatch', (OMD([('a', 1)]) == {'a': 1, 'b': 2}) is False)

# fact 4: != agrees with ==
check('f4.ne-differing', (OMD([('a', 1)]) != {'a': 2}) is True)
check('f4.ne-equal', (OMD([('a', 1)]) != {'a': 1}) is False)

# fact 5: the OrderedMultiDict bundled inside urlutils.py, used when that file
# stands alone, compares values the same way -- as does QueryParamDict
vu = load_standalone_urlutils()
VOMD = vu.OrderedMultiDict
check('f5.vendored-differing-value', (VOMD([('a', 1)]) == {'a': 2}) is False)
check('f5.vendored-equal-mapping', (VOMD([('a', 1)]) == {'a': 1}) is True)
check('f5.vendored-equal-distinct-objects',
      (VOMD([('a', [1, 2])]) == {'a': [1, 2]}) is True)
check('f5.vendored-missing-key', (VOMD([('a', 1)]) == {'b': 1}) is False)
check('f5.vendored-ne', (VOMD([('a', 1)]) != {'a': 2}) is True)
check('f5.query-params-differing-value',
      (vu.URL('http://x/?a=1').query_params == {'a': '2'}) is False)
check('f5.query-params-equal',
      (vu.URL('http://x/?a=1').query_params == {'a': '1'}) is True)

if failures:
    print('FAIL: ' + ', '.join(failures))
    sys.exit(1)
print('OK')
sys.exit(0)
