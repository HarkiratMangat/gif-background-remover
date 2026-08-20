"""Falsifiers for the changing-background guard.

Every fixture here is SYNTHESISED inside the test from a few numpy arrays, so the suite is
self-contained: it depends on no corpus, on no earlier render, and on nothing another session
happened to leave on disk. A fixture that only works because of something rendered earlier in
the session is not a fixture.

The tests that matter are not "does it fire on a changing background" -- that one is easy and
would pass for a detector that fires on everything. They are the three that can distinguish a
real measure from a broken one:

  * a NEGATIVE whose corner colour genuinely moves, so "did not fire" is a real pass;
  * PALETTE DRIFT below the distance threshold, which is a margin of degree and must not fire;
  * the FALL-THROUGH, which has to report UNVERIFIED rather than the pass value.
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, 'scripts', 'remove_gif_background.py')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from remove_gif_background import analyze, recommend  # noqa: E402

SIZE = 64


def _write(frames, path):
    """Animated LOSSLESS WebP, so the exact RGB values the test chose are the exact values the
    product reads back. A GIF would re-quantize them and quietly move every distance this file
    asserts on.

    ⚠️ Pillow's animated-WebP writer COLLAPSES identical consecutive frames. A first version of
    these fixtures wrote ten frames and got back TWO, so a test asserting on frame indexes 5-9
    was really testing a two-frame file -- the fixture had quietly become a different fixture.
    Every frame here therefore carries a moving marker pixel, and the frame count is read back
    and asserted rather than trusted. A fixture that silently loses 80% of itself tests
    something other than what it says.
    """
    ims = [Image.fromarray(f, 'RGB') for f in frames]
    ims[0].save(str(path), save_all=True, append_images=ims[1:], duration=100, loop=0,
                lossless=True, minimize_size=False)
    back = getattr(Image.open(str(path)), 'n_frames', 1)
    assert back == len(frames), (
        f'fixture collapsed on write: {len(frames)} frames in, {back} back out')
    return str(path)


def _frame(bg, shapes=((20, 20, 12),), tick=None):
    """`shapes` is a list of (y, x, size) dark squares. `tick` moves one marker pixel, which is
    what keeps two consecutive frames from being byte-identical -- see _write."""
    f = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    f[:, :] = bg
    for (y, x, sz) in shapes:
        f[y:y + sz, x:x + sz] = (10, 10, 10)
    if tick is not None:
        f[SIZE // 2, tick % SIZE] = (200, 200, 200)
    return f


@pytest.fixture
def recoloured(tmp_path):
    """Background is magenta for frames 0-4 and green for frames 5-9: the real defect."""
    frames = [_frame((255, 26, 254) if i < 5 else (20, 247, 57), tick=i) for i in range(10)]
    return _write(frames, tmp_path / 'recoloured.webp')


@pytest.fixture
def constant_but_corners_move(tmp_path):
    """THE falsifier. The background never changes, but on every odd frame dark art covers
    THREE of the four corners, so the corner-MAJORITY colour moves -- exactly the condition
    that makes a corner-only rule fire. If this fixture's corner majority did not move, a pass
    here would be vacuous, which is why the test asserts on that first.

    Three corners, not one: a first version covered one corner per frame and the majority never
    budged, so `distinct_corner_colors` came back 1 and the falsifier falsified nothing. The
    real control corpus has an asset reading 11 distinct corner colours with a perfectly
    constant background; this is the synthetic version of it."""
    frames = []
    for i in range(12):
        shapes = ([(0, 0, 18), (0, SIZE - 18, 18), (SIZE - 18, 0, 18)] if i % 2
                  else [(20, 20, 12)])
        frames.append(_frame((255, 26, 254), shapes=shapes, tick=i))
    return _write(frames, tmp_path / 'corners.webp')


@pytest.fixture
def palette_drift(tmp_path):
    """The background moves 16 units -- the size of a real re-quantization of the same colour,
    measured on the asset that motivated this guard. A margin of DEGREE, not of kind."""
    frames = [_frame((255, 26, 254) if i < 5 else (255, 10, 253), tick=i) for i in range(10)]
    return _write(frames, tmp_path / 'drift.webp')


def _stability(path):
    return analyze(path)['background_color_stability']


# ------------------------------------------------------------------ the measure

def test_a_recoloured_background_is_detected(recoloured):
    st = _stability(recoloured)
    assert st['changes'] is True
    assert st['recolored_frame_indexes'] == [5, 6, 7, 8, 9]
    assert st['peak_recolored_plane_coverage'] > 0.5, \
        'the replacement colour should be measured as a real plane, not a stray corner'


def test_a_constant_background_does_not_fire_even_when_the_corners_move(constant_but_corners_move):
    st = _stability(constant_but_corners_move)
    # Non-vacuity FIRST: if the corners never moved, the pass below tests nothing.
    assert st['distinct_corner_colors'] > 1, \
        'fixture is vacuous -- its corner MAJORITY never moved, so it cannot falsify anything'
    assert st['changes'] is False
    assert st['recolored_frame_indexes'] == []


def test_palette_drift_is_not_a_background_change(palette_drift):
    """16 units apart is the same colour re-quantized. A threshold at --tolerance (15) would
    call this a background change; the guard's 40 is deliberately a margin of KIND."""
    st = _stability(palette_drift)
    assert st['changes'] is False, \
        'a 16-unit shift is palette drift, not a recolour -- see references/lessons.md SS36'


