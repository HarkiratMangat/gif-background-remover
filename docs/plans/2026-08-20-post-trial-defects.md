# Post-Trial Defect Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the seven defects the 2026-08-19 three-agent package trial found, starting with the output scorer that would otherwise certify a fade fix as working.

**Architecture:** Six of the seven are independent changes to `scripts/remove_gif_background.py`. The seventh is the measurement harness, and it comes FIRST because every downstream acceptance test depends on a grader that can currently report a broken fade as perfect. Two filed items (erosion default, WebP outline artefacting) contradict each other and are deliberately fused into one task.

**Tech Stack:** Python 3.11, numpy, scipy.ndimage, Pillow 12.3.0, gifsicle. No new dependencies.

**Spec:** `docs/investigations/2026-08-19-three-agent-package-trial.md` — read it before Task 1. Product-side mechanisms are `references/lessons.md` §34.

## Global Constraints

- **`love.gif --auto` must remain `2fd526b6fb3b191c`** after every task. It is the standing byte-level control for "nothing else moved".
- **Run `python3 scripts/audit_docs.py` and read its EXIT CODE** before every commit. Never pipe a gate to `tail`.
- **Report the WORST frame, never a mean**, in any new measurement. A defect on 16 consecutive frames averaged to 99.9% and vanished; that is what this plan exists to stop.
- **Prose is soft-wrapped**: one physical line per paragraph. Check with `node "/Applications/Claude Code/Diors-Builds/scripts/reflow-prose.mjs" --check <files>`.
- **Every claim in a commit message must be a number you measured in that task**, not one carried from this plan.
- Trial assets live at `local/Corpus Trial Gifs/`; the three agents' outputs are in its `agent-*` subfolders.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `scripts/harness/score_outputs.py` | **new.** Grades a rendered output against per-frame ground truth from its source. Worst-frame, edge-aware, fade-aware. | 1 |
| `scripts/remove_gif_background.py` | the product. All behaviour changes. | 2–6 |
| `SKILL.md` | the delivery convention and the erosion wording | 4, 7 |
| `references/lessons.md` | §34 gains measured outcomes as each task lands | all |
| `gif-deferred-list.md` | items close as tasks land | all |

---

### Task 1: A scorer that can fail

**Files:**
- Create: `scripts/harness/score_outputs.py`
- Reference: `docs/investigations/2026-08-19-three-agent-package-trial.md`, "Where the scorer failed"

**Interfaces:**
- Produces: `score(src_path, out_path) -> dict` with keys `bg_removed_worst`, `interior_kept_worst`, `art_kept_worst`, `edge_cleanliness`, `fade_correlation`, `worst_frame_index`. Every later task's acceptance step calls this.

⚠️ **This task's acceptance is that the scorer FAILS on files that are already known to be broken.** A grader that cannot reproduce a known defect is not fixed, and this one currently reports the worst asset as 100% correct.

- [ ] **Step 1: Write the failing test — the grader must catch the fade bug it currently certifies**

```python
# scripts/harness/test_score_outputs.py
import score_outputs as S
SRC = 'local/Corpus Trial Gifs/hurricane.gif'
OUT = 'local/Corpus Trial Gifs/agent-3-expert/hurricane_transparent.webp'

def test_fade_bug_is_detected():
    """All three agents produced BYTE-IDENTICAL hurricane output and human review
    called it a disaster. A grader that scores it clean cannot validate a fix."""
    r = S.score(SRC, OUT)
    assert r['fade_correlation'] < 0.90, (
        f"fade_correlation {r['fade_correlation']:.3f} — the source colour ramps "
        f"smoothly and the output alpha holds flat then cliffs; a correlation this "
        f"high means the measure cannot see the defect")

def test_worst_frame_not_mean():
    """growth/agent-3 holds an opaque background wedge on 16 consecutive frames.
    A mean over sampled frames reads 99.9% and hides it."""
    r = S.score('local/Corpus Trial Gifs/growth.gif',
                'local/Corpus Trial Gifs/agent-3-expert/growth_transparent.webp')
    assert r['bg_removed_worst'] < 0.98, (
        f"bg_removed_worst {r['bg_removed_worst']:.4f} — this asset has a known "
        f"16-frame background wedge; a worst-frame measure must show it")
```

