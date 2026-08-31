import sys

sys.path.insert(0, ".")

from tabulate import SEPARATING_LINE, tabulate  # noqa: E402

TABLE = [["spam", 41.9999], ["eggs", "451.0"]]
HEADERS = ["strings", "numbers"]


def _lines(*args, **kwargs):
    return tabulate(*args, **kwargs).splitlines()


def case_numeric_column_delimiter_is_right_aligned():
    delim = _lines(TABLE, HEADERS, tablefmt="github")[1]
    seg = delim.split("|")[2]
    assert seg.endswith(":") and not seg.startswith(":"), (
        f"numeric column delimiter should be '---:', got {seg!r} in {delim!r}"
    )


def case_string_column_delimiter_is_left_aligned():
    delim = _lines(TABLE, HEADERS, tablefmt="github")[1]
    seg = delim.split("|")[1]
    assert seg.startswith(":") and not seg.endswith(":"), (
        f"string column delimiter should be ':---', got {seg!r} in {delim!r}"
    )


def case_github_delimiter_matches_pipe():
    got = tabulate(TABLE, HEADERS, tablefmt="github")
    want = tabulate(TABLE, HEADERS, tablefmt="pipe")
    assert got == want, f"github must carry the same alignment colons as pipe:\n{got!r}\n{want!r}"


def case_headerless_delimiter_has_colons():
    first = _lines(TABLE, tablefmt="github")[0]
    assert first == "|:-----|---------:|", f"headerless github delimiter row: {first!r}"


def case_separating_line_has_colons():
    table = [["spam", 41.9999], SEPARATING_LINE, ["eggs", "451.0"]]
    got = tabulate(table, HEADERS, tablefmt="github")
    want = tabulate(table, HEADERS, tablefmt="pipe")
    assert got == want, f"github separating line must match pipe:\n{got!r}\n{want!r}"


def case_center_alignment_colons():
    delim = _lines([["a", 1]], ["x", "y"], tablefmt="github", colalign=("center", "left"))[1]
    left, right = delim.split("|")[1], delim.split("|")[2]
    assert left.startswith(":") and left.endswith(":"), f"center column: {left!r}"
    assert right.startswith(":") and not right.endswith(":"), f"left column: {right!r}"


def case_explicit_right_alignment_colons():
    delim = _lines([["a", "b"]], ["x", "y"], tablefmt="github", colglobalalign="right")[1]
    for seg in delim.split("|")[1:-1]:
        assert seg.endswith(":") and not seg.startswith(":"), f"right column: {seg!r}"


def case_negative_and_decimal_numbers_right_aligned():
    delim = _lines([["a", -1.5], ["b", -22.25]], ["x", "y"], tablefmt="github")[1]
    seg = delim.split("|")[2]
    assert seg.endswith(":") and not seg.startswith(":"), (
        f"decimal-aligned negative numbers need '---:', got {seg!r}"
    )


def case_numbers_as_text_stay_left():
    delim = _lines(
        [["spam", "1"], ["eggs", "2"]], ["s", "n"], tablefmt="github", disable_numparse=True
    )[1]
    for seg in delim.split("|")[1:-1]:
        assert seg.startswith(":") and not seg.endswith(":"), (
            f"non-numeric column must stay left-marked, got {seg!r}"
        )


def case_multiline_delimiter_has_colons():
    table = [[2, "foo\nbar"]]
    headers = ("more\nspam eggs", "more spam\n& eggs")
    delim = _lines(table, headers, tablefmt="github")[2]
    assert delim == "|------------:|:------------|", f"multiline github delimiter row: {delim!r}"


def case_delimiter_width_unchanged():
    lines = _lines(TABLE, HEADERS, tablefmt="github")
    for line in lines:
        assert len(line) == len(lines[0]), f"ragged row: {line!r} vs {lines[0]!r}"


def case_data_rows_still_visually_aligned():
    lines = _lines(TABLE, HEADERS, tablefmt="github")
    assert lines[0] == "| strings   |   numbers |", f"header row changed: {lines[0]!r}"
    assert lines[2] == "| spam      |   41.9999 |", f"data row changed: {lines[2]!r}"
    assert lines[3] == "| eggs      |  451      |", f"data row changed: {lines[3]!r}"


def case_empty_data_keeps_plain_delimiter():
    got = tabulate([], ["a", "b"], tablefmt="github")
    assert got == "| a   | b   |\n|-----|-----|", f"empty github table: {got!r}"


def case_empty_table_still_empty():
    got = tabulate([[]], [], tablefmt="github")
    assert got == "", f"fully empty github table: {got!r}"


def case_pipe_format_unchanged():
    got = tabulate(TABLE, HEADERS, tablefmt="pipe")
    want = "\n".join(
        [
            "| strings   |   numbers |",
            "|:----------|----------:|",
            "| spam      |   41.9999 |",
            "| eggs      |  451      |",
        ]
    )
    assert got == want, f"pipe output must not change:\n{got!r}"


def case_colon_grid_format_unchanged():
    got = tabulate(TABLE, HEADERS, tablefmt="colon_grid")
    want = "\n".join(
        [
            "+-----------+-----------+",
            "| strings   | numbers   |",
            "+:==========+:==========+",
            "| spam      | 41.9999   |",
            "+-----------+-----------+",
            "| eggs      | 451       |",
            "+-----------+-----------+",
        ]
    )
    assert got == want, f"colon_grid output must not change:\n{got!r}"


def case_orgtbl_format_unchanged():
    got = tabulate(TABLE, HEADERS, tablefmt="orgtbl")
    want = "\n".join(
        [
            "| strings   |   numbers |",
            "|-----------+-----------|",
            "| spam      |   41.9999 |",
            "| eggs      |  451      |",
        ]
    )
    assert got == want, f"orgtbl must stay colon-free:\n{got!r}"


CASES = {name: obj for name, obj in sorted(globals().items()) if name.startswith("case_")}


def main(argv):
    names = argv[1:] if len(argv) > 1 else list(CASES)
    failed = 0
    for name in names:
        fn = CASES.get(name)
        if fn is None:
            print(f"UNKNOWN {name}")
            failed += 1
            continue
        try:
            fn()
        except AssertionError as e:
            print(f"FAIL {name}: {e}")
            failed += 1
        else:
            print(f"ok   {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
