#!/usr/bin/env python3
"""Baseline what the tool RENDERS, not just what it recommends.

The standing corpus check ran --recommend over the labelled set and diffed the
suggested command. That catches a changed DECISION and cannot catch a changed
RENDER: only the assets whose recommendation moved were ever actually processed,
so a flag combination that produces a wrong IMAGE on any other asset passed
silently. This renders every asset through the real CLI in --auto mode -- the
autonomous entry point, so the baseline covers the path autonomy actually uses
-- and fingerprints the output.

Per asset it stores: the CLI exit code, a sha256 over the concatenated ALPHA
planes of every output frame, the per-frame opaque-pixel counts, dimensions,
frame count, output bytes, and the ART LOSS / survival lines --auto prints. The
alpha checksum is the load-bearing field: alpha IS the product of this tool.

EVERY ASSET IS RENDERED TWICE: once at native size, and once through
--resize-max-dim at half the source's larger side, recorded under a second key
suffixed ` [resize]`. The second pass is not padding. --auto with no other flag
cannot express the single most destructive thing a wrong --pixel-art verdict
does -- switch the resize filter from LANCZOS to nearest-neighbour -- so a
verdict that only matters on resize had no baseline at all. Measured: the
v5.5.0 hardness change moved 8 verdicts inside the 106-asset set and every
output came back byte-identical, because all 8 were already-transparent sources
whose removal is confined to their own alpha. "0 changed" partly meant "this
set cannot express the change" (references/lessons.md SS29.10).

  python3 scripts/harness/render_baseline.py --out base.json --set standard
  python3 scripts/harness/render_baseline.py --compare base.json new.json
"""
import argparse
import concurrent.futures as cf, hashlib, json, os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populations import iter_assets

ROOT = "/Applications/Claude Code/Gif-Background-Remover"
DEFAULT_SCRIPT = os.path.join(ROOT, 'scripts/remove_gif_background.py')
from machine import default_jobs as _default_jobs   # noqa: E402
DEFAULT_JOBS = _default_jobs()
# ⚠️ --script is REQUIRED for a comparison run, and this is why: the first
# attempt at a pre-fix baseline read the working-tree script on every asset, and
# the working tree was edited 15 minutes into the run. Forty assets were measured
# against the old code and the rest against the new, and nothing in the output
# said so -- a "baseline" that silently straddles the change it exists to
# measure. Point --script at a pristine copy (git show HEAD:… > /tmp/pre.py).
SCRIPT = DEFAULT_SCRIPT
# Only the alpha-carrying populations can regress on a source-transparency
# change, and `labelled` is the opaque control that must NOT move.
SETS = {
    # `trial` is in BOTH sets and is never subsampled. Until 2026-08-20 the render gate did
    # not contain a single asset a human had complained about, which is why a change to the
    # incidental-region verdict could come back "214 vs 214, 0 changed" while visibly fixing
    # the asset that motivated it. These 6 are the ones with a complaint attached.
    'standard': dict(labelled=None, alphas=None, sprites=40, corpus=None, trial=None),
    'fast': dict(labelled=8, alphas=8, sprites=8, trial=None),
    'full': dict(labelled=None, alphas=None, sprites=None, corpus=None, emoji=None),
}


def fingerprint(path):
    from PIL import Image
    import numpy as np
    # Context-managed: the caller deletes this path immediately afterwards, and an
    # un-closed handle leaks one descriptor per asset (212 over a `standard` run with
    # the resize pass) and blocks the delete outright on Windows.
    with Image.open(path) as im:
        return _fingerprint_open(im, path)


def _fingerprint_open(im, path):
    from PIL import Image
    import numpy as np
    n = getattr(im, 'n_frames', 1)
    h = hashlib.sha256(); counts = []; size = None
    for i in range(n):
        im.seek(i)
        a = np.array(im.convert('RGBA'))
        size = (a.shape[1], a.shape[0])
        alpha = np.ascontiguousarray(a[..., 3])
        h.update(alpha.tobytes())
        counts.append(int((alpha > 0).sum()))
    return {'alpha_sha256': h.hexdigest(), 'opaque_per_frame': counts,
            'opaque_total': sum(counts), 'size': size, 'frames': n,
            'bytes': os.path.getsize(path)}