- [ ] **Step 2: Run it and watch it fail for the right reason**

Run: `cd scripts/harness && python3 -m pytest test_score_outputs.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'score_outputs'`.

- [ ] **Step 3: Implement the three measures**

```python
# scripts/harness/score_outputs.py
"""Grade a rendered output against per-frame ground truth derived from its SOURCE.

⚠️ Replaces an earlier grader that reported the hardest asset 100% correct on all
three trial agents while human review called it a disaster. Three causes, each
addressed here by name:
  1. binary keep/remove ground truth cannot grade a FADE -> fade_correlation
  2. no measure of outline quality at all                -> edge_cleanliness
  3. a MEAN over sampled frames hid a 16-frame defect    -> every figure is a WORST
"""
import numpy as np
from PIL import Image
from scipy import ndimage
ST = np.ones((3, 3), bool)

def _truth(rgb):
    """outside = white connected to the border; interior = white that is not; art = the rest."""
    white = np.abs(rgb.astype(int) - 255).sum(-1) <= 30
    lab, n = ndimage.label(white, structure=ST)
    bl = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    bl.discard(0)
    outside = white & np.isin(lab, list(bl))
    return outside, white & ~outside, ~white

def _edge_cleanliness(rgba):
    """Of the pixels in the 2px band just inside the silhouette, what share sit at an
    alpha the encoder never asked for -- i.e. neither ~0 nor ~255 nor a deliberate fade?
    A clean cutout has few; a fringe has many. Human reviewers notice this FIRST and the
    old grader could not see it at all."""
    a = rgba[..., 3]
    op = a > 0
    if not op.any():
        return 1.0
    inner = op & ~ndimage.binary_erosion(op, iterations=2)
    if not inner.any():
        return 1.0
    v = a[inner]
    return 1.0 - float(((v > 12) & (v < 243)).mean())

def score(src_path, out_path, samples=24):
    src, out = Image.open(src_path), Image.open(out_path)
    n = min(getattr(src, 'n_frames', 1), getattr(out, 'n_frames', 1))
    idxs = sorted(set(np.linspace(0, n - 1, min(samples, n)).astype(int).tolist()))
    bg, inter, art, edge = [], [], [], []
    src_dist, out_alpha = [], []
    for i in idxs:
        src.seek(i); s_rgb = np.array(src.convert('RGB'))
        out.seek(i); o = np.array(out.convert('RGBA'))
        if o.shape[:2] != s_rgb.shape[:2]:
            return {'shape_mismatch': True}
        outside, interior, arts = _truth(s_rgb)
        al = o[..., 3]
        bg.append(float((al[outside] == 0).mean()) if outside.any() else 1.0)
        inter.append(float((al[interior] > 0).mean()) if interior.any() else 1.0)
        art.append(float((al[arts] > 0).mean()) if arts.any() else 1.0)
        edge.append(_edge_cleanliness(o))
        # fade: how far the interior sits from white in the SOURCE, against the alpha
        # the output gave it. A faithful fade makes these two move together.
        if interior.any():
            src_dist.append(float(np.abs(s_rgb[interior].astype(int) - 255).sum(-1).mean()))
            out_alpha.append(float(al[interior].mean()))
    worst = int(np.argmin(bg)) if bg else 0
    fade = 1.0
    if len(src_dist) > 3 and np.std(src_dist) > 1.0 and np.std(out_alpha) > 1.0:
        fade = float(abs(np.corrcoef(src_dist, out_alpha)[0, 1]))
    return {'bg_removed_worst': min(bg) if bg else 1.0,
            'interior_kept_worst': min(inter) if inter else 1.0,
            'art_kept_worst': min(art) if art else 1.0,
            'edge_cleanliness': min(edge) if edge else 1.0,
            'fade_correlation': fade,
            'worst_frame_index': idxs[worst] if idxs else 0,
            'frames_compared': len(idxs)}
```

- [ ] **Step 4: Run the tests and confirm BOTH now fail the OUTPUT, not the import**

Run: `cd scripts/harness && python3 -m pytest test_score_outputs.py -v` Expected: PASS — meaning the grader now detects both known defects. If either test passes trivially, the measure is not working; print the dict and inspect before continuing.

