"""Falsifiers for the fade-LADDER guard -- the painted-vs-flattened discriminator.

Every fixture is SYNTHESISED here from numpy arrays, so the suite depends on no corpus and on
nothing an earlier session left on disk. The corpora these rules were derived on are gitignored;
a test that needs them is a test that stops running.

The tests that matter are not "does it fire on hurricane" -- that one is easy and would pass for
a rule that fires on everything. They are the pairs that can tell a real discriminator from a
broken one:

  * a FLATTENED fade, built as the exact arithmetic a GIF export performs, which must NOT fire.
    This is the negative class at the same value of the confound: it has just as many faded
    stages as the positive, and differs only in whether they sit ON the background-to-colour
    line. Without it a "ladder" rule is indistinguishable from "this asset has a fade".
  * the ESCAPE HATCH: --fade-color must still work on a laddered asset, because naming the
    colour is the user overriding detection, not asking detection to try harder.
  * the THREE CALL SITES agreeing. analyze() predicts, recommend() declines and
    recover_fade_alpha_frames() refuses; SS36 shipped with two of those three disagreeing, so
    "they agree" is asserted rather than assumed.
"""
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, 'scripts', 'remove_gif_background.py')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from remove_gif_background import (  # noqa: E402
    analyze, build_art_palette, detect_fade_ladder, detect_fading_colors, hex_to_rgb)

SIZE = 128
BG = np.array([255, 255, 255], float)
ART = np.array([40, 50, 140], float)          # the colour that fades
N_FRAMES = 40
BLOCK = slice(20, 100)                        # 80x80 = 6400 px, well over the 2000 px floor

# TWO vectors perpendicular to (ART - BG), so a stage can be moved OFF the
# background-to-colour line without changing how far along that line it sits. 14 clears
# FADE_RESIDUAL_TOLERANCE (10.0) with margin -- the synthetic stand-in for the hue drift a human
# colour-picker leaves behind, measured at 13.8 on the real motivating asset.
#
# ⚠️ THE DRIFT DIRECTION MUST ROTATE, and two weaker versions were built and rejected first --
# both produced a fixture that was quietly a second copy of the NEGATIVE one:
#   * a CONSTANT offset puts every stage on one line parallel to the background-to-colour ray,
#     so each stage is a clean blend of the previous stage and pass 1 rejects it exactly as it
#     rejects a flattened stage. Palette came back with 3 entries and no ladder.
#   * ALTERNATING the sign per frame looks like it fixes that and does not, because
#     build_art_palette samples every 8th frame (sample_stride=8) -- so every sampled frame has
#     the same parity and the same offset, and the constant case returns unchanged. A fixture
#     whose defect is invisible at the sampling rate the product actually uses is not a fixture.
_D = ART - BG
_P1 = np.array([-_D[1], _D[0], 0.0])
_P1 = _P1 / np.linalg.norm(_P1) * 14.0
_P2 = np.cross(_D, _P1)
_P2 = _P2 / np.linalg.norm(_P2) * 14.0


def _frames(painted):
    """A square that fades toward the background over N_FRAMES.

    `painted=False` composites the exact blend a flattened export produces; `painted=True` adds
    a rotating perpendicular offset to every stage, which is what an artist hand-picking
    successively lighter tints leaves behind. Nothing else differs.
    """
    out = []
    for i in range(N_FRAMES):
        t = 1.0 - i / N_FRAMES
        col = BG + t * _D
        if painted:
            th = i * 0.9          # irrational-ish step: consecutive SAMPLED frames differ
            col = col + _P1 * np.cos(th) + _P2 * np.sin(th)
        f = np.zeros((SIZE, SIZE, 3), np.uint8)
        f[:] = BG.astype(np.uint8)
        f[BLOCK, BLOCK] = np.clip(col, 0, 255).astype(np.uint8)
        # A moving marker so Pillow's animated-WebP writer cannot collapse identical
        # consecutive frames -- the trap test_changing_background.py records. Kept OFF the
        # border ring: on row 0 it makes one corner disagree with the other three and the tool
        # correctly warns about ambiguous background detection.
        f[5, 5 + i] = (0, 0, 0)
        out.append(f)
    return out


