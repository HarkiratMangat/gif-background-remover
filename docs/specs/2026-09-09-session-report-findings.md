# Spec — what three claude.ai session reports found, and what to build from it

*2026-09-09 12:38 EDT, against **v6.4.1**. One document: the findings, their evidence, the retractions, the build order and the spec proper. Written for a session that has none of this context.*

*Supersedes the working notes that were in `local/` — they were gitignored, which is the same mistake this repo already fixed once when the labelled ground truth was moved out of `local/` in August. Data appendix: `docs/investigations/2026-09-09-devoid-corpus-bg-detection.md`. Source bundles stay in `local/claude ai session reports/` because they are 230 MB of third-party assets.*

```yaml
skill_version_audited: v6.4.1
sources: 3 claude.ai session bundles - wordmark+grid fade / nebula grid removal / banner edge fade
tool_invocations_across_all_three_sessions: 1 before their write-ups
confirmed_by_running: 4      # D1-D4
confirmed_by_reading: 5      # G1-G5
open_hypotheses: 4           # O1-O4, each with a named test
retracted: 3                 # R1-R3 - read section 7 before starting
renders_changed_by_this_spec: 0
test_fixture: scripts/harness/fixtures/gradient_alpha_source_1280x512.png  # committed, proven
issue_tracker: none configured; /setup-matt-pocock-skills not run
```

## Start here — paste this into a fresh session

```
Read docs/specs/2026-09-09-session-report-findings.md in /Applications/Claude Code/Gif-Background-Remover.
It is one document: findings, evidence classes, retractions, build order and spec.
The source bundles are in local/claude ai session reports/.

Read section 7 first so you do not re-derive a killed claim.

Then work section 9 phase 0: two measurements that can each come back "no" and close a
branch, both upstream of everything else.
  0a - O1's bow test, on the labelled GIF corpus in local/, NOT the DEVOID assets
       (section 4 O1 explains why those cannot test it). Isolate one art colour per
       measurement by connected component; exclude near-background darks.
  0b - O2's clamp test.

Then phase 1: pixel-neutral instrumentation. None of it changes output bytes, and
render_baseline.py --set standard --compare reporting 0 changed is the proof.

Do not start phase 4 in the same session as anything else.
Release gates 8 and 10 apply.
```

Model + effort, and why: §10.4. Everything below is the evidence behind that prompt.

---

| you want to… | go to |
|---|---|
| understand why this exists | §1 |
| fix something today | §4 (D1-D5), then §5 |
| run the measurement that settles an open question | §4 (O1-O4) |
| **avoid re-deriving something already killed** | **§7 — read first** |
| know the order and the cost | §9 |
| open a session on it | §10.4 |

---

## 1. Problem Statement

I hand the tool an image and it answers confidently. On a class of source it cannot reason about, the answer is wrong and nothing in the output says so.

The sharpest case: I gave it a PNG that is 70% partial alpha — a banner faded to transparency at its edges. It told me GIF was fine and handed me a command ending in `<output.gif>`. Running that command destroyed the entire fade: 2,202,940 partial-alpha pixels went to zero. Every check the tool has reported success, because the flattening moves pixels *within* the opaque set rather than deleting any. The last line it printed was `durations preserved exactly`.

In the same JSON it told me the source had no pre-existing transparency, on a file with 315,504 fully transparent pixels — while another field in that same object said "normal for an already-background-removed source."

**The renders were correct both times.** This is an advice-and-reporting problem, and it is worse than a crash because a crash stops me. An autonomous run reads `suggested_command`, executes it, and reports success on a destroyed deliverable.

There is a second problem underneath, and it only shows at the sizes I now use the tool at. The tool keys on **one** background colour sampled from **four corner pixels**. Across 101 of my own images, three have four corners that agree. On my app icon the background varies by **79.7** RGB units across the canvas against a default tolerance of 15 — keying it with a single colour needs a tolerance that puts **12.14% of the artwork** inside the key. There is no flag that expresses the alternative.

