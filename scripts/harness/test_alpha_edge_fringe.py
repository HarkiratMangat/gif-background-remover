"""Falsifiers for the 8-bit-alpha edge fringe (plan Task 9).

The defect, noticed by Harkirat unprompted on every WebP/AVIF the MANUAL path
produced: a ~1px light ring around the whole artwork. `--verify`'s
`edge_fringe_check` reported `looks_fringed: false` on it, so the check that
exists to catch this could not.

Root cause is a defaults decision, not an erosion bug. For `webp`/`avif`/`apng`,
`--edge-cleanup-erosion` defaulted to a flat **0** on the reasoning that partial
alpha already represents the antialiased edge and needs no trim. `--auto` never
had the problem, because it calibrates erosion against the asset's own fringe
curve and picks 1.

Measured on megaphone.gif, same flags, erosion 0 against erosion 1 -- pale
partial-alpha pixels (0 < alpha < 255 and still within 128 of the background
colour, i.e. edge pixels that kept the background's tint rather than the art's):

    erosion 0   worst frame   852 px   total 92,560 px
    erosion 1   worst frame     1 px   total      10 px

⚠️ EVERY test here asserts on what STAYED as well as what left, because the
cheap way to score zero fringe is to erode the artwork away, and this repo has
448 renders' worth of evidence that erosion above 1 does exactly that
(`references/lessons.md` SS37). The negative fixtures are the point:

  * a GIF output must be untouched by this change (its default is a different
    number for a measured reason),
  * an explicitly typed `--edge-cleanup-erosion 0` must still win,
  * a recovered fade must keep its partial alpha -- that alpha is the artwork,
    and a calibration that ate it would score perfectly on the fringe measure.
"""
import hashlib
import os
import re
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image, ImageSequence

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
MEGAPHONE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')
BROADCAST = os.path.join(ROOT, 'local/2026-08-22-fade-edge-cases/inputs/broadcast.gif')
CACHE = os.path.join(ROOT, 'local', '.test-renders', 'fringe')

needs = pytest.mark.skipif(
    not (os.path.exists(MEGAPHONE) and os.path.exists(SECURE) and os.path.exists(BROADCAST)),
    reason='the trial inputs are gitignored third-party assets; not present in this checkout')


def _script_sha():
    with open(SCRIPT, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def render(src, ext, *flags):
    """(path, log) for `src` rendered through the real CLI, cached per script SHA."""
    slug = (os.path.basename(src).rsplit('.', 1)[0] + '_'
            + '_'.join(f.lstrip('-').replace('-', '') for f in flags) + ext)
    d = os.path.join(CACHE, _script_sha())
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, slug)
    logp = out + '.log'
    if not (os.path.exists(out) and os.path.exists(logp)):
        tmp = out + f'.{os.getpid()}.tmp' + ext
        r = subprocess.run([sys.executable, SCRIPT, src, tmp, *flags],
                           capture_output=True, text=True, timeout=1800)
        assert r.returncode == 0 and os.path.exists(tmp), \
            f'render failed rc={r.returncode}\n{r.stderr[-3000:]}'
        with open(tmp + '.log', 'w') as fh:
            fh.write(r.stdout + r.stderr)
        os.replace(tmp + '.log', logp)
        os.replace(tmp, out)
    with open(logp) as fh:
        return out, fh.read()


def _frames(path):
    im = Image.open(path)
    for f in ImageSequence.Iterator(im):
        yield np.array(f.convert('RGBA'))


def pale_halo(path, bg=(255, 255, 255)):
    """(worst frame, total) pale partial-alpha pixels.

    A partial-alpha pixel is legitimate antialiasing when it carries the ART's
    colour. It is fringe when it still carries the BACKGROUND's -- the unmixing
    did not reach it. Worst frame, never the mean: a defect on 16 consecutive
    frames of 144 reads as 99.9% clean when averaged.
    """
    bg = np.array(bg, float)
    worst = total = 0
    for arr in _frames(path):
        a = arr[..., 3].astype(int)
        d = np.sqrt(((arr[..., :3].astype(float) - bg) ** 2).sum(-1))
        n = int(((a > 0) & (a < 255) & (d < 128)).sum())
        worst = max(worst, n)
        total += n
    return worst, total


def partial_alpha_px(path):
    return sum(int(((arr[..., 3] > 0) & (arr[..., 3] < 255)).sum()) for arr in _frames(path))


def opaque_px(path):
    return sum(int((arr[..., 3] == 255).sum()) for arr in _frames(path))


@needs
def test_a_default_webp_render_does_not_leave_a_pale_fringe():
    """PRE: worst frame 852 pale px. The manual default must reach what --auto reaches."""
    out, _ = render(MEGAPHONE, '.webp', '--protect-outline-color', '002864')
    worst, total = pale_halo(out)
    assert worst <= 10, f'{worst} pale partial-alpha px on the worst frame ({total} total)'


@needs
def test_the_fix_did_not_simply_erode_the_artwork_away():
    """What STAYED. Erosion 1 costs a thin ring; erosion 3 ate 38.7% of a sprite (SS29)."""
    fixed, _ = render(MEGAPHONE, '.webp', '--protect-outline-color', '002864')
    floor, _ = render(MEGAPHONE, '.webp', '--protect-outline-color', '002864',
                      '--edge-cleanup-erosion', '0')
    assert opaque_px(fixed) >= 0.90 * opaque_px(floor), (
        f'artwork lost: {opaque_px(fixed)} opaque px vs {opaque_px(floor)} at erosion 0')


@needs
def test_erosion_never_escalates_past_the_measured_ceiling():
    """448 renders showed erosion above 1 never recovers artwork. Nothing here may exceed 2."""
    _, log = render(SECURE, '.webp', '--protect-outline-color', '002864')
    lvls = [int(m) for m in re.findall(r'--edge-cleanup-erosion (\d)', log)]
    lvls += [int(m) for m in re.findall(r'erosion.*?-> (\d)', log)]
    assert all(v <= 2 for v in lvls), f'erosion escalated past the ceiling: {lvls}'


@needs
def test_an_explicit_erosion_zero_still_wins():
    """The user's typed value outranks any calibration -- and stays 0, fringe and all."""
    out, log = render(MEGAPHONE, '.webp', '--protect-outline-color', '002864',
                      '--edge-cleanup-erosion', '0')
    assert 'auto: --edge-cleanup-erosion' not in log, \
        'a typed erosion value was recalibrated behind the user'
    assert pale_halo(out)[0] > 100, \
        'erosion 0 no longer reproduces the fringe -- the fixture has stopped falsifying'


@needs
def test_a_gif_output_default_is_untouched_by_this_change():
    """A GIF takes 1 or 2 for a separately measured reason. This change must not reach it."""
    _, log = render(MEGAPHONE, '.gif', '--protect-outline-color', '002864')
    m = re.search(r'edge-cleanup erosion defaulted to (\d)', log)
    assert m is None or int(m.group(1)) in (1, 2), f'GIF default moved: {m and m.group(1)}'


@needs
def test_a_recovered_fade_keeps_its_partial_alpha():
    """The negative fixture that matters: on a fade, partial alpha IS the artwork.

    A calibration that eroded it would score a perfect 0 on the fringe measure
    above while deleting the thing --recover-fade-alpha exists to produce.
    """
    out, _ = render(BROADCAST, '.webp', '--recover-fade-alpha')
    assert partial_alpha_px(out) > 10000, \
        f'the recovered fade was eroded away: only {partial_alpha_px(out)} partial-alpha px'
