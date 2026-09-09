# Spec — what three claude.ai session reports found, and what to build from it

*2026-09-09 12:55 EDT, against **v6.4.1**. One document: findings, evidence, retractions, build order and spec. Written for a session with none of this context.*

## Read this before anything below it

**This document is thinly verified and says so per item.** The tool was run twice while writing it. Four findings were reproduced by executing it or measuring real assets; five are code reads that were never executed; four are hypotheses with a test attached and nothing more. **No corpus re-score, no render diff and no falsifier suite was run for anything proposed here.** Release gate 8, the three-tier agent trial, is unrun three shipped versions deep — and several items here are exactly what it exists to catch.

Three of this audit's own measurements were invalidated, and three of its claims retracted (§6). Treat every number as its label says, not as the surrounding prose sounds.

This version incorporates a three-agent review of the previous draft: an execution test, a critical read, and a code-level check of its central claim. **That check falsified the claim** — see 4.5.

```yaml
skill_version_audited: v6.4.1
sources: 3 claude.ai session bundles - wordmark+grid fade / nebula grid removal / banner edge fade
tool_invocations_across_all_three_sessions: 1 before their write-ups
confirmed_by_running: 4        # D1 D2 D3 D4
observed_visually: 1           # D5 - qualitative, not a measurement
confirmed_by_reading_only: 5   # G1-G5, never executed
open_hypotheses: 4             # O1-O4, each with a named test
retracted: 4                   # R1-R4 - read section 6 first
pixel_neutral: phase 1 only. Phases 2-5 all move pixels. See 4.9.
test_fixture: scripts/harness/fixtures/gradient_alpha_source_1280x512.png
```

## Start here — paste this into a fresh session

```
Read docs/specs/2026-09-09-session-report-findings.md in /Applications/Claude Code/Gif-Background-Remover,
starting with its calibration note and section 6 (retracted claims) so you do not re-derive
something already killed.

Work D1 and D2 FIRST. Both are reproduced on v6.4.1, both have a committed fixture that
fails today, and D1 is the only confirmed destructive defect in the document. They are
downstream of nothing.

  D1  scripts/harness/fixtures/gradient_alpha_source_1280x512.png --recommend
      returns gif-ok on a source that is 73.6% partial alpha. Section 3 has the root
      cause and the already-computed value the verdict block fails to read.
  D2  one line at :2200, wrong transparency spelling. Section 3 gives the replacement.

Then section 8's phase table in order. Phase 0's two measurements gate only the FEATHER-BAND
tuning items, not D1/D2 — and 0a needs a population decision the document could not make
for you; read O1 before starting it.

Do not start phase 4 in the same session as anything else.
The release gates that apply are the three-tier agent trial and the labelled-population
re-score (CLAUDE.md's numbered release-gate list, items 8 and 10).
```

Model and effort: §9.4. Everything below is the evidence behind that prompt.

| you want to… | go to |
|---|---|
| fix something today | **§3 D1, D2** then §4 |
| know what a change can and cannot move | **§4.9** |
| run a measurement that settles an open question | §3 O1-O4 |
| **avoid re-deriving something killed** | **§6, §7** |
| order and cost | §8 |

---

## 1. Problem Statement

I hand the tool an image and it answers confidently. On a class of source it cannot reason about, the answer is wrong and nothing in the output says so.

The sharpest case: I gave it a PNG that is 70% partial alpha — a banner faded to transparency at its edges. It told me GIF was fine and handed me a command ending in `<output.gif>`. Running that command destroyed the fade: 2,202,940 partial-alpha pixels went to zero. Every check the tool has reported success, because the flattening moves pixels *within* the opaque set rather than deleting any. The last line it printed was `durations preserved exactly`.

In the same JSON it told me the source had no pre-existing transparency, on a file with 315,504 fully transparent pixels — while another field in that object said "normal for an already-background-removed source."

**The renders were correct both times.** This is an advice-and-reporting problem, and it is worse than a crash because a crash stops me. An autonomous run reads `suggested_command`, executes it, and reports success on a destroyed deliverable.

