"""Falsifiers for --unprotect-region: a region-scoped BACKGROUND removal.

The defect this exists for, measured 2026-08-22 on broadcast.gif: there was no
way to say "this enclosed interior is background." Every protection mechanism --
explicit outline, the fade path's topological protection, the band-interior scan
-- independently classifies an enclosed region of background colour as design.

⚠️ The obvious workaround was tried and DESTROYED THE ARTWORK. `--remove-region
rect:238,332,168,206` took enclosed white from 8,569 px to 0 and the navy tower
from 23,157 px to 6,297 -- a 73% loss -- because it force-deletes everything in
its box. The white-pixel assertion PASSED on that render. That is why every test
here asserts on BOTH halves: what left, and what stayed.
"""
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image, ImageSequence
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
BROADCAST = os.path.join(ROOT, 'local/2026-08-22-fade-edge-cases/inputs/broadcast.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')


def _measure(path, frame=30):
    """(enclosed near-white opaque px, navy artwork px, total opaque px)."""
    fr = [f.convert('RGBA') for f in ImageSequence.Iterator(Image.open(path))]
    a = np.asarray(fr[min(frame, len(fr) - 1)])
    rgb, al = a[..., :3].astype(int), a[..., 3] / 255.0
    white = ((rgb > 238).all(-1)) & (al >= 0.98)
    lab, n = ndimage.label(white)
    enclosed = 0
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if not (xs.min() == 0 or ys.min() == 0
                or xs.max() == lab.shape[1] - 1 or ys.max() == lab.shape[0] - 1):
            enclosed += int((lab == i).sum())
    navy = int((((rgb[..., 2] > 80) & (rgb[..., 2] - rgb[..., 0] > 40)) & (al > 0.5)).sum())
    return enclosed, navy, int((al > 0.5).sum())


def _run(args, out, timeout=900):
    r = subprocess.run([sys.executable, SCRIPT] + args, capture_output=True,
                       text=True, timeout=timeout)
    assert r.returncode == 0, r.stderr[-2000:]
    assert os.path.exists(out), 'no output written'
    return r


@pytest.mark.skipif(not os.path.exists(BROADCAST), reason='asset not in this checkout')
def test_it_removes_the_enclosed_white_AND_keeps_the_tower(tmp_path):
    out = str(tmp_path / 'u.webp')
    _run([BROADCAST, out, '--recover-fade-alpha', '--erosion-exempt-transient',
          '--unprotect-region', 'rect:238,332,168,206'], out)
    white, navy, _ = _measure(out)
    assert white < 500, f'{white} enclosed white px survived (8,569 before)'
    assert navy > 20000, (
        f'only {navy} navy artwork px survived; the source render has 23,157. '
        f'--remove-region scored 6,297 here and that is the failure being fixed')


@pytest.mark.skipif(not os.path.exists(BROADCAST), reason='asset not in this checkout')
def test_it_composes_with_the_fade_path(tmp_path):
    """--recover-fade-alpha ignores every protection flag. This must survive it."""
    out = str(tmp_path / 'f.webp')
    _run([BROADCAST, out, '--recover-fade-alpha', '--erosion-exempt-transient',
          '--unprotect-region', 'rect:238,332,168,206'], out)
    fr = [f.convert('RGBA') for f in ImageSequence.Iterator(Image.open(out))]
    A = np.stack([np.asarray(f)[..., 3] for f in fr]).astype(float) / 255.0
    mid = 100.0 * ((A > 0.15) & (A < 0.85)).sum() / A.size
    assert mid > 3.0, f'fade lost: {mid:.2f}% mid-alpha (fade-only render scores 4.25%)'


@pytest.mark.skipif(not os.path.exists(BROADCAST), reason='asset not in this checkout')
def test_it_is_NOT_a_force_delete(tmp_path):
    """The direct falsifier against reintroducing --remove-region's behaviour:
    a region placed over SOLID artwork must change almost nothing."""
    out_a, out_b = str(tmp_path / 'a.webp'), str(tmp_path / 'b.webp')
    base = [BROADCAST, out_a, '--protect-outline-color', '002864',
            '--erosion-exempt-transient']
    _run(base, out_a)
    _run([BROADCAST, out_b, '--protect-outline-color', '002864',
          '--erosion-exempt-transient',
          '--unprotect-region', 'rect:250,190,60,60'], out_b)
    _, navy_a, opaque_a = _measure(out_a)
    _, navy_b, opaque_b = _measure(out_b)
    assert opaque_b > opaque_a * 0.97, (
        f'opaque px fell {opaque_a} -> {opaque_b}: the region deleted artwork '
        f'instead of only background-coloured pixels')


@pytest.mark.skipif(not os.path.exists(SECURE), reason='asset not in this checkout')
def test_omitting_the_flag_changes_nothing(tmp_path):
    """Guards the default path: this feature must be inert unless asked for."""
    a, b = str(tmp_path / 'x.webp'), str(tmp_path / 'y.webp')
    for o in (a, b):
        _run([SECURE, o, '--protect-outline-color', '002864'], o)
    assert open(a, 'rb').read() == open(b, 'rb').read()

@pytest.mark.skipif(not os.path.exists(BROADCAST), reason='asset not in this checkout')
def test_the_boundary_does_not_leave_a_pale_OPAQUE_rim(tmp_path):
    """The defect a viewer sees as a shimmering edge, and the reason the colour
    ramp alone is not enough.

    Measured on the broadcast tower over a FIXED ring population: colour-derived
    alpha alone left 12.4% of the antialiasing ring FULLY OPAQUE and pale, because
    a pixel just outside --tolerance gets an alpha near 1 from the ramp. Combining
    it with apply_remove_regions' geometric taper brings that to 0.5%.

    ⚠️ The population is fixed BEFORE looking at either render. Selecting ring
    pixels BY alpha compares a different set in each render -- the mistake that
    produced a wrong "+27% recovered" claim earlier in this investigation.
    """
    import numpy as np
    from scipy import ndimage
    out = str(tmp_path / 'rim.webp')
    _run([BROADCAST, out, '--recover-fade-alpha', '--erosion-exempt-transient',
          '--unprotect-region', 'rect:238,300,168,240'], out)
    y0, x0, h, w = 300, 238, 240, 168
    src = np.stack([np.asarray(f.convert('RGB')).astype(float)
                    for f in ImageSequence.Iterator(Image.open(BROADCAST))])
    d = np.linalg.norm(src[:, y0:y0 + h, x0:x0 + w] - 255.0, axis=-1)
    stable = (d <= 15).mean(0) >= 0.95
    ring = ndimage.binary_dilation(stable, iterations=2) & ~stable
    a = np.asarray(list(ImageSequence.Iterator(Image.open(out)))[30].convert('RGBA'))
    al = a[y0:y0 + h, x0:x0 + w, 3] / 255.0
    opaque = (al[ring] >= 0.95).mean()
    assert opaque < 0.04, (
        f'{opaque:.1%} of the antialiasing ring is fully opaque; the colour ramp '
        f'alone measured 12.4% and reads as a pale shimmering rim')
