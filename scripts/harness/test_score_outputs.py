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

SCRIPT = os.path.join(ROOT, 'scripts', 'remove_gif_background.py')

ASSETS = ('galaxy', 'growth', 'hurricane', 'rocket', 'satellite')

# ⚠️ Six tests here USED to read fixed `/tmp/*.webp` paths that the suite never created.
# They passed only because the session that wrote them happened to have rendered those files
# by hand minutes earlier. On a fresh machine, after a reboot, or after /tmp is cleaned they
# fail with FileNotFoundError -- which reads as a regression and is not one. That is the
# "fixture that only works because of session state" trap, shipped by the very session that
# spent the day catching that class of error.
#
# `rendered()` fixes it and is deliberately CACHED rather than re-rendering every run: a
# render is 20-60s and six of them would put minutes on every invocation. The cache key is
# the SHA of remove_gif_background.py, so any edit to the product -- which is what these
# tests exist to police -- invalidates every entry automatically. A cache that a code change
# cannot invalidate is worse than no cache; this one cannot serve a stale answer.
_RENDER_CACHE = os.path.join(ROOT, 'local', '.test-renders')


def _script_sha():
    import hashlib
    with open(SCRIPT, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def rendered(asset, *flags):
    """Path to `asset` rendered through the real CLI with `flags`, rendering on first use.

    Keyed by script SHA, so it re-renders whenever the product changes and never otherwise.
    """
    import subprocess
    slug = asset.replace('.gif', '') + ('_' + '_'.join(
        f.lstrip('-').replace('-', '') for f in flags) if flags else '')
    d = os.path.join(_RENDER_CACHE, _script_sha())
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, slug + '.webp')
    if not os.path.exists(out):
        r = subprocess.run([sys.executable, SCRIPT, _p(asset), out, '--auto', *flags],
                           capture_output=True, text=True)
        assert r.returncode == 0 and os.path.exists(out), \
            f'rendering {asset} {flags} failed rc={r.returncode}\n{r.stderr[-2000:]}'
    return out


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


# --------------------------------------------------------------- Task 2: truncating GIF

