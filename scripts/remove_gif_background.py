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
      - 'medium': -O3 --lossy=30 -k 200 --dither=floyd-steinberg. The
        200-color cap exists specifically so --dither has something to do:
        confirmed directly that gifsicle's --dither is a no-op unless the
        palette is actually being reduced (byte-identical output with/
        without it when only --lossy was set, no -k). 200 is a light touch
        deliberately -- most source art here uses well under 200 colors
        even before any reduction, so this mainly dithers the antialiased/
        feathered edge transition pixels (which DO commonly exceed 200
        distinct shades) rather than visibly flattening the interior.
      - 'heavy': -O3 --lossy=80 -k 128 --dither=floyd-steinberg. Cuts to a
        128-color palette using Floyd-Steinberg error-diffusion dithering
        -- the right choice for smoothly-shaded/antialiased source art
        (this skill's feathered edges in particular): it distributes
        quantization error into neighboring pixels instead of banding,
        unlike gifsicle's other dither modes (`ordered`/`halftone`/`o8x8`),
        which are better suited to flat poster-style art and show an
        obvious repeating pattern on gradients or feathered edges.
    Returns True on success (file replaced in place), False if gifsicle
    isn't available or the call failed (original file is left untouched
    either way).
    """
    if not shutil.which('gifsicle'):
        return False
    args = {
        'lossless': ['-O3'],
        'medium': ['-O3', '--lossy=30', '-k', '200', '--dither=floyd-steinberg'],
        'heavy': ['-O3', '--lossy=80', '-k', '128', '--dither=floyd-steinberg'],
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
    if 'transparency' not in im0.info:
        return None
    trans_index = im0.info['transparency']
    raw = np.array(im0.convert('P')) if im0.mode != 'P' else np.array(im0)
    return raw == trans_index


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
    """
    im = Image.open(input_path)
    n_frames = im.n_frames
    warn_if_source_has_transparency(im, input_path)
    im.seek(0)
    rgb0 = np.array(im.convert('RGB'))
    bg_rgb = detect_bg_color(rgb0)
    H, W, _ = rgb0.shape

    all_rgb_frames = []
    for i in range(n_frames):
        im.seek(i)
        all_rgb_frames.append(np.array(im.convert('RGB')))

    if n_frames <= max_samples:
        sample_idxs = list(range(n_frames))
    else:
        sample_idxs = sorted(set(np.linspace(0, n_frames - 1, max_samples).astype(int).tolist()))

    union_mask = np.zeros((H, W), dtype=bool)
    rep_frame_for_color = {}  # remember a frame index/rgb to sample outline color later

    for i in sample_idxs:
        rgb = all_rgb_frames[i]
        bg_mask = color_mask(rgb, bg_rgb, tolerance)
        labeled, num = ndimage.label(bg_mask, structure=STRUCTURE)
        border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | set(labeled[:, 0]) | set(labeled[:, -1])
        border_labels.discard(0)
        enclosed = bg_mask & ~np.isin(labeled, list(border_labels))
        union_mask |= enclosed
        rep_frame_for_color[i] = rgb

    # merge nearby/jittery regions across frames with a small dilation before labeling
    dilated = ndimage.binary_dilation(union_mask, structure=np.ones((5, 5)))
    clabeled, cnum = ndimage.label(dilated, structure=STRUCTURE)

    results = []
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
            rgb = all_rgb_frames[i]
            bg_mask = color_mask(rgb, bg_rgb, tolerance)
            labeled, num = ndimage.label(bg_mask, structure=STRUCTURE)
            border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | set(labeled[:, 0]) | set(labeled[:, -1])
            border_labels.discard(0)
            enclosed = bg_mask & ~np.isin(labeled, list(border_labels))
            if (enclosed & comp_footprint).any():
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
            true_footprint_frame_rgb, bg_rgb, true_footprint, tolerance)

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

        results.append({
            'id': cid,
            'pixel_count': int(comp_footprint.sum()),
            'bbox_xyxy': bbox,
            'center_xy': [round(cx, 1), round(cy, 1)],
            'suggested_protect_region': f'circle:{cx:.0f},{cy:.0f},{radius:.0f}',
            'frames_enclosed': frames_hit,
            'frames_sampled': len(sample_idxs),
            'enclosure_ratio': round(ratio, 3),
            'likely_intentional_design': ratio >= 0.9,
            'candidate_outline_color': outline_color,
            'outline_color_verified': outline_color is not None,
            'circularity_ratio': round(circularity, 2),
            'circle_region_safe': circularity >= 0.85,
            'note': note,
        })

    return {
        'n_frames_total': n_frames,
        'frames_sampled': len(sample_idxs),
        'detected_bg_color': rgb_to_hex(bg_rgb),
        'source_has_pre_existing_transparency': 'transparency' in im.info,
        'edge_hardness': measure_edge_hardness(rgb0, bg_rgb, tolerance),
        'candidate_regions': results,
    }