def _write(frames, path):
    """Animated LOSSLESS WebP: the exact RGB values chosen here are the exact values read back.
    A GIF would re-quantize them and move every distance this file asserts on."""
    ims = [Image.fromarray(f, 'RGB') for f in frames]
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=40, loop=0,
                lossless=True, quality=100)
    with Image.open(path) as im:
        assert getattr(im, 'n_frames', 1) == len(frames), 'fixture lost frames on write'
    return path


@pytest.fixture(scope='module')
def painted(tmp_path_factory):
    return _write(_frames(True), str(tmp_path_factory.mktemp('fl') / 'painted.webp'))


@pytest.fixture(scope='module')
def flattened(tmp_path_factory):
    return _write(_frames(False), str(tmp_path_factory.mktemp('fl') / 'flattened.webp'))


def _detected(path):
    """The fading colours the product itself would find, through its own two functions."""
    with Image.open(path) as im:
        rgbs = []
        for i in range(getattr(im, 'n_frames', 1)):
            im.seek(i)
            rgbs.append(np.array(im.convert('RGB')))
    prov = build_art_palette(rgbs, tuple(int(x) for x in BG))
    idx = sorted(detect_fading_colors(rgbs, tuple(int(x) for x in BG), prov))
    return prov, [prov[i] for i in idx]


# --------------------------------------------------------------- the helper, in isolation
def test_ladder_needs_three_members():
    """Two collinear colours are a colour and a lighter version of it, not a ladder. The floor
    is what stops the rule firing on the ordinary case of one tint of one art colour."""
    cols = [BG + 1.0 * _D, BG + 0.5 * _D]
    assert detect_fade_ladder(BG, cols) is None


def test_ladder_does_not_group_unrelated_colours():
    """Three genuinely different art colours must not read as one ladder, however many of them
    the fade detector happens to flag."""
    cols = [np.array([255, 0, 0], float), np.array([0, 255, 0], float),
            np.array([0, 0, 255], float)]
    assert detect_fade_ladder(BG, cols) is None


def test_ladder_is_anchored_on_the_farthest_member():
    """Rungs run INWARD from the farthest colour along one ray, so the reported distances must
    come back descending and the span must exceed 1."""
    cols = [BG + f * _D for f in (1.0, 0.7, 0.45, 0.25)]
    lad = detect_fade_ladder(BG, cols)
    assert lad is not None and lad['members'] == 4
    assert lad['distances_from_bg'] == sorted(lad['distances_from_bg'], reverse=True)
    assert lad['distance_span_ratio'] > 1.0


# ------------------------------------------------- the mechanism, on real synthetic fades
def test_flattened_fade_contributes_one_colour_and_no_ladder(flattened):
    """THE NEGATIVE CLASS. A flattened fade is bg*(1-a)+c*a by construction, so pass 1's blend
    rejection removes every intermediate stage and one element yields ONE detected colour.
    Measured the same way on the four real assets --recover-fade-alpha exists for -- crystal,
    gift, love and heart -- all four report exactly one."""
    prov, fading = _detected(flattened)
    assert len(fading) >= 1, 'the fixture must still look like a fade at all'
    assert detect_fade_ladder(BG, fading) is None
    assert len(fading) <= 2, f'a flattened fade should not fan out into stages: {len(fading)}'