- [ ] **Step 5: Confirm it does NOT flag a known-good file**

```bash
cd scripts/harness && python3 -c "
import score_outputs as S
r = S.score('../../local/Corpus Trial Gifs/satellite.gif',
            '../../local/Corpus Trial Gifs/agent-3-expert/satellite_transparent.webp')
print(r)
assert r['interior_kept_worst'] > 0.95 and r['edge_cleanliness'] > 0.5, r
print('control PASSES — the grader is not simply failing everything')
"
```

- [ ] **Step 6: Commit**

```bash
git add scripts/harness/score_outputs.py scripts/harness/test_score_outputs.py
git commit -m "test(harness): a scorer that can fail on the defects the old one certified"
```

---

### Task 2: Refuse a GIF that will truncate

**Files:**
- Modify: `scripts/remove_gif_background.py` — `analyze()` (add the field) and the GIF save path
- Test: `scripts/harness/test_score_outputs.py` (extend)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `analyze()['has_fully_transparent_frame'] -> bool`, consumed by `--recommend` and by the save path.

- [ ] **Step 1: Write the failing test**

```python
def test_all_transparent_frame_is_detected_before_render(tmp_path):
    """An all-transparent output frame silently truncates a GIF at that frame
    (Pillow 12.3.0). growth.gif has one and shipped 85 of 123 frames."""
    import subprocess, sys, json
    r = subprocess.run([sys.executable, '../remove_gif_background.py',
                        '../../local/Corpus Trial Gifs/growth.gif', '--analyze'],
                       capture_output=True, text=True)
    a = json.loads(r.stdout)
    assert a.get('has_fully_transparent_frame') is True
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd scripts/harness && python3 -m pytest test_score_outputs.py::test_all_transparent_frame_is_detected_before_render -v` Expected: FAIL — the key does not exist yet.

- [ ] **Step 3: Detect it in `analyze()`, after the alpha planes are built**

```python
    # ⚠️ Pillow's GIF writer emits an unreadable block for a frame in which EVERY pixel
    # is transparent, and the file truncates there: measured 85 of 123 frames on a real
    # asset whose subject leaves the canvas. Reproduced with three synthetic controls, at
    # defaults and under pngquant and --dither-mode none alike. Detected here so
    # --recommend can steer away from GIF BEFORE the render rather than warning after.
    _has_blank_frame = any(not (a > 0).any() for a in source_alpha_planes) \
        if source_alpha_planes else False
```

- [ ] **Step 4: Refuse the GIF at the save path with an actionable message**

```python
    if out_format == 'gif' and _has_blank_frame and not getattr(args, 'allow_truncating_gif', False):
        raise SystemExit(
            "This animation has a frame in which every pixel is transparent (the subject "
            "leaves the canvas entirely). Pillow's GIF writer emits an unreadable block "
            "there and the file TRUNCATES at that frame -- measured 85 of 123 frames on a "
            "real asset. Write .webp or .apng instead, which use a different encoder and "
            "keep every frame. Pass --allow-truncating-gif to write it anyway.")
```

- [ ] **Step 5: Run the test, then confirm the refusal fires and WebP still works**

```bash
cd scripts/harness && python3 -m pytest test_score_outputs.py -v
cd ../.. && python3 scripts/remove_gif_background.py "local/Corpus Trial Gifs/growth.gif" /tmp/t.gif --auto; echo "gif exit=$? (want non-zero)"
python3 scripts/remove_gif_background.py "local/Corpus Trial Gifs/growth.gif" /tmp/t.webp --auto; echo "webp exit=$? (want 0)"
python3 -c "from PIL import Image; print('webp frames', Image.open('/tmp/t.webp').n_frames, '(want 123)')"
```

- [ ] **Step 6: Confirm the control is untouched, then commit**

```bash
python3 scripts/remove_gif_background.py local/corpus-webp-avif-2026-08-17/love_ORIGINAL.gif /tmp/l.gif --auto >/dev/null 2>&1
shasum -a 256 /tmp/l.gif | cut -c1-16   # must be 2fd526b6fb3b191c
python3 scripts/audit_docs.py; echo "audit=$?"
git add -A && git commit -m "fix(gif): refuse a GIF that a fully transparent frame would truncate"
```

