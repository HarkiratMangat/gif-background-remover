"""Falsifiers for the --target-kb rung search (Part 4, Task B).

Two claims need proving, and they pull in opposite directions:

  1. The rung list is a TOTAL ORDER by destructiveness, so "the first rung that fits" and
     "the least destructive rung that fits" are the same element. That equivalence is the
     ONLY reason the search may evaluate rungs concurrently.
  2. Concurrency therefore cannot change the delivered file. Asserted by running the same
     asset serially and in parallel and comparing the chosen rung AND the bytes -- not by
     reasoning that it structurally cannot differ, which is how the last "it cannot
     disagree" claim in this repo turned out to be wrong.
"""
import os
import sys

import pytest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

import remove_gif_background as R  # noqa: E402

SCALES = (1.0, 0.75, 0.5, 0.375, 0.25)


def _idx(rungs, pred):
    return next(i for i, r in enumerate(rungs) if pred(r))


# --------------------------------------------------------------------------
# The ordering itself
# --------------------------------------------------------------------------

def test_the_ladder_is_a_total_order_and_deterministic():
    a = R.build_target_rungs('webp', SCALES)
    b = R.build_target_rungs('webp', SCALES)
    assert a == b
    assert len(a) == len(set(a)), 'a rung appears twice'
    assert a[0] == (1, 1.0, 100, True), a[0]


def test_a_deep_downscale_now_ranks_BELOW_frame_stride():
    """The change Harkirat approved 2026-08-21, and the whole reason this file exists.
    Measured on galaxy: stride 2 at native resolution (1183 KB) is smaller than scale
    0.75/0.5/0.375 at EVERY quality, so the old order handed back a 160px file where a
    full-resolution one of the same size existed."""
    r = R.build_target_rungs('webp', SCALES)
    first_stride2 = _idx(r, lambda x: x[0] == 2)
    assert first_stride2 < _idx(r, lambda x: x[1] == 0.375)
    assert first_stride2 < _idx(r, lambda x: x[1] == 0.25)


def test_a_moderate_downscale_still_ranks_ABOVE_frame_stride():
    """Only the DEEP end moved. Reversing the whole axis would have been a different,
    unmeasured claim."""
    r = R.build_target_rungs('webp', SCALES)
    first_stride2 = _idx(r, lambda x: x[0] == 2)
    assert _idx(r, lambda x: x[1] == 0.75) < first_stride2
    assert _idx(r, lambda x: x[1] == 0.5) < first_stride2


def test_quality_is_still_degraded_before_anything_else():
    r = R.build_target_rungs('webp', SCALES)
    assert [x[2] for x in r[:6]] == [100, 95, 90, 80, 70, 60]
    assert all(x[0] == 1 and x[1] == 1.0 for x in r[:6])


def test_a_pinned_resolution_never_produces_a_scale_rung():
    """--resize-max-dim is a REQUIREMENT, not a constraint to trade away: the ladder once
    produced 48x48 files for a requested 128px emoji."""
    r = R.build_target_rungs('webp', (1.0,))
    assert {x[1] for x in r} == {1.0}


def test_avif_never_offers_a_lossless_rung_and_apng_offers_only_lossless():
    """AVIF quality=100 is not lossless and is the biggest output of all; APNG has no
    quality knob at all, so resolution and frames are its only levers."""
    assert not any(x[3] for x in R.build_target_rungs('avif', SCALES))
    apng = R.build_target_rungs('apng', SCALES)
    assert all(x[3] and x[2] == 100 for x in apng)
    assert len(apng) == 4 * len(SCALES)


# --------------------------------------------------------------------------
# Capacity detection -- probed, never assumed, and never below 1
# --------------------------------------------------------------------------

def test_capacity_is_at_least_one_and_explains_itself():
    jobs, why = R.detect_worker_capacity(300, explain=True)
    assert jobs >= 1 and isinstance(why, str) and why


