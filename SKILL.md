---
name: gif-background-remover
description: Remove the background color from an animated image -- GIF, WebP, AVIF or APNG, or a static PNG/JPEG -- while protecting interior parts of the design that are the same color as the background (e.g. a white highlight inside a badge). Handles antialiased vector icon/sticker/emoji art and hard-edged pixel art (--pixel-art). Outputs GIF, or WebP/AVIF with true 8-bit partial transparency, including recovering a fade/glow/sparkle whose translucency a GIF export already flattened. Also shrinks an animated image to fit a platform size limit (e.g. 256KB Discord stickers/emoji) and batch-processes many files from a manifest. Use when the user asks for background removal, to remove/strip/delete a background, make an image transparent, cut out a background, convert a GIF to WebP or AVIF, keep a fading element translucent, turn something into a sticker or emoji, shrink an animated file, or just handle it automatically end to end.
---

# GIF Background Remover

**Skill version: v6.0.0** (previous: v5.5.0, v5.4.0, v5.3.0, v5.2.1, v5.2.0, v5.1.1, v5.1.0, v5.0.0, v4.0.0, v3.3.3 … v1). Full per-version detail, and the three-part versioning convention itself, live in `references/version-history.md` — read it when you need to know what a past version changed or which tier a pending change belongs to.