---

### Task 3: An enclosure ratio is not "incidental" over a large region

**Files:**
- Modify: `scripts/remove_gif_background.py` — the region-selection code emitting `looks incidental, leaving as background`

**Interfaces:**
- Consumes: `score()` from Task 1 for acceptance.
- Produces: no new signature; changes which regions `--recommend` protects.

⚠️ **This is the highest-value fix in the plan.** It caused two of three trial sessions to delete 83% of an asset's artwork while reporting success.

- [ ] **Step 1: Write the failing test**

```python
def test_large_enclosed_region_is_not_incidental():
    """growth.gif: --recommend called the rocket's white BODY incidental background
    at enclosure_ratio 0.825, and two of three trial agents deleted it."""
    import subprocess, sys
    r = subprocess.run([sys.executable, '../remove_gif_background.py',
                        '../../local/Corpus Trial Gifs/growth.gif', '--recommend'],
                       capture_output=True, text=True)
    assert 'looks incidental, leaving as background' not in r.stdout, \
        'a large interior region is still being dismissed as incidental'
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd scripts/harness && python3 -m pytest test_score_outputs.py::test_large_enclosed_region_is_not_incidental -v` Expected: FAIL — the string is present today.

- [ ] **Step 3: Measure what the ratio does against region AREA before changing it**

```bash
cd "/Applications/Claude Code/Gif-Background-Remover" && python3 - <<'PY'
import glob, json, subprocess, sys
for p in sorted(glob.glob('local/Corpus Trial Gifs/*.gif')) + \
         sorted(glob.glob('local/Diors-builds Emojis/others/*.gif'))[:12]:
    a = json.loads(subprocess.run([sys.executable,'scripts/remove_gif_background.py',p,'--analyze'],
                                  capture_output=True,text=True).stdout)
    for r in a.get('candidate_regions', []):
        print(f"{p.split('/')[-1][:24]:<26} area={r.get('area')} ratio={r.get('enclosure_ratio')}")
PY
```

⚠️ Record this table in the commit message. **Do not pick a threshold before seeing it** — the point is that ratio alone is the wrong axis, and the fix is to condition on area.

- [ ] **Step 4: Implement — gate the "incidental" verdict on region area**

Replace the unconditional ratio test with one that cannot dismiss a large region. Use the measured table from Step 3 to place the area floor; state the chosen number and its evidence in the comment.

- [ ] **Step 5: Verify against the trial assets with the Task 1 scorer**

```bash
python3 scripts/remove_gif_background.py "local/Corpus Trial Gifs/growth.gif" /tmp/g.webp --auto
cd scripts/harness && python3 -c "
import score_outputs as S
r = S.score('../../local/Corpus Trial Gifs/growth.gif','/tmp/g.webp'); print(r)
assert r['interior_kept_worst'] > 0.95, r"
```

- [ ] **Step 6: Re-score the labelled populations — this changes recommendations corpus-wide**

```bash
python3 scripts/harness/run_populations.py --out local/pixelart-probe/analyze-post-t3.json
python3 scripts/harness/render_baseline.py --set standard --script <(git show HEAD:scripts/remove_gif_background.py) --out /tmp/PRE.json
python3 scripts/harness/render_baseline.py --set standard --out /tmp/POST.json
python3 scripts/harness/render_baseline.py --compare /tmp/PRE.json /tmp/POST.json
```

Acceptance: no asset loses opaque pixels. Any asset that gains protection must be explainable.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "fix(recommend): condition the incidental-region verdict on AREA, not ratio alone"
```

---

### Task 4: Settle the erosion contradiction — both filed items at once

**Files:**
- Modify: `scripts/remove_gif_background.py` — erosion auto-calibration gating
- Modify: `SKILL.md` — the `--auto-erosion` sentence

⚠️ **Two filed items DISAGREE and must be settled together.** One says `--auto` should stop overriding the documented WebP default of 0 (it costs 2,878 art pixels on growth). The other says erosion 0 leaves visible outline artefacting a human noticed on three of five assets. Fixing either alone risks making the other worse.

- [ ] **Step 1: Measure outline cleanliness at 0 / 1 / calibrated, on all five trial assets**

```bash
cd "/Applications/Claude Code/Gif-Background-Remover" && for f in galaxy growth hurricane rocket satellite; do
  for e in 0 1; do
    python3 scripts/remove_gif_background.py "local/Corpus Trial Gifs/$f.gif" "/tmp/${f}_e$e.webp" --auto --edge-cleanup-erosion $e >/dev/null 2>&1
  done
  python3 scripts/remove_gif_background.py "local/Corpus Trial Gifs/$f.gif" "/tmp/${f}_auto.webp" --auto >/dev/null 2>&1
