# Performance work — an open menu, not a closed plan

> **For agentic workers:** this is deliberately **NOT** a locked task list. Task 1 is ready to build. Everything after it needs a measurement first, and §4 is explicitly unexplored. The absence of an option here is not evidence it was rejected — §5 lists what actually was.

**Spec:** `docs/investigations/2026-09-01-analysis-cost-and-the-missing-instrument.md`

**Status:** ⚠️ **The first version of this plan had its central task deleted.** It specified a module-level memo whose correctness argument was falsified, whose decorator composition was inverted, and whose test could not fail. Three adversarial audits caught it. What survives is one small task and a set of open questions.

---

## Global Constraints

- `analyze(input_path, max_samples=40, tolerance=15)` — `scripts/remove_gif_background.py:1174`.
- **The shipped `.skill` carries no disk-cache behaviour by default.** The deployment sandbox is ephemeral and 1-core (`lessons.md` §24).
- **Every new flag must fail loudly when it cannot take effect** (`lessons.md` §44, §48.6).
- **`python3 scripts/audit_docs.py` must pass.** It requires `README.md` to name every argparse flag, and it **rejects packaged files pointing at `docs/`, `local/`, `scripts/harness/`** — do not cite this document from inside `remove_gif_background.py`.
- **Markdown is soft-wrapped**, including prose inside fences.
- **No number goes in a doc without a back-to-back measurement.** The same set has measured 976s and 488s on consecutive runs.

---

## Task 1: pass the analysis into `verify()` instead of recomputing it

**The only task here that is ready to build.** Roughly three lines.

**Files:**
- Modify: `scripts/remove_gif_background.py` — `verify()` signature (`:4725`), `auto_run`'s call (`:10026`)
- Create: `scripts/harness/conftest.py`, `scripts/harness/test_verify_reuses_the_analysis.py`

**Value:** 20–24% of an `--auto` run. ⚠️ **Zero on any run that crops, resizes, or hits a `--target-kb` size change** — `verify()` returns at `:4783` before it would analyse.

**Why a parameter, not a memo:** `auto_run` already holds `rec['analysis']` at `:9760`. A parameter has no global state, no retention, no copy semantics, no `--batch` interaction, and stays inside `analyze()`'s fingerprint closure. The rejected memo had all five hazards.

- [ ] **Step 0: Create the fixture file — this repo has none**

`fd conftest.py` returns nothing; `pytest.ini` is `addopts = -n 6 -q` only.

```python
# scripts/harness/conftest.py
import pathlib
import pytest


@pytest.fixture(scope='session')
def sample_gif():
    """An asset that renders through all three --auto passes WITHOUT refusing, and whose
    output keeps the source canvas. Both are load-bearing: a refusal never reaches pass 3,
    and a resized output makes verify() return before it would analyse."""
    p = pathlib.Path(__file__).resolve().parents[2] / 'local' / 'Corpus Trial Gifs' / 'in-love.gif'
    if not p.exists():
        pytest.skip(f'fixture asset not present: {p}')
    return p
```

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_verify_reuses_the_analysis.py
import contextlib
import importlib.util
import io
import pathlib
import sys

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'remove_gif_background.py'