def test_the_scan_is_dense_enough_to_see_a_one_frame_transient(tmp_path):
    """A spread cannot see a transient: the measurement that motivated this guard sampled 10
    frames of 30 and read 78.6% at frame 10 while frame 12 was 0.0%. The test picks a frame
    analyze()'s own `sample_idxs` provably skips, so it fails if the scan is ever moved onto
    the sampled indices."""
    n = 60
    sampled = set(np.linspace(0, n - 1, 40).astype(int).tolist())
    hidden = next(i for i in range(1, n) if i not in sampled)
    frames = [_frame((255, 26, 254) if i != hidden else (20, 247, 57), tick=i)
              for i in range(n)]
    st = _stability(_write(frames, tmp_path / 'transient.webp'))
    assert hidden not in sampled, 'the test frame must be one the sampled spread misses'
    assert st['changes'] is True
    assert st['recolored_frame_indexes'] == [hidden]


# ------------------------------------------------------------------ the fall-through

def test_the_fall_through_is_unverified_not_pass(tmp_path):
    """Four differently-coloured corners over a fifth colour: the detected background covers
    ~1 pixel of frame 0, so there is no reference plane for a collapse to be measured against
    and the rule would silently never fire. That is a vacuous pass and must be reported as
    UNVERIFIED -- `None`, never `False`."""
    frames = []
    for i in range(6):
        f = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
        f[:, :] = (90, 90, 90)
        f[0, 0] = (255, 0, 0)
        f[0, SIZE - 1] = (0, 255, 0)
        f[SIZE - 1, 0] = (0, 0, 255)
        f[SIZE - 1, SIZE - 1] = (255, 255, 0)
        f[SIZE // 2, i] = (200, 200, 200)
        frames.append(f)
    st = _stability(_write(frames, tmp_path / 'nocorners.webp'))
    assert st['changes'] is None, 'an unmeasurable input must not be reported as clean'
    assert st['unverified_reason']
    assert 'UNVERIFIED' in st['unverified_reason']


def test_a_single_frame_is_a_determination_not_a_fall_through(tmp_path):
    p = tmp_path / 'one.png'
    Image.fromarray(_frame((255, 26, 254)), 'RGB').save(str(p))  # noqa: E501
    st = _stability(str(p))
    assert st['changes'] is False, 'one frame cannot change colour -- that is a real answer'
    assert st['unverified_reason'] is None


# ------------------------------------------------------------------ steer, and refuse

def test_recommend_refuses_to_emit_a_command(recoloured):
    rec = recommend(recoloured)
    assert rec['suggested_command'] is None, \
        'an autonomous run pastes this verbatim, so it cannot hold a removal command here'
    assert 'BACKGROUND CHANGES COLOUR' in rec['not_applicable_reason']
    assert rec['evidence'][0] == rec['not_applicable_reason']


def test_recommend_is_unaffected_on_a_constant_background(constant_but_corners_move):
    rec = recommend(constant_but_corners_move)
    assert rec['not_applicable_reason'] is None
    assert rec['suggested_command']


def test_process_refuses_through_the_cli_and_writes_nothing(recoloured, tmp_path):
    """The render-side half. --recommend already refuses, but a run that never called it -- a
    hand-written command line, a batch manifest -- has to be stopped too."""
    out = tmp_path / 'out.webp'
    r = subprocess.run([sys.executable, SCRIPT, recoloured, str(out)],
                       capture_output=True, text=True)
    assert r.returncode != 0, 'the run should have been refused'
    assert 'BACKGROUND CHANGES COLOUR' in (r.stdout + r.stderr)
    assert 'Traceback' not in r.stderr, 'the refusal must be a message, not a crash'
    assert not out.exists(), 'nothing may be written when the render is refused'


def test_auto_refuses_too(recoloured, tmp_path):
    out = tmp_path / 'auto.webp'
    r = subprocess.run([sys.executable, SCRIPT, recoloured, str(out), '--auto'],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert 'BACKGROUND CHANGES COLOUR' in (r.stdout + r.stderr)
    assert not out.exists()


def test_the_escape_hatch_lets_it_through(recoloured, tmp_path):
    out = tmp_path / 'forced.webp'
    r = subprocess.run([sys.executable, SCRIPT, recoloured, str(out),
                        '--allow-changing-background'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.exists() and out.stat().st_size > 0


def test_auto_honours_the_escape_hatch_too(recoloured, tmp_path):
    """`--auto` refuses on any `not_applicable_reason`, so the override has to reach the
    RECOMMENDER, not only process(). A documented flag that works on one entry point and not on
    the flagship autonomous one is the half-fix this repo keeps re-learning."""
    out = tmp_path / 'auto_forced.webp'
    r = subprocess.run([sys.executable, SCRIPT, recoloured, str(out), '--auto',
                        '--allow-changing-background'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.exists() and out.stat().st_size > 0


def test_recommend_warns_instead_of_refusing_when_allowed(recoloured):
    rec = recommend(recoloured, allow_changing_background=True)
    assert rec['not_applicable_reason'] is None
    assert rec['suggested_command'].endswith('--allow-changing-background'), \
        'the emitted command must actually run -- it is pasted verbatim'
    assert 'WARNING' in rec['evidence'][0]


def test_one_refused_asset_does_not_abort_a_whole_batch(recoloured, constant_but_corners_move,
                                                        tmp_path):
    """Every refusal in process() is a `raise SystemExit`, which is NOT an `Exception` -- so the
    batch loop's own error handler never saw one and a single bad asset killed the run. Measured
    before the fix: the second, perfectly processable job produced no output at all."""
    o1, o2 = tmp_path / 'o1.webp', tmp_path / 'o2.webp'
    manifest = tmp_path / 'm.json'
    manifest.write_text(json.dumps([
        {'input': recoloured, 'output': str(o1)},
        {'input': constant_but_corners_move, 'output': str(o2)},
    ]))
    r = subprocess.run([sys.executable, SCRIPT, '--batch', str(manifest)],
                       capture_output=True, text=True)
    assert not o1.exists(), 'the refused job must still write nothing'
    assert o2.exists(), 'the job AFTER the refused one must still run'
    assert 'BACKGROUND CHANGES COLOUR' in (r.stdout + r.stderr)


def test_a_constant_background_still_renders(constant_but_corners_move, tmp_path):
    """The guard must not have become a blanket refusal."""
    out = tmp_path / 'ok.webp'
    r = subprocess.run([sys.executable, SCRIPT, constant_but_corners_move, str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert out.exists()


def test_analyze_json_carries_the_field(recoloured):
    """--analyze's JSON is what an autonomous run reads; the field has to survive
    serialisation, not just exist as a Python dict."""
    r = subprocess.run([sys.executable, SCRIPT, recoloured, '--analyze'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout[r.stdout.index('{'):r.stdout.rindex('}') + 1])
    st = payload['background_color_stability']
    assert st['changes'] is True
    assert st['recolored_colors']
