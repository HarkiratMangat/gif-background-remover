# `analyze()` is the program's cost, `--auto` pays it twice, and nobody could see it

**Date:** 2026-09-01
**Trigger:** A pre-merge render gate (`render_baseline.py --set fast`) took 626s + 296s on the v6.3.0 branch. Harkirat asked why, given the repo has a caching system; then asked whether any speedup reaches the shipped skill or only the tests; then asked for the CLASS rather than the instances.
**Method:** In-process instrumentation of the real `main()` by monkey-patching the module from a scratch script — after two attempts using external stopwatches produced falsified numbers. Every figure below is reproducible with the commands in §9.
**Scope:** Performance only. The v6.3.0 correctness findings are in `references/lessons.md` §48 and are not repeated here.
**Status:** No performance code was changed. This is a measurement document; the work is planned in `docs/plans/2026-09-01-analysis-cost-and-observability.md`.

---

## 1. The headline, in one table

One `--auto` invocation on `grenade.gif` (640×640, 62 frames), instrumented in-process:

| `analyze()` call | caller | cost | share of run |
|---|---|---|---|
| 1 | `recommend()` — AUTO pass 1 | 11.5s | 29% |
| 2 | `verify()` — AUTO pass 3 | 12.7s | 32% |
| | **analysis total** | **24.4s** | **61%** |
| | everything else (render, calibration, encode, I/O) | 15.6s | 39% |
| | **run total** | **40.0s** | |

**The second call is provably redundant.** Both calls receive `path=grenade.gif`, `max_samples=40`, `tolerance=15`, and return a **byte-identical result hash** (`c1036647208c8ecf`). This was established by hashing both return values, not by reading the code.

**This is the shipped skill, not the test harness.** Every `--auto` run any user makes — including every autonomous run on claude.ai — spends roughly a third of its wall time recomputing an answer it already has.

---

## 2. `analyze()` is not a cost centre; it is the cost

Measured across every entry point, same asset, in-process:

| command | `analyze()` calls | analysis time | share of runtime | total runtime |
|---|---|---|---|---|
| `--recommend` | 1 | 11.4s | **100%** | 11.4s |
| `--verify` (standalone) | 1 | 11.9s | **87%** | 13.8s |
| `--auto` | **2** | 24.1s | **61%** | 39.6s |
| plain render (explicit flags) | **0** | 0.0s | **0%** | **10.1s** |
| `--auto`, two files | 3 | 38.3s | 49% | 78.6s |

Two consequences follow, and the second is easy to miss:

1. **Every expensive entry point is a thin wrapper around one or two `analyze()` calls.** Optimising anything else is optimising the 39%.
2. **A plain render is 4× faster than `--auto`** (10.1s vs 39.6s) purely because it never analyses. That is a *routing* fact, not a code change: a session that already knows its flags should not be paying for `--auto`.

**On the two-file count of 3, not 4 — explained, not assumed.** `grenade.gif` was analysed once (pass 1) and never reached pass 3, because `--out-dir` derived a `.gif` output name and the render legitimately refused under the entirely-transparent-frame guard (frame 44 of 62). `ak47.gif` was analysed twice. The multi-file path handled the refusal correctly and reported it in its summary. **An earlier reading of this number as "multi-file `--auto` silently skips verification" was wrong and was checked before being filed.**

---

## 3. Why a naive memo would be a bug, not a speedup

The obvious fix — memoize `analyze()` and hand the same object to both callers — **changes output**. AST scan of the consumers:

| consumer | mutations of the `analyze()` result | examples |
|---|---|---|
| `verify()` | **24** | `report['dimensions_match']`, `report['checks_skipped']`, `report['leftover_background_opaque_px']`, `report['output_format']`, `report['edge_fringe_check']`, `report['protected_region_coverage']` |
| `recommend()` | **6** | `report['recommended_format']` (six branches) |
| `auto_run()` | 0 | — |

`verify()` does not merely read the analysis — **it builds its entire report on top of that dict**. Sharing one object would give `verify()`'s output a `recommended_format` key it does not have today, and in a multi-file run the second file's verify would inherit the first file's mutations.

**Requirement: the memo must return a deep copy.** Falsifier: after a memoized `--auto`, assert `verify()`'s report contains no `recommended_format` key.

This was found by scanning, not assumed. Stopping at "`analyze()` is pure, so memoize it" would have shipped the bug.

---

## 4. What was falsified — including four of my own claims

