"""Falsifiers for the erosion COMPONENT protection -- the mirror of the tiny-removed-region exemption.

Every fixture is synthesised from numpy arrays, so this suite depends on no corpus and on nothing
an earlier session left on disk. The corpora the rule was measured on are gitignored; a test that
needs them is a test that stops running.

The tests that matter are not "does a thin stroke survive" -- that one would also pass for a rule
that simply disabled erosion. They are the pairs that separate a real per-component exemption from
a broken one:

  * a LARGE silhouette in the same frame must still lose its outer ring. Without this, "protection
    works" and "erosion is off" are the same observation.
  * SPECKLE under the size floor must still be erased. It is the negative class at the same value
    of the confound -- it is just as thin and just as short-lived as the stroke, and differs only
    in size, which is the one thing the rule is allowed to use.
  * the protection must fire on a frame the DIAGNOSTIC never samples. check_erosion_damage looks at
    up to 40 frames; a protection that inherited that sampling would keep a stroke on some frames
    and erase it on others, turning a uniform loss into a flicker.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, "/Applications/Claude Code/Gif-Background-Remover/scripts")
from remove_gif_background import (  # noqa: E402
    check_erosion_damage,
    erode_alpha_edge,
    erode_alpha_edge_protecting_damaged_components,
    find_erosion_damaged_components,
    find_tiny_removed_regions,
)


def _canvas(h=80, w=80):
    return np.zeros((h, w), dtype=np.uint8)


def _blob(a, y0, y1, x0, x1, value=255):
    a[y0:y1, x0:x1] = value
    return a


def frame_with_stroke_and_blob():
    """A 30x30 solid blob (survives a 1px trim) plus a 2px-wide, 30px-long stroke (does not).

    The stroke is 60px, comfortably over the 25px floor, and 2px wide -- a 1px 8-connected
    erosion leaves exactly nothing of it, which is the pokeball-rim geometry from
    `Starters!.gif` reduced to its essentials.
    """
    a = _canvas()
    _blob(a, 5, 35, 5, 35)      # 900px, thick
    _blob(a, 50, 52, 10, 40)    # 60px, 2px wide -> erosion kills it
    return a


def test_thin_component_is_erased_without_protection():
    """The defect itself. If this ever stops failing, the fixture no longer reproduces it."""
    a = frame_with_stroke_and_blob()
    out = erode_alpha_edge([a], iterations=1)[0]
    assert out[50:52, 10:40].sum() == 0, "fixture does not reproduce the defect"
    assert out[5:35, 5:35].any(), "fixture's thick blob should survive a 1px trim"


def test_thin_component_survives_with_protection():
    a = frame_with_stroke_and_blob()
    out = erode_alpha_edge_protecting_damaged_components([a], 1)[0]
    assert np.array_equal(out[50:52, 10:40], a[50:52, 10:40]), \
        "protected component must come back at its exact pre-erosion pixels"


def test_large_component_is_still_eroded():
    """Separates "the component was protected" from "erosion was switched off"."""
    a = frame_with_stroke_and_blob()
    out = erode_alpha_edge_protecting_damaged_components([a], 1)[0]
    assert out[5, 5] == 0 and out[34, 34] == 0, "the thick blob's outer ring must still go"
    assert out[10:30, 10:30].all(), "its interior must be untouched"


def test_speckle_below_the_size_floor_is_still_erased():
    """The negative class at the same value of the confound: just as thin, only smaller.

    Dither speckle along a feathered edge is what edge cleanup exists to remove. A rule that
    protects everything erosion erases would protect this too, and would be indistinguishable
    from no erosion at all on a feathered asset.
    """
    a = _canvas()
    _blob(a, 5, 35, 5, 35)
    _blob(a, 60, 62, 60, 68)    # 16px, under the 25px floor
    out = erode_alpha_edge_protecting_damaged_components([a], 1)[0]
    assert out[60:62, 60:68].sum() == 0, "sub-floor speckle must not be protected"


def test_partially_surviving_component_is_left_alone():
    """A component that keeps most of itself is a normal ring bite, not damage.

    Harkirat's product call on `gift_ORIGINAL.gif` and `explosion_ORIGINAL.gif` was that a plain
    1px ring bite is acceptable; only near-total loss of a component is the defect.
    """
    a = _canvas()
    _blob(a, 5, 35, 5, 35)      # a lone thick blob: 900px -> 784px, 87% survival
    out = erode_alpha_edge_protecting_damaged_components([a], 1)[0]
    plain = erode_alpha_edge([a], iterations=1)[0]
    assert np.array_equal(out, plain), "a component above the survival bar must be untouched"


def test_disabled_reproduces_the_unprotected_result_exactly():
    a = frame_with_stroke_and_blob()
    off = erode_alpha_edge_protecting_damaged_components([a], 1, enabled=False)[0]
    plain = erode_alpha_edge([a], iterations=1)[0]
    assert np.array_equal(off, plain)


def test_zero_iterations_is_a_no_op():
    """scipy's binary_erosion treats iterations=0 as "erode to convergence" -- i.e. to nothing.

    erode_alpha_edge's own docstring records this as a shipped bug that erased a real icon. Any
    new erosion entry point has to carry the same guard rather than inherit the trap.
    """
    a = frame_with_stroke_and_blob()
    out = erode_alpha_edge_protecting_damaged_components([a], 0)[0]
    assert np.array_equal(out, a)


def test_partial_alpha_is_restored_at_its_original_value():
    """Restoration writes the pre-erosion VALUES back, not a flat 255.

    On WebP/AVIF a thin stroke can legitimately sit at partial alpha; restoring it as opaque
    would be a different defect wearing this fix's clothes.
    """
    a = _canvas()
    _blob(a, 5, 35, 5, 35)
    _blob(a, 50, 52, 10, 40, value=120)
    out = erode_alpha_edge_protecting_damaged_components([a], 1)[0]
    assert set(np.unique(out[50:52, 10:40]).tolist()) == {120}


def test_protection_fires_on_a_frame_the_diagnostic_never_samples():
    """The flicker falsifier, and the reason this does not reuse check_erosion_damage's sampling.

    check_erosion_damage samples at most 40 frames. If the protection inherited that spread, a
    stroke present on every frame would be kept on the sampled ones and erased on the rest --
    a uniform loss converted into a flicker, which is worse than the defect being fixed.
    """
    n = 60
    sampled = set(np.linspace(0, n - 1, 40).astype(int).tolist())
    unsampled = [i for i in range(n) if i not in sampled]
    assert unsampled, "fixture assumes 40 samples cannot cover 60 frames"
    target = unsampled[0]

    frames = []
    for i in range(n):
        a = _canvas()
        _blob(a, 5, 35, 5, 35)
        if i == target:
            _blob(a, 50, 52, 10, 40)
        frames.append(a)

    out = erode_alpha_edge_protecting_damaged_components(frames, 1)
    assert np.array_equal(out[target][50:52, 10:40], frames[target][50:52, 10:40]), \
        "a component on an unsampled frame must be protected too"
    # And the diagnostic genuinely cannot see that frame, which is what makes the test non-vacuous.
    assert target not in {d['frame'] for d in check_erosion_damage(
        frames, erode_alpha_edge(frames, iterations=1))}


def test_protection_leaves_the_diagnostic_with_nothing_to_report():
    """Post-condition: the fix uses the warning's own selection rule, so the warning must fall silent.

    This is the invariant that makes the surviving `NOTE:` branch in process() a bug report rather
    than advice -- if the two ever disagree, one of them is wrong.
    """
    frames = [frame_with_stroke_and_blob() for _ in range(3)]
    before = check_erosion_damage(frames, erode_alpha_edge(frames, iterations=1))
    assert before, "fixture must trip the diagnostic before the fix"
    after = check_erosion_damage(
        frames, erode_alpha_edge_protecting_damaged_components(frames, 1))
    assert after == [], f"protection left {len(after)} finding(s) the diagnostic still reports"


def test_a_tiny_removed_region_stays_removed():
    """The two exemptions are disjoint and must not undo each other.

    A tiny removed region is alpha == 0; a protected component is alpha > 0. Restoring the latter
    must not resurrect the former, which is punched back to transparent after the erosion.
    """
    a = _canvas()
    _blob(a, 5, 45, 5, 45)
    a[24:26, 24:26] = 0          # a 4px enclosed gap, the tiny-region case
    _blob(a, 60, 62, 10, 40)     # and a thin stroke, the component case
    tiny = find_tiny_removed_regions([a], max_size=10)
    assert tiny[0][24:26, 24:26].all(), "fixture's tiny region was not detected"
    out = erode_alpha_edge_protecting_damaged_components([a], 1, tiny)[0]
    assert out[24:26, 24:26].sum() == 0, "the tiny removed region must stay removed"
    assert np.array_equal(out[60:62, 10:40], a[60:62, 10:40]), "the stroke must still be protected"


def test_masks_mark_pre_erosion_pixels_only():
    """find_erosion_damaged_components returns the component's OWN pixels, nothing dilated."""
    a = frame_with_stroke_and_blob()
    eroded = erode_alpha_edge([a], iterations=1)[0]
    mask = find_erosion_damaged_components([a], [eroded])[0]
    assert mask.sum() == 60, f"expected exactly the 60px stroke, got {int(mask.sum())}px"
    assert not mask[(a == 0)].any(), "mask must not mark anything that was transparent"


