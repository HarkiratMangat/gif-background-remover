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

  python3 scripts/harness/render_baseline.py --out base.json --set standard
  python3 scripts/harness/render_baseline.py --compare base.json new.json
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populations import iter_assets

ROOT = "/Applications/Claude Code/Gif-Background-Remover"
DEFAULT_SCRIPT = os.path.join(ROOT, 'scripts/remove_gif_background.py')
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
    'standard': dict(labelled=None, alphas=None, sprites=40, corpus=None),
    'fast': dict(labelled=8, alphas=8, sprites=8),
    'full': dict(labelled=None, alphas=None, sprites=None, corpus=None, emoji=None),
}


def fingerprint(path):
    from PIL import Image
    import numpy as np
    im = Image.open(path)
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


def spread(items, k):
    if k is None or k >= len(items):
        return items
    return [items[i * len(items) // k] for i in range(k)]


def collect(setname):
    plan = SETS[setname]; out = []
    for pop, k in plan.items():
        rows = [(key, p, pop, lab) for key, p, pop2, lab in iter_assets([pop])]
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
    for i, (key, path, pop, lab) in enumerate(assets):
        ext = os.path.splitext(path)[1].lower()
        dst = os.path.join(tmp, f"{i:04d}{ext if ext in ('.gif','.png','.webp','.avif') else '.gif'}")
        rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, ROOT)}
        try:
            r = subprocess.run([sys.executable, a.script, path, dst, '--auto'],
                               capture_output=True, text=True, timeout=600)
            rec['returncode'] = r.returncode
            tail = [l for l in (r.stdout + r.stderr).splitlines()
                    if any(t in l for t in ('ART LOSS', 'survival', 'not applicable',
                                            'output_is_empty', 'refus', 'Error', 'error'))]
            rec['signal_lines'] = tail[-6:]
            if os.path.exists(dst):
                rec.update(fingerprint(dst))
                os.remove(dst)
            else:
                rec['no_output'] = True
        except subprocess.TimeoutExpired:
            rec['error'] = 'timeout'
        except Exception as e:
            rec['error'] = f"{type(e).__name__}: {e}"
        out[key] = rec
        # Written EVERY asset, not every tenth: the partial file is the only
        # honest progress signal, and a cadence of 10 made a 24-asset run look
        # stalled at 1 record for two minutes.
        json.dump(out, open(partial, 'w'), indent=1)
        print(f"  {i+1}/{len(assets)} {time.time()-t0:.0f}s {key[:60]}", flush=True)
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
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'))
    a = ap.parse_args()
    if a.compare:
        compare(*a.compare)
    elif a.out:
        run(a)
    else:
        ap.error('need --out or --compare A B')