House rule: a negative result is only worth having once you have checked the test could have produced a positive one. Each row below was tested, not reasoned about.

| claim | verdict | evidence |
|---|---|---|
| "81% of the gate is three pure functions (verify 32%, analysis 27%, calibration 22%)" — **mine** | **FALSE** | One asset. On the population: `marketing-automation.gif` (171f) runs `--auto` in 22.8s vs grenade's 45.2s *because it refuses at pass 1*; `Pixel Saber.gif` (213f) takes 6.1s for the same reason. Frame count is not the driver — whether the asset renders is. |
| "The gate can be cut to 60–90s" — **mine** | **WITHDRAWN** | Extrapolated from the falsified profile above. |
| "Amortising Python startup is a lever" — **mine** | **FALSE** | Bare `python -c pass` = 0.02s; `import numpy, scipy.ndimage, PIL.Image` = 0.24s. 62 records pay ~15s of 626s = **2.4%**. |
| "Pure functions are recomputed across the codebase" — **mine** | **FALSE** | Instrumented one run: `load_animation_rgba_frames` ×4 for **1.0s**, `detect_bg_color` ×5 for ~0s, `build_art_palette` ×5 for ~0s. `analyze()` ×2 for **24.4s**. The class of repeated pure work has exactly one member that matters. |
| A whole-render content cache keyed on a render fingerprint | **REJECTED** | Checked against a real change before building it: the v6.3.0 branch edited `process()`, the render root, so the key would have moved and the cache would have saved **zero**. The render closure is most of the file. Its failure mode — a stale hit — makes the gate silently lie about the one thing it exists to detect. |
| Swapping Pillow for `avifenc`/`cwebp` | **REJECTED** | Changing the encoder changes the output bytes, which is the quantity the gate compares. |
| Truncating assets to fewer frames | **REJECTED** | This repo's own grenade defect lived only on frames 46–51 (`references/lessons.md` §48). |
| "All 10 no-output records are coin-flip refusals" — **mine** | **FALSE** | Two causes: 4 are the GIF entirely-transparent-frame refusal (`growth.gif`, `paper-plane.gif`), the rest are `--auto` coin-flip / changing-background refusals. Generalised from checking a single asset. |
| "Multi-file `--auto` skips verification" — **mine** | **FALSE** | See §2. A legitimate render refusal, correctly reported. |

---

## 5. The class: three wrong profiles, one missing instrument

The four self-falsifications above are not four separate mistakes.

**Prior art, in this repo, before this session.** `scripts/remove_gif_background.py:881` carries a comment in which a previous investigator claims a **"tripled `analyze()`"** and then retracts it — the retraction states the claim came from comparing a slow 25-asset prefix against a whole-corpus mean on a machine another job was saturating.

So the tally is: one previous investigator and one session (twice) have attempted to characterise this program's cost profile, and **all three attempts produced wrong answers**, each using the only method available — a stopwatch around a whole subprocess.

**Getting the true number required monkey-patching the module from a scratch script.** A user cannot do that. A live claude.ai session hitting a tool timeout — the exact failure `docs/investigations/2026-08-22-v6-timeout-trial.md` documents — certainly cannot.

**Therefore the class is not "a redundant call". The class is: nothing in this product can report where its time goes, so redundant work is undetectable by construction, including by the people trying to optimise it.** This is the repo's own standing rule that a discipline is not a control, applied to measurement rather than to correctness: the fix belongs in the tool, not in the next person's care.

The 61% figure sat in the flagship autonomous path across at least three releases, and the harness has had an `analyze()` disk cache the whole time — meaning someone once noticed the cost *in the harness* and nobody could see the same cost *in the product*.

---

## 6. The caching system exists and cannot reach the two consumers that need it most

### 6.1 The render gate cannot use it at all

`render_baseline.py` does not import `analysis_cache`; only `run_populations.py`, `snapshot.py` and three test files do. This is correct by design — the gate deliberately shells out to the real `--auto` CLI so it exercises the shipped product rather than a reconstruction. But it means the gate's dominant cost is uncacheable today, and `--auto` runs a full `analyze()` inside every one of its 62 renders.

### 6.2 The cache key structurally excludes the test suite — invisibly

The cache is keyed on `analysis_fingerprint(script)` plus **each asset's mtime and size**.

The test suite is the heaviest repeat-analyser in the repo: its 15 slowest tests total **~773s**, and every one is an `--auto` / `--verify` / `--target-kb` invocation.