def test_an_empty_frame_is_handled():
    a = _canvas()
    out = erode_alpha_edge_protecting_damaged_components([a], 1)[0]
    assert out.sum() == 0
    assert find_erosion_damaged_components([a], [a])[0].sum() == 0


def test_log_reports_the_pixels_it_saved():
    """An autonomous run reads stderr; a protection that acts silently cannot be audited."""
    a = frame_with_stroke_and_blob()
    log = []
    erode_alpha_edge_protecting_damaged_components([a], 1, log=log)
    assert log and "protected 60 pixel(s)" in log[0], log
    quiet = []
    erode_alpha_edge_protecting_damaged_components([_blob(_canvas(), 5, 35, 5, 35)], 1, log=quiet)
    assert quiet == [], "nothing protected must log nothing"


# --------------------------------------------------------------------------------------------
# The EARNED erosion ceiling -- level 2 is reachable, but only for an asset whose own curve
# shows a two-pixel fringe. These are curve-shape tests, so they need no fixtures at all.
# --------------------------------------------------------------------------------------------
from remove_gif_background import (  # noqa: E402
    EROSION_KNEE_MIN_GAIN,
    EROSION_MAX_AUTO,
    EROSION_MAX_AUTO_KNEE,
    calibrate_edge_cleanup_erosion,
    earned_erosion_ceiling,
)