def color_mask(rgb, target, tolerance):
    diff = np.abs(rgb.astype(int) - np.array(target).astype(int))
    return np.all(diff <= tolerance, axis=-1)


def find_verified_outline_color(rgb, bg_rgb, comp_footprint, tolerance,
                                 outline_tolerance=40,
                                 dilation_radii=(4, 10, 20, 35, 55)):
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
    H, W, _ = rgb.shape
    candidate_colors = {}
    prev_cumulative = np.zeros((H, W), dtype=bool)
    for radius in dilation_radii:
        dilated = ndimage.binary_dilation(comp_footprint, iterations=radius)
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
        vals, counts = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
        order = np.argsort(-counts)
        for v in vals[order][:3]:
            candidate_colors[tuple(int(x) for x in v)] = True

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
        containment = (comp_footprint & filled).sum() / max(comp_footprint.sum(), 1)
        if containment >= 0.95:
            area = int(filled.sum())
            if best_area is None or area < best_area:
                best_color, best_area, best_shape = rgb_to_hex(np.array(color)), area, filled

    return best_color, best_area, best_shape


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


BAYER4 = np.array([
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
], dtype=float) / 16.0


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


def estimate_alpha_and_defringe(rgb, bg_rgb, protected, tolerance, band_multiplier=4.0):
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
    """
    H, W, _ = rgb.shape
    bg = np.array(bg_rgb, dtype=float)
    dist_to_bg = np.linalg.norm(rgb.astype(float) - bg, axis=-1)

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


def compute_alpha_mask(rgb, protected, args):
    """
    Full alpha decision for one frame, combining the hard background mask
    with (optionally) feathered/dithered edges. Returns (alpha_uint8, rgb_out).
    """
    bg_rgb = hex_to_rgb(args.bg_color)

    if not args.feather:
        bg_mask = color_mask(rgb, bg_rgb, args.tolerance)
        transparent_mask = bg_mask & ~protected
        alpha = np.where(transparent_mask, 0, 255).astype(np.uint8)
        return alpha, rgb

    alpha_f, recolored, band_mask = estimate_alpha_and_defringe(
        rgb, bg_rgb, protected, args.tolerance, args.feather_band_multiplier
    )
    dither_mode = getattr(args, 'dither_mode', 'bayer')
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
        keep = ordered_dither_mask(alpha_f)
    # Outside the transition band, alpha_f is already exactly 0 or 1 (or 1 if
    # protected), so dithering there is a no-op; this keeps behavior identical
    # to the hard-cutoff path away from edges.
    alpha = np.where(keep, 255, 0).astype(np.uint8)
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
            for bi in bad_idxs:
                nearest = min(good_idxs, key=lambda gi: abs(gi - bi))
                frame_masks[bi] = frame_masks[nearest]
        per_color_masks[hex_color] = frame_masks

    result = []
    for i in range(n):
        union = np.zeros((H, W), dtype=bool)
        for hex_color in hex_colors:
            union |= per_color_masks[hex_color][i]
        result.append(union)
    return result


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
                written.append(im.info.get('duration') or 0)
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


def resize_rgba_frames(rgb_frames, alpha_frames, scale, resample=None):
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
        rgb_im = Image.fromarray(rgb).resize((new_w, new_h), resample)
        alpha_im = Image.fromarray(alpha).resize((new_w, new_h), resample)
        new_rgb.append(np.array(rgb_im))
        a = np.array(alpha_im)
        new_alpha.append(np.where(a > 127, 255, 0).astype(np.uint8))
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


def process(input_path, output_path, args):
    im0 = Image.open(input_path)
    n_frames = im0.n_frames
    loop = im0.info.get('loop', 0)
    warn_if_source_has_transparency(im0, input_path)

    rgb_frames_raw = []
    source_trans_masks = []
    durations = []

    for i in range(n_frames):
        im0.seek(i)
        durations.append(im0.info.get('duration', 100))
        source_trans_mask = get_source_transparency_mask(im0)  # BEFORE convert('RGB')
        frame = im0.convert('RGB')
        rgb = np.array(frame)
        rgb_frames_raw.append(rgb)
        source_trans_masks.append(source_trans_mask)

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
        protected_masks = build_protected_masks_robust(rgb_frames_raw, args)

    rgb_frames = []
    alpha_frames = []
    any_source_transparency = False

    for i in range(n_frames):
        rgb = rgb_frames_raw[i]
        protected = protected_masks[i]
        if getattr(args, 'protect_band_only', None) is not None:
            removable_core = ~protected
            protected = build_band_only_removal_mask(removable_core, args.protect_band_only)
        alpha, rgb_out = compute_alpha_mask(rgb, protected, args)

        source_trans_mask = source_trans_masks[i]
        if source_trans_mask is not None and source_trans_mask.any():
            any_source_transparency = True
            # Force pixels the SOURCE already declared transparent to stay
            # transparent, overriding whatever this script's own color-based
            # detection concluded about them -- their revealed RGB is
            # meaningless flattening fallout, not real art (see
            # get_source_transparency_mask's docstring).
            alpha = np.where(source_trans_mask, 0, alpha)

        rgb_frames.append(rgb_out)
        alpha_frames.append(alpha)

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
        if exempt_max is not None and exempt_max > 0:
            tiny_masks = find_tiny_removed_regions(alpha_frames, exempt_max)
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
    # overrides that tier's own resize target instead of stacking with it
    # (handled below via resize_override passed into apply_tier).
    if tier is None and args.resize_max_dim:
        h, w = alpha_frames[0].shape
        scale = fit_scale_for_max_dimension(w, h, args.resize_max_dim)
        if scale < 1.0:
            resample = Image.NEAREST if args.pixel_art else Image.LANCZOS
            rgb_frames, alpha_frames = resize_rgba_frames(rgb_frames, alpha_frames, scale, resample=resample)
            new_h, new_w = alpha_frames[0].shape
            print(f"Resized to fit {args.resize_max_dim}px on the longer "
                  f"side: {w}x{h} -> {new_w}x{new_h}"
                  f"{' (nearest-neighbor, pixel-art mode)' if args.pixel_art else ''}.",
                  file=sys.stderr)
            if args.pixel_art:
                print("Skipped post-resize erosion (pixel-art mode -- "
                      "nearest-neighbor resize has no fuzz to clean up).",
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

    size_bytes = render_frames_to_gif(rgb_frames, alpha_frames, durations, loop, output_path,
                                       quantizer=args.quantizer)
    out_w, out_h = alpha_frames[0].shape[1], alpha_frames[0].shape[0]
    print(f"Saved {output_path} ({describe_written_timing(output_path, durations)})",
          file=sys.stderr)
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

    if args.target_kb:
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


def apply_pixel_art_preset(args):
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
        args.feather = False
        args.edge_cleanup_erosion = 0


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
    p.add_argument('--edge-cleanup-erosion', type=int, default=2,
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
    p.add_argument('--dither-mode', choices=['bayer', 'none'], default='bayer',
                    help='How feathered edges resolve to GIF\'s 1-bit '
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
    args = p.parse_args()

    if args.analyze:
        if not args.input_gif:
            p.error('input_gif is required when using --analyze')
        report = analyze(args.input_gif)
        print(json.dumps(report, indent=2))
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