| slowest tests | time |
|---|---|
| `test_auto_coinflip_refusal.py::test_a_pre_answered_run_proceeds_and_drops_the_named_colour` | 123.75s |
| `test_final_dimensions_are_reprinted.py::test_a_fit_that_changes_dimensions_reprints_them` | 96.96s |
| `test_target_kb_min_dimension.py::test_the_same_fit_WOULD_have_gone_smaller_without_the_floor` | 69.49s |
| `test_score_outputs.py::test_growth_interior_survives_a_real_render` | 65.57s |
| `test_target_kb_min_dimension.py::test_a_fit_never_delivers_below_the_stated_floor` | 57.20s |

**But the suite's assets are synthetic fixtures regenerated into a fresh temp directory on every run** — new path, new mtime. **The cache would miss on 100% of them.**

And the miss is silent: a warm cache and a cache that never hits are indistinguishable from outside. This repo has already been bitten by exactly that shape, when `codebase-memory-mcp` returned an empty index that read identically to "never indexed".

**Keying on a content hash of the asset bytes instead of mtime+size fixes it**, costs one hash of bytes already being read, and lets a single cache serve the product, both gates and the suite.

### 6.3 A constant `analyze()` cannot read still cold-invalidated the whole cache

`analysis_fingerprint` hashes **every** module-level statement unconditionally — its docstring states a constant is "reachable from anywhere and cheap to include, so it is never analysed for reach."

Measured on this branch: adding `DEAD_PROTECTION_OPACITY = 0.05`, read only by `unprotected_design_regions` (a `verify()` helper `analyze()` cannot reach), moved the fingerprint `a99c2880ae5d6975` → `a27d82c48415731b` and discarded all **29 entries / 42 MB** of warm cache.

The closure itself was proven identical: **34 functions reachable from `analyze()`, zero changed**, the only module-level addition being that constant.

This is the design's deliberate safe direction and must stay that way — a *missed* invalidation serves a pre-change answer to the gate meant to catch the change, which is far worse. But the docstring's word for the other direction is "cheap", and that was assumed rather than measured. Here it cost a full cold pass on a merge that changed nothing `analyze()` can see.

---

## 7. Secondary measurements

### 7.1 BLAS thread oversubscription — real, modest, and free to fix

numpy here is Apple **Accelerate**, which multithreads. Nothing sets a thread cap while `default_jobs()` runs 6 worker processes on 6 performance cores.

Interleaved A/B/A/B on 3 assets at 3 parallel workers, to control for drift:

| rep | uncapped | capped to 1 thread/worker |
|---|---|---|
| 0 | 67.6s | 59.2s |
| 1 | 67.1s | 61.9s |
| **best** | **67.1s** | **59.2s** |

**1.13× speedup, reproducible across both reps.** Harness-only: a single-file user run wants all the threads, and the claude.ai sandbox has one core.

### 7.2 The render gate's shape

62 records = **31 assets × 2 passes** (native, then `--resize-max-dim`). `analyze()` is a pure function of the source and `--resize-max-dim` is applied after it, so **~50% of the gate's analysis work is a literal duplicate inside a single run** — removable by an in-process memo or by one CLI invocation doing both passes, with no cross-run cache and no staleness risk.

**10 of 62 records (16%) render nothing at all** and pay analysis only. The gate compares `returncode` and `no_output`, so a refusal flipping *is* caught — this is not a vacuous pass.

**Timing is not stable and no speedup claim should be quoted without a back-to-back pair.** This merge measured 626s and 296s for identical work at different contention levels; CLAUDE.md already records the standard set at 976s and 488s on consecutive runs.

Machine: 6 performance cores, 8 logical, 6,246 MB available; `default_jobs()` returned 6, bound by cores (memory allowed 12).

### 7.3 An unrelated product defect the gate has been recording, unread

`render_baseline.py` captures `signal_lines` per record and compares them PRE/POST, so a *change* would be caught. The standing content is surfaced nowhere. On `main`, today:

| asset | source artwork px | survived | lost |
|---|---|---|---|
| `alphas/cinnamonexcited.gif` | 44,565 | 32,169 | **27.8%** |
| `alphas/PixelSaber-ezgif.com-gif-maker (2).gif` | 1,643,209 | 1,444,385 | **12.1%** |

`--verify` states it plainly — *"The SOURCE already had transparency, so its N opaque pixels were the artwork … Colour-based removal has eaten real art"* — and it has sat in the baseline unread.

