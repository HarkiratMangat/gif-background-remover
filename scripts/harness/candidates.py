#!/usr/bin/env python3
"""Candidate hardness measures for the packs the plateau-cliff ratio misses.

Scored against ALL five populations via populations.py, per-pack. Exploration
only -- anything that survives here must then be re-measured through analyze().

The four candidates and what each is a hypothesis ABOUT:

  cliff_raw   reproduction of the shipped measure, so a difference is attributable.
  cliff_op    the same measure with every step and flatness window confined to
              OPAQUE pixels. Hypothesis: on a hard-alpha sprite sheet the shipped
              measure counts art->padding boundary steps, whose art side is a 1px
              outline and therefore never a cliff, so the sheet's own silhouette
              drags the ratio down.
  pal16       share of opaque pixels covered by the 16 most common RGB values.
              Hypothesis: a small flat palette is what pixel art IS.
  ramp        share of opaque pixels that are the middle of a monotone 3-pixel
              colour ramp. Hypothesis: an intermediate pixel between two colours
              is antialiasing by construction, and 1:1 pixel art has none -- a
              margin of KIND, not of degree, and it does not care about block size.
  ncol_comp   distinct colours over the COMPOSITED frame -- the image a viewer
              actually sees -- rather than over the opaque pixels only. `ncol`
              counts alpha==255 pixels, and that is the same rock the four
              discriminators before the cliff ratio died on: a flat-fill vector
              icon keeps its antialiasing entirely in its partial-alpha edge, so
              excluding those pixels makes it look like a 35-colour palette.
              Compositing is what SS28.5 already requires of every hardness
              measure, for exactly this reason.
  ⚠️ rare_frac / rare_mass / k99_frac / min_share are ALL FALSIFIED -- kept for the
     same reason cliff_op is, so nobody re-derives them. `min_share` scored recall
     0.9389 -> 0.9722 with ZERO new false positives over 148 antialiased assets and
     is a SIZE PROXY: `art_px <= 2000`, a rule with no colour statistic in it,
     scores 0.9833, and inside the size-matched band of 400-3,000 art pixels the
     corpus holds 99 pixel-art assets and exactly ONE antialiased one. Constructing
     the missing population -- real antialiased icons at sprite scale, quantized to
     a realistic palette -- false-positives it on 11% at 32 colours and 30% at 16.
     Do not ship any of them. references/lessons.md SS29.12

  rare_frac   share of the palette that is RARE -- distinct composited colours
              carrying under 0.2% of the art pixels, over the total distinct
              count. Hypothesis: a hand-picked pixel-art palette has no rare
              entries at all, because every colour in it is a FILL somewhere,
              while machine antialiasing manufactures intermediates that exist
              only along one edge and therefore carry almost no pixel mass. This
              is the one question the colour COUNT cannot ask: at 21 colours a
              1:1 sprite and a heavily quantized sticker are indistinguishable
              by count, and differ completely by how that mass is distributed.
  rare_mass   the pixel mass those rare colours carry, rather than their share
              of the palette -- the same hypothesis measured on the other axis.
  k99_frac    smallest number of colours covering 99% of art pixels, over the
              total. The scale-free version of rare_frac.
  min_share   the smallest share of art pixels any single composited colour
              carries. rare_frac's threshold expressed as a sweepable quantity.
  art_px      how many art pixels that share was computed over. Load-bearing,
              not bookkeeping: below 1/share pixels the rarest colour clears any
              share threshold with a single pixel, so min_share passes VACUOUSLY
              on small art and must not be read without it.
"""
import argparse
import concurrent.futures as cf, json, os, sys, time, warnings, collections
import numpy as np
from PIL import Image
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populations import iter_assets, score

STRONG, MINP = 40, 2


def _lines(rgb, op):
    """yield (c, o, axis) for row-major and column-major views.

    The axis TAG is not decoration: an earlier version inferred it from
    `c.shape[0] == rgb.shape[0]`, which is true of BOTH views on a square image,
    and 512x512 and 32x32 are the two commonest sizes in these corpora.
    """
    yield rgb.astype(np.int16), op, 0
    yield np.ascontiguousarray(rgb.transpose(1, 0, 2)).astype(np.int16), np.ascontiguousarray(op.T), 1


