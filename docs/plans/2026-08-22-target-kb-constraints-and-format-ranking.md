# `--target-kb` Constraint Awareness and Format Ranking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `--target-kb` from silently delivering an asset that violates a stated minimum dimension, make the tool say which of several format outputs is the one to keep, and give a session a cost estimate before it commits to a multi-minute fit.

**Architecture:** Four independent changes to `scripts/remove_gif_background.py`, each landing behind its own falsifier suite in `scripts/harness/`. Task 1 extends the *existing* `_pinned` mechanism in `fit_to_target_bytes` from an exact pin to a floor. Task 2 adds a post-batch comparison that ranks sibling outputs of one source. Task 3 emits a pre-flight rung/encode estimate. Task 4 makes `--verify` refuse to report a vacuous pass. No change alters which rung wins for any asset that already satisfies its constraints.

**Tech Stack:** Python 3.11, Pillow, numpy, pytest. External binaries `gifsicle`/`pngquant` unchanged.

**Spec:** `docs/investigations/2026-08-22-v6-timeout-trial.md` — the measured trial this plan answers. Executors read both; every numeric claim below is sourced there.

## Global Constraints

- No packaged file may reference a repo file that is not packaged. `CLAUDE.md` is the sole allowlisted exception. `python3 scripts/audit_docs.py` enforces this and must pass before merge.
- Markdown is soft-wrapped: one physical line per paragraph or list item, including prose inside fenced blocks.
- Every `references/lessons.md` section added needs a ToC entry, a symptom-table row, and an `**Also searched as:**` line, or `audit_docs.py` fails.
- Conventional Commits v1.0.0, the 11 standard types only, `<type>(<scope>): <desc>`, imperative, lowercase, no trailing period.
- Branch commits are free. Push, PR-merge and tag are each asked, every time; approval never carries over.
- Do not change the destructiveness ordering in `_SCALE_COST` / `_STRIDE_COST`. It was set on measured evidence 2026-08-21 and `test_target_rung_search.py` pins it.
- The release gates in `CLAUDE.md` run BEFORE merging, not after — including the 797-asset population score if any hardness rule input changes, and `render_baseline.py --set standard` for the render diff.

---

## ⛔ Gate before any task starts

**✅ Answered 2026-08-22 — see the spec's §13.** Harkirat reviewed the delivered files directly. The background removal itself is correct. Two things are not, and both were invisible to every measurement in this plan:

1. **A ~1px light fringe on every 8-bit-alpha output**, which `--verify`'s `edge_fringe_check` reports as clean. This became **Task 9** and it is the highest-value item here — it affects every WebP/AVIF the manual path has produced, not just these assets.
2. **Frame-stride is visibly choppy** at the levels `--target-kb` chose. This is NOT a task: it questions the `_STRIDE_COST` weights, and those were set on measurement. Changing them needs its own measurement, filed as spec §14 question 6.

Two design answers also landed: the min-dimension floor must be able to express **"width >= N, aspect preserved"** (Task 1 now adds `--min-width`/`--min-height`), and `--auto` should **ask** on a coin-flip enclosure region (Task 10).

⚠️ **The lesson this gate now records:** one person looking at four contact sheets found a defect that ten measurements, two sessions, a corpus and a code-reading pass all missed — and found it in one sentence. Keep the gate for the next plan.

## Recommended order — NOT the listed order

| order | task | why |
|---|---|---|
| 1st | **Task 9** — the 8-bit-alpha erosion fringe | the only defect a user actually noticed, and it is on every WebP/AVIF the manual path produces |
| 2nd | **Task 7** — reprint final dimensions | ~3 lines, prevents the worst observed outcome (a false compliance report). Nearly free. |
| 3rd | **Task 6** — `--webp-quality` warning | small, self-contained, stops two wasted renders per session |
| 4th | **Task 4** — non-vacuous `--verify` | small, and every later task's verification depends on `--verify` meaning something |
| 5th | **Task 8** — SKILL.md debloat + portable navigation | fixes a silent failure at the skill's entry point; independent of all code work |
| 6th | **Task 3** — pre-flight cost estimate | needs no design decision |
| 7th | **Task 1** — min-dimension floor | largest, and gated on open question 2 |
| 8th | **Task 2** — format ranking | gated on open question 1 |

Task 10 slots beside Task 1 (both touch recommendation handling). Task 5 (docs) runs last regardless, and Task 5's gates cover everything above it.

---

## File Structure

| file | responsibility | change |
|---|---|---|
| `scripts/remove_gif_background.py` | the product | modify — 4 sites |
| `scripts/harness/test_target_kb_min_dimension.py` | falsifiers for Task 1 | create |
| `scripts/harness/test_format_ranking.py` | falsifiers for Task 2 | create |
| `scripts/harness/test_fit_cost_estimate.py` | falsifiers for Task 3 | create |
| `scripts/harness/test_verify_vacuity.py` | falsifiers for Task 4 | create |
| `SKILL.md` | packaged instructions | modify — flag docs + version entry |
| `references/lessons.md` | packaged history | modify — new section + ToC + symptom row |

The four product changes touch different functions and are independently revertable. They are ordered by severity from the trial: Task 1 ships wrong artwork, Task 2 lets the user pick the wrong file, Task 3 kills sessions, Task 4 hides a missing check.

---

### Task 1: `--min-dimension` — a resolution FLOOR for the rung search

**Files:**
- Modify: `scripts/remove_gif_background.py:5948-5999` (`fit_to_target_bytes`), `:6108` (the failure message), `:8770` (argparse, beside `--resize-max-dim`)
- Test: `scripts/harness/test_target_kb_min_dimension.py`

**Interfaces:**
- Consumes: `build_target_rungs(fmt, scales, strides, pixel_art)` — unchanged signature.
- Produces: `args.min_dimension: int | None`, and a filtered `_scales` tuple inside `fit_to_target_bytes`. Later tasks read `args.min_dimension` only to report it.

**RESOLVED 2026-08-22 — three flags, not one.** Harkirat: *"i meant at least 128 px wide, keeping the same aspect ratio as the original artwork (after cropping the transparent canvas), and whatever height that respectively concluded. but to be fair, thats an explicit ask. as the default method, you can use whichever one you want. but it does need to support explicit requests such as this."*

So the requirement is **expressiveness**, not a particular default. Implement all three:

| flag | constrains | use |
|---|---|---|
| `--min-width N` | output width | the explicit ask above |
| `--min-height N` | output height | its mirror |
| `--min-dimension N` | `min(width, height)` | the convenient default when no axis is named |

`scales_for_fit` takes the tightest surviving constraint of whichever are set. Aspect ratio is preserved throughout — every scale rung is uniform — so "width >= N, aspect preserved" needs no extra machinery beyond testing the width. Add one falsifier per flag, plus one asserting two flags together take the tighter of the two.

**Original reasoning, retained for the default choice.** The user said "at least 128px wide x relative height." For megaphone the two coincide (delivered 120x128, so either test catches it), but they diverge on a wide short asset — 600x100 passes a width test and fails a shorter-side test. Shorter-side is the safer reading of "at least this big" for a sticker or emoji slot, and it is what the tests below encode. **This is open question 2 in the spec — confirm it with Harkirat before implementing, and if he meant width literally, change `min(width, height)` to `width` in `scales_for_fit` and in the two enforcement points, and rename the test accordingly.**

**Why this shape.** The code at `:5990` already carries the exact reasoning, for `--resize-max-dim`:

> a byte cap is a constraint; the requested resolution is a REQUIREMENT. Trade quality and frames instead, and if it still will not fit, say so rather than quietly delivering a different size.