def _analyze(path):
    import json
    import subprocess
    r = subprocess.run([sys.executable, SCRIPT, path, '--analyze'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def test_all_transparent_frame_is_detected_before_render():
    """An all-transparent output frame silently truncates a GIF at that frame
    (Pillow 12.3.0). growth.gif has one and shipped 85 of 123 frames."""
    a = _analyze(_p('growth.gif'))
    assert a.get('has_fully_transparent_frame') is True
    assert a.get('fully_transparent_frames') == [85], a.get('fully_transparent_frames')


def test_an_asset_without_a_blank_frame_reports_false():
    """The negative half. A detector that says True on everything is not a detector."""
    a = _analyze(_p('rocket.gif'))
    assert a.get('has_fully_transparent_frame') is False
    assert a.get('fully_transparent_frames') == []


def test_recommend_steers_away_from_gif_on_a_blank_frame():
    """An autonomous run takes --recommend's flags verbatim, so the container decision has
    to be IN the recommendation, not only in a post-render warning."""
    import subprocess
    r = subprocess.run([sys.executable, SCRIPT, _p('growth.gif'), '--recommend'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert 'NOT GIF' in r.stdout, r.stdout[:3000]


# ------------------------------------------------- Task 3: "incidental" over a large region

def test_large_enclosed_region_is_not_incidental():
    """growth.gif: --recommend called the rocket's white BODY incidental background
    at enclosure_ratio 0.825, and two of three trial agents deleted it."""
    import subprocess
    r = subprocess.run([sys.executable, SCRIPT, _p('growth.gif'), '--recommend'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert 'looks incidental, leaving as background' not in r.stdout, \
        'a large interior region is still being dismissed as incidental'
    assert '--protect-outline-color' in r.stdout, \
        'the region is called design but nothing was recommended to protect it with'


def test_a_genuine_background_pocket_is_still_left_alone():
    """The negative half, and it is the one that matters: 9a4177e8 id5 is the gap between a
    character's two legs at ratio 0.625 -- 0.025 away in ratio from rocket's wing panel,
    which IS design. Only the AREA separates them, which is the whole point of the change.
    A rule that protects both has not fixed anything, it has moved the error."""
    import json
    import subprocess
    src = os.path.join(ROOT, 'local', 'Diors-builds Emojis', 'others',
                       '9a4177e82f1a333ef64066f7a7529eb2.gif')
    a = json.loads(subprocess.run([sys.executable, SCRIPT, src, '--analyze'],
                                  capture_output=True, text=True).stdout)
    reg = next(r for r in a['candidate_regions'] if r['id'] == 5)
    assert reg['enclosure_ratio'] >= 0.6, reg          # the ratio really is high
    assert reg['likely_intentional_design'] is False, reg


def test_growth_interior_survives_a_real_render():
    """End to end through the real CLI, graded by the Task 1 scorer."""
    import subprocess
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), 'task3_growth.webp')
    r = subprocess.run([sys.executable, SCRIPT, _p('growth.gif'), out, '--auto'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    s = S.score(_p('growth.gif'), out)
    assert s['interior_kept_worst'] > 0.95, s


# ------------------------------------ a worst-frame FRACTION needs its denominator

def test_worst_frame_fraction_reports_its_own_denominator():
    """growth's rocket leaves the canvas, so its worst art frame holds almost nothing and a
    1px erosion reads as "21% of the artwork destroyed". Harkirat caught that number on its
    way into a release decision. The scorer must make the artifact visible on its face:
    a collapsed denominator, and a loss no bigger than one perimeter ring."""
    r = S.score(_p('growth.gif'), rendered('growth.gif', '--edge-cleanup-erosion', '1'))
    assert r['art_kept_worst'] < 0.90, r          # the alarming fraction is real...
    assert r['art_frame_share_at_worst'] < 0.05, r  # ...on a frame holding <5% of the art
    assert r['art_lost_over_perimeter'] <= 1.1, r   # ...and the loss is one perimeter ring


def test_a_full_size_frame_is_not_explained_away():
    """The negative half. On assets whose worst frame is full-size the share must be HIGH,
    or the new field would excuse every result instead of discriminating."""
    for f in ('rocket', 'satellite'):
        r = S.score(_p(f'{f}.gif'), rendered(f'{f}.gif', '--edge-cleanup-erosion', '1'))
        assert r['art_frame_share_at_worst'] > 0.9, (f, r)
        assert r['art_lost_over_perimeter'] <= 1.1, (f, r)


# ------------------------------------------------------- paper-plane, supplied 2026-08-20

def test_paper_plane_reproduces_both_2026_08_20_p1_defects():
    """Harkirat supplied this after seeing v6 give "nearly the same result" as v3.x: the
    plane exits the canvas and the animation appeared to freeze mid-flight. It exercises
    BOTH P1 fixes from the same day, independently of the trial assets."""
    a = _analyze(_p('paper-plane.gif'))
    assert a['has_fully_transparent_frame'] is True
    assert a['fully_transparent_frames'] == [41], a['fully_transparent_frames']
    # its two design regions sit UNDER the old 0.9 bar -- the pre-2026-08-20 code
    # would have called them incidental background and deleted them
    big = [r for r in a['candidate_regions'] if r['region_canvas_fraction'] >= 0.025]
    assert len(big) == 2, big
    assert all(0.5 <= r['enclosure_ratio'] < 0.9 for r in big), big
    assert all(r['likely_intentional_design'] for r in big), big


def test_interior_loss_reports_its_own_shape():
    """`interior_kept_worst` is a SCREEN, not a verdict. paper-plane reads 0.556 because the
    removed pixels are the COUNTER of a closed loop -- a hole a transparent sticker should
    see through. The fields must separate that from real destruction of a body."""
    ok = S.score(_p('paper-plane.gif'), rendered('paper-plane.gif'))
    bad = S.score(_p('growth.gif'), _p('agent-2-detailed', 'growth.webp'))
    assert ok['interior_lost_largest_component'] < 5000, ok
    assert bad['interior_lost_largest_component'] > 10000, bad
    assert bad['interior_kept_worst'] < ok['interior_kept_worst']


# ------------------------------- retained background: a fade, a ghost, or a real miss

def test_a_preserved_fade_is_not_reported_as_leftover_background():
    """in-love.gif (Harkirat, 2026-08-20): hearts fade in and out behind a smiley, each
    carrying a darker outline AND a lighter interior that both fade. `bg_removed_worst`
    reads 0.931 -- which sounds like 7% of the background missed. Every one of those 13,622
    pixels is translucent and its alpha tracks the source's own paleness."""
    r = S.score(_p('in-love.gif'), rendered('in-love.gif'))
    assert r['bg_removed_worst'] < 0.99                    # the strict figure fires...
    assert r['bg_not_opaque_worst'] > 0.99, r              # ...nothing is kept solid...
    assert r['bg_kept_fade_correlation'] > 0.80, r         # ...and it tracks the fade


def test_a_ghosted_output_is_still_condemned():
    """The negative half, and the reason neither supporting field can stand alone. The
    known-broken hurricane output keeps nothing solid (so the opacity screen passes it) AND
    its retained alpha tracks paleness at 0.957, BETTER than the correct fade's 0.943 --
    because `--recover-fade-alpha` derives alpha from paleness, so its failure is faithful
    to paleness by construction. What condemns it is the AMOUNT: it retains 61% of the
    background where the correct fade retains 6.9%."""
    r = S.score(_p('hurricane.gif'), _p('agent-3-expert', 'hurricane_transparent.webp'))
    assert r['bg_not_opaque_worst'] > 0.99, r        # the opacity screen passes it
    assert r['bg_kept_fade_correlation'] > 0.80, r   # and so does the correlation
    assert r['bg_removed_worst'] < 0.50, r           # only the magnitude condemns it


def test_the_two_fades_are_separated_by_amount_not_by_shape():
    """Locks the falsified hypothesis in place so it is not re-derived: on the correct fade
    and the ghost, both supporting fields agree; only bg_removed_worst separates them."""
    good = S.score(_p('in-love.gif'), rendered('in-love.gif'))
    ghost = S.score(_p('hurricane.gif'), _p('agent-3-expert', 'hurricane_transparent.webp'))
    assert good['bg_not_opaque_worst'] > 0.99 and ghost['bg_not_opaque_worst'] > 0.99
    assert good['bg_kept_fade_correlation'] > 0.80 and ghost['bg_kept_fade_correlation'] > 0.80
    assert good['bg_removed_worst'] - ghost['bg_removed_worst'] > 0.4, (good, ghost)


def test_a_solid_background_wedge_is_caught_by_opacity():
    """The third failure mode: growth/agent-3 holds a fully opaque background wedge."""
    r = S.score(_p('growth.gif'), _p('agent-3-expert', 'growth_transparent.webp'))
    assert r['bg_not_opaque_worst'] < 0.99, r


def test_for_you_survives_an_outline_that_is_recoloured_mid_animation():
    """for-you.gif (Harkirat, 2026-08-20): the navy outline turns yellow, so navy drops
    below 20% of its peak on 37 CONSECUTIVE frames of 144. `--recommend` must not pick a
    colour that vanishes -- it picks the heart fill, present in all 144."""
    import subprocess
    out = subprocess.run([sys.executable, SCRIPT, _p('for-you.gif'), '--recommend'],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert '--protect-outline-color c83c78' in out.stdout, out.stdout[:1500]
    r = S.score(_p('for-you.gif'), rendered('for-you.gif'))
    assert r['interior_kept_worst'] > 0.99 and r['bg_removed_worst'] > 0.99, r