def test_a_smooth_monotone_curve_does_not_earn_level_2():
    """The NEGATIVE class, and the one that matters.

    A curve that keeps falling is the normal case on soft-edged art -- SS37.4 measured 37 of 186
    assets sitting at 2 or 3 under the old unbounded rule. If "level 2 reads lower" were enough,
    this rule would be a blanket cap raise wearing a discriminator's clothes.
    """
    assert earned_erosion_ceiling({0: 0.90, 1: 0.30, 2: 0.10, 3: 0.05}) == EROSION_MAX_AUTO


def test_a_convex_curve_earns_level_2():
    """The real signature: the second pixel removes more than the first did."""
    assert earned_erosion_ceiling({0: 0.95, 1: 0.69, 2: 0.00, 3: 0.00}) == EROSION_MAX_AUTO_KNEE


def test_a_convex_but_tiny_knee_does_not_earn_it():
    """A flat curve's noise must not read as a knee."""
    tiny = EROSION_KNEE_MIN_GAIN / 5
    assert earned_erosion_ceiling({0: 0.50, 1: 0.499, 2: 0.499 - tiny, 3: 0.499 - tiny}) \
        == EROSION_MAX_AUTO


def test_an_unmeasurable_level_is_not_evidence_of_a_knee():
    assert earned_erosion_ceiling({0: 0.9, 1: 0.5, 2: None, 3: None}) == EROSION_MAX_AUTO
    assert earned_erosion_ceiling({}) == EROSION_MAX_AUTO
    assert earned_erosion_ceiling(None) == EROSION_MAX_AUTO


def test_string_keys_from_a_json_table_are_accepted():
    """auto_run reads this off a diagnostics table that may have round-tripped through JSON."""
    assert earned_erosion_ceiling({'0': 0.95, '1': 0.69, '2': 0.0, '3': 0.0}) == EROSION_MAX_AUTO_KNEE


def test_level_3_is_never_earned():
    """However convex the curve gets, the ceiling moves by exactly one step."""
    assert earned_erosion_ceiling({0: 1.0, 1: 0.99, 2: 0.5, 3: 0.0}) == EROSION_MAX_AUTO_KNEE


class _Curve:
    """Drive calibrate_edge_cleanup_erosion off a chosen curve without rendering anything.

    The calibrator measures each candidate through measure_outer_ring_background_fraction, so a
    fake frame set cannot express an arbitrary curve. Monkeypatching that one measurement is what
    lets these tests assert on the SELECTION rule -- which is the part the knee changes -- rather
    than re-testing the metric.
    """

    def __init__(self, curve):
        self.curve = curve
        self.calls = 0

    def __call__(self, rgb, alpha, bg, pal, opaque_min=250):
        # `alpha` carries the candidate level in its first pixel; see _calibrate below.
        return self.curve[int(alpha[0, 0])]