def render_once(script, src, dst, extra=()):
    """Render `src` -> `dst` through the real CLI and fingerprint the result.

    ⚠️ `dst` is DELETED FIRST, and that is the load-bearing line. Both passes share one
    output path, and the native pass used to remove the file only AFTER fingerprinting it
    -- so a fingerprint that raised (Pillow errors on a mid-sequence seek for some
    sources; see references/lessons.md §9) left the native output in place, and if the
    resize subprocess then wrote nothing, `os.path.exists(dst)` was True and the NATIVE
    alpha plane was recorded under the ` [resize]` key. A release gate reporting a pass
    for a render that never ran. Written once, for both passes, so the guarantee cannot
    hold in one and not the other.
    """
    rec = {}
    if os.path.exists(dst):
        os.remove(dst)
    try:
        r = subprocess.run([sys.executable, script, src, dst, '--auto'] + list(extra),
                           capture_output=True, text=True, timeout=600)
        rec['returncode'] = r.returncode
        rec['signal_lines'] = [l for l in (r.stdout + r.stderr).splitlines()
                               if any(t in l for t in ('ART LOSS', 'survival', 'not applicable',
                                                       'output_is_empty', 'refus', 'Error',
                                                       'error'))][-6:]
        if os.path.exists(dst):
            try:
                rec.update(fingerprint(dst))
            finally:
                os.remove(dst)
        else:
            rec['no_output'] = True
    except subprocess.TimeoutExpired:
        rec['error'] = 'timeout'
    except Exception as e:
        rec['error'] = f"{type(e).__name__}: {e}"
    return rec


