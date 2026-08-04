#!/usr/bin/env python3
"""Scripted stand-in for the compiler's model roles.

Reads a role prompt on stdin, decides which role it is from the prompt's own
wording, and replies with canned YAML for the scenario named in FAKE_SCENARIO.
FAKE_STATE names a file used to count breaker invocations across the run, so a
scenario can be weak in round one and unbreakable in round two — the shape the
orchestrator's refinement loop exists to exercise.
"""
import os
import pathlib
import sys

PROBE_WEAK = '''\
import sys
sys.path.insert(0, '.')


def case_total_basic():
    from src import cart
    assert cart.total([1, 2]) == 3, 'total([1,2]) should be 3'


def main(argv):
    cases = {k: v for k, v in sorted(globals().items()) if k.startswith('case_')}
    names = argv[1:] or sorted(cases)
    code = 0
    for name in names:
        fn = cases.get(name)
        if fn is None:
            print('unknown case: ' + name)
            return 1
        try:
            fn()
            print(name + ': ok')
        except AssertionError as exc:
            print(name + ': FAIL ' + str(exc))
            code = 1
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv))
'''

PROBE_STRONG = PROBE_WEAK.replace(
    "def main(argv):",
    '''def case_total_general():
    from src import cart
    assert cart.total([2, 2]) == 4, 'total([2,2]) should be 4'
    assert cart.total([5]) == 5, 'total([5]) should be 5'


def case_total_empty():
    from src import cart
    assert cart.total([]) == 0, 'total([]) should be 0'


def main(argv):''')

COUNTER_PROBE = '''\
import sys
sys.path.insert(0, '.')


def case_total_not_special_cased():
    from src import cart
    assert cart.total([2, 2]) == 4, 'total([2,2]) should be 4'


if __name__ == '__main__':
    try:
        case_total_not_special_cased()
    except AssertionError as exc:
        print('FAIL ' + str(exc))
        sys.exit(1)
    print('ok')
'''

WRONG_CART = '''\
def add(items, item):
    return list(items) + [item]


def total(items):
    if list(items) == [1, 2]:
        return 3
    return sum(items) - 1
'''


def resolver_reply(probe, questions="[]", policy="immutable",
                   constraints="[]", editable="[]"):
    indented = "\n".join("  " + line for line in probe.splitlines())
    return f"""\
requirements:
  - id: R1
    text: total() returns the exact sum of its items for every list, including empty
    kind: behavioral
    evidence:
      - "src/cart.py:9 — sum(items) - 1"
      - "tests/test_total.py fails on HEAD"
    cases: [CASES]
scope:
  - path: src/cart.py
    reason: total() lives here
    new: false
forbidden: []
constraints: {constraints}
tests_policy: {policy}
tests_editable: {editable}
regression:
  - cmd: python -m unittest tests.test_cart
    reason: existing suite for the untouched add()
probe_file: |
{indented}
questions: {questions}
notes: sum semantics generalized from sibling behavior and the failing test.
"""


BREAK_REPLY = """\
verdict: counterexample
attempted:
  - special-case the probe's exact example list
  - keep the off-by-one for every other input
counterexample:
  description: total() special-cases [1, 2] and stays off by one elsewhere
  writes:
    src/cart.py: |
{wrong}
  counter_probe: |
{counter}
  counter_case: case_total_not_special_cased
"""

NO_BREAK_REPLY = """\
verdict: no_counterexample
attempted:
  - special-case the probed lists
  - off-by-one on empty input only
  - wrong sign on single-element lists
"""


def bump(name):
    state = pathlib.Path(os.environ.get("FAKE_STATE", ""))
    counts = {}
    if state.is_file():
        for line in state.read_text().splitlines():
            key, _, value = line.partition("=")
            counts[key] = int(value or 0)
    counts[name] = counts.get(name, 0) + 1
    state.write_text("".join(f"{k}={v}\n" for k, v in counts.items()))
    return counts[name]


def indent(text, pad):
    return "\n".join(pad + line for line in text.splitlines())


