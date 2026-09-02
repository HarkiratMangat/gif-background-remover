# Where the time goes — measured, then falsified by three audits

**Date:** 2026-09-01
**Trigger:** A pre-merge render gate took 626s + 296s. Harkirat asked why, given the repo has a caching system; then whether any speedup reaches the shipped skill or only the tests; then for the CLASS, not the instances.
**Method:** In-process instrumentation of the real `main()`. Then three adversarial subagents attacked the result.
**Status:** ⚠️ **THIS IS A STARTING POINT, NOT A CONCLUSION.** The option space is deliberately open — see §8. No performance code has been changed.

---

## 0. Read this first: the first draft of this document was wrong five times

Three subagents audited it. Every headline claim failed. Kept here in full, because the pattern is the finding.

| first draft claimed | measured truth |
|---|---|
| `--auto` wastes 32% on every run | **20–24%**, and **0%** on any run that crops, resizes, or hits a `--target-kb` size change |
| analysis = 61% of a run | **39%** and **47%** on assets that exist in this repo |
| `verify()` mutates the analysis 24× | **0×.** The scan counted a different variable of the same name |
| a deep copy is required for correctness | Not required. A shared object gives **byte-identical output** |
| a memo layer is the fix | **3 lines** does it — the caller already holds the answer |
| `analyze()` has never been profiled | It has, twice, in this repo |
| the gate would catch the artwork loss | It would not. That defect is **ungated** |

**Why every attempt failed the same way:** the only available method was a stopwatch around a subprocess. See §5.

---

## 1. `--auto` analyses the same file twice — but only sometimes

| run | `analyze()` calls |
|---|---|
| `--auto`, output keeps source canvas | **2** |
| `--auto --crop` / `--resize-max-dim` / a `--target-kb` fit that resizes | **1** |

**Why:** `verify()` returns at `:4783` when input and output dimensions differ — *before* its `analyze()` call at `:4817`.

**Where the second call comes from:** `recommend()` at `:2353` (AUTO pass 1) and `verify()` at `:4817` (AUTO pass 3). Same path, same `tolerance`, `max_samples` always 40, byte-identical result hash.

**Measured, on assets that exist in this repo:**

| asset | frames | analysis share | 2nd call alone |
|---|---|---|---|
| `in-love.gif` | 48 | 39% | **20%** |
| `satellite.gif` | 120 | 47% | **24%** |

**Who this does NOT help:** every cropped/resized deliverable, and **31 of the render gate's 62 records**, which already analyse once.

---

## 2. `analyze()` is most of what the program does

| command | `analyze()` calls | share of runtime |
|---|---|---|
| `--recommend` | 1 | 100% |
| `--verify` | 1 | 87% |
| `--auto` | 2 (or 1) | 39–47% |
| plain render, explicit flags | **0** | **0%** — and 2.2–3.5× faster |

---

## 3. The cheap fix, and why the first draft's expensive one was wrong

**`auto_run` already holds the analysis it makes `verify()` recompute.**

```
:9760   rec = recommend(...)     # returns {'analysis': report, ...}
:10026  _v  = verify(...)        # recomputes it, 266 lines later
```

Passing `rec['analysis']` into `verify()` is **~3 lines**. No global state, no retention, no copy semantics, no `--batch` interaction, and inside `analyze()`'s fingerprint closure by construction.

**On the deep copy** — measured, not argued:

| | |
|---|---|
| `verify()` mutations of the analysis | **0** (its `report` is a fresh dict at `:4759`) |
| `recommend()` mutations | **6** (`report['recommended_format']`, and `report` IS the analysis) |
| shared-object run vs baseline | **byte-identical output**, 3 runs |
| `deepcopy` cost | **0.046 ms** on a 2.3 KB report — no numpy, no buffers |

So a copy is cheap insurance against `recommend()`'s stamping, **not** a measured necessity.

---

## 4. The test suite — the part the first draft barely looked at

**The suite already has a render cache, and almost nothing uses it.**

| fact | value |
|---|---|
| `rendered()` — renders once, caches, reuses | defined in `test_score_outputs.py:51` |
| test files that use it | **1 of 30** |
| everything else | raw `subprocess.run` per test |
| cache key | **whole-script SHA** — every product edit busts it |
| cache on disk | **400 MB, 46 SHA directories**, never pruned |
| 15 slowest tests | **~773s**, none of them use it |

**Consequence:** during any session that edits the product — i.e. every development session — the suite is cold by construction, and 29 of 30 files were never warm to begin with.

⚠️ **The first draft proposed content-hash keying the *analysis* cache to speed the suite. That was wrong** — the slow tests never import `analysis_cache` at all. The cache that matters here is `rendered()`.

**Open, not answered:** how much of the 773s is re-rendering the same (asset, flags) pair across files; whether `-n 6` is the right worker count; whether tests could assert on a shorter path than a full render; whether the 400 MB needs pruning or a smaller key.

---

## 5. The class: no instrument, so everyone guesses

| attempt | outcome |
|---|---|
| A previous investigator's "tripled `analyze()`" (`:881`) | claimed, then **retracted** — bad measurement |
| First draft, attempt 1 | 32%/27%/22%/12% from **one asset** — falsified |
| First draft, attempt 2 | "60–90s" built on that — withdrawn |
| First draft, attempt 3 | five headline claims in §0 — all falsified |

**Four attempts, four wrong answers, one missing instrument.** The true numbers needed monkey-patching the module from a scratch script — which a user cannot do, and a claude.ai session hitting a tool timeout certainly cannot.

⚠️ **But note what actually caught it:** three adversarial readers, not a profiler. An instrument would have prevented attempts 1–2; it would not have caught the wrong-variable AST scan or the early-return path. **Both are needed. Neither is sufficient.**