A second problem shows only at the sizes I now use the tool at. It keys on **one** background colour sampled from **four corner pixels**. Across 101 of my own images, three have four corners that agree. On my app icon the background varies by **79.7** RGB units across the canvas against a default tolerance of 15 — keying it with one colour would need a tolerance that puts **12.14% of the artwork** inside the key. No flag expresses the alternative.

A third explains why the first two went unnoticed: **three multi-hour sessions of real image work on my own assets produced one tool invocation between them.** Not carelessness — session 3 checked all 63 flags and correctly concluded none applied. The work people bring to this art — matte removal, overlay subtraction, edge fading — sits adjacent to what the tool does, and its surface does not reach it.

## 2. Solution

**The tool becomes honest about what it read.** The format verdict consults the source's alpha plane. `source_has_pre_existing_transparency` is derived from the mask that already handles every spelling. A flat erosion curve says "this knob does nothing here". Counts gain distributions; conservation figures gain completion figures. One absolute assertion exists, because every current gate is a comparison and a uniform error cancels in all of them.

**The tool learns that a background is a field, not a colour.** `detect_bg_color` returns one RGB and everything downstream inherits it. Make it a function of position and every existing check works unchanged. The flagship, and a real feature.

**The tool gains the capability whose absence pushed a fifteen-turn job outside it.** `--edge-fade`, a spatial alpha map keyed to the canvas frame, with a reference implementation and acceptance test already supplied.

---

## 3. Findings ledger

**Two conventions, because a cold reader has been observed tripping on both.**

*Line anchors.* Every `:NNNN` in this document points into `scripts/remove_gif_background.py` **as it stood at v6.4.1, commit `e19ac1a`'s parent tree**. They are navigation aids, not identifiers — the file is ~10k lines and any edit above a citation moves it. Locate by the function name given alongside; treat the number as a hint. None was independently re-verified while writing this.