And a third, which is the reason the first two went unnoticed for so long: **three multi-hour sessions of real image work on my own assets produced one tool invocation between them.** Not from carelessness — session 3 checked all 63 flags and correctly concluded none applied. The work people actually bring to this art — matte removal, overlay subtraction, edge fading — sits adjacent to what the tool does, and its surface does not reach it.

## 2. Solution

Three things, in an order where each is cheap to abandon if its measurement comes back negative.

**The tool becomes honest.** The format verdict consults the source's alpha plane before choosing a container. `source_has_pre_existing_transparency` is derived from the mask that already handles every spelling correctly. A flat erosion curve says "this knob does nothing here" instead of picking among noise. The recommender can name the band's *start*, not only its endpoint. One absolute assertion exists, because every current gate is a comparison and a uniform error cancels in all of them. **No rendered pixel moves.**

**The tool learns that a background is a field, not a colour.** `detect_bg_color` returns one RGB and everything downstream inherits it. Make it a function of position and every existing check works unchanged. This is the flagship and it is a real feature, not a patch.

**The tool gains the capability whose absence pushed a fifteen-turn job outside it.** `--edge-fade` — a spatial alpha map keyed to the canvas frame. Session 3 supplies a reference implementation, converged defaults and a bit-exact acceptance test.

## 3. User Stories

1. As someone converting a faded banner, I want the tool to refuse GIF when my source carries real partial alpha, so that following its own suggestion does not destroy the thing I made.
2. As someone reading `--recommend`, I want `suggested_command` to name a container that can hold my source's alpha, so that I can run it without inspecting the result myself.
3. As an autonomous agent executing `suggested_command` unattended, I want that command to be safe on the source it was computed from, so that "success" means the deliverable survived.
4. As someone whose GIF sticker workflow works today, I want an opaque source's verdict completely unchanged, so that a fix for someone else's asset is not a regression for mine.
5. As someone whose source has a few stray partial-alpha pixels from an earlier imperfect cut, I want those not to flip the verdict, so that the rule keys on a fraction rather than a count.
6. As someone reading the evidence strings, I want the "no partial transparency for GIF to lose" claim gated on the same measurement that drives the verdict, so that the prose and the decision cannot disagree.
7. As someone handing the tool an RGBA file, I want `source_has_pre_existing_transparency` to say `true`, so that I do not reason about it as an ordinary opaque source.
8. As someone handing the tool a palette-transparency GIF, I want that field to still say `true`, so that the fix does not trade one spelling for another.
9. As someone handing the tool a fully opaque source, I want it to still say `false`, so that the fix has not hard-coded a `true`.
10. As someone reading one analysis object, I want no two fields in it to contradict each other, so that I can trust any one of them.
11. As a maintainer, I want every other `im.info`-derived report field audited in the same pass, so that a failure class the code's own comment calls recurrent is closed rather than patched at one site.
12. As someone whose asset has no trimmable fringe, I want the run to say erosion bought nothing measurable, so that I stop reaching for a knob that does not apply.
13. As someone whose asset genuinely needs erosion, I want the existing pick unchanged, so that the flatness report is additive.
14. As someone reading the erosion log, I want the gain from doing anything at all stated, not the spread across levels, so that an asset fixed entirely at level 1 is not mislabelled as flat.
15. As someone told my edge reads as a crop rather than a fade, I want the tool able to recommend a lower `--tolerance`, so that I am not hand-editing the one parameter that matters.
16. As someone reading a recommendation, I want the band's start and endpoint reported separately, so that I can see which one moved.
17. As someone whose output was uniformly made 5% transparent by a bug, I want at least one check that can see it, so that an error affecting every pixel equally is not invisible to a suite made entirely of comparisons.
18. As someone reading `leftover_background_opaque_px`, I want the largest connected leftover's area and bbox alongside the count, so that "0.02% of pixels" and "one 40x3 sliver at the left edge" stop being the same number.
19. As someone reading any whole-file statistic, I want it per frame and per region too, so that a defect concentrated in one place is not averaged into invisibility.
20. As someone whose fade was flattened by the container, I want a `source_partial_alpha_retained` figure, so that a run that destroyed the gradient cannot produce a clean-looking verification block.
21. As someone reading "93.6% of pixels unchanged", I want a completion statistic beside it, so that a run that did almost nothing cannot look better than one that did the job.
22. As someone with a vignetted background, I want the four-corner sample's disagreement with the border population reported in the analysis, so that I learn the estimate is weak before acting on it rather than from a stderr line an autonomous run never reads.
23. As someone processing a large static artwork, I want the background estimated from a population rather than four pixels, so that grain or a corner vignette does not decide it.
24. As someone whose background is a vignette or a gradient, I want the tool to key against a local background, so that it stops choosing between eating my artwork and leaving background behind.
25. As someone whose asset has a genuinely flat background, I want the field estimator to prove non-flatness before it corrects anything, so that my working assets come out byte-identical.
26. As someone whose canvas has a region with no background samples at all, I want the estimator to report undetermined rather than extrapolate, so that it does not invent a value and subtract it.
27. As someone who wants a banner to fade into transparency at its edges, I want a flag that does it, so that the job stays inside the tool.
28. As someone applying an edge fade to a source that already has alpha, I want it applied as a minimum and never as an assignment, so that it cannot invent opacity the source did not have.
29. As someone asking for an edge fade on a GIF, I want a printed refusal naming the reason, so that I am not handed a dithered mesh.
30. As a maintainer, I want every change here provable by a test that fails on the current code, so that "fixed" is demonstrated rather than asserted.
31. As a maintainer, I want the test fixture committed rather than referenced in `local/`, so that the evidence cannot be lost to a directory clean.
32. As a maintainer, I want the fixture to be real content rather than something constructed, so that it cannot be shaped to flatter the fix.
33. As a maintainer, I want a render diff proving no output byte moved on the standard set, so that a reporting change is confirmed to be one.
34. As a maintainer reading this later, I want the retracted claims listed, so that I do not spend a session re-deriving something already killed.

