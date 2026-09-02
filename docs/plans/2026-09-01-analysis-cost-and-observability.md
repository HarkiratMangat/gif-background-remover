# Analysis Cost and Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant second `analyze()` call from every `--auto` run (≈32% of the flagship path, in the shipped skill), and give the product an instrument so the next redundancy is visible instead of hunted.

**Architecture:** Task 1 builds the instrument FIRST, so every task after it is measured by the tool rather than by a stopwatch — which is the failure this whole plan exists to fix. Task 2 removes the redundant call with a deep-copying in-process memo, whose correctness rests on a mutation fact established in the spec. Tasks 3–6 are harness-side and independent of each other; they may be reordered or dropped without affecting Tasks 1–2.

**Tech Stack:** Python 3, stdlib only. No new dependencies — the shipped `.skill` must stay dependency-clean. ⚠️ **`copy` and `os` are already imported at module scope (lines 64, 66); `time`, `functools` and `hashlib` are NOT** — Task 1 must add `import time` at module scope, and the function-local `import functools` / `import hashlib` below are written that way deliberately.

**Spec:** `docs/investigations/2026-09-01-analysis-cost-and-the-missing-instrument.md`

## Global Constraints

- **`analyze()`'s signature is `analyze(input_path, max_samples=40, tolerance=15)`** (`scripts/remove_gif_background.py:1174`). Any memo key must cover all three.
- **`verify()` mutates the analyze result 24 times and `recommend()` 6 times.** A memo MUST return a deep copy. Non-negotiable; see spec §3.
- **The shipped `.skill` must carry no disk-cache behaviour by default.** The deployment sandbox is ephemeral and single-core (`references/lessons.md` §24); a disk cache there is dead weight. Anything cross-run is opt-in via an explicit flag.
- **Every new flag must fail loudly when it cannot take effect.** `references/lessons.md` §44 catalogues eight instances of a flag accepted and discarded; §48.6 added a ninth. This is a house rule, not a preference.
- **`python3 scripts/audit_docs.py` must pass before any commit.** It gates packaged docs against the script and fails on undocumented flags.
- **Markdown is soft-wrapped: one physical line per paragraph or list item.** Applies to prose inside fenced blocks too.
- **No number goes into a doc without a back-to-back measurement.** This repo has recorded the same render set at 976s and 488s on consecutive runs, and this plan's own spec had to withdraw two figures derived from single-asset stopwatching.

---

### Task 1: `--profile` — the instrument, built before anything it will measure

**Files:**
- Modify: `scripts/remove_gif_background.py` (add `_PROFILE` state + `_profiled` decorator near the top-level constants, ~line 630; add the `--profile` argparse entry beside `--min-quality`, ~line 10281; print the report at the end of `main()`)
- Test: `scripts/harness/test_profile_instrument.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_PROFILE` (a `dict[str, list[float]]` mapping function name → per-call durations), and `_profiled(fn)` — a decorator that records `(name, duration)` when profiling is enabled and is a pass-through when it is not. Task 2's falsifier reads `_PROFILE` to assert the call count dropped from 2 to 1.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_profile_instrument.py
import importlib.util, pathlib, subprocess, sys, tempfile

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'remove_gif_background.py'

