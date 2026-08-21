"""Falsifiers for the cheap-dense-pass frame NOMINATION, and for the crash it uncovered.

Fixtures are dicts in the shape `summarise_background_color_stability` returns, so this suite
depends on no corpus. The two tests that matter most are the two GUARDS, because both of them
exist because a real asset walked straight through the rule without them:

  * an UNVERIFIED verdict must nominate nothing. `recolored_frame_indexes` is populated from the
    raw per-frame comparison even when the verdict is None — measured on a real asset with
    `changes: null` ("there is no background colour for the animation to change") and 44 of 60
    frames listed as recoloured anyway.
  * an already-background-removed source must nominate nothing, for the same reason and via a
    cheap hint, because the authoritative flag cannot be computed before `sample_idxs` exists.
"""
import sys

import numpy as np
import pytest

sys.path.insert(0, "/Applications/Claude Code/Gif-Background-Remover/scripts")
from remove_gif_background import (  # noqa: E402
    BG_RECOLOR_COLLAPSE,
    MAX_NOMINATED_FRAMES,
    nominate_sample_frames,
    summarise_background_color_stability,
)


def _stability(**kw):
    base = dict(changes=True, recolored_frame_indexes=[],
                reference_coverage_frame_0=0.5, min_reference_coverage=0.5,
                min_reference_coverage_frame_index=0)
    base.update(kw)
    return base


def test_a_recoloured_frame_is_nominated():
    nom = nominate_sample_frames(_stability(recolored_frame_indexes=[11, 12, 13]), 200)
    assert [f['frame'] for f in nom] == [11, 12, 13]
    assert all('moved beyond tolerance' in f['reason'] for f in nom)


def test_a_stable_asset_nominates_nothing():
    """The negative class. Without this, "nomination works" and "nomination always fires" agree."""
    assert nominate_sample_frames(_stability(changes=False), 200) == []


def test_an_unverified_verdict_nominates_nothing():
    """GUARD 1 — the one a real asset walked through.

    A summary can carry recoloured frame indices AND a null verdict at the same time: the
    indices come from the raw comparison, the verdict from whether the question was answerable
    at all. Reading the indices without the verdict escalates the expensive pass on a question
    the summary already declared not applicable.
    """
    s = _stability(changes=None, recolored_frame_indexes=list(range(2, 46)))
    assert nominate_sample_frames(s, 60) == []


def test_an_already_background_removed_source_nominates_nothing():
    """GUARD 2 — same reasoning, delivered through the cheap hint.

    The authoritative `_src_bg_transparent` reads sampled frames, so it cannot be consulted
    before `sample_idxs` exists without a cycle. The hint stands in and governs only whether we
    bother nominating.
    """
    s = _stability(recolored_frame_indexes=[5, 6, 7])
    assert nominate_sample_frames(s, 200, source_bg_transparent=True) == []
    assert len(nominate_sample_frames(s, 200, source_bg_transparent=False)) == 3


def test_a_collapsed_reference_plane_nominates_its_worst_frame():
    """Fires even when nothing crosses the recolour bar — that is the point of the second rule."""
    s = _stability(recolored_frame_indexes=[], reference_coverage_frame_0=0.60,
                   min_reference_coverage=0.60 * BG_RECOLOR_COLLAPSE / 2,
                   min_reference_coverage_frame_index=77)
    nom = nominate_sample_frames(s, 200)
    assert [f['frame'] for f in nom] == [77]
    assert 'smallest' in nom[0]['reason']


def test_a_plane_that_merely_dips_is_not_nominated():
    """The negative class for the second rule, at the same value of the confound."""
    s = _stability(recolored_frame_indexes=[], reference_coverage_frame_0=0.60,
                   min_reference_coverage=0.55, min_reference_coverage_frame_index=77)
    assert nominate_sample_frames(s, 200) == []


def test_nominations_are_capped_and_thinned_across_the_span():
    """A long recolour run is ONE event; its middle is as informative as its start.

    Truncating to the first N would hand the expensive pass only the leading edge of a
    forty-frame recolour and call it covered.
    """
    s = _stability(recolored_frame_indexes=list(range(50, 90)))
    nom = nominate_sample_frames(s, 200)
    frames = [f['frame'] for f in nom]
    assert len(frames) <= MAX_NOMINATED_FRAMES
    assert frames[0] == 50 and frames[-1] == 89, frames
    assert len(set(frames)) == len(frames)


def test_a_frame_index_outside_the_animation_is_dropped():
    s = _stability(recolored_frame_indexes=[5, 999, -3])
    assert [f['frame'] for f in nominate_sample_frames(s, 200)] == [5]


def test_empty_and_missing_inputs_are_safe():
    assert nominate_sample_frames(None, 200) == []
    assert nominate_sample_frames({}, 200) == []
    assert nominate_sample_frames(_stability(recolored_frame_indexes=[1]), 0) == []


# --------------------------------------------------------------------------------------------
# The crash the nomination work uncovered: a PRE-EXISTING unhandled TypeError in the summary.
# --------------------------------------------------------------------------------------------

def _probe(corner, dist, cov):
    return {'corner_color': corner, 'distance_from_reference': dist,
            'reference_coverage': cov, 'corner_color_coverage': cov}


def test_a_partly_unreadable_scan_does_not_raise():
    """The exact shape that crashed `--analyze` on 3 real corpus assets.

    The existing guard bails only when FEWER than half the frames are readable. Between 50% and
    100% readable, an individual `distance_from_reference: None` reached `None > int` and raised
    a bare TypeError with no file name and no frame number — the same class §39 fixed for a
    different cause. Measured on 3 real corpus assets, each confirmed against the pre-fix script
    (the render harness's `no_output` list named 8, but only 3 were this bug — two overlapping
    failure lists are not the same list).
    """
    probes = [_probe('#ffffff', 0, 0.5)] * 6 + [_probe(None, None, 0.5)] * 4
    out = summarise_background_color_stability(probes)          # must not raise
    assert out['frames_unreadable'] == 4
    assert out['changes'] is False
    assert 'carry no colour to compare' in (out['unverified_reason'] or '')


def test_an_unreadable_frame_is_never_counted_as_a_recolour():
    """It is not evidence of a change, and it is not evidence of stability either."""
    probes = [_probe('#ffffff', 0, 0.50)] * 5 + [_probe(None, None, 0.0)] * 4
    out = summarise_background_color_stability(probes)
    assert out['recolored_frame_indexes'] == []
    assert out['frames_unreadable'] == 4


def test_a_real_recolour_still_fires_alongside_unreadable_frames():
    """The fix must not have bought its silence by disabling the rule."""
    probes = ([_probe('#ffffff', 0, 0.50)] * 5
              + [_probe(None, None, 0.0)] * 2
              + [_probe('#00ff00', 200, 0.001)] * 3)
    out = summarise_background_color_stability(probes)
    assert out['changes'] is True
    assert out['recolored_frame_indexes'] == [7, 8, 9]
    assert out['frames_unreadable'] == 2