## 4. Findings ledger

`RUN` = reproduced by executing the tool or measuring real assets. `READ` = established from source, not executed. `OPEN` = reasoned, with a named test not yet run. **Do not promote a class without doing the work.**

### D1 · RUN · the format verdict is blind to the source's alpha plane

Reproduced on v6.4.1, verbatim: `recommended_format: gif-ok`, a `<output.gif>` command, `source_has_pre_existing_transparency: False` — on a source that is **70.0% partial alpha** and **10.0% fully transparent**. Following it: partial-alpha px out = **0**, `a > 0` retention **100.0%**, stderr `durations preserved exactly`.

```bash
python3 scripts/remove_gif_background.py \
  scripts/harness/fixtures/gradient_alpha_source_1280x512.png --recommend
# v6.4.1 prints: gif-ok / False
```

**Root cause.** The verdict comes from `detect_fading_colors` (`:5629`) over `build_art_palette` (`:5531`) — machinery that asks whether a colour *in the art palette* unmixes as a fade toward the background. Right for a GIF whose fade was flattened at authoring time; blind to a source that already carries an alpha channel, because the palette scan never reads the alpha plane.

**The fix is smaller than the source report knew.** `_partial_alpha_seen` already exists at `:1794`/`:1807` and is surfaced as `measured_on_alpha_composite` at `:2090`. The verdict block at `:2924-2974` never consults it.

### D2 · RUN · one line, the wrong transparency spelling

`scripts/remove_gif_background.py:2200` reads `'transparency' in im.info` — the palette-index spelling. An RGBA source carries no such key, so this reports `false` on a file with 315,504 alpha-0 pixels. `get_source_transparency_mask` (`:943`) already handles RGBA correctly and **its own comment dates that fix to 2026-08-18 and names this failure class as one the project keeps hitting.** The function was fixed; the report field was not.