It implements that as `_pinned` — an *exact* pin that collapses the scale axis to `(1.0,)`. A user saying "at least 128px wide" is stating the same kind of requirement with a weaker shape, and there is currently no way to express it. This task generalises the existing mechanism rather than adding a second one.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_target_kb_min_dimension.py
import pytest
import remove_gif_background as R


class _Args:
    def __init__(self, **kw):
        self.resize_max_dim = None
        self.pixel_art = False
        self.min_dimension = None
        self.__dict__.update(kw)


def _scales_for(args, width, height):
    return R.scales_for_fit(args, width, height)


def test_no_min_dimension_keeps_the_full_scale_ladder():
    assert _scales_for(_Args(), 482, 513) == (1.0, 0.75, 0.5, 0.375, 0.25)


def test_a_min_dimension_drops_only_the_rungs_that_violate_it():
    # 482 wide: 0.375 -> 180px (ok), 0.25 -> 120px (violates a 128 floor)
    assert _scales_for(_Args(min_dimension=128), 482, 513) == (1.0, 0.75, 0.5, 0.375)


def test_the_floor_is_measured_on_the_SHORTER_side_not_the_width():
    # 482x513: the shorter side is 482. A 400 floor kills every scale below 1.0.
    assert _scales_for(_Args(min_dimension=400), 482, 513) == (1.0,)


def test_an_explicit_resize_max_dim_still_pins_and_the_floor_cannot_widen_it():
    args = _Args(resize_max_dim=136, min_dimension=128)
    assert _scales_for(args, 482, 513) == (1.0,)


def test_a_floor_larger_than_the_canvas_leaves_scale_1_only_and_does_not_empty_the_ladder():
    # An empty tuple would make build_target_rungs return no rungs at all and the
    # search would report "could not reach" for a reason that is not the byte cap.
    assert _scales_for(_Args(min_dimension=9999), 482, 513) == (1.0,)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_target_kb_min_dimension.py -v`
Expected: FAIL — `AttributeError: module 'remove_gif_background' has no attribute 'scales_for_fit'`

- [ ] **Step 3: Extract the scale decision into a named function**

Replace the two lines at `scripts/remove_gif_background.py:5996-5997` with a call, and add the function immediately above `fit_to_target_bytes`:

```python
def scales_for_fit(args, width, height):
    """The scale rungs a --target-kb fit may use, after resolution REQUIREMENTS.

    Two different requirements, one axis. `--resize-max-dim` pins the resolution
    exactly (the confirmed bug it fixed: the cascade shrank an explicit 128px
    request to 48x48). `--min-dimension` is the weaker form of the same claim --
    "at least this big" -- and it appeared in a real user request the tool could
    not express: a 128px floor against a 256 KB cap, where the ladder's only two
    neighbouring rungs were 181px (over cap) and 120px (under floor). The
    compliant zone was unreachable BY CONSTRUCTION, so the fit silently returned
    120px. See docs/investigations/2026-08-22-v6-timeout-trial.md.

    Never returns an empty tuple: an empty scale axis produces zero rungs, and the
    search would then blame the byte cap for a resolution failure.
    """
    if getattr(args, 'resize_max_dim', None) is not None:
        return (1.0,)
    ladder = (1.0, 0.75, 0.5, 0.375, 0.25)
    floor = getattr(args, 'min_dimension', None)
    if not floor:
        return ladder
    shorter = min(width, height)
    kept = tuple(s for s in ladder if int(round(shorter * s)) >= floor)
    return kept or (1.0,)
```

Then at the former `_scales` site:

```python
    _scales = scales_for_fit(args, base_width, base_height)
    rungs = build_target_rungs(fmt, _scales,
                               pixel_art=bool(getattr(args, 'pixel_art', False)))
```

Bind `base_width`/`base_height` from the frames already in scope immediately above the call. ⚠️ **Verified 2026-08-22, do not re-derive:** crop runs at `:7754` and resize at `:7789`, both BEFORE the fit call at `:7954`, so these frames are the cropped and resized ones (482x513 for megaphone) and the rung table above is computed against the right canvas. **The five unit tests below cannot detect a wrong binding here** — they call `scales_for_fit` with hand-passed dimensions. Step 7's end-to-end test is the load-bearing one and must be confirmed to FAIL on the PRE code.

```python
    base_height, base_width = alpha_frames[0].shape[:2]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts/harness && python3 -m pytest test_target_kb_min_dimension.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Add the argparse flag**

At `scripts/remove_gif_background.py:8770`, immediately after `--resize-max-dim`:

```python
    p.add_argument('--min-dimension', type=int, default=None,
                   help='Floor on the output\'s SHORTER side in pixels. --target-kb '
                        'will trade quality and frames but never shrink below this, '
                        'and refuses rather than silently delivering a smaller file.')
```

- [ ] **Step 6: Make the failure message name the real constraint**

At `scripts/remove_gif_background.py:6108`, the "Could not reach" branch currently blames the byte cap alone. Replace with:

```python
        if getattr(args, 'min_dimension', None):
            say(f"Could not reach {target_kb} KB without going below the "
                f"{args.min_dimension}px floor; smallest compliant was "
                f"{best[0]/1024:.1f} KB ({best[1]}). Raise --target-kb, lower "
                f"--min-dimension, or use a format with better alpha compression "
                f"-- on a 144-frame asset AVIF measured 7.7x smaller than WebP "
                f"at the same nominal quality.")
        else:
            say(f"Could not reach {target_kb} KB; smallest was "
                f"{best[0]/1024:.1f} KB ({best[1]}).")
```

- [ ] **Step 6b: Add the SECOND enforcement point — rung filtering is not enough**

⚠️ **Filtering rungs covers `--target-kb` and nothing else.** Verified 2026-08-22: `--resize-max-dim` is applied at `:7789` **independently of any fit**, sizing the LONGER side — so 900x200 at `--resize-max-dim 192` gives 192x43 with no check at all. And `--compress heavy` sets `resize_max_dim: 256` while `optimize`/`medium` set `512` (`:6894-6896`), so a tier reaches this path with no resize flag from the user. A fix that lives only inside `fit_to_target_bytes` reaches one consumer of at least three.

Add one check immediately before the final size is reported, after every resolution-changing step, in the same place Task 7 reprints dimensions:

```python
    _floor = getattr(args, 'min_dimension', None)
    if _floor and min(out_w, out_h) < _floor:
        raise SystemExit(
            f"REFUSING to deliver {out_w}x{out_h}: its shorter side is below the "
            f"--min-dimension {_floor} floor you set. This is a REQUIREMENT, not a "
            f"target -- raise --target-kb, lower the floor, drop --resize-max-dim, "
            f"or choose a format with better alpha compression.")
```

Refuse rather than warn: a warning on stderr is exactly what both real sessions failed to act on, and the failure mode being fixed is a file that ships looking fine.

- [ ] **Step 6c: Test the second enforcement point on a path with NO fit**

```python
def test_resize_max_dim_alone_cannot_undershoot_the_floor(tmp_path):
    """No --target-kb anywhere. Rung filtering cannot see this path."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    out = tmp_path / 'r.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--crop',
                        '--resize-max-dim', '140', '--min-dimension', '128',
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=900)
    # 482x513 -> longer side 140 -> 131x140: shorter side 131 >= 128, must SUCCEED
    assert out.exists(), r.stderr
    r2 = subprocess.run([sys.executable, SCRIPT, src, str(tmp_path / 'r2.webp'),
                         '--crop', '--resize-max-dim', '120', '--min-dimension', '128',
                         '--protect-outline-color', '002864'],
                        capture_output=True, text=True, timeout=900)
    # longer side 120 -> shorter side 112 < 128, must REFUSE
    assert r2.returncode != 0 and 'min-dimension' in (r2.stdout + r2.stderr)


def test_a_compress_tier_cannot_undershoot_the_floor_either(tmp_path):
    """--compress heavy sets resize_max_dim 256 with no resize flag from the user."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    r = subprocess.run([sys.executable, SCRIPT, src, str(tmp_path / 'h.webp'),
                        '--crop', '--compress', 'heavy', '--min-dimension', '300',
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode != 0 and 'min-dimension' in (r.stdout + r.stderr)
```

