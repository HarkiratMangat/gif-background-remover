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
from concurrent.futures import ProcessPoolExecutor
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



# ⚠️ EVERYTHING runtime lives under main(). On macOS multiprocessing uses SPAWN, so each worker
# RE-IMPORTS this module -- and with the argparse call and the corpus scan at module level, every
# child re-parsed argv and rescanned 774 assets before dying. That is what a
# BrokenProcessPool with a 1-second wall time turned out to mean; the run reported "8 jobs: 1s",
# which reads as a 133x speedup until you notice no output file was written.
_WORKER_MOD = None


def _init_worker(script_path):
    """Load the script under test ONCE per worker, not once per asset."""
    global _WORKER_MOD
    _WORKER_MOD = load(script_path, 'under_test')


def score_one(row):
    """One asset in, one record out. Pure: reads a file, returns a dict, shares no state."""
    k, path, pop, lab = row
    rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, ROOT)}
    try:
        r = _WORKER_MOD.analyze(path)
        eh = r['edge_hardness']
        rec.update({f: eh.get(f) for f in FIELDS})
        rec['pred'] = eh.get('appears_hard_edged')
        rec['frames'] = r.get('n_frames_total')
    except (Exception, SystemExit) as e:
        rec['error'] = f"{type(e).__name__}: {e}"
    return k, rec


def main():
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
    # The 774 assets are INDEPENDENT -- analyze() reads a file and returns a dict, touching no
    # shared state -- so the serial loop was leaving 7 of 8 cores idle for 42 minutes. This is
    # the real lever: micro-optimising analyze() bought 10% for a packed np.unique and every
    # further percent means restructuring per-frame passes on a pipeline that has already
    # produced three data-loss classes. Parallelism costs nothing in the product at all.
    # maxtasksperchild is not tuning: a worker that has decoded a 3840x2160 sheet holds that
    # memory, and 8 of them at once is how a machine starts swapping.
    ap.add_argument('--jobs', '-j', type=int, default=1,
                    help='parallel worker processes (default 1). Results are identical either '
                         'way -- each asset is scored independently -- but ordering in the output '
                         'dict follows completion, so compare by KEY, never by position.')
    a = ap.parse_args()
    pops = a.only.split(',') if a.only else None
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


    def _score_one(row):
        """Worker body: one asset in, one record out. Must stay import-safe and self-contained."""
        k, path, pop, lab = row
        rec = {'pop': pop, 'label': lab, 'path': os.path.relpath(path, ROOT)}
        try:
            m = _worker_mod()
            r = m.analyze(path)
            eh = r['edge_hardness']
            rec.update({f: eh.get(f) for f in FIELDS})
            rec['pred'] = eh.get('appears_hard_edged')
            rec['frames'] = r.get('n_frames_total')
        except (Exception, SystemExit) as e:
            rec['error'] = f"{type(e).__name__}: {e}"
        return k, rec


    _WORKER_MOD = None


    def _worker_mod():
        """Load the script under test ONCE per worker, not once per asset."""
        global _WORKER_MOD
        if _WORKER_MOD is None:
            _WORKER_MOD = load(_SCRIPT_PATH, 'under_test')
        return _WORKER_MOD
    if a.jobs > 1:
        print(f"running {a.jobs} workers", flush=True)
        # No max_tasks_per_child. It was there to bound memory, but the largest asset in the
        # corpus holds 100 MB of frames and 8 workers of those is 0.8 GB of 16 -- so it was
        # bounding nothing, while its repeated respawns hung the pool partway through a full
        # run: parent alive at 0% CPU, zero workers left, no error raised. A knob that solves
        # no measured problem and can hang the run is worse than absent.
        with ProcessPoolExecutor(max_workers=a.jobs,
                                 initializer=_init_worker, initargs=(a.script,)) as ex:
            for n, (k, rec) in enumerate(ex.map(score_one, assets, chunksize=1)):
                out[k] = rec
                if n % 25 == 0:
                    json.dump(out, open(partial, 'w'), indent=1)
                    print(f"  {n}/{len(assets)}  {time.time()-t0:.0f}s", flush=True)
    else:
        _init_worker(a.script)
        for n, row in enumerate(assets):
            k, rec = score_one(row)
            out[k] = rec
            if n % 25 == 0:
                json.dump(out, open(partial, 'w'), indent=1)
                print(f"  {n}/{len(assets)}  {time.time()-t0:.0f}s", flush=True)
    json.dump({'_script': a.script, '_populations': pops or list(POPULATIONS),
               '_seconds': round(time.time() - t0, 1), '_score': score(out), 'records': out},
              open(a.out, 'w'), indent=1)
    if os.path.exists(partial):
        os.remove(partial)
    print(json.dumps(score(out), indent=1))
    print(f"wrote {a.out} in {time.time()-t0:.0f}s")


if __name__ == '__main__':
    main()
