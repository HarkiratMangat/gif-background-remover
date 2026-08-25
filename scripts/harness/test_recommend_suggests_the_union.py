"""recommend() never suggested combining --protect-outline-color and --protect-region,
even after build_protected_mask/build_protected_masks_robust were changed this branch to
UNION the two rather than treat them as alternatives (references/lessons.md SS45, SS46's
sibling gif-deferred-list.md item filed 2026-08-25).

Since --recommend's suggested_command is what an autonomous --auto run takes verbatim, the
union capability the render pipeline already supports was functionally unreachable by any
unattended run -- only a human manually combining the flags by hand could use it.

Fixture is a REAL analyze() report captured from `local/Diors-builds Emojis/others/Cut
loop.gif` (the exact asset references/lessons.md SS26 documents as the original
partial_outline motivating case), not hand-constructed -- every field recommend() reads
elsewhere in the same function is present and internally consistent. Only the ONE field
under test (circle_region_safe) is mutated per case, so a failure here is about the new
branch, not about an incomplete synthetic report tripping some unrelated code path.
"""
import copy
import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import remove_gif_background as M

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, 'fixtures', 'cutloop_analyze_report.json')


def _report():
    return copy.deepcopy(json.load(open(FIXTURE)))


def _partial_outline_region(report):
    for r in report['candidate_regions']:
        if r.get('partial_outline'):
            return r
    raise AssertionError('fixture has no partial_outline region -- fixture is stale')


def test_real_fixture_has_circle_region_safe_false_as_captured():
    """Ground truth check: the real asset this fixture came from is circularity 0.38,
    NOT circle-safe -- confirms the fixture is unmodified before either test below
    mutates a copy of it, and is the negative control for the next test."""
    region = _partial_outline_region(_report())
    assert region['circle_region_safe'] is False
    assert region['circularity_ratio'] < 0.85


def test_partial_outline_with_unsafe_circle_does_not_get_a_region_backstop():
    report = _report()
    region = _partial_outline_region(report)
    assert region['circle_region_safe'] is False  # the real, captured value
    with patch.object(M, 'analyze', return_value=report):
        rec = M.recommend('unused-path-analyze-is-mocked.gif')
    cmd = rec['suggested_command'] or ''
    assert '--protect-outline-color' in cmd
    assert '--protect-region' not in cmd, (
        f'a poorly-fitting circle (circularity {region["circularity_ratio"]}) should not '
        f'be suggested as a backstop -- it would bleed past the true edge: {cmd}')


def test_partial_outline_with_safe_circle_gets_a_region_backstop_unioned_not_replaced():
    report = _report()
    region = _partial_outline_region(report)
    region['circle_region_safe'] = True
    region['circularity_ratio'] = 0.91
    with patch.object(M, 'analyze', return_value=report):
        rec = M.recommend('unused-path-analyze-is-mocked.gif')
    cmd = rec['suggested_command'] or ''
    assert '--protect-outline-color' in cmd, (
        f'the backstop must be ADDED alongside the outline colour, not replace it: {cmd}')
    assert region['partial_outline']['color'] in cmd
    assert f"--protect-region {region['suggested_protect_region']}" in cmd, (
        f'expected the backstop region flag in the suggested command: {cmd}')
    assert any('backstop' in n.lower() for n in rec['evidence']), (
        'the evidence text should explain why a region backstop was added')
