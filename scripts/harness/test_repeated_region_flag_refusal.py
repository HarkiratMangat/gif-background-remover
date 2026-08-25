"""A region/colour-list flag typed TWICE instead of joined silently drops every value
but the last -- argparse's default=None keeps only the final occurrence, with no
warning. Found auditing the fix for the identical pattern in recommend()'s own
suggestion logic (references/lessons.md SS46): recommend() could no longer produce a
repeated occurrence, but a human -- or an agent reasoning about flags directly rather
than pasting recommend()'s suggested_command -- typing the flag twice on the real CLI
hits the same landmine. `--protect-region`, `--fade-protect-region`,
`--fade-protect-colors`, `--remove-region`, `--unprotect-region` and
`--translucent-region` all document a joined multi-value syntax (';' or ',') and were
all equally exposed; not just the one flag the recommend() bug happened to touch.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

import pytest

needs = pytest.mark.skipif(not os.path.exists(SECURE),
                            reason='the trial input is a gitignored third-party asset')


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args],
                           capture_output=True, text=True, timeout=120)


@needs
def test_protect_region_repeated_is_refused_not_silently_overwritten():
    r = _run(SECURE, '/tmp/_unused_dup1.gif',
              '--protect-region', 'circle:1,2,3', '--protect-region', 'circle:4,5,6')
    assert r.returncode != 0
    assert 'was passed 2 times' in r.stderr
    assert "join the values with ';'" in r.stderr


@needs
def test_protect_outline_color_repeated_is_refused_with_comma_not_semicolon():
    r = _run(SECURE, '/tmp/_unused_dup2.gif',
              '--protect-outline-color', '111111', '--protect-outline-color', '222222')
    assert r.returncode != 0
    assert "join the values with ','" in r.stderr, (
        'the guidance must name the RIGHT separator for this flag -- outline colours '
        'join with a comma, region specs with a semicolon, and mixing them up in the '
        'error message would send someone toward a syntax that still fails')


@needs
def test_equals_form_is_also_caught():
    r = _run(SECURE, '/tmp/_unused_dup3.gif',
              '--protect-region=circle:1,2,3', '--protect-region=circle:4,5,6')
    assert r.returncode != 0
    assert 'was passed 2 times' in r.stderr


@needs
def test_a_single_occurrence_is_not_flagged():
    """The real falsifier: a guard that fires on everything would pass the tests
    above trivially. This must NOT error on ordinary, correct usage."""
    r = _run(SECURE, '/tmp/_unused_single.gif', '--protect-region', 'circle:1,2,3')
    assert 'was passed' not in r.stderr


@needs
def test_the_joined_multi_region_syntax_still_works_and_is_not_flagged():
    r = _run(SECURE, '/tmp/_unused_joined.gif',
              '--protect-region', 'circle:1,2,3;circle:4,5,6')
    assert 'was passed' not in r.stderr
    assert r.returncode == 0, r.stderr[-2000:]