def test_painted_fade_produces_a_ladder(painted):
    """THE POSITIVE. The only difference from the fixture above is a rotating perpendicular
    offset -- the same hue drift a human colour-picker leaves -- and it is what makes the stages
    survive pass 1 and show up as a near-collinear chain."""
    prov, fading = _detected(painted)
    lad = detect_fade_ladder(BG, fading)
    assert lad is not None, f'no ladder found among {len(fading)} detected fading colours'
    assert lad['members'] >= 3
    # The GROUPING is anchored on the farthest rung, so this reported pairwise figure is
    # evidence rather than the rule's own threshold; it is asserted loosely on purpose, because
    # the drift has to be large enough to survive pass 1 (>10) and that necessarily opens the
    # angle at the rungs closest to the background.
    assert lad['min_pairwise_cosine'] >= 0.90


def test_analyze_reports_the_ladder_it_finds(painted, flattened):
    """The prediction side. `fade_palette_is_ladder` is None unless the gradient-fade screen
    fired AND a ladder is present, so a None here is 'not applicable', never a quiet pass."""
    rp, rf = analyze(painted), analyze(flattened)
    assert rf.get('fade_palette_is_ladder') is None
    if rp.get('fade_colors_detected'):
        assert rp.get('fade_palette_is_ladder') is not None, \
            'the screen fired and the palette is a ladder, so analyze() must say so'


# ------------------------------------------------------------ the renderer's own refusal
def _run(src, dst, *extra):
    return subprocess.run([sys.executable, SCRIPT, src, dst, '--recover-fade-alpha', *extra],
                          capture_output=True, text=True, timeout=600)


def test_renderer_refuses_a_painted_fade(painted, tmp_path):
    """PREVENTION, not just prediction. A run that never called --recommend must still be
    stopped -- the three-place split SS35 and SS36 both turned on."""
    r = _run(painted, str(tmp_path / 'o.webp'))
    assert r.returncode != 0, 'a laddered source must be refused, not rendered'
    assert 'fade LADDER' in (r.stdout + r.stderr)
    assert not os.path.exists(str(tmp_path / 'o.webp'))


def test_renderer_still_accepts_a_flattened_fade(flattened, tmp_path):
    """The guard must not swallow the case the flag exists for. This is the falsifier that a
    blanket refusal would fail."""
    out = str(tmp_path / 'o.webp')
    r = _run(flattened, out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(out)


def test_fade_color_bypasses_the_ladder_guard(painted, tmp_path):
    """THE ESCAPE HATCH. --fade-color names the colour and bypasses detection entirely, so the
    guard -- which is a statement about what DETECTION found -- must not block it. Every other
    refusal in this file points the user here, and a pointer to something that does not work is
    worse than no pointer."""
    out = str(tmp_path / 'o.webp')
    hexc = '%02x%02x%02x' % tuple(int(v) for v in ART)
    r = _run(painted, out, '--fade-color', hexc)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(out)
    assert hex_to_rgb(hexc) == tuple(int(v) for v in ART)


def test_unverified_fade_is_declined_not_emitted(flattened, monkeypatch):
    """THE FALL-THROUGH. `fade_colors_confirmed` is three-state and its None arm is documented
    "unverified, never a pass" -- but the gate tested only `is False`, so a confirmation step
    that RAISED emitted the destructive flag on no evidence. The word and the behaviour
    disagreed, which is what SS38 was one function along. Driven by making the real detector
    raise, because that is the only way the None arm is reachable."""
    import remove_gif_background as M

    def boom(*a, **k):
        raise RuntimeError('detector unavailable')

    monkeypatch.setattr(M, 'detect_fading_colors', boom)
    rep = M.analyze(flattened)
    assert rep.get('fade_colors_confirmed') is None
    out = M.recommend(flattened)
    # The COMMAND, not the whole report -- the evidence prose legitimately contains the flag
    # name in the sentence declining it, and asserting on the report as a whole would pass for
    # a build that emitted it and fail for one that explained itself.
    assert '--recover-fade-alpha' not in out['suggested_command'], \
        'an unverified fade must not emit the flag'
    assert any('NOT recommending --recover-fade-alpha' in e for e in out['evidence']), \
        'and it must say why, since an autonomous run has nothing else to read'
