"""Falsifiers for --auto guessing at a coin-flip protection decision (plan Task 10).

Measured 2026-08-22 on megaphone.gif: `--auto` printed
`applying: --protect-outline-color f0c850,002864`, protected the sparkle
interiors the user had explicitly asked to have REMOVED, and reported success.
Every region on that asset sat in the coin-flip band by the tool's own evidence
(2/144, 102/144) -- and an evidence string changes nothing for an autonomous
run, which reads flags.

⚠️ The tension with the autonomy goal is real and is NOT smoothed over. An
unattended run has nobody to ask, so the question is made answerable IN ADVANCE
-- `--assume-protect` / `--assume-remove` -- rather than dropped. A run that is
neither pre-answered nor willing to be asked stops.

The third test is the one that keeps this honest: a refusal that fires on
everything would pass the first two and make --auto useless.
"""
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
MEGAPHONE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

needs = pytest.mark.skipif(not (os.path.exists(MEGAPHONE) and os.path.exists(SECURE)),
                           reason='the trial inputs are gitignored third-party assets')


def _auto(src, out, *flags):
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--auto', *flags],
                       capture_output=True, text=True, timeout=3600)
    return r.returncode, r.stdout + r.stderr


@needs
def test_auto_refuses_on_a_coinflip_region_and_names_both_options(tmp_path):
    rc, out = _auto(MEGAPHONE, tmp_path / 'a.webp')
    assert rc != 0, '--auto proceeded on a coin-flip region'
    assert 'f0c850' in out, 'the refusal did not name the region in question'
    assert '--assume-remove' in out and '--assume-protect' in out, \
        'the refusal did not tell an unattended caller how to answer it'
    assert '2 of 144' in out, 'the refusal did not show the evidence it is refusing on'


@needs
def test_a_pre_answered_run_proceeds_and_drops_the_named_colour(tmp_path):
    out_path = tmp_path / 'b.webp'
    rc, out = _auto(MEGAPHONE, out_path, '--assume-remove', 'f0c850',
                    '--assume-protect', '002864')
    assert rc == 0 and out_path.exists(), out[-3000:]
    applied = re.search(r'applying:.*', out).group(0)
    assert 'f0c850' not in applied, f'the removed colour was still protected: {applied}'
    assert '002864' in applied, f'the protected colour was dropped too: {applied}'
    assert 'assumption applied' in out, \
        'a run that acted on an assumption did not say so'


@needs
def test_an_unambiguous_asset_is_NOT_made_to_ask(tmp_path):
    """secure.gif encloses on every frame -- 1.000, not a coin flip.

    Without this, the fix would be a refusal that fires on everything.
    """
    out_path = tmp_path / 'c.webp'
    rc, out = _auto(SECURE, out_path)
    assert rc == 0 and out_path.exists(), f'--auto refused an unambiguous asset: {out[-2000:]}'
    assert 'assumption applied' not in out


@needs
def test_a_partial_answer_still_refuses(tmp_path):
    """Every listed colour must be answered; answering one is not answering both."""
    rc, out = _auto(MEGAPHONE, tmp_path / 'd.webp', '--assume-remove', 'f0c850')
    assert rc != 0, 'a partially answered run proceeded'
    assert '002864' in out
