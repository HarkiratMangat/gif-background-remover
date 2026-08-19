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
ap.add_argument('--script', default=os.path.join(ROOT, 'scripts/remove_gif_background.py'))
a = ap.parse_args()
pops = a.only.split(',') if a.only else None
mod = load(a.script, 'under_test')
assets = list(iter_assets(pops, include_excluded=True))
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
        rec['frames'] = r.get('frame_count')
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