def cliff(rgb, op=None, strong=STRONG, min_plateau=MINP):
    """(ratio, n). `op` restricts every step and its flatness window to opaque pixels."""
    if op is None:
        m = (rgb != rgb[0, 0]).any(axis=2)
        ys, xs = np.where(m)
        if ys.size >= 64:
            rgb = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        op = np.ones(rgb.shape[:2], bool)
    good = total = 0
    for c, o, _ax in _lines(rgb, op):
        n = c.shape[1]
        if n < 2 * min_plateau + 2:
            continue
        step = (np.abs(np.diff(c, axis=1)).max(axis=2) >= strong) & o[:, :-1] & o[:, 1:]
        if not step.any():
            continue
        flat = np.ones_like(step)
        for j in range(1, min_plateau):
            left = np.zeros_like(step)
            left[:, j:] = (c[:, j:-1] == c[:, :-1 - j]).all(axis=2) & o[:, j:-1] & o[:, :-1 - j]
            right = np.zeros_like(step)
            right[:, :n - 1 - j] = ((c[:, 1:n - j] == c[:, 1 + j:]).all(axis=2)
                                    & o[:, 1:n - j] & o[:, 1 + j:])
            flat &= left & right
        total += int(step.sum())
        good += int((step & flat).sum())
    return (good / max(total, 1)), total


def palette_share(rgb, op, top=16):
    px = rgb[op]
    if px.size == 0:
        return None, None
    packed = (px[:, 0].astype(np.uint32) << 16) | (px[:, 1].astype(np.uint32) << 8) | px[:, 2]
    vals, cnt = np.unique(packed, return_counts=True)
    cnt.sort()
    return float(cnt[::-1][:top].sum() / cnt.sum()), int(vals.size)


def ramp_frac(rgb, op, gap=30, tol=12):
    """Share of opaque pixels sitting strictly between two neighbours in colour."""
    hit = np.zeros(rgb.shape[:2], bool)
    for c, o, ax in _lines(rgb, op):
        n = c.shape[1]
        if n < 3:
            continue
        l, m, r = c[:, :-2], c[:, 1:-1], c[:, 2:]
        ok = o[:, :-2] & o[:, 1:-1] & o[:, 2:]
        d = np.abs(l - r).max(axis=2)
        # m strictly between l and r on every channel, and not equal to either end
        between = (((m - l) * (r - m)) >= 0).all(axis=2)
        interior = (np.abs(m - l).max(axis=2) >= 4) & (np.abs(m - r).max(axis=2) >= 4)
        # near the l->r segment: |(m-l) x (r-l)| small relative to |r-l|
        v, w = (r - l).astype(np.float32), (m - l).astype(np.float32)
        vn = np.linalg.norm(v, axis=2) + 1e-6
        proj = (w * v).sum(axis=2) / (vn * vn)
        resid = np.linalg.norm(w - proj[..., None] * v, axis=2)
        good = ok & (d >= gap) & between & interior & (resid <= tol)
        if ax == 0:
            hit[:, 1:-1] |= good
        else:
            hit[1:-1, :] |= good.T
    return float(hit.sum() / max(int(op.sum()), 1))


def palette_mass(comp, art, rare_share=0.002):
    """How is the palette's PIXEL MASS distributed across its entries?

    `comp` is the composited frame, `art` a bool mask of pixels that are artwork
    (alpha > 0). Returns (rare_frac, rare_mass, k99_frac, ncol).
    """
    P = ((comp[..., 0].astype(np.uint32) << 16) | (comp[..., 1].astype(np.uint32) << 8)
         | comp[..., 2])
    px = P[art]
    if px.size == 0:
        return None, None, None, None, None, None
    _, cnt = np.unique(px, return_counts=True)
    cnt = np.sort(cnt)[::-1]
    tot = float(cnt.sum())
    rare = cnt < rare_share * tot
    k99 = int(np.searchsorted(np.cumsum(cnt) / tot, 0.99) + 1)
    # min_share is the SWEEPABLE form of rare_frac: "no colour under share s" is
    # exactly min_share >= s, so reporting the minimum lets the 0.2% cut be
    # checked against the data instead of asserted.
    return (float(rare.sum() / cnt.size), float(cnt[rare].sum() / tot),
            float(k99 / cnt.size), int(cnt.size), float(cnt.min() / tot), int(tot))


