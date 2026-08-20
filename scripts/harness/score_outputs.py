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


def score(src_path, out_path=None, samples=24, alpha_override=None):
    """Grade `out_path` against `src_path`. Every figure is a WORST over sampled frames.

    `alpha_override` is a callable(distance_map) -> alpha_map used INSTEAD of reading
    `out_path`; it exists so the two synthetic controls in the module docstring stay
    executable. Production callers never pass it.
    """
    src = Image.open(src_path)
    out = Image.open(out_path) if alpha_override is None else None
    n = getattr(src, 'n_frames', 1)
    if out is not None:
        n = min(n, getattr(out, 'n_frames', 1))
    idxs = sorted(set(np.linspace(0, n - 1, min(samples, n)).astype(int).tolist()))

    src.seek(0)
    bg_c = background_colour(np.array(src.convert('RGB')))  # frame 0 defines it throughout
    art0 = np.abs(np.array(src.convert('RGB')).astype(int) - bg_c).sum(-1) > TOL
    lab, k = ndimage.label(art0, structure=ST)
    areas = ndimage.sum(art0, lab, range(1, k + 1)) if k else []
    comps = [i + 1 for i, ar in enumerate(areas) if ar >= 0.01 * art0.size]

    bg, inter, art, edge = [], [], [], []
    fade_series = {c: [] for c in comps}
    for i in idxs:
        src.seek(i)
        s_rgb = np.array(src.convert('RGB'))
        d = np.abs(s_rgb.astype(int) - bg_c).sum(-1)
        if alpha_override is None:
            out.seek(i)
            o = np.array(out.convert('RGBA'))
            if o.shape[:2] != s_rgb.shape[:2]:
                return {'shape_mismatch': True}
            al = o[..., 3]
        else:
            al = alpha_override(d).astype(np.uint8)
            o = np.dstack([s_rgb, al])
        outside, interior, arts = _truth(s_rgb, bg_c)
        bg.append(float((al[outside] == 0).mean()) if outside.any() else 1.0)
        inter.append(float((al[interior] > 0).mean()) if interior.any() else 1.0)
        art.append(float((al[arts] > 0).mean()) if arts.any() else 1.0)
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
    return {'bg_removed_worst': min(bg) if bg else 1.0,
            'interior_kept_worst': min(inter) if inter else 1.0,
            'art_kept_worst': min(art) if art else 1.0,
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