⚠️ **v6.0.0 is NOT published, and neither was v5.5.0. GitHub's Releases page deliberately still shows v5.4.0 as Latest.** This entry describes work that is built, gated and committed but deliberately held: a three-agent trial on real assets found seven defects AFTER the build, three of them severe, and publishing now would ship a fade that pops instead of ramping and a GIF path that can silently truncate. See `references/lessons.md` §34 for what those are and how to route around them. When v6.0.0 is eventually published its notes will cover everything since v5.4.0, v5.5.0's entry folded into its history. **v6.0.0** is a *major* bump: two data-loss classes on the alpha path, a reversal of a compression default, a seventh pixel-art discriminator, a new region flag, and the ground truth the detection figures rest on rebuilt by eye. Detection over the independent populations goes **recall 0.8932 → 0.9644**.
- **A source's partial alpha was being promoted to fully opaque, and 218 of 249 corpus assets carrying a fade lost it.** `process()` built its working frames with a bare `convert('RGB')`, so a pixel the source drew at 35% opacity became byte-identical to a solid one and `estimate_alpha_and_defringe` re-derived its alpha from RGB alone. `love_emoji_128.webp` went in with 913 partial-alpha pixels and out with **0**, its 5,509 opaque becoming 6,422. Fixed with a MINIMUM, never an assignment — the colour path may still make a pixel more transparent, it may never invent opacity the source did not have. **207 of 249 now keep 90%+ of their partial alpha.** The control that had to run first: `--pixel-art` implies `--no-feather`, which is binary by design, and 20 of the 45 largest cases were that — without the split the headline would have been half artefact. `references/lessons.md` §31
- **The removal decision now keys on the COMPOSITE, and the output still carries raw art colours.** `analyze()` has composited partial-alpha frames since §28.5; `process()` had not, so the flags were chosen from one image and `color_mask` acted on another — 41 of 338 partial-alpha sources disagreed at the real removal reach, worst 18.41% of a frame. `compute_alpha_mask` and `estimate_alpha_and_defringe` take `rgb_key`; every colour COMPARISON reads it, every returned pixel still comes from the raw plane. 47 assets change, **opaque counts identical on every one**, and of the 5,166 partial-alpha pixels removed **65.0% are under 2% opaque and 0.0% are above half opacity**. §31.2
- **A seventh discriminator: a transition band that is REAL but narrow.** The vacuity gate silences both band rules on a hard-alpha cutout whose transparency is its background — correct for an EMPTY band, and it was applied to every such source. Among the 378 assets it silences: at ratio 0.000, 46 pixel art / 40 antialiased; at 0 < ratio < 0.20, **49 / 9**. Native-resolution pixel art carries a thin band (the artist's own 1px shading); antialiasing carries a wide one. `Tiny RPG Character Asset Pack` goes **0.235 → 0.941**. `plateau_cliff_ratio` could never have reached it: it needs flat runs of 2px, and 1:1 art has none by construction. §32.7
- **`--dither=floyd-steinberg` is REMOVED from `--compress medium` and `heavy`.** Measured on 23 gradient assets and, as a falsifier, 5 flat animated vector sources: it cost **11–24% file size, 8–12% colour error and 2.6–5x static-region instability** to buy a ~6% banding improvement. The falsifier did not save it — flat art improves too. Temporal crawl is the decisive axis and the precedent was already here: error diffusion is refused for ALPHA on exactly that ground. `--auto` is unaffected; `love.gif` is still `2fd526b6fb3b191c`. §30.1
- **`--remove-region-track` follows a moving hole.** The one case filed with no answer: a hole that must be punched while same-coloured decoration is kept, where neither differs in size or aspect and both move. The seed supplies what no single frame can — two identical holes are indistinguishable within a frame and completely distinguishable across an animation, because only one is where the seeded one just was. On an asset built to make that premise true: static `--remove-region` punches the target on **1 of 24** frames, the tracker on **24 of 24 and the decoy on 0**. Losing the target is reported, never hidden. §33
- **The ground truth was rebuilt by eye, and one apparent collapse turned out to be an artefact.** 267 assets had arrived labelled `antialiased` in a single pass with 8 inspected. Every disagreement was rendered to a nearest-neighbour contact sheet and judged: 9 were real pixel art, 7 are undecidable at 32–128px and are now `ambiguous` rather than guessed. `small_aa` specificity **0.887 → 0.970**. The `small_aa_quantized` specificity of 0.615 is NOT 45 false positives — it is the quantization hazard measured at scale, and checking ORIGINALS showed the whole Blox-Fruits family is smooth rendering in the source and blocks only in its 16-colour twin. §32
- **The 16-colour floor was tested against real negatives at last and DOES NOT MOVE.** Lowering it 16 → 12 looks like 4 detections for 20 false positives — until you notice all 20 removed false positives are in the DERIVED population. On the independent populations specificity is **0.9787 at floor 16, 14, 12 and 10 alike**. The measurement that would have justified the change was run and came out the other way. §32.5
- **Also:** the outline leak gate tests the union of border-touching background components instead of the largest (which can be an interior region of the artwork); `--translucent-region` warns when it touches zero pixels instead of silently no-opping; erosion auto-calibration is skipped on any source carrying its own partial alpha, after it read a restored ramp as fringe and shaved 6,844 pixels; APNG playback is confirmed by Chrome's own decoder (12 animated, pixel-distinct frames against a control GIF at 35); and a detector for "this file is our own output" was built, measured and falsified. §30.3, §31.1, §33.1

**v5.5.0** was a *minor* bump — the fifth pixel-art discriminator (`plateau_cliff_ratio`), hardness measured on the alpha composite, and a static-JPEG crash. Full entry in `references/version-history.md`.

**v5.4.0** was a *minor* bump — the degenerate outline candidate that left design regions unprotected, partial-enclosure acceptance, APNG output, `--translucent-region`, and a faster `--analyze`. Full entry in `references/version-history.md`.

**v5.3.0, v5.2.1, v5.2.0 and v5.1.0** are summarised in `references/version-history.md` — the tumble-safe stranding fix and the `--recover-fade-alpha` recommendation (v5.3.0), the 1024-character description limit claude.ai enforces (v5.2.1), static-image and RGB-APNG input plus the six flags that lived only in a changelog (v5.2.0), and the sandbox path/AVIF-guard fixes (v5.1.0).

**v5.0.0** was the major release: WebP and AVIF output with true 8-bit alpha, `--recover-fade-alpha` (reconstructs partial transparency a GIF export already flattened — a case §7 had recorded as impossible), `--auto`/`--auto-erosion`, a `--verify` overhaul, and a pixel-art detector rebuilt and scored against 37 labelled assets (17/37 → 30/37, zero false positives). Full entry in `references/version-history.md`.

**If you are running as the standalone skill on claude.ai, you are in an isolated sandbox**: you can read this `SKILL.md`, `references/`, and `scripts/` — frozen at the uploaded version — and nothing else. Not the development repo, its `CLAUDE.md`, its git history, or any memory folder, and you cannot write to Harkirat's machine. So a finding does not travel on its own: state it in the chat and hand over the full text of anything you changed. Never call a finding "saved", "synced" or "logged" — the chat is the only persistence there is. Keep the skill `name` in the frontmatter unchanged.


**This file is the lean, actionable core.** The full evidence trail behind its rules — bug postmortems, tool evaluations, measured numbers, reverted attempts — lives in `references/lessons.md`.

⚠️ **`references/lessons.md` is far too large to read whole. Never do it.** Any single section is a small fraction of it, so the right move is always to find one section and read only that. It opens with a "How to read this file" block giving four routes: a symptom→section table covering every section, a grep recipe (its prose is soft-wrapped so multi-word phrases match on one line), a one-liner that extracts one section by number, and a one-liner that prints the real per-section sizes if you need to budget rather than guess. Spend one grep there before re-diagnosing anything that smells like a past case — a fringe, a flicker, erosion eating detail, jagged edges surviving a resize, a wrong duration, a tool-or-quantizer question, a check that disagrees with your eyes. This skill's history is long and specific, and several fixes were tried, looked right, and later regressed; re-deriving one from scratch risks repeating that.

## When to use this
The user has an animated GIF and wants its background color (usually white) removed / made transparent, while preserving some part of the interior design that happens to be the same or a similar color.

## Check content type FIRST — this determines which defaults are even safe
This script's defaults for GIF output (feathering on, `--edge-cleanup-erosion 2`, LANCZOS resizing) assume the source has real antialiasing to clean up — true for this skill's primary target, antialiased vector icon/sticker art, but **actively destructive** on hard-edged content like pixel art. Confirmed directly: the DEFAULT settings eroded a 31px pixel-art shape down to ZERO surviving pixels (0% survival) on a real synthetic test file — total destruction, not just a quality hit.

**Before choosing settings, always check `--analyze`'s `edge_hardness` field:**
```json
"edge_hardness": {
  "ratio": 20.895,                    // frame 0, kept for continuity
  "ratio_max_across_frames": 20.895,  // the band measure the DECISION uses
  "antialiasing_blend_ratio": 0.0,    // the second discriminator
  "change_line_density": 0.061,       // how often the image changes as you sweep across it
  "plateau_cliff_ratio": 1.0,         // what share of EDGES are block-to-block cliffs
  "plateau_cliff_samples": 3826,      // under 500, the ratio above is NOT dispositive
  "composited_color_count": 9,        // at or under 16 = a flat palette, i.e. pixel art
  "band_measures_are_vacuous": false, // true = the two band rules ABSTAIN (see below)
  "measured_on_alpha_composite": false,
  "alpha_only_source": false,            // if true, NO colour rule gets a vote
  "source_alpha_levels": 1,              // 2 = a hard cutout, 186+ = a real ramp
  "appears_hard_edged": true,
  "hard_edged_reasons": ["change_line_density 0.061, below the 0.5 floor …"],
  "hard_edged_suppressed_notes": []
}
```
**If the source is ALREADY transparent, the question is not which settings to use — it is whether to remove anything at all.** A PNG/WebP/GIF whose background is already alpha has no background *colour*: the RGB stored under those pixels is padding, and on real sprite packs that padding is `(0,0,0)` — the same value as the artwork's own outlines. Removing "everything that colour" then deletes the outlines. Measured across 76 alpha-carrying assets, unrestricted colour removal left **28.7% of the artwork** on the worst one and averaged 79.6% on the 25 assets where the padding colour also appears in the art. The script now confines removal to the region the source's alpha already covers, reports it on stderr, and `--verify`'s `opaque_survival_vs_transparent_source` catches any remainder. **So on an already-transparent source, expect the output to be close to the input, and treat a big drop in opaque pixels as a defect rather than a result.** See `--source-alpha-band` / `--ignore-source-alpha` in `references/flag-reference.md`, and §28.14.

⚠️ **Decide content type from the ORIGINAL asset — never from any file this tool has written.** Writing a GIF *is* a palette reduction, so re-analysing your own output can turn antialiased art into `appears_hard_edged: true`: a 1px antialiasing ramp gains the flat neighbours it never had, and `plateau_cliff_ratio` clears its floor on art with no blocks in it. Measured over 48 antialiased assets run through the real CLI at every tier and re-analysed: **8.3% flip with NO compression flag at all**, 25.0% at `--compress optimize`, 20.8% at `medium`, 12.5% at `heavy` — so `heavy` is the *least* affected tier, not the trigger, and 14 of the 48 flip somewhere. The colour count correctly abstains, and the obvious veto (distrust a high cliff ratio when the palette is large) was measured and costs five real detections while removing none of the corpus's actual false positives, because dithered pixel art legitimately carries hundreds of colours. A documented hazard, not a fixed one. §29.9

**Read `appears_hard_edged` and `hard_edged_reasons` — not the raw numbers.** FIVE independent rules feed that verdict, any one of them is enough, and `hard_edged_reasons` names the one(s) that actually fired. Two of them ABSTAIN on a hard-alpha cutout whose own transparency is the background — see `band_measures_are_vacuous` below — so on that content type the list can be shorter than five. The example above is real: that asset is pixel art with a band ratio of 20.895, *higher* than any genuinely antialiased asset measured, and it is detected anyway because a different rule carries it.

The five rules, in the order they were added:

- **`ratio_max_across_frames` under 0.5 AND `antialiasing_blend_ratio` under 0.15** — a thin transition band with essentially no genuine background-to-art blend pixels. Measured across every sampled frame, not frame 0: love ranges 0.290–7.863 and heart 0.239–9.008, so a single frame decides nothing. `ratio` alone produced two false positives on real vector art (love 0.425, heart 0.316), which is why the blend ratio was added. §1, §18.1
- **`ratio_max_across_frames` exactly 0.000** — dispositive on its own. Antialiasing IS intermediate pixels, so zero of them means none, and a blend ratio computed on top of that is measuring palette collisions. §23.3
- **`change_line_density` under 0.5** — how often the image changes as you sweep across it. Pixel art is drawn on a coarse grid and enlarged, so it changes only at block boundaries. Reads no colour value, so palette collisions cannot reach it. Measured over 37 labelled assets: antialiased 0.835–1.000, pixel art 0.037–0.245 for 18 of 25. §23.4
- **`composited_color_count` at or under 16** — how many distinct colours the composited frame holds, and the only rule here that never looks at an edge. Pixel art comes from a deliberate small palette; antialiasing manufactures intermediate colours by construction. **This is the rule that reaches pixel art drawn 1:1**, where no edge has a 2px plateau and the cliff ratio is low by construction. Measured over 688 assets: pixel art median 12, antialiased median 403, nearest negative 26. Abstains on an alpha-only source, like every colour rule. §29.3, §29.4
- **`plateau_cliff_ratio` at or above 0.30, with at least 500 `plateau_cliff_samples`** — of the *strong* colour steps (40+ on a channel, i.e. real edges), what share sit between two flat runs of 2 px or more. Upscaled pixel art transitions block-to-block; a 1 px antialiasing ramp cannot, because the ramp pixel is a plateau of length 1. **This is the rule that reaches dithered and photographic pixel art**, which saturates `change_line_density`. Scored against both populations — the 31 labelled assets AND 127 antialiased negatives: **22/25 pixel art, zero false positives**, lowest true positive 0.356 against highest negative 0.186. §28

**When `band_measures_are_vacuous` is `true`, the first two rules above got no vote, and that is correct.** The source is a hard-alpha cutout whose transparency is standing in for its background, so there is no background-to-art region for a band measure to read: the ramp pixels were made transparent when the background was removed and their colour replaced by padding, which makes `ratio max 0.000` a fact about the export rather than about the art. Five real false positives came from treating it as evidence — all of them antialiased art that had already been cut out. The reason still appears in `hard_edged_suppressed_notes`, so you can see what was set aside. §29.1

A LOW `change_line_density` or a HIGH `plateau_cliff_ratio` is dispositive; the reverse proves nothing either way, so neither can veto a verdict — they only ever ADD one. The one exception is documented below.

⚠️ **The 3 assets still missed are pixel art whose blocks were softened by re-encoding** (a "flat" block holding `184,159,159` next to `185,161,161`, or blocks separated by 1 px grey seams). If art is a photo mosaic or dither-shaded and the tool says antialiased, check it by eye. Do not reach for a tolerance on the plateau test — it was measured, rescues none of the three, and turns a real antialiased asset into a false positive. §28.3

⚠️ **A source that ALREADY has an alpha channel is measured on an alpha composite, and it has to be.** Antialiasing in an RGBA source lives in ALPHA; reading RGB alone drops the ramp and every measure here then sees a hard silhouette that is not there. Measured on a real RGBA icon: `plateau_cliff_ratio` 0.320 from raw RGB against 0.000 composited. `measured_on_alpha_composite` tells you which happened. Note that a **1-bit-alpha** source (an already-processed GIF from this tool) genuinely IS hard-edged — writing the GIF destroyed the ramp — and nothing can composite that back. §28.5

⚠️ **A low `change_line_density` is set aside when `plateau_cliff_ratio` contradicts it on a decent sample**, because a pixel grid coarse enough to give that density would give plateau-to-plateau edges. A large, simple, flat vector icon can score density 0.447 purely from having little detail. When this fires, the reasoning appears in `hard_edged_suppressed_notes` rather than vanishing. §28.6

⚠️ **The two band-based measures are unreliable when the background is COLOURED rather than white**, because a solid palette colour then becomes indistinguishable from a blend: a solid art colour near the background inflates `ratio`, and a solid colour lying on a background→art line inflates the blend ratio. Measured across 8 real pixel-art assets on coloured backgrounds, **6 were reported as antialiased** — one scoring `ratio` 20.895. Their ranges overlap almost completely on this content. The two block-structure measures show no coloured-background penalty at all, which is what carries detection here. §23, §23.7

⛔ **An ALPHA-ONLY source has no background to remove, and running removal on it EMPTIES THE FILE.** One flat RGB value across the whole canvas with the image carried in the alpha channel — an ordinary way to export a monochrome glyph icon. `detect_bg_color` returns that one colour, so every pixel matches the background and the render deletes everything: measured on a real 512x512 PNG, **69,925 opaque pixels in, zero out**, with `--auto` reporting success because an empty output has no leftover background to count. `--analyze` now reports `alpha_only_source`, every colour rule abstains, `--recommend` returns `not_applicable_reason` instead of a command, `--auto` refuses, and the renderers refuse to write a file in which nothing is opaque. **If you see `alpha_only_source: true`, the answer is that the background is already transparent — there is nothing to remove.** §28.9

**If `appears_hard_edged` is true → use `--pixel-art`** (bundles `--no-feather`, `--edge-cleanup-erosion 0`, and nearest-neighbor resizing into one flag).

If content doesn't fit either bucket well — genuine photographic or full-bleed content with no distinguishable background at all (shows up as the "four corner pixels don't all agree" warning, or an obviously-wrong detected color) — that's a real boundary of what this script does. It performs chroma-key style background removal, not general image segmentation. Say so plainly rather than forcing chroma-key settings onto content that structurally doesn't have a keyable background.

## Animated/rotating content — check this SECOND, right after content type
Everything above is about ART STYLE. This is about ANIMATION STYLE: does the foreground shape's position/orientation change significantly across frames (rotating, tumbling, falling, spinning, translating across a large fraction of the canvas), as opposed to a mostly-static icon with only minor internal motion? Eyeball a handful of widely-spaced frames, not just frame 0. **If yes, several of this skill's normal default assumptions become actively dangerous, not just imprecise.** Confirmed on a real 124-frame tumbling calendar/gamepad icon that took seven full rounds to fully fix — full case history in `references/lessons.md` §10; this is the lean rule.

- **Never derive a fixed-position region (bbox/circle/rect) from one frame and apply it to other frames.** Any region needing frame-specific handling must be re-derived per frame from position-independent signals (size, shape, bordering color) — extends the existing `--protect-region` geometry-mismatch caution (below) to a new axis: position, not just shape.
- **Don't rely on border-touching as "is background"** once the foreground can graze the canvas edge — it can sweep real content into "background" and delete it. Use `--tumble-safe`, which defines background as the single largest connected bg-colored component per frame instead. `--analyze`'s `tumble_risk` field now measures this automatically across every frame (`worst_margin_ratio`, `likely_tumble_risk`) — check it on a new asset instead of eyeballing frames by hand.
- **`--protect-outline-color`'s per-frame enclosure can fail under self-overlapping/rotating geometry** in a way that doesn't trigger the existing flicker/anomaly detection (that detection is for a *different* shape briefly crossing a stable outline, not the outline's own shape rotating — see `references/lessons.md` §10 for why these are genuinely different failure signatures). Each candidate region's `outline_enclosure_all_frames.anomalous_frame_count` now checks this across every frame automatically — nonzero means the outline's own shape is breaking enclosure somewhere, the exact signature this bullet describes. `--tumble-safe` bypasses single-frame flood-fill enclosure entirely for this case; keep using `--protect-outline-color` for the stable-shape-crossed-by-something-else case it already handles well.
- **To selectively remove one small bg-colored region while keeping another** (e.g. a real hole/cutout vs. a same-colored decorative detail), add `--keep-bg-blob-if-near <hex[,hex,...]>` (only valid with `--tumble-safe`), narrowed with `--hole-size-range`/`--hole-max-aspect` to the real target's measured size/shape. **The distinguishing color has no default — identify it manually** the same way outline-color verification's fallback already works: zoom in, sample pixels bordering what should stay vs. what should go, use whatever genuinely differs.
- **If a solid design color might coincidentally sit near the background color** (a pale tint, a shadow/glow shape, a light gradient), add `--protect-band-only <px>` (4px was sufficient on the motivating case) — protects everything except a thin ring around the actual removal, instead of allowlisting specific safe regions, so no future near-background color can be silently mistaken for an antialiasing blend.
- **If a solid-color composite check (not checkerboard) shows speckle/noise on an otherwise-correct edge, try `--dither-mode none`** before assuming it's a mask bug — Bayer dithering can look like noise, not softness, over a flat background.
- **Verify against every frame, not a spot-check sample.** `tumble_risk`, `outline_enclosure_all_frames`, and `band_interior_regions` all scan every frame automatically now (not a sample) — see "Run analysis first" below. Still manually composite against a SOLID-color background in addition to checkerboard (see the Verification section) — that part stays visual. Every bug in this case was localized to specific rotation phases or specific colors; a normal spot-check would not reliably have caught any of them.

## Small removed regions can be inflated by edge-cleanup erosion — check this whenever a fix produces one
This is a separate pitfall from "Animated/rotating content" above, though it was found on the same kind of content (an animated icon) and can compound with it. It applies any time a fix removes a small, isolated bg-colored region — an incidental gap where two independently-moving parts of the SAME icon transiently graze each other (confirmed real case: an animated gear rotating/bouncing near a static book's page edge, pinching off a tiny gap of background at certain frames — nothing to do with a deliberate design hole), not just `--tumble-safe`'s `--keep-bg-blob-if-near` case.

`--edge-cleanup-erosion` (default 2px) shrinks the OPAQUE region uniformly by a fixed pixel count at every boundary, with no regard for how small the removed region on the other side is. That's correct for its intended case (a couple of pixels off a large silhouette's outer edge is proportionally tiny). For a small, isolated removed region well under the erosion radius's own scale, the same operation doesn't trim it proportionally — it consumes the thin opaque wall around it instead, INFLATING it. Confirmed directly: a single original 1px removed pixel became a 49-70px hole after a normal 2px erosion pass — a 50-70x size inflation that turned an imperceptible artifact into a visibly distracting "speckle." A naive fix — just raising the minimum size before a region counts as removable at all — trades this for the opposite failure: the same tiny features now stay solid opaque, which reads as its own kind of visible speckle at exactly the points (like where the gear teeth and book outline nearly touch) a person is most likely to be looking closely. Neither "always remove, let it erode" nor "never remove, leave it solid" is correct — the region needs to be removed at its own true, tiny, native size, un-inflated.

Use `--erosion-exempt-max-size <px>` for this: it excludes any removed region at or below that size from erosion's INPUT entirely (erosion behaves exactly as if it were never flagged as removable, identical to how the surrounding area is normally treated), then restores it to its own exact pre-erosion pixels afterward. This is deliberately not "restore nearby reclaimed pixels after the fact" — that was tried first and was measurably incomplete (a 1px notch still came out ~40-50px) because erosion's actual spillover pattern around a small feature isn't a clean uniform ring, especially near other nearby geometry. Pass a rough ceiling comfortably above the size of incidental noise and comfortably below any genuinely large/visible removed region on the same asset (30px worked on the motivating case, where noise measured 1-11px and the two real gaps measured 69px and 137px). `--analyze`'s `small_removed_regions.suggested_erosion_exempt_max_size` now computes this ceiling from the real region-size histogram on a new asset instead of reusing 30 blindly. Full case history: `references/lessons.md` §11.

## Art that FADES toward the background colour — check this on anything with sparkles, glows or twinkles
Distinct from both sections above, and from the `--dither-mode none` note in "Animated/rotating content." That note is about a correct EDGE looking speckly once composited on flat paint. This is about a large INTERIOR region of the art meshing no matter what you view it over.

GIF has no partial alpha, so an artist's fade-out is flattened against the background at authoring time — a fading element literally becomes progressively paler versions of the background colour. If a fade stage's solid body colour lands inside the feather band (`--tolerance` to `--tolerance x --feather-band-multiplier`, Euclidean RGB distance), the script assigns it partial alpha and dithers it, and a spatial dither across a solid interior reads as a **visible grid/mesh**, not as translucency. Confirmed real case: a sparkle whose mid-fade body is `fff2d1`, distance 47.8 from white, inside the default 15–60 band.

- **Detect it before delivering:** `--analyze`'s `band_interior_regions` measures this automatically — grouped across every frame and classified `gradient_fade` vs `solid_tint`, with a plain-language `recommendation` per region. A thin edge band is normal; an interior `gradient_fade` region is the signature.
- **The real fix is to stop using GIF.** If the deliverable can be WebP or AVIF, use `--recover-fade-alpha` with a `.webp`/`.avif` output: it reconstructs the original alpha exactly rather than approximating it, and the fade renders as actual translucency. **No GIF setting can represent a fade correctly** — on the confirmed case the fade's colour-distance range (36→146) straddled a solid art colour at 121.7, so no feather band separates them. See the "Output format" section below and `references/lessons.md` §16.
- **If it MUST be a GIF, fix with `--dither-mode none`** — hard 50% cutoff on the already-defringed alpha. On the real case, faded bodies went from 47–68% opaque to 95–96%. Faintest stages drop out a beat earlier instead of meshing, which is the right trade.
- **Price it first: `--dither-mode none` changes EVERY edge in the file.** It was nearly free on an icon whose silhouette is mostly straight lines (`edge_hardness` 0.506) — verified by zooming the outer silhouette before and after. On curve-heavy art, measure narrowing `--feather-band-multiplier` instead. Full case history: `references/lessons.md` §12.

## Output format: GIF vs WebP vs AVIF vs APNG — decide this BEFORE tuning anything
The output container is chosen by the output filename's extension (or `--format`). It is not a late packaging detail: it decides whether partial transparency is even representable, and therefore whether several of this skill's other rules apply at all.

- **GIF** — 1 bit of alpha. Every pixel is fully opaque or fully transparent. Correct when the deliverable must be a GIF; everything about feathering, Bayer dithering and `--dither-mode` exists to cope with that limit.

  ⚠️ **A GIF cannot hold a frame in which every pixel is transparent** — Pillow's writer emits an unreadable block there and the file TRUNCATES at that frame. Measured on an asset whose subject leaves the canvas: **85 of 123 frames written, 1700ms of 2920ms**, reproduced at defaults, under `--quantizer pngquant` and under `--dither-mode none` alike, so no flag avoids it. `--analyze` reports `has_fully_transparent_frame` and the offending indices, `--recommend` steers to WebP/APNG, and the render **refuses** rather than writing the truncated file; `--allow-truncating-gif` overrides if a truncated GIF really is preferable to none. Do not work around it by duplicating the previous frame — that was tried and produces a visible stall.
- **APNG** — 8-bit alpha, lossless, no plugin needed (`.apng` or `.png`, or `--format apng`). Pillow's PNG writer has always handled it, so unlike AVIF it cannot fail on a missing dependency. It is the LARGEST of the three 8-bit containers, so reach for it when the destination wants PNG specifically rather than as a default. A single-frame source writes an ordinary static PNG under the same extension. `--target-kb` drives it through the same resolution/frame cascade, minus the quality rung — APNG has no quality knob.
- **Making something SEE-THROUGH rather than kept or removed** — `--translucent-region` (same `circle:cx,cy,r` / `rect:x,y,w,h` `;`-separated syntax as `--protect-region`), with `--translucent-alpha` (0.0-1.0, default 0.35) and `--translucent-color` (defaults to the background colour). For glass, a window, a transparent bag: art where one colour is background HERE, opaque design THERE, and translucent material somewhere else. It has to be named by hand, and `references/lessons.md` §27 has the measurement showing why — on the asset it was built for, the see-through pocket and the opaque one are byte-identical white AND both fully enclosed by the same outline, so neither colour nor connectivity can tell them apart. Requires an 8-bit-alpha container. Only lowers alpha that is already opaque, and only on pixels matching `--translucent-color`, so a coarse rectangle does not also dissolve the contents.
- **WebP** — 8-bit alpha. Use `--webp-lossy` only when fitting a byte cap: at native resolution lossy is *bigger* than lossless on flat vector art (measured 2675 KB at q85 vs 2114 KB lossless), though the ordering reverses once downscaled (at 128px: 650 KB lossy vs 1190 KB lossless). `--bayer-size` (GIF, `--dither-mode bayer`) defaults to **8** — 64 threshold levels against 4×4's 16, tracking the intended alpha 2.5× more closely at identical temporal stability. Pass `4` to reproduce pre-v5.0.0 output byte-identical. Error-diffusion dithers (Floyd–Steinberg, Jarvis, Sierra, Stucki) are deliberately NOT offered for alpha: measured, Floyd–Steinberg changed 8.1% of pixels in a region byte-identical between frames — visible crawl on every edge — where both Bayer sizes changed 0.

  `--edge-cleanup-erosion` now resolves its default by context: **0** for WebP/AVIF (8-bit alpha needs no fringe trim), **1** under `--dither-mode none` (no Bayer noise to trim, and 2 deletes thin strokes), **2** for the Bayer path. ⚠️ Do NOT use `--verify`'s `looks_fringed` to pick this — it reported False at every erosion level including one with a clearly visible fringe. Measure the outer opaque ring instead (`references/lessons.md` §16).

  `--webp-method` defaults to **2** — measured across 5 real assets, m2 costs 0.6–8.3% more bytes than m4 for ~2× the speed. **Do not raise it to 6** (45× slower for 2.3% smaller). Method 0 is faster still but its size cost is wildly content-dependent (+134% on one asset, +14% on another) — measure before using it.
- **AVIF** — 8-bit alpha, and roughly **3× the frame budget of WebP under a hard byte cap**: all 124 frames of a real asset fit Discord's 256 KB emoji limit at 128×128, where WebP had to drop to 42. ⚠️ `--avif-quality 100` is NOT lossless and produces the largest file of all — never use it as a "best quality" knob.

**Decision procedure** (measured on 5 real assets — the direction generalises, the exact numbers do not, so measure rather than quoting a ratio):
1. **Full fidelity / "no compression"** → WebP lossless (`-m 2`). The only bit-exact option; AVIF has no true lossless mode.
2. **Full resolution, minor optimization** → AVIF q85. Smaller than WebP lossless on every asset tested, but by anywhere from 28% to 72%.
3. **Hard byte cap (e.g. Discord's 256 KB emoji)** → AVIF at 128×128, keeping every frame, trying q85 then q70. All five test assets fit that way — two at q85, three at q70. `--target-kb` runs this cascade for you. Must ship a GIF →
accept the 1-bit-alpha consequences and read the fade section above.

⚠️ **Platform acceptance is not playback.** A platform listing a format as an accepted upload type does not prove its clients animate it inline — verify with a real upload before shipping. (Discord accepting *and animating* AVIF emoji was confirmed by real test, not assumed.)

⚠️ **`--verify` skips EVERY pixel check when the output was cropped or resized** (it says so in a `note` field and reports only timing). A pass from a cropped output is therefore vacuous — re-render at the source canvas size and verify that, then crop. Confirmed 2026-08-17: the delivered `military-tag` output is 536x570 against a 640x640 source, so its clean `--verify` had substantiated nothing at all. §22

## Workflow: `--auto` first, manual only when it cannot decide
Don't open by asking the user to specify the background color and protected region from scratch, and don't hand-assemble flags before trying the path that assembles them for you.

**INPUT formats — verified end to end 2026-08-17, not assumed:**

| source | status |
|---|---|
| animated GIF | ✅ the original path |
| animated WebP | ✅ renders to WebP and to GIF; `--analyze` reads all frames |
| animated AVIF | ✅ same reader |
| **animated PNG (APNG)** | ✅ 24/46/50-frame files, palette and RGB modes |
| **static PNG / JPEG** | ✅ treated as a one-frame animation; output to GIF, WebP or AVIF |

The reader is `Image.open` — format-agnostic, so anything Pillow decodes works. ⚠️ **The skill's NAME is historical; this is not a GIF-only tool.** Two crashes on non-GIF sources were fixed the day this was written: a static JPEG had no `n_frames` attribute, and an RGB-mode APNG stores `transparency` as a colour TUPLE rather than a palette index, which raised a broadcast error.

⚠️ **OUTPUT is GIF, WebP, AVIF or APNG.** This line used to say APNG output was a gap; v5.4.0 closed it (`--format apng`, or a `.apng`/`.png` extension) and the sentence went stale one release later, contradicting the format table above it.

⚠️ **A photograph is still out of scope.** This is chroma-key removal against a flat, keyable background — static-image support means a one-frame DESIGN, not general subject segmentation.

**The INPUT may be an animated GIF, WebP or AVIF** — the reader is format-agnostic, and every mode (`--analyze`, `--recommend`, `--verify`, `--auto`, plain rendering) works on all three. The skill's name is historical; it is not a GIF-only tool. Verified end to end 2026-08-17: a WebP source renders to both WebP and GIF, and `--analyze` reads its 124 frames correctly.

⚠️ **If the SOURCE is a WebP or AVIF rather than a GIF**, read `references/lessons.md` §17 before trusting any timing. Pillow populates `info['duration']` during `seek()` for GIF but only during `load()` for WebP/AVIF, so a seek-only read returns the PREVIOUS frame's value — a real 124-frame source came back one bogus frame prepended and the last dropped, 240 ms short, while the script reported "durations preserved exactly". Fixed in the script, but the failure mode is worth recognising if you see it anywhere else.

### 0. Start with `--auto` unless a check below says otherwise
```
python scripts/remove_gif_background.py <input.gif> <output.gif> --auto
```
`--auto` runs `--recommend`, applies its flags **only where you left that option at its default** (anything you pass explicitly wins, and it prints what it skipped), renders, then RE-MEASURES the written file and re-renders once if the encoded result disagrees with the pre-encode calibration. It is **two passes, not a loop** — no iteration construct, no counter, worst case two renders and exactly one correction. Add `--auto-erosion` to have `--edge-cleanup-erosion` calibrated against the asset's own fringe curve rather than a global default.

⚠️ **`--auto` does not replace the two checks above it.** Content type and animation style decide whether the defaults are safe *at all*, and `--auto` cannot tell you that a pinhole needs `--hole-size-range` (§14) or that a sub-region needs `--remove-region` (§15). Run those checks first; use `--auto` as the starting point for everything they do not flag, and go manual for what they do.

### The manual path — when `--auto` is refused, overridden, or the checks above flagged something

### 1. Run analysis first
```
python scripts/remove_gif_background.py <input.gif> --analyze
```
For a ready-to-confirm suggestion instead of reasoning across `--analyze`'s fields by hand, use `--recommend` — it runs `--analyze` internally and returns `suggested_command` plus an `evidence` list justifying each flag:
```
python scripts/remove_gif_background.py <input.gif> --recommend
```
Returns JSON with:
- `detected_bg_color` — auto-sampled from the corner pixels.
- `candidate_regions` — background-colored areas enclosed by other colors somewhere in the animation, each with:
  - `enclosure_ratio` — fraction of sampled frames where it's actually enclosed. `>= 0.9` → `likely_intentional_design: true` (keep it). Occasionally enclosed (e.g. an animated swoosh temporarily cutting off a pocket of background) → should stay transparent.
  - `suggested_protect_region` — a ready-to-use `circle:cx,cy,r` value.
  - `candidate_outline_color` — a guess at a bordering outline color (a hint, not a fact — see `outline_color_verified` below).
  - `outline_color_verified` — `true` only if the color was actually simulated (built its mask, ran `binary_fill_holes`, confirmed it truly encloses the region) rather than guessed. Treat `candidate_outline_color` as unusable when `false`.
  - `outline_enclosure_all_frames` — the same simulation re-run across EVERY frame, not just the one it was first verified on. `anomalous_frame_count == 0` means the outline holds everywhere; nonzero is the rotating/self-overlapping-geometry failure described above under "Animated/rotating content" — treat `outline_color_verified: true` with a nonzero count here as NOT safe to use unreviewed.
  - `outline_background_leak` — `over_protects_background: true` means this outline color's flood-fill also swallows real background somewhere, not just the intended interior — don't use it even if otherwise verified.
  - `circularity_ratio` (0-1) and `circle_region_safe` — how well a plain circle approximates the region's true shape. Low values mean scalloped/pointed/star-shaped outlines, where `--protect-region circle:...` is a poor fit (see "Run the real processing" below).

Warnings worth reading from stderr:
- If the four corner pixels don't unanimously agree on a background color, double-check `detected_bg_color` looks right.
- If the source GIF already has its own transparency index, its pre-existing transparent pixels are carried through automatically — no action needed, the `source_has_pre_existing_transparency` field and a printed NOTE just flag that it's happening.

### 2. Form a recommendation, then confirm with the user in one short message
Check `edge_hardness` first — if hard-edged, mention `--pixel-art` up front rather than as an afterthought.

Summarize what was found in plain language, e.g.:
> "Looks like white is the background. There's also a white/light area in the middle of the badge enclosed by a ring — that's enclosed in 100% of frames, so it looks intentional and I'd keep it. There's also a gap between the ribbon tails that's occasionally enclosed by an animated swoosh (~20% of frames) — that looks incidental, so I'd treat it as background. Sound right, or should I handle either differently?"

Use a short multiple-choice confirmation (one question, options like "Keep it opaque" / "Make it transparent" per region) when there are multiple regions, rather than a wall of text. Only skip confirmation entirely if there's exactly one obvious candidate region with `enclosure_ratio` at or near 1.0 and the user's request already implied preserving an interior highlight.

**Multiple candidate regions with different outline colors are common** (e.g. a badge with both a ring interior AND a separate gear/hole cutout, each outlined differently) — a real case, not hypothetical. When two or more come back `outline_color_verified: true`, do NOT run the script once per color (a second run has no memory of what the first protected). Pass `--protect-outline-color` ONE time with all verified colors joined by a comma (e.g. `--protect-outline-color c8dcf0,8cb4f0`) — the script unions every color's enclosed region in a single pass. Same idea for `--protect-region` if needed for more than one region, joined with `;` instead (since `,` is already used inside a single region's own coordinates).

### 3. Run the real processing with confirmed settings

**`--protect-outline-color` is the default choice. `--protect-region` is a last resort, not an alternative style** — reach for it only when there is genuinely no usable outline color, and even then treat the result as provisional until step-by-step verified (below). A fixed-radius circle/rect almost never matches a real icon interior's true (usually irregular) shape — two real, initially-unnoticed bleeds/gaps from exactly this are documented in `references/lessons.md` §2. Concretely:
- **Always try `--protect-outline-color` first** using the analyzed `candidate_outline_color` IF `outline_color_verified` is `true` AND `outline_enclosure_all_frames.anomalous_frame_count == 0` AND `outline_background_leak.over_protects_background` is `false` — that's the exact gate `--recommend` applies before suggesting the flag, safe to use directly when all three hold.
- **If `outline_color_verified` is `false`**: don't fall back to `--protect-region` yet. Open the source frame yourself and identify the true enclosing outline color by eye — sample a pixel a short distance outward from the protected area in a couple of directions and check they agree — then use that with `--protect-outline-color`. Cheaper than debugging a bleed after the fact.
- **Only use `--protect-region`** when there's truly no enclosing outline (a soft glow/gradient with no hard edge) — and check `circularity_ratio` / `circle_region_safe` first. If `circle_region_safe` is `false`, either use `rect:` if the true shape is axis-aligned rectangular, or warn the user this region's protection may not be pixel-perfect and needs extra-careful verification.
- A region the user wants left as background needs nothing extra — it's already removed by default.
- **If two different design features are enclosed by the SAME outline color but need opposite treatment** (one kept, one removed — e.g. a highlight star and a separate pin/grommet hole both ringed in the same navy), that's not a bug in `--protect-outline-color` (it correctly unions the whole area one color encloses); run it as normal, then carve the unwanted sub-region back out with `--remove-region` (below). Confirmed real case: `references/lessons.md` §15. **`--remove-region` is a STATIC mask, same caution as `--protect-region`** — do not use it alone on a target that moves/resizes across frames without re-deriving the region per frame yourself first (confirmed: a static circle missed the true target in 76% of frames on a real tumbling asset). For a moving target with no external per-frame tracking available, `--tumble-safe` + `--keep-bg-blob-if-near` with a tight `--hole-size-range`/`--hole-max-aspect` (§14) is the more robust choice when the hole and the decoration differ measurably in size or aspect across the whole animation — check `references/lessons.md` §14 vs §15 for which fits.
- If `--bg-color` wasn't confirmed differently, omit it — auto-detected the same way `--analyze` does.
- **Edge feathering is ON by default; cropping is NOT.** Feathering is a pure quality improvement, so it stays on unconditionally. Cropping, resizing, frame-dropping, and gifsicle are opt-in via `--compress` tiers (see below) — a plain run changes nothing about canvas, frame count, or timing.

```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    [--bg-color <hex>] \
    [--protect-outline-color <hex[,hex,...]>] \
    [--protect-region circle:cx,cy,r | rect:x,y,w,h [;more-regions]] \
    [--remove-region circle:cx,cy,r | rect:x,y,w,h [;more-regions]] \
    [--remove-region-feather 1.5] \
    [--tolerance 15] [--outline-tolerance 40] \
    [--feather-band-multiplier 4.0] [--no-feather] \
    [--edge-cleanup-erosion 2] [--pixel-art] \
    [--crop] [--frame-stride 1] [--resize-max-dim <px>] \
    [--compress optimize|medium|heavy] \
    [--quantizer pil|pngquant] \
    [--target-kb <n>] [--preview <path.png>]
```
For several GIFs in one invocation, see "Batch processing" below — a JSON manifest, not more CLI flags.

*(`--no-gifsicle-optimize` also exists in `--help` output but isn't listed above — it's a confirmed no-op, kept only for backward compatibility with old invocations now that gifsicle only ever runs as part of a `--compress` tier. Don't spend time trying to use it for anything.)*


**Output quality/encoder knobs**: `--webp-quality` / `--webp-method` / `--webp-lossy` (WebP), `--avif-quality` (AVIF), `--quantizer pil|pngquant` (GIF palette), `--remove-region-feather` (softness of a `--remove-region` cut), and `--erosion-exempt-transient` (exempt small removed regions from erosion by IDENTITY rather than size — use it when design and incidental regions OVERLAP in size, which a size threshold structurally cannot separate). Defaults are tuned; reach for these only with a measured reason.

**What the individual quality/output flags actually do** — edge feathering and `--feather-band-multiplier`, standalone `--crop`, the printed size report, and `--preview` contact sheets — **is in `references/flag-reference.md`.** Read it when a flag's name is not enough to know whether you want it.

## Delivery file naming, when reprocessing the same source
If a user reports a problem and asks for a fix, name the corrected file so its iteration is obvious rather than silently overwriting: first attempt `name_transparent.gif`, a fix `name_transparent_v2.gif`, `_v3.gif`, and so on. Independent from the skill's own version number above.

## Verification (always do this before delivering the result)
Run `--verify` first — it covers the mechanical half of the checks below (leftover background, protected-region coverage, edge fringe, small-region inflation, duration/frame-count) across every frame automatically:
```
python scripts/remove_gif_background.py <input.gif> <output.gif> --verify
```
It does NOT replace the visual checks (soft-vs-jagged edges, a `--protect-region` bulge following the art's own silhouette) — those still need a human/agent's eyes, below.

**For animated/rotating content (see that section above), do two things more thoroughly, not skip them:** `--verify` already checks every frame automatically (not a first/middle/last sample) for the fields below — the bugs in `references/lessons.md` §10 were each localized to specific rotation phases, which only a full-frame check reliably catches. Still manually composite against a SOLID flat color (e.g. pure green) at least once, not just checkerboard — checkerboard camouflages dithering noise and unstable partial-alpha artifacts the same way it camouflages soft bleed (point 2 below), and both need checking, each catches what the other hides.

1. `--verify`'s `leftover_background_opaque_px`, `protected_region_coverage`, and `edge_fringe_check.looks_fringed` now mechanically cover: background fully transparent everywhere it should be, the protected interior region fully opaque with no holes, and the outermost opaque ring being the TRUE art color rather than a lighter/tinted fringe left by imperfect color-unmixing (the default `--edge-cleanup-erosion 2` exists to prevent this; if `looks_fringed` is still true, pull actual edge pixel values rather than cranking erosion blind). What's left to check by eye: composite a handful of frames (first, middle, last, plus any frame flagged near a protected region) over a dark background — `--preview <path.png>` does this automatically — and check edges look soft/dithered, not jagged (zoom into a diagonal/curved edge). **If the source canvas is small (roughly under 200px on its shorter side), also check fine details (thin strokes, small dots, small gaps) survived the default erosion** — `--edge-cleanup-erosion`'s 2px default is a FIXED pixel count, not scaled to resolution, so a detail comfortable on a 640px icon can be nearly erased on a 128px one. The script warns to stderr when this situation is detected — don't ignore it; redo with `--edge-cleanup-erosion 1` or `0` if a detail got eaten.
2. **If you used `--protect-region` (circle or rect) anywhere, specifically look for a bulge, halo, disc, or straight edge that doesn't follow the artwork's own silhouette** — the signature of a mismatched protect-region, easy to miss on a quick glance (see `references/lessons.md` §2 for two real cases that slipped past an initial check). `--verify`'s `leftover_background_opaque_px` and `protected_region_coverage` now catch most of this mechanically; also composite over a plain dark background (not checkerboard, which can camouflage a soft-edged bleed) and check the protected area's outline traces the actual art. Disagreement of more than a few pixels in any direction → switch to `--protect-outline-color`.
3. **Duration/frame-count**: `--verify`'s `timing` field (via `describe_written_timing`) and `frame_alignment` cover this mechanically now — trust its verdict over comparing frame counts by eye. **A lower output frame count is not automatically a bug**: Pillow's encoder coalesces consecutive frames that come out byte-identical after quantization and folds their delays into the survivor (confirmed real case: 170 in, 168 out, nothing visually lost). Total playback length changing is the real defect signal, frame count alone is not — the `timing` field's verdict already reflects this distinction. Full Pillow-duration-read footgun and raw-bytes ground-truth method: `references/lessons.md` §9 and §13.
4. If a `--compress` tier or standalone `--crop` was used, confirm the crop removed the intended blank margin without clipping the design — check the `WxH -> W'xH'` line the script prints to stderr. If resize also ran, check final dimensions match the expected max-side target. (`--verify` skips its pixel-position checks entirely when input/output dimensions differ — see its `note` field — so this one stays manual.)
5. **When investigating a reported flicker/gap complaint, use the actual geometric interior mask, not a bounding-box sample** — `--verify`'s own `protected_region_coverage` already does this internally (a real per-frame enclosed-region footprint, not a bbox rectangle), so a `looks_unprotected` finding from `--verify` is trustworthy as-is; this matters if you're hand-rolling a check instead. See `references/lessons.md` §9 for a real case a bbox-based check false-positived on. If the flicker is real, the root cause and fix live in §3, not §9 — start by sampling the outline color itself on a good frame vs. a bad one: fading toward background → widen `--outline-tolerance` first; replaced by an unrelated solid color → occlusion, the built-in detection/substitution is the right tool.
6. If anything fails verification, adjust `--tolerance` / `--outline-tolerance` / `--feather-band-multiplier` or the protect region and rerun — don't patch the output GIF directly.

## File-size optimization: default vs. named tiers
**The default output is plain background removal, plus one correctness fix, nothing else.** No crop, resize, frame-drop, or gifsicle pass — every frame and its exact timing survive untouched at the original canvas size. The one exception is `--edge-cleanup-erosion` (default 2px): not a size tradeoff, it's fixing a real color artifact in the feathering math, so it applies regardless of any `--compress` tier.

### When to raise file-size optimization at all
Don't ask by default on every request — do ask when there's a reasonable signal it matters: the user mentioned a platform with known constraints (Discord stickers = 256KB, exact error `[50138]... 262144` bytes; Slack emojis; a CMS upload limit), the printed size is large enough that a common constraint would plausibly bite, or the phrasing suggests a specific destination ("for my Discord server", "as a sticker"). Otherwise just deliver the plain file. When you do ask, keep it short: "This came out to 2.7 MB — want me to optimize it for a specific target, like Discord's 256KB sticker limit?"

### The three named tiers (`--compress optimize|medium|heavy`)
Each is a fixed, tested bundle, not independent flags to mix by hand. `medium`/`heavy` include every `optimize` step, then add more:

| Step | `optimize` | `medium` | `heavy` |
|---|---|---|---|
| Frame-stride | — (every frame kept) | 2 | 2 |
| Crop to transparent bounds | Y | Y | Y |
| Resize to fit (longer side) | 512px | 512px | **256px** |
| 1px edge erosion | Y | Y | Y |
| `gifsicle -O3` | Y | Y | Y |
| `gifsicle --lossy` | — | 30 | 80 |
| Color palette | native | **200 colors** | **128 colors** |
| Dithering | — | Floyd-Steinberg | Floyd-Steinberg |

`optimize` deliberately keeps every frame — it's for someone who wants a smaller file with zero motion-quality tradeoff (crop/resize/erosion/lossless gifsicle only touch redundant/invisible data). Frame-stride is a real, visible tradeoff (choppier playback), reserved for `medium`/`heavy`. If `optimize` alone isn't enough, step up a tier rather than adding standalone `--frame-stride` on top of `optimize`.

**If someone reports fine details looking "grainy," "messy," or not matching the original after `medium`/`heavy`, step DOWN to `optimize` first** rather than tweaking dither/color-cap settings — thin design elements (a lightning bolt, a small icon detail) are proportionally mostly edge transition, so even `medium`'s relatively light 200-color dithering can visibly wreck them (confirmed: 100+ unique colors in a thin region under `medium` vs. 3 under `optimize` on identical content). `optimize` also keeps every frame by default, so it's often a single fix for both a graininess and a choppiness complaint at once. Full measurement details and the reasoning behind each tier's specific choices (why 200 vs. 128 colors, why frame-stride waits for `medium`, and why Floyd-Steinberg dithering was REMOVED from both tiers in 2026-08-19 after it lost on size, colour error and frame-to-frame stability alike) are in `references/lessons.md` §6 and §30.

Order steps actually run in: frame-stride → crop → resize → erosion → render → gifsicle (gifsicle is always last regardless of tier, since it needs an already-encoded file; `optimize` simply skips frame-stride).

Practical notes:
- All three tiers keep alpha clean (binary 0/255, transparent corners) — confirmed at every tier on real test files.
- An explicit `--frame-stride N` overrides a tier's own default (1 for `optimize`, 2 for `medium`/`heavy`) rather than stacking with it.
- If `gifsicle` isn't available, the non-gifsicle parts of a tier still apply, with a clear warning that gifsicle-dependent size reduction didn't happen — never a silent partial failure.
- Always check the actual result after a tier — `heavy` is a real quality tradeoff (256px cap, 128 colors), for a strict platform limit, not a default reach.
- **The GIF palette is built ONCE across all frames combined, not independently per frame.** An independently-quantized per-frame palette can assign different indices to the same visual color across otherwise-static frames, defeating disposal-based frame-diffing — confirmed a real case where fixing this dropped output size ~40% (from ~50% LARGER than source to smaller than it). If a future edit to `render_frames_to_gif` reintroduces a per-frame `convert('P', palette=Image.ADAPTIVE, ...)` call instead of one shared palette, treat that as a regression.
- **gifski** (external, quality-based re-encode after transparency is finalized) beat this script's own tiers in one confirmed real case where smooth motion mattered more than absolute minimum size — not integrated into this script yet. See `references/lessons.md` §8 before reaching for `--compress heavy`/aggressive `--frame-stride` on a "keep it smooth" ask.


**The standalone levers — `--frame-stride`, `--resize-max-dim`, and automatic `--target-kb` fitting — plus their measured case histories, are in `references/compression.md`.** Read it when a tier alone is not the right answer: the user wants only a frame-rate cut, only a resize, or a hard byte target.

## Batch processing multiple GIFs
```
python scripts/remove_gif_background.py --batch manifest.json --compress optimize
```
Manifest is a JSON list, each entry needs at least `"input"`/`"output"`:
```json
[
  {"input": "seal.gif", "output": "seal_out.gif", "protect_outline_color": "1a2b3c"},
  {"input": "star.gif", "output": "star_out.gif"}
]
```
**Per-file settings go in the manifest, shared settings go on the command line.** `--compress optimize --edge-cleanup-erosion 1` alongside `--batch` applies to every file unless an entry overrides it. But don't put `protect_outline_color`/`bg_color` on the shared command line expecting it to apply everywhere — those almost always differ art to art, so they belong per-entry, found the normal way (`--analyze` each file first — batch mode doesn't skip that step). Manifest keys match this script's flag names with underscores instead of dashes.

One job failing doesn't abort the rest — it's reported in the summary table at the end. Check that summary before telling the user the batch is done.