⚠️ **This is not the already-filed "two assets where the keyer removes solid artwork" item.** That one is two *dark-corpus GIFs on flat coloured backgrounds* (`ff6666`, `921219`), diagnosed and closed 2026-08-20/21. These two are **already-transparent sources** — the `--source-alpha-band` / `--ignore-source-alpha` mechanism of §28.14. Different defect. Checked before claiming it, because the titles are close enough to merge by mistake.

**A gate that records a defect and reports "0 changed" is working exactly as designed and is still telling nobody.**

---

## 8. Levers that are not caching

The caching framing hid these. Listed with their honest value:

| lever | value | notes |
|---|---|---|
| **Profile inside `analyze()`** | Unknown — worth finding out | 11.5s for a 62-frame 640×640 asset. Nobody has looked since §29.8 replaced `np.unique` with a boolean sieve. A different lever entirely, with a precedent for winning. |
| **Parallelise `analyze()` across frames** | Real on a 6-core Mac, **zero** on claude.ai | The deployment target has one core (§24). Named explicitly so nobody builds it for the wrong reason. |
| **Do not call it at all** | 4× on a known-flags run | Routing, not code. Free. |
| **Commit a PRE baseline keyed on `main`'s script SHA** | Flat −50% of the gate | The gate re-renders `main` from scratch every run. The artefact is a few KB of hashes. |
| **Longest-processing-time-first scheduling** | Unquantified | A run ends when its last unit ends. ⚠️ The harness does not currently record per-unit durations, so this cannot be implemented or measured until it does. |

---

## 9. Reproducing every number

```bash
# §1, §2 — analyze() call count and cost, in-process on the real main()
#   monkey-patch module.analyze with a timing wrapper, then call main()
#   with sys.argv set; see the session transcript for the exact script.

# §3 — mutation scan (no render needed, ~1s)
python3 - <<'PY'
import ast, pathlib
tree = ast.parse(pathlib.Path('scripts/remove_gif_background.py').read_text())
for fn in ('recommend', 'verify', 'auto_run'):
    node = next((n for n in tree.body if getattr(n, 'name', None) == fn), None)
    muts = [ast.unparse(t) for s in ast.walk(node) if isinstance(s, ast.Assign)
            for t in s.targets if isinstance(t, ast.Subscript)
            and isinstance(t.value, ast.Name) and t.value.id in ('report', 'analysis', 'rep')]
    print(fn, len(muts))
PY

# §4 — startup cost
python3 -c "import time,subprocess,sys; t=time.time(); subprocess.run([sys.executable,'-c','import numpy, scipy.ndimage, PIL.Image']); print(time.time()-t)"

# §6.3 — is analyze()'s closure actually unchanged between two revisions?
#   compare analysis_fingerprint() on both, then diff the reachable
#   function set to separate a real change from an ambient false invalidation.

# §7.1 — thread oversubscription, interleaved A/B/A/B
#   run N assets in parallel with and without VECLIB_MAXIMUM_THREADS=1

# §6.2 — suite profile
python3 -m pytest scripts/harness -q --durations=15
```

---

## 10. What is NOT known

Named rather than papered over, because two of this session's wrong answers came from filling gaps like these with reasoning:

- **Whether `--auto`'s pass-2 corrective re-render adds a THIRD `analyze()`.** Only assets where the correction did *not* fire have been measured.
- **What dominates inside `analyze()`'s 11.5s.** Never profiled at function granularity.
- **Whether `run_populations.py` and `candidates.py` carry their own duplication.** Neither was checked.
- **Whether the two ART-LOSS assets in §7.3 are a regression in the source-alpha scoping or assets whose own alpha is wrong** (and which therefore legitimately need `--ignore-source-alpha`).
- **The real end-to-end gain from any fix below.** Every estimate in the plan is arithmetic on the measurements above, not an observed result, and this document's own history is a warning about that distinction.

---

## 11. Related

- `references/lessons.md` §48 — the four-asset correctness review that opened this session
- `references/lessons.md` §24 — the claude.ai sandbox is 1 CPU with per-call teardown
- `references/lessons.md` §29.8 — the previous win inside `analyze()`
- `docs/investigations/2026-08-22-v6-timeout-trial.md` — sessions timing out on this cost
- `docs/investigations/2026-08-21-diors-builds-caching-transfer.md` — where `analysis_fingerprint` came from
- `gif-deferred-list.md` — the filed items
- `docs/plans/2026-09-01-analysis-cost-and-observability.md` — the implementation plan
