#!/usr/bin/env python3
"""Score every population through the PRODUCT entry point, analyze().

Replaces final_run.py + sprite_run.py, whose directory lists are now in
populations.py. Two deliberate differences from those scripts:

  * --out is REQUIRED and the file is written as <out>.partial until the run
    finishes, then renamed. final_run.py wrote a fixed path, so a stale result
    was indistinguishable from a finished run -- and a "DONE" was reported off
    one. A missing <out> plus a present <out>.partial now says "still running".
  * every record carries the label from populations.py, so scoring never has to
    re-derive ground truth from a directory name.

  python3 scripts/harness/run_populations.py --out run-2026-08-18.json
  python3 scripts/harness/run_populations.py --only sprites,alphas --out x.json
"""
import argparse, importlib.util, json, os, sys, time, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from populations import iter_assets, score, POPULATIONS

ROOT = "/Applications/Claude Code/Gif-Background-Remover"
FIELDS = ('appears_hard_edged', 'plateau_cliff_ratio', 'plateau_cliff_samples', 'change_line_density',
          'composited_color_count', 'band_measures_are_vacuous',
          'source_background_already_transparent',
          'ratio_max_across_frames', 'antialiasing_blend_ratio', 'hard_edged_reasons',
          'hard_edged_suppressed_notes', 'measured_on_alpha_composite', 'alpha_only_source',
          'source_alpha_levels', 'source_is_hard_alpha_cutout')


def load(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m


ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
ap.add_argument('--only', default=None, help='comma-separated population names')
# The corpus is 774 assets and ~42 minutes, and pruning barely moved that: the 212
# measurement-identical sprites removed on 2026-08-19 were worth 3.6% of runtime, because
# cost is dominated by `emoji` (122 large animated GIFs, 65.8%). Deleting evidence is the
# wrong lever -- 122 negatives are what make "0 false positives" a claim, and 20 would not
# be. Subsampling for ITERATION is the right one; the release gate still runs everything.
ap.add_argument('--sample', type=int, default=None,
                help='score at most N assets per population, spread evenly through each. For '
                     'iteration only -- never quote a recall or specificity figure from a '
                     'sampled run, and never use one as a release gate.')
ap.add_argument('--script', default=os.path.join(ROOT, 'scripts/remove_gif_background.py'))
a = ap.parse_args()
pops = a.only.split(',') if a.only else None
mod = load(a.script, 'under_test')
assets = list(iter_assets(pops, include_excluded=True))
if a.sample:
    bypop = {}
    for row in assets:
        bypop.setdefault(row[2], []).append(row)
    assets = [g[i * len(g) // min(a.sample, len(g))]
              for g in bypop.values() for i in range(min(a.sample, len(g)))]
    print(f"⚠️  SAMPLED: {len(assets)} assets, at most {a.sample} per population. "
          f"Figures from this run are for iteration only.", flush=True)
print(f"{len(assets)} assets; script={a.script}", flush=True)
out, t0 = {}, time.time()
partial = a.out + '.partial'
for i, (k, path, pop, lab) in enumerate(assets):
    rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, ROOT)}
    try:
        r = mod.analyze(path)
        eh = r['edge_hardness']
        rec.update({f: eh.get(f) for f in FIELDS})
        rec['pred'] = eh.get('appears_hard_edged')
        # 'frame_count' is not a key analyze() returns -- it is 'n_frames_total' -- so this
        # field was None on all 719 records, and a question about animated assets silently
        # answered "zero". Caught 2026-08-19 by sanity-checking a count before acting on it.
        rec['frames'] = r.get('n_frames_total')
    # SystemExit, not just Exception: the script under test raises it in several places
    # (_refuse_empty_render, populations.check_corpora, argparse errors) and it derives from
    # BaseException, so one bad asset would kill a 45-minute run and never write <out> --
    # leaving only <out>.partial, which this file's own docstring defines as "still running".
    except (Exception, SystemExit) as e:
        rec['error'] = f"{type(e).__name__}: {e}"
    out[k] = rec
    if i % 25 == 0:
        json.dump(out, open(partial, 'w'), indent=1)
        print(f"  {i}/{len(assets)}  {time.time()-t0:.0f}s", flush=True)
json.dump({'_script': a.script, '_populations': pops or list(POPULATIONS),
           '_seconds': round(time.time() - t0, 1), '_score': score(out), 'records': out},
          open(a.out, 'w'), indent=1)
if os.path.exists(partial):
    os.remove(partial)
print(json.dumps(score(out), indent=1))
print(f"wrote {a.out} in {time.time()-t0:.0f}s")
