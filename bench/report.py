#!/usr/bin/env python3
"""Aggregate a bench JSONL file into a task × (variant × agent) matrix.

Usage: python3 bench/report.py bench/results/run.jsonl
Exit 0 = rendered clean. Exit 2 = could not fully decide — either no readable
rows at all, or one or more cells mix more than one (prompt_sha, model,
prompire_rev) population. In the latter case the matrix still renders, with
the offending cells marked MIXED, so one contaminated cell does not blank the
other fifty-nine.

A run is SOLVED only when every acceptance criterion passed AND check_scope
exited 0. An agent that made the acceptance green by moving a frozen test shows
up as SCOPE, not ok — that split is the whole point of the benchmark. A run
that edited the brief or the pin is GAMED whatever else it scored: the harness
put both files back before measuring, so the numbers are honest, but a run that
tried to write its own criteria is not a run that solved the task, even if it
also crashed on the way out. A harness row that never got a repo (`error`) or a
rate-limited/crashed live CLI reads ERR — an empty diff there means the run
never happened, not that the prompt failed, and ERR rows are excluded from a
cell's attempted count so one crash cannot drag down the rate for runs that did
happen; a cell where every rep crashed prints as "no attempts", never a 0/0
rate. The per-arm footer line ("v×a: n/n runs solved") uses that same
denominator — every non-ERR row for that variant×agent, across every task —
so it never disagrees with the cell marks printed above it. Rows are never
deduplicated: repeats are the measurement, not noise. A cell run once keeps
its qualitative mark; a cell run repeatedly renders as its solved rate among
the rows that actually ran.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "prompire"))

from brief_common import utf8_stdio


def wilson_lo(k, n, z=1.96):
    """Lower bound of the 95% Wilson score interval. A cell that solved 5 of 5 is not
    a measurement of 1.0 — it is consistent with a true rate near 0.57, and printing
    "5/5" without this invites reading noise as certainty."""
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    radius = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max(0.0, (centre - radius) / d)


# Per live CLI, the field a completed run always reports: claude names the models
# that ran; codex and antigravity never report one, so their usage stands in. A row
# missing its signal is a run that never happened, not a prompt that failed.
LIVE_SIGNAL = {"claude": "model", "codex": "tokens_out", "antigravity": "tokens_out"}


def mark(row):
    """The single classifier: solved() is defined off this, not the other way round,
    so the two can never disagree about one row."""
    if row.get("error"):
        return "ERR"
    if row.get("tampered"):
        return "GAMED"
    # A rate-limited or crashed CLI leaves an untouched repo: acceptance is red and the
    # row would otherwise read FAIL, blaming the prompt for a run that never happened.
    signal = LIVE_SIGNAL.get(row.get("agent"))
    if signal and (row.get("agent_exit") or row.get(signal) is None):
        return "ERR"
    a = row.get("acceptance") or {}
    ok = (a.get("passed", 0) >= 1 and a.get("failed") == 0 and a.get("not_run") == 0
          and row.get("scope_exit") == 0)
    if ok:
        return "ok"
    if row.get("scope_exit") != 0:
        return "SCOPE"
    return "FAIL"


def solved(row):
    return mark(row) == "ok"


def cell_mark(cell):
    if len(cell) == 1:
        return mark(cell[0])
    modes = [mark(r) for r in cell]
    # An ERR row is a run that never happened — it has no place in either half of a
    # solved rate, so it is dropped from the denominator, not just the numerator.
    attempted = sum(1 for m in modes if m != "ERR")
    extra = "".join(f" {m[0]}{modes.count(m)}"
                    for m in ("SCOPE", "FAIL", "GAMED", "ERR") if m in modes)
    if attempted == 0:
        # Every rep crashed: 0/0 with a bound reads as a measured zero, not "nothing
        # ran". Say so in words instead of printing a rate that was never taken.
        return f"no attempts{extra}"
    n_ok = modes.count("ok")
    return f"{n_ok}/{attempted}≥{wilson_lo(n_ok, attempted):.2f}{extra}"


def main(argv):
    utf8_stdio()
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    lines = pathlib.Path(argv[1]).read_text(encoding="utf-8").splitlines()
    rows = [json.loads(l) for l in lines if l.strip()]
    if not rows:
        print(f"no rows in {argv[1]}")
        return 2
    cells = {}
    for r in rows:
        cells.setdefault((r["task"], r["variant"], r["agent"]), []).append(r)
    # An error row (bench/run.py's own except-block row) never reached run_agent, so it
    # carries no prompt_sha/model/prompire_rev — it has no population to belong to and
    # must not read as a second one beside a cell's honest rows.
    mixed = {key for key, cell in cells.items()
             if len({(r.get("prompt_sha"), r.get("model"), r.get("prompire_rev"))
                     for r in cell if not r.get("error")}) > 1}
    cols = sorted({(v, a) for _, v, a in cells})
    tasks = sorted({t for t, _, _ in cells})
    print("\t".join(["task"] + [f"{v}×{a}" for v, a in cols]))
    for t in tasks:
        row_out = []
        for v, a in cols:
            key = (t, v, a)
            if key not in cells:
                row_out.append("-")
            elif key in mixed:
                row_out.append("MIXED")
            else:
                row_out.append(cell_mark(cells[key]))
        print("\t".join([t] + row_out))
    print()
    for v, a in cols:
        # Same convention as cell_mark: ERR is a run that never happened, so it is
        # dropped from this denominator too — otherwise this line and the cell marks
        # above it both say "solved" while counting different things.
        runs = [r for (_, rv, ra), cell in cells.items() if (rv, ra) == (v, a)
                for r in cell if mark(r) != "ERR"]
        n_ok = sum(1 for r in runs if solved(r))
        secs = [r["seconds"] for r in runs
                if isinstance(r.get("seconds"), (int, float))]
        mean = f", mean {sum(secs) / len(secs):.1f}s" if secs else ""
        print(f"{v}×{a}: {n_ok}/{len(runs)} runs solved{mean}")
    if mixed:
        print()
        print("refusing to pool: these cells contain more than one "
              "(prompt_sha, model, prompire_rev) population:")
        for task, variant, agent in sorted(mixed):
            print(f"  {task} × {variant} × {agent}")
        print("A variant name is a label; only prompt_sha binds it to bytes. "
              "Split the file or re-run the arm.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