done
cd scripts/harness && python3 -c "
import score_outputs as S
for f in ('galaxy','growth','hurricane','rocket','satellite'):
    for tag in ('e0','e1','auto'):
        r = S.score(f'../../local/Corpus Trial Gifs/{f}.gif', f'/tmp/{f}_{tag}.webp')
        print(f'{f:<10} {tag:<5} edge={r[\"edge_cleanliness\"]:.3f} art={r[\"art_kept_worst\"]:.4f}')
"
```

- [ ] **Step 2: Decide from that table, and write the decision into the code comment**

The two items are settled by one question: does erosion 1 buy enough `edge_cleanliness` to justify what it costs in `art_kept_worst`? If yes, the documented WebP default of 0 is wrong and SKILL.md changes. If no, the calibration must stop overriding it. **Both outcomes are acceptable; an unmeasured compromise is not.**

- [ ] **Step 3: Make SKILL.md and the code agree**

SKILL.md currently says "Add `--auto-erosion` to have `--edge-cleanup-erosion` calibrated"; the code sets `auto_erosion = 'edge_cleanup_erosion' not in _typed`, i.e. on by default. Whichever behaviour Step 2 chose, both must state it.

- [ ] **Step 4: Verify the control and commit**

```bash
python3 scripts/remove_gif_background.py local/corpus-webp-avif-2026-08-17/love_ORIGINAL.gif /tmp/l.gif --auto >/dev/null 2>&1
shasum -a 256 /tmp/l.gif | cut -c1-16   # 2fd526b6fb3b191c
python3 scripts/audit_docs.py; echo "audit=$?"
git add -A && git commit -m "fix(erosion): settle the default against measured outline cleanliness"
```

---

### Task 5: `--recover-fade-alpha` must not silently disable protection

**Files:**
- Modify: `scripts/remove_gif_background.py` — the `recovered_rgb` branch in `process()`

- [ ] **Step 1: Write the failing test**

```python
def test_fade_recovery_does_not_silently_drop_protection(capfd):
    """The recovered_rgb branch skips protected_masks entirely, so --tumble-safe and
    --protect-outline-color are ignored with no warning when combined with it."""
    import subprocess, sys
    r = subprocess.run([sys.executable, '../remove_gif_background.py',
                        '../../local/Corpus Trial Gifs/growth.gif', '/tmp/fr.webp',
                        '--auto', '--recover-fade-alpha', '--tumble-safe'],
                       capture_output=True, text=True)
    assert 'tumble' in r.stderr.lower(), \
        'combining fade recovery with a protection flag produced no message at all'
```

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL — nothing is printed today.

- [ ] **Step 3: Refuse the combination out loud**

```python
    if recovered_rgb is not None and (getattr(args, 'tumble_safe', False)
                                      or args.protect_outline_color or args.protect_region):
        print("⚠️  --recover-fade-alpha takes its own render path and does NOT apply "
              "--tumble-safe / --protect-outline-color / --protect-region. They are being "
              "IGNORED for this run. Pick one: fade recovery, or protection.",
              file=sys.stderr)