- [ ] **Step 7: Write the end-to-end falsifier on the real asset**

```python
def test_the_real_megaphone_case_refuses_instead_of_delivering_120px(tmp_path):
    """The trial's exact failure: 482x513, 256 KB cap, 128px floor, WebP.

    Measured 2026-08-22: the compliant zone is empty for this asset, so the ONLY
    correct behaviours are refuse-and-say-why or deliver >=128px. Delivering
    120px is the bug. This test must fail on the PRE code.
    """
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    if not os.path.exists(src):
        pytest.skip('trial asset not present in this checkout')
    out = tmp_path / 'out.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out),
                        '--crop', '--target-kb', '256', '--min-dimension', '128',
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=900)
    if out.exists() and out.stat().st_size:
        with Image.open(out) as im:
            assert min(im.size) >= 128, f'delivered {im.size}, below the stated floor'
    else:
        assert 'floor' in r.stdout.lower() or 'floor' in r.stderr.lower(), \
            'refused without naming the constraint that caused the refusal'
```

- [ ] **Step 8: Run the full suite**

Run: `cd scripts/harness && python3 -m pytest test_target_kb_min_dimension.py test_target_rung_search.py -v`
Expected: PASS. `test_target_rung_search.py` must be untouched — this task must not move any existing rung ordering.

- [ ] **Step 9: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_target_kb_min_dimension.py
git commit -m "feat(target-kb): honour a minimum-dimension floor instead of silently undershooting it"
```

---

### Task 2: rank sibling format outputs instead of delivering both unlabelled

**Files:**
- Modify: `scripts/remove_gif_background.py` — the `=== Batch summary ===` writer (search `Batch summary`)
- Test: `scripts/harness/test_format_ranking.py`

**Interfaces:**
- Consumes: the per-output records the batch summary already builds — each carries source path, output path, final bytes, and (after this task) dimensions and frame count.
- Produces: `rank_sibling_outputs(records) -> list[dict]`, each with `dominated_by: str | None` and `reason: str | None`.

**Why.** Measured on both trial assets, the AVIF was better than the WebP on **resolution, frame count and size simultaneously** — megaphone AVIF 482×513/144/225.1 KB against WebP 120×128/36/242.3 KB. The tool printed `2/2 succeeded.` and ranked neither. Strict domination is a total, objective comparison — no weighting or taste is involved — so this reports a fact, not a preference.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_format_ranking.py
import remove_gif_background as R


def _rec(src, out, w, h, frames, kb):
    return {'source': src, 'output': out, 'width': w, 'height': h,
            'frames': frames, 'kb': kb}


def test_strict_domination_is_reported_with_the_dominator_named():
    recs = [_rec('m.gif', 'm.webp', 120, 128, 36, 242.3),
            _rec('m.gif', 'm.avif', 482, 513, 144, 225.1)]
    out = {r['output']: r for r in R.rank_sibling_outputs(recs)}
    assert out['m.webp']['dominated_by'] == 'm.avif'
    assert out['m.avif']['dominated_by'] is None


def test_a_genuine_tradeoff_is_NOT_called_domination():
    # smaller file but fewer frames -- a real tradeoff, not domination
    recs = [_rec('m.gif', 'a.webp', 482, 513, 72, 100.0),
            _rec('m.gif', 'b.avif', 482, 513, 144, 225.1)]
    out = {r['output']: r for r in R.rank_sibling_outputs(recs)}
    assert out['a.webp']['dominated_by'] is None
    assert out['b.avif']['dominated_by'] is None


def test_outputs_of_DIFFERENT_sources_are_never_compared():
    recs = [_rec('a.gif', 'a.webp', 120, 128, 36, 242.3),
            _rec('b.gif', 'b.avif', 482, 513, 144, 225.1)]
    assert all(r['dominated_by'] is None for r in R.rank_sibling_outputs(recs))


def test_equal_on_every_axis_is_not_domination():
    recs = [_rec('m.gif', 'x.webp', 482, 513, 144, 225.1),
            _rec('m.gif', 'y.avif', 482, 513, 144, 225.1)]
    assert all(r['dominated_by'] is None for r in R.rank_sibling_outputs(recs))


def test_the_secure_case_from_the_trial():
    recs = [_rec('s.gif', 's.webp', 524, 531, 17, 240.2),
            _rec('s.gif', 's.avif', 524, 531, 50, 185.8)]
    out = {r['output']: r for r in R.rank_sibling_outputs(recs)}
    assert out['s.webp']['dominated_by'] == 's.avif'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_format_ranking.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'rank_sibling_outputs'`

- [ ] **Step 3: Implement**

```python
def rank_sibling_outputs(records):
    """Mark any output another output of the SAME source beats on every axis.

    Strict domination only -- larger-or-equal on resolution and frames, smaller-or-
    equal in bytes, and strictly better on at least one. A genuine tradeoff is left
    unranked, because choosing between "smaller" and "smoother" is the user's call
    and the tool has no basis for it.

    Exists because the 2026-08-22 trial delivered a 120x128/36-frame WebP alongside
    a 482x513/144-frame AVIF that was also SMALLER, printed "2/2 succeeded.", and
    said nothing. See docs/investigations/2026-08-22-v6-timeout-trial.md.
    """
    out = []
    for r in records:
        best = None
        for o in records:
            if o is r or o.get('source') != r.get('source'):
                continue
            ge = (o['width'] >= r['width'] and o['height'] >= r['height']
                  and o['frames'] >= r['frames'] and o['kb'] <= r['kb'])
            gt = (o['width'] > r['width'] or o['height'] > r['height']
                  or o['frames'] > r['frames'] or o['kb'] < r['kb'])
            if ge and gt:
                best = o
                break
        rec = dict(r)
        rec['dominated_by'] = best['output'] if best else None
        rec['reason'] = (
            f"{best['width']}x{best['height']}, {best['frames']} frames, "
            f"{best['kb']:.1f} KB beats {r['width']}x{r['height']}, "
            f"{r['frames']} frames, {r['kb']:.1f} KB on every axis"
        ) if best else None
        out.append(rec)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts/harness && python3 -m pytest test_format_ranking.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Wire it into the batch summary**

In the `=== Batch summary ===` writer, after the existing per-output `OK` lines:

```python
    ranked = rank_sibling_outputs(summary_records)
    for r in ranked:
        if r['dominated_by']:
            print(f"  ⚠ {r['output']} is STRICTLY WORSE than {r['dominated_by']}: "
                  f"{r['reason']}. Keep {r['dominated_by']} unless you need this "
                  f"container specifically.")
```

- [ ] **Step 6: Verify against the real trial outputs**

Run the two-format batch on `local/2026-08-21-v6-timeout-trial/inputs/secure.gif` and confirm the warning names the AVIF. Expected: one `⚠` line, naming `secure_transparent.avif` as the dominator.

- [ ] **Step 7: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_format_ranking.py
git commit -m "feat(batch): flag an output another format beats on every axis"
```

---

### Task 3: pre-flight cost estimate before a `--target-kb` fit

