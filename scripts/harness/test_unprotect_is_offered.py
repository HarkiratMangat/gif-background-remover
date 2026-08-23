"""--recommend must OFFER --unprotect-region on an ambiguous enclosed interior.

The gap: every protection mechanism classifies an enclosed background-coloured
region as design, and the recommender only ever offered to PROTECT one. A user
who wanted such an interior removed had no path, and --auto could not reach the
answer at all. Measured 2026-08-22 -- see references/lessons.md SS43.

⚠️ The third test is the one that keeps this honest. A hint emitted on every
asset is noise, not guidance, and would pass the first two.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
BROADCAST = os.path.join(ROOT, 'local/2026-08-22-fade-edge-cases/inputs/broadcast.gif')
MEGAPHONE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')


def _evidence(path):
    """Whole --recommend output as text.

    Deliberately NOT json.loads: a single-input run does not emit the list a
    multi-input run does, and a parser that assumes one shape fails on the other
    -- which is how the first version of this test failed on all three assets
    while the feature was working correctly.
    """
    r = subprocess.run([sys.executable, SCRIPT, path, '--recommend'],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout + r.stderr


@pytest.mark.skipif(not os.path.exists(BROADCAST), reason='asset not in this checkout')
def test_broadcast_is_offered_the_counter_option_with_coordinates():
    ev = _evidence(BROADCAST)
    assert '--unprotect-region' in ev, 'no path offered for "this interior is background"'
    assert 'rect:' in ev, 'the hint has no ready-to-paste coordinates'


@pytest.mark.skipif(not os.path.exists(MEGAPHONE), reason='asset not in this checkout')
def test_megaphone_sparkles_are_offered_it_too():
    """--auto prints `applying: --protect-outline-color f0c850,002864` on this asset
    and keeps the sparkle interiors the user asked to remove."""
    assert '--unprotect-region' in _evidence(MEGAPHONE)


@pytest.mark.skipif(not os.path.exists(SECURE), reason='asset not in this checkout')
def test_an_unambiguous_asset_is_NOT_cluttered_with_it():
    """secure.gif encloses 50/50 on both regions -- 1.000, not in doubt.
    A hint here would mean the hint fires on everything and means nothing."""
    assert '--unprotect-region' not in _evidence(SECURE)
