# GIF Background Remover — Lessons, Postmortems & Tool Evaluations

This file holds the full evidence trail behind SKILL.md's rules: bug postmortems, tool evaluations, and measured numbers from this skill's real development history. SKILL.md states the resulting *rule* concisely and points here; this file has the *why*, including approaches that were tried and reverted — read those before re-attempting them.

**When to read this file:** before re-diagnosing anything that smells like a past case (flicker or a gap in a protected region, erosion eating fine detail, jagged edges surviving a resize, a wrong animation-length claim, a "grainy/messy" complaint after compression, a which-tool-or-quantizer question). Check the table of contents below for a matching section first. This history is long and specific, and several fixes were tried, looked right, and later regressed — re-deriving one from scratch risks retrying an approach already known to fail.

## How to read this file — do NOT read it whole

It is ~56,000 tokens across 28 sections. The median section is ~1,100 and the largest ~8,000. **Find the one section you need and read only that**; reading the file end to end costs roughly 40x what the answer costs.

Three routes, cheapest first:

1. **Symptom table below** — scan it for something resembling what you are seeing, then jump to that section.
2. **Grep for the symptom in your own words.** Prose here is soft-wrapped (one line per paragraph) specifically so that multi-word phrases match on a single line:
   ```
   grep -n "whitish fringe" references/lessons.md      # or: rg -n "whitish fringe"
   ```
3. **Extract one section by number**, without loading the rest:
   ```
   python3 -c "import re,sys;s=open('references/lessons.md').read();print(re.search(r'^## 16\..*?(?=^## \d+\.|\Z)',s,re.M|re.S).group(0))"
   ```

**Long sections have numbered sub-anchors** (`§16.5`, `§21.4`, `§23.4`, `§26.5` …), so you can extract a part rather than the whole. §16 alone is ~6,500 tokens across 21 sub-anchors; one of them is usually what you actually want:
   ```
   python3 -c "import re;s=open('references/lessons.md').read();print(re.search(r'^### 16\.5 .*?(?=^### |\Z)',s,re.M|re.S).group(0))"
   ```

If you are about to re-diagnose something that smells like a past case — a fringe, a flicker, erosion eating detail, a wrong duration, a tool-or-quantizer question, a check that disagrees with your eyes — spend one grep here first. Several fixes in this history were tried, looked right, and later regressed; re-deriving one from scratch risks repeating that.