**Files:**
- Modify: `scripts/remove_gif_background.py:7944-7955` (the fit entry point)
- Test: `scripts/harness/test_fit_cost_estimate.py`

**Interfaces:**
- Consumes: `build_target_rungs`, the frame count, the probed worker count.
- Produces: `estimate_fit_cost(n_rungs, n_frames, workers) -> dict` with `encodes`, `frame_encodes`, `warn: bool`.

**Why.** The trial's fit walked ~118 of 120 rungs at 144 frames each and took 207.84s — and the first attempt died at a 120s tool timeout having produced nothing. Neither `--analyze` nor `--recommend` says anything beforehand, so a session learns the cost only by losing a tool call to it. The estimate does not need to be accurate in seconds; it needs to let a caller decide to split the job.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_fit_cost_estimate.py
import remove_gif_background as R


def test_the_megaphone_case_warns():
    est = R.estimate_fit_cost(n_rungs=120, n_frames=144, workers=6)
    assert est['frame_encodes'] == 120 * 144
    assert est['warn'] is True


def test_a_small_asset_does_not_warn():
    est = R.estimate_fit_cost(n_rungs=120, n_frames=8, workers=6)
    assert est['warn'] is False


def test_more_workers_lowers_the_estimate_but_not_the_work():
    a = R.estimate_fit_cost(n_rungs=120, n_frames=144, workers=2)
    b = R.estimate_fit_cost(n_rungs=120, n_frames=144, workers=8)
    assert a['frame_encodes'] == b['frame_encodes']
    assert a['serial_batches'] > b['serial_batches']


def test_one_worker_never_divides_by_zero():
    assert R.estimate_fit_cost(n_rungs=10, n_frames=10, workers=0)['serial_batches'] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_fit_cost_estimate.py -v`
Expected: FAIL — attribute missing

- [ ] **Step 3: Implement**

```python
# One 144-frame WebP encode measured at roughly 1.5s on 6 performance cores
# (207.84s for ~118 rungs at 6 workers, 2026-08-22). The threshold is set where a
# fit starts to threaten a typical 120s tool timeout, not at a round number.
_FIT_WARN_FRAME_ENCODES = 6000


def estimate_fit_cost(n_rungs, n_frames, workers):
    workers = max(1, int(workers or 1))
    frame_encodes = int(n_rungs) * int(n_frames)
    return {
        'encodes': int(n_rungs),
        'frame_encodes': frame_encodes,
        'serial_batches': -(-int(n_rungs) // workers),
        'warn': frame_encodes >= _FIT_WARN_FRAME_ENCODES,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts/harness && python3 -m pytest test_fit_cost_estimate.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Emit it before the search starts**

At `scripts/remove_gif_background.py:7950`, in the "Over the target -- fitting" branch, before calling `fit_to_target_bytes`:

```python
                _est = estimate_fit_cost(len(rungs), len(alpha_frames), _workers)
                if _est['warn']:
                    print(f"  NOTE: this fit may evaluate up to {_est['encodes']} rungs "
                          f"x {len(alpha_frames)} frames = {_est['frame_encodes']:,} "
                          f"frame-encodes in ~{_est['serial_batches']} serial batches. "
                          f"On a 144-frame asset this measured 207s on 6 cores, and "
                          f"could not complete at all on a 1-core sandbox. If you are "
                          f"running under a tool timeout, render one file and one "
                          f"format per call, or pass the flags directly instead of "
                          f"searching. A background job is NOT a reliable workaround.")
```

- [ ] **Step 6: Add the SKILL.md rule this estimate exists to support**

`SKILL.md`'s "One invocation per JOB, not per FILE" section currently pushes toward batching everything. Add the exception directly beneath it, as one soft-wrapped line each:

```markdown
⚠️ **`--target-kb` is the one exception to "one invocation per JOB".** A fit is up to 120 rungs and each rung re-encodes every frame, so cost scales with frame count times rungs, not with file count. Measured 2026-08-22: one 144-frame 640x640 asset took **207.84s** for two formats, and the same call covering two files and two formats was killed at a 120s tool timeout having delivered nothing. Above roughly 100 frames, render **one file and one format per call** -- and if the constraints are already known, pass the flags directly instead of running the search at all. The tool prints an estimate before starting. ⚠️ **Do NOT reach for a background job as the workaround.** Measured in the claude.ai sandbox 2026-08-22: `nohup ... &` returned a PID, and the next tool call found an empty log and no process -- each tool call is torn down with its own process group, so a job cannot span two calls there. That sandbox also has **one logical CPU**, so the rung search runs serially and an AVIF fit cannot finish inside a single call at all.
```

- [ ] **Step 7: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_fit_cost_estimate.py SKILL.md
git commit -m "feat(target-kb): estimate fit cost before committing to the rung search"
```

---

### Task 4: `--verify` must not report a vacuous pass

**Files:**
- Modify: `scripts/remove_gif_background.py` — the `--verify` entry point, where the dimension-mismatch skip lives
- Test: `scripts/harness/test_verify_vacuity.py`

**Interfaces:**
- Produces: a `checks_skipped` list and a `verified: false` field in `--verify`'s JSON whenever the pixel checks did not run.

**Why.** `--verify` skips every pixel check when output dimensions differ from the source. Every `--crop`ped deliverable therefore verifies vacuously. In the trial all four initial `--verify` runs did nothing, in 0.9–2.0s, and returned output that reads like a pass; the real checks (13.9s and 39.0s) only ran after re-rendering uncropped. A check that cannot run must say so rather than return a shape that looks like success — this is the project's own standing rule from `references/lessons.md` §13/§16/§17, applied to the verifier itself.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_verify_vacuity.py
import json
import subprocess
import sys


def test_a_cropped_output_reports_that_it_was_not_verified(tmp_path):
    """A --crop'ped deliverable is the NORMAL case, and it verified vacuously."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 'c.webp'
    subprocess.run([sys.executable, SCRIPT, src, str(out), '--crop',
                    '--protect-outline-color', '002864'],
                   capture_output=True, timeout=600, check=True)
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--verify'],
                       capture_output=True, text=True, timeout=600)
    doc = json.loads(r.stdout[r.stdout.index('{'):])
    assert doc['verified'] is False
    assert doc['checks_skipped'], 'skipped checks were not named'
    assert 'dimension' in ' '.join(doc['checks_skipped']).lower()


def test_a_same_size_output_still_reports_verified_true(tmp_path):
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 'u.webp'
    subprocess.run([sys.executable, SCRIPT, src, str(out),
                    '--protect-outline-color', '002864'],
                   capture_output=True, timeout=600, check=True)
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--verify'],
                       capture_output=True, text=True, timeout=600)
    doc = json.loads(r.stdout[r.stdout.index('{'):])
    assert doc['verified'] is True
    assert not doc['checks_skipped']
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_verify_vacuity.py -v`
Expected: FAIL — `KeyError: 'verified'`

- [ ] **Step 3: Implement**

At the dimension-mismatch skip, collect rather than silently pass:

```python
    checks_skipped = []
    if (out_h, out_w) != (src_h, src_w):
        checks_skipped.append(
            f'pixel checks skipped: output {out_w}x{out_h} differs from source '
            f'{src_w}x{src_h} (--crop or --resize-max-dim). Re-render without '
            f'them to verify the artwork, then apply them to the verified flags.')
    report['checks_skipped'] = checks_skipped
    report['verified'] = not checks_skipped
```

And print a stderr line when skipped, so a session that reads only the console sees it:

```python
    if checks_skipped:
        print('WARNING: --verify did NOT check any pixels. ' + checks_skipped[0],
              file=sys.stderr)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd scripts/harness && python3 -m pytest test_verify_vacuity.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_verify_vacuity.py
git commit -m "fix(verify): report a skipped check as unverified rather than as a pass"
```

---

### Task 6: `--webp-quality` must not be silently discarded

**Files:**
- Modify: `scripts/remove_gif_background.py:7906` (the encoder call), `:5605-5612` (the lossless branch)
- Test: `scripts/harness/test_webp_quality_is_not_a_noop.py`

**Interfaces:**
- Consumes: `args.webp_lossy`, `args.webp_quality`.
- Produces: no signature change. A stderr warning, and a non-default `--webp-quality` no longer silently vanishes.

**Why.** Measured in the claude.ai session of 2026-08-22: the same render at `--webp-quality 70` and `--webp-quality 45` produced **byte-identical 403.1 KB output**. At `:7906` the encoder is called with `lossless=not args.webp_lossy`, and the lossless branch at `:5610` overrides the caller with `quality=100`. So on the default path the flag is parsed and thrown away. A user tuning it sees nothing change and gets no warning — and a session then wastes render cycles concluding the tool is broken. This trial missed it because its own override passed `--webp-lossy` alongside, which is exactly the combination that hides the bug.

**Design decision.** Do NOT make `--webp-quality` imply `--webp-lossy`. Lossless is the measured-correct default for flat vector art (the comment at `:5596` records this) and silently switching a user to lossy because they nudged a quality number would trade a silent no-op for a silent behaviour change, which is worse. Warn instead, and name the flag that makes it take effect.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_webp_quality_is_not_a_noop.py
import subprocess
import sys


def test_a_non_default_webp_quality_without_lossy_warns(tmp_path):
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 'q.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out),
                        '--protect-outline-color', '002864', '--webp-quality', '45'],
                       capture_output=True, text=True, timeout=600)
    msg = (r.stdout + r.stderr).lower()
    assert 'webp-quality' in msg and 'lossless' in msg, \
        'the flag was discarded without saying so'
    assert '--webp-lossy' in (r.stdout + r.stderr), \
        'the warning did not name the flag that makes it take effect'


