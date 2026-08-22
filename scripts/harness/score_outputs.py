"""Grade a rendered output against per-frame ground truth derived from its SOURCE.

⚠️ Replaces an earlier grader that reported the hardest asset 100% correct on all three
trial agents while human review called it a disaster. Three causes, each addressed here
by name:
  1. binary keep/remove ground truth cannot grade a FADE -> fade_coherence
  2. no measure of outline quality at all                -> edge_cleanliness
  3. a MEAN over sampled frames hid a 16-frame defect    -> every figure is a WORST

Two deliberate deviations from the plan that specified this file, both forced by
measurement rather than preference:

* **The background colour is NOT hardcoded to white.** Measured 2026-08-20: all five
  trial assets are pure white on every border pixel, so a white constant would have
  graded them correctly -- and would have silently produced garbage on
  `local/corpus dark/`, the non-white population this same scorer is required to measure.
  The modal border colour reduces to exactly the white constant on a white asset.

* **`fade_correlation` (a Pearson r over per-frame means) was implemented, measured, and
  discarded.** It returned exactly 1.000 on all seven trial outputs INCLUDING the broken
  one, because the interior region it sampled is spatially static and its per-frame std
  fell under the guard, so the measure defaulted to its pass value on every input. That is
  the vacuous pass this file exists to prevent. `fade_coherence` replaces it.

**`fade_coherence` is deliberately MODEL-NEUTRAL, and that is the whole design.** Whether
a solid pale shape drawn getting lighter should become translucent (recover alpha) or stay
opaque (keep colour fidelity) is an open product question -- `references/lessons.md` §16
and the 2026-08-19 trial both say so, and a grader has no standing to answer it. So this
measure fits BOTH models to the observed alpha and keeps the better fit: an output is
graded on whether it implements *some* coherent mapping, not on which one it picked.
Measured 2026-08-20 against three reference points on the five trial assets:

    synthetic ideal ramp  (alpha = 255*d/765)     -> 1.000 on every gradeable component
    synthetic binary cut  (alpha = 255 where art) -> 1.000 on every gradeable component
    hurricane, agent-3 (the filed cliff defect)   -> 0.688
    growth / satellite, agent-3                   -> 0.994 / 0.989

Both legitimate answers pass at 1.000 and the filed defect sits alone at 0.688, so the
0.90 threshold is a gap, not a tuned constant. `alpha_override` below is how those two
controls are reproduced -- it is part of the shipped module on purpose, so the claim
"this measure can pass a correct fade" stays re-runnable instead of being a note.

An asset with no ramping component is reported as `fade_coherence: None` /
`fade_model: None` -- UNVERIFIED, never a vacuous 1.0 (§13, §16, §17).
"""
import numpy as np
from PIL import Image
from scipy import ndimage

ST = np.ones((3, 3), bool)
TOL = 30          # per-pixel |sum of channel deltas| from the background colour
MIN_RAMP = 0.15   # a component whose source colour barely moves has no fade to grade
MIN_LIVE = 0.02   # a frame counts only if this share of the component is still art


def background_colour(rgb):
    """The modal colour of the 1px border ring. On a white asset this is (255,255,255),
    i.e. identical to the constant the plan specified; on a dark or saturated asset it is
    the actual background, which is the whole point."""
    border = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
    cols, cnt = np.unique(border.reshape(-1, 3), axis=0, return_counts=True)
    return cols[int(np.argmax(cnt))].astype(int)


def _frame_start_times_ms(im):
    """Cumulative start time (ms) of every STORED frame in an animated image, plus the
    file's total duration. Frame i covers [starts[i], starts[i+1)) -- the last frame
    extends to `total`.

    Needed because GIF/WebP encoders merge a run of pixel-identical consecutive frames
    into one stored frame with an extended duration, to save space. Reading two files'
    frames by raw POSITION (`src.seek(i)` / `out.seek(i)` for the same i) silently drifts
    out of sync the instant one file merges a frame the other did not -- every stored
    index after that point points at a different moment in the animation in each file.
    Missing/zero duration metadata defaults to 30ms rather than 0, so a file with no
    duration info at all does not collapse every frame's start time onto zero.
    """
    starts = []
    t = 0
    for i in range(getattr(im, 'n_frames', 1)):
        im.seek(i)
        starts.append(t)
        t += im.info.get('duration', 30) or 30
    return starts, t


