#!/usr/bin/env python3
"""
Remove the background from an animated GIF while protecting an interior
region of the design from being erased, even if that interior region is
the same color as the background (e.g. white background + white highlight
inside a badge/logo).

Usage examples
--------------
# Simple case: no protected interior, just strip white background
python remove_gif_background.py input.gif output.gif --bg-color ffffff

# Protect everything inside a closed outline color (e.g. a navy ring)
python remove_gif_background.py input.gif output.gif \
    --bg-color ffffff --protect-outline-color 002a75

# Protect a manually specified circle (no clean outline to detect)
python remove_gif_background.py input.gif output.gif \
    --bg-color ffffff --protect-region circle:320,240,150

# Protect a manually specified rectangle
python remove_gif_background.py input.gif output.gif \
    --bg-color ffffff --protect-region rect:100,100,400,300

Notes
-----
- Background matching uses a tolerance around --bg-color (default 15),
  not an exact match, since GIFs have antialiasing/dithering.
- --protect-outline-color finds a CLOSED shape of that color and treats
  everything enclosed by it as protected, regardless of pixel color
  inside. This is the most robust option when your art has an outline.
- Do NOT rely on flood-fill from the image border alone to find the
  background: animated decorative elements can visually enclose
  background pockets and disconnect them from the border, leaving
  leftover opaque background color. This script instead treats ANY
  background-colored pixel OUTSIDE the protected region as background,
  regardless of border connectivity.
- Frame durations are read individually per frame from the source GIF
  and reapplied exactly on save. GIFs commonly have variable per-frame
  timing; grabbing only frame 0's duration and reusing it for all
  frames is a common bug that silently breaks playback speed.
- Edge feathering is ON by default. GIF only supports 1-bit (on/off)
  transparency, so a hard color-distance threshold alone leaves a
  jagged/pixelated boundary wherever the source art had smooth
  antialiasing against the background. To counter this, pixels in a
  transition band around the threshold get their alpha estimated by
  color-unmixing against the background, are de-fringed (background
  color bled out of their RGB), and are then converted to a stable
  binary transparent/opaque pattern with ordered (Bayer) dithering
  instead of a single hard cutoff. The dither pattern is fixed in
  space (not per-frame-random) so it doesn't flicker across frames.
  Disable with --no-feather if you want the old hard-cutoff behavior.
- The default output is otherwise UNMODIFIED beyond background removal:
  no cropping, no resizing, no frame-dropping, no gifsicle pass. Every
  original frame and its exact original timing survive untouched. All
  of that is opt-in via --compress {optimize,medium,heavy} (or the
  individual --crop / --frame-stride flags) -- see SKILL.md for when to
  reach for which tier.
"""

import argparse
import contextlib
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import numpy as np
from PIL import Image
from scipy import ndimage

STRUCTURE = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])


def ensure_gifsicle():
    """
    Check whether gifsicle is available, and try to install it via apt if
    not (works in most sandboxed Linux environments where archive.ubuntu.com
    is reachable; this was verified directly -- `apt-get install -y
    gifsicle` succeeds in ~1s and pulls a ~150KB package with no other
    dependencies). Returns True if gifsicle ends up available, False if not
    (e.g. no apt, no network, non-Debian system) -- callers must fall back
    gracefully to the Pillow-only path and note the size cost to the user
    rather than failing outright.

    Why this matters: gifsicle's GIF encoder is meaningfully better than
    Pillow's built-in writer even with ZERO quality loss (`-O3` alone, no
    --lossy or --colors). Confirmed directly on a real output: identical
    pixels, ~5-15% smaller purely from smarter LZW packing and palette
    handling. There's no reason not to apply this by default whenever
    it's available.
    """
    if shutil.which('gifsicle'):
        return True
    try:
        subprocess.run(['apt-get', 'install', '-y', 'gifsicle'],
                        capture_output=True, timeout=60, check=True)
        return shutil.which('gifsicle') is not None
    except Exception:
        return False


def ensure_pngquant():
    """
    Check whether pngquant is available, installing via apt if not (same
    pattern/reliability as ensure_gifsicle -- confirmed directly, `apt-get
    install -y pngquant` succeeds in ~1s). Returns True if pngquant ends up
    available, False otherwise; callers must fall back gracefully to
    Pillow's own quantizer rather than failing outright.

    Only used when --quantizer pngquant is explicitly requested (NOT the
    default -- see render_frames_to_gif and --quantizer's help text for
    the full reasoning). Summary: pngquant/libimagequant produces
    meaningfully lower quantization error than Pillow's `Image.ADAPTIVE`
    in isolation (confirmed directly: 38-81% lower MSE across a 16-128
    color range on real test art), but a real end-to-end A/B test on this
    skill's typical content (flat vector icon/sticker art) showed it
    producing LARGER output files at every tier (+4-7%) despite the lower
    error, likely because it optimizes for perceptual color accuracy
    rather than GIF-LZW-friendly index repetition, and flat icon art's
    handful of real design colors are already losslessly preserved by
    either quantizer within typical color budgets -- the measured error
    difference is concentrated in secondary antialiasing/blend-fringe
    fidelity, not the core design colors. So: not the default. Worth
    offering as an opt-in for content this skill hasn't primarily been
    validated against -- genuine gradients/soft shading with many colors
    doing real visual work, not just flat fills -- or whenever the person
    explicitly cares about visual fidelity more than file size.
    """
    if shutil.which('pngquant'):
        return True
    try:
        subprocess.run(['apt-get', 'install', '-y', 'pngquant'],
                        capture_output=True, timeout=60, check=True)
        return shutil.which('pngquant') is not None
    except Exception:
        return False


def gifsicle_optimize(path, level='lossless', timeout=60):
    """
    Run gifsicle over an already-saved GIF in place. `level` maps directly
    to this skill's three named tiers (see SKILL.md for how these were
    chosen/validated):
      - 'lossless': -O3 only. Zero visual cost, pure encoding efficiency.
        This is the gifsicle component of the 'optimize' tier.
      - 'medium': -O3 --lossy=30 -k 200. 200 is a light touch deliberately --
        most source art here uses well under 200 colors even before any
        reduction, so the cap mainly bites on the antialiased/feathered edge
        transition pixels, which DO commonly exceed 200 distinct shades.
      - 'heavy': -O3 --lossy=80 -k 128.

    ⚠️ NO --dither, on either tier, and that is a REVERSAL of what this docstring
    used to argue. Floyd-Steinberg was chosen on the reasoning that error diffusion
    beats banding on smoothly-shaded art. Measured 2026-08-19 on 23 purpose-built
    gradient assets and 5 flat animated vector sources, four axes each, it lost on
    every one that matters:

      axis                          gradient corpus        flat vector art
      file size                     +11% to +24% larger    +4% to +10% larger
      mean colour error             +8% to +12% worse      +13% to +14% worse
      static-region instability     2.8-3.6% vs 0.7-1.1%   ~0.01% either way
      banding (plateau run, step)   ~6% better  <-- its ONE real win

    The banding axis is the one dithering exists for, and it was measured separately
    rather than assumed away: contour plateau runs are 3.32 px with Floyd-Steinberg
    against 3.52 px without, on an unquantized reference of 3.72. Real, and an order
    of magnitude smaller than the costs. **Temporal instability is the decisive one**
    -- this project already refuses error-diffusion dithering for ALPHA on exactly
    that ground (it changed 8.1% of pixels in a region byte-identical between frames,
    where both Bayer sizes changed 0), and the same crawl appears here at 2.6x to 5x
    the no-dither rate, on content that is mostly static between frames. It also
    fights GIF inter-frame compression, which is where the size regression comes from.

    The earlier spot-check on `love.gif` alone called this "too close to call" (all
    options within 0.7% size, 0.013 colour error). That was one flat 6-colour asset,
    where a 200-colour palette reproduces the source almost exactly and dithering
    barely engages. `--auto` output is unaffected: no tier is applied unless
    --compress is passed, and `love.gif --auto` is still 2fd526b6fb3b191c.
    Returns True on success (file replaced in place), False if gifsicle
    isn't available or the call failed (original file is left untouched
    either way).
    """
    if not shutil.which('gifsicle'):
        return False
    args = {
        'lossless': ['-O3'],
        'medium': ['-O3', '--lossy=30', '-k', '200'],
        'heavy': ['-O3', '--lossy=80', '-k', '128'],
    }.get(level)
    if args is None:
        raise ValueError(f"Unknown gifsicle level: {level}")
    tmp_out = path + '.gifsicle_tmp.gif'
    try:
        subprocess.run(['gifsicle'] + args + [path, '-o', tmp_out],
                        capture_output=True, timeout=timeout, check=True)
        os.replace(tmp_out, path)
        return True
    except Exception as e:
        print(f"WARNING: gifsicle {level} optimization failed ({e}); "
              f"leaving file as-is.", file=sys.stderr)
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        return False


def frame_duration_ms(im, default=0):
    """
    Duration in ms of the frame `im` is CURRENTLY seeked to.

    The im.load() is load-bearing, not defensive. GifImagePlugin populates
    info['duration'] during seek(), so seek-then-read has always worked for a
    GIF -- but WebPImagePlugin populates it only in load(), so on a WebP the
    same pattern returns the PREVIOUS frame's value: a silent one-position
    lag that no exception ever reports.

    Measured on a real 124-frame WebP source (references/lessons.md SS17): the
    durations read back as [100, 220, 20 x122] against a true
    [220, 20 x122, 340] -- a bogus 100ms frame prepended, the final 340ms
    frame dropped, and every WebP/AVIF written from a WebP source came out
    240ms short with its timing shifted by one frame. It stayed invisible
    because the readback used this same lagged pattern, so intended and
    written agreed with each other and the script reported success.
    """
    im.load()
    return im.info.get('duration', default)


def average_frame_delay(durations):
    return sum(durations) / max(len(durations), 1)


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return '%02x%02x%02x' % tuple(int(c) for c in rgb)


def detect_bg_color(rgb, warn=True):
    """Sample the four corners; majority color (they should agree)."""
    h, w, _ = rgb.shape
    corners = [rgb[0, 0], rgb[0, w-1], rgb[h-1, 0], rgb[h-1, w-1]]
    corners = [tuple(int(v) for v in c) for c in corners]
    if warn and len(set(corners)) > 1:
        print(f"WARNING: the four corner pixels don't all agree on background "
              f"color ({corners}) — auto-detection picked the majority color, "
              f"but double-check --bg-color is right, especially for designs "
              f"with a diagonal composition or a corner-cropped canvas.",
              file=sys.stderr)
    return max(set(corners), key=corners.count)


def measure_edge_hardness(rgb, bg_rgb, tolerance=15, band_multiplier=4.0):
    """
    Measure whether the boundary between background and foreground is a
    hard cutoff (pixel art, or any flat art exported with no antialiasing)
    or a soft antialiased blend (typical vector icon export). Returns a
    dict with a 'ratio' -- roughly, how many transition-band pixels exist
    per pixel of boundary perimeter.

    This matters a lot, not just as a fun fact: this script's defaults
    (feathering on, --edge-cleanup-erosion 2) assume there's real
    antialiasing to clean up. Confirmed directly on a real synthetic pixel-
    art test case that this assumption, when wrong, is actively
    destructive rather than just suboptimal -- default settings eroded a
    31px pixel-art shape down to ZERO surviving pixels (0% survival),
    because there was no antialiasing fringe to begin with, just real art
    sitting exactly at the erosion boundary with nothing to spare. Ratio
    was 0.0 on that test case (literally zero transition-band pixels)
    versus 4.5-17.5 on real antialiased vector icon test files -- a clean,
    reliable separation, not a fuzzy judgment call.

    Use --pixel-art (bundles --no-feather, --edge-cleanup-erosion 0, and
    nearest-neighbor resizing) when this comes back hard-edged.
    """
    dist = np.abs(rgb.astype(int) - np.array(bg_rgb).astype(int)).max(axis=-1)
    hard_bg = dist <= tolerance
    band = (dist > tolerance) & (dist <= tolerance * band_multiplier)
    boundary = ndimage.binary_dilation(hard_bg) & ~hard_bg
    boundary_count = int(boundary.sum())
    band_count = int(band.sum())
    ratio = band_count / max(boundary_count, 1)
    return {
        'boundary_px': boundary_count,
        'transition_band_px': band_count,
        'ratio': round(ratio, 3),
        'appears_hard_edged': ratio < 0.5,
    }


# Containers that carry true 8-bit alpha. Every "can this hold partial
# transparency?" decision keys off this rather than an inline tuple -- adding
# APNG in v5.4.0 meant touching five such tuples, and a missed one would have
# silently handed an 8-bit container the 1-bit code path.
EIGHT_BIT_ALPHA_FORMATS = ('webp', 'avif', 'apng')


def _avif_available():
    """True if this Pillow can write AVIF -- via built-in support or the plugin."""
    try:
        from PIL import features
        if features.check('avif'):
            return True
    except Exception:
        pass
    try:
        import pillow_avif  # noqa: F401
        return True
    except Exception:
        return False


def measure_change_line_density(rgb):
    """Fraction of scan lines that differ from the previous line -- LOW means pixel art.

    Pixel art is drawn on a coarse grid and enlarged, so sweeping across it finds a change only at
    block boundaries. Antialiased art changes at nearly every line, because an edge ramp differs
    from its neighbour by construction.

    This measure exists because BOTH of the other two are defined relative to bg_rgb, and both
    collapse when a solid palette colour sits near the background (inflating the transition band)
    or on a background->art line (inflating the blend ratio) -- see references/lessons.md SS23,
    where 6 of 8 real pixel-art assets on coloured backgrounds were called antialiased, one of
    them scoring a band ratio of 20.895, higher than any genuinely antialiased asset measured.
    Counting WHERE the image changes never looks at a colour value, so neither collision reaches it.

    It is also scale-free, which an integer-lattice fit is not: a 500x500 export of a 32px sprite
    is a 15.625x upscale and lands on no integer grid at all. Measured across 37 labelled assets:
    antialiased 0.986-1.000, pixel art 0.041-0.245 for 18 of 25 -- a margin of KIND, with the
    remaining 7 (dithered or photographic pixel art, whose dithering puts noise on every line)
    saturating at the antialiased end. So a LOW value is dispositive for pixel art; a HIGH value
    proves nothing either way.
    """
    def _axis(a):
        nz = np.flatnonzero((a != a[0, 0]).any(axis=(0, 2)))
        if nz.size < 16:
            return 1.0
        sub = a[:, nz[0]:nz[-1] + 1]
        return float((np.diff(sub.astype(np.int16), axis=1) != 0).any(axis=(0, 2)).mean())
    return max(_axis(rgb), _axis(np.ascontiguousarray(rgb.transpose(1, 0, 2))))


# An enclosed background-coloured region is "intentional design" (a highlight inside a badge,
# a rocket's white body) rather than "incidental background" (a pocket the artwork happens to
# close off for a few frames). The original rule was a bare `enclosure_ratio >= 0.9`, with no
# reference to how BIG the region is, and it is the single most damaging thing this tool has
# been measured doing: on a real asset it called a rocket's white body
# `enclosure_ratio 0.825 looks incidental, leaving as background`, and in a three-agent trial
# the two agents that followed that advice deleted 83.1% and 83.3% of that asset's interior
# white -- and 45.8% of another's -- while reporting success. Documentation cannot reach a
# session that is being actively misadvised, so the fix has to be here.
#
# RATIO ALONE IS THE WRONG AXIS, and the measurement says so plainly. Over 26 real assets,
# 22 regions at or above 0.5% of the canvas, every ambiguous one inspected by eye:
#
#   CONFIRMED DESIGN     growth id1   14.1% of canvas  ratio 0.825   rocket body
#                        Best  id1    26.1%            ratio 0.800   rosette inner disc
#                        Meta  id2    11.4%            ratio 0.750   trophy handle field
#                        Meta  id1     8.3%            ratio 0.825   trophy handle field
#                        rocket id2    4.4%            ratio 0.650   left wing panel
#                        rocket id3    3.9%            ratio 0.650   right wing panel
#   CONFIRMED BACKGROUND hurricane id1 41.8%           ratio 0.050   badge, only bg-coloured
#                                                                    at the END of its fade
#                        GIFfromGIFER id2  8.1%        ratio 0.286   pocket under a raised arm
#                        GIFfromGIFER id34 1.9%        ratio 0.429   gap beside a hand
#                        9a4177e8 id5  1.2%            ratio 0.625   gap between two legs
#                        DFB2A5D7 id3   0.6%           ratio 0.500   gap between crown spikes
#                        Cut loop id8/id12 0.007%      ratio 0.500   speckle
#
# The decisive pair is `9a4177e8 id5` (1.2%, ratio 0.625, BACKGROUND) against `rocket id3`
# (3.9%, ratio 0.650, DESIGN): 0.025 apart in ratio and on opposite sides of the answer.
# Nothing in the ratio separates them; the area does. Both constants sit in a measured GAP
# rather than between neighbours -- area 1.2% -> 3.9%, ratio 0.286 -> 0.650 -- so neither was
# fitted to a boundary case.
#
# ⚠️ hurricane id1 is the honest limit and is NOT covered here: it is real design that reads
# as background only in the last frames of a fade, so its ratio is 0.05 and no area rule
# should rescue it (an area-only rule would protect 41.8% of every canvas). That asset needs
# --recover-fade-alpha, not region protection. See references/lessons.md SS34.2/SS34.3.
LARGE_REGION_CANVAS_FRACTION = 0.025   # a region this share of the canvas is not "incidental"
LARGE_REGION_ENCLOSURE_RATIO = 0.5     # ...provided it is enclosed at least half the time
INTENTIONAL_ENCLOSURE_RATIO = 0.9      # the size-independent bar, unchanged


def is_intentional_design(ratio, pixel_count, canvas_px):
    """Is this enclosed background-coloured region part of the ARTWORK? See the block above
    for the 26-asset measurement behind both constants and for the case they deliberately
    do not cover."""
    if ratio >= INTENTIONAL_ENCLOSURE_RATIO:
        return True
    return (canvas_px > 0
            and pixel_count / canvas_px >= LARGE_REGION_CANVAS_FRACTION
            and ratio >= LARGE_REGION_ENCLOSURE_RATIO)


PLATEAU_CLIFF_STRONG_STEP = 40      # a colour step this big is an EDGE, not a ramp step
PLATEAU_CLIFF_MIN_PLATEAU = 2       # px of flat colour required on each side
PLATEAU_CLIFF_THRESHOLD = 0.30      # at or above this, the art is hard-edged
PLATEAU_CLIFF_MIN_SAMPLES = 500     # below this the ratio is not dispositive
# For an alpha-only mask the hardness question becomes "does the ALPHA channel hold a ramp?", and
# this is the line between a cutout and a ramp. It is not a fine margin: measured over 524 real
# sprite-pack files (pixel art by provenance), EVERY ONE has 4 or fewer distinct alpha levels --
# 32 at 1, 198 at 2, 293 at 3, 1 at 4, and none above. The 15 alpha-only antialiased icons in this
# project's folders carry 186-256. So the two populations are separated by a factor of ~46, and 16
# sits between them without being tuned to either edge. An earlier version of this cut at 2, which
# would have called a 3-level sprite antialiased and handed it feathering plus 2px erosion -- the
# destructive direction, on exactly the content --pixel-art exists to protect. SS28.10
ALPHA_MASK_RAMP_LEVELS = 16
# At or under this many distinct colours in the COMPOSITED frame, the art is drawn from a flat
# palette rather than blended into one. 16 is not swept: it is the pixel-art convention itself --
# EGA, PICO-8 and most sprite work are drawn on a 16-colour palette -- and the measured negative
# frontier sits well above it. Over 146 labelled antialiased assets the LOWEST composited count is
# 26 (a heavily quantized 93x96 sticker), the next 60, and the median 403; over 542 labelled pixel
# art the median is 12 and the 25th percentile 9. So 16 sits 10 below the nearest negative with the
# positives' bulk beneath it, the same shape of margin PLATEAU_CLIFF_THRESHOLD has. Sharing the
# value of ALPHA_MASK_RAMP_LEVELS above is a coincidence of two different arguments, not one
# threshold used twice. SS29
VACUOUS_REAL_BAND_MAX = 0.20   # see the seventh-discriminator note in analyze()
FLAT_PALETTE_MAX_COLORS = 16


def measure_plateau_cliff_ratio(rgb, strong=PLATEAU_CLIFF_STRONG_STEP,
                                min_plateau=PLATEAU_CLIFF_MIN_PLATEAU):
    """Of the STRONG colour steps in this frame, what share are plateau-to-plateau cliffs?

    Returns (ratio, n_strong_steps). A strong step is a pair of adjacent pixels differing by
    `strong` on some channel -- an edge, not an antialiasing increment. It is a CLIFF when both
    sides sit in a flat run of at least `min_plateau` px. Upscaled pixel art transitions
    block-to-block and is nearly all cliffs; a 1px antialiasing ramp cannot be one, because the
    ramp pixel is a plateau of length 1 by construction.

    This is the FIFTH structural discriminator tried and the first to survive both populations
    (references/lessons.md SS28). The four before it -- modal run length, integer-lattice fit,
    duplicate-line density, gap regularity (SS23.4, SS23.8, SS23.9) -- all asked *where does the
    image change along a scan line*, unconditionally, and all four died on the same rock: a
    flat-fill vector icon is locally as uniform as a pixel grid, so its long uniform runs score
    like blocks. The difference here is the CONDITIONING: uniformity is only ever counted at a
    strong step. A vector icon's flat interior contributes nothing, because it has no strong steps
    in it; its edges do, and they carry the ramp pixel that disqualifies them.

    Measured over 158 assets -- the 31 labelled (25 pixel art / 6 antialiased), 122 vector emoji
    from this project's own asset folders, and the 5 corpus originals:

        pixel art detected      22 of 25 (lowest detected 0.356)
        antialiased + emoji     0 of 133 false positives (highest 0.186)

    0.30 sits between 0.186 and 0.356, nearer the negative end on purpose: a false positive
    applies --pixel-art to antialiased art (no feather, no erosion, nearest resize -- SS18's
    catastrophe), while a false negative is only the status quo.

    A HIGH value is dispositive for pixel art; a LOW value proves nothing, exactly like
    change_line_density. The three misses are all art whose blocks have been softened by
    re-encoding -- see SS28.3.

    The caller takes the MEDIAN across sampled frames, NOT the max, which is the opposite of
    ratio_max_across_frames and is deliberate. The two fire in opposite directions: a high band
    ratio proves antialiasing, so one frame showing a ramp settles it; a high cliff ratio proves
    pixel art, and one atypical frame must not. Measured -- a max-based rule would false-positive
    `GIF Selections` (per-frame 0.000-0.344, only 3% of frames over the threshold) and
    `love_transparent` (0.015-0.409, 20%). SS28.4
    """
    m = (rgb != rgb[0, 0]).any(axis=2)
    ys, xs = np.where(m)
    if ys.size >= 64:
        rgb = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    good = total = 0
    for col in (rgb, np.ascontiguousarray(rgb.transpose(1, 0, 2))):
        c = col.astype(np.int16)
        n = c.shape[1]
        if n < 2 * min_plateau + 2:
            continue
        step = np.abs(np.diff(c, axis=1)).max(axis=2) >= strong
        if not step.any():
            continue
        flat = np.ones_like(step)
        for j in range(1, min_plateau):
            left = np.zeros_like(step)
            left[:, j:] = (c[:, j:-1] == c[:, :-1 - j]).all(axis=2)
            right = np.zeros_like(step)
            right[:, :n - 1 - j] = (c[:, 1:n - j] == c[:, 1 + j:]).all(axis=2)
            flat &= left & right
        total += int(step.sum())
        good += int((step & flat).sum())
    return (good / max(total, 1)), total


def measure_composited_color_count(rgb):
    """How many distinct colours does this frame contain?

    The SIXTH structural discriminator, and the first that does not ask about edges at all. Pixel
    art is drawn from a deliberate, small palette; antialiasing manufactures a continuum of
    intermediate colours, and cannot help doing so. The count therefore separates the two
    populations by more than an order of magnitude without measuring block size anywhere -- which
    is exactly what the plateau-cliff ratio cannot do, because a 1:1 sprite has no 2px plateau for
    a cliff to sit between and scores like a ramp (SS28.6 already says so in its own docstring).

    It must be read off the COMPOSITED frame, and that is not a detail. Counted over opaque pixels
    only, a flat-fill vector icon whose entire antialiasing lives in its partial-alpha edge reads
    as a 35-colour palette -- `previous.png`, a plain chevron, measures 35 opaque colours and 289
    composited. That is the same rock the four discriminators before the cliff ratio died on
    (SS23.4, SS23.8, SS23.9): a flat vector interior is locally as uniform as a pixel grid.
    Compositing is what SS28.5 already requires of every hardness measure here, for this reason.

    Measured over the five labelled populations, 688 scoreable assets:

        pixel art (542)    p25 9    median 12    p75 17    p95 32
        antialiased (146)  lowest 26    next 60    median 403    max 27,089

    A LOW value is dispositive for pixel art; a high value proves nothing, exactly like the cliff
    ratio -- dithered pixel art re-encoded through a lossy step can carry hundreds of colours. And
    the failure direction is benign: art flat enough to come in under the floor without being
    pixel art is art with no ramps to protect, which wants --pixel-art's treatment anyway.
    """
    px = rgb.reshape(-1, 3).astype(np.uint32)
    packed = (px[:, 0] << 16) | (px[:, 1] << 8) | px[:, 2]
    # A boolean sieve over the 24-bit colour space, not np.unique. Same answer, exactly -- verified
    # frame by frame -- but np.unique SORTS, so its cost tracks the pixel count and not the colour
    # count: 1,347ms on a 1667x1667 frame and 3,903ms on a 3840x2160 one, against 18ms here, for an
    # identical answer (verified frame by frame on real assets). This bounds the WORST case; it is
    # not a speedup to a normal run -- an A/B/A over five assets put no-measure, np.unique and this
    # within 1.3s of each other over 57s, and the "tripled analyze()" I first claimed came from
    # comparing a slow 25-asset prefix to a whole-corpus mean on a machine another job was
    # saturating. SS29.8. The 16MB buffer is allocated per call (1ms, calloc), not at module scope.
    seen = np.zeros(1 << 24, bool)
    seen[packed] = True
    return int(seen.sum())


def measure_antialiasing_presence(rgb, bg_rgb, palette, tolerance=15, ring=3):
    """
    Fraction of near-boundary pixels that are TRUE blends of the background and
    one of the art's own flat colours, per pixel of boundary perimeter.

    This is the second discriminator `edge_hardness.ratio` needed and lacked.
    That ratio counts pixels in a narrow band just outside the background
    tolerance, so a clean vector export made mostly of straight edges -- which
    needs only a thin antialiasing band -- scores LOW and reads as pixel art.
    Two real assets scored 0.425 and 0.316 against a 0.5 threshold and would
    have had --pixel-art applied, which disables feathering and erosion and is
    destructive on curved antialiased art.

    Asking instead "are there real background-to-art blends here at all?"
    separates the two cleanly, because genuine pixel art has NONE by
    construction -- every pixel is a palette colour, never a mixture.
    Measured (mean over sampled frames):

        synthetic pixel art  0.000      <- the fixture from SS1
        love                 0.538
        explosion            1.221
        crystal              1.226
        gift                 1.395
        heart                1.581

    Zero versus 0.538 is a far wider margin than 0.425 versus 0.5, and it is a
    margin of KIND (blends exist / do not) rather than of degree.
    """
    bg = np.asarray(bg_rgb, dtype=np.float32)
    dist = np.abs(rgb.astype(int) - np.asarray(bg_rgb).astype(int)).max(axis=-1)
    hard_bg = dist <= tolerance
    boundary = ndimage.binary_dilation(hard_bg) & ~hard_bg
    boundary_count = int(boundary.sum())
    if boundary_count == 0:
        return 0.0
    near = ndimage.binary_dilation(hard_bg, iterations=ring) & ~hard_bg
    v = rgb[near].astype(np.float32) - bg
    palette = np.asarray(palette, dtype=np.float32).reshape(-1, 3)
    if v.size == 0 or len(palette) == 0:
        return 0.0
    is_blend = np.zeros(len(v), dtype=bool)
    for pc in palette:
        c = pc - bg
        L = float(c @ c)
        if L < 1.0:
            continue
        t = (v @ c) / L
        res = np.linalg.norm(v - t[:, None] * c, axis=1)
        # t bounded away from 0 and 1 so the endpoints themselves (pure
        # background, pure art colour) are not counted as evidence of a blend.
        is_blend |= (t > 0.12) & (t < 0.88) & (res < 14.0)
    return round(float(is_blend.sum()) / boundary_count, 3)


def get_source_transparency_mask(im0):
    """
    If the current (already-seeked) frame's source GIF carries a native
    GIF-transparency index, return a boolean mask of pixels using that
    index -- i.e. pixels the SOURCE already declared transparent, before
    this script does any of its own background detection. Returns None if
    the source has no transparency info at all.

    Must be called BEFORE im0.convert('RGB') on this frame: converting to
    RGB flattens transparent pixels onto whatever color happens to be
    sitting underneath them in the palette (implementation-defined, often
    a color that has nothing to do with the actual background) and that
    flattened color is indistinguishable from real art afterwards. Confirmed
    concretely on a synthetic test: a source with a real transparent hole
    came back OPAQUE with a garbage fill color after naive RGB flattening,
    because the revealed color didn't happen to match the auto-detected
    background and so read as foreground. This function exists so callers
    can force those pixels transparent in the output regardless of what
    color-based background detection concludes about them -- there's no
    real color data there to make a foreground/background call on in the
    first place.
    """
    # An RGBA/LA source keeps its transparency in the ALPHA CHANNEL, not in a
    # palette index, and has no 'transparency' info key at all -- so every
    # spelling below used to return None for a plain transparent PNG. That is
    # the inverse-spelling failure this project keeps hitting: two exotic forms
    # were handled and the most common one was not. Measured cost, 2026-08-18:
    # a real itch.io sprite (98.5% fully transparent, (0,0,0) padding under it)
    # went in with 7,130 opaque pixels and out with 4,675, because
    # detect_bg_color read the padding colour and color_mask then matched the
    # sprite's own 2,455 black outline pixels -- 7,130 - 2,455 = 4,675 exactly.
    #
    # ONLY alpha == 0 counts. A partially transparent pixel is a real
    # antialiasing ramp with real colour in it; treating a soft edge as "the
    # source declared this nothing" would throw away the very ramp SS28.5 exists
    # to preserve.
    if im0.mode in ('RGBA', 'LA', 'PA'):
        return np.array(im0.convert('RGBA'))[..., 3] == 0
    if 'transparency' not in im0.info:
        return None
    trans_index = im0.info['transparency']
    # For a PALETTE image this is an index into the palette. For an RGB/RGBA source -- an
    # APNG in RGB mode, for instance -- Pillow stores a COLOUR TUPLE instead, and comparing
    # a (H,W) index array against a 3-tuple raises "operands could not be broadcast
    # together". Confirmed 2026-08-17 on a real 46-frame RGB APNG, which crashed outright.
    if isinstance(trans_index, (tuple, list)):
        arr = np.array(im0.convert('RGB'))
        return np.all(arr == np.array(trans_index[:3], dtype=arr.dtype), axis=-1)
    if im0.mode not in ('P', 'L'):
        # a non-palette mode with a scalar transparency value: nothing reliable to key on
        return None
    raw = np.array(im0) if im0.mode == 'P' else np.array(im0.convert('P'))
    return raw == trans_index


SOURCE_ALPHA_BAND_DEFAULT = 2


def source_transparency_is_the_background(source_trans_mask, rgb, bg_rgb, tolerance):
    """
    Is the source's own transparency already standing in for the background?

    Two conditions, both cheap, each blocking a DIFFERENT wrong engagement:

      1. the transparent region touches the frame border -- that is what makes
         it the outside rather than an interior hole. A source whose only
         transparent pixels are punched holes still has a real painted
         background that must be removable.
      2. the modal RGB sitting UNDER those transparent pixels matches the
         detected background colour. This tests the failure mechanism directly
         instead of by proxy: when it holds, `detect_bg_color` did not find a
         background, it found padding, and "remove every pixel of that colour"
         is a meaningless instruction that happens to also match real art.

    Returns (bool, reason). The reason string is reported, because a silent
    change to the core removal path is exactly what this project's own history
    says goes wrong.
    """
    if source_trans_mask is None or not source_trans_mask.any():
        return False, 'source declares no fully transparent pixels'
    touches = bool(source_trans_mask[0].any() or source_trans_mask[-1].any()
                   or source_trans_mask[:, 0].any() or source_trans_mask[:, -1].any())
    if not touches:
        return False, ('the source transparency never touches the frame border, so it reads as '
                       'interior holes rather than the background')
    under = rgb[source_trans_mask]
    if under.size == 0:
        return False, 'no colour data under the transparent pixels'
    packed = (under[:, 0].astype(np.uint32) << 16) | (under[:, 1].astype(np.uint32) << 8) | under[:, 2]
    vals, counts = np.unique(packed, return_counts=True)
    modal = int(vals[int(np.argmax(counts))])
    modal_rgb = ((modal >> 16) & 255, (modal >> 8) & 255, modal & 255)
    if max(abs(int(a) - int(b)) for a, b in zip(modal_rgb, bg_rgb)) > tolerance:
        return False, (f'the colour under the source transparency is {rgb_to_hex(modal_rgb)}, which is '
                       f'not the detected background {rgb_to_hex(tuple(bg_rgb))} -- so the background '
                       f'is real paint, not padding')
    share = float(counts.max()) / float(counts.sum())
    return True, (f'{rgb_to_hex(tuple(bg_rgb))} is the padding colour under the source\'s own '
                  f'transparency ({share:.0%} of {int(source_trans_mask.sum())} transparent pixels) '
                  f'and that transparency reaches the frame border')


def build_source_alpha_scope(source_trans_mask, rgb, bg_rgb, tolerance, band, reach=None):
    """
    The region colour-based removal is allowed to touch on an already-transparent
    source: the source's transparent pixels, plus a `band`-pixel cleanup ring --
    but ONLY when that ring cannot also be artwork.

    ⚠️ The blunt ring was measured and it is HARMFUL. On a real itch.io sprite,
    survival by band was: 0px -> 100.0% (alpha byte-identical to the source),
    1px -> 70.7%, 2px -> 68.1%, unrestricted -> 65.6%. A 2px ring recovered only
    184 of the 2,455 pixels the unrestricted path destroyed, because pixel art's
    black outline sits DIRECTLY against its black padding: the ring IS the
    outline. A compromise that keeps two thirds of the damage is not a fix.

    So the ring is gated on a margin of KIND rather than a tuned radius: does the
    background colour also occur in the artwork's INTERIOR, away from the
    boundary? If it does, that colour is design, the ring would eat design, and
    the scope collapses to exactly the source's own transparency. If it does not,
    the only pixels of that colour anywhere are hugging the transparent boundary
    -- which is what a leftover matte fringe from an earlier, imperfect cut looks
    like -- and removing them is the whole point of not simply refusing.

    Returns (scope_mask, reason).
    """
    if band <= 0:
        return source_trans_mask, False, ('removal confined to exactly the pixels the source already '
                                   'declared transparent (--source-alpha-band 0)')
    # ⚠️ `reach` is the colour distance the REMOVAL path can actually act at, which is
    # NOT `tolerance` when feathering is on: estimate_alpha_and_defringe works in a band
    # of tolerance x --feather-band-multiplier, i.e. 60 at the defaults. Testing the veto
    # at 15 while removal reaches 60 left the guarantee three quarters short, and it
    # showed up as real loss: measured over every frame of 57 alpha-carrying assets, the
    # feather path survived 99.71% mean / 95.24% worst against the non-feather path's
    # 100.00% / 99.95%. A veto has to be evaluated at the radius of the thing it vetoes.
    if reach is None:
        reach = tolerance
    ring = ndimage.binary_dilation(source_trans_mask, structure=np.ones((3, 3), bool),
                                   iterations=int(band)) & ~source_trans_mask
    interior = ~source_trans_mask & ~ring          # opaque art, away from the boundary
    # color_mask is a pure per-channel comparison (checked: no neighbourhood term), so a
    # flat pixel list is a valid argument -- but spell it as one rather than as a fake image.
    if interior.any() and color_mask(rgb[interior], bg_rgb, reach).any():
        return source_trans_mask, False, (f'the {band}px cleanup band was DROPPED: '
                                   f'{rgb_to_hex(tuple(bg_rgb))} also occurs in the artwork away '
                                   f'from the transparent boundary, so the band would delete design '
                                   f'-- measured at 2px on a real sprite, it recovered 184 pixels '
                                   f'and destroyed 2,271')
    return (source_trans_mask | ring), True, (f'a {band}px cleanup band is included: '
                                        f'{rgb_to_hex(tuple(bg_rgb))} occurs nowhere in the artwork '
                                        f'except hugging the transparent boundary, which is what a '
                                        f'leftover matte fringe looks like')


def decide_source_alpha_policy(source_trans_masks, rgb_frames, bg_rgb, tolerance, band, reach):
    """
    ONE policy for the whole animation. Returns (engaged, band_allowed, reason, per_frame_scopes).

    ⚠️ Deciding this per frame produces FLICKER, and it is not hypothetical: measured
    over 57 alpha-carrying assets, **17 of them flip the veto branch mid-animation**
    (one alternates keep/drop/keep/drop across consecutive frames). A scope that
    changes between frames removes a pixel on frame 3 and keeps it on frame 4 --
    exactly the frame-to-frame instability this project rejects error-diffusion
    dithering for.

    The reduction is deliberately asymmetric, on the safe side of each question:
      * engaged if ANY frame's transparency reads as its background -- a frame where
        the character happens to cover the border should not switch protection off;
      * the cleanup band is allowed only if NO frame vetoes it -- one frame in which
        the background colour is also design is enough to make the ring unsafe for
        the whole animation.
    """
    engaged_frames, veto_frames, first_why, first_veto = 0, 0, None, None
    # The scope each frame produced, kept rather than discarded: `_scope_for` used to
    # recompute the identical binary_dilation per frame at render time, so an
    # alpha-carrying animation paid two dilation passes per frame where one would do.
    scopes = [None] * len(source_trans_masks)
    for idx, (st, rgb) in enumerate(zip(source_trans_masks, rgb_frames)):
        ok, why = source_transparency_is_the_background(st, rgb, bg_rgb, tolerance)
        if not ok:
            continue
        engaged_frames += 1
        if first_why is None:
            first_why = why
        if band > 0:
            # ⚠️ Read the BOOLEAN, never the message. This used to test
            # `band_why.startswith('the Npx cleanup band was DROPPED')`, so the guard was
            # armed by prose: rewording that sentence -- an ordinary doc-pass edit in this
            # repo -- would have left `veto_frames` at 0 and silently re-enabled the ring on
            # exactly the sprites it was measured to destroy (survival 100.0% -> 68.1%).
            scopes[idx], band_applied, band_why = build_source_alpha_scope(
                st, rgb, bg_rgb, tolerance, band, reach)
            if not band_applied:
                veto_frames += 1
                if first_veto is None:
                    first_veto = band_why
    if not engaged_frames:
        return False, False, 'no frame\'s transparency reads as its background', scopes
    n = len(source_trans_masks)
    reason = (f'{first_why} (holds on {engaged_frames} of {n} frame(s))')
    if band <= 0:
        return True, False, reason + '. Removal confined to exactly the source\'s own transparency (--source-alpha-band 0)', scopes
    if veto_frames:
        return True, False, (reason + f'. The {band}px cleanup band is DROPPED for the whole '
                             f'animation because {veto_frames} of {engaged_frames} engaged frame(s) '
                             f'have that colour in the artwork away from the boundary -- one such '
                             f'frame makes the ring unsafe for all of them, and deciding per frame '
                             f'would flicker'), scopes
    return True, True, (reason + f'. A {band}px cleanup band is included: no engaged frame has that '
                        f'colour in the artwork away from the transparent boundary'), scopes


def warn_if_source_has_transparency(im0, input_path):
    """
    Source GIFs with pre-existing native transparency are handled
    correctly (see get_source_transparency_mask) -- their already-
    transparent pixels are forced transparent in the output regardless of
    this script's own background-color detection. This is just an FYI
    print so the person knows that's happening, not a data-loss warning.
    """
    has_transparency = 'transparency' in im0.info
    if has_transparency:
        print(f"NOTE: {input_path} already has a transparency index in "
              f"its palette. Its pre-existing transparent pixels are "
              f"carried through to the output as transparent regardless "
              f"of this script's own background-color detection -- they "
              f"won't be reinterpreted or lost.",
              file=sys.stderr)
    return has_transparency


def analyze(input_path, max_samples=40, tolerance=15):
    """
    Scan the GIF for background-colored regions that are enclosed by other
    colors (i.e. candidates for --protect-outline-color or --protect-region),
    and determine whether each is enclosed CONSISTENTLY across frames
    (likely intentional design, e.g. a highlight inside a ring) or only
    OCCASIONALLY (likely incidental — an animated element temporarily
    cutting off a pocket of real background). Returns a JSON-serializable
    report; does not modify anything.

    Also runs three whole-GIF checks independent of any specific candidate
    region, each a top-level field on the returned report: `tumble_risk`
    (does the foreground ever graze the canvas edge, motivating
    --tumble-safe), `band_interior_regions` (solid design tints or baked-in
    fades sitting inside the feathering transition band, motivating
    --protect-band-only or --dither-mode none), and `small_removed_regions`
    (a size histogram of small removed regions, motivating
    --erosion-exempt-max-size). See each check's own function docstring
    (measure_bg_component_margin, detect_band_interior_regions,
    collect_small_removed_region_sizes) for what real bug each one exists
    to catch.
    """
    im = Image.open(input_path)
    # A STATIC source has no n_frames -- JpegImageFile raises AttributeError outright. The
    # PROCESSING path learned this in v5.2.0 and uses getattr (see the identical comment above
    # its own read); analyze() and load_animation_rgba_frames() were left on the bare attribute,
    # so --analyze, --recommend, --auto and --verify all crashed with a raw traceback on exactly
    # the static JPEG input v5.2.0 advertised. Found by feeding a real .jpeg from the labelled
    # asset folder. This is the handoff's "inverse spelling" failure: five sites fixed, a sixth
    # missed, and the gates could not see it because no test ever pointed --analyze at a JPEG.
    n_frames = getattr(im, 'n_frames', 1)
    warn_if_source_has_transparency(im, input_path)
    im.seek(0)
    rgb0 = np.array(im.convert('RGB'))
    bg_rgb = detect_bg_color(rgb0)
    H, W, _ = rgb0.shape

    # COMPOSITED, not `convert('RGB')` -- and this is the same correction SS28.5 made for the
    # hardness family, applied to everything else that reads a frame. `convert('RGB')` DISCARDS
    # alpha rather than resolving it, so on an RGBA source a half-transparent pixel keeps its
    # full-strength art colour and every check downstream reads a colour no viewer will ever see.
    # SS28.5 fixed only measure_edge_hardness and its relatives; `all_rgb_frames` feeds
    # detect_bg_color's siblings, color_mask, the candidate-region enclosure search,
    # measure_bg_component_margin, detect_band_interior_regions and
    # collect_small_removed_region_sizes, and every one of them was still reading the raw plane.
    #
    # MEASURED before changing it, because the tracker's own scope note said this must not be
    # switched blind (there is still no LABELLED RGBA corpus). Running analyze() twice per file,
    # once with frames composited, over 14 partial-alpha icons and then over the 10 most
    # translucent assets in the sprite corpus:
    #   * three checks move -- band_interior_regions, candidate_regions, tumble_risk. Nothing
    #     else does, and the detected background colour is stable either way.
    #   * on the icons the movement is small (pixel counts 0.5-4%, bboxes 1px) and no verdict
    #     flips. On the TRANSLUCENT population it is a verdict: seven Tiny Swords cloud sprites
    #     go from 0 band-interior regions to 1 `solid_tint`, and `Shadow.png`'s
    #     mean_distance_from_bg reads 58.2 uncomposited against 18.1 composited.
    #   * two of those change the RECOMMENDED COMMAND, in both directions: `Clouds_03.png` gains
    #     --protect-band-only 4 (a real tint the raw read could not see), and `Shadow.png` LOSES
    #     --feather-band-multiplier 3.4 (the raw read had put a solid colour 58 from the
    #     background when a viewer sees it at 18). An autonomous run pastes that command
    #     verbatim, so this was a wrong flag on real assets, not a cosmetic field.
    # A fully opaque source has no partial alpha and takes the identical path, byte for byte,
    # which is what keeps the labelled corpus a valid control for it. SS29.11
    all_rgb_frames = []
    for i in range(n_frames):
        im.seek(i)
        _rgba_i = np.array(im.convert('RGBA'))
        _a_i = _rgba_i[..., 3]
        if ((_a_i > 0) & (_a_i < 255)).any():
            _f_i = _a_i[..., None].astype(np.float32) / 255.0
            all_rgb_frames.append((_rgba_i[..., :3].astype(np.float32) * _f_i
                                   + np.asarray(bg_rgb, dtype=np.float32) * (1.0 - _f_i)
                                   ).round().clip(0, 255).astype(np.uint8))
        else:
            # ascontiguousarray, not a bare slice: `convert('RGB')` returned a fresh
            # contiguous array and `_rgba_i[..., :3]` is a non-contiguous VIEW that also
            # pins the whole RGBA buffer alive for every frame.
            all_rgb_frames.append(np.ascontiguousarray(_rgba_i[..., :3]))

    # Tumble margin and the small-region histogram both scan every frame
    # and both start from the identical color_mask(rgb, bg_rgb, tolerance)
    # -- computed once per frame and shared, instead of each check
    # recomputing it independently. Confirmed via the final whole-branch
    # review that scanning every frame (necessary, see each check's own
    # docstring for the real false negatives it fixes) made --analyze
    # measurably slower; this removes one of the concrete redundant
    # per-frame costs without reverting to sampling, which would reopen
    # the exact false-negative bugs these checks exist to close.
    worst_margin = None
    worst_margin_frame = None
    all_small_sizes = []
    per_frame_small_sizes = []
    # A frame in which EVERY pixel is background becomes an entirely transparent output
    # frame, and Pillow's GIF writer emits an unreadable block for one: the file TRUNCATES
    # there. Measured on `growth.gif` (the rocket leaves the canvas at frame 85 of 123):
    # `gifsicle: unknown block type 71`, 85 of 123 frames readable, 1700ms of 2920ms.
    # Reproduced at defaults, under --quantizer pngquant, and under --dither-mode none, so
    # it is not flag-dependent. WebP and APNG use different encoders and keep all 123.
    #
    # Scanned on EVERY frame, never on `sample_idxs`. growth's blank frame is a SINGLE frame
    # in 123; the changing-background item filed the same day is the record of what sampling
    # does to a transient -- a 10-frame spread over 30 read 78.6% at frame 10 while frame 12
    # was 0.0%. This costs nothing extra: the loop already computes frame_bg_mask.
    blank_frames = []
    for i in range(n_frames):
        frame_bg_mask = color_mask(all_rgb_frames[i], bg_rgb, tolerance)
        if frame_bg_mask.all():
            blank_frames.append(i)
        m = measure_bg_component_margin(all_rgb_frames[i], bg_rgb, tolerance, mask=frame_bg_mask)
        if m['margin_ratio'] is not None and (worst_margin is None or m['margin_ratio'] < worst_margin):
            worst_margin = m['margin_ratio']
            worst_margin_frame = i
        _frame_small = collect_small_removed_region_sizes(
            all_rgb_frames[i], bg_rgb, tolerance, mask=frame_bg_mask)
        per_frame_small_sizes.append(_frame_small)
        all_small_sizes.extend(_frame_small)
    # --tumble-safe defines the background as the single LARGEST connected
    # bg-coloured component per frame. That premise fails outright when the
    # foreground divides the background into several large pieces: everything
    # outside the biggest piece is then silently kept.
    #
    # Measured 2026-08-17 on a 35-frame pixel-art asset whose limbs span the
    # canvas: the yellow background splits into 3-7 disconnected regions, and
    # --tumble-safe removed 69,548 of 158,899 background pixels on frame 0 --
    # leaving 56% of it behind. Without the flag: 0 background left, 0 art lost.
    # --recommend had suggested the one flag that breaks the asset, because
    # edge-grazing (which is what triggers tumble risk) is EXACTLY the condition
    # that also fragments the background.
    _split_frac = []
    for _i in (fg_sample_idxs if 'fg_sample_idxs' in dir() else range(min(n_frames, 8))):
        _m = color_mask(all_rgb_frames[_i], bg_rgb, tolerance)
        if not _m.any():
            continue
        _lb, _n = ndimage.label(_m, structure=STRUCTURE)
        if _n <= 1:
            _split_frac.append(0.0)
            continue
        _sz = ndimage.sum(_m, _lb, range(1, _n + 1))
        _split_frac.append(float((_sz.sum() - _sz.max()) / _sz.sum()))
    _bg_outside_largest = round(float(np.mean(_split_frac)), 3) if _split_frac else 0.0

    tumble_risk = {
        'worst_margin_ratio': worst_margin,
        'worst_margin_frame_index': worst_margin_frame,
        'background_outside_largest_component': _bg_outside_largest,
        # 0.35 sits MID-GAP, not at a convenient round number. Measured across the
        # corpus: explosion 0.0%, love 1.1%, military-tag 1.5%, gift 4.8%,
        # crystal 6.2%, heart 23.6% -- against 57.7% on the asset --tumble-safe
        # actually stranded. A first attempt used 0.05, which fell BETWEEN gift
        # and crystal, two assets 1.4 points apart: a margin of degree, and the
        # exact trap SS18 and SS23 document. Anything from ~0.30 to ~0.50
        # separates the real failure from every asset here.
        'tumble_safe_would_strand_background': _bg_outside_largest > 0.35,
        'likely_tumble_risk': (worst_margin is not None and worst_margin < 3.0
                               and _bg_outside_largest <= 0.35),
    }

    if n_frames <= max_samples:
        sample_idxs = list(range(n_frames))
    else:
        sample_idxs = sorted(set(np.linspace(0, n_frames - 1, max_samples).astype(int).tolist()))

    # Group detections of the same spatial region across frames (by bbox-
    # center proximity) so classification can use CROSS-FRAME distance
    # variance, not within-frame variance -- see detect_band_interior_
    # regions's docstring for why within-frame spread can't see a real fade.
    band_interior_groups = []
    for i in range(n_frames):
        for region in detect_band_interior_regions(all_rgb_frames[i], bg_rgb, tolerance):
            cx_r = (region['bbox_xyxy'][0] + region['bbox_xyxy'][2]) / 2
            cy_r = (region['bbox_xyxy'][1] + region['bbox_xyxy'][3]) / 2
            # 40px, not 15 -- confirmed too tight on real moving/rotating art
            # during the final whole-branch review: a single physical region
            # on jewelry.gif fragmented into ~15 separate groups because its
            # bbox center drifted 25-32px between consecutive detections as
            # the design rotated. 40px still keeps this fixture's two
            # genuinely distinct physical regions separate (their bbox
            # centers are 200+px apart). Known remaining limitations (not
            # fully fixed here, see the review): (1) this still doesn't know
            # which of these groups is actually the SAME area a verified
            # --protect-outline-color already covers -- that needs analyze()
            # to compute candidate regions before this loop runs, which is a
            # larger reordering left as a follow-up; (2) groups store no
            # frame index, only a distances list, so widening this threshold
            # also makes it more likely (though not observed on the fixtures
            # this was tuned against, whose distinct regions are far apart)
            # that two DIFFERENT regions detected in the SAME frame merge
            # into one group if their bboxes happen to be close -- which
            # would inflate distance_span_across_frames with a same-frame,
            # different-color difference rather than a real temporal one,
            # risking a false gradient_fade classification. Both need the
            # same fix: track frame index per detection, not just position.
            grp = next((g for g in band_interior_groups
                        if abs((g['bbox_xyxy'][0] + g['bbox_xyxy'][2]) / 2 - cx_r) < 40
                        and abs((g['bbox_xyxy'][1] + g['bbox_xyxy'][3]) / 2 - cy_r) < 40), None)
            if grp is None:
                band_interior_groups.append({
                    'pixel_count': region['pixel_count'],
                    'bbox_xyxy': region['bbox_xyxy'],
                    'mean_color': region['mean_color'],
                    'distances': [region['mean_distance_from_bg']],
                })
            else:
                grp['distances'].append(region['mean_distance_from_bg'])
                if region['pixel_count'] > grp['pixel_count']:
                    grp['pixel_count'] = region['pixel_count']
                    grp['bbox_xyxy'] = region['bbox_xyxy']
                    grp['mean_color'] = region['mean_color']

    band_interior_regions = []
    for g in band_interior_groups:
        # Only drop a single-observation group when there were multiple
        # frames available to have produced a second one -- on a genuinely
        # single-frame GIF (n_frames == 1) every real group necessarily has
        # exactly one observation, and dropping those would silently empty
        # band_interior_regions for every 1-frame input. Confirmed as a real
        # regression this guard fixes, caught by the review of the fix that
        # introduced this filter.
        if len(g['distances']) < 2 and n_frames > 1:
            continue  # single-frame blip amid a real animation, not stable enough to report
        dist_span = round(max(g['distances']) - min(g['distances']), 1)
        is_fade = dist_span >= 6.0
        band_interior_regions.append({
            'pixel_count': g['pixel_count'],
            'bbox_xyxy': g['bbox_xyxy'],
            'mean_color': g['mean_color'],
            'mean_distance_from_bg': round(sum(g['distances']) / len(g['distances']), 1),
            'distance_span_across_frames': dist_span,
            'frames_seen': len(g['distances']),
            'classification': 'gradient_fade' if is_fade else 'solid_tint',
            # band_only_width is the real numeric field callers should read;
            # recommendation is human-readable text for evidence display
            # only -- confirmed during the final whole-branch review that
            # parsing the width back out of this string
            # (int(recommendation.split()[-1])) was a fragile pattern with
            # a duplicated magic constant. 4 = edge_margin_px (3, this
            # function's own default) + 1, matching build_band_only_
            # removal_mask's own docstring guidance that the ring should be
            # at least as wide as the real antialiasing fringe.
            'band_only_width': None if is_fade else 4,
            # A gradient_fade is a translucent element the source flattened
            # against the background. --dither-mode none is the best GIF can do
            # (it just cuts the faintest stages); --recover-fade-alpha into a
            # webp/avif reconstructs the real alpha. Name the better answer
            # first -- see references/lessons.md SS16.
            'recommendation': ('--recover-fade-alpha with a .webp/.avif output '
                               '(or --dither-mode none if it must be a GIF)'
                               if is_fade else '--protect-band-only 4'),
        })

    # Persistence split. The <=500px ceiling above exists to keep genuine
    # protected DESIGN regions out of this measurement, but it assumes design
    # regions are LARGE. Confirmed false on a real asset (references/lessons.md
    # SS16): four ~287px controller buttons -- the exact detail the user asked to
    # preserve -- sailed under the ceiling and were reported as 1070 "small
    # removed regions", which made --recommend suggest --erosion-exempt-max-size
    # for regions that were about to be protected anyway. Per SS14, the robust
    # discriminator is not size but PERSISTENCE: a design element is physically
    # constant (present in essentially every frame at a stable size), while the
    # incidental gaps SS11 cares about appear transiently at particular frames.
    # Cluster by RELATIVE tolerance, not fixed-width bins. Fixed bins were tried
    # first and are measurably wrong: the motivating asset's buttons measure
    # 286-306px, which straddles a 25px bin edge, so the two halves scored 47.6%
    # and 83.9% and NEITHER cleared the persistence threshold -- despite the
    # region being present in every single frame. A stable-size region must not
    # be split by where an arbitrary boundary happens to fall.
    _n_sampled = max(len(per_frame_small_sizes), 1)
    _clusters = []                     # each: [representative_size, {frame indices}]
    for _fi, _sizes in enumerate(per_frame_small_sizes):
        for _sz in _sizes:
            for _c in _clusters:
                if abs(_sz - _c[0]) <= 0.15 * max(_sz, _c[0]):
                    _c[1].add(_fi)
                    break
            else:
                _clusters.append([_sz, {_fi}])
    _persistent_reps = [c[0] for c in _clusters if len(c[1]) / _n_sampled >= 0.9]

    def _is_persistent(sz):
        return any(abs(sz - r) <= 0.15 * max(sz, r) for r in _persistent_reps)

    _transient = [sz for sz in all_small_sizes if not _is_persistent(sz)]
    _persistent = [sz for sz in all_small_sizes if _is_persistent(sz)]

    # --erosion-exempt-max-size is a SIZE threshold: it exempts every removed
    # region at or below it. So it can only separate incidental noise from
    # design if the two size ranges do not overlap. Classifying regions
    # correctly is not enough on its own -- on love the four controller buttons
    # ARE correctly identified as persistent design (497 of 1070 regions), and
    # the suggestion computed from the transient regions still came out at 487,
    # well above the buttons' own 286-306px, so applying it would have exempted
    # the design anyway and reintroduced the v3.3.3 fringe. When the ranges
    # overlap the honest answer is that no threshold works, not a threshold
    # picked from one side of the overlap.
    _exempt_suppressed = None
    _exempt_suggestion = int(max(_transient) * 1.1) + 1 if _transient else 0
    if _exempt_suggestion and _persistent:
        _pmin = min(_persistent)
        if _exempt_suggestion >= _pmin:
            _exempt_suppressed = (
                f"a threshold of {_exempt_suggestion}px (from the largest transient "
                f"region, {max(_transient)}px) would also exempt PERSISTENT regions, "
                f"the smallest of which is {_pmin}px -- the transient and design size "
                f"ranges overlap, so no single size threshold separates them")
            _exempt_suggestion = 0

    small_removed_regions = {
        'sizes_sample': sorted(all_small_sizes, reverse=True)[:20],
        'count': len(all_small_sizes),
        'max_small_region_px': max(all_small_sizes) if all_small_sizes else 0,
        # Persistent regions are excluded from the suggestion: they look like
        # design, and erosion-exempting design is what produced a real fringe
        # bug in v3.3.3.
        'persistent_count': len(_persistent),
        'transient_count': len(_transient),
        'max_transient_region_px': max(_transient) if _transient else 0,
        'min_persistent_region_px': min(_persistent) if _persistent else None,
        'suggested_erosion_exempt_max_size': _exempt_suggestion,
        'erosion_exempt_suppressed_reason': _exempt_suppressed,
    }

    union_mask = np.zeros((H, W), dtype=bool)
    rep_frame_for_color = {}  # remember a frame index/rgb to sample outline color later
    # Each sampled frame's enclosed-background mask, kept so the per-region
    # loop below does not rebuild it. It was previously recomputed (a full
    # ndimage.label over the frame) once per REGION per FRAME, so a 4-region
    # 40-sample asset paid for 160 labelings of a mask already built here.
    enclosed_by_frame = {}

    for i in sample_idxs:
        rgb = all_rgb_frames[i]
        bg_mask = color_mask(rgb, bg_rgb, tolerance)
        labeled, num = ndimage.label(bg_mask, structure=STRUCTURE)
        border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | set(labeled[:, 0]) | set(labeled[:, -1])
        border_labels.discard(0)
        enclosed = bg_mask & ~np.isin(labeled, list(border_labels))
        union_mask |= enclosed
        enclosed_by_frame[i] = enclosed
        rep_frame_for_color[i] = rgb

    # Per-frame largest-background-component masks, built lazily and shared by
    # every outline-candidate check below (see _LazyCoreBgMasks).
    core_bg_masks = _LazyCoreBgMasks(all_rgb_frames, bg_rgb, tolerance)
    outline_fill_cache = _FilledOutlineCache(all_rgb_frames)

    # merge nearby/jittery regions across frames with a small dilation before labeling
    dilated = ndimage.binary_dilation(union_mask, structure=np.ones((5, 5)))
    clabeled, cnum = ndimage.label(dilated, structure=STRUCTURE)

    results = []
    # Footprints of the regions that will actually END UP protected, kept so the
    # band-interior list can say which of its detections are already covered.
    protected_footprints = {}
    for cid in range(1, cnum + 1):
        comp_footprint = (clabeled == cid) & union_mask  # restrict back to actual enclosed pixels
        if comp_footprint.sum() < 20:
            continue
        ys, xs = np.where(comp_footprint)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        cx, cy = float(xs.mean()), float(ys.mean())
        radius = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / 2.0

        frames_hit = 0
        for i in sample_idxs:
            if (enclosed_by_frame[i] & comp_footprint).any():
                frames_hit += 1

        ratio = frames_hit / len(sample_idxs)

        # NOTE on a known limitation: comp_footprint is a UNION across every
        # sampled frame. For a mostly-static design this union is a GOOD
        # ground truth (GIF palette dithering can shift exactly which
        # pixels fall within tolerance frame to frame, so the union
        # recovers the true full extent better than any single frame does
        # -- confirmed on a real badge icon: any single frame only showed
        # ~10300px of a highlight whose true solid extent was ~23700px).
        # But for a design with an ANIMATED element that temporarily
        # encloses a different, incidental patch of background in
        # different frames (e.g. a moving sparkle/swoosh), the union can
        # overstate the real shape by merging those different incidental
        # pockets into one inflated "component" that never exists at once
        # in any single frame (confirmed on a real gem icon: union was
        # 36422px, but the real stable triangle at that spot was only
        # ~5300px in any given frame). There is no cheap, universally
        # reliable way to distinguish these two cases from the union shape
        # alone -- so outline-color verification below is deliberately
        # conservative (requires the fill-holes containment check to pass
        # at 95%+) and reports `outline_color_verified: false` rather than
        # guessing when it can't confirm a candidate. A `false` here does
        # NOT mean no valid outline exists -- it means auto-detection
        # couldn't confirm one, and a human/Claude should zoom into an
        # actual frame and identify it manually rather than falling back
        # to an unverified circle/rect guess.
        true_footprint_frame_rgb = rep_frame_for_color[sample_idxs[0]]
        true_footprint = comp_footprint

        # Find and VERIFY an enclosing outline color, rather than trusting
        # whatever color happens to sit closest to the footprint.
        #
        # A naive "look at the immediate few pixels around the footprint and
        # take the majority color" approach breaks whenever the protected
        # region is only PART of a multi-color interior (e.g. a highlight
        # split into two shades, like a white/light-blue "moon" inside a
        # ring). In that case most of the footprint's border touches the
        # OTHER interior color, not the true enclosing outline further out
        # -- so the naive pick can land on the wrong color by a narrow
        # margin. This happened for real on a badge/rosette icon: the
        # immediate neighbor color won by 468 votes to 456 over the actual
        # navy ring, purely because of how the two interior shades split
        # near the boundary.
        #
        # To avoid that, sample candidate colors at SEVERAL dilation radii
        # (not just one shallow ring), then VERIFY each candidate by
        # actually simulating what --protect-outline-color would do with
        # it: build that color's mask, run the same binary_fill_holes used
        # at process time, and check whether the filled shape actually
        # contains (encloses) this footprint. Only verified candidates are
        # eligible; among those, prefer the tightest-fitting one (smallest
        # filled area), since that's most likely the immediate true
        # boundary rather than some larger, more distant shape that
        # happens to also enclose this point.
        outline_color, outline_filled_area, outline_shape = find_verified_outline_color(
            true_footprint_frame_rgb, bg_rgb, true_footprint, tolerance,
            core_bg=core_bg_masks[sample_idxs[0]])

        # PER-FRAME FALLBACK for exactly the union-overstatement case the note
        # above describes. When the union merges a real design region with
        # incidental pockets that exist in different frames, the merged
        # footprint is enclosed by nothing, so verification fails on a region
        # whose real shape has a perfectly good outline.
        #
        # Measured on gift.gif: the white strip is reported as design
        # (enclosure_ratio 1.0) but got candidate_outline_color None, so nothing
        # protected it and --verify came back with protected_region_coverage
        # 0.0 -- while 052a75/002864 encloses the region's own 21,184px
        # footprint in 40 of 40 sampled frames. The union had inflated it to
        # 25,219px by merging a neighbouring transient pocket.
        #
        # So: re-verify against what is ACTUALLY enclosed in each frame
        # (footprint INTERSECTED with that frame's own enclosed-background
        # mask), and accept a colour only if it verifies in >=90% of the frames
        # where the region really appears. That keeps the conservatism the note
        # argues for -- it is still a verified containment check, run more times
        # and on cleaner inputs, not a guess.
        if outline_color is None and ratio >= 0.9:
            _votes = {}
            _checked = 0
            for _i in sample_idxs[:15]:
                _frgb = all_rgb_frames[_i]
                _here = comp_footprint & enclosed_by_frame[_i]
                if _here.sum() < 20:
                    continue
                _checked += 1
                _c, _, _ = find_verified_outline_color(
                    _frgb, bg_rgb, _here, tolerance, core_bg=core_bg_masks[_i])
                if _c:
                    _votes[_c] = _votes.get(_c, 0) + 1
            if _checked and _votes:
                _best = max(_votes, key=_votes.get)
                if _votes[_best] / _checked >= 0.9:
                    outline_color = _best
                    _om = color_mask(true_footprint_frame_rgb,
                                     hex_to_rgb(_best), 40)
                    outline_shape = ndimage.binary_fill_holes(_om)
                    outline_filled_area = int(outline_shape.sum())

        outline_enclosure_all_frames = None
        outline_background_leak = None
        if outline_color is not None:
            outline_enclosure_all_frames = verify_outline_enclosure_all_frames(
                all_rgb_frames, outline_color, true_footprint)
            outline_background_leak = detect_outline_background_leak(
                all_rgb_frames, bg_rgb, tolerance, outline_color,
                core_bg_masks=core_bg_masks)

        # Nothing encloses this design region on any single frame. Before
        # giving up on it -- which means NO protection, not weaker protection
        # -- look for a colour that encloses part of it and never swallows
        # background. See find_partial_enclosure_outline_color for the measured
        # case this exists for.
        # Gated on the SAME predicate as the verdict, not on a second copy of the 0.9
        # constant. A region newly called design by the area rule and then denied the
        # partial-outline search would be marked "protect this" with nothing to protect it
        # WITH -- a worse outcome than either half alone.
        partial_outline = None
        if outline_color is None and is_intentional_design(
                ratio, int(comp_footprint.sum()), H * W):
            partial_outline = find_partial_enclosure_outline_color(
                all_rgb_frames, sample_idxs, bg_rgb, tolerance,
                comp_footprint, core_bg_masks, fill_cache=outline_fill_cache)

        # Circularity check: how well would a bounding CIRCLE (i.e.
        # --protect-region circle:...) approximate the true protected
        # shape? Measured as the IoU between the true shape (the verified
        # outline's filled interior if we found one, else the raw
        # footprint) and the best-fit circle of the same centroid/radius.
        # Low IoU means the shape is scalloped/pointed/irregular (badge
        # rosettes, gems, stars...) and a circle protect-region would
        # either bleed past the true edge (where the real boundary is
        # closer than the circle radius) or leave gaps (where it's
        # farther) -- exactly the bug that motivated this check. High IoU
        # means the shape really is close to circular and a circle region
        # is a reasonable fallback if no outline color is available.
        true_shape = outline_shape if outline_shape is not None else true_footprint
        circularity = circularity_iou(true_shape, cx, cy, radius)

        note = None
        if outline_color is None and circularity < 0.85:
            note = ("No verified enclosing outline color was found, AND this "
                    "region's shape is not close to circular (circularity "
                    f"{circularity:.2f} of 1.0) -- a circle protect-region "
                    "would likely bleed past the true edge in some "
                    "directions and fall short in others. Prefer manually "
                    "identifying the true enclosing outline color (zoom into "
                    "a frame) over --protect-region for this one, or use "
                    "rect: only if the true shape is genuinely axis-aligned "
                    "rectangular.")
        elif outline_color is not None and circularity < 0.85:
            note = ("Verified outline color found -- use "
                    "--protect-outline-color, NOT --protect-region, since "
                    f"this shape's circularity ({circularity:.2f} of 1.0) "
                    "means a bounding circle would be a poor approximation "
                    "of the true (non-circular) enclosed shape.")

        if outline_color is not None or partial_outline is not None:
            protected_footprints[cid] = comp_footprint
        results.append({
            'id': cid,
            'pixel_count': int(comp_footprint.sum()),
            'bbox_xyxy': bbox,
            'center_xy': [round(cx, 1), round(cy, 1)],
            'suggested_protect_region': f'circle:{cx:.0f},{cy:.0f},{radius:.0f}',
            'frames_enclosed': frames_hit,
            'frames_sampled': len(sample_idxs),
            'enclosure_ratio': round(ratio, 3),
            'region_canvas_fraction': round(int(comp_footprint.sum()) / float(H * W), 4),
            'likely_intentional_design': is_intentional_design(
                ratio, int(comp_footprint.sum()), H * W),
            'candidate_outline_color': outline_color,
            'outline_color_verified': outline_color is not None,
            'outline_enclosure_all_frames': outline_enclosure_all_frames,
            'outline_background_leak': outline_background_leak,
            'partial_outline': partial_outline,
            'circularity_ratio': round(circularity, 2),
            'circle_region_safe': circularity >= 0.85,
            'note': note,
        })

    # Edge hardness across SAMPLED FRAMES, not frame 0 alone. Frame 0 is not
    # representative on animated art: love's ratio ranges 0.290-7.863 across its
    # 124 frames and heart's 0.239-9.008 across 35, so which frame you happen to
    # measure decides the answer. `ratio` stays frame 0 for continuity with
    # every previously recorded number; the DECISION uses the max, because
    # antialiasing is a property of the artwork -- if any frame clearly shows a
    # ramp, the art is antialiased no matter how many frames hide it.
    #
    # ONE MORE THING EVERY HARDNESS MEASURE NEEDS, and none of them had: if the source already
    # carries an ALPHA CHANNEL, its antialiasing lives in ALPHA, not in RGB. Image.convert('RGB')
    # drops alpha without compositing, so a partially transparent edge pixel keeps its
    # full-strength art colour and the ramp vanishes -- every measure here then sees a hard
    # silhouette that does not exist. Measured on a real 512x512 RGBA icon (`exchange.png`,
    # 1.5% partial-alpha pixels): plateau_cliff_ratio 0.320 read straight from RGB against 0.000
    # composited, i.e. the difference between "pixel art" and "obviously not". Compositing over
    # the detected background colour reconstructs exactly what a viewer sees, which is the image
    # the removal step will actually face. Opaque sources -- every asset in the labelled corpus --
    # take the identical path, because there is no partial alpha to composite. SS28.5
    _hardness_frames = dict()
    _partial_alpha_seen = False
    _alpha_levels = 1
    _rgb_span = 0
    _has_transparent_px = False
    for i in sample_idxs:
        im.seek(i)
        _rgba = np.array(im.convert('RGBA'))
        _a = _rgba[..., 3]
        _alpha_levels = max(_alpha_levels, int(np.unique(_a).size))
        _rgb_span = max(_rgb_span, int(_rgba[..., :3].max()) - int(_rgba[..., :3].min()))
        _has_transparent_px = _has_transparent_px or bool((_a == 0).any())
        if not ((_a > 0) & (_a < 255)).any():
            continue
        _partial_alpha_seen = True
        _f = (_a[..., None].astype(np.float32) / 255.0)
        _hardness_frames[i] = (_rgba[..., :3].astype(np.float32) * _f
                               + np.asarray(bg_rgb, dtype=np.float32) * (1.0 - _f)
                               ).round().clip(0, 255).astype(np.uint8)
    _hf = (lambda i: _hardness_frames.get(i, all_rgb_frames[i]))

    # AN ALPHA-ONLY SOURCE: one flat RGB value over the whole canvas, with the entire image
    # carried in the alpha channel. A monochrome glyph icon exported this way is extremely
    # common, and EVERY colour-based measure in this file is meaningless on it -- there is no
    # background colour to key, no transition band, no blends, and no colour steps at all.
    # Measured across this project's asset folders: 15 of 137 files are like this, each with
    # exactly ONE unique RGB value (span 0) and 186-256 distinct ALPHA values.
    #
    # Left unhandled it is not a cosmetic misread. detect_bg_color returns that one colour,
    # color_mask then matches every pixel in the frame, and the render removes the entire
    # image: measured on `pencil.png`, 69,925 opaque pixels in and ZERO out, while --auto
    # reported success because an empty output has no leftover background to count. The
    # RENDER-side guard (_refuse_empty_render) is the backstop; this is the diagnosis.
    _alpha_only_source = bool(_has_transparent_px and _rgb_span <= 8)

    # Does the source's OWN transparency already stand in for its background? If so there is
    # nothing for colour-based removal to do, and the RGB stored under those pixels is
    # padding rather than a background colour -- keying on it deletes any artwork that shares
    # the value, which on real sprites is the black outline (SS28.14). This has to reach
    # --recommend, not just the renderer: an autonomous run pastes suggested_command
    # verbatim, and a command that reads as "remove the background" while being a no-op is
    # the kind of confidently-wrong output this whole project is aimed at.
    #
    # ⚠️ Decided over the SAMPLED FRAMES, not frame 0. `decide_source_alpha_policy` decides this
    # same underlying property per ANIMATION -- "engaged if ANY frame's transparency reads as its
    # background" -- while this read frame 0 alone, and `source_alpha_levels`, the other half of
    # `_band_measures_are_vacuous`, was already a max over these same sampled frames. One property,
    # three answers, from three different frame sets. Frame 0 is also the frame most likely to
    # disagree: condition 1 of `source_transparency_is_the_background` is "the transparent region
    # touches the border", so a character that happens to cover the canvas border on its first
    # frame and not on its later ones fails it purely by animation phase.
    _src_bg_transparent, _src_bg_why, _src_bg_frames = False, None, 0
    if _has_transparent_px and not _alpha_only_source:
        for _sbi in sample_idxs:
            im.seek(int(_sbi))
            _st_i = get_source_transparency_mask(im)
            if _st_i is None or not _st_i.any():
                continue
            _ok_i, _why_i = source_transparency_is_the_background(
                _st_i, all_rgb_frames[int(_sbi)], bg_rgb, tolerance)
            if _ok_i:
                _src_bg_frames += 1
                if _src_bg_why is None:
                    _src_bg_transparent, _src_bg_why = True, _why_i
        im.seek(0)
        if _src_bg_transparent:
            _src_bg_why = (f'{_src_bg_why} (holds on {_src_bg_frames} of '
                           f'{len(sample_idxs)} sampled frame(s))')
        else:
            _src_bg_why = "no sampled frame's transparency reads as its background"

    # Strictly binary alpha means a HARD CUTOUT: the silhouette carries no antialiasing, by
    # construction. Computed here rather than beside its first old use because two rules below now
    # need it before they may speak at all. SS28.12
    _hard_alpha_cutout = bool(_has_transparent_px and _alpha_levels <= 2)

    # WHEN THE TRANSITION-BAND MEASURES HAVE NOTHING TO MEASURE. Both band-based rules read the
    # region between the background colour and the art. On a hard-alpha cutout whose transparency
    # IS the background, that region does not exist: the pixels that held the antialiasing ramp
    # were made fully transparent by whoever removed the background, and their RGB was replaced by
    # a flat padding value. So `ratio max 0.000` there is a statement about the removal that
    # already happened, not about the artwork -- it is guaranteed by the container whether the art
    # is pixel art or not.
    #
    # Measured: FIVE of the seven false positives across all five populations were exactly this,
    # and every one is antialiased art that had already been cut out -- `love_transparent.gif`
    # (this tool's own output from antialiased `love.gif`), `clown_transparent-ezgif.com-crop.gif`,
    # `NewDraws copy.gif` and two GIFs in the alphas set. Each was called hard-edged on the
    # strength of an empty band, and --pixel-art on antialiased art is the destructive direction
    # (SS18). Gating the two band rules on this predicate takes specificity from 0.966 to 0.993.
    #
    # This is SS28.9's lesson a second time: an empty measurement is not weak evidence, it is the
    # absence of any evidence, and the fix is to establish WHY the plane is blank rather than to
    # build something that out-votes it. Note the conjunction -- a SOFT-alpha source whose
    # transparency is the background still gets a real band, because SS28.5 composites the ramp
    # back before measuring. Only the binary cutout is unrecoverable. SS29
    _band_measures_are_vacuous = bool(_src_bg_transparent and _hard_alpha_cutout)

    _eh0 = measure_edge_hardness(_hf(0), bg_rgb, tolerance)
    _eh_ratios = [measure_edge_hardness(_hf(i), bg_rgb, tolerance)['ratio']
                  for i in sample_idxs]
    _eh_max = max(_eh_ratios) if _eh_ratios else _eh0['ratio']
    _art_palette = build_art_palette([_hf(i) for i in sample_idxs], bg_rgb)
    _blend_ratio = max(
        (measure_antialiasing_presence(_hf(i), bg_rgb, _art_palette, tolerance)
         for i in sample_idxs), default=0.0)
    # BOTH must agree before calling something hard-edged. The band ratio alone
    # produced two false positives on real vector art (SS18); requiring an
    # actual absence of background-to-art blends is what closes them.
    #
    # ...EXCEPT when there is no transition band AT ALL. SS18 asserted that
    # "genuine pixel art has no background-to-art blends by construction" and
    # validated that against a synthetic fixture I generated myself -- which is
    # circular, and false. Real pixel art (SS23: a 1667x1667 sprite, palette of
    # 9) scores blend_ratio 0.638, because measure_antialiasing_presence cannot
    # tell a true blend from a SOLID palette colour that happens to lie on the
    # segment between the background and another palette colour. Here the sky is
    # 9cd6f7 and the art carries solid whites at 255,255,255 / 252,252,253 /
    # 228,246,255 -- residuals 4.69, 2.35 and 2.92 from that line, all well
    # inside the 14 the blend test allows. The blend measure then VETOED a
    # correct verdict and handed pixel art the antialiased defaults, which are
    # destructive on it (measured 0% survival, SS4).
    #
    # Zero transition pixels in every sampled frame is dispositive: antialiasing
    # IS intermediate pixels, so none of them means none of it, and a blend
    # ratio computed on top of that is measuring palette collisions. This cannot
    # reopen SS18's false positives -- those scored 7.863 and 9.008, not 0.
    _no_transition_band_at_all = (_eh_max == 0.0)
    # A low change-line density is dispositive on its own (see the measure's docstring for the
    # 37-asset separation and why a HIGH value proves nothing). Threshold 0.5 sits between a
    # measured 0.245 and 0.986 -- deliberately mid-gap rather than tuned to either edge.
    _density = float(np.median([measure_change_line_density(_hf(i))
                                for i in sample_idxs])) if sample_idxs else 1.0
    # The plateau-cliff ratio is the measure that finally reaches DITHERED and photographic pixel
    # art, which saturates change_line_density (a dither puts a change on essentially every line,
    # so 7 of 25 labelled assets scored 0.592-1.000 and were missed). Conditioning on a strong
    # colour step is what makes it survive the vector-emoji population that killed the four
    # previous attempts -- see the measure's docstring and references/lessons.md SS28. Like the
    # density, it can only ever ADD a hard-edged verdict: high is dispositive, low proves nothing.
    _cliff_pairs = [measure_plateau_cliff_ratio(_hf(i)) for i in sample_idxs]
    _cliff = float(np.median([r for r, _ in _cliff_pairs])) if _cliff_pairs else 0.0
    _cliff_n = float(np.median([n for _, n in _cliff_pairs])) if _cliff_pairs else 0.0
    # Too few strong steps and the ratio is an estimate from a handful of pixels rather than a
    # measurement: one labelled antialiased asset has 177 of them and swings wildly. Report the
    # count so a low-sample verdict is visible instead of silently confident (SS28.4).
    _cliff_says_hard = (_cliff_n >= PLATEAU_CLIFF_MIN_SAMPLES
                        and _cliff >= PLATEAU_CLIFF_THRESHOLD)
    # The palette-size measure reaches the art the cliff ratio structurally cannot: pixel art drawn
    # 1:1, where no edge has a 2px plateau on either side. Median across sampled frames for the
    # same reason the cliff ratio takes one -- a small count is dispositive, so a single atypical
    # frame must not decide it. See the measure's docstring for the 688-asset separation.
    _ncolors = int(np.median([measure_composited_color_count(_hf(i))
                             for i in sample_idxs])) if sample_idxs else 0
    _flat_palette = bool(_ncolors <= FLAT_PALETTE_MAX_COLORS and not _alpha_only_source)
    # Record WHICH disjunct fired, not just that one did. `appears_hard_edged` has been an OR of
    # several independent rules since v5.0.0, but --recommend's evidence line still described the
    # ORIGINAL pair ("two independent measures agree: the transition band is empty AND there are
    # no blends") for every verdict, including ones reached by change_line_density alone -- where
    # both halves of that sentence can be false. An autonomous run takes the flags verbatim and a
    # human audits the evidence, so evidence naming a measure that did not drive the decision is
    # worse than none. Built here rather than re-derived in recommend() so the thresholds live in
    # exactly one place.
    _hard_reasons = []
    _soft_notes = []
    if _alpha_only_source:
        # Hardness read from the ALPHA channel, because that is where the whole image is. The
        # separation is a margin of KIND, not degree: a hard cutout has exactly 2 alpha levels
        # (0 and 255), while the 15 measured alpha-only icons carry 186-256. No threshold is
        # being tuned here, and no colour-based rule gets a vote -- each of them would be
        # reporting on a uniform plane.
        if _alpha_levels <= ALPHA_MASK_RAMP_LEVELS:
            _hard_reasons.append(
                f"the source is an alpha-only mask (one flat RGB value) with {_alpha_levels} "
                f"alpha levels, at or under the {ALPHA_MASK_RAMP_LEVELS} a hard cutout uses -- "
                f"no ramp anywhere")
        else:
            _soft_notes.append(
                f"the source is an alpha-only mask: one flat RGB value across the canvas, with "
                f"{_alpha_levels} distinct ALPHA levels, well over the "
                f"{ALPHA_MASK_RAMP_LEVELS} a hard cutout uses. Every colour-based hardness measure is "
                f"reading a uniform plane and none of them gets a vote; the {_alpha_levels} alpha "
                f"levels ARE the antialiasing ramp, so this is antialiased art "
                f"(references/lessons.md SS28.9).")
    elif _no_transition_band_at_all and not _band_measures_are_vacuous:
        _hard_reasons.append(
            f"no transition band at all in any sampled frame (edge_hardness ratio max "
            f"{_eh_max:.3f})")
    elif _no_transition_band_at_all:
        _soft_notes.append(
            f"the transition band is empty (ratio max {_eh_max:.3f}), but this source is a "
            f"hard-alpha cutout whose own transparency is the background, so an empty band is "
            f"guaranteed by the export and says nothing about the artwork: the ramp pixels were "
            f"made transparent and their colour replaced by padding. Not counted as evidence "
            f"(references/lessons.md SS29).")
    # A low density and a low cliff ratio CANNOT both be true of pixel art, and that contradiction
    # is the only thing standing between the density rule and a measured false positive. Density
    # below 0.5 means the image changes only every few scan lines -- blocks wider than one pixel --
    # which ENTAILS plateaus of 2px or more on each side of an edge, i.e. a high cliff ratio. When
    # the cliff ratio says the opposite on a decent sample, the low density is coming from
    # something else: a large, simple, flat shape whose columns repeat because there is barely any
    # detail, not because there is a pixel grid. Measured on `add.png`, a 512x512 vector icon:
    # density 0.447 (reads as pixel art) against cliff 0.070 over 3,737 strong steps, band ratio
    # 16.079 and blend ratio 2.960 (both emphatically antialiased). HEAD recommends --pixel-art
    # for it. All 18 corpus assets the density rule detects score cliff 1.000, so this costs no
    # detection. Note the asymmetry that keeps it safe: the cliff ratio may only SUPPRESS the
    # density rule when it has the samples to contradict it -- with a thin sample the density rule
    # still stands alone, which is the one regime where it is the only measure available. SS28.6
    # ...WITH ONE EXCEPTION, and it was a real false negative before it existed. A source whose
    # alpha is strictly binary is a HARD CUTOUT: there is no antialiasing at its silhouette, by
    # construction. So on such a file a low cliff ratio cannot be evidence of a ramp -- it just
    # means the art is drawn 1:1, where a block boundary has no 2px plateau to sit between. Letting
    # the cliff ratio suppress the density rule there reverses a CORRECT verdict on real pixel art.
    #
    # Measured on 524 files from real sprite packs: without this exception the suppression turned 4
    # genuine pixel-art sprite sheets from detected to undetected (`Soldier.png`, `Orc.png` and
    # their with-shadows variants -- density 0.271-0.309, cliff 0.130-0.211 over 7,109-11,342
    # steps, and band/blend 0.093-0.160 / 0.236-0.671, i.e. no antialiasing evidence at all).
    # Contrast `add.png`, which the suppression SHOULD catch: 255 alpha levels, band ratio 16.079
    # and blend 2.960. The discriminator is not the blend ratio -- SS23.5 measured that pixel art
    # and vector art overlap completely on it -- it is the alpha channel, which states the fact
    # directly rather than inferring it. SS28.12
    _cliff_contradicts = (_cliff_n >= PLATEAU_CLIFF_MIN_SAMPLES
                          and _cliff < PLATEAU_CLIFF_THRESHOLD
                          and not _hard_alpha_cutout)
    if _density < 0.5 and not _cliff_contradicts and not _alpha_only_source:
        _hard_reasons.append(
            f"change_line_density {_density:.3f}, below the 0.5 floor -- the image changes only "
            f"at block boundaries")
    elif _density < 0.5 and not _alpha_only_source:
        _soft_notes.append(
            f"change_line_density {_density:.3f} is below the 0.5 hard-edged floor, but "
            f"plateau_cliff_ratio {_cliff:.3f} across {int(_cliff_n)} strong colour steps "
            f"contradicts it: a pixel grid coarse enough to give that density would give "
            f"plateau-to-plateau edges. Treating the low density as a large flat shape, not "
            f"blocks (references/lessons.md SS28.6).")
    if _cliff_says_hard and not _alpha_only_source:
        _hard_reasons.append(
            f"plateau_cliff_ratio {_cliff:.3f} across {int(_cliff_n)} strong colour steps, at or "
            f"above the {PLATEAU_CLIFF_THRESHOLD:.2f} floor -- its edges are block-to-block "
            f"cliffs, not antialiasing ramps")
    if (_eh_max < 0.5) and (_blend_ratio < 0.15) and not _alpha_only_source \
            and not _band_measures_are_vacuous:
        _hard_reasons.append(
            f"a thin transition band (ratio max {_eh_max:.3f}) together with essentially no "
            f"background-to-art blend pixels (antialiasing_blend_ratio {_blend_ratio:.3f})")
    # THE SEVENTH DISCRIMINATOR, and the first one that is a REFINEMENT of an existing
    # suppression rather than a new measure. `_band_measures_are_vacuous` silences both band
    # rules on a hard-alpha cutout whose transparency is its background, because there an EMPTY
    # band is guaranteed by the export and says nothing about the artwork (SS29). Correct -- and
    # it was applied to every such source, including the ones whose band is not empty.
    #
    # A band that EXISTS on a cutout is real evidence, and its WIDTH separates the classes:
    # native-resolution pixel art carries a thin one (the artist's own 1px shading against the
    # silhouette), antialiased art carries a wide one. Measured over the labelled corpus, among
    # the 378 assets the vacuity gate silences:
    #     ratio_max  0.000        46 pixel art / 40 antialiased  (guaranteed empty -- stays silent)
    #     0 < ratio < 0.20        49 pixel art /  9 antialiased
    #     ratio >= 0.30          118 pixel art / 75 antialiased
    # On the INDEPENDENT populations (excluding the derived `small_aa_quantized`, which shares
    # every source with `small_aa`), adding this rule moves recall 0.8932 -> 0.9644 for a
    # specificity of 0.9787 -> 0.9681: +24 detections against 3 false positives.
    #
    # ⚠️ The 0.20 threshold is chosen from that corpus, and the honest reason to trust it is that
    # specificity is FLAT at 0.9681 across 0.10, 0.15 and 0.20 and only falls at 0.25 -- a
    # plateau, not a knife-edge, with 0.20 the recall-maximising point on it.
    #
    # ⚠️ 22 of the 24 new detections are one pack (Tiny RPG Character Asset Pack, which sat at
    # 23.5% recall), so this is pack-concentrated by construction -- that pack IS the population
    # the rule was built for. What makes it a rule rather than a fit is that it names a mechanism
    # (a real but narrow transition band) instead of a signature, and that it was scored on the
    # independent populations before being kept. SS32.7
    if (_band_measures_are_vacuous and 0.0 < _eh_max < VACUOUS_REAL_BAND_MAX
            and not _alpha_only_source):
        _hard_reasons.append(
            f"the transition band is REAL but narrow (ratio max {_eh_max:.3f}, under the "
            f"{VACUOUS_REAL_BAND_MAX:.2f} an antialiasing ramp needs) on a hard-alpha cutout -- "
            f"an EMPTY band would say nothing here, but a band this thin is the artist's own "
            f"1px shading, not a ramp")
    if _flat_palette:
        _hard_reasons.append(
            f"the composited frame holds only {_ncolors} distinct colours, at or under the "
            f"{FLAT_PALETTE_MAX_COLORS} of a flat pixel-art palette -- antialiasing manufactures a "
            f"continuum of intermediate colours and cannot come out this small")
    _hard = bool(_hard_reasons)
    edge_hardness = dict(_eh0)
    edge_hardness.update({
        'ratio_max_across_frames': round(float(_eh_max), 3),
        'ratio_min_across_frames': round(float(min(_eh_ratios)), 3) if _eh_ratios else None,
        'antialiasing_blend_ratio': _blend_ratio,
        'change_line_density': round(_density, 3),
        'plateau_cliff_ratio': round(_cliff, 3),
        'plateau_cliff_samples': int(_cliff_n),
        'composited_color_count': _ncolors,
        'band_measures_are_vacuous': _band_measures_are_vacuous,
        'appears_hard_edged': bool(_hard),
        'hard_edged_reasons': _hard_reasons,
        'hard_edged_suppressed_notes': _soft_notes,
        'measured_on_alpha_composite': bool(_partial_alpha_seen),
        'alpha_only_source': _alpha_only_source,
        'source_background_already_transparent': _src_bg_transparent,
        'source_background_transparent_reason': _src_bg_why,
        'source_alpha_levels': int(_alpha_levels),
        'source_is_hard_alpha_cutout': _hard_alpha_cutout,
    })

    # detect_band_interior_regions runs BEFORE the candidate-region loop and so
    # has no idea a detection sits inside a region that is about to be protected
    # by an outline colour. On a real asset that made what is physically 1-2
    # regions report as up to 17 separate band-interior entries, and --recommend
    # then said "17 solid-tint region(s) observed" about artwork already fully
    # covered. Reordering the whole function is the clean fix and a much larger
    # change; annotating here needs neither, because by this point BOTH lists
    # exist. A gradient fade is deliberately NOT excluded: a flattened fade
    # inside a protected outline is still a flattened fade and still needs
    # --recover-fade-alpha.
    for _br in band_interior_regions:
        _x0, _y0, _x1, _y1 = _br['bbox_xyxy']
        _cy, _cx = int((_y0 + _y1) / 2), int((_x0 + _x1) / 2)
        _br['inside_protected_region_id'] = next(
            (int(_cid) for _cid, _fp in protected_footprints.items()
             if 0 <= _cy < H and 0 <= _cx < W and _fp[_cy, _cx]), None)

    return {
        'n_frames_total': n_frames,
        'frames_sampled': len(sample_idxs),
        'detected_bg_color': rgb_to_hex(bg_rgb),
        'has_fully_transparent_frame': bool(blank_frames),
        'fully_transparent_frames': blank_frames,
        'source_has_pre_existing_transparency': 'transparency' in im.info,
        'edge_hardness': edge_hardness,
        'tumble_risk': tumble_risk,
        'band_interior_regions': band_interior_regions,
        'small_removed_regions': small_removed_regions,
        'candidate_regions': results,
    }


def recommend(input_path, tolerance=15):
    """
    Run analyze() and translate its report into a suggested command line
    plus the evidence behind each flag, per the decision tree SKILL.md's
    "Workflow: infer first, then confirm" and "Run the real processing"
    sections already document. Collapses "write five analyses, reason
    across them, pick flags" down to "read a recommendation, sanity-check
    it, confirm with the user."
    """
    report = analyze(input_path, tolerance=tolerance)
    evidence = []
    region_notes = []
    flags = []

    _eh = report['edge_hardness']
    _hardness = float(_eh['ratio'])
    _hard_max = float(_eh.get('ratio_max_across_frames', _hardness))
    _blend = float(_eh.get('antialiasing_blend_ratio', 0.0))
    if _eh['appears_hard_edged']:
        flags.append('--pixel-art')
        _reasons = _eh.get('hard_edged_reasons') or []
        evidence.append(
            "Hard-edged art detected -- recommending --pixel-art. What actually fired: "
            + ("; ".join(_reasons) if _reasons else "(reason not recorded)")
            + f". Each rule is dispositive on its own and none can veto another; the band ratio "
              f"is {_hardness:.3f} on frame 0 and the blend ratio {_blend:.3f}, quoted here for "
              f"context whether or not they drove the verdict "
              f"(references/lessons.md SS23, SS28).")
    elif _hard_max < 0.5:
        # The exact false positive SS18 documents: a thin-antialiasing vector
        # export whose band ratio reads as hard-edged. Reported as evidence
        # rather than silently dropped, so the run is auditable.
        # WHY it is not hard-edged has to match the case, and one wording cannot cover three.
        # This line used to assert "real background-to-art blends ARE present (blend_ratio X,
        # above the 0.15 floor)" unconditionally -- so on a hard-alpha cutout, where the verdict
        # is now decided by the vacuous-band gate, it printed "blends ARE present" beside a
        # measured blend ratio of 0.000, i.e. a sentence contradicted by its own number, on a
        # whole content class. Same defect family as SS28.7: evidence naming a rule that did not
        # drive the decision. Found by READING the output on a real asset rather than by checking
        # that the branch existed. SS29.1
        _vac = bool(_eh.get('band_measures_are_vacuous'))
        if _vac:
            _why = (f"the band measures got no vote at all -- this source is a hard-alpha cutout "
                    f"whose own transparency is its background, so a thin or empty band is "
                    f"guaranteed by the export and says nothing about the art "
                    f"(antialiasing_blend_ratio {_blend:.3f} is reading the same blank region). ")
        elif _blend >= 0.15:
            _why = (f"real background-to-art blends ARE present (antialiasing_blend_ratio "
                    f"{_blend:.3f}, above the 0.15 floor), so this is antialiased vector art with "
                    f"a thin band -- typical of shapes made mostly of straight edges -- not pixel "
                    f"art. ")
        else:
            _why = (f"no rule reached its hard-edged floor; a low band ratio is not on its own "
                    f"evidence of blocks (antialiasing_blend_ratio {_blend:.3f}). ")
        evidence.append(
            f"NOT recommending --pixel-art despite a low edge_hardness ratio "
            f"({_hardness:.3f}, max across frames {_hard_max:.3f}, under the 0.5 "
            f"hard-edged threshold): " + _why
            + f"The three block-structure measures agree: change_line_density "
            f"{float(_eh.get('change_line_density', 1.0)):.3f} (hard-edged below 0.5), "
            f"plateau_cliff_ratio {float(_eh.get('plateau_cliff_ratio', 0.0)):.3f} over "
            f"{int(_eh.get('plateau_cliff_samples', 0))} strong colour steps (hard-edged at or "
            f"above {PLATEAU_CLIFF_THRESHOLD:.2f}), and composited_color_count "
            f"{int(_eh.get('composited_color_count', 0))} (hard-edged at or under "
            f"{FLAT_PALETTE_MAX_COLORS}). --pixel-art here would "
            f"disable feathering and erosion and damage the ramp "
            f"(references/lessons.md SS1, SS18, SS28, SS29).")

    for _note in (_eh.get('hard_edged_suppressed_notes') or []):
        evidence.append("Hard-edged evidence weighed and set aside: " + _note)

    tumble = report.get('tumble_risk', {})
    tumble_safe = bool(tumble.get('likely_tumble_risk'))
    if tumble.get('tumble_safe_would_strand_background'):
        evidence.append(
            f"NOT recommending --tumble-safe despite an edge-grazing margin: "
            f"{tumble['background_outside_largest_component']:.1%} of the background sits "
            f"OUTSIDE its largest connected component, so the foreground divides the "
            f"background into pieces. --tumble-safe keeps only the largest piece and would "
            f"strand the rest -- measured on a real asset, it left 56% of the background "
            f"behind (references/lessons.md SS25).")
    if tumble_safe:
        flags.append('--tumble-safe')
        evidence.append(
            f"Foreground/background size margin drops to "
            f"{tumble['worst_margin_ratio']}x on frame "
            f"{tumble['worst_margin_frame_index']} (below the 3x safety threshold) -- "
            f"recommending --tumble-safe instead of "
            f"--protect-outline-color/--protect-region.")

    outline_colors = []
    if not tumble_safe:
        for region in report['candidate_regions']:
            rid = region['id']
            if not region['likely_intentional_design']:
                _frac = region.get('region_canvas_fraction')
                region_notes.append(
                    f"Region {rid}: enclosure_ratio {region['enclosure_ratio']} over "
                    f"{region['pixel_count']}px"
                    + (f" ({_frac:.1%} of the canvas)" if _frac is not None else "")
                    + f" -- left as background. It clears neither bar: "
                      f"{INTENTIONAL_ENCLOSURE_RATIO} enclosure at any size, or "
                      f"{LARGE_REGION_ENCLOSURE_RATIO} enclosure at "
                      f"{LARGE_REGION_CANVAS_FRACTION:.1%}+ of the canvas. "
                      f"⚠️ If this region is visibly part of the ARTWORK, protect it by hand "
                      f"(--protect-outline-color / --protect-region) -- this verdict has been "
                      f"wrong on a large pale region before.")
                continue

            all_frames = region.get('outline_enclosure_all_frames')
            leak = region.get('outline_background_leak')
            # ⚠️ A nonzero anomalous_frame_count means "this outline needs the
            # substitution path", NOT "this outline is unusable". Gating it out
            # entirely was measurably the wrong call: on crystal.gif the outline
            # is verified with enclosure_ratio 1.0 but breaks on 75/130 frames
            # (a sparkle crossing it), so --recommend fell through to
            # --protect-band-only -- which loses 19.99% of the artwork against
            # the 0.91% the outline loses. Nearly a 22x worse result from a gate
            # meant to be conservative.
            #
            # The substitution is now clamped to each frame's own silhouette
            # (see build_protected_masks_robust), which removes the artifact
            # that made anomalous frames untrustworthy in the first place. So
            # recommend it, and say plainly that the substitution will engage.
            # A background LEAK is still a hard reject -- that one over-protects
            # and there is no safe fallback.
            if (region['outline_color_verified'] and all_frames
                    and not (leak and leak['over_protects_background'])):
                outline_colors.append(region['candidate_outline_color'])
                anom = all_frames['anomalous_frame_count']
                region_notes.append(
                    f"Region {rid}: outline {region['candidate_outline_color']} verified "
                    f"across {all_frames['frames_checked']} frames "
                    f"({all_frames['enclosure_ratio_all_frames'] * 100:.0f}% enclosed) -- "
                    f"recommending --protect-outline-color."
                    + ("" if anom == 0 else
                       f" Enclosure breaks on {anom}/{all_frames['frames_checked']} frames "
                       f"(another element crossing the outline); the per-frame mask "
                       f"substitution handles it, clamped to each frame's own silhouette. "
                       f"Measured on a real asset, using the outline anyway beat falling back "
                       f"to --protect-band-only by ~22x on preserved artwork."))
            elif leak and leak['over_protects_background']:
                region_notes.append(
                    f"Region {rid}: outline {region['candidate_outline_color']} fills into "
                    f"{leak['leaked_pixel_count']}px of real background on frame "
                    f"{leak['leak_frame_index']} -- needs manual outline-color "
                    f"identification, not auto-recommended.")
            elif region.get('partial_outline'):
                _po = region['partial_outline']
                outline_colors.append(_po['color'])
                region_notes.append(
                    f"Region {rid}: no colour ENCLOSES this design region on a single "
                    f"frame, but outline {_po['color']} encloses part of it on "
                    f"{_po['frames_with_enclosure']}/{_po['frames_sampled']} sampled frames "
                    f"(best frame {_po['best_frame_index']}: {_po['best_frame_enclosed_px']}px, "
                    f"{_po['best_frame_enclosed_fraction'] * 100:.0f}% of the footprint) and "
                    f"never swallows real background on any of them -- recommending "
                    f"--protect-outline-color anyway. The shape opens and closes as it "
                    f"animates, so no single frame holds all of it; the per-frame mask "
                    f"substitution propagates the closed frames' shape to the open ones, "
                    f"clamped to each frame's own silhouette. The alternative here is not a "
                    f"weaker protection but NONE -- measured on a real asset, that cost "
                    f"976,800px of artwork (references/lessons.md SS26).")
            elif not region['outline_color_verified']:
                if region['circle_region_safe']:
                    flags.append(f"--protect-region {region['suggested_protect_region']}")
                    region_notes.append(
                        f"Region {rid}: no verified outline color, but shape is circular "
                        f"(circularity {region['circularity_ratio']}) -- falling back to "
                        f"--protect-region {region['suggested_protect_region']}.")
                else:
                    region_notes.append(
                        f"Region {rid}: no verified outline color AND shape isn't circular "
                        f"(circularity {region['circularity_ratio']}) -- needs manual "
                        f"identification, not auto-recommended.")
            else:
                region_notes.append(
                    f"Region {rid}: outline {region['candidate_outline_color']} could not be "
                    f"confirmed across frames -- needs manual review before trusting "
                    f"--protect-outline-color for this region.")

    if outline_colors:
        flags.append(f"--protect-outline-color {','.join(dict.fromkeys(outline_colors))}")

    band_regions = report.get('band_interior_regions', [])
    if any(r['classification'] == 'gradient_fade' for r in band_regions):
        # A fade means the FORMAT decision is already made: GIF structurally
        # cannot carry it. So recommend the flag that RECONSTRUCTS the alpha,
        # not the one that makes the loss look tidier.
        #
        # This used to always emit --dither-mode none -- the GIF-era workaround --
        # and mention --recover-fade-alpha only in prose. `--auto` takes the flag
        # list VERBATIM and never reads the prose, so on a real asset it produced
        # ZERO translucent pixels where --recover-fade-alpha produced 249,774.
        # CLAUDE.md's own rule: a warning in the evidence is not a fix, because an
        # autonomous run cannot act on it.
        flags.append('--recover-fade-alpha')
        evidence.append(
            "A translucent element was flattened against the background by the source "
            "export -- recommending --recover-fade-alpha, which unmixes each pixel "
            "against the art's own palette and reconstructs the original alpha "
            "arithmetically. Requires a .webp/.avif output; GIF's 1-bit alpha cannot "
            "carry the result. Measured on a real asset: 0 translucent pixels without "
            "this flag, 249,774 with it (references/lessons.md SS16).")
        evidence.append(
            "Band-interior region(s) show a gradient-fade signature (color distance from "
            "background varies across the frames it appears in) -- recommending "
            "--dither-mode none instead of the default Bayer dither.")
    _covered = [r for r in band_regions
                if r['classification'] == 'solid_tint'
                and r.get('inside_protected_region_id') is not None]
    tint_widths = [r['band_only_width'] for r in band_regions
                   if r['classification'] == 'solid_tint'
                   and r.get('inside_protected_region_id') is None]
    if _covered:
        evidence.append(
            f"{len(_covered)} solid-tint band-interior detection(s) sit INSIDE a region "
            f"that is already getting --protect-outline-color, and are not counted toward "
            f"--protect-band-only. The band-interior scan groups its per-frame detections "
            f"by proximity before the protected regions are known, so one physical "
            f"highlight can surface as many entries; these are that, not separate "
            f"unprotected tints.")
    if tint_widths and not outline_colors:
        flags.append(f'--protect-band-only {max(tint_widths)}')
        evidence.append(
            "Band-interior region(s) show a uniform solid-tint signature (constant across "
            "frames) -- recommending --protect-band-only to keep them fully opaque instead "
            "of allowlist-only protection.")
    # A SOLID art colour whose distance from the background falls inside the
    # feather band (tolerance .. tolerance*multiplier) is given partial alpha and
    # then dithered/eroded away -- it vanishes from a GIF output even though it is
    # not the background colour at all. Confirmed on real assets: #d2dcfd (dist
    # 57) and #d1dcfb (dist 58) against the default band of 15..60 wiped the pale
    # interior of an explosion and the white strip of a gift box. --protect-band-
    # only alone did NOT save them; narrowing the band so the colour falls OUTSIDE
    # it does. Compute that multiplier instead of leaving it to be rediscovered.
    _band_top = tolerance * 4.0
    _tint_dists = [r.get('mean_distance_from_bg') for r in report.get('band_interior_regions', [])
                   if r.get('classification') == 'solid_tint' and r.get('mean_distance_from_bg')
                   and r.get('inside_protected_region_id') is None]
    _at_risk = [d for d in _tint_dists if tolerance < d <= _band_top]
    if _at_risk:
        # ⚠️ The band cannot be narrowed arbitrarily far. Narrowing it protects the
        # tint, but the SAME band is what gives the antialiasing ramp its partial
        # alpha -- past a point the ramp stops being removed and survives as a
        # visible pale fringe. Which side you land on depends on how far the tint
        # sits from the background, and the old max(1.5, ...) clamp silently
        # crossed that line:
        #
        #   tint at 57-58 (explosion, gift) -> 3.3 -> band 15..49.5, ramp still
        #       removed. This is the case the flag was built for and it works.
        #   tint at 27 (heart)              -> 1.3, CLAMPED UP to 1.5 -> band
        #       15..22.5. Measured fringe fraction 0.2186 at 1.5 and 0.1831 at
        #       2.5, against 0.0000 at the default 4.0 -- a real fringe, produced
        #       by the recommendation itself.
        #
        # The clamp was the bug: it manufactured a value that satisfied the
        # formula while failing the thing the formula was for. Below 3.0 the tint
        # is close enough to the background that --protect-band-only must carry
        # it instead -- measured on heart, band-only alone keeps 117,027 of the
        # 119,810 near-background solid pixels the multiplier keeps (97.7%) with
        # NO fringe, so the multiplier buys ~2% more protection at the cost of a
        # visibly fringed edge.
        _computed = (min(_at_risk) / tolerance) - 0.5
        if _computed >= 3.0:
            flags.append(f"--feather-band-multiplier {_computed:.1f}")
            evidence.append(
                f"A SOLID art colour sits {min(_at_risk):.0f} from the background, inside the "
                f"default feather band ({tolerance:.0f}..{_band_top:.0f}) -- it would be given "
                f"partial alpha and dithered away in a GIF even though it is not the background. "
                f"Recommending --feather-band-multiplier {_computed:.1f} so the band stops short "
                f"of it while still reaching {tolerance * _computed:.0f}, far enough to keep "
                f"removing the antialiasing ramp. (For a WebP/AVIF output this cannot happen: "
                f"--recover-fade-alpha identifies it as a solid palette colour and keeps it "
                f"opaque. See references/lessons.md SS16.)")
        else:
            evidence.append(
                f"A SOLID art colour sits {min(_at_risk):.0f} from the background, inside the "
                f"default feather band ({tolerance:.0f}..{_band_top:.0f}), but NOT recommending "
                f"--feather-band-multiplier: the value that would clear it is {_computed:.1f}, "
                f"which narrows the band to {tolerance:.0f}..{tolerance * max(_computed, 1.5):.0f} "
                f"and stops the antialiasing ramp being removed -- measured on a real asset, that "
                f"produces a fringe fraction of 0.219 against 0.000 at the default. "
                + ("--protect-band-only is already recommended above and carries this case "
                   "instead (measured: 97.7% of the same protection, no fringe)."
                   if tint_widths and not outline_colors else
                   "Protect this colour explicitly (--protect-band-only or "
                   "--protect-outline-color) rather than narrowing the band.")
                + " See references/lessons.md SS18.")

    elif tint_widths and outline_colors:  # documented: combining the two shrinks protection
        evidence.append(
            f"{len(tint_widths)} solid-tint band-interior region(s) observed, but a "
            f"verified --protect-outline-color is already recommended -- not adding "
            f"--protect-band-only too, since combining it with an outline-verified "
            f"protected mask shrinks protection right at the outline's own edge "
            f"(confirmed against build_band_only_removal_mask's actual mask math). If "
            f"these tints fall outside the verified outline's interior, they need manual "
            f"review.")

    # FORMAT RECOMMENDATION. The output container is the first decision, not a
    # packaging afterthought: it decides whether partial transparency is even
    # representable. A gradient_fade region means the source has a translucent
    # element flattened against the background, which GIF structurally cannot
    # carry (references/lessons.md SS16).
    _fades = [r for r in report.get('band_interior_regions', [])
              if r.get('classification') == 'gradient_fade']
    # Ranking is Harkirat's stated preference (2026-08-17), weighted for
    # COMPATIBILITY as well as bytes -- not smallest-file-wins:
    #   full resolution      WebP lossless > AVIF q85 > GIF
    #   under a byte cap     AVIF > WebP > GIF   (AVIF keeps every frame; the
    #                        others must drop a third to two-thirds)
    #   compatibility        WebP > GIF > AVIF
    #   GIF                  only when explicitly required, or a genuine win on
    #                        size/render-time at near-equal visual quality
    _rank = ("  full resolution -> WebP lossless (bit-exact, widest support), "
             "then AVIF q85 (smaller, still excellent), then GIF.\n"
             "  under a byte cap (e.g. 256 KB emoji) -> AVIF first: measured, it keeps EVERY "
             "frame where WebP and GIF each drop a third to two-thirds. Then WebP, then GIF.\n"
             "  maximum compatibility -> WebP, then GIF, then AVIF.\n"
             "  Prefer GIF only when the destination requires it, or when it is a genuine win on "
             "size or render time at near-equal visual quality. Always report frame counts "
             "alongside file sizes -- under a cap, frames are what actually gets spent.")
    # A blank frame outranks the fade check: it is not a quality preference but a
    # container-level impossibility, and an autonomous run takes these flags verbatim.
    _blank = report.get('fully_transparent_frames') or []
    if _blank:
        report['recommended_format'] = 'webp-or-apng'
        evidence.insert(0,
            f"FORMAT: .webp or .apng -- NOT GIF. Frame(s) {_blank[:6]}"
            f"{' ...' if len(_blank) > 6 else ''} of {report['n_frames_total']} contain nothing "
            f"but background, so the output frame is entirely transparent. Pillow's GIF writer "
            f"emits an unreadable block for such a frame and the file TRUNCATES there -- measured "
            f"85 of 123 frames written on a real asset whose subject leaves the canvas. WebP and "
            f"APNG use different encoders and keep every frame. Ranking:\n" + _rank)
    elif _fades:
        report['recommended_format'] = 'webp-or-avif'
        evidence.insert(0,
            f"FORMAT: .webp or .avif, with --recover-fade-alpha. {len(_fades)} region(s) show a "
            f"translucent element that was flattened against the background at authoring time. GIF "
            f"has 1-bit alpha and CANNOT represent it -- the faded stages render as opaque pale "
            f"blobs or vanish, and no tolerance setting fixes it. Ranking:\n" + _rank)
    else:
        report['recommended_format'] = 'gif-ok'
        evidence.insert(0,
            "FORMAT: no translucent/fading element detected, so GIF can represent this asset "
            "faithfully and is a legitimate choice on compatibility grounds. WebP/AVIF still keep "
            "real antialiasing on the silhouette instead of dithering it, and need far less "
            "per-asset flag tuning. Ranking:\n" + _rank)

    small = report.get('small_removed_regions', {})
    if small.get('suggested_erosion_exempt_max_size'):
        flags.append(f"--erosion-exempt-max-size {small['suggested_erosion_exempt_max_size']}")
        evidence.append(
            f"{small['transient_count']} TRANSIENT small removed region(s) observed "
            f"(largest {small['max_transient_region_px']}px) -- recommending "
            f"--erosion-exempt-max-size {small['suggested_erosion_exempt_max_size']} to "
            f"protect them from erosion inflation. "
            f"{small['persistent_count']} further small region(s) were seen in ~every "
            f"frame at a stable size and are treated as DESIGN, not incidental noise, so "
            f"they are excluded from this suggestion.")
    elif small.get('erosion_exempt_suppressed_reason'):
        flags.append('--erosion-exempt-transient')
        evidence.append(
            f"{small['transient_count']} transient small region(s) need exempting, but "
            f"{small['erosion_exempt_suppressed_reason']}. A SIZE threshold therefore "
            f"cannot separate them from the {small['persistent_count']} design region(s) "
            f"-- exempting the noise would also exempt the design and leave the fringe "
            f"regression v3.3.3 documents. Recommending --erosion-exempt-transient "
            f"instead, which exempts by IDENTITY (present in ~every frame at a stable "
            f"size = design, eroded normally; comes and goes = incidental, exempt), so "
            f"the two size ranges are free to overlap.")
    elif small.get('persistent_count'):
        evidence.append(
            f"{small['persistent_count']} small removed region(s) found, but every one is "
            f"present in ~all frames at a stable size -- that is the signature of a design "
            f"element (a hole/cutout the art intends), not of the incidental gaps "
            f"--erosion-exempt-max-size exists for. NOT recommending the flag: applying it "
            f"to real design skips the normal edge cleanup and leaves a fringe (confirmed "
            f"regression, v3.3.3). If these should stay opaque, protect them instead.")
    elif len(report['candidate_regions']) > 0:
        evidence.append(
            "No small removed regions found under the ~500px heuristic ceiling -- if this "
            "GIF has a deliberately small removed region larger than that, "
            "--erosion-exempt-max-size may still be needed and should be measured manually.")

    # The script's OWN location, never a repo-relative guess. --recommend's whole
    # purpose is to emit a line an autonomous run pastes verbatim, and the primary
    # deployment target is a claude.ai sandbox where the skill unpacks somewhere
    # that is not a repo root -- "scripts/remove_gif_background.py" resolves there
    # only by luck. Every test of this was run FROM the repo root, where the wrong
    # path happens to be right: a check that could not fail.
    _self = os.path.abspath(__file__)
    # The placeholder must name a container that can actually HOLD what the flags
    # produce -- suggesting <output.gif> alongside --recover-fade-alpha emits a
    # command line that exits with an error.
    _ext = 'webp' if '--recover-fade-alpha' in flags else 'gif'
    suggested = f"python3 {shlex.quote(_self)} {shlex.quote(input_path)} <output.{_ext}>"
    if flags:
        suggested += " " + " ".join(flags)

    if _eh.get('source_background_already_transparent'):
        # Not a not_applicable_reason: unlike an alpha-only source, running the command here is
        # SAFE (removal is confined to the source's own alpha since SS28.14) and a format/size
        # conversion is a legitimate reason to run it. What would be dishonest is presenting it
        # as background removal, so the evidence says plainly that there is nothing to remove.
        evidence.insert(0, (
            "NOTHING TO REMOVE: this source's background is ALREADY transparent -- "
            f"{_eh.get('source_background_transparent_reason')}. Colour-based removal is confined "
            "to the region that alpha already covers, so the command below will leave the artwork "
            "intact and change little besides the container. Run it only if you want a format "
            "change, a size cap, or a leftover matte fringe cleaned up. If a run reports ART LOSS "
            "on this input, something overrode that confinement -- check --ignore-source-alpha and "
            "--edge-cleanup-erosion before reaching for --bg-color."))

    _not_applicable = None
    if _eh.get('alpha_only_source'):
        # An autonomous run pastes suggested_command verbatim, so on this input the field cannot
        # hold a removal command: there is no background colour to key, and running one empties
        # the file (SS28.9). None forces every caller to handle it -- run_auto checks this field
        # before it renders anything.
        _not_applicable = (
            f"This source is an ALPHA-ONLY mask: one flat RGB value across the canvas, with the "
            f"whole image carried in {_eh.get('source_alpha_levels')} levels of alpha. There is no "
            f"background COLOUR to remove -- its background is already fully transparent. Running "
            f"background removal would match the single flat colour everywhere and empty the file. "
            f"If the goal is a smaller file, use --target-kb / --resize-max-dim on it directly; if "
            f"it is a recolour, that is outside what this skill does.")
        suggested = None
    return {
        'recommended_format': report.get('recommended_format'),
        'suggested_command': suggested,
        'not_applicable_reason': _not_applicable,
        'evidence': ([_not_applicable] if _not_applicable else []) + evidence + region_notes,
        'analysis': report,
    }


def color_mask(rgb, target, tolerance):
    """
    Per-channel "within `tolerance` of `target`", i.e. abs(rgb - target) <= tol
    on all three channels.

    The obvious spelling -- `np.abs(rgb.astype(int) - target)` then `np.all(...)`
    -- upcasts a uint8 frame to int64, so an 800x600 frame allocates and walks
    11 MB per call where the answer needs none of it. This is the single most
    called function in analyze() (1,772 calls, 16s of self time on a 1000x1200
    asset before this change), so the allocation dominates.

    Comparing in place against a clipped inclusive range is arithmetically the
    same statement: abs(x - t) <= tol  <=>  t - tol <= x <= t + tol. Clipping the
    bounds into 0..255 is safe because a bound outside that range is satisfied by
    every uint8 value anyway. Checked equal to the old implementation on random
    arrays across tolerances 0, 1, 15, 40 and 300 and targets at both extremes.
    """
    a = np.asarray(rgb)
    t = np.asarray(target)
    mask = None
    for c in range(3):
        lo = max(int(t[c]) - int(tolerance), 0)
        hi = min(int(t[c]) + int(tolerance), 255)
        band = (a[..., c] >= lo) & (a[..., c] <= hi)
        mask = band if mask is None else (mask & band)
    return mask


def _gather_outline_candidates(rgb, bg_rgb, comp_footprint, tolerance,
                               dilation_radii=(4, 10, 20, 35, 55)):
    """
    Colors that appear in rings at several dilation radii around
    comp_footprint, quantized so near-duplicate antialiased shades merge
    into one candidate. Split out of find_verified_outline_color so the
    partial-enclosure search below gathers candidates exactly the same way.
    """
    H, W, _ = rgb.shape
    candidate_colors = {}
    prev_cumulative = np.zeros((H, W), dtype=bool)
    # `binary_dilation(mask, iterations=k)` with the default cross structure is k
    # sequential erosion passes, so five radii cost 4+10+20+35+55 = 124 of them --
    # measured as the single largest cost in analyze() (7.18s of 23.8s on
    # Cut loop.gif, 749 calls). Iterated cross-dilation by k is EXACTLY "every
    # pixel within taxicab distance k", so one chamfer distance transform answers
    # all five radii at once. Verified equal to the old result at every radius on
    # random multi-blob masks, and 4.3x faster on an 800x600 frame.
    _taxicab = ndimage.distance_transform_cdt(~comp_footprint, metric='taxicab')
    for radius in dilation_radii:
        dilated = _taxicab <= radius
        ring = dilated & ~comp_footprint & ~prev_cumulative
        prev_cumulative = dilated & ~comp_footprint
        if not ring.any():
            continue
        ring_pixels = rgb[ring]
        not_bg = ~color_mask(ring_pixels[None, :, :], bg_rgb, tolerance)[0]
        px = ring_pixels[not_bg]
        if len(px) == 0:
            continue
        # Quantize to merge near-duplicate antialiased shades into one
        # candidate rather than treating each as separate.
        q = (px // 20 * 20).astype(np.uint8)
        # packed, for the same reason as build_art_palette above -- q is quantized to a 20-step
        # grid so there are at most a few thousand distinct values, but the ROW sort still
        # dominates on a large frame.
        _qp = ((q[..., 0].astype(np.uint32).reshape(-1) << 16)
               | (q[..., 1].astype(np.uint32).reshape(-1) << 8) | q[..., 2].astype(np.uint32).reshape(-1))
        _qv, counts = np.unique(_qp, return_counts=True)
        vals = np.stack([(_qv >> 16) & 255, (_qv >> 8) & 255, _qv & 255], 1).astype(np.uint8)
        order = np.argsort(-counts)
        for v in vals[order][:3]:
            candidate_colors[tuple(int(x) for x in v)] = True
    return list(candidate_colors)


class _FilledOutlineCache:
    """
    Memo of `binary_fill_holes(color_mask(frame, colour))`, keyed by
    (frame index, colour), bounded to `cap` entries with FIFO eviction.

    The partial-enclosure search runs once per unenclosed design region, and
    the SAME handful of candidate colours comes back for every one of them --
    they are the art's own palette. Without this, a 1000x1200 asset with six
    such regions paid for ~380 fill-holes passes and analyze() went from 46s
    to 112s. The cap is what keeps the saving from turning into a memory
    problem: each entry is one bool mask the size of a frame.
    """

    def __init__(self, frames, cap=64):
        self._frames = frames
        self._cap = cap
        self._cache = {}
        self._order = []

    def filled(self, i, color, outline_tolerance):
        key = (i, color, outline_tolerance)
        hit = self._cache.get(key)
        if hit is None:
            omask = color_mask(self._frames[i], color, outline_tolerance)
            hit = (ndimage.binary_fill_holes(omask, structure=STRUCTURE)
                   if omask.any() else None)
            self._cache[key] = hit
            self._order.append(key)
            if len(self._order) > self._cap:
                del self._cache[self._order.pop(0)]
        return hit


class _LazyCoreBgMasks:
    """
    Per-frame largest_bg_component_mask results, built on first access and
    reused. Every outline check wants the same masks: candidate rejection
    (find_verified_outline_color), the all-frames leak test
    (detect_outline_background_leak, once per REGION before this) and the
    partial-enclosure search. Rebuilding them each time was the dominant
    cost of analyze() on a long asset.
    """

    def __init__(self, frames, bg_rgb, tolerance):
        self._frames = frames
        self._bg_rgb = bg_rgb
        self._tolerance = tolerance
        self._cache = {}

    def __len__(self):
        return len(self._frames)

    def __getitem__(self, i):
        if i not in self._cache:
            self._cache[i] = largest_bg_component_mask(
                self._frames[i], self._bg_rgb, self._tolerance)
        return self._cache[i]


def find_verified_outline_color(rgb, bg_rgb, comp_footprint, tolerance,
                                 outline_tolerance=40,
                                 dilation_radii=(4, 10, 20, 35, 55),
                                 core_bg=None):
    """
    Find a color that VERIFIABLY encloses comp_footprint, instead of just
    guessing from whatever color is immediately adjacent (see the long
    comment at the call site for why the naive approach fails).

    Gathers candidate colors from several dilation radii around the
    footprint (so it isn't fooled by a neighboring interior color that
    happens to be closer than the true outline), then verifies each
    candidate the same way the real processing pipeline would use it:
    build that color's mask and run binary_fill_holes, then check whether
    the filled result actually contains comp_footprint. Among verified
    candidates, returns the tightest-fitting one (smallest filled area) on
    the theory that the true immediate boundary produces the smallest
    enclosing shape.

    Returns (hex_color_or_None, filled_area_or_None, filled_mask_or_None).
    """
    candidate_colors = _gather_outline_candidates(
        rgb, bg_rgb, comp_footprint, tolerance, dilation_radii)
    if core_bg is None:
        core_bg = largest_bg_component_mask(rgb, bg_rgb, tolerance)

    # Verify each candidate the same way --protect-outline-color would
    # actually use it at process time: build that color's mask, run the
    # same binary_fill_holes, and check whether the filled result contains
    # (encloses) comp_footprint. Among verified candidates, keep the
    # tightest-fitting one (smallest filled area) -- the true immediate
    # boundary should produce the smallest shape that still fully encloses
    # the footprint; a color that happens to form some larger, more
    # distant enclosing shape elsewhere is a less specific (and less
    # trustworthy) match.
    best_color, best_area, best_shape = None, None, None
    for color in candidate_colors:
        omask = color_mask(rgb, color, outline_tolerance)
        if not omask.any():
            continue
        filled = ndimage.binary_fill_holes(omask, structure=STRUCTURE)
        # ⚠️ DEGENERATE CANDIDATE REJECT. A colour whose filled shape swallows
        # the real background is not enclosing anything -- it "contains" the
        # footprint only because it contains the entire canvas. Measured on
        # `Cut loop.gif`: candidate dcdcdc's mask covers 442,385 px, fills to
        # 480,000 (every pixel of an 800x600 frame) and overlaps 423,855 px of
        # true background, yet it scored containment 1.0 and WON the
        # tightest-fit contest as the only "verified" candidate. It was then
        # rejected one step later by detect_outline_background_leak, and
        # because selection had already thrown the other candidates away the
        # whole design region fell through to no protection at all -- 976,800
        # px of artwork destroyed on the GIF path (references/lessons.md SS26).
        # This is the SAME criterion that rejection uses, applied while the
        # alternatives are still on the table, so it can only ever turn
        # "region abandoned" into "next candidate considered".
        if (filled & core_bg).sum() > 20:
            continue
        containment = (comp_footprint & filled).sum() / max(comp_footprint.sum(), 1)
        if containment >= 0.95:
            area = int(filled.sum())
            if best_area is None or area < best_area:
                best_color, best_area, best_shape = rgb_to_hex(np.array(color)), area, filled

    return best_color, best_area, best_shape


def find_partial_enclosure_outline_color(all_rgb_frames, sample_idxs, bg_rgb,
                                         tolerance, comp_footprint,
                                         core_bg_masks, outline_tolerance=40,
                                         fill_cache=None):
    """
    Last resort for a design region that NO colour encloses on any single
    frame, where the alternative is not a weaker protection but none at all.

    find_verified_outline_color asks a binary question -- does this colour's
    filled shape contain 95% of the footprint -- on ONE representative frame.
    Two things defeat it at once on a shape that opens and closes as it
    animates (measured on `Cut loop.gif`, a pokeball that unlatches):

      1. the footprint is a UNION across frames, so it is far larger than
         what any one frame's outline can hold (30,191 px against a 13,603 px
         hole on the widest frame); and
      2. the outline only closes on part of the animation -- 15 of 76 frames
         here -- because in the rest the interior is an open bowl,
         topologically continuous with the background.

    Neither makes the colour wrong. At process time the per-frame mask
    substitution propagates the closed frames' shape to the open ones,
    clamped to each frame's own silhouette, which is exactly what
    --protect-outline-color 39215a does on that asset: 976,800 px of artwork
    preserved that the recommender's fallback destroyed entirely.

    So this searches the same candidates for the one that encloses the MOST
    of the region across sampled frames, and gates it on the one property
    that actually distinguishes a usable outline from a damaging one: it must
    never swallow real background on ANY sampled frame. That is a hard
    physical test (the same >20 px criterion detect_outline_background_leak
    uses), not a tuned margin -- and a colour that passes it cannot keep
    background that should have been removed, so against zero protection it
    is a strict improvement.

    Returns None, or a dict describing the winning colour.
    """
    candidates = {}
    for i in list(sample_idxs)[:6]:
        for c in _gather_outline_candidates(all_rgb_frames[i], bg_rgb,
                                            comp_footprint, tolerance):
            candidates[c] = candidates.get(c, 0) + 1
    # Rank by how many of the gather frames proposed the colour, and score at most
    # the top 8. A colour seen on one frame out of six is a transient element
    # passing through, not this region's boundary.
    ordered = sorted(candidates, key=lambda c: -candidates[c])[:8]

    footprint_total = max(int(comp_footprint.sum()), 1)
    # TWO STAGE, because this runs per unenclosed design region and a fill-holes
    # pass over every sampled frame for every candidate is the single most
    # expensive thing analyze() can do -- measured, the naive one-stage version
    # took a 1000x1200 8-frame asset with six such regions from 46s to 112s.
    # Stage 1 ranks on a subset; stage 2 re-runs the WHOLE leak gate on the
    # winner across every sampled frame, so the hard guarantee is unchanged.
    scan = list(sample_idxs)[:12] if len(sample_idxs) > 12 else list(sample_idxs)

    if fill_cache is None:
        fill_cache = _FilledOutlineCache(all_rgb_frames)

    def _score(color, frames):
        total = best_px = frames_with = 0
        best_idx = None
        for i in frames:
            filled = fill_cache.filled(i, color, outline_tolerance)
            if filled is None:
                continue
            if (filled & core_bg_masks[i]).sum() > 20:
                return None
            got = int((comp_footprint & filled).sum())
            if got:
                frames_with += 1
                total += got
                if got > best_px:
                    best_px, best_idx = got, int(i)
        if best_px == 0:
            return None
        return total, best_px, best_idx, frames_with

    ranked = []
    for color in ordered:
        r = _score(color, scan)
        if r is not None:
            ranked.append((r[0], color))
    for _total, color in sorted(ranked, key=lambda x: -x[0]):
        full = _score(color, sample_idxs)
        if full is None:      # leaks on a frame the subset did not cover
            continue
        total, best_px, best_idx, frames_with = full
        return {
            'color': rgb_to_hex(np.array(color)),
            'frames_sampled': len(sample_idxs),
            'frames_with_enclosure': frames_with,
            'best_frame_index': best_idx,
            'best_frame_enclosed_px': best_px,
            'best_frame_enclosed_fraction': round(best_px / footprint_total, 3),
            'total_enclosed_px_across_frames': total,
            'leaks_into_background': False,
        }
    return None


def verify_outline_enclosure_all_frames(all_rgb_frames, outline_hex, comp_footprint, outline_tolerance=40):
    """
    Re-run the same enclosure test find_verified_outline_color uses (build
    the outline color's mask, binary_fill_holes it, check containment of
    comp_footprint) across EVERY frame, not just the single first-sampled
    frame outline_color_verified checks. Confirmed real gap this closes: a
    color that binary_fill_holes-verifies on frame 0 can still fail to
    enclose the region on other frames if the outline itself gets crossed by
    another animated element (see build_protected_masks_robust's docstring
    for the exact mechanism) -- exactly the scenario
    detect_anomalous_frame_sizes exists to flag.
    """
    outline_rgb = hex_to_rgb(outline_hex)
    sizes = []
    containments = []
    footprint_total = max(int(comp_footprint.sum()), 1)
    for rgb in all_rgb_frames:
        omask = color_mask(rgb, outline_rgb, outline_tolerance)
        filled = ndimage.binary_fill_holes(omask, structure=STRUCTURE) if omask.any() else omask
        sizes.append(int(filled.sum()))
        containments.append(float((comp_footprint & filled).sum()) / footprint_total)

    bad_flags = detect_anomalous_frame_sizes(np.array(sizes))
    frames_enclosed = sum(1 for c in containments if c >= 0.95)
    anomalous = [i for i, b in enumerate(bad_flags) if b]
    return {
        'frames_checked': len(all_rgb_frames),
        'frames_enclosed': frames_enclosed,
        'enclosure_ratio_all_frames': round(frames_enclosed / max(len(all_rgb_frames), 1), 3),
        'anomalous_frame_indices': anomalous[:20],
        'anomalous_frame_count': len(anomalous),
    }


def detect_outline_background_leak(all_rgb_frames, bg_rgb, tolerance, outline_hex,
                                   outline_tolerance=40, core_bg_masks=None):
    """
    Opposite failure direction from verify_outline_enclosure_all_frames: not
    "does the outline fail to enclose the intended region" but "does the
    outline's filled shape leak outward and swallow real background". This
    happens when the outline isn't fully closed in some frame and
    binary_fill_holes fills straight through the gap into the actual
    background rather than stopping at the intended boundary. Flags any
    frame where the filled shape overlaps background-colored area that
    TOUCHES THE CANVAS BORDER -- the union of every such component, not
    just the biggest one.

    ⚠️ This used to test `largest_bg_component_mask`, and that was wrong in BOTH
    directions -- measured 2026-08-19 over 117 outline-colour tests, 3 of which
    differ and 2 of which flip the verdict, each in the direction that fixes a
    real error:

      * `DMZRecon_Gamemode_Icon_CoDM (1).webp`: the largest bg-coloured component
        (6,834 px) does NOT touch the border -- it is an interior black region of
        the ARTWORK. The old gate scored a 6,834 px "leak" into it and rejected a
        perfectly good outline colour, costing protection over a region that is
        not background at all. Border-union scores 0.
      * `gaming.jpeg`: 5 border-touching components total 71,390 px while the
        largest is 23,999. The old gate saw 14 px of leak and passed the colour;
        the union sees 207 and correctly rejects it. That is the blind spot this
        gate was filed for -- removable background that is not the biggest piece.

    `largest_bg_component_mask` stays correct where it is used for REMOVAL: there,
    taking only the biggest component is what stops a tumbling design that grazes
    the canvas edge from being flood-filled away. Here the question is the opposite
    one -- "what is genuinely background?" -- and border contact answers it, at the
    residual cost that art which touches the border and matches the background
    colour is counted as background by this gate.

    `core_bg_masks` is still accepted so existing call sites keep working, but it is
    deliberately NOT used: it caches largest-component masks, which is the very
    thing this gate must not test against.
    """
    outline_rgb = hex_to_rgb(outline_hex)
    max_leak = 0
    leak_frame = None
    for i, rgb in enumerate(all_rgb_frames):
        omask = color_mask(rgb, outline_rgb, outline_tolerance)
        if not omask.any():
            continue
        filled = ndimage.binary_fill_holes(omask, structure=STRUCTURE)
        core_bg = border_bg_component_mask(rgb, bg_rgb, tolerance)
        leaked = int((filled & core_bg).sum())
        if leaked > max_leak:
            max_leak = leaked
            leak_frame = i
    return {
        'leaked_pixel_count': max_leak,
        'leak_frame_index': leak_frame,
        'over_protects_background': max_leak > 20,
    }


def circularity_iou(shape_mask, cx, cy, radius):
    """
    How well does a circle of the given center/radius approximate
    shape_mask? Returns IoU (1.0 = perfect circle match, lower = more
    irregular/scalloped/pointed). Used to warn against using
    --protect-region circle:... on non-circular enclosed shapes -- the
    exact mismatch that let a rosette badge's scalloped ring and a
    diamond gem's pointed apex both leak background-colored bleed past
    the true edge when approximated with a plain circle.
    """
    H, W = shape_mask.shape
    if radius <= 0 or not shape_mask.any():
        return 1.0
    yy, xx = np.mgrid[0:H, 0:W]
    circle = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    intersection = (shape_mask & circle).sum()
    union = (shape_mask | circle).sum()
    return float(intersection) / float(union) if union > 0 else 1.0


def parse_protect_region(spec, shape):
    H, W = shape
    kind, rest = spec.split(':')
    vals = [float(v) for v in rest.split(',')]
    yy, xx = np.mgrid[0:H, 0:W]
    if kind == 'circle':
        cx, cy, r = vals
        return (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
    elif kind == 'rect':
        x, y, w, h = vals
        mask = np.zeros((H, W), dtype=bool)
        mask[int(y):int(y + h), int(x):int(x + w)] = True
        return mask
    else:
        raise ValueError(f"Unknown protect-region kind: {kind}")


def parse_protect_regions(spec, shape):
    """
    ⚠️ COORDINATES ARE IN **SOURCE** PIXELS, always. Every region flag
    (--protect-region, --remove-region, --translucent-region) is applied before
    --crop, --resize-max-dim and --square-pad, so measure the coordinates off
    the INPUT file, never off a cropped or resized output. Nothing in the code
    can catch a mis-measured region -- it will simply protect, remove or
    dissolve the wrong rectangle -- so the ordering is stated here rather than
    left to be inferred from the call sites.

    Parse one or more `;`-separated protect-region specs (each itself a
    `circle:cx,cy,r` or `rect:x,y,w,h`) and union their masks. `;` rather
    than `,` is the separator between specs specifically because `,`
    is already used WITHIN a single spec to separate that spec's own
    numeric fields (e.g. `circle:100,200,50`) -- reusing it as the
    between-specs separator too would make `circle:100,200,50,rect:...`
    ambiguous to parse.
    """
    H, W = shape
    union = np.zeros((H, W), dtype=bool)
    for one_spec in spec.split(';'):
        one_spec = one_spec.strip()
        if not one_spec:
            continue
        union |= parse_protect_region(one_spec, (H, W))
    return union


def apply_translucent_regions(rgb_frames, alpha_frames, region_mask, alpha_fraction,
                              target_rgb, tolerance):
    """
    Reduce alpha to `alpha_fraction` inside region_mask, for art where the same
    colour plays a THIRD role the binary keep/remove split cannot express:
    material that should read as see-through.

    The motivating asset is a bunny holding a transparent bag of popcorn, where
    one #ffffff serves as outer background (remove), bunny body (keep opaque) and
    bag interior (make translucent). No pixel-level rule separates them -- the
    pixels are byte-identical -- and the obvious structural hypothesis was that
    the bag interior is topologically connected to the outer background through
    the bag's opening, which would at least have explained the behaviour.

    MEASURED, and it is false: on frame 0 the bag interior is component 2, 14,069
    px, NOT border-connected, and the bunny's body is component 3, 27,767 px, also
    not border-connected. Both are fully enclosed pockets bounded by the same
    brown outline. Connectivity cannot tell them apart, and neither can colour,
    so nothing recoverable from the pixels can -- in flat vector art "translucent"
    is authoring intent, not evidence. That rules the structural route out and
    leaves naming the region, which is what this does.

    Two restrictions keep a coarse rectangle from doing collateral damage, which
    matters because the region has to be given by hand:

    * COLOUR. Only pixels within `tolerance` of `target_rgb` are affected --
      the glass itself, which is the background-coloured enclosed area. Without
      this a rectangle over the bag also turns the POPCORN inside it
      translucent, which is exactly backwards: the contents are what you are
      supposed to see through the glass.
    * ALPHA. Only pixels that are ALREADY opaque are lowered, so an antialiasing
      ramp or a recovered fade inside the region keeps its own alpha instead of
      being raised to the translucency level.

    Needs an 8-bit-alpha container; the caller enforces that.
    """
    level = int(round(255 * alpha_fraction))
    out = []
    for rgb, a in zip(rgb_frames, alpha_frames):
        a = a.copy()
        touch = region_mask & (a > level) & color_mask(rgb, target_rgb, tolerance)
        a[touch] = level
        out.append(a)
    return out


def apply_remove_regions(rgb_frames, alpha_frames, remove_mask, feather_px=1.5):
    """
    Force full removal (alpha -> 0) inside remove_mask, overriding whatever
    --protect-outline-color / --protect-region already decided -- the
    inverse of --protect-region. For carving out a small feature (e.g. a
    decorative hole/grommet) that shares its enclosing outline color with a
    DIFFERENT feature the user wants kept, so outline-color protection
    can't tell them apart on its own (confirmed real case, both features
    enclosed by the same navy ring color: a badge's highlight star, keep;
    a pin/grommet hole, remove -- see references/lessons.md SS15).

    Confirmed real bug this guards against: naively zeroing alpha inside
    remove_mask without touching RGB leaves the ORIGINAL pixel color
    (frequently an antialiased blend from the source art's own edge, e.g.
    a white-into-navy blend) sitting at partial alpha across the feather
    band. Composited over anything, that reads as a visible colored
    fringe/halo hugging the removed region's boundary -- not a mask/shape
    bug, a color bug, and easy to miss unless checked over a SOLID
    composite (checkerboard hides it). Fixed here by recoloring every
    touched pixel to the LOCAL kept color -- sampled fresh per frame from
    the thin ring of pixels just outside remove_mask, so it tracks
    per-frame shading/lighting changes -- before tapering alpha down, so a
    fading pixel always reads as "local surrounding color fading to
    transparent," never a ghost of whatever got removed. This is the same
    fringe failure mode --feather's own de-fringe step exists to prevent
    on the primary background-removal edge; this function brings the same
    protection to a manually-specified removal region, which the main
    feathering path doesn't touch.

    remove_mask is a single static (H, W) bool mask applied IDENTICALLY to
    every frame, same as --protect-region -- it does not track a moving
    target. If the region to remove changes position/size across frames
    (tumbling/rotating content, or a feature whose apparent size shifts
    frame to frame), this flag alone is not sufficient; that requires
    deriving the mask per frame from position-independent signals before
    calling this function once per frame with each frame's own mask (see
    the "Animated/rotating content" section and lessons.md SS15 for a real
    worked case -- notably including how a per-frame RE-MEASURED radius
    can itself be corrupted by an unrelated bright overlay, e.g. a shine
    sweep, transiently passing through the same screen area; a fixed
    radius measured only from unaffected frames was the confirmed fix
    there, not a smarter per-frame measurement).
    """
    # `remove_mask` may be ONE mask for the whole animation (the original contract) or a
    # LIST of per-frame masks from track_region_across_frames. The single-mask path still
    # computes its taper exactly once, so a static region costs what it always did.
    per_frame = isinstance(remove_mask, (list, tuple))
    if not per_frame:
        if remove_mask is None or not remove_mask.any():
            return rgb_frames, alpha_frames
        masks = [remove_mask] * len(rgb_frames)
    else:
        masks = list(remove_mask)
        if not masks or not any(m is not None and m.any() for m in masks):
            return rgb_frames, alpha_frames

    _cache = {}

    def _geom(m):
        key = id(m)
        if key not in _cache:
            dist_outside = ndimage.distance_transform_edt(~m)
            # 1.0 at/inside the mask boundary, tapering linearly to 0.0 by
            # feather_px outside it -- the region OUTSIDE remove_mask that still
            # gets touched at all is exactly this feather band.
            taper = np.clip(1.0 - dist_outside / max(feather_px, 1e-6), 0.0, 1.0)
            taper[m] = 1.0
            # Sample the local kept color from a thin ring just outside the mask
            # (not the whole frame, and not a single global color) so shading/
            # lighting/shine gradients across the design are respected per frame.
            _cache[key] = (taper, taper > 0,
                           (dist_outside > 0) & (dist_outside <= feather_px + 2.0))
        return _cache[key]

    out_rgb, out_alpha = [], []
    for m, rgb, alpha in zip(masks, rgb_frames, alpha_frames):
        if m is None or not m.any():
            out_rgb.append(rgb)
            out_alpha.append(alpha)
            continue
        taper, touched, ring = _geom(m)
        rgb2 = rgb.copy()
        if ring.any():
            local_color = rgb[ring].reshape(-1, 3).mean(axis=0)
        else:
            # No ring pixels (mask touches frame edge, or feather_px is
            # tiny relative to pixel grid) -- fall back to whatever color
            # already borders the mask directly.
            border = ndimage.binary_dilation(m, iterations=1) & ~m
            local_color = rgb[border].reshape(-1, 3).mean(axis=0) if border.any() else np.zeros(3)
        for c in range(3):
            rgb2[:, :, c] = np.where(touched, local_color[c], rgb2[:, :, c]).astype(np.uint8)
        alpha2 = alpha.astype(np.float64) * (1.0 - taper)
        out_rgb.append(rgb2)
        out_alpha.append(np.clip(alpha2, 0, 255).astype(np.uint8))
    return out_rgb, out_alpha


def track_region_across_frames(rgb_frames, bg_rgb, tolerance, seed_mask, log=None,
                               max_centroid_jump_frac=0.25):
    """Follow ONE background-coloured region across an animation, from a frame-0 seed.

    The gap this closes, filed 2026-08-08 (references/lessons.md SS15): punching a hole
    that shares its colour AND its geometry with decoration that must be kept. The two
    existing answers both fail here -- SS14's geometric gate needs the hole and the
    decoration to differ measurably in size or aspect on EVERY frame, and --remove-region
    is static, which on a real tumbling asset missed the true target in 76% of frames.
    The remaining option was a bespoke external tracking script per asset.

    What makes tracking possible when geometry is not: the SEED. The user names the
    target once, on frame 0, and identity is then carried forward by continuity rather
    than by any property that distinguishes it from its twin. Two identical holes are
    indistinguishable in a single frame and completely distinguishable across an
    animation, because only one of them is where the seeded one just was.

    Scoring, cheapest discriminator first:
      * centroid distance from the previous frame's target, gated at
        `max_centroid_jump_frac` of the frame diagonal -- a region cannot teleport;
      * area ratio, then bbox aspect ratio, as tie-breakers among candidates that pass
        the gate. Both are RELATIVE to the seed, so a hole that grows or foreshortens
        through a rotation still matches while an unrelated blob does not.

    ⚠️ Returns (masks, report). When no candidate passes the gate on a frame the mask is
    carried forward from the previous frame TRANSLATED by the last motion vector, and the
    frame index is recorded in `report['coasted_frames']`. A tracker that silently loses
    its target and keeps emitting a plausible mask is the exact failure this project
    refuses -- so coasting is reported, and process() prints it.

    scipy only, no OpenCV: the live session that motivated this reached for
    cv2.HoughCircles, and a dependency that heavy for a per-frame centroid is what the
    deferred item asked to avoid.
    """
    log = log if log is not None else []
    H, W = seed_mask.shape
    diag = float(np.hypot(H, W))
    gate = max_centroid_jump_frac * diag

    def components(rgb):
        bg = color_mask(rgb, bg_rgb, tolerance)
        lab, n = ndimage.label(bg, structure=STRUCTURE)
        out = []
        for i in range(1, n + 1):
            m = lab == i
            ys, xs = np.nonzero(m)
            if not len(ys):
                continue
            h = ys.max() - ys.min() + 1.0
            w = xs.max() - xs.min() + 1.0
            out.append({'mask': m, 'area': float(m.sum()),
                        'cy': float(ys.mean()), 'cx': float(xs.mean()),
                        'aspect': w / max(h, 1.0)})
        return out

    # frame 0: the seeded component is the one overlapping the seed most
    cands = components(rgb_frames[0])
    best = max(cands, key=lambda c: (c['mask'] & seed_mask).sum(), default=None)
    if best is None or not (best['mask'] & seed_mask).any():
        log.append('--remove-region-track: the seed region overlaps no background-coloured '
                   'component on frame 0, so there is nothing to follow. Falling back to the '
                   'static seed for every frame.')
        return [seed_mask] * len(rgb_frames), {'tracked_frames': 0, 'coasted_frames': [],
                                               'seed_found': False}
    masks = [best['mask']]
    prev, vel, coasted = best, (0.0, 0.0), []
    for i, rgb in enumerate(rgb_frames[1:], start=1):
        pred_y, pred_x = prev['cy'] + vel[0], prev['cx'] + vel[1]
        scored = []
        for c in components(rgb):
            d = float(np.hypot(c['cy'] - pred_y, c['cx'] - pred_x))
            if d > gate:
                continue
            area_pen = abs(np.log((c['area'] + 1.0) / (best['area'] + 1.0)))
            asp_pen = abs(np.log((c['aspect'] + 1e-3) / (best['aspect'] + 1e-3)))
            scored.append((d / max(gate, 1e-6) + area_pen + 0.5 * asp_pen, c))
        if scored:
            c = min(scored, key=lambda t: t[0])[1]
            vel = (c['cy'] - prev['cy'], c['cx'] - prev['cx'])
            prev = c
            masks.append(c['mask'])
        else:
            # ⚠️ COASTING, and it is reported. Shift the last mask by the last motion
            # vector rather than emitting nothing (a dropped frame is a visible flicker)
            # or the frame-0 mask (which is wrong by exactly the amount it has moved).
            dy, dx = int(round(vel[0])), int(round(vel[1]))
            m = np.zeros_like(masks[-1])
            src = masks[-1]
            ys, xs = np.nonzero(src)
            ys2, xs2 = ys + dy, xs + dx
            ok = (ys2 >= 0) & (ys2 < H) & (xs2 >= 0) & (xs2 < W)
            m[ys2[ok], xs2[ok]] = True
            masks.append(m)
            coasted.append(i)
            prev = {'cy': prev['cy'] + vel[0], 'cx': prev['cx'] + vel[1],
                    'area': prev['area'], 'aspect': prev['aspect']}
    report = {'tracked_frames': len(masks) - len(coasted), 'coasted_frames': coasted,
              'seed_found': True, 'seed_area': best['area']}
    if coasted:
        log.append(f"--remove-region-track: no candidate passed the continuity gate on "
                   f"{len(coasted)} of {len(masks)} frame(s) {coasted[:8]}; those masks were "
                   f"carried forward along the last motion vector. Check those frames.")
    else:
        log.append(f"--remove-region-track: followed the seeded region across all "
                   f"{len(masks)} frame(s).")
    return masks, report


BAYER4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
], dtype=float) / 16.0


def _bayer_matrix(n):
    """Recursive Bayer threshold matrix of size n (n a power of 2), normalised 0..1."""
    M = np.array([[0]])
    while M.shape[0] < n:
        M = np.block([[4 * M, 4 * M + 2], [4 * M + 3, 4 * M + 1]])
    return M.astype(float) / (n * n)


BAYER8 = _bayer_matrix(8)


def ordered_dither_mask(alpha, tile=BAYER4):
    """
    Convert a continuous 0..1 alpha map into a binary (0/255) map using a
    fixed spatial Bayer dither pattern. Fixed-in-space (not per-frame-random)
    so the pattern doesn't flicker/swim between animation frames.
    """
    H, W = alpha.shape
    th, tw = tile.shape
    reps_h = H // th + 1
    reps_w = W // tw + 1
    thresh = np.tile(tile, (reps_h, reps_w))[:H, :W]
    return (alpha > thresh)


def estimate_alpha_and_defringe(rgb, bg_rgb, protected, tolerance, band_multiplier=4.0,
                                rgb_key=None):
    """
    Estimate a continuous alpha (0..1) for every pixel based on color
    distance from the background color, and de-fringe (remove background
    color bleed from) pixels in the transition band via color-unmixing.

    Returns (alpha_float, recolored_rgb, band_mask).
    - alpha_float: 0..1 per pixel. 0 = fully background, 1 = fully kept.
    - recolored_rgb: rgb with background tint unmixed out of edge pixels.
    - band_mask: boolean, True for pixels in the transition band (used by
      the caller to decide which pixels go through dithering vs. a
      straight opaque/transparent assignment).

    `rgb_key`, when given, is the plane the background DISTANCE is measured
    against; `rgb` still supplies every pixel that comes back. They differ on a
    source carrying partial alpha, where `rgb` is a bare convert('RGB') -- the
    stored colour under a 35%-opaque pixel, which is whatever the encoder left
    there, not what the pixel looks like. `analyze()` has composited before
    measuring since SS28.5; this is the same correction on the removal side.
    The split matters: recolouring from the COMPOSITE would bake the background
    into the output, which is the one thing the output must not carry.
    """
    H, W, _ = rgb.shape
    bg = np.array(bg_rgb, dtype=float)
    key = rgb if rgb_key is None else rgb_key
    dist_to_bg = np.linalg.norm(key.astype(float) - bg, axis=-1)

    band_lo = float(tolerance)
    band_hi = float(tolerance) * band_multiplier

    alpha = np.clip((dist_to_bg - band_lo) / max(band_hi - band_lo, 1e-6), 0.0, 1.0)
    alpha[protected] = 1.0

    # "core" foreground = clearly not background/transition, or explicitly protected
    core_fg_mask = (dist_to_bg >= band_hi) | protected

    if core_fg_mask.any() and not core_fg_mask.all():
        _, indices = ndimage.distance_transform_edt(~core_fg_mask, return_indices=True)
        fg_estimate = rgb[indices[0], indices[1]].astype(float)
    else:
        fg_estimate = rgb.astype(float)

    band_mask = (dist_to_bg > band_lo) & (dist_to_bg < band_hi) & ~protected

    # Un-mix: pixel = alpha*fg + (1-alpha)*bg  =>  fg = bg + (pixel-bg)/alpha
    # Clamp alpha before dividing to avoid blowing up colors for near-zero alpha.
    a_safe = np.clip(alpha, 0.25, 1.0)[..., None]
    unmixed = bg + (rgb.astype(float) - bg) / a_safe
    unmixed = np.clip(unmixed, 0, 255)

    recolored = rgb.astype(float).copy()
    recolored[band_mask] = unmixed[band_mask]

    return alpha, recolored.astype(np.uint8), band_mask


def detect_band_interior_regions(rgb, bg_rgb, tolerance, band_multiplier=4.0, min_size=30, edge_margin_px=3):
    """
    Find solid-colored interior regions that fall inside the feathering
    transition band [tolerance, tolerance*band_multiplier] purely by color
    coincidence, not because they're a real antialiased edge. SKILL.md's own
    prose check (the "Art that FADES toward the background colour" section)
    already describes exactly this signature: band-distance pixels more than
    ~edge_margin_px from any true background pixel, in a blob bigger than a
    thin edge fringe. Two distinct real root causes converge on this same
    signature (references/lessons.md SS10 Bug 4 and SS12). This function only
    finds regions in ONE frame; the caller (analyze()) groups detections of
    the same spatial region across frames and classifies solid-tint vs.
    gradient-fade from how much mean_distance_from_bg varies ACROSS those
    frames -- a within-frame color-distance spread was tried first and
    confirmed wrong: a fade is temporal (the same spot changes color across
    the animation), so a single mid-fade frame looks spatially uniform and a
    within-frame spread metric can never see it. Confirmed on the real
    fff2d1 sparkle case (lessons.md SS12): within-frame spread was ~0.0 even
    though the region is a genuine fade.
    """
    bg = np.array(bg_rgb, dtype=float)
    dist = np.linalg.norm(rgb.astype(float) - bg, axis=-1)
    band_lo, band_hi = float(tolerance), float(tolerance) * band_multiplier
    band = (dist > band_lo) & (dist <= band_hi)
    true_bg = dist <= band_lo
    near_bg = ndimage.binary_dilation(true_bg, iterations=edge_margin_px)
    interior_band = band & ~near_bg

    labeled, num = ndimage.label(interior_band, structure=STRUCTURE)
    regions = []
    for lab in range(1, num + 1):
        comp = labeled == lab
        size = int(comp.sum())
        if size < min_size:
            continue
        ys, xs = np.where(comp)
        comp_dist = dist[comp]
        regions.append({
            'pixel_count': size,
            'bbox_xyxy': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            'mean_color': rgb_to_hex(rgb[comp].mean(axis=0)),
            'mean_distance_from_bg': round(float(comp_dist.mean()), 1),
        })
    return regions


def border_bg_component_mask(rgb, bg_rgb, tolerance):
    """Union of every bg-colored connected component that touches the canvas border.

    The same border-label technique analyze() already uses to build
    `enclosed_by_frame`. This is "what is outside the design", which is the right
    question for a LEAK test -- see detect_outline_background_leak for why the
    largest-component version was wrong in both directions.
    """
    bg_mask = color_mask(rgb, bg_rgb, tolerance)
    labeled, n = ndimage.label(bg_mask, structure=STRUCTURE)
    if n == 0:
        return np.zeros_like(bg_mask)
    border_labels = (set(labeled[0, :]) | set(labeled[-1, :])
                     | set(labeled[:, 0]) | set(labeled[:, -1]))
    border_labels.discard(0)
    if not border_labels:
        return np.zeros_like(bg_mask)
    return bg_mask & np.isin(labeled, list(border_labels))


def largest_bg_component_mask(rgb, bg_rgb, tolerance):
    """
    Tumble-safe background detection. Returns a mask of ONLY the single
    largest connected bg-colored region in this frame, instead of "every
    bg-colored region touching the canvas border" (color_mask + border-
    touch, used implicitly wherever the rest of this script treats
    "touches the edge" as synonymous with "is background").

    Why this exists: border-touch is a safe proxy for "is background"
    ONLY when the foreground design never itself reaches the canvas
    edge. That assumption breaks on animated content that rotates or
    translates within the frame -- confirmed on a real tumbling/falling-
    calendar icon where, at the peak of its rotation, a genuine corner of
    the card touched row 639 of a 640px canvas. Border-touch flood-fill
    swept that entire connected white shape -- 22,169px of real card
    content, not background -- into "background" and deleted it, purely
    because it grazed the edge at one point.

    Why "largest component" is a safe replacement rather than just a
    different guess: true background is not merely large, it's
    overwhelmingly large relative to any other same-colored region,
    because it's everything in the canvas that isn't the (much smaller)
    icon. Verified directly on the motivating case across all 124 frames:
    the largest bg-colored component was never less than ~3x the size of
    the second-largest in any single frame, including frames where a
    genuine second large white region (the card's own interior, up to
    ~47,000px) coexisted with it. A 3x-plus margin with zero close calls
    across a full animation is what makes "just take the largest" safe
    here -- if a future asset's background is comparably sized to (or
    smaller than) its own foreground bg-colored regions (e.g. a mostly-
    white illustration where the "background" is only a thin margin),
    this heuristic is the wrong tool; check the margin the same way
    before trusting it blindly (print the top 2-3 component sizes per
    frame and confirm a comfortable, consistent gap).
    """
    mask = color_mask(rgb, bg_rgb, tolerance)
    labeled, num = ndimage.label(mask, structure=STRUCTURE)
    if num == 0:
        return np.zeros(rgb.shape[:2], dtype=bool)
    sizes = ndimage.sum(mask, labeled, range(1, num + 1))
    largest_label = int(np.argmax(sizes)) + 1
    return labeled == largest_label


def measure_bg_component_margin(rgb, bg_rgb, tolerance, mask=None):
    """
    Per-frame safety check for the assumption largest_bg_component_mask relies
    on (see its docstring): true background should be overwhelmingly larger
    than any other same-colored region, not just the largest by any margin.
    Returns the largest and second-largest bg-colored component sizes and
    their ratio, so callers can flag frames where that margin gets
    uncomfortably close -- the confirmed-safe case measured a margin that
    never dropped below ~3x across a full animation.

    Only compares the largest against other BORDER-TOUCHING components, not
    every same-colored component -- an enclosed (non-border-touching)
    component is a candidate design region (exactly what --protect-outline-
    color/--protect-region would target), not a tumble-detection risk, which
    is specifically about the border-touch heuristic breaking down (see
    largest_bg_component_mask's docstring). Without this exclusion, a large
    enclosed candidate region can read as a false "close margin" and wrongly
    trigger a --tumble-safe recommendation that then skips
    --protect-outline-color entirely for every region -- confirmed as a real
    latent risk (not yet observed on the 3 fixtures this was built against,
    but directly analogous to the false positive collect_small_removed_
    region_sizes needed its own size ceiling to avoid, see that function's
    docstring) during the final whole-branch review of this feature.

    Accepts an optional pre-computed `mask` (color_mask(rgb, bg_rgb,
    tolerance)) so a caller iterating every frame for multiple checks
    (analyze() does, for this and collect_small_removed_region_sizes) can
    compute it once and share it -- confirmed via the final whole-branch
    review that escalating these checks from a 40-frame sample to every
    frame (needed to fix real false negatives, see analyze()'s own call
    sites) made --analyze measurably slower, and this redundant per-frame
    color_mask call was one concrete, safe-to-remove piece of that cost.
    """
    mask = color_mask(rgb, bg_rgb, tolerance) if mask is None else mask
    labeled, num = ndimage.label(mask, structure=STRUCTURE)
    if num == 0:
        return {'largest_px': 0, 'second_largest_px': 0, 'margin_ratio': None}
    border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | set(labeled[:, 0]) | set(labeled[:, -1])
    border_labels.discard(0)
    sizes_by_label = {lab: int(s) for lab, s in
                       zip(range(1, num + 1), ndimage.sum(mask, labeled, range(1, num + 1)))}
    largest_label = max(sizes_by_label, key=sizes_by_label.get)
    largest = sizes_by_label[largest_label]
    border_sizes = sorted((sizes_by_label[lab] for lab in border_labels if lab != largest_label),
                           reverse=True)
    second = border_sizes[0] if border_sizes else 0
    margin = (largest / second) if second > 0 else None
    return {
        'largest_px': largest,
        'second_largest_px': second,
        'margin_ratio': round(margin, 2) if margin is not None else None,
    }


def build_tumble_safe_protected_mask(rgb, bg_rgb, tolerance,
                                      keep_bg_blob_if_near_colors=None,
                                      near_tolerance=40, near_dilate_px=6,
                                      hole_size_range=(50, 2000),
                                      hole_max_aspect=3.0):
    """
    Per-frame protected-mask builder for animated/rotating content, as an
    ALTERNATIVE to build_protected_mask / build_protected_masks_robust
    (which lean on --protect-outline-color's binary_fill_holes -- see
    that function's docstring for the "flashing" failure mode it already
    handles). This targets a DIFFERENT failure signature: not a brief
    crossing element breaking one outline color's enclosure, but the
    asset's OWN geometry (self-overlapping card flaps, a shape that
    tumbles through many orientations) making single-frame flood-fill
    enclosure unreliable in ways that don't show up as a sharp isolated
    anomaly against nearby frames -- because the "break" can correlate
    smoothly with rotation progress rather than spiking briefly. Confirmed
    real case: a tumbling calendar/gamepad icon where --protect-outline-
    color's per-frame fill-holes silently failed to fully enclose the
    white card during several tumble frames, deleting real content in a
    way that a 40-frame enclosure_ratio sample from --analyze did not
    catch (see SKILL.md's "Animated/rotating content" section).

    Default behavior (no keep_bg_blob_if_near_colors given): protects
    EVERYTHING that is not the single largest bg-colored component
    (see largest_bg_component_mask) -- i.e. "keep all real content,
    remove only the background", with no risk of deleting a legitimate
    same-color design element, at the cost of not being able to remove
    OTHER small bg-colored regions that also need removing (e.g. a
    hole/cutout in the design itself, distinct from the outer
    background).

    To selectively remove such regions (confirmed real case: a spiral-
    binding icon's punch-holes, which are also enclosed-white and same
    size range as a nearby gamepad's white cross/dot details, but must
    be removed while the cross/dot must NOT be): pass
    keep_bg_blob_if_near_colors, a list of RGB triples for whatever
    color(s) mark "this bg-colored blob is actually decoration, keep
    it" in THIS SPECIFIC asset -- identified the same way outline-color
    verification's manual fallback works (zoom into a frame, sample
    pixels near the region you want to keep vs. the region you want
    removed, find what's different). A candidate small bg-colored blob
    is kept ONLY if it borders one of these colors within
    near_dilate_px; otherwise it's treated as removable, but ONLY if it
    also falls within hole_size_range and its bounding-box aspect ratio
    is <= hole_max_aspect (both default to generous ranges, but should
    be tightened to the real target's measured size/shape on a real
    asset -- on the motivating case, the true holes measured a tight
    280-330px across every one of 124 frames with aspect ~1.0-2.0, and
    narrowing to that range was what kept this from also catching
    incidental antialiasing-noise islands and unrelated card-fragment
    slivers elsewhere in the frame). This is inherently per-asset-
    calibrated, not a universal rule -- there is no substitute for
    looking at the actual art.
    """
    core = largest_bg_component_mask(rgb, bg_rgb, tolerance)
    mask = color_mask(rgb, bg_rgb, tolerance)
    labeled, num = ndimage.label(mask, structure=STRUCTURE)
    if num == 0:
        return ~core

    sizes = ndimage.sum(mask, labeled, range(1, num + 1))
    core_label = int(np.argmax(sizes)) + 1
    removable = core.copy()

    if keep_bg_blob_if_near_colors:
        target_rgbs = keep_bg_blob_if_near_colors
        for lab in range(1, num + 1):
            if lab == core_label:
                continue
            comp = (labeled == lab)
            cnt = comp.sum()
            if cnt < 20:
                continue
            ys, xs = np.where(comp)
            w = xs.max() - xs.min() + 1
            h = ys.max() - ys.min() + 1
            aspect = max(w, h) / max(1, min(w, h))
            if not (hole_size_range[0] <= cnt <= hole_size_range[1] and aspect <= hole_max_aspect):
                continue
            dil = ndimage.binary_dilation(comp, structure=np.ones((3, 3)), iterations=near_dilate_px // 2 + 1)
            ring = dil & ~comp
            ring_colors = rgb[ring]
            near_hit = False
            for target in target_rgbs:
                d = np.linalg.norm(ring_colors.astype(float) - np.array(target, dtype=float), axis=-1)
                if (d < near_tolerance).any():
                    near_hit = True
                    break
            if not near_hit:
                removable |= comp

    return ~removable


def build_band_only_removal_mask(removable_core, band_px):
    """
    Given the definitively-removable pixels (background union any
    verified holes, i.e. the INVERSE of a protected mask), return a
    protected mask that keeps EVERYTHING except removable_core and a
    thin band_px-wide ring immediately around it -- for use in place of
    an allowlist-style protected mask when calling
    estimate_alpha_and_defringe.

    Why: estimate_alpha_and_defringe (and the feathering path in general)
    decides a pixel's alpha by its raw color distance to the background
    color, for any pixel NOT explicitly marked protected. An allowlist
    protected mask (only mark the specific regions you've verified are
    safe) leaves every OTHER color in the image subject to that distance
    check -- which silently breaks for any solid, deliberate design color
    that happens to sit close to the background color for reasons that
    have nothing to do with antialiasing (a pale tint, a soft shadow/glow
    shape, a light gradient fill). Confirmed real case: a flat light-blue
    "shadow" design shape (RGB ~209,220,251, a distance of 46 from pure
    white) fell inside the default feathering transition band (tolerance
    x feather-band-multiplier = 15 x 4 = 60) purely by coincidence, so it
    was treated as if it were an antialiased blend toward the background
    and given unstable, partial alpha -- producing a visibly speckled/
    noisy edge where that shape met the surrounding page, even after
    dithering was ruled out as the cause (confirmed by testing a hard
    50%% cutoff with dithering removed entirely -- the noise persisted).

    Inverting the default (protect everything EXCEPT a thin ring around
    what's actually being removed, rather than an allowlist of what to
    keep) fixes this generically for any future asset with tinted/shadow
    elements near the background color, with no per-asset color tuning
    needed for the protection step itself. band_px should be at least as
    wide as the real antialiasing fringe in the source art (4px was
    sufficient on the motivating case; if fringe survives after this,
    check the source art's actual blend width the same way edge_hardness
    is checked, and widen band_px to match rather than guessing).
    """
    ring = ndimage.binary_dilation(
        removable_core, structure=np.ones((2 * band_px + 1, 2 * band_px + 1))
    ) & ~removable_core
    return ~removable_core & ~ring


def compute_alpha_mask(rgb, protected, args, removal_scope=None, rgb_key=None):
    """
    Full alpha decision for one frame, combining the hard background mask
    with (optionally) feathered/dithered edges. Returns (alpha_uint8, rgb_out).

    `removal_scope`, when given, is a boolean mask OUTSIDE of which nothing may
    be made transparent. It is how an already-transparent source is honoured:
    the source's own alpha has already answered the question for every pixel it
    covers, so colour matching is confined to that region plus a thin band
    around it (the only place a leftover matte fringe can live). Without it, a
    padding colour that also appears in the artwork deletes the artwork -- see
    source_transparency_is_the_background.
    """
    bg_rgb = hex_to_rgb(args.bg_color)
    # Every colour COMPARISON below reads `key`; every pixel returned still comes from
    # `rgb`. Defaults to `rgb`, so a caller that does not pass it is unchanged.
    key = rgb if rgb_key is None else rgb_key

    if not args.feather:
        bg_mask = color_mask(key, bg_rgb, args.tolerance)
        transparent_mask = bg_mask & ~protected
        if removal_scope is not None:
            transparent_mask &= removal_scope
        alpha = np.where(transparent_mask, 0, 255).astype(np.uint8)
        return alpha, rgb

    alpha_f, recolored, band_mask = estimate_alpha_and_defringe(
        rgb, bg_rgb, protected, args.tolerance, args.feather_band_multiplier, rgb_key=key
    )
    dither_mode = getattr(args, 'dither_mode', 'bayer')
    if dither_mode == 'continuous':
        # No dither and no cutoff: keep the estimated alpha as real 8-bit
        # partial transparency. Only meaningful for a container that
        # supports it (WebP); GIF has 1 bit of alpha, which is the entire
        # reason the bayer/none modes above exist. See references/lessons.md
        # SS16 for the measured case that motivated this.
        alpha = np.clip(np.rint(alpha_f * 255.0), 0, 255).astype(np.uint8)
        if removal_scope is not None:
            # ⚠️ THE THIRD RETURN. This branch is the DEFAULT for every 8-bit-alpha
            # container (line ~5131 sets dither_mode='continuous' for .webp/.avif/
            # .apng/.png), so it is the one a PNG sprite actually takes -- and the
            # first version of this scope logic applied it at the other two returns
            # only. The result: --pixel-art (feather off) survived 100% while a
            # plain PNG run still lost 2,455 outline pixels, and the log said
            # "SOURCE ALPHA HONOURED" both times. Exactly the inverse-spelling
            # failure SS28.13 records, committed while documenting it.
            alpha = np.where(removal_scope, alpha, 255).astype(np.uint8)
            recolored = np.where(removal_scope[..., None], recolored, rgb)
        return alpha, recolored
    if dither_mode == 'none':
        # Hard 50% cutoff on the ALREADY-defringed alpha, instead of a
        # spatial Bayer pattern. Keeps the color-unmixing benefit (no
        # whitish fringe ring) but produces a single clean edge instead
        # of a dithered soft one.
        #
        # Why this is an option at all, not just strictly worse: Bayer
        # dithering is a real, deliberate trick for simulating soft
        # antialiased edges under GIF's 1-bit alpha limit, and it works
        # well when the delivered asset ends up composited over varied/
        # textured backgrounds. But confirmed on a real case: the exact
        # same dithered edge that looks like reasonable soft antialiasing
        # in isolation reads as visible "glitchy noise" the moment it's
        # composited over a SOLID flat color (a green-screen transparency
        # check, but just as relevant to a solid-color chat bubble or
        # app background the asset might realistically land on) --
        # because a spatial dither pattern only reads as "smooth" against
        # content with its own texture to blend into; against a flat
        # color it's just visible speckle. 'none' trades a very slightly
        # harder edge silhouette for zero visible noise on any
        # background, which is the safer default for small flat-vector
        # icon/sticker GIFs (this skill's primary target) whenever the
        # final placement context isn't known to be textured/varied.
        keep = alpha_f > 0.5
    else:
        keep = ordered_dither_mask(
            alpha_f, tile=BAYER8 if getattr(args, 'bayer_size', 8) == 8 else BAYER4)
    # Outside the transition band, alpha_f is already exactly 0 or 1 (or 1 if
    # protected), so dithering there is a no-op; this keeps behavior identical
    # to the hard-cutoff path away from edges.
    alpha = np.where(keep, 255, 0).astype(np.uint8)
    if removal_scope is not None:
        # Outside the scope, keep BOTH the opacity and the original colour:
        # estimate_alpha_and_defringe recolours edge pixels to unmix them from
        # the background, and unmixing art from a padding colour it merely
        # resembles is the same error one level down.
        alpha = np.where(removal_scope, alpha, 255).astype(np.uint8)
        recolored = np.where(removal_scope[..., None], recolored, rgb)
    return alpha, recolored


def build_protected_mask(rgb, args):
    H, W, _ = rgb.shape
    if args.protect_outline_color:
        union = np.zeros((H, W), dtype=bool)
        for hex_color in args.protect_outline_color.split(','):
            hex_color = hex_color.strip()
            if not hex_color:
                continue
            outline_rgb = hex_to_rgb(hex_color)
            omask = color_mask(rgb, outline_rgb, args.outline_tolerance)
            if not omask.any():
                print(f"WARNING: outline color {hex_color} not found in this "
                      f"frame; no interior protection applied for it in this "
                      f"frame.", file=sys.stderr)
                continue
            union |= ndimage.binary_fill_holes(omask, structure=STRUCTURE)
        return union
    elif args.protect_region:
        return parse_protect_regions(args.protect_region, (H, W))
    else:
        return np.zeros((H, W), dtype=bool)


def detect_anomalous_frame_sizes(sizes, window=5, local_ratio_threshold=0.8, gap_ratio_threshold=1.08):
    """
    Given a per-frame array of region sizes (pixel counts), flag frames whose
    size is anomalously low relative to the rest of the sequence, using two
    detectors that catch different occlusion patterns (see
    build_protected_masks_robust's docstring for the full history and the
    real cases each detector was built against):
    (a) local-neighborhood sharp drop -- catches brief, isolated occlusion;
    (b) whole-distribution bimodal gap -- catches sustained occlusion
        spanning many consecutive frames.
    Returns a boolean array, one entry per input frame, True where anomalous.
    """
    n = len(sizes)
    nonzero = sizes[sizes > 0]

    local_flags = np.zeros(n, dtype=bool)
    for i in range(n):
        lo, hi = max(0, i - window), min(n, i + window + 1)
        neighborhood = [sizes[j] for j in range(lo, hi) if j != i]
        if not neighborhood:
            continue
        if sizes[i] < local_ratio_threshold * np.median(neighborhood):
            local_flags[i] = True

    gap_flags = np.zeros(n, dtype=bool)
    sorted_sizes = np.sort(nonzero)
    if len(sorted_sizes) > 1:
        gaps = np.diff(sorted_sizes)
        max_gap_idx = np.argmax(gaps)
        below, above = sorted_sizes[max_gap_idx], sorted_sizes[max_gap_idx + 1]
        if below > 0 and above / below >= gap_ratio_threshold:
            gap_threshold = (below + above) / 2
            # ⚠️ A "flag only a minority of frames" guard was TRIED HERE AND
            # REVERTED (2026-08-17). The theory was that occlusion is the
            # exception, so a small-mode majority must be the baseline. Measured
            # on crystal.gif, where the small mode IS the majority (75/130):
            # suppressing the flags took art loss from 0.95% to 7.07% and left
            # an 11,451 px hole, because there the small mode is the BROKEN
            # state -- the outline genuinely fails to enclose in those frames.
            # A majority can be wrong. Do not re-add this guard.
            gap_flags = sizes < gap_threshold

    return local_flags | gap_flags


def build_protected_masks_robust(rgb_frames, args):
    """
    Compute a protected mask for EVERY frame, but correct for a real,
    confirmed failure mode of single-frame flood-fill enclosure:
    --protect-outline-color's `binary_fill_holes` on the outline-color
    mask requires the outline to form a fully CLOSED ring in that specific
    frame. If any other animated design element (confirmed real cases: a
    wifi signal pulse animation; a "wipe" sweep effect) happens to
    visually cross or overlap the outline at some frames, it locally
    replaces outline-color pixels with its own color, punching a gap that
    makes the ring non-closed for just those frames -- and
    `binary_fill_holes` doesn't degrade gracefully when that happens, it
    leaks interior out. The visible symptom is the protected region
    intermittently going transparent -- "flashing" -- exactly matching
    real user reports on two separate icons.

    This is NOT something --analyze's `outline_color_verified` catches:
    that check only verifies the outline color against a SINGLE frame
    (the first sampled one), then the same color gets applied uniformly
    to every frame during real processing, with no cross-frame check that
    the same color reliably encloses the region everywhere.

    HISTORY, kept because it directly informs the current design -- two
    more aggressive approaches were tried and reverted:
    - Patching in ANY per-pixel difference from a majority-vote reference
      built across many/all frames (even gated to only fire on frames
      with a real aggregate-area drop) produced visible incorrect white
      "ghost" patches on a real file after end-to-end delivery -- caught
      by a user, not by pre-ship testing. Root cause, confirmed after the
      fact: a majority-vote reference built across frames where the
      protected shape MOVES (not just where it's occluded) blends
      together every position that shape was ever in into one smeared
      composite, then patches that composite into individual frames --
      producing exactly a "ghost of an earlier position" artifact on any
      icon with real motion, not just rotation. Confirmed independently
      on a SECOND icon with a cloud that shifts position/size as part of
      its normal animation (that icon's own filled-area ratio naturally
      swings from 0.50 to 1.06 -- even more dramatic than the rotating-
      icon case that first exposed this).
    - Whole-frame substitution with NO gate also broke the
      first rotating-icon case for the analogous reason (one frame's
      content silently replaced by an unrelated frame's).
    - Lesson from both: never compare a frame's protected-region content
      against ANY reference built by combining/blending multiple frames
      when the design may legitimately move. Any fix here must be
      re-verified against multiple real animated icons (not just the one
      motivating the change) before being trusted, specifically checking
      for smeared/frozen-shape artifacts, not just whether the originally
      reported gap closed.

    Current approach, detection: a frame is anomalous if EITHER (a) its
    filled area is a sharp, ISOLATED drop versus its own small local
    neighborhood (window of nearby frames), which catches brief
    transient occlusions (confirmed case: a wifi pulse crossing the
    outline for a few frames at a time) without misfiring on gradual
    animation (confirmed safe on a rotating icon and two icons with large
    smooth pulse/shift cycles -- a single genuine one-frame anomaly
    embedded in one of those smooth cycles was still correctly caught,
    because it's a sharp local outlier even though the broader cycle
    has large amplitude); OR (b) the whole animation's filled-area
    distribution shows a clear statistical gap separating a low cluster
    from a high cluster (a sorted-value jump of >=8%), which catches
    SUSTAINED occlusion spanning many consecutive frames (confirmed case:
    a continuous "wipe" sweep effect) that (a) alone under-catches since
    it's not a brief isolated blip. Both mechanisms were verified to
    produce ZERO false positives across every legitimate-animation test
    case available (a rotation, and two large-amplitude smooth pulse/
    shift cycles) before being combined; neither alone was sufficient for
    all confirmed real bugs, which is why both run together (union of
    flagged frames).

    Detection: for each --protect-outline-color color independently
    (never on a union across colors -- confirmed a union can dilute one
    color's real anomaly below detection since other colors' stable
    regions inflate the combined total). Substitution: the SPECIFIC
    anomalous frame's mask is replaced with the mask from the temporally
    NEAREST individual non-anomalous frame (never a blended/combined
    reference across multiple frames -- that blending is exactly the
    mechanism that caused the reverted regressions above).

    Known remaining gap: the sustained-occlusion detector requires a
    genuine statistical gap in the distribution; if a sustained occlusion
    doesn't produce a clean gap (e.g. it's present in most frames with
    only mild severity, or the animation's own natural variation is
    noisy enough to mask the gap), it won't be caught. Confirmed on one
    real sustained-occlusion case that this catches roughly half the
    visibly-bad frames, not all of them -- an improvement over catching
    almost none, but not a complete fix. Do not claim this is fully
    resolved without re-checking the specific case.

    --protect-region doesn't have this failure mode at all (it's pure
    geometry, no color/flood-fill involved), so it's passed through
    unchanged.
    """
    n = len(rgb_frames)
    H, W, _ = rgb_frames[0].shape

    if args.protect_region:
        return [parse_protect_regions(args.protect_region, (H, W)) for _ in range(n)]
    if not args.protect_outline_color:
        return [np.zeros((H, W), dtype=bool) for _ in range(n)]

    hex_colors = [c.strip() for c in args.protect_outline_color.split(',') if c.strip()]
    per_color_masks = {}  # hex -> list of per-frame filled masks
    for hex_color in hex_colors:
        outline_rgb = hex_to_rgb(hex_color)
        frame_masks = []
        for rgb in rgb_frames:
            omask = color_mask(rgb, outline_rgb, args.outline_tolerance)
            filled = ndimage.binary_fill_holes(omask, structure=STRUCTURE) if omask.any() else omask
            frame_masks.append(filled)

        sizes = np.array([mm.sum() for mm in frame_masks])
        nonzero = sizes[sizes > 0]
        if len(nonzero) == 0:
            per_color_masks[hex_color] = frame_masks
            continue

        bad_flags = detect_anomalous_frame_sizes(sizes)
        bad_idxs = [i for i in range(n) if bad_flags[i]]
        good_idxs = [i for i in range(n) if not bad_flags[i] and sizes[i] > 0]

        if bad_idxs and good_idxs:
            print(f"NOTE: --protect-outline-color {hex_color}'s enclosure "
                  f"broke down (likely another animated element crossing "
                  f"the outline) on {len(bad_idxs)}/{n} frames; substituting "
                  f"the nearest good frame's mask for those so the "
                  f"protected region doesn't flicker.", file=sys.stderr)
            # ⚠️ CLAMP the borrowed mask to THIS frame's own silhouette. A mask
            # lifted from another frame describes that frame's geometry, so on
            # anything that moves or grows it protects background the current
            # frame does not cover. Confirmed real case (crystal.gif): a yellow
            # sparkle crossing the outline broke enclosure on 75/130 frames, and
            # the borrowed masks left a white wedge floating above the tall
            # crystal's tip in frames 0-18 -- ~1,600 px/frame of background kept
            # opaque, visible against any non-white backdrop. Intersecting with
            # the frame's own filled silhouette keeps the useful part of the
            # substitution (interior detail that IS enclosed here) and drops the
            # part that describes a different frame.
            # UNION, then clamp -- do not REPLACE. The frame's own mask is
            # partially correct even when flagged: it encloses whatever this
            # frame does enclose. Replacing it with a borrowed mask throws that
            # away, and anything the borrowed mask happens to miss at this
            # frame's geometry is simply lost. Confirmed on crystal.gif: pure
            # replacement deleted ~500 px from inside the left crystal in
            # frames 0-19, while the frame's own mask covered it correctly.
            #
            # The clamp to this frame's filled silhouette stays, because a
            # borrowed mask describes ANOTHER frame's geometry and would
            # otherwise protect background this frame does not cover (the white
            # wedge above the tall crystal's tip, ~1,600 px/frame).
            bg_for_clamp = hex_to_rgb(args.bg_color)
            own_raw = list(frame_masks)
            for bi in bad_idxs:
                nearest = min(good_idxs, key=lambda gi: abs(gi - bi))
                silhouette = ndimage.binary_fill_holes(
                    ~color_mask(rgb_frames[bi], bg_for_clamp, args.tolerance),
                    structure=STRUCTURE)
                frame_masks[bi] = (own_raw[nearest] | own_raw[bi]) & silhouette
        per_color_masks[hex_color] = frame_masks

    result = []
    for i in range(n):
        union = np.zeros((H, W), dtype=bool)
        for hex_color in hex_colors:
            union |= per_color_masks[hex_color][i]
        result.append(union)
    return result


def _timing_line(output_path, in_durations, out_alpha):
    """Timing description, or the honest static-image line when there is no animation.

    A static source has no timing to preserve, and comparing its default 100ms placeholder against
    a written PNG's 0ms produced "a real timing defect, not encoder frame-coalescing" on an
    ordinary single-frame sprite. v5.4.0 added the static-image line to the PROCESS path and left
    verify() comparing durations -- the same split-brain that SS28.8 found in `n_frames`, where the
    processing path was fixed and two other readers were not. Shared by BOTH of verify()'s exits
    (the early dimension-mismatch return had its own copy of the call). SS28.13
    """
    if len(in_durations) <= 1 and len(out_alpha) <= 1:
        return "1 frame (static image -- no animation timing to verify)"
    return describe_written_timing(output_path, in_durations)


def describe_written_timing(output_path, intended_durations):
    """
    Describe the timing of the file that was ACTUALLY written, by reading it
    back -- never by restating the frame list we meant to write.

    Why this exists (found 2026-08-07, see references/lessons.md §13): the
    old line here printed `len(durations)` and asserted "durations preserved
    exactly" without ever opening the output. On a real 170-frame job it
    reported 170 while the file on disk had 168, because Pillow's GIF
    encoder coalesces consecutive frames that come out byte-identical after
    quantization and folds their delays into the survivor. Total playback
    was genuinely unchanged, so nothing was broken -- but the message was a
    claim about a file nobody had looked at, which is exactly the kind of
    unverified assertion the rest of this skill's verification rules exist
    to prevent.

    Coalescing is not a defect and is not worth suppressing: the dropped
    frames were visually identical, and refusing the merge would only make
    the file bigger. What matters is saying what actually happened. A real
    change in total playback length WOULD be a defect, so that gets an
    explicit warning rather than a quiet mention.
    """
    intended_total = sum(d or 0 for d in intended_durations)
    try:
        written = []
        with Image.open(output_path) as im:
            i = 0
            while True:
                try:
                    im.seek(i)
                except EOFError:
                    break
                written.append(frame_duration_ms(im) or 0)
                i += 1
    except Exception as exc:
        # Readback is a reporting nicety, never a reason to fail a job that
        # already wrote its output successfully.
        return (f"{len(intended_durations)} frames intended; could not read "
                f"back the written file to confirm timing ({exc})")

    written_total = sum(written)
    if written == list(intended_durations):
        return f"{len(written)} frames, durations preserved exactly"

    if written_total != intended_total:
        print(f"WARNING: total playback length changed on write "
              f"({intended_total}ms intended, {written_total}ms written). "
              f"This is a real timing defect, not encoder frame-coalescing.",
              file=sys.stderr)
        return (f"{len(written)} frames written from {len(intended_durations)} "
                f"intended, total {written_total}ms vs {intended_total}ms intended")

    merged = len(intended_durations) - len(written)
    return (f"{len(written)} frames written from {len(intended_durations)} "
            f"intended -- {merged} identical frame(s) coalesced by the encoder, "
            f"total playback unchanged at {written_total}ms")


def load_animation_rgba_frames(path):
    """
    Read every frame of a GIF as (rgb, alpha, duration). Works for both an
    unprocessed source (alpha will be all-255, since a source GIF's own
    transparency handling is a separate concern -- see
    get_source_transparency_mask) and an already-processed output (alpha
    reflects its real transparency index).
    """
    im = Image.open(path)
    n = getattr(im, 'n_frames', 1)   # static source: JPEG raises on the bare attribute
    rgb_frames, alpha_frames, durations = [], [], []
    for i in range(n):
        im.seek(i)
        durations.append(frame_duration_ms(im, 100))
        arr = np.array(im.convert('RGBA'))
        # .copy(): a bare slice is a VIEW into arr, so without copying,
        # every element of rgb_frames/alpha_frames keeps its own frame's
        # full RGBA buffer alive for the whole call (verify() holds three
        # complete GIF decodes at once -- input, output, and the alpha
        # channel from each -- so this is a real, not theoretical, memory
        # cost on a large animation). Copying lets the RGBA array itself be
        # garbage collected once split.
        rgb_frames.append(arr[:, :, :3].copy())
        alpha_frames.append(arr[:, :, 3].copy())
    return rgb_frames, alpha_frames, durations


# Kept because the old name appears in this project's own written history
# (references/lessons.md SS17). The reader is GIF-only in name only: it handles
# GIF, WebP, AVIF, APNG, PNG and JPEG, and that name reinforced the GIF-only
# misconception inside the code -- the same misconception that kept non-GIF
# input out of the skill description for two versions.
load_gif_rgba_frames = load_animation_rgba_frames

def align_input_to_output_frames(in_durations, out_durations):
    """
    Map each output frame index to the input frame index it actually
    corresponds to, accounting for Pillow's GIF-encoder frame coalescing:
    consecutive frames that come out byte-identical after quantization get
    merged, with their delays folded into the one frame the encoder keeps
    (see describe_written_timing's docstring / references/lessons.md SS13
    for the real confirmed case this handles -- 170 frames in, 168 out).
    Pillow keeps the FIRST frame of each identical run and extends its own
    delay to cover the run, so each output frame maps to the first input
    frame of the run that collapsed into it.

    Matches runs by accumulating input durations until they sum to each
    output duration in turn, in order -- both duration lists are exact
    integers read from real GIF frame data, so this is an exact match, not
    a fuzzy one. Returns a list the same length as out_durations (input
    frame index per output frame), or None if the durations don't
    reconcile at all (a real timing defect describe_written_timing already
    flags separately -- this function isn't the place to also report that).
    """
    mapping = []
    in_idx = 0
    for out_dur in out_durations:
        if in_idx >= len(in_durations):
            return None
        start_idx = in_idx
        acc = in_durations[in_idx]
        in_idx += 1
        while acc < out_dur and in_idx < len(in_durations):
            acc += in_durations[in_idx]
            in_idx += 1
        if acc != out_dur:
            return None
        mapping.append(start_idx)
    if in_idx != len(in_durations):
        return None
    return mapping


def verify(input_path, output_path, tolerance=15):
    """
    Mechanical half of SKILL.md's "Verification" checklist: leftover
    background, protected-region coverage, edge fringe, small removed-
    region inflation (see erode_alpha_edge_exempting_tiny_regions's
    docstring for the real bug this last check targets), and duration/
    frame-count (delegated straight to describe_written_timing). Does NOT
    judge whether an edge "looks" soft/jagged or whether a --protect-region
    bulge follows the art's own silhouette -- those genuinely need a
    human/agent's eyes and stay in SKILL.md as a visual check.

    CORRECTED DURING TASK 10 IMPLEMENTATION (real, data-confirmed design
    flaws in the original draft, caught by an implementer running the
    negative-validation test rather than trusting the design on paper):
    the original leftover_background_opaque_px had no way to distinguish
    a correctly-protected bg-colored interior (--protect-outline-color
    working as intended) from genuinely leftover unremoved background --
    both look IDENTICAL from raw color alone (bg-colored in input, opaque
    in output). And the original small_region_inflation match had no
    pixel-overlap sanity check on top of its centroid-distance search, so
    it could match a tiny input region to a large, unrelated, irregularly-
    shaped background blob whose CENTROID (not its actual pixels)
    coincidentally landed nearby -- confirmed as a real false positive on
    jewelry.gif. Both are fixed below by having verify() call analyze()
    on the input and reuse its own candidate-region detection (which
    already knows how to tell "large enclosed likely-intentional region"
    from "true background") -- this also adds protected_region_coverage,
    a check for the actual failure mode the negative-validation test was
    exercising (a region that should have stayed protected but didn't),
    which nothing in the original design could see at all.
    """
    in_rgb, in_alpha, in_durations = load_animation_rgba_frames(input_path)
    out_rgb, out_alpha, out_durations = load_animation_rgba_frames(output_path)

    report = {'input_path': input_path, 'output_path': output_path}

    if in_rgb[0].shape != out_rgb[0].shape:
        report['dimensions_match'] = False
        ih, iw = in_rgb[0].shape[:2]
        oh, ow = out_rgb[0].shape[:2]
        report['input_dims'] = [iw, ih]
        report['output_dims'] = [ow, oh]
        report['note'] = ('Input/output canvas size differs (crop/resize likely used) -- '
                           'pixel-position checks are skipped; only the timing check ran.')
        report['timing'] = _timing_line(output_path, in_durations, out_alpha)
        return report

    report['dimensions_match'] = True

    # Align input frames to output frames by DURATION, not raw index --
    # the encoder can coalesce consecutive identical frames (real confirmed
    # case: 170 in, 168 out, see describe_written_timing's docstring), and
    # naive index pairing would silently compare mismatched animation
    # frames past the first coalesced run. Rebinding in_rgb to the aligned
    # list means every loop below that already indexes in_rgb[i]/out_*[i]
    # for i in range(n) is correct without further changes.
    mapping = align_input_to_output_frames(in_durations, out_durations)
    if mapping is not None:
        in_rgb = [in_rgb[j] for j in mapping]
        report['frame_alignment'] = 'exact'
    else:
        m = min(len(in_rgb), len(out_rgb))
        in_rgb, out_rgb, out_alpha = in_rgb[:m], out_rgb[:m], out_alpha[:m]
        report['frame_alignment'] = ('index_fallback -- durations did not reconcile into a '
                                      'clean coalescing pattern; comparing by raw index, '
                                      'which may compare mismatched frames past any divergence')

    n = len(in_rgb)
    bg_rgb = detect_bg_color(in_rgb[0], warn=False)

    # Reuse analyze()'s own candidate-region detection so the checks below
    # can tell "background-colored input pixel that's a legitimate
    # protected interior" from "background-colored input pixel that's
    # really just background" -- see the docstring above for why this is
    # necessary, not optional polish.
    input_analysis = analyze(input_path, tolerance=tolerance)
    _out_fmt = format_from_path(output_path)

    protected_regions = [r for r in input_analysis['candidate_regions']
                          if r['likely_intentional_design']]
    H, W = in_rgb[0].shape[:2]
    # A modest bbox union, dilated a few px, scoping WHERE a real candidate
    # region could be -- used only to restrict the per-frame enclosed-mask
    # computation below to known candidate areas, not as the exclusion mask
    # itself (see the fix note just below for why a bare rectangle isn't
    # precise enough on its own).
    bbox_scope = np.zeros((H, W), dtype=bool)
    for r in protected_regions:
        x0, y0, x1, y1 = r['bbox_xyxy']
        bbox_scope[y0:y1 + 1, x0:x1 + 1] = True
    bbox_scope = ndimage.binary_dilation(bbox_scope, iterations=5) if protected_regions else bbox_scope

    leftover_bg_counts = []
    fringed_pixel_fractions = []
    bg_masks = []
    # Art palette for the fringe metric below. Built from the INPUT, whose flat
    # colours are the reference the ring is compared against.
    _fringe_palette = build_art_palette(in_rgb[::max(1, n // 8)] or in_rgb[:1], bg_rgb)
    for i in range(n):
        bg_mask = color_mask(in_rgb[i], bg_rgb, tolerance)
        bg_masks.append(bg_mask)

        # Real per-frame enclosed-region footprint, not a static bbox
        # rectangle -- confirmed during the final whole-branch review that
        # a bare rectangle blanks out its whole area regardless of the
        # actual (often irregular) candidate shape, which could mask a
        # genuine leftover-background bug that happens to fall in the
        # rectangle's corners. Same border-touching-exclusion technique
        # analyze() itself uses to find these regions in the first place,
        # scoped to bbox_scope so a coincidentally enclosed area elsewhere
        # in THIS frame that has nothing to do with a known candidate
        # region isn't also swept in.
        labeled, num = ndimage.label(bg_mask, structure=STRUCTURE)
        border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | set(labeled[:, 0]) | set(labeled[:, -1])
        border_labels.discard(0)
        enclosed = bg_mask & ~np.isin(labeled, list(border_labels)) & bbox_scope

        # Also exclude whatever a VERIFIED outline colour legitimately protects.
        # `enclosed` only covers regions that are enclosed in THIS frame, but a
        # protected region can open to the outside in some frames while still
        # being correctly kept opaque -- those pixels are then counted as
        # leftover background even though keeping them was the whole point.
        # Measured on gift: 3,878 px on the worst frame, all of them the white
        # strip the outline protects. Reconstructing the same fill the pipeline
        # would apply takes it to 0.
        _protected_fill = np.zeros_like(bg_mask)
        for _r in protected_regions:
            _hex = _r.get('candidate_outline_color')
            if _r.get('outline_color_verified') and _hex:
                _protected_fill |= ndimage.binary_fill_holes(
                    color_mask(in_rgb[i], hex_to_rgb(_hex), 40))
        # An 8-bit-alpha output legitimately carries partly transparent
        # background-coloured pixels (a recovered fade, an antialiasing ramp);
        # only a essentially-opaque one is leftover background.
        still_opaque = (bg_mask & (out_alpha[i] >= 250)
                        & ~enclosed & ~_protected_fill)
        leftover_bg_counts.append(int(still_opaque.sum()))

        # Fraction of the edge ring still close to the background color, not
        # the ring's MEAN distance -- confirmed on a real fixture that the
        # mean has essentially no discriminative power: it's dominated by
        # the art's own outline color (which can be hundreds of units from
        # bg), so a localized background-colored fringe (the actual failure
        # this check exists for) can't move a whole-silhouette mean
        # anywhere near `tolerance`. A per-pixel fraction is scale-free and
        # localized regardless of the art's own dominant colors.
        # iterations=1: the OUTERMOST opaque ring only. That is exactly the ring
        # erosion removes, and measured at 2 it dilutes the signal with pixels one
        # step further in that erosion never touches (love erosion-0 reads 0.2647
        # at ring 1 versus 0.1726 at ring 2, against an unchanged clean baseline).
        edge_ring = ndimage.binary_dilation(out_alpha[i] == 0, iterations=1) & (out_alpha[i] > 0)
        if edge_ring.any():
            # ⚠️ This used to ask whether a ring pixel was WITHIN `tolerance` of
            # the background colour, which is far too strict to detect a real
            # fringe: a pale fringe pixel is a BLEND, tens of units away from
            # pure background, so it passed. That version returned
            # looks_fringed=False at erosion 0, 1 AND 2 on the same asset --
            # including a level with a fringe visible by eye -- and the false
            # negative was trusted and shipped a regression (SS16).
            #
            # The question that actually discriminates is RELATIVE: is this
            # ring pixel closer to the background than to any real art colour?
            # Measured on the asset that exposed the false negative, erosion
            # 0/1/2: 49.1% / 0.2% / 0.7%.
            _v = measure_outer_ring_background_fraction(
                out_rgb[i], out_alpha[i], bg_rgb, _fringe_palette)
            if _v is not None:
                fringed_pixel_fractions.append(_v)

    report['leftover_background_opaque_px'] = {
        'max_per_frame': max(leftover_bg_counts) if leftover_bg_counts else 0,
        'worst_frame_index': int(np.argmax(leftover_bg_counts)) if leftover_bg_counts else None,
        'total_frames_with_any': sum(1 for c in leftover_bg_counts if c > 0),
    }
    _fringe_mean = float(np.mean(fringed_pixel_fractions)) if fringed_pixel_fractions else None
    if _fringe_mean is None:
        _fringe_verdict, _fringe_basis = None, 'no opaque edge ring found in any frame'
    elif _fringe_mean > 0.15:
        _fringe_verdict, _fringe_basis = True, (
            f'{_fringe_mean:.4f} is above 0.15, higher than every measured clean output '
            f'(worst clean 0.0830) -- a real pale fringe')
    elif _fringe_mean < 0.04:
        _fringe_verdict, _fringe_basis = False, (
            f'{_fringe_mean:.4f} is below 0.04, lower than every measured fringed output '
            f'(faintest fringed 0.0665) -- edge is clean')
    else:
        _fringe_verdict, _fringe_basis = None, (
            f'{_fringe_mean:.4f} falls in the 0.04-0.15 band where fringed and clean outputs '
            f'OVERLAP across assets (art with a baked-in fade carries pale near-background '
            f'pixels at its boundary legitimately). INCONCLUSIVE -- do not use this to choose '
            f'--edge-cleanup-erosion. Compare this asset against its own erosion 0/1/2 outputs, '
            f'or composite over a dark solid and look')
    report['output_format'] = _out_fmt
    if _out_fmt != 'gif':
        report['scope_note'] = (
            "8-bit-alpha output. Every check here is now partial-alpha aware: "
            "leftover background counts only ESSENTIALLY OPAQUE (alpha>=250) "
            "background-coloured pixels, because a recovered fade or an antialiasing "
            "ramp is legitimately pale AND semi-transparent; the fringe metric looks "
            "only at the outermost near-opaque ring for the same reason. Before "
            "2026-08-17 --verify refused non-GIF output entirely rather than report "
            "a 1-bit-assumption result as though it meant something.")
    report['edge_fringe_check'] = {
        'mean_fringed_pixel_fraction': round(_fringe_mean, 4) if _fringe_mean is not None else None,
        'metric': 'fraction of outermost opaque ring closer to background than to any art colour',
        # TRI-STATE, and deliberately so. Measured across 4 real assets at
        # erosion 0 (fringed) vs 1 and 2 (clean):
        #
        #   asset     er0      er1      er2
        #   love      0.2647   0.0765   0.0755
        #   heart     0.0665   0.0000   0.0000
        #   gift      0.4000   0.0372   0.0362
        #   crystal   0.1681   0.0830   0.0823
        #
        # The metric separates cleanly WITHIN each asset (every er0 is 2-4x its
        # own clean baseline) but the ranges OVERLAP across assets: heart's
        # fringed 0.0665 sits below crystal's clean 0.0830, because an asset
        # with a baked-in fade carries pale near-background pixels at its
        # boundary legitimately. Tightening the ratio does not rescue it --
        # tested at 0.6, 0.4 and 0.25 of the art distance, and 0.4 and below
        # collapse every asset to 0.0000, a test that cannot fail.
        #
        # So no single global threshold is honest here, and inventing one is how
        # this check earned its previous false negative. Above 0.15 is above
        # every measured clean value; below 0.04 is below every measured fringed
        # value; in between the check reports None and says why, rather than
        # guessing. An unverifiable answer must present as unverified
        # (SS13/SS16/SS17), never as a pass.
        'looks_fringed': _fringe_verdict,
        'verdict_basis': _fringe_basis,
    }

    # Protected-region coverage: the opposite failure direction from
    # leftover background -- a region analyze() flagged as likely
    # intentional design (high enclosure_ratio) that DIDN'T stay opaque in
    # the output, e.g. --protect-outline-color was omitted or used the
    # wrong color. Restricted to pixels that are background-colored in the
    # INPUT within the bbox (the region's real footprint), not the whole
    # bbox -- see the module-level history above for why. Reuses bg_masks
    # already computed per-frame above instead of recomputing color_mask.
    #
    # `frames_with_data` / a None mean_opacity_fraction exist to distinguish
    # "no comparable background-colored pixels were found in any frame"
    # from "confirmed unprotected" (mean_opacity_fraction == 0.0 with real
    # data) -- silently collapsing those two into the same 0.0 would hide a
    # measurement gap behind what looks like a confirmed failure. Mirrors
    # edge_fringe_check's own None-when-empty handling just above.
    # ⚠️ The footprint must be the ENCLOSED region, not every background-coloured
    # pixel inside its bounding RECTANGLE. A bbox around an irregular shape also
    # contains real background, which is correctly transparent in the output and
    # drags the fraction down as though the region were half-unprotected.
    # Measured on gift: 12,371 background-coloured pixels in the bbox against
    # 10,257 actually enclosed, reporting coverage 0.874 for a region that is in
    # fact 100% protected. Restricting to the enclosed footprint reads 1.000.
    protected_coverage = []
    for r in protected_regions:
        x0, y0, x1, y1 = r['bbox_xyxy']
        opacities = []
        residual_stats = []
        for i in range(n):
            _scope = np.zeros_like(bg_masks[i])
            _scope[y0:y1 + 1, x0:x1 + 1] = True
            _lb, _nl = ndimage.label(bg_masks[i], structure=STRUCTURE)
            _border = (set(_lb[0, :]) | set(_lb[-1, :])
                       | set(_lb[:, 0]) | set(_lb[:, -1]))
            _border.discard(0)
            region_fp = bg_masks[i] & ~np.isin(_lb, list(_border)) & _scope
            if not region_fp.any():
                continue
            opacities.append(float((out_alpha[i][region_fp] > 0).mean()))

            # Characterise WHAT the non-opaque remainder actually is, so a
            # sub-1.0 coverage number is self-explaining instead of inviting
            # a re-investigation. Confirmed on military-tag.gif 2026-08-17:
            # coverage 0.757 with the whole 24.3% remainder being ONE blob
            # per frame, 441-457px, in all 126 frames -- the deliberately
            # punched pinhole, which is background-coloured, enclosed, and
            # CORRECTLY transparent. §14 predicted exactly this residual
            # ("would need verify() to know about deliberately-carved
            # sub-holes, which it currently cannot express"). verify() only
            # receives an input and an output path, so it cannot read the
            # render's flags and can never *know* a cutout was intended --
            # but it can measure whether the remainder has the shape of one.
            _resid = region_fp & (out_alpha[i] == 0)
            _rn = int(_resid.sum())
            if _rn:
                _rl, _rc = ndimage.label(_resid, structure=STRUCTURE)
                residual_stats.append((_rn, _rc, int(region_fp.sum())))
        if not opacities:
            protected_coverage.append({
                'region_id': r['id'],
                'frames_with_data': 0,
                'mean_opacity_fraction': None,
                'looks_unprotected': None,
            })
            continue
        mean_opacity = sum(opacities) / len(opacities)
        # Only a region with a VERIFIED outline color has an automatic
        # protection mechanism analyze()/recommend() could have applied --
        # an unverified region needs manual --protect-region/--protect-
        # outline-color identification (SKILL.md's own guidance), so low
        # opacity there isn't necessarily a bug, just an unaddressed
        # region nobody claimed to have protected. Confirmed as a real
        # false positive on jewelry.gif's own accepted output: its region
        # 1 (unverified) reported looks_unprotected=True even though
        # nothing ever claimed to protect it. Report the real number
        # either way, but only assert the boolean for verified regions.
        looks_unprotected = (mean_opacity < 0.5) if r['outline_color_verified'] else None

        # A deliberately punched cutout and a genuine protection failure both
        # show up as non-opaque footprint pixels, but they do NOT look alike:
        #   - a cutout is a physical feature of the art, so it appears in
        #     essentially every frame, as one or two blobs, at a stable size,
        #     and occupies a SMALL fraction of the footprint;
        #   - a protection failure takes out a large share of the footprint
        #     (and drives mean_opacity below the 0.5 boolean anyway).
        # The size-fraction ceiling is what stops this from becoming an excuse
        # for a real failure -- without it, "persistent and stable" would also
        # describe a region that is reliably, wholly unprotected in every frame.
        residual = None
        if residual_stats and opacities:
            _fracs = [rn / fp for rn, _rc, fp in residual_stats]
            _sizes = [rn for rn, _rc, _fp in residual_stats]
            _mean = sum(_sizes) / len(_sizes)
            _cv = ((sum((x - _mean) ** 2 for x in _sizes) / len(_sizes)) ** 0.5
                   / _mean) if _mean else 0.0
            _mean_frac = sum(_fracs) / len(_fracs)
            _mean_blobs = sum(rc for _rn, rc, _fp in residual_stats) / len(residual_stats)
            _present = len(residual_stats) / len(opacities)
            residual = {
                'frames_with_residual_fraction': round(_present, 3),
                'mean_blobs_per_frame': round(_mean_blobs, 2),
                'mean_residual_px_per_frame': int(round(_mean)),
                'residual_size_cv': round(_cv, 3),
                'mean_residual_fraction_of_footprint': round(_mean_frac, 3),
                'consistent_with_deliberate_cutout': bool(
                    _present >= 0.9 and _cv <= 0.15
                    and _mean_blobs <= 2.0 and _mean_frac <= 0.35),
            }
        _expected = (r.get('candidate_outline_color')
                     or (r.get('partial_outline') or {}).get('color'))
        protected_coverage.append({
            'region_id': r['id'],
            'frames_with_data': len(opacities),
            'mean_opacity_fraction': round(mean_opacity, 3),
            'looks_unprotected': looks_unprotected,
            'expected_protection': (f'--protect-outline-color {_expected}' if _expected
                                    else 'none was recommended'),
            'residual_nonopaque': residual,
        })
    report['protected_region_coverage'] = protected_coverage

    # A region analyze() called `likely_intentional_design` that comes back at
    # essentially ZERO opacity did not get "less" protection -- it got none, and
    # the artwork is gone. This number was already being computed and printed as
    # one neutral statistic among a dozen: on the asset behind SS26, `--auto`
    # reported `worst protected-region coverage: 0.0` and then declared success,
    # while 976,800 px of design were destroyed. Saying it loudly is the general
    # detector for that whole class, independent of which flag was at fault.
    #
    # 0.05 is not a fine margin: every real failure measured reads exactly 0.000
    # (Cut loop, Starters!, pandapanda, 2d4a092f before the SS26 fix) and the
    # weakest genuine SUCCESS reads 0.331, so the threshold sits in a 0.33-wide
    # gap rather than between two neighbouring assets.
    _dead = [c for c in protected_coverage
             if c['frames_with_data'] and c['mean_opacity_fraction'] < 0.05]
    report['unprotected_design_regions'] = _dead
    for c in _dead:
        print(f"WARNING: region {c['region_id']} was identified as intentional design "
              f"but came out {c['mean_opacity_fraction']:.1%} opaque -- it received NO "
              f"protection, not weak protection. Expected protection: "
              f"{c['expected_protection']}. Re-run --analyze and read that region's note: "
              f"either the outline colour is wrong, or no colour encloses the region and "
              f"it needs --protect-region or a manually identified outline "
              f"(references/lessons.md SS26).", file=sys.stderr)

    # Small-region inflation: match each input small removed region to its
    # nearest output alpha==0 region by CENTROID within a size-scaled search
    # radius, THEN require actual pixel overlap with a small, FIXED (not
    # size-scaled) dilation of the input region as a sanity gate. Centroid-
    # only matching was tried first and confirmed to false-positive on an
    # irregularly-shaped/annular background component whose centroid landed
    # near a small input region's centroid despite having no real pixels
    # nearby -- the pixel-overlap gate rejects that kind of coincidental
    # match while still being far more conservative than the ORIGINAL
    # mistake this whole check exists to avoid (an 8px blanket dilation of
    # the source region used as the primary, unscoped search mechanism,
    # tried by hand earlier in this project and confirmed to leak into
    # unrelated background, misreporting a 1px region as 121px). Here the
    # dilation is only a secondary sanity check on an already
    # centroid-and-radius-scoped candidate, not the search mechanism itself.
    struct = np.ones((3, 3), dtype=bool)
    inflated = []
    step = max(1, n // 20)
    for i in range(0, n, step):
        in_removed = color_mask(in_rgb[i], bg_rgb, tolerance)
        in_labeled, in_num = ndimage.label(in_removed, structure=struct)
        if in_num == 0:
            continue
        in_sizes = ndimage.sum(in_removed, in_labeled, range(1, in_num + 1))
        in_largest = int(np.argmax(in_sizes)) + 1

        out_removed = (out_alpha[i] == 0)
        out_labeled, out_num = ndimage.label(out_removed, structure=struct)
        if out_num == 0:
            continue
        out_sizes = ndimage.sum(out_removed, out_labeled, range(1, out_num + 1))
        out_centroids = ndimage.center_of_mass(out_removed, out_labeled, range(1, out_num + 1))

        for lab in range(1, in_num + 1):
            if lab == in_largest or in_sizes[lab - 1] < 2:
                continue
            comp = in_labeled == lab
            cy, cx = ndimage.center_of_mass(comp)
            search_r = max(8.0, (in_sizes[lab - 1] ** 0.5) * 2)
            comp_dilated = ndimage.binary_dilation(comp, iterations=10)
            best = None
            for oc_idx, (ocy, ocx) in enumerate(out_centroids):
                d = ((ocy - cy) ** 2 + (ocx - cx) ** 2) ** 0.5
                if d > search_r or (best is not None and d >= best[0]):
                    continue
                out_comp_mask = (out_labeled == (oc_idx + 1))
                if (out_comp_mask & comp_dilated).any():
                    best = (d, oc_idx)
            if best is not None:
                out_size = int(out_sizes[best[1]])
                in_size = int(in_sizes[lab - 1])
                if out_size > in_size * 3 and out_size - in_size > 15:
                    inflated.append({
                        'frame_index': i,
                        'input_size_px': in_size,
                        'output_size_px': out_size,
                        'inflation_factor': round(out_size / max(in_size, 1), 1),
                    })

    report['small_region_inflation'] = {'flagged': inflated[:10], 'flagged_count': len(inflated)}
    # Every other check here is a QUALITY measure, and every one of them reads an empty output as
    # flawless -- no leftover background, no fringe, no inflation. So the one check that catches
    # total destruction has to be stated separately. SS28.9
    _out_opaque = int(sum(int((a > 0).sum()) for a in out_alpha))
    report['output_opaque_px'] = _out_opaque
    # PARTIAL destruction, the sibling of the empty-output check below. When the SOURCE already
    # carries transparency, its opaque area IS the artwork -- so the output should keep essentially
    # all of it, and a big shortfall means colour-based removal ate real art. This cannot be a
    # blanket ratio: on an ordinary opaque source the whole canvas is "opaque" and a low survival
    # rate is the entire point of the tool. Measured on a real itch.io sprite sheet whose
    # transparent region stores RGB (0,0,0): detect_bg_color picks black, and the sprite's black
    # outlines go with it -- 7,130 opaque px in, 4,675 out, 65.6% survival, with every other check
    # passing. SS28.13
    _in_opaque = int(sum(int((a > 0).sum()) for a in in_alpha))
    _src_had_alpha = any(bool((a < 255).any()) for a in in_alpha)
    if _src_had_alpha and _in_opaque > 0:
        _survival = _out_opaque / _in_opaque
        report['opaque_survival_vs_transparent_source'] = round(_survival, 4)
        if _survival < 0.95:
            report['opaque_survival_warning'] = (
                f"The SOURCE already had transparency, so its {_in_opaque} opaque pixels were the "
                f"artwork -- and only {_out_opaque} survived ({_survival:.1%}). Colour-based "
                f"removal has eaten real art: the background colour detected from the RGB stored "
                f"under the transparent pixels also matches part of the design -- OR a later step "
                f"eroded it. Removal itself is confined to the source's own alpha (SS28.14), so on "
                f"a default run this points at one of four things, in the order worth checking: "
                f"--ignore-source-alpha was passed; --edge-cleanup-erosion was passed explicitly "
                f"(it shaves a source-defined silhouette, and nothing can distinguish that from "
                f"trimming a fringe); the confinement did not engage (the transparency does not "
                f"reach the frame border, or the colour under it is not the detected background); "
                f"or the source is one this project has not seen. An explicit --bg-color is the "
                f"LAST thing to reach for, not the first.")
    if _out_opaque == 0:
        report['output_is_empty'] = (
            'EVERY pixel of every frame is transparent -- the output is empty, not clean. No '
            'other check here can see this: an empty output has no leftover background, no '
            'fringe and no thin protected region. Read edge_hardness.alpha_only_source and the '
            'detected background colour.')
    report['timing'] = _timing_line(output_path, in_durations, out_alpha)
    return report


def _refuse_empty_render(alpha_frames, output_path):
    """Refuse to write an output in which NOTHING is opaque, on any frame.

    "Remove the background" has no valid result that is a fully transparent file, and writing one
    silently is the worst outcome available: it overwrites whatever was at the output path, and
    every quality check downstream reads it as perfect -- an empty output has no leftover
    background to count, no fringe, and no protected region to come back thin. Measured on a real
    alpha-only PNG (`pencil.png`): 69,925 opaque pixels in, ZERO out, and --auto printed success.
    SS28.9

    Note the invariant is deliberately whole-file, not per-frame: a genuinely blank frame is
    normal inside an animation that fades out. Only "no opaque pixel anywhere" is impossible.
    """
    if any(bool((a > 0).any()) for a in alpha_frames):
        return
    raise SystemExit(
        f"ERROR: refusing to write {output_path!r} -- every pixel of every frame came out "
        f"transparent, so the render would destroy the image rather than remove its background. "
        f"Nothing has been written.\n"
        f"  The usual causes: the detected --bg-color matched the ARTWORK as well as the "
        f"background, or the source is an alpha-only mask (one flat RGB value, with the whole "
        f"image in its alpha channel) and so has no background colour to key at all.\n"
        f"  Run --analyze and read 'alpha_only_source' and 'background_color', or pass an "
        f"explicit --bg-color.")


def render_frames_to_gif(rgb_frames, alpha_frames, durations, loop, output_path,
                          colors=255, quantizer='pil'):
    """
    Build P-mode frames from RGB+alpha arrays and save as a GIF. Shared by
    the normal save path and the size-optimization loop (which calls this
    repeatedly with fewer colors / smaller dimensions / fewer frames).
    Returns the resulting file size in bytes.

    `quantizer`: 'pil' (default) or 'pngquant'. Only affects how the ONE
    shared master palette below is built -- every frame is still quantized
    against that single fixed palette either way, so this never touches
    the shared-palette/frame-diffing architecture. 'pil' is the validated
    default (see ensure_pngquant's docstring for the real A/B numbers that
    justify keeping it default); 'pngquant' is an opt-in for content this
    skill hasn't primarily been tuned for (genuine gradients/soft shading)
    or whenever the person explicitly wants visual fidelity prioritized
    over file size. Falls back to 'pil' with a warning if pngquant isn't
    available or fails.

    Uses ONE shared palette across every frame, built from the opaque
    pixels of all frames combined, rather than quantizing each frame to
    its own independent adaptive palette. This matters a lot for file
    size: an animation with mostly-static content (e.g. only a small part
    of the icon moves) relies on the GIF encoder recognizing that most
    pixels are unchanged frame-to-frame so it can skip re-encoding them.
    A per-frame palette breaks that even when the underlying RGB is
    bit-identical across frames, because the adaptive quantizer's chosen
    palette shifts slightly with each frame's overall color histogram (a
    rotating gear introducing more/less orange, say), so the SAME visual
    color can land on a DIFFERENT palette index in consecutive frames --
    every pixel then looks "changed" to the encoder even though nothing
    moved, defeating disposal/diff-based compression and gifsicle's own
    -O3 optimization on top. A shared palette keeps identical colors on
    identical indices across frames so static regions compress like the
    static regions they are.
    """
    _refuse_empty_render(alpha_frames, output_path)
    n_colors = max(2, min(colors, 255))
    palette_colors = min(n_colors, 254)  # leave room for the reserved transparency slot

    opaque_pixel_rows = [rgb[alpha > 0] for rgb, alpha in zip(rgb_frames, alpha_frames)
                          if (alpha > 0).any()]
    if opaque_pixel_rows:
        all_opaque = np.concatenate(opaque_pixel_rows, axis=0)
    else:
        all_opaque = np.zeros((1, 3), dtype=np.uint8)
    # Cap how many pixels feed the quantizer purely for speed -- a random
    # sample is still representative of the color distribution for the
    # flat/icon-style art this skill targets, and median-cut quantization
    # doesn't need every pixel to find the right palette.
    max_sample = 300_000
    if len(all_opaque) > max_sample:
        idx = np.random.default_rng(0).choice(len(all_opaque), max_sample, replace=False)
        all_opaque = all_opaque[idx]
    master_im = Image.fromarray(all_opaque.reshape(1, -1, 3), 'RGB')

    master_p = None
    if quantizer == 'pngquant':
        if ensure_pngquant():
            with tempfile.TemporaryDirectory() as tmpdir:
                src_path = os.path.join(tmpdir, 'master.png')
                out_path = os.path.join(tmpdir, 'master_q.png')
                master_im.save(src_path)
                try:
                    subprocess.run(
                        ['pngquant', '--quality=0-100', '--speed', '1',
                         str(palette_colors), src_path, '-o', out_path, '--force'],
                        capture_output=True, timeout=60, check=True)
                    master_p = Image.open(out_path).convert('P')
                except Exception as e:
                    print(f"WARNING: --quantizer pngquant was requested but "
                          f"pngquant failed ({e}); falling back to Pillow's "
                          f"own quantizer for this master palette.",
                          file=sys.stderr)
                    master_p = None
        else:
            print("WARNING: --quantizer pngquant was requested but pngquant "
                  "isn't available and couldn't be installed; falling back "
                  "to Pillow's own quantizer for this master palette.",
                  file=sys.stderr)
    if master_p is None:
        master_p = master_im.convert('P', palette=Image.ADAPTIVE, colors=palette_colors)

    palette = master_p.getpalette()
    if len(palette) < 768:
        palette = palette + [0] * (768 - len(palette))
    palette[255*3:255*3+3] = [255, 0, 255]  # reserved transparency slot

    out_frames = []
    for rgb_out, alpha in zip(rgb_frames, alpha_frames):
        rgb_im = Image.fromarray(rgb_out, 'RGB')
        im_p = rgb_im.quantize(palette=master_p, dither=Image.Dither.NONE)

        arr_p = np.array(im_p)
        arr_p[alpha == 0] = 255
        im_p2 = Image.fromarray(arr_p, 'P')
        im_p2.putpalette(palette)
        im_p2.info['transparency'] = 255

        out_frames.append(im_p2)

    out_frames[0].save(
        output_path,
        save_all=True,
        append_images=out_frames[1:],
        duration=durations,
        loop=loop,
        disposal=2,
        transparency=255,
        optimize=False,
    )
    return os.path.getsize(output_path)


# --- Baked-in fade recovery (palette unmixing) -------------------------------
#
# Motivating real case, references/lessons.md SS16: art whose glow/sparkle/pulse
# FADES OUT was authored with real alpha, but GIF has none, so the authoring
# tool flattened each fade stage against the background -- a 40%-opacity yellow
# pulse became a solid pale cream. The information is not lost, just encoded:
# every faded pixel lies on the straight line between the background colour and
# the element's true colour, and its position along that line IS the original
# alpha. Recovering it is exact arithmetic, not estimation.
#
# Why the normal feather path cannot do this: estimate_alpha_and_defringe only
# assigns partial alpha inside `tolerance`..`tolerance*band_multiplier` (15..60
# by default) of the background. On the motivating asset the fade stages sat at
# distance 36/73/110/146 -- only the faintest fell inside. Widening the band is
# NOT a fix: a real solid art colour (a pale lavender) sat at 121.7, so any band
# wide enough to catch the fade also dissolves genuine artwork. The two ranges
# overlap, so no single distance threshold separates them. Asking "is this pixel
# explained as background blended with ONE known art colour?" does separate them.

FADE_RESIDUAL_TOLERANCE = 10.0   # max distance off the bg<->colour line to count as a blend
FADE_BARRIER_ALPHA = 0.5         # unmixed alpha at/above which a solid colour blocks flood fill
FADE_EDGE_DILATE = 3             # px around true background that may carry partial alpha
FADE_OPAQUE_BLOCK = 0.90         # a fading colour this opaque occludes what it covers
FADE_ART_PRIOR = 0.30            # ...but only where art is present in >=30% of frames


def unmix_against_palette(rgb, bg_rgb, palette):
    """
    For every pixel, the best explanation of "background blended with ONE
    palette colour": returns (index, alpha, residual) arrays.

    Kept as (N, K) throughout via |r|^2 = |v|^2 - 2t(v.d) + t^2|d|^2 rather than
    materialising an (N, K, 3) difference -- the naive form is ~40x slower here
    and was the original reason a 124-frame job took minutes.
    """
    bg = np.asarray(bg_rgb, dtype=np.float32)
    d = palette - bg
    dd = (d * d).sum(1)
    v = (rgb.astype(np.float32) - bg).reshape(-1, 3)
    proj = v @ d.T
    t = np.clip(proj / dd, 0.0, 1.0)
    r2 = (v * v).sum(1)[:, None] - 2.0 * t * proj + (t * t) * dd
    k = r2.argmin(1)
    n = np.arange(len(v))
    res = np.sqrt(np.maximum(r2[n, k], 0.0))
    shape = rgb.shape[:2]
    return k.reshape(shape), t[n, k].reshape(shape), res.reshape(shape)


def build_art_palette(rgb_frames, bg_rgb, sample_stride=8, protect_parents=None,
                      force_include=None):
    """
    The small set of SOLID colours the art is actually drawn from.

    ⚠️ The ordering here is load-bearing, and getting it wrong is a real bug that
    was hit and fixed on the motivating asset. A fading element's intermediate
    stages cover tens of thousands of pixels per frame, so they rank as
    "dominant colours" and get admitted as solid palette entries of their own.
    Every faded pixel then unmixes against its OWN stage at alpha ~1.0 and
    renders fully opaque -- reproducing, inside the new format, the exact GIF
    artifact this whole path exists to avoid.

    The fix: consider candidates FURTHEST from the background first (a fade
    stage is always closer to the background than the colour it fades from),
    and reject any candidate already explained as a blend of the background and
    an accepted colour.

    ⚠️ That rejection is too aggressive on its own, and the failure is severe.
    A SOLID art colour can legitimately sit on the line between the background
    and another art colour -- a pale tint, a light shade of a mid-tone. Rejecting
    it means it never becomes a palette entry, so it gets unmixed as
    "background + its parent" and rendered SEMI-TRANSPARENT. Confirmed on a real
    asset (crystal.gif): #d2dcfd is a genuine solid colour that is also exactly
    43% #93b2f4 over white, and 1,092,411 solid pixels across 130 frames came out
    at alpha ~109/255 instead of 255 -- the background visibly showing through
    the artwork.

    The discriminator is the PARENT: a fade stage's parent is a fading colour, a
    solid tint's parent is not. `protect_parents` is the set of parent colours
    whose blends may be rejected (i.e. the detected fading colours). None means
    reject every blend -- correct ONLY for the provisional first pass that exists
    to find the fading colours in the first place.
    """
    bg = np.asarray(bg_rgb, dtype=np.float32)
    sample = np.concatenate(
        [f.reshape(-1, 3) for f in rgb_frames[::sample_stride]], 0).astype(np.uint8)
    # PACK to uint32, then unique on a 1-D array -- never np.unique(axis=0). Both return the
    # same colours in the same order with the same counts (asserted on real frames), because
    # (r<<16)|(g<<8)|b sorts lexicographically by (r,g,b) exactly as row-unique does. But
    # axis=0 builds a structured view and sorts ROWS, and that costs 7,524 ms on the 7.4M-row
    # sample a 138-frame emoji produces, against 65 ms here -- 115x, and it was the single
    # largest line in an --analyze profile. Same lesson as measure_composited_color_count's
    # sieve: the cost of np.unique tracks the SORT, so give it the smallest thing to sort.
    _packed = ((sample[:, 0].astype(np.uint32) << 16)
               | (sample[:, 1].astype(np.uint32) << 8) | sample[:, 2])
    _vals, counts = np.unique(_packed, return_counts=True)
    cols = np.stack([(_vals >> 16) & 255, (_vals >> 8) & 255, _vals & 255], 1).astype(np.uint8)
    floor = max(1, int(len(sample) * 0.0008))
    cand = [(c.astype(np.float32), int(n)) for c, n in zip(cols, counts)
            if n >= floor and np.linalg.norm(c.astype(np.float32) - bg) > 40]
    cand.sort(key=lambda cn: -float(np.linalg.norm(cn[0] - bg)))

    # force_include seeds the palette so a manually named colour survives even
    # when it is too rare to clear the frequency floor -- see the fade_hexes
    # branch in recover_fade_alpha_frames for the real case.
    palette = [np.asarray(c, dtype=np.float32) for c in (force_include or [])]
    for col, _n in cand:
        v = col - bg
        explained = False
        for prev in palette:
            d = prev - bg
            dd = float(d @ d)
            t = min(max(float(v @ d) / dd, 0.0), 1.0)
            if float(np.linalg.norm(v - t * d)) < FADE_RESIDUAL_TOLERANCE:
                if protect_parents is not None and not any(
                        float(np.linalg.norm(prev - q)) < 1e-6 for q in protect_parents):
                    continue          # parent is solid art -> this is a real colour
                explained = True
                break
        if explained or any(np.linalg.norm(col - q) < 30 for q in palette):
            continue
        palette.append(col)

    # ⚠️ SATURATION PROMOTION WAS TRIED HERE AND REVERTED (2026-08-17) -- do not
    # re-attempt without reading this. The idea: an element drawn at constant
    # partial opacity never appears at full strength, so its TRUE colour can fall
    # under the frequency floor while its blended stage clears it; the blend then
    # enters the palette as "solid" and renders OPAQUE PALE. Real case, gift.gif:
    # a sparkle at ~27% opacity put #d1dcfb in the palette instead of #6969f2, so
    # it turned whitish instead of staying translucent purple.
    #
    # The attempted fix walked each accepted colour's background->colour ray
    # looking for a more saturated colour present at a lower count, and promoted
    # to it. MEASURED NET-HARMFUL across the corpus:
    #   * crystal.gif: promoted the genuinely-solid #d2dcfd to #8599f5, which
    #     re-broke the exact semi-transparency bug the two-pass palette fixes.
    #   * explosion.gif: emitted a duplicate palette entry (#93b2f4 twice).
    #   * gift.gif: only reached #c4d0f2, still not the true #6969f2.
    # Root reason it cannot work from a histogram alone: "pale colour is a blend
    # of a rarer saturated colour" and "pale colour is solid art that happens to
    # be collinear with a saturated colour" are INDISTINGUISHABLE in colour
    # statistics. Separating them needs evidence this function does not have
    # (e.g. per-region temporal behaviour). --fade-color is the working escape
    # hatch meanwhile, and it injects the named colour into the palette.
    return np.array(palette, dtype=np.float32)


def detect_fading_colors(rgb_frames, bg_rgb, palette, min_px=2000, partial_fraction=0.9):
    """
    Which palette colours appear as a LARGE region at a flat PARTIAL alpha --
    i.e. are translucent elements flattened against the background, not solid art.

    Scans EVERY frame. An earlier version sampled every 10th frame for speed and
    silently stopped detecting the fade on the motivating asset, producing a
    plausible-looking but wrong result. That is this repo's own SS10 lesson
    ("verify against every frame, not a spot-check sample") reasserting itself;
    unmixing is ~50ms/frame, so a full scan is affordable and a sample is not
    worth the failure mode.
    """
    fading = set()
    for rgb in rgb_frames:
        k, t, res = unmix_against_palette(rgb, bg_rgb, palette)
        for ki in range(len(palette)):
            if ki in fading:
                continue
            m = (k == ki) & (res <= FADE_RESIDUAL_TOLERANCE) & (t > 0.05)
            if int(m.sum()) < min_px:
                continue
            if float(((t[m] > 0.08) & (t[m] < 0.92)).mean()) > partial_fraction:
                fading.add(ki)
    return fading


def recover_fade_alpha_frames(rgb_frames, bg_rgb, fade_hexes=None, log=None):
    """
    Full alpha for every frame by palette unmixing, recovering translucency that
    was flattened against the background at authoring time. Returns
    (rgb_frames_out, alpha_frames) with 8-bit alpha -- for a container that can
    hold it (WebP/AVIF), never GIF.

    Per frame: unmix -> mark solid non-fading art as a flood-fill barrier ->
    flood from the canvas border -> anything the flood reaches (plus a thin
    dilated rim, which is the real antialiased silhouette) gets its unmixed
    alpha; anything enclosed and unreached is interior design and stays fully
    opaque with its original pixels.

    A FADING colour is deliberately NOT a barrier. At full opacity it is still
    see-through in intent, and treating it as a wall lets it enclose real
    background -- on the motivating asset that turned the gap between the heart
    outline and the pulse ring into an opaque white band.
    """
    say = (lambda m: log.append(m)) if log is not None else (lambda m: None)
    # TWO PASSES. Pass 1 rejects every background-blend candidate, which is what
    # makes the fading colours findable at all. Pass 2 rebuilds the palette
    # KEEPING solid near-background tints, rejecting only blends whose PARENT is
    # actually a fading colour -- see build_art_palette's docstring for the real
    # bug this closes.
    provisional = build_art_palette(rgb_frames, bg_rgb)
    if len(provisional) == 0:
        raise SystemExit(
            "--recover-fade-alpha found no solid art colours distinct from the "
            "background. This path assumes flat-colour art (vector icon/sticker "
            "style); it cannot work on photographic or heavily-gradient content.")
    if fade_hexes:
        # --fade-color ADDS the colour when it isn't already present, rather than
        # snapping to the nearest existing entry. Confirmed necessary on a real
        # asset (gift.gif): a translucent sparkle drawn at ~27% opacity means its
        # TRUE colour (#6969f2) barely exists at full strength anywhere in the
        # animation, so it never clears the frequency floor -- only its blended
        # stage (#d1dcfb) does, which then gets admitted as a solid colour and
        # renders OPAQUE PALE. Snapping to the nearest entry would just re-select
        # that same wrong pale colour; the point of the override is to name the
        # colour the detector could not see.
        _want = [np.array(hex_to_rgb(h), dtype=np.float32) for h in fade_hexes]
        parents = []
        for w in _want:
            dists = np.linalg.norm(provisional - w, axis=1)
            i = int(np.argmin(dists))
            if float(dists[i]) <= 12.0:
                parents.append(provisional[i])
            else:
                provisional = np.vstack([provisional, w[None, :]])
                parents.append(w)
    else:
        parents = [provisional[i] for i in
                   sorted(detect_fading_colors(rgb_frames, bg_rgb, provisional))]
    palette = build_art_palette(rgb_frames, bg_rgb, protect_parents=parents,
                                force_include=parents if fade_hexes else None)
    if len(palette) == 0:
        raise SystemExit(
            "--recover-fade-alpha found no solid art colours distinct from the "
            "background. This path assumes flat-colour art (vector icon/sticker "
            "style); it cannot work on photographic or heavily-gradient content.")
    say("palette: " + ', '.join('#%02x%02x%02x' % tuple(int(v) for v in c)
                                for c in palette))

    if fade_hexes:
        want = [np.array(hex_to_rgb(h), dtype=np.float32) for h in fade_hexes]
        fading = set()
        for w in want:
            i = int(np.argmin(np.linalg.norm(palette - w, axis=1)))
            if float(np.linalg.norm(palette[i] - w)) > 30:
                raise SystemExit(
                    f"--fade-color #{rgb_to_hex(tuple(int(x) for x in w))} does not match any "
                    f"detected art colour. Detected: " +
                    ', '.join('#%02x%02x%02x' % tuple(int(v) for v in c) for c in palette))
            fading.add(i)
        say("fading colours (from --fade-color): " +
            ', '.join('#%02x%02x%02x' % tuple(int(v) for v in palette[i]) for i in sorted(fading)))
    else:
        fading = {i for i, c in enumerate(palette)
                  if any(float(np.linalg.norm(c - q)) < 1e-6 for q in parents)}
        say("fading colours (auto-detected): " +
            (', '.join('#%02x%02x%02x' % tuple(int(v) for v in palette[i])
                       for i in sorted(fading)) or 'none'))

    bg = np.asarray(bg_rgb, dtype=np.float32)
    solid_idx = [i for i in range(len(palette)) if i not in fading]
    struct8 = ndimage.generate_binary_structure(2, 2)

    # ART PRIOR -- how often each pixel position is SOLID art across the whole
    # animation. Needed because a fading colour is deliberately NOT a flood-fill
    # barrier (background behind a translucent element must stay reachable), but
    # at FULL opacity such an element occludes whatever it covers. Where it
    # crosses solid artwork, exempting it punches a hole clean through, and the
    # background flood pours in.
    #
    # Confirmed real case (crystal.gif): an opaque yellow sparkle lying across the
    # crystal's navy outline emptied the crystal's white interior in 59 of 130
    # frames -- 24,520 px in one blob.
    #
    # Colour alone cannot separate "opaque sparkle over navy" from "opaque
    # sparkle over background". Position over TIME can: the outline is art in
    # most frames, the background is not. So a near-opaque fading pixel blocks
    # only where art usually lives. Measured: fixes all 59 crystal frames with
    # ZERO cost to love.gif's gap-between-outline-and-ring (which must stay
    # reachable THROUGH the ring). A plain opacity cut with no prior fixed
    # crystal too but sealed love's gap in 27 frames -- that trade was rejected.
    art_prior = np.zeros(rgb_frames[0].shape[:2], np.float32)
    for rgb in rgb_frames:
        k, t, res = unmix_against_palette(rgb, bg_rgb, palette)
        solid = np.isin(k, solid_idx)
        art_prior += ((res > FADE_RESIDUAL_TOLERANCE) | (solid & (t >= FADE_BARRIER_ALPHA)))
    art_prior /= max(len(rgb_frames), 1)

    out_rgb, out_alpha = [], []
    coverage_total = coverage_ok = 0
    interior_total = interior_leaky = 0

    for rgb in rgb_frames:
        rgbf = rgb.astype(np.float32)
        k, t, res = unmix_against_palette(rgb, bg_rgb, palette)
        coverage_total += res.size
        coverage_ok += int((res <= FADE_RESIDUAL_TOLERANCE).sum())

        solid = np.isin(k, solid_idx)
        barrier = (res > FADE_RESIDUAL_TOLERANCE) | (solid & (t >= FADE_BARRIER_ALPHA))
        # A near-opaque translucent element occludes; block it, but only where
        # solid art usually lives (see art_prior above).
        barrier |= (t >= FADE_OPAQUE_BLOCK) & (~solid) & (art_prior >= FADE_ART_PRIOR)
        lab, _ = ndimage.label(~barrier)
        border = set(np.unique(np.concatenate(
            [lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        outside = np.isin(lab, list(border)) if border else np.zeros_like(barrier)
        bgside = ndimage.binary_dilation(outside, struct8, iterations=FADE_EDGE_DILATE)

        alpha = np.full(rgb.shape[:2], 255.0, dtype=np.float32)
        rgb_out = rgbf.copy()

        exact = bgside & (res <= FADE_RESIDUAL_TOLERANCE)
        alpha[exact] = t[exact] * 255.0
        rgb_out[exact] = palette[k[exact]]

        # Corners where two art colours meet the background are not a clean
        # two-colour blend. Unmix them generically; the alpha floor keeps the
        # unpremultiplied colour in gamut so compositing back over the
        # background still reproduces the source pixel exactly.
        gen = bgside & (res > FADE_RESIDUAL_TOLERANCE)
        if gen.any():
            ref = np.sqrt(((palette - bg) ** 2).sum(1))[k]
            dist = np.linalg.norm(rgbf - bg, axis=2)
            lo = np.where(rgbf < bg, (bg - rgbf) / np.maximum(bg, 1e-6),
                          (rgbf - bg) / np.maximum(255.0 - bg, 1e-6)).max(axis=2)
            ag = np.clip(np.maximum(dist / np.maximum(ref, 1e-6), lo), 0.0, 1.0)
            alpha[gen] = ag[gen] * 255.0
            rgb_out[gen] = bg + (rgbf[gen] - bg) / np.maximum(ag[gen], 1e-3)[:, None]

        clear = alpha < 1.0
        alpha[clear] = 0.0
        rgb_out[clear] = bg

        interior = (~barrier) & (~outside)
        interior_total += int(interior.sum())
        interior_leaky += int((interior & (alpha < 255)).sum())

        out_rgb.append(np.clip(rgb_out, 0, 255).astype(np.uint8))
        out_alpha.append(np.clip(np.rint(alpha), 0, 255).astype(np.uint8))

    cov = coverage_ok / max(coverage_total, 1)
    say(f"palette coverage: {cov*100:.1f}% of pixels explained as background + one art colour")
    if cov < 0.90:
        # Without this the tool fails SILENTLY on the wrong content type: every
        # pixel becomes a "residual" case, gets forced opaque, and the run
        # reports success while having recovered nothing.
        print(f"WARNING: only {cov*100:.1f}% of pixels are explained as a blend of the "
              f"background and a single flat art colour. --recover-fade-alpha assumes "
              f"flat-colour vector art; this looks like gradient/photographic content, "
              f"where it will mostly no-op (regions left opaque) rather than recover "
              f"anything. Check the result carefully or drop the flag.", file=sys.stderr)
    if interior_leaky:
        print(f"WARNING: {interior_leaky} of {interior_total} enclosed interior pixels came out "
              f"partially transparent when they should be fully opaque. If a protected "
              f"detail looks see-through, the art likely has strokes thinner than "
              f"{2*FADE_EDGE_DILATE}px, letting the edge rim reach through from both sides.",
              file=sys.stderr)
    return out_rgb, out_alpha


def format_from_path(path):
    """
    Container implied by a file extension. Shared by resolve_output_format and
    verify() so the two cannot disagree -- they did: verify() carried its own
    `{'.webp': ..., '.avif': ...}.get(ext, 'gif')` map, so an APNG output was
    classified as GIF, and the report then withheld the 8-bit scope note and
    described an 8-bit file in 1-bit terms. Found by audit, not by any gate:
    every check passed because a GIF verdict on a valid file looks like a pass.
    """
    low = str(path).lower()
    if low.endswith('.webp'):
        return 'webp'
    if low.endswith('.avif'):
        return 'avif'
    if low.endswith('.apng') or low.endswith('.png'):
        return 'apng'
    return 'gif'


def resolve_output_format(output_path, args):
    """
    'gif', 'webp', 'avif' or 'apng' for this run. --format wins; otherwise the
    output file extension decides, defaulting to gif. `.png` resolves to apng
    too: Pillow writes a single-frame APNG as an ordinary PNG, so a static
    source and an animated one both do the right thing under one extension.
    """
    explicit = getattr(args, 'format', None)
    if explicit and explicit != 'auto':
        return explicit
    # An unrecognised extension falls through to GIF, which is right for a path with no
    # extension -- but NOT for another image format Pillow will claim by extension. Writing GIF
    # frames to `out.jpeg` made Pillow pick its JPEG handler and die inside SAVE_ALL, surfacing as
    # a raw traceback line rather than "that is not a container I can write". Same shape as
    # v5.4.0's --verify FileNotFoundError fix: a legible refusal beats an internal crash.
    _low = str(output_path).lower()
    for _ext in ('.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.ico', '.pdf', '.svg', '.mp4', '.webm'):
        if _low.endswith(_ext):
            raise SystemExit(
                f"ERROR: {output_path!r} asks for {_ext} output, which cannot hold transparency "
                f"and is not a container this script writes. Choose .gif, .webp, .avif or "
                f"'.apng'/'.png' (or pass --format).")
    return format_from_path(output_path)


def render_frames_to_webp(rgb_frames, alpha_frames, durations, loop, output_path,
                          lossless=True, quality=90, method=4):
    """
    Save RGB+alpha arrays as an animated WebP with true 8-bit alpha.

    Unlike render_frames_to_gif there is no shared-palette/quantization step
    and no transparency index -- WebP stores straight (non-premultiplied)
    RGBA directly, so partial alpha survives and no dithering is needed.

    `method` defaults to 2. Measured across 5 real assets: m2 costs 0.6-8.3%
    more bytes than m4 while encoding ~2x faster. m6 is never worth it (45x
    slower than m4 for 2.3%); m0 is faster still but its size penalty ranges
    from +14% to +134% depending on content, so it must be measured, not
    assumed.

    On flat vector art, `lossless=True` is usually SMALLER as well as better
    than lossy: measured 2109 KB lossless vs 3005 KB at quality 90 on the
    same asset, because lossy injects noise into large uniform regions and
    that defeats inter-frame prediction. Reach for lossy only when fitting a
    hard byte cap.
    """
    _refuse_empty_render(alpha_frames, output_path)
    ims = []
    for rgb_out, alpha in zip(rgb_frames, alpha_frames):
        ims.append(Image.fromarray(
            np.dstack([rgb_out, alpha[:, :, None]]).astype(np.uint8), 'RGBA'))
    kw = dict(save_all=True, append_images=ims[1:], duration=list(durations),
              loop=loop, minimize_size=True, method=method)
    if lossless:
        kw.update(lossless=True, quality=100)
    else:
        kw.update(lossless=False, quality=quality, alpha_quality=100)
    ims[0].save(output_path, 'WEBP', **kw)
    return os.path.getsize(output_path)


def render_frames_to_avif(rgb_frames, alpha_frames, durations, loop, output_path,
                          quality=70):
    """
    Save RGB+alpha arrays as an animated AVIF with 8-bit alpha.

    Measured against WebP on the same 128x128 emoji-sized content (SS16): AVIF
    held ALL 124 frames inside Discord's 256 KB emoji cap at quality 70
    (244 KB), where WebP had to drop to 42 frames to fit. Roughly a 3x frame
    budget at equivalent apparent quality, so AVIF is the better choice
    whenever a hard byte cap is forcing frames out of a WebP.

    ⚠️ Acceptance is not playback. A platform listing AVIF as an accepted
    upload type does not prove its clients ANIMATE it inline -- verify with a
    real upload before shipping an animated AVIF, and keep a WebP fallback.
    (Diors-Builds settled the same question for WebP only by testing a real
    Discord client on desktop and mobile.)
    """
    _refuse_empty_render(alpha_frames, output_path)
    # Fail before doing the work, not after. AVIF needs Pillow built with AVIF
    # support (or the pillow-avif-plugin); --recommend actively ranks AVIF FIRST
    # under a byte cap, so an autonomous run is steered straight at this
    # dependency. Without the check the failure surfaces as a bare Pillow
    # KeyError/OSError after every frame has already been processed.
    if not _avif_available():
        raise SystemExit(
            "AVIF output needs Pillow built with AVIF support, which this "
            "environment does not have. Install it with `pip install "
            "pillow-avif-plugin` (or upgrade Pillow), or write a .webp instead "
            "-- WebP also carries true 8-bit alpha and is more widely supported.")
    ims = [Image.fromarray(np.dstack([r, a[:, :, None]]).astype(np.uint8), 'RGBA')
           for r, a in zip(rgb_frames, alpha_frames)]
    ims[0].save(output_path, 'AVIF', save_all=True, append_images=ims[1:],
                duration=list(durations), loop=loop, quality=quality)
    return os.path.getsize(output_path)


def render_frames_to_apng(rgb_frames, alpha_frames, durations, loop, output_path):
    """
    Save RGB+alpha arrays as an animated PNG with true 8-bit alpha.

    APNG is the PNG-family answer to the same problem WebP and AVIF solve here:
    it stores straight (non-premultiplied) 8-bit alpha, so a recovered fade
    survives it. It is lossless and needs no capability check -- Pillow's PNG
    writer has always handled `save_all=True` (verified: a 3-frame RGBA save
    reads back as n_frames=3, mode=RGBA), unlike AVIF which depends on a plugin.

    It is the largest of the three by some margin on photographic content, so
    --recommend still ranks WebP and AVIF ahead of it; APNG is here for the case
    where the destination wants PNG specifically.
    """
    _refuse_empty_render(alpha_frames, output_path)
    ims = [Image.fromarray(np.dstack([r, a[:, :, None]]).astype(np.uint8), 'RGBA')
           for r, a in zip(rgb_frames, alpha_frames)]
    ims[0].save(output_path, 'PNG', save_all=True, append_images=ims[1:],
                duration=list(durations), loop=loop, disposal=2)
    return os.path.getsize(output_path)


def read_animation_timing(path):
    """
    (frame_count, total_ms) read back from a written animation, or None if this
    environment cannot read it.

    Returning None rather than a guess is the point: asserting the durations we
    intended to write produces a message that CANNOT fail, which is exactly the
    defect SS13 documents and SS16 repeats for WebP.
    """
    try:
        im = Image.open(path)
        n = getattr(im, 'n_frames', 1)
        total = 0
        for i in range(n):
            im.seek(i)
            total += frame_duration_ms(im, 0) or 0
        if total > 0:
            return n, total
        # Pillow reports 0 for animated WebP; fall back to the container.
        d = read_webp_durations(path)
        if d:
            return len(d), sum(d)
        return None
    except Exception:
        return None


def read_webp_durations(path):
    """
    Per-frame durations of an animated WebP, read from the container.

    Pillow does NOT expose `duration` when READING an animated WebP -- every
    frame comes back 0, so a naive timing check passes vacuously against a
    file whose timing is actually wrong. Same footgun class as SS9's
    Pillow-duration issue on GIF. Uses `webpmux -info`; returns None if
    webpmux isn't available, so callers can say "unverified" rather than
    silently report 0.
    """
    if shutil.which('webpmux') is None:
        return None
    try:
        out = subprocess.run(['webpmux', '-info', path],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    d = [int(m) for m in re.findall(
        r'^\s*\d+:\s+\d+\s+\d+\s+\w+\s+\d+\s+\d+\s+(\d+)', out, re.M)]
    return d or None


def square_pad_frames(rgb_frames, alpha_frames, bg_rgb):
    """
    Pad every frame with transparent margin to a square canvas, centred.
    Emoji/sticker slots are square; padding here rather than letting the host
    letterbox keeps the art centred and unstretched.
    """
    h, w = alpha_frames[0].shape
    side = max(h, w)
    if side == h == w:
        return rgb_frames, alpha_frames
    oy, ox = (side - h) // 2, (side - w) // 2
    out_rgb, out_alpha = [], []
    for rgb, alpha in zip(rgb_frames, alpha_frames):
        r = np.zeros((side, side, 3), np.uint8)
        r[:, :] = np.asarray(bg_rgb, dtype=np.uint8)
        a = np.zeros((side, side), np.uint8)
        r[oy:oy + h, ox:ox + w] = rgb
        a[oy:oy + h, ox:ox + w] = alpha
        out_rgb.append(r)
        out_alpha.append(a)
    return out_rgb, out_alpha


def fit_to_target_bytes(rgb_frames, alpha_frames, durations, loop, output_path,
                        target_kb, fmt, args, log=None):
    """
    Shrink a WebP/AVIF under `target_kb`, preferring the least destructive lever
    first. Measured ordering (references/lessons.md SS16), NOT guesswork:

      * Quality before resolution before frames. On a real 128x128 emoji, AVIF
        held all 124 frames at 244 KB where WebP had to fall to 42 frames --
        dropping frames is the most visible loss, so it goes last.
      * For WebP at NATIVE resolution, lossy is worse than lossless on BOTH
        axes (2675 KB at q85 vs 2114 KB lossless), so the ladder only reaches
        for WebP lossy once the frames have been scaled down, where the
        ordering genuinely reverses (at 128px: 650 KB lossy vs 1190 lossless).
      * AVIF quality=100 is NOT lossless and is the biggest output of all --
        never used as a rung.

    Leaves the best attempt on disk either way and returns (size_bytes, hit).
    """
    say = (lambda m: log.append(m)) if log is not None else (lambda m: None)
    target_bytes = target_kb * 1024
    resample = Image.NEAREST if getattr(args, 'pixel_art', False) else Image.LANCZOS

    def encode(fr, al, dur, scale, quality, lossless):
        if scale != 1.0:
            fr, al = resize_rgba_frames(fr, al, scale, resample=resample, binarize=False)
        if fmt == 'avif':
            return render_frames_to_avif(fr, al, dur, loop, output_path, quality=quality)
        if fmt == 'apng':
            # Lossless only -- APNG has no quality knob, so the cascade can trade
            # resolution and frames for it but not encoder quality.
            return render_frames_to_apng(fr, al, dur, loop, output_path)
        return render_frames_to_webp(fr, al, dur, loop, output_path,
                                     lossless=lossless, quality=quality,
                                     method=getattr(args, 'webp_method', 4))

    # ⚠️ If the caller already chose an explicit output size (--resize-max-dim,
    # e.g. a platform's 128x128 emoji slot), this cascade must NOT shrink below
    # it. Confirmed bug: the scale ladder was applied ON TOP of an explicit
    # 128px resize and silently produced 48x48 / 64x64 / 96x96 "128px emoji"
    # files. A byte cap is a constraint; the requested resolution is a
    # REQUIREMENT. Trade quality and frames instead, and if it still will not
    # fit, say so rather than quietly delivering a different size.
    _pinned = getattr(args, 'resize_max_dim', None) is not None
    _scales = (1.0,) if _pinned else (1.0, 0.75, 0.5, 0.375, 0.25)
    if fmt == 'avif':
        rungs = [(sc, q, False) for sc in _scales for q in (95, 85, 75, 65, 55, 45)]
    else:
        rungs = []
        for sc in _scales:
            rungs += [(sc, 100, True)] + [(sc, q, False) for q in (95, 90, 80, 70, 60)]

    best = None
    for stride in (1, 2, 3, 4):
        fr, al, dur = (reduce_frame_count(rgb_frames, alpha_frames, durations, stride)
                       if stride > 1 else (rgb_frames, alpha_frames, durations))
        for scale, quality, lossless in rungs:
            size = encode(fr, al, dur, scale, quality, lossless)
            desc = (f"stride={stride} scale={scale:g} "
                    f"{'lossless' if lossless else f'q{quality}'}")
            say(f"  tried {desc}: {size/1024:.1f} KB")
            if best is None or size < best[0]:
                best = (size, desc, (stride, scale, quality, lossless))
            if size <= target_bytes:
                say(f"Hit target: {size/1024:.1f} KB <= {target_kb} KB ({desc})")
                return size, True
    # Nothing fit. Re-encode the SMALLEST configuration so the file left on disk
    # is the one we report -- otherwise the file is whatever the last rung
    # happened to produce, and the reported number describes a different file.
    if best is not None and best[2] is not None:
        stride, scale, quality, lossless = best[2]
        fr, al, dur = (reduce_frame_count(rgb_frames, alpha_frames, durations, stride)
                       if stride > 1 else (rgb_frames, alpha_frames, durations))
        encode(fr, al, dur, scale, quality, lossless)
    say(f"Could not reach {target_kb} KB; smallest was {best[0]/1024:.1f} KB ({best[1]})."
        + (" The output size was pinned by --resize-max-dim, so resolution was NOT "
           "reduced to get there -- drop --resize-max-dim to allow it." if _pinned else ""))
    return os.path.getsize(output_path), False


def resize_rgba_frames(rgb_frames, alpha_frames, scale, resample=None, binarize=True):
    """
    Resize every frame's RGB and alpha by `scale`, re-binarizing alpha.
    `resample` defaults to LANCZOS (smooth, correct for antialiased vector
    art) -- pass Image.NEAREST for pixel art / hard-edged content, where
    LANCZOS would introduce exactly the antialiasing/blur that shouldn't
    be there, undermining the whole point of hard-edged source art. See
    --pixel-art, which sets this automatically.
    """
    if resample is None:
        resample = Image.LANCZOS
    new_rgb, new_alpha = [], []
    for rgb, alpha in zip(rgb_frames, alpha_frames):
        h, w = alpha.shape
        new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
        if binarize:
            rgb_im = Image.fromarray(rgb).resize((new_w, new_h), resample)
            alpha_im = Image.fromarray(alpha).resize((new_w, new_h), resample)
            new_rgb.append(np.array(rgb_im))
            a = np.array(alpha_im)
            new_alpha.append(np.where(a > 127, 255, 0).astype(np.uint8))
        else:
            # 8-bit-alpha path: PREMULTIPLY before resampling, unpremultiply after.
            # Resampling straight (non-premultiplied) RGBA lets fully-transparent
            # pixels' colour bleed into the edge, which for this script means the
            # BACKGROUND COLOUR haloes exactly the silhouette we just cut out.
            # Re-binarizing would also throw away the partial alpha that is the
            # whole point of a WebP/AVIF output.
            af = alpha.astype(np.float32) / 255.0
            pm = np.dstack([rgb.astype(np.float32) * af[:, :, None], alpha.astype(np.float32)])
            im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), 'RGBA').resize(
                (new_w, new_h), resample)
            r = np.array(im).astype(np.float32)
            a2 = r[:, :, 3:4] / 255.0
            rgb_out = np.where(a2 > 1e-4, r[:, :, :3] / np.maximum(a2, 1e-4), 255.0)
            new_rgb.append(np.clip(rgb_out, 0, 255).astype(np.uint8))
            new_alpha.append(r[:, :, 3].astype(np.uint8))
    return new_rgb, new_alpha


def fit_scale_for_max_dimension(width, height, max_dim):
    """
    Scale factor to bring the LONGER of width/height down to max_dim,
    preserving aspect ratio (e.g. a 512-wide target on a taller-than-wide
    source instead constrains height to 512 and scales width to match --
    "512px on the dominant dimension" rather than a fixed axis). Never
    upscales: returns 1.0 if the source is already within the target, so
    running a small icon through the 'heavy' tier doesn't blow it up to
    256px for no reason.
    """
    longer = max(width, height)
    if longer <= max_dim:
        return 1.0
    return max_dim / longer


def find_tiny_removed_regions(alpha_frames, max_size):
    """
    Per-frame: find every connected TRANSPARENT (alpha==0) region at or
    below max_size pixels, excluding whichever removed region is largest
    in that frame (assumed to be the true background -- consistent with
    largest_bg_component_mask's reasoning elsewhere in this file). Returns
    a list of boolean masks, one per frame, marking exactly those tiny
    regions' own pixels.

    Built for erode_alpha_edge_exempting_tiny_regions below -- see that
    function's docstring for why tiny removed regions need to be found
    and handled separately from normal edge cleanup in the first place.
    """
    struct = np.ones((3, 3), dtype=bool)
    tiny_masks = []
    for alpha in alpha_frames:
        removed = (alpha == 0)
        labeled, num = ndimage.label(removed, structure=struct)
        tiny = np.zeros(alpha.shape, dtype=bool)
        if num > 0:
            sizes = ndimage.sum(removed, labeled, range(1, num + 1))
            largest_label = int(np.argmax(sizes)) + 1
            for lab in range(1, num + 1):
                if lab == largest_label:
                    continue
                if sizes[lab - 1] <= max_size:
                    tiny |= (labeled == lab)
        tiny_masks.append(tiny)
    return tiny_masks


def collect_small_removed_region_sizes(rgb, bg_rgb, tolerance, max_plausible_size=500, mask=None):
    """
    Single-frame version of find_tiny_removed_regions's labeling pattern,
    but on a raw background color_mask (analyze() has no processed alpha
    array to work with) and returning sizes for a histogram instead of
    masks.

    Excludes the largest removed component per frame (assumed true
    background), same reasoning as find_tiny_removed_regions and
    largest_bg_component_mask elsewhere in this file -- but that alone is
    NOT enough here, unlike in find_tiny_removed_regions: this function
    runs on the raw, pre-processing color_mask, where a large ENCLOSED
    candidate region (e.g. a highlight that --protect-outline-color would
    protect) is a second large background-colored component that isn't the
    single largest one, so it would otherwise get miscounted as a "small"
    region. Confirmed on real fixtures: jewelry.gif's own protected
    highlight region (3700-11500+px) was being reported as a "small removed
    region" this way, inflating the suggested --erosion-exempt-max-size by
    ~300x (12647 vs. the real ballpark of ~40). max_plausible_size is a
    heuristic ceiling -- real erosion-inflation-prone gaps measured well
    under 150px on every fixture checked so far (references/lessons.md
    SS11's own motivating case was a single ORIGINAL pixel), while every
    false positive found was in the thousands; 500 leaves a wide margin on
    both sides for the fixtures this was verified against, but a genuinely
    larger deliberate "small" removed region on some future asset would
    need this raised.

    Accepts an optional pre-computed `mask` -- see measure_bg_component_
    margin's docstring for why (shared per-frame computation in analyze(),
    a real cost fix, not premature optimization).
    """
    removed = color_mask(rgb, bg_rgb, tolerance) if mask is None else mask
    struct = np.ones((3, 3), dtype=bool)
    labeled, num = ndimage.label(removed, structure=struct)
    if num == 0:
        return []
    sizes = ndimage.sum(removed, labeled, range(1, num + 1))
    largest_label = int(np.argmax(sizes)) + 1
    return [int(sizes[lab - 1]) for lab in range(1, num + 1)
            if lab != largest_label and sizes[lab - 1] <= max_plausible_size]


def find_transient_removed_regions(alpha_frames, max_size=500, persistence=0.9,
                                    size_tolerance=0.15):
    """
    Like find_tiny_removed_regions, but keeps ONLY the regions that are
    incidental -- and needs no size threshold to tell them apart.

    `--erosion-exempt-max-size` is a size threshold, so it exempts every removed
    region at or below it. That only separates incidental noise from design when
    the two occupy DIFFERENT size ranges, and on real art they need not: love's
    four controller buttons are design at 286-306px while its transient noise
    reaches 442px, so any threshold that covers the noise also covers the
    buttons and reintroduces the v3.3.3 fringe (SS18.2). The guard added there
    detects the overlap and declines to recommend the flag -- which picks the
    safer side of the conflict rather than resolving it, leaving the v3.1.0
    small-region inflation bug live for those assets.

    This resolves it instead, using the classification analyze() already does
    correctly: a region present in ~every frame at a stable size is DESIGN; one
    that comes and goes is incidental. Exempt by identity, not by size, and the
    two size ranges are free to overlap completely.

    Returns a list of per-frame boolean masks, same shape as
    find_tiny_removed_regions, so it drops straight into
    erode_alpha_edge_exempting_tiny_regions.
    """
    struct = np.ones((3, 3), dtype=bool)
    per_frame = []          # [(label_array, {label: size}), ...]
    for alpha in alpha_frames:
        removed = (alpha == 0)
        labeled, num = ndimage.label(removed, structure=struct)
        sizes = {}
        if num > 0:
            counts = ndimage.sum(removed, labeled, range(1, num + 1))
            largest = int(np.argmax(counts)) + 1
            for lab in range(1, num + 1):
                if lab == largest:
                    continue        # the true background component
                sz = int(counts[lab - 1])
                if sz <= max_size:
                    sizes[lab] = sz
        per_frame.append((labeled, sizes))

    # Cluster observed sizes across frames, the same way analyze() does, so a
    # region whose size jitters by a few pixels is not split into two clusters.
    clusters = []                       # [representative_size, {frame indices}]
    for fi, (_, sizes) in enumerate(per_frame):
        for sz in sizes.values():
            for c in clusters:
                if abs(sz - c[0]) <= size_tolerance * max(sz, c[0]):
                    c[1].add(fi)
                    break
            else:
                clusters.append([sz, {fi}])
    n = max(len(per_frame), 1)
    persistent_reps = [c[0] for c in clusters if len(c[1]) / n >= persistence]

    def _is_design(sz):
        return any(abs(sz - r) <= size_tolerance * max(sz, r) for r in persistent_reps)

    masks = []
    for labeled, sizes in per_frame:
        m = np.zeros(labeled.shape, dtype=bool)
        for lab, sz in sizes.items():
            if not _is_design(sz):
                m |= (labeled == lab)
        masks.append(m)
    return masks


def erode_alpha_edge_exempting_tiny_regions(alpha_frames, iterations, tiny_masks):
    """
    Same contraction as erode_alpha_edge, EXCEPT any pixel inside a given
    per-frame tiny_masks[i] is excluded from the erosion computation
    entirely (as if it were fully opaque, i.e. didn't exist as a removed
    region at all), then punched back to transparent at its own exact
    original size immediately afterward.

    Why this exists, not just erode_alpha_edge with a smaller iterations
    value: erode_alpha_edge's contraction is a GLOBAL, uniform shrink of
    the opaque region by `iterations` pixels in every direction, applied
    everywhere without regard to the size of what's on the other side of
    any given boundary. That's the right behavior for its intended case
    (trimming dither/resample fuzz off a large silhouette's outer edge --
    a couple of pixels off a large boundary is proportionally tiny). It
    is NOT the right behavior for a small, ISOLATED removed region well
    below the erosion radius's own scale: eroding the opaque ring
    surrounding it by `iterations` pixels doesn't trim it proportionally,
    it grows it, because the erosion consumes the thin opaque wall around
    it rather than a thin sliver off a large area on the other side.
    Confirmed directly on a real asset: a single ORIGINAL 1px enclosed
    background-colored pixel (a natural, incidental gap where an
    animated gear's tooth transiently grazed a static book-page outline,
    not a deliberate design hole) became a 49-70px hole after a normal
    2px `erode_alpha_edge` pass -- a 50-70x size inflation turning an
    imperceptible artifact into a visibly distracting one. This was
    initially patched by only recovering nearby PARTIALLY-restorable
    pixels post-erosion (dilating the tiny region by the erosion radius
    and restoring anything reclaimed that wasn't also near a legitimately
    large removed region) -- that approach was less wrong but still
    measurably incomplete (a 1px notch still came out ~40-50px after
    restoration) because erosion's actual spillover pattern around a
    small feature isn't a clean uniform ring, especially near other
    nearby geometry (a second small feature, a corner, another edge).
    Excluding the tiny region from erosion's INPUT entirely, rather than
    trying to undo erosion's effect on it after the fact, is exact by
    construction: erosion behaves exactly as if the tiny region were
    never flagged as removable in the first place (identical result to
    the surrounding area's normal, correct edge treatment), and the tiny
    region itself is restored to precisely its own pre-erosion pixels,
    no more and no less.

    A second, real, generalizable lesson from the same case: the actual
    UI-facing threshold decision here (how large is "tiny" -- i.e. what
    max_size to pass to find_tiny_removed_regions) is separate from
    whether a removed region should exist at all in the first place
    (that's decided upstream, by whatever produced alpha_frames --
    --tumble-safe's --keep-bg-blob-if-near, a manual position/color rule,
    or normal antialiasing-band feathering). Getting ONLY the removal
    decision right and applying normal erosion regardless still produces
    a real, visible bug on any sufficiently small removed region,
    independent of how correctly that region was identified as removable
    in the first place. Whenever any removal mechanism in this skill
    (this one included) might produce a removed region under roughly
    20-30px, route the final erosion pass through this function instead
    of erode_alpha_edge directly.
    """
    if iterations <= 0:
        return list(alpha_frames)
    exempted_pre = []
    for alpha, tiny in zip(alpha_frames, tiny_masks):
        a = alpha.copy()
        a[tiny] = 255  # erosion must not see these pixels as removed at all
        exempted_pre.append(a)
    eroded = erode_alpha_edge(exempted_pre, iterations=iterations)
    final = []
    for alpha_out, tiny in zip(eroded, tiny_masks):
        a = alpha_out.copy()
        a[tiny] = 0  # restore each tiny region to its own exact original pixels
        final.append(a)
    return final


def measure_outer_ring_background_fraction(rgb, alpha, bg_rgb, palette,
                                           opaque_min=250):
    """
    Fraction of the outermost NEAR-OPAQUE ring that is closer to the background
    colour than to any of the art's own flat colours. High = a pale fringe the
    edge cleanup should have removed.

    `opaque_min` is what makes this usable on 8-bit alpha. On a GIF every pixel
    is 0 or 255 and the ring is just "the edge". On WebP/AVIF the edge is a real
    alpha ramp, and those ramp pixels are SUPPOSED to be pale and semi-
    transparent -- counting them would flag correct output as fringed. Looking
    only at pixels that are essentially fully opaque asks the right question in
    both cases: is there anything SOLID here that should not be?

    Returns None when the frame has no such ring, so callers can tell "measured
    zero" apart from "nothing to measure".
    """
    solid = alpha >= opaque_min
    ring = ndimage.binary_dilation(~solid, iterations=1) & solid
    if not ring.any():
        return None
    pal = np.asarray(palette, np.float32).reshape(-1, 3)
    if len(pal) == 0:
        return None
    px = rgb[ring].astype(np.float32)
    d_bg = np.linalg.norm(px - np.asarray(bg_rgb, np.float32), axis=-1)
    d_art = np.linalg.norm(px[:, None, :] - pal[None, :, :], axis=-1).min(axis=1)
    return float((d_bg < d_art).mean())


def calibrate_edge_cleanup_erosion(rgb_frames, alpha_frames, bg_rgb, palette,
                                    candidates=(0, 1, 2, 3), tiny_masks=None,
                                    tolerance_above_floor=0.02, log=None):
    """
    Choose --edge-cleanup-erosion by comparing THIS asset against ITSELF.

    This exists because the fringe metric has no honest global threshold. It
    separates cleanly WITHIN one asset -- every erosion-0 reading is 2-4x that
    same asset's own clean baseline -- but the ranges OVERLAP across assets:
    measured, heart's genuinely fringed 0.0665 sits BELOW crystal's perfectly
    clean 0.0830, because art with a baked-in fade legitimately carries pale
    near-background pixels at its boundary (references/lessons.md SS18.5).

    A constant cannot express "2-4x above THIS asset's floor". So rather than
    invent one, measure the asset at each candidate erosion and read the answer
    off its own curve. The pick is the SMALLEST erosion whose reading is within
    `tolerance_above_floor` of that asset's own minimum -- smallest because
    erosion also eats thin strokes, so the goal is the least erosion that has
    already removed the fringe, not the most.

    One rule covers both failure directions: too little erosion reads well above
    the floor, too much shows no further improvement and loses the tie to the
    smaller candidate.

    Runs on in-memory alpha before any encode, so it costs one extra erosion
    pass per candidate -- not one extra render.
    """
    log = log if log is not None else []
    table = {}
    for e in candidates:
        if e == 0:
            cand_alpha = alpha_frames
        elif tiny_masks is not None:
            cand_alpha = erode_alpha_edge_exempting_tiny_regions(alpha_frames, e, tiny_masks)
        else:
            cand_alpha = erode_alpha_edge(alpha_frames, iterations=e)
        vals = [v for rgb, al in zip(rgb_frames, cand_alpha)
                if (v := measure_outer_ring_background_fraction(rgb, al, bg_rgb, palette)) is not None]
        table[e] = round(float(np.mean(vals)), 4) if vals else None
    measured = {e: v for e, v in table.items() if v is not None}
    if not measured:
        log.append("erosion calibration: no measurable opaque edge ring -- keeping the default.")
        return None, table
    floor = min(measured.values())
    best = min(e for e, v in measured.items() if v <= floor + tolerance_above_floor)
    log.append("erosion calibrated against this asset's own curve ("
               + ", ".join(f"{e}:{v}" for e, v in sorted(measured.items()))
               + f") -> {best}; floor {floor:.4f}, and {best} is the smallest level "
                 f"already within {tolerance_above_floor} of it, so the fringe is gone "
                 f"without eroding more than necessary.")
    return best, table


def erode_alpha_edge(alpha_frames, iterations=1):
    """
    Shave the outermost `iterations` pixel(s) off every frame's opaque
    region, snapping them to fully transparent. Targets "rugged edges" --
    the last ring of pixels right at the opaque/transparent boundary often
    carries leftover dither noise or resize resampling fuzz, and trimming
    it gives a cleaner, more consistent silhouette. Uses a full 3x3
    (8-connected) structuring element for a uniform contraction in all
    directions including diagonals -- the plus-shaped 4-connected
    STRUCTURE used elsewhere in this file for flood-fill connectivity
    would leave the boundary's corner pixels untouched, which isn't what
    "shave off 1 pixel all around" should mean here.

    `iterations <= 0` is an explicit no-op (returns the input unchanged).
    This guard is NOT optional/defensive-programming filler -- confirmed
    directly as a real, previously-shipped bug: scipy.ndimage.binary_
    erosion treats `iterations=0` as "erode until convergence" (its own
    documented behavior for iterations < 1), which for any bounded shape
    means eroding it away to NOTHING, not "no erosion" like every other
    call site in this file assumes. Confirmed concretely: a 10x10 filled
    square went from 100px to 0px at iterations=0. This is exactly
    backwards from what `--edge-cleanup-erosion 0` (a documented,
    user-facing option) promises, and it was only accidentally not
    hit by --pixel-art's own use of erosion=0, because --pixel-art
    also sets feather=False, which happens to skip the call site
    entirely via an unrelated guard -- calling --edge-cleanup-erosion 0
    directly (feathering still on, no --pixel-art) hit this directly and
    silently erased 100% of a real icon's content. Any future refactor of
    this function must keep an explicit `iterations <= 0` guard rather
    than relying on callers to avoid passing 0, or relying on scipy's
    default behavior at the boundary.
    """
    if iterations <= 0:
        return list(alpha_frames)
    struct = np.ones((3, 3), dtype=bool)
    new_alpha = []
    for alpha in alpha_frames:
        mask = alpha > 0
        eroded = ndimage.binary_erosion(mask, structure=struct, iterations=iterations)
        new_alpha.append(np.where(eroded, alpha, 0).astype(np.uint8))
    return new_alpha


def check_erosion_damage(alpha_frames_before, alpha_frames_after,
                          min_component_px=25, min_survival_frac=0.3, max_frames_checked=40):
    """
    Precise complement to the blanket small-canvas warning: instead of a
    canvas-size proxy, directly measure whether erosion actually erased or
    badly damaged a specific real feature, and say exactly where.

    For each of up to `max_frames_checked` sampled frames, label connected
    opaque components in the PRE-erosion alpha, then check what fraction
    of each component's pixels are still opaque POST-erosion. A component
    that mostly or entirely vanished (survival fraction under
    `min_survival_frac`) is reported with its frame index, size, and
    bounding box.

    `min_component_px` deliberately excludes tiny components: the dithered
    speckle pixels along a soft feathered edge are SUPPOSED to disappear
    during erosion cleanup (that's the point of the feature), and without
    a size floor those would swamp this check with false positives on
    every single feathered GIF. 25px is small enough to catch a thin
    stroke or small dot (e.g. the ~16px-wide status dot measured on a real
    test icon) while being comfortably larger than isolated dither noise,
    which is typically only a few pixels.

    Returns a list of dicts (empty if nothing looks damaged); does not
    raise or modify anything -- purely diagnostic, for the caller to print.
    """
    struct = np.ones((3, 3), dtype=bool)
    n = len(alpha_frames_before)
    if n <= max_frames_checked:
        sample_idxs = range(n)
    else:
        sample_idxs = sorted(set(np.linspace(0, n - 1, max_frames_checked).astype(int).tolist()))

    findings = []
    for i in sample_idxs:
        before_mask = alpha_frames_before[i] > 0
        after_mask = alpha_frames_after[i] > 0
        labeled, num = ndimage.label(before_mask, structure=struct)
        if num == 0:
            continue
        sizes = ndimage.sum(before_mask, labeled, index=range(1, num + 1))
        for comp_id, size in enumerate(sizes, start=1):
            if size < min_component_px:
                continue
            comp_mask = labeled == comp_id
            survived = np.count_nonzero(comp_mask & after_mask)
            frac = survived / size
            if frac < min_survival_frac:
                ys, xs = np.where(comp_mask)
                findings.append({
                    'frame': int(i),
                    'component_size_px': int(size),
                    'survival_fraction': round(float(frac), 3),
                    'bbox_xyxy': [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
                })
    return findings


# The three named optimization tiers. 'optimize' is the light/base tier;
# 'medium' and 'heavy' both build on ALL of its steps (resize, 1px edge
# erosion) and add progressively more aggressive gifsicle settings --
# 'heavy' also overrides the resize target down to 256px. Frame-stride is
# NOT part of 'optimize': it's a real motion-quality tradeoff (choppier
# playback), not a free size win, so it only kicks in starting at 'medium'
# where the user has already signaled they want a more aggressive size
# reduction. 'optimize' stays crop + resize + erosion + lossless gifsicle
# only -- every source frame survives. See SKILL.md for the reasoning and
# the real measurements behind each choice.
TIER_SPECS = {
    'optimize': {'stride': 1, 'resize_max_dim': 512, 'gifsicle_level': 'lossless'},
    'medium':   {'stride': 2, 'resize_max_dim': 512, 'gifsicle_level': 'medium'},
    'heavy':    {'stride': 2, 'resize_max_dim': 256, 'gifsicle_level': 'heavy'},
}


def apply_tier(rgb_frames, alpha_frames, durations, tier, stride_override=None,
                resize_override=None, pixel_art=False, log=None):
    """
    Apply one of the named optimization tiers' frame/pixel-level steps
    (frame-stride, resize-to-fit, 1px edge erosion) IN PLACE on the given
    frame data. Does NOT run gifsicle -- that has to happen after
    render_frames_to_gif, since it operates on the encoded file, not numpy
    arrays; the caller is expected to render then call gifsicle_optimize
    with TIER_SPECS[tier]['gifsicle_level']. Cropping is also the caller's
    responsibility (done once, before any tier, in process()) since it's
    shared by all tiers rather than tier-specific.

    `stride_override` lets an explicit --frame-stride win over the tier's
    own default stride (1 for 'optimize' -- i.e. no frame drop -- and 2 for
    'medium'/'heavy'; tier provides sensible defaults, explicit flags take
    precedence). `resize_override` similarly lets an explicit
    --resize-max-dim win over the tier's own resize target (512 for
    optimize/medium, 256 for heavy) for an arbitrary size that doesn't
    match either. `pixel_art` switches any resize in this tier to
    nearest-neighbor resampling instead of LANCZOS, and skips the tier's
    own post-resize erosion (see --pixel-art's help text for why). `log`
    is an optional list to append human-readable step descriptions to
    (process() uses this for stderr output).
    """
    spec = TIER_SPECS[tier]
    log = log if log is not None else []

    stride = stride_override if stride_override is not None else spec['stride']
    if stride > 1:
        avg_before = average_frame_delay(durations)
        n_before = len(durations)
        rgb_frames, alpha_frames, durations = reduce_frame_count(
            rgb_frames, alpha_frames, durations, stride)
        avg_after = average_frame_delay(durations)
        log.append(f"Frame-rate reduced (stride {stride}): {n_before} -> "
                    f"{len(durations)} frames, total playback length "
                    f"unchanged ({sum(durations)}ms), avg delay "
                    f"{avg_before:.0f}ms -> {avg_after:.0f}ms.")
        if avg_after > 120:
            log.append(f"WARNING: average frame delay after this stride is "
                        f"{avg_after:.0f}ms (~{1000/avg_after:.1f}fps) -- "
                        f"dropped frames will likely read as visibly "
                        f"choppier motion here, not just 'slightly less "
                        f"smooth'.")

    h, w = alpha_frames[0].shape
    resize_target = resize_override if resize_override else spec['resize_max_dim']
    scale = fit_scale_for_max_dimension(w, h, resize_target)
    if scale < 1.0:
        resample = Image.NEAREST if pixel_art else Image.LANCZOS
        rgb_frames, alpha_frames = resize_rgba_frames(rgb_frames, alpha_frames, scale, resample=resample)
        new_h, new_w = alpha_frames[0].shape
        log.append(f"Resized to fit {resize_target}px on the "
                    f"longer side: {w}x{h} -> {new_w}x{new_h}"
                    f"{' (nearest-neighbor, pixel-art mode)' if pixel_art else ''}.")
        if pixel_art:
            # No post-resize erosion cleanup here -- nearest-neighbor
            # resizing doesn't introduce the antialiasing fuzz LANCZOS
            # would, so there's nothing for this step to clean up, and
            # erosion on pixel art risks the same real-detail destruction
            # --pixel-art exists specifically to avoid (see
            # measure_edge_hardness's docstring for the confirmed case:
            # 0% survival on a real pixel-art test shape).
            log.append("Skipped post-resize erosion (pixel-art mode -- "
                        "nearest-neighbor resize has no fuzz to clean up).")
        else:
            # Resize-specific cleanup: LANCZOS resampling on the alpha channel
            # (and on RGB, which can reintroduce a fringe-colored edge ring
            # analogous to the pre-resize one already cleaned up above) tends
            # to leave its own bit of fuzz right at the new boundary. Only
            # needed when a resize actually happened -- separate from, and in
            # addition to, the feather-fringe cleanup erosion already applied
            # to every frame regardless of tier.
            alpha_frames_pre_erosion = alpha_frames
            alpha_frames = erode_alpha_edge(alpha_frames, iterations=1)
            log.append("Eroded 1px off the opaque edge (targets fuzz "
                        "reintroduced by the resize above).")
            damage = check_erosion_damage(alpha_frames_pre_erosion, alpha_frames)
            if damage:
                log.append(f"WARNING: post-resize erosion may have erased or "
                           f"badly shrunk {len(damage)} real detail(s) at "
                           f"{new_w}x{new_h} -- a detail that was fine at the "
                           f"pre-resize size can become too thin to survive "
                           f"once downscaled. Example: frame {damage[0]['frame']}, "
                           f"~{damage[0]['component_size_px']}px component at "
                           f"bbox {damage[0]['bbox_xyxy']}, only "
                           f"{damage[0]['survival_fraction']*100:.0f}% survived. "
                           f"Consider a larger --resize-max-dim if this detail "
                           f"matters.")
    else:
        log.append(f"Already within {resize_target}px on the "
                    f"longer side ({w}x{h}) -- no resize needed.")

    return rgb_frames, alpha_frames, durations


def reduce_frame_count(rgb_frames, alpha_frames, durations, stride):
    """
    Keep every `stride`-th frame, folding the dropped frames' durations into
    the kept frame so total playback length is preserved (choppier motion
    rather than sped-up motion).
    """
    new_rgb, new_alpha, new_dur = [], [], []
    n = len(rgb_frames)
    i = 0
    while i < n:
        chunk_end = min(i + stride, n)
        new_rgb.append(rgb_frames[i])
        new_alpha.append(alpha_frames[i])
        new_dur.append(sum(durations[i:chunk_end]))
        i += stride
    return new_rgb, new_alpha, new_dur


def optimize_to_target(rgb_frames, alpha_frames, durations, loop, output_path, target_kb,
                        quantizer='pil', pixel_art=False):
    """
    Iteratively shrink the GIF to fit under target_kb by walking up the
    same three named tiers used elsewhere in this skill ('optimize' ->
    'medium' -> 'heavy'), then escalating stride/scale further within the
    'heavy' settings as a last resort if even that isn't enough. Using the
    tiers as the backbone (rather than an independent lever search) means
    --target-kb produces results consistent with what --compress would
    give at each stage, instead of a different, undocumented combination.

    Re-saves output_path in place at each attempt; the last attempt made
    is what's left on disk. Returns a dict summarizing what was tried and
    whether the target was hit.
    """
    attempts = []

    def hit(size):
        return size / 1024 <= target_kb

    def record(lever, value, size):
        attempts.append({'lever': lever, 'value': value, 'size_kb': round(size / 1024, 1)})

    size = render_frames_to_gif(rgb_frames, alpha_frames, durations, loop, output_path, quantizer=quantizer)
    record('baseline', None, size)
    if hit(size):
        return {'hit_target': True, 'final_size_kb': round(size / 1024, 1), 'attempts': attempts}

    gifsicle_ok = ensure_gifsicle()

    cur_rgb, cur_alpha, cur_dur = rgb_frames, alpha_frames, durations
    for tier in ('optimize', 'medium', 'heavy'):
        cur_rgb, cur_alpha, cur_dur = apply_tier(cur_rgb, cur_alpha, cur_dur, tier, pixel_art=pixel_art)
        size = render_frames_to_gif(cur_rgb, cur_alpha, cur_dur, loop, output_path, quantizer=quantizer)
        if gifsicle_ok:
            gifsicle_optimize(output_path, TIER_SPECS[tier]['gifsicle_level'])
            size = os.path.getsize(output_path)
        record(f'tier_{tier}', None, size)
        if hit(size):
            return {'hit_target': True, 'final_size_kb': round(size / 1024, 1), 'attempts': attempts}

    # Still over target even at 'heavy'. Last resort: keep escalating
    # frame-stride (capped by the same >120ms/frame choppiness guard used
    # everywhere else) and, if that alone isn't enough, keep shrinking the
    # canvas further below heavy's 256px floor. Both re-apply heavy's
    # gifsicle settings each time since that's already the most aggressive
    # tier defined.
    resample = Image.NEAREST if pixel_art else Image.LANCZOS
    for stride in (3, 4, 6):
        candidate_dur = reduce_frame_count(rgb_frames, alpha_frames, durations, stride)[2]
        if average_frame_delay(candidate_dur) > 120:
            break
        cur_rgb, cur_alpha, cur_dur = reduce_frame_count(rgb_frames, alpha_frames, durations, stride)
        cur_rgb, cur_alpha = resize_rgba_frames(
            cur_rgb, cur_alpha,
            fit_scale_for_max_dimension(cur_alpha[0].shape[1], cur_alpha[0].shape[0], 256),
            resample=resample)
        if not pixel_art:
            cur_alpha = erode_alpha_edge(cur_alpha, iterations=1)
        size = render_frames_to_gif(cur_rgb, cur_alpha, cur_dur, loop, output_path, quantizer=quantizer)
        if gifsicle_ok:
            gifsicle_optimize(output_path, 'heavy')
            size = os.path.getsize(output_path)
        record('frame_stride_beyond_heavy', stride, size)
        if hit(size):
            return {'hit_target': True, 'final_size_kb': round(size / 1024, 1), 'attempts': attempts}

    for extra_max_dim in (192, 128, 96):
        cur_rgb2, cur_alpha2 = resize_rgba_frames(
            cur_rgb, cur_alpha,
            fit_scale_for_max_dimension(cur_alpha[0].shape[1], cur_alpha[0].shape[0], extra_max_dim),
            resample=resample)
        if not pixel_art:
            cur_alpha2 = erode_alpha_edge(cur_alpha2, iterations=1)
        size = render_frames_to_gif(cur_rgb2, cur_alpha2, cur_dur, loop, output_path, quantizer=quantizer)
        if gifsicle_ok:
            gifsicle_optimize(output_path, 'heavy')
            size = os.path.getsize(output_path)
        record('scale_beyond_heavy', extra_max_dim, size)
        if hit(size):
            return {'hit_target': True, 'final_size_kb': round(size / 1024, 1), 'attempts': attempts}

    return {'hit_target': False, 'final_size_kb': round(size / 1024, 1), 'attempts': attempts}


def make_checkerboard(w, h, tile=8):
    y_idx, x_idx = np.indices((h, w))
    checker = ((x_idx // tile) + (y_idx // tile)) % 2
    board = np.where(checker[..., None] == 0, 200, 150).astype(np.uint8)
    return np.repeat(board, 3, axis=-1)


def build_preview(rgb_frames, alpha_frames, n_preview=6):
    """
    Composite a handful of frames, spread evenly across the animation, over
    a checkerboard and lay them out side by side in one PNG — a quick way
    to eyeball transparency/edge quality without opening the GIF itself.
    """
    n = len(rgb_frames)
    idxs = sorted(set(np.linspace(0, n - 1, min(n_preview, n)).astype(int).tolist()))

    tiles = []
    for i in idxs:
        rgb = rgb_frames[i].astype(float)
        alpha = (alpha_frames[i].astype(float) / 255.0)[..., None]
        board = make_checkerboard(rgb.shape[1], rgb.shape[0]).astype(float)
        comp = (rgb * alpha + board * (1 - alpha)).astype(np.uint8)
        tiles.append(comp)

    h = max(t.shape[0] for t in tiles)
    gap = 10
    total_w = sum(t.shape[1] for t in tiles) + gap * (len(tiles) - 1)
    canvas = np.full((h, total_w, 3), 255, dtype=np.uint8)
    x = 0
    for t in tiles:
        th, tw = t.shape[:2]
        canvas[0:th, x:x + tw] = t
        x += tw + gap
    return Image.fromarray(canvas)


def process(input_path, output_path, args, diagnostics=None):
    args = copy.copy(args)          # never mutate the caller's args (batch reuses them)
    out_format = resolve_output_format(output_path, args)
    if getattr(args, 'dither_mode', None) is None:
        args.dither_mode = 'continuous' if out_format in EIGHT_BIT_ALPHA_FORMATS else 'bayer'
    if getattr(args, 'translucent_region', None) and out_format not in EIGHT_BIT_ALPHA_FORMATS:
        raise SystemExit(
            "--translucent-region needs PARTIAL transparency, which GIF cannot "
            "store (1-bit alpha). Write a .webp, .avif or .apng output instead.")
    if not 0.0 <= getattr(args, 'translucent_alpha', 0.35) <= 1.0:
        raise SystemExit("--translucent-alpha must be between 0.0 and 1.0.")
    if getattr(args, 'recover_fade_alpha', False) and out_format == 'gif':
        raise SystemExit(
            "--recover-fade-alpha recovers PARTIAL transparency, which GIF cannot "
            "store (1-bit alpha). Write a .webp or .avif output instead -- that is "
            "the whole point of the flag; see references/lessons.md SS16.")
    if out_format == 'gif' and args.dither_mode == 'continuous':
        raise SystemExit("--dither-mode continuous needs 8-bit alpha, which GIF "
                         "does not have. Write a .webp output (or --format webp).")
    # --edge-cleanup-erosion's 2px default is calibrated for the BAYER-DITHER
    # path, where the last ring of edge pixels carries dither noise worth
    # trimming. With --dither-mode none there is no such ring: defringing has
    # already recoloured those pixels to the pure art colour and the cutoff is
    # applied to that clean alpha, so erosion removes real artwork and nothing
    # else. Measured across 5 real assets (references/lessons.md SS16) --
    # non-background pixels wrongly deleted, erosion 2 vs erosion 0:
    #   crystal 931,569 -> 2,631   explosion 448,205 -> 3,174   gift 635,720 -> 0
    #   love    807,343 -> 116,013 heart     257,143 -> 51,979
    # with --verify reporting looks_fringed=False at EVERY level, i.e. the
    # artifact erosion exists to remove was not present in any of them. It hits
    # thin strokes hardest (a 2px bite from each side of a 4px outline erases
    # it), which is why it showed up as "thin lines" and "large transparent
    # areas" on real review.
    if args.edge_cleanup_erosion is None:
        # 2 is calibrated for the BAYER-DITHER path. Under --dither-mode none the
        # dither noise it targets does not exist, and 2px bites thin strokes from
        # both sides -- measured across 5 assets, non-background pixels wrongly
        # deleted at erosion 2 vs 1: crystal 931,569 vs 466,092, explosion
        # 448,205 vs 223,686, gift 635,720 vs 313,631.
        #
        # ⚠️ But 0 is NOT the answer, and --verify's looks_fringed says False at
        # EVERY level, so it cannot be used to decide this -- a false negative
        # that cost a shipped regression. Measure the outer opaque ring instead:
        # at erosion 0, 49.1% of ring pixels are closer to the BACKGROUND colour
        # than to the art colour (mean distance to the true outline colour 162.3)
        # -- a visible pale fringe. At erosion 1 that collapses to 0.2% (mean
        # distance 15.6). 1 keeps the edge clean AND keeps thin strokes.
        args.edge_cleanup_erosion = (
            0 if out_format in EIGHT_BIT_ALPHA_FORMATS
            else 1 if (args.dither_mode == 'none' and not args.pixel_art)
            else 2)
        if args.edge_cleanup_erosion != 2:
            print(f"edge-cleanup erosion defaulted to {args.edge_cleanup_erosion} "
                  f"({'8-bit alpha needs no fringe trim' if out_format != 'gif' else 'no Bayer noise to trim under --dither-mode none, and 2 deletes thin strokes'}). "
                  f"Pass --edge-cleanup-erosion explicitly to override.", file=sys.stderr)
    if out_format in EIGHT_BIT_ALPHA_FORMATS:
        # --compress is GIF-encoder specific (palette quantization + gifsicle).
        # --target_kb is NOT: it is handled by fit_to_target_bytes below.
        gif_only = [n for n in ('compress',) if getattr(args, n, None)]
        if gif_only:
            raise SystemExit("These options are GIF-only and have no effect on WebP "
                             "output: " + ", ".join('--' + n.replace('_', '-')
                                                    for n in gif_only))
        if False:  # superseded by the unified erosion default resolved above
            # Erosion exists to hide the whitish fringe left by imperfect
            # unmixing under a 1-bit cutoff. With continuous alpha the
            # defringed partial-alpha edge is already correct, and eroding
            # it would eat the real soft edge instead of cleaning it.
            args.edge_cleanup_erosion = 0
            print("8-bit alpha output: edge-cleanup erosion defaulted to 0 "
                  "(it exists to hide 1-bit-cutoff fringe, which does not occur "
                  "here). Pass --edge-cleanup-erosion explicitly to override.",
                  file=sys.stderr)
    im0 = Image.open(input_path)
    # A STATIC source (JPEG, single-frame PNG) has no n_frames at all -- JPEG raises
    # AttributeError here. Confirmed 2026-08-17 on real files: the whole pipeline works on
    # a one-frame image, this single attribute access was the only thing stopping it.
    n_frames = getattr(im0, 'n_frames', 1)
    loop = im0.info.get('loop', 0)
    warn_if_source_has_transparency(im0, input_path)

    rgb_frames_raw = []
    source_trans_masks = []
    # The source's FULL alpha plane, not just its fully-transparent pixels. `alpha == 0`
    # is what source_trans_masks carries; everything between 1 and 254 -- a fade, a glow,
    # a soft shadow -- was invisible to this whole function, which is how a source could
    # go in with partial alpha and come out fully opaque. See the clamp below.
    source_alpha_planes = []
    durations = []

    for i in range(n_frames):
        im0.seek(i)
        durations.append(frame_duration_ms(im0, 100))
        source_trans_mask = get_source_transparency_mask(im0)  # BEFORE convert('RGB')
        _rgba = np.array(im0.convert('RGBA'))                  # also BEFORE convert('RGB')
        rgb = _rgba[..., :3].copy()
        source_alpha_planes.append(_rgba[..., 3])
        rgb_frames_raw.append(rgb)
        source_trans_masks.append(source_trans_mask)

    # The KEYING plane: what the pixels LOOK like, composited over the background where
    # the source is partially transparent. `rgb_frames_raw` is what gets written; this is
    # what gets compared. ⚠️ Never composite rgb_frames_raw itself -- the output must carry
    # original art colours, and the composite also masks MORE (3,017 extra pixels on
    # love_emoji_128.webp, exactly the half-transparent artwork --recover-fade-alpha exists
    # to reconstruct). Built only where a frame actually carries partial alpha, so an
    # ordinary opaque or 1-bit source shares the raw array and pays nothing.
    #
    # Does ANY frame carry real partial alpha? A 1-bit source (GIF, or a hard cutout) has
    # only 0 and 255, where the clamp below is a no-op; computing this once keeps it that
    # way instead of paying a per-frame minimum on every ordinary asset.
    _src_has_partial_alpha = any(
        bool(((a > 0) & (a < 255)).any()) for a in source_alpha_planes)
    rgb_frames_key = rgb_frames_raw
    if _src_has_partial_alpha:
        _bg_arr = np.asarray(hex_to_rgb(args.bg_color), dtype=np.float32)
        rgb_frames_key = []
        for _r, _a in zip(rgb_frames_raw, source_alpha_planes):
            if not ((_a > 0) & (_a < 255)).any():
                rgb_frames_key.append(_r)
                continue
            _f = (_a[..., None].astype(np.float32) / 255.0)
            rgb_frames_key.append((_r.astype(np.float32) * _f + _bg_arr * (1.0 - _f)
                                   ).round().clip(0, 255).astype(np.uint8))

    if getattr(args, 'tumble_safe', False):
        bg_rgb = hex_to_rgb(args.bg_color)
        keep_near = None
        if getattr(args, 'keep_bg_blob_if_near', None):
            keep_near = [hex_to_rgb(c.strip()) for c in args.keep_bg_blob_if_near.split(',') if c.strip()]
        lo, hi = (int(x) for x in args.hole_size_range.split(','))
        protected_masks = [
            build_tumble_safe_protected_mask(
                rgb, bg_rgb, args.tolerance,
                keep_bg_blob_if_near_colors=keep_near,
                hole_size_range=(lo, hi),
                hole_max_aspect=args.hole_max_aspect,
            )
            for rgb in rgb_frames_raw
        ]
    else:
        protected_masks = ([None] * n_frames
                           if getattr(args, 'recover_fade_alpha', False)
                           else build_protected_masks_robust(rgb_frames_raw, args))

    recovered_rgb = recovered_alpha = None
    if getattr(args, 'recover_fade_alpha', False):
        fade_log = []
        recovered_rgb, recovered_alpha = recover_fade_alpha_frames(
            rgb_frames_raw, hex_to_rgb(args.bg_color),
            fade_hexes=[h.strip() for h in args.fade_color.split(',')] if getattr(args, 'fade_color', None) else None,
            log=fade_log)
        for line in fade_log:
            print(line, file=sys.stderr)

    rgb_frames = []
    alpha_frames = []
    any_source_transparency = False
    source_alpha_scope_reasons = []

    # ONE policy for the whole animation. Deciding per frame made 17 of 57 measured
    # assets flip the veto branch mid-animation, which changes what is removable
    # between consecutive frames -- flicker, the same instability this project
    # rejects error-diffusion dithering for. The reach passed here is the distance
    # the removal path can actually act at, which is tolerance x the feather band
    # multiplier when feathering is on, not tolerance.
    _sa_band = int(getattr(args, 'source_alpha_band', SOURCE_ALPHA_BAND_DEFAULT))
    _sa_reach = (int(round(args.tolerance * getattr(args, 'feather_band_multiplier', 4.0)))
                 if getattr(args, 'feather', True) else args.tolerance)
    _sa_engaged = _sa_band_ok = False
    _sa_scopes = []
    if not getattr(args, 'ignore_source_alpha', False) and any(
            m is not None and m.any() for m in source_trans_masks):
        _sa_engaged, _sa_band_ok, _sa_reason, _sa_scopes = decide_source_alpha_policy(
            source_trans_masks, rgb_frames_raw, hex_to_rgb(args.bg_color),
            args.tolerance, _sa_band, _sa_reach)
        if _sa_engaged:
            source_alpha_scope_reasons.append(_sa_reason)

    def _scope_for(i, st):
        """The removal scope for frame `i`, reusing what the policy already computed.

        The policy dilates every engaged frame to answer the veto question and used to
        throw the result away, so this recomputed the identical dilation per frame --
        two passes where one does, on every alpha-carrying animation. Keyed by INDEX
        rather than by mask identity because two frames can legitimately share an
        equal mask, and by index the reuse is exact.
        """
        if not _sa_engaged or st is None or not st.any():
            return None
        if not _sa_band_ok:
            return st
        cached = _sa_scopes[i] if i < len(_sa_scopes) else None
        if cached is not None:
            return cached
        return ndimage.binary_dilation(st, structure=np.ones((3, 3), bool),
                                       iterations=_sa_band)

    # Edge-cleanup erosion exists to trim the mis-coloured ring that the feathering
    # math leaves behind. When the silhouette came from the SOURCE's own alpha there
    # is no such ring to trim, and erosion just eats the artwork: measured on a real
    # sprite written to .gif, 1,642 of 7,130 opaque pixels survived (23.0%) with the
    # scope working perfectly -- the colour path kept every pixel and erosion then
    # removed three quarters of them. Same "explicit wins, and we say so" contract
    # --pixel-art uses.
    if _sa_engaged and args.edge_cleanup_erosion > 0:
        if 'edge_cleanup_erosion' in typed_option_names():
            print(f"NOTE: the source's own alpha defines the silhouette, so edge-cleanup erosion "
                  f"has nothing to trim -- but you passed {args.edge_cleanup_erosion} explicitly, "
                  f"so it stands. It will shave {args.edge_cleanup_erosion}px off real artwork.",
                  file=sys.stderr)
        else:
            print(f"edge-cleanup erosion set to 0 (was {args.edge_cleanup_erosion}): the source's "
                  f"own alpha defines the silhouette, so there is no feathering fringe to trim and "
                  f"erosion would delete artwork. Pass --edge-cleanup-erosion explicitly to "
                  f"override.", file=sys.stderr)
            args.edge_cleanup_erosion = 0

    for i in range(n_frames):
        rgb = rgb_frames_raw[i]
        if recovered_rgb is not None:
            # Palette unmixing derives protection topologically (enclosed =
            # opaque), so it needs neither protected_masks nor the feather path.
            alpha, rgb_out = recovered_alpha[i], recovered_rgb[i]
            source_trans_mask = source_trans_masks[i]
            # This branch keys on the background colour too -- build_art_palette
            # rejects art colours near it and the flood starts from the border --
            # so it has the SAME data-loss failure, measured at 4,678 of 7,130
            # opaque (65.6%) on the sprite from SS28.13. It needs its own
            # treatment rather than the colour path's, because the whole point of
            # palette unmixing is to produce legitimate PARTIAL alpha for an
            # interior fade: forcing everything outside the scope fully opaque
            # would delete the feature. So outside the scope a pixel may keep any
            # recovered partial alpha but may NOT be made fully transparent --
            # an interior pixel reaching exactly 0 means "entirely background
            # coloured", which on a padding-coloured source is the outline.
            if source_trans_mask is not None and source_trans_mask.any():
                any_source_transparency = True
                scope = _scope_for(i, source_trans_mask)
                if scope is not None:
                    # Palette unmixing produces legitimate PARTIAL alpha for an
                    # interior fade, so forcing everything outside the scope fully
                    # opaque would delete the feature. Outside the scope a pixel may
                    # keep any recovered partial alpha but may not be made FULLY
                    # transparent: an interior pixel reaching exactly 0 means
                    # "entirely background coloured", which on a padding-coloured
                    # source is the outline. Measured before the fix: 4,678 of 7,130.
                    alpha = np.where(~scope & (alpha == 0), 255, alpha)
                    rgb_out = np.where(scope[..., None], rgb_out, rgb)
                alpha = np.where(source_trans_mask, 0, alpha)
            rgb_frames.append(rgb_out)
            alpha_frames.append(alpha)
            continue
        protected = protected_masks[i]
        if getattr(args, 'protect_band_only', None) is not None:
            removable_core = ~protected
            protected = build_band_only_removal_mask(removable_core, args.protect_band_only)

        # An already-transparent source has ALREADY decided which pixels are
        # background. Colour matching may then only clean up a leftover matte
        # fringe hugging that boundary; anywhere else it is matching padding
        # against artwork. Restricting rather than refusing is what keeps this
        # useful on a PARTIAL cut, and it degrades to "change nothing" when the
        # source's alpha is already complete.
        removal_scope = _scope_for(i, source_trans_masks[i])
        alpha, rgb_out = compute_alpha_mask(rgb, protected, args, removal_scope=removal_scope,
                                            rgb_key=rgb_frames_key[i])

        source_trans_mask = source_trans_masks[i]
        if source_trans_mask is not None and source_trans_mask.any():
            any_source_transparency = True
            # Force pixels the SOURCE already declared transparent to stay
            # transparent, overriding whatever this script's own color-based
            # detection concluded about them -- their revealed RGB is
            # meaningless flattening fallout, not real art (see
            # get_source_transparency_mask's docstring).
            alpha = np.where(source_trans_mask, 0, alpha)

        if _src_has_partial_alpha:
            # ⚠️ NEVER MORE OPAQUE THAN THE SOURCE. `rgb_frames_raw` is built with a bare
            # convert('RGB'), so by the time the colour path runs, a pixel the source drew
            # at 35% opacity is indistinguishable from a solid one -- its alpha was thrown
            # away, and estimate_alpha_and_defringe re-derives alpha from RGB alone. Any
            # such pixel whose flattened colour is not near the background therefore comes
            # out at 255. `removal_scope`'s `np.where(removal_scope, alpha, 255)` is the
            # loudest expression of it, but the promotion happens with or without a scope.
            #
            # Measured 2026-08-19 over every corpus source carrying >=50 partial-alpha px:
            # 218 of 249 came out with under 10% of that partial alpha left, 199 of them
            # with source-alpha scoping engaged. Twenty of the 45 largest are binary BY
            # DESIGN (--pixel-art implies --no-feather), which is why that control was run
            # -- the other 25 had feathering ON and lost the fade anyway. `love_emoji_128`
            # went in with 913 partial-alpha pixels and out with 0, its 5,509 opaque
            # becoming 6,422: every faded pixel promoted to solid.
            #
            # A minimum, not an assignment: the colour path may still make a pixel MORE
            # transparent (that is its job), it may never invent opacity the source did
            # not have. On a 1-bit source this is exactly a no-op, which `_src_has_partial
            # _alpha` already guarantees by not running it at all.
            #
            # Deliberately NOT applied to the `recovered_rgb` branch above:
            # --recover-fade-alpha exists to reconstruct a fade the source FLATTENED, so
            # there the source alpha is 255 by definition and clamping to it would be
            # either a no-op or a way to delete the feature.
            alpha = np.minimum(alpha, source_alpha_planes[i])

        rgb_frames.append(rgb_out)
        alpha_frames.append(alpha)

    if source_alpha_scope_reasons:
        # The scope's own reason string says what it did; do NOT restate it here.
        # The first version announced "plus a 2px cleanup band" from the flag value
        # and then appended a reason saying the band had been DROPPED -- one
        # sentence contradicting the next, which is how a log stops being read.
        print(f"SOURCE ALPHA HONOURED. {source_alpha_scope_reasons[0]}. "
              f"Pass --ignore-source-alpha to remove by colour across the whole frame anyway.",
              file=sys.stderr)

    if any_source_transparency:
        print("Preserved the source's own pre-existing transparent pixels "
              "in the output (forced transparent regardless of this "
              "script's background-color detection).", file=sys.stderr)

    # Edge cleanup: shave a couple of pixels off the opaque/transparent
    # boundary whenever feathering produced the alpha. This is NOT a
    # size-optimization step (unlike the crop/resize/stride bundled into
    # --compress tiers below) -- it's a correctness fix for the feathering
    # math itself, so it applies unconditionally rather than being tier-
    # gated. Background color-unmixing (de-fringing) doesn't perfectly
    # recover the true foreground color on every antialiased boundary
    # pixel; empirically, on real test art, the single outermost ring of
    # kept pixels frequently lands a visibly-wrong, lighter/tinted color
    # (e.g. a navy outline's edge pixel coming out as a pale blue-gray
    # rather than true navy) even though its alpha was correctly resolved
    # to opaque. A single pixel of erosion isn't always enough to clear
    # this -- confirmed on a real file where the mis-colored ring was
    # still present after 1px and gone after 2px, with negligible impact
    # on fine details (~1% of opaque pixels removed on that test case,
    # far smaller than any real feature like a gear tooth or small dot).
    # Only applies when feathering is active (args.feather) since the
    # non-feathered hard-cutoff path doesn't have this fringe-color issue
    # in the first place.
    if args.feather:
        h0, w0 = alpha_frames[0].shape
        if args.edge_cleanup_erosion > 0 and min(h0, w0) < 200:
            print(f"WARNING: source canvas is small ({w0}x{h0}) and "
                  f"--edge-cleanup-erosion is {args.edge_cleanup_erosion}px "
                  f"(default 2). That's a FIXED pixel count, not scaled to "
                  f"resolution -- on a canvas this size it can be a large "
                  f"fraction of any fine detail (thin strokes, small dots), "
                  f"potentially eroding them away entirely rather than just "
                  f"cleaning up a 1-pixel fringe. Worth checking the preview "
                  f"closely for lost detail, and considering "
                  f"--edge-cleanup-erosion 1 or 0 if this source has fine "
                  f"linework.", file=sys.stderr)
        alpha_frames_pre_erosion = alpha_frames
        exempt_max = getattr(args, 'erosion_exempt_max_size', None)
        if getattr(args, 'erosion_exempt_transient', False):
            _tiny_for_cal = find_transient_removed_regions(
                alpha_frames, max_size=exempt_max if exempt_max else 500)
            print("erosion exemption by PERSISTENCE, not size: regions present in ~every "
                  "frame at a stable size are treated as design and eroded normally; only "
                  "incidental ones are exempt.", file=sys.stderr)
        else:
            _tiny_for_cal = (find_tiny_removed_regions(alpha_frames, exempt_max)
                             if exempt_max is not None and exempt_max > 0 else None)
        # ⚠️ A FOURTH consumer of the same wrong assumption, and it OVERRODE the guard
        # below. auto-erosion picks a level from a fringe-fraction curve -- how many
        # outer-ring pixels look background-coloured. On a source whose padding colour
        # is also its outline colour, the artwork's own outline reads as fringe, so the
        # curve keeps improving as the outline disappears. Measured on a 192x32 sprite:
        # the guard set erosion 0, the calibration read (0:1.0, 1:0.2448, 2:0.2985,
        # 3:0.2064) and chose 3, and 3px of erosion left 1,226 of 3,167 opaque pixels
        # (38.7%). The metric cannot succeed here -- it is measuring art and calling it
        # fringe -- so the honest move is to not run it, exactly as for --pixel-art.
        # ⚠️ `_src_has_partial_alpha` belongs in this guard too, and leaving it out cost
        # 6,844 pixels. The guard was keyed on the SCOPE engaging, but its own reasoning is
        # about the SOURCE carrying its own antialiasing -- and those are different sets.
        # `CODM BP Icon.png` has 2,917 partial-alpha pixels and the scope does NOT engage on
        # it. Once the source-alpha clamp stopped promoting that antialiasing to 255, the
        # calibration curve moved from (0:0.0885, 1:0.0, 2:0.0, 3:0.0) to
        # (0:0.2549, 1:0.1852, 2:0.0296, 3:0.0) -- because the metric counts pale
        # near-background pixels in the outer ring, and a restored antialiasing ramp IS pale
        # near-background pixels. It duly picked erosion 3 instead of 1 and shaved 6,844 real
        # pixels off the artwork. The metric was measuring the source's own soft edge and
        # calling it fringe, which is precisely the failure the message below describes.
        _erosion_metric_blind = _sa_engaged or _src_has_partial_alpha
        if _erosion_metric_blind and getattr(args, 'auto_erosion', False) and not args.pixel_art:
            print("erosion auto-calibration SKIPPED: "
                  + ("the source's own alpha defines the silhouette" if _sa_engaged
                     else "the source carries its own partial alpha (antialiasing, a fade or "
                          "a glow)")
                  + ", so the fringe metric would be measuring artwork. Its curve is "
                  "monotone in the wrong direction on such a source -- it improves as the "
                  "outline is eroded away. Pass --edge-cleanup-erosion explicitly to force a "
                  "level.", file=sys.stderr)
        if (getattr(args, 'auto_erosion', False) and not args.pixel_art
                and not _erosion_metric_blind):
            _cal_pal = build_art_palette(
                rgb_frames[::max(1, len(rgb_frames) // 8)], hex_to_rgb(args.bg_color))
            _cal_log = []
            _picked, _cal_table = calibrate_edge_cleanup_erosion(
                rgb_frames, alpha_frames, hex_to_rgb(args.bg_color), _cal_pal,
                tiny_masks=_tiny_for_cal, log=_cal_log)
            for _l in _cal_log:
                print(_l, file=sys.stderr)
            if diagnostics is not None:
                diagnostics['erosion_table'] = _cal_table
                diagnostics['erosion_picked'] = _picked
            if _picked is not None and _picked != args.edge_cleanup_erosion:
                print(f"auto: --edge-cleanup-erosion {args.edge_cleanup_erosion} -> {_picked}",
                      file=sys.stderr)
                args.edge_cleanup_erosion = _picked
        # ⚠️ process() works on a COPY of args, so anything resolved in here is
        # invisible to the caller. Report the value actually used through the
        # diagnostics sink -- auto_run escalates from it, and reading it off the
        # caller's args instead produced a re-render at the SAME erosion level
        # while reporting a different one (caught in testing).
        if diagnostics is not None:
            diagnostics['erosion_used'] = args.edge_cleanup_erosion
        if _tiny_for_cal is not None or (exempt_max is not None and exempt_max > 0):
            tiny_masks = (_tiny_for_cal if _tiny_for_cal is not None
                          else find_tiny_removed_regions(alpha_frames, exempt_max))
            alpha_frames = erode_alpha_edge_exempting_tiny_regions(
                alpha_frames, args.edge_cleanup_erosion, tiny_masks
            )
        else:
            alpha_frames = erode_alpha_edge(alpha_frames, iterations=args.edge_cleanup_erosion)
        if args.edge_cleanup_erosion > 0:
            damage = check_erosion_damage(alpha_frames_pre_erosion, alpha_frames)
            if damage:
                print(f"WARNING: edge-cleanup erosion may have erased or "
                      f"badly shrunk {len(damage)} real detail(s) (not just "
                      f"fringe noise -- these were >=25px components before "
                      f"erosion). Examples:", file=sys.stderr)
                for d in damage[:5]:
                    print(f"  frame {d['frame']}: ~{d['component_size_px']}px "
                          f"component at bbox {d['bbox_xyxy']}, only "
                          f"{d['survival_fraction']*100:.0f}% survived. "
                          f"Consider --edge-cleanup-erosion 1 or 0.",
                          file=sys.stderr)
                if len(damage) > 5:
                    print(f"  ...and {len(damage) - 5} more.", file=sys.stderr)

    # Translucency regions, applied before --remove-region so a force-removal
    # inside one still wins.
    if getattr(args, 'translucent_region', None):
        H0, W0 = alpha_frames[0].shape
        _tmask = parse_protect_regions(args.translucent_region, (H0, W0))
        _before = sum(int((a >= 250).sum()) for a in alpha_frames)
        _tcol = hex_to_rgb(args.translucent_color or args.bg_color)
        alpha_frames = apply_translucent_regions(
            rgb_frames, alpha_frames, _tmask, args.translucent_alpha,
            _tcol, args.tolerance)
        _after = sum(int((a >= 250).sum()) for a in alpha_frames)
        _taken = _before - _after
        if _taken or args.translucent_alpha >= 1.0:
            # alpha 1.0 is a legitimate no-op (the level equals full opacity), so it is
            # reported plainly rather than warned about.
            print(f"--translucent-region: {_taken} pixels taken to "
                  f"{args.translucent_alpha:.0%} alpha across {len(alpha_frames)} frame(s).",
                  file=sys.stderr)
        else:
            # An explicitly requested region that changes NOTHING is the confidently-wrong
            # shape this project exists to remove: the run succeeds, the output looks
            # plausible, and the flag the user reached for did nothing. Measured on a real
            # fixture -- omitting --translucent-color makes the target default to the
            # BACKGROUND colour, which by construction is absent from the kept art, so the
            # whole feature silently no-ops.
            print(f"  WARNING: --translucent-region touched ZERO pixels, so this run is "
                  f"identical to one without it. Two things to check: the region is given in "
                  f"SOURCE coordinates (it is applied BEFORE --crop/--resize-max-dim, so "
                  f"measure it on the INPUT file), and only pixels within --tolerance "
                  f"{args.tolerance} of "
                  f"{'--translucent-color' if args.translucent_color else 'the background colour'}"
                  f" #{rgb_to_hex(_tcol)} are affected -- pass --translucent-color if the "
                  f"see-through material is not the background colour.", file=sys.stderr)

    # Force-remove regions (inverse of --protect-region), applied last so it
    # overrides whatever --protect-outline-color / --protect-region decided
    # -- see apply_remove_regions' docstring for the case this is for.
    if getattr(args, 'remove_region', None) or getattr(args, 'remove_region_track', None):
        H0, W0 = alpha_frames[0].shape
        if getattr(args, 'remove_region_track', None):
            _seed = parse_protect_regions(args.remove_region_track, (H0, W0))
            _tlog = []
            remove_mask, _treport = track_region_across_frames(
                rgb_frames, hex_to_rgb(args.bg_color), args.tolerance, _seed, log=_tlog)
            for _l in _tlog:
                print(_l, file=sys.stderr)
        else:
            remove_mask = parse_protect_regions(args.remove_region, (H0, W0))
        rgb_frames, alpha_frames = apply_remove_regions(
            rgb_frames, alpha_frames, remove_mask,
            feather_px=args.remove_region_feather)

    tier = args.compress  # None (plain background removal), 'optimize', 'medium', or 'heavy'

    # Cropping: explicit --crop, OR bundled automatically into any tier
    # (all three tiers include "crop transparent areas" as a base step).
    # Plain background removal with no tier does NOT crop by default
    # anymore -- the workflow default is now "just remove the background",
    # full stop; crop/resize/frame-stride/erosion are opt-in via a tier.
    do_crop = args.crop or (tier is not None)
    if do_crop:
        union_mask = np.zeros_like(alpha_frames[0], dtype=bool)
        for a in alpha_frames:
            union_mask |= (a > 0)
        ys, xs = np.where(union_mask)
        if len(ys) == 0:
            print("WARNING: every frame is fully transparent; skipping crop.",
                  file=sys.stderr)
        else:
            y0, y1 = ys.min(), ys.max() + 1
            x0, x1 = xs.min(), xs.max() + 1
            rgb_frames = [r[y0:y1, x0:x1] for r in rgb_frames]
            alpha_frames = [a[y0:y1, x0:x1] for a in alpha_frames]
            print(f"Cropped to transparent bounding box: "
                  f"{x0},{y0} -> {x1},{y1} "
                  f"({im0.size[0]}x{im0.size[1]} -> {x1-x0}x{y1-y0})",
                  file=sys.stderr)

    # Standalone --frame-stride: works with or without a tier. Without a
    # tier it's the only opt-in lever applied (matches the earlier
    # "do the frame stuff but don't do the compression" use case). With a
    # tier, an explicit --frame-stride overrides that tier's own default
    # stride (1 for 'optimize', 2 for 'medium'/'heavy') rather than
    # stacking with it.
    if tier is None and args.frame_stride and args.frame_stride > 1:
        avg_before = average_frame_delay(durations)
        rgb_frames, alpha_frames, durations = reduce_frame_count(
            rgb_frames, alpha_frames, durations, args.frame_stride)
        avg_after = average_frame_delay(durations)
        print(f"Frame-rate reduced (stride {args.frame_stride}): "
              f"{n_frames} -> {len(durations)} frames, total playback "
              f"length unchanged ({sum(durations)}ms), avg delay "
              f"{avg_before:.0f}ms -> {avg_after:.0f}ms.", file=sys.stderr)
        if avg_after > 120:
            print(f"WARNING: average frame delay after this stride is "
                  f"{avg_after:.0f}ms (~{1000/avg_after:.1f}fps) -- this is "
                  f"slow enough that dropped frames will likely read as "
                  f"visibly choppier motion, not just 'slightly less "
                  f"smooth'. Consider a smaller stride or verify the "
                  f"result before delivering.", file=sys.stderr)

    # Standalone --resize-max-dim: works with or without a tier, mirroring
    # --frame-stride's pattern. Without a tier it's an opt-in lever for an
    # arbitrary target that doesn't match either fixed tier size (e.g.
    # 128px for a platform that wants exactly that). With a tier, it
    _fmt = resolve_output_format(output_path, args)
    # overrides that tier's own resize target instead of stacking with it
    # (handled below via resize_override passed into apply_tier).
    if tier is None and args.resize_max_dim:
        h, w = alpha_frames[0].shape
        scale = fit_scale_for_max_dimension(w, h, args.resize_max_dim)
        if scale < 1.0:
            resample = Image.NEAREST if args.pixel_art else Image.LANCZOS
            # An 8-bit-alpha output must NOT be re-binarized or eroded here.
            # Confirmed bug, caught end-to-end: with the default binarize=True
            # a 128px emoji came back with 14 distinct alpha levels and 99.4% of
            # pixels fully opaque-or-transparent -- the recovered fade was
            # silently destroyed by the resize, and the file merely LOOKED
            # pleasingly small (97 KB) because the pulses were gone.
            # --recover-fade-alpha bypasses compute_alpha_mask entirely, so it
            # produces 8-bit alpha regardless of dither_mode -- test both.
            keeps_alpha = _fmt in EIGHT_BIT_ALPHA_FORMATS and (
                args.dither_mode == 'continuous'
                or getattr(args, 'recover_fade_alpha', False))
            rgb_frames, alpha_frames = resize_rgba_frames(
                rgb_frames, alpha_frames, scale, resample=resample,
                binarize=not keeps_alpha)
            new_h, new_w = alpha_frames[0].shape
            print(f"Resized to fit {args.resize_max_dim}px on the longer "
                  f"side: {w}x{h} -> {new_w}x{new_h}"
                  f"{' (nearest-neighbor, pixel-art mode)' if args.pixel_art else ''}"
                  f"{' (alpha-correct, premultiplied)' if keeps_alpha else ''}.",
                  file=sys.stderr)
            if args.pixel_art:
                print("Skipped post-resize erosion (pixel-art mode -- "
                      "nearest-neighbor resize has no fuzz to clean up).",
                      file=sys.stderr)
            elif keeps_alpha:
                print("Skipped post-resize erosion (8-bit alpha -- the resize "
                      "produced real partial alpha, not fuzz to trim).",
                      file=sys.stderr)
            else:
                alpha_frames = erode_alpha_edge(alpha_frames, iterations=1)
                print("Eroded 1px off the opaque edge (targets fuzz "
                      "reintroduced by the resize above).", file=sys.stderr)
        else:
            print(f"Already within {args.resize_max_dim}px on the longer "
                  f"side ({w}x{h}) -- no resize needed.", file=sys.stderr)

    # Named tier: bundles frame-stride + resize-to-fit + 1px edge erosion,
    # then (below, after rendering) the matching gifsicle settings.
    if tier is not None:
        stride_override = args.frame_stride  # None (unset) or an explicit value, 1 included
        resize_override = args.resize_max_dim if args.resize_max_dim else None
        tier_log = []
        rgb_frames, alpha_frames, durations = apply_tier(
            rgb_frames, alpha_frames, durations, tier,
            stride_override=stride_override, resize_override=resize_override,
            pixel_art=args.pixel_art, log=tier_log)
        for line in tier_log:
            print(line, file=sys.stderr)

    if getattr(args, 'square_pad', False):
        before = alpha_frames[0].shape
        rgb_frames, alpha_frames = square_pad_frames(
            rgb_frames, alpha_frames, hex_to_rgb(args.bg_color))
        print(f"Square-padded {before[1]}x{before[0]} -> "
              f"{alpha_frames[0].shape[1]}x{alpha_frames[0].shape[0]}", file=sys.stderr)
    # Refuse rather than write a file that truncates. This is checked on the FINAL alpha
    # planes, after every stride/resize/tier transform, because those can remove the blank
    # frame (--frame-stride may simply skip it) -- analyze()'s source-side prediction is
    # what steers --recommend BEFORE the render; this is the backstop that cannot be wrong.
    # The script already warned about the shortfall after the fact ("85 frames written from
    # 123 intended") and wrote the broken file anyway; a warning nobody reads is not a gate.
    if _fmt == 'gif' and not getattr(args, 'allow_truncating_gif', False):
        _blank_out = [i for i, a in enumerate(alpha_frames) if not (a > 0).any()]
        if _blank_out:
            raise SystemExit(
                f"ERROR: refusing to write {output_path!r} as a GIF. Frame(s) "
                f"{_blank_out[:6]}{' ...' if len(_blank_out) > 6 else ''} of {len(alpha_frames)} "
                f"came out entirely transparent (the subject leaves the canvas). Pillow's GIF "
                f"writer emits an unreadable block there and the file TRUNCATES at that frame -- "
                f"measured 85 of 123 frames on a real asset. Nothing has been written.\n"
                f"  Write .webp or .apng instead: different encoder, every frame kept, and true "
                f"8-bit alpha as a bonus.\n"
                f"  Pass --allow-truncating-gif to write the truncated GIF anyway.")
    if _fmt == 'apng':
        size_bytes = render_frames_to_apng(
            rgb_frames, alpha_frames, durations, loop, output_path)
        written = read_animation_timing(output_path)
        if len(rgb_frames) == 1:
            # A one-frame output is a still image. "timing not read back" is true
            # but reads as a failed verification of something that does not exist.
            timing = "1 frame (static image -- no animation timing to verify)"
        elif written is None:
            timing = (f"{len(rgb_frames)} frames intended; timing not read back "
                      f"(no reader available for this container)")
        else:
            n, total = written
            timing = (f"{n} frames, {total}ms total"
                      + ("" if total == sum(durations)
                         else f" -- WARNING: source was {sum(durations)}ms"))
    elif _fmt == 'avif':
        size_bytes = render_frames_to_avif(
            rgb_frames, alpha_frames, durations, loop, output_path,
            quality=args.avif_quality)
        # Read the written file back rather than restating what we intended to
        # write -- the SS13/SS16 footgun. If the reader cannot supply timing,
        # say so instead of asserting a number that cannot fail.
        written = read_animation_timing(output_path)
        if len(rgb_frames) == 1:
            # A one-frame output is a still image. "timing not read back" is true
            # but reads as a failed verification of something that does not exist.
            timing = "1 frame (static image -- no animation timing to verify)"
        elif written is None:
            timing = (f"{len(rgb_frames)} frames intended; timing not read back "
                      f"(no reader available for this container)")
        else:
            n, total = written
            timing = (f"{n} frames, {total}ms total"
                      + ("" if total == sum(durations)
                         else f" -- WARNING: source was {sum(durations)}ms"))
    elif _fmt == 'webp':
        size_bytes = render_frames_to_webp(
            rgb_frames, alpha_frames, durations, loop, output_path,
            lossless=not args.webp_lossy, quality=args.webp_quality,
            method=args.webp_method)
        written = read_webp_durations(output_path)
        if written is None:
            timing = (f"{len(rgb_frames)} frames; timing not verified "
                      f"(webpmux not available to read it back)")
        else:
            timing = (f"{len(written)} frames, {sum(written)}ms total"
                      + ("" if sum(written) == sum(durations)
                         else f" -- WARNING: source was {sum(durations)}ms"))
    else:
        size_bytes = render_frames_to_gif(rgb_frames, alpha_frames, durations, loop, output_path,
                                           quantizer=args.quantizer)
        timing = describe_written_timing(output_path, durations)
    out_w, out_h = alpha_frames[0].shape[1], alpha_frames[0].shape[0]
    print(f"Saved {output_path} ({timing})", file=sys.stderr)
    print(f"Output: {out_w}x{out_h}, {size_bytes/1024:.1f} KB", file=sys.stderr)

    # gifsicle pass matching the tier. No tier at all = no gifsicle either
    # -- the default is now genuinely "just remove the background" with no
    # extra processing of any kind, per the current workflow design. (An
    # explicit --no-gifsicle-optimize is a no-op in that case; kept only so
    # old invocations don't error out.)
    if tier is not None:
        gifsicle_level = TIER_SPECS[tier]['gifsicle_level']
        if ensure_gifsicle():
            if gifsicle_optimize(output_path, gifsicle_level):
                new_size = os.path.getsize(output_path)
                print(f"gifsicle ({gifsicle_level}): {size_bytes/1024:.1f} KB -> "
                      f"{new_size/1024:.1f} KB", file=sys.stderr)
        else:
            print(f"WARNING: '{tier}' tier requested but gifsicle isn't "
                  f"available in this environment (tried `apt-get install "
                  f"-y gifsicle`, no luck) -- delivering with the "
                  f"frame-stride/resize/erosion steps applied but WITHOUT "
                  f"the gifsicle encoding pass, so the size reduction will "
                  f"be smaller than normal for this tier.", file=sys.stderr)

    if args.target_kb and _fmt in EIGHT_BIT_ALPHA_FORMATS:
        final_size = os.path.getsize(output_path)
        if final_size / 1024 <= args.target_kb:
            print(f"Already under the {args.target_kb} KB target -- no further "
                  f"optimization needed.", file=sys.stderr)
        else:
            print(f"Over the {args.target_kb} KB target -- fitting (quality, then "
                  f"resolution, then frames)...", file=sys.stderr)
            fit_log = []
            size_bytes, hit = fit_to_target_bytes(
                rgb_frames, alpha_frames, durations, loop, output_path,
                args.target_kb, _fmt, args, log=fit_log)
            for line in fit_log:
                print(line, file=sys.stderr)
            print(f"Final: {os.path.getsize(output_path)/1024:.1f} KB "
                  f"(saved over {output_path})", file=sys.stderr)
    elif args.target_kb:
        final_size = os.path.getsize(output_path)
        if final_size / 1024 <= args.target_kb:
            print(f"Already under the {args.target_kb} KB target — no further "
                  f"optimization needed.", file=sys.stderr)
        else:
            print(f"Over the {args.target_kb} KB target — optimizing "
                  f"(walking optimize -> medium -> heavy tiers, then "
                  f"escalating stride/scale beyond heavy if still needed)...",
                  file=sys.stderr)
            result = optimize_to_target(rgb_frames, alpha_frames, durations, loop,
                                         output_path, args.target_kb,
                                         quantizer=args.quantizer, pixel_art=args.pixel_art)
            for a in result['attempts']:
                print(f"  tried {a['lever']}={a['value']}: {a['size_kb']} KB", file=sys.stderr)
            if result['hit_target']:
                print(f"Hit target: {result['final_size_kb']} KB <= {args.target_kb} KB "
                      f"(saved over {output_path})", file=sys.stderr)
            else:
                print(f"Could not fully reach {args.target_kb} KB; best achieved was "
                      f"{result['final_size_kb']} KB (saved over {output_path}). "
                      f"The source content may just be too complex/long for this "
                      f"target without a manual reduction in scope (e.g. trimming "
                      f"frames).", file=sys.stderr)

    if args.preview:
        preview_im = build_preview(rgb_frames, alpha_frames)
        preview_im.save(args.preview)
        print(f"Saved preview contact sheet to {args.preview}", file=sys.stderr)


class _PrefixedStream:
    """Wraps a stream, prepending a prefix to every line written to it."""
    def __init__(self, stream, prefix):
        self.stream = stream
        self.prefix = prefix
        self._at_line_start = True

    def write(self, s):
        for line in s.splitlines(keepends=True):
            if self._at_line_start and line.strip('\n'):
                self.stream.write(self.prefix)
            self.stream.write(line)
            self._at_line_start = line.endswith('\n')

    def flush(self):
        self.stream.flush()


@contextlib.contextmanager
def _prefixed_stderr(prefix):
    """
    Temporarily prefix every stderr line with `prefix`. Used by --batch so
    process()'s internal prints (Cropped/Resized/WARNING/Saved/etc, none of
    which know they're running inside a batch) are attributable to the
    right file at a glance in a long multi-file log, instead of all
    reading identically and only distinguishable by which block of output
    they happen to fall under.
    """
    old = sys.stderr
    sys.stderr = _PrefixedStream(old, prefix)
    try:
        yield
    finally:
        sys.stderr = old


def run_batch(args, arg_parser):
    """
    Process multiple GIFs from a JSON manifest (see --batch's help text for
    the format). Shared settings come from whatever else was passed on the
    command line alongside --batch (e.g. --compress, --edge-cleanup-erosion,
    --target-kb); each manifest entry can override any of those plus must
    supply its own "input"/"output" and typically its own
    "protect_outline_color"/"bg_color" (these usually differ art to art,
    which is the whole reason this isn't just "run the same flags on N
    files" -- most real batches share quality/size settings but NOT color
    settings across files).

    One job failing doesn't abort the rest -- each is wrapped individually,
    errors are collected and reported in the final summary table so a typo
    in file #3 doesn't waste the work already done on files #1-2 and #4-10.
    """
    try:
        with open(args.batch) as f:
            jobs = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        arg_parser.error(f"Could not read/parse --batch manifest {args.batch}: {e}")
        return

    if not isinstance(jobs, list) or not jobs:
        arg_parser.error(f"--batch manifest {args.batch} must be a non-empty JSON list")
        return

    results = []
    for idx, job in enumerate(jobs):
        job_input = job.get('input')
        job_output = job.get('output')
        label = job_input or f"job #{idx + 1}"
        if not job_input or not job_output:
            print(f"[{idx + 1}/{len(jobs)}] SKIPPED {label}: manifest entry "
                  f"needs both \"input\" and \"output\".", file=sys.stderr)
            results.append({'input': job_input, 'output': job_output,
                             'status': 'skipped', 'reason': 'missing input/output'})
            continue

        print(f"[{idx + 1}/{len(jobs)}] Processing {job_input} -> {job_output} ...",
              file=sys.stderr)
        try:
            job_args = copy.deepcopy(args)
            for key, value in job.items():
                if key in ('input', 'output'):
                    continue
                if not hasattr(job_args, key):
                    print(f"  WARNING: unknown manifest key '{key}' for "
                          f"{job_input}, ignoring.", file=sys.stderr)
                    continue
                setattr(job_args, key, value)
            apply_pixel_art_preset(job_args)

            if job_args.protect_outline_color and job_args.protect_region:
                raise ValueError("manifest entry sets both protect_outline_color "
                                  "and protect_region -- use only one")

            job_label = os.path.basename(job_input)
            with _prefixed_stderr(f"  [{job_label}] "):
                if not job_args.bg_color:
                    im = Image.open(job_input)
                    rgb0 = np.array(im.convert('RGB'))
                    job_args.bg_color = rgb_to_hex(detect_bg_color(rgb0))
                    print(f"Auto-detected background color: #{job_args.bg_color}",
                          file=sys.stderr)

                process(job_input, job_output, job_args)
            size_kb = os.path.getsize(job_output) / 1024
            results.append({'input': job_input, 'output': job_output,
                             'status': 'ok', 'size_kb': round(size_kb, 1)})
        except Exception as e:
            print(f"  ERROR processing {job_input}: {e}", file=sys.stderr)
            results.append({'input': job_input, 'output': job_output,
                             'status': 'error', 'reason': str(e)})

    print("\n=== Batch summary ===", file=sys.stderr)
    ok_count = sum(1 for r in results if r['status'] == 'ok')
    for r in results:
        if r['status'] == 'ok':
            print(f"  OK      {r['input']} -> {r['output']} ({r['size_kb']} KB)",
                  file=sys.stderr)
        elif r['status'] == 'skipped':
            print(f"  SKIPPED {r.get('input')}: {r['reason']}", file=sys.stderr)
        else:
            print(f"  ERROR   {r['input']}: {r['reason']}", file=sys.stderr)
    print(f"{ok_count}/{len(results)} succeeded.", file=sys.stderr)


def apply_pixel_art_preset(args, argv=None):
    """
    If --pixel-art is set, force the settings it bundles (see --pixel-art's
    help text for why each one matters). Mutates `args` in place. Called
    both on the top-level parsed args (for the direct process() path) and
    per-job inside run_batch (so a manifest entry's own "pixel_art": true
    override cascades correctly too, not just a top-level flag) -- a
    manifest job setting pixel_art without this would only get the literal
    key set, not the feather/erosion consequences that make it useful.
    """
    if getattr(args, 'pixel_art', False):
        # Explicit flags win, and we SAY so -- the same contract --auto already
        # implements via typed_option_names(). This preset used to overwrite an
        # explicitly typed --edge-cleanup-erosion with 0 silently, so the script
        # had two mechanisms that disagreed about who wins and one of them said
        # nothing. Safe direction, wrong principle.
        typed = typed_option_names(argv)
        if 'feather' not in typed and 'no_feather' not in typed:
            args.feather = False
        if 'edge_cleanup_erosion' not in typed:
            args.edge_cleanup_erosion = 0
        elif args.edge_cleanup_erosion != 0:
            print(f"--pixel-art would set --edge-cleanup-erosion 0, but you passed "
                  f"{args.edge_cleanup_erosion} explicitly, so that wins. Erosion is "
                  f"destructive on hard-edged art (measured: 0% survival on a 31px "
                  f"shape, references/lessons.md SS4) -- drop the flag unless you "
                  f"mean it.", file=sys.stderr)


def typed_option_names(argv=None):
    """
    The long-option names the user ACTUALLY typed, as attribute names.

    argparse records no provenance, so comparing a parsed value against the
    default cannot tell "user passed the default explicitly" from "user passed
    nothing". Any feature that promises explicit flags win has to read argv.
    """
    out = set()
    for tok in (sys.argv[1:] if argv is None else argv):
        name = tok.split('=', 1)[0]
        if name.startswith('--'):
            out.add(name[2:].replace('-', '_'))
    return out


def post_render_fringe_check(input_path, output_path, tolerance=15):
    """
    Re-measure the fringe metric on the ENCODED file, not on the in-memory
    frames the calibration used.

    These can genuinely disagree, which is the whole reason to look twice: GIF
    palette quantization can snap an edge pixel onto a different palette entry
    and merge identical frames, and a lossy WebP/AVIF can shift edge colours.
    A calibration done before the encoder runs cannot see any of that.

    Returns the mean fraction, or None if it could not be measured.
    """
    try:
        in_rgb, _, _ = load_animation_rgba_frames(input_path)
        out_rgb, out_alpha, _ = load_animation_rgba_frames(output_path)
    except Exception:
        return None
    if not in_rgb or not out_rgb:
        return None
    bg = detect_bg_color(in_rgb[0])
    pal = build_art_palette(in_rgb[::max(1, len(in_rgb) // 8)], bg)
    vals = [v for rgb, al in zip(out_rgb, out_alpha)
            if (v := measure_outer_ring_background_fraction(rgb, al, bg, pal)) is not None]
    return round(float(np.mean(vals)), 4) if vals else None


def auto_run(input_path, output_path, args, parser):
    """
    TWO PASSES, not a loop: analyse -> recommend -> render -> re-verify the
    RENDERED file -> at most ONE corrective re-render.

    ⚠️ There is deliberately no iteration construct here. Worst case is two
    renders, bounded by the code's shape rather than by a counter, so there is
    no counter that could fail to increment and no runaway. Two is the right
    number for a reason, not out of caution:
      * Pass 1 already corrects everything predictable from the source, and the
        erosion calibration is EXHAUSTIVE over its candidate set -- it measures
        all of them rather than stepping toward an answer, so iterating it
        would add nothing.
      * Pass 2 exists for exactly one thing the first pass structurally cannot
        see: the encoder. Palette quantization and lossy edge shifts are a
        single discrete effect, not something that compounds.
      * There is no third class of error a third pass would address; it would
        re-measure the same encoder on the same input and learn nothing new.

    If anyone ever does turn this into a real loop, it MUST also carry: an
    explicit iteration cap, the keep-the-better-render rule implemented below
    (each pass can make things worse), and a monotonic-progress check, since
    escalating erosion has diminishing returns and eventually destroys artwork.

    Harkirat's framing, and the reason this exists: the manual tweaks were only
    ever an investigation layer, so anything learned there belongs in the script
    as something it can derive itself. --recommend already reasons about the
    SOURCE; this adds the second half, reasoning about the RESULT.

    Explicit flags always win. A recommended flag is applied only where the user
    left that option at its default, so --auto never silently overrides a
    deliberate choice -- it fills in the ones nobody expressed an opinion about.
    """
    print("=== AUTO 1/3: analysing source ===", file=sys.stderr)
    rec = recommend(input_path, tolerance=args.tolerance)
    if rec.get('not_applicable_reason'):
        raise SystemExit("ERROR: --auto has nothing to do here, and doing it anyway would "
                         "destroy the image.\n  " + rec['not_applicable_reason'])
    rec_tokens = shlex.split(rec['suggested_command'])[4:]

    base = parser.parse_args([input_path, output_path])
    rec_ns = parser.parse_args([input_path, output_path] + rec_tokens)

    # Which options did the user ACTUALLY type? Comparing against the default
    # is not good enough: a user who explicitly passes the default value is
    # indistinguishable from one who passed nothing, and --auto would then
    # override a deliberate choice while claiming explicit flags always win.
    # argparse keeps no provenance, so read it off argv directly.
    _typed = typed_option_names()

    # Flags that the user's CHOSEN CONTAINER cannot honour must not be applied,
    # however sound the recommendation. --recover-fade-alpha is correct advice on
    # a faded asset AND exits with an error on a .gif output, so applying it to a
    # gif run turns --auto into a crash. Caught by the determinism gate on
    # 2026-08-18, immediately after --recover-fade-alpha started being
    # recommended: --auto had produced no file at all on every faded asset
    # written to .gif. The format conflict is still reported below -- the user is
    # told the container is wrong; they are just not handed a traceback for it.
    _out_fmt_early = resolve_output_format(output_path, args)
    _incompatible = {'recover_fade_alpha'} if _out_fmt_early == 'gif' else set()

    applied, overridden = [], []
    skipped_for_format = []
    for k in vars(rec_ns):
        rv, dv, uv = getattr(rec_ns, k), getattr(base, k), getattr(args, k, None)
        if rv == dv:
            continue
        if k in _incompatible and k not in _typed:
            skipped_for_format.append(f"--{k.replace('_', '-')}")
            continue
        if k in _typed:
            if uv != rv:
                overridden.append(
                    f"--{k.replace('_', '-')}: recommended {rv}, you set {uv} -- keeping yours")
        elif uv == dv:
            setattr(args, k, rv)
            applied.append(f"--{k.replace('_', '-')} {rv}")
        elif uv != rv:
            overridden.append(
                f"--{k.replace('_', '-')}: recommended {rv}, you set {uv} -- keeping yours")
    for line in rec['evidence']:
        print("  evidence: " + line[:220].replace("\n", " "), file=sys.stderr)
    _recfmt = rec.get('recommended_format')
    print(f"  recommended format: {_recfmt}", file=sys.stderr)
    # The container is the single most consequential decision and --auto does
    # NOT make it -- the user named the output file. But proceeding silently
    # when the analysis says this asset cannot be represented in that container
    # would be the tool knowingly shipping a wrong result.
    _outfmt = resolve_output_format(output_path, args)
    if _recfmt == 'webp-or-avif' and _outfmt == 'gif':
        print("  ⚠️  FORMAT CONFLICT: this source has a translucent element that was "
              "flattened against the background, and GIF's 1-bit alpha CANNOT represent "
              "it -- the faded stages will render as opaque pale blobs or vanish, and no "
              "setting fixes that. You asked for a .gif, so that is what will be written. "
              "Re-run with a .webp or .avif output plus --recover-fade-alpha for a correct "
              "result (references/lessons.md SS16).", file=sys.stderr)
    if skipped_for_format:
        print(f"  NOT applying {' '.join(skipped_for_format)}: a .gif output cannot carry "
              f"partial transparency, so the flag would only error. See the format "
              f"conflict note above.", file=sys.stderr)
    print(f"  applying: {' '.join(applied) if applied else '(nothing beyond defaults)'}",
          file=sys.stderr)
    for line in overridden:
        print(f"  {line}", file=sys.stderr)

    # Do NOT re-enable calibration when the user typed an erosion value -- main()
    # already turned it off for exactly that reason, and unconditionally setting
    # it back here would silently override them (caught in testing: an explicit
    # --edge-cleanup-erosion 2 was still being recalibrated down to 1).
    args.auto_erosion = 'edge_cleanup_erosion' not in _typed
    diag = {}
    print("=== AUTO 2/3: rendering ===", file=sys.stderr)
    process(input_path, output_path, args, diagnostics=diag)

    print("=== AUTO 3/3: verifying the RENDERED file ===", file=sys.stderr)
    post = post_render_fringe_check(input_path, output_path, tolerance=args.tolerance)
    table = diag.get('erosion_table') or {}
    measured = {e: v for e, v in table.items() if v is not None}
    floor = min(measured.values()) if measured else None
    if post is None:
        print("  post-render fringe: not measurable on this output -- reporting "
              "unverified rather than assuming a pass.", file=sys.stderr)
        return
    print(f"  post-render fringe fraction: {post}"
          + (f" (pre-encode floor for this asset: {floor})" if floor is not None else ""),
          file=sys.stderr)
    # The comparison is against THIS asset's own pre-encode floor, never a
    # global constant -- the same reason calibrate_edge_cleanup_erosion exists.
    # 0.05 is not an absolute threshold -- it is a margin ABOVE THIS ASSET'S OWN
    # pre-encode floor, so the comparison stays within-asset (the whole point of
    # SS19). The size of the margin is calibrated: across five real assets the
    # largest benign encoder gap measured 0.0021, so 0.05 is ~24x the worst
    # observed agreement. Measured on flat vector icon art over white; an art
    # style far outside that corpus may warrant re-measuring.
    if floor is not None and post > floor + 0.05:
        _used = diag.get('erosion_used')
        if _used is None:
            _used = args.edge_cleanup_erosion or 0
        newe = _used + 1
        print(f"  DISAGREEMENT: the encoded file is {post - floor:.4f} above the floor the "
              f"in-memory calibration predicted -- the encoder reintroduced edge pixels the "
              f"calibration could not see. Re-rendering ONCE at "
              f"--edge-cleanup-erosion {newe} (up from {_used}).", file=sys.stderr)
        # Preserve the first render. A correction is not guaranteed to help, and
        # overwriting a better file with a worse one and merely printing a warning
        # would leave the inferior result on disk -- the same failure shape as
        # reporting a pass that was never verified (SS13/SS17).
        _keep = output_path + '.pass1'
        shutil.copyfile(output_path, _keep)
        args.edge_cleanup_erosion = newe
        args.auto_erosion = False          # do not re-calibrate over the escalation
        try:
            process(input_path, output_path, args)
            post2 = post_render_fringe_check(input_path, output_path,
                                             tolerance=args.tolerance)
            if post2 is not None and post2 < post:
                print(f"  after correction: {post2} -- improved, keeping the corrected render.",
                      file=sys.stderr)
            else:
                shutil.copyfile(_keep, output_path)
                print(f"  after correction: {post2} -- NOT an improvement over {post}. "
                      f"Reverted: the file on disk is the FIRST render "
                      f"(--edge-cleanup-erosion {_used}). The encoder disagreement is "
                      f"real but more erosion is not the remedy; inspect this asset by hand.",
                      file=sys.stderr)
        finally:
            if os.path.exists(_keep):
                os.remove(_keep)
    else:
        print("  the rendered file agrees with the calibration -- no correction needed.",
              file=sys.stderr)

    # Fringe is only one of the things that can be wrong. For a GIF output the
    # full verify() is available and free, and it covers the duration/frame-count
    # class that SS17 was -- so report all of it rather than implying that a clean
    # fringe reading means a clean file.
    # Run the FULL verify for every container, not only GIF. The note this
    # replaced said the leftover-background and protected-coverage checks were
    # "still 1-bit assumptions" -- that stopped being true when they were made
    # partial-alpha aware (leftover counts only alpha>=250 background-coloured
    # pixels; the fringe metric looks at the outermost near-opaque ring), but the
    # GIF-only gate around the call site was never lifted with them. The effect
    # was that WebP -- the format --recommend actively prefers -- got the
    # weakest self-check of any output this tool writes, including the
    # zero-coverage warning that exists to catch a wholly unprotected region.
    try:
        _v = verify(input_path, output_path, tolerance=args.tolerance)
        _lb = _v.get('leftover_background_opaque_px', {})
        _tm = _v.get('timing', {}) or {}
        print(f"  full verify -- leftover background (worst frame): "
              f"{_lb.get('max_per_frame')}", file=sys.stderr)
        _pc = [p for p in (_v.get('protected_region_coverage') or [])
               if p.get('mean_opacity_fraction') is not None]
        if _pc:
            _worst = min(_pc, key=lambda x: x['mean_opacity_fraction'])
            print(f"  full verify -- worst protected-region coverage: "
                  f"{_worst['mean_opacity_fraction']}", file=sys.stderr)
        if _tm:
            print(f"  full verify -- timing: {_tm}", file=sys.stderr)
        # An autonomous run is the only reader of this. SS28.13's survival check is worthless if it
        # sits in a JSON field nobody prints -- the same reason SS26.7 exists.
        if _v.get('opaque_survival_warning'):
            print(f"  full verify -- ART LOSS: {_v['opaque_survival_warning']}", file=sys.stderr)
        elif _v.get('opaque_survival_vs_transparent_source') is not None:
            print(f"  full verify -- opaque artwork surviving from the transparent source: "
                  f"{_v['opaque_survival_vs_transparent_source']:.1%}", file=sys.stderr)
        if _v.get('output_is_empty'):
            print(f"  full verify -- {_v['output_is_empty']}", file=sys.stderr)
    except SystemExit:
        pass
    except Exception as _exc:
        print(f"  full verify unavailable ({_exc}) -- reporting the fringe check only, "
              f"not a clean bill of health.", file=sys.stderr)



def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('input_gif', nargs='?', default=None,
                    help='Not required when using --batch')
    p.add_argument('output_gif', nargs='?', default=None,
                    help='Not required when using --analyze or --batch')
    p.add_argument('--batch', default=None,
                    help='Path to a JSON manifest for processing multiple '
                         'GIFs in one invocation: a list of objects, each '
                         'with at least "input" and "output" paths, plus '
                         'any per-file overrides (matching this script\'s '
                         'own flag names with underscores instead of '
                         'dashes, e.g. "protect_outline_color", '
                         '"bg_color", "protect_region"). Any flag NOT '
                         'given in a job entry falls back to whatever was '
                         'passed on the command line alongside --batch --'
                         ' the intended pattern is per-file color/'
                         'protection settings in the manifest (these '
                         'usually differ art to art) plus shared quality/'
                         'size settings on the command line (e.g. '
                         '--compress optimize --edge-cleanup-erosion 1, '
                         'these are usually consistent across a batch). '
                         'Example manifest:\n'
                         '[\n'
                         '  {"input": "seal.gif", "output": "seal_out.gif", '
                         '"protect_outline_color": "1a2b3c"},\n'
                         '  {"input": "star.gif", "output": "star_out.gif"}\n'
                         ']\n'
                         'One file failing (bad path, parse error, etc.) '
                         'prints an error for that entry and continues '
                         'with the rest rather than aborting the whole '
                         'batch; a summary table prints at the end.')
    p.add_argument('--bg-color', default=None,
                    help='Hex color of the background to remove, e.g. ffffff. '
                         'If omitted, auto-detected from the corner pixels of frame 0.')
    p.add_argument('--tolerance', type=int, default=15,
                    help='Per-channel tolerance for matching bg-color (default 15)')
    p.add_argument('--protect-outline-color', default=None,
                    help='Hex color of a closed outline; everything enclosed by it '
                         'is protected from removal, e.g. 002a75. Accepts a '
                         'comma-separated list (e.g. c8dcf0,8cb4f0) to protect '
                         'multiple independently-outlined regions in the same '
                         'image -- each color\'s enclosed area is filled and the '
                         'results unioned.')
    p.add_argument('--outline-tolerance', type=int, default=40,
                    help='Per-channel tolerance for matching the outline color (default 40)')
    p.add_argument('--protect-region', default=None,
                    help='Manual protected region: circle:cx,cy,r or '
                         'rect:x,y,w,h. Accepts multiple regions separated '
                         'by `;` (e.g. circle:100,200,50;rect:10,10,20,20) '
                         '-- `;` rather than `,` between regions since `,` '
                         'already separates each region\'s own numeric '
                         'fields. Each region\'s mask is unioned.')
    p.add_argument('--remove-region', default=None,
                    help='Manual FORCE-REMOVE region (inverse of '
                         '--protect-region): circle:cx,cy,r or rect:x,y,w,h, '
                         'same multi-region `;`-joined syntax. Overrides '
                         '--protect-outline-color / --protect-region inside '
                         'this region regardless of what they decided -- for '
                         'carving out a small feature (e.g. a decorative '
                         'hole/grommet) that shares its enclosing outline '
                         'color with something else you want kept, so '
                         'outline-color protection alone can\'t tell them '
                         'apart. Edge is feathered and defringed against the '
                         'LOCAL surrounding color (sampled fresh per frame), '
                         'not left as a stale color at partial alpha -- see '
                         '--remove-region-feather. Static across all frames, '
                         'same caution as --protect-region: do not use this '
                         'for a target that moves/resizes across frames '
                         '(tumbling/rotating content) without re-deriving '
                         'the mask per frame yourself first.')
    p.add_argument('--remove-region-track', default=None,
                    help='Like --remove-region, but the spec is a SEED on frame 0 and the '
                         'region is then FOLLOWED across the animation instead of staying '
                         'put. For a hole that moves and cannot be told from same-coloured '
                         'decoration by size or aspect -- the case --remove-region cannot '
                         'reach (a static circle missed the true target in 76%% of frames on '
                         'a real tumbling asset) and --tumble-safe\'s geometric gate cannot '
                         'either. Identity is carried by CONTINUITY, not by any property '
                         'that separates the target from its twin: only one candidate is '
                         'where the seeded one just was. If no candidate passes the '
                         'continuity gate on a frame, the mask is carried forward along the '
                         'last motion vector and those frame indices are PRINTED -- a '
                         'tracker that loses its target silently is worse than one that '
                         'says so. Same spec syntax as --remove-region.')
    p.add_argument('--remove-region-feather', type=float, default=1.5,
                    help='Feather width in px for --remove-region\'s edge '
                         'taper (default 1.5).')
    p.add_argument('--no-feather', dest='feather', action='store_false',
                    help='Disable edge feathering/de-fringing; use a hard '
                         'color-distance cutoff (old behavior, choppier edges).')
    p.add_argument('--pixel-art', action='store_true', default=False,
                    help='Convenience preset for pixel art / any hard-edged, '
                         'non-antialiased source (as opposed to this '
                         'script\'s primary target of antialiased vector '
                         'icon/sticker art). Equivalent to --no-feather '
                         '--edge-cleanup-erosion 0 plus nearest-neighbor '
                         '(instead of LANCZOS) resampling for any resize, '
                         'all bundled into one flag. Confirmed necessary, '
                         'not just nice-to-have: this script\'s DEFAULT '
                         'settings, run against a real synthetic pixel-art '
                         'test file, eroded a 31px shape down to ZERO '
                         'surviving pixels (0% survival) -- there was no '
                         'antialiasing fringe for feathering/erosion to '
                         'clean up, just real art sitting exactly at the '
                         'erosion boundary with nothing to spare, and '
                         'LANCZOS resampling would have softened perfectly '
                         'hard pixel edges regardless. Check '
                         '--analyze\'s "edge_hardness" field first (or eyeball '
                         'the source at high zoom) if unsure -- a ratio '
                         'under ~0.5 means hard-edged, use this flag; a '
                         'real vector icon typically measures 4-17+.')
    p.add_argument('--feather-band-multiplier', type=float, default=4.0,
                    help='Width of the edge transition band, as a multiple of '
                         '--tolerance (default 4.0). Larger = softer/wider edge.')
    p.add_argument('--edge-cleanup-erosion', type=int, default=None,
                    help='Pixels of erosion applied to the opaque/transparent '
                         'boundary to clean up feather-fringe artifacts -- '
                         'background color-unmixing doesn\'t perfectly '
                         'recover the true foreground color on every '
                         'antialiased edge pixel, so the outermost ring can '
                         'come out a visibly wrong, lighter/tinted color '
                         'even when its alpha resolved correctly. Applied '
                         'unconditionally whenever feathering is on '
                         '(default 2; empirically the minimum that fully '
                         'clears the mis-colored ring on real test art). '
                         'Set to 0 to disable if the source has no such '
                         'fringing and you want to preserve every pixel.')
    p.add_argument('--resize-max-dim', type=int, default=None,
                    help='Resize to fit N pixels on the longer side '
                         '(preserving aspect ratio, only ever downscaling). '
                         'Works standalone with no --compress tier, for an '
                         'arbitrary target that doesn\'t match either fixed '
                         'tier size (512 for optimize/medium, 256 for '
                         'heavy) -- e.g. a platform that wants exactly '
                         '128px. Combined with a tier, an explicit '
                         '--resize-max-dim overrides that tier\'s own '
                         'resize target rather than stacking with it. '
                         'Always followed by a 1px cleanup erosion pass '
                         '(same reasoning as the tiers\' own post-resize '
                         'erosion) to remove fuzz the resize reintroduces.')
    p.add_argument('--crop', action='store_true', default=False,
                    help='Crop to the transparent bounding box. Off by '
                         'default for plain background removal; '
                         'automatically included when any --compress tier '
                         'is used, regardless of this flag.')
    p.set_defaults(feather=True)
    p.add_argument('--frame-stride', type=int, default=None,
                    help='Keep every Nth frame, folding dropped frames\' '
                         'durations into the kept frame so total playback '
                         'length is unchanged (default: unset, meaning no '
                         'stride standalone / whatever the tier specifies '
                         'when one is used). Works standalone (with no '
                         '--compress tier) or combined with one, where an '
                         'explicit value -- including 1, to force keeping '
                         'every frame -- overrides that tier\'s own default '
                         'stride (1 for "optimize", 2 for "medium"/"heavy"). '
                         'This is the one place `1` is NOT the same as '
                         'leaving the flag unset: unset defers to the '
                         'tier, `--frame-stride 1` explicitly forces no '
                         'frame-dropping even under a tier that would '
                         'otherwise drop frames (e.g. `--compress medium '
                         '--frame-stride 1` keeps medium\'s color/lossy '
                         'treatment but every original frame). A warning '
                         'prints if the resulting average delay gets slow '
                         'enough to look choppy (>120ms/frame).')
    p.add_argument('--compress', choices=['optimize', 'medium', 'heavy'], default=None,
                    help='Apply a named optimization tier. All three '
                         'include: crop to transparent bounds, resize to '
                         'fit 512px on the longer side, 1px edge erosion, '
                         'and gifsicle -O3. "optimize" keeps every frame '
                         '(no frame-stride) -- it\'s a lossless/no-motion- '
                         'tradeoff tier. "medium" adds frame-stride 2 '
                         '(unless overridden by --frame-stride), '
                         '--lossy=30, a 200-color palette, and '
                         'Floyd-Steinberg dithering (the color cap exists '
                         'so dithering has any effect -- gifsicle only '
                         'dithers when colors are actually reduced). '
                         '"heavy" keeps frame-stride 2, adds --lossy=80, a '
                         '128-color palette with Floyd-Steinberg dithering, '
                         'and overrides the resize target down to 256px. '
                         'Not applied by default -- only on explicit '
                         'request, or via --target-kb\'s own search.')
    p.add_argument('--no-gifsicle-optimize', dest='gifsicle_optimize', action='store_false',
                    help='(Currently a no-op kept for backward '
                         'compatibility -- gifsicle only runs as part of a '
                         '--compress tier now, never unconditionally.)')
    p.set_defaults(gifsicle_optimize=True)
    p.add_argument('--quantizer', choices=['pil', 'pngquant'], default='pil',
                    help='Algorithm for building the shared master color '
                         'palette (see render_frames_to_gif\'s docstring). '
                         '\'pil\' (default) is validated as producing '
                         'SMALLER files on this skill\'s typical content '
                         '(flat vector icon/sticker art) despite pngquant '
                         'having lower quantization error in isolation -- '
                         'a real A/B test showed pngquant +4-7%% LARGER '
                         'output at every tier on real test art, likely '
                         'because it optimizes for perceptual accuracy '
                         'rather than GIF-LZW-friendly index repetition, '
                         'and flat icon art\'s handful of real design '
                         'colors are already losslessly preserved by '
                         'either quantizer within typical budgets. Use '
                         '\'pngquant\' as an explicit opt-in when visual '
                         'fidelity matters more than file size, or for '
                         'content with genuine gradients/soft shading '
                         '(more real colors competing for the budget, not '
                         'just antialiasing fringe) -- content this skill '
                         'hasn\'t been primarily validated against. Falls '
                         'back to \'pil\' with a warning if pngquant isn\'t '
                         'available or fails.')
    p.add_argument('--target-kb', type=float, default=None,
                    help='If the output exceeds this size in KB, iteratively '
                         'walk the optimize -> medium -> heavy tiers, then '
                         'escalate frame-stride/scale further within heavy\'s '
                         'settings as a last resort, until it fits (or '
                         'options run out).')
    p.add_argument('--tumble-safe', action='store_true', default=False,
                    help='Use for animated content whose foreground shape '
                         'rotates/translates significantly within the '
                         'canvas (a tumbling/falling/spinning icon), as '
                         'opposed to a mostly-static icon with only minor '
                         'internal motion. Switches background detection '
                         'from "any bg-colored region touching the canvas '
                         'border" to "only the single largest bg-colored '
                         'region" (see largest_bg_component_mask\'s '
                         'docstring for why the latter is safe and the '
                         'former isn\'t once the foreground itself can '
                         'graze the edge), and switches protection from '
                         '--protect-outline-color\'s per-frame fill-holes '
                         '(fragile under self-overlapping/rotating '
                         'geometry -- confirmed real failure, see SKILL.md) '
                         'to keeping everything that is not that single '
                         'largest region. Combine with '
                         '--keep-bg-blob-if-near to selectively remove '
                         'OTHER small bg-colored regions (e.g. real '
                         'holes/cutouts) while still protecting everything '
                         'else. Incompatible with --protect-outline-color '
                         'and --protect-region (those assume single-frame '
                         'enclosure geometry generalizes across frames, '
                         'which is exactly what breaks on this content '
                         'type) -- use --keep-bg-blob-if-near instead.')
    p.add_argument('--keep-bg-blob-if-near', default=None,
                    help='Only meaningful with --tumble-safe. '
                         'Comma-separated hex colors: a small bg-colored '
                         'region (other than the main background) is kept '
                         '(protected) only if it borders one of these '
                         'colors; otherwise it\'s treated as removable, '
                         'subject to --hole-size-range/--hole-max-aspect. '
                         'Identify these colors the same way outline-color '
                         'verification\'s manual fallback works: zoom into '
                         'a frame, sample pixels bordering the region you '
                         'want to KEEP vs. the region you want REMOVED, and '
                         'use whatever color reliably distinguishes them. '
                         'This is inherently per-asset -- there is no '
                         'universal value.')
    p.add_argument('--hole-size-range', default='50,2000',
                    help='Only meaningful with --keep-bg-blob-if-near. '
                         '"min,max" pixel-count range for a bg-colored '
                         'region to be eligible for removal. Narrow this '
                         'to the real target\'s measured size across '
                         'several frames (default is deliberately generous '
                         'and, alone, is NOT enough to avoid false '
                         'positives on real art -- see '
                         'build_tumble_safe_protected_mask\'s docstring).')
    p.add_argument('--hole-max-aspect', type=float, default=3.0,
                    help='Only meaningful with --keep-bg-blob-if-near. '
                         'Maximum bounding-box aspect ratio '
                         '(max(w,h)/min(w,h)) for a bg-colored region to '
                         'be eligible for removal -- excludes thin slivers '
                         '(fold lines, incidental antialiasing islands) '
                         'that are small enough to fall in --hole-size-'
                         'range by coincidence but are the wrong shape to '
                         'be the real target.')
    p.add_argument('--protect-band-only', type=int, default=None,
                    help='Pixel width of the transition ring to feather/ '
                         'defringe around the removable core (background '
                         'union any --tumble-safe holes), with EVERYTHING '
                         'else in the frame force-protected regardless of '
                         'its own color -- the inverse of the normal '
                         'allowlist-style protected mask. Use when the '
                         'source art has ANY solid design color (a pale '
                         'tint, a soft shadow/glow shape, a light gradient '
                         'fill) that might coincidentally sit within the '
                         'feathering transition band of the background '
                         'color -- confirmed real case where an allowlist '
                         'protected mask let exactly this happen (see '
                         'build_band_only_removal_mask\'s docstring). '
                         '4px was sufficient on the motivating case; widen '
                         'if fringe survives, matching the real '
                         'antialiasing blend width in the source art.')
    p.add_argument('--square-pad', action='store_true',
                    help='Pad the canvas to a square with transparent margin '
                         '(centred) before encoding. Emoji/sticker slots are '
                         'square; pairs naturally with --crop --target-kb.')
    p.add_argument('--recover-fade-alpha', action='store_true',
                    help='Recover partial transparency that was FLATTENED against '
                         'the background when the source was authored -- a fading '
                         'glow/sparkle/pulse that GIF had to bake into progressively '
                         'paler versions of the background colour. Works by unmixing '
                         'each pixel against the art\'s own flat palette, so the '
                         'recovered alpha is arithmetic rather than an estimate. '
                         'Requires .webp or .avif output. Assumes flat-colour vector '
                         'art; warns if the content does not look like that. See '
                         'references/lessons.md SS16.')
    p.add_argument('--fade-color', default=None,
                    help='Comma-separated hex colour(s) to TREAT as the fading '
                         'translucent element, overriding --recover-fade-alpha\'s '
                         'auto-detection. Use when a fade is too brief or too small '
                         'to be detected automatically, or when a solid colour is '
                         'wrongly detected as fading.')
    p.add_argument('--avif-quality', type=int, default=70,
                    help='AVIF quality 0-100 (default 70). AVIF fits roughly 3x the '
                         'frames of WebP under the same byte cap at comparable '
                         'apparent quality -- measured 124 frames at 244 KB where '
                         'WebP needed to drop to 42.')
    p.add_argument('--translucent-region', default=None,
                    help='Make a named region SEE-THROUGH rather than opaque or '
                         'removed -- glass, a transparent bag, a window. Same '
                         'spec syntax as --protect-region '
                         '(`circle:cx,cy,r` or `rect:x,y,w,h`, `;`-separated). '
                         'Needed because the third role is not recoverable from '
                         'the pixels: on the asset this was built for, the '
                         'see-through bag interior and the opaque body are '
                         'byte-identical white AND both fully enclosed pockets '
                         'bounded by the same outline, so neither colour nor '
                         'connectivity separates them (references/lessons.md '
                         'SS27). Requires a .webp/.avif/.apng output. Only '
                         'lowers alpha that is already opaque, so an '
                         'antialiasing ramp inside the region keeps its own.')
    p.add_argument('--translucent-color', default=None,
                    help='Which colour inside --translucent-region becomes '
                         'see-through, as hex. Defaults to the background '
                         'colour, which is the glass case: the material is the '
                         'same colour as the background and its CONTENTS are '
                         'not, so restricting by colour is what stops a hand-'
                         'drawn rectangle from also making the contents '
                         'transparent.')
    p.add_argument('--translucent-alpha', type=float, default=0.35,
                    help='Alpha level --translucent-region applies, 0.0-1.0 '
                         '(default 0.35).')
    p.add_argument('--format', choices=['auto', 'gif', 'webp', 'avif', 'apng'],
                    default='auto',
                    help='Output container. "auto" (default) reads the output '
                         'filename extension: .webp, .avif, .apng/.png, else '
                         'gif. WebP, AVIF and APNG all carry true 8-bit alpha; '
                         'APNG is lossless and needs no plugin, but is the '
                         'largest of the three, so prefer it only when the '
                         'destination wants PNG specifically. WebP '
                         'supports true 8-bit alpha, so it is the right '
                         'choice for art with a fade/glow that was baked '
                         'against the background at authoring time -- GIF '
                         'physically cannot represent that (references/'
                         'lessons.md SS16).')
    p.add_argument('--allow-truncating-gif', action='store_true',
                    help='Write a GIF even when a frame comes out entirely '
                         'transparent. Pillow\'s GIF writer emits an unreadable '
                         'block for such a frame and the file truncates there '
                         '(measured: 85 of 123 frames written on a real asset '
                         'whose subject leaves the canvas), so the default is to '
                         'refuse and point at WebP/APNG, which keep every frame. '
                         'This flag exists for the case where a truncated GIF is '
                         'genuinely preferred to no GIF at all.')
    p.add_argument('--webp-lossy', action='store_true',
                    help='Encode WebP lossily. Default is lossless, which on '
                         'flat vector art is usually SMALLER as well as '
                         'better (measured 2109 KB lossless vs 3005 KB lossy '
                         'on the same asset). Use only to hit a hard byte cap.')
    p.add_argument('--webp-quality', type=int, default=90,
                    help='Quality 0-100 for --webp-lossy (default 90). Alpha '
                         'is always kept at maximum quality.')
    p.add_argument('--webp-method', type=int, default=2,
                    help='WebP encoder effort 0-6 (default 2). Measured across 5 '
                         'real assets: m2 costs only 0.6-8.3%% more bytes than m4 '
                         'but encodes ~2x faster, which is the better default. '
                         'm0 is faster still but its size cost is wildly '
                         'content-dependent (+134%% on one asset, +14%% on another '
                         '-- measure before using it). Do NOT raise to 6: 45x '
                         'slower (415s vs 9.2s) for 2.3%%.')
    p.add_argument('--bayer-size', type=int, choices=[4, 8], default=8,
                    help='Bayer threshold-matrix size for --dither-mode bayer '
                         '(default 8). Measured: 8x8 gives 64 threshold levels '
                         'against 4x4\'s 16 and tracks the intended alpha 2.5x '
                         'more closely (mean local-density error 0.0051 vs '
                         '0.0128), at identical temporal stability -- both are '
                         'ORDERED dithers, so a static region is byte-identical '
                         'frame to frame. Pass 4 to reproduce output from before '
                         'v5.0.0. (Error-diffusion dithers -- Floyd-Steinberg, '
                         'Jarvis, Sierra, Stucki -- are NOT offered for alpha: '
                         'measured, Floyd-Steinberg changed 8.1%% of pixels in a '
                         'region that was byte-identical between frames, i.e. '
                         'visible crawl on every edge, and it defeats GIF '
                         'inter-frame compression. gifsicle still uses '
                         'Floyd-Steinberg for COLOUR in the compress tiers.)')
    p.add_argument('--dither-mode', choices=['bayer', 'none', 'continuous'],
                    default=None,
                    help='How feathered edges resolve to the container\'s '
                         'alpha. Defaults to "bayer" for GIF output and '
                         '"continuous" for WebP output. "continuous" keeps '
                         'the estimated alpha as real 8-bit partial '
                         'transparency and is only valid for WebP -- GIF '
                         'has 1 bit of alpha, which is why the other two '
                         'modes exist at all. For GIF: '
                         'alpha. "bayer" (default) uses a spatial dither '
                         'pattern to simulate a soft edge -- looks good '
                         'over varied/textured backgrounds but can read as '
                         'visible noise/speckle over a SOLID flat color '
                         '(confirmed real case, including in a green-'
                         'screen transparency check specifically). "none" '
                         'uses a hard 50%% cutoff on the already-defringed '
                         'alpha instead -- a very slightly harder edge, '
                         'but zero visible noise on any background. Prefer '
                         '"none" for small flat-vector icon/sticker '
                         'content (this skill\'s primary target) unless '
                         'you specifically know the final placement '
                         'context is textured/varied. Verify your choice '
                         'against BOTH a checkerboard AND a solid-color '
                         'composite before delivering -- checkerboard can '
                         'visually camouflage bleed/noise that a solid '
                         'color exposes immediately.')
    p.add_argument('--erosion-exempt-max-size', type=int, default=None,
                    help='Exempt any removed (transparent) connected region '
                         'at or below this many pixels from '
                         '--edge-cleanup-erosion, instead of letting it '
                         'erode like every other edge. Normal erosion '
                         'shrinks the OPAQUE region around a boundary by a '
                         'fixed pixel count regardless of what\'s on the '
                         'transparent side -- proportionally fine for a '
                         'large silhouette\'s outer edge, but for a small '
                         'ISOLATED removed region well under the erosion '
                         'radius\'s own scale, it consumes the thin opaque '
                         'wall around it instead, inflating it rather than '
                         'trimming it. Confirmed real case: a single '
                         'original 1px removed pixel became a 49-70px hole '
                         'after a normal 2px erosion pass. Use this whenever '
                         'a removal mechanism (--tumble-safe\'s '
                         '--keep-bg-blob-if-near, or any other source of '
                         'small removed regions) might produce something '
                         'under roughly 20-30px -- pass that rough ceiling '
                         'here. Exempted regions are restored to their exact '
                         'pre-erosion pixels, not just left unshrunk, so '
                         'they stay at their true native size rather than '
                         'either extreme (a leftover solid opaque fleck if '
                         'skipped from removal entirely, or an inflated '
                         'transparent one if left to normal erosion).')
    p.add_argument('--preview', default=None,
                    help='Path to save a PNG contact sheet of sampled frames '
                         'composited over a checkerboard, for quick visual '
                         'verification without opening the GIF itself.')
    p.add_argument('--analyze', action='store_true',
                    help='Do not process the GIF. Instead scan it and print a JSON report '
                         'of the detected background color and candidate regions that may '
                         'need protecting, with a recommendation for each based on how '
                         'consistently each region is enclosed across frames.')
    p.add_argument('--recommend', action='store_true',
                    help='Do not process the GIF. Run --analyze internally and print a '
                         'JSON report with a suggested command line and the evidence '
                         'behind each recommended flag.')
    p.add_argument('--verify', action='store_true',
                    help='Do not process the GIF. Instead compare input_gif (the original '
                         'source) against output_gif (an already-produced result) and print '
                         'a JSON report of the mechanical verification checks: leftover '
                         'background, protected-region coverage, edge fringe, small '
                         'removed-region inflation, and duration/frame-count.')
    p.add_argument('--erosion-exempt-transient', action='store_true',
                   help='Exempt small removed regions from edge-cleanup erosion by '
                        'IDENTITY rather than by size: regions present in ~every frame at '
                        'a stable size are treated as design and eroded normally, and only '
                        'incidental ones are exempt. Use instead of '
                        '--erosion-exempt-max-size when the two overlap in size -- on a real '
                        'asset the design sat at 286-306px while the incidental noise reached '
                        '442px, so NO size threshold separated them (references/lessons.md '
                        'SS18.2, SS21). Optionally still bounded by --erosion-exempt-max-size '
                        'as a sanity cap.')
    p.add_argument('--auto', action='store_true',
                   help='FULLY AUTONOMOUS MODE. Runs --recommend, applies its flags '
                        '(only where you left that option at its default -- your explicit '
                        'flags always win), renders, then RE-VERIFIES the rendered file and '
                        'corrects/re-renders if the encoded result disagrees with what the '
                        'pre-encode calibration predicted. Also enables --auto-erosion.')
    p.add_argument('--ignore-source-alpha', action='store_true',
                   help="Remove by COLOUR across the whole frame even when the source is "
                        "already transparent. Off by default because a transparent source's "
                        "padding colour routinely also appears in its artwork -- a measured "
                        "sprite lost 2,455 of its 7,130 opaque pixels that way, all of them "
                        "black outline. Use this only when you know the source's own alpha is "
                        "wrong and the colour really is a background.")
    p.add_argument('--source-alpha-band', type=int, default=SOURCE_ALPHA_BAND_DEFAULT,
                   metavar='PX',
                   help=f"How far outside the source's own transparent region colour-based "
                        f"removal may reach, in pixels (default {SOURCE_ALPHA_BAND_DEFAULT}). "
                        f"This is where a leftover matte fringe from an earlier, imperfect "
                        f"background removal lives. 0 confines removal to exactly the pixels "
                        f"the source already declared transparent, i.e. changes nothing on a "
                        f"source whose cut is already clean. Ignored unless the source carries "
                        f"transparency that reads as its background.")
    p.add_argument('--auto-erosion', action='store_true',
                   help='Choose --edge-cleanup-erosion by measuring THIS asset against '
                        'itself (its own erosion 0/1/2/3 curve) instead of a fixed default. '
                        'Exists because the fringe metric has no honest global threshold: it '
                        'separates cleanly within one asset but the ranges overlap across '
                        'assets (heart fringed 0.0665 < crystal clean 0.0830). Picks the '
                        'SMALLEST erosion already at that asset\'s own floor, so it removes '
                        'the fringe without eating thin strokes. In-memory: costs one erosion '
                        'pass per candidate, not one render.')
    args = p.parse_args()

    if sum([args.analyze, args.recommend, args.verify, args.auto]) > 1:
        p.error('Use only one of --analyze, --recommend, --verify, or --auto at a time')
    if args.auto:
        if args.batch:
            p.error('--auto processes a single file; use --batch without --auto, or '
                    'run --auto per file')
        args.auto_erosion = True
    # An explicitly typed --edge-cleanup-erosion outranks the calibration. Gating
    # this on the parsed value would not work: the user may have typed the default
    # on purpose, and that is indistinguishable from silence without argv.
    if args.auto_erosion and 'edge_cleanup_erosion' in typed_option_names():
        args.auto_erosion = False
        print(f"--edge-cleanup-erosion {args.edge_cleanup_erosion} was given explicitly, "
              f"so erosion auto-calibration is OFF for this run (your value wins).",
              file=sys.stderr)

    if args.analyze:
        if not args.input_gif:
            p.error('input_gif is required when using --analyze')
        report = analyze(args.input_gif, tolerance=args.tolerance)
        print(json.dumps(report, indent=2))
        return

    if args.recommend:
        if not args.input_gif:
            p.error('input_gif is required when using --recommend')
        rec = recommend(args.input_gif, tolerance=args.tolerance)
        print(json.dumps(rec, indent=2))
        return

    if args.verify:
        if not args.input_gif or not args.output_gif:
            p.error('both input_gif and output_gif are required when using --verify '
                    '(input_gif = original source, output_gif = the file to verify)')
        # --verify inspects an output that ALREADY EXISTS; it does not render one.
        # Passing a path that has not been written yet used to surface as a raw
        # Pillow FileNotFoundError traceback from inside load_gif_rgba_frames,
        # which reads like a crash rather than "you skipped the render".
        if not os.path.exists(args.output_gif):
            p.error(f'--verify inspects an output that already exists, and '
                    f'{args.output_gif!r} does not. Run the processing first '
                    f'(same command WITHOUT --verify), then re-run with --verify.')
        report = verify(args.input_gif, args.output_gif, tolerance=args.tolerance)
        print(json.dumps(report, indent=2))
        return

    if args.auto:
        if not args.input_gif or not args.output_gif:
            p.error('both input_gif and output_gif are required when using --auto')
        if not args.bg_color:
            _im = Image.open(args.input_gif)
            args.bg_color = rgb_to_hex(detect_bg_color(np.array(_im.convert('RGB'))))
        auto_run(args.input_gif, args.output_gif, args, p)
        return

    if args.batch:
        run_batch(args, p)
        return

    if not args.input_gif:
        p.error('input_gif is required unless --batch is used')
    if not args.output_gif:
        p.error('output_gif is required unless --analyze or --batch is used')
    if not args.bg_color:
        im = Image.open(args.input_gif)
        rgb0 = np.array(im.convert('RGB'))
        args.bg_color = rgb_to_hex(detect_bg_color(rgb0))
        print(f'Auto-detected background color: #{args.bg_color}', file=sys.stderr)

    if args.protect_outline_color and args.protect_region:
        p.error('Use only one of --protect-outline-color or --protect-region')
    if args.tumble_safe and (args.protect_outline_color or args.protect_region):
        p.error('--tumble-safe replaces --protect-outline-color/--protect-region '
                 '(their single-frame enclosure geometry does not generalize '
                 'across frames of tumbling/rotating content) -- use '
                 '--keep-bg-blob-if-near instead')
    if args.keep_bg_blob_if_near and not args.tumble_safe:
        p.error('--keep-bg-blob-if-near only applies with --tumble-safe')

    apply_pixel_art_preset(args)
    process(args.input_gif, args.output_gif, args)


if __name__ == '__main__':
    main()