### D3 · RUN · the background is sampled from four corner pixels

`detect_bg_color` (`:247`) majority-votes four corners; disagreement prints a stderr warning `--auto` does not act on. Measured over 101 corpus images: **3** have four agreeing corners; **38** give an answer further than `--tolerance` from the modal RGB of an 8 px border ring, up to **38.7**. Corners are the worst place to sample on artwork with any vignette. Not yet shown to break a delivered asset — an exposure with a thin margin.

### D4 · RUN · a single colour cannot express a background field

| asset | background spread | tolerance needed | art destroyed |
|---|---|---|---|
| app icon | **79.7** | ~80 | **12.14%** |
| vignette banner | **62.0** | ~63 | 3.04% |
| wordmark *(flat control)* | 19.2 | ~20 | 0.01% |

Session 3 independently measured the same icon with a different mask: luminance **43.8 → 13.5** brightest ring to corners.

### D5 · RUN · the renders, looked at rather than measured

Session 1's three wordmark outputs on a checkerboard: `out_fade` keeps the glow as an **opaque navy haze**; `out_nofade` ramps it away and leaves the **vortex core as a hole**; `out_v2` keeps the core and carries **more halo than either**.

**The fork's arms were *too much* and *too little*, not "both wrong".** The glow genuinely is dark navy, so a faithful recovery *should* read as grey haze on white — which validates the refusal. What no flag expresses is the answer that was right: **recover it partially**. The fork is missing its middle.

### G1 · READ · no colour-space handling anywhere
Zero hits for `gamma`, `srgb`, `2.2` or a linear-light round trip. Every alpha estimate, unmix and composite runs on gamma-encoded sRGB. **Exactly correct for sRGB-authored art**; wrong for linear-authored art. Consequence is O1, unproven.

### G2 · READ · the calibration curve's shape is half-read
`calibrate_edge_cleanup_erosion` (`:7716`) builds `table = {0:v0, 1:v1, 2:v2, 3:v3}` then reduces it to `min()` plus a pick. `earned_erosion_ceiling` **does** read convexity (the knee at 2, §37.10) — the principle is established and implemented for one shape. The flat case is not tested. Session 1 measured the tell on the wordmark: `0.6349 → 0.5862`. Statistic is `v0 − min(v)`, **not** variance across all four.

### G3 · READ · the recommender can only move the band's endpoint
It appends `--feather-band-multiplier` (`:2852`) and never a `--tolerance` value. Session 1's accepted command moved the **start** (15→8). Session 3 measured that the start is the perceptual variable: 0.34-0.475 reads as "fading", 0.66 as "a crop", identical endpoint.

### G4 · READ · every check is differential
No assertion anywhere that the output contains `alpha == 255` pixels. Session 3 shipped a global 5% opacity ceiling nobody noticed. *Honest negative: `unmix_family_blend`'s softmax (`:5600`) **is** correctly normalised — flagged speculatively by session 3, and clean.*

### G5 · READ · no spatial alpha map
63 flags, none keyed to canvas geometry. `--translucent-region` is region-scoped, colour-keyed and uniform; `--edge-softening` is a 1 px silhouette ramp; `--recover-fade-alpha` reconstructs from colour.

```python
r       = (abs(nx)**p + abs(ny)**p) ** (1/p)   # nx, ny normalised to +-1 over the canvas
falloff = clip(1 - smoothstep(start, 1.0, r), 0, 1)
alpha   = minimum(alpha, falloff)               # MINIMUM, never assignment (SS31)
```
`r == 1` at every edge midpoint for any `p`; the corner sits at `2**(1/p)`, so **p is a pure corner knob**. Defaults from real use: `start=0.45, p=4.0`.