def test_the_default_quality_does_not_warn(tmp_path):
    """A user who never touched the flag must not be nagged."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 'd.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out),
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=600)
    assert 'webp-quality' not in (r.stdout + r.stderr).lower()


def test_with_lossy_the_quality_actually_changes_the_bytes(tmp_path):
    """The falsifier that would have caught this: two qualities, two sizes.

    Without this half the warning could be added while the flag stays broken.
    """
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    sizes = []
    for q in ('30', '90'):
        out = tmp_path / f'l{q}.webp'
        subprocess.run([sys.executable, SCRIPT, src, str(out),
                        '--protect-outline-color', '002864',
                        '--webp-lossy', '--webp-quality', q],
                       capture_output=True, timeout=600, check=True)
        sizes.append(out.stat().st_size)
    assert sizes[0] != sizes[1], 'quality had no effect even with --webp-lossy'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_webp_quality_is_not_a_noop.py -v`
Expected: the first test FAILS (no warning is emitted); the third PASSES already, which is what proves the warning is the only thing missing.

- [ ] **Step 3: Implement the warning**

At `scripts/remove_gif_background.py:7906`, immediately before the encoder call:

```python
            if not args.webp_lossy and args.webp_quality != WEBP_QUALITY_DEFAULT:
                print(f"WARNING: --webp-quality {args.webp_quality} has NO EFFECT "
                      f"without --webp-lossy -- the default WebP path is lossless "
                      f"and encodes at quality 100 regardless. Add --webp-lossy to "
                      f"make it take effect, or drop the flag. Measured 2026-08-22: "
                      f"q70 and q45 produced byte-identical output.",
                      file=sys.stderr)
```

- [ ] **Step 4: Bind the default as a named constant**

The warning must compare against the argparse default rather than a literal, or changing the default silently disarms the check. At `:9009` the default is `90`; hoist it:

```python
WEBP_QUALITY_DEFAULT = 90
```

and use it in `add_argument('--webp-quality', type=int, default=WEBP_QUALITY_DEFAULT, ...)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scripts/harness && python3 -m pytest test_webp_quality_is_not_a_noop.py -v`
Expected: PASS, 3 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_webp_quality_is_not_a_noop.py
git commit -m "fix(webp): warn when --webp-quality cannot take effect instead of discarding it"
```

---

### Task 7: reprint the final dimensions after a `--target-kb` fit

**Files:**
- Modify: `scripts/remove_gif_background.py:7922` (the `Output:` line), and the fit's `Final:` line inside `fit_to_target_bytes`
- Test: `scripts/harness/test_final_dimensions_are_reprinted.py`

**Interfaces:** no signature change. One additional printed line after a fit lands.

**Why — this is the cheapest fix on the list and it prevents the worst observed failure.** `:7922` prints `Output: {w}x{h}, {kb} KB` **before** the fit begins at `:7944`. When the fit lands it prints only `Final: 242.3 KB (saved over ...)`. The file on disk is now a different size in pixels, and **the last dimensions the tool printed are stale.**

Measured consequence: the claude.ai session of 2026-08-22 reported `482×513` as the delivered dimensions of a file that was 120×128. Its own audit attributes the number to a confused diagnostic render — but the tool had printed exactly `Output: 482x513` in that same run. A session reporting faithfully what the tool said would still have been wrong. Fixing the operator discipline does not fix this; fixing the output does.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_final_dimensions_are_reprinted.py
import re
import subprocess
import sys


def test_a_fit_that_changes_dimensions_reprints_them(tmp_path):
    """The megaphone case: Output: says 482x513, the delivered file is 120x128."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    out = tmp_path / 'm.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--crop',
                        '--target-kb', '256',
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=1800)
    log = r.stdout + r.stderr
    from PIL import Image
    with Image.open(out) as im:
        real = f'{im.size[0]}x{im.size[1]}'
    finals = re.findall(r'Final:.*?(\d+x\d+)', log)
    assert finals, 'the Final: line never reported dimensions'
    assert finals[-1] == real, \
        f'last reported {finals[-1]} but the delivered file is {real}'


