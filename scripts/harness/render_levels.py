#!/usr/bin/env python3
"""Render assets through the REAL CLI at FORCED erosion levels, and score every output.

⚠️ WHY THIS EXISTS, and why `run_populations.py` and `render_baseline.py` could not answer the
question it answers. Both of those measure the tool's CURRENT decision: one scores `analyze()`,
the other fingerprints what `--auto` chose. Neither can say what the tool WOULD have produced at
a level it did not pick -- and that counterfactual is the only thing that can settle "is this
level the right one?". Two erosion cost terms were built, measured against the corpus and
rejected (references/lessons.md SS37.1, SS37.2) precisely because a corpus scored at the
decision the tool already makes can only tell you the rule agrees with itself.

Rendering every asset at levels 0, 1, 2 AND 3 costs four renders per asset and buys something no
single-decision measurement can: **any policy that maps an asset to a level in the measured set
can then be evaluated EXACTLY, with no further rendering.** That is what turned the erosion
question from an argument into a table (SS37.4): 112 assets x 4 levels = 448 renders, and three
facts fell straight out of it -- no asset anywhere lost less artwork at a higher level, going
above 1 bought at most 0.021 of background removal, and going from 0 to 1 buys up to +0.622.

Also useful for the OTHER half of the same finding: `--levels 0` isolates keyer damage from
erosion damage exactly, because whatever loss survives erosion 0 was never erosion's.

⚠️ `score_outputs` is NOT valid on the `alphas` population -- it derives ground truth from the
source's RGB, which under `alpha == 0` is encoder noise (SS36). Read that population's records
as a DETERMINISM check only; its real gate is `render_baseline.py`'s alpha fingerprint.

Usage:
  render_levels.py --out X.json --pops labelled,trial,corpus,dark_bg,alphas --levels 0,1,2,3
                   [--keys-file only-these-keys.txt] [--only substring] [--sample N]
                   [--script /path/to/pristine.py] [--out-ext .webp] [--jobs N]

`auto` is a valid level and means "let the tool decide", which is how a PRE/POST pair is taken.
The script under test is FROZEN at startup (scripts/harness/snapshot.py), so a long run does not
block editing the file it is measuring.
"""
import argparse, concurrent.futures as cf, json, os, re, subprocess, sys, tempfile, time

HARNESS = "/Applications/Claude Code/Gif-Background-Remover/scripts/harness"
sys.path.insert(0, HARNESS)
from populations import iter_assets              # noqa: E402
from snapshot import freeze                      # noqa: E402
from machine import default_jobs                 # noqa: E402
import score_outputs                             # noqa: E402

ROOT = "/Applications/Claude Code/Gif-Background-Remover"
SCRIPT = os.path.join(ROOT, "scripts/remove_gif_background.py")

CURVE = re.compile(r"erosion calibrated against this asset's own curve \(([^)]*)\)\s*->\s*(\d+)")
PROBE = re.compile(r"erosion probe beyond the selectable range:\s*(\S+)")
SKIP = re.compile(r"erosion auto-calibration SKIPPED")
NONCONV = re.compile(r"NON-CONVERGENT|not a fringe floor")


def parse_curve(err):
    m = CURVE.search(err)
    out = {}
    if m:
        for part in m.group(1).split(','):
            k, _, v = part.strip().partition(':')
            try:
                out[int(k)] = float(v)
            except ValueError:
                pass
        return out, int(m.group(2))
    return None, None


def one(script, key, path, pop, lab, levels, tmp, out_ext=None):
    rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, ROOT), 'levels': {}}
    ext = out_ext or os.path.splitext(path)[1].lower()
    for lv in levels:
        dst = os.path.join(tmp, f"{abs(hash(key)):016x}_{lv}{ext if ext in ('.gif','.png','.webp','.avif') else '.gif'}")
        cmd = [sys.executable, script, path, dst, '--auto']
        if lv != 'auto':
            cmd += ['--edge-cleanup-erosion', str(lv)]
        r = {}
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            err = p.stdout + p.stderr
            r['rc'] = p.returncode
            curve, picked = parse_curve(err)
            if curve:
                r['curve'] = curve
                r['picked'] = picked
            mp = PROBE.search(err)
            if mp:
                r['probe'] = mp.group(1)
            if SKIP.search(err):
                r['cal_skipped'] = True
            if NONCONV.search(err):
                r['nonconvergent'] = True
            r['erosion_lines'] = [l for l in err.splitlines()
                                  if 'erosion' in l.lower() or 'DISAGREEMENT' in l][:8]
            if os.path.exists(dst):
                try:
                    r['score'] = score_outputs.score(path, dst)
                finally:
                    os.remove(dst)
            else:
                r['no_output'] = True
        except subprocess.TimeoutExpired:
            r['error'] = 'timeout'
        except Exception as e:
            r['error'] = f"{type(e).__name__}: {e}"
        rec['levels'][str(lv)] = r
    return key, rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--pops', default='labelled,trial,corpus,dark_bg,alphas')
    ap.add_argument('--levels', default='auto')
    ap.add_argument('--only', default=None)
    ap.add_argument('--keys-file', default=None)
    ap.add_argument('--script', default=SCRIPT)
    ap.add_argument('--out-ext', default=None, help='force the output container, e.g. .webp')
    ap.add_argument('--sample', type=int, default=None)
    ap.add_argument('--jobs', type=int, default=None)
    a = ap.parse_args()
    levels = [x if x == 'auto' else int(x) for x in a.levels.split(',')]
    pops = a.pops.split(',')
    rows = [(k, p, pop, lab) for k, p, pop, lab in iter_assets(pops, include_excluded=True)]
    if a.keys_file:
        want = set(l.strip() for l in open(a.keys_file) if l.strip())
        rows = [r for r in rows if r[0] in want]
        missing = want - {r[0] for r in rows}
        assert not missing, f'keys not found: {sorted(missing)[:5]}'
    if a.only:
        rows = [r for r in rows if a.only in r[0]]
    if a.sample and a.sample < len(rows):
        rows = [rows[i * len(rows) // a.sample] for i in range(a.sample)]
    jobs = a.jobs or default_jobs()
    script, digest = freeze(a.script)
    tmp = tempfile.mkdtemp(prefix='erprobe_')
    print(f"{len(rows)} assets x {len(levels)} levels, jobs={jobs}, script {digest}", flush=True)
    out = {}
    t0 = time.time()
    partial = a.out + '.partial'
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = [ex.submit(one, script, k, p, pop, lab, levels, tmp, a.out_ext) for k, p, pop, lab in rows]
        for i, f in enumerate(cf.as_completed(futs), 1):
            k, rec = f.result()
            out[k] = rec
            json.dump(out, open(partial, 'w'), indent=1)
            print(f"  {i}/{len(rows)} {time.time()-t0:.0f}s {k[:70]}", flush=True)
    json.dump({'_script_sha12': digest, '_levels': [str(x) for x in levels],
               '_pops': pops, '_seconds': round(time.time() - t0, 1), 'records': out},
              open(a.out, 'w'), indent=1)
    if os.path.exists(partial):
        os.remove(partial)
    print(f"wrote {a.out} in {time.time()-t0:.0f}s")


if __name__ == '__main__':
    main()
