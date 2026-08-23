"""Falsifiers for sibling-format ranking (plan Task 2).

Measured on both v6 trial assets: the AVIF beat the WebP on resolution, frame
count AND size simultaneously -- megaphone AVIF 482x513/144/225.1 KB against
WebP 120x128/36/242.3 KB. The tool printed `2/2 succeeded.` and ranked neither,
so the user had two files and no basis for choosing.

Only STRICT DOMINATION is reported. That is a total, objective comparison with
no weighting and no taste in it, so the tool states a fact; a genuine tradeoff
is left alone. Harkirat's call 2026-08-23: rank and warn, write every file.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import remove_gif_background as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')


def _rec(src, out, w, h, frames, kb):
    return {'source': src, 'output': out, 'width': w, 'height': h,
            'frames': frames, 'kb': kb}


def _by_output(recs):
    return {r['output']: r for r in R.rank_sibling_outputs(recs)}


def test_strict_domination_is_reported_with_the_dominator_named():
    out = _by_output([_rec('m.gif', 'm.webp', 120, 128, 36, 242.3),
                      _rec('m.gif', 'm.avif', 482, 513, 144, 225.1)])
    assert out['m.webp']['dominated_by'] == 'm.avif'
    assert out['m.avif']['dominated_by'] is None
    assert 'every axis' in out['m.webp']['reason']


def test_a_genuine_tradeoff_is_NOT_called_domination():
    """What STAYED: smaller-but-fewer-frames is the user's call, not the tool's."""
    out = _by_output([_rec('m.gif', 'a.webp', 482, 513, 72, 100.0),
                      _rec('m.gif', 'b.avif', 482, 513, 144, 225.1)])
    assert out['a.webp']['dominated_by'] is None
    assert out['b.avif']['dominated_by'] is None


def test_outputs_of_DIFFERENT_sources_are_never_compared():
    recs = [_rec('a.gif', 'a.webp', 120, 128, 36, 242.3),
            _rec('b.gif', 'b.avif', 482, 513, 144, 225.1)]
    assert all(r['dominated_by'] is None for r in R.rank_sibling_outputs(recs))


def test_equal_on_every_axis_is_not_domination():
    recs = [_rec('m.gif', 'x.webp', 482, 513, 144, 225.1),
            _rec('m.gif', 'y.avif', 482, 513, 144, 225.1)]
    assert all(r['dominated_by'] is None for r in R.rank_sibling_outputs(recs))


def test_the_secure_case_from_the_trial():
    out = _by_output([_rec('s.gif', 's.webp', 524, 531, 17, 240.2),
                      _rec('s.gif', 's.avif', 524, 531, 50, 185.8)])
    assert out['s.webp']['dominated_by'] == 's.avif'


@pytest.mark.skipif(not os.path.exists(SECURE),
                    reason='the trial inputs are gitignored third-party assets')
def test_the_summary_records_are_measured_on_the_delivered_files(tmp_path):
    """End to end. The unit tests above would all pass on a ranker nothing calls, and
    on records carrying what was REQUESTED rather than what was written."""
    a = tmp_path / 's.webp'
    b = tmp_path / 's.avif'
    for out, extra in ((a, ['--resize-max-dim', '128']), (b, [])):
        r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out),
                            '--protect-outline-color', '002864', *extra],
                           capture_output=True, text=True, timeout=1800)
        assert r.returncode == 0, r.stderr[-3000:]
    recs = R._summary_records([
        {'status': 'ok', 'input': SECURE, 'output': str(a)},
        {'status': 'ok', 'input': SECURE, 'output': str(b)}])
    assert len(recs) == 2
    small = [r for r in recs if r['output'] == str(a)][0]
    assert max(small['width'], small['height']) == 128, \
        f'the record does not reflect the delivered file: {small}'
    ranked = _by_output(recs)
    assert ranked[str(a)]['dominated_by'] == str(b), \
        f'the 128px sibling was not flagged: {ranked}'