```

- [ ] **Step 4: Run the test, verify the control, commit**

```bash
cd scripts/harness && python3 -m pytest test_score_outputs.py -v && cd ../..
python3 scripts/remove_gif_background.py local/corpus-webp-avif-2026-08-17/love_ORIGINAL.gif /tmp/l.gif --auto >/dev/null 2>&1
shasum -a 256 /tmp/l.gif | cut -c1-16
git add -A && git commit -m "fix(fade): say out loud that fade recovery ignores every protection flag"
```

---

### Task 6: The fade cliff — fix it or bound it

**Files:**
- Modify: `scripts/remove_gif_background.py` — `recover_fade_alpha_frames()`

⚠️ **A documented limit is an acceptable outcome and the criterion is set NOW, before any tuning:** if `fade_correlation` on hurricane cannot exceed **0.90** without `art_kept_worst` on the other four trial assets dropping below **0.98**, stop, and write the boundary into `references/lessons.md` §34.2 with the numbers that closed it. Do not tune until a number moves.

- [ ] **Step 1: Establish the baseline with the Task 1 scorer**

```bash
cd scripts/harness && python3 -c "
import score_outputs as S
r = S.score('../../local/Corpus Trial Gifs/hurricane.gif',
            '../../local/Corpus Trial Gifs/agent-3-expert/hurricane_transparent.webp')
print('BASELINE fade_correlation', r['fade_correlation'])"
```

- [ ] **Step 2: Find where alpha saturates**

The measured shape is: source distance 258.7 → alpha 255, then 197.8 → 140.5. Alpha is clamped at full opacity above a distance threshold. Locate that clamp in `recover_fade_alpha_frames()` and print the mapping for hurricane's actual distance range.

- [ ] **Step 3: Make the mapping monotone across the observed range, then re-measure**

- [ ] **Step 4: Check the other four assets did not regress**

```bash
cd scripts/harness && python3 -c "
import score_outputs as S
for f in ('galaxy','growth','rocket','satellite'):
    r = S.score(f'../../local/Corpus Trial Gifs/{f}.gif', f'/tmp/{f}_fade.webp')
    print(f, r['art_kept_worst'], r['interior_kept_worst'])"
```

- [ ] **Step 5: Whichever way it goes, record it in `references/lessons.md` §34.2 with numbers, and commit**

---

### Task 7: The delivery convention and the boilerplate

**Files:**
- Modify: `SKILL.md` — add the GIF-vs-WebP delivery convention
- Modify: `scripts/remove_gif_background.py` — collapse the repeated FORMAT block

- [ ] **Step 1: Write the convention into SKILL.md**

Three trial agents hit "the user said GIF, the tool says WebP" and invented three different, incompatible conventions. State one: ship the format the art needs, name the conflict in the delivery note, and offer the compatible format alongside only where it carries the art honestly.

- [ ] **Step 2: Print the FORMAT reasoning once per invocation, not once per asset**

~150 identical words per asset; one trial agent read it five times in one job and called it the single most wasteful thing it read. Emit it once, then a one-line per-asset verdict.

- [ ] **Step 3: Verify on a five-asset batch, then commit**

```bash
for f in galaxy growth hurricane rocket satellite; do
  python3 scripts/remove_gif_background.py "local/Corpus Trial Gifs/$f.gif" --recommend
done 2>&1 | rg -c 'FORMAT'   # must be far below the pre-change count
python3 scripts/audit_docs.py; echo "audit=$?"
git add -A && git commit -m "docs(skill): one delivery convention for the format fork, and stop repeating the FORMAT block"
```

---

### Task 8: Register the dark corpus and settle the narrow constants

**Files:**
- Modify: `scripts/harness/populations.py` — new population entry
- Modify: `scripts/remove_gif_background.py` — only if Step 4's measurement says a constant must move

**Interfaces:**
- Consumes: `score()` from Task 1.
- Produces: population `dark_bg`, usable by `run_populations.py --only dark_bg`.

**Why this exists.** The fringe bands (0.04 / 0.15), the floor tolerance (0.02) and the post-render margin (0.05) were calibrated on 4–5 flat vector icons **on white**. Before 2026-08-20 the whole corpus held **97** opaque-background assets, of which **76 were white-ish and only 5 dark**, and every one of the 18 non-white ones came from a single population. The ring metric had never seen a dark or coloured background.

**Measured 2026-08-20** on `local/corpus dark/` (119 files, supplied by Harkirat): **all 119 have opaque backgrounds**, 59 dark (<80 luminance), 63 saturated (chroma ≥60), 76 animated. **107 of 119 are genuinely keyable** — ≥30% of the frame is border-connected background colour. That takes dark backgrounds from 5 to ~60, across two independent sources instead of one.

⚠️ **The 12 that are not keyable must be excluded explicitly, not quietly.** They are full-bleed illustrations with no background field at all (0.1–6.9% border-connected: `Malika Favre portrait…`, `Animated Loops - José Pistilli.gif`, `By Rafahu #art #illustration #gif #Batman.gif`, `Art gif.gif`, `Wallpaper and Illustration 《LADY AGNES》(5).jpeg`, `Bits - Giacomo D'Ancona.jpeg`, plus the six marginal ones between 10% and 30%). Scoring them would produce a vacuous pass, which this corpus has already recorded twice.