def _load():
    spec = importlib.util.spec_from_file_location('rgb_reuse', _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules['rgb_reuse'] = m
    spec.loader.exec_module(m)
    return m


def _count_analyze(m, argv):
    n = {'c': 0}
    orig = m.analyze
    m.analyze = lambda *a, **k: (n.__setitem__('c', n['c'] + 1), orig(*a, **k))[1]
    sys.argv = argv
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        with contextlib.suppress(SystemExit):
            m.main()
    return n['c']


def test_auto_analyses_once_not_twice(tmp_path, sample_gif):
    m = _load()
    assert _count_analyze(m, ['x', str(sample_gif), str(tmp_path / 'o.webp'), '--auto']) == 1


def test_standalone_verify_STILL_analyses(tmp_path, sample_gif):
    """The negative half. Without it, deleting verify()'s analyze() outright would pass the
    test above -- and standalone --verify has no caller to hand it an analysis."""
    m = _load()
    out = tmp_path / 'o.webp'
    _count_analyze(m, ['x', str(sample_gif), str(out), '--auto'])
    m2 = _load()
    assert _count_analyze(m2, ['x', str(sample_gif), str(out), '--verify']) == 1


def test_the_report_does_not_inherit_recommends_stamp(tmp_path, sample_gif):
    """recommend() mutates the analysis 6 times (report['recommended_format']) and returns
    that same object as rec['analysis']. verify()'s own report must not gain the key."""
    m = _load()
    out = tmp_path / 'o.webp'
    sys.argv = ['x', str(sample_gif), str(out), '--auto']
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        with contextlib.suppress(SystemExit):
            m.main()
    assert 'recommended_format' not in m.verify(str(sample_gif), str(out))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest scripts/harness/test_verify_reuses_the_analysis.py -v -p no:randomly` Expected: `test_auto_analyses_once_not_twice` FAILS with `2 != 1`. The other two already pass — they are guards, not the target.

- [ ] **Step 3: Implement**

```python
def verify(input_path, output_path, tolerance=15, assume_remove_colors=(),
           input_analysis=None):
    ...
    # ⚠️ REUSE, NOT RECOMPUTE. auto_run already paid for this exact analysis in pass 1 --
    # same path, same tolerance, byte-identical result -- and it is 20-24% of the run.
    # A PARAMETER rather than a memo, deliberately: no global state, no retention, no copy
    # semantics to argue about, and it stays inside analyze()'s fingerprint closure, so a
    # change here cannot silently serve a stale cached analysis.
    #
    # ⚠️ COPY IT. recommend() stamps report['recommended_format'] onto this same object six
    # times and hands it back as rec['analysis']. verify() itself mutates it ZERO times --
    # measured, and a shared object gives byte-identical output -- but the copy costs
    # 0.046 ms on a 2.3 KB report and removes the question entirely.
    input_analysis = (copy.deepcopy(input_analysis) if input_analysis is not None
                      else analyze(input_path, tolerance=tolerance))
```

At `auto_run:10026`: `_v = verify(..., input_analysis=rec.get('analysis'))`.

⚠️ **Keep the call where it is.** The existing `analyze()` sits at `:4817`, *after* the early return at `:4783`. A caller-supplied analysis must not make the dimension-mismatch path start doing work it currently skips.

- [ ] **Step 4: Run to verify it passes** — all three green.

- [ ] **Step 5: Prove the output did not move**

```bash
git stash -u
python3 scripts/remove_gif_background.py <asset> /tmp/pre.webp --auto
git stash pop
python3 scripts/remove_gif_background.py <asset> /tmp/post.webp --auto
cmp /tmp/pre.webp /tmp/post.webp && echo BYTE-IDENTICAL
```

Run on three assets: one plain, one needing `--recover-fade-alpha`, one that **refuses**.

- [ ] **Step 6: Render gate**

```bash
git show main:scripts/remove_gif_background.py > /tmp/rgb_main.py
python3 scripts/harness/render_baseline.py --set fast --script /tmp/rgb_main.py --out /tmp/pre.json
python3 scripts/harness/render_baseline.py --set fast --out /tmp/post.json
python3 scripts/harness/render_baseline.py --compare /tmp/pre.json /tmp/post.json
```

Expected: **`0 changed`.** ⚠️ Use `--set standard` if this ships as part of a release (`CLAUDE.md` gate 9).

- [ ] **Step 7: Measure back to back, then commit**

Three runs before, three after; quote the **minimum**. Include one asset that resizes, so the quoted gain is honest about the 0% case.

```bash
git add scripts/remove_gif_background.py scripts/harness/conftest.py scripts/harness/test_verify_reuses_the_analysis.py
git commit -m "perf: reuse pass 1's analysis in --auto's verify instead of recomputing it"
```

---

## 2. Open questions — measure before building any of these

Each needs a number that does not exist yet.

| # | question | why it is open |
|---|---|---|
| 2.1 | How much of the suite's 773s is duplicate work? | `rendered()` exists (`test_score_outputs.py:51`) but **only 1 of 30 files uses it**. Nobody has counted repeated (asset, flags) pairs across files. |
| 2.2 | Should `rendered()` key on reachable code rather than whole-script SHA? | Today every product edit busts it — **400 MB, 46 SHA directories, never pruned**. `analysis_fingerprint` already does the smarter thing. |
| 2.3 | Is `max_samples=40` necessary? | Straight arithmetic on the dominant cost, never questioned. Could `recommend()`'s screening pass use fewer than `verify()`'s? |
| 2.4 | Is `-n 6` right for the suite? | Chosen to match `default_jobs()`. Never measured against 4 or 8, and never with BLAS threads capped. |
| 2.5 | Does any slow test need a *full* render to assert what it asserts? | Unexamined. Some may need only `--recommend` output, or a few frames. |
| 2.6 | Does the 1.13× BLAS cap hold at 6 workers? | Measured at **3**. The deployed configuration was never tested. |
| 2.7 | Is a `--profile` flag worth a permanent packaged surface? | It would have caught 2 of the 4 wrong profiles, not the other 2 (a wrong-variable AST scan, an early-return path). Its only current customer is one call count. |

---

## 3. Harness-side options, each independently droppable

Sketches, not specs. Each needs its own falsifier before it is written.

- **Commit a PRE baseline** keyed on `main`'s script SHA — flat −50% of gate wall time. ⚠️ The key must also cover `render_baseline.py`'s own version, the `SETS` definition and the asset corpus, or a "match" can be a rubber stamp.
- **Extend `rendered()`** to the 29 test files that shell out raw.
- **Cap BLAS threads** — `render_once` takes `env=`; ⚠️ `run_populations.py` uses `ProcessPoolExecutor` with no subprocess, so it needs `os.environ` set before the pool is created.
- **Prune `local/.test-renders`** — 400 MB across 46 script versions.
- **Longest-first scheduling** — ⚠️ blocked: the harness records no per-unit durations, and `compare()` diffs six fields, so a wrong duration would fail nothing.

---

## 4. Not explored at all

Listed so nobody mistakes this for the full option space:

a session-scoped fixture sharing renders across test *files* · a library entry point so tests skip subprocess + import · running the gate on more cores · whether the gate needs 31 assets or 8 · tiering the gate (smoke per merge, full per release) · anything about the encoder itself.

---

## 5. Rejected, with evidence — do not re-derive

| idea | why not |
|---|---|
| A module-level `analyze()` memo | Task 1's parameter does the same job. The memo added global state, ~1.1 GB retention in `run_populations`, a fingerprint-closure hazard and a `--batch` interaction. |
| Amortising Python startup | imports are 0.24s = **2.4%** |
| A whole-render fingerprint cache | would have saved **zero** on the branch that motivated it |
| Swapping the encoder | changes output bytes, the quantity being compared |
| Truncating assets to fewer frames | this repo's grenade defect lived only on frames 46–51 |
| Content-hash keying the *analysis* cache to speed the suite | the slow tests never import it |
| Parallelising `analyze()` across frames | worth **zero** on the 1-core deployment target |

---

## 6. Defect shapes the audits caught, so the next session recognises them

| defect in the first draft | shape |
|---|---|
| Counted mutations of the wrong variable | an AST scan matched by *name*, not by binding |
| A falsifier that passes with the bug present | vacuous test — `CLAUDE.md` gate 8's scorer caveat |
| Decorator composition inverted | the test asserted 1; the implementation guaranteed 2 |
| Headline asset not in the repo | an unreproducible number |
| "Never profiled" | it had been, twice, in this file's own comments |
| A task premise that was simply false | the consumers it targeted never call the thing it changed |

**An instrument would have caught two of these. Three adversarial readers caught all six.** Both are needed; neither is sufficient.