def _stored_index_at_time(starts, total, t):
    """The stored-frame index active at time `t` on that file's own timeline, clamped to
    its range. `bisect_right` then step back one gives the last start <= t, i.e. exactly
    the frame whose interval contains it."""
    import bisect
    if t <= 0:
        return 0
    if t >= total:
        return len(starts) - 1
    i = bisect.bisect_right(starts, t) - 1
    return max(0, min(i, len(starts) - 1))


def _truth(rgb, bg):
    """outside = bg-coloured and connected to the border; interior = bg-coloured but not;
    art = the rest."""
    flat = np.abs(rgb.astype(int) - bg).sum(-1) <= TOL
    lab, _ = ndimage.label(flat, structure=ST)
    bl = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    bl.discard(0)
    outside = flat & np.isin(lab, list(bl))
    return outside, flat & ~outside, ~flat


def _edge_cleanliness(rgba):
    """Of the pixels in the 2px band just inside the silhouette, what share sit at an
    alpha the encoder never asked for -- i.e. neither ~0 nor ~255 nor a deliberate fade?
    A clean cutout has few; a fringe has many. Human reviewers notice this FIRST and the
    old grader could not see it at all."""
    a = rgba[..., 3]
    op = a > 0
    if not op.any():
        return 1.0
    inner = op & ~ndimage.binary_erosion(op, iterations=2)
    if not inner.any():
        return 1.0
    v = a[inner]
    return 1.0 - float(((v > 12) & (v < 243)).mean())


def _fade(series):
    """Fit the two legitimate alpha models to one component's (distance, alpha) series and
    keep the better fit. Returns (coherence, model, ramp) or (None, None, ramp).

    ramp model:   alpha proportional to source distance, one least-squares scale factor
    opaque model: alpha constant on whatever is still art

    Alpha is averaged over pixels STILL ART in that frame, never over the frame-0 mask --
    averaging over the whole mask conflates "how many pixels remain" with "how translucent
    they are", which is what made a correct binary cutout score 0.284 in the first draft.
    """
    d = np.array([x for x, _ in series], float)
    a = np.array([y for _, y in series], float)
    ramp = float((d.max() - d.min()) / max(d.max(), 1e-9))
    if len(d) < 6 or ramp < MIN_RAMP:
        return None, None, ramp
    an, dn = a / 255.0, d / d.max()
    scale = float((an * dn).sum() / max((dn * dn).sum(), 1e-9))
    ramp_err = float(np.abs(an - scale * dn).max())
    opaque_err = float((np.abs(a - np.median(a)) / 255.0).max())
    err = min(ramp_err, opaque_err)
    return 1.0 - err, ('ramp' if ramp_err <= opaque_err else 'opaque'), ramp


def _perimeter(mask):
    """The one-pixel boundary ring of a mask. Erosion removes exactly this."""
    return int((mask & ~ndimage.binary_erosion(mask, structure=ST)).sum())