### O1 · OPEN · the colour-space consequence
Synthetic only. Against a linear-authored composite over `#141124`: recovered-colour error **136.1** at α=0.15 on saturated mid-tones, alpha estimate biased **always positive**, up to **+0.25** — linear-authored edges render *more opaque* than they should. Signature is a **bow** off the background→colour line, 5-7 units vs **0.00**, below the existing `FADE_RESIDUAL_TOLERANCE = 10.0`.
**Test:** run the bow measurement over the labelled GIF corpus in `local/`, isolating one art colour per measurement by connected component and excluding near-background darks. **If real assets cluster near 0, the branch closes.**

### O2 · OPEN · does the `0.25` clamp matter?
`estimate_alpha_and_defringe` (`~:3963`) uses `a_safe = np.clip(alpha, 0.25, 1.0)` before dividing. **Measured: binds on 28.2% of real band pixels** (13.3% below α=0.10), at the band's **outer** end.
**Test:** render a real asset twice, floor at 0.25 and at 0.05, and compare the outer band's chroma against the adjacent interior. Under-dividing pulls a pixel toward the background, i.e. desaturated. Nil delta closes it.

### O3 · OPEN · small features through the fit ladder
`_FIT_SCALE_LADDER` descends to 0.25 with `_SCALE_COST`/`_STRIDE_COST` as hand-assigned preferences, not damage measurements. Nothing measures whether a 2 px highlight survived; `--pixel-art` selects NEAREST, which drops rather than rings.
**Test:** count connected components of local maxima above a contrast threshold before and after the fit, on real stickers at a 256 KB cap.

### O4 · OPEN · pooled jitter broadens the hardness measure
The skill pools hardness across frames; on a tumbling sprite the same edge sits at a different sub-pixel offset each frame. **Prediction:** a rotating hard-edged sprite measures *softer* than the same sprite still, and misclassifies as antialiased.
**Test:** score a hard-edged corpus sprite, then a synthetically rotated copy, and compare `edge_hardness`.

## 5. Implementation Decisions

**The format verdict reads the alpha plane.** Compute a partial-alpha **fraction** over the frames the loader already returns; disqualify GIF above a threshold, structurally identical to the existing `has_fully_transparent_frame` steer toward WebP/APNG. The same fraction gates the evidence string so verdict and stated reason cannot diverge. **A fraction, not a count**, and the number is printed whether or not it binds — a threshold nobody can see the input to is a threshold nobody can audit.

**`source_has_pre_existing_transparency` is derived from the mask.** Consume `get_source_transparency_mask`; add `source_transparent_fraction`, which the render path already computes. **The `im.info` audit ships with this change, not after it** — the comment asserts the class is recurrent, so one pass closes the class rather than one instance.

**The erosion calibrator gains a reading, not a decision.** `v0 − min(v)`, not variance. Below a floor the run states erosion bought nothing measurable. **The selected level does not change.**

**The recommender gains the band's start.** Symmetric ability to append a `--tolerance` value, and the band reported as two endpoints rather than a multiplier.

**One absolute assertion.** A source with fully opaque artwork must produce an output containing fully opaque pixels.

**Counting checks gain a distribution and a largest-instance.** Every count reports the largest connected component's area and bbox; every conservation figure reports a completion figure beside it.

**The background estimate gains a second opinion.** Four-corner sample retained as primary; the modal colour of a border ring computed alongside; their distance reported **in the analysis object**, not only on stderr.

**Then, and only after O1 and O2 report:** background as a field. `bg` becomes a function of position, estimated along whichever axis it is invariant along — radial for a vignette, linear for a gradient. Session 2's v6 discipline is the build spec, because each of its hard-won failures maps to a way this ships broken:

| lesson | what it forces |
|---|---|
| anchor the reference where the feature cannot reach | estimate only from pixels far from artwork |
| refuse to invent a value where there is no data | a region with no background samples reports **undetermined** |
| a real measurement does not license a correction | prove non-flatness first; the wordmark must come out byte-identical |
| null control | on a flat asset the estimator returns ~constant, or it is manufacturing a field |
| gated repair | apply per region only where it measurably improves |

