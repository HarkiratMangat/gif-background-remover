"""Falsifiers for --verify reporting a vacuous pass (plan Task 4).

`--verify` skips every pixel check when the output canvas differs from the
source, so every `--crop`ped or `--resize-max-dim`ed deliverable verified
vacuously. Measured in the v6 trial 2026-08-22: all four initial `--verify` runs
did nothing, in 0.9-2.0s, and returned a document that reads like a pass. The
real checks (13.9s and 39.0s) only ran after re-rendering uncropped.

This is the project's own standing rule -- an unverifiable check reports
`unverified`, never a vacuous pass (`references/lessons.md` SS13/SS16/SS17) --
applied to the verifier itself.
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
                           reason='the trial inputs are gitignored third-party assets')


def _render(out, *flags):
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out),
                        '--protect-outline-color', '002864', *flags],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stderr[-3000:]


def _verify(out):
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out), '--verify'],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout[r.stdout.index('{'):]), r.stderr


@needs
def test_a_cropped_output_reports_that_it_was_not_verified(tmp_path):
    """A --crop'ped deliverable is the NORMAL case, and it verified vacuously."""
    out = tmp_path / 'c.webp'
    _render(out, '--crop')
    doc, err = _verify(out)
    assert doc['verified'] is False
    assert doc['checks_skipped'], 'skipped checks were not named'
    assert 'dimension' in ' '.join(doc['checks_skipped']).lower() \
        or 'differs from source' in ' '.join(doc['checks_skipped']).lower()
    assert 'did NOT check any pixels' in err, \
        'a console-only reader gets no signal that nothing was checked'


@needs
def test_a_same_size_output_still_reports_verified_true(tmp_path):
    """What STAYED: the fix must not mark a real verification as unverified.

    Without this half, `verified: false` everywhere would pass the first test and
    make the field meaningless.
    """
    out = tmp_path / 's.webp'
    _render(out)
    doc, err = _verify(out)
    assert doc['verified'] is True, f'a full verification was reported unverified: {doc.get("checks_skipped")}'
    assert not doc['checks_skipped']
    assert 'did NOT check any pixels' not in err
