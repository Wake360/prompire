#!/usr/bin/env python3
"""Prompt variants under test. Each maps (brief, brief_path) -> prompt text.

`current` is whatever render_brief.py produces today — the control. Every other
entry is a hypothesis; the matrix in bench/report.py is what accepts or rejects
it. A variant that never beats `current` across the task set does not move into
the renderer.
"""
import pathlib
import sys

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from render_brief import render_prompt


def current(brief, brief_path):
    return render_prompt(brief, brief_path, "claude")


def persona(brief, brief_path):
    """The book-discouraged opener, kept here to be measured, not believed."""
    return "You are a meticulous senior engineer.\n\n" + current(brief, brief_path)


def bare(brief, brief_path):
    """The request as it would have arrived without Prompire — goal only, no
    boundary, no criteria, no autonomy. The control for whether the brief earns
    the tokens it costs: both variants are still measured from outside against
    the *author's* brief, so only what the agent was told differs."""
    return str(brief.get("goal") or "").strip() + "\n"


VARIANTS = {"current": current, "persona": persona, "bare": bare}