*The word "band".* Throughout this document it means **the alpha transition band** — the pixels between `--tolerance` and `--tolerance × --feather-band-multiplier`, where alpha ramps from 0 to 1. Its **start** is the tolerance end, its **endpoint** the multiplier end, and its **inner**/**outer** edges are toward the opaque core and toward the background respectively. R1's retraction turns on that inner/outer distinction, so it has to be one object.

*The word "session".* A **source session** is one of the three claude.ai sessions this document audits. A **working session** is the future one that executes it.

**`RUN`** reproduced by executing the tool or measuring real assets. **`LOOKED`** observed in a render, qualitative, not a measurement. **`READ`** established from source, never executed. **`OPEN`** reasoned, with a test not yet run. **Do not promote a class without doing the work.**

### D1 · RUN · the format verdict is blind to the source's alpha plane

Reproduced on v6.4.1: `recommended_format: gif-ok`, a `<output.gif>` command, `source_has_pre_existing_transparency: False`.

**Two assets, two sets of numbers — do not confuse them.** The original defect was found on session 3's full deliverable (3072×512, **70.0% partial / 10.0% transparent**). The committed fixture is a crop of it (1280×512, **73.6% partial / 11.7% transparent / 14.7% opaque**). Both reproduce; the fixture is what the tests use.

```bash
python3 scripts/remove_gif_background.py \
  scripts/harness/fixtures/gradient_alpha_source_1280x512.png --recommend
# v6.4.1 prints: gif-ok / False
```

On the full asset, following the suggested command took partial-alpha pixels to **0** while `a > 0` retention read **100.0%**.

**Root cause.** The verdict comes from `detect_fading_colors` (`:5629`) over `build_art_palette` (`:5531`) — machinery asking whether a colour *in the art palette* unmixes as a fade toward the background. Right for a GIF whose fade was flattened at authoring time; blind to a source already carrying an alpha channel, because the palette scan never reads the alpha plane.

**The fix is smaller than the source report knew.** `_partial_alpha_seen` already exists at `:1794`/`:1807` and is surfaced as `measured_on_alpha_composite` at `:2090`. The verdict block at `:2924-2974` never consults it.

⚠️ **A second gap, found by the code check and not by the original report.** `recommended_format` does **not** choose the container — `resolve_output_format(output_path, args)` (`:9941`, `:9994`) does, from the caller's filename. `--auto` reads `recommended_format` only to print a `FORMAT CONFLICT` warning to stderr, then proceeds. **So fixing the verdict fixes the *suggestion* and does not stop `--auto` from flattening a fade when the caller named a `.gif`.** Closing D1 properly means the refusal has to reach the run, not just the advice.

### D2 · RUN · one line, the wrong transparency spelling

`:2200` reads `'transparency' in im.info` — the palette-index spelling. An RGBA source carries no such key, so this reports `false` on a file with 315,504 alpha-0 pixels. `get_source_transparency_mask` (`:943`) already handles RGBA correctly and **its own comment dates that fix to 2026-08-18 and names this failure class as one the project keeps hitting.** The function was fixed; the report field was not.

```python
_m = get_source_transparency_mask(im)
'source_has_pre_existing_transparency': _m is not None and bool(_m.any()),
```

### D3 · RUN · the background is sampled from four corner pixels

`detect_bg_color` (`:247`) majority-votes four corners; disagreement prints a stderr warning `--auto` does not act on. Over 101 corpus images: **3** have four agreeing corners; **38** give an answer further than `--tolerance` from the modal RGB of an 8 px border ring, up to **38.7**. Not yet shown to break a delivered asset — an exposure with a thin margin.

### D4 · RUN · a single colour cannot express a background field

Background spread across the canvas, and the tolerance that would be needed to key it:

| asset | spread | tolerance needed | share of artwork that would fall inside the key |
|---|---|---|---|
| app icon | **79.7** | ~80 | **12.14%** |
| vignette banner | **62.0** | ~63 | 3.04% |
| wordmark *(flat control)* | 19.2 | ~20 | 0.01% |

**Nothing was rendered** — this is what the key *would* swallow, not measured damage. Session 3 independently measured the same icon with a different background mask: luminance **43.8 → 13.5**, brightest ring to corners.

### D5 · LOOKED · the fade fork's arms, on a checkerboard

Session 1's three wordmark outputs composited over a checkerboard. `out_fade` keeps the glow as an opaque navy haze; `out_nofade` ramps it away and leaves the vortex core as a hole; `out_v2` keeps the core and carries more halo than either. **Qualitative, not measured.**

**The arms were *too much* and *too little*, not "both wrong".** The glow genuinely is dark navy, so a faithful recovery *should* read as grey haze on white — which validates the refusal. No flag expresses the answer that was right: **recover it partially.** The fork is missing its middle.

### G1 · READ · no colour-space handling, and its unproven consequence

Zero hits for `gamma`, `srgb`, `2.2` or a linear-light round trip. Every alpha estimate, unmix and composite runs on gamma-encoded sRGB — **exactly correct for sRGB-authored art**, wrong for linear-authored art. The consequence is O1 and is unproven; the absence itself is certain.

### G2 · READ · the calibration curve's shape is half-read

`calibrate_edge_cleanup_erosion` (`:7716`) builds a four-level table then reduces it to `min()` plus a pick. `earned_erosion_ceiling` **does** read convexity (the knee at 2, `references/lessons.md` §37.10) — the principle is established and implemented for one shape. The flat case is not tested. Session 1 measured the tell on the wordmark: `0.6349 → 0.5862`.

**The statistic is `v0 − min(v)`** — the gain from doing anything at all — **not** the variance across all four, because an asset fixed entirely by level 1 is flat across 1–3 and must not be read as having no fringe.

### G3 · READ · the recommender can only move the band's endpoint

It appends `--feather-band-multiplier` (`:2852`) and never a `--tolerance` value. Session 1's accepted command moved the **start** (15→8). Session 3 measured that the start is the perceptual variable: 0.34–0.475 reads as "fading", 0.66 as "a crop", identical endpoint.

⚠️ **This one moves pixels. See 4.9.**

### G4 · READ · every check is differential

No assertion anywhere that the output contains `alpha == 255` pixels. Session 3 shipped a global 5% opacity ceiling that neither author nor user noticed. *Honest negative: `unmix_family_blend`'s softmax (`:5600`) **is** correctly normalised — flagged speculatively by session 3, and clean.*

### G5 · READ · no spatial alpha map

63 flags, none keyed to canvas geometry. `--translucent-region` is region-scoped, colour-keyed and uniform; `--edge-softening` is a 1 px silhouette ramp; `--recover-fade-alpha` reconstructs from colour.

```python
r       = (abs(nx)**p + abs(ny)**p) ** (1/p)   # nx, ny normalised to +-1 over the canvas
falloff = clip(1 - smoothstep(start, 1.0, r), 0, 1)
alpha   = minimum(alpha, falloff)
```

`r == 1` at every edge midpoint for any `p`; the corner sits at `2**(1/p)`, so **p is a pure corner knob**. Defaults from real use: `start=0.45, p=4.0`. **Apply as a minimum, never an assignment** — `references/lessons.md` §31, the rule that a source's own alpha may be reduced but never invented.

Session 3's acceptance figures, from its own bit-exact parameter audit: on `assets/DEVOID_Banner_V2_Warp.png`, `--edge-fade 0.45,4.0` should reproduce `DEVOID_Banner_Alpha_Fade_v9.1.png` — edge midpoints 0, first zero at ≈0.828 along the diagonal, ≈19.9% at α=255, ≈10.0% at α=0.

### O1 · OPEN · the colour-space consequence

**Synthetic construction only.** Against a linear-authored composite over `#141124`: recovered-colour error **136.1** at α=0.15 on saturated mid-tones; the alpha estimate came out biased positive at every sampled point, up to **+0.25** — linear-authored edges rendering *more opaque* than they should. Signature is a **bow** off the background→colour line, 5–7 units against **0.00**, below the existing `FADE_RESIDUAL_TOLERANCE = 10.0`.

**The test, and the two things the previous draft got wrong about it.**

*The population.* The previous draft said "the labelled GIF corpus in `local/`". **No such population exists** — `populations.py` registers six labelled corpora (sprites, emoji, small-sizes) and four unlabelled ones, and the only GIF-named one carries `labels=None`. Labels encode pixel-art vs antialiased, which is not the property this test needs. **What it needs is assets with a flat background behind antialiased art.** Select on that, from whichever population supplies it, and state the selection in the result.

*The pass/fail rule.* "Cluster near 0" is not a rule, and R2 records this exact measurement failing twice at median 25.26 against a 5–7 unit signature. **The rule must separate "swamped by background variation" from "no signal":** report the bow's median AND the local background's own variation over the same pixels. A background varying by more than the signature means the measurement is void for that asset, not negative. Only assets whose background varies by less than ~2 units can vote.

### O2 · OPEN · does the `0.25` clamp matter?

`estimate_alpha_and_defringe` (`~:3963`) uses `a_safe = np.clip(alpha, 0.25, 1.0)` before dividing. **Measured: binds on 28.2% of real band pixels** (13.3% below α=0.10), at the **outer**, faintest end of the transition band.

**Test:** render a real asset twice, floor at 0.25 and at 0.05, and compare chroma (`R−G`) on the outer band against the adjacent interior. Under-dividing pulls a pixel toward the background, i.e. desaturated. Nil delta closes it.

### O3 · OPEN · small features through the fit ladder

`_FIT_SCALE_LADDER` descends to 0.25 with `_SCALE_COST`/`_STRIDE_COST` as hand-assigned preferences, not damage measurements. Nothing measures whether a 2 px highlight survived; `--pixel-art` selects NEAREST, which drops rather than rings.
**Test:** count connected components of local maxima above a contrast threshold before and after the fit, on real stickers at a 256 KB cap.

### O4 · OPEN · pooled jitter broadens the hardness measure

Hardness is pooled across frames; on a tumbling sprite the same edge sits at a different sub-pixel offset each frame. **Prediction:** a rotating hard-edged sprite measures *softer* than the same sprite still, and misclassifies as antialiased.
**Test:** score a hard-edged corpus sprite, then a synthetically rotated copy, and compare `edge_hardness`. **This one re-scores a hardness measure, so the labelled-population gate applies.**

---

## 4. Implementation Decisions

### 4.1 The format verdict reads the alpha plane
Compute a partial-alpha **fraction** over the frames the loader already returns; disqualify GIF above a threshold, structurally identical to the existing `has_fully_transparent_frame` steer toward WebP/APNG. The same fraction gates the evidence string so verdict and stated reason cannot diverge.

**A fraction, not a count** — a raw count trips on residue from an earlier imperfect cut. **Suggested starting threshold: 2% of non-transparent pixels carrying partial alpha**, chosen to sit far below the fixture's 73.6% and far above stray-pixel residue; calibrate against opaque controls and move it if they trip. **Print the number whether or not it binds** — a threshold nobody can see the input to cannot be audited.

**And make the refusal reach the run.** Per D1's second gap, the verdict alone does not stop `--auto` flattening a fade into a caller-named `.gif`. Either escalate the `FORMAT CONFLICT` stderr line into a refusal, or make it a question `--auto` will not answer for the caller.

### 4.2 The transparency field is derived from the mask
Consume `get_source_transparency_mask`; add `source_transparent_fraction`, which the render path already computes. **The `im.info` audit ships with this change, not after it** — the code comment asserts the class is recurrent, so one pass closes the class rather than one instance.

### 4.3 The erosion calibrator gains a reading, not a decision
`v0 − min(v)`, not variance. **Suggested floor: 0.02**, the same `tolerance_above_floor` the pick already uses, so the flatness statement fires exactly when no level clears the tie-break. Below it, the run states erosion bought nothing measurable. **The selected level does not change.**

### 4.4 One absolute assertion
A source with fully opaque artwork must produce an output containing fully opaque pixels. Every other gate is differential, so a uniform transformation of the whole alpha plane cancels in all of them.

### 4.5 The recommender gains the band's start — and this one is not free
Symmetric ability to append a `--tolerance` value, with the band reported as two endpoints rather than a multiplier.

⚠️ **This changes rendered output, and the mechanism is already live.** `auto_run()` (`:9840`) calls `recommend()` (`:9876`), then splits `suggested_command`'s flags into `rec_tokens` (`:9967`), parses them (`:9971`) and **applies any flag the caller left at its default** (`:~9976-9992`). That is how `--feather-band-multiplier` recommendations already reach real conversions. Adding `--tolerance` to the same append path makes it the real tolerance, and `tolerance` gates the colour-key, mask and feather maths pervasively.

**So this ships in phase 3 with its own acceptance test, not in phase 1.** And note that `render_baseline.py --compare` reporting `0 changed` would **not** prove it safe — it only proves the standard set contains no asset whose recommended tolerance differs from the default. The check must be constructed, not inherited.

### 4.6 Counting checks gain a distribution and a largest-instance
Every count reports the largest connected component's area and bbox; every conservation figure reports a completion figure beside it. *"0.02% of pixels leftover"* and *"one 40×3 sliver at the left edge"* are the same number and different defects.

### 4.7 The background estimate gains a second opinion
Four-corner sample retained as primary; the modal colour of a border ring computed alongside; their distance reported **in the analysis object**, not only on stderr.

### 4.8 Background as a field — after O1 and O2 report
`bg` becomes a function of position, estimated along whichever axis it is invariant along: radial for a vignette, linear for a gradient. The discipline session 2 arrived at for its own v6 build is the build spec here, because each of its failures maps to a way this ships broken:

| lesson | what it forces |
|---|---|
| anchor the reference where the feature cannot reach | estimate only from pixels far from artwork |
| refuse to invent a value where there is no data | a region with no background samples reports **undetermined**, never extrapolates |
| a real measurement does not license a correction | prove non-flatness first; flat assets must come out byte-identical |
| null control | on a flat asset the estimator returns ~constant, or it is manufacturing a field |
| gated repair | apply per region only where it measurably improves |

### 4.9 What each change can move — verified against the code

| change | moves pixels? | why |
|---|---|---|
| 4.2 transparency field | **No** | report-only; the field has one other occurrence in the file, its own assignment |
| 4.3 erosion flatness log | **No** | additive log line; `_pick` and the knee-raise block are untouched |
| 4.4 absolute assertion | **No** | reads a written output, like every check of its shape |
| 4.6 counts and distributions | **No** | analysis-object fields populated after the removal work |
| 4.1 format verdict | **No** for `--auto`'s own run | the container comes from `resolve_output_format` (`:9941`, `:9994`), never from `recommended_format`. *Its escalation-to-refusal half, however, is a behaviour change by design* |
| **4.5 tolerance in the recommendation** | **YES** | `auto_run`'s flag auto-apply loop, `:9967-9992` |
| **GIF alpha dithering** | **YES, by design** | `ordered_dither_mask` (`:3898`) sits inside the alpha-encoding function that returns the written bytes |
| **4.8 background field** | **YES, by design** | it corrects the key |

**Phase 1 is pixel-neutral. Nothing after it is.** The previous draft's header claimed otherwise for the whole spec; that claim was false and a code-level check caught it.

---

## 5. Testing Decisions

**A good test asserts what a caller receives** — a JSON field, a stderr line, or the bytes of a written file — never an internal function's return. **D1 is the reason:** the internal measurement is already correct and the defect lives in a consumer that ignores it. An import-level test would pass while the CLI still emitted `gif-ok`.

**One seam, and it already exists:** `subprocess.run([sys.executable, "scripts/remove_gif_background.py", ...])`, the pattern used by ~20 files under `scripts/harness/` with `pytest.ini` beside them. No new seam. Chosen over an import seam deliberately — the "confirm behaviour, not signatures" release gate exists for exactly this, and D1 is a case where the signature is right and the behaviour is wrong.

**Prior art**, closest first: `test_auto_coinflip_refusal.py` (the refusal path D1 sits beside), `test_analyze_recommend_redundancy_note.py` (asserting on `--analyze` text), `test_verify_vacuity.py` (proving a check can fail), `test_alpha_edge_fringe.py` (rendering through the CLI and measuring the written alpha plane).

**The fixture is committed, real, and proven.** `scripts/harness/fixtures/gradient_alpha_source_1280x512.png` — a 649 KB crop of session 3's accepted deliverable, **11.7% transparent / 73.6% partial / 14.7% opaque**. Committed rather than left in `local/` for the reason the labelled ground truth left `local/` in August: gitignored evidence is unversioned and one clean away from gone. A crop of real content rather than a constructed gradient, because a fixture you draw is chosen to flatter. **Verified to reproduce both D1 and D2 on v6.4.1 before this spec was written around it** — that is the whole of what "proven" means here.

**Every test must fail on the current code**, and the falsifier is stated per behaviour: the verdict test fails today because the fixture returns `gif-ok`; the field test because it returns `False`; the flatness test because no such line is emitted.

**Every test needs its negative.** The verdict change is paired with opaque controls from the labelled populations — a verdict that moves there means the threshold reads antialiasing the tool computed itself rather than alpha the source shipped with. The transparency field is paired with a palette-transparency GIF and a fully opaque source.

**Corpus confirmation.** `render_baseline.py --set standard --compare` reporting **0 changed** is the proof for phase 1 and **is not sufficient for 4.5** (§4.9). O4 re-scores a hardness measure, so the labelled-population gate applies there.

---

## 6. Retracted claims — do not re-derive

*Paired with §7, which records approaches measured and lost. Both exist to stop a session spending a day on something already settled.*

| id | claim | why it died |
|---|---|---|
| **R1** | The `0.25` clamp under-corrects at the transition band's **inner** edge, so the tool's own arithmetic puts a defect where no instrument looks | Measured backwards. Low-alpha pixels sit **11.81 px** from the opaque core against **9.37 px** for all band pixels — the **outer** end. Alpha is low where distance-to-background is low. The clamp still binds; it has no inner-edge consequence |
| **R2** | The gamma bow is confirmed on real content | Two failed attempts. Pooling all band pixels against the bg→white line: median 21.33. Isolating the five white letter components correctly: median 25.26, p90 111.73 — the letters sit over a **nebula**, so the background varies by tens of levels and swamps a 5–7 unit signature |
| **R3** | "Two of three sessions independently derived X" is strong evidence | Session 3 **read** reports 1 and 2 first and could re-measure none of their numbers. Only session 2's pre-report derivations are independent: component-geometry separation, the amplified view, orientation splitting, integer-offset profiles |
| **R4** | The dark rim inside `out_v2`'s punched counter is tool-added | The comparison averaged the source over all ring pixels and the output over only `alpha > 0` ones. The source is already grey (~170) there — the letter carries an inner bevel. Most of the rim is artwork; whether any tool-added component exists is **unresolved** |

**R1, R2 and R4 failed the same way** — comparing two populations that were not the same pixels, the trap both source reports document. **Before comparing two populations, print `n` for each and confirm they are the same pixels.** Where they legitimately differ — an unmixed colour *should* differ from its source — state the expected difference before reading the number.

## 7. Evaluated and rejected

**Nothing about improving the skill is out of scope.** This records approaches measured *against* the skill that lost, so nobody rebuilds one. Each fails: **can I name the asset it fixes and the measurement that shows it?**

| approach | why it lost |
|---|---|
| Fill-vs-subtract for fringe repair (session 1's own headline) | needs an axis the artifact is invariant along. A grid line is constant along its length; a keyed fringe changes colour continuously around the outline, so a robust median along it has nothing to average. Sample count is not the objection — it fails at 4000 px too |
| Lattice tracking, sub-pixel binning, junction patches | need a periodic structure |
| Grain synthesis, normalized-convolution fill, texture copy | fill-repair for continuous tone; the skill's artifact is a keyed colour, and where it is a composite the exact algebraic inverse already exists |
| Frequency-domain separation | session 2 falsified it: 1.136 with the grid present against 1.132 without, inside a grid-free null of 1.116–1.165 |
| Ensembling as an improvement method | every combination landed inside the inputs' own spread |
| `super:cx,cy,rx,ry,p` region grammar | marked speculative; justifying it needs a `circularity_ratio` distribution over regions where `circle_region_safe` is false, and nobody has that distribution |
| Polarity as a colour-direction concern | the metric is a vector norm and the unmix is signed, so there is no directional assumption to break. *The residue — that every fringe instrument reads outward — survives as an observation* |

**One reversal.** Ensembling is dead as a method and live as a **diagnostic**: variants averaging to no better than any of them share a common-mode error. `--auto`'s two-signal erosion calibration is a candidate, because both signals read the **outer ring** and may be blind in the same direction. **Two signals blind the same way are one signal.** Filed into phase 5.

**The only genuine exclusions**, neither about the skill: the three sessions' own pipelines as *products* (removing a coordinate grid from a nebula is a seven-hour specialist job), and publishing this to an issue tracker (none configured).

## 8. Build order and cost

| phase | items | why here | moves pixels | size |
|---|---|---|---|---|
| **1. Confirmed defects + instrumentation** | **D1** (verdict half), **D2**, G2, G4, 4.6 | reproduced, fixture fails today, downstream of nothing | **No** | S-M |
| **2. Settle the upstream questions** | O1, O2 | both cheap, **both can return "no"** and close a branch; they gate feather-band tuning, nothing in phase 1 | No | S each |
| **3. Behaviour changes** | D1's refusal half, **4.5**, GIF alpha dithering | each needs its own constructed acceptance test | **Yes** | M |
| **4. Structural** | the background field, D3 | real feature with a refusal path and a corpus re-score | **Yes** | **L** |
| **5. Measured experiments** | per-site erosion gating, O3, O4, the two-signal common-mode check | each needs a corpus run before belief | varies | M each |

**Do not bundle phase 4 with anything.** GIF alpha dithering ships in phase 3 **with** D1's refusal and never alone — the honest result is a visible mesh, and without the refusal that only moves the failure from invisible to ugly.

**Cost.** `--recommend` took **87.5 s** on session 3's 3072×1024 frame (3.1 MP); two calls do not fit in a 120 s tool call. The GIF corpus averages 0.36 MP, so a 2048×2048 icon at 4.2 MP is ~12× it — the tool is most expensive exactly where the product is expanding. The committed fixture is 0.65 MP, about a fifth of the frame the 87.5 s was measured on.

## 9. Further Notes

### 9.1 The design target
Design against the near-certain next request: **"rebuild the banner from the no-grid nebula, with the wordmark and the edge fade."** It walks into every finding at once — a re-cut wordmark (D5's missing middle), a non-flat background (D4), an edge fade (G5), a 70%-partial-alpha output (D1), then an upscale. **If the tool can do that job without a human writing numpy, the findings were the right ones.**

### 9.2 The vocabulary gap
Every user rejection across the three sessions names a measurable property, and `--verify` speaks none of them. Checked against the code: **four for four absent.**

| what was said | the statistic | exists? |
|---|---|---|
| "colors seem more **smudged**" | chroma noise of the change *(session 2 measured 0.612 → 0.010 in its own pipeline)* | **no** |
| "**eating into** the artwork" | ramp start vs endpoint | computed, never reported separately |
| "hints of lines when I **zoom in**" | worst localised residual | **no** |
| "it **erased pixels**" | over-correction distribution (p1, p5) | **no** |

Session 2 recorded the user being right on all 8 occasions a metric disagreed with them. A plausible mechanical reading, from one session and not independently confirmed: the user's vocabulary carries distinctions the tool's cannot express.

### 9.3 Five aggregation axes, not one slogan
"Report the worst frame, not the mean" is five distinct failures, which is why this "one" lesson keeps being re-fixed: the centre hiding the tail; a membership count blind to transformation within the set; an aggregate over the wrong axis (channels); a spatial mean hiding a localised defect; a temporal mean hiding consecutive bad frames. **For every statistic reported, name which axis it aggregates over and what it therefore cannot see.** *(Channel axis is clean — no `.std()`/`.var()`/`np.ptp()` anywhere.)*

### 9.4 Model and effort
**Opus 5, high.** From the priority-tier grid in the Diors-Builds memory folder (`reference_priority_tier_system.md`, "Model + reasoning effort") — effort buys breadth, model buys premise risk — not from the effort tier. Premise risk binds: this audit retracted four of its own claims, a three-agent review falsified its central acceptance condition, and two open hypotheses can invalidate work done downstream of them. Deliberation load is moderate — the tasks are individually small. **If phase 2 closes both branches and the work becomes mechanical instrumentation, step DOWN to Sonnet-high and say why.**

Session title: `Opus5-high · Session-report findings phase 1 · 2026-09-09`

### 9.5 Evidence index

| what | where |
|---|---|
| D1's source asset, session 3's 24 outputs, scripts, verification | `local/claude ai session reports/session 3 report (banner edge fade)/` |
| Session 1's wordmark + `out_fade`/`out_nofade`/`out_v2` — a fixture with a human-accepted answer | `local/claude ai session reports/session 1 report (reduced grid)/` |
| Session 2's source, v6 final, 6 named failure files, annotated screenshot | `local/claude ai session reports/session 2 report (removed grid)/` |
| The 101-image `detect_bg_color` table | `docs/investigations/2026-09-09-devoid-corpus-bg-detection.md` |
| Production corpus | `/Applications/Claude Code/Devoid/DEVOID Logo Assets/` |

⚠️ **The bundles and the production corpus are gitignored or outside the repo.** A fresh clone has this document, the fixture and the investigation table, and none of the rest. Check for them before planning around them.

**Hash-confirmed lineage:** `DEVOID Workmark_Transparent.png` = session 1's delivered output; `DEVOID Nebula_NoGrid.png` = session 2's `00_FINAL_v6.png`. *(Several finals then went through Upscayl at 1×, which is why `out_v2.png` is not byte-identical to the delivered file.)*

### 9.6 What was not done
- **~70 scripts across the three bundles remain unread**, including ones their READMEs mark "broken by design and kept".
- **The tool was run twice.** Every other behavioural claim is a code read.
- **No corpus re-score, no render diff, no falsifier suite** was run for anything proposed here.
- **Release gate 8 is unrun**, three shipped versions deep. Several items here are exactly what it catches: advice confidently wrong while the render is correct is invisible to a corpus score, a code review and a render diff alike, because all three compare the product against itself or a label.
- **The publish step of the `to-spec` skill this document's structure came from** was not run — it wants an issue tracker with a `ready-for-agent` label, and none is configured for this repo.
