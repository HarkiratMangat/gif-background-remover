"""Falsifiers for the background-RAMP candidate — evidence for a person, never an automatic flag.

The point of this suite is not "does it find the glow" — a rule that fired on everything would
pass that too. It is that the candidate stays EVIDENCE: it must be reported, it must name a
colour that actually ramps, and nothing in the recommendation path may turn it into an applied
flag. Deriving a decision from it was built and falsified against the 91-asset population where
this branch is reached (references/lessons.md §41); the tests below encode the shape of that
result so it is not quietly rebuilt.
"""
import sys

import numpy as np
import pytest

sys.path.insert(0, "/Applications/Claude Code/Gif-Background-Remover/scripts")
from remove_gif_background import (  # noqa: E402
    build_art_palette,
    detect_fading_colors,
    strongest_background_ramp_candidate,
)

BG = (0, 0, 0)
CYAN = (1, 251, 255)


def _glow_frame(h=120, w=120, core=18, reach=40):
    """A solid core of one colour with a radial falloff toward black — an additive glow.

    Built as the exact arithmetic a GIF export performs when it flattens translucency
    (`bg + a*(C - bg)`), so the ramp lies ON the background-to-colour ray. That is what makes
    it the real positive rather than a shape that merely looks soft.
    """
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(yy - h / 2, xx - w / 2)
    a = np.clip((reach - d) / (reach - core), 0.0, 1.0)
    a[d <= core] = 1.0
    f = (np.asarray(BG, np.float32) + a[..., None] * (np.asarray(CYAN, np.float32) - np.asarray(BG, np.float32)))
    return f.round().astype(np.uint8)


def _hard_frame(h=120, w=120, r=30):
    """The same colour with NO ramp — a hard-edged disc. The negative class."""
    yy, xx = np.mgrid[0:h, 0:w]
    f = np.zeros((h, w, 3), np.uint8)
    f[np.hypot(yy - h / 2, xx - w / 2) <= r] = CYAN
    return f


def test_the_glow_fixture_is_invisible_to_the_existing_detector():
    """Non-vacuity: if detect_fading_colors already saw this, the candidate would be pointless.

    This is the whole premise of §41 — the colour is BOTH the solid core and the falloff, so it
    can never clear a gate asking that it be almost never solid.
    """
    frames = [_glow_frame()] * 4
    pal = build_art_palette(frames, BG)
    assert len(pal), "fixture produced no art palette"
    assert detect_fading_colors(frames, BG, pal) == set(), \
        "fixture no longer reproduces the blind spot the candidate exists for"


def test_a_ramp_is_reported_with_its_colour_and_its_faint_mass():
    frames = [_glow_frame()] * 4
    pal = build_art_palette(frames, BG)
    c = strongest_background_ramp_candidate(frames, BG, pal, min_px=100)
    assert c is not None, "a real ramp must be named"
    assert c['faint_px'] >= 100 and 0.0 < c['faint_fraction'] < 1.0
    assert c['color']


def test_a_hard_edged_shape_names_no_ramp():
    """The negative class at the same colour and the same background — only the ramp differs."""
    frames = [_hard_frame()] * 4
    pal = build_art_palette(frames, BG)
    assert strongest_background_ramp_candidate(frames, BG, pal, min_px=100) is None


def test_an_empty_palette_or_no_frames_is_safe():
    assert strongest_background_ramp_candidate([], BG, [(1, 2, 3)]) is None
    assert strongest_background_ramp_candidate([_glow_frame()], BG, []) is None
    assert strongest_background_ramp_candidate([_glow_frame()], BG, None) is None


def test_the_min_px_floor_actually_withholds():
    """A floor that nothing can fail is not a floor."""
    frames = [_glow_frame()] * 4
    pal = build_art_palette(frames, BG)
    assert strongest_background_ramp_candidate(frames, BG, pal, min_px=10**7) is None


def test_the_candidate_is_never_turned_into_an_applied_flag():
    """The guard that keeps §41's falsification from being quietly reversed.

    `--fade-color` may be NAMED in evidence; it must not appear in the suggested command line
    on the strength of a ramp candidate alone.
    """
    import remove_gif_background as m
    src = m.recommend.__doc__ or ''
    # Behavioural, not textual: the recommender builds its flag list from `flags`, and the
    # ramp candidate is read only where evidence is appended.
    import inspect
    body = inspect.getsource(m.recommend)
    for line in body.splitlines():
        if '_ramp' in line and 'flags.append' in line:
            pytest.fail(f"a ramp candidate is being turned into a flag: {line.strip()}")
