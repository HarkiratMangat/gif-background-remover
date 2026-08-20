# ✅ GIF Background Remover — resolved list

**Archive. Not active content. Do not read this file by default** — grep it when you are about to re-litigate something, or when an item's history matters.

Where entries from `gif-deferred-list.md` come to rest once they ship, get dropped, or turn out not to be real. Created **2026-08-18** on Harkirat's instruction, modelled on Dior's Builds' `docs/archive/resolved-list.md`, because the active tracker had grown to 313 lines of which two thirds were closed work — and a live P1 sat below three closed items, which is how the tracker came to report 14 open when 12 was the truth.

## The rules
- An item moves here the moment it is **shipped / dropped / proven-not-an-issue**, in the same pass that closes it. **Never delete — always move.**
- Keep the original wording and add the outcome: **what happened, when, and where the full story lives** (version, commit, `references/lessons.md` section).
- Newest at the top of each section.
- **Not for standing "decided-no" calls that could get re-raised** — those stay visible in `gif-deferred-list.md`'s own ✅ Considered-and-NOT-fixed section, precisely so nobody re-opens them.
- **Conservation is gated, not trusted:** `python3 scripts/audit_docs.py --diff <base>` fails a branch that removes a substantive line from the active list without adding traceable text here. A sweep and a deletion look identical in a diff; the gate is what tells them apart.

---

## ✅ A background that CHANGES COLOUR mid-animation is now detected, reported and refused — CLOSED 2026-08-20 (v6.0.0, branch `feat/v6-backlog`)

**Original entry, struck through:**

> ~~### `[P2 · M · Opus5-High]` A background that CHANGES COLOUR mid-animation is unprocessable, and nothing detects it *(filed 2026-08-20)*~~
>
> ~~`--bg-color` is one value and `detect_bg_color` reads frame 0, so an animation whose background changes colour cannot be processed at all — and no check anywhere reports that. Measured on `Pew Pew Pew.gif`: the background cycles magenta → pink → red → orange → yellow → green across frames 11–15 of 30, and on frame 12 the frame-0 colour covers **0.0%** of the canvas. Six such assets are now isolated in `local/corpus dark/_changing_bg/` with their worst frame and colour transition recorded.~~
>
> ~~⚠️ **It was found by eye, by Harkirat, after passing an automated filter that never looked at the background across frames** — and then my first attempt to measure it SAMPLED 10 frames across 30 and missed the 5-frame window, reading 78.6% at frame 10 while frame 12 was 0.0%. A consecutive per-frame scan of all 65 remaining animated assets then found **zero further cases**, so the six are the complete set. **A spread cannot see a transient; on a 309-frame file a 12-sample scan would step straight over it.**~~
>
> ~~**Do:** detect it in `analyze()` — scan every frame's detected background colour, and if it moves beyond a tolerance, say so and refuse rather than silently keying frame 0's colour across an animation where it means nothing. Whether a per-frame background colour is worth supporting after that is a separate and larger question. Start from `_changing_bg/`, which is the only place in the corpus that demonstrates this.~~

**What happened.** Implemented in an isolated worktree and merged. The three-place pattern the truncating-GIF fix established: `analyze()` reports `background_color_stability`, `recommend()` returns `not_applicable_reason` with a null command so `--auto` refuses, and `process()` refuses independently for a run that never called `--recommend`. `--allow-changing-background` is the escape hatch and reaches all three paths. The scan runs on EVERY frame, riding the per-frame loop `analyze()` already runs and reusing the background mask it already computes — a spread cannot see a transient, and the first attempt at this measurement read 78.6% coverage at frame 10 while frame 12 was 0.0%.

**The rule needs both halves, and that is measured rather than assumed.** A frame counts as recoloured when its corner-majority colour moves more than 40 units AND the reference colour's coverage collapses below 15% of its frame-0 share. Each half alone has a real false positive in the 65-asset animated control: a corner move alone fires wherever art sweeps a corner (`Ghost.gif` reads 11 distinct corner colours with a constant background), and a coverage collapse alone fires wherever art fills the canvas (two controls bottom out at 0.0% and 0.65% with corners that never move).

**Verified:** 6 of 6 positives fire, 0 of 65 negatives do; one negative reports `null`/unverified rather than a quiet pass, which is the intended fall-through. The verdict is invariant across all 30 cells of distance ∈ {24,32,40,60,90,120} × collapse ∈ {0.05,0.10,0.15,0.25,0.50} — every negative produces zero qualifying frames, so this is a threshold the control never reaches rather than one it clears. Value spread proving the measure is measuring: `min_reference_coverage` takes 67 distinct values across 0.0000–0.9876. `analyze()` timing delta is inside run-to-run noise (−3.0%, +6.5%, −1.3% on three long assets, against a 61.6–82.8s spread on one of them). 55 tests pass, 15 of them new with all fixtures synthesised in-test; `love.gif --auto` still `2fd526b6fb3b191c`; `audit_docs.py` exits 0. Full write-up: `references/lessons.md` §36.

**Two extra defects found while verifying, both fixed here:** a `process()` refusal is `raise SystemExit`, which is not an `Exception`, so ONE refused asset aborted a whole batch and the next good file produced no output. And Pillow's animated-WebP writer collapses identical consecutive frames, which silently turned three 10-frame fixtures into 2-frame files — a falsifier that passed for the wrong reason. Both are now structurally guarded rather than remembered.

**One finding rolled forward:** `Ying and Yang Koi Fish.gif` crashes `analyze()` on a frame one pixel wider than the canvas. Pre-existing and unrelated; filed as a P3 on the active list.

---

## ✅ `--recover-fade-alpha` was recommended where the renderer's own detector disagreed — CLOSED 2026-08-20 (v6.0.0, branch `feat/v6-backlog`)

**Original entry, struck through:**

> ~~### `[P1 · S · Opus5-High]` `--recover-fade-alpha` GHOSTS the whole image on a flat dark background, and `--recommend` asks for it *(filed 2026-08-20 from the dark corpus)*~~
>
> ~~`local/corpus dark/_ (7).gif` — a flat BLACK background (border 93.7% within tolerance of `#000000`). `--recommend` emits `--tumble-safe --recover-fade-alpha`, and the render keeps **100% of the background**: `bg_removed_worst 0.0000`, `bg_not_opaque_worst 1.0000`, `bg_kept_fade_correlation 1.0000`. Every background pixel survives at low alpha tracking its own distance from black — the whole frame becomes a translucent ghost.~~
>
> ~~**This is the hurricane mechanism (`references/lessons.md` §34.2) on a dark background**, and it is worse here: against white, a ghosted output at least composites plausibly over white; against black, "distance from the background" is *brightness*, so every lit pixel in the image reads as a fade stage. **`detect_fading_colors` has never been measured on a non-white background** — the whole corpus was white-ish until 2026-08-20.~~
>
> ~~**Do:** find out whether the fade detector has any specificity at all on a dark background before trusting the recommendation. If it does not, `--recommend` must stop suggesting `--recover-fade-alpha` there. Start from this asset; the `dark_bg` population has 55 more dark ones. ⚠️ Note the recommendation ALSO pairs it with `--tumble-safe`, which fade recovery ignores — the warning added 2026-08-20 fires here, so the run now says so out loud, but saying so is not choosing correctly.~~

**What happened.** The filed hypothesis — that `detect_fading_colors` over-flags on a dark background because "distance from the background" there is brightness — was measured and **falsified**: on the three worst assets the detector flagged nothing at all, and background luminance does not separate the recommendation (61% dark vs 55% white among flat-keyable assets whose screen fires). The real fault was that `--recommend` gated the flag on `band_interior_regions`' `gradient_fade` verdict, a cheap screen the renderer never reads; across the 34 assets where the flag fired, screen and detector disagree on 16, and that half holds every catastrophic output. Fixed in three places: `analyze()` confirms the screen with the detector when and only when the screen fires (tri-state, fall-through is *unverified*), `recommend()` emits the flag only on a confirmation and explains itself otherwise, and `recover_fade_alpha_frames()` refuses rather than writing a ghost.

**Verified:** worst three dark assets `0.0000 → 0.5043`, `0.0004 → 0.7241`, `0.1759 → 0.9176`; `_ (15).jpeg` exit 1 → 0.9945. All 17 confirmed-fade assets byte-identical; white controls 9 of 10 byte-identical, the tenth improved 0.7258 → 0.9156. `love.gif --auto` still `2fd526b6fb3b191c`; `audit_docs.py` exits 0; 36 tests pass, four of them new falsifiers including the negative half (satellite.gif must STILL get the flag) and the unverified fall-through. Cost: `analyze()` +42-51% on assets whose screen fires (hurricane 15.3s → 23.0s), paid only there. Full write-up: `references/lessons.md` §35.

**One finding rolled forward rather than closed:** a soft glow on a dark background has no single fading colour, so neither path handles it well — refiled as a P2 on the active list.

---

## Where these came from

*Two section preambles from the active list are kept here because the sections they described no longer exist.*

- *On the two oldest items (`--analyze`'s runtime regression, `band_interior_regions`' grouping):* "Populated 2026-08-07, end of the session that shipped `--analyze`/`--recommend`/`--verify` (Phase 1 of the optimization work, branch `feat/analyze-recommend-verify`). Both items below were found during that session's final whole-branch review, genuinely attempted, and correctly NOT fixed in that session because each needs a real design decision, not just more time. See `local/HANDOFF-phase2-prose-compression.md` and `local/plans/2026-08-07-analyze-recommend-verify.md` for full context."
- *On the 2026-08-17/18 audit batches, which used to live in a "🔬 Findings ledger" section of the active list:* "These sat under 'Resolved' with no heading of their own until 2026-08-18, so a session skimming for open work could skip live P1 items." That section was **dissolved on 2026-08-18** by this split: its closed items are below, and its one open item (`edge_hardness` misclassifies pixel art) moved into the active list's Open section under P2. A section whose stated purpose was "OPEN and closed mixed" has no reason to exist once they are separated.

---

## Shipped / fixed / closed

### ✅ CLOSED — `--recover-fade-alpha` silently disabled every protection flag
**Closed:** 2026-08-20, on `feat/v6-backlog`. **Full story:** `references/lessons.md` §34.4; plan task 5.

**What happened.** The combination is now refused OUT LOUD rather than composed. `--recover-fade-alpha` takes its own render branch, deriving protection topologically (enclosed = opaque) and never consulting `protected_masks`, so `--tumble-safe`, `--protect-outline-color`, `--protect-region`, `--protect-band-only` and `--keep-bg-blob-if-near` were all ignored with no message. The run now prints exactly which flags are being ignored, says "not weakened, ignored", and points at §34.4. Verified live on the asset that motivated it: combining fade recovery with `--tumble-safe` on growth prints `does NOT apply --tumble-safe, --protect-outline-color`.

**Not composed, deliberately.** Making the two paths compose is a real design question — the fade branch's flood starts from the canvas border, which is precisely what tumble protection exists to prevent — and a much larger change than this item. The difference between a known limit and a silent one is the message.

<details><summary>Original item, kept verbatim</summary>

### ~~`[P2 · S · Sonnet5-High]` `--recover-fade-alpha` silently disables `--tumble-safe` and every other protection flag *(filed 2026-08-19)*~~

The render loop takes the `recovered_rgb` branch and skips `protected_masks` entirely, so a run combining fade recovery with tumble-safe protection gets only the former, with no warning. Found by the expert-prompt agent on `growth.gif`, where fade recovery deletes the rocket body on ~25 frames because its flood starts from the canvas border — and `--tumble-safe` is exactly the fix that cannot be combined with it. **Do:** either make them composable or refuse the combination out loud.

</details>

### ✅ CLOSED — the two erosion items, which contradicted each other and were both wrong
**Closed:** 2026-08-20, on `feat/v6-backlog`. **Full story:** `references/lessons.md` §34.5; plan task 4 of `docs/plans/2026-08-20-post-trial-defects.md`.

**Outcome: the CODE was right on all five assets and SKILL.md's sentence was the bug.** Measured on the calibrator's own fringe metric (pale-near-background share of the outer opaque ring) at erosion 0/1/2 — galaxy 0.0000/0.0000/0.0000 → picks 0; satellite 0.0000/0.0000/0.0000 → picks 0; hurricane 0.0521/0.0362/0.0358 → picks 0; growth 0.1548/0.0219/0.0219 → picks 1; rocket 0.1462/0.0371/0.0373 → picks 1. Five of five correct, and it genuinely ran on all five — the two flat-zero curves were checked for vacuity rather than assumed (11/11 and 10/10 frames measured, exactly 0.0000 on every individual frame). The "2,878 art pixels" is 0.27% of that asset's opaque pixels and buys a 7× fringe reduction: the price of a correct decision.

**The P3 artefacting item is a PREFERENCE, not a defect.** On the two assets whose outlines the reviewer disliked there is no fringe at any level; erosion 1 improves the look only by deleting the antialiasing ramp, which is what the 8-bit-alpha rule exists to preserve. Now documented in SKILL.md as an explicit style choice (`--edge-cleanup-erosion 1`), with the measurement, rather than being made a default.

⚠️ **Two metric traps were walked into and caught, and they are the transferable half.** (1) An ALPHA-based edge score said erosion 1 was a big win on the two zero-fringe assets — but a soft antialiased edge legitimately carries partial alpha, so a metric counting partial alpha as "unclean" rewards destroying antialiasing. (2) A worst-frame FRACTION said erosion 1 destroyed 21% of one asset's artwork. **Harkirat challenged that number directly and was right**: erosion removes a perimeter (O(r)) while "art present" is an area (O(r²)), so the fraction grows without bound as the subject shrinks. That asset's worst frame is one where the rocket has nearly left the canvas — 5,232 art pixels against 84,672 on frame 0 — losing 695, the smallest absolute loss of any worst frame measured, and its total loss (2.70%) is the lowest of the four assets. The cheap discriminator: `lost / perimeter` ran 0.70–0.95 across five worst-frame cases, always under one full ring, so nothing thin was bitten. **A defect's absolute magnitude stays large as the denominator shrinks; a geometric cost shrinks with it.**

<details><summary>Original items, kept verbatim</summary>

### ~~`[P2 · S · Sonnet5-High]` `--auto` calibrates erosion by default, while SKILL.md says `--auto-erosion` is what enables it *(filed 2026-08-19)*~~

