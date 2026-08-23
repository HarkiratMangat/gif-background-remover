"""Falsifiers for --fade-color (plan Task 13 -- the investigation, then the fix).

DIAGNOSED 2026-08-22/23 by instrumenting rather than by reading the call graph.
`--fade-color` is read ONLY inside the `--recover-fade-alpha` branch, so on its
own it is parsed and thrown away. Measured on notification.gif, the faint fade
stages on frame 14 (pixels on the fd6050 -> white ray at 5-35% opacity):

    --recover-fade-alpha alone          REFUSES (no translucent colour detected)
    --recover-fade-alpha --fade-color   41.5% opaque, mean alpha 0.522
    --fade-color alone                   0.0% opaque, mean alpha 0.000, NO WARNING

⚠️ THE THIRD ROW IS THE DEFECT AND IT ALSO CORRECTS THE ORIGINAL REPORT. The
flag was recorded as "leaving the fade opaque". It does not: on its own it
removes the fade stages entirely. The run that looked broken was also passing
`--protect-outline-color f05050,002864`, and the PROTECTION was what held those
pixels opaque -- `--fade-color` did nothing whatsoever, silently.

The trap is a good one to have closed: `--recover-fade-alpha`'s own refusal
message told the user to "name the fading colour explicitly with --fade-color",
which reads as an alternative to the flag rather than an addition to it.
"""
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image, ImageSequence

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
NOTIFICATION = os.path.join(ROOT, 'local/2026-08-22-fade-edge-cases/inputs/notification.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

BASE = np.array([0xfd, 0x60, 0x50], float)
WHITE = np.array([255., 255., 255.])

needs = pytest.mark.skipif(not (os.path.exists(NOTIFICATION) and os.path.exists(SECURE)),
                           reason='the fade-edge-case inputs are gitignored third-party assets')


def _faint_source_pixels(frame=14, lo=0.05, hi=0.35):
    """Pixels on the BASE->white ray at low opacity: the faintest fade stages."""
    s = np.asarray(list(ImageSequence.Iterator(Image.open(NOTIFICATION)))[frame]
                   .convert('RGB')).astype(float)
    d = WHITE - BASE
    t = ((WHITE - s) @ d) / (d @ d)
    recon = WHITE - t[..., None] * d
    return (np.linalg.norm(s - recon, axis=-1) < 12) & (t >= lo) & (t < hi)


def _run(out, *flags):
    r = subprocess.run([sys.executable, SCRIPT, NOTIFICATION, str(out), *flags],
                       capture_output=True, text=True, timeout=1800)
    return r.returncode, r.stdout + r.stderr


@needs
def test_fade_color_alone_is_refused_instead_of_silently_ignored(tmp_path):
    rc, log = _run(tmp_path / 'a.webp', '--fade-color', 'fd6050')
    assert rc != 0, '--fade-color alone was accepted and did nothing'
    assert '--recover-fade-alpha' in log, \
        'the refusal did not name the flag that makes --fade-color work'
    assert not (tmp_path / 'a.webp').exists(), 'a file was written for a run that cannot work'


@needs
def test_the_pair_actually_recovers_the_faintest_stages(tmp_path):
    """What the flag is FOR. Without this half, the refusal above could ship beside a
    --fade-color that still does nothing when correctly paired."""
    out = tmp_path / 'b.webp'
    rc, log = _run(out, '--recover-fade-alpha', '--fade-color', 'fd6050')
    assert rc == 0, log[-3000:]
    m = _faint_source_pixels()
    assert m.sum() > 50, 'the fixture has no faint fade stages; it cannot falsify anything'
    al = np.asarray(list(ImageSequence.Iterator(Image.open(out)))[14])[..., 3] / 255.
    opaque = (al[m] >= 0.98).mean()
    assert opaque < 0.60, \
        f'{opaque:.1%} of the faintest fade stages came out fully opaque; --fade-color did ' \
        f'not recover them'
    assert al[m].mean() < 0.90, 'the fade stages are essentially still opaque'


@needs
def test_the_recover_refusal_prescribes_a_COMPLETE_command(tmp_path):
    """The trap that produced the defect: the message said "name the fading colour
    explicitly with --fade-color", which reads as an alternative, not an addition."""
    rc, log = _run(tmp_path / 'c.webp', '--recover-fade-alpha')
    assert rc != 0 and 'found no translucent colour' in log, log[-2000:]
    assert 'KEEP --recover-fade-alpha' in log and 'ADD --fade-color' in log, \
        'the refusal still reads as if --fade-color replaces the flag'


@needs
def test_a_run_that_never_mentions_a_fade_is_unaffected(tmp_path):
    """What STAYED: the new refusal must not reach an ordinary render."""
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(tmp_path / 'd.webp'),
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0 and (tmp_path / 'd.webp').exists(), r.stderr[-2000:]
    assert 'fade-color' not in (r.stdout + r.stderr)