def main():
    prompt = sys.stdin.read()
    scenario = os.environ.get("FAKE_SCENARIO", "ready-after-strengthen")
    if "Breaker stage" in prompt:
        round_no = bump("breaker")
        declines = ("unbreakable-round-one", "one-question", "three-questions",
                    "relax-tests-policy", "stall-constraint")
        if scenario in declines or round_no > 1:
            sys.stdout.write(NO_BREAK_REPLY)
        elif scenario == "breaker-garbage":
            sys.stdout.write("this is not yaml: [")
        elif scenario == "breaker-uncaught":
            # claims a counterexample the oracle in fact catches: the write-set
            # leaves the bug in place, so the flip case still fails
            reply = BREAK_REPLY.format(
                wrong=indent("def add(items, item):\n    return list(items) "
                             "+ [item]\n\n\ndef total(items):\n    return "
                             "sum(items) - 1\n", "      "),
                counter=indent(COUNTER_PROBE, "    "))
            sys.stdout.write(reply)
        else:
            sys.stdout.write(BREAK_REPLY.format(
                wrong=indent(WRONG_CART, "      "),
                counter=indent(COUNTER_PROBE, "    ")))
        return 0
    if "continuing after an" in prompt and "adversarial round" in prompt:
        bump("refiner")
        if scenario == "refine-fails":
            sys.stdout.write("still not yaml {{{")
            return 0
        if scenario in ("vacuous-probe", "denied-probe"):
            # a refiner that cannot repair its probe: reply unchanged
            probe = (PROBE_WEAK.replace("assert cart.total([1, 2]) == 3",
                                        "assert cart.total([1, 2]) == 2")
                     if scenario == "vacuous-probe" else
                     PROBE_WEAK.replace("from src import cart",
                                        "import subprocess\n    from src "
                                        "import cart"))
            reply = resolver_reply(probe)
            reply = reply.replace("cases: [CASES]", "cases: [case_total_basic]")
            sys.stdout.write(reply)
            return 0
        reply = resolver_reply(PROBE_STRONG)
        reply = reply.replace(
            "cases: [CASES]",
            "cases: [case_total_basic, case_total_general, case_total_empty]")
        sys.stdout.write(reply)
        return 0
    bump("resolver")
    if scenario == "resolver-garbage":
        sys.stdout.write("no yaml here at all")
        return 0
    if scenario == "vacuous-probe":
        probe = PROBE_WEAK.replace(
            "assert cart.total([1, 2]) == 3",
            "assert cart.total([1, 2]) == 2")  # green on HEAD: observes the bug
        reply = resolver_reply(probe)
        reply = reply.replace("cases: [CASES]", "cases: [case_total_basic]")
        sys.stdout.write(reply)
        return 0
    if scenario == "one-question":
        reply = resolver_reply(
            PROBE_WEAK,
            questions=('[{id: Q1, text: "Should total() reject non-numeric '
                       'items or propagate the TypeError?", options: '
                       '["reject with ValueError", "propagate"], '
                       'default: propagate}]'))
    elif scenario == "three-questions":
        q = ('[{id: Q1, text: one, options: [a, b]}, '
             '{id: Q2, text: two, options: [a, b]}, '
             '{id: Q3, text: three, options: [a, b]}]')
        reply = resolver_reply(PROBE_WEAK, questions=q)
    elif scenario == "relax-tests-policy":
        reply = resolver_reply(PROBE_WEAK, policy="named",
                               editable="[tests/test_total.py]")
    elif scenario == "stall-constraint":
        reply = resolver_reply(
            PROBE_WEAK,
            constraints=('[{text: "wait for plan approval before editing '
                         'anything", requirement: R1}, '
                         '{text: "add() keeps returning a new list", '
                         'requirement: R1}]'))
    elif scenario == "denied-probe":
        probe = PROBE_WEAK.replace(
            "from src import cart",
            "import subprocess\n    from src import cart")
        reply = resolver_reply(probe)
    else:
        reply = resolver_reply(PROBE_WEAK)
    reply = reply.replace("cases: [CASES]", "cases: [case_total_basic]")
    sys.stdout.write(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