def score(src_path, out_path=None, samples=24, alpha_override=None):
    """Grade `out_path` against `src_path`. Every figure is a WORST over sampled frames.

    `alpha_override` is a callable(distance_map) -> alpha_map used INSTEAD of reading
    `out_path`; it exists so the two synthetic controls in the module docstring stay
    executable. Production callers never pass it.
    """
    src = Image.open(src_path)
    out = Image.open(out_path) if alpha_override is None else None
    n = getattr(src, 'n_frames', 1)
    # Sampled over the SOURCE's own frame count, not min(src, out) -- capping to the
    # shorter of the two silently excluded source frames whenever the output coalesced
    # frames, which is exactly where a real defect is likely to live (SS37.8: the
    # `Cut loop.gif` case this was found on had its worst frame outside the capped range
    # entirely on some renders).
    idxs = sorted(set(np.linspace(0, n - 1, min(samples, n)).astype(int).tolist()))
    out_idx_for = None
    if out is not None:
        out_n = getattr(out, 'n_frames', 1)
        if out_n == n:
            # EQUAL frame counts is the common case and means no coalescing happened --
            # position i of the output IS logical frame i, exactly as before. Falling
            # through to duration-based mapping here was tried and is actively WRONG: a
            # source and a re-encoded output can report different per-frame durations for
            # the same discrete frame sequence (measured on `in-love.gif`: source 40ms,
            # rendered .webp 30ms/frame, same 48 frames both files) with no coalescing at
            # all, and mapping by absolute time then reads the WRONG frame despite the
            # correspondence being trivially 1:1. Nine real fixture tests caught this.
            out_idx_for = {i: i for i in idxs}
        else:
            src_starts, _ = _frame_start_times_ms(src)
            out_starts, out_total = _frame_start_times_ms(out)
            # Frame counts differ, which is the actual signal that the output coalesced
            # (or otherwise dropped) frames the source has -- only here does duration-based
            # mapping have anything real to correct. See _frame_start_times_ms's docstring.
            out_idx_for = {i: _stored_index_at_time(out_starts, out_total, src_starts[i])
                           for i in idxs}

    src.seek(0)
    bg_c = background_colour(np.array(src.convert('RGB')))  # frame 0 defines it throughout
    art0 = np.abs(np.array(src.convert('RGB')).astype(int) - bg_c).sum(-1) > TOL
    lab, k = ndimage.label(art0, structure=ST)
    areas = ndimage.sum(art0, lab, range(1, k + 1)) if k else []
    comps = [i + 1 for i, ar in enumerate(areas) if ar >= 0.01 * art0.size]

    bg, inter, art, edge = [], [], [], []
    # ⚠️ `art_kept_worst` is a FRACTION, and a fraction is only as meaningful as its
    # denominator. Erosion removes a PERIMETER (O(r)) while "art pixels present" is an
    # AREA (O(r^2)), so a fixed 1px trim costs a share that grows without bound as the
    # subject shrinks or leaves the canvas. Measured 2026-08-20 on a rocket that exits
    # frame: the worst frame held 5,232 art pixels against 84,672 on frame 0 and lost 695
    # -- the SMALLEST absolute loss of any worst frame in the set -- yet read as 13-21%
    # "destroyed", and that number was on its way into a release decision until Harkirat
    # challenged it. So the worst frame is reported WITH the two things needed to judge it:
    #   art_frame_share_at_worst -- how much of this animation's peak artwork was even
    #                               present on that frame. A low value means the
    #                               denominator collapsed, not that artwork was destroyed.
    #   art_lost_over_perimeter  -- the scale-free version. Erosion of n px cannot cost
    #                               more than ~n perimeter rings, so <=1.1 is geometry and
    #                               >1.1 means something THIN was bitten from both sides.
    #                               Measured across five worst-frame cases: 0.70-0.95.
    # Keep reporting the worst frame -- a 16-frame background wedge averaged to 99.9% and
    # vanished, which is why the rule exists. Just never read a worst-frame FRACTION as
    # damage without its denominator.
    # `interior_kept_worst` has the same denominator problem in a different dress, found
    # 2026-08-20 on paper-plane: it read 0.556, which sounds like half the artwork gone. The
    # lost pixels are the COUNTER of a closed loop -- the hole inside a swirl -- which a
    # transparent sticker is supposed to see through. The measure is a SCREEN, not a verdict:
    # on growth and rocket it correctly caught real destruction (0.000 and 0.309), and here it
    # correctly caught a removal that happens to be right. So report what was lost and how big
    # the biggest single piece was, and let the caller tell a loop counter from a rocket body.
    # `bg_removed_worst` is the THIRD measure here to be caught punishing a correct answer,
    # and all three failed the same way: a binary ground truth cannot grade a fade. Found
    # 2026-08-20 on an asset whose hearts fade in and out behind a smiley -- it read 0.931,
    # which sounds like 7% of the background left behind. Measured on its worst frame: all
    # 13,622 "retained background" pixels are TRANSLUCENT (alpha 2-37, median 32, zero at
    # 255), their source colour sits 5-28 from the background against a tolerance of 30, and
    # the correlation between source distance and output alpha is 0.943. That is a fade being
    # preserved faithfully, not background being missed.
    # So report the strict figure AND the unambiguous one: background kept at more than half
    # opacity is wrong under every interpretation, while background kept at low alpha
    # proportional to its own paleness is what a fade is supposed to look like.
    # ⚠️ NEITHER of the two supporting fields discriminates a preserved fade from a ghost,
    # and both candidate discriminators were BUILT AND FALSIFIED before this comment was
    # written. `bg_not_opaque_worst` does not: the known-broken hurricane output scores
    # 1.0000 on it too, because that failure ghosts the whole image at low alpha instead of
    # leaving a solid patch. And the distance/alpha correlation does not either -- the
    # obvious hypothesis was that a ghost keeps alpha unrelated to paleness, but hurricane
    # reads **0.957** at its worst frame against in-love's 0.943, because
    # `--recover-fade-alpha` derives alpha FROM paleness, so its failure is faithful to
    # paleness by construction. An early probe showed 0.021 and was wrong: it had sampled a
    # different frame than the one it reported.
    #
    # What actually separates them is MAGNITUDE, which `bg_removed_worst` already carries:
    #   a preserved fade   0.931 retained-background worst  (6.9% kept, all translucent)
    #   a ghosted output   0.390                            (61% kept)
    #   a solid bg wedge   0.951, and bg_not_opaque_worst 0.951 -- the only case where a
    #                      pixel is kept at full opacity
    # So the three fields are a SCREEN, read together: a low strict figure with everything
    # translucent is a fade only if the amount retained is small. Do not reach for the
    # correlation as a verdict; it is reported as evidence and it is kept here mainly so the
    # next session does not re-derive the falsified hypothesis.
    bg_opaque = []
    bg_keep_corr = []
    interior_lost, interior_biggest = [], []
    art_px, art_lost, art_perim = [], [], []
    art_lost_faint, art_lost_solid = [], []
    fade_series = {c: [] for c in comps}
    for i in idxs:
        src.seek(i)
        s_rgb = np.array(src.convert('RGB'))
        d = np.abs(s_rgb.astype(int) - bg_c).sum(-1)
        if alpha_override is None:
            out.seek(out_idx_for[i])
            o = np.array(out.convert('RGBA'))
            if o.shape[:2] != s_rgb.shape[:2]:
                return {'shape_mismatch': True}
            al = o[..., 3]
        else:
            al = alpha_override(d).astype(np.uint8)
            o = np.dstack([s_rgb, al])
        outside, interior, arts = _truth(s_rgb, bg_c)
        bg.append(float((al[outside] == 0).mean()) if outside.any() else 1.0)
        bg_opaque.append(float((al[outside] <= 128).mean()) if outside.any() else 1.0)
        # ⚠️ Indexed by FRAME, and read back at the frame with the worst bg_removed -- not
        # the frame with the most retained pixels, and not the best correlation. The first
        # draft took max() over frames and reported hurricane at 0.957 when its own worst
        # frame reads 0.021, i.e. it certified the known-broken output by quoting its most
        # flattering frame. Same worst-frame rule as every other figure in this file, and
        # exactly the failure the file exists to prevent, reintroduced in a new field.
        _kept = outside & (al > 0)
        _c = None
        if _kept.sum() >= 200:
            _d = np.abs(s_rgb[_kept].astype(int) - bg_c).sum(-1).astype(float)
            _v = al[_kept].astype(float)
            if _d.std() > 0 and _v.std() > 0:
                _c = float(np.corrcoef(_d, _v)[0, 1])
        bg_keep_corr.append(_c)
        inter.append(float((al[interior] > 0).mean()) if interior.any() else 1.0)
        _il = interior & (al == 0)
        interior_lost.append(int(_il.sum()))
        if _il.any():
            _lab, _n = ndimage.label(_il, structure=ST)
            interior_biggest.append(int(np.bincount(_lab.ravel())[1:].max()) if _n else 0)
        else:
            interior_biggest.append(0)
        art.append(float((al[arts] > 0).mean()) if arts.any() else 1.0)
        art_px.append(int(arts.sum()))
        _lost = arts & (al == 0)
        art_lost.append(int(_lost.sum()) if arts.any() else 0)
        art_perim.append(_perimeter(arts) if arts.any() else 0)
        # ⚠️ WHAT was lost, not just how much. `art_lost_over_perimeter` is the FOURTH measure
        # in this file caught punishing a correct answer, and it fails the same way the other
        # three did: `_truth` calls every pixel more than TOL from the background "art", so a
        # flattened fade's faint stages ARE artwork by that definition -- and truncating them
        # at a 1-bit cutoff, the only thing a GIF can do, then scores as destruction.
        # Measured 2026-08-20 over the 20 assets a PRE/POST erosion study had attributed to
        # the keyer: 10 of them lose pixels whose median source distance is 33-63, i.e. sitting
        # just above the TOL=30 line, at a faint share of 98.7-100%. Two of those ten are
        # `love` and `heart`, whose outputs have been accepted for months. The 4 with real
        # damage lose pixels at median distance 145-264, 40-88% of them past 150, and remove
        # solid blobs of 2,072-6,657px. That is a bimodal split with nothing in between, which
        # is where these two cut points come from -- they are read off the distribution, not
        # chosen. 90 is 3x TOL: the band a truncated fade occupies.
        if _lost.any():
            _dl = d[_lost]
            art_lost_faint.append(float((_dl <= 3 * TOL).mean()))
            _solid = _lost & (d > 150)
            if _solid.any():
                _sl, _sn = ndimage.label(_solid, structure=ST)
                art_lost_solid.append(int(np.bincount(_sl.ravel())[1:].max()) if _sn else 0)
            else:
                art_lost_solid.append(0)
        else:
            art_lost_faint.append(1.0)
            art_lost_solid.append(0)
        edge.append(_edge_cleanliness(o))
        for c in comps:
            live = (lab == c) & (d > TOL)
            if live.sum() >= MIN_LIVE * (lab == c).sum():
                fade_series[c].append((float(d[live].mean()), float(al[live].mean())))

    graded = [(_fade(v), c) for c, v in fade_series.items() if len(v) >= 6]
    graded = [(r, c) for (r, c) in graded if r[0] is not None]
    coh = model = None
    fade_ramp = max([r[2] for (r, _) in graded], default=None)
    if graded:
        (coh, model, _), _ = min(graded, key=lambda t: t[0][0])   # WORST component

    worst = int(np.argmin(bg)) if bg else 0
    aw = int(np.argmin(art)) if art else 0
    peak = max(art_px) if art_px else 0
    _pairs = [(l / p, i) for i, (l, p) in enumerate(zip(art_lost, art_perim)) if p > 0]
    ratios = [r for r, _ in _pairs]
    # Read the two supporting fields at the frame the RATIO is worst -- the frame that needs
    # explaining -- not at the worst-art frame and not as a mean. Same rule as
    # `bg_kept_fade_correlation`, which was caught quoting its most flattering frame.
    _wi = max(_pairs)[1] if _pairs else None
    return {'bg_removed_worst': min(bg) if bg else 1.0,
            'bg_not_opaque_worst': min(bg_opaque) if bg_opaque else 1.0,
            # read at the WORST bg_removed frame -- the one that needs explaining
            'bg_kept_fade_correlation': (round(bg_keep_corr[worst], 3)
                                         if bg_keep_corr and bg_keep_corr[worst] is not None
                                         else None),
            'interior_kept_worst': min(inter) if inter else 1.0,
            'art_kept_worst': min(art) if art else 1.0,
            'interior_lost_px_worst': max(interior_lost) if interior_lost else 0,
            'interior_lost_largest_component': (max(interior_biggest)
                                                if interior_biggest else 0),
            'art_kept_worst_frame': idxs[aw] if idxs else 0,
            'art_px_at_worst': art_px[aw] if art_px else 0,
            'art_px_peak': peak,
            'art_frame_share_at_worst': (round(art_px[aw] / peak, 4)
                                         if peak else None),
            'art_lost_over_perimeter': (round(max(ratios), 3) if ratios else None),
            # Read these two BEFORE calling a high ratio damage. A high ratio with a faint
            # share near 1.0 and no solid component is a fade being truncated, which is
            # correct on a 1-bit container and is not a defect.
            'art_lost_faint_share': (round(art_lost_faint[_wi], 3)
                                     if _wi is not None and art_lost_faint else None),
            'art_lost_solid_largest_component': (art_lost_solid[_wi]
                                                 if _wi is not None and art_lost_solid else None),
            'edge_cleanliness': min(edge) if edge else 1.0,
            'fade_coherence': coh,
            'fade_model': model,
            'fade_ramp': fade_ramp,
            'worst_frame_index': idxs[worst] if idxs else 0,
            'frames_compared': len(idxs),
            'background_colour': tuple(int(x) for x in bg_c)}


def IDEAL_RAMP(d):
    """Control: a perfectly proportional colour-distance -> alpha ramp."""
    return np.clip(255.0 * d / 765.0, 0, 255)


def BINARY_CUT(d):
    """Control: a fully opaque cutout -- the OTHER legitimate answer for a pale shape."""
    return np.where(d > TOL, 255.0, 0.0)