- [ ] **Step 1: Register the population as `ambiguous`**

```python
    'dark_bg': dict(
        dir=os.path.join(ROOT, 'local/corpus dark'), labels=None, recurse=False,
        default_label='ambiguous',
        what='107 keyable assets on FLAT OPAQUE NON-WHITE backgrounds -- 59 dark (<80 luminance), '
             '63 saturated (chroma >=60), 76 animated. Supplied 2026-08-20 to close the one gap the '
             'rest of the corpus could not test around: before this, 76 of 97 opaque-background '
             'assets were white-ish, only 5 were dark, and all 18 non-white ones came from a single '
             'population.',
        blind_to='EVERYTHING about hardness -- labelled `ambiguous` ON PURPOSE, so it is excluded '
                 'from every recall and specificity figure. Its job is the RING METRIC and the '
                 'narrow fringe constants on a non-white background, not classification. Labelling '
                 '119 assets by blanket would be the exact error SS32 records; labelling them by eye '
                 'would cost hours and buy nothing this population is for.'),
```

- [ ] **Step 2: Exclude the 12 non-keyable files by name, with the reason in the entry**

- [ ] **Step 3: Confirm the population scores and that its figures are excluded**

```bash
python3 scripts/harness/run_populations.py --only dark_bg --out /tmp/dark.json
python3 -c "
import json; d=json.load(open('/tmp/dark.json'))['records']
print(len(d),'scored'); import collections
print(collections.Counter(v['label'] for v in d.values()))
assert all(v['label']=='ambiguous' for v in d.values())
print('OK — excluded from recall/specificity by construction')"
```

- [ ] **Step 4: Measure the ring metric and the fringe constants on a non-white background**

```bash
cd scripts/harness && python3 -c "
import glob, os, subprocess, sys, score_outputs as S
for p in sorted(glob.glob('../../local/corpus dark/*'))[:20]:
    d='/tmp/'+os.path.basename(p).replace(' ','_')+'.webp'
    subprocess.run([sys.executable,'../remove_gif_background.py',p,d,'--auto'],capture_output=True)
    if os.path.exists(d):
        r=S.score(p,d)
        print(f'{os.path.basename(p)[:30]:<32} edge={r["edge_cleanliness"]:.3f} bg={r["bg_removed_worst"]:.3f} art={r["art_kept_worst"]:.3f}')"
```

**Acceptance:** a constant moves **only if the dark population shows it failing**, and the change is then re-checked against the white-background assets so it does not trade one family for another. **"The numbers look fine on dark backgrounds too" is a valid and likely outcome** — record it and close the item.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test(harness): register the dark-background corpus, and settle the narrow constants against it"
```

---

## Self-Review

**Spec coverage.** All seven defects from the investigation map to a task, and Task 8 closes the long-standing narrow-constants item that was blocked on a corpus until 2026-08-20: enclosure/incidental → 3 · transparent-frame GIF → 2 · fade cliff → 6 · erosion contradiction + WebP artefacting → 4 (fused) · fade-recovery flag conflict → 5 · format convention + boilerplate → 7 · the scorer → 1. The `--recommend` "0% enclosed" evidence string is NOT covered — it is cosmetic, it is filed at P3, and adding it here would pad the plan.

**Placeholders.** Tasks 4 and 6 deliberately leave a NUMBER unfixed, because the number is the deliverable of a measurement step within the task and the plan states the decision criterion up front. That is not a placeholder; a plan that pre-picked those thresholds would be inventing evidence.

**Type consistency.** `score()` returns the same six keys everywhere it is called (Tasks 1, 3, 4, 6). `has_fully_transparent_frame` is produced in Task 2 and consumed only there.