def _calibrate(monkeypatch, curve, **kw):
    import remove_gif_background as m
    levels = sorted(curve)

    def fake_erode(alpha_frames, iterations, tiny_masks=None, **_):
        return [np.full((4, 4), iterations, dtype=np.uint8) for _ in alpha_frames]

    monkeypatch.setattr(m, 'erode_alpha_edge_protecting_damaged_components', fake_erode)
    monkeypatch.setattr(m, 'measure_outer_ring_background_fraction', _Curve(curve))
    frames = [np.zeros((4, 4), dtype=np.uint8)]
    log = []
    best, table = m.calibrate_edge_cleanup_erosion(
        frames, frames, (0, 0, 0), [(255, 255, 255)], candidates=tuple(levels), log=log, **kw)
    return best, table, log


def test_calibrator_picks_2_on_a_convex_curve(monkeypatch):
    best, table, log = _calibrate(monkeypatch, {0: 0.95, 1: 0.69, 2: 0.00, 3: 0.00})
    assert best == 2, (best, table)
    assert any('CONVEX at 2' in l for l in log), log


def test_calibrator_still_stops_at_1_on_a_smooth_curve(monkeypatch):
    """The regression guard for the whole EROSION_MAX_AUTO finding."""
    best, table, log = _calibrate(monkeypatch, {0: 0.90, 1: 0.30, 2: 0.10, 3: 0.05})
    assert best == 1, (best, table)
    assert not any('CONVEX' in l for l in log), log


def test_a_knee_cannot_promote_an_asset_that_did_not_want_level_1(monkeypatch):
    """0 -> 2 must be unreachable: the extra step is earned only from the routine ceiling.

    Curve: 0 and 1 are within the 0.02 tolerance of each other so the routine pick is 0, and 2
    is far below both. Without the `best == max_selectable` condition this asset would jump two
    levels on a knee it never earned by needing one pixel in the first place.
    """
    best, table, log = _calibrate(monkeypatch, {0: 0.200, 1: 0.199, 2: 0.000, 3: 0.000})
    assert best == 0, (best, table)


def test_every_level_is_still_measured_even_when_not_selectable(monkeypatch):
    """The table is the evidence a human audits; restricting the SEARCH must not restrict it."""
    best, table, log = _calibrate(monkeypatch, {0: 0.90, 1: 0.30, 2: 0.10, 3: 0.05})
    assert sorted(table) == [0, 1, 2, 3] and all(v is not None for v in table.values())


# --------------------------------------------------------------------------------------------
# Edge SOFTENING -- the ramp put back on a deep trim. 8-bit-alpha containers only.
# --------------------------------------------------------------------------------------------
from remove_gif_background import soften_alpha_edge  # noqa: E402


def test_softening_puts_a_ramp_on_the_boundary_and_nowhere_else():
    a = _blob(_canvas(), 10, 40, 10, 40)
    out = soften_alpha_edge([a], 1)[0]
    assert out[10, 10] == 128, out[10, 10]        # boundary ring: depth 1 -> half alpha
    assert out[12, 12] == 255                      # depth >= 2: untouched
    assert out[0, 0] == 0                          # transparent stays transparent


def test_softening_never_removes_a_pixel():
    """It softens an edge; it must not do erosion's job as a side effect."""
    a = frame_with_stroke_and_blob()
    out = soften_alpha_edge([a], 1)[0]
    assert np.count_nonzero(out) == np.count_nonzero(a), \
        "softening turned an opaque pixel fully transparent"


def test_a_protected_component_is_exempt_from_softening():
    """A 2px rim lies ENTIRELY within a 1px ramp, so ramping it would undo the protection.

    Without the exemption the whole component drops to half opacity — the fix that just saved
    it from erosion would be quietly half-undone by the step that follows it.
    """
    a = frame_with_stroke_and_blob()
    eroded = erode_alpha_edge([a], iterations=1)[0]
    protect = find_erosion_damaged_components([a], [eroded])
    plain = soften_alpha_edge([a], 1)[0]
    assert plain[50, 10] < 255, "fixture must show the stroke being ramped without the exemption"
    exempt = soften_alpha_edge([a], 1, exempt_masks=protect)[0]
    assert np.array_equal(exempt[50:52, 10:40], a[50:52, 10:40])


def test_zero_radius_is_a_no_op():
    a = frame_with_stroke_and_blob()
    assert np.array_equal(soften_alpha_edge([a], 0)[0], a)


def test_softening_scales_alpha_rather_than_replacing_it():
    """A partial-alpha source pixel must not be promoted to opaque by the ramp."""
    a = _canvas()
    _blob(a, 10, 40, 10, 40, value=100)
    out = soften_alpha_edge([a], 1)[0]
    assert out[12, 12] == 100 and out[10, 10] == 50


def test_an_empty_frame_survives_softening():
    a = _canvas()
    assert soften_alpha_edge([a], 1)[0].sum() == 0