## Table of contents
1. [Edge-hardness caveat: geometry-heavy false positives](#1-edge-hardness-caveat-geometry-heavy-false-positives)
2. [Why `--protect-region` is a last resort](#2-why---protect-region-is-a-last-resort)
3. [Protected-region flicker: three implementation attempts, then v2 detection](#3-protected-region-flicker-three-implementation-attempts-then-v2-detection)
4. [`--edge-cleanup-erosion 0` total-destruction bug (fixed in v2.1)](#4---edge-cleanup-erosion-0-total-destruction-bug-fixed-in-v21)
5. [Reduced erosion & resize degradation on thin/geometry-light icons](#5-reduced-erosion--resize-degradation-on-thingeometry-light-icons)
6. [Tools considered: gifski and pngquant](#6-tools-considered-gifski-and-pngquant)
7. [GIF format has no partial transparency](#7-gif-format-has-no-partial-transparency)
8. [gifski as a compression-tier alternative (not yet integrated)](#8-gifski-as-a-compression-tier-alternative-not-yet-integrated)
9. [Verification pitfalls: Pillow's `ImageSequence.Iterator`, bbox-vs-mask, frame-offset drift](#9-verification-pitfalls-pillows-imagesequenceiterator-bbox-vs-mask-frame-offset-drift)
10. [Animated/rotating content: four related failures on a tumbling icon, seven rounds to fully fix](#10-animatedrotating-content-four-related-failures-on-a-tumbling-icon-seven-rounds-to-fully-fix)
11. [Small removed regions get inflated by edge-cleanup erosion: a second animated-icon case, five rounds](#11-small-removed-regions-get-inflated-by-edge-cleanup-erosion-a-second-animated-icon-case-five-rounds)
12. [Art that fades toward the background colour renders as a dither mesh](#12-art-that-fades-toward-the-background-colour-renders-as-a-dither-mesh)
13. [The save message asserted a frame count it never read back](#13-the-save-message-asserted-a-frame-count-it-never-read-back)
14. [Punching one same-colour interior hole while protecting a same-colour, same-size-range animated design element](#14-punching-one-same-colour-interior-hole-while-protecting-a-same-colour-same-size-range-animated-design-element)
15. [A second, independent solution to §14's same problem — `--remove-region`, and where it needs help](#15-a-second-independent-solution-to-14s-same-problem---remove-region-and-where-it-needs-help)
16. [Escaping GIF's 1-bit alpha: recovering a baked-in fade, and WebP/AVIF output](#16-escaping-gifs-1-bit-alpha-recovering-a-baked-in-fade-and-webpavif-output)
17. [A WebP source silently shifted every frame duration by one](#17-a-webp-source-silently-shifted-every-frame-duration-by-one)
18. [Closing the autonomy backlog: four recommendations that were wrong, and why](#18-closing-the-autonomy-backlog-four-recommendations-that-were-wrong-and-why)
19. [`--auto`: verifying the OUTPUT, and calibrating each asset against itself](#19---auto-verifying-the-output-and-calibrating-each-asset-against-itself)
20. [Auditing §19: five defects found by reviewing my own work](#20-auditing-19-five-defects-found-by-reviewing-my-own-work)
21. [Four verification defects, and exempting by identity instead of by size](#21-four-verification-defects-and-exempting-by-identity-instead-of-by-size)
22. [Closing §14 on its own asset: the residual was the cutout, and 519 vs 371 measured](#22-closing-14-on-its-own-asset-the-residual-was-the-cutout-and-519-vs-371-measured)
23. [`edge_hardness` fails on pixel art with a coloured background — 6 of 8 real assets](#23-edge_hardness-fails-on-pixel-art-with-a-coloured-background--6-of-8-real-assets)
24. [Two defects that only exist in the deployment environment](#24-two-defects-that-only-exist-in-the-deployment-environment)
25. [`--tumble-safe` strands the background it does not own — 56% left behind](#25---tumble-safe-strands-the-background-it-does-not-own--56-left-behind)
26. [A degenerate outline candidate won selection, so a design region got no protection at all](#26-a-degenerate-outline-candidate-won-selection-so-a-design-region-got-no-protection-at-all)
27. [Three roles for one colour: the structural route measured and ruled out](#27-three-roles-for-one-colour-the-structural-route-measured-and-ruled-out)
28. [The fifth pixel-art discriminator, and what the first four never tested](#28-the-fifth-pixel-art-discriminator-and-what-the-first-four-never-tested)

**Symptom → section**, for scanning without reading the full ToC titles:

| If you're seeing... | Go to |
|---|---|
| Pixel art misdetected as antialiased (or vice versa) | §1 |
| A bulge/halo/gap that doesn't follow the art's silhouette | §2 |
| Flicker or a hole in a protected region | §3 (real bug) or §9 (bbox-vs-mask measurement artifact — check which first) |
| A shape totally erased / near-zero survival | §4 |
| Blurry or degraded fine detail after resize/compress | §5 |
| A fade/glow/sparkle that ends as an opaque pale blob, or pops out abruptly | §16 (GIF cannot hold it — change format) |
| Scattered speckle dots where a fading element disappears | §16 |
| A WebP/AVIF whose partial alpha vanished after a resize | §16 |
| Choosing between compression tools/quantizers | §6, §8 |
| claude.ai refuses the skill upload | the description exceeds its 1024-char limit (§24 — the development repo's doc-audit gate enforces it) |
| "there's a white edge / outline / halo around it" | §16 (fringe), §19 (pick erosion by the asset's own curve) |
| "it looks blurry / soft / smudged after resizing" | §5 (resize degradation), §1 (is it pixel art?) |
| "the colours look wrong / washed out / banded" | §12 (dither mesh), §6 (quantizer choice) |
| "it's too big" / "it won't upload" / a platform size limit | §8, and SKILL.md's compression tiers |
| "it looks chunky / blocky / like it lost detail" | §4, §5 (erosion eating detail), §1 (pixel art misdetected) |
| "part of the picture disappeared" | §3 (protected-region flicker), §10 (tumbling content) |
| "it plays too fast / too slow / is cut short" | §13, §17 (duration read from the wrong frame) |
| "the see-through part went solid" or a glow turned opaque | §16 (GIF cannot hold it — change format) |
| Output is shorter than the source, or "durations preserved exactly" is a lie | §17 (non-GIF SOURCE: Pillow needs load(), not seek()) |
| `--recommend` suggested a flag that made the output worse | §18, §20 (four wrong recommendations and why) |
| A flag had to be tuned by hand to get a good result | §18 (the gap is the bug — the tool should derive it) |
| Choosing `--edge-cleanup-erosion`, or `--auto` picked a surprising one | §19 (calibrated against the asset's OWN curve) |
| Reviewing your own just-finished work | §20 (five defects found exactly this way) |
| `--verify` flags something you believe is correct | §21 (footprint defects), §22 (`residual_nonopaque`) |
| A check passes but the number looks implausible | §20 (a passing test with a wrong number IS a failing test) |
| Something works here but might not in the claude.ai sandbox | §24 (two defects invisible from the repo) |
| `--recommend`'s command fails with "No such file or directory" | §24.1 (repo-relative path) |
| AVIF output fails after all the work is done | §24.2 (missing capability guard) |
| Pixel art on a COLOURED background read as antialiased | §23 (both measures fail; check the art by eye) |
| Background left behind in patches after `--tumble-safe` | §25 (it keeps only the LARGEST bg component) |
| `--recommend` suggested `--tumble-safe` on art that spans the canvas | §25 |
| A design region came out with NO protection, and the evidence names an outline colour that looks wrong | §26 (a degenerate candidate won selection) |
| `protected-region coverage 0.0` from `--auto` or `--verify` | §26 (nothing was protected at all — read the region note) |
| An outline colour that "verifies" but fills the whole canvas | §26 |
| The same colour needs to be removed here, kept there, and SEE-THROUGH somewhere else | §27 (`--translucent-region`; nothing in the pixels can infer it) |
| Glass, a window, a transparent bag reading as solid | §27 |
| Dithered or photographic pixel art called antialiased | §28 (`plateau_cliff_ratio` is the measure that reaches it) |
| A pixel-art discriminator scores brilliantly and you want to ship it | §28.2 (score it on the emoji population too, or it is not evidence) |
| `--pixel-art` recommended for a plain flat vector icon | §28.6 (a low `change_line_density` on a large simple shape) |
| A PNG/WebP source that already has transparency reads as hard-edged | §28.5 (the ramp is in ALPHA; RGB alone cannot see it) |
| `--recommend`'s `--pixel-art` evidence cites numbers that do not match the verdict | §28.7 (fixed — it now names the rule that fired) |
| `--analyze` / `--recommend` / `--verify` crashes on a static JPEG | §28.8 (`n_frames` on a bare attribute) |
| The output file is EMPTY / fully transparent, but every check says it is clean | §28.9 (an empty output scores perfectly on all four quality measures) |
| A monochrome/glyph PNG comes out blank, or reads as pixel art | §28.9 (an alpha-only mask — one flat RGB value, image in the alpha channel) |
| `--auto` refuses with "nothing to do here" | §28.9 (alpha-only source: its background is already transparent) |
| An AI-upscaled sprite is not detected as pixel art | §28.10 (the upscale removed the blocks — the verdict is correct) |
| Pixel art with 1-px shading at its edges reads as antialiased | §28.11 (hand-antialiased art; no edge-local measure can separate it) |
| A transparent-background PNG sprite is not detected as pixel art | §28.12 (HEAD detected 0 of 294; fixed) |
| A sprite SHEET (mostly empty canvas) reads as antialiased | §28.12 (low density from empty space, not blocks) |
| A sprite with a transparent background loses its black outlines | §28.13 (bg colour inferred from the RGB under the alpha) |
| Output written to `.jpg`/`.jpeg`/`.bmp` dies in a Pillow traceback | §28.13 (now refused legibly) |
| A static image is reported as having a timing defect | §28.13 (verify() was comparing a placeholder duration) |
| An already-transparent source comes back with far fewer opaque pixels | §28.14 (removal is now scoped to the source's own alpha) |
| A cleanup band around existing transparency eats the outline | §28.14 (the band is vetoed when the bg colour is also design) |
| A transparent PNG behaves as though it had no source transparency | §28.14 (only the palette-index spelling was handled) |
| A new threshold passes every corpus and breaks on real files | §28.15 (what each population is blind to) |
| A corpus label that cannot be wrong | §28.15 (flat plates are excluded, not counted as negatives) |
| Detection looks good pooled but one pack is at 15% | §28.15 (report per-pack; 78% of that corpus is one pack) |
| A results JSON looks finished but is stale | §28.15 (fixed output paths; require --out and write .partial) |
| Considering a NEW pixel-art discriminator | §23.8 (score it against real antialiased icons, not only the labelled corpus) |
| `protected_region_coverage` below 1.0 on an output you believe is correct | §22 (check `residual_nonopaque` before assuming a bug) |
| A pale fringe at the edge of a deliberately punched hole | §14 addendum, §22 (`--erosion-exempt-max-size` too high) |
| Confused why alpha looks all-or-nothing | §7 |
| A reported animation length that seems wrong | §9, §13 |
| Anything on tumbling/rotating/translating content | §10 |
| A small removed region looks like an inflated speckle | §11 |
| A grid/mesh pattern over what should be solid color | §12 (interior fade) vs §10 Bug 5 (edge over flat paint — different trigger, see §12's own note) |
| Lower output frame count than input | §13 |
| A real cutout/hole must stay transparent but a same-colour design element keeps getting damaged (or the hole won't punch at all) | §14, §15 |
| Need to force-remove a specific region regardless of what outline/region protection decided | §15 (`--remove-region`) |
| A whitish halo/fringe hugging a manually punched or edited region's edge | §14 addendum (skipped cleanup erosion) or §15 (hand-rolled alpha edit with no defringing) — different root causes, check which |

---

## 1. Edge-hardness caveat: geometry-heavy false positives

**Second confirmed case (2026-08-17, §16's asset):** `love.gif` scored **0.425** — under the 0.5 threshold, so `--recommend` suggested `--pixel-art`, which would have disabled feathering and erosion on curve-heavy antialiased vector art. Zooming 8× showed a real 1–2px antialiasing ramp. `--recommend` now attaches an explicit "near the 0.5 boundary, zoom before accepting" warning to any ratio at or above 0.30, so this caveat travels with the recommendation instead of relying on someone remembering to read this section. SKILL.md's rule: `edge_hardness.ratio` under ~0.5 means hard-edged (use `--pixel-art`); a few units or more means real antialiasing (normal defaults are correct). Real measurements for reference: a genuine pixel-art test file measured 0.0; two real antialiased vector icon test files measured 4.5 and 17.6. The gap is normally large and clean.

**The caveat, found on a real icon pack that was otherwise entirely normal vector art:** the ratio is sensitive to how much of the icon's perimeter is curved vs. straight, not purely to "is there antialiasing." A straight axis-aligned edge only needs a thin 1px antialiasing transition regardless of style, while a curved or diagonal edge needs a wider graduated band — so an icon dominated by straight lines (a trash can, a rectangular sweep effect) can score LOW (e.g. 0.17-0.39, under the ~0.5 threshold) despite being entirely ordinary antialiased vector art from the same consistent design system as icons in the same set scoring 2-17+. Confirmed directly: two icons from an otherwise uniform icon pack triggered the hard-edged threshold this way, and applying `--pixel-art` to them would have been wrong. **When a ratio comes back hard-edged but the icon is visually part of a set with other icons that scored normally, or the source is a professional/exported vector asset rather than something hand-drawn pixel-by-pixel, look at it directly (zoom in) before trusting the ratio alone** — geometry-heavy icons are the false-positive case to watch for.

## 2. Why `--protect-region` is a last resort
`--protect-region circle:cx,cy,r` assumes the true protected shape IS a circle of that exact radius in every direction from the center. Almost no real icon interior actually is. A badge/rosette ring is scalloped (the true boundary can easily range e.g. 86-183px from center depending on direction, even though it "looks roughly round" at a glance); a gem/diamond has a pointed apex; stars, seals, and most decorative icon interiors are similarly non-circular. Picking one fixed radius means:
- In directions where the true edge is CLOSER than that radius, the circle overshoots past the real boundary and keeps background-colored pixels opaque that should have been removed — a bleed/halo that sits flush against the art (easy to mistake for part of the design at a glance).
- In directions where the true edge is FARTHER than that radius, the circle falls short and clips into what should have been protected, leaving a notch or gap.

**Not a hypothetical** — it happened twice in the same session on two different icons that both "looked round enough" at a glance: a badge rosette (scalloped ring, true radius 86-183px) rendered with a fixed radius-126 circle left a visible extra white lobe bulging past the ring on one side, and a diamond gem's pointed white facet rendered as a bounding circle left a large stray white disc floating in the background above the diamond's point. Both looked fine in a quick glance at the preview thumbnail and were only caught on user report / closer pixel inspection. `rect:x,y,w,h` has the same failure mode for anything not truly axis-aligned rectangular.

The badge/rosette case above was actually fixed by opening the source frame and identifying the true enclosing outline color by eye — sampling a pixel a short distance outward from the protected area in a couple of different directions and checking they agree — then using that directly with `--protect-outline-color`. This one extra manual step is far cheaper than debugging a bleed after the fact.

## 3. Protected-region flicker: three implementation attempts, then v2 detection
This started as a real, confirmed bug reported by a user, went through THREE implementations, and the shipped v1 mechanism is deliberately the most conservative of the three after the other two caused real regressions on real files. **Read this before touching `build_protected_masks_robust` again.**

**The mechanism:** `--protect-outline-color` works by finding all pixels matching that color, then running `binary_fill_holes` to identify what's enclosed. This requires the outline to form a fully CLOSED ring in that specific frame. If any other animated design element (confirmed real cases: a wifi-signal pulse; a "wipe" sweep effect) happens to visually cross or overlap the outline at some frames, it locally replaces outline pixels with its own color, punching a gap — and `binary_fill_holes` doesn't degrade gracefully, it can leak interior out. Symptom: the protected region intermittently goes transparent or shows a gap.

**Attempt 1 (reverted): whole-frame substitution, gated on 70% of median area.** Flag frames whose color-mask area drops under 70% of that color's own median, substitute the WHOLE mask from the nearest non-anomalous frame. Confirmed to fix a severe case (wifi pulse breaking a cloud's enclosure on 16/120 frames, area dropping to ~56% of median) without breaking a legitimately- animated icon (a rotating design element that stays within +/-0.35% of its own median area throughout). Confirmed gap: MISSES smaller, localized holes that don't move the aggregate area much — a real case had a clearly visible hole (source solid white, output transparent) on frames still at 93-95% of median, comfortably above even a 90% threshold.

**Attempt 2 (reverted): local connected-component patching against a majority-vote reference, gated at 98% of median.** Built a per-pixel majority-vote reference shape from near-full-size frames, and for any frame below the 98% gate, patched in specific missing connected components (over a 50px floor) rather than substituting the whole frame. This DID fix the attempt-1 gap in isolated testing — verified the specific reported hole closed, verified the previously-known rotating-icon case still correctly stayed ungated. But delivered to the user end-to-end across a full batch, it produced a NEW, different regression ("random white parts appearing behind the gifs") that was not caught by the isolated per-case testing done before shipping it. The exact mechanism was not pinned down before reverting — the decision was to stop layering increasingly complex, incompletely-understood fixes on real user files rather than keep guessing. **The lesson: verifying a fix against the specific case that motivated it, and against one or two known prior regressions, is not the same as verifying it end-to-end across a full real batch.** Both matter; only doing the former is how this shipped a second regression.

**v1 restored (current baseline underneath v2):** whole-frame substitution at a 70%-of-median gate — the version with actual confirmed history of not causing a regression. Known limitation, accepted deliberately: it will NOT catch a hole on a frame whose aggregate area is still 70%+ of median, even if that hole is visibly real (confirmed real example above at 93-95%).

**Why `--analyze` doesn't catch this ahead of time:** `outline_color_verified` only checks the candidate color against a SINGLE frame (the first sampled one). That result gets applied uniformly across every frame during real processing, with no check that the color reliably encloses the region on frames it was never tested against.

**v2 detection (current state) — improved again, this time without a regression** (unlike attempts 2 and 3 above, which is why this one is the shipped state and those weren't). Two more real cases exposed v1's 70%-of-median threshold's blind spot in different ways:
- A gradually/dramatically MOVING design element (a cloud shifting position, not just occluded) has natural filled-area variation that can swing even more than a rotating shape — confirmed 0.50 to 1.06 of median on a real icon, i.e. legitimate variation that dips WELL under v1's 70% gate. Distinguishing signal that separates this from a real bug: legitimate variation is GRADUAL across many consecutive frames; a real bug is a SHARP, often single-frame outlier against its own local neighborhood, even when it's embedded inside a smooth large-amplitude cycle (confirmed: a real one-frame anomaly on this exact icon was still correctly caught this way).
- A SUSTAINED occlusion spanning many consecutive frames (confirmed real case: a continuous "wipe" sweep effect) doesn't produce a sharp local outlier at all, so the local-neighborhood check alone can't see it — confirmed catching only 1 of ~15 visibly-bad frames with that check in isolation.

v2 detection combines BOTH, independently per color, taking the union of frames either one flags: (a) a local-neighborhood check (sharp, isolated drop vs. a small window of nearby frames — safe for gradual/large-amplitude legitimate motion), and (b) a whole-distribution statistical-gap check (a sorted-value jump of >=8% separating a low cluster from a high cluster — catches sustained occlusion that (a) can't). Both were verified independently to produce zero false positives across every legitimate-animation case available (a rotation, and two large-amplitude smooth pulse/shift cycles) before being combined. Substitution mechanism is unchanged from v1 (single nearest non-anomalous frame, never a blended/combined reference).

**Known remaining gap, carried from v1, now narrower but not zero:** the sustained-occlusion (gap) detector needs a genuine statistical gap; a sustained-but-mild occlusion that blends smoothly into the animation's own natural variation (confirmed real case: a handful of frames on the same "wipe" icon sitting in a transition zone between the bad and normal clusters) still won't be caught. Don't claim "fully fixed" for a sustained-occlusion case without checking the specific frames a user reports.

**A SEPARATE, more direct fix, worth trying FIRST before reaching for detection/substitution at all:** if the outline is fading toward background color gradually (rather than being replaced outright by a differently-colored crossing element), widening `--outline-tolerance` alone can keep the ring topologically closed through the fade with NO cross-frame logic needed at all — confirmed on a real "wipe" case: tolerance 40->80 brought the minimum per-frame filled-area ratio from 0.79 to 0.93, and a rigorous full-animation check (every true-interior pixel against source, not just an aggregate area proxy) found zero remaining mismatches across all 124 frames. This is strictly safer than substitution (no risk of cross-frame position mismatches, since nothing is borrowed from another frame). Check by sampling a point that's outline-colored in a good frame across several bad frames: shifts toward background color gradually → try tolerance first; gets replaced by an unrelated solid color → occlusion, detection/substitution is the right tool.

**Confirmed generalizing to a second, structurally different case — a full color SHIFT between two saturated colors, not just a fade toward background:** a star icon's own outline animated smoothly between navy and a distinct purple (`104,100,247`), as an intentional design effect, not occlusion. First instinct was multi-color `--protect-outline-color` (list both navy and purple) — this was the WRONG lever and didn't work: both colors independently still showed heavy substitution (32/46 and 34/46 frames), because the outline passes through a continuous gradient of intermediate colors between the two named endpoints, not a discrete switch — naming just the two endpoints leaves every in-between frame still unmatched by either. Tolerance widening on the single base color (navy alone) fixed it completely instead: tolerance 40->150 brought the minimum ratio from 0.216 to 0.865, confirmed zero substitution needed, stable across all 46 frames.

**Takeaway: when the outline's own color visibly changes across frames — fading toward background OR shifting toward a completely different saturated color — try widening `--outline-tolerance` on the ORIGINAL single color FIRST, before reaching for multi-color protection.** Multi-color protection is for when multiple DISTINCT, STABLE outline colors coexist (confirmed real case: a folder icon whose folder and triangle badge happened to share one outline color but could equally have used two) — not for one outline that continuously drifts. The right tolerance value is case-specific (80 sufficed for the fade-to-white case, the color-shift case needed 150) — test a few values and check the resulting min-ratio rather than assuming a fixed number transfers.

**`--outline-tolerance` has its own real interaction with `--edge-cleanup-erosion`, confirmed the hard way:** on the same "wipe" icon, after fixing the enclosure via tolerance widening, a DIFFERENT artifact appeared — a visibly lighter, blended outline color staying fully opaque right at the true silhouette edge before the cutoff to transparent (a real fringe artifact, confirmed via direct pixel comparison to NOT be present at that severity with the default erosion). This icon had already been set to `--edge-cleanup-erosion 1` (reduced from the default 2) earlier in the same investigation, specifically to preserve a different thin design element — but erosion=1 turned out insufficient to clean up the NEW fringe exposed by the wider tolerance. Reverting to the default erosion=2 fixed it (confirmed: direct navy-to-transparent transition, no blended pixel) at the cost of the thin element shrinking from 137px back to 126px (87% of the original source's 145px — a real but acceptable tradeoff, not destruction). **Lesson: `--outline-tolerance` and `--edge-cleanup-erosion` are not independent settings for a given icon — changing one can require re-checking the other**, especially on icons that already needed a non-default erosion value for unrelated reasons.

**Practical guidance for verification and reporting:** if a user reports a protected area "flashing," a gap that "disappears," or white/background patches appearing where they shouldn't, check the NOTE in stderr output first to see whether the fix fired — don't assume "no NOTE" means "no problem," the detectors have known blind spots documented above. Before concluding a specific reported artifact isn't reproducible, double- and triple-check the exact crop/coordinate offset used for any diagnostic comparison (see section 9 below — a real case of an incorrectly-assumed crop offset masking a real artifact while producing a spurious one elsewhere).

## 4. `--edge-cleanup-erosion 0` total-destruction bug (fixed in v2.1)
Confirmed directly: `--edge-cleanup-erosion 0` on a real icon produced a completely blank, fully-transparent output (a 47-frame GIF that shrank to 1.9 KB) with NO error or warning. Root cause: `erode_alpha_edge` passed `iterations` straight through to `scipy.ndimage.binary_erosion`, and scipy's own documented behavior for `iterations < 1` is "repeat until the result no longer changes" — NOT "no-op." For any bounded opaque region, repeated erosion always converges to nothing, so `iterations=0` silently eroded every frame's content away completely. Confirmed the mechanism in isolation: a 10x10 filled square went from 100px to 0px at `iterations=0`.

**Why this wasn't caught earlier despite `--pixel-art` also using `--edge-cleanup-erosion 0` internally:** `--pixel-art` additionally sets `feather=False`, and the erosion call site is guarded by `if args.feather:` for an unrelated reason (erosion is specifically feather-fringe cleanup, so it's skipped when there's no feathering to clean up). That guard happened to also prevent `--pixel-art`'s use of erosion=0 from ever reaching the buggy scipy call. The bug was only reachable by passing `--edge-cleanup-erosion 0` directly, with feathering still on (the default) — a real, unremarkable-looking combination that came up naturally while trying to preserve a tiny, delicate animated element (a sparkle icon that shrinks to a few hundred pixels at the start/end of its own pop-in/pop-out animation).

**Fix:** `erode_alpha_edge` now has an explicit `if iterations <= 0: return list(alpha_frames)` guard at the top, making it a true no-op regardless of what scipy would otherwise do. Verified: erosion=0 now correctly returns the full, undamaged content; existing behavior at erosion>=1 and `--pixel-art` are both unchanged.

**The generalizable lesson:** a library function's behavior at a boundary/degenerate input value (0, empty, None, negative) is not guaranteed to match the caller's intuition even when the non-degenerate behavior is well understood and has been correct for a long time. This bug shipped silently through v1 and v2 because every prior real-world case happened to either use erosion>=1, or use erosion=0 exclusively via the one path (`--pixel-art`) that never actually reached the vulnerable call. Don't assume a parameter's "obvious" meaning at its extreme values without checking the underlying library's actual documented behavior there, especially for a value (0/off) that reads as if it should be the safest, simplest case.

## 5. Reduced erosion & resize degradation on thin/geometry-light icons
`--pixel-art`'s `edge_hardness` check is a binary "is this pixel art" signal, but erosion damage isn't actually binary — it's a spectrum tied to how much "bulk" a design has to absorb a fixed pixel-count shave. A real confirmed case: two icons from an otherwise normal antialiased vector icon pack (NOT flagged as pixel art, correctly so) still had thin elements (a lightning bolt, a folder's back-flap outline line) that came back visibly more jagged/thinner than the source under the DEFAULT `--edge-cleanup-erosion 2`, because thin elements have much less interior "padding" to lose before erosion eats into the visible shape itself. Measured directly: a thin line's opaque run-length was 145px in the source, 129px after default erosion (2px), and 137px at `--edge-cleanup-erosion 1` — noticeably closer to source without reintroducing the fringe-color artifact the default erosion exists to prevent (re-checked for fringe colors at erosion=1 on both affected files, none found).

**Practical signal:** both affected icons also happened to have low `edge_hardness` ratios (0.39 and 0.17) — below the ~0.5 pixel-art threshold, but not by a huge margin, and this is the SAME "straight-line-heavy geometry" pattern documented in section 1 above. Treat a low-but-not-hard- edged ratio as a signal to consider `--edge-cleanup-erosion 1` even when `--pixel-art` itself would be wrong. This isn't automatic — it needs a judgment call per icon, since erosion=1 is a real quality/fringe-cleanup tradeoff, not a pure correctness fix like the erosion=0 bug was.

**Resize is a second, independent contributor to the same thin-element problem — check it separately from erosion.** A user specifically reported a thin lightning-bolt element looking "jagged and rough" versus a smooth original even AFTER erosion was reduced to 1. Measured directly with a scale-invariant roundness proxy (edge-pixel-count / sqrt(area), isolated to just the thin element): source measured 7.276, the SAME icon with NO resize measured 7.313 (~0.5% worse, essentially unchanged), but the SAME icon WITH the tier's normal 512px-target resize measured 7.514 (~3.3% worse) and also lost ~24% of the element's pixel area outright. The mechanism: this script's alpha decision is computed at full source resolution, THEN resized with LANCZOS, THEN re-binarized (`alpha > 127`) — resizing an already-effectively-binary mask and re-thresholding is a well-known recipe for staircasing on thin/high-curvature shapes, unlike resizing a naturally continuous-tone image. If the icon's crop is only modestly above a tier's resize target (e.g. 536px vs. a 512px target — an ~5% overage), consider `--resize-max-dim` set high enough to skip the resize entirely — confirmed on the real case: skipping resize was not just higher quality but also produced a SMALLER file (1292.9 KB vs. 1443.7 KB), since a cleaner, less-aliased edge compresses better via LZW than a staircased one. Not even a pure quality-vs-size tradeoff in every case — check both.

**Confirmed a second time on a differently-shaped icon** (curved star points, not a thin bolt) after a user asked for "smoother animation" with no more specific complaint than that: measured the same roughness proxy on the star's outer silhouette and found the identical pattern — 11.28 resized vs. 10.48 source, improving to 10.99 with resize skipped, again with a smaller file as a side benefit (562 KB vs. 680 KB). Confirmed on two structurally different icons (a thin straight-line element, and a curved/pointed outer silhouette) — treat "check whether skipping resize helps, whenever the crop is only modestly over a tier's target" as a general check worth running whenever a complaint is about smoothness/roughness/jaggedness.

## 6. Tools considered: gifski and pngquant
Documented so these aren't re-researched or re-tested from scratch without new evidence — both were investigated seriously, not dismissed on sight.

**gifski** (libimagequant-based GIF encoder, same engine family as pngquant). Its own maintainer, responding to a bug report about jagged edges from transparent PNG input, said plainly: "This is unavoidable. The GIF format doesn't support alpha transparency" — meaning gifski does its own alpha thresholding on whatever it's handed rather than preserving an input mask exactly, which conflicts with this script's protected-region/feathered-edge alpha decisions (gifski would potentially re-derive the transparency boundary rather than respect the one already computed). Separately, its docs describe "cross-frame palettes" designed to combat per-frame palette drift — reasonable, but not verified against this skill's mostly-static-content case, and not worth the risk to transparency handling to find out. **Not integrated for the transparency/removal step, at all** — see section 8 below for a separate, later-discovered use as a compression-only step.

**pngquant / libimagequant** (used directly, not via gifski) for building `render_frames_to_gif`'s shared master palette, in place of Pillow's `Image.ADAPTIVE`. This one WAS implemented and empirically tested, not just reasoned about abstractly. **Implemented as an explicit opt-in (`--quantizer pngquant`), NOT the default** — the full reasoning:
- Isolated quantization-error measurement (MSE against the original, color-only, no GIF encoding involved) showed pngquant meaningfully outperforming Pillow's median-cut at every color count tested: 38% lower error at 16 colors, up to 81% lower at 128 colors.
- But swapped into the real end-to-end pipeline on real test art (identical settings, same source, only the master-palette algorithm changed) it produced LARGER output files at every tier tested — +4.0% at `optimize`, +6.8% at `heavy` — not smaller, the opposite of what the isolated MSE numbers implied.
- Working theory: pngquant optimizes for perceptual color accuracy, not for how well the resulting palette's indices compress via GIF's LZW. This skill's actual content (flat vector icon/sticker art, not photos or gradients) is exactly the case where index run-length/predictability matters more than marginal per-pixel color error, and `medium`/`heavy` tiers already run their own further gifsicle `--lossy`/`--dither` pass on top, which dilutes whatever quality edge the master palette had going in. Checked the color histogram directly on real test art: only ~8 colors actually do real design work (the flat fills); the rest of the ~150 distinct colors are a long tail of antialiasing/blend fringe shades. Either quantizer preserves those 8 core colors losslessly within any of this skill's color budgets (128+), so the measured MSE gap is concentrated in secondary edge-fringe fidelity, not core design accuracy — a real difference, but a narrow one for THIS content type.
- Given that, defaulting to it wasn't justified — but the underlying case for it wasn't zero either, just narrower than "always better." **`--quantizer pngquant` exists for**: content this skill hasn't primarily been validated against (genuine gradients/soft shading, where more real colors compete for the budget rather than a long tail of minor blend noise), or whenever the person explicitly says quality matters more than file size. Falls back to `pil` with a clear warning if pngquant isn't installed/available or the call fails. Works from `--batch` manifests too (any per-file override key works generically, `"quantizer": "pngquant"` included).
- **The lesson generalized, not just about this one tool:** a component that wins on an isolated, narrower benchmark (quantization MSE) can still lose on the metric that actually matters for the full pipeline (final file size on this skill's real content) if the two aren't measuring the same thing. Prefer re-testing swaps like this end-to-end on real output before adopting them, even when the underlying algorithm is well-regarded and the component-level numbers look unambiguous. (Standing rule behind this: test the naive/simpler option end-to-end on real content before committing to a bigger rebuild.)

## 7. GIF format has no partial transparency
Every pixel in a GIF frame is binary opaque-or-transparent; there is no such thing as a real semi-transparent pixel the way PNG/WebP support. Confirmed hands-on while trying to fake a "background bleeds through a highlight" effect on a recolored icon: wrote a pixel at alpha 114/255 intending a soft blended look, saved via Pillow's GIF encoder, and re-read the output — the alpha came back rounded to 255 (fully opaque), byte-identical to a version that never attempted partial alpha at all. This isn't a Pillow limitation specifically — it's the GIF format's own single-bit transparency index, the same underlying fact section 6 above cites from gifski's maintainer in a different context (gifski's alpha-thresholding behavior on transparent PNG input is a symptom of this same format limitation, not an unrelated gifski quirk).

**⚠️ Updated by §16 (2026-08-17).** Everything in this section is still true *of GIF*, but it is no longer the end of the story. The real fix for a translucent/fading element is to stop using GIF: WebP and AVIF both store 8-bit alpha, and `--recover-fade-alpha` can reconstruct alpha that a GIF export already flattened. Read §16 before reaching for the bake-a-flat-blend workaround below — that workaround is now the fallback for when the deliverable *must* be a GIF, not the default answer.

**Workaround for "I want it to look like the background bleeds through"**: if the final background color is fixed and known ahead of time (e.g. a specific Discord button color), bake a literal flat blend of that background color with the foreground color as an opaque pixel value, in place of relying on real partial alpha. This achieves the same visual read without needing the format to do something it structurally can't — confirmed working end-to-end on a real delivered asset (a recolored eyedropper icon's highlight stripe, blended toward Discord blurple instead of left pure white). This is a real constraint to flag to the user up front whenever a "soft"/"bleeding"/ "translucent" effect is requested against a GIF deliverable, not something to attempt and discover mid-task.

## 8. gifski as a compression-tier alternative (not yet integrated)
Section 6 documents gifski being rejected for the TRANSPARENCY step specifically (its own alpha-thresholding conflicts with this script's protected-region/feathering decisions) — that finding still holds and gifski should NOT be used for the background-removal pass itself. But a separate, later use case surfaced: as a COMPRESSION-ONLY step applied AFTER transparency is already finalized (i.e. gifski re-encoding an already-transparent GIF, not deriving transparency itself), a genuinely different tradeoff than what was evaluated in section 6.

Real comparison, same source asset, same target ("keep it smooth, hit Discord's 256KB emoji limit"): this skill's own `--compress` tiers, working from `--target-kb 200`'s automatic cascade, had to drop frames to hit budget — `--target-kb 200` alone jumped straight to a stride-4 frame-drop (180 → 45 frames, 12.5fps) to reach 79.8KB; manually dialing in `--compress heavy --frame-stride 3` did better (180 → 60 frames, 16.7fps, ~144KB) but still threw away 2 of every 3 frames. A user's own manual pipeline outside this skill — crop transparent margin → resize to 128px width → gifski re-encode at quality 68 — kept ALL 180 original frames (zero frame drops, full smoothness) at 248.26KB, comfortably under the 256KB limit with real margin. gifski at a well-chosen quality setting outperformed this skill's own gifsicle-based frame-stride/lossy-dither tiers for this specific "smooth motion matters more than absolute minimum size" case.

**Not yet integrated into this script** — flagging as a real, evidence-backed option to reach for next time a user explicitly prioritizes animation smoothness over squeezing every last KB: for that specific ask, after transparency is finalized via this script's normal removal pass, piping the transparent output through an external `gifski --quality <N>` pass (tuning quality rather than frame-stride to hit the target size) is worth trying as an alternative to escalating this script's own `--compress heavy`/`--frame-stride` further. Not validated across a range of source assets yet — this is one confirmed real-world data point, not a new default recommendation to reach for unconditionally.

## 9. Verification pitfalls: Pillow's `ImageSequence.Iterator`, bbox-vs-mask, frame-offset drift

**Pillow's `ImageSequence.Iterator` yields the SAME underlying image object every time**, just seeked to a new position — it does not return independent per-frame copies. `frames = list(ImageSequence.Iterator(im)); [f.info['duration'] for f in frames]` looks reasonable but is WRONG: by the time the second line runs, every `f` is the same object, now seeked to the last frame, so every entry silently returns the LAST frame's duration. This produced a totally fabricated "total animation length" that was off by more than 10x in one real case, and was reported to a user before being caught. The correct pattern reads `.info['duration']` *immediately* after each `.seek(i)`, in the same loop iteration — never after materializing a list of frames first:
```python
im = Image.open(path)
durations = []
for i in range(im.n_frames):
    im.seek(i)
    durations.append(im.info.get('duration', 100))
```
For a fully independent, Pillow-bug-proof ground truth (worth using whenever duration correctness actually matters for a claim you're about to make to the user), parse the GIF's raw Graphic Control Extension delay bytes directly instead of trusting any decoder: each `0x21 0xF9` block has delay as a little-endian 16-bit value at offset+4 in centiseconds; multiply by 10 for milliseconds. This is what actually resolved the discrepancy above.

**When investigating a reported "this part flickers / goes transparent when it shouldn't" complaint, sampling pixels by bounding box alone produces false positives.** A candidate region's reported `bbox_xyxy` is a rectangle; the real enclosed shape usually isn't, so pixels that are white-in-source-and-inside-the-bbox can still be legitimate background sitting just outside the true enclosed area (e.g. the gap between two nearby design elements that both fall inside one bounding rectangle). This happened for real while debugging a user report: a bbox-based check showed opacity swinging from 0.0 to 1.0 across frames, looking exactly like a bug, until re-checking with the proper mask (`binary_fill_holes` on the outline-color mask, same as the actual processing code) showed the TRUE interior pixels were 100% opaque in every single frame — no bug at all. Reproduce the actual protection logic (fill-holes on the outline mask) rather than approximating it with a bounding box when the distinction matters for a real diagnosis.

**Frame-number correspondence between a user's own sprite-sheet/export tool and this script's own frame indexing is NOT guaranteed to be a simple fixed offset.** Confirmed needing composite-and-MSE matching against a candidate frame range to find the true correspondence, and the offset drifted slightly (+4 vs +5) across the same sprite sheet, consistent with accumulated rounding in a hand-estimated row pitch. Don't assume "the user's frame 40" is "this script's frame 40." Also double- and triple-check the exact crop/coordinate offset used for any diagnostic comparison — a real case had an incorrectly-assumed crop offset (derived from frame-0-only foreground detection instead of the TRUE union-of-all-frames crop this script actually uses) produce a spurious "artifact" in one location while masking a real one elsewhere. Re-derive the offset from the script's own logged crop coordinates.

## 10. Animated/rotating content: four related failures on a tumbling icon, seven rounds to fully fix
SKILL.md's rule: check whether the foreground shape rotates/translates significantly within the canvas before choosing a strategy; if so, several default assumptions below become actively dangerous, not just imprecise. This section is the evidence trail — four distinct, confirmed bugs from the same real asset, each only surfacing after the previous one was fixed, taking seven full delivery-and-rejection rounds (v1 through v7) before the asset was actually correct.

**The real case:** a 640x640, 124-frame calendar/gamepad icon GIF where the whole card tumbles/rotates through a wide range of orientations (not a subtle wobble — real rotation, occasionally flipping to show a second card layer behind it), while a purple gamepad with a white cross and four white dots sits on the card's face, and the card's header has four navy "spiral-binding" loops each with a small white gap inside. Three different things needed different treatment (gamepad cross/dots stay opaque; the four spiral-hole gaps go transparent; everything else white goes transparent) while all of it tumbles together in lockstep.

### 10.1 Bug 1 (v1): a fixed-position region derived from one frame doesn't hold for other frames
`--analyze`'s `bbox_xyxy`/`suggested_protect_region` are correct for the sampled frames they came from, but nothing stops using those as a FIXED rectangle applied uniformly across all frames — a natural move when a region is a bad `--protect-region` fit (non-circular, no verified outline color; see §2's existing caution, which warns about the wrong GEOMETRY at one position but not about the position itself being wrong elsewhere). Confirmed real result: visibly destroyed frames mid-animation — chunks of the gamepad and card cut out — because by the time the tumbling icon reached other frames, the fixed pixel rectangle now overlapped completely different content.

**Fix:** re-derive any frame-specific region independently, per frame, from intrinsic properties that don't depend on position — size range, bounding-box aspect ratio, and immediate bordering color(s) — never from one frame's absolute coordinates.

### 10.2 Bug 2 (v3): border-touching stops being a safe proxy for "background" once the foreground can graze the edge
A natural definition of "background" is "whatever bg-colored region touches the canvas border" (flood-fill from the edges) — safe ONLY when the foreground design never itself reaches the canvas edge. Confirmed real failure: at the peak of the tumble, a genuine corner of the card touched row 639 of the 640px canvas, and border-touch flood-fill correctly identified that as "border-connected" and swept the ENTIRE connected white shape — 22,169px of real card content, not background — into "background," deleting it. This is a topology problem, not a color/edge-blend problem this skill already handles well: a large chunk of real content became graph-connected to the true background purely by touching the border at one point.

**Fix:** for animated content where the foreground might reach the edge, define background as the SINGLE LARGEST connected bg-colored component per frame, not "any bg-colored region touching the border." Confirmed safe specifically because true background is overwhelmingly large relative to any other same-colored region — verified directly across all 124 frames of the motivating case, the largest bg-colored component was never less than ~3x the size of the second-largest, even in frames where a second genuinely large white region (the card's own visible interior, up to ~47,000px) coexisted with it. **This margin needs re-verifying on any new asset before trusting it** (print the top 2-3 component sizes per frame) — an asset whose true background is only a thin margin, comparable in size to its own foreground bg-colored regions, is the case where this heuristic is the wrong tool.

### 10.3 Bug 3 (v2, and again after v3's fix): single-frame outline enclosure can fail under self-overlapping/rotating geometry, past what §3's existing anomaly detector catches
§3 above already documents real, hard-won infrastructure for one enclosure-failure mode: a DIFFERENT animated element briefly crossing and breaking a stable outline's closure (the "flashing" bug, with local-anomaly + whole-distribution-gap detection, and real history of two reverted approaches that produced "ghost" artifacts on rotating icons specifically — read that section in full before touching this area again, it already encodes hard lessons). **This case's failure was different enough to slip past that existing detector.** Rather than a stable shape being briefly crossed by something else, the asset's OWN geometry — a card tumbling through orientations, at times self-overlapping its second layer — made single-frame `binary_fill_holes` enclosure unreliable in a way that correlated smoothly with rotation progress rather than spiking as a sharp, isolated anomaly against nearby frames. It silently deleted real card content across a meaningful span of frames without ever reading as "flashing," and a 40-frame `--analyze` sample (`enclosure_ratio: 1.0`) did not catch it either, because the specific sampled frames happened to be fine even though frames in between weren't.

**Fix:** for this failure signature specifically, don't lean on `--protect-outline-color` at all — bypass single-frame flood-fill enclosure as a concept in favor of bug 2's largest-component background definition, plus bug 4's mechanism below for anything needing selective removal. **This does NOT replace §3's existing anomaly detection** — that remains the right tool for its own documented failure mode (a distinct crossing element). Use this section's approach when the SHAPE ITSELF is what's moving/rotating/self-overlapping; keep using `--protect-outline-color` (with its existing anomaly correction) for a stable shape being briefly crossed by something else.

### 10.4 Bug 4 (v5, discovered fixing an unrelated fringe issue after bugs 1-3 were resolved): allowlist-style feathering protection misses solid near-background design colors
Not specific to animated content — would affect a perfectly static icon too — but found in the same investigation, one step later. The motivating icon has a flat, deliberate, pale blue-lavender "shadow" design shape (RGB ~209,220,251). That color's distance from pure white background (~46) happens to fall INSIDE the default feathering transition band (`tolerance x feather-band-multiplier` = 15 x 4 = 60) — purely by coincidence, not because it's an antialiasing blend. Because the protected mask in use at the time was allowlist-style (only the specific regions already verified as needing protection were marked protected — the page/gamepad interior), this shadow shape wasn't on the list, so it went through the normal distance-based alpha estimate and came out with unstable, partial alpha — a visibly speckled/noisy edge where the shape met the surrounding page.

**Initially, wrongly, suspected to be a Bayer-dithering artifact** — ruled out by testing a hard 50% cutoff with dithering removed entirely; the noise persisted unchanged, which is what correctly redirected the investigation to the alpha estimate itself rather than the dithering step. Don't skip that isolation step next time a "noisy/glitchy" report comes in — assuming it's dithering because dithering is the obvious suspect cost a full round here.

**Fix (v6/v7):** inverted the protected-mask default. Instead of allowlisting specific verified- safe regions (leaving every OTHER color subject to the raw distance-to-background check), protect EVERYTHING in the frame except the verified-removable core (background union any identified holes) and a thin ~4px ring immediately around it. This generically prevents ANY solid design color — not just this specific pale blue — from being mistaken for an antialiasing blend, with zero per-asset color tuning needed for the protection step itself. Confirmed: zero isolated speckles across all 124 frames after this change (down from a real, visible pattern before it), and the pale shadow shape stays fully solid in every frame.

### 10.5 Bug 5 (found in the same investigation, not its own delivery round): Bayer dithering reads as noise on flat backgrounds
Surfaced while ruling out dithering as bug 4's cause — not the cause there, but a real, separate, worth-keeping finding. This skill's default feathering resolves partial alpha to GIF's 1-bit alpha via a spatial Bayer dither pattern, meant to simulate a soft edge — reasonable for content composited over varied/textured backgrounds. **Confirmed directly: the exact same dithered edge, composited over a SOLID flat color, reads as visible glitchy noise, not smoothness** — a spatial dither pattern only looks smooth against content with its own texture to blend into. This matters beyond the literal green-screen check used here: a flat/solid color is also how the delivered asset may realistically be placed in the wild (a solid-color chat bubble, a flat app background), not just a debugging artifact of the verification method.

**Fix:** added a hard-cutoff alternative (50% threshold on the already-defringed alpha) in place of the Bayer pattern — keeps the color-unmixing benefit from bug 4's fix, trades a very slightly harder edge silhouette for zero visible noise on any background. Worth defaulting to for small flat-vector icon/sticker content (this skill's primary target) whenever the final placement context isn't known to be textured/varied.

### 10.6 Generalizable takeaways
- A fixed pixel-space region derived from one frame is only valid for that frame — extends §2's existing circle/rect-shape-mismatch caution to a new axis (position, not just geometry).
- Border-touching is a safe proxy for "background" only when the foreground provably never reaches the canvas edge — verify the size-margin assumption directly (across ALL frames) before relying on it, the same way `edge_hardness` gets checked before trusting antialiasing defaults.
- §3's existing flicker-detection infrastructure is built for a DIFFERENT failure signature (a stable shape briefly crossed by another element) — it is not guaranteed to catch enclosure failure that correlates smoothly with the shape's OWN rotation. Don't assume it covers this case just because both produce "content that should be protected went transparent."
- Disambiguating two same-colored, similarly-sized regions (one to remove, one to keep) has no universal automatic rule — required manually sampling bordering colors on the real art, the same manual-inspection philosophy §2's outline-color fallback already established for a different problem. Expect to recalibrate size range, aspect limit, and distinguishing color per asset, not reuse fixed numbers.
- When a "noisy/glitchy" artifact is reported, isolate dithering from the alpha computation itself before assuming which one is at fault — they produce visually similar speckled results but need different fixes, and guessing wrong (as happened here initially) costs a full round.
- Verify against ALL frames for this content type, not a spot-check sample. Every one of the four bugs above was localized to specific rotation phases or specific design colors; a first/middle/ last spot-check (this skill's normal verification habit, sufficient for most content) would not reliably have caught any of them.
- Verify against a solid-color composite, not just checkerboard, at least once. Checkerboard (already flagged in the Verification section as camouflaging soft bleed) also camouflages dithering noise and unstable partial-alpha artifacts — both bugs 4 and 5 above were only clearly visible against a solid color.

### 10.7 What shipped
`--tumble-safe` (largest-connected-component background detection, replacing `--protect-outline-color`/`--protect-region` for this content type), `--keep-bg-blob-if-near <hex,...>` (per-frame, color-bordering-based hole disambiguation, gated by `--hole-size-range`/ `--hole-max-aspect`), `--protect-band-only <px>` (invert-by-default protection), and `--dither-mode {bayer,none}`. All four are additive/opt-in — default behavior for non-tumbling content is unchanged, confirmed via a byte-identical `--analyze` diff against the pre-change script on the same test file. See SKILL.md's "Animated/rotating content" section for the lean actionable rule and decision summary.

## 11. Small removed regions get inflated by edge-cleanup erosion: a second animated-icon case, five rounds
SKILL.md's rule: any time a fix removes a small, isolated bg-colored region, route the final erosion pass through `--erosion-exempt-max-size` instead of letting it hit normal `--edge-cleanup-erosion`. This section is the evidence trail — a different asset from §10's tumbling calendar, a different failure mechanism, five rounds (open-book-gear-transparent.gif through -v5.gif) to fully resolve.

**The real case:** a 640x640, 50-frame open-book-with-gear icon. An orange gear (rotating and bouncing vertically) sits above an open book whose pages are enclosed white, verified by `--protect-outline-color` across all 50 frames with zero enclosure failures (unlike §10's case, this asset's outline enclosure was completely reliable — a useful reminder that §10's failure mode is real but not universal, and checking is still worth doing even when it turns out fine). The gear's rotation/bounce means it transiently grazes the book's top-edge outline at certain frames, pinching off tiny gaps of true background between the gear's teeth and the book's curve — nothing to do with §10's tumble/rotation bugs, and this asset didn't need `--tumble-safe` at all.

### 11.1 Round 1 (v1, baseline `--protect-outline-color` delivery): visible white gaps at the gear/book boundary
User-reported (not internally discovered): two frames had a clearly visible white gap where the gear's teeth met the book's page-top curve — 69px and 137px respectively, large enough to read as an obvious defect. `--protect-outline-color` correctly (by its own logic) treated these as enclosed white and protected them, since they genuinely are bordered by navy on both the gear and book side. The defect is about design intent, not about the mechanism working incorrectly.

### 11.2 Round 2 (v2): blanket small-size removal broke unrelated content elsewhere in the frame
Fix: any enclosed white component under 800px (comfortably below the smallest legitimate protected region, the gear's ~2252px center circle, confirmed by scanning size across all 50 frames) was treated as removable. This over-generalized: the book's pages have wavy purple/blue decorative lines, and where two nearby line-strokes' antialiasing curves happen to nearly touch, they can pinch off their own tiny (1-5px) incidental background pocket — completely unrelated to the gear, just an artifact of the line art's own geometry. The blanket rule removed these too, producing scattered 1-5px transparent "particles" inside the book pages in frames far from the gear (measured y≈352-357, vs. the real gear-boundary notches at y≈228-317 — a clean ~35px separation once actually measured).

**Fix:** added a position constraint (y-center < 340) so only small enclosed regions actually near the gear are eligible for removal. Verified: page-interior specks now stay opaque, real gear-notches still transparent.

### 11.3 Round 3 (v3, confirmed independently by the user re-testing the delivered file, not a self-caught bug): erosion inflated the smallest notches into visible "speckles"
This is the same content-independent mechanism documented as its own general lesson above/in SKILL.md's "Small removed regions can be inflated by edge-cleanup erosion" section — restated here briefly since it's the specific case that surfaced it. Several of the gear-boundary notches were themselves tiny (1-11px) before any cleanup, since the exact overlap between the gear's teeth and the book's curve varies continuously with the gear's rotation/bounce phase, and most frames only produce a marginal, barely-there gap. The standard 2px `--edge-cleanup-erosion` pass, applied uniformly with no regard for how small the removed region on the other side of a boundary is, inflated a confirmed real 1px removed pixel (frame 6) into a 49-70px hole — a 50-70x size increase, turning an imperceptible rendering quirk into a visibly distracting speckle. **The user caught this on their own re-check of the delivered file** (not something the standard verification checklist — full-frame structural checks, solid-color composite — flagged, because those checks confirm correctness of WHAT got removed, not whether an already-correct removal got inflated afterward by a later pipeline stage). Worth internalizing: passing every structural check doesn't rule out a bug introduced by a downstream step those checks don't specifically probe.

### 11.4 Round 4 (v4): raising the size floor traded one visible defect for its mirror image
First attempt at a fix: require a candidate notch to be at least 30px (comfortably above the 1-11px noise range, comfortably below the two real 69px/137px gaps) before it's even considered removable. This stopped the erosion inflation (nothing under 30px was touched at all), but the sub-30px slivers now stayed fully opaque white instead — visible as small white specks at exactly the points (gear teeth nearly touching the book outline) a person looks most closely at. **The user caught this too, on the very next re-check**, correctly identifying it as a new, different artifact from round 3's (transparent specks vs. opaque specks) rather than assuming it was the same bug recurring.

### 11.5 Round 5 (v5): exclude tiny regions from erosion's INPUT, not just its size threshold
The actual fix, and the one that shipped: rather than choosing between "remove and let it erode" and "don't remove at all," exclude any tiny (<30px) removable region from the erosion computation entirely — mark it as if it were fully opaque/protected for that computation only, so erosion produces exactly the result it would have if the tiny region had never been flagged as removable in the first place (identical to how the surrounding area is normally, correctly treated) — then punch each tiny region back to transparent at its own exact pre-erosion pixels afterward. An intermediate attempt (dilate each tiny region by the erosion radius and restore whatever erosion reclaimed there, provided it wasn't also near a legitimately large removed region) was tried first and was measurably incomplete — a 1px notch still came out ~40-50px post-restore — because erosion's real spillover pattern around a small feature isn't a clean, independent ring, especially with other nearby geometry (a second small feature close by, a corner, another edge) also contributing to the same local erosion result. Excluding the region from erosion's input is exact by construction; trying to undo erosion's output after the fact is not.

### 11.6 Generalizable takeaways
- A blanket size-based removal rule needs a second, independent constraint (position, color, whatever the asset actually offers) the moment there's more than one source of small same-colored enclosed regions in the frame — extends §10's bug-1 lesson (position-independent per-frame re-derivation) with a concrete case of getting the DISAMBIGUATION signal itself wrong on the first attempt, not just the removal mechanism.
- Passing the standard verification checklist (full-frame structural checks, solid-color composite) does not rule out a bug introduced by a LATER pipeline stage (here, erosion) that those checks don't specifically probe. The checks confirm the removal decision was right; they don't by themselves confirm nothing downstream altered its size.
- When a person reports "still broken" after a fix, don't assume it's the same bug persisting — round 4's opaque-speck complaint was a genuinely different defect from round 3's transparent-speck complaint, caused by the fix itself, not a failure of the fix to apply. Confirm which failure mode is actually present (in this case: check the actual pixel/component sizes) before re-diagnosing.
- Undoing a global transformation's effect on a small region, after the fact, by trying to identify and reverse just its local spillover, is fragile the moment other nearby geometry is also contributing to the same local result. Excluding the region from the transformation's input entirely is exact; patching its output is not — worth defaulting to the former whenever the transformation (here, erosion) supports being scoped that way.
- A file mismatch (someone re-testing an old delivered version, not the latest one) is a real, mundane possibility worth checking for directly (file hash, filename in what they show you) BEFORE assuming a fix didn't work — but confirmed here it isn't always the explanation: round 3 and 4's reports were both against the actual current file and were both real, distinct bugs. Check, don't assume either way.

### 11.7 What shipped
`find_tiny_removed_regions` + `erode_alpha_edge_exempting_tiny_regions`, wired to a new `--erosion-exempt-max-size <px>` flag. Confirmed the fully-automated version (no manual pre- classification, just feeding it the complete removable-region alpha and letting it auto-detect anything at or below the given size) reproduces the same result as the manually-verified fix. Additive/opt-in, default off — confirmed the existing default codepath is unaffected.

---

## 12. Art that fades toward the background colour renders as a dither mesh

**⚠️ Superseded for non-GIF deliverables by §16 (2026-08-17).** Everything below is still the right answer *if the output must be a GIF*. If it can be WebP or AVIF, `--recover-fade-alpha` reconstructs the original alpha exactly instead of cutting the faintest stages, and the fade renders as real translucency. Read §16 first; treat `--dither-mode none` as the GIF fallback, not the default answer.

**Found 2026-08-07** on `ruby.gif`, a 109-frame 640x640 gem icon with yellow four-pointed sparkles. Reported by Harkirat directly, from the delivered file, against a dark backdrop.

### The symptom
Most sparkles came out solid yellow, but some rendered as a **visible grid/mesh** — a regular crosshatch of transparent pixels through the sparkle body — instead of solid colour. The gem itself, the sparkle outlines, and the deliberately-removed white sparkle cores were all correct.

### Why this is NOT §10's Bug 5, despite both ending at `--dither-mode none`
§10's Bug 5 is about a **correct edge** being *composited* onto a flat colour, where the Bayer pattern that reads as soft antialiasing over texture reads as speckle over flat paint. The trigger is the *viewing background*, and the affected pixels are a thin edge band.

This is different in trigger, location, and cause: **the source art has a fade baked into it.** GIF has no partial alpha (§7), so the artist's fade-out was flattened against white at authoring time — the sparkle literally *is* progressively lighter cream in later frames. Measured on the real file: at peak the sparkle is `fdcb50`; mid-fade its body is a solid `fff2d1`, Euclidean distance **47.8** from white. The default band is `--tolerance 15` to `15 x 4.0 = 60`, so that solid body colour lands **inside the feather band**, gets assigned alpha ~0.73, and is dithered. The affected pixels are the sparkle's whole **interior**, not an edge, and they mesh no matter what you composite over.

So the alpha was arguably *right* — a 73%-transparent sparkle is a faithful rendering of a fade that no longer has an alpha channel to live in. It just looks wrong, because a spatial dither across a solid interior region reads as a mesh rather than as translucency.

### The fix, and what it costs
`--dither-mode none` — hard 50% cutoff on the already-defringed alpha. Measured before/after on the frames that showed it:

| source frame | faded body | opaque with Bayer (v1) | opaque with `none` (v2) |
|---|---|---|---|
| 68 | 803px | 651px (81%) | 762px (95%) |
| 97 | 2966px | 1393px (47%) | **2805px (95%)** |
| 103 | 2962px | 2016px (68%) | **2845px (96%)** |

The two faintest frames (61, 67) go to 0% opaque in both — below the 50% cutoff the sparkle simply disappears a beat earlier instead of meshing, which is the correct trade.

**Check the cost before reaching for it: `--dither-mode none` changes EVERY edge in the file, not just the offending region.** It was nearly free here because ruby's silhouette is mostly straight lines (`edge_hardness` ratio 0.506) — verified by zooming the outer navy silhouette in both versions and finding no new jaggedness, and by confirming 0 near-white fringe pixels in the outermost opaque ring. On a curve-heavy icon that trade would be worse, and narrowing `--feather-band-multiplier` would be worth measuring first.

### Generalizable takeaway
**A "solid" colour is only solid relative to the background you're keying against.** Before trusting the feather band, check whether any *large interior* region of the art sits inside it — `tolerance` to `tolerance x feather-band-multiplier` in Euclidean RGB distance. Feathering is designed for thin edge transitions; a wide interior region inside that band is the signature of a baked-in fade (or a pale design tint, which is §10 Bug 4's `--protect-band-only` case), and both want handling other than "let it dither."

---

## 13. The save message asserted a frame count it never read back

**Found 2026-08-07** while verifying `jewelry.gif` (170 frames) — caught by the verification step, not by the script.

### What happened
The script printed `Saved <path> (170 frames, durations preserved exactly)`. The written file has **168**. The line was `print(f"... ({len(durations)} frames, durations preserved exactly)")` — it restated the frame list the script *intended* to write and asserted a property of a file it had never opened.

### Why the file legitimately has fewer frames
Pillow's GIF encoder coalesces consecutive frames that come out **byte-identical after quantization**, folding their delays into the survivor. Source frames 166–168 differ by at most **9 RGB levels on at most 91 of 409,600 pixels** — the animation has settled into its resting pose and the residual difference is encoder noise. After palette quantization they are the same frame. Total playback was **3600ms before and after**.

**So the coalescing is not a defect and is not worth suppressing.** The dropped frames were visually identical; refusing the merge would only make the file bigger. The defect was purely the claim.

### The fix
`describe_written_timing(output_path, intended_durations)` re-opens the written file, reads its actual per-frame durations, and reports what is actually true:
- identical to intended → `"N frames, durations preserved exactly"` (unchanged wording, now earned)
- fewer frames, same total → `"N frames written from M intended -- K identical frame(s) coalesced by the encoder, total playback unchanged at Xms"`
- **total playback changed** → an explicit `WARNING:` to stderr, because that *would* be a real timing defect rather than encoder coalescing
- readback itself fails → says so, and never fails a job that already wrote its output

Verified on two synthetic files that isolate the branches: one whose middle frames drift ≤2 RGB levels (reports `4 frames written from 5 intended -- 1 identical frame(s) coalesced ... unchanged at 200ms`) and a control with clearly distinct frames (reports `5 frames, durations preserved exactly`). The old code printed the identical "preserved exactly" line for both.

### Generalizable takeaway
**Verification step 3 in SKILL.md tells the reader to compare input and output durations by reading the real file — but the script's own success message was doing exactly what that rule forbids.** A tool that reports on its own output must read that output back; restating the input is not a check, it's a claim wearing a check's clothing, and it is more dangerous than no message at all because it actively discourages looking. Worth grepping for the same shape anywhere else a message asserts a property of a written file.

---

## 14. Punching one same-colour interior hole while protecting a same-colour, same-size-range animated design element

**Found 2026-08-07** on `military-tag.gif` (126-frame dog-tag icon), delivered by a user who had already gotten 4 incorrect/ugly attempts from a live claude.ai v3.1.0 session on the same file.

### The symptom
The tag has a pure-white 4-point star (a real design element, must stay opaque) and a small round pinhole where the ball-chain threads through (must become transparent) — both near-white, both enclosed by the tag's navy outline, both non-border-touching. `--recommend`'s own suggested `--protect-outline-color 002864` reported the region's `outline_enclosure_all_frames` at only **47% enclosed across all 126 frames** (own evidence text: *"outline 002864 verified across 126 frames (47% enclosed)"*) — a real, honest signal that this asset's outline color isn't reliably enclosing, not something to trust blindly. Root cause: the star **twinkles** (its rendered shape changes size/aspect every frame, from ~75px to ~6000px across the sample), so a single fixed-frame `comp_footprint` containment check misses most frames.

### First attempt: `--tumble-safe` (sidesteps outline reliability) + `--keep-bg-blob-if-near` with a decoy colour
`--tumble-safe`'s default (protect everything except the single largest bg-colored component, computed fresh per frame) sidesteps the outline-reliability problem entirely — correct call, confirmed by full 127-frame verification later. But `--keep-bg-blob-if-near 000000` (a colour picked to match nothing, intending "hole-size-range alone decides") punched holes through the star's own antialiased boundary in the frames where the twinkle happens to fragment it into pieces inside the default `--hole-size-range 50,2000` — visible in a `--preview` contact sheet as a jagged bite out of the star (looked like solid dark fill only because it was composited over a dark preview background; it was actually alpha=0, confirmed by checking the raw alpha array directly rather than trusting the visual).

### Second attempt: real design colours as the keep-target — also wrong, in the other direction
Passing the tag's own body/sheen colours (`93b2f4,d1dbfc`) as `--keep-bg-blob-if-near` stopped the star damage, but now punched **zero** holes in **all 126 frames** — the pinhole itself got kept. Traced with the real `build_tumble_safe_protected_mask` function directly (not re-derived by hand): the pinhole's antialiased boundary (white → navy) passes, for a handful of pixels, within `near_tolerance`(40) of `d1dbfc` purely by coincidence (measured min distance 19.5) — and the match is an `.any()` over the whole dilated ring, so one coincidental pixel flips the entire component's verdict. More dilation doesn't fix this: the boundary pixels closest to the shape are included at every dilation radius once they first appear.

### The fix: separate the two by geometry, not colour
Measured the pinhole's real per-frame size/aspect across all 126 frames: **423–466px, aspect 1.00–1.04 — a near-perfect circle, essentially constant**, because the physical hole doesn't change even though the tag translates and swings. The twinkling star's fragments, sampled the same way, range 75–6070px, aspect 1.0–2.69, and only ever coincidentally overlap the pinhole's size band without also matching its aspect. `--hole-size-range 400,480 --hole-max-aspect 1.3` (still paired with a `--keep-bg-blob-if-near` decoy colour, required only because the code path is gated on that flag being present) admits **exactly one component per frame across all 126**, and it's the pinhole every time — confirmed by brute-force scanning every frame, not sampling.

### Verification note: `--verify`'s `protected_region_coverage` false-positives here
`--verify` correctly skipped its pixel checks given `--crop` changed the canvas size (its own documented behavior), so verification ran against an uncropped intermediate. On that, `leftover_background_opaque_px`, `edge_fringe_check`, `small_region_inflation`, and `timing` all came back clean — but `protected_region_coverage` flagged the merged star+pinhole candidate region as `looks_unprotected: true` (46.2% opacity). Confirmed as a false positive by two independent, more precise checks: (1) restricting the same opacity measurement to each frame's own correctly-identified star component (excluding the pinhole) still isn't clean-looking from the bbox math, but (2) directly checking "is every star-component pixel opaque, per frame, using that frame's own true star mask" — the unambiguous test — came back **100% opaque in all 126 frames, zero exceptions**. The false positive traces to the same root cause as `outline_enclosure_all_frames`'s low ratio and the known `band_interior_regions` grouping gap (tracked in the development repo's backlog): `analyze()`'s candidate-region detection ties a region to one fixed-frame bbox/footprint, which a translating design with a legitimate interior sub-hole breaks. Not fixed here (would need `verify()` to know about deliberately-carved sub-holes, which it currently cannot express) — noted as a real, novel gap for the deferred list rather than left silently unmentioned.

### Generalizable takeaway
**When a "keep vs. remove" distinction is needed between two same-colour blobs, ask which axis actually separates them before reaching for `--keep-bg-blob-if-near`'s colour-adjacency mechanism.** Colour-adjacency is fragile across an antialiased boundary — a coincidental match on a handful of transition pixels is enough to flip an entire component, in either direction, and more dilation does not fix a coincidental match found at low dilation. If one blob is physically constant (a real cutout) and the other is animated (breathing/twinkling/pulsing), size+aspect over the FULL frame range is usually the more robust discriminator — verify it by scanning every frame's actual measured values, never a handful of samples, since the whole failure mode here is an animated element occasionally drifting into the other's range.

### Addendum, same asset, found by the user zooming into the delivered file: `--erosion-exempt-max-size` left a whitish fringe around the punched hole
Passed `--erosion-exempt-max-size 519` on `--recommend`'s generic evidence ("152 small removed region(s) observed") without checking whether that number meant genuine incidental noise on THIS asset. It didn't: every one of those 152 detections across all 126 frames was either the pinhole itself (repeated once per frame) or a star-twinkle fragment that never actually enters this pipeline's removable set (confirmed: only the pinhole ever passes the `--hole-size-range`/ `--hole-max-aspect` gate). So the exemption had nothing genuine to protect — but it still did its job of restoring the pinhole to its exact PRE-erosion pixels, which skipped the normal `--edge-cleanup-erosion` pass that would have cleaned up the antialiasing blend between the white pinhole and the navy ring. Result: a handful of pale, technically-opaque, off-white pixels (measured `237,241,253` — not pure white, not navy, an untrimmed antialiasing blend) sitting right at the hole's edge, small enough to miss in a `--preview` contact sheet composited over transparency-checkerboard but visible zoomed in over a solid dark background.

**The fix:** drop `--erosion-exempt-max-size` entirely and let the default 2px erosion run normally. Re-verified across all 126 frames: fringe pixels went to zero, the hole's own true size grew modestly (~423–466px raw → ~632–682px post-erosion, roughly a 20% radius increase) because the navy ring is thick (15+px) relative to the 2px erosion radius — nowhere near the 50–70x runaway inflation §11 exists to prevent, which only happens when the wall around a removed region is thin relative to the erosion radius. `small_region_inflation` (from `--verify`) correctly did not flag this growth.

**Generalizable takeaway:** `--erosion-exempt-max-size`'s own evidence count from `--recommend` (or `--analyze`'s `small_removed_regions`) is a raw histogram of ANY small removable-by-color blob across every frame — it does not know which of those blobs actually survive into your SPECIFIC chosen protection pipeline as truly removable. Before applying the flag, check whether the asset actually has incidental noise distinct from its main removed-region logic (as §11's original gear/book case did) or whether, as here, the "152 regions" are just one legitimate, physically constant hole detected 126 times — in the latter case the exemption trades a real fringe defect for protection against an inflation risk that was never actually present.

---

## 15. A second, independent solution to §14's same problem — `--remove-region`, and where it needs help

**Found 2026-08-07**, same asset as §14 (`military-tag.gif`), from a parallel claude.ai live-skill session working the identical problem (star to keep, pin hole to remove, both enclosed by the same navy outline) with no knowledge of §14's approach. Reconciled into the repo 2026-08-08. Kept as its own section rather than merged into §14 because the two solutions are genuinely different in shape, not just different phrasing of the same fix — read both before picking one for a new case.

### The approach: `--protect-outline-color` (as normal) + a new inverse flag to carve the hole back out
Unlike §14 (which avoided `--protect-outline-color` entirely because its all-frame enclosure ratio measured only 47%), this session used `--protect-outline-color 002864` as normal — correct per-region framing either way, since it protects the whole navy-enclosed interior including the star — then added **`--remove-region`** (new flag, inverse of `--protect-region`: force-removes a manually specified region regardless of what protection already decided there) to punch the pin hole back out. The underlying insight, precisely: **"enclosed by the same outline color" is not the same claim as "the same region should get the same treatment."** `--protect-outline-color` correctly unions the whole enclosed area for one color; there was previously no way to say "protect this EXCEPT that sub-region."

**A real bug found and fixed in the same session, general beyond this one flag:** the first hand-rolled hole-punch (before `--remove-region` existed) zeroed alpha inside a circle without touching RGB, leaving the original antialiased white-into-navy blend color sitting at partial alpha — invisible over checkerboard, a visible pale halo over any solid composite. `apply_remove_regions()` fixes this generically: recolor every touched pixel to the LOCAL kept color (sampled fresh per frame from a thin ring just outside the removal mask, not a hardcoded hex) BEFORE tapering alpha down, so a fading pixel always reads as "surrounding color fading to transparent," never a ghost of what got removed. **This is a different root cause than §14's addendum fringe**, worth keeping distinct: §14's fringe came from `--erosion-exempt-max-size` skipping an EXISTING cleanup step (the main feathering path already defringes correctly); this one is about a hand-rolled alpha edit that bypassed the main feathering path entirely and so never got defringed in the first place. Both LOOK like "a whitish ring around a punched hole" — they are not the same bug, and the fix for one would not have fixed the other.

### Where it needs help: this flag alone did not solve this specific asset — confirmed independently, not just taken on faith
`--remove-region`'s own worked example (`--protect-outline-color 002864 --remove-region circle:283.5,231.5,15`) is a STATIC mask, same limitation `--protect-region` already has. This asset's pin hole is not static: **re-measured independently while reconciling this drop into the repo — the true hole center drifts up to ~67px from that fixed circle across the 126 frames** (the live session's own account cites ~150px, plausibly measured at a different scale/crop; both readings agree the drift is large, not marginal). Directly checking the STATIC-circle output against the real per-frame hole location: **96 of 126 frames (76%) do NOT actually have the true pin hole punched** — the fixed circle is simply removing the wrong patch of navy ring in most frames. The flag's own documentation is honest about this ("do not use this for a target that moves/resizes across frames... without re-deriving the mask per frame yourself first") — this is a confirmation that the caveat is load-bearing on this exact asset, not a defect in the flag or its docs.

The live session's real fix for this (§ their Bug 3/4, condensed): track the hole's true per-frame center via `cv2.HoughCircles` on each source frame independently, and — after finding that a per-frame RE-MEASURED radius was itself corrupted by a shine/sparkle sweep passing through the same screen area in some frames (a real second bug, a differently-principled edge/gradient-based method disagreeing with a color-threshold radial scan is what caught it) — settle on ONE constant radius measured only from unaffected frames, applied to every frame's own tracked center. None of this tracking happens inside the script; it is bespoke, external, per-asset work.

**§14's `--tumble-safe` + `--keep-bg-blob-if-near` + tight `--hole-size-range`/`--hole-max-aspect` approach handles this exact drift natively, with no external tracking script**, because it re-derives the hole's mask fresh from each frame's own connected-component geometry rather than applying one fixed region — the drift was never a problem for it, verified in §14 across all 126 frames without needing to know the drift's magnitude in advance.

### Generalizable takeaway: two valid tools for the same *shape* of problem, different fits
- **`--remove-region` is the more general, more directly-expressive fix** when the target to punch out is static, or as a component after you've separately solved per-frame tracking yourself — it works regardless of whether the hole is geometrically distinguishable from nearby decoration (§14's approach specifically needed the hole and the decoration to differ in measurable size/aspect across every frame, which was true here somewhat fortuitously, not guaranteed on a future asset).
- **§14's geometric-gate approach is the more robust fix for a moving/resizing target with no external tooling**, but only when the thing to remove and the thing to keep really are separable by a stable, measurable geometric signal (size, aspect, or similar) across the whole animation — verify that separation across every frame before trusting it, same discipline §14 itself used.
- **Neither is a substitute for the other in every case.** A static hole shared with animated same-colored decoration wants `--remove-region`. A moving hole with no reliable external tracking step wants the geometric-gate approach. A moving hole where NEITHER geometric separation nor tracking tooling is available is a real gap this skill does not yet close.


## 16. Escaping GIF's 1-bit alpha: recovering a baked-in fade, and WebP/AVIF output

Real job, 2026-08-17: `love.gif`, 640×640, 124 frames, a gamepad-in-a-heart sticker with yellow pulses that expand outward from the heart's outline while fading out. The ask was to remove the white background while keeping the white controller buttons — and, because the requester had already worked out that GIF cannot express a fade against transparency, to deliver WebP instead. That prediction was correct, and provably so.

### 16.1 The fade was flat-opacity on one solid colour — so it is EXACTLY recoverable
Measured before choosing any approach: each pulse frame carries ~30,000 pixels at a *single* blend fraction of pure `#fdcb50`, and across the animation those fractions are **1.0 → 0.8 → 0.6 → 0.4 → 0.2**. Not a gradient, not a blur — a global opacity ramp that the GIF export flattened against white. Since `px = a·C + (1−a)·W` with `C` and `W` both known, `a` is arithmetic, not estimation.

**The falsifier that made this trustworthy:** frame 0 has no pulse. If the classifier were sloppy it would report phantom yellow there. It returned **zero** pixels. Any "detector" for this should be checked against a frame where the answer is known to be nothing — a detector that cannot fail has not been tested.

### 16.2 Why NO GIF setting can represent it
Yellow sits 182.6 (Euclidean RGB) from white. The feather band is `--tolerance`(15) → `× --feather-band-multiplier`(4) = 15…60.

| Fade stage | Distance from white | What GIF did |
|---|---|---|
| α 0.2 | 36.5 | inside band → dithered, then erosion ate it (**99% destroyed**) |
| α 0.4 | 73 | above band → **opaque pale cream** |
| α 0.6 | 110 | above band → **opaque pale cream** |
| α 0.8 | 146 | above band → **opaque pale cream** |
| α 1.0 | 182.6 | opaque yellow — correct |

**And it cannot be tuned around.** Widening the band to catch α 0.8 means reaching past 146 — but a real solid art colour, the lavender controller body, sits at **121.7**. Any band wide enough to catch the fade dissolves genuine artwork. The fade's range *straddles* an art colour, so no single distance threshold separates them. That is the structural argument; it generalises to any asset where a fading element passes through the colour-distance of a solid one.

A second, uglier symptom appeared at the faintest stage: dithering α 0.2 produced a sparse Bayer pattern, the 2px erosion then removed 99% of it, and the survivors were left stranded as isolated **speckle dots** scattered where the pulse should have faded to nothing. `--verify` flagged this as `small_region_inflation` (a 9px input region → 638px out, 70×).

### 16.3 The fix: unmix against the art's own palette, not against a distance threshold
`--recover-fade-alpha` asks a different question per pixel: *is this explained as the background blended with ONE known art colour?* That separates cleanly where a distance threshold cannot — measured on frame 36, yellow came back 99.2% partial-alpha while every other palette colour was ~99% fully opaque.

**⚠️ The palette build order is load-bearing, and getting it wrong silently reproduces the bug.** A fading element's intermediate stages cover tens of thousands of pixels per frame, so they rank as *dominant colours* and get admitted as solid palette entries of their own (`#feeab9`, `#fee096`, `#fdd573` all appeared alongside the true `#fdcb50`). Every faded pixel then unmixes against its own stage at α≈1.0 and renders **fully opaque** — the exact GIF artifact, now inside a format that didn't need to have it. Fix: consider candidates **furthest from the background first** (a fade stage is always nearer the background than the colour it fades from), and reject any candidate already explained as a blend of the background and an accepted colour.

Two further guards, both from real failures during this build:
- **Fade detection must scan every frame.** Sampling every 10th frame for speed silently stopped detecting the fade and produced a plausible-but-wrong file. That is §10's own "verify against every frame, not a spot-check sample" rule reasserting itself. Unmixing is ~50ms/frame; a full scan is affordable and a sample is not worth the failure mode.
- **A palette-coverage guard is mandatory, because the failure is silent.** On gradient or photographic content every pixel becomes a residual case, gets forced opaque, and the run *reports success having recovered nothing*. The script now warns below 90% coverage (this asset: 98.7%).

### 16.4 Format findings (all measured on this asset, 640×640 / 124 frames unless noted)

| Format | Size | Encode | RGB error | Alpha error |
|---|---|---|---|---|
| WebP lossless `-m 4` | 2114 KB | 22.2s | **0 (exact)** | **0 (exact)** |
| WebP lossless `-m 0` | 4944 KB | 2.6s | 0 | 0 |
| WebP lossy q95 | 3617 KB | 6.9s | 1.51 | 0 |
| WebP lossy q85 | 2675 KB | 6.7s | 1.93 | 0 |
| AVIF q100 | 5034 KB | 7.0s | 1.89 | 0 |
| AVIF q95 | 2146 KB | 7.5s | 1.92 | ±20 |
| **AVIF q85** | **1331 KB** | 7.1s | 2.03 | ±31 |
| AVIF q70 | 785 KB | 5.6s | 2.28 | ±50 |

- **WebP lossy is pointless at native resolution** — q85 (2675 KB) and q95 (3617 KB) are both *bigger* than lossless (2114 KB), because lossy injects noise into large flat regions and that defeats inter-frame prediction. **But the ordering REVERSES once downscaled**: at 128×128, lossless was 1190 KB against lossy q80's 650 KB. Neither claim is general — the crossover is what matters.
- **AVIF `quality=100` is a trap**: not lossless (max RGB delta 145) *and* the largest file of all.
- **AVIF fits ~3× the frames under a hard cap.** Discord's 256 KB emoji limit: AVIF held all 124 frames at 128×128 in **244 KB at q70** (q85 was 357 KB and did *not* fit); WebP had to drop to 42 frames to fit at all. Confirmed live by the requester that Discord accepts *and animates* AVIF emoji.
- **AVIF's alpha "error" is not where the max-delta suggests.** Despite ±31–50 maxima, every fade stage reproduced with median alpha exactly right (255/204/152/102/50); on the faintest stage the mean error was 0.81/255 (1.6% relative) at q85. The outliers sit on hard edges, not in the fade body. Worth measuring per-feature rather than trusting a global max.
- **`-m 6` is never worth it, but `-m 0` is content-dependent.** Here `-m 6` cost 415s against `-m 4`'s 9.2s (**45×**) to save 2.3%; `-m 0` was 8.5× faster but **+134%** size. Dior's Builds measured the same knob on gradient-bed nameplate frames and got `-m 0` at only **+14%** (and `-m 6` *worse on both axes*). Same flag, opposite verdicts — **measure `-m` per asset class; only "avoid `-m 6`" transfers.**

### 16.5 Two footguns that make a wrong result look like a passing one
- **Pillow returns duration 0 for every frame when READING an animated WebP.** A naive timing check therefore passes vacuously against a file whose timing is actually broken. Read the container instead (`webpmux -info`); `read_webp_durations()` does this and returns `None` rather than guessing when webpmux is absent. Same class as §9's Pillow-duration issue, different format. For the same reason `--verify` now **refuses** a non-GIF output rather than reporting a pass it cannot substantiate.
- **Resizing destroyed the recovered alpha, and the result looked *better* for it.** `resize_rgba_ frames` re-binarized alpha (`a > 127`) and resized RGB without premultiplying. A 128px emoji came back with **14 distinct alpha levels, 99.4% fully binary** — the fade silently gone — and the file was a pleasingly small 97 KB *because* the pulses had been deleted. Caught only by testing end-to-end and counting alpha levels. 8-bit-alpha output now premultiplies before resampling, unpremultiplies after, and skips the post-resize erosion (which exists to trim 1-bit-cutoff fuzz that no longer occurs). **A smaller-than-expected file is a symptom to investigate, not a win.**

### 16.6 `--recommend` gave three suggestions on this asset and two were wrong
1. **`--pixel-art`** — `edge_hardness` 0.425 reads "hard-edged", but zooming 8× showed a real 1–2px antialiasing ramp. This is exactly §1's caveat (a clean vector export with a thin AA band scores low); `--pixel-art` would have disabled feathering and erosion on curve-heavy art.
2. **`--erosion-exempt-max-size 487`** — the "1070 small removed regions" **were the controller buttons**, i.e. the very design the user asked to preserve. The ≤500px ceiling exists to keep protected regions out of this measurement but assumes design regions are *large*; four ~287px dots sailed under it. Applying the flag to real design skips normal edge cleanup and leaves a fringe — the v3.3.3 regression, recurring with a new signature.
   **Fix shipped:** classify by **persistence**, not size (per §14's logic — design is physically constant, incidental gaps are transient). A region present in ≥90% of frames is treated as design and excluded from the suggestion. ⚠️ Fixed-width bins were tried first and are *measurably wrong*: the buttons measure 286–306px and straddle a 25px bin edge, scoring 47.6% and 83.9% so that neither half cleared the threshold despite being present in every frame. Cluster by **relative tolerance** (±15%) instead.
3. `--protect-outline-color 002864` — correct, verified across all 124 frames.

### 16.7 Check whether your input is already a degraded proxy
The requester also had `love.mp4`. It was tested rather than assumed, and it is the **worse** source: 512×512 (vs the GIF's 640×640) and, decisively, H.264 ringing plus 4:2:0 chroma subsampling scatter the fade off its flat levels (IQR 0.04–0.13, peak-bin fraction 0.23–0.80) where the GIF puts ~30,000 pixels at one exact value. A flat 256-colour GIF can be a *better* recovery source than a 24-bit video.

But ask the question anyway, early: this whole pipeline is archaeology on a flattened artifact, and if an original with real alpha exists (After Effects / Lottie / Rive / SVG), exporting from it beats any recovery. Dior's Builds' nameplate work is the cautionary version — a session concluded an asset "genuinely has no alpha channel" when the alpha was there all along and ffmpeg's *default decoder choice* was discarding it (`-c:v libvpx-vp9` recovered 234 distinct alpha values). **A tool's default reading of an asset is not the asset.**

### 16.8 Validated across a 5-asset corpus, not just the motivating file
Run 2026-08-17 against four further real emoji (`heart`, `gift`, `explosion`, `crystal`) chosen to attack specific assumptions. **Two predicted failures did not occur**, which is worth recording as honestly as a failure would be:

| Asset | Probe | Result |
|---|---|---|
| `heart` | replication of a fading pulse | fade found (`#384998`), coverage 99.2% — method is not overfit |
| `gift` | many *small* sparkles vs `min_px=2000` tuned on a 30,000px ring | **prediction wrong** — fade found, coverage 99.3% |
| `explosion` | tumbling motion (§10's failure class) | correctly found **no** fade; no fixed-region artifacts — supports position-independence |
| `crystal` | art colours very close to the background | **prediction wrong** — near-white crystals stayed opaque, coverage 99.7% |

**But `crystal` exposed a real latent fragility.** Its `#d2dcfd` (distance 57 from white, 261k px) is a *solid art colour* that the palette builder REJECTS as a blend-impostor, because it is genuinely explained as 43% `#93b2f4` over white (residual 3.6). It survived only because it sits **interior**, where topological protection keeps it opaque. **A near-background solid colour that appears at the silhouette edge would be unmixed to partial alpha and go semi-transparent.** The impostor-rejection rule that fixes the fade-stage bug creates this one; they are the same mechanism pointed in opposite directions.

**⚠️ This WAS hit, on `crystal` itself — an earlier draft of this section claimed "not hit on any corpus asset" and was wrong.** A single-frame spot-check sampled a frame where that colour happened to sit interior; compositing the whole animation over a checkerboard exposed it immediately. Measured: **1,092,411 solid-source pixels across 130 frames rendered at alpha ~109/255 instead of 255** — the background visibly showing through the artwork. *Lesson within the lesson: a single-frame spot-check is not a test for a defect that depends on position. Composite every frame over a checkerboard AND a flat colour before believing an asset is clean.*

**Fix shipped — a two-pass palette.** The discriminator is the PARENT: a fade stage's parent is a fading colour, a solid tint's parent is not. Pass 1 rejects every background-blend candidate (that is what makes the fading colours findable at all); pass 2 rebuilds the palette KEEPING solid near-background tints, rejecting only blends whose parent is a detected fading colour. Result: 1,092,411 → 0 wrongly-translucent solid pixels, with love.gif's fade ramp and frame-0 falsifier unchanged.

**Format conclusions, now measured on 5 assets rather than 1:**

| Asset | Frames | WebP m2 | WebP m4 | m2 time | m4 time | AVIF q85 | q85 as % of m4 |
|---|---|---|---|---|---|---|---|
| love | 124 | 2163 KB | 2114 KB | 11.3s | 22.6s | 1331 KB | 63% |
| heart | 35 | 595 | 575 | 3.3s | 5.9s | 392 | 68% |
| gift | 172 | 1519 | 1403 | 11.0s | 20.5s | 675 | 48% |
| explosion | 77 | 1215 | 1178 | 7.3s | 13.0s | 655 | 56% |
| crystal | 130 | 1416 | 1408 | 9.1s | 16.6s | 396 | 28% |

- **`-m 2` is the right default, not `-m 4`** — 0.6–8.3% more bytes for ~2× the speed, consistently across all five. (Contrast `-m 0`: +134% on love, +14% on Dior's Builds' content — the curve between 0 and 2 is steep and content-dependent, the curve between 2 and 4 is flat and boring.)
- **AVIF q85 beat WebP lossless on every asset**, but by 28–72% — the *direction* generalises, the *magnitude* does not. Do not quote "37% smaller" as a rule.
- **All five fit Discord's 256 KB emoji cap at 128×128 with every frame kept**, at q85 (heart, crystal) or q70 (love, gift, explosion). So "AVIF, all frames, try q85 then q70" is a sound default procedure — but it is a procedure that MEASURES, not a fixed quality number.

### 16.9 Known limits of `--recover-fade-alpha` (not yet hit, recorded before they are)
- **A fading element that OVERLAPS artwork** is a blend of glow+art, not background+one colour. It becomes a residual case and is forced opaque — the translucency over the art is lost. Degrades safely but silently; the coverage guard only catches it if the overlap is large.
- **A fading element whose colour EQUALS a solid art colour** is the dangerous one: that colour stops being a flood-fill barrier, so the fill can leak through solid artwork and punch it transparent. This is precisely why `--fade-color` exists as a manual override.
- **Strokes thinner than `2 × FADE_EDGE_DILATE` (6px)** let the edge rim reach through from both sides. The interior-protection warning is the designed detector and fires with a count (10 px on love, 349 on heart) — it is meant to be read, not ignored.

### 16.10 An observation bigger than the feature itself
`--recover-fade-alpha` derives protection **topologically** — enclosed-and-unreached-by-the-flood means opaque — with no outline colour to verify and no region geometry to supply. On `love.gif` it protected the controller buttons perfectly with **zero user input**, where the normal path required `--protect-outline-color 002864` discovered through analysis. That is position-independent by construction, so it also sidesteps §10's whole fixed-region failure class, and with erosion off it sidesteps §11's inflation class too.

If that holds generally, it is a better default protection strategy for flat vector art than either `--protect-outline-color` (§2) or `--protect-region`. It is currently gated behind a fade-oriented flag name and a webp/avif requirement — the latter is stricter than necessary, since binary alpha is enough when there is no fade to preserve. **Observed on 5 assets, not proven; recorded as the direction this skill should probably go next, not as a claim.**

### 16.11 Decision recorded: `img2webp -exact` was considered and NOT adopted
libwebp can rewrite RGB under fully-transparent pixels to improve compression; `-exact` forbids it, and Dior's Builds passes it. Not adopted here because: this script sets transparent pixels to the background colour (the least harmful value for this content), its own resize path premultiplies and is therefore immune regardless, and adopting it means adding an external-binary dependency to the main output path with a Pillow fallback to maintain — for a benefit not demonstrable on any asset tested. **`-exact` is the lever if a halo is ever actually observed.** Recorded so this is not re-litigated from scratch.

**Re-examined 2026-08-17, same day, after Harkirat asked whether this predated WebP support and whether Dior's Builds uses `img2webp` for exactly this.** Both halves of that challenge were fair, and one of them found a real gap:

- **Timing:** the decision was NOT made before WebP support — this section IS the WebP/AVIF section, written in the same commit that shipped the feature.
- **Dior's Builds does use it**, for APNG → animated WebP, and its reason does not transfer: *"libwebp's own CLI set ships no APNG reader at all"*, so it needs a two-step (ffmpeg extracts frames, `img2webp` assembles them). Pillow reads APNG natively, so this script needs neither binary for the same job.
- **The real gap:** this decision was argued entirely on DEPENDENCY grounds and never compared the encoders' OUTPUT. "Not demonstrable on any asset tested" referred to the `-exact` halo, not to size or quality.

**So it was measured.** Identical 40 RGBA frames from a real processed asset, both encoders lossless: **Pillow 374.0 KB vs `img2webp` 379.1 KB** — Pillow is 1.3% SMALLER, and both preserve alpha identically. There is no output-quality case for the dependency, which is what the original decision assumed without checking. The rejection stands, now on evidence rather than on argument.

### 16.12 A translucent element whose TRUE colour never appears at full strength
Found on `gift.gif` after the user spotted the four-dot sparkle turning *whitish* as it faded.

The sparkle is drawn at a roughly **constant ~27% opacity**, so pure `#6969f2` barely exists anywhere in the animation. It therefore never clears `build_art_palette`'s frequency floor, while its *blended* stage `#d1dcfb` (thousands of pixels every frame) sails over it. The blend is then admitted as a SOLID palette colour and rendered fully opaque — a pale lavender, which reads as white-ish. The fade information was not lost by the encoder here; it was lost by the palette builder picking the wrong endpoint of the ray.

**This is the mirror image of the fade-stage-impostor bug:** there, a blend was wrongly admitted as solid *while the true colour was present*; here, a blend is wrongly admitted as solid *because the true colour is absent*. Same symptom, opposite cause.

**Fix: `--fade-color` now INJECTS the named colour into the palette** instead of snapping to the nearest existing entry. Snapping was useless for exactly this case — the nearest entry *is* the wrong pale colour, and `#6969f2` sits 155 away, past the match tolerance, so the flag simply errored out. `--recover-fade-alpha --fade-color 6969f2,fd6050` produces the correct translucent sparkle.

**⚠️ An automatic fix was attempted and REVERTED — do not re-attempt without reading this.** "Saturation promotion": for each accepted colour, walk its background→colour ray looking for a more saturated colour present at a lower count, and promote to it. Measured net-harmful across the corpus:
- `crystal.gif`: promoted the genuinely-solid `#d2dcfd` to `#8599f5`, **re-breaking the exact semi-transparency bug the two-pass palette had just fixed**.
- `explosion.gif`: emitted a duplicate palette entry (`#93b2f4` twice).
- `gift.gif`: only reached `#c4d0f2` — still not the true `#6969f2`.

Root reason it cannot work from colour statistics alone: *"pale colour is a blend of a rarer saturated colour"* and *"pale colour is solid art that happens to be collinear with a saturated colour"* are **indistinguishable in a histogram**. Separating them needs evidence the palette builder does not have (per-region temporal behaviour). `--fade-color` is the working escape hatch, and the auto-detector should be expected to miss this class.

### 16.13 Is WebP/AVIF worth it when there is NO partial transparency?
Yes — measured, including on `explosion`, which has no fading element at all:

| Asset | Original GIF | plain GIF out | WebP lossless | AVIF q85 |
|---|---|---|---|---|
| explosion | 1506 KB | 1057 KB | 1216 KB | **665 KB** |
| crystal | 1189 KB | 1061 KB | 1417 KB | **392 KB** |

1. **Edge quality** — GIF's 1-bit alpha forces every antialiased silhouette pixel to be dithered or cut; WebP/AVIF keep the real antialiasing. Applies to *every* asset, fade or not.
2. **Size** — AVIF q85 beat the plain GIF output on both.
3. **Protection comes free** — `--recover-fade-alpha` derives protection topologically, so interior detail stays opaque with no flags at all. Visible in the corpus preview: `gift`'s plain-GIF output has its white box stripes punched TRANSPARENT (they are background-coloured and nothing protected them), while the WebP/AVIF outputs keep them correctly opaque with zero user input.

**Ship GIF only when the destination requires GIF.** Otherwise AVIF q85 is smaller and better, and WebP lossless is the bit-exact master.

### 16.14 A SOLID art colour inside the feather band is silently deleted from a GIF
Found when the user reviewed the corpus GIFs and reported colours missing from the *interior* of `explosion` and `crystal`, and a white strip missing from `gift` — regions that are not the background colour and should never have been touched.

Cause: the feather band runs `--tolerance` (15) to `× --feather-band-multiplier` (4) = **15…60**. Any solid colour whose distance from the background lands in that window is given partial alpha and then dithered/eroded away. Measured on these assets:

| Colour | Distance from white | Fate under the default band |
|---|---|---|
| `#d2dcfd` (explosion, crystal interior) | 57.0 | **inside 15–60 → deleted** |
| `#d1dcfb` (gift strip region) | 57.9 | **inside 15–60 → deleted** |
| `#93b2f4` (crystal mid-tone) | 133.1 | outside → survives |
| `#bb9bf1` (love lavender) | 121.7 | outside → survives |

That is why *half* of crystal's colours survived and half did not — the survivors were simply further from white. Same structural shape as the fade problem in §16: a colour-distance window that cannot separate "background blend" from "real art".

**`--protect-band-only` alone did NOT fix it** (tried first, measured: explosion still lost 13.8% of its opaque pixels versus the WebP reference). What works is narrowing the band so the colour falls outside it — `--feather-band-multiplier 3.0` took explosion from 13.8% → **3.0%** and gift from 16.1% → **2.1%** loss, where the remaining few percent is ordinary 1-bit edge antialiasing.

**Fix shipped:** `--recommend` now reads `band_interior_regions`' `solid_tint` distances and, when one falls inside the band, emits a computed `--feather-band-multiplier` that stops short of it, with evidence naming the colour and its distance. Previously it had all the data and never did the arithmetic.

**This class cannot occur in a WebP/AVIF output at all**: `--recover-fade-alpha` identifies such a colour as a solid palette entry and keeps it fully opaque. The GIF path needs per-asset flag tuning that the new path derives on its own.

⚠️ **Process lesson, and the more important half.** These outputs were generated with NO flags as a naive size baseline, then placed in a review folder beside properly-processed WebP/AVIF files without being labelled as naive. The user reasonably read them as the skill's real GIF output. A baseline that is not labelled a baseline is a false claim about the tool. Label deliberately-naive artifacts, or do not ship them next to real ones.

### 16.15 Objective way to compare a GIF output against a WebP one
Rather than arguing about which colours "look" missing: the WebP output is verified-correct, so **pixels opaque in the WebP but transparent in the GIF are exactly what the GIF lost.** Per-frame average across the corpus after proper flags:

| Asset | opaque in WebP | lost in GIF | % lost | top lost colour |
|---|---|---|---|---|
| love | 147,978 | 2,979 | 2.0% | `#052a75` (edge) |
| heart | 159,056 | 2,946 | 1.9% | `#052a75` (edge) |
| gift | 94,217 | ~2,000 | 2.1% | `#052a75` (edge) |
| explosion | 127,497 | ~3,800 | 3.0% | `#052a75` (edge) |
| crystal | 103,880 | 3,510 | 3.4% | `#052a75` (edge) |

When the top lost colour is the OUTLINE colour and the loss is 2–3%, the GIF is correct and you are seeing the unavoidable cost of 1-bit alpha on antialiased edges. When the top lost colour is an interior fill (`#ffffff`, `#d2dcfd`) and the loss is >10%, something is genuinely misconfigured.

### 16.16 An opaque translucent element punches a hole through whatever it covers
A fading colour is deliberately NOT a flood-fill barrier — background behind a translucent element has to stay reachable (love.gif's gap between heart outline and pulse ring depends on it). But at FULL opacity such an element occludes, and where it crosses solid artwork, exempting it opens a corridor the background flood pours through.

Confirmed on `crystal.gif`: an opaque yellow sparkle lying across the crystal's navy outline **emptied the crystal's white interior in 59 of 130 frames — 24,520 px in one blob.** A leak map (barrier black / correctly-outside green / leaked red / translucent corridor yellow) showed the sparkle sitting exactly on the outline.

**Rejected fix:** a plain opacity cut (any pixel at t≥0.95 blocks). Fixes crystal, but **seals love's gap in 27 frames** — trading one visible bug for another.

**Shipped fix — an ART PRIOR.** Colour alone cannot separate "opaque sparkle over navy" from "opaque sparkle over background". Position over TIME can: the outline is art in most frames, background is not. A near-opaque fading pixel (`t ≥ FADE_OPAQUE_BLOCK` 0.90) now blocks only where solid art is present in ≥30% of frames (`FADE_ART_PRIOR`). Measured: crystal 59/130 → **0**, love's ramp identical, falsifier still passing, opaque-white within 0.17%.

### 16.17 `--verify`'s `looks_fringed` is unreliable — do not decide erosion with it
`--edge-cleanup-erosion`'s 2px default is calibrated for the BAYER path. Under `--dither-mode none` there is no dither noise to trim and 2px bites thin strokes from both sides. Measured, non-background px wrongly deleted at erosion 2 vs 1:

| asset | erosion 2 | erosion 1 |
|---|---|---|
| crystal | 931,569 | 466,092 |
| explosion | 448,205 | 223,686 |
| gift | 635,720 | 313,631 |

So erosion was reduced — **to 0, which was wrong**, and Harkirat caught a visible pale fringe on love.gif immediately. `--verify` reported `looks_fringed: False` at erosion **0, 1 AND 2**, so it could not have caught this and actively misled the decision.

**Measure the outer opaque ring instead** — for the outermost ring of opaque pixels, how many are closer to the BACKGROUND colour than to the art colour:

| erosion | mean distance to true outline colour | % of ring closer to background |
|---|---|---|
| 0 | 162.3 | **49.1%** ← visible fringe |
| 1 | 15.6 | 0.2% |
| 2 | 9.0 | 0.7% |

**Resolved defaults: 0 for WebP/AVIF (8-bit alpha needs no fringe trim), 1 under `--dither-mode none`, 2 for the Bayer path.** ⚠️ `--edge-cleanup-erosion` now defaults to `None` and resolves explicitly — the previous version could not distinguish "user typed 2" from "default is 2" and silently overrode an explicit value, which also made a diagnostic probe return identical numbers for 0 and 2 and nearly produced a second wrong conclusion.

### 16.18 Bayer 8×8, and why error-diffusion dithers are wrong for ALPHA
`--bayer-size` now defaults to **8** (64 threshold levels vs 4×4's 16), tracking the intended alpha **2.5× more closely** (mean local-density error 0.0051 vs 0.0128) at identical temporal stability. `--bayer-size 4` reproduces pre-v5.0.0 output byte-identical.

**Floyd–Steinberg, Jarvis, Sierra, Stucki are disqualified for alpha**, and the test that shows it must be able to fail. A first attempt nudged one pixel by 2% and scored 0 for both methods — vacuous, because that pixel never crossed a threshold. Redone across two frames whose right half is **byte-identical**:

| dither | px changed in the static region |
|---|---|
| Bayer 4×4 | **0** |
| Bayer 8×8 | **0** |
| Floyd–Steinberg | **312 (8.1%)** ← visible crawl |

Error diffusion propagates each pixel's error to its neighbours, so the pattern depends on scan order and everything upstream: it crawls frame to frame even where the art is static, and that also defeats GIF inter-frame compression. Ordered dithers are position-indexed and therefore temporally stable by construction. (gifsicle still uses Floyd–Steinberg for COLOUR quantization in the tiers — a different problem; tracked in the development repo's backlog for the open question of whether even that is right.)

### 16.19 `--recommend`'s outline gate was too strict — a 22× worse result from being "safe"
The gate refused `--protect-outline-color` whenever `anomalous_frame_count != 0`, treating "enclosure breaks on some frames" as "unusable". On `crystal.gif` the outline is verified with `enclosure_ratio` 1.0 but breaks on 75/130 frames (the sparkle crossing it), so `--recommend` fell through to `--protect-band-only` — **19.99% of the artwork lost against the outline's 0.91%.**

A nonzero count means "the substitution path will engage", not "reject". Background LEAK remains a hard reject (it over-protects, with no safe fallback). ⚠️ **A conservative gate is not automatically the safe choice** — it has to be judged against what the fallback actually costs.

### 16.20 Borrowed masks: UNION with the frame's own, and CLAMP to its silhouette
When enclosure is flagged anomalous, the per-frame mask substitution used to REPLACE that frame's mask with a borrowed one. Two separate defects came out of that, both on crystal:

- **Replacement discards correct information.** The frame's own mask encloses whatever that frame does enclose. Pure replacement deleted ~500 px from inside the small left crystal in frames 0-19. Fix: `(own | borrowed)`.
- **A borrowed mask describes ANOTHER frame's geometry.** On anything that moves or grows it protects background the current frame does not cover — a white wedge floating above the tall crystal's tip, ~1,600 px/frame. Fix: `& this-frame's-filled-silhouette`.

Combined: `(own | borrowed) & silhouette`. Measured: hole 502 px → 10-17 px, wedge +1,642 → 0, art loss 0.95% → 0.89%.

⚠️ **Also tried and REVERTED:** suppressing the bimodal gap detector when the small mode is the MAJORITY, on the theory that occlusion is the exception. On crystal the small mode IS the majority (75/130) — and is the BROKEN state. Suppressing took art loss from 0.95% to 7.07% and left an 11,451 px hole. **A majority can be wrong.**

### 16.21 `--recommend` now recommends the FORMAT, ranked for compatibility not just bytes
It previously suggested flags but never the container — the first decision, not a packaging afterthought. A `gradient_fade` region means GIF structurally cannot carry the asset. Ranking (Harkirat's, 2026-08-17):

- **full resolution** → WebP lossless > AVIF q85 > GIF
- **under a byte cap** → AVIF > WebP > GIF (AVIF keeps EVERY frame; the others drop a third to two-thirds)
- **maximum compatibility** → WebP > GIF > AVIF
- **GIF** only when required, or a genuine win on size/render-time at near-equal quality

Always report frame counts beside file sizes — under a cap, frames are what actually gets spent.

---

## 17. A WebP source silently shifted every frame duration by one

**Found 2026-08-17** on the first job whose SOURCE was a WebP rather than a GIF — Harkirat had manually removed the gamepad from `love.gif` and supplied a lossless WebP export of the result. Not found by a test; found because the save line printed a total that disagreed with the source.

### What happened
The script read the 124-frame source, processed it correctly, and wrote a WebP whose durations were:

| | durations | total |
|---|---|---|
| source | `[220, 20 x122, 340]` | 3000 ms |
| output | `[100, 220, 20 x122]` | 2760 ms |

The list is **shifted one position right**: a 100 ms frame that exists nowhere in the source is prepended, and the final 340 ms frame is dropped. The animation ran 240 ms short with every frame's timing off by one.

### Root cause — a Pillow API difference that fails silently
`GifImagePlugin` populates `info['duration']` inside `seek()`. `WebPImagePlugin` populates it only inside `load()`. The script used the same seek-then-read pattern for both:

```python
im.seek(i)
durations.append(im.info.get('duration', 100))   # WebP: returns the PREVIOUS frame's value
```

On a GIF this is correct and always has been. On a WebP it returns whatever the last *loaded* frame left behind — a one-position lag, with Pillow's 100 ms default standing in for the frame that was never read. No exception, no warning; just wrong numbers.

**Four call sites shared the bug**, and they concealed each other: `process()`'s source loader (wrote the wrong output), `load_gif_rgba_frames`, `read_animation_timing`, and — critically — `describe_written_timing`, the readback added in §13 precisely to stop the script asserting timing it had not verified. Because the readback used the same lagged pattern, *intended* and *written* agreed with each other and the script reported **"durations preserved exactly."** §13's fix was correct in design and still could not catch this: a readback written with the same faulty assumption as the writer confirms the assumption, not the file.

### The fix
One helper, used at all four sites:

```python
def frame_duration_ms(im, default=0):
    im.load()                              # load-bearing: WebP/AVIF set duration only here
    return im.info.get('duration', default)
```

Verified: the GIF path is **byte-identical** before and after (compared against the retained `love_transparent.gif` baseline), so this is a pure no-op wherever it already worked, and the WebP output now round-trips `[220, 20 x122, 340]` element-wise, not merely by total.

### It also closed a separate open item
The autonomy backlog carried "AVIF durations cannot be read back — Pillow exposes none." That was the *same* bug wearing a different symptom: seek-only on an AVIF returns `0` for every frame, so `read_animation_timing` summed to zero and honestly reported the timing as unverifiable. With `load()` it returns `[220, 20 x122, 340]`, total 3000 ms. **The item was never an AVIF limitation at all** — it was this missing call, and it sat on the backlog as an external constraint because nothing had tested the alternative.

### Lessons
- **A readback only verifies if it reads the file by a genuinely different path than the write.** Sharing a helper, an assumption, or an API quirk with the writer turns verification into an echo. This is §13's lesson one level deeper: §13 stopped the script asserting what it never read; §17 shows that reading it back through the same flawed lens is still not evidence.
- **Format plugins differ in WHEN they populate metadata, not just what.** A pattern proven on GIF carried to WebP/AVIF without re-testing, and the failure was silent because both APIs return a plausible integer.
- **"Cannot be done" on a backlog deserves one falsification attempt before it is recorded as a constraint.** This one cost a single `load()` call and had been written down as a property of Pillow.
- **Scope check before claiming impact:** every previously delivered file was rendered from a GIF source, so all measured correct (3000 ms, `[220, ..., 340]`) — including a 42-frame byte-capped WebP whose merged durations still summed correctly. The bug only ever bit a WebP/AVIF *source*, which this job was the first to use.

---

## 18. Closing the autonomy backlog: four recommendations that were wrong, and why

**Worked 2026-08-17**, driven by Harkirat's standing goal that the skill run fully autonomously — `--analyze`/`--recommend` producing correct flags with no human tuning. Each item below was a case where a manual override was still required. A manual flag tweak is the *investigation*, never the fix; the fix is whatever makes the tool reach the same answer itself.

### 18.1 `--pixel-art` on antialiased vector art — a second discriminator, not a moved threshold
`edge_hardness.ratio` counts pixels in a narrow band just outside the background tolerance. A clean vector export built mostly from straight edges needs only a thin antialiasing band, so it scores low and reads as pixel art: **love 0.425 and heart 0.316 against a 0.5 threshold**, and `--pixel-art` disables feathering and erosion, which is destructive on curved antialiased art.

Moving the threshold was not safe — measured per frame, love ranges **0.290–7.863** and heart **0.239–9.008**, and the *median* is below 0.5 for both (0.481, 0.388), so a majority of frames look hard-edged on this metric. `analyze()` also measured frame 0 alone, making the answer depend on which frame you happened to sample.

The fix asks a different question: **are there real background-to-art blends at all?** Genuine pixel art has none by construction — every pixel is a palette colour, never a mixture.

| asset | band ratio (frame 0) | band ratio (max) | blend ratio |
|---|---|---|---|
| synthetic pixel art | 0.000 | 0.000 | **0.000** |
| love | 0.425 | 7.863 | **2.415** |
| heart | 0.316 | 9.008 | **2.529** |
| gift | 1.382 | 3.295 | 1.713 |
| explosion | 6.508 | 10.347 | 1.653 |
| crystal | 8.228 | 10.920 | 1.530 |

`appears_hard_edged` now requires BOTH the band ratio (max across frames) under 0.5 AND the blend ratio under 0.15. The fixture still gets `--pixel-art`; love and heart no longer do. This is a margin of KIND (blends exist / do not), not of degree.

### 18.2 `--erosion-exempt-max-size` — classifying regions correctly is not sufficient
The persistence classifier was already right: on love it correctly identified the four controller buttons as DESIGN (497 of 1070 regions, present in ~every frame at a stable 286–306px). The suggestion was still wrong, because **the flag is a size threshold** — it exempts every region at or below it. Computed from the transient regions, it came out at **487px, above the buttons' own size**, so it would have exempted the design anyway and reintroduced the v3.3.3 fringe.

The rule now: if the suggested threshold reaches the smallest PERSISTENT region, the transient and design size ranges overlap and **no threshold separates them** — so recommend nothing and say why, rather than picking a value from one side of an overlap. love is suppressed; heart and gift (no persistent regions at all) still get it.

**The general lesson: a correct classification does not imply a usable parameter.** Check that the knob you are about to set can actually express the distinction you just made.

### 18.3 `--feather-band-multiplier` — the clamp was manufacturing the bug
The flag narrows the feather band so a near-background SOLID art colour falls outside it. But the same band is what gives the antialiasing ramp its partial alpha, so past a point the ramp stops being removed and survives as a visible fringe. The old value was `max(1.5, dist/tolerance - 0.5)`, and that clamp silently crossed the line:

| asset | tint distance | multiplier | fringe fraction |
|---|---|---|---|
| explosion, gift | 57–58 | 3.3 (band 15–49.5) | clean — the case the flag was built for |
| **heart** | **27** | **1.3, clamped up to 1.5** (band 15–22.5) | **0.2186 — fringed** |

heart also measured 0.1831 at 2.5, against **0.0000 at the default 4.0**. So the recommendation was itself producing the fringe that backlog item 3.3 suspected.

`--protect-band-only` — already recommended alongside it — solves the same problem without the cost: measured on heart it keeps **117,027 of the 119,810** near-background solid pixels the multiplier keeps (97.7%) with **no fringe**. The multiplier is now only recommended when the computed value is ≥3.0; below that the evidence says so and points at `--protect-band-only`.

**The clamp was the tell.** A clamp that fires is a value the formula could not produce honestly — it satisfied the formula while failing the thing the formula was for.

### 18.4 gift's white strip — the union footprint, not the colour detection
`--analyze` reported the strip as design (`enclosure_ratio` 1.0) but returned `candidate_outline_color: None`, so nothing protected it and `--verify` came back with **`protected_region_coverage` 0.0** — the region was deleted outright. The working flag (`--protect-outline-color 052a75`) had been found by eye.

The colour detection was fine. The FOOTPRINT was wrong: `comp_footprint` is a union across sampled frames, and the union had merged the strip with a neighbouring transient pocket, inflating it from **21,184px to 25,219px**. Nothing encloses the inflated shape, so verification correctly failed — on a region that isn't real. Measured directly: `052a75`/ `002864` encloses the strip's own footprint in **40 of 40** sampled frames.

The fix re-verifies against what is ACTUALLY enclosed in each frame (footprint ∩ that frame's own enclosed-background mask) and accepts a colour only if it verifies in ≥90% of them. This keeps the conservatism the original note argued for — still a verified containment check, just run on inputs that correspond to something real. gift now auto-recommends `--protect-outline-color 002864`; coverage went **0.0 → 0.874** and fringe **0.0388 → 0.007**.

**The union limitation was documented in the code for months as "no cheap, universally reliable way to distinguish these two cases from the union shape alone."** That was true and remains true — the escape was not to distinguish them from the union shape, but to stop relying on the union for this particular question.

### 18.5 `looks_fringed` — replaced, and deliberately made tri-state
The old check asked whether an edge-ring pixel was within `tolerance` of the background colour. A pale fringe pixel is a BLEND, tens of units from pure background, so it passed: the check returned False at erosion 0, 1 AND 2 on the same asset, including a level with a fringe visible by eye, and that false negative was trusted and shipped a regression (§16).

The replacement asks a RELATIVE question — is the pixel closer to the background than to any real art colour? — over the outermost opaque ring only. Measured:

| asset | erosion 0 | erosion 1 | erosion 2 |
|---|---|---|---|
| love | 0.2647 | 0.0765 | 0.0755 |
| heart | 0.0665 | 0.0000 | 0.0000 |
| gift | 0.4000 | 0.0372 | 0.0362 |
| crystal | 0.1681 | 0.0830 | 0.0823 |

It separates cleanly WITHIN each asset — every erosion-0 value is 2–4× its own clean baseline — but the ranges **OVERLAP across assets**: heart's fringed 0.0665 sits below crystal's clean 0.0830, because art with a baked-in fade legitimately carries pale near-background pixels at its boundary. Tightening the ratio does not rescue it: tested at 0.6, 0.4 and 0.25 of the art distance, and **0.4 and below collapse every asset to 0.0000** — a test that cannot fail, which §16 already names as the worst possible outcome.

So the check reports **True above 0.15, False below 0.04, and None in between with the reason** — because inventing a single global threshold here is precisely how the previous version earned its false negative. An unverifiable answer must present as unverified, never as a pass.

### 18.6 One backlog item was not real
"GIF `--target-kb` discards `--square-pad`" did not reproduce: measured at 128×128 with and without `--crop`, the padding survives the whole tier cascade. The original 128×110 observation was a render script that never passed `--square-pad` to the GIF variant in the first place. **A backlog item is a hypothesis until it is reproduced** — this one cost two commands to falsify and would have cost a speculative fix to "solve."

---

## 19. `--auto`: verifying the OUTPUT, and calibrating each asset against itself

**Built 2026-08-17, from Harkirat's question** after §18.5 concluded the fringe metric could not be made a reliable boolean:

> "why don't we make the script do a double verification/analysis? on the original, as it currently does, and then again on the output, to decide if it's original recommendation was correct or if something needs to be changed... like an automatic post render verification analysis?"

That reframes the problem correctly. §18.5 had established the metric **separates cleanly within one asset** (every erosion-0 reading is 2–4× that asset's own clean baseline) and **overlaps across assets** (heart's fringed 0.0665 below crystal's clean 0.0830). I had treated that as a dead end and shipped an "inconclusive" verdict. But it is only a dead end for a *global constant* — the within-asset signal was never the problem, and comparing an asset against **itself** is exactly the calibration a constant cannot express.

### The calibration
`calibrate_edge_cleanup_erosion()` measures the asset at each candidate erosion and reads the answer off its own curve, picking the **smallest** erosion already within 0.02 of that asset's own floor — smallest because erosion also eats thin strokes, so the goal is the least erosion that has already removed the fringe. Measured:

| asset | erosion 0 | 1 | 2 | 3 | picked |
|---|---|---|---|---|---|
| love | 0.3688 | 0.0853 | 0.0850 | 0.0847 | **1** |
| heart | 0.0720 | 0.0002 | 0.0002 | 0.0002 | **1** |
| gift | 0.4343 | 0.0078 | 0.0073 | 0.0068 | **1** |
| explosion | 0.2171 | 0.0000 | 0.0000 | 0.0000 | **1** |
| crystal | 0.1928 | 0.0068 | 0.0057 | 0.0047 | **1** |
| love (WebP, 8-bit alpha) | 0.0003 | 0.0003 | 0.0003 | 0.0003 | **0** |

**heart is the proof.** Its fringed reading of 0.072 is what defeated the global threshold — it sits below crystal's *clean* 0.0830. Against its own floor of 0.0002 it is 360× the baseline and utterly unambiguous. Same number, same metric; only the reference changed.

The last row matters just as much: the identical rule returns **0** for an 8-bit-alpha output, because the ring metric only looks at near-opaque pixels (`opaque_min=250`). On WebP/AVIF the edge is a real alpha ramp that is *supposed* to be pale and semi-transparent, so there is nothing to erode — and the calibration discovers that rather than being told. Both of last session's hand-derived defaults (1 for the GIF path, 0 for WebP/AVIF) now fall out of measurement.

**One rule covers both failure directions.** Too little erosion reads far above the floor; too much shows no further improvement and loses the tie to the smaller candidate. There is no separate "is it over-eroded?" check to get wrong.

### Why BOTH a pre-encode calibration and a post-render check
The calibration runs on in-memory alpha, so it costs one extra erosion pass per candidate rather than one extra render — and it corrects before encoding, so nothing is wasted. But it cannot see the encoder: GIF palette quantization can snap an edge pixel onto a different palette entry (§16 measured that same quantization destroying 90% of an outline's antialiasing), and lossy WebP/AVIF shifts edge colours. So `--auto` re-measures the **written file** and, if it exceeds the asset's own pre-encode floor by more than 0.05, escalates erosion once and re-renders.

Across all five assets the encoder agreed (largest gap 0.0021), so the correction never fired on real content — which is a good result and also means the branch was **untested**. Per §16's own lesson that a test which cannot fail proves nothing, it was verified by stubbing the post-render reading high: the branch fires, re-renders, and re-measures to 0.0.

### Design points worth keeping
- **Explicit flags always win.** A recommended flag is applied only where the user left that option at its default, computed by diffing three namespaces (defaults / recommended / actual). `--auto` fills gaps; it never overrides a deliberate choice, and it prints what it skipped.
- **`--auto` is opt-in, and the default codepath is byte-identical** — re-verified against the retained `love_transparent.gif` baseline after every edit in this round.
- **The general lesson: when a measurement has no absolute threshold, look for a relative one before declaring it unusable.** "Compare it against itself" was available the whole time, and I had written the manual version of it into the inconclusive verdict's own advice text ("compare this asset against its own erosion 0/1/2 outputs") without noticing that a machine could simply do it.

---

## 20. Auditing §19: five defects found by reviewing my own work

**2026-08-17**, after Harkirat asked how many times `--auto` would loop and then asked for a full audit. The loop question alone surfaced a wording error; the audit surfaced four more defects, three of which the tests as written would never have caught.

### 20.1 I called straight-line code "a loop"
`auto_run` has no `while`, no recursion, and no counter — it calls `process()`, measures, and calls it at most once more. I described it as "the closed loop" in the summary, the docstring and the handoff, **in the exact context where the distinction mattered**: a question about runaway risk. Harkirat caught it. A future reader would have gone looking for an iteration cap that does not exist, or added one.

Bounded-by-shape is stronger than bounded-by-counter — there is no state that can fail to increment. And two passes is principled rather than cautious: pass 1's calibration is EXHAUSTIVE over its candidate set (it measures every candidate rather than stepping toward an answer, so iterating adds nothing), pass 2 exists for the single discrete effect pass 1 structurally cannot see (the encoder), and no third class of error remains. That reasoning is now in the docstring, along with what a future looping version would have to carry.

### 20.2 The correction could ship a WORSE file than the one it replaced
The corrective re-render overwrote the output in place, then printed a warning if the result was not an improvement — leaving the inferior file on disk with the better one already destroyed. Now the first render is preserved, the correction is compared against it, and the loser is discarded. The message states which render is actually on disk. Same principle as §13/§17: report what IS, not what was attempted.

### 20.3 The escalation was computed from a value that was never written back
`process()` starts with `args = copy.copy(args)`, so every setting it resolves internally — including the calibrated erosion — is invisible to the caller. `auto_run` computed `newe = (args.edge_cleanup_erosion or 0) + 1` from the CALLER's copy, where the value was still `None`. So the "escalation" re-rendered at erosion 1 when pass 1 had already used 1: **not an escalation at all**, while reporting one.

Found by reading the test output rather than the assertion — the revert test passed, and the message beneath it said "the FIRST render (--edge-cleanup-erosion 0)" when pass 1 had used 1. The assertion checked that the branch fired, not that it did the right thing. The resolved value now travels back through the diagnostics sink.

**A passing test plus an implausible number in its output is a failing test.**

### 20.4 "Explicit flags always win" was false, twice over
I put that guarantee in the help text and the docstring. Two separate holes:
1. `--auto` decided "the user expressed no opinion" by comparing against the default, so a user who explicitly typed the default value was indistinguishable from one who typed nothing, and got overridden. argparse keeps no provenance; `typed_option_names()` now reads argv.
2. Worse, and caught only by testing it: an explicitly typed `--edge-cleanup-erosion 2` was still recalibrated down to 1, because the calibration is gated on `auto_erosion` and `auto_run` set that flag unconditionally — re-enabling what `main()` had just turned off.

The second one is the instructive half: I "fixed" the guarantee in the flag-application code and declared it done, while the actual override lived somewhere else entirely. **Fixing the mechanism you were thinking about is not the same as fixing the behaviour.** Only running the command proved it.

### 20.5 `--auto` knew the format was wrong and said nothing
`recommend()` returns `webp-or-avif` for four of five corpus assets, with evidence that GIF structurally cannot carry a baked-in fade. `--auto` printed that and then rendered a GIF anyway if that is what the output path said. The single most consequential decision — the container — was the one `--auto` did not act on. It now prints a prominent FORMAT CONFLICT warning. It still does not override the user's chosen filename, which is right: the user named the file. But proceeding silently when the analysis says the result will be wrong is not.

Related, same audit: pass 2 only measured fringe. For a GIF output the full `verify()` is available and free, and it covers the duration/frame-count class that §17 was — so `--auto` now runs it and reports leftover background, protected coverage and timing, rather than letting a clean fringe reading imply a clean file. For 8-bit-alpha outputs it says explicitly that only the alpha-aware check ran and this is NOT a full verification.

### 20.6 Limits of this session's calibration, stated plainly
Every threshold set in §18–§19 was calibrated on **five assets from one art family** (flat vector icons on white, from one emoji set) plus a synthetic pixel-art fixture **I wrote myself**. That fixture confirms the discriminator does not fire on art with literally zero antialiasing, but it is not independent evidence about real-world pixel art, which often carries some AA or a palette dither. The blend-ratio margin (0.000 vs 1.530) is wide enough to survive that; the narrower constants (feather ≥3.0, fringe bands 0.04/0.15, floor tolerance 0.02, post-render 0.05) rest on 4–5 points from one style, and no dark-background asset was tested at all.

Also worth recording honestly: **every GIF asset calibrated to erosion 1.** That is the correct answer being stable, not degeneracy — the WebP path returns 0 from the same code, which proves the rule is not stuck. But it means the calibration mostly re-derives a constant for this corpus, and its 2/3 branches have never been exercised on real content. Its genuine value is that it DERIVES rather than assumes, and adapts across alpha depths — not that it finds a different answer per asset.

---

## 21. Four verification defects, and exempting by identity instead of by size

**2026-08-17.** Harkirat asked to fold the tractable backlog items into this session and leave the research ones for a fresh one. Items 9, 10, 11 and 12. Three of the four turned out to be the SAME underlying mistake, which is why they are written up together.

### 21.1 The shared root cause: a bounding RECTANGLE is not a region
`protected_region_coverage` measured opacity across every background-coloured pixel inside a region's bounding box. A bbox around an irregular shape also contains real background, which is correctly transparent — so the check counted correct transparency as missing protection.

Measured on gift, frame 0: **12,371** background-coloured pixels inside the bbox against **10,257** actually enclosed. Coverage read **0.874** for a region that is in fact **100%** protected. Restricting to the enclosed footprint reads **1.000**.

This is item 12, and it retroactively settles item 4: gift's white strip was never partly unprotected. I had reported "0.0 → 0.874" as a fix and let the summary say CLOSED while quietly not knowing what the remaining 12.6% was. It was never real.

**It also appears to fix a separately-tracked P3 item** — `protected_region_coverage` false-positiving on a legitimately punched sub-hole inside a translating candidate region. Same mechanism: a punched hole inside a bbox is background-coloured, correctly transparent, and was being counted against the region. Corroborating evidence: crystal's coverage went **0.569 → 1.000** with no change to the render. ⚠️ Not confirmed against that item's own asset (`military-tag.gif` is not on this machine), so it is recorded as probably-fixed, not fixed.

### 21.2 Leftover background counted the very thing it was told to protect
`leftover_background_opaque_px` excluded pixels *enclosed in that frame*, which is not the same as pixels the pipeline protected: a protected region can open to the outside in some frames while still being correctly kept opaque. gift reported **14,243** background-coloured opaque pixels on its worst frame — all of them the white strip the outline protects, i.e. the intended output.

Reconstructing the same fill the pipeline applies (`--protect-outline-color`'s mask, hole-filled) and excluding it takes that to **0**. Measured alternatives, worst frame:

| exclusion | leftover |
|---|---|
| none | 14,243 |
| enclosed-in-scope (what it did) | 3,878 |
| whole protected bbox scope | 3,878 |
| **enclosed + the outline's own filled area** | **0** |

### 21.3 `--verify` now accepts WebP/AVIF
The refusal was correct when written — its checks assumed 1-bit alpha — but the reason had already been dismantled: §17 made durations readable, §19 made the fringe metric alpha-aware. The last piece was leftover background, which now requires **alpha ≥ 250**: on an 8-bit output a background-coloured pixel that is *partly transparent* is a recovered fade or an antialiasing ramp, i.e. correct output, not leftover. The report carries a `scope_note` stating this rather than silently changing meaning between formats.

Verified on a real WebP (`love_nocontroller_fullres.webp`): runs, reports `output_format: webp`, fringe 0.0003 clean, leftover 327 px.

### 21.4 Exempting by IDENTITY dissolves what the size guard only sidestepped
§18.2 stopped `--erosion-exempt-max-size` being recommended when the transient and design size ranges overlap. That was correct but partial: it picks the safer side of the conflict, so love gets no exemption at all and the v3.1.0 small-region inflation bug stays live for it.

The overlap is only a problem because the flag keys on SIZE. The classifier already distinguishes them correctly — present in ~every frame at a stable size = design — and the erosion machinery already takes MASKS (`erode_alpha_edge_exempting_tiny_regions`), not a threshold. So `find_transient_removed_regions()` applies the same persistence clustering at process time and builds the exemption mask from the incidental regions only. New flag `--erosion-exempt-transient`, now auto-recommended exactly where the size threshold is refused. love's design at 262–306px and its noise at up to 442px may overlap freely; identity does not care.

**The lesson worth keeping: when two things cannot be separated by the parameter you have, check whether a different parameter separates them trivially before settling for the safer side.** The machinery for the better answer had been in the file the whole time.

### 21.5 Result across the corpus
Every asset rendered straight from its own `--recommend` output, then verified:

| asset | leftover bg | fringe | verdict | worst coverage |
|---|---|---|---|---|
| love | 0 | 0.0901 | inconclusive | 1.000 |
| heart | 0 | 0.0000 | clean | — |
| gift | 0 | 0.0070 | clean | 1.000 |
| explosion | 0 | 0.0001 | clean | — |
| crystal | 0 | 0.0068 | clean | 1.000 |

Against the previous round: gift leftover 14,243 → 0 and coverage 0.874 → 1.000; crystal coverage 0.569 → 1.000. No render changed — every one of these was a measurement defect, which is its own warning about how much weight a self-check can carry before it has been checked itself.

---

## 22. Closing §14 on its own asset: the residual was the cutout, and 519 vs 371 measured

**2026-08-17.** Two items were carried in the development repo's backlog on the premise that `military-tag.gif` was "not on this machine". It is — a directory search in the development repo's own asset folders found it in seconds. **A blocker recorded as "asset unavailable (checked)" is worth re-checking before it is inherited by another session**; this one had already survived one handoff and would have survived another.

### 22.1 The `protected_region_coverage` false positive is fixed, and reproducing it proved it

The delivered `military-tag_transparent_fixed.gif` is CROPPED (536x570 vs the 640x640 source), so `--verify` skips every pixel check on it and reports only timing — a **vacuous pass**, and exactly the kind §13/§16/§17 warn about. Re-rendering §14's pipeline uncropped is what makes the check mean anything:

```
--tumble-safe --keep-bg-blob-if-near ff00ff --hole-size-range 400,480 --hole-max-aspect 1.3
```

| script | `mean_opacity_fraction` | `looks_unprotected` |
|---|---|---|
| `fc7443b` (before §21.1's footprint fix) | **0.462** | `true` |
| `2674693` (after) | **0.757** | `false` |

0.462 reproduces §14's recorded 46.2% exactly, so this is a real reproduction rather than a coincidence of two clean runs.

### 22.2 The residual is 100% the punched pinhole — and §14's stated root cause was half wrong

Measuring what the non-opaque remainder actually consists of, per frame:

```
frame 0:  footprint 4410  non-opaque 441   -> ONE blob, 441px
frame 60: footprint 3280  non-opaque 457   -> ONE blob, 457px
total     footprint 435,143   non-opaque 57,229
```

One blob per frame, in all 126 frames, 441–457px — inside the 423–466px range §14 measured for the pinhole via a completely different code path. The remainder is the deliberately punched hole and nothing else.

**§14 attributed the false positive to the region's bbox being tied to one reference frame while the tag translates and swings.** The bbox is still fixed and the tag still translates, yet no stray outer-background pockets appear in the footprint at all. So the bounding-RECTANGLE-vs-enclosed- FOOTPRINT mistake was doing all the damage, and the translation half of the diagnosis contributes nothing measurable here. Two plausible mechanisms were named; only one was real, and nothing distinguished them until the residual was actually decomposed.

### 22.3 `residual_nonopaque`: measuring whether a remainder has the SHAPE of a cutout

`verify()` receives an input path and an output path — not the render's flags — so it can never *know* a cutout was intended. §14 concluded this made the case unexpressible. It can, however, measure whether the remainder looks like one, which is enough to stop a correct 0.757 from reading as an unexplained defect. Falsified against a deliberately unprotected render of the same asset:

| | blobs/frame | size CV | fraction of footprint | verdict |
|---|---|---|---|---|
| punched cutout | 1.00 | 0.025 | 0.243 | `true` |
| no protection at all | 2.13 | 0.586 | 1.000 | `false` |

**The footprint-fraction ceiling (0.35) is the load-bearing guard.** Without it, "persistent and stable across every frame" would equally describe a region that is reliably, WHOLLY unprotected — the check would excuse the exact failure it exists to catch. Persistence alone is not a discriminator here; persistence *at a small, stable fraction* is.

The field is additive: diffing the full pre-change and post-change `--verify` reports on the same pair, with the new key removed, comes back identical, so no previously recorded number moved.

### 22.4 The §14 addendum's manual fix is now derived, and the fringe is counted in pixels

§14's addendum records `--erosion-exempt-max-size 519` as the cause of a pale fringe at the punched hole, fixed by hand by dropping the flag. Running `--recommend` on the same asset with both versions:

| version | suggests |
|---|---|
| `v4.0.0` (shipped) | `--erosion-exempt-max-size 519` |
| this branch | `--erosion-exempt-max-size 371` |

The persistent/transient split (§18) classifies the pinhole as DESIGN (`min_persistent_region_px 428`) and sizes the suggestion from the transient regions alone (`max_transient_region_px 337`). Counting the pale, technically-opaque pixels adjacent to interior holes across all 126 frames:

| render | pale px at hole edges | interior-hole px |
|---|---|---|
| `--erosion-exempt-max-size 519` | **807** (worst frame 14) | 57,199 |
| `--erosion-exempt-max-size 371` | **0** | 83,644 |
| no exemption flag at all | **0** | 83,644 |

371 is outcome-identical to dropping the flag — the manual fix, reached by the tool. The hole areas corroborate independently: 57,199/126 = 454px/frame un-eroded and 83,644/126 = 664px/frame eroded, both inside the addendum's separately measured 423–466 and 632–682 bands.

**Takeaway: a defect closed by "drop the flag" is not closed until the tool stops suggesting the flag.** The addendum ended with the right output and a recommender that would reproduce the defect on the next asset of the same shape — which is what `CLAUDE.md`'s end-goal section means by a manual tweak being the investigation rather than the fix.

---

## 23. `edge_hardness` fails on pixel art with a coloured background — 6 of 8 real assets

**2026-08-17.** §18 added a second edge-hardness discriminator and validated it against a synthetic pixel-art fixture **I generated myself**. Harkirat then supplied a folder of 9 real assets, 8 of them genuine pixel art, all on COLOURED backgrounds rather than white. (That corpus lives in the development repo and is NOT part of this package — the numbers below are provenance for the rule, not something you can re-run here.) The fixture had been agreeing with me; the real assets do not.

### 23.1 Ground truth vs. what the tool says

| asset | truth | `ratio_max` | `blend` | verdict | |
|---|---|---|---|---|---|
| 07761f30 (frog) | pixel | 20.895 | 0.000 | antialiased | ❌ |
| 2d4a092f (jar bunny) | **antialiased** | 0.649 | 0.999 | antialiased | ✅ |
| 5bf1a3da (cat) | pixel | 1.776 | 0.000 | antialiased | ❌ |
| 6CFF9959 | pixel | 2.046 | 0.199 | antialiased | ❌ |
| 7cddd430 (cat+balloon) | pixel | 0.000 | 0.638 | pixel art | ✅ *(fixed here)* |
| 8acad64c (nyan) | pixel | 17.428 | 0.006 | antialiased | ❌ |
| 9a4177e8 | pixel | 0.000 | 0.000 | pixel art | ✅ |
| DFB2A5D7 (frog) | pixel | 0.245 | 1.074 | antialiased | ❌ |
| panda | pixel | 1.041 | 0.872 | antialiased | ❌ |

**Three of nine correct** (two before the fix below). The consequence scales with sprite size: `--pixel-art` exists because feathering, 2px erosion and LANCZOS resizing destroy hard-edged art (§4 measured 0% survival on a 31px shape). On these large upscaled sprites it softens the blocky edges that ARE the art style rather than annihilating them — wrong, but not catastrophic.

### 23.2 Both measures break, in opposite directions, for the same underlying reason

**A solid palette colour is indistinguishable from a blend when the background is chromatic.**

- **`ratio` (transition band)** counts pixels just outside the background tolerance. With a light- green background (`#bbfeba`) and green art, solid art fill lands in that band: the frog scores **20.895**, higher than any genuinely antialiased asset in the corpus. On white backgrounds with dark art this never happens, which is why 640x640 navy-on-white art hid it.
- **`blend`** counts near-boundary pixels lying on a background→art colour line. On the sprite with a `#9cd6f7` sky, solid whites at `(255,255,255)`, `(252,252,253)` and `(228,246,255)` sit **4.69, 2.35 and 2.92** from that line — inside the 14 it allows — so 63.8% "blends", all of them palette collisions.

The two measures' pixel-art ranges (0.000–20.895 and 0.000–1.074) **overlap the antialiased corpus almost entirely** on the band ratio, so it has no discriminating power here at all.

### 23.3 What shipped: zero transition band is dispositive

`_hard` was `(_eh_max < 0.5) and (_blend_ratio < 0.15)` — an AND, so the blend measure could VETO a correct verdict. On `7cddd430` it did: `transition_band_px 0`, `ratio 0.000`, and a 0.638 blend ratio made of pure collisions overrode it.

Zero transition pixels across every sampled frame is now dispositive. Antialiasing IS intermediate pixels; none of them means none of it, and a blend ratio computed on top of that is measuring palette collisions. This cannot reopen §18's false positives — love and heart scored 7.863 and 9.008, not 0. Verified: the corpus five all stay `False`, two pixel-art assets flip to `True`.

**It is a partial fix and is documented as one.** It rescues only the subset scoring exactly zero.

### 23.4 The fix that shipped: change-line density

Harkirat expanded `others/` to **31 assets**, labelled by eye into 25 pixel art and 6 antialiased (`others/LABELS.json`, method recorded in `others/README.md`). Adding the six-asset vector corpus as further negatives gives **37 labelled assets** — the first time any threshold in this skill has had a validation set at all.

Two structural ideas were tried and scored before one was believed:

1. **Modal colour-run length** — dead. The vector corpus scores k = **19–20**, not the 2–3 the `others/` antialiased assets score, because modal run length is dominated by flat-fill area and resolution, not block structure. A `k >= 4` rule would have flagged all six vector icons as pixel art: §18's exact catastrophe, reintroduced.
2. **Integer-lattice fit** (change positions congruent mod k, phase solved for) — sound but narrow. Zero false positives, but only 11 of 25, because a 500x500 export of a 32px sprite is a 15.625x upscale that lands on no integer grid.

**What worked is scale-free: how OFTEN does the image change as you sweep across it?** Pixel art is drawn on a coarse grid and enlarged by any factor, so a sweep finds a change only at block boundaries. Antialiased art changes at nearly every line, because an edge ramp differs from its neighbour by construction. It never reads a colour value, so neither palette collision reaches it.

| rule | correct | pixel art found | false positives |
|---|---|---|---|
| v4.0.0 (band AND blend) | 17/37 | 5/25 | 0/12 |
| §23.3 (+ zero-band short-circuit) | 19/37 | 7/25 | 0/12 |
| **+ change-line density < 0.5** | **30/37** | **18/25** | **0/12** |

Antialiased assets measure **0.835–1.000**; the 18 pixel-art assets it catches measure **0.037–0.245**. The 0.5 threshold sits mid-gap rather than tuned to either edge — a margin of KIND, which is what §18 wanted and did not get. A LOW value is dispositive; a HIGH value proves nothing, so density can only ever ADD a hard-edged verdict, never veto one.

### 23.5 The 7 that remain, and why they are one class

Every miss is **dithered or photographic pixel art** — mosaics of photographs, and sprites shaded with dither — where the dithering puts a change on essentially every line and saturates the measure: `_ (9)` 0.592, `DFB2A5D7` 0.732, `_ (10)` 0.840, `The Last Jedi` 0.878, `_ (11)` 0.917, `Pixel Saber` 1.000, `pandapanda...` 1.000.

A promising next step is to measure density on a dither-suppressed copy (a small median filter, or counting only changes that persist across several adjacent lines), then re-score against the same
37. ⚠️ **Do not reach for a bare blend-ratio threshold.** It looks tempting — but the band ratio on
this corpus reaches **247.147** on one pixel-art asset, and blend puts genuinely antialiased art at 0.731 against pixel art at 3.037. Both overlap completely. Only the geometric measure separated.

### 23.6 The lesson, which is the same one §18 should have learned
**A fixture you generated yourself cannot validate a discriminator.** §18's claim — "genuine pixel art has no background-to-art blends by construction" — reads as a statement about pixel art and was actually a statement about the file I happened to build: its palette contained no colour lying on a background→art line. Every real asset with a coloured background does. The synthetic fixture agreed with the theory because both came from the same set of assumptions.

---

### 23.7 Scoring the two measures on coloured vs white backgrounds — the collapse belongs to the band ratio, not the line measure

**2026-08-18.** §23 asserted that a coloured background breaks edge-hardness detection, on 8 assets. The labelled corpus is now 31 (25 pixel art, 6 antialiased), 20 of them on genuinely non-white opaque backgrounds, so the claim is testable as a rate rather than an anecdote. Detection rates for pixel art, false positives on antialiased in brackets:

| rule | white bg (6 px / 5 aa) | coloured bg (19 px / 1 aa) |
|---|---|---|
| band ratio (`ratio_max < 0.5 AND blend < 0.15`) | 1/6 [0] | 4/19 [0] |
| `change_line_density < 0.5` | 4/6 [0] | 14/19 [0] |
| shipped `appears_hard_edged` (either of the above, plus the zero-band rule) | 4/6 [0] | 14/19 [0] |

**The refinement §23 could not see with 8 assets:** the band ratio is weak *everywhere* (5/25 overall), not specifically on coloured backgrounds — its 1/6 on white is no better than its 4/19 on colour. The measure that actually carries detection, `change_line_density`, shows **no coloured-background penalty at all** (67% white vs 74% coloured), exactly as its docstring predicts: counting where an image changes never reads a colour value, so a palette collision cannot reach it. So the standing rule stays "check the art by eye on a coloured background", but the reason is that detection is mediocre overall, not that colour specifically defeats it.

### 23.8 A better measure that scored 24/25 — and had to be thrown away

§23.5 left 7 pixel-art assets undetected, all dithered or photographic, and proposed suppressing the dither before counting changed lines. The cheapest version of that idea: instead of asking whether a scan line differs from its neighbour *at all* (which one dithered pixel satisfies), ask what FRACTION of it differs, and count lines that are **essentially duplicates** of their neighbour — `fraction_changed <= 0.01`. Pixel art upscaled by k has roughly (k-1)/k duplicate lines by construction; dither perturbs a few pixels per line and leaves that structure standing.

Against the 31 labelled assets it looked decisive: **24/25 pixel art detected against the shipped 18/25, zero false positives**, with the antialiased half topping out at 0.050 and 24 of 25 pixel-art assets at 0.150 or above.

**It is wrong, and the labelled corpus could not show it.** Scored against **145 vector emoji** from this repo's own asset folders — the content type this skill primarily exists for, presumed antialiased from their provenance rather than labelled by eye — the same rule fires on **37 of them (25.5%)**, up to 0.735, and the top scorers are flat interface icons (`add.png` 0.735, `delete.gif` 0.592, `no-data.gif` 0.572). Even if a handful of the 145 turn out to be pixel art, a 25% hit rate on that population is disqualifying. The reason is obvious in hindsight and invisible in the corpus: a flat-fill vector icon has large areas where the next column is genuinely identical, so it accumulates duplicate lines for a reason that has nothing to do with a pixel grid. The labelled corpus holds only 6 antialiased assets; 6 is not enough to see a 25% failure rate.

**The lesson is §23.6's and the release-gate checklist rule in one.** A validation set that is 25 pixel art and 6 antialiased cannot certify a measure whose failure mode is *antialiased art misread as pixel art* — the population that would falsify it is the one barely represented. **Before believing a discriminator, ask which population its failure would live in, and check whether that population is actually in the sample.**

### 23.9 A second idea, falsified the same way — and what that pattern now says

The natural repair for §23.8 is to stop counting duplicate lines and start asking whether the change lines are REGULARLY SPACED, since a pixel grid has a pitch and a flat fill does not. Measured as the share of gaps between strong change lines (≥ half that frame's own maximum change fraction, so dither noise does not qualify) falling on the two commonest gap values. Fractional upscales are handled by design: 15.625x gives gaps of 15 and 16, still two values.

On the labelled corpus it reads **25/25 pixel art at a 0.55 threshold**. On the 145 vector emoji it fires on **119 of the 123 it can measure — 96.7%** — and, decisively, the six antialiased assets in the labelled corpus score 0.848–0.984 against pixel art's 0.573–1.000. The measure is not weak, it is **inverted**: flat vector art has *more* regular strong-change spacing than dithered pixel art does, because its long uniform runs produce a handful of clean repeated gaps while dither fragments the pixel grid's own pitch.

**Four structural ideas have now been tried and scored against real assets: modal run length (§23.4), integer-lattice fit (§23.4), duplicate-line density (§23.8) and gap regularity (here).** All four are variations on *where does the image change along a scan line*, and all four fail on the same rock: a flat-fill vector icon is locally as uniform as a pixel grid. That family is exhausted. Anything further should measure something categorically different — the palette's own structure, or the shape of the alpha ramp, not the geometry of change positions — and must be scored against BOTH populations before it is believed. The labelled corpus alone said yes to two measures in a row that the emoji set then destroyed.

## 24. Two defects that only exist in the deployment environment

**2026-08-17**, found by a sequential-thinking double-check run AFTER v5.0.0 was already merged, tagged and pushed. Both break the skill in the claude.ai sandbox — the environment it actually ships to — and neither was reachable by any test run in this repo.

### 24.1 `--recommend` emitted a path that only works from the repo root
`suggested_command` was built as `f"python3 scripts/remove_gif_background.py {input} <output.gif>"`. That path is repo-relative. In a claude.ai sandbox the skill unpacks somewhere that is not a repo root, so an autonomous run pasting the suggested line verbatim gets `No such file or directory` — and `--recommend` exists precisely so a run can paste it verbatim.

Every test of `--recommend` this project has ever run was executed FROM the repo root, where the wrong path is right by coincidence. **That is a test that cannot fail**, the exact defect §23 recorded about the synthetic pixel-art fixture, in a different costume. Now derived from `os.path.abspath(__file__)`.

### 24.2 AVIF saved with no capability guard, while `--recommend` ranks it first
`ims[0].save(output_path, 'AVIF', ...)` ran bare. AVIF needs Pillow built with AVIF support or the `pillow-avif-plugin`; this Mac has Pillow 12.3.0 where `features.check('avif')` is True, so it has always worked here and the dependency was invisible.

The compounding part: v5.0.0's own `--recommend` ranks **AVIF first** under a byte cap. So an autonomous run in an environment without AVIF is steered directly at the missing dependency, and the failure arrives as a bare Pillow error *after* every frame has been processed. Now checked before any work, with a message that names the fix and points at WebP as the equivalent-quality fallback.

### 24.3 A finding I first reported backwards
I reported that `--pixel-art --edge-cleanup-erosion 2` runs silently at erosion 2, destroying hard edges. Wrong direction. `apply_pixel_art_preset` did `args.edge_cleanup_erosion = 0` unconditionally, so the explicitly typed 2 was silently DISCARDED.

The real defect was an inconsistency, not a destruction: `--auto` uses `typed_option_names()` so "explicit flags always win, and it prints what it skipped", while this preset silently overrode a typed flag. Two mechanisms in one script disagreeing about who wins, one of them saying nothing. Fixed to match `--auto`'s contract.

**Worth recording that the first report was wrong**, because a postmortem is what a future session trusts instead of re-deriving. Had it shipped, it would have sent someone hunting a destruction bug that does not exist.

### 24.4 The generalisable rule
**Test in the environment the thing ships to, not only the one you develop in.** Both §24.1 and §24.2 are invisible from the repo and obvious from the sandbox. The packaged skill is the product; this repo is the workshop.

A cheap proxy, since a claude.ai sandbox is not available from here: for anything the skill emits for someone else to RUN, ask what it resolves to when the current working directory is not this one — and for any dependency, check whether it is guaranteed or merely present on this machine.

## 25. `--tumble-safe` strands the background it does not own — 56% left behind

**2026-08-17, v5.3.0.** This is the section the shipped evidence string has always pointed at; it was written into the release notes and never into this file, so every run that emitted "see references/lessons.md §25" was pointing at nothing. Recorded here properly.

`--tumble-safe` exists for §10's tumbling icon: it defines the background as the single LARGEST connected background-coloured component in each frame, so an interior pocket that momentarily opens to the canvas edge is not swallowed. That definition assumes the background is essentially one piece.

**When the foreground spans the canvas, it is not.** On `GIFfromGIFER-ezgif.com-remove-background.gif` (35 frames, yellow `ffe75c` background) the artwork divides the background into 3-7 disconnected regions. `--tumble-safe` kept the biggest and silently left the rest: frame 0 removed 69,548 of 158,899 background pixels, **56% stranded**, and **2,329,956 pixels of background left behind across the animation**.

**`--recommend` chose that flag itself**, which is what made it worth a fix rather than a caveat. Tumble risk fires on an edge-grazing foreground, and an edge-grazing foreground is *also* what fragments the background — the trigger condition and the failure condition are the same condition.

**What shipped:** `tumble_risk` now reports `background_outside_largest_component`, and `--recommend` withholds `--tumble-safe` above 0.35 with the refusal spelled out in the evidence. The threshold is mid-gap, not tuned: the corpus spans 0.0-23.6% and the failing asset sits at 57.7%. `military-tag`, the asset the flag exists for, reads 1.5% and is unaffected.

**How it was found:** Harkirat looked at a README showcase I had called clean. I had written "preserved crisply, yellow fully gone" from a 248px thumbnail without measuring. **A glance at a thumbnail is not a measurement**, and the damage was 56% of the thing being checked.

## 26. A degenerate outline candidate won selection, so a design region got no protection at all

**2026-08-18.** On `Cut loop.gif` (76 frames, 800x600, an animated pokeball on `f7f7f9`) `--auto` writing a `.gif` destroyed the entire enclosed interior of the design — and its own verification said so, reporting `worst protected-region coverage: 0.0` while carrying on.

### 26.1 The candidate that "verified" by containing everything

`find_verified_outline_color` gathers colours from rings at several dilation radii around a region and keeps those whose `binary_fill_holes` shape contains 95% of the footprint, preferring the tightest fit. For region 2 it gathered four candidates:

| candidate | mask px | filled px | containment | overlap with real background |
|---|---|---|---|---|
| `dcdcdc` | 442,385 | **480,000** | 1.000 | **423,855** |
| `281450` (the true purple outline, quantized) | 14,507 | 16,001 | 0.248 | 0 |
| `f0c800` | — | 8,584 | 0.050 | 0 |
| `dc1428` | — | 8,005 | 0.044 | 0 |

480,000 is every pixel of an 800x600 frame. `dcdcdc` is a pale grey inside the background's own tolerance neighbourhood; its mask covers most of the canvas, so filling it fills everything, so it "contains" the footprint. It was the ONLY candidate to clear 95%, won the tightest-fit contest unopposed, and was then rejected one step later by `detect_outline_background_leak` — correctly, but too late. Selection had already discarded the alternatives, so the region fell through to `--protect-band-only 4`, which has nothing to hold: the pokeball's interior is an open bowl, topologically continuous with the background, so band-only protection cannot reach it.

**Measured on the GIF path: 976,800 pixels of artwork kept by `--protect-outline-color 39215a` and destroyed by the recommended flags.** (`39215a` and its quantized bucket `281450` differ by 4,749 px out of 2.92M — 0.16% — so the quantization is not the problem.)

### 26.2 What the WebP path shows, and why the bug is narrower than it looks

The same asset written to `.webp` with the recommended `--recover-fade-alpha` is **unaffected** — that path protects 1,005,156 enclosed interior pixels on its own, and adding the outline flag changes not one pixel of alpha. `--recommend` asks for WebP here, so the destruction only lands when the output is forced to `.gif`. Worth stating plainly, because the first framing of this bug ("`--auto` destroys the region") is true only for one of the two containers, and a fix credited with more than it does is a fix nobody can re-verify.

### 26.3 Two fixes, both hard properties rather than tuned margins

**Reject the degenerate candidate during selection.** A colour whose filled shape overlaps the frame's own largest background component is not enclosing anything. This is the *same* criterion `detect_outline_background_leak` already applies — just applied while the alternatives are still on the table. It can only ever turn "region abandoned" into "next candidate considered", so it carries no regression risk for an asset whose winner does not leak.

**Accept a PARTIAL enclosure when nothing encloses.** Even with `dcdcdc` gone, `281450` still fails the 95% test, for two compounding reasons: the footprint is a cross-frame UNION (30,191 px) far larger than any single frame's hole (13,603 px at widest), and the outline only closes on **15 of 76 frames** because the bowl is open for the rest. Neither makes the colour wrong — at process time the per-frame mask substitution propagates the closed frames' shape to the open ones, clamped to each frame's own silhouette. So `find_partial_enclosure_outline_color` ranks the leak-free candidates by how much of the region they enclose across sampled frames and recommends the best. The gate is binary and physical (never swallows background on any sampled frame), and the alternative in this state is not weaker protection but **none**, so anything leak-free is a strict improvement.

### 26.4 What it changed across the corpus

7 of 31 labelled assets got a different recommendation. Rendered both ways and measured:

| asset | opaque px delta | leftover background | protected coverage |
|---|---|---|---|
| `Cut loop` (GIF path, via `--auto`) | **+884,352** | unchanged | 0.0 → 0.843 |
| `pandapanda…` | **+383,575** | 0 → 0 | 0.0 → up to 1.0 |
| `2d4a092f…` (the jar bunny) | **+202,845** | 0 → 0 | 0.0 → 0.331 |
| `Starters!` | +22,883 | 0 → 1 px on 1 frame | 0.0 → 0.776 |
| `_ (9)`, `_ (11)`, `ezgif.com-remove-background` | 0 | unchanged | unchanged |

**No asset lost artwork and none gained meaningful leftover background.** The three zero-delta rows gained an extra outline colour in the recommendation that turned out to protect only what was already protected — cosmetic noise in the suggested command, not a behaviour change. `love.gif` still renders byte-identical to its known-good output.

### 26.5 The safety evidence had to be re-taken, because the obvious check cannot fail here

`verify()`'s `leftover_background_opaque_px` **excludes** the filled area of every verified outline colour — deliberately, since §21.2. So using it as the primary evidence that "adding an outline colour did not keep background" is close to circular: the metric stops counting exactly what the change adds. It happens not to bite here, because the partial path leaves `outline_color_verified` false and `candidate_outline_color` None, so `_protected_fill` never picks the new colour up — **but that is an accident of where the field was stored, not a safeguard**, and anyone tidying the two representations into one will silently turn this check vacuous.

The independent falsifier, which uses no analyze footprint and no outline exclusion: of the pixels that are opaque AFTER and transparent BEFORE, how many lie in that frame's own largest background component?

| asset | newly opaque | of which real outer background |
|---|---|---|
| `Cut loop` (`--auto`, GIF) | 884,352 | **709** (0.08%, across 76 frames) |
| `pandapanda…` | 383,575 | **0** |
| `2d4a092f…` | 202,845 | **0** |
| `Starters!` | 22,883 | **0** |

That is the number the fix should be judged on, and it is the one worth re-running if this path is ever widened.

### 26.6 Known bound: the leak gate only sees the LARGEST background component

Both the selection reject and the partial search test overlap against `largest_bg_component_mask`. A pocket of genuinely removable background that is NOT the largest component — background enclosed between two limbs, say — passes the gate and would be kept. That limitation is inherited from `detect_outline_background_leak` and is not new, but this fix **invokes it far more often** (up to six recommended outline colours on one asset where there was one), so the exposure is larger than it was. Tracked in the development repo's backlog.

### 26.7 The evidence strings ARE documentation

Finding this needed a `references/lessons.md §26` to exist, which is how it surfaced that **§25 did not** — the script had been printing "see references/lessons.md SS25" inside a recommendation for a whole release, pointing at a section nobody had written.

**The generalisable part: a tool's user-facing OUTPUT is documentation, and it is usually the half nobody checks.** Prose files get checked because they look like documentation. The strings a program prints do not — and for an autonomous run they are the *only* documentation it ever reads, because it never opens a reference file. Whatever consistency check covers the prose should cover the output too. (The development repo's own gate for this, and the release checklist it belongs to, live on the repo side; a session running from the packaged skill cannot act on them.)

## 27. Three roles for one colour: the structural route measured and ruled out

**2026-08-18.** `2d4a092f5494a8d2455703857ee83d5c.gif` is a bunny holding a transparent bag of popcorn, and one `#ffffff` plays three parts: outer background (remove), bunny body (keep opaque), bag interior (make TRANSLUCENT, so it reads as a bag). The pixels are byte-identical, so no colour rule separates them. The open question was whether STRUCTURE could.

### 27.1 The hypothesis, and the measurement that killed it

The recorded next step was: check whether the bag interior is topologically CONNECTED to the outer background through the bag's opening. If it were, flood-fill-from-border would reach into it, which would have explained "the white inside the bag gets removed" exactly and pointed at a fix.

Measured on frame 0, labelling the background-coloured mask and marking which components touch the canvas edge:

| component | px | bbox | border-connected |
|---|---|---|---|
| 1 (outer background) | 58,037 | full canvas | **yes** |
| 3 (bunny body) | 27,767 | (157,79)-(353,330) | no |
| 2 (**bag interior**) | 14,069 | (51,17)-(306,250) | no |

**The hypothesis is false.** The bag interior is a fully enclosed pocket, and so is the bunny's body — both bounded by the same brown outline, both unreachable from the border, and 42,209 px of enclosed background exists on every one of the 12 frames. Connectivity does not distinguish them any more than colour does.

That is the useful result, because it closes the search rather than narrowing it. In flat vector art there is nothing *behind* the bag — the popcorn is drawn on top of a white fill, not seen through a translucent layer — so "translucent" is authoring intent, with no pixel or topological evidence to recover it from. Every structural signal available here is identical for the two pockets.

### 27.2 What shipped, and the two restrictions that make a hand-drawn region safe

`--translucent-region` (same `circle:`/`rect:`, `;`-separated spec syntax as `--protect-region`), with `--translucent-alpha` (default 0.35) and `--translucent-color` (defaults to the background colour). Requires a `.webp`/`.avif`/`.apng` output.

Naming the region by hand is the whole mechanism, so the restrictions matter more than usual:

* **Colour.** Only pixels matching `--translucent-color` are touched. Without this the first test — a rectangle over the bag — turned the POPCORN translucent too, which is precisely backwards: the contents are what the glass is supposed to reveal. Measured: 133,070 px affected without the colour restriction, 76,988 with it.
* **Alpha.** Only already-opaque pixels are lowered, so an antialiasing ramp or a recovered fade inside the region keeps its own alpha rather than being raised to the translucency level.

Verified by compositing over a dark solid rather than a checkerboard (§16's rule — a checkerboard camouflages exactly this): the bag material reads see-through, the popcorn and the bunny stay opaque.

**Known limit, and it is inherent:** a rectangle cannot follow a shape that another same-colour element overlaps. On this asset the bunny's white body sits partly inside any rectangle large enough to cover the whole bag, so it needs several `;`-separated specs. That is a cost of the region being hand-drawn, and the measurement above is why it has to be.

---

## 28. The fifth pixel-art discriminator, and what the first four never tested

**2026-08-18.** §23.5 left 7 of 25 labelled pixel-art assets undetected, all dithered or photographic. §23.8 and §23.9 then killed two more candidates on the vector-emoji population and concluded that the whole "where does the image change along a scan line" family was exhausted, recommending palette structure or the alpha ramp instead. What actually worked was neither — it was the same family, **conditioned on an edge**. Getting there also turned up four defects that had nothing to do with the new measure and everything to do with how the old ones were being fed.

### 28.1 The measure: what share of the STRONG steps are plateau-to-plateau cliffs

`measure_plateau_cliff_ratio` walks both axes and looks only at pairs of adjacent pixels differing by 40 or more on some channel — an *edge*, not an antialiasing increment. Such a step counts as a **cliff** when both sides sit inside a flat run of at least 2 px. Upscaled pixel art transitions block-to-block and is nearly all cliffs. A 1 px antialiasing ramp cannot be one, because the ramp pixel is a plateau of length 1 by construction.

**The conditioning is the load-bearing part, not the statistic.** §23.9's diagnosis was that the four dead measures asked the wrong question; the sharper reading is that they asked it *everywhere*. Duplicate-line density fired on 37 of 145 emoji because a flat vector fill has large areas where the next column is genuinely identical — and that area contains no strong steps at all, so it contributes nothing here. Pixel-art-ness is a property of EDGES: `--pixel-art` exists because feathering, erosion and LANCZOS destroy hard edges (§4, 0% survival on a 31 px shape). A measure of global uniformity was never measuring the thing the decision depends on. It is entirely possible that duplicate-line density would also have survived had it been localised the same way; the lesson to carry forward is **localise to where the decision lives**, not "prefer palette measures over geometric ones".

### 28.2 Scored on both populations, because one of them cannot falsify it

Per §23.8's rule, every candidate is scored against the 25/6 labelled corpus AND the vector-emoji population the labelled corpus cannot represent. Here that is 122 emoji plus the 5 corpus originals (`love`, `heart`, `gift`, `explosion`, `crystal`), 133 negatives in total:

| | pixel art found | false positives | lowest true positive | highest negative |
|---|---|---|---|---|
| shipped v5.4.0 (`change_line_density` etc.) | 18/25 | see §28.6 | — | — |
| `plateau_cliff_ratio >= 0.30` | **22/25** | **0/133** | 0.356 | 0.186 |

The threshold sits between 0.186 and 0.356, deliberately nearer the negative end: a false positive applies `--pixel-art` to antialiased art — no feather, no erosion, nearest-neighbour resize, §18's catastrophe — while a false negative is only the status quo.

**Measure-level scoring is not the release number.** `appears_hard_edged` is an OR of four rules, so the only honest figure is what `analyze()` returns end to end. Run over all 155 assets under HEAD and under the branch, zero errors:

| population | n | HEAD says hard-edged | branch says hard-edged |
|---|---|---|---|
| labelled pixel art | 25 | 18 | **22** |
| labelled antialiased | 6 | 0 | **0** |
| corpus originals | 5 | 0 | **0** |
| vector emoji | 119 | 30 | **18** |

Every one of the four verdicts that flipped to TRUE is a labelled pixel-art asset. Every one of the twelve emoji verdicts that flipped to FALSE did so through §28.5's alpha composite — so the alpha bug was mis-recommending `--pixel-art` for **12 of 119 vector icons (10%)** at v5.4.0, not the two the spot check happened to catch. On the 34 files in the labelled folder, `--recommend`'s suggested flags changed on exactly 4, each of them gaining `--pixel-art` and nothing else, with no flag removed and no format changed anywhere.

`plateau_cliff_ratio >= 0.30` turned out to be a strict SUPERSET of `change_line_density < 0.5` on this corpus: all 18 assets the density rule catches score exactly 1.000 on the cliff ratio. That matters twice over — it is why §28.6's suppression costs no detection, and it means the density rule now contributes only in the thin-sample regime described in §28.4.

### 28.3 The three it still misses, and the obvious repair, measured and rejected

`Pixel Saber` 0.001 · `pandapanda…` 0.103 · `DFB2A5D7` 0.135.

⚠️ **CORRECTED the same day — "all three are blocks softened by re-encoding" was wrong, and §28.11 has the measurement that shows it.** They are not one mechanism. `Pixel Saber` has the *strongest* pixel grid of any asset tested (round-trip reconstruction error **0.44**, better than every confidently-detected control) with **97% of neighbouring pixels exactly equal** — nothing about it is softened. Its 1,450 strong steps simply have 1-px transition pixels at the high-contrast edges: **hand-placed antialiasing, a normal pixel-art shading style.** `DFB2A5D7` is the same story (grid error 0.97, 1-px grey seams between blocks). Only `pandapanda…` fits the original explanation: a weak grid (3.62) with 85% exact neighbours and a dither checkerboard.

The original wording came from looking at two raw pixel dumps and generalising to the third. The measurement is in §28.11.

So the obvious repair is a **tolerant** plateau: count near-equal as flat. It was implemented and scored, and it fails on both counts. It does not rescue the three (panda 0.103 → 0.144, DFB2A5D7 0.135 → 0.167, still far under any usable threshold) and it MANUFACTURES a false positive: `GIF Selections`, labelled antialiased, goes 0.078 → 0.497 at tolerance 4 and → 0.864 at tolerance 8, because loosening the plateau test lets a slow gradient count as flat. **Do not re-attempt tolerant plateaus.** Exact equality is not an oversight; it is what keeps the measure from reading a gradient as a block.

### 28.4 A ratio computed from 177 samples is not a measurement

`GIF Selections` has only ~180 strong steps in a 500x500 frame, and its cliff ratio swings wildly across frames as a result. It is reported as `plateau_cliff_samples` and gated: below 500 strong steps the cliff ratio may not produce a hard-edged verdict. The floor costs nothing — the lowest sample count among the 22 detected assets is 1,642 — and it follows the standing rule that a check which cannot be made reliable should say so rather than return a confident wrong answer (§13, §16, §17).

Note precisely what the count measures: it is the MEDIAN across sampled frames, so an animation whose art enters late has a low median for a reason that has nothing to do with resolution. That is a false-negative direction, so it is safe.

**The median is load-bearing, and it is the OPPOSITE choice from `ratio_max_across_frames` — deliberately.** Per-frame spread was measured across the sampled frames of 16 assets, because this project already found the band ratio swinging 0.290–7.863 across love's 124 frames and had to switch it to a max. Most assets are tight (`Cut loop` 0.000–0.004, `07761f30` 1.000 flat, `Last Jedi` 0.771–0.843), but three straddle the threshold: `GIF Selections` **0.000–0.344** with only 3% of frames at or above 0.30, `love_transparent` **0.015–0.409** with 20%, and the marginal true positive `_ (9)` **0.283–0.370** with 92%. **A max-based rule would false-positive the first two.** The reason the two measures need opposite statistics is that they fire in opposite directions: a HIGH band ratio proves antialiasing, so any single frame showing a ramp settles it (max); a HIGH cliff ratio proves pixel art, and a single atypical frame — art mostly off-canvas, a transitional flash — must not settle it (median).

⚠️ `_ (9)` is detected at a median of 0.336 with a per-frame minimum of 0.283. It is a true positive, but a marginal one: change the frame sampling and its verdict could move. It is the only asset in the corpus with that property.

### 28.5 Every hardness measure was reading RGB with the alpha thrown away

**This is the defect the new measure did not cause and did expose.** `analyze()` builds its frames as `np.array(im.convert('RGB'))`. For a source that already carries an ALPHA channel, the antialiasing lives in alpha — and `convert('RGB')` drops alpha without compositing, so a partially transparent edge pixel keeps its full-strength art colour and **the ramp vanishes**. Every hardness measure then sees a hard silhouette that does not exist.

Measured on `exchange.png`, a real 512x512 RGBA icon with 1.5% partial-alpha pixels: `plateau_cliff_ratio` **0.320 read straight from RGB against 0.000 composited** — the difference between "pixel art" and "obviously not". It is not confined to the new measure: at HEAD, `exchange.png` and `delete.png` both come back `appears_hard_edged: true`, so v5.4.0 recommends `--pixel-art` for two ordinary antialiased vector icons.

The fix composites over the DETECTED BACKGROUND COLOUR, which reconstructs exactly what a viewer sees, and therefore the image the removal step will actually face. Opaque sources — every asset in the labelled corpus and every corpus original — take the identical path, because there is no partial alpha to composite. `edge_hardness` now reports `measured_on_alpha_composite` so the choice is visible.

**How it was found is the transferable part.** The first validation of the cliff measure fed the function frames *I* had composited, sampled 5 per asset. The product reads up to 40 raw frames. Re-scoring through the product's own frame handling was what surfaced the single false positive, and that false positive was the alpha bug. **A measure validated on pixels the product never sees has not been validated** — the same shape as §24 (a path only the sandbox takes) and §23.6 (a fixture that agreed with the theory because both came from me).

⚠️ **The composite fixes the ramps that CARRY COLOUR, and the class it cannot reach turned out to be a different bug entirely — see §28.9.** 18 emoji still came back hard-edged after the composite landed, all through the pre-existing "no transition band at all" rule and all identically flagged at HEAD. 15 of them are **alpha-only masks**, and chasing that is what found a data-destruction bug. The 3 others are 1-bit-alpha files, covered by the note below. The contrast case worth keeping here is `delete.png`, whose ramp DOES carry colour — 67% of its ramp pixels land inside the band window — which is exactly why the composite rescued it.

⚠️ **A 1-bit-alpha source is a different case and is NOT a bug.** An already-processed GIF from this tool (`love_transparent.gif`) reads as hard-edged, and correctly: writing the GIF destroyed the ramp, so the FILE genuinely has hard edges even though the ARTWORK is antialiased. Compositing cannot help — there is no partial alpha left to composite. This also means the "presumed antialiased by provenance" emoji population needs stratifying: a processed output is not a counterexample.

### 28.6 A low density and a low cliff ratio cannot both be true of pixel art

`add.png`, a 512x512 vector icon: `change_line_density` **0.447** — below the 0.5 floor, so v5.4.0 calls it hard-edged and recommends `--pixel-art` — against `plateau_cliff_ratio` **0.070** over 3,737 strong steps, a band ratio of **16.079** and a blend ratio of **2.960**, the last two emphatically antialiased. Checked by eye from an edge-dense crop upscaled NEAREST (the `others/LABELS.json` method): a large flat green field meeting white through a single grey ramp column. Its low density comes from having barely any detail, not from a pixel grid.

The rule that resolves it is an **entailment, not a tuned margin**: a density below 0.5 means the image changes only every few scan lines — blocks wider than one pixel — which *entails* plateaus of 2 px or more at each edge, i.e. a high cliff ratio. When the cliff ratio says the opposite on a decent sample, the low density is coming from something else. So `change_line_density < 0.5` is dispositive UNLESS the cliff measure has the samples to contradict it (≥ 500 steps and ratio < 0.30). All 18 assets the density rule detects score cliff 1.000, so this costs no detection, and the suppressed evidence is reported rather than dropped (`hard_edged_suppressed_notes`).

**Note the asymmetry that keeps it safe.** §23.3 established that the blend ratio must never VETO a verdict, because on coloured backgrounds its "blends" are palette collisions. This is not that: the cliff ratio may only suppress the density rule, both measures are colour-blind block-structure measures, and with a thin sample the density rule still stands alone.

### 28.7 The evidence string described a rule that had not been the rule since v5.0.0

`--recommend` printed, for EVERY hard-edged verdict: *"Two independent measures agree: the transition band is empty in every sampled frame, AND there are essentially no background-to-art blend pixels."* `appears_hard_edged` has been an OR of several independent rules since v5.0.0. On an asset detected by `change_line_density` alone — `07761f30`, band ratio 20.895, blend 0.000 — the first half of that sentence is simply false, and on others both halves are.

`analyze()` now records WHICH disjunct fired (`hard_edged_reasons`) and `--recommend` prints those. This is §26.7's rule applied to itself: an autonomous run takes the flags verbatim and a human audits the evidence, so **evidence naming a measure that did not drive the decision is worse than no evidence** — it manufactures the impression that two things were checked. Built in `analyze()` rather than re-derived in `recommend()` so the thresholds live in exactly one place.

### 28.8 `--analyze` crashed on the static JPEG the skill advertises

Feeding a real `.jpeg` from the asset folder to `--analyze`: `AttributeError: 'JpegImageFile' object has no attribute 'n_frames'`. The PROCESSING path learned this in v5.2.0 and reads `getattr(im0, 'n_frames', 1)` with a comment naming JPEG explicitly — but `analyze()` and `load_animation_rgba_frames()` were left on the bare attribute, so `--analyze`, `--recommend`, `--auto` and `--verify` all died with a raw traceback on exactly the static-image input v5.2.0 shipped support for.

This is the handoff's **"the inverse spelling is where the bug hides"** in its purest form: the sites that needed fixing were found and fixed, and two that needed the identical fix were not, because no test ever pointed `--analyze` at a JPEG. Red-green verified: the fixed script analyses and recommends on that file, and HEAD still raises the AttributeError.

### 28.9 An alpha-only source: the tool destroyed the image and reported success

**The 15 remaining false positives were all one thing, and it was not a detection problem.** Measured across this project's asset folders: 15 of 137 files have **exactly ONE unique RGB value** (max-minus-min channel span 0) and **186–256 distinct ALPHA levels**. They are monochrome glyph icons exported as a flat fill plus an alpha mask — an entirely ordinary export style. Every colour-based measure in this file is reading a uniform plane on such a file: there is no background colour to key, no transition band, no blends, and no colour steps at all (`plateau_cliff_samples` comes back **0**).

**The misread was the least of it.** `detect_bg_color` returns that one flat colour, `color_mask` then matches every pixel in the frame, and the render removes the whole image. Measured on `pencil.png`: **69,925 opaque pixels in, ZERO out** — and HEAD's `--auto` printed success. The destructive run even coalesced 30 frames down to 1, and nothing objected.

**Why every gate passed.** This is §26.5's rule in its purest form: *a metric that cannot fail is not a check.* Every quality measure in `verify()` asks how WELL the background was removed — leftover background, edge fringe, small-region inflation, protected-region coverage. **An empty output scores perfectly on all four**, because there is no leftover background to count, no fringe to find, no region to come back thin. Not one of them asks whether anything survived.

Three fixes, at three different layers:

- **Detection.** `alpha_only_source` and `source_alpha_levels` are reported, every colour-based rule abstains, and hardness is read off the alpha channel instead. The separation there is a margin of KIND: a hard cutout has exactly **2** alpha levels, these carry **186–256**. Nothing is tuned.
- **Recommendation.** `--recommend` returns `not_applicable_reason` and sets `suggested_command` to `None`, so an autonomous run cannot paste a command that empties the file, and `--auto` exits with the explanation instead of rendering.
- **The render itself.** `_refuse_empty_render` runs at the top of all four renderers and refuses to write a file in which nothing is opaque on any frame. The invariant is deliberately whole-file rather than per-frame — a blank frame inside an animation that fades out is normal; "no opaque pixel anywhere" is not. Nothing is written, so a good file at the output path is never overwritten by an empty one. `verify()` also reports `output_opaque_px` and an explicit `output_is_empty`.

**The transferable lesson is about where I was looking.** I had filed these 15 as a P1 blocked on acquiring labelled RGBA pixel art, and was about to build an alpha-ramp *veto* to out-vote the band rules. Asking instead **why** the band was empty — rather than how to overrule it — found the data-destruction bug and made the veto unnecessary: no new measure, no new threshold, and no new corpus needed. **When a measure gives an answer you believe is wrong, establish what it is actually reading before deciding it needs outvoting.** An empty transition band was not weak evidence of hard edges; it was the absence of any evidence at all, on an input where the colour channel is blank by construction.

### 28.10 An AI upscale removes the very property `--pixel-art` keys on

**2026-08-18.** Harkirat ran Upscayl's Digital Art model at 4x, 8x and 16x over eight assets to test §28.3's claim. The result settles a different question than the one asked, and it is worth keeping:

| asset | original | 4x | 8x | 16x |
|---|---|---|---|---|
| `07761f30` (detected pixel art) | cliff **1.000** | 0.000 | 0.000 | 0.000 |
| `cat` (detected) | cliff **1.000** | 0.000 | 0.000 | 0.000 |
| `mario` (detected) | cliff **1.000** | 0.000 | 0.000 | 0.000 |
| `_ (9)` (detected, dithered) | cliff **0.321** | 0.000 | 0.000 | 0.000 |
| jar bunny (antialiased control) | cliff 0.029 | 0.000 | 0.000 | 0.000 |

**Every asset comes back at cliff 0.000 and `change_line_density` 0.78–1.00**, including the three the detector is most confident about. The model reconstructs each block boundary as a gradient, so the file is no longer hard-edged in any measurable sense.

Two things follow. **First, the detector is RIGHT to decline `--pixel-art` on an upscaled sprite** — the artwork was pixel art, the file no longer is, and feathering plus erosion is now the appropriate treatment for it. "I upscaled my sprite, now handle it" is a completely ordinary user path, and the answer it gets is correct. **Second, this treatment cannot test §28.3**, because it destroys the property under test on the known-positive controls as well. The negative control is what makes that conclusion safe rather than assumed: the antialiased asset went 0.029 → 0.000, so the upscaler only ever REMOVES blocks and never manufactures them, which rules out "the upscaler invented the smoothness".

### 28.11 Hand-antialiased pixel art, and the one signal that survives

Testing §28.3 needed a treatment that does not disturb what it measures, so: **does a real pixel GRID underlie the image?** Downsample by k, re-upscale by k with nearest, and measure the reconstruction error, solving for phase so a crop offset cannot hide a grid. A genuine k-times upscale reconstructs with small error however much re-encoding has since softened it; genuinely antialiased art loses real detail.

| asset | grid error | reading |
|---|---|---|
| `Pixel Saber` (MISSED) | **0.44** | strongest grid of all eight |
| `_ (9)` (detected) | 0.69 | strong |
| `mario` (detected) | 0.75 | strong |
| `07761f30` (detected) | 0.84 | strong |
| `DFB2A5D7` (MISSED) | 0.97 | strong |
| `cat` (detected) | 1.06 | strong |
| `pandapanda…` (MISSED) | 3.62 | weak |
| jar bunny (antialiased) | 3.91 | weak |

**So two of the three misses have a pixel grid as good as or better than the assets the detector is most sure about.** What they lack is not blocks; it is *cliffs*. `Pixel Saber` has 97% of neighbouring pixels exactly equal and 1,450 strong colour steps, and **essentially none of those steps has a 2-px plateau on both sides** — the cliff ratio is 0.001 at every plateau tolerance from 0 to 4, so noise is not the cause. Its high-contrast edges carry a single transition pixel, placed by hand. That is **hand-antialiased pixel art**, an ordinary shading style.

**And that is a hard limit on every edge-local measure, this one included.** At the edge, hand-placed antialiasing and machine antialiasing are the same thing: an intermediate pixel between two flat colours. No measurement taken at the boundary can separate them, because there is nothing there to separate. The only signal that distinguishes them is the GRID — a global property — and the round-trip reconstruction error above measures it with a **4x margin** on this sample (0.44–1.06 for the six grid-bearing assets against 3.62–3.91 for the two without).

**Next action, and it is a better one than the entry it replaces:** score that round-trip grid error against BOTH populations — the 31 labelled assets and the 122 emoji, now joined by 524 real sprite-pack files — before believing it. Note what it is: §23.4's integer-lattice idea rebuilt as a *reconstruction error* rather than a congruence fit, which is why it may survive where that scored only 11 of 25. It is also the first measure in this whole line that is global rather than edge-local, which is the specific reason to expect something new from it. **It is NOT shipped: an 8-asset pilot is a lead, not evidence.**

### 28.12 524 real sprites: the biggest gain of the session, and a regression in my own new rule

**2026-08-18.** Harkirat supplied two populations this project had never had: **524 files from real itch.io sprite packs** (pixel art by provenance — 198 hard-alpha, 294 soft-alpha, 32 opaque) and 37 background-removed assets. (Both live in the development repo and are NOT part of this package — the numbers below are provenance for the rules, not something you can re-run here.) Scored end to end through `analyze()`, HEAD against the branch:

| population | n | HEAD detected | branch detected |
|---|---|---|---|
| sprite packs, hard-alpha | 198 | 52 (26.3%) | **143 (72.2%)** |
| sprite packs, soft-alpha | 294 | 0 (0.0%) | **282 (95.9%)** |
| sprite packs, opaque | 32 | 2 | 2 |
| **sprite packs, total** | **524** | **54 (10.3%)** | **427 (81.5%)** |
| background-removed assets | 37 | 24 | 26 |

The soft-alpha row is the striking one: HEAD detected **none** of 294 real pixel-art sprites, because a PNG with a transparent background has no colour band for the band rules to read. This is the single largest correctness gain in the session, and none of it was visible from the labelled corpus, whose 31 assets are all fully opaque GIFs.

**And the same population found a regression in a rule I had added hours earlier.** §28.6's density suppression turned **4 genuine pixel-art sprite sheets from detected to undetected** — `Soldier.png`, `Orc.png` and their with-shadows variants: density 0.271–0.309 (correctly reading as pixel art), cliff 0.130–0.211 over 7,109–11,342 steps (suppressing it). My entailment argument had a hole in both halves: a low density can come from **empty space** rather than blocks (a 900x700 sheet of 100x100 cells is mostly transparent), and a low cliff ratio can come from art drawn **1:1** rather than from a ramp, because a 1-px block has no 2-px plateau to sit between.

**The exception, and why it is stated in terms of ALPHA rather than the blend ratio.** A source whose alpha is strictly binary is a hard cutout: there is no antialiasing at its silhouette, by construction. So on such a file the absence of cliffs cannot be evidence of a ramp, and the suppression is blocked. The tempting alternative was to require positive antialiasing evidence from the blend ratio — `add.png`, which the suppression *should* catch, reads band 16.079 and blend 2.960 against these sprites' 0.093–0.160 and 0.236–0.671. **But §23.5 measured pixel art and vector art overlapping completely on the blend ratio, so it cannot carry that weight.** The alpha channel states the fact directly instead of inferring it from colour.

**Verified exhaustively rather than by sampling.** Across all 716 scored assets the density suppression was firing on exactly **five**: the four sprite sheets, which the exception now correctly detects, and `add.png` (173 alpha levels), which stays suppressed. Nothing else in any population can change, so the fix is bounded by enumeration, not by a spot check.

**The standing lesson, for the third time today.** [[feedback_falsifier_population]] says to ask which population a measure's failure would live in and check that it is in the sample. Every rule added today was scored against 133 negatives and 25 positives and looked clean; two of them had defects that only a *new* population could show — the alpha-mask level cut (§28.10's sibling, caught by all 524 sprites having ≤4 alpha levels against my cut at 2) and this suppression. **A falsifier population is not a one-time gate you pass; it is only ever as good as the content types it happens to contain.**

### 28.13 Partial destruction: 65.6% survival on a sprite, and every other check passed

**Found in the final gate sweep, on one of the new sprite files.** §28.9 caught TOTAL destruction. This is its sibling: a real itch.io sprite sheet went in with **7,130 opaque pixels and came out with 4,675 — 65.6% survival** — and `--verify` reported no leftover background, no fringe, no inflation, correct dimensions and exact frame alignment. Every check passed on a file that had lost a third of its artwork.

**The mechanism.** A hard-alpha PNG stores *something* in the RGB channels under its transparent pixels, and on these sprites that something is `(0, 0, 0)`. `detect_bg_color` reads the modal colour and returns black; `color_mask` then matches every black pixel in the frame — **including the sprite's own black outlines**, which pixel art uses constantly.

Two safety nets, and one root cause deliberately left open:

- **`verify()` now reports `opaque_survival_vs_transparent_source`** and warns below 95%. It cannot be a blanket ratio: on an ordinary opaque source the whole canvas is "opaque" and a low survival rate is the entire *point* of the tool. It is only meaningful when the SOURCE already carried transparency, because then its opaque area IS the artwork. `--auto` prints it as `ART LOSS:` — §26.7's rule, since a warning in a JSON field nobody prints changes nothing.
- **An output extension this script cannot write is refused legibly.** `out.jpeg` fell through to GIF, Pillow claimed the extension for its own JPEG handler, and it died inside `SAVE_ALL` as a raw traceback line. Same shape as v5.4.0's `--verify` `FileNotFoundError` fix.
- **A static source is no longer reported as a timing defect.** Comparing a static input's default 100 ms placeholder against a written PNG's 0 ms printed *"a real timing defect, not encoder frame-coalescing"* on an ordinary single-frame sprite. v5.4.0 added the static-image line to the PROCESS path and left `verify()` comparing durations — **the same split-brain as §28.8's `n_frames`, in the same session that documented it.** Both of `verify()`'s exits now share one `_timing_line` helper; the early dimension-mismatch return had its own copy of the call, which is how one gets fixed and the other does not.

**The root cause is a design decision, not a bug to patch quietly:** what *should* background removal do when the source already has a transparent background? There is nothing to remove, and inferring a background colour from the bytes under the alpha is guessing. Filed with this measurement rather than fixed, because changing it alters the core removal semantics for every alpha-carrying input and this project has no rendered-output baseline to validate that against — the same reason the uncomposited-RGB item is filed. **What is NOT deferred is the detection of the failure**, which is why both safety nets shipped here.

**Three data-loss classes in one session, all of them invisible to every quality check.** Total destruction (§28.9), partial destruction (here), and the destructive `--pixel-art` misapplication the detector work was originally about. Each was invisible for the same structural reason: **every measure in `verify()` scores how WELL the background was removed, and none of them asked how much of the artwork was still there.**

### 28.14 What removal should DO on an already-transparent source, and why the obvious compromise is harmful

§28.13 measured the damage and filed the semantics decision rather than guessing it. This is that decision, made with rendered evidence.

**The three candidates.** (a) Refuse, the way an alpha-only source now does — there is nothing to remove. (b) Restrict colour-based removal to the region the source's alpha already covers, plus a small band around it, honouring the existing alpha as the answer. (c) Keep the old behaviour but demand an explicit `--bg-color` for any source carrying transparency. (b) was recommended on the reasoning that it is the only one that still helps a source whose transparency is *partial* — a sprite with a transparent background but a leftover matte fringe — and that it degrades to (a) when the alpha is already complete.

**(b) was implemented and the cleanup band, its whole reason for existing, turned out to be harmful.** Survival on the sprite from §28.13, by band radius:

| `--source-alpha-band` | opaque out | survival | alpha identical to source? |
|---|---|---|---|
| 0 (i.e. option (a)) | 7,130 | **100.0%** | **yes, byte-identical** |
| 1 | 5,042 | 70.7% | no |
| 2 | 4,859 | 68.1% | no |
| unrestricted (option (c) / pre-fix) | 4,675 | 65.6% | no |

A 2px ring recovered **184** of the 2,455 pixels the unrestricted path destroyed and still destroyed 2,271 of them. The reason is structural rather than a bad radius: **pixel art's outline sits directly against its padding**, so any ring wide enough to catch a fringe is wide enough to be the outline. A compromise that keeps two thirds of the damage is not a fix, and had the band shipped at its proposed default it would have read as one.

**The repair is a margin of KIND, not a smaller radius.** The band is kept, and vetoed automatically whenever the background colour *also occurs in the artwork away from the transparent boundary*. If it does, that colour is design and the ring would eat design, so the scope collapses to exactly the source's own transparency. If it does not, the only pixels of that colour anywhere are hugging the boundary — which is what a leftover matte fringe looks like — and removing them is the point of not simply refusing. Same move as §28.1: localise the test to where the decision actually lives.

**Engagement is gated on two conditions, each blocking a different wrong engagement.** (1) The transparent region must reach the frame border — that is what makes it the outside rather than a punched interior hole, and a source whose only transparency is holes still has a real painted background that must stay removable. (2) The modal RGB *under* the transparent pixels must match the detected background within tolerance — this tests the failure mechanism directly instead of by proxy: when it holds, `detect_bg_color` did not find a background, it found padding.

**Measured across 76 alpha-carrying assets** (the 37 background-removed set plus a 40-file spread across all sprite packs), survival under each scope:

| branch | n | source-alpha only | +2px band, vetoed | unrestricted |
|---|---|---|---|---|
| veto fires (colour is also design) | 25 | 100.0% | 100.0% | mean 79.6%, **worst 28.7%** |
| veto does not fire | 51 | 100.0% | 100.0% | 100.0% (worst 99.9%) |

So the veto identifies exactly the assets that were losing artwork and takes all of them to full survival, while the 51 that were never at risk are untouched. **Both branches fire on real content** — 51 kept, 25 dropped — so neither is a dead path.

**What is NOT proven:** the band's *benefit*. On these 76 real assets the band removes nothing the unrestricted path would not also have left, so its fringe-cleanup value is unexercised — only its risk has been measured and neutralised. It stays because a partial cut is a real case, not because it has been seen to help. ⚠️ Do not quote the band as a feature that works; quote the veto.

**The inverse spelling, again (§28.13's own lesson, one level up).** `get_source_transparency_mask` handled a GIF palette transparency index and an RGB colour tuple, and returned `None` for a plain RGBA source — the most common spelling of all — so every transparent PNG looked like it had no source transparency. Only `alpha == 0` counts: a partially transparent pixel is a real antialiasing ramp with real colour in it, and treating a soft edge as "the source declared this nothing" would throw away the very ramp §28.5 exists to preserve.

**⚠️ FOUR PATHS, and the first fix reached only one of them. This is the part worth reading.** The scope was written into `compute_alpha_mask`, measured on the sprite with `--pixel-art`, and reported as fixed. A sequential-thinking audit pass then found that every other path still lost the artwork, each for a different reason, and each while the log printed `SOURCE ALPHA HONOURED`:

| path | before the audit | why | after |
|---|---|---|---|
| non-feather (`--pixel-art`) | 100.0% | the branch that was actually measured | 100.0% |
| **8-bit alpha (`.png`/`.webp`/`.avif`/`.apng`)** | **65.6%** | `dither_mode='continuous'` is a **THIRD return** in `compute_alpha_mask`, and the scope was applied at the other two | 100.0% |
| **`--recover-fade-alpha`** | **65.6%** | that branch `continue`s before the scope code; `build_art_palette` rejects art colours near the background and the flood starts at the border, so it has the same bug in a different spelling | 100.0% |
| **`.gif` output** | **23.0%** | the scope worked and then `--edge-cleanup-erosion 2` shaved the silhouette | 100.0% |

**The GIF number is the one to remember: 1,642 of 7,130 pixels survived with the scope working perfectly.** Edge-cleanup erosion exists to trim the mis-coloured ring that the *feathering math* leaves behind. When the silhouette came from the source's own alpha there is no such ring, and erosion is pure deletion. It is now set to 0 whenever the source-alpha policy engages, unless typed explicitly — the same "explicit wins, and we say so" contract `--pixel-art` uses.

**And the veto was being tested at the wrong radius.** `tolerance` is 15; the feather path acts across `tolerance × --feather-band-multiplier` = **60**. A veto evaluated at 15 while removal reaches 60 is three quarters short, and it showed: over every frame of 57 assets the feather path survived **99.71% mean / 95.24% worst** against the non-feather path's 100.00% / 99.95%. The veto now takes the reach the running path will actually use. **A veto has to be evaluated at the radius of the thing it vetoes.**

**Per-frame decisions flicker.** Deciding engagement and the veto per frame made **17 of 57 assets flip branch mid-animation** — one alternates keep/drop/keep/drop on consecutive frames — so a pixel would be removed on frame 3 and kept on frame 4. The policy is now computed once for the whole animation, reduced asymmetrically on the safe side of each question: engaged if ANY frame's transparency reads as its background (a frame where the character covers the border must not switch protection off), and the band allowed only if NO frame vetoes it.

**After all four: 100.00% mean and 100.00% worst, on both branches, across 57 assets and every frame of each.** The earlier "all 25 to 100.0%" was true of the one branch it was measured on, which is exactly the §28.5 mistake — a measurement taken on the path you chose rather than the path that runs.

**`--recommend` now says there is nothing to remove.** `analyze()` reports `source_background_already_transparent` with its reason, and the recommendation leads with `NOTHING TO REMOVE`. Deliberately NOT a `not_applicable_reason` like §28.9's: running the command here is safe and a format change or size cap is a real reason to. What would be dishonest is presenting a no-op as background removal, and an autonomous run reads that evidence.

**Escape hatch and reporting.** `--ignore-source-alpha` restores the old whole-frame behaviour for a source whose own alpha is wrong. Every run that engages the restriction prints what it did and why on stderr — the first version of that message announced the band from the flag value and then appended a reason saying the band had been dropped, one sentence contradicting the next, which is how a log stops being read.

### 28.15 Labelling the two populations that had been finding the defects

Every threshold in this skill had been scored against 31 labelled assets that are **all fully opaque GIFs**. On the same day, two brand-new rules cleared that scoring and were broken hours later by content the sample did not contain (§28.12). Both alpha-carrying populations are now labelled corpora.

**Method, and the one rule that keeps it honest: no measure from the script was consulted while labelling.** A corpus labelled by the thing under test proves only that the thing agrees with itself — §23's circular fixture. Labels come from edge-dense crops upscaled NEAREST (the method `others/LABELS.json` documents; a centre crop lands on flat fill and makes everything look smooth), at 7x for every asset and three non-overlapping crops at 13x for the eight genuinely ambiguous ones.

**524 sprite-pack files: 493 `pixel_art`, 31 `unsuitable_no_edges`.** Provenance was not trusted on its own — a spread sample from every pack was inspected, which matters most for the one pack that is 410 of the 524 files, i.e. the pack whose label decides the population. Two judgements are worth carrying:

- **30 full-frame colour-grade overlay plates are `unsuitable_no_edges` and EXCLUDED from scoring, not labelled antialiased.** They have 242–256 unique RGB values and **0.0% of horizontal steps ≥40**, so the cliff measure never runs (n=0 on 29 of 30). Calling them antialiased would hand any hard-edge rule 30 free true negatives that test nothing at all and inflate specificity — the falsifier-population trap, arrived at from the other direction. A label that cannot be wrong is not a label.
- **A 1-colour flat tile is also excluded.** 100% of its steps are 0; no edge exists, so no edge measure has an answer. The honest label is "unverifiable", not a pass.

**37 background-removed assets: 22 `pixel_art`, 15 `antialiased`.** Four of them are the cut-out counterparts of assets already labelled in the opaque corpus, and all four carry the same label their originals do — an independent consistency check on the method. One file has pixel-art *lineage* (its source is labelled pixel art) but is labelled **antialiased**, because it is an upscaled, re-encoded copy whose own pixels are ramped. **A label must describe what a discriminator can see, not the artwork's history.**

**The labelling immediately found something: 4 false positives among the 15 antialiased cutouts**, every one of them a ≤2-level hard-alpha source. A hard-alpha cutout composited over the detected background has a hard silhouette *by construction* — the alpha is binary, so there is no blend band to find — while the art's interior ramps are untouched. §28.12's hard-alpha exception to the density suppression therefore fires on exactly the wrong population. The same shape appears in the vector-emoji set, where 2 of the 3 remaining detections are files with `transparent` in their names.

**One registry, not four scripts.** `extract.py`, `final_run.py`, `sprite_run.py` and `corpus_run.sh` each hardcoded their own directory list, which is *why* two populations existed only inside whichever script had most recently needed them. A single registry now names all five populations, each with an explicit note on **what it is blind to** — the sprite corpus contains no antialiased art and therefore cannot detect a false positive; the emoji set contains no pixel art, so a rule that fires on nothing scores perfectly there. Scoring reports per-population and, for the sprite corpus, per-pack, because a pooled number over a population that is 78% one pack is mostly a statement about that pack.

**The first registry-wide run paid for the registry immediately.** 688 scoreable assets through `analyze()`: recall 0.870 overall, specificity 0.953. Per population — labelled 22/25 with 0 false positives, background-removed cutouts 22/22 with **4** false positives (specificity 0.733, the hard-alpha class above), sprites 426/493, vector emoji 3 false positives in 122, corpus originals 0 in 5. **And the per-pack split immediately falsified the headline number:** the sprite corpus's 86.4% is 409 Tiny Swords files at 0.941 carrying two packs at **0.147 and 0.250**. Measured over the 67 misses against the 426 hits, medians: cliff ratio 0.215 vs 0.823, cliff samples **885 vs 7,021**, band ratio 0.246 vs 3.266, and `change_line_density` 1.000 in both — the misses are small sprites that simply do not contain enough strong colour steps to measure, some with n=17. No suppression rule is involved (every miss has an empty `hard_edged_suppressed_notes`). A pooled number over a lopsided population is a statement about its largest member, and that is the sentence the warning in the labels file now exists to prevent.

⚠️ **Two operational traps, both hit.** A results file written to a FIXED path is indistinguishable from a stale one — a "done" was once reported off a leftover file — so a run now requires an explicit output path and writes `<out>.partial` until it finishes. And a render baseline that reads the working-tree script re-reads it **per asset**: the first attempt at a pre-fix baseline had 40 of 106 assets measured against the old code and the rest against the new, because the script was edited mid-run.

⚠️ **That trap was then hit a SECOND time, one hour later, in the run whose whole purpose was to measure those edits** — the fix had been to give the harness an explicit script argument and pass a pristine copy, and the post-fix run was pointed at the working tree because that is where the fix under test lived. The results were uninterpretable in a way that looked like data: 60 of 106 assets changed, some opaque counts tripling and others falling to 21%, with no way to tell which half of the code produced which row. **The lesson is not "be careful not to edit during a run".** A discipline that has to be remembered at the moment of highest distraction is not a control. The harness now **copies the script to a temp file at startup and runs the copy**, recording the source digest in the output — so the split cannot happen whether or not anyone remembers.
