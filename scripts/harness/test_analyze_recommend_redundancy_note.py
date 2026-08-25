"""A doc-only fix for the same recurring waste did not stop it recurring.

SKILL.md documented, after the 2026-08-19 trial, that --recommend's JSON already
embeds everything --analyze returns. The 2026-08-23 trial found three independent
fresh sessions still calling both on the same file, on all 10 assets -- the rule was
read once, apparently, and not retained across nine repeats of the same choice.

The fix moves the guarantee into the tool: --analyze now prints a one-line reminder
to stderr, at the exact moment the redundant call is made, rather than relying on a
paragraph read (or not) before the session ever touched the CLI.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

needs = pytest.mark.skipif(not os.path.exists(SECURE),
                            reason='the trial input is a gitignored third-party asset')


@needs
def test_analyze_standalone_prints_the_redundancy_note_to_stderr():
    r = subprocess.run([sys.executable, SCRIPT, SECURE, '--analyze'],
                        capture_output=True, text=True, timeout=120)
    assert '--recommend' in r.stderr and 'already embeds' in r.stderr, (
        "the redundancy note did not print -- an agent calling --analyze standalone "
        "gets no in-tool signal that --recommend would have returned this and more")


@needs
def test_the_note_does_not_land_in_stdout_and_corrupt_the_json():
    """The real falsifier. A note that leaks onto stdout breaks every caller that
    pipes --analyze's output straight into a JSON parser."""
    r = subprocess.run([sys.executable, SCRIPT, SECURE, '--analyze'],
                        capture_output=True, text=True, timeout=120)
    report = json.loads(r.stdout)  # raises if the note leaked into stdout
    assert 'detected_bg_color' in report


@needs
def test_recommend_standalone_does_not_print_the_note():
    """--recommend already IS the non-redundant call -- printing this note there
    would be nagging the correct usage instead of the wasteful one."""
    r = subprocess.run([sys.executable, SCRIPT, SECURE, '--recommend'],
                        capture_output=True, text=True, timeout=120)
    assert '--recommend' not in r.stderr or 'already embeds' not in r.stderr