SKILL.md: "Add `--auto-erosion` to have `--edge-cleanup-erosion` calibrated against the asset's own fringe curve rather than a global default." The code: `args.auto_erosion = 'edge_cleanup_erosion' not in _typed` — it is ON unless you pass an explicit erosion. Measured cost on `growth.gif` → WebP: the default loses **2,878 art pixels** against explicit `--edge-cleanup-erosion 0`, and it overrides the documented WebP default of 0 to do it. A documentation/behaviour contradiction in the direction that damages artwork. **Do:** decide which is right and make both agree; if default-on is right, SKILL.md's sentence is the bug.

### ~~`[P3 · S · Sonnet5-High]` WebP's erosion-0 default leaves visible outline artefacts on some assets *(filed 2026-08-19 from visual review)*~~

Human review of the trial outputs: galaxy's WebP and GIF at erosion 0 carry "anti-aliasing outline effect across its entire outer navy outline… not a clean polish", while the same asset at erosion 1 scored 9.5/10 with only minor speckles. The documented rule is that 8-bit alpha needs no fringe trim — true for the alpha, but the RGB fringe from colour unmixing is still visible. ⚠️ Interacts with the erosion-calibration item above: they disagree about which default is right. **Do:** measure outline cleanliness directly rather than inferring it from the alpha depth.

</details>

### ✅ SHIPPED — `--recommend` called a large interior design region "incidental background"
**Closed:** 2026-08-20, on `feat/v6-backlog`. **Full story:** `references/lessons.md` §34.3; plan task 3 of `docs/plans/2026-08-20-post-trial-defects.md`.

**What happened.** `likely_intentional_design` was a bare `enclosure_ratio >= 0.9`, size-blind. It is now a named predicate, `is_intentional_design(ratio, pixel_count, canvas_px)`: 90%+ enclosure at any size, OR 50%+ enclosure at 2.5%+ of the canvas. The **same** predicate now gates the partial-outline search, which previously carried its own copy of the 0.9 constant — without that, growth's region would have been relabelled design and then denied the only thing that could protect it, which is worse than either half alone. Measured effect: `growth.gif --recommend` goes from `Region 1: enclosure_ratio 0.825 looks incidental` to recommending `--protect-outline-color 002864` via the partial-outline path, and `interior_kept_worst` on a real `--auto` render is >0.95 where agents 1 and 2 scored **0.000**.

**The measurement, over 26 assets and 22 regions at ≥0.5% of canvas, every ambiguous one inspected by eye.** The decisive pair is a leg-gap at 1.2% of canvas / ratio 0.625 (BACKGROUND) against a rocket wing panel at 3.9% / ratio 0.650 (DESIGN) — 0.025 apart in ratio, opposite answers, separated only by area. Both constants sit in gaps (area 1.2%→3.9%, ratio 0.286→0.650), not between neighbours.

⚠️ **It also corrected a wrong number this repo had already published.** §34.3 previously advised that "a region above roughly 1% of the canvas is not incidental at any ratio". The leg-gap is 1.2% and is background; a pocket under a raised arm is 8.1% at ratio 0.286 and is also background. An area-only rule protects real background.

⚠️ **One case is deliberately NOT covered and is documented as the limit:** a badge fading toward the background colour reads as background only at the end of its fade — ratio 0.050 at 41.8% of canvas. That needs `--recover-fade-alpha`, not region protection.

**Verified:** three falsifier tests, including the negative half (the leg-gap must still come back `likely_intentional_design: False`) and an end-to-end `--auto` render graded by `scripts/harness/score_outputs.py`.

<details><summary>Original item, kept verbatim</summary>

### ~~`[P1 · M · Opus5-High]` `--recommend` calls a large interior design region "incidental background", and two of three agents destroyed the asset because of it *(filed 2026-08-19)*~~

On `growth.gif`, `--recommend` emits: `Region 1: enclosure_ratio 0.825 looks incidental, leaving as background.` **That region is the rocket's white body.** In a three-agent trial on five real assets, the two agents that followed the recommendation deleted **83.1% and 83.3% of growth's interior white**, and **45.8% of rocket's**, in both cases while reporting success. Only the agent given an explicit hand-written list of regions to protect got all five right.

⚠️ **The severity is in who it fools.** Agent 2 was told in plain language that interior light areas were artwork, ran the tool, read the evidence, followed it, and shipped a ruined file believing it was clean. This is not a missing lesson — no amount of documentation reaches a session that is being actively misadvised. **Do:** an enclosure ratio of 0.825 over a region of this size should not read as "incidental". Re-derive that threshold against region AREA, and check what the evidence string says when the region is large and the ratio is mid-range.

</details>

### ✅ SHIPPED — A fully-transparent frame makes Pillow's GIF writer truncate the file
**Closed:** 2026-08-20, on `feat/v6-backlog`. **Full story:** `references/lessons.md` §34.1; plan task 2 of `docs/plans/2026-08-20-post-trial-defects.md`.

**What happened.** Three changes, because prediction and prevention are different jobs. `analyze()` gained `has_fully_transparent_frame` and `fully_transparent_frames`, scanned on EVERY frame rather than on `sample_idxs` and piggybacked on the per-frame `color_mask` the margin/small-region checks already compute, so it costs nothing extra — growth's blank frame is frame 85 of 123, a single frame, and the changing-background item filed the same day is the standing record of what a spread does to a transient. `recommend()` gained a FORMAT branch that outranks the fade check and emits `FORMAT: .webp or .apng -- NOT GIF`, because an autonomous run takes those flags verbatim. And `process()` refuses the write, checked on the FINAL alpha planes after every stride/resize/tier transform (`--frame-stride` can legitimately skip the blank frame, so the source-side prediction steers the recommendation while the render-side check is the one that cannot be wrong). `--allow-truncating-gif` is the escape hatch.

**Verified:** `growth.gif --auto` → `.gif` now exits 1 naming frame 85 of 123 and writes nothing; with `--allow-truncating-gif` it exits 0; `.webp` exits 0 with all 123 frames. `love.gif --auto` still hashes `2fd526b6fb3b191c`. `audit_docs.py` exits 0. Four falsifier tests in `scripts/harness/test_score_outputs.py`, including the negative half — `rocket.gif` must report `False`, because a detector that says True on everything is not a detector.

**The transferable lesson:** the script ALREADY warned (`Saved (85 frames written from 123 intended)`) and wrote the broken file anyway. A warning emitted after an irreversible write is not a gate.

<details><summary>Original item, kept verbatim</summary>

### ~~`[P1 · M · Opus5-High]` A fully-transparent frame makes Pillow's GIF writer truncate the file *(filed 2026-08-19 from the three-agent trial)*~~

`growth.gif --auto` → GIF: `gifsicle: unknown block type 71 at file offset 702623`, **85 of 123 frames readable**, 1700ms of 2920ms. Root cause confirmed three ways — my own synthetic control, and independently by two of the three trial agents with their own controls: **an all-transparent output frame breaks the writer.** growth has one (frame 85, the rocket entirely off-canvas). Not flag-dependent: reproduced at defaults, with `pngquant`, and with `--dither-mode none`. WebP and APNG keep all 123.

The script DOES warn — `WARNING: total playback length changed on write (2920ms intended, 1700ms written)` and `Saved (85 frames written from 123 intended)` — so this is not silent. **It writes the broken file anyway, and nothing in `--analyze`/`--recommend` predicts it BEFORE the render**, which is the autonomy gap: an unattended run ships a file missing 31% of its animation. **Do:** detect an all-transparent frame during analysis and either refuse GIF with a reason or auto-select WebP/APNG. One agent worked around it by duplicating the previous frame, which produced a visible stall — that is not the fix.

</details>

### `[P3 · L (first slice: S) · Opus5-High]` No answer yet for a moving hole with neither geometric separability nor external tracking
**Added:** 2026-08-08, from reconciling the v4.0.0 live-skill-drop (`references/lessons.md` §15).

**The problem:** this repo now has two real solutions to "punch a hole shared with same-color decoration that needs opposite treatment" -- §14's geometric-gate approach (`--tumble-safe` + `--keep-bg-blob-if-near` + tight `--hole-size-range`/`--hole-max-aspect`), which needs the hole and the decoration to differ measurably in size/aspect across every frame; and §15's `--remove-region`, which needs either a static target or an external per-frame tracking script (confirmed: a static circle alone missed the true target in 76% of frames on a real tumbling asset). Neither covers a moving hole that ISN'T geometrically separable from its decoration and has no available tracking tooling -- a real, currently-unsolved case, not yet encountered on a real asset but now a known gap rather than a silent one.