def bg_of(path):
    """Frame-0 corner-majority background, the same value analyze() keys on."""
    im = Image.open(path); im.seek(0)
    rgb = np.array(im.convert('RGB'))
    h, w, _ = rgb.shape
    cs = [tuple(int(v) for v in rgb[y, x]) for y, x in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1))]
    return collections.Counter(cs).most_common(1)[0][0]


def frames(path, max_samples=6):
    im = Image.open(path)
    n = getattr(im, 'n_frames', 1)
    idxs = sorted(set(np.linspace(0, n - 1, min(n, max_samples)).astype(int).tolist()))
    out = []
    for i in idxs:
        im.seek(i)
        a = np.array(im.convert('RGBA'))
        out.append((np.ascontiguousarray(a[..., :3]), a[..., 3]))
    return out


def composite(rgb, al, bg):
    """What the viewer sees: art over `bg` wherever alpha is partial (SS28.5)."""
    if not ((al > 0) & (al < 255)).any():
        return rgb
    f = al[..., None].astype(np.float32) / 255.0
    return (rgb.astype(np.float32) * f + np.asarray(bg, np.float32) * (1.0 - f)
            ).round().clip(0, 255).astype(np.uint8)


def measure(path):
    rows = []
    bg = bg_of(path)
    for rgb, al in frames(path):
        op = al == 255
        if not op.any():
            op = al > 0
        if not op.any():
            continue
        cr, cn = cliff(rgb)
        orr, on = cliff(rgb, op)
        p16, ncol = palette_share(rgb, op)
        comp = composite(rgb, al, bg)
        _, ncomp = palette_share(comp, np.ones(comp.shape[:2], bool))
        art = al > 0
        if not art.any():
            art = np.ones(al.shape, bool)
        rf, rm, kf, nart, mshare, npix = palette_mass(comp, art)
        rows.append(dict(cliff_raw=cr, cliff_raw_n=cn, cliff_op=orr, cliff_op_n=on,
                         pal16=p16, ncol=ncol, ncol_comp=ncomp, ramp=ramp_frac(rgb, op),
                         opaque_frac=float(op.mean()), rare_frac=rf, rare_mass=rm,
                         k99_frac=kf, ncol_art=nart, min_share=mshare, art_px=npix))
    if not rows:
        return {}
    med = lambda k: float(np.median([r[k] for r in rows if r.get(k) is not None]))
    return {k: round(med(k), 4) for k in rows[0]}


def _measure_one(row):
    """Module level ON PURPOSE. `ProcessPoolExecutor` pickles the callable, and macOS
    uses `spawn`, so a nested `def` inside `__main__` fails every task with
    "Can't pickle local object". The parallel default only works because this is here."""
    k, path, pop, lab = row
    rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, os.getcwd())}
    try:
        rec.update(measure(path))
    except Exception as e:
        rec['error'] = f"{type(e).__name__}: {e}"
    return k, rec


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--only', default=None)
    ap.add_argument('--jobs', '-j', type=int, default=min(8, os.cpu_count() or 1),
                    help='parallel workers. Defaults to %(default)s; pass 1 to force serial. '
                         'PROCESSES here, not threads: unlike the render harness this measures '
                         'in-process with numpy rather than shelling out, so the GIL is held. '
                         '⚠️ Timings under --jobs > 1 are wall clock for the RUN, not per-asset.')
    a = ap.parse_args()
    assets = list(iter_assets(a.only.split(',') if a.only else None, include_excluded=True))
    print(f"{len(assets)} assets, {a.jobs} worker(s)", flush=True)
    out, t0 = {}, time.time()

    def emit(i, k, rec):
        out[k] = rec
        if i % 50 == 0:
            json.dump(out, open(a.out + '.partial', 'w'), indent=1)
            print(f"  {i}/{len(assets)} {time.time()-t0:.0f}s", flush=True)

    if a.jobs > 1:
        with cf.ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for i, (k, rec) in enumerate(ex.map(_measure_one, assets, chunksize=1)):
                emit(i, k, rec)
    else:
        for i, row in enumerate(assets):
            k, rec = _measure_one(row)
            emit(i, k, rec)
    json.dump({'_seconds': round(time.time() - t0, 1), 'records': out}, open(a.out, 'w'), indent=1)
    os.path.exists(a.out + '.partial') and os.remove(a.out + '.partial')
    print(f"wrote {a.out} in {time.time()-t0:.0f}s")