**Nothing in sections 5.1-5.7 changes a rendered pixel.** That is the acceptance condition, not a hope.

## 6. Testing Decisions

**A good test here asserts what a caller receives** — a JSON field, a stderr line, or the bytes of a written file — never an internal function's return. **D1 is the reason:** the internal measurement is already correct and the defect lives in a consumer that ignores it. An import-level test would pass while the CLI still emitted `gif-ok`.

**One seam, and it already exists:** `subprocess.run([sys.executable, "scripts/remove_gif_background.py", ...])`, the pattern used by ~20 files under `scripts/harness/` with `pytest.ini` beside them. No new seam. Chosen over an import seam deliberately — release gate 7 is "confirm behaviour, not signatures", and D1 is exactly a case where the signature is right and the behaviour is wrong.

**Prior art**, closest first: `test_auto_coinflip_refusal.py` (the refusal path D1 sits beside), `test_analyze_recommend_redundancy_note.py` (asserting on `--analyze` text), `test_verify_vacuity.py` (proving a check can fail), `test_alpha_edge_fringe.py` (rendering through the CLI and measuring the written alpha plane).

**The fixture is committed, real, and proven.** `scripts/harness/fixtures/gradient_alpha_source_1280x512.png` — a 649 KB crop of session 3's accepted deliverable carrying **11.7% transparent / 73.6% partial / 14.7% opaque** against the full asset's 10.0 / 70.0 / 19.9. Committed rather than referenced in `local/` for the reason the labelled ground truth left `local/` in August. A crop of real content rather than a constructed gradient, because a fixture you draw is chosen to flatter. **Verified to reproduce both defects before this spec was written.**

**Every test must fail on the current code**, and the falsifier is stated per behaviour: the verdict test fails today because the fixture returns `gif-ok`; the field test because it returns `False`; the flatness test because no such line is emitted.

**Every test needs its negative.** The verdict change is paired with opaque controls from the labelled populations — a verdict that moves there means the threshold reads antialiasing the tool computed itself rather than alpha the source shipped with. The transparency field is paired with a palette-transparency GIF and a fully opaque source.

**Corpus confirmation reuses what exists.** `render_baseline.py --set standard --compare` must report **0 changed**. `run_populations.py` is re-scored only if a hardness rule or anything one reads is touched — nothing here should, and if that turns out false it is a signal the change grew beyond scope.

## 7. Retracted claims — do not re-derive

*Paired with §8, which records approaches that were measured and lost. Both exist for the same reason: to stop a session spending a day on something already settled.*

| id | claim | why it died |
|---|---|---|
| **R1** | The `0.25` clamp under-corrects at the band's **inner** edge, so the tool's own arithmetic puts a defect where no instrument looks | Measured backwards. Low-alpha pixels sit **11.81 px** from the core vs **9.37 px** for all band pixels — the **outer** end. Alpha is low where distance-to-background is low. The clamp still binds; it has no inner-edge consequence |
| **R2** | The gamma bow is confirmed on real content | Two failed attempts. Pooling all band pixels against the bg→white line: median 21.33. Isolating the five white letter components correctly: median 25.26, p90 111.73 — the letters sit over a **nebula**, so the background varies by tens of levels and swamps a 5-7 unit signature |
| **R3** | "Two of three sessions independently derived X" is strong evidence | Session 3 **read** reports 1 and 2 first and could re-measure none of their numbers. Only session 2's pre-report derivations are independent: component-geometry separation, the amplified view, orientation splitting, integer-offset profiles |

**Three of this audit's own measurements failed the same way** — comparing two populations that were not the same pixels (R1's direction, R2's bow, and an attempt to prove a counter-hole rim was tool-added). Every one is "the bucket does not contain what its name says", committed three times by the person auditing for it. **Before comparing two populations, print `n` for each and confirm they are the same pixels.**