def resize_target(path):
    """Half the source's larger side, or None when the source is too small to halve.

    Half is not arbitrary: a nearest-neighbour downscale to an odd fraction drops
    whole pixel rows and any filter looks bad; at exactly 1/2 nearest and LANCZOS
    disagree only where the artwork actually has detail, which is the difference
    this pass exists to see.
    """
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    big = max(w, h)
    return (big // 2) if big >= 64 else None


def spread(items, k):
    if k is None or k >= len(items):
        return items
    return [items[i * len(items) // k] for i in range(k)]


def collect(setname):
    plan = SETS[setname]; out = []
    for pop, k in plan.items():
        # include_excluded, and it is not a copy-paste of the scoring call. Those
        # 31 assets are EXCLUDED FROM SCORING on purpose -- 31 flat overlay plates
        # would hand any hard-edge rule 31 free true negatives that test nothing --
        # but they are exactly the degenerate inputs a RENDER gate wants, and this
        # harness had been inheriting the scoring default by accident. Measured
        # 2026-08-18: the flat 1-colour tile correctly hits `_refuse_empty_render`
        # (rc=1, nothing written), and two 1800x1200 overlay plates render at 88%
        # and 93% of their source alpha -- real loss on assets nobody had rendered.
        rows = [(key, p, pop, lab)
                for key, p, pop2, lab in iter_assets([pop], include_excluded=True)]
        if pop == 'sprites' and k:
            # spread ACROSS packs, not across the flat sorted list -- 78% of this
            # population is one pack, so a flat spread is that pack's baseline.
            packs = {}
            for r in rows:
                packs.setdefault(r[0].split('/', 1)[1].split('/')[0], []).append(r)
            per = max(1, k // max(1, len(packs)))
            rows = [x for pk in sorted(packs) for x in spread(packs[pk], per)]
        else:
            rows = spread(rows, k)
        out += rows
    return out


def run(a):
    assets = collect(a.set)
    # ⚠️ SNAPSHOT THE SCRIPT. Passing a path is not enough and this is the second
    # time it bit, an hour apart: the run re-reads the file for every asset, so any
    # edit mid-run silently splits the results across two versions of the code.
    # The first time it was the working tree; the second time it was the working
    # tree AGAIN, during a run whose whole purpose was to measure the edits being
    # made. "Be careful not to edit during a run" is not a fix -- freezing a copy
    # here is, because it cannot be forgotten.
    snap = os.path.join(tempfile.mkdtemp(prefix='script_snapshot_'), 'under_test.py')
    shutil.copy2(a.script, snap)
    src_digest = hashlib.sha256(open(a.script, 'rb').read()).hexdigest()[:12]
    a.script = snap
    print(f"{len(assets)} assets, set={a.set}, script frozen from {src_digest}", flush=True)
    out = {}; t0 = time.time(); partial = a.out + '.partial'
    tmp = tempfile.mkdtemp(prefix='render_baseline_')

    def one(i_row):
        """Everything for a single asset: the native render and, unless disabled, the
        resize pass. Returns [(key, rec), ...]. Each asset owns its own `dst` path,
        indexed by position, so two workers can never collide on the same file."""
        i, (key, path, pop, lab) = i_row
        ext = os.path.splitext(path)[1].lower()
        dst = os.path.join(tmp, f"{i:04d}{ext if ext in ('.gif','.png','.webp','.avif') else '.gif'}")
        rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, ROOT)}
        rec.update(render_once(a.script, path, dst))
        pairs = [(key, rec)]
        # Second pass, same asset, through --resize-max-dim. Recorded under its own
        # key rather than as extra fields on the first record so the schema stays
        # uniform and `compare` needs no special case: against a pre-resize baseline
        # these simply show up as "only in B", which is the truth.
        if not a.no_resize_pass:
            dim = resize_target(path)
            rrec = {'pop': pop, 'label': lab, 'path': rec['path'], 'resize_max_dim': dim}
            if dim is None:
                rrec['skipped'] = 'source smaller than 64px'
            else:
                rrec.update(render_once(a.script, path, dst, ['--resize-max-dim', str(dim)]))
            pairs.append((key + ' [resize]', rrec))
        return pairs

    # ⚠️ THREADS, not processes, and that is deliberate. Every unit of work here is a
    # `subprocess.run` of the CLI, so the GIL is released for essentially the whole
    # duration and threads get the same speedup a process pool would -- without the
    # macOS `spawn` re-import trap that silently killed run_populations.py's first
    # parallel version (the module re-executed its argparse at import and every worker
    # died, and the only reason it was caught is that no output file appeared).
    done = 0
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = {ex.submit(one, (i, row)): row[0] for i, row in enumerate(assets)}
        for f in cf.as_completed(futs):
            for k, rec in f.result():
                out[k] = rec
            done += 1
            # Written EVERY asset, not every tenth: the partial file is the only
            # honest progress signal, and a cadence of 10 made a 24-asset run look
            # stalled at 1 record for two minutes.
            json.dump(out, open(partial, 'w'), indent=1)
            print(f"  {done}/{len(assets)} {time.time()-t0:.0f}s {futs[f][:60]}", flush=True)
    json.dump({'_set': a.set, '_script': a.script, '_script_sha256_12': src_digest,
               '_seconds': round(time.time() - t0, 1), 'records': out},
              open(a.out, 'w'), indent=1)
    if os.path.exists(partial):
        os.remove(partial)
    print(f"wrote {a.out} in {time.time()-t0:.0f}s")


def compare(pa, pb):
    A = json.load(open(pa))['records']; B = json.load(open(pb))['records']
    only_a = sorted(set(A) - set(B)); only_b = sorted(set(B) - set(A))
    changed = []
    for k in sorted(set(A) & set(B)):
        a, b = A[k], B[k]
        d = {}
        for f in ('alpha_sha256', 'opaque_total', 'returncode', 'frames', 'size', 'no_output'):
            if a.get(f) != b.get(f):
                d[f] = (a.get(f), b.get(f))
        if d:
            changed.append((k, a, b, d))
    print(f"{len(A)} vs {len(B)} records; {len(changed)} changed, "
          f"{len(only_a)} only in A, {len(only_b)} only in B")
    for k, a, b, d in changed:
        head = f"  {k}  [{a.get('label')}/{a.get('pop')}]"
        if 'opaque_total' in d:
            x, y = d['opaque_total']
            pct = (100.0 * y / x) if x else float('nan')
            head += f"  opaque {x} -> {y} ({pct:.1f}%)"
        elif 'alpha_sha256' in d:
            head += "  alpha CHANGED (same opaque count)"
        for f in ('returncode', 'no_output', 'frames', 'size'):
            if f in d:
                head += f"  {f} {d[f][0]} -> {d[f][1]}"
        print(head)
    # A summary that cannot be read as "nothing happened" when 0 assets rendered.
    rendered = sum(1 for v in B.values() if v.get('alpha_sha256'))
    print(f"\n{rendered}/{len(B)} of B actually produced an output file.")
    return changed


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out'); ap.add_argument('--set', default='standard', choices=list(SETS))
    ap.add_argument('--script', default=DEFAULT_SCRIPT,
                    help='the script under test; pass a pristine copy for a baseline')
    ap.add_argument('--no-resize-pass', action='store_true',
                    help='skip the --resize-max-dim second pass (halves runtime, and blinds '
                         'the gate to the nearest-vs-LANCZOS filter switch)')
    ap.add_argument('--jobs', type=int, default=DEFAULT_JOBS,
                    help='parallel renders. Defaults to %(default)s (min(8, cpu_count)); pass 1 '
                         'to force serial. Each unit is a CLI subprocess, so THREADS scale it '
                         'without the macOS spawn re-import trap. Measured on the fast set: '
                         '440s serial -> 212s at 8 (2.2x, floored by one 212s asset), and '
                         '--jobs 1 vs --jobs 8 gives 46 vs 46 records, 0 changed. ⚠️ Timings '
                         'printed under --jobs > 1 are wall clock for the RUN, never per-asset '
                         'cost, and must not be quoted as the latter.')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'))
    a = ap.parse_args()
    if a.compare:
        compare(*a.compare)
    elif a.out:
        run(a)
    else:
        ap.error('need --out or --compare A B')
