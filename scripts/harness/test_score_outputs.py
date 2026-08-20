"""Falsifier suite for score_outputs.py.

Every test here encodes a defect that ACTUALLY SHIPPED and that the previous grader scored
as clean, plus two controls proving the grader is not simply failing everything. A test
that passes trivially is worse than no test: the first draft of `fade_correlation` returned
exactly 1.000 on all seven trial outputs including the broken one, and only printing the
dict revealed it.

Paths are anchored to the repo root from __file__, never to the cwd -- the plan that
specified these tests mixed root-relative and `../../`-relative paths in the same file,
which resolves differently depending on where pytest is invoked from.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRIAL = os.path.join(ROOT, 'local', 'Corpus Trial Gifs')

import score_outputs as S  # noqa: E402

ASSETS = ('galaxy', 'growth', 'hurricane', 'rocket', 'satellite')


def _p(*parts):
    return os.path.join(TRIAL, *parts)


# --------------------------------------------------------------------------- defects

def test_fade_bug_is_detected():
    """All three agents produced BYTE-IDENTICAL hurricane output and human review called it
    a disaster. A grader that scores it clean cannot validate a fix."""
    r = S.score(_p('hurricane.gif'), _p('agent-3-expert', 'hurricane_transparent.webp'))
    assert r['fade_coherence'] is not None, 'hurricane must be GRADEABLE, not unverified'
    assert r['fade_coherence'] < 0.90, (
        f"fade_coherence {r['fade_coherence']:.3f} — the source colour ramps smoothly and "
        f"the output alpha holds flat then cliffs; a score this high means the measure "
        f"cannot see the defect")


def test_worst_frame_not_mean():
    """growth/agent-3 holds an opaque background wedge on 16 consecutive frames.
    A mean over sampled frames reads 99.9% and hides it."""
    r = S.score(_p('growth.gif'), _p('agent-3-expert', 'growth_transparent.webp'))
    assert r['bg_removed_worst'] < 0.98, (
        f"bg_removed_worst {r['bg_removed_worst']:.4f} — this asset has a known 16-frame "
        f"background wedge; a worst-frame measure must show it")


def test_hurricane_edge_and_background_are_condemned():
    """Before the fade axis is even consulted, hurricane must fail on two model-neutral
    measures. The OLD grader gave this file 100% on all three agents."""
    r = S.score(_p('hurricane.gif'), _p('agent-3-expert', 'hurricane_transparent.webp'))
    assert r['bg_removed_worst'] < 0.50, r
    assert r['edge_cleanliness'] < 0.20, r


def test_interior_loss_is_detected_on_the_asset_two_agents_destroyed():
    """agents 1 and 2 followed `enclosure_ratio 0.825 looks incidental` and deleted 83% of
    growth's interior white while reporting success. `interior_kept_worst` is the measure
    Task 3's acceptance depends on, so it must be able to FAIL on exactly that file."""
    r = S.score(_p('growth.gif'), _p('agent-2-detailed', 'growth.webp'))
    assert r['interior_kept_worst'] < 0.50, (
        f"interior_kept_worst {r['interior_kept_worst']:.4f} — agent 2's growth output is "
        f"the known interior-deletion case; a measure that passes it cannot validate Task 3")


# --------------------------------------------------------------------------- controls

def test_both_legitimate_fade_models_pass():
    """fade_coherence must NOT pre-judge the open product question of whether a pale shape
    should become translucent or stay opaque. Both synthetic answers must score 1.0, or the
    measure would condemn whichever one Task 6 chooses."""
    for name in ASSETS:
        for label, model in (('ideal-ramp', S.IDEAL_RAMP), ('binary-cut', S.BINARY_CUT)):
            r = S.score(_p(f'{name}.gif'), alpha_override=model)
            if r['fade_coherence'] is None:
                continue                      # no ramping component: nothing to grade
            assert r['fade_coherence'] > 0.99, f'{name} {label} -> {r}'


def test_a_known_good_file_is_not_flagged():
    """The grader must not simply fail everything."""
    r = S.score(_p('satellite.gif'), _p('agent-3-expert', 'satellite_transparent.webp'))
    assert r['interior_kept_worst'] > 0.95, r
    assert r['edge_cleanliness'] > 0.05, r
    assert r['bg_removed_worst'] > 0.95, r


def test_ungradeable_fade_reports_unverified_not_a_pass():
    """An asset whose components do not ramp has no fade to grade. It must come back None,
    never 1.0 — a vacuous pass is the exact failure this file replaced."""
    r = S.score(_p('galaxy.gif'), _p('agent-3-expert', 'galaxy_transparent.webp'))
    assert r['fade_coherence'] is None and r['fade_model'] is None, r