## 8. Evaluated and rejected — the other half of "do not re-derive"

**Nothing about improving the skill is out of scope.** This section is not an exclusion list; it is the record of approaches that were *measured against* the skill and lost, so that a future session does not spend a day rebuilding one. Each fails the same test: **can I name the asset it fixes and the measurement that shows it?**

| approach | why it lost |
|---|---|
| Fill-vs-subtract for fringe repair (session 1's own headline) | needs an axis the artifact is invariant along. A grid line is constant along its length; a keyed fringe changes colour continuously around the outline, so a robust median along it has nothing to average. Sample count is not the objection — it fails on a 4000 px asset too |
| Lattice tracking, sub-pixel binning, junction patches | need a periodic structure to track |
| Grain synthesis, normalized-convolution fill, texture copy | fill-repair for continuous tone; the skill's artifact is a keyed colour, and where it is a composite the exact algebraic inverse already exists |
| Frequency-domain separation | session 2 falsified it themselves: 1.136 with the grid present against 1.132 with it removed, inside a grid-free null of 1.116-1.165 |
| Ensembling as an improvement method | every combination landed inside the inputs' own spread |
| `super:cx,cy,rx,ry,p` region grammar | session 3 marked it speculative; justifying it needs a `circularity_ratio` distribution over regions where `circle_region_safe` is false, and nobody has that distribution |
| Polarity as a colour-direction concern | the skill's metric is a vector norm and its unmix is signed, so there is no directional assumption to break. *The useful residue — that every fringe instrument reads outward — survives as an observation in §4* |

**One reversal worth keeping.** Ensembling is dead as a method and live as a **diagnostic**: variants that average to no better than any of them share a common-mode error. `--auto`'s two-signal erosion calibration is a candidate, because both signals read the **outer ring** and may be blind in the same direction. **Two signals blind the same way are one signal.** Filed into phase 5.

**The only genuine exclusions**, and they are not about the skill: the three sessions' own pipelines as *products* (removing a coordinate grid from a nebula is a seven-hour specialist job, not a capability this tool should grow), and publishing this to an issue tracker (none is configured).

## 9. Build order and cost

**Dependencies are real.** O1 and the background field are **upstream** of the alpha ramp, the erosion curve, the fringe metrics and the hardness discriminator. Fixing anything downstream first means re-tuning it after.

| phase | items | why here | size |
|---|---|---|---|
| **0. Settle upstream** | O1, O2 | both cheap, **both can return "no"** and close a branch | S each |
| **1. Pixel-neutral instrumentation** | D2, G2, G4, the aggregation-axis audit | changes no output bytes | S-M |
| **2. Advice defects** | D1, G3, **+ GIF alpha dithering** | wrong advice is what an autonomous run consumes. Dithering inherited partial alpha ships HERE and never alone: the honest result is a visible mesh, and without D1 that only moves the failure from invisible to ugly | M |
| **3. Additive capability** | G5 `--edge-fade` | independent; reference impl and acceptance test supplied | M |
| **4. Structural** | the background field, D3 | real feature with a refusal path and a corpus re-score | **L** |
| **5. Measured experiments** | per-site erosion gating, O3, O4, the two-signal common-mode check (§8) | each needs a corpus run before belief | M each |

**Do not bundle phase 4 with anything.**

**Cost worth knowing.** `--recommend` took **87.5 s** on one 3072×1024 frame; two calls do not fit in a 120 s tool call. A 4.2 MP asset is ~12× the GIF corpus's 0.36 MP — the tool is most expensive exactly where the product is expanding. The committed fixture is a sixth of that area, which is part of why it is the size it is.

## 10. Further Notes

### 10.1 The design target

Rather than a proposal list, design against the near-certain next request: **"rebuild the banner from the no-grid nebula, with the wordmark and the edge fade."** It walks into every finding at once — a re-cut wordmark (D5's missing middle), a non-flat background (D4), an edge fade (G5), a 70%-partial-alpha output (D1), then an upscale (provenance). **If the tool can do that job without a human writing numpy, the findings were the right ones.**

### 10.2 The vocabulary gap

Every user rejection across the three sessions names a specific measurable property, and `--verify` speaks none of them:

| what was said | the statistic | exists? |
|---|---|---|
| "colors seem more **smudged**" | chroma noise of the change (0.612 → 0.010) | **no** |
| "**eating into** the artwork" | ramp **start** vs endpoint | computed, never reported separately |
| "hints of lines when I **zoom in**" | worst localised residual | **no** |
| "it **erased pixels**" | over-correction distribution (p1, p5) | **no** |
| "the **brighter regions**" | per-background-bucket defect distribution | **no** |

Session 2 recorded that the user was right on all 8 occasions a metric disagreed with them. The mechanical reading: **the user's vocabulary contains distinctions the tool's cannot express, so the metrics could not have won.**

### 10.3 Five aggregation axes, not one slogan

"Report the worst frame, not the mean" is five distinct failures, which is why this "one" lesson keeps being re-fixed: the centre hiding the tail; a membership count blind to transformation within the set; an aggregate over the wrong axis (channels); a spatial mean hiding a localised defect; a temporal mean hiding consecutive bad frames. **For every statistic reported, name which axis it aggregates over and what it therefore cannot see.** *(Channel axis is clean here — no `.std()`/`.var()`/`np.ptp()` anywhere.)*

### 10.4 Session title and model call

*The starting prompt itself is at the top of this document.*

**Session title:** `Opus5-high · Session-report findings phase 0 · 2026-09-09`

**Model + effort: Opus 5, high.** From the two-axis grid, not the effort tier. Premise risk binds: this audit retracted three of its own claims, and two open hypotheses can invalidate work done downstream of them. Deliberation load is moderate — the tasks are individually small. **If phase 0 closes both branches and the work becomes mechanical instrumentation, step DOWN to Sonnet-high and say why.**

### 10.5 Evidence index

| what | where |
|---|---|
| D1's test asset, session 3's 24 outputs, scripts, verification | `local/claude ai session reports/session 3 report (banner edge fade)/` |
| Session 1's wordmark + `out_fade`/`out_nofade`/`out_v2` — a fixture with a human-accepted answer | `local/claude ai session reports/session 1 report (reduced grid)/` |
| Session 2's source, v6 final, 6 named failure files, annotated screenshot | `local/claude ai session reports/session 2 report (removed grid)/` |
| The 101-image `detect_bg_color` table | `docs/investigations/2026-09-09-devoid-corpus-bg-detection.md` |
| Production corpus | `/Applications/Claude Code/Devoid/DEVOID Logo Assets/` |

**Hash-confirmed production lineage:** `DEVOID Workmark_Transparent.png` = session 1's delivered output; `DEVOID Nebula_NoGrid.png` = session 2's `00_FINAL_v6.png`. *(Several finals then went through Upscayl at 1×, which is why `out_v2.png` is not byte-identical to the delivered file.)*

### 10.6 What was not done

- **~70 scripts across the three bundles remain unread**, including ones their READMEs mark "broken by design and kept".
- **The tool was run twice.** Every other behavioural claim is a code read — one layer from release gate 7.
- **No corpus re-score, no render diff, no falsifier suite** was run for anything proposed here.
- **Release gate 8 is unrun**, three shipped versions deep. Several items here are exactly what it exists to catch: advice that is confidently wrong while the render is correct is invisible to a corpus score, a code review and a render diff alike, because all three compare the product against itself or a label.
- **doc-coauthoring Stage 3** (reader-testing with fresh sub-agents) is held pending Harkirat's go. Stages 1 and 2 did not apply.
- **`to-spec`'s publish step** was not run — no issue tracker is configured and `/setup-matt-pocock-skills` has not been run here.
