"""The word `verified` was printed over a number that said otherwise (2026-08-20).

`Region 1: outline c83c78 verified across 144 frames (68% enclosed)` -- the number is honest
and the sentence is not, and an autonomous run reads the word. Separately, rocket and
satellite printed `verified across 177 frames (0% enclosed)`, which is two different fields
(`anomalous_frame_count` and `enclosure_ratio_all_frames`) reading as one claim.

⚠️ THE BAND EDGES ARE MEASURED, NOT CHOSEN. Over 269 verified-outline regions across five
populations, 168 (62.5%) sit at exactly 1.000, 6 at exactly 0.000, and the remaining 95 are
spread almost evenly between with no cluster to justify subdividing them. The mid band is
35% of all regions -- every one of which used to print "verified".

The unit tests below need no render at all; the two end-to-end ones invoke the real CLI.
"""
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, 'scripts', 'remove_gif_background.py')
TRIAL = os.path.join(ROOT, 'local', 'Corpus Trial Gifs')

_spec = importlib.util.spec_from_file_location('under_test_enc', SCRIPT)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _v(ratio, checked, enclosed):
    return R._enclosure_verdict(1, 'aabbcc', {
        'enclosure_ratio_all_frames': ratio, 'frames_checked': checked,
        'frames_enclosed': enclosed, 'anomalous_frame_count': 0})


def test_only_every_frame_earns_the_word_verified():
    assert 'VERIFIED' in _v(1.0, 124, 124)
    assert 'COIN FLIP' not in _v(1.0, 124, 124)


def test_the_mid_band_says_coin_flip_and_names_what_to_check():
    m = _v(0.68, 144, 98)
    assert 'COIN FLIP' in m and 'not verified' in m
    assert '98 of 144' in m, m
    assert 'CHECK:' in m, 'a coin-flip verdict that does not say what to check is just a hedge'


def test_a_near_miss_of_full_enclosure_is_still_the_mid_band():
    """0.99 is not 1.00. The distribution has a spike at exactly 1.000 and 11 regions in
    0.9-1.0; the strict reading puts those in the mid band, which is the point."""
    assert 'COIN FLIP' in _v(0.99, 100, 99)


def test_zero_enclosure_does_not_read_as_verified():
    m = _v(0.0, 177, 0)
    assert 'verified' not in m.lower() or 'NEVER' in m
    assert 'NEVER fully encloses' in m and '0 of 177' in m
    assert 'VERIFY THE OUTPUT' in m


def test_the_three_bands_are_actually_different():
    """A wording rule whose branches say the same thing is not a rule."""
    a, b, c = _v(1.0, 50, 50), _v(0.5, 50, 25), _v(0.0, 50, 0)
    assert len({a, b, c}) == 3


def _regions(asset):
    r = subprocess.run([sys.executable, SCRIPT, os.path.join(TRIAL, asset), '--recommend'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1200:]
    return [e for e in json.loads(r.stdout).get('evidence', []) if e.startswith('Region ')]


def test_for_you_gif_no_longer_claims_verified():
    """The filed case: 68% enclosure reported with the word 'verified'."""
    notes = _regions('for-you.gif')
    assert notes, 'no region evidence at all -- the fixture stopped exercising this path'
    assert any('COIN FLIP' in n for n in notes), notes
    assert not any('verified across' in n for n in notes), notes


def test_rocket_gif_no_longer_prints_the_contradiction():
    """`verified across 177 frames (0% enclosed)` -- two fields reading as one claim."""
    notes = _regions('rocket.gif')
    assert notes
    assert not any('verified across' in n and '(0% enclosed)' in n for n in notes), notes
    assert any('NEVER fully encloses' in n for n in notes), notes
