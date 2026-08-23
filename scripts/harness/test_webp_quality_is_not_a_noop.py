"""Falsifiers for --webp-quality being silently discarded (plan Task 6).

Measured in the claude.ai session of 2026-08-22: the same render at
`--webp-quality 70` and `--webp-quality 45` produced byte-identical 403.1 KB
output. `render_frames_to_webp`'s lossless branch overrides the caller with
`quality=100`, and lossless is the default -- so on the default path the flag is
parsed and thrown away with no signal. That trial nearly missed it because its
own override passed `--webp-lossy` alongside, which is exactly the combination
that hides the bug.

The flag deliberately does NOT imply `--webp-lossy`: lossless is the
measured-correct default for flat vector art, and switching someone to lossy
because they nudged a number would trade a silent no-op for a silent behaviour
change. The tool warns and names the flag that arms it.

⚠️ The third test is the one that keeps this honest. Without it the warning
could be added while the flag stays broken on both branches.
"""
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


def _run(out, *flags):
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out),
                        '--protect-outline-color', '002864', *flags],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stderr[-3000:]
    return r.stdout + r.stderr


@needs
def test_a_non_default_webp_quality_without_lossy_warns(tmp_path):
    log = _run(tmp_path / 'q.webp', '--webp-quality', '45').lower()
    assert '--webp-quality' in log and 'no effect' in log, \
        'a quality the encoder cannot read was accepted silently'
    assert '--webp-lossy' in log, 'the warning did not name the flag that arms it'


@needs
def test_the_default_path_stays_quiet(tmp_path):
    """What STAYED: an untouched --webp-quality must not warn on every ordinary run."""
    log = _run(tmp_path / 'd.webp').lower()
    assert 'no effect' not in log, 'the warning fires on a run that never set the flag'


@needs
def test_with_lossy_the_quality_actually_changes_the_bytes(tmp_path):
    """Two qualities, two sizes. Without this the warning could mask a still-broken flag."""
    sizes = []
    for q in ('30', '90'):
        out = tmp_path / f'l{q}.webp'
        _run(out, '--webp-lossy', '--webp-quality', q)
        sizes.append(out.stat().st_size)
    assert sizes[0] != sizes[1], f'quality had no effect even with --webp-lossy: {sizes}'