def test_capacity_falls_back_to_serial_when_nothing_can_be_probed(monkeypatch):
    """The claude.ai sandbox's profile is unknown. An unprobeable environment must get the
    old serial behaviour, never a guessed worker count."""
    monkeypatch.setattr(R, '_read_int', lambda *a, **k: None)
    monkeypatch.setattr(R.os, 'cpu_count', lambda: None)
    monkeypatch.setattr(R.subprocess, 'run',
                        lambda *a, **k: (_ for _ in ()).throw(OSError('no such tool')))
    assert R.detect_worker_capacity(300) == 1


def test_a_huge_per_worker_estimate_collapses_to_one_worker():
    """The memory half must actually bind, or it is decoration."""
    assert R.detect_worker_capacity(10_000_000) == 1


# --------------------------------------------------------------------------
# The claim that matters: concurrency cannot change the delivered file
# --------------------------------------------------------------------------

def _asset(path, size=160, frames=8):
    ims = []
    for i in range(frames):
        im = Image.new('RGB', (size, size), (255, 255, 255))
        for y in range(40, 120):
            for x in range(30 + i * 4, 110 + i * 4):
                im.putpixel((x % size, y), (20 + 25 * i, 90, 200 - 10 * i))
        ims.append(im)
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=80, loop=0)
    return path


def _frames(path):
    import numpy as np
    im = Image.open(path)
    rgb, alpha, dur = [], [], []
    for i in range(getattr(im, 'n_frames', 1)):
        im.seek(i)
        f = im.convert('RGBA')
        a = np.array(f)
        rgb.append(a[:, :, :3].copy())
        alpha.append(np.full(a.shape[:2], 255, dtype='uint8'))
        dur.append(im.info.get('duration', 80) or 80)
    return rgb, alpha, dur


class _Args:
    pixel_art = False
    resize_max_dim = None
    webp_method = 4


@pytest.mark.parametrize('target_kb', [12, 30])
def test_serial_and_parallel_choose_the_same_rung_and_the_same_bytes(tmp_path, target_kb):
    src = _asset(str(tmp_path / 'src.gif'))
    rgb, alpha, dur = _frames(src)

    out_s, log_s = str(tmp_path / 's.webp'), []
    size_s, hit_s = R.fit_to_target_bytes(rgb, alpha, dur, 0, out_s, target_kb,
                                          'webp', _Args(), log=log_s, jobs=1)
    out_p, log_p = str(tmp_path / 'p.webp'), []
    size_p, hit_p = R.fit_to_target_bytes(rgb, alpha, dur, 0, out_p, target_kb,
                                          'webp', _Args(), log=log_p, jobs=6)

    assert (size_s, hit_s) == (size_p, hit_p)
    assert open(out_s, 'rb').read() == open(out_p, 'rb').read()
    chosen_s = [l for l in log_s if l.startswith('Hit target') or l.startswith('Could not')]
    chosen_p = [l for l in log_p if l.startswith('Hit target') or l.startswith('Could not')]
    assert chosen_s == chosen_p, (chosen_s, chosen_p)


def test_the_parallel_run_leaves_no_temp_files_behind(tmp_path):
    src = _asset(str(tmp_path / 'src.gif'))
    rgb, alpha, dur = _frames(src)
    out = str(tmp_path / 'out.webp')
    R.fit_to_target_bytes(rgb, alpha, dur, 0, out, 20, 'webp', _Args(), jobs=6)
    leftovers = [n for n in os.listdir(tmp_path) if '.rung' in n]
    assert leftovers == [], leftovers


def test_an_unreachable_target_still_leaves_the_smallest_attempt_on_disk(tmp_path):
    """The reported number must describe the file actually on disk, not whatever the last
    rung happened to write."""
    src = _asset(str(tmp_path / 'src.gif'))
    rgb, alpha, dur = _frames(src)
    out, log = str(tmp_path / 'tiny.webp'), []
    size, hit = R.fit_to_target_bytes(rgb, alpha, dur, 0, out, 0.001, 'webp', _Args(),
                                      log=log, jobs=4)
    assert hit is False
    assert os.path.getsize(out) == size
    assert any('Could not reach' in l for l in log)