---

## 6. The caching that exists, and what it does not reach

| cache | keyed on | reaches | misses |
|---|---|---|---|
| `analysis_cache` | reachable-code fingerprint + asset mtime/size | `run_populations.py` | the product, the render gate, 29 of 30 test files |
| `rendered()` | whole-script SHA | 1 test file | everything else |

**Also measured:** adding one module-level constant (`DEAD_PROTECTION_OPACITY`) moved the analysis fingerprint `a99c2880…` → `a27d82c4…` and discarded **29 entries / 42 MB**, while `analyze()`'s closure was **provably identical** (34 functions, 0 changed). Deliberate safe direction — a missed invalidation is far worse — but the cost was assumed, not measured.

---

## 7. Secondary findings

**BLAS oversubscription.** numpy is Apple Accelerate (multithreaded); nothing caps threads while 6 workers run on 6 cores. Interleaved A/B/A/B at 3 workers: **67.1s → 59.2s, 1.13×**. ⚠️ Never measured at the deployed 6 workers.

**A product defect the gate records and cannot catch.**

| asset | artwork px | survived | lost |
|---|---|---|---|
| `alphas/cinnamonexcited.gif` | 44,565 | 32,169 | **27.8%** |
| `alphas/PixelSaber-…gif` | 1,643,209 | 1,444,385 | **12.1%** |

`--verify` says *"Colour-based removal has eaten real art"* and the gate writes it to `signal_lines`. ⚠️ **`compare()` diffs six fields and `signal_lines` is not one of them** — so this is ungated, not merely unread. Not the already-filed dark-corpus item; these are already-transparent sources (`--source-alpha-band`, §28.14).

---

## 8. The option space — deliberately open

**Nothing here is settled. This is a menu for the next session, not a plan.**

### 8.1 Measured, ready to try

| option | value | risk |
|---|---|---|
| Pass the analysis into `verify()` | 20–24% of `--auto`, same-canvas runs only | ~3 lines |
| Extend `rendered()` to the other 29 test files | unquantified, plausibly large | needs per-test audit |
| Commit a PRE baseline for the render gate | flat −50% of gate wall time | staleness |
| Cap BLAS threads in harness workers | 1.13× at 3 workers | reduction order may move bytes |

### 8.2 Named but unmeasured — measure before building

- **`max_samples=40`.** Straight arithmetic on the dominant cost. Nobody has asked whether 40 is needed, or whether `recommend()`'s screening pass could use fewer than `verify()`'s.
- **Inside `analyze()`.** ⚠️ Already profiled: `:3076` (16s self time), `:3109` ("7.18s of 23.8s"), §29.16. Its verdict is pessimistic — *"a 115× on one line is a 10% on the run."*
- **`rendered()`'s key.** Whole-script SHA busts on every edit; the reachable-code fingerprint trick already exists in `analysis_cache`.
- **Longest-first scheduling.** The harness records no per-unit durations, so this cannot be measured yet.
- **A `--profile` flag.** Would have caught attempts 1–2 but not 3. Its only current customer is one call count.
- **Routing away from `--auto`** when flags are known (2.2–3.5×). ⚠️ §46 says a doc fix did not stop the analogous problem recurring.

### 8.3 Rejected, with evidence

| idea | why not |
|---|---|
| Amortise Python startup | imports are 0.24s = **2.4%** |
| Whole-render fingerprint cache | would have saved **zero** on this branch — `process()` was edited |
| Swap Pillow for `avifenc`/`cwebp` | changes output bytes, the quantity being compared |
| Truncate assets to fewer frames | this repo's grenade defect lived only on frames 46–51 |
| Content-hash the *analysis* cache to speed tests | the slow tests never call it |
| Parallelise `analyze()` across frames | worth **zero** on the 1-core deployment target |

### 8.4 Not yet explored at all

Named so the next session does not mistake this list for the whole space: per-test render sharing via a session-scoped fixture; a library entry point so tests skip subprocess+import; whether `-n 6` is optimal; pruning the 400 MB render cache; whether any slow test needs a *full* render to make its assertion; running the gate on more cores.

---

## 9. Reproducing

⚠️ **The first draft's headline asset (`grenade.gif`) is not in this repo** — it lives in `~/Downloads`. Numbers below use repo assets.

```bash
# analyze() call count and cost, in-process on the real main()
#   monkey-patch module.analyze with a timing wrapper, set sys.argv, call main()

# the early return that makes the second call conditional
sed -n '4775,4790p' scripts/remove_gif_background.py

# which variable the analysis is bound to in each consumer
python3 -c "import ast,pathlib; ..."   # bind to the name assigned from analyze(), not 'report'

# the test suite's own render cache
rg -n 'def rendered' -A 22 scripts/harness/test_score_outputs.py
du -sh local/.test-renders && ls local/.test-renders | wc -l

# suite profile
python3 -m pytest scripts/harness -q --durations=15
```

---

## 10. Still unknown

- How much of the suite's 773s is duplicate work vs genuinely distinct renders.
- Whether the 1.13× thread-cap holds at 6 workers.
- Whether the two ART-LOSS assets are a regression or sources whose own alpha is wrong.
- What `max_samples` could safely be.

**Answered since the first draft:** `--auto`'s pass-2 corrective re-render adds **no** third `analyze()` — four call sites, enumerated.

---

## 11. Related

`references/lessons.md` §24 (1-core sandbox) · §29.8, §29.16 (prior `analyze()` profiling) · §44, §46 (a flag or doc fix that changed nothing) · §48 (the four-asset review) · `docs/investigations/2026-08-22-v6-timeout-trial.md` · `gif-deferred-list.md` · `docs/plans/2026-09-01-analysis-cost-and-observability.md`
