"""Falsifiers for the --target-kb resolution floor (plan Task 1).

The v6 trial delivered a 120x128 megaphone against a stated "at least 128px
wide" -- the byte cap silently outranked a resolution the user had required.
`--resize-max-dim` already encoded the right reasoning as an exact PIN; these
three flags are the same requirement with a weaker shape, a floor.

⚠️ A bare `--min-dimension` constrains the SHORTER side. Harkirat's call
2026-08-23: for a sticker or emoji slot that is the safer reading of "at least
this big", and it is the stricter one -- a 600x100 asset passes `--min-width
128` and fails `--min-dimension 128`. `--min-width` expresses the literal ask.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import remove_gif_background as R  # noqa: E402

LADDER = (1.0, 0.75, 0.5, 0.375, 0.25)


class _Args:
    def __init__(self, **kw):
        self.resize_max_dim = None
        self.pixel_art = False
        self.min_width = None
        self.min_height = None
        self.min_dimension = None
        self.__dict__.update(kw)


def _scales_for(args, width, height):
    return R.scales_for_fit(args, width, height)


def test_no_floor_keeps_the_full_scale_ladder():
    """What STAYED: the common path must be untouched by this feature."""
    assert _scales_for(_Args(), 482, 513) == LADDER


def test_a_min_dimension_drops_only_the_rungs_that_violate_it():
    # 482x513: 0.375 -> 181x192 (ok), 0.25 -> 121x128 (shorter side 121 < 128).
    assert _scales_for(_Args(min_dimension=128), 482, 513) == (1.0, 0.75, 0.5, 0.375)


def test_the_bare_floor_is_measured_on_the_SHORTER_side_not_the_width():
    # 600x100: every rung passes a 128 WIDTH test; none passes a shorter-side one.
    assert _scales_for(_Args(min_dimension=128), 600, 100) == (1.0,)
    assert _scales_for(_Args(min_width=128), 600, 100) == (1.0, 0.75, 0.5, 0.375, 0.25)


def test_min_width_expresses_the_literal_ask():
    # "at least 128px wide, aspect preserved": 482*0.25 = 121 < 128, 482*0.375 = 181.
    assert _scales_for(_Args(min_width=128), 482, 513) == (1.0, 0.75, 0.5, 0.375)


def test_min_height_is_the_mirror():
    assert _scales_for(_Args(min_height=400), 482, 513) == (1.0,)
    assert _scales_for(_Args(min_width=400), 482, 513) == (1.0,)


def test_two_flags_together_take_the_TIGHTER_of_the_two():
    loose = _scales_for(_Args(min_width=128), 482, 513)
    tight = _scales_for(_Args(min_height=300), 482, 513)
    both = _scales_for(_Args(min_width=128, min_height=300), 482, 513)
    assert both == tight and len(both) < len(loose), (loose, tight, both)


def test_an_unreachable_floor_still_offers_the_native_rung():
    """Nothing here upscales, so a floor above the source is unreachable by definition.

    Returning an EMPTY ladder would turn a stated requirement into a crash instead of
    the report the failure message exists to give.
    """
    assert _scales_for(_Args(min_dimension=9999), 482, 513) == (1.0,)


def test_resize_max_dim_still_wins_and_pins_the_ladder():
    """What STAYED: the exact pin this generalises must not be weakened by it."""
    assert _scales_for(_Args(resize_max_dim=128, min_dimension=16), 482, 513) == (1.0,)


def test_the_filter_computes_dimensions_the_way_the_encoder_does():
    """max(1, round(dim*scale)) -- a floor that rounded differently would disagree
    with the file actually written, which is the whole defect being fixed."""
    # 482 * 0.375 = 180.75 -> 181. A floor of 181 must KEEP that rung, not drop it.
    assert 0.375 in _scales_for(_Args(min_width=181), 482, 513)
    assert 0.375 not in _scales_for(_Args(min_width=182), 482, 513)


# --- end to end, through the real CLI ------------------------------------------------
# The unit tests above would all pass on a scales_for_fit that nothing calls. These do not.
import json  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

needs = pytest.mark.skipif(not os.path.exists(SECURE),
                           reason='the trial inputs are gitignored third-party assets')


def _fit(out, *flags):
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out),
                        '--protect-outline-color', '002864', '--target-kb', '40', *flags],
                       capture_output=True, text=True, timeout=3600)
    assert r.returncode == 0, r.stderr[-3000:]
    with Image.open(out) as im:
        return im.size, r.stdout + r.stderr


@needs
def test_a_fit_never_delivers_below_the_stated_floor(tmp_path):
    (w, h), log = _fit(tmp_path / 'floored.webp', '--min-dimension', '400')
    assert min(w, h) >= 400, f'delivered {w}x{h} against --min-dimension 400'
    assert '--min-dimension 400' in log, 'the floor was applied but never reported'


@needs
def test_the_same_fit_WOULD_have_gone_smaller_without_the_floor(tmp_path):
    """Non-vacuity. Without this, the floor test passes on a fit that never resized."""
    (w, h), _ = _fit(tmp_path / 'free.webp')
    assert min(w, h) < 400, (
        f'the unfloored fit delivered {w}x{h}, so the floor fixture proves nothing -- '
        f'lower --target-kb until the fit is forced down the scale axis')