**First slice (S):** wait for a real asset that actually needs this before designing a fix -- speculative design against a hypothetical case risks solving the wrong shape of problem, the same mistake `--keep-bg-blob-if-near`'s color-adjacency approach made when first reached for on §14's own asset. If/when a real case arrives, the likely direction is a lighter-weight, script-native per-frame tracking primitive (a lower-effort analog to the live session's `cv2.HoughCircles` step) rather than requiring bespoke external tooling every time.

**Model pick reasoning:** premise High (no real case yet, so even the shape of the right fix is speculative) · deliberation High (a script-native tracking primitive is real algorithm design) -> `Opus5-High`, and only once a concrete motivating case exists.

✅ **CLOSED 2026-08-19 — `--remove-region-track` ships.** The first slice said to wait for a real asset; Harkirat asked for it to be built now, which supersedes that, and the design turned out not to need one to be falsifiable.

**The insight is that the SEED supplies what no single frame can.** Two identical holes are indistinguishable within a frame and completely distinguishable across an animation, because only one of them is where the seeded one just was. The flag takes `--remove-region`'s spec syntax, treats it as a frame-0 seed, and carries identity forward by continuity: centroid distance from a predicted position, gated at a fraction of the frame diagonal, with area and bbox-aspect ratios relative to the seed as tie-breakers.

**Measured on an asset built to make this item's premise TRUE** — a rotating card with two byte-identical white holes, both orbiting, so neither the geometric gate nor a static region can work: static `--remove-region` punches the target on **1 of 24 frames** (and the decoy on 1), while `--remove-region-track` punches it on **24 of 24 and the decoy on 0**. Control: with both holes protected and no region flag, the target stays opaque on 24/24, so the falsifier could have failed.

⚠️ A constructed asset is legitimate here for the same reason `gradient_beds` is — the question is whether the tracker follows the seeded region, not what kind of art it is. **A real asset should still be run through it when one appears.** ⚠️ Losing the target is REPORTED: when no candidate passes the continuity gate the mask is carried forward along the last motion vector and those frame indices are printed. No new dependency — `scipy.ndimage.label` plus centroids replaces the `cv2.HoughCircles` the live session reached for. `references/lessons.md` §33.

---

### `[P2 · M · Opus5-High]` `edge_hardness` misclassifies pixel art — 3 of 25 still missed *(was `[P1 · L]`; 18/25 → 22/25 with 0 false positives in v5.5.0, 2026-08-18)*

**Added 2026-08-17.** Harkirat supplied `local/Diors-builds Emojis/others/` — 9 real assets, 8 of them genuine pixel art on COLOURED backgrounds. The tool calls 6 of the 8 antialiased. Full ground- truth table, both failure mechanisms, and the measured numbers: `references/lessons.md` §23.

**Why P1 despite being pre-existing:** it is a correctness failure on a whole content class the skill explicitly claims to support, and it fails toward the destructive setting (feather + 2px erosion + LANCZOS on hard-edged art). §18's second discriminator was validated against a synthetic fixture generated in-session, which is circular — this is what that circularity was hiding.

**Shipped 2026-08-17 (two rounds, still partial):** (1) zero transition band is dispositive; (2) `change_line_density` — a geometric, palette-free measure — is dispositive below 0.5. Scored against 37 labelled assets: **17/37 -> 30/37, pixel art 5/25 -> 18/25, false positives 0/12 throughout.** Corpus renders unchanged; love still byte-identical.

**Remaining: 7 assets, all one class** — dithered or photographic pixel art, where dithering puts a change on every line and saturates the density measure (0.592-1.000).

⚠️ **2026-08-18 — that next action was tried, scored 24/25, and FAILED the real test. Do not re-attempt it in this form.** The cheapest dither-suppression is to count lines that are *essentially duplicates* of their neighbour (`fraction_changed <= 0.01`) instead of lines that differ at all. Against the labelled corpus it looked decisive: **24/25 pixel art, 0 false positives**, antialiased topping out at 0.050 against 24 pixel-art assets at 0.150+. Scored against **145 real antialiased vector emoji** from this repo's own folders — the content type the skill primarily exists for — it fires on **37 of them (25.5%), up to 0.735**, because a flat-fill vector icon has large areas where the next column is genuinely identical. The labelled corpus holds only 6 antialiased assets, which cannot show a 25% failure rate. `references/lessons.md` §23.8.

⚠️ **2026-08-18, a SECOND idea tried and falsified — gap regularity.** "Are the change lines regularly spaced?" reads 25/25 on the labelled corpus at a 0.55 threshold and fires on **119 of 123 vector emoji (96.7%)**. It is inverted, not weak: the six antialiased corpus assets score 0.848-0.984 against pixel art's 0.573-1.000, because a flat fill's long uniform runs give cleaner repeated gaps than a dithered pixel grid does. **Four ideas have now been scored and failed — modal run length, integer-lattice fit, duplicate-line density, gap regularity — and all four ask the same question (where does the image change along a scan line). Treat that family as exhausted; the next attempt should measure the palette's structure or the alpha ramp's shape instead.** `references/lessons.md` §23.9.

✅ **2026-08-18 (v5.5.0) — the fifth idea WORKED, and it was not the kind §23.9 predicted.** `plateau_cliff_ratio`: of the STRONG colour steps (40+ on a channel — real edges, not ramp increments), what share sit between two flat runs of 2px or more. Upscaled pixel art transitions block-to-block; a 1px antialiasing ramp cannot be a cliff, because the ramp pixel is a plateau of length 1. Scored against BOTH populations — 31 labelled assets and 127 antialiased negatives (122 emoji + 5 corpus originals): **22/25 pixel art, 0/133 false positives**, lowest true positive 0.356 against highest negative 0.186. `references/lessons.md` §28.

⚠️ **§23.9's advice ("measure the palette's structure or the alpha ramp") was NOT what worked, and the record should not imply it was.** The successful measure is in the same family as the four dead ones — it asks where the image changes along a scan line. The difference is that the four asked it *unconditionally*, so a flat vector fill scored like a pixel grid; this one only counts uniformity AT AN EDGE, where the decision actually lives. Likely the other four would also survive that localisation. **Carry forward "localise to where the decision lives", not "prefer palette measures".** §28.1

**What remains: 3 assets, one mechanism.** `Pixel Saber` 0.001 · `pandapanda…` 0.103 · `DFB2A5D7` 0.135 — all pixel art whose blocks were softened by re-encoding (inside one panda block, `184,159,159` sits next to `185,161,161`; DFB2A5D7's blocks are separated by 1px grey seams, which is literally a 1px ramp). ⚠️ **The obvious repair — a tolerance on the plateau test — was implemented and scored and FAILS BOTH WAYS: it rescues none of the three (panda 0.103 → 0.144, DFB2A5D7 0.135 → 0.167) and it manufactures a false positive (`GIF Selections`, labelled antialiased, 0.078 → 0.497 at tol 4, → 0.864 at tol 8), because loosening "flat" lets a gradient count as a block. Do not re-attempt it.** §28.3

**Next action:** anything further has to separate "a block softened by re-encoding" from "a genuine 1px antialiasing ramp", which is the same pixels by construction. That is plausibly not decidable from a single frame — a cross-frame check (does the seam colour move with the block, or stay pinned to the edge?) is the one angle not yet tried. Score it against both populations before believing it.

**The scoring harness is TRACKED, at `scripts/harness/`** *(moved there 2026-08-18 — the `local/pixelart-probe/` scripts this line used to name are superseded scratch and should not be reused).* `populations.py` is the population registry and owns the corpus list; `labels/<population>.json` holds all 714 hand-written labels, which are the denominator of every recall and specificity figure this project quotes; `run_populations.py` scores every asset through the real `analyze()`; `render_baseline.py` renders through the `--auto` CLI and fingerprints alpha planes, native and resized; `candidates.py` holds candidate measures under evaluation **including the seven falsified ones**. A new candidate is one function plus a re-run, not a rebuild.

**Still true, and still the gate on any candidate:** any discriminator must be scored against BOTH sets — the 31 labelled assets AND the 145 antialiased emoji (`local/Diors-builds Emojis/{Arrows,Database emojis,codm emojis,interface emojis,more,untitled folder}/`) — before it is believed, because the population that falsifies a pixel-art measure is the antialiased one and it is barely represented in the labelled corpus. A measure that survives both is worth shipping; one scored only on the corpus is not.

**Two structural ideas were tried and scored before one was believed** (§23.4): modal run length is DEAD (the vector corpus scores k=19-20, so a `k>=4` rule flags all six vector icons — §18's catastrophe reintroduced); an integer-lattice fit is sound but narrow (0 false positives, 11/25, because a 500x500 export of a 32px sprite is a 15.625x upscale on no integer grid).

⚠️ **Do not ship a bare blend-ratio threshold.** It looks tempting — pixel art spans 0.000–1.074 and the antialiased corpus 1.530–2.529, so ~1.3 would score 13 of 14 — but the sole overlap is the jar (antialiased, 0.999) against DFB2A5D7 (pixel art, 1.074), and a threshold justified by a 0.075 gap between two assets is a margin of DEGREE, the exact trap §18 set out to escape and then fell into.

✅ **CLOSED 2026-08-19 — superseded by a corpus-wide measurement.** This item counted misses in the 25-asset `labelled` population, which is now the smallest of eight. Across all labelled populations the current figures are **recall 0.9618, specificity 0.8510**; on the independent populations (excluding the derived `small_aa_quantized`) **recall 0.9644, specificity 0.9681**. The remaining misses are named and mechanised in `references/lessons.md` §32.3 and §32.6 rather than counted: hard-alpha cutouts where the band rules correctly abstain, and pixel art whose plateaus a lossy encode filled in (`star2.webp`, 1,502 colours and a 0.000 cliff ratio, against siblings of the same artwork at 239 and 253). Tracking "3 of 25" against a 736-asset labelled corpus is a stale denominator, not a live defect.

---

### `[P2 · M · Opus5-High]` Two sprite packs are at 24% and 25% — pooled recall is now 94.1% *(filed 2026-08-18; retitled 2026-08-18 when the pooled figure went 86.4% → 94.1% and the per-cell direction was falsified)*

⚠️ **PARTIALLY FIXED 2026-08-18 (v5.5.0) — and this item's own recommended direction was FALSIFIED, so do not retry it.** Sprite recall is now **0.941** pooled: Tiny Swords 0.941 → **1.000**, Free City 0.667 → **1.000**, EVil Wizard and Samurai still 1.000. **Tiny RPG (34 files) at 0.235 and CatPackFree (4) at 0.250 are what remain**, and they are the whole reason this item stays open. Corpus-wide, both v5.5.0 hardness changes together: recall 0.870 → **0.939**, specificity 0.953 → **0.987** (`references/lessons.md` §29.5).

**The "score the cliff ratio per CELL" direction below does not work, and the measurement is worth keeping so nobody spends a session on it.** Confining the ratio to opaque pixels — the same reasoning, tested directly — made every pack with misses WORSE: Tiny RPG 0.157 → **0.063**, Samurai 0.413 → 0.221, EVil Wizard 0.481 → 0.318. The alpha boundary was *contributing* cliffs, because a hard cutout's silhouette is the most reliable plateau-to-plateau edge in the image. And the premise underneath it was wrong too: these misses are not sample-starved. Tiny Swords' 24 old misses were (cliff 0.742 at n=290, under the 500 floor), but Tiny RPG's have n=700-2,500 and ratios of 0.07-0.27 — **the ratio itself is low, because the art is drawn 1:1 and no edge has a 2px plateau for a cliff to sit between.** §29.2

**What DID work, and what it leaves:** a sixth discriminator that never looks at an edge — `composited_color_count`, distinct colours in the composited frame, hard-edged at or under 16. It is the sole rule carrying 51 detections. **The residual is now precisely characterised:** the Tiny RPG and CatPackFree misses carry **20-64 colours**, above the 16 floor and below the 0.30 cliff threshold, in the one overlap region §29.4 shows colour count cannot separate — a genuinely antialiased 93x96 sticker sits at 26 colours, so the floor cannot rise to 32 without buying a false positive on exactly the destructive side. ⚠️ **2026-08-18 — THREE candidate seventh measures were scored against all 719 assets and all three are dead. Do not re-derive them.** (1) *colours per strong colour step* — the misses run 0.010–0.253 against antialiased negatives starting at 0.006, complete overlap. (2) *ramp fraction* — inverted: the misses score 0.05–0.10 and the vector icons 0.000–0.010, because these sprites carry real hand-drawn antialiasing. (3) *`min_share`*, the smallest share of the artwork any single composited colour carries — **it scored recall 0.9389 → 0.9722 with ZERO new false positives across 148 antialiased assets, and it is a size proxy.** `art_px <= 2000`, a rule with no colour statistic in it, scores 0.9833; and inside the size-matched band of 400–3,000 art pixels the corpus holds 99 pixel-art assets and **exactly ONE** antialiased asset, so no population existed that could tell the two apart.

⚠️ **The missing population was then CONSTRUCTED, and it killed the measure.** Real antialiased emoji downscaled to 64px and quantized to the palette a small icon actually ships with: at 32 colours **13 of 118 (11.0%)** clear the 0.002 threshold, at 16 colours **36 of 118 (30.5%)**. The Orc/Soldier sprites sit at 0.0024–0.0071 with 20–32 colours, inside that range. (The plain LANCZOS downscale WITHOUT quantization passes 0 of 236 and is **not** a valid falsifier — at 64px it carries 128–1,371 colours over 1,375–1,900 art pixels, a resampling artefact no authored icon has.)

**So the residual is a CORPUS gap at least as much as a measure gap, and that is the actionable half.** This project owns essentially no antialiased art at sprite scale, so any measure that helps these two packs is untestable for false positives. **Do:** acquire ~20 real 32–128px antialiased icons before attempting a seventh measure at all; without them the next candidate will score perfectly for the same reason this one did. Do NOT raise the floor. `references/lessons.md` §29.12

**What the misses actually cost, now measured rather than assumed:** nothing until a resize is in play, and then several hundred manufactured partial-alpha pixels per sprite (§29.10). Original note follows.

**Added 2026-08-18, from the first registry-wide run over all five populations (688 scoreable assets through `analyze()`).** The pooled sprite recall of **426/493 = 86.4%** is almost entirely one pack: Tiny Swords is 409 of the 493 and scores 0.941. The per-pack breakdown the new `LABELS.json` warned about:

| pack | n | recall |
|---|---|---|
| EVil Wizard 2 | 8 | 1.000 |
| FREE_Samurai | 5 | 1.000 |
| Tiny Swords | 409 | 0.941 |
| Free City Enemies | 33 | 0.667 |
| CatPackFree | 4 | **0.250** |
| Tiny RPG Character Asset Pack | 34 | **0.147** |

**So "sprite detection went 54/524 → 427/524" was a statement about Tiny Swords.** Reporting per-pack is what surfaced this, and it is the whole reason the lopsidedness warning went into that file — a population that is 78% one pack cannot be summarised by one number.

**The mechanism, measured over the 67 misses against the 426 hits (medians):** `plateau_cliff_ratio` **0.215 vs 0.823**, `plateau_cliff_samples` **885 vs 7,021**, `ratio_max_across_frames` **0.246 vs 3.266**. `change_line_density` is 1.000 in BOTH groups, so it contributes nothing here. The misses are simply SMALL: a 100x100 or 32x32 sprite has few strong colour steps, so the cliff ratio is computed from a thin sample (some as low as n=17, well under the 500-sample floor that makes it non-dispositive) and lands under the 0.30 threshold. Every miss has `hard_edged_suppressed_notes: []`, so no suppression rule is involved — this is the measures themselves running out of evidence, not a rule mis-firing.

**Do:** the promising direction is that these are *sprite sheets* — many small cells on one canvas. Scoring the cliff ratio per CELL (or per connected art component) rather than per canvas would give each cell the sample count it needs, and cell boundaries are findable from the transparent gutters. ⚠️ Score any change across all five populations, per-pack, before believing it: the 122 vector emoji currently give 3 false positives and the labelled set 0, and a threshold loosened to catch a 32x32 sprite is exactly the kind of change that has cost this project a regression twice. `references/lessons.md` §28.15

✅ **CLOSED 2026-08-19 — one pack fixed at the mechanism, the other is 4 assets and stays visible below.** `Tiny RPG Character Asset Pack` goes **0.235 → 0.941 (32/34)** via the seventh discriminator: a hard-alpha cutout whose transition band is REAL but narrow (0 < ratio < 0.20) is now read as pixel art, where before the vacuity gate silenced the band rules on every cutout regardless of whether the band was empty.

**Why the existing measures could never have reached this pack.** `plateau_cliff_ratio` requires flat runs of 2px or more. Tiny Swords sits at 197/197 because it is UPSCALED pixel art; the Orc and Soldier sheets are 100×100 at 1:1, so every art pixel is one screen pixel and there are no multi-pixel plateaus by construction — cliff ratios 0.07–0.28 against a 0.30 floor. A measure that needs a scale factor is blind to art drawn at native resolution.

Independent-population effect: recall **0.8932 → 0.9644**, specificity 0.9787 → 0.9681. ⚠️ `CatPackFree` remains at **0.250 (1/4)** — four assets, and left open as its own line rather than folded into a closed item. `references/lessons.md` §32.7.

---

### `[P2 · S · Opus5-High]` The 16-colour flat-palette floor rests on a sample of ONE, and this session made that worse *(filed 2026-08-18)*

`FLAT_PALETTE_MAX_COLORS = 16` is argued from the pixel-art convention (EGA/PICO-8) rather than swept, and its safety rests on the measured negative frontier: over 146 labelled antialiased assets the LOWEST composited count is 26. **That is a margin resting on one asset**, and the class that could land under the floor — a lossily-quantized antialiased image — is now measured and it is not rare. Real antialiased emoji downscaled to 64px and quantized to 16 colours put **36 of 118 (30.5%)** into palette territory the floor cannot distinguish, and re-analysing this tool's own GIF output already flips 8.3% of antialiased assets by a different rule.

✅ **The corpus now exists, and the floor DOES fire on it — measured 2026-08-19.** `small_aa` (150 real icons and custom emoji at 32–128px) and `small_aa_quantized` (117 of those re-exported as GIF at 16–64 colours) are registered populations. Scoring the current code against them: **62 disagreements, ~40 of which are the colour-count rule firing on assets holding 2–16 colours** — `small_aa_quantized` specificity reads 0.615.

⚠️ **Do NOT treat 0.615 as a specificity collapse yet, and do NOT move the threshold to improve it.** Those 267 labels are PROVISIONAL: all were labelled `antialiased`, but only 8 were inspected by eye before the blanket label went on. Inspecting the 17 disagreements in `small_aa` showed the split is real BOTH ways — Mareep, CryPepe, Pepecoin and the flame emoji are genuinely antialiased and genuinely misclassified, while BlackVerified, FlyingHearts, HOT and PrettyGay are flat 2–4 colour vector shapes with no ramps at all, where `hard-edged` is arguably the correct verdict and `measure_composited_color_count`'s own docstring says so.

**Do:** inspect the 62 disputed assets individually and fix the labels first — that is the load-bearing set, not all 267. THEN measure where the floor sits. Do NOT move the threshold before that measurement exists — the failure direction is destructive. Note the argued mitigation still stands and should be re-tested rather than assumed: "art flat enough to come in under 16 colours has no ramps to protect and wants `--pixel-art`'s treatment anyway." `references/lessons.md` §29.4, §29.12

✅ **CLOSED 2026-08-19 — tested against real negatives for the first time, and the floor STAYS AT 16.** The corpus now has 134 eye-verified antialiased assets at small sizes, so the measurement this item asked for could finally be run. Over all labelled populations, lowering the floor 16 → 12 looks like an easy win: recall 0.8912 → 0.8794 (−4 detections) for specificity 0.8763 → **0.9268** (−20 false positives), in a project whose stated asymmetry makes a false positive the destructive direction.

⚠️ **It is an artefact, and one `Counter` over the changed assets says so: ALL 20 of the removed false positives are in `small_aa_quantized`** — every one a DERIVED asset, an antialiased original re-exported at 16–64 colours. "Lowering the floor improves specificity" therefore means "lowering the floor stops detecting the quantization I applied myself". **On the independent populations alone, specificity is 0.9787 at floor 16, 14, 12 AND 10 — it does not move at all.** No threshold change removes a single independent false positive; the floor's whole independent cost is 6, and every candidate is pure recall loss (the three named casualties are `Free City Enemies Pixel Art` 1/Hurt, 3/Hurt, 3/Hurt2 at cc 13–15). The measurement that would have justified the change was run and came out the other way. `references/lessons.md` §32.5.

---

### `[P2 · M · Opus5-High]` `analyze()` keys on the COMPOSITE, `process()` still keys on the raw plane *(filed 2026-08-19 by the xhigh code review)*

⚠️ **PARTIALLY ADDRESSED 2026-08-19 — the alpha half is fixed, the KEYING half is not.** Investigating this item found a second, larger consequence of the same discarded plane: `process()`'s bare `convert('RGB')` meant the source's partial alpha never reached the OUTPUT either, so **218 of 249 corpus sources carrying partial alpha came out with under 10% of it left** (`love_emoji_128.webp`: 913 partial-alpha px in, 0 out, 5,509 opaque becoming 6,422). Fixed with `alpha = np.minimum(alpha, source_alpha_plane)` — a minimum, never an assignment, so the colour path may still remove but may not invent opacity. 207 of 249 now keep 90%+ of their partial alpha, and the survivors are dominated by `--pixel-art`/`--no-feather`, which is binary by design. Fallout fixed in the same pass: the erosion auto-calibrator read the restored ramp as fringe and picked erosion 3 over 1, shaving 6,844 px, so its skip-guard now keys on `_sa_engaged or _src_has_partial_alpha`. `references/lessons.md` §31.

**What REMAINS, and it is this item's original subject:** the removal decision is still made from `rgb_frames_raw`, so the flags are chosen from one image and `color_mask` acts on another — measured at 41 of 338 partial-alpha sources disagreeing, worst 18.41% of a frame. The fix shape is unchanged: `compute_alpha_mask(..., rgb_key=None)` defaulting to `rgb_out`, with a composited keying plane built beside `rgb_frames_raw`. ⚠️ Do NOT composite `rgb_frames_raw` itself — the output must carry original art colours, and the composite masks MORE (3,017 extra pixels on `love_emoji_128.webp`, exactly the half-transparent artwork `--recover-fade-alpha` exists to reconstruct).

`analyze()` now composites every frame carrying partial alpha, so `--recommend` chooses flags from the image a viewer sees. `process()` still builds `rgb_frames_raw` with a bare `convert('RGB')`, so the removal those flags drive acts on full-strength art colour. **The recommendation and the removal read different images.**

**Measured, so this is not a consistency argument in the abstract.** `color_mask` at the real removal reach (tolerance x4) over all 338 partial-alpha sources: **41 assets disagree**, 38,063 pixels total. Worst cases: `love_emoji_128.webp` differs on **18.41% of the frame** (raw masks 7,356 px, composite masks 10,373), then four `interface emojis` icons around 0.9%.

⚠️ **The obvious fix is DESTRUCTIVE and must not be applied as stated.** The composite masks MORE, and the extra pixels are half-transparent ones whose blended colour reads as background — which on a faded asset is exactly the artwork `--recover-fade-alpha` exists to reconstruct. Compositing `rgb_frames_raw` would also bake the background into the OUTPUT colours, which is wrong independently.

**Do:** thread a second plane through `compute_alpha_mask` — composite for the mask DECISION, raw for the output pixels — and measure over the 338 partial-alpha sources with the fade assets watched specifically, before believing it. `references/lessons.md` §28.5 is the argument for why the decision should read the composite; this item is the half that was left.

✅ **CLOSED 2026-08-19 — both halves now landed.** `compute_alpha_mask` and `estimate_alpha_and_defringe` take `rgb_key`, defaulting to `rgb` so every existing caller is unchanged, and `process()` builds `rgb_frames_key` beside `rgb_frames_raw` — composited only for frames that actually carry partial alpha, so an opaque or 1-bit source shares the raw array and pays nothing. **Every colour COMPARISON reads the key plane; every pixel returned still comes from the raw plane**, which is what keeps the background out of the output.

**Measured over the 249-asset reachable population: 47 assets change, and the opaque pixel count is IDENTICAL on every one of them.** What moves is partial alpha — 5,166 pixels removed. That number alone is not a verdict in either direction, so the source alpha of every removed pixel was read: **65.0% are under 2% opaque, 84% under 9%, 99.3% under 25%, and 0.0% are above half opacity.** The corrected key plane removes near-invisible pixels whose composited appearance genuinely is the background, and touches no artwork.

⚠️ **The 107-asset `standard` render set reports 214 vs 214 records, 0 changed — and that is a REGRESSION control, not evidence about this change.** That set is overwhelmingly opaque sources, which `_src_has_partial_alpha` makes this a literal no-op on; the acceptance measurement is the reachable-population run above. Release gate 8's own warning, applied deliberately rather than tripped over. `references/lessons.md` §31.2.

---

### `[P3 · S · Sonnet5-High]` The outline leak gate only tests the LARGEST background component *(downgraded P2→P3 2026-08-18: measured, not exercised)*

**Measured before building anything, per the standing rule.** For each of the 7 assets whose recommendation changed, over the first 12 frames: how much border-touching background is NOT in the largest component (i.e. invisible to the gate), and how much of THAT do the recommended outline colours actually protect? Two assets have substantial blind-spot area — `ezgif` 2,604,400 px and `pandapanda` 286,128 px — and the other five have none. **In every case the outline colours protect 0 px of it.** The falsifier could have failed and did not, so the exposure is real in principle and unexercised in practice. Left open with the fix shape recorded below, but not worth building speculatively.

**Added 2026-08-18**, from the sequential-thinking audit of v5.4.0. Both the degenerate-candidate reject and the new partial-enclosure search decide "does this colour swallow real background?" by intersecting its filled shape with `largest_bg_component_mask`. Background that is genuinely removable but is NOT the largest component — a pocket enclosed between two limbs, a region the foreground has cut off — passes the gate and gets protected. The limitation is inherited from `detect_outline_background_leak` and predates this release, but v5.4.0 invokes it far more often: up to six recommended outline colours on one asset where there was one. **Do:** test against the union of ALL border-touching background components, not just the largest — the same border-label technique `analyze()` already uses to build `enclosed_by_frame`, so the machinery exists. Measure against the 31-asset corpus before believing it; the reason the largest-component version exists is that it is cheap. `references/lessons.md` §26.6.

✅ **CLOSED 2026-08-19 — changed on structural grounds, with a measured effect of ZERO, and the probe that suggested otherwise was wrong.** `detect_outline_background_leak` now tests the union of every bg-coloured component that touches the canvas border, instead of `largest_bg_component_mask`. The category error is real and demonstrable: on `DMZRecon_Gamemode_Icon_CoDM (1).webp` the largest bg-coloured component (6,834 px of 143) **does not touch the border at all** — it is an interior black region of the artwork, so the old gate could reject a good outline colour over something that is not background.

⚠️ **What did NOT survive contact with the product.** A standalone probe reported "117 outline-colour tests, 3 differ, 2 flip the verdict" and named two assets flipping in opposite directions. That probe reconstructed the background colour, the tolerance and the frame sampling itself. Run through `analyze()` PRE and POST over 153 assets, **exactly one changes and it changes nothing**: `gaming.jpeg`'s `leaked_pixel_count` 1 → 6, `over_protects_background` False both ways, identical recommended colours. A PRE/POST render of the supposedly-flipped assets is byte-identical on the alpha plane. [[feedback_validate_through_the_product_entry_point]], violated while writing a lesson about measuring the right thing. Kept because the old question was the wrong one, not because it fixed anything here. `references/lessons.md` §30.3.

---

### `[P3 · S · Sonnet5-High]` Two predicates about one property are computed on different frame sets *(filed 2026-08-18)*

`source_background_already_transparent` is computed from **frame 0 only**, while `source_alpha_levels` is a **max over sampled frames**, and `_band_measures_are_vacuous` is the conjunction of the two — so the vacuous-band gate mixes a frame-0 property with an all-frames one. `decide_source_alpha_policy` decides the same underlying property per ANIMATION, so the file now holds two answers to "is this source's transparency its background" derived from different evidence.

**Left alone deliberately, and the reason is the only thing making it P3:** both directions of the asymmetry err toward abstention — fewer hard-edged verdicts, i.e. away from the destructive direction. **Do:** make the two agree on a frame set, or state in one place which one is authoritative and why. Cheap; the risk is that "harmless today" stops being true the next time a rule reads either predicate.

✅ **CLOSED 2026-08-19 — `_src_bg_transparent` is now decided over the SAMPLED FRAMES**, matching `decide_source_alpha_policy`'s "engaged if ANY frame's transparency reads as its background" and the frame set `source_alpha_levels` already used. The reason string now carries the tally (`… (holds on 1 of 1 sampled frame(s))`), so the evidence says which frames spoke.

⚠️ **Zero of 797 corpus assets move — and that is exactly why the change needed a constructed falsifier rather than a corpus run.** A no-op across the corpus is indistinguishable from an edit that never executed. So a two-frame fixture was built where the background colour is identical in both frames (white corners either way, so `detect_bg_color` cannot drift) and the ONLY difference is condition 1 of `source_transparency_is_the_background`: frame 0's transparency is an interior hole, frame 1's reaches the canvas border. Per-frame the predicate reads `[False, True]`; `analyze()` now returns **True**, where the old frame-0-only rule returned False. The change is live, behaviour-changing on the case it was written for, and harmless on everything real. The harness now captures `source_background_transparent_reason` so a future run can see this without a bespoke probe.

---

### `[P3 · M · Sonnet5-High]` Re-test gifsicle's colour dither on a GRADIENT-heavy corpus — **UNBLOCKED 2026-08-19** *(opened 2026-08-17, tagged 2026-08-18)*
The `medium`/`heavy` tiers use `gifsicle --dither=floyd-steinberg` for COLOUR quantization. Spot- measured on `love.gif` at `medium` settings, Floyd-Steinberg came out **worst on both** axes that matter for animation:

✅ **The blocker is gone.** `local/corpus gradient beds/` holds 23 assets carrying a real smooth alpha ramp (1,990–12,413 partial-alpha px each), built with Dior's Builds' actual nameplate-bed curve and palette — Harkirat's suggestion, because gradient-heavy source material is genuinely hard to find in the wild. Registered as the `gradient_beds` population with `default_label='ambiguous'`, so it is excluded from every recall and specificity figure: its job is the encoder question, not classification. **Do:** run the dither comparison across it and record the result. `references/lessons.md` §6 has the original gifski/pngquant evaluation this extends.

| dither | KiB | mean colour err | frame-to-frame instability in static regions |
|---|---|---|---|
| floyd-steinberg (current default) | 1649.3 | 0.039 | 1.32% |
| atkinson | 1655.7 | 0.028 | 1.12% |
| ordered / o8 | 1658.4 | **0.026** | **0.97%** |
| none | 1654.1 | 0.026 | 1.01% |

i.e. it buys ~0.6% file size for the worst colour fidelity AND the most temporal crawl — the same error-diffusion instability that disqualified it for ALPHA (measured separately: Floyd-Steinberg changed 8.1% of pixels in a region that was byte-identical between frames; both Bayer sizes changed 0). Crawl also fights GIF inter-frame compression, so the size win may not even survive on other content.

**NOT acted on, deliberately.** `love.gif` is flat 6-colour vector art, so a 200-colour palette reproduces it almost exactly and dithering barely engages — all five options sit within 0.7% size and 0.013 colour error, too close to call. The tiers exist precisely for content where quantization DOES bite, and that content is what should decide this.

**What a future session should do:** assemble a corpus with real gradients/soft shading (not the flat vector icons this skill is usually pointed at), run the same three measurements (bytes, colour error against the pre-quantization frames, and static-region frame-to-frame instability) across `floyd-steinberg` / `atkinson` / `o8` / `ordered` / none at both `medium` and `heavy`, and change the tier default only if a clear winner emerges on gradient content without regressing flat art.

⚠️ **Jarvis, Sierra and Stucki are NOT options here** — verified by enumeration against the installed gifsicle 1.6.0: it implements only `floyd-steinberg` and `atkinson` as error-diffusion kernels (plus `ordered`/`o3`/`o4`/`o8`/`halftone`/`squarehalftone`/`diagonal`/`ro64`). Using them would mean doing colour reduction outside gifsicle entirely, which is a much larger change than a flag and should be scoped separately if the corpus test suggests error diffusion is worth improving at all.

---

✅ **CLOSED 2026-08-19 — Floyd-Steinberg REMOVED from both tiers.** Measured across the 23 `gradient_beds` assets and, as a falsifier, 5 flat animated vector sources, at `medium` and `heavy`:

| axis | gradient corpus | flat vector art (falsifier) |
|---|---|---|
| file size vs no dither | **+11% to +24% larger** | **+4% to +10% larger** |
| mean colour error | **+8% to +12% worse** | **+13% to +14% worse** |
| static-region frame-to-frame instability | **2.80% / 3.56%** vs 1.08% / 0.66% | ~0.01% either way |
| banding (plateau run) | **~6% better** — its one real win | — |

The falsifier did not save the default: dropping the dither improves flat art too, so this is not a trade between content types. **The decisive axis is temporal instability, and the precedent was already in this repo** — error diffusion is refused for ALPHA here because it changed 8.1% of pixels in a region byte-identical between frames; the same crawl appears in COLOUR quantization at 2.6–5x the no-dither rate, and it is also where the size regression comes from (a dithered static region can no longer be coded as unchanged).

⚠️ **The banding axis was measured, not assumed away, and the first attempt measured the ARTWORK.** Counting every luma change gave a mean "step height" of 129/765 — an icon boundary, not a quantization contour, and arithmetically impossible from a 128-colour palette. Restricted to steps ≤12/765 with both bounding steps small, the unquantized reference moved to 3.72 px / 5.22 and the comparison became real. `--auto` output is unchanged (`love.gif` still `2fd526b6fb3b191c`); no tier applies without `--compress`. Full write-up: `references/lessons.md` §30.

---

### `[P3 · S · Sonnet5-High]` The 2px cleanup band's BENEFIT is still unproven *(filed 2026-08-18)*

The source-alpha scope fix vetoes the 2px cleanup ring whenever the background colour also occurs in the artwork away from the boundary, and that veto is measured and correct: across 76 alpha-carrying assets it fires on exactly the 25 that were losing art and takes all 25 to 100% survival. **What was never measured is the band's upside.** On those same 76 assets it removes nothing the unrestricted path would have left, so its fringe-cleanup value is entirely unexercised — only its RISK was measured and neutralised. **Do:** find or construct a source whose own alpha leaves a real fringe the band would clean, or delete the band and its `--source-alpha-band` flag as unearned complexity. Quote the veto, never the band. `references/lessons.md` §28.14

✅ **CLOSED 2026-08-19 — KEPT, and its benefit is measured for the first time.** The probe this item prescribed overstated the candidate set six-fold by measuring at tolerance 60 while `build_source_alpha_scope` actually runs at 15: 289 apparent hits, **47 real ones**. All 47 were then rendered through the real CLI at `--source-alpha-band 0` and `2` and their alpha planes diffed. **20 of the 47 change the render at all. Band 2 removes 693 px that band 0 keeps, and every one of the 693 is background-coloured. Band 2 keeps 0 px that band 0 removed.** So the ring cleans a real matte fringe, costs no artwork in either direction, and "delete it as unearned" would have been the wrong call — the earlier "removes nothing" reading came from a 76-asset sample that happened to exclude the small antialiased icons where the fringe survives. Largest single case 143 px (`small_aa/emoji_8.png`); most are 4–64 px.

---

### `[P3 · XS · Sonnet5-Medium]` `--source-alpha-band` is not plumbed into batch manifests *(filed 2026-08-18)*

The flag works on a single-file run and is absent from the batch manifest schema, so a batch job cannot tune the ring per asset. Small and mechanical; the same shape as any other per-asset flag already in the manifest. ⚠️ Sequenced behind the item above — if the band turns out to be unearned, this becomes moot rather than done.

✅ **CLOSED 2026-08-19 — the claim was FALSE, and it was filed from reading rather than running.** There is no "batch manifest schema" for the flag to be absent from: `run_batch` applies any key for which `hasattr(job_args, key)` holds, so `"source_alpha_band": 0` has always worked per entry. Verified with a three-entry manifest against `small_aa/emoji_8.png` — the band-0 and band-2 outputs differ by exactly the 143 px measured on the same asset from the command line, and a deliberately bogus key produced `WARNING: unknown manifest key 'no_such_flag' ... ignoring` and still succeeded. **The lesson is the item, not the flag:** "absent from the schema" was inferred from a docstring example that lists three keys, on a code path that enumerates none.

---

### `[P3 · S · Sonnet5-Medium]` `--translucent-region` is verified on one asset, one shape kind, one alpha

**Added 2026-08-18**, same audit. The flag shipped verified end to end on `2d4a092f…` with a single `rect:` spec at `--translucent-alpha 0.3`, checked over a dark composite. Untested: the `circle:` form, several `;`-joined specs, alpha at the extremes (0.0 and 1.0), and interaction with `--crop`/`--resize-max-dim` (the coordinates are source-relative and the flag is applied before both — now documented in `parse_protect_regions` and `references/flag-reference.md`, but documented is not tested). **Do:** one render per case with a pixel assertion. Small, and it closes the gap between "the mechanism works" and "the flag works".

✅ **CLOSED 2026-08-19 — all six untested cases now assert on real pixels, and one real defect fell out.** On a 640x640 35-frame source, with the target colour chosen from the KEPT art so no case could pass vacuously: `circle:` takes 9,477 px, all inside the circle · two `;`-joined specs take 36,045 px = 26,568 (rect) + 9,477 (circle) with **none outside either region** · `--translucent-alpha 0.0` drives 26,568 px to alpha 0, all inside the rect · `--translucent-alpha 1.0` is byte-identical to a no-flag render · a `.gif` output is refused with the 1-bit-alpha message · `--translucent-alpha 1.5` is refused by the range guard. Under `--resize-max-dim 160`, **100.0% of the total alpha difference lands inside the scaled rectangle** — the source-relative coordinate rule was documented but never tested, and now it is. ⚠️ **The defect:** omitting `--translucent-color` defaults the target to the BACKGROUND colour, which by construction is absent from the kept art, so the whole feature silently no-ops on a successful-looking run. It now warns, naming both causes (source coordinates, and the colour default). Red-green verified: fires at 0 px, silent at 2,648 px, and stays silent at `--translucent-alpha 1.0` where a no-op is the defined behaviour.

---

### `[P3 · XS · Sonnet5-Medium]` APNG playback is unverified in a real browser — an independent DECODER now confirms the frames *(narrowed 2026-08-18)*

**Added 2026-08-18.** v5.4.0's APNG output is confirmed for frame count, distinct alpha values, exact duration read-back, static-source handling and the byte-cap cascade — all through Pillow, the same library that wrote it. That is a round-trip, not an acceptance test. `references/lessons.md` §16 already records the general form of this for AVIF: **acceptance is not playback**. ✅ **Half of this is now closed, 2026-08-18.** `ffmpeg` — a decoder that did not write the file — reads the APNG as **19 frames, 18 distinct**, exactly matching the same source rendered to GIF and decoded the same way. So the round-trip objection is answered: the animation is really in the file, not just in Pillow's opinion of it.

⚠️ **The browser half is NOT closed, and the attempt to close it produced a vacuous result that a control caught.** The in-app preview pane sampled the APNG over 1.2s and reported no frame advance — which looks like a damning defect and is not one: **the same test on a plain animated GIF also reported static**, so the pane renders snapshots and animates nothing. Without that control this session would have filed a false product defect. **Do:** open one in a REAL browser (or hand one to Harkirat), and keep WebP as the fallback until someone has actually watched it move. `references/lessons.md` §29.14

✅ **CLOSED 2026-08-19 — a real browser engine animates it, and the control passed this time.** Chrome 151's own `ImageDecoder` (Blink, the shipping engine, driven headless) reports the rendered APNG as `supported: true`, `animated: true`, **12 frames, 12 pixel-distinct**, against a control GIF at **35 frames, 35 distinct** — so the harness demonstrably separates animated from static, which is exactly what the two failed attempts could not show. `ffmpeg`, a decoder that wrote neither file, independently counts 12 and 35 on the same pair. ⚠️ **Two more viewers reported "static" and both failed their control**: the in-app preview pane (which serves pages as `data:` snapshots) and headless Chrome's `--screenshot --virtual-time-budget`, which does not advance `<img>` animation. §29.14 reproduced twice in one session — **the control is what stood between this and a false P1 filed against a shipped output format, three times now.** Consequence for the docs: SKILL.md's "OUTPUT is GIF, WebP or AVIF only ... APNG is a real gap" line was stale since v5.4.0 and contradicted its own format table; fixed in the same pass.

---

### ~~`[P3 · XS · Sonnet5-Medium]` `audit_docs.py`'s heading/body drift gate matches a bare keyword anywhere in a body~~ — **CLOSED 2026-08-18**

Filed and fixed the same day, and the fix found a worse defect than the one filed. The gate now tests for a closure MARKER rather than the word: the keyword must sit at the start of a bold span or a line, separated from it by nothing but emoji, punctuation and ALL-CAPS qualifiers — which is how every one of the 28 real markers in these two files is written, and never how prose uses them.

**The worse defect: there was no word boundary, so `ENCLOSED` matched `CLOSED`.** In a repo whose main feature is outline ENCLOSURE and whose house style emphasises in caps, that is a spurious failure waiting on the next open item that mentions it. ⚠️ And the `\b` had to be applied to the bare keywords ONLY — `✅` is not a word character, so a boundary in front of the tick branch never matches after a space or newline, i.e. every real occurrence. The falsifier suite caught that within a minute of writing it.

**The suite now runs on EVERY invocation of `audit_docs.py`, not once.** Eleven cases, each one that actually happened or actually would have, including the two prose patterns that tripped the old gate while this very item was being written. Proven non-vacuous end to end: injecting a real closure marker into an open item still exits 1. A check that proves itself every run is a control; a check that was proven once is a memory.

**Original item, verbatim:**

#### `[P3 · XS · Sonnet5-Medium]` `audit_docs.py`'s heading/body drift gate matches a bare keyword anywhere in a body *(filed 2026-08-18)*

The gate fails an OPEN item whose body contains any of its three closure keywords anywhere at all, which is right for a closure marker and wrong for ordinary prose — it fired on this very file for a sentence that used the past-tense-release keyword as an ADJECTIVE. ⚠️ **Writing this item TRIPPED the gate**, on the sentence above that quoted the keywords — a defect that reproduces itself in its own bug report. **Do NOT loosen it casually**: it has caught real drift, and a gate that stops catching drift is worse than a gate that occasionally makes you reword. **Do:** require the keyword to appear as a MARKER — bolded, or at the start of a line — which is how every genuine closure in both files is written, and re-run the gate against the known drift case to prove it still fails.

---

### ~~`[P2 · S · Sonnet5-High]` The render gate never RESIZES, so `--pixel-art`'s main destructive lever is untested end to end~~ — **CLOSED 2026-08-18 (v5.5.0)**

`render_baseline.py` now renders every asset a SECOND time through `--resize-max-dim` at half its larger side and fingerprints that alpha plane too, under a key suffixed ` [resize]`; sources under 64px are skipped and say so. `--no-resize-pass` turns it off and documents what that blinds.

**The measurement that came out of building it is the useful part, and it settles a question this item could only pose.** 47 assets rendered both ways at half size — `--auto` against `--auto --pixel-art`: the 29 undetected sprites gain **388–1,333 partial-alpha pixels** under `--auto` where a correct verdict produces **zero** (4.5–85% of pixels differ); the 10 correctly-detected sprites differ by **0.0%**, which is the control that makes the rest attributable; and forcing `--pixel-art` onto antialiased art destroys up to **67,552** real partial-alpha pixels on one icon. So a missed verdict is real damage once a resize is in play, and the false-positive direction costs roughly fifty times more — the quantitative form of the asymmetry this project keeps asserting. `references/lessons.md` §29.10

**Original item, verbatim:**

#### `[P2 · S · Sonnet5-High]` The render gate never RESIZES, so `--pixel-art`'s main destructive lever is untested end to end *(filed 2026-08-18)*

**Added 2026-08-18, from the first release-gated use of the render baseline.** The harness runs every asset through `--auto` with no other flags. That is the right default — it is the autonomous entry point — but it means the gate cannot see the single most destructive thing a wrong `--pixel-art` verdict does: **switch the resize filter from LANCZOS to nearest-neighbour.** Nothing in the 106-asset diff exercises `--resize-max-dim`, `--compress`, or WebP/AVIF output either.

**The measured consequence, which is why this is P2 and not P3.** The v5.5.0 hardness change flipped 8 verdicts inside the render set and the rendered output of all 106 assets came back **byte-identical**. That is a genuine no-regression result, but a weak one: all 8 are already-transparent sources, where removal is confined to the source's own alpha and the erosion guard has already forced erosion to 0, so no hardness verdict can move those pixels. The 31 fully-opaque assets — the only ones where feathering and erosion are live — had **zero** verdict changes. So "0 changed" partly means "this set cannot express the change".

**Do:** add a second render pass per asset with `--resize-max-dim` at roughly half the source's larger side, and fingerprint that alpha plane too. A `--pixel-art` verdict that only matters on resize needs a baseline that resizes. Cheap: the harness already loops, and `fast` is 24 assets. `references/lessons.md` §29.5

---

### ~~`[P2 · M · Opus5-High]` Only the HARDNESS measures read an alpha composite — every other `--analyze` check still reads RGB with the alpha discarded~~ — **CLOSED 2026-08-18 (v5.5.0)**

Measured first, exactly as this item's scope note demanded, by running `analyze()` twice per file with the frames composited the second time — the probe carrying its own falsifier (compositing over magenta moves 110 fields, so a quiet result means agreement and not a patch that never ran).

**On 14 partial-alpha icons the exposure looked cosmetic:** 5 of 14 move at all, only `band_interior_regions` and `candidate_regions`, pixel counts 0.5–4%, bboxes 1px, no verdict flips. **On the 10 most translucent assets in the sprite corpus — the population that can actually falsify it — it is verdict-level:** seven Tiny Swords cloud sprites go from 0 band-interior regions to 1 `solid_tint`; `Shadow.png` reads `mean_distance_from_bg` 58.2 uncomposited against 18.1 composited; `4.1-clear-notification.png`'s tumble margin ratio reads 1.08 against 2.01. **Scored properly over 38 partial-alpha assets — the whole population the change can reach — 31 of 38 get different recommended flags**, dominated by `--feather-band-multiplier 3.4` being dropped (17 assets) where the raw read had put a solid art colour outside the feather band that a viewer sees inside. Two assets get a different `--protect-outline-color` entirely. The hard-edged verdict moved on zero of the 38.

`all_rgb_frames` is now composited whenever a frame carries partial alpha. Verified two ways: 12 fully-opaque labelled assets produce byte-identical `analyze()` reports before and after, so the opaque corpus stays a valid control; and rendering PRE against POST over the 38 affected assets, native and resized, changed **8 outputs with the opaque count identical to the pixel on 7 of them** — only edge partial alpha moves, in both directions, and three pixel-art sprites correctly LOSE the 751–1,706 partial-alpha pixels `--recover-fade-alpha` had been giving them. `references/lessons.md` §29.11

**Original item, verbatim:**

#### `[P2 · M · Opus5-High]` Only the HARDNESS measures read an alpha composite — every other `--analyze` check still reads RGB with the alpha discarded

**Added 2026-08-18 (v5.5.0), and deliberately scoped this way rather than forgotten.** §28.5 fixed the edge-hardness family: for a source carrying partial alpha, those measures now run on a composite over the detected background colour, because the antialiasing lives in ALPHA and `convert('RGB')` drops it. **`analyze()`'s `all_rgb_frames` is still built with the bare `convert('RGB')`, and every other check reads it** — `detect_bg_color`, `color_mask`, the candidate-region enclosure search, `measure_bg_component_margin`/tumble, `detect_band_interior_regions`, `collect_small_removed_region_sizes`. On an RGBA source those are all reading full-strength art colour where a viewer sees a blend.

**Why it was NOT fixed in the same pass, which is a scope decision and not a shrug:** switching `all_rgb_frames` wholesale changes background detection and region classification for every alpha-carrying input, and **this project has no labelled RGBA-source corpus to validate that against.** The 31 labelled assets and the 5 corpus originals are all fully opaque, so they cannot detect a regression here in either direction — the same "the population that would falsify it is not in the sample" trap §23.8 and §28.2 are about. Shipping it blind would be the more expensive mistake.

**First slice (S):** assemble a small RGBA-source corpus — the `interface emojis/` PNGs are ready-made (`exchange.png`, `add.png`, `delete.png`, `alert.png` all carry partial alpha) — and diff full `--analyze` reports composited vs not, per check, to find out which checks actually change their answer. Fix only those that do, with the diff as evidence. Until then the honest position is that hardness is right on RGBA input and the rest is unmeasured.

---

### ~~`[P3 · S · Sonnet5-High]` Two residuals from the source-alpha fix, both small and both unexplained~~ — **CLOSED 2026-08-18 (v5.5.0) — neither was a defect**

`Soldier_Attack02.png`: re-measured on both copies, source **1,677** opaque and output **1,677**, gained 0, lost 0, no partial alpha in either. The 1,653 the item quoted does not reproduce. `f2ea31a625….gif`: the suspicion that the comparison was invalid is itself wrong — `load_animation_rgba_frames` and a per-`seek` count agree exactly at 912,486 — and the real answer is the FRAME COUNT. The source's frames 0 and 1 are identical duplicates at 116,007 opaque each, the output coalesces them, and 912,486 − 116,007 = **796,479**, the output total to the pixel. Zero art loss. `references/lessons.md` §29.13

**Original item, verbatim:**

#### `[P3 · S · Sonnet5-High]` Two residuals from the source-alpha fix, both small and both unexplained *(filed 2026-08-18)*

**Added 2026-08-18**, from the end-to-end render baseline that caught the auto-erosion override (§28.14). After that fix, 6 of the 7 regressed assets land EXACTLY on their source's opaque count. Two do not, and neither is understood:

1. **`Soldier_Attack02.png` comes out at 1,677 opaque against a source's 1,653 — 24 pixels MORE.** With the cleanup band dropped and no flags applied, the output should equal the source exactly. The direction is harmless (more artwork retained, not less), which is why it is P3 rather than P1, but "harmless and unexplained" is still unexplained. **Do:** diff the output alpha against the source alpha and identify those 24 pixels; the likely suspect is a source pixel with partial alpha being forced to 255 outside the scope.
2. **`f2ea31a625…gif` sits at 87.3% of its source figure (796,479 against 912,486).** ⚠️ **The comparison itself may be invalid:** the pipeline COMPOSITES a GIF's frames while the measurement counted them per-`seek`, so the two numbers may not describe the same pixels. **Do:** establish a comparable source count for an animated GIF first — through `load_animation_rgba_frames`, the function the pipeline actually uses — before treating this as art loss. If it survives that, the cleanup band is the next suspect (the veto did not fire on this asset, so its 2px ring is in scope).

**Why both are worth keeping:** the render baseline found the auto-erosion override on its first real use, and these two are what it flagged and nobody has explained. An unexplained residual is how the next real defect stays hidden.

---

### ~~`[P2 · M · Sonnet5-XHigh]` The corpus check compares RECOMMENDATIONS, never RENDERS — 24 of 31 assets are unexercised end to end~~ — **CLOSED 2026-08-18 (v5.5.0)**

**✅ DONE — the wiring that was all that remained is in place.** `CLAUDE.md`'s release-gate checklist now has gate 6 (diff the RENDERED output: the `fast` 24-asset set for routine checks, `standard` 106 at release, then `--compare A B`) and gate 7 (re-score the labelled populations through `analyze()` whenever an `edge_hardness` rule or threshold changes, reporting per population and, for sprites, per pack). The harness itself moved out of gitignored space in the same pass, because a gate whose script and ground truth are untracked is not a control — the hand-written labels for all 714 labelled assets were one `rm -rf` from gone, and `populations.py` now exits loudly when a corpus directory is absent instead of scoring a vacuous 1.000 over an empty population. `references/lessons.md` §29. Original note follows.

⚠️ **PARTIALLY DONE 2026-08-18 — the harness now exists and has been used for a real comparison, so this item's next action has CHANGED.** `local/pixelart-probe/render_baseline.py` renders each asset through the real `--auto` CLI and stores a sha256 over the concatenated ALPHA planes of every output frame plus per-frame opaque counts, dimensions, frame count and output bytes; `--compare A B` diffs two runs. It has `fast` (24 assets), `standard` (106: all 31 labelled + all 37 cutouts + a 40-file spread across every sprite pack + the 5 corpus originals) and `full` sets, and it **freezes a copy of the script under test at startup** — without that, a run re-reads the working tree per asset and silently splits its results across two versions of the code, which happened twice an hour apart (§28.15). **What REMAINS is only the wiring:** make it a release gate in `CLAUDE.md`'s checklist (`fast` for routine checks, `standard` at release) and record the accepted baseline alongside the tag, so a release diffs FILES rather than recommendations. Original note follows.

**Added 2026-08-18**, from the v5.4.0 pre-merge audit. The standing regression check runs `--recommend` on all 31 labelled assets and diffs the suggested command. That catches a changed DECISION and is why v5.4.0 could prove its optimisations changed nothing. It cannot catch a changed RENDER: only the 7 assets whose recommendation moved were actually processed and measured, so a flag combination that produces a wrong image on one of the other 24 passes silently. **Do:** extend the harness to render each asset with its own recommended flags and store a per-asset alpha checksum plus opaque-pixel count as the baseline, then diff those. That turns "the tool decides the same thing" into "the tool produces the same file", which is the claim releases actually need. The rendering cost is the reason it has not been done — roughly 31 renders per run — so consider a `--fast` subset for routine checks and the full set at release.

### ~~`[P3 · XS]` The vector-emoji falsifier population is presumed antialiased, not labelled~~ — **CLOSED 2026-08-18 (v5.5.0), and this item's own answer was WRONG**

**✅ DONE, but read the correction first, because the "partially ANSWERED" note below is the part that mattered and it was false.** That note said the population contains this tool's own outputs whose 1-bit alpha makes the FILE genuinely hard-edged, so `appears_hard_edged: true` on them "is correct rather than a false positive", and concluded the set needed stratifying by provenance. **Measured 2026-08-18: no.** All three of those verdicts came from a rule reading a plane that is blank by construction — on a hard-alpha cutout whose transparency is the background there is no background-to-art region at all, so `ratio max 0.000` is a fact about the export and would have read identically on pixel art and on antialiased art alike. A verdict that cannot vary with the property it claims to measure is not correct-by-accident; it is uninformative. And it is not harmless: it drives `--pixel-art`, whose nearest-neighbour resize is wrong for antialiased artwork whatever its alpha depth. **The 3 false positives were real, the count was accurate, and the fix belonged in the script** (`references/lessons.md` §29.1), not in the labels. **A provenance story is not a defence of a verdict** — what an asset was made from does not change what its pixels are.

**What DID get done, as the roster this item asked for:** all 122 files were viewed — 121 in four montages at 150px, plus one JPEG separately — and every one is antialiased; the roster records that, marks the 13 files derived from other assets, and states the population's blind spot (it contains no pixel art, so it can only ever measure specificity). The item asked for a spot-label of 20; the whole set was cheap enough to do properly. Original note follows.

⚠️ **The "145" in this item's own former title was never derived, and three different numbers were in circulation — 145 here, 119 in the scoring scripts, 123 in one §23.9 measurement.** Enumerated 2026-08-18: the six folders hold **130 files**, of which **122 carry an image extension** (2 `.zip`, 1 `.psd` and 5 extensionless directories are not assets) and 123 are openable by Pillow. The registry now uses 122 and states that derivation, and finding this ALSO exposed a real bug in the registry itself, which had been yielding the `.zip`/`.psd`/directory entries as assets. **A count nothing re-derives rots, and this one had rotted in the one number a session uses to judge whether a falsifier is big enough to trust.**

**Added 2026-08-18.** Two pixel-art discriminators were killed by scoring them against 145 vector emoji from this repo's own folders (§23.8, §23.9). Those 145 are presumed antialiased from their provenance — flat interface icons — not labelled by eye the way the 31 in `others/` were. The conclusion survives either way (a 25% and a 97% hit rate cannot be explained by a handful of mislabels, and the top scorers are visibly flat icons), but the set is now load-bearing for every future discriminator, so it deserves the same treatment as the labelled corpus. **Do:** spot-label a random 20 by eye from edge-dense crops (the method `others/LABELS.json` documents) and record the result; if all 20 are antialiased, promote the set to a labelled falsifier corpus with its own LABELS file.

⚠️ **SUPERSEDED IN SCOPE 2026-08-18 by the item above** — the falsifier question is no longer just "are these 145 antialiased?" but "which four content types is a threshold being scored against?". Read that item first.

⚠️ **Partially ANSWERED 2026-08-18 (v5.5.0), and the answer changes what the set is for.** The population is not homogeneous: it contains this tool's OWN OUTPUTS (`love_transparent.gif`, `bulk add_transparent.gif`, `star_transparent*`, `*_transparent_experimental*`). Those have 1-bit alpha, so writing the GIF destroyed the antialiasing ramp — the FILE genuinely is hard-edged even though the ARTWORK is antialiased, and `appears_hard_edged: true` on them is correct rather than a false positive. **So the set must be stratified by provenance before it can be used as a clean falsifier**: raw antialiased sources are counterexamples, processed outputs are not. Two of them were also revealed as genuine PRE-EXISTING false positives for a different reason entirely (§28.5, the alpha-channel bug), which is a second reason the flat "presumed antialiased" label was hiding structure. `references/lessons.md` §28.5

### ~~`[P1 · M · Opus5-High]` Background removal on an ALREADY-TRANSPARENT source eats real art — 65.6% survival measured~~ — **CLOSED 2026-08-18 (v5.5.0)**

**✅ FIXED, and the recommended option (b) needed correcting on the way in.** Removal is now confined to the region the source's own alpha covers, gated on two conditions that each block a different wrong engagement: the transparency must reach the frame border (otherwise it is a punched hole, not the background) and the modal RGB under it must match the detected background (otherwise the background is real paint, not padding). **The 2px cleanup band that was (b)'s whole advantage over (a) was measured and is harmful as specified** — survival by band on the filed sprite: 0px **100.0%** (alpha byte-identical to source), 1px 70.7%, 2px 68.1%, unrestricted 65.6%, because pixel art's outline sits directly against its padding, so the ring IS the outline; 2px recovered 184 pixels and destroyed 2,271. The band is therefore vetoed automatically whenever the background colour also occurs in the artwork away from the boundary — a margin of KIND rather than a tuned radius. Measured across 76 alpha-carrying assets: the veto fires on exactly the 25 that were losing art (mean survival 79.6%, worst **28.7%**) and takes all 25 to 100.0%; the other 51 were never at risk and are unchanged. Both branches fire on real content (51 kept / 25 dropped), so neither is dead. ⚠️ **That first measurement covered ONE of four code paths, and the audit pass found the other three still losing art while the log said `SOURCE ALPHA HONOURED`:** 8-bit-alpha output 65.6% (`dither_mode='continuous'` is a third return in `compute_alpha_mask`), `--recover-fade-alpha` 65.6% (returns before the scope, same bug in its own spelling), `.gif` output **23.0%** (the scope worked and `--edge-cleanup-erosion 2` then shaved the silhouette). Also: the veto was tested at `tolerance` while the feather path removes at `tolerance x --feather-band-multiplier`, and a per-frame decision flipped branch mid-animation on 17 of 57 assets. All fixed; re-measured over every frame of 57 assets on both branches at **100.00% mean, 100.00% worst**. `--recommend` now leads with `NOTHING TO REMOVE` on such a source. `--ignore-source-alpha` restores the old behaviour, `--source-alpha-band` tunes the ring, `love.gif` is still byte-identical and every doc gate passes. ⚠️ **What is NOT proven is the band's benefit** — on these 76 assets it removes nothing the unrestricted path would have left, so its fringe-cleanup value is unexercised; only its risk was measured and neutralised. `references/lessons.md` §28.14. Original note follows.

**Added 2026-08-18 (v5.5.0). This is data loss on a whole content class, and the detection shipped while the fix did not.** A hard-alpha PNG stores something in RGB under its transparent pixels — on real itch.io sprites, `(0,0,0)`. `detect_bg_color` returns black, `color_mask` matches every black pixel including **the sprite's own outlines**, and a measured sprite went in with 7,130 opaque pixels and out with **4,675 (65.6%)** while `--verify` reported no leftover background, no fringe, no inflation, matching dimensions and exact frame alignment. `references/lessons.md` §28.13

**Shipped in v5.5.0 (the detection half):** `verify()` reports `opaque_survival_vs_transparent_source` and warns under 95%, and `--auto` prints it as `ART LOSS:`. So the failure is now loud instead of silent.

**NOT shipped (the fix), because it is a semantics decision:** what should background removal DO when the source's background is already transparent? Candidates — (a) refuse, the way an alpha-only source now does, since there is nothing to remove; (b) restrict colour-based removal to pixels that were already transparent, honouring the existing alpha as the answer; (c) keep current behaviour but require an explicit `--bg-color` for any source carrying transparency. **(b) is my recommendation** — it is the only one that still helps a source whose transparency is partial, and it degrades to (a) when the alpha is already complete.

⚠️ **Why not just do it:** this changes the core removal path for every alpha-carrying input, and the project has no rendered-output baseline for that class — the same gap as the uncomposited-RGB item. The 524 sprites now make one buildable. **First slice (S):** render 20 of them under each of (a)/(b)/(c), diff the opaque-survival ratio and eyeball the outlines, then choose with evidence.

---

### ~~`[P1 · S · Sonnet5-High]` The labelled corpus is 31 fully-opaque GIFs, and the two populations that found today's defects are unlabelled~~ — **CLOSED 2026-08-18 (v5.5.0)**

**✅ DONE.** Both populations have a `LABELS.json` written by eye from edge-dense NEAREST crops, with no measure from the script consulted while labelling (a corpus labelled by the thing under test proves only self-agreement). Sprite packs: **493 pixel_art / 31 unsuitable_no_edges** — the 32 "opaque" files the item flagged were inspected and are 30 full-frame colour-grade overlay plates plus a 1-colour tile, all excluded from scoring rather than counted as antialiased, because 30 free true negatives on files with zero strong colour steps inflate specificity while testing nothing. Background-removed set: **22 pixel_art / 15 antialiased**, and 4 of them are cut-out counterparts of already-labelled assets that carry the same label their originals do — an independent check on the method. The four hardcoded directory lists are now ONE registry (`populations.py`) that records what each population is **blind to**, scores per-pack as well as pooled (one pack is 78% of the sprite corpus), and requires an explicit output path so a stale results file can no longer read as a finished run. The labelling immediately found 4 false positives among the 15 antialiased cutouts, all hard-alpha — the same class as the item above. `references/lessons.md` §28.15. Original note follows.

**Added 2026-08-18 (v5.5.0), and this is now the single highest-value corpus job.** Every threshold in this skill was scored against `others/` — 31 assets, **all fully opaque GIFs, zero with an alpha channel**. On 2026-08-18 Harkirat supplied **524 files from real itch.io sprite packs** (`local/itch.io sprites/`) and 37 background-removed assets (`local/Diors-builds Emojis/others/alphas/`), and those two populations immediately found **two defects that the labelled corpus certified as clean**:

1. The alpha-mask ramp cut was set at 2 levels; all 524 sprites have **4 or fewer** alpha levels, so a 3-level sprite would have been called antialiased and handed feathering plus 2px erosion (§28.12).
2. The density suppression turned **4 genuine sprite sheets** from detected to undetected (§28.12).

It also produced the largest correctness gain of the session: sprite-pack detection **54/524 → 427/524**, including 294 soft-alpha sprites of which HEAD detected **zero**.

**Do:** promote both folders to labelled corpora with their own `LABELS.json`, recording provenance as the label source (a sprite pack is pixel art; that is stronger evidence than an eyeball). Then wire them into `local/pixelart-probe/` as standing populations, so the next threshold is scored against opaque GIFs, hard-alpha PNGs, soft-alpha PNGs and vector emoji rather than against one of those four. ⚠️ The 32 "opaque" files inside the sprite packs are probably tilesets or backgrounds rather than sprites and need looking at before they count as either label — detection there is 2/32 and that may well be correct.

---

### ~~`[P1 · M]` `--recommend` chose `--protect-band-only` where `--protect-outline-color` was needed~~ — **CLOSED 2026-08-18 (v5.4.0)**

**✅ CLOSED 2026-08-18.** Root cause was NOT "prefer outline when a candidate encloses" — no candidate enclosed. `find_verified_outline_color` accepted a DEGENERATE candidate (`dcdcdc`, whose `binary_fill_holes` filled all 480,000 px of the frame and overlapped 423,855 px of real background), it won the tightest-fit contest as the only one clearing 95% containment, and was rejected one step later — by which point the true purple outline had been discarded. Two fixes shipped: reject candidates that overlap the frame's own largest background component *during* selection, and accept a leak-free PARTIAL enclosure when nothing encloses (the pokéball closes on only 15 of 76 frames). `--auto` on `.gif` now applies `--protect-outline-color 281450`: **+884,352 opaque px, protected coverage 0.0 → 0.843.** Across the 31-asset corpus 7 recommendations changed, no asset lost artwork, no meaningful leftover background introduced; `love.gif` still byte-identical. ⚠️ **One correction to the record below: the WebP path was never affected** — `--recover-fade-alpha` already protects 1,005,156 enclosed interior px there, and adding the outline flag changes zero pixels of alpha. The destruction only lands when the output is forced to `.gif`, which `--recommend` does not ask for on this asset. Full postmortem: `references/lessons.md` §26. Original note follows.

**Found 2026-08-17** on `local/Diors-builds Emojis/others/Cut loop.gif` (76 frames, Pikachu bursting from a pokéball, background `#f7f7f9`).

The pokéball's pale interior is `#eeeeee` — a per-channel gap of 9/9/11 from the background, inside the default tolerance of 15, so colour alone cannot separate them. `--analyze` DID see it: 12 `band_interior_regions`, including `#eeeeee` at distance 21.7 covering 8,177px. `--recommend` then chose `--protect-band-only 4`, which is the flag for a solid design colour near the background.

**It was the wrong flag, and the result is catastrophic:**

| flags | pale interior deleted | art deleted |
|---|---|---|
| `--auto` chose `--protect-band-only 4 --dither-mode none --erosion-exempt-max-size 521` | **593,583 / 593,583 = 100%** | 1,079,456 |
| `--protect-outline-color 39215a --dither-mode none` | 7,398 / 148,918 = **5.0%** | 26,829 |

**Why the chosen flag cannot work here:** `--protect-band-only` protects everything outside a thin ring around the *removable core*. The pokéball's lower half is an OPEN BOWL, so its interior is topologically continuous with the outer background — it IS part of the removable core, and the flag has nothing to hold. Only an enclosing outline closes the shape, and the dark purple stroke `#39215a` does exactly that.

**Next action:** when `band_interior_regions` reports a large near-background region AND a candidate outline colour encloses it, prefer `--protect-outline-color` over `--protect-band-only`. The two are not interchangeable: band-only assumes the region is OUTSIDE the removable core, outline assumes it is ENCLOSED. Check enclosure before choosing.

**Related:** this is the same topological root cause as the translucent-jar item. Two independent assets now hit it, which makes "a design region open to the background" the most common real-world failure in this corpus rather than an edge case.

---

### ~~`[P1 · M]` Thresholds are still calibrated on white-background art~~ — **CLOSED 2026-08-18, premise REVERSED** *(heading corrected 2026-08-18: the body said CLOSED while the heading still read open)*

**2026-08-17, corrected twice.** The record on this item was wrong in both directions, which is worth stating plainly because the third answer is the actionable one.

1. A probe reported "26 non-white background assets". **Wrong** — it ran `detect_bg_color` on `im.convert('RGB')`, which drops alpha and exposes a GIF's TRANSPARENCY-INDEX palette entry as though it were a painted background. Caught when Harkirat asked why a README panel captioned "magenta background" showed a white one.
2. The correction said the corpus has NO genuine coloured-background asset. **Also wrong** — it only re-checked `Diors-builds Emojis/` (where assets are indeed already transparent) and never looked in `others/`, the folder the labelled corpus actually lives in.
3. **The truth: `others/` holds 19 fully-opaque, genuinely non-white backgrounds**, verified by `'transparency' in im.info == False` AND every alpha at 255: `#bbfeba` 74%, `#9c38ff` 54%, `#c25027` 55%, `#4dbcfd` 74%, `#9cd6f7` 80%, `#42b4ff` 80%, `#000000` 71%, `#ffe75c` 64%, and more.

**Why this matters now:** §23 measured BOTH edge-hardness measures collapsing when a solid palette colour sits near the background — far likelier on a coloured one. Several of those 19 are already in the 37-asset labelled corpus, so the test is available immediately and needs no new assets from Harkirat.

**✅ CLOSED 2026-08-18 — the experiment ran, and it reverses the premise.** Scored over the 31 labelled assets split by background (11 white, 20 coloured): `change_line_density` detects 4/6 white-bg pixel art and 14/19 coloured-bg — **no coloured-background penalty**, exactly as a measure that never reads a colour value should behave. The band ratio manages 1/6 white and 4/19 coloured, i.e. it is weak everywhere rather than specifically colour-sensitive. Zero false positives on antialiased in every cell. So the standing "check by eye on a coloured background" caveat stays, but its stated reason was wrong: detection is mediocre overall, colour is not the discriminating factor. Numbers and the table: `references/lessons.md` §23.7.

~~**Next action:** score the edge-hardness measures on the coloured-background subset specifically, separately from the white-background majority, and see whether the failure rate differs.~~

⚠️ **When auditing for this, check `'transparency' in im.info` FIRST, and check the right folder.** An RGB conversion will lie to you, and so will a probe pointed at the wrong directory — both happened here.

---

### ~~`[P1 · S]` Project hooks are installed but NOT VERIFIED FIRING~~ — **CLOSED 2026-08-18: they fire**

`.claude/hooks/` + `.claude/settings.json` were added 2026-08-17. A filesystem tracer proved the hook process **never ran** — neither hook fires, on either event. ⚠️ **The cause is UNKNOWN.** "Project settings load at session start" is NOT it: Dior's Builds disproved that live (`reference_enforcement_hooks` — editing settings.json IS picked up mid-session). Not the `hookEventName` discard bug either, since the process never starts. Most likely a new project settings file needs trusting/approving, but that is unverified. See `.claude/hooks/README.md`.

**✅ CONFIRMED FIRING 2026-08-18, first session started AFTER the files existed.** SessionStart injected the repo-conventions block, and the PreToolUse release gate fired on the first `Bash` call (its tracer log is being written). **The surviving hypothesis was right: a `settings.json` that did not EXIST at session start is not discovered mid-session — creation is not the same as an edit**, which is why Dior's Builds' mid-session-edit evidence did not apply. Nothing needed trusting or approving. The gates they encode are no longer manual. ⚠️ Note for whoever next tests this: `rm`-ing the tracer log and reading it back **in the same Bash call** proves nothing — PreToolUse runs before the command, so the hook writes the log and then your own `rm` deletes it. Use two calls.

---

### ~~`[P3 · S]` `load_gif_rgba_frames` is misnamed~~ — **DONE 2026-08-18 (v5.4.0)**

**✅ CLOSED.** Renamed to `load_animation_rgba_frames` at all 6 sites; the old name stays as a module-level alias because this project's own written history cites it (`references/lessons.md` §17).

It reads GIF, WebP, AVIF, APNG, PNG and JPEG. The name reinforces the GIF-only misconception *inside the code*, which is the same misconception that kept non-GIF input out of the description for two versions. 5 call sites.

---

### ~~`[P2 · S]` APNG output is not exposed, though Pillow can write it~~ — **SHIPPED 2026-08-18 (v5.4.0)**

**✅ CLOSED.** `.apng`/`.png` or `--format apng`. Verified end to end: 76 frames, 123 distinct alpha values, durations read back exactly (2280ms); a static source writes a plain PNG with an honest "static image" timing line instead of "timing not read back"; `--target-kb 256` hits 193 KB through the resolution/frame cascade (no quality rung — APNG has none). Every 8-bit-alpha predicate now keys off one `EIGHT_BIT_ALPHA_FORMATS` constant rather than five inline tuples, which is what made adding a third container safe.

**Added 2026-08-17.** `--format` offers `auto|gif|webp|avif`. Pillow writes APNG with full 8-bit alpha — verified directly: a 3-frame RGBA save reads back as `n_frames=3, mode=RGBA`. APNG is the natural output for someone who wants PNG-family animation with real transparency and does not want WebP. Roughly a `save_all=True` call plus a `--format` choice and the byte-cap cascade hooked up.

---

### ~~`[P2 · L · Opus5-High]` Translucent glass/jar: three roles for identical `#ffffff` pixels~~ — **CLOSED 2026-08-18 (v5.4.0)**

**✅ CLOSED, and the structural route is ruled out rather than left hanging.** The cheap first measurement finally ran and the hypothesis is FALSE: the bag interior (component 2, 14,069 px) is NOT connected to the outer background — it is a fully enclosed pocket, and so is the bunny's body (component 3, 27,767 px), bounded by the same brown outline. Connectivity separates them no better than colour does, and in flat vector art nothing is drawn *behind* the bag, so there is no pixel evidence of translucency to recover. That leaves naming the region, which shipped as `--translucent-region` + `--translucent-alpha` + `--translucent-color`, restricted by colour (133,070 px affected without that restriction vs 76,988 with it — the unrestricted version dissolved the popcorn) and to already-opaque pixels. Verified over a dark composite, not a checkerboard. `references/lessons.md` §27.

**Added 2026-08-17**, from `local/Diors-builds Emojis/others/2d4a092f5494a8d2455703857ee83d5c.gif` (Harkirat's own framing): a bunny holding a transparent bag of popcorn. The same `#ffffff` plays three different roles — outer background (remove entirely), bunny body (keep fully opaque), and jar interior (make TRANSLUCENT, so it reads as glass). Current behaviour does one or the other: either the jar interior is removed with the background, or it is protected and stays solid white.

**No pixel-level threshold can separate these** — the pixels are byte-identical. The distinction is semantic, so this needs either a region/colour flag naming the glass, or a structural signal.

**Only expressible in WebP/AVIF.** GIF's 1-bit alpha cannot hold "20% opaque", so this sits on top of the 8-bit alpha pathway added in v5.0.0 (§16), and is a natural extension of it rather than a new subsystem.

**Partly improved 2026-08-18 as a side effect of §26's fix** — this asset is one of the 7 whose recommendation changed. It now gets `--protect-outline-color 3c2814` from the partial-enclosure path: **+202,845 opaque px, protected coverage 0.0 → 0.331, leftover background still 0.** That protects more of the design but does NOT solve the three-roles problem — the jar interior becomes opaque rather than translucent, which is still one of the two wrong answers. The semantic distinction remains open.

**Cheap first measurement, not yet done:** check whether the jar's interior is topologically CONNECTED to the outer background through the bag's opening. If it is, flood-fill-from-border reaches straight into it, which would exactly explain the "removes the white inside the jar" half of the observed behaviour and would point at the fix.

**Notable:** this asset is also the only ANTIALIASED file in `others/`, so it doubles as the negative control for the pixel-art item above (`blend` 0.999, `ratio_max` 0.649).

---

### ~~PARKED: remove the controller from love.gif~~ — CLOSED 2026-08-17 (Harkirat edited it manually; skill rendered the deliverables). Retained below only for the mask-isolation findings, which stay valid if this is ever automated.
Boundary reconstruction and the encoding path are SOLVED (static-in-canvas divide, degree-6 fit at 0.33px RMS, no GIF round-trip). **Unsolved: isolating the controller mask on frames 26–34**, where it touches the heart outline. Four approaches measured — see the handoff.

---

### ~~`[P1 · S · ⛓️blocked-by: no labelled RGBA pixel art]` 15 of 119 vector icons still get `--pixel-art` recommended~~ — **CLOSED 2026-08-18 (v5.5.0), and the filed diagnosis was WRONG**

✅ **CLOSED, by a completely different fix than the one filed here, and the difference is the lesson.** This item said the mechanism was zeroed RGB and the fix was an alpha-ramp veto, blocked on acquiring labelled RGBA pixel art. Both halves were wrong. All 15 are **alpha-only masks**: exactly ONE unique RGB value across the canvas (span 0) with 186–256 distinct ALPHA levels. The colour channel is blank by construction, so the empty transition band was never weak evidence of hard edges — it was the absence of any evidence, and there was nothing to out-vote.

**And the misread was the smaller half.** `detect_bg_color` returns that one flat colour, `color_mask` matches every pixel, and the render deletes the whole image: measured on `pencil.png`, **69,925 opaque pixels in and ZERO out**, with `--auto` printing success and the frame count collapsing 30 → 1. Every quality check in `verify()` passed, because all four ask how WELL the background was removed and an empty output scores perfectly on every one of them (§26.5's "a metric that cannot fail", again).

Fixed at three layers: `alpha_only_source`/`source_alpha_levels` reported with every colour rule abstaining and hardness read off the alpha channel (2 levels = hard cutout, 186–256 = real ramp, a margin of KIND); `--recommend` returning `not_applicable_reason` with `suggested_command: null` and `--auto` refusing; and `_refuse_empty_render` in all four renderers, so a good file can never be overwritten by an empty one. Red-green verified against HEAD in both directions. **No new threshold, no new measure, and no new corpus needed.** `references/lessons.md` §28.9

⚠️ **The RGBA-pixel-art asset request is therefore NO LONGER BLOCKING anything** — but it is still wanted, for two smaller purposes: corroborating §28.3's claim that the 3 remaining misses are re-encoding damage (upscaling them is an independent test of that explanation), and as the first slice of the uncomposited-RGB item below.

---

### ~~`[P1 · XS · Sonnet5-Medium]` `--auto` already detects this whole bug class and says nothing~~ — **DONE 2026-08-18 (v5.4.0)**

**✅ CLOSED, same day it was filed.** `verify()` now names any `likely_intentional_design` region that comes back under 5% opaque, says which flag was supposed to protect it, and points at the analyze note. Non-vacuous in both directions: it fires on the pre-fix flag set for `Cut loop.gif` and stays silent on the fixed one. The 5% line sits in a 0.33-wide gap (every measured failure reads exactly 0.000; the weakest genuine success 0.331). `--auto` also now runs the full verify for EVERY container rather than GIF only, so the warning reaches WebP/AVIF/APNG output too.

**Added 2026-08-18.** On the asset that motivated v5.4.0, `--auto`'s own verification printed `full verify -- worst protected-region coverage: 0.0` and carried straight on to report success. That line is a complete detector for "a region `analyze()` called `likely_intentional_design` received no protection at all" — the general form of the bug that cost 976,800 pixels — and it is emitted as a neutral statistic among a dozen others. **Do:** when `--auto` renders and any region with `likely_intentional_design: true` comes back at coverage ~0.0, emit a loud warning naming the region and the flag that was supposed to protect it. XS because the number is already computed; the only work is noticing it. This is the cheapest autonomy win on the list: it converts the next instance of this class from "discovered by eye months later" into "reported by the run itself".

---

### ~~`[P3 · M]` `--verify`'s `protected_region_coverage` false-positives on a legitimately punched sub-hole~~ — **CLOSED 2026-08-17** *(heading corrected 2026-08-18: the body said CLOSED while the heading still read open)*

**✅ CLOSED 2026-08-17 — confirmed against this item's own asset.** `military-tag.gif` IS on this machine (found in the repo's own asset folders); the earlier "not on this machine" note was wrong. Re-rendering §14's pipeline uncropped and running `--verify` with both scripts: **0.462 → 0.757**, `looks_unprotected` **true → false**. The 0.462 reproduces §14's recorded 46.2% exactly, so this is a real reproduction, not two clean runs agreeing by luck.

⚠️ Verifying against the DELIVERED file would have been a vacuous pass — it is cropped (536x570 vs 640x640), so `--verify` skips every pixel check and reports only timing.

**The residual 0.757 is correct, and now self-explaining.** Decomposed, the non-opaque remainder is ONE blob per frame in all 126 frames, 441–457px — the punched pinhole, which is background-coloured and *should* be transparent. A new additive `residual_nonopaque` field reports persistence, blob count, size CV and footprint fraction so this reads as a cutout rather than an unexplained defect; falsified against a deliberately unprotected render (1.00 blob/cv 0.025/0.243 → cutout; 2.13/0.586/ 1.000 → not). **Correction to the original diagnosis below:** cause (1), the translating bbox, contributes nothing measurable here — cause (2) was doing all of it. Full case: `references/ lessons.md` §22.

**Added:** 2026-08-07, from `military-tag.gif` production job (see `references/lessons.md` §14 for the full case).

**The problem:** `protected_region_coverage` measures opacity for background-colored-in-input pixels within a candidate region's bbox. Two things break this on a real asset: (1) the region's footprint is tied to one fixed reference frame, but if the design translates/swings across the animation, real outer background can fall inside that same fixed bbox in other frames and get correctly removed -- inflating the "not opaque" count with pixels that were never really part of the region; (2) if a verified region legitimately contains its own interior sub-hole (punched via `--hole-size-range`/`--hole-max-aspect`, not `--protect-outline-color`), the hole's pixels are *supposed* to go transparent, but the check has no concept of an intentional sub-hole and just counts it as unprotected coverage. Confirmed false positive: flagged `looks_unprotected: true` at 46.2% opacity on an output independently verified (via a frame-by-frame true-component check, not the bbox metric) to have the protected element at 100% opacity in all 126 frames.

**Why not fixed now:** same root architectural cause as the `band_interior_regions` gap above (candidate-region detection ties to one fixed-frame bbox/footprint) -- a real fix needs `verify()` to either re-derive the region's footprint per-frame the way `outline_enclosure_all_frames` does, or accept an explicit "known intentional sub-hole" input. Genuinely a design question, not a quick patch, and lower priority than the two items above since it only produces a misleading warning (evidence text), never a wrong processing command.

**Model pick reasoning:** premise Medium (root cause understood, but the right API shape for "this region has an intentional sub-hole" isn't obvious yet) · deliberation Medium (touches `verify()`'s existing, reviewed logic, but is more contained than the `band_interior_regions` reorder) -> `Sonnet5-High`.

---

### ~~`[P2 · M · Sonnet5-XHigh]` `band_interior_regions`' cross-frame grouping doesn't know about verified candidate regions~~ — **CLOSED 2026-08-18 (v5.4.0), without the reorder**

**✅ CLOSED by annotation rather than restructuring.** The recorded fix was to reorder `analyze()` so candidate regions are built before the band-interior scan. That is a ~450-line reorder with real regression risk, and it turns out not to be necessary: by the time the report is assembled BOTH lists exist, so each band-interior detection can simply be labelled with the protected region whose footprint contains its centre, and `recommend()` excludes labelled solid tints from the `--protect-band-only` decision and from the feather-band risk list. `Cut loop.gif`: 6 of 12 detections labelled, 5 solid tints excluded from the count. A gradient fade is deliberately NOT excluded — a flattened fade inside a protected outline is still a flattened fade. Corpus recommendations unchanged, `love.gif` byte-identical. The item's own analysis said the wrong output was never a WRONG flag but wordier evidence; that is exactly what this fixes.
**Added:** 2026-08-07, from the final whole-branch review of Phase 1 (found, partially mitigated, then the mitigation itself was re-reviewed and two smaller regressions in it were fixed same session — see the plan doc's Task 6 section and the SDD ledger for the full sequence).

**The problem:** `detect_band_interior_regions`'s per-frame detections are grouped across frames by bbox-center proximity (currently 40px) into `band_interior_regions`. This grouping runs BEFORE `analyze()` computes its candidate-region list (`candidate_regions`, the enclosed/protected areas), so it has no way to know a given band-interior detection is actually inside a region that's already protected by a verified `--protect-outline-color`. Confirmed real consequence on `jewelry.gif`: what's genuinely 1-2 physical regions (the protected highlight itself) fragmented into up to 17 separate `band_interior_regions` entries, producing misleading evidence text in `--recommend`'s output ("17 solid-tint region(s) observed") even though `recommend()` correctly avoids adding a wrong CLI flag for it (already gated: `--protect-band-only` is suppressed whenever a verified outline color is also being recommended, so this doesn't currently ship a WRONG command — it ships a wordier, less precise one).

**The real fix:** reorder `analyze()` so the union-mask/candidate-region detection (the loop that builds `results`/`candidate_regions`) runs BEFORE the tumble-margin/band-interior/small-region checks, then thread the resulting candidate bboxes (or footprints) into `detect_band_interior_regions`'s grouping step as an exclusion, the same technique `verify()` already uses successfully for its own `leftover_background_opaque_px`/`protected_region_coverage` checks. Not done in Phase 1 — genuinely a reordering of a ~450-line function's internal structure, not a small patch.

**Model pick reasoning:** premise Low-risk (the fix shape is well-understood and already proven elsewhere in the same function for a structurally similar problem) · deliberation High (reordering a large function's internals without regressing its existing, already-reviewed checks needs real care, and the byte-identical/behavior-preservation discipline this whole project runs on) → `Sonnet5-XHigh`.

---

### ~~`[P2 · L (first slice: S) · Sonnet5-XHigh]` `--analyze`'s runtime regression~~ — **FIRST SLICE DONE + TWO FIXES LANDED 2026-08-18 (v5.4.0)**

**✅ The profile the first slice asked for ran, and it named two costs the architectural reasoning had missed.** On `Cut loop.gif` (23.8s): `binary_dilation` 7.2s and `color_mask` 6.1s — and on the 1000x1200 asset, `color_mask` alone was **16s of SELF time across 1,772 calls**. Both fixed with proven equivalence, not assumed: (1) `binary_dilation(mask, iterations=k)` with the default cross structure is exactly "within taxicab distance k", so ONE `distance_transform_cdt` replaces 124 sequential erosion passes across five radii — checked equal at every radius on random multi-blob masks, 4.3x faster; (2) `color_mask` was upcasting a uint8 frame to int64 (11 MB per call on an 800x600 frame) — now an in-place clipped inclusive-range comparison, checked equal on random arrays across five tolerances and both colour extremes, **5.1x faster**. Result, re-measured back to back two runs per side (the first figures filed here paired an intermediate state against a post-fix one and read as a bigger win than it is): `Cut loop` **27.9/26.8s → 19.4/18.0s, ~32% faster** while running the new partial-enclosure search; `ezgif` **49.5s → 55.7s, ~12% SLOWER** — on that asset the new search still costs more than the caching saves, and it is the honest exception. **Zero of the 31 corpus recommendations changed**, which is the equivalence check that matters. Remaining, if it is ever worth more: `binary_fill_holes` (985 calls) and the `np.unique` on Nx3 pixel arrays in candidate quantization (2.7s), which a packed-uint32 `bincount` would cut.
**Added:** 2026-08-07, from the final whole-branch review of Phase 1.

**The problem, measured:** escalating 3 of `--analyze`'s checks (tumble margin, band-interior detection, small-region histogram) from a 40-frame sample to every frame — necessary, it's what fixes real false-negative bugs the checks exist to catch (confirmed real case: `references/lessons.md` §12's `fff2d1` sparkle was on frame 97, which a 40-frame sample of a 109-frame GIF never lands on) — made `--analyze` **~3-8x slower**: `jewelry.gif` 3.14s → 19.71s, `gemstone.gif` 2.14s → 18.19s, `ruby.gif` 2.49s → 6.84s (all real fixture measurements, same machine, before vs. after).

**One real attempt already made and measured, not just theorized:** shared the per-frame `color_mask()` computation between the tumble-margin and small-region checks (they were each computing the identical thing independently). Re-measured honestly: **did not help** (`jewelry.gif` 20.66s after — within noise of the 19.71s baseline). `color_mask` itself is cheap; it was never the real cost.

**The actual cost driver, identified but not yet fixed:** `ndimage.label`/`binary_fill_holes` calls running multiple times per frame across DIFFERENT checks, each on a DIFFERENT mask (the raw background-color mask, the band-interior distance mask, one mask per verified outline color) — they can't share one labeling pass the way `color_mask` could, because they're not labeling the same thing.

**First slice (S):** profile which specific call sites actually dominate (which check, `label` vs `binary_fill_holes`, on which fixture) before attempting to batch/vectorize anything — the current diagnosis is architectural reasoning, not a profile. `cProfile` or manual per-call timing on `jewelry.gif` (the slowest fixture) would settle it in well under a session.

**Model pick reasoning:** premise Med (the general cause is identified and real, but the specific call-by-call breakdown that would drive a batching design isn't measured yet) · deliberation High (vectorizing/batching `ndimage` operations across frames for several structurally different checks is a real design task, not mechanical) → `Sonnet5-XHigh`. Re-score once the profile (first slice) is done — that measurement may well drop this to a lower cell.

---

## Earlier phase work (2026-08-07/08)

- ~~Phase 1: move SKILL.md's manual checks into `--analyze`/`--recommend`/`--verify`~~ → **SHIPPED 2026-08-07** on `feat/analyze-recommend-verify` (not yet pushed/merged — Harkirat's call). 5 new `--analyze` checks, `--recommend`, `--verify`, all reviewed (including a full whole-branch review) and fixed. Three real design bugs found via testing against real fixtures rather than written to spec and trusted — see the plan doc and SDD ledger for specifics.
- ~~Phase 2: compress SKILL.md's manual-check prose against Phase 1's new fields~~ → **SHIPPED 2026-08-08** (fresh session, on the same branch, v3.3.0 → v3.3.1). Every check-by-hand paragraph Phase 1 made mechanically checkable now points at the real field name; also closed a real documentation gap (two `candidate_regions` fields shipped in Phase 1 but never documented, and `--recommend`'s actual outline-trust gate wasn't stated in "Run the real processing"). Pure docs change, no script touched. `references/lessons.md` gained a symptom→section lookup table.