def _load():
    spec = importlib.util.spec_from_file_location('rgb_prof', _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules['rgb_prof'] = m
    spec.loader.exec_module(m)
    return m

def test_profile_is_off_by_default_and_records_nothing():
    m = _load()
    assert m._PROFILE == {}, 'profiling must be OFF until --profile is passed'

def test_profiled_decorator_is_a_pass_through_when_disabled():
    m = _load()
    calls = []
    fn = m._profiled(lambda x: (calls.append(x), x * 2)[1])
    assert fn(21) == 42
    assert m._PROFILE == {}

def test_profiled_decorator_records_when_enabled():
    m = _load()
    m._PROFILE_ENABLED = True
    fn = m._profiled(lambda: None)
    fn(); fn()
    name = next(iter(m._PROFILE))
    assert len(m._PROFILE[name]) == 2, f'expected 2 recorded calls, got {m._PROFILE}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/harness/test_profile_instrument.py -v` Expected: FAIL with `AttributeError: module 'rgb_prof' has no attribute '_PROFILE'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/remove_gif_background.py, near the module-level constants
#: Per-function wall time, recorded only when --profile is passed. Off by default and
#: pass-through when off, so an unprofiled run pays one boolean check per decorated call.
#:
#: ⚠️ THIS EXISTS BECAUSE THREE ATTEMPTS TO PROFILE THIS PROGRAM PRODUCED THREE WRONG
#: ANSWERS -- a previous investigator's retracted "tripled analyze()" (see the comment in
#: measure_composited_color_count) and two in one session on 2026-09-01 -- every one of them using
#: a stopwatch around a whole subprocess, because that was the only method available. The
#: true numbers needed monkey-patching the module from a scratch script, which a user cannot
#: do and a sandbox session hitting a tool timeout certainly cannot.
_PROFILE = {}
_PROFILE_ENABLED = False


def _profiled(fn):
    """Record wall time per call when profiling is on; otherwise call straight through."""
    import functools   # NOT imported at module scope in this file -- checked 2026-09-01

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _PROFILE_ENABLED:
            return fn(*args, **kwargs)
        t0 = time.time()
        try:
            return fn(*args, **kwargs)
        finally:
            _PROFILE.setdefault(fn.__name__, []).append(time.time() - t0)
    return wrapper
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/harness/test_profile_instrument.py -v` Expected: PASS (3 tests)

- [ ] **Step 5: Decorate the expensive functions and add the flag**

Apply `@_profiled` to exactly these, and no others — they are the ones the spec measured as expensive or repeated: `analyze`, `recommend`, `verify`, `load_animation_rgba_frames`, `load_gif_rgba_frames`, `detect_bg_color`, `build_art_palette`, `recover_fade_alpha_frames`, `erode_alpha_edge_exempting_tiny_regions`, `encode`.

```python
    p.add_argument('--profile', action='store_true', default=False,
                    help='Print a per-phase wall-time and call-count report to stderr when '
                         'the run finishes. Off by default and free when off. Use it before '
                         'optimising anything: three separate attempts to characterise this '
                         'program by external timing produced three wrong answers.')
```

- [ ] **Step 6: Print the report at the end of `main()`**

```python
    if getattr(args, 'profile', False) and _PROFILE:
        _tot = time.time() - _RUN_STARTED_AT
        print(f"\n=== profile: {_tot:.1f}s total ===", file=sys.stderr)
        print("  NOTE: nested calls double-count. Read the COUNT column for redundancy; "
              "read the SELF column only for leaf functions.", file=sys.stderr)
        for _name, _times in sorted(_PROFILE.items(), key=lambda kv: -sum(kv[1])):
            _n, _s = len(_times), sum(_times)
            _flag = '  <-- CALLED MORE THAN ONCE' if _n > 1 and _s > 0.5 * _tot / 10 else ''
            print(f"    {_name:38s} x{_n:<4d} {_s:7.1f}s  {_s / _tot:5.0%}{_flag}",
                  file=sys.stderr)
```

Set `_RUN_STARTED_AT = time.time()` as the first statement in `main()`, and set `_PROFILE_ENABLED` from `args.profile` immediately after parsing — using `global _PROFILE_ENABLED`.

- [ ] **Step 7: Verify the instrument reproduces the spec's headline number**

Run: `python3 scripts/remove_gif_background.py <a 60-frame 640px gif> /tmp/p.webp --auto --profile` Expected: `analyze` appears with `x2` and roughly 60% of total. **If it does not show `x2`, stop — either the decorator is not applied to `analyze` or Task 2's premise is wrong.**

- [ ] **Step 8: Document and commit**

Add `--profile` to SKILL.md's usage block and a paragraph to `references/flag-reference.md`. Run `python3 scripts/audit_docs.py`.

```bash
git add scripts/remove_gif_background.py scripts/harness/test_profile_instrument.py SKILL.md references/flag-reference.md
git commit -m "feat: --profile, so the next redundancy is visible instead of hunted"
```

---

### Task 2: Deep-copying in-process memo for `analyze()`

**Files:**
- Modify: `scripts/remove_gif_background.py` (memo wrapper around `analyze`, applied under `_profiled`)
- Test: `scripts/harness/test_analyze_memo.py`

**Interfaces:**
- Consumes: `_PROFILE` and `_profiled` from Task 1.
- Produces: `_analyze_memo_clear()` — resets the memo; the multi-file path calls it between files so a long batch cannot grow the memo without bound.

**Why in-process and not the disk cache:** a memo over one invocation of a pure function cannot go stale by construction — no fingerprint, no key-versioning, nothing to invalidate. It is also safe to ship in the package, where a disk cache would be dead weight in an ephemeral sandbox.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_analyze_memo.py
import contextlib, importlib.util, io, pathlib, sys

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'remove_gif_background.py'

def _load():
    spec = importlib.util.spec_from_file_location('rgb_memo', _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules['rgb_memo'] = m
    spec.loader.exec_module(m)
    return m

def test_auto_analyses_the_same_file_exactly_once(tmp_path, sample_gif):
    m = _load()
    m._PROFILE_ENABLED = True
    sys.argv = ['x', str(sample_gif), str(tmp_path / 'o.webp'), '--auto']
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        with contextlib.suppress(SystemExit):
            m.main()
    assert len(m._PROFILE.get('analyze', [])) == 1, \
        f"expected ONE analyze() call, got {len(m._PROFILE.get('analyze', []))}"

def test_the_memo_hands_back_a_COPY_not_the_same_object(sample_gif):
    """verify() mutates the analyze result 24 times and recommend() 6. Sharing one object
    would give verify()'s report a recommended_format key it must not have."""
    m = _load()
    a = m.analyze(str(sample_gif))
    b = m.analyze(str(sample_gif))
    assert a is not b, 'memo returned the SAME object -- mutations will leak between callers'
    a['recommended_format'] = 'poisoned'
    assert 'recommended_format' not in b, 'mutating one result changed the other'

def test_a_different_tolerance_is_a_different_key(sample_gif):
    m = _load()
    m._PROFILE_ENABLED = True
    m.analyze(str(sample_gif), tolerance=15)
    m.analyze(str(sample_gif), tolerance=40)
    assert len(m._PROFILE.get('analyze', [])) == 2, 'tolerance must be part of the key'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/harness/test_analyze_memo.py -v` Expected: FAIL — `expected ONE analyze() call, got 2`

- [ ] **Step 3: Write minimal implementation**

```python
_ANALYZE_MEMO = {}


def _analyze_memo_clear():
    """Drop the memo. Called between files in the multi-file path so a long batch cannot
    grow it without bound -- each analysis holds a substantial report."""
    _ANALYZE_MEMO.clear()


def _memoized_analyze(fn):
    """One invocation, one analysis per (path, mtime, size, max_samples, tolerance).

    ⚠️ RETURNS A DEEP COPY, AND THAT IS THE WHOLE CORRECTNESS ARGUMENT. `verify()` mutates
    the analyze result 24 times -- it builds its ENTIRE report on top of that dict -- and
    `recommend()` mutates it 6 times (`report['recommended_format']`). Handing both the same
    object would give verify()'s output a key it does not have today, and in a multi-file run
    the second file's verify would inherit the first file's mutations. Measured by AST scan
    2026-09-01, not assumed. See docs/investigations/2026-09-01-analysis-cost-and-the-
    missing-instrument.md SS3.

    mtime and size are in the key so a source rewritten mid-run cannot serve a stale answer,
    even though --auto only ever writes the OUTPUT.
    """
    import functools   # `copy` and `os` ARE already at module scope (lines 64, 66)

    @functools.wraps(fn)
    def wrapper(input_path, max_samples=40, tolerance=15, *a, **k):
        try:
            st = os.stat(input_path)
            key = (os.path.abspath(input_path), st.st_mtime_ns, st.st_size,
                   max_samples, tolerance)
        except OSError:
            return fn(input_path, max_samples, tolerance, *a, **k)
        if key not in _ANALYZE_MEMO:
            _ANALYZE_MEMO[key] = fn(input_path, max_samples, tolerance, *a, **k)
        return copy.deepcopy(_ANALYZE_MEMO[key])
    return wrapper
```

Apply as `analyze = _profiled(_memoized_analyze(analyze))` so the profile counts REAL computations, not memo hits. Call `_analyze_memo_clear()` between files in the multi-file loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/harness/test_analyze_memo.py -v` Expected: PASS (3 tests)

- [ ] **Step 5: Prove the output is unchanged, not just faster**

Run, on at least three assets including one that refuses and one with `--recover-fade-alpha`:

```bash
git stash && python3 scripts/remove_gif_background.py <asset> /tmp/pre.webp --auto && git stash pop
python3 scripts/remove_gif_background.py <asset> /tmp/post.webp --auto
cmp /tmp/pre.webp /tmp/post.webp && echo "BYTE-IDENTICAL"
python3 scripts/remove_gif_background.py <asset> /tmp/post.webp --verify | grep -c recommended_format
```

Expected: `BYTE-IDENTICAL`, and the `--verify` report contains **zero** `recommended_format` keys.

- [ ] **Step 6: Run the full render gate**

Run: `python3 scripts/harness/render_baseline.py --set fast --script <pristine main copy> --out /tmp/pre.json` then the same without `--script` to `/tmp/post.json`, then `--compare /tmp/pre.json /tmp/post.json`. Expected: **`0 changed`.** A speedup that moves one rendered byte is a regression, not a speedup.

- [ ] **Step 7: Measure the gain back to back and commit**

Run `--auto --profile` on the same asset three times before and three times after; quote the **minimum** of each, not the mean. Record the pair in the investigation doc.

```bash
git add scripts/remove_gif_background.py scripts/harness/test_analyze_memo.py
git commit -m "perf: analyse each file once per --auto run, not twice"
```

---

### Task 3: Key the analysis cache on content, not mtime

**Files:**
- Modify: `scripts/harness/analysis_cache.py:85` region (the key construction inside `analysis_fingerprint`'s caller — the asset half of the key, not the script fingerprint)
- Test: `scripts/harness/test_analysis_fingerprint.py` (extend the existing suite)

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: no new public names. The cache directory layout changes, so the first run after this lands is cold by design.

- [ ] **Step 1: Write the failing test**

```python
def test_the_same_bytes_at_a_new_path_and_mtime_still_HIT(tmp_path):
    """The test suite regenerates synthetic fixtures into a fresh tmpdir every run, so an
    mtime-keyed cache misses 100% of its highest-reuse consumer -- silently, because a warm
    cache and one that never hits look identical from outside."""
    src = tmp_path / 'a' / 'fixture.gif'; src.parent.mkdir()
    src.write_bytes(FIXTURE_BYTES)
    first = cache_key_for(src)
    twin = tmp_path / 'b' / 'fixture.gif'; twin.parent.mkdir()
    twin.write_bytes(FIXTURE_BYTES)          # same bytes, new path, new mtime
    assert cache_key_for(twin) == first

def test_DIFFERENT_bytes_still_MISS(tmp_path):
    """The negative half. Without it, a key that ignored the asset entirely would pass."""
    a = tmp_path / 'a.gif'; a.write_bytes(FIXTURE_BYTES)
    b = tmp_path / 'b.gif'; b.write_bytes(FIXTURE_BYTES + b'\x00')
    assert cache_key_for(a) != cache_key_for(b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/harness/test_analysis_fingerprint.py -k content -v` Expected: FAIL — the two paths produce different keys.

- [ ] **Step 3: Write minimal implementation**

Replace the `(mtime_ns, size)` half of the asset key with `hashlib.sha256(asset_bytes).hexdigest()[:16]`, keeping `analysis_fingerprint(script)` unchanged. Read the bytes once and reuse them for the analysis that follows, so the hash costs no extra I/O.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/harness/test_analysis_fingerprint.py -v` Expected: PASS, including all twelve pre-existing paired falsifiers.

- [ ] **Step 5: Re-run the 28-commit historical measurement**

The current key was chosen on evidence: 9 of 28 real product commits keep a warm cache. **Reproduce that measurement with the new key before believing any improvement.** A refinement that cannot show a gain on the same population is not worth the extra failure mode.

- [ ] **Step 6: Measure the suite, back to back, and commit**

Run `python3 -m pytest scripts/harness -q --durations=15` cold, then again warm. Expected: the ~773s spent by the fifteen slowest tests drops materially on the warm run. Quote both numbers.

```bash
git add scripts/harness/analysis_cache.py scripts/harness/test_analysis_fingerprint.py
git commit -m "perf: key the analysis cache on content, so the test suite can hit it"
```

---

### Task 4: Commit a PRE baseline so the render gate stops re-rendering `main`

**Files:**
- Create: `scripts/harness/baselines/fast-<main-script-sha>.json`
- Modify: `scripts/harness/render_baseline.py` (`--compare` grows a `--baseline` mode that loads the committed file when its SHA matches `main`'s script)
- Test: `scripts/harness/test_baseline_reuse.py`

- [ ] **Step 1: Write the failing test**

```python
def test_a_baseline_whose_sha_does_not_match_is_REFUSED(tmp_path):
    """A stale baseline silently turns the gate into a rubber stamp. It must refuse, not
    fall back to comparing against the wrong revision."""
    stale = tmp_path / 'fast-deadbeef.json'; stale.write_text('{"records": {}}')
    with pytest.raises(SystemExit, match='does not match'):
        load_baseline(stale, expected_sha='cafe1234')

def test_a_matching_baseline_LOADS(tmp_path):
    good = tmp_path / 'fast-cafe1234.json'; good.write_text('{"records": {}}')
    assert load_baseline(good, expected_sha='cafe1234') == {'records': {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/harness/test_baseline_reuse.py -v` Expected: FAIL — `load_baseline` is not defined.

- [ ] **Step 3: Write minimal implementation**

Name the file by the SHA of `main`'s `scripts/remove_gif_background.py`. Refuse on mismatch with a message naming both SHAs and the command that regenerates it. **Never fall back** to rendering silently — a gate that quietly compares against the wrong revision is worse than a slow one.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest scripts/harness/test_baseline_reuse.py -v` Expected: PASS

- [ ] **Step 5: Generate, verify and commit**

Generate the baseline from `main`, then confirm a full PRE/POST pair and a baseline/POST pair give **the same verdict** on a known-unchanged branch. Then measure the wall-clock saving back to back.

```bash
git add scripts/harness/baselines scripts/harness/render_baseline.py scripts/harness/test_baseline_reuse.py
git commit -m "perf: reuse a committed PRE baseline instead of re-rendering main every run"
```

---

### Task 5: Record per-unit durations, then schedule longest-first

**Files:**
- Modify: `scripts/harness/render_baseline.py` (record `seconds` per record; sort the work queue by the previous run's duration, descending)
- Test: `scripts/harness/test_render_scheduling.py`

**Interfaces:**
- Consumes: the baseline JSON from Task 4, which is where prior durations live.
- Produces: a `seconds` field on every record.

⚠️ **Ordering matters: durations must be RECORDED before scheduling can use them.** The harness does not record them today, which is why the spec could not quantify this lever.

- [ ] **Step 1: Write the failing test**

```python
def test_every_record_carries_its_duration():
    rec = render_one(asset)
    assert isinstance(rec.get('seconds'), float) and rec['seconds'] > 0

def test_the_queue_is_ordered_LONGEST_first():
    prior = {'slow.gif': 200.0, 'fast.gif': 2.0, 'mid.gif': 40.0}
    assert order_queue(['fast.gif', 'mid.gif', 'slow.gif'], prior) == \
        ['slow.gif', 'mid.gif', 'fast.gif']

def test_an_asset_with_NO_prior_duration_goes_FIRST():
    """Unknown cost is treated as potentially the longest -- the tail risk a run ends on."""
    prior = {'known.gif': 5.0}
    assert order_queue(['known.gif', 'new.gif'], prior)[0] == 'new.gif'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest scripts/harness/test_render_scheduling.py -v` Expected: FAIL — `order_queue` is not defined.

- [ ] **Step 3–4: Implement `order_queue` and the `seconds` field, and re-run until the tests pass.**

- [ ] **Step 5: Measure and commit**

Run the fast set three times before and three times after, on an otherwise idle machine, and quote the **minimum** of each. ⚠️ Do not quote a single pair: this repo has recorded the same set at 976s and 488s on consecutive runs.

```bash
git add scripts/harness/render_baseline.py scripts/harness/test_render_scheduling.py
git commit -m "perf: schedule the render gate longest-first, on recorded durations"
```

---

### Task 6: Cap BLAS threads in harness workers

**Files:**
- Modify: `scripts/harness/render_baseline.py` and `scripts/harness/run_populations.py` (subprocess `env`)

**Value:** measured 1.13× (67.1s → 59.2s, interleaved A/B/A/B at 3 workers, reproducible across both reps). Harness-only: a single-file user run wants every thread, and the claude.ai sandbox has one core.

- [ ] **Step 1: Set the caps on the subprocess environment**

```python
_WORKER_ENV = dict(os.environ, VECLIB_MAXIMUM_THREADS='1', OMP_NUM_THREADS='1',
                   OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
```

numpy here is Apple **Accelerate**, which multithreads; `default_jobs()` already runs one worker per performance core, so each worker's internal threads oversubscribe the same cores.

- [ ] **Step 2: Prove the output is unchanged**

Run the fast set with and without the caps and `--compare` the two. Expected: **`0 changed`.** Thread counts must not move a rendered byte; if they do, that is a far more interesting bug than the speedup.

- [ ] **Step 3: Measure back to back and commit**

```bash
git add scripts/harness/render_baseline.py scripts/harness/run_populations.py
git commit -m "perf: cap BLAS threads in harness workers (1.13x, measured)"
```

---

## Self-Review

**Spec coverage.** Spec §1–3 → Tasks 1–2. §5 (the class) → Task 1. §6.1 → Task 4. §6.2 → Task 3. §7.1 → Task 6. §7.2 → Tasks 4 and 5. §8's non-caching levers → **deliberately not planned**: profiling inside `analyze()` has no measurement yet (Task 1 is its prerequisite), parallelising `analyze()` is worth zero on the deployment target, and "route away from `--auto`" is documentation, not code. §6.3 (ambient over-invalidation) and §7.3 (the ART-LOSS assets) are **not in this plan** — the first needs the 28-commit study re-run and the second is a correctness investigation, not a performance one. Both remain filed in `gif-deferred-list.md`.

**Placeholder scan.** No "TBD", no "add error handling", no "similar to Task N". Every code step carries real code. Task 5's Steps 3–4 are compressed because the two functions are fully specified by their tests — if the implementer wants them expanded, the tests are the specification.

**Type consistency.** `_PROFILE` is `dict[str, list[float]]` in Task 1 and read as such in Task 2. `_profiled` and `_memoized_analyze` compose in one documented order (`_profiled(_memoized_analyze(analyze))`) so the profile counts real computations, not memo hits. `cache_key_for` and `load_baseline` / `order_queue` appear only in their own tasks.

**Known risk, stated plainly.** Task 2 is the only task that touches the shipped product's behaviour. Its correctness rests entirely on the deep copy, which rests on a mutation count established by AST scan in the spec. If that scan was wrong, Task 2 ships a silent output change — which is why Step 5 compares bytes and Step 6 runs the full render gate before the commit.