def test_a_run_with_no_fit_is_unchanged(tmp_path):
    """No --target-kb means no second line -- do not add noise to the common path."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 's.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out),
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=600)
    assert (r.stdout + r.stderr).count('Final:') == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_final_dimensions_are_reprinted.py -v`
Expected: the first test FAILS — `assert finals, 'the Final: line never reported dimensions'`. The second passes already.

- [ ] **Step 3: Implement**

In `fit_to_target_bytes`, at the `Final:` line (`scripts/remove_gif_background.py:6097-6100` area), include the delivered dimensions read back from the written file rather than computed:

```python
    with Image.open(output_path) as _im:
        _fw, _fh = _im.size
    say(f"Final: {size/1024:.1f} KB, {_fw}x{_fh} (saved over {output_path})")
```

Read them from the FILE, not from the winning rung's intended scale. A rung records what it asked for; the encoder records what it wrote, and the two can differ by a rounding pixel. The claim being made is about the delivered artifact.

- [ ] **Step 4: Add the stale-line guard to the pre-fit print**

At `:7922`, when a fit is going to run, mark the line as provisional so a reader cannot mistake it for the delivered size:

```python
    _will_fit = bool(getattr(args, 'target_kb', None))
    print(f"Output: {out_w}x{out_h}, {size_bytes/1024:.1f} KB"
          + (" (BEFORE --target-kb fitting -- see the Final: line for what was "
             "actually delivered)" if _will_fit else ""), file=sys.stderr)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd scripts/harness && python3 -m pytest test_final_dimensions_are_reprinted.py -v`
Expected: PASS, 2 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_final_dimensions_are_reprinted.py
git commit -m "fix(target-kb): report the delivered dimensions instead of the pre-fit ones"
```

---

### Task 8: debloat SKILL.md and make its navigation recipe portable

**Files:**
- Modify: `SKILL.md:1-52` (header, navigation recipe, version block)
- Modify: `references/version-history.md` (receives the moved v6.0.0 notes)
- Modify: `references/lessons.md:18` (same navigation fix, smaller instance)
- Test: `scripts/harness/test_skill_navigation_is_portable.py`, plus `audit_docs.py`

**Interfaces:** no code change. This task is entirely about what the packaged file costs a live session to read and whether its first instruction works.

**Why — two separate defects in the first 52 lines, both measured 2026-08-22.**

**8a. The first executable instruction in the file fails silently off this machine.** `SKILL.md:10` gives exactly one navigation recipe:

```
rg -n '^#{2,3} ' SKILL.md          # the outline, with line numbers
```

`rg` is not present in the claude.ai sandbox. Harkirat's session substituted `grep` — its own record, §4, documents running `grep -n '^#{2,3} ' SKILL.md`. That command **returns zero matches and exits 0**, because `#{2,3}` is ERE and plain `grep` is BRE, where it is a literal string. Verified here:

```
$ grep -c  '^#{2,3} ' SKILL.md   ->  0     (exit 0)
$ grep -cE '^#{2,3} ' SKILL.md   ->  20
```

So a session that cannot run `rg` does not get an error. It gets an empty outline of a file the header has just told it never to `cat`, with no signal that anything went wrong. **This is a silent failure at the entry point of the entire skill** — the worst possible place for one, and it is invisible from this repo because `rg` is installed here.

**8b. 28.9% of the file is release notes before the first actionable line.** Measured: `SKILL.md` is 13,351 words; lines 1-52 — everything before `## When to use this` — are **3,863 of them**, and almost all of that is the v6.0.0 changelog plus one-line summaries of v5.5.0 down to v5.0.0. The actionable body is 9,488 words.

A claude.ai session loads this file to find out what to *do*. Release notes are provenance for a maintainer. `references/version-history.md` already exists for precisely this purpose and already holds v5.3.0 and earlier — the current release simply never gets moved down when the next one lands.

⚠️ **This is also the file's own rule being broken.** `CLAUDE.md` states SKILL.md keeps "only the current version's entry plus the versioning convention itself." v6.0.0's entry is 21 bullets, several of them multi-hundred-word measurement writeups belonging in `references/lessons.md`, which is where their `§N` pointers already lead.

**Boundary — what must NOT be cut.** The refusal/⛔ blocks in the body (alpha-only source, changing background, and the rest) read like reference material and are not: they are the conditions under which the tool destroys an asset, and a live session needs them inline. Cut provenance, never a hazard. And do not compress a measured number down to an adjective — "measured on 336 assets, 3 promote" is what makes a rule trustworthy; "rarely promotes" is not.

- [ ] **Step 1: Write the failing test**

```python
# scripts/harness/test_skill_navigation_is_portable.py
import re
import subprocess

SKILL = 'SKILL.md'


def _recipe_commands(text):
    """Every shell command inside the first fenced block of SKILL.md."""
    block = re.search(r'```\n(.*?)```', text, re.S)
    assert block, 'SKILL.md has no navigation code block'
    return [ln for ln in block.group(1).splitlines()
            if ln.strip() and not ln.strip().startswith('#')]


def test_the_navigation_recipe_does_not_depend_on_ripgrep():
    """rg is absent from the claude.ai sandbox -- the deployment target."""
    cmds = _recipe_commands(open(SKILL).read())
    assert not any(re.match(r'\s*rg\b', c) for c in cmds), \
        'the navigation recipe leads with rg, which the deployment sandbox lacks'


def test_every_navigation_command_actually_returns_matches():
    """The real 2026-08-22 failure: grep -n '^#{2,3} ' returns 0 and exits 0."""
    for cmd in _recipe_commands(open(SKILL).read()):
        if 'sed' in cmd or '<' in cmd:
            continue
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        assert r.stdout.strip(), f'{cmd!r} produced NO output -- a silent empty result'


def test_the_header_stays_lean():
    """Release notes belong in references/version-history.md, not above the body."""
    lines = open(SKILL).read().split('\n')
    head = '\n'.join(lines[:52])
    body = '\n'.join(lines[52:])
    head_w, body_w = len(head.split()), len(body.split())
    share = head_w / (head_w + body_w)
    assert share < 0.12, (
        f'the pre-body header is {share:.1%} of the file ({head_w} words). '
        f'Measured 28.9% on 2026-08-22; move the release notes to '
        f'references/version-history.md.')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_skill_navigation_is_portable.py -v`
Expected: all three FAIL. The second is the important one — it must fail with a *silent empty result*, reproducing the real defect rather than an exception.

- [ ] **Step 3: Fix the navigation recipe**

Replace `SKILL.md:8-11` with a recipe that uses only POSIX tools and correct BRE, and says why:

```
grep -n '^##* ' SKILL.md            # the outline, with line numbers
sed -n '<start>,<end>p' SKILL.md    # then the section you need, by the range grep gave you
```

`^##* ` is one `#` followed by zero or more — plain BRE, no `-E`, matches every heading level, and works identically under `grep`, `ggrep` and `rg`. Add one line beneath it: **do not substitute a different regex flavour here; `grep -n '^#{2,3} '` returns zero matches and exit 0 on a POSIX grep, which reads as "this file has no headings."**

- [ ] **Step 4: Apply the same fix to `references/lessons.md:18`**

That line already offers `grep` first and `rg` as an alternative, which is the right shape — but check its pattern is BRE-safe under plain `grep` and fix it if not. Run the actual command before declaring it fine.

- [ ] **Step 5: Move the v6.0.0 release notes into `references/version-history.md`**

Cut the 21-bullet v6.0.0 block and the v5.5.0/v5.4.0/v5.0.0 summaries out of `SKILL.md`. In `references/version-history.md`, add the v6.0.0 entry at the top, above v5.5.0, preserving every bullet verbatim — this is a MOVE, not a rewrite, and no measured number may be reworded in transit.

Leave behind in `SKILL.md`, in place of the whole block:

```markdown
**Skill version: v6.0.0.** The versioning convention is three-part `v{major}.{minor}.{correction}` — a major bump changes what the tool can do or refuses to do, a minor adds a capability or a discriminator, a correction fixes a defect without changing the interface. **Per-version release notes for v6.0.0 and every earlier release are in `references/version-history.md`** — read them only when you need to know when a behaviour changed, never to find out what to do now.
```

- [ ] **Step 6: Re-check what the body lost**

Several v6.0.0 bullets are the *only* statement of a live behaviour rather than a historical note — the `--target-kb` rung structure and the `--recommend` three-tier enclosure wording are both read as current guidance by a working session, and the claude.ai session of 2026-08-22 pulled both from the changelog. For each moved bullet, ask: **would a session doing the job today need this?** If yes, the fact belongs in the relevant body section as a present-tense rule, not only in version-history. Do not let the move quietly delete guidance.

⚠️ This is exactly the v5.3.0 failure that `audit_docs.py` gate 0 exists for — six flags including `--auto` lived only in a changelog. **A changelog reads like documentation and is not.** Moving the changelog out makes that gate more load-bearing, not less.

- [ ] **Step 7: Run the gates**

Run: `python3 scripts/audit_docs.py`
Expected: exit 0. Every argparse flag reachable from the instructional body must still be documented there — if the move stripped a flag's only mention, this fails, which is the intended safety net.

Run: `cd scripts/harness && python3 -m pytest test_skill_navigation_is_portable.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 8: Verify against the deployment target's constraints, not this machine's**

Confirm by reading, not by running (there is no claude.ai shell here): every command in the navigation recipe uses only `grep`, `sed`, `cat`, `head`, `sed -n`. No `rg`, no `fd`, no `-E`-dependent pattern, no GNU-only flag. State plainly in the commit message that this was verified by inspection and not executed in the target sandbox.

- [ ] **Step 9: Commit**

```bash
git add SKILL.md references/version-history.md references/lessons.md \
        scripts/harness/test_skill_navigation_is_portable.py
git commit -m "docs(skill): make the navigation recipe portable and move release notes out of SKILL.md"
```

---

### Task 9: the 8-bit-alpha erosion default leaves a visible fringe

**Files:**
- Modify: `scripts/remove_gif_background.py:7190-7195` (the format erosion default)
- Test: `scripts/harness/test_alpha_edge_fringe.py`

**Why — this is the only defect a human noticed unprompted, and it is on every WebP/AVIF the manual path has ever produced.** At `:7193` erosion defaults to **0** for `webp`/`avif`/`apng`, printing "8-bit alpha needs no fringe trim." Harkirat, reviewing the delivered files: *"the output of both the claude.ai session and the agent had a ~1 px anti-aliasing edge around the entire artwork which should have been eroded away/removed. Right now the outline does not look 'clean' on any of the outputs."*

`--verify`'s `edge_fringe_check` returned `looks_fringed: false` at 0.0000 on secure and `null` on megaphone. **The check that exists to catch this reports clean.**

Measured on a controlled pair — same asset, same flags, erosion 0 vs erosion 1:

| megaphone render | outer opaque ring vs interior | partial-alpha halo |
|---|---|---|
| erosion 0 (the manual default) | **16.9% closer to white** | **624 px** |
| erosion 1 (`--auto` calibrated) | 26.8% darker than interior | **0 px** |

`--auto` already reaches the right answer by calibrating against the asset's own fringe curve. The manual path never runs that calibration and takes 0.

⛔ **Do NOT simply flip the default to 1 and ship it.** This repo has 448 renders' worth of evidence about what erosion costs, and erosion is a destructive operation on thin art — `references/lessons.md` §37 and the erosion-exemption work exist precisely because it eats detail. The candidate fixes, in order of preference:

1. **Run the existing auto-calibration unconditionally** for 8-bit-alpha formats, rather than only under `--auto`. Correct per-asset, and reuses code already proven on 336 assets.
2. Flip the default 0 → 1. Blunt, cheap, and wrong for any asset whose edge genuinely needs none.

- [ ] **Step 1: Reproduce the defect as a failing test**

```python
# scripts/harness/test_alpha_edge_fringe.py
import numpy as np
from PIL import Image, ImageSequence
from scipy import ndimage


def _halo_px(path, frame=0):
    """Partial-alpha pixels around the opaque body -- the fringe, counted."""
    f = list(ImageSequence.Iterator(Image.open(path)))[frame].convert('RGBA')
    al = np.asarray(f)[..., 3] / 255.0
    return int(((al > 0.02) & (al < 0.98)).sum())


def test_a_default_webp_render_does_not_leave_a_fringe(tmp_path):
    """Erosion 0 left 624 partial-alpha px on megaphone; erosion 1 left 0."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    out = tmp_path / 'd.webp'
    subprocess.run([sys.executable, SCRIPT, src, str(out),
                    '--protect-outline-color', '002864'],
                   capture_output=True, timeout=900, check=True)
    assert _halo_px(out) == 0, (
        f'{_halo_px(out)} partial-alpha fringe pixels survived the default render')


def test_erosion_is_still_capped_and_thin_art_survives(tmp_path):
    """The falsifier that must NOT pass vacuously: the fix must not raise erosion
    above 1, which 448 renders showed never recovers artwork."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 's.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out),
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=900)
    log = r.stdout + r.stderr
    import re
    lvl = re.findall(r'erosion.*?(\d)', log)
    assert all(int(x) <= 2 for x in lvl if x.isdigit()), f'erosion escalated: {lvl}'
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd scripts/harness && python3 -m pytest test_alpha_edge_fringe.py -v`
Expected: the first test FAILS reporting a non-zero fringe count. If it passes on PRE code, the fixture is wrong — find an asset that reproduces what Harkirat saw before going further.

- [ ] **Step 3: Make the calibration unconditional for 8-bit-alpha formats**

At `:7190`, replace the flat `0` default with a call to the same calibration `--auto` uses, leaving an explicit `--edge-cleanup-erosion` to win as it does today. Print which level was chosen and why, exactly as `--auto` does (`erosion calibrated against this asset's own curve (...) -> 1`).

- [ ] **Step 4: Run to verify it passes**

Expected: both tests pass.

- [ ] **Step 5: PRE/POST render diff — this is the gate, not the tests**

Run: `python3 scripts/harness/render_baseline.py --set standard --out /tmp/post-erosion.json` then `--compare` against the current baseline.

⚠️ **Unlike every other task here, a non-zero diff is EXPECTED and is the point.** Read it as the erosion work did: count assets that got better, assets that got worse, and confirm `art_kept_worst` never falls. **If any asset loses artwork, this fix is not ready** — a cleaner edge bought by eating a thin stroke is the trade this repo has already refused twice.

- [ ] **Step 6: Show Harkirat the renders before merging**

He found this defect by looking. The fix is not confirmed until he looks again at the same assets. Do not merge on a green test suite alone.

- [ ] **Step 7: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_alpha_edge_fringe.py
git commit -m "fix(erosion): calibrate edge cleanup on 8-bit-alpha output instead of defaulting to none"
```

---

### Task 10: `--auto` asks instead of guessing on a coin-flip region

**Files:**
- Modify: `scripts/remove_gif_background.py` — the `--auto` flag-application path
- Test: `scripts/harness/test_auto_coinflip_refusal.py`

**Why.** Measured 2026-08-22: `--auto` on megaphone prints `applying: --protect-outline-color f0c850,002864` and protects the sparkle interiors the user explicitly asked to have removed, then reports success. Every region on that asset was flagged by the tool's own evidence as a "COIN FLIP, not verified" (2/144, 102/144, 0/144 frames enclosed). Harkirat's answer: **ask the user.**

⚠️ **This is in tension with the project's stated end goal and the tension must not be smoothed over.** `CLAUDE.md` wants the skill "completely automatically run-able"; an unattended run has nobody to ask. The resolution is to make the question **answerable in advance** rather than to drop it:

- `--auto` refuses when a candidate region's `enclosure_ratio_all_frames` is in the coin-flip band, naming the region, its bbox, its outline colour, and both options in one sentence a user can answer.
- Two new flags pre-answer it for an unattended caller: `--assume-protect <colours>` and `--assume-remove <colours>`.
- A run that is neither interactive nor pre-answered **stops**. It does not guess.

- [ ] **Step 1: Write the failing test**

```python
def test_auto_refuses_on_a_coinflip_region_and_names_both_options(tmp_path):
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    r = subprocess.run([sys.executable, SCRIPT, src, str(tmp_path / 'a.webp'), '--auto'],
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode != 0, '--auto proceeded on a coin-flip region'
    assert 'f0c850' in out, 'the refusal did not name the region in question'
    assert '--assume-remove' in out and '--assume-protect' in out, \
        'the refusal did not tell an unattended caller how to answer it'


def test_a_pre_answered_run_proceeds_and_removes_the_sparkles(tmp_path):
    src = 'local/2026-08-21-v6-timeout-trial/inputs/megaphone.gif'
    out = tmp_path / 'b.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--auto',
                        '--assume-remove', 'f0c850'],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0 and out.exists()
    assert 'f0c850' not in re.search(r'applying:.*', r.stdout + r.stderr).group(0)


def test_an_unambiguous_asset_is_NOT_made_to_ask(tmp_path):
    """secure.gif encloses 50/50 on both regions -- 1.000, not a coin flip.
    Without this, the fix would be a refusal that fires on everything."""
    src = 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif'
    out = tmp_path / 'c.webp'
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--auto'],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0 and out.exists(), '--auto refused an unambiguous asset'
```

The third test is the one that keeps this honest: `secure.gif` sits at enclosure 1.000 on both regions, so a correct implementation must sail through it. A refusal that fires on every asset would pass the first two tests and be useless.

- [ ] **Step 2: Run to verify it fails**

Expected: the first two FAIL, the third PASSES already.

- [ ] **Step 3: Implement the band check, the refusal text and the two flags**

Reuse the existing three-tier enclosure wording (`references/lessons.md` §38) — the band is already computed and already printed as evidence. This task turns an evidence string nobody reads into a decision.

- [ ] **Step 4: Run to verify it passes** — expected 3 passed.

- [ ] **Step 5: Re-score the labelled populations**

Run: `python3 scripts/harness/run_populations.py --out /tmp/post-auto.json`

⚠️ **This adds a refusal path, so measure how often it fires across all 797 assets before merging.** If it refuses a large fraction, the band is too wide and `--auto` has been made useless in the name of correctness — report the rate, do not merge blind.

- [ ] **Step 6: Commit**

```bash
git add scripts/remove_gif_background.py scripts/harness/test_auto_coinflip_refusal.py
git commit -m "feat(auto): refuse a coin-flip protection decision instead of guessing at it"
```

---

### Task 5: documentation, lessons section, and the release gates

**Files:**
- Modify: `SKILL.md` (flag docs for `--min-dimension`, version entry), `references/lessons.md` (new section + ToC + symptom row + `Also searched as:`)

- [ ] **Step 0: Add the `--webp-quality` / `--webp-lossy` dependency to `references/flag-reference.md`**

One soft-wrapped line: `--webp-quality` applies only with `--webp-lossy`; the default WebP path is lossless and encodes at quality 100 regardless.

- [ ] **Step 1: Add `--min-dimension` to SKILL.md's instructional body**

Not only the changelog. `audit_docs.py` fails any argparse flag reachable from SKILL.md's body that is undocumented there — and the v5.3.0 precedent is that six flags, including `--auto`, lived only in a version changelog and were invisible to every autonomous run. Add it beside `--resize-max-dim` in the flag list and in the compression section.

- [ ] **Step 2: Write `references/lessons.md` §43**

Content: the empty-compliant-zone finding, the falsified q60 hypothesis and why the falsification mattered, and the AVIF-vs-WebP 7.7× measurement. Do NOT state an absolute token size for the file anywhere — `audit_docs.py` fails on that.

- [ ] **Step 3: Add the ToC entry, the symptom-table row, and the `**Also searched as:**` line**

Symptom row wording should key on what a reader would actually search: "output came out smaller than I asked for", "target-kb ignored my minimum size", "webp much bigger than avif".

- [ ] **Step 4: Run the doc gate**

Run: `python3 scripts/audit_docs.py`
Expected: exit 0.

- [ ] **Step 5: Run the full falsifier suite**

Run: `cd scripts/harness && python3 -m pytest -q`
Expected: all pass, including the pre-existing 130.

- [ ] **Step 6: Run the render diff**

Run: `python3 scripts/harness/render_baseline.py --set standard --out /tmp/post.json` then `--compare` against the current baseline.
Expected: **0 changed.** None of these four tasks may alter a delivered file for an asset that already satisfied its constraints. Any change is a regression and must be explained before merge, not after.

- [ ] **Step 7: Commit**

```bash
git add SKILL.md references/lessons.md
git commit -m "docs: record the min-dimension gap, the falsified q60 hypothesis and the avif/webp gap"
```

---

## Self-Review

**Spec coverage.** Trial findings 1 (min dimension) → Task 1. Finding 2 (no ranking) → Task 2. Finding 3 (runtime, no pre-flight estimate) → Task 3 plus the SKILL.md exception. Finding 5 (vacuous verify) → Task 4. Finding 7 (`--webp-quality` no-op) → Task 6. Finding 8 (stale dimensions after a fit) → Task 7. The 8-bit-alpha fringe → Task 9. `--auto` guessing on a coin-flip region → Task 10. Frame-stride weighting is deliberately NOT a task — it questions weights set on measurement, and needs its own, filed as spec §14 question 6. **Task 8 covers a defect class the trial did not file as a numbered finding because it is about the packaged prose rather than the code: SKILL.md's navigation recipe fails silently without `rg`, and 28.9% of the file is release notes. Findings 4 and 6 are deliberately NOT in this plan** — finding 4 (`--recommend` cannot infer intent) needs a design decision about whether the tool should ask, refuse, or annotate, and belongs in its own brainstorming pass; finding 6 (the "downscaling made this LARGER" diagnostic not feeding back into the search) is low severity and would touch the rung ordering this plan is forbidden to move. Both should be filed in `gif-deferred-list.md` rather than silently dropped.

**Placeholder scan.** No TBDs. Every code step carries the actual code. The one judgement call left to the implementer is the exact insertion point of the batch-summary hook, because that writer's local variable names were not read during planning — Task 2 Step 5 names what it needs (`summary_records` carrying source, output, width, height, frames, kb) so the implementer can bind it correctly.

**Type consistency.** `scales_for_fit(args, width, height) -> tuple[float, ...]` is used identically in Task 1 Steps 3 and 4. `rank_sibling_outputs(records) -> list[dict]` returns copies carrying `dominated_by` and `reason`, matching Task 2 Steps 3 and 5. `estimate_fit_cost(n_rungs, n_frames, workers) -> dict` returns `encodes`, `frame_encodes`, `serial_batches`, `warn`, all four of which are read in Task 3 Steps 4 and 5. `args.min_dimension` is the single spelling everywhere; the CLI flag is `--min-dimension`.

**Coverage risk, found in the audit pass and fixed.** The first draft of Task 1 filtered rungs inside `fit_to_target_bytes` and stopped there — reaching one consumer of at least three, with `--resize-max-dim` and the compress tiers untouched. That is this repo's own "count the consumers" failure, committed while auditing for exactly that class. Steps 6b/6c add a second enforcement point after every resolution-changing step, which also covers paths not yet written. **If a reviewer can name a fourth path that changes output dimensions, this plan is still incomplete** — say so rather than assuming three is all of them.

**One risk worth naming.** Task 1 changes which rungs exist whenever `--min-dimension` is passed, and only then — every existing call site passes `None` and gets the untouched ladder. That is why Task 5 Step 6 demands **0 changed** on the render diff rather than "explain the diffs": a non-zero diff here means the default path moved, which nothing in this plan intends.

---

## Execution Handoff

Plan saved to `docs/plans/2026-08-22-target-kb-constraints-and-format-ranking.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in one session with checkpoints for review.

**Recommended model + effort for execution: Opus 5, medium.** The diagnosis is done and the tasks are specified down to the code, so this is scoped implementation rather than investigation — but Task 2 encodes a design judgement about what the tool should refuse to hand a user without comment, and Task 1 touches a search whose ordering was set on measured evidence. Sonnet would very likely land Tasks 3 and 4 unaided; Tasks 1 and 2 are where a wrong premise is expensive.

Session title: `Opus5-Med · target-kb min-dimension + format ranking · Aug 22`
