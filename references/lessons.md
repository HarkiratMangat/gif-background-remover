# GIF Background Remover — Lessons, Postmortems & Tool Evaluations

This file holds the full evidence trail behind SKILL.md's rules: bug postmortems, tool
evaluations, and measured numbers from this skill's real development history. SKILL.md states the
resulting *rule* concisely and points here; this file has the *why*, including approaches that
were tried and reverted — read those before re-attempting them.

**When to read this file:** before re-diagnosing anything that smells like a past case (flicker or
a gap in a protected region, erosion eating fine detail, jagged edges surviving a resize, a wrong
animation-length claim, a "grainy/messy" complaint after compression, a which-tool-or-quantizer
question). Check the table of contents below for a matching section first. This history is long and
specific, and several fixes were tried, looked right, and later regressed — re-deriving one from
scratch risks retrying an approach already known to fail.

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

**Second confirmed case (2026-08-17, §16's asset):** `love.gif` scored **0.425** — under the 0.5
threshold, so `--recommend` suggested `--pixel-art`, which would have disabled feathering and
erosion on curve-heavy antialiased vector art. Zooming 8× showed a real 1–2px antialiasing ramp.
`--recommend` now attaches an explicit "near the 0.5 boundary, zoom before accepting" warning to any
ratio at or above 0.30, so this caveat travels with the recommendation instead of relying on someone
remembering to read this section.
SKILL.md's rule: `edge_hardness.ratio` under ~0.5 means hard-edged (use `--pixel-art`); a few units
or more means real antialiasing (normal defaults are correct). Real measurements for reference: a
genuine pixel-art test file measured 0.0; two real antialiased vector icon test files measured 4.5
and 17.6. The gap is normally large and clean.

**The caveat, found on a real icon pack that was otherwise entirely normal vector art:** the ratio
is sensitive to how much of the icon's perimeter is curved vs. straight, not purely to "is there
antialiasing." A straight axis-aligned edge only needs a thin 1px antialiasing transition
regardless of style, while a curved or diagonal edge needs a wider graduated band — so an icon
dominated by straight lines (a trash can, a rectangular sweep effect) can score LOW (e.g.
0.17-0.39, under the ~0.5 threshold) despite being entirely ordinary antialiased vector art from
the same consistent design system as icons in the same set scoring 2-17+. Confirmed directly: two
icons from an otherwise uniform icon pack triggered the hard-edged threshold this way, and
applying `--pixel-art` to them would have been wrong. **When a ratio comes back hard-edged but the
icon is visually part of a set with other icons that scored normally, or the source is a
professional/exported vector asset rather than something hand-drawn pixel-by-pixel, look at it
directly (zoom in) before trusting the ratio alone** — geometry-heavy icons are the false-positive
case to watch for.

## 2. Why `--protect-region` is a last resort
`--protect-region circle:cx,cy,r` assumes the true protected shape IS a circle of that exact
radius in every direction from the center. Almost no real icon interior actually is. A
badge/rosette ring is scalloped (the true boundary can easily range e.g. 86-183px from center
depending on direction, even though it "looks roughly round" at a glance); a gem/diamond has a
pointed apex; stars, seals, and most decorative icon interiors are similarly non-circular. Picking
one fixed radius means:
- In directions where the true edge is CLOSER than that radius, the circle overshoots past the
  real boundary and keeps background-colored pixels opaque that should have been removed — a
  bleed/halo that sits flush against the art (easy to mistake for part of the design at a glance).
- In directions where the true edge is FARTHER than that radius, the circle falls short and clips
  into what should have been protected, leaving a notch or gap.

**Not a hypothetical** — it happened twice in the same session on two different icons that both
"looked round enough" at a glance: a badge rosette (scalloped ring, true radius 86-183px) rendered
with a fixed radius-126 circle left a visible extra white lobe bulging past the ring on one side,
and a diamond gem's pointed white facet rendered as a bounding circle left a large stray white
disc floating in the background above the diamond's point. Both looked fine in a quick glance at
the preview thumbnail and were only caught on user report / closer pixel inspection.
`rect:x,y,w,h` has the same failure mode for anything not truly axis-aligned rectangular.

The badge/rosette case above was actually fixed by opening the source frame and identifying the
true enclosing outline color by eye — sampling a pixel a short distance outward from the protected
area in a couple of different directions and checking they agree — then using that directly with
`--protect-outline-color`. This one extra manual step is far cheaper than debugging a bleed after
the fact.

## 3. Protected-region flicker: three implementation attempts, then v2 detection
This started as a real, confirmed bug reported by a user, went through THREE implementations, and
the shipped v1 mechanism is deliberately the most conservative of the three after the other two
caused real regressions on real files. **Read this before touching `build_protected_masks_robust`
again.**

**The mechanism:** `--protect-outline-color` works by finding all pixels matching that color, then
running `binary_fill_holes` to identify what's enclosed. This requires the outline to form a fully
CLOSED ring in that specific frame. If any other animated design element (confirmed real cases: a
wifi-signal pulse; a "wipe" sweep effect) happens to visually cross or overlap the outline at some
frames, it locally replaces outline pixels with its own color, punching a gap — and
`binary_fill_holes` doesn't degrade gracefully, it can leak interior out. Symptom: the protected
region intermittently goes transparent or shows a gap.

**Attempt 1 (reverted): whole-frame substitution, gated on 70% of median area.** Flag frames whose
color-mask area drops under 70% of that color's own median, substitute the WHOLE mask from the
nearest non-anomalous frame. Confirmed to fix a severe case (wifi pulse breaking a cloud's
enclosure on 16/120 frames, area dropping to ~56% of median) without breaking a legitimately-
animated icon (a rotating design element that stays within +/-0.35% of its own median area
throughout). Confirmed gap: MISSES smaller, localized holes that don't move the aggregate area
much — a real case had a clearly visible hole (source solid white, output transparent) on frames
still at 93-95% of median, comfortably above even a 90% threshold.

**Attempt 2 (reverted): local connected-component patching against a majority-vote reference,
gated at 98% of median.** Built a per-pixel majority-vote reference shape from near-full-size
frames, and for any frame below the 98% gate, patched in specific missing connected components
(over a 50px floor) rather than substituting the whole frame. This DID fix the attempt-1 gap in
isolated testing — verified the specific reported hole closed, verified the previously-known
rotating-icon case still correctly stayed ungated. But delivered to the user end-to-end across a
full batch, it produced a NEW, different regression ("random white parts appearing behind the
gifs") that was not caught by the isolated per-case testing done before shipping it. The exact
mechanism was not pinned down before reverting — the decision was to stop layering increasingly
complex, incompletely-understood fixes on real user files rather than keep guessing. **The lesson:
verifying a fix against the specific case that motivated it, and against one or two known prior
regressions, is not the same as verifying it end-to-end across a full real batch.** Both matter;
only doing the former is how this shipped a second regression.

**v1 restored (current baseline underneath v2):** whole-frame substitution at a 70%-of-median
gate — the version with actual confirmed history of not causing a regression. Known limitation,
accepted deliberately: it will NOT catch a hole on a frame whose aggregate area is still 70%+ of
median, even if that hole is visibly real (confirmed real example above at 93-95%).

**Why `--analyze` doesn't catch this ahead of time:** `outline_color_verified` only checks the
candidate color against a SINGLE frame (the first sampled one). That result gets applied uniformly
across every frame during real processing, with no check that the color reliably encloses the
region on frames it was never tested against.

**v2 detection (current state) — improved again, this time without a regression** (unlike attempts
2 and 3 above, which is why this one is the shipped state and those weren't). Two more real cases
exposed v1's 70%-of-median threshold's blind spot in different ways:
- A gradually/dramatically MOVING design element (a cloud shifting position, not just occluded)
  has natural filled-area variation that can swing even more than a rotating shape — confirmed
  0.50 to 1.06 of median on a real icon, i.e. legitimate variation that dips WELL under v1's 70%
  gate. Distinguishing signal that separates this from a real bug: legitimate variation is GRADUAL
  across many consecutive frames; a real bug is a SHARP, often single-frame outlier against its own
  local neighborhood, even when it's embedded inside a smooth large-amplitude cycle (confirmed: a
  real one-frame anomaly on this exact icon was still correctly caught this way).
- A SUSTAINED occlusion spanning many consecutive frames (confirmed real case: a continuous "wipe"
  sweep effect) doesn't produce a sharp local outlier at all, so the local-neighborhood check alone
  can't see it — confirmed catching only 1 of ~15 visibly-bad frames with that check in isolation.

v2 detection combines BOTH, independently per color, taking the union of frames either one flags:
(a) a local-neighborhood check (sharp, isolated drop vs. a small window of nearby frames — safe for
gradual/large-amplitude legitimate motion), and (b) a whole-distribution statistical-gap check (a
sorted-value jump of >=8% separating a low cluster from a high cluster — catches sustained
occlusion that (a) can't). Both were verified independently to produce zero false positives across
every legitimate-animation case available (a rotation, and two large-amplitude smooth pulse/shift
cycles) before being combined. Substitution mechanism is unchanged from v1 (single nearest
non-anomalous frame, never a blended/combined reference).

**Known remaining gap, carried from v1, now narrower but not zero:** the sustained-occlusion (gap)
detector needs a genuine statistical gap; a sustained-but-mild occlusion that blends smoothly into
the animation's own natural variation (confirmed real case: a handful of frames on the same "wipe"
icon sitting in a transition zone between the bad and normal clusters) still won't be caught. Don't
claim "fully fixed" for a sustained-occlusion case without checking the specific frames a user
reports.

**A SEPARATE, more direct fix, worth trying FIRST before reaching for detection/substitution at
all:** if the outline is fading toward background color gradually (rather than being replaced
outright by a differently-colored crossing element), widening `--outline-tolerance` alone can keep
the ring topologically closed through the fade with NO cross-frame logic needed at all — confirmed
on a real "wipe" case: tolerance 40->80 brought the minimum per-frame filled-area ratio from 0.79 to
0.93, and a rigorous full-animation check (every true-interior pixel against source, not just an
aggregate area proxy) found zero remaining mismatches across all 124 frames. This is strictly safer
than substitution (no risk of cross-frame position mismatches, since nothing is borrowed from
another frame). Check by sampling a point that's outline-colored in a good frame across several bad
frames: shifts toward background color gradually → try tolerance first; gets replaced by an
unrelated solid color → occlusion, detection/substitution is the right tool.

**Confirmed generalizing to a second, structurally different case — a full color SHIFT between two
saturated colors, not just a fade toward background:** a star icon's own outline animated smoothly
between navy and a distinct purple (`104,100,247`), as an intentional design effect, not occlusion.
First instinct was multi-color `--protect-outline-color` (list both navy and purple) — this was the
WRONG lever and didn't work: both colors independently still showed heavy substitution (32/46 and
34/46 frames), because the outline passes through a continuous gradient of intermediate colors
between the two named endpoints, not a discrete switch — naming just the two endpoints leaves every
in-between frame still unmatched by either. Tolerance widening on the single base color (navy
alone) fixed it completely instead: tolerance 40->150 brought the minimum ratio from 0.216 to
0.865, confirmed zero substitution needed, stable across all 46 frames.

**Takeaway: when the outline's own color visibly changes across frames — fading toward background
OR shifting toward a completely different saturated color — try widening `--outline-tolerance` on
the ORIGINAL single color FIRST, before reaching for multi-color protection.** Multi-color
protection is for when multiple DISTINCT, STABLE outline colors coexist (confirmed real case: a
folder icon whose folder and triangle badge happened to share one outline color but could equally
have used two) — not for one outline that continuously drifts. The right tolerance value is
case-specific (80 sufficed for the fade-to-white case, the color-shift case needed 150) — test a
few values and check the resulting min-ratio rather than assuming a fixed number transfers.

**`--outline-tolerance` has its own real interaction with `--edge-cleanup-erosion`, confirmed the
hard way:** on the same "wipe" icon, after fixing the enclosure via tolerance widening, a DIFFERENT
artifact appeared — a visibly lighter, blended outline color staying fully opaque right at the true
silhouette edge before the cutoff to transparent (a real fringe artifact, confirmed via direct
pixel comparison to NOT be present at that severity with the default erosion). This icon had
already been set to `--edge-cleanup-erosion 1` (reduced from the default 2) earlier in the same
investigation, specifically to preserve a different thin design element — but erosion=1 turned out
insufficient to clean up the NEW fringe exposed by the wider tolerance. Reverting to the default
erosion=2 fixed it (confirmed: direct navy-to-transparent transition, no blended pixel) at the cost
of the thin element shrinking from 137px back to 126px (87% of the original source's 145px — a
real but acceptable tradeoff, not destruction). **Lesson: `--outline-tolerance` and
`--edge-cleanup-erosion` are not independent settings for a given icon — changing one can require
re-checking the other**, especially on icons that already needed a non-default erosion value for
unrelated reasons.

**Practical guidance for verification and reporting:** if a user reports a protected area
"flashing," a gap that "disappears," or white/background patches appearing where they shouldn't,
check the NOTE in stderr output first to see whether the fix fired — don't assume "no NOTE" means
"no problem," the detectors have known blind spots documented above. Before concluding a specific
reported artifact isn't reproducible, double- and triple-check the exact crop/coordinate offset
used for any diagnostic comparison (see section 9 below — a real case of an incorrectly-assumed
crop offset masking a real artifact while producing a spurious one elsewhere).

## 4. `--edge-cleanup-erosion 0` total-destruction bug (fixed in v2.1)
Confirmed directly: `--edge-cleanup-erosion 0` on a real icon produced a completely blank,
fully-transparent output (a 47-frame GIF that shrank to 1.9 KB) with NO error or warning. Root
cause: `erode_alpha_edge` passed `iterations` straight through to `scipy.ndimage.binary_erosion`,
and scipy's own documented behavior for `iterations < 1` is "repeat until the result no longer
changes" — NOT "no-op." For any bounded opaque region, repeated erosion always converges to
nothing, so `iterations=0` silently eroded every frame's content away completely. Confirmed the
mechanism in isolation: a 10x10 filled square went from 100px to 0px at `iterations=0`.

**Why this wasn't caught earlier despite `--pixel-art` also using `--edge-cleanup-erosion 0`
internally:** `--pixel-art` additionally sets `feather=False`, and the erosion call site is guarded
by `if args.feather:` for an unrelated reason (erosion is specifically feather-fringe cleanup, so
it's skipped when there's no feathering to clean up). That guard happened to also prevent
`--pixel-art`'s use of erosion=0 from ever reaching the buggy scipy call. The bug was only
reachable by passing `--edge-cleanup-erosion 0` directly, with feathering still on (the default) —
a real, unremarkable-looking combination that came up naturally while trying to preserve a tiny,
delicate animated element (a sparkle icon that shrinks to a few hundred pixels at the start/end of
its own pop-in/pop-out animation).

**Fix:** `erode_alpha_edge` now has an explicit `if iterations <= 0: return list(alpha_frames)`
guard at the top, making it a true no-op regardless of what scipy would otherwise do. Verified:
erosion=0 now correctly returns the full, undamaged content; existing behavior at erosion>=1 and
`--pixel-art` are both unchanged.

**The generalizable lesson:** a library function's behavior at a boundary/degenerate input value
(0, empty, None, negative) is not guaranteed to match the caller's intuition even when the
non-degenerate behavior is well understood and has been correct for a long time. This bug shipped
silently through v1 and v2 because every prior real-world case happened to either use erosion>=1,
or use erosion=0 exclusively via the one path (`--pixel-art`) that never actually reached the
vulnerable call. Don't assume a parameter's "obvious" meaning at its extreme values without
checking the underlying library's actual documented behavior there, especially for a value (0/off)
that reads as if it should be the safest, simplest case.

## 5. Reduced erosion & resize degradation on thin/geometry-light icons
`--pixel-art`'s `edge_hardness` check is a binary "is this pixel art" signal, but erosion damage
isn't actually binary — it's a spectrum tied to how much "bulk" a design has to absorb a fixed
pixel-count shave. A real confirmed case: two icons from an otherwise normal antialiased vector
icon pack (NOT flagged as pixel art, correctly so) still had thin elements (a lightning bolt, a
folder's back-flap outline line) that came back visibly more jagged/thinner than the source under
the DEFAULT `--edge-cleanup-erosion 2`, because thin elements have much less interior "padding" to
lose before erosion eats into the visible shape itself. Measured directly: a thin line's opaque
run-length was 145px in the source, 129px after default erosion (2px), and 137px at
`--edge-cleanup-erosion 1` — noticeably closer to source without reintroducing the fringe-color
artifact the default erosion exists to prevent (re-checked for fringe colors at erosion=1 on both
affected files, none found).

**Practical signal:** both affected icons also happened to have low `edge_hardness` ratios (0.39
and 0.17) — below the ~0.5 pixel-art threshold, but not by a huge margin, and this is the SAME
"straight-line-heavy geometry" pattern documented in section 1 above. Treat a low-but-not-hard-
edged ratio as a signal to consider `--edge-cleanup-erosion 1` even when `--pixel-art` itself
would be wrong. This isn't automatic — it needs a judgment call per icon, since erosion=1 is a
real quality/fringe-cleanup tradeoff, not a pure correctness fix like the erosion=0 bug was.

**Resize is a second, independent contributor to the same thin-element problem — check it
separately from erosion.** A user specifically reported a thin lightning-bolt element looking
"jagged and rough" versus a smooth original even AFTER erosion was reduced to 1. Measured directly
with a scale-invariant roundness proxy (edge-pixel-count / sqrt(area), isolated to just the thin
element): source measured 7.276, the SAME icon with NO resize measured 7.313 (~0.5% worse,
essentially unchanged), but the SAME icon WITH the tier's normal 512px-target resize measured 7.514
(~3.3% worse) and also lost ~24% of the element's pixel area outright. The mechanism: this script's
alpha decision is computed at full source resolution, THEN resized with LANCZOS, THEN re-binarized
(`alpha > 127`) — resizing an already-effectively-binary mask and re-thresholding is a well-known
recipe for staircasing on thin/high-curvature shapes, unlike resizing a naturally continuous-tone
image. If the icon's crop is only modestly above a tier's resize target (e.g. 536px vs. a 512px
target — an ~5% overage), consider `--resize-max-dim` set high enough to skip the resize entirely
— confirmed on the real case: skipping resize was not just higher quality but also produced a
SMALLER file (1292.9 KB vs. 1443.7 KB), since a cleaner, less-aliased edge compresses better via
LZW than a staircased one. Not even a pure quality-vs-size tradeoff in every case — check both.

**Confirmed a second time on a differently-shaped icon** (curved star points, not a thin bolt)
after a user asked for "smoother animation" with no more specific complaint than that: measured the
same roughness proxy on the star's outer silhouette and found the identical pattern — 11.28 resized
vs. 10.48 source, improving to 10.99 with resize skipped, again with a smaller file as a side
benefit (562 KB vs. 680 KB). Confirmed on two structurally different icons (a thin straight-line
element, and a curved/pointed outer silhouette) — treat "check whether skipping resize helps,
whenever the crop is only modestly over a tier's target" as a general check worth running whenever
a complaint is about smoothness/roughness/jaggedness.

## 6. Tools considered: gifski and pngquant
Documented so these aren't re-researched or re-tested from scratch without new evidence — both were
investigated seriously, not dismissed on sight.

**gifski** (libimagequant-based GIF encoder, same engine family as pngquant). Its own maintainer,
responding to a bug report about jagged edges from transparent PNG input, said plainly: "This is
unavoidable. The GIF format doesn't support alpha transparency" — meaning gifski does its own alpha
thresholding on whatever it's handed rather than preserving an input mask exactly, which conflicts
with this script's protected-region/feathered-edge alpha decisions (gifski would potentially
re-derive the transparency boundary rather than respect the one already computed). Separately, its
docs describe "cross-frame palettes" designed to combat per-frame palette drift — reasonable, but
not verified against this skill's mostly-static-content case, and not worth the risk to
transparency handling to find out. **Not integrated for the transparency/removal step, at all** —
see section 8 below for a separate, later-discovered use as a compression-only step.

**pngquant / libimagequant** (used directly, not via gifski) for building `render_frames_to_gif`'s
shared master palette, in place of Pillow's `Image.ADAPTIVE`. This one WAS implemented and
empirically tested, not just reasoned about abstractly. **Implemented as an explicit opt-in
(`--quantizer pngquant`), NOT the default** — the full reasoning:
- Isolated quantization-error measurement (MSE against the original, color-only, no GIF encoding
  involved) showed pngquant meaningfully outperforming Pillow's median-cut at every color count
  tested: 38% lower error at 16 colors, up to 81% lower at 128 colors.
- But swapped into the real end-to-end pipeline on real test art (identical settings, same source,
  only the master-palette algorithm changed) it produced LARGER output files at every tier tested —
  +4.0% at `optimize`, +6.8% at `heavy` — not smaller, the opposite of what the isolated MSE
  numbers implied.
- Working theory: pngquant optimizes for perceptual color accuracy, not for how well the resulting
  palette's indices compress via GIF's LZW. This skill's actual content (flat vector icon/sticker
  art, not photos or gradients) is exactly the case where index run-length/predictability matters
  more than marginal per-pixel color error, and `medium`/`heavy` tiers already run their own
  further gifsicle `--lossy`/`--dither` pass on top, which dilutes whatever quality edge the master
  palette had going in. Checked the color histogram directly on real test art: only ~8 colors
  actually do real design work (the flat fills); the rest of the ~150 distinct colors are a long
  tail of antialiasing/blend fringe shades. Either quantizer preserves those 8 core colors
  losslessly within any of this skill's color budgets (128+), so the measured MSE gap is
  concentrated in secondary edge-fringe fidelity, not core design accuracy — a real difference, but
  a narrow one for THIS content type.
- Given that, defaulting to it wasn't justified — but the underlying case for it wasn't zero
  either, just narrower than "always better." **`--quantizer pngquant` exists for**: content this
  skill hasn't primarily been validated against (genuine gradients/soft shading, where more real
  colors compete for the budget rather than a long tail of minor blend noise), or whenever the
  person explicitly says quality matters more than file size. Falls back to `pil` with a clear
  warning if pngquant isn't installed/available or the call fails. Works from `--batch` manifests
  too (any per-file override key works generically, `"quantizer": "pngquant"` included).
- **The lesson generalized, not just about this one tool:** a component that wins on an isolated,
  narrower benchmark (quantization MSE) can still lose on the metric that actually matters for the
  full pipeline (final file size on this skill's real content) if the two aren't measuring the same
  thing. Prefer re-testing swaps like this end-to-end on real output before adopting them, even when
  the underlying algorithm is well-regarded and the component-level numbers look unambiguous.
  (Standing rule behind this: test the naive/simpler option end-to-end on real content before
  committing to a bigger rebuild.)

## 7. GIF format has no partial transparency
Every pixel in a GIF frame is binary opaque-or-transparent; there is no such thing as a real
semi-transparent pixel the way PNG/WebP support. Confirmed hands-on while trying to fake a
"background bleeds through a highlight" effect on a recolored icon: wrote a pixel at alpha 114/255
intending a soft blended look, saved via Pillow's GIF encoder, and re-read the output — the alpha
came back rounded to 255 (fully opaque), byte-identical to a version that never attempted partial
alpha at all. This isn't a Pillow limitation specifically — it's the GIF format's own single-bit
transparency index, the same underlying fact section 6 above cites from gifski's maintainer in a
different context (gifski's alpha-thresholding behavior on transparent PNG input is a symptom of
this same format limitation, not an unrelated gifski quirk).

**⚠️ Updated by §16 (2026-08-17).** Everything in this section is still true *of GIF*, but it is no
longer the end of the story. The real fix for a translucent/fading element is to stop using GIF:
WebP and AVIF both store 8-bit alpha, and `--recover-fade-alpha` can reconstruct alpha that a GIF
export already flattened. Read §16 before reaching for the bake-a-flat-blend workaround below —
that workaround is now the fallback for when the deliverable *must* be a GIF, not the default
answer.

**Workaround for "I want it to look like the background bleeds through"**: if the final background
color is fixed and known ahead of time (e.g. a specific Discord button color), bake a literal flat
blend of that background color with the foreground color as an opaque pixel value, in place of
relying on real partial alpha. This achieves the same visual read without needing the format to do
something it structurally can't — confirmed working end-to-end on a real delivered asset (a
recolored eyedropper icon's highlight stripe, blended toward Discord blurple instead of left pure
white). This is a real constraint to flag to the user up front whenever a "soft"/"bleeding"/
"translucent" effect is requested against a GIF deliverable, not something to attempt and discover
mid-task.

## 8. gifski as a compression-tier alternative (not yet integrated)
Section 6 documents gifski being rejected for the TRANSPARENCY step specifically (its own
alpha-thresholding conflicts with this script's protected-region/feathering decisions) — that
finding still holds and gifski should NOT be used for the background-removal pass itself. But a
separate, later use case surfaced: as a COMPRESSION-ONLY step applied AFTER transparency is already
finalized (i.e. gifski re-encoding an already-transparent GIF, not deriving transparency itself),
a genuinely different tradeoff than what was evaluated in section 6.

Real comparison, same source asset, same target ("keep it smooth, hit Discord's 256KB emoji
limit"): this skill's own `--compress` tiers, working from `--target-kb 200`'s automatic cascade,
had to drop frames to hit budget — `--target-kb 200` alone jumped straight to a stride-4 frame-drop
(180 → 45 frames, 12.5fps) to reach 79.8KB; manually dialing in `--compress heavy --frame-stride 3`
did better (180 → 60 frames, 16.7fps, ~144KB) but still threw away 2 of every 3 frames. A user's
own manual pipeline outside this skill — crop transparent margin → resize to 128px width → gifski
re-encode at quality 68 — kept ALL 180 original frames (zero frame drops, full smoothness) at
248.26KB, comfortably under the 256KB limit with real margin. gifski at a well-chosen quality
setting outperformed this skill's own gifsicle-based frame-stride/lossy-dither tiers for this
specific "smooth motion matters more than absolute minimum size" case.

**Not yet integrated into this script** — flagging as a real, evidence-backed option to reach for
next time a user explicitly prioritizes animation smoothness over squeezing every last KB: for that
specific ask, after transparency is finalized via this script's normal removal pass, piping the
transparent output through an external `gifski --quality <N>` pass (tuning quality rather than
frame-stride to hit the target size) is worth trying as an alternative to escalating this script's
own `--compress heavy`/`--frame-stride` further. Not validated across a range of source assets yet
— this is one confirmed real-world data point, not a new default recommendation to reach for
unconditionally.

## 9. Verification pitfalls: Pillow's `ImageSequence.Iterator`, bbox-vs-mask, frame-offset drift

**Pillow's `ImageSequence.Iterator` yields the SAME underlying image object every time**, just
seeked to a new position — it does not return independent per-frame copies.
`frames = list(ImageSequence.Iterator(im)); [f.info['duration'] for f in frames]` looks reasonable
but is WRONG: by the time the second line runs, every `f` is the same object, now seeked to the
last frame, so every entry silently returns the LAST frame's duration. This produced a totally
fabricated "total animation length" that was off by more than 10x in one real case, and was
reported to a user before being caught. The correct pattern reads `.info['duration']` *immediately*
after each `.seek(i)`, in the same loop iteration — never after materializing a list of frames
first:
```python
im = Image.open(path)
durations = []
for i in range(im.n_frames):
    im.seek(i)
    durations.append(im.info.get('duration', 100))
```
For a fully independent, Pillow-bug-proof ground truth (worth using whenever duration correctness
actually matters for a claim you're about to make to the user), parse the GIF's raw Graphic Control
Extension delay bytes directly instead of trusting any decoder: each `0x21 0xF9` block has delay as
a little-endian 16-bit value at offset+4 in centiseconds; multiply by 10 for milliseconds. This is
what actually resolved the discrepancy above.

**When investigating a reported "this part flickers / goes transparent when it shouldn't"
complaint, sampling pixels by bounding box alone produces false positives.** A candidate region's
reported `bbox_xyxy` is a rectangle; the real enclosed shape usually isn't, so pixels that are
white-in-source-and-inside-the-bbox can still be legitimate background sitting just outside the
true enclosed area (e.g. the gap between two nearby design elements that both fall inside one
bounding rectangle). This happened for real while debugging a user report: a bbox-based check
showed opacity swinging from 0.0 to 1.0 across frames, looking exactly like a bug, until
re-checking with the proper mask (`binary_fill_holes` on the outline-color mask, same as the actual
processing code) showed the TRUE interior pixels were 100% opaque in every single frame — no bug at
all. Reproduce the actual protection logic (fill-holes on the outline mask) rather than
approximating it with a bounding box when the distinction matters for a real diagnosis.

**Frame-number correspondence between a user's own sprite-sheet/export tool and this script's own
frame indexing is NOT guaranteed to be a simple fixed offset.** Confirmed needing
composite-and-MSE matching against a candidate frame range to find the true correspondence, and the
offset drifted slightly (+4 vs +5) across the same sprite sheet, consistent with accumulated
rounding in a hand-estimated row pitch. Don't assume "the user's frame 40" is "this script's frame
40." Also double- and triple-check the exact crop/coordinate offset used for any diagnostic
comparison — a real case had an incorrectly-assumed crop offset (derived from frame-0-only
foreground detection instead of the TRUE union-of-all-frames crop this script actually uses)
produce a spurious "artifact" in one location while masking a real one elsewhere. Re-derive the
offset from the script's own logged crop coordinates.

## 10. Animated/rotating content: four related failures on a tumbling icon, seven rounds to fully fix
SKILL.md's rule: check whether the foreground shape rotates/translates significantly within the
canvas before choosing a strategy; if so, several default assumptions below become actively
dangerous, not just imprecise. This section is the evidence trail — four distinct, confirmed bugs
from the same real asset, each only surfacing after the previous one was fixed, taking seven full
delivery-and-rejection rounds (v1 through v7) before the asset was actually correct.

**The real case:** a 640x640, 124-frame calendar/gamepad icon GIF where the whole card
tumbles/rotates through a wide range of orientations (not a subtle wobble — real rotation,
occasionally flipping to show a second card layer behind it), while a purple gamepad with a white
cross and four white dots sits on the card's face, and the card's header has four navy
"spiral-binding" loops each with a small white gap inside. Three different things needed different
treatment (gamepad cross/dots stay opaque; the four spiral-hole gaps go transparent; everything
else white goes transparent) while all of it tumbles together in lockstep.

### Bug 1 (v1): a fixed-position region derived from one frame doesn't hold for other frames
`--analyze`'s `bbox_xyxy`/`suggested_protect_region` are correct for the sampled frames they came
from, but nothing stops using those as a FIXED rectangle applied uniformly across all frames — a
natural move when a region is a bad `--protect-region` fit (non-circular, no verified outline
color; see §2's existing caution, which warns about the wrong GEOMETRY at one position but not
about the position itself being wrong elsewhere). Confirmed real result: visibly destroyed frames
mid-animation — chunks of the gamepad and card cut out — because by the time the tumbling icon
reached other frames, the fixed pixel rectangle now overlapped completely different content.

**Fix:** re-derive any frame-specific region independently, per frame, from intrinsic properties
that don't depend on position — size range, bounding-box aspect ratio, and immediate bordering
color(s) — never from one frame's absolute coordinates.

### Bug 2 (v3): border-touching stops being a safe proxy for "background" once the foreground can graze the edge
A natural definition of "background" is "whatever bg-colored region touches the canvas border"
(flood-fill from the edges) — safe ONLY when the foreground design never itself reaches the canvas
edge. Confirmed real failure: at the peak of the tumble, a genuine corner of the card touched row
639 of the 640px canvas, and border-touch flood-fill correctly identified that as
"border-connected" and swept the ENTIRE connected white shape — 22,169px of real card content, not
background — into "background," deleting it. This is a topology problem, not a color/edge-blend
problem this skill already handles well: a large chunk of real content became graph-connected to
the true background purely by touching the border at one point.

**Fix:** for animated content where the foreground might reach the edge, define background as the
SINGLE LARGEST connected bg-colored component per frame, not "any bg-colored region touching the
border." Confirmed safe specifically because true background is overwhelmingly large relative to
any other same-colored region — verified directly across all 124 frames of the motivating case, the
largest bg-colored component was never less than ~3x the size of the second-largest, even in frames
where a second genuinely large white region (the card's own visible interior, up to ~47,000px)
coexisted with it. **This margin needs re-verifying on any new asset before trusting it** (print the
top 2-3 component sizes per frame) — an asset whose true background is only a thin margin,
comparable in size to its own foreground bg-colored regions, is the case where this heuristic is
the wrong tool.

### Bug 3 (v2, and again after v3's fix): single-frame outline enclosure can fail under self-overlapping/rotating geometry, past what §3's existing anomaly detector catches
§3 above already documents real, hard-won infrastructure for one enclosure-failure mode: a
DIFFERENT animated element briefly crossing and breaking a stable outline's closure (the
"flashing" bug, with local-anomaly + whole-distribution-gap detection, and real history of two
reverted approaches that produced "ghost" artifacts on rotating icons specifically — read that
section in full before touching this area again, it already encodes hard lessons). **This case's
failure was different enough to slip past that existing detector.** Rather than a stable shape
being briefly crossed by something else, the asset's OWN geometry — a card tumbling through
orientations, at times self-overlapping its second layer — made single-frame `binary_fill_holes`
enclosure unreliable in a way that correlated smoothly with rotation progress rather than spiking
as a sharp, isolated anomaly against nearby frames. It silently deleted real card content across a
meaningful span of frames without ever reading as "flashing," and a 40-frame `--analyze` sample
(`enclosure_ratio: 1.0`) did not catch it either, because the specific sampled frames happened to
be fine even though frames in between weren't.

**Fix:** for this failure signature specifically, don't lean on `--protect-outline-color` at all —
bypass single-frame flood-fill enclosure as a concept in favor of bug 2's largest-component
background definition, plus bug 4's mechanism below for anything needing selective removal. **This
does NOT replace §3's existing anomaly detection** — that remains the right tool for its own
documented failure mode (a distinct crossing element). Use this section's approach when the SHAPE
ITSELF is what's moving/rotating/self-overlapping; keep using `--protect-outline-color` (with its
existing anomaly correction) for a stable shape being briefly crossed by something else.

### Bug 4 (v5, discovered fixing an unrelated fringe issue after bugs 1-3 were resolved): allowlist-style feathering protection misses solid near-background design colors
Not specific to animated content — would affect a perfectly static icon too — but found in the
same investigation, one step later. The motivating icon has a flat, deliberate, pale blue-lavender
"shadow" design shape (RGB ~209,220,251). That color's distance from pure white background (~46)
happens to fall INSIDE the default feathering transition band (`tolerance x
feather-band-multiplier` = 15 x 4 = 60) — purely by coincidence, not because it's an antialiasing
blend. Because the protected mask in use at the time was allowlist-style (only the specific
regions already verified as needing protection were marked protected — the page/gamepad interior),
this shadow shape wasn't on the list, so it went through the normal distance-based alpha estimate
and came out with unstable, partial alpha — a visibly speckled/noisy edge where the shape met the
surrounding page.

**Initially, wrongly, suspected to be a Bayer-dithering artifact** — ruled out by testing a hard
50% cutoff with dithering removed entirely; the noise persisted unchanged, which is what correctly
redirected the investigation to the alpha estimate itself rather than the dithering step. Don't
skip that isolation step next time a "noisy/glitchy" report comes in — assuming it's dithering
because dithering is the obvious suspect cost a full round here.

**Fix (v6/v7):** inverted the protected-mask default. Instead of allowlisting specific verified-
safe regions (leaving every OTHER color subject to the raw distance-to-background check), protect
EVERYTHING in the frame except the verified-removable core (background union any identified holes)
and a thin ~4px ring immediately around it. This generically prevents ANY solid design color — not
just this specific pale blue — from being mistaken for an antialiasing blend, with zero per-asset
color tuning needed for the protection step itself. Confirmed: zero isolated speckles across all
124 frames after this change (down from a real, visible pattern before it), and the pale shadow
shape stays fully solid in every frame.

### Bug 5 (found in the same investigation, not its own delivery round): Bayer dithering reads as noise on flat backgrounds
Surfaced while ruling out dithering as bug 4's cause — not the cause there, but a real, separate,
worth-keeping finding. This skill's default feathering resolves partial alpha to GIF's 1-bit alpha
via a spatial Bayer dither pattern, meant to simulate a soft edge — reasonable for content
composited over varied/textured backgrounds. **Confirmed directly: the exact same dithered edge,
composited over a SOLID flat color, reads as visible glitchy noise, not smoothness** — a spatial
dither pattern only looks smooth against content with its own texture to blend into. This matters
beyond the literal green-screen check used here: a flat/solid color is also how the delivered
asset may realistically be placed in the wild (a solid-color chat bubble, a flat app background),
not just a debugging artifact of the verification method.

**Fix:** added a hard-cutoff alternative (50% threshold on the already-defringed alpha) in place of
the Bayer pattern — keeps the color-unmixing benefit from bug 4's fix, trades a very slightly
harder edge silhouette for zero visible noise on any background. Worth defaulting to for small
flat-vector icon/sticker content (this skill's primary target) whenever the final placement context
isn't known to be textured/varied.

### Generalizable takeaways
- A fixed pixel-space region derived from one frame is only valid for that frame — extends §2's
  existing circle/rect-shape-mismatch caution to a new axis (position, not just geometry).
- Border-touching is a safe proxy for "background" only when the foreground provably never reaches
  the canvas edge — verify the size-margin assumption directly (across ALL frames) before relying
  on it, the same way `edge_hardness` gets checked before trusting antialiasing defaults.
- §3's existing flicker-detection infrastructure is built for a DIFFERENT failure signature (a
  stable shape briefly crossed by another element) — it is not guaranteed to catch enclosure
  failure that correlates smoothly with the shape's OWN rotation. Don't assume it covers this case
  just because both produce "content that should be protected went transparent."
- Disambiguating two same-colored, similarly-sized regions (one to remove, one to keep) has no
  universal automatic rule — required manually sampling bordering colors on the real art, the same
  manual-inspection philosophy §2's outline-color fallback already established for a different
  problem. Expect to recalibrate size range, aspect limit, and distinguishing color per asset, not
  reuse fixed numbers.
- When a "noisy/glitchy" artifact is reported, isolate dithering from the alpha computation itself
  before assuming which one is at fault — they produce visually similar speckled results but need
  different fixes, and guessing wrong (as happened here initially) costs a full round.
- Verify against ALL frames for this content type, not a spot-check sample. Every one of the four
  bugs above was localized to specific rotation phases or specific design colors; a first/middle/
  last spot-check (this skill's normal verification habit, sufficient for most content) would not
  reliably have caught any of them.
- Verify against a solid-color composite, not just checkerboard, at least once. Checkerboard
  (already flagged in the Verification section as camouflaging soft bleed) also camouflages
  dithering noise and unstable partial-alpha artifacts — both bugs 4 and 5 above were only clearly
  visible against a solid color.

### What shipped
`--tumble-safe` (largest-connected-component background detection, replacing
`--protect-outline-color`/`--protect-region` for this content type), `--keep-bg-blob-if-near
<hex,...>` (per-frame, color-bordering-based hole disambiguation, gated by `--hole-size-range`/
`--hole-max-aspect`), `--protect-band-only <px>` (invert-by-default protection), and
`--dither-mode {bayer,none}`. All four are additive/opt-in — default behavior for non-tumbling
content is unchanged, confirmed via a byte-identical `--analyze` diff against the pre-change script
on the same test file. See SKILL.md's "Animated/rotating content" section for the lean actionable
rule and decision summary.

## 11. Small removed regions get inflated by edge-cleanup erosion: a second animated-icon case, five rounds
SKILL.md's rule: any time a fix removes a small, isolated bg-colored region, route the final
erosion pass through `--erosion-exempt-max-size` instead of letting it hit normal
`--edge-cleanup-erosion`. This section is the evidence trail — a different asset from §10's
tumbling calendar, a different failure mechanism, five rounds (open-book-gear-transparent.gif
through -v5.gif) to fully resolve.

**The real case:** a 640x640, 50-frame open-book-with-gear icon. An orange gear (rotating and
bouncing vertically) sits above an open book whose pages are enclosed white, verified by
`--protect-outline-color` across all 50 frames with zero enclosure failures (unlike §10's case,
this asset's outline enclosure was completely reliable — a useful reminder that §10's failure mode
is real but not universal, and checking is still worth doing even when it turns out fine). The
gear's rotation/bounce means it transiently grazes the book's top-edge outline at certain frames,
pinching off tiny gaps of true background between the gear's teeth and the book's curve — nothing
to do with §10's tumble/rotation bugs, and this asset didn't need `--tumble-safe` at all.

### Round 1 (v1, baseline `--protect-outline-color` delivery): visible white gaps at the gear/book boundary
User-reported (not internally discovered): two frames had a clearly visible white gap where the
gear's teeth met the book's page-top curve — 69px and 137px respectively, large enough to read as
an obvious defect. `--protect-outline-color` correctly (by its own logic) treated these as enclosed
white and protected them, since they genuinely are bordered by navy on both the gear and book side.
The defect is about design intent, not about the mechanism working incorrectly.

### Round 2 (v2): blanket small-size removal broke unrelated content elsewhere in the frame
Fix: any enclosed white component under 800px (comfortably below the smallest legitimate protected
region, the gear's ~2252px center circle, confirmed by scanning size across all 50 frames) was
treated as removable. This over-generalized: the book's pages have wavy purple/blue decorative
lines, and where two nearby line-strokes' antialiasing curves happen to nearly touch, they can pinch
off their own tiny (1-5px) incidental background pocket — completely unrelated to the gear, just an
artifact of the line art's own geometry. The blanket rule removed these too, producing scattered
1-5px transparent "particles" inside the book pages in frames far from the gear (measured y≈352-357,
vs. the real gear-boundary notches at y≈228-317 — a clean ~35px separation once actually measured).

**Fix:** added a position constraint (y-center < 340) so only small enclosed regions actually near
the gear are eligible for removal. Verified: page-interior specks now stay opaque, real gear-notches
still transparent.

### Round 3 (v3, confirmed independently by the user re-testing the delivered file, not a self-caught bug): erosion inflated the smallest notches into visible "speckles"
This is the same content-independent mechanism documented as its own general lesson above/in
SKILL.md's "Small removed regions can be inflated by edge-cleanup erosion" section — restated here
briefly since it's the specific case that surfaced it. Several of the gear-boundary notches were
themselves tiny (1-11px) before any cleanup, since the exact overlap between the gear's teeth and
the book's curve varies continuously with the gear's rotation/bounce phase, and most frames only
produce a marginal, barely-there gap. The standard 2px `--edge-cleanup-erosion` pass, applied
uniformly with no regard for how small the removed region on the other side of a boundary is,
inflated a confirmed real 1px removed pixel (frame 6) into a 49-70px hole — a 50-70x size increase,
turning an imperceptible rendering quirk into a visibly distracting speckle. **The user caught this
on their own re-check of the delivered file** (not something the standard verification checklist —
full-frame structural checks, solid-color composite — flagged, because those checks confirm
correctness of WHAT got removed, not whether an already-correct removal got inflated afterward by a
later pipeline stage). Worth internalizing: passing every structural check doesn't rule out a bug
introduced by a downstream step those checks don't specifically probe.

### Round 4 (v4): raising the size floor traded one visible defect for its mirror image
First attempt at a fix: require a candidate notch to be at least 30px (comfortably above the 1-11px
noise range, comfortably below the two real 69px/137px gaps) before it's even considered removable.
This stopped the erosion inflation (nothing under 30px was touched at all), but the sub-30px slivers
now stayed fully opaque white instead — visible as small white specks at exactly the points (gear
teeth nearly touching the book outline) a person looks most closely at. **The user caught this too,
on the very next re-check**, correctly identifying it as a new, different artifact from round 3's
(transparent specks vs. opaque specks) rather than assuming it was the same bug recurring.

### Round 5 (v5): exclude tiny regions from erosion's INPUT, not just its size threshold
The actual fix, and the one that shipped: rather than choosing between "remove and let it erode" and
"don't remove at all," exclude any tiny (<30px) removable region from the erosion computation
entirely — mark it as if it were fully opaque/protected for that computation only, so erosion
produces exactly the result it would have if the tiny region had never been flagged as removable in
the first place (identical to how the surrounding area is normally, correctly treated) — then punch
each tiny region back to transparent at its own exact pre-erosion pixels afterward. An intermediate
attempt (dilate each tiny region by the erosion radius and restore whatever erosion reclaimed there,
provided it wasn't also near a legitimately large removed region) was tried first and was measurably
incomplete — a 1px notch still came out ~40-50px post-restore — because erosion's real spillover
pattern around a small feature isn't a clean, independent ring, especially with other nearby geometry
(a second small feature close by, a corner, another edge) also contributing to the same local erosion
result. Excluding the region from erosion's input is exact by construction; trying to undo erosion's
output after the fact is not.

### Generalizable takeaways
- A blanket size-based removal rule needs a second, independent constraint (position, color,
  whatever the asset actually offers) the moment there's more than one source of small
  same-colored enclosed regions in the frame — extends §10's bug-1 lesson (position-independent
  per-frame re-derivation) with a concrete case of getting the DISAMBIGUATION signal itself wrong on
  the first attempt, not just the removal mechanism.
- Passing the standard verification checklist (full-frame structural checks, solid-color composite)
  does not rule out a bug introduced by a LATER pipeline stage (here, erosion) that those checks
  don't specifically probe. The checks confirm the removal decision was right; they don't by
  themselves confirm nothing downstream altered its size.
- When a person reports "still broken" after a fix, don't assume it's the same bug persisting —
  round 4's opaque-speck complaint was a genuinely different defect from round 3's transparent-speck
  complaint, caused by the fix itself, not a failure of the fix to apply. Confirm which failure mode
  is actually present (in this case: check the actual pixel/component sizes) before re-diagnosing.
- Undoing a global transformation's effect on a small region, after the fact, by trying to identify
  and reverse just its local spillover, is fragile the moment other nearby geometry is also
  contributing to the same local result. Excluding the region from the transformation's input
  entirely is exact; patching its output is not — worth defaulting to the former whenever the
  transformation (here, erosion) supports being scoped that way.
- A file mismatch (someone re-testing an old delivered version, not the latest one) is a real,
  mundane possibility worth checking for directly (file hash, filename in what they show you)
  BEFORE assuming a fix didn't work — but confirmed here it isn't always the explanation: round 3 and
  4's reports were both against the actual current file and were both real, distinct bugs. Check,
  don't assume either way.

### What shipped
`find_tiny_removed_regions` + `erode_alpha_edge_exempting_tiny_regions`, wired to a new
`--erosion-exempt-max-size <px>` flag. Confirmed the fully-automated version (no manual pre-
classification, just feeding it the complete removable-region alpha and letting it auto-detect
anything at or below the given size) reproduces the same result as the manually-verified fix.
Additive/opt-in, default off — confirmed the existing default codepath is unaffected.

---

## 12. Art that fades toward the background colour renders as a dither mesh

**⚠️ Superseded for non-GIF deliverables by §16 (2026-08-17).** Everything below is still the right
answer *if the output must be a GIF*. If it can be WebP or AVIF, `--recover-fade-alpha` reconstructs
the original alpha exactly instead of cutting the faintest stages, and the fade renders as real
translucency. Read §16 first; treat `--dither-mode none` as the GIF fallback, not the default answer.

**Found 2026-08-07** on `ruby.gif`, a 109-frame 640x640 gem icon with yellow four-pointed
sparkles. Reported by Harkirat directly, from the delivered file, against a dark backdrop.

### The symptom
Most sparkles came out solid yellow, but some rendered as a **visible grid/mesh** — a regular
crosshatch of transparent pixels through the sparkle body — instead of solid colour. The gem
itself, the sparkle outlines, and the deliberately-removed white sparkle cores were all correct.

### Why this is NOT §10's Bug 5, despite both ending at `--dither-mode none`
§10's Bug 5 is about a **correct edge** being *composited* onto a flat colour, where the Bayer
pattern that reads as soft antialiasing over texture reads as speckle over flat paint. The trigger
is the *viewing background*, and the affected pixels are a thin edge band.

This is different in trigger, location, and cause: **the source art has a fade baked into it.**
GIF has no partial alpha (§7), so the artist's fade-out was flattened against white at authoring
time — the sparkle literally *is* progressively lighter cream in later frames. Measured on the
real file: at peak the sparkle is `fdcb50`; mid-fade its body is a solid `fff2d1`, Euclidean
distance **47.8** from white. The default band is `--tolerance 15` to `15 x 4.0 = 60`, so that
solid body colour lands **inside the feather band**, gets assigned alpha ~0.73, and is dithered.
The affected pixels are the sparkle's whole **interior**, not an edge, and they mesh no matter
what you composite over.

So the alpha was arguably *right* — a 73%-transparent sparkle is a faithful rendering of a fade
that no longer has an alpha channel to live in. It just looks wrong, because a spatial dither
across a solid interior region reads as a mesh rather than as translucency.

### The fix, and what it costs
`--dither-mode none` — hard 50% cutoff on the already-defringed alpha. Measured before/after on
the frames that showed it:

| source frame | faded body | opaque with Bayer (v1) | opaque with `none` (v2) |
|---|---|---|---|
| 68 | 803px | 651px (81%) | 762px (95%) |
| 97 | 2966px | 1393px (47%) | **2805px (95%)** |
| 103 | 2962px | 2016px (68%) | **2845px (96%)** |

The two faintest frames (61, 67) go to 0% opaque in both — below the 50% cutoff the sparkle simply
disappears a beat earlier instead of meshing, which is the correct trade.

**Check the cost before reaching for it: `--dither-mode none` changes EVERY edge in the file, not
just the offending region.** It was nearly free here because ruby's silhouette is mostly straight
lines (`edge_hardness` ratio 0.506) — verified by zooming the outer navy silhouette in both
versions and finding no new jaggedness, and by confirming 0 near-white fringe pixels in the
outermost opaque ring. On a curve-heavy icon that trade would be worse, and narrowing
`--feather-band-multiplier` would be worth measuring first.

### Generalizable takeaway
**A "solid" colour is only solid relative to the background you're keying against.** Before
trusting the feather band, check whether any *large interior* region of the art sits inside it —
`tolerance` to `tolerance x feather-band-multiplier` in Euclidean RGB distance. Feathering is
designed for thin edge transitions; a wide interior region inside that band is the signature of a
baked-in fade (or a pale design tint, which is §10 Bug 4's `--protect-band-only` case), and both
want handling other than "let it dither."

---

## 13. The save message asserted a frame count it never read back

**Found 2026-08-07** while verifying `jewelry.gif` (170 frames) — caught by the verification step,
not by the script.

### What happened
The script printed `Saved <path> (170 frames, durations preserved exactly)`. The written file has
**168**. The line was `print(f"... ({len(durations)} frames, durations preserved exactly)")` — it
restated the frame list the script *intended* to write and asserted a property of a file it had
never opened.

### Why the file legitimately has fewer frames
Pillow's GIF encoder coalesces consecutive frames that come out **byte-identical after
quantization**, folding their delays into the survivor. Source frames 166–168 differ by at most
**9 RGB levels on at most 91 of 409,600 pixels** — the animation has settled into its resting pose
and the residual difference is encoder noise. After palette quantization they are the same frame.
Total playback was **3600ms before and after**.

**So the coalescing is not a defect and is not worth suppressing.** The dropped frames were
visually identical; refusing the merge would only make the file bigger. The defect was purely the
claim.

### The fix
`describe_written_timing(output_path, intended_durations)` re-opens the written file, reads its
actual per-frame durations, and reports what is actually true:
- identical to intended → `"N frames, durations preserved exactly"` (unchanged wording, now earned)
- fewer frames, same total → `"N frames written from M intended -- K identical frame(s) coalesced
  by the encoder, total playback unchanged at Xms"`
- **total playback changed** → an explicit `WARNING:` to stderr, because that *would* be a real
  timing defect rather than encoder coalescing
- readback itself fails → says so, and never fails a job that already wrote its output

Verified on two synthetic files that isolate the branches: one whose middle frames drift ≤2 RGB
levels (reports `4 frames written from 5 intended -- 1 identical frame(s) coalesced ... unchanged
at 200ms`) and a control with clearly distinct frames (reports `5 frames, durations preserved
exactly`). The old code printed the identical "preserved exactly" line for both.

### Generalizable takeaway
**Verification step 3 in SKILL.md tells the reader to compare input and output durations by reading
the real file — but the script's own success message was doing exactly what that rule forbids.** A
tool that reports on its own output must read that output back; restating the input is not a check,
it's a claim wearing a check's clothing, and it is more dangerous than no message at all because it
actively discourages looking. Worth grepping for the same shape anywhere else a message asserts a
property of a written file.

---

## 14. Punching one same-colour interior hole while protecting a same-colour, same-size-range animated design element

**Found 2026-08-07** on `military-tag.gif` (126-frame dog-tag icon), delivered by a user who had
already gotten 4 incorrect/ugly attempts from a live claude.ai v3.1.0 session on the same file.

### The symptom
The tag has a pure-white 4-point star (a real design element, must stay opaque) and a small round
pinhole where the ball-chain threads through (must become transparent) — both near-white, both
enclosed by the tag's navy outline, both non-border-touching. `--recommend`'s own suggested
`--protect-outline-color 002864` reported the region's `outline_enclosure_all_frames` at only
**47% enclosed across all 126 frames** (own evidence text: *"outline 002864 verified across 126
frames (47% enclosed)"*) — a real, honest signal that this asset's outline color isn't reliably
enclosing, not something to trust blindly. Root cause: the star **twinkles** (its rendered shape
changes size/aspect every frame, from ~75px to ~6000px across the sample), so a single fixed-frame
`comp_footprint` containment check misses most frames.

### First attempt: `--tumble-safe` (sidesteps outline reliability) + `--keep-bg-blob-if-near` with a decoy colour
`--tumble-safe`'s default (protect everything except the single largest bg-colored component, computed
fresh per frame) sidesteps the outline-reliability problem entirely — correct call, confirmed by full
127-frame verification later. But `--keep-bg-blob-if-near 000000` (a colour picked to match nothing,
intending "hole-size-range alone decides") punched holes through the star's own antialiased boundary
in the frames where the twinkle happens to fragment it into pieces inside the default
`--hole-size-range 50,2000` — visible in a `--preview` contact sheet as a jagged bite out of the star
(looked like solid dark fill only because it was composited over a dark preview background; it was
actually alpha=0, confirmed by checking the raw alpha array directly rather than trusting the visual).

### Second attempt: real design colours as the keep-target — also wrong, in the other direction
Passing the tag's own body/sheen colours (`93b2f4,d1dbfc`) as `--keep-bg-blob-if-near` stopped the
star damage, but now punched **zero** holes in **all 126 frames** — the pinhole itself got kept.
Traced with the real `build_tumble_safe_protected_mask` function directly (not re-derived by hand):
the pinhole's antialiased boundary (white → navy) passes, for a handful of pixels, within
`near_tolerance`(40) of `d1dbfc` purely by coincidence (measured min distance 19.5) — and the match
is an `.any()` over the whole dilated ring, so one coincidental pixel flips the entire component's
verdict. More dilation doesn't fix this: the boundary pixels closest to the shape are included at
every dilation radius once they first appear.

### The fix: separate the two by geometry, not colour
Measured the pinhole's real per-frame size/aspect across all 126 frames: **423–466px, aspect
1.00–1.04 — a near-perfect circle, essentially constant**, because the physical hole doesn't change
even though the tag translates and swings. The twinkling star's fragments, sampled the same way,
range 75–6070px, aspect 1.0–2.69, and only ever coincidentally overlap the pinhole's size band
without also matching its aspect. `--hole-size-range 400,480 --hole-max-aspect 1.3` (still paired
with a `--keep-bg-blob-if-near` decoy colour, required only because the code path is gated on that
flag being present) admits **exactly one component per frame across all 126**, and it's the pinhole
every time — confirmed by brute-force scanning every frame, not sampling.

### Verification note: `--verify`'s `protected_region_coverage` false-positives here
`--verify` correctly skipped its pixel checks given `--crop` changed the canvas size (its own
documented behavior), so verification ran against an uncropped intermediate. On that,
`leftover_background_opaque_px`, `edge_fringe_check`, `small_region_inflation`, and `timing` all came
back clean — but `protected_region_coverage` flagged the merged star+pinhole candidate region as
`looks_unprotected: true` (46.2% opacity). Confirmed as a false positive by two independent, more
precise checks: (1) restricting the same opacity measurement to each frame's own correctly-identified
star component (excluding the pinhole) still isn't clean-looking from the bbox math, but (2) directly
checking "is every star-component pixel opaque, per frame, using that frame's own true star mask" —
the unambiguous test — came back **100% opaque in all 126 frames, zero exceptions**. The false
positive traces to the same root cause as `outline_enclosure_all_frames`'s low ratio and the known
`band_interior_regions` grouping gap (see `gif-deferred-list.md`): `analyze()`'s candidate-region
detection ties a region to one fixed-frame bbox/footprint, which a translating design with a legitimate
interior sub-hole breaks. Not fixed here (would need `verify()` to know about deliberately-carved
sub-holes, which it currently cannot express) — noted as a real, novel gap for the deferred list rather
than left silently unmentioned.

### Generalizable takeaway
**When a "keep vs. remove" distinction is needed between two same-colour blobs, ask which axis
actually separates them before reaching for `--keep-bg-blob-if-near`'s colour-adjacency mechanism.**
Colour-adjacency is fragile across an antialiased boundary — a coincidental match on a handful of
transition pixels is enough to flip an entire component, in either direction, and more dilation does
not fix a coincidental match found at low dilation. If one blob is physically constant (a real cutout)
and the other is animated (breathing/twinkling/pulsing), size+aspect over the FULL frame range is
usually the more robust discriminator — verify it by scanning every frame's actual measured values,
never a handful of samples, since the whole failure mode here is an animated element occasionally
drifting into the other's range.

### Addendum, same asset, found by the user zooming into the delivered file: `--erosion-exempt-max-size` left a whitish fringe around the punched hole
Passed `--erosion-exempt-max-size 519` on `--recommend`'s generic evidence ("152 small removed
region(s) observed") without checking whether that number meant genuine incidental noise on THIS
asset. It didn't: every one of those 152 detections across all 126 frames was either the pinhole
itself (repeated once per frame) or a star-twinkle fragment that never actually enters this
pipeline's removable set (confirmed: only the pinhole ever passes the `--hole-size-range`/
`--hole-max-aspect` gate). So the exemption had nothing genuine to protect — but it still did its
job of restoring the pinhole to its exact PRE-erosion pixels, which skipped the normal
`--edge-cleanup-erosion` pass that would have cleaned up the antialiasing blend between the white
pinhole and the navy ring. Result: a handful of pale, technically-opaque, off-white pixels
(measured `237,241,253` — not pure white, not navy, an untrimmed antialiasing blend) sitting right
at the hole's edge, small enough to miss in a `--preview` contact sheet composited over
transparency-checkerboard but visible zoomed in over a solid dark background.

**The fix:** drop `--erosion-exempt-max-size` entirely and let the default 2px erosion run
normally. Re-verified across all 126 frames: fringe pixels went to zero, the hole's own true size
grew modestly (~423–466px raw → ~632–682px post-erosion, roughly a 20% radius increase) because
the navy ring is thick (15+px) relative to the 2px erosion radius — nowhere near the 50–70x
runaway inflation §11 exists to prevent, which only happens when the wall around a removed region
is thin relative to the erosion radius. `small_region_inflation` (from `--verify`) correctly did
not flag this growth.

**Generalizable takeaway:** `--erosion-exempt-max-size`'s own evidence count from `--recommend`
(or `--analyze`'s `small_removed_regions`) is a raw histogram of ANY small removable-by-color blob
across every frame — it does not know which of those blobs actually survive into your SPECIFIC
chosen protection pipeline as truly removable. Before applying the flag, check whether the asset
actually has incidental noise distinct from its main removed-region logic (as §11's original
gear/book case did) or whether, as here, the "152 regions" are just one legitimate, physically
constant hole detected 126 times — in the latter case the exemption trades a real fringe defect for
protection against an inflation risk that was never actually present.

---

## 15. A second, independent solution to §14's same problem — `--remove-region`, and where it needs help

**Found 2026-08-07**, same asset as §14 (`military-tag.gif`), from a parallel claude.ai live-skill
session working the identical problem (star to keep, pin hole to remove, both enclosed by the same
navy outline) with no knowledge of §14's approach. Reconciled into the repo 2026-08-08. Kept as its
own section rather than merged into §14 because the two solutions are genuinely different in shape,
not just different phrasing of the same fix — read both before picking one for a new case.

### The approach: `--protect-outline-color` (as normal) + a new inverse flag to carve the hole back out
Unlike §14 (which avoided `--protect-outline-color` entirely because its all-frame enclosure ratio
measured only 47%), this session used `--protect-outline-color 002864` as normal — correct
per-region framing either way, since it protects the whole navy-enclosed interior including the
star — then added **`--remove-region`** (new flag, inverse of `--protect-region`: force-removes a
manually specified region regardless of what protection already decided there) to punch the pin
hole back out. The underlying insight, precisely: **"enclosed by the same outline color" is not the
same claim as "the same region should get the same treatment."** `--protect-outline-color` correctly
unions the whole enclosed area for one color; there was previously no way to say "protect this
EXCEPT that sub-region."

**A real bug found and fixed in the same session, general beyond this one flag:** the first
hand-rolled hole-punch (before `--remove-region` existed) zeroed alpha inside a circle without
touching RGB, leaving the original antialiased white-into-navy blend color sitting at partial alpha
— invisible over checkerboard, a visible pale halo over any solid composite. `apply_remove_regions()`
fixes this generically: recolor every touched pixel to the LOCAL kept color (sampled fresh per frame
from a thin ring just outside the removal mask, not a hardcoded hex) BEFORE tapering alpha down, so
a fading pixel always reads as "surrounding color fading to transparent," never a ghost of what got
removed. **This is a different root cause than §14's addendum fringe**, worth keeping distinct: §14's
fringe came from `--erosion-exempt-max-size` skipping an EXISTING cleanup step (the main feathering
path already defringes correctly); this one is about a hand-rolled alpha edit that bypassed the main
feathering path entirely and so never got defringed in the first place. Both LOOK like "a whitish
ring around a punched hole" — they are not the same bug, and the fix for one would not have fixed
the other.

### Where it needs help: this flag alone did not solve this specific asset — confirmed independently, not just taken on faith
`--remove-region`'s own worked example (`--protect-outline-color 002864 --remove-region
circle:283.5,231.5,15`) is a STATIC mask, same limitation `--protect-region` already has. This
asset's pin hole is not static: **re-measured independently while reconciling this drop into the
repo — the true hole center drifts up to ~67px from that fixed circle across the 126 frames** (the
live session's own account cites ~150px, plausibly measured at a different scale/crop; both
readings agree the drift is large, not marginal). Directly checking the STATIC-circle output against
the real per-frame hole location: **96 of 126 frames (76%) do NOT actually have the true pin hole
punched** — the fixed circle is simply removing the wrong patch of navy ring in most frames. The
flag's own documentation is honest about this ("do not use this for a target that moves/resizes
across frames... without re-deriving the mask per frame yourself first") — this is a confirmation
that the caveat is load-bearing on this exact asset, not a defect in the flag or its docs.

The live session's real fix for this (§ their Bug 3/4, condensed): track the hole's true per-frame
center via `cv2.HoughCircles` on each source frame independently, and — after finding that a
per-frame RE-MEASURED radius was itself corrupted by a shine/sparkle sweep passing through the same
screen area in some frames (a real second bug, a differently-principled edge/gradient-based method
disagreeing with a color-threshold radial scan is what caught it) — settle on ONE constant radius
measured only from unaffected frames, applied to every frame's own tracked center. None of this
tracking happens inside the script; it is bespoke, external, per-asset work.

**§14's `--tumble-safe` + `--keep-bg-blob-if-near` + tight `--hole-size-range`/`--hole-max-aspect`
approach handles this exact drift natively, with no external tracking script**, because it
re-derives the hole's mask fresh from each frame's own connected-component geometry rather than
applying one fixed region — the drift was never a problem for it, verified in §14 across all 126
frames without needing to know the drift's magnitude in advance.

### Generalizable takeaway: two valid tools for the same *shape* of problem, different fits
- **`--remove-region` is the more general, more directly-expressive fix** when the target to punch
  out is static, or as a component after you've separately solved per-frame tracking yourself — it
  works regardless of whether the hole is geometrically distinguishable from nearby decoration
  (§14's approach specifically needed the hole and the decoration to differ in measurable
  size/aspect across every frame, which was true here somewhat fortuitously, not guaranteed on a
  future asset).
- **§14's geometric-gate approach is the more robust fix for a moving/resizing target with no
  external tooling**, but only when the thing to remove and the thing to keep really are separable
  by a stable, measurable geometric signal (size, aspect, or similar) across the whole animation —
  verify that separation across every frame before trusting it, same discipline §14 itself used.
- **Neither is a substitute for the other in every case.** A static hole shared with animated
  same-colored decoration wants `--remove-region`. A moving hole with no reliable external tracking
  step wants the geometric-gate approach. A moving hole where NEITHER geometric separation nor
  tracking tooling is available is a real gap this skill does not yet close.


## 16. Escaping GIF's 1-bit alpha: recovering a baked-in fade, and WebP/AVIF output

Real job, 2026-08-17: `love.gif`, 640×640, 124 frames, a gamepad-in-a-heart sticker with yellow
pulses that expand outward from the heart's outline while fading out. The ask was to remove the
white background while keeping the white controller buttons — and, because the requester had
already worked out that GIF cannot express a fade against transparency, to deliver WebP instead.
That prediction was correct, and provably so.

### The fade was flat-opacity on one solid colour — so it is EXACTLY recoverable
Measured before choosing any approach: each pulse frame carries ~30,000 pixels at a *single*
blend fraction of pure `#fdcb50`, and across the animation those fractions are
**1.0 → 0.8 → 0.6 → 0.4 → 0.2**. Not a gradient, not a blur — a global opacity ramp that the GIF
export flattened against white. Since `px = a·C + (1−a)·W` with `C` and `W` both known, `a` is
arithmetic, not estimation.

**The falsifier that made this trustworthy:** frame 0 has no pulse. If the classifier were sloppy
it would report phantom yellow there. It returned **zero** pixels. Any "detector" for this should
be checked against a frame where the answer is known to be nothing — a detector that cannot fail
has not been tested.

### Why NO GIF setting can represent it
Yellow sits 182.6 (Euclidean RGB) from white. The feather band is `--tolerance`(15) →
`× --feather-band-multiplier`(4) = 15…60.

| Fade stage | Distance from white | What GIF did |
|---|---|---|
| α 0.2 | 36.5 | inside band → dithered, then erosion ate it (**99% destroyed**) |
| α 0.4 | 73 | above band → **opaque pale cream** |
| α 0.6 | 110 | above band → **opaque pale cream** |
| α 0.8 | 146 | above band → **opaque pale cream** |
| α 1.0 | 182.6 | opaque yellow — correct |

**And it cannot be tuned around.** Widening the band to catch α 0.8 means reaching past 146 — but
a real solid art colour, the lavender controller body, sits at **121.7**. Any band wide enough to
catch the fade dissolves genuine artwork. The fade's range *straddles* an art colour, so no single
distance threshold separates them. That is the structural argument; it generalises to any asset
where a fading element passes through the colour-distance of a solid one.

A second, uglier symptom appeared at the faintest stage: dithering α 0.2 produced a sparse Bayer
pattern, the 2px erosion then removed 99% of it, and the survivors were left stranded as isolated
**speckle dots** scattered where the pulse should have faded to nothing. `--verify` flagged this as
`small_region_inflation` (a 9px input region → 638px out, 70×).

### The fix: unmix against the art's own palette, not against a distance threshold
`--recover-fade-alpha` asks a different question per pixel: *is this explained as the background
blended with ONE known art colour?* That separates cleanly where a distance threshold cannot —
measured on frame 36, yellow came back 99.2% partial-alpha while every other palette colour was
~99% fully opaque.

**⚠️ The palette build order is load-bearing, and getting it wrong silently reproduces the bug.**
A fading element's intermediate stages cover tens of thousands of pixels per frame, so they rank as
*dominant colours* and get admitted as solid palette entries of their own (`#feeab9`, `#fee096`,
`#fdd573` all appeared alongside the true `#fdcb50`). Every faded pixel then unmixes against its own
stage at α≈1.0 and renders **fully opaque** — the exact GIF artifact, now inside a format that
didn't need to have it. Fix: consider candidates **furthest from the background first** (a fade
stage is always nearer the background than the colour it fades from), and reject any candidate
already explained as a blend of the background and an accepted colour.

Two further guards, both from real failures during this build:
- **Fade detection must scan every frame.** Sampling every 10th frame for speed silently stopped
  detecting the fade and produced a plausible-but-wrong file. That is §10's own "verify against
  every frame, not a spot-check sample" rule reasserting itself. Unmixing is ~50ms/frame; a full
  scan is affordable and a sample is not worth the failure mode.
- **A palette-coverage guard is mandatory, because the failure is silent.** On gradient or
  photographic content every pixel becomes a residual case, gets forced opaque, and the run
  *reports success having recovered nothing*. The script now warns below 90% coverage (this asset:
  98.7%).

### Format findings (all measured on this asset, 640×640 / 124 frames unless noted)

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

- **WebP lossy is pointless at native resolution** — q85 (2675 KB) and q95 (3617 KB) are both
  *bigger* than lossless (2114 KB), because lossy injects noise into large flat regions and that
  defeats inter-frame prediction. **But the ordering REVERSES once downscaled**: at 128×128,
  lossless was 1190 KB against lossy q80's 650 KB. Neither claim is general — the crossover is what
  matters.
- **AVIF `quality=100` is a trap**: not lossless (max RGB delta 145) *and* the largest file of all.
- **AVIF fits ~3× the frames under a hard cap.** Discord's 256 KB emoji limit: AVIF held all 124
  frames at 128×128 in **244 KB at q70** (q85 was 357 KB and did *not* fit); WebP had to drop to
  42 frames to fit at all. Confirmed live by the
  requester that Discord accepts *and animates* AVIF emoji.
- **AVIF's alpha "error" is not where the max-delta suggests.** Despite ±31–50 maxima, every fade
  stage reproduced with median alpha exactly right (255/204/152/102/50); on the faintest stage the
  mean error was 0.81/255 (1.6% relative) at q85. The outliers sit on hard edges, not in the fade
  body. Worth measuring per-feature rather than trusting a global max.
- **`-m 6` is never worth it, but `-m 0` is content-dependent.** Here `-m 6` cost 415s against
  `-m 4`'s 9.2s (**45×**) to save 2.3%; `-m 0` was 8.5× faster but **+134%** size. Dior's Builds
  measured the same knob on gradient-bed nameplate frames and got `-m 0` at only **+14%** (and
  `-m 6` *worse on both axes*). Same flag, opposite verdicts — **measure `-m` per asset class; only
  "avoid `-m 6`" transfers.**

### Two footguns that make a wrong result look like a passing one
- **Pillow returns duration 0 for every frame when READING an animated WebP.** A naive timing check
  therefore passes vacuously against a file whose timing is actually broken. Read the container
  instead (`webpmux -info`); `read_webp_durations()` does this and returns `None` rather than
  guessing when webpmux is absent. Same class as §9's Pillow-duration issue, different format.
  For the same reason `--verify` now **refuses** a non-GIF output rather than reporting a pass it
  cannot substantiate.
- **Resizing destroyed the recovered alpha, and the result looked *better* for it.** `resize_rgba_
  frames` re-binarized alpha (`a > 127`) and resized RGB without premultiplying. A 128px emoji came
  back with **14 distinct alpha levels, 99.4% fully binary** — the fade silently gone — and the file
  was a pleasingly small 97 KB *because* the pulses had been deleted. Caught only by testing
  end-to-end and counting alpha levels. 8-bit-alpha output now premultiplies before resampling,
  unpremultiplies after, and skips the post-resize erosion (which exists to trim 1-bit-cutoff fuzz
  that no longer occurs). **A smaller-than-expected file is a symptom to investigate, not a win.**

### `--recommend` gave three suggestions on this asset and two were wrong
1. **`--pixel-art`** — `edge_hardness` 0.425 reads "hard-edged", but zooming 8× showed a real 1–2px
   antialiasing ramp. This is exactly §1's caveat (a clean vector export with a thin AA band scores
   low); `--pixel-art` would have disabled feathering and erosion on curve-heavy art.
2. **`--erosion-exempt-max-size 487`** — the "1070 small removed regions" **were the controller
   buttons**, i.e. the very design the user asked to preserve. The ≤500px ceiling exists to keep
   protected regions out of this measurement but assumes design regions are *large*; four ~287px
   dots sailed under it. Applying the flag to real design skips normal edge cleanup and leaves a
   fringe — the v3.3.3 regression, recurring with a new signature.
   **Fix shipped:** classify by **persistence**, not size (per §14's logic — design is physically
   constant, incidental gaps are transient). A region present in ≥90% of frames is treated as design
   and excluded from the suggestion. ⚠️ Fixed-width bins were tried first and are *measurably wrong*:
   the buttons measure 286–306px and straddle a 25px bin edge, scoring 47.6% and 83.9% so that
   neither half cleared the threshold despite being present in every frame. Cluster by **relative
   tolerance** (±15%) instead.
3. `--protect-outline-color 002864` — correct, verified across all 124 frames.

### Check whether your input is already a degraded proxy
The requester also had `love.mp4`. It was tested rather than assumed, and it is the **worse**
source: 512×512 (vs the GIF's 640×640) and, decisively, H.264 ringing plus 4:2:0 chroma subsampling
scatter the fade off its flat levels (IQR 0.04–0.13, peak-bin fraction 0.23–0.80) where the GIF puts
~30,000 pixels at one exact value. A flat 256-colour GIF can be a *better* recovery source than a
24-bit video.

But ask the question anyway, early: this whole pipeline is archaeology on a flattened artifact, and
if an original with real alpha exists (After Effects / Lottie / Rive / SVG), exporting from it beats
any recovery. Dior's Builds' nameplate work is the cautionary version — a session concluded an asset
"genuinely has no alpha channel" when the alpha was there all along and ffmpeg's *default decoder
choice* was discarding it (`-c:v libvpx-vp9` recovered 234 distinct alpha values). **A tool's
default reading of an asset is not the asset.**

### Validated across a 5-asset corpus, not just the motivating file
Run 2026-08-17 against four further real emoji (`heart`, `gift`, `explosion`, `crystal`) chosen to
attack specific assumptions. **Two predicted failures did not occur**, which is worth recording as
honestly as a failure would be:

| Asset | Probe | Result |
|---|---|---|
| `heart` | replication of a fading pulse | fade found (`#384998`), coverage 99.2% — method is not overfit |
| `gift` | many *small* sparkles vs `min_px=2000` tuned on a 30,000px ring | **prediction wrong** — fade found, coverage 99.3% |
| `explosion` | tumbling motion (§10's failure class) | correctly found **no** fade; no fixed-region artifacts — supports position-independence |
| `crystal` | art colours very close to the background | **prediction wrong** — near-white crystals stayed opaque, coverage 99.7% |

**But `crystal` exposed a real latent fragility.** Its `#d2dcfd` (distance 57 from white, 261k px)
is a *solid art colour* that the palette builder REJECTS as a blend-impostor, because it is
genuinely explained as 43% `#93b2f4` over white (residual 3.6). It survived only because it sits
**interior**, where topological protection keeps it opaque. **A near-background solid colour that
appears at the silhouette edge would be unmixed to partial alpha and go semi-transparent.** The
impostor-rejection rule that fixes the fade-stage bug creates this one; they are the same mechanism
pointed in opposite directions.

**⚠️ This WAS hit, on `crystal` itself — an earlier draft of this section claimed "not hit on any
corpus asset" and was wrong.** A single-frame spot-check sampled a frame where that colour happened
to sit interior; compositing the whole animation over a checkerboard exposed it immediately.
Measured: **1,092,411 solid-source pixels across 130 frames rendered at alpha ~109/255 instead of
255** — the background visibly showing through the artwork. *Lesson within the lesson: a
single-frame spot-check is not a test for a defect that depends on position. Composite every frame
over a checkerboard AND a flat colour before believing an asset is clean.*

**Fix shipped — a two-pass palette.** The discriminator is the PARENT: a fade stage's parent is a
fading colour, a solid tint's parent is not. Pass 1 rejects every background-blend candidate (that
is what makes the fading colours findable at all); pass 2 rebuilds the palette KEEPING solid
near-background tints, rejecting only blends whose parent is a detected fading colour. Result:
1,092,411 → 0 wrongly-translucent solid pixels, with love.gif's fade ramp and frame-0 falsifier
unchanged.

**Format conclusions, now measured on 5 assets rather than 1:**

| Asset | Frames | WebP m2 | WebP m4 | m2 time | m4 time | AVIF q85 | q85 as % of m4 |
|---|---|---|---|---|---|---|---|
| love | 124 | 2163 KB | 2114 KB | 11.3s | 22.6s | 1331 KB | 63% |
| heart | 35 | 595 | 575 | 3.3s | 5.9s | 392 | 68% |
| gift | 172 | 1519 | 1403 | 11.0s | 20.5s | 675 | 48% |
| explosion | 77 | 1215 | 1178 | 7.3s | 13.0s | 655 | 56% |
| crystal | 130 | 1416 | 1408 | 9.1s | 16.6s | 396 | 28% |

- **`-m 2` is the right default, not `-m 4`** — 0.6–8.3% more bytes for ~2× the speed, consistently
  across all five. (Contrast `-m 0`: +134% on love, +14% on Dior's Builds' content — the curve
  between 0 and 2 is steep and content-dependent, the curve between 2 and 4 is flat and boring.)
- **AVIF q85 beat WebP lossless on every asset**, but by 28–72% — the *direction* generalises, the
  *magnitude* does not. Do not quote "37% smaller" as a rule.
- **All five fit Discord's 256 KB emoji cap at 128×128 with every frame kept**, at q85 (heart,
  crystal) or q70 (love, gift, explosion). So "AVIF, all frames, try q85 then q70" is a sound
  default procedure — but it is a procedure that MEASURES, not a fixed quality number.

### Known limits of `--recover-fade-alpha` (not yet hit, recorded before they are)
- **A fading element that OVERLAPS artwork** is a blend of glow+art, not background+one colour. It
  becomes a residual case and is forced opaque — the translucency over the art is lost. Degrades
  safely but silently; the coverage guard only catches it if the overlap is large.
- **A fading element whose colour EQUALS a solid art colour** is the dangerous one: that colour stops
  being a flood-fill barrier, so the fill can leak through solid artwork and punch it transparent.
  This is precisely why `--fade-color` exists as a manual override.
- **Strokes thinner than `2 × FADE_EDGE_DILATE` (6px)** let the edge rim reach through from both
  sides. The interior-protection warning is the designed detector and fires with a count (10 px on
  love, 349 on heart) — it is meant to be read, not ignored.

### An observation bigger than the feature itself
`--recover-fade-alpha` derives protection **topologically** — enclosed-and-unreached-by-the-flood
means opaque — with no outline colour to verify and no region geometry to supply. On `love.gif` it
protected the controller buttons perfectly with **zero user input**, where the normal path required
`--protect-outline-color 002864` discovered through analysis. That is position-independent by
construction, so it also sidesteps §10's whole fixed-region failure class, and with erosion off it
sidesteps §11's inflation class too.

If that holds generally, it is a better default protection strategy for flat vector art than either
`--protect-outline-color` (§2) or `--protect-region`. It is currently gated behind a fade-oriented
flag name and a webp/avif requirement — the latter is stricter than necessary, since binary alpha is
enough when there is no fade to preserve. **Observed on 5 assets, not proven; recorded as the
direction this skill should probably go next, not as a claim.**

### Decision recorded: `img2webp -exact` was considered and NOT adopted
libwebp can rewrite RGB under fully-transparent pixels to improve compression; `-exact` forbids it,
and Dior's Builds passes it. Not adopted here because: this script sets transparent pixels to the
background colour (the least harmful value for this content), its own resize path premultiplies and
is therefore immune regardless, and adopting it means adding an external-binary dependency to the
main output path with a Pillow fallback to maintain — for a benefit not demonstrable on any asset
tested. **`-exact` is the lever if a halo is ever actually observed.** Recorded so this is not
re-litigated from scratch.

### A translucent element whose TRUE colour never appears at full strength
Found on `gift.gif` after the user spotted the four-dot sparkle turning *whitish* as it faded.

The sparkle is drawn at a roughly **constant ~27% opacity**, so pure `#6969f2` barely exists
anywhere in the animation. It therefore never clears `build_art_palette`'s frequency floor, while
its *blended* stage `#d1dcfb` (thousands of pixels every frame) sails over it. The blend is then
admitted as a SOLID palette colour and rendered fully opaque — a pale lavender, which reads as
white-ish. The fade information was not lost by the encoder here; it was lost by the palette builder
picking the wrong endpoint of the ray.

**This is the mirror image of the fade-stage-impostor bug:** there, a blend was wrongly admitted as
solid *while the true colour was present*; here, a blend is wrongly admitted as solid *because the
true colour is absent*. Same symptom, opposite cause.

**Fix: `--fade-color` now INJECTS the named colour into the palette** instead of snapping to the
nearest existing entry. Snapping was useless for exactly this case — the nearest entry *is* the
wrong pale colour, and `#6969f2` sits 155 away, past the match tolerance, so the flag simply errored
out. `--recover-fade-alpha --fade-color 6969f2,fd6050` produces the correct translucent sparkle.

**⚠️ An automatic fix was attempted and REVERTED — do not re-attempt without reading this.**
"Saturation promotion": for each accepted colour, walk its background→colour ray looking for a more
saturated colour present at a lower count, and promote to it. Measured net-harmful across the corpus:
- `crystal.gif`: promoted the genuinely-solid `#d2dcfd` to `#8599f5`, **re-breaking the exact
  semi-transparency bug the two-pass palette had just fixed**.
- `explosion.gif`: emitted a duplicate palette entry (`#93b2f4` twice).
- `gift.gif`: only reached `#c4d0f2` — still not the true `#6969f2`.

Root reason it cannot work from colour statistics alone: *"pale colour is a blend of a rarer
saturated colour"* and *"pale colour is solid art that happens to be collinear with a saturated
colour"* are **indistinguishable in a histogram**. Separating them needs evidence the palette
builder does not have (per-region temporal behaviour). `--fade-color` is the working escape hatch,
and the auto-detector should be expected to miss this class.

### Is WebP/AVIF worth it when there is NO partial transparency?
Yes — measured, including on `explosion`, which has no fading element at all:

| Asset | Original GIF | plain GIF out | WebP lossless | AVIF q85 |
|---|---|---|---|---|
| explosion | 1506 KB | 1057 KB | 1216 KB | **665 KB** |
| crystal | 1189 KB | 1061 KB | 1417 KB | **392 KB** |

1. **Edge quality** — GIF's 1-bit alpha forces every antialiased silhouette pixel to be dithered or
   cut; WebP/AVIF keep the real antialiasing. Applies to *every* asset, fade or not.
2. **Size** — AVIF q85 beat the plain GIF output on both.
3. **Protection comes free** — `--recover-fade-alpha` derives protection topologically, so interior
   detail stays opaque with no flags at all. Visible in the corpus preview: `gift`'s plain-GIF
   output has its white box stripes punched TRANSPARENT (they are background-coloured and nothing
   protected them), while the WebP/AVIF outputs keep them correctly opaque with zero user input.

**Ship GIF only when the destination requires GIF.** Otherwise AVIF q85 is smaller and better, and
WebP lossless is the bit-exact master.

### A SOLID art colour inside the feather band is silently deleted from a GIF
Found when the user reviewed the corpus GIFs and reported colours missing from the *interior* of
`explosion` and `crystal`, and a white strip missing from `gift` — regions that are not the
background colour and should never have been touched.

Cause: the feather band runs `--tolerance` (15) to `× --feather-band-multiplier` (4) = **15…60**.
Any solid colour whose distance from the background lands in that window is given partial alpha and
then dithered/eroded away. Measured on these assets:

| Colour | Distance from white | Fate under the default band |
|---|---|---|
| `#d2dcfd` (explosion, crystal interior) | 57.0 | **inside 15–60 → deleted** |
| `#d1dcfb` (gift strip region) | 57.9 | **inside 15–60 → deleted** |
| `#93b2f4` (crystal mid-tone) | 133.1 | outside → survives |
| `#bb9bf1` (love lavender) | 121.7 | outside → survives |

That is why *half* of crystal's colours survived and half did not — the survivors were simply
further from white. Same structural shape as the fade problem in §16: a colour-distance window that
cannot separate "background blend" from "real art".

**`--protect-band-only` alone did NOT fix it** (tried first, measured: explosion still lost 13.8% of
its opaque pixels versus the WebP reference). What works is narrowing the band so the colour falls
outside it — `--feather-band-multiplier 3.0` took explosion from 13.8% → **3.0%** and gift from
16.1% → **2.1%** loss, where the remaining few percent is ordinary 1-bit edge antialiasing.

**Fix shipped:** `--recommend` now reads `band_interior_regions`' `solid_tint` distances and, when
one falls inside the band, emits a computed `--feather-band-multiplier` that stops short of it,
with evidence naming the colour and its distance. Previously it had all the data and never did the
arithmetic.

**This class cannot occur in a WebP/AVIF output at all**: `--recover-fade-alpha` identifies such a
colour as a solid palette entry and keeps it fully opaque. The GIF path needs per-asset flag tuning
that the new path derives on its own.

⚠️ **Process lesson, and the more important half.** These outputs were generated with NO flags as a
naive size baseline, then placed in a review folder beside properly-processed WebP/AVIF files
without being labelled as naive. The user reasonably read them as the skill's real GIF output. A
baseline that is not labelled a baseline is a false claim about the tool. Label deliberately-naive
artifacts, or do not ship them next to real ones.

### Objective way to compare a GIF output against a WebP one
Rather than arguing about which colours "look" missing: the WebP output is verified-correct, so
**pixels opaque in the WebP but transparent in the GIF are exactly what the GIF lost.** Per-frame
average across the corpus after proper flags:

| Asset | opaque in WebP | lost in GIF | % lost | top lost colour |
|---|---|---|---|---|
| love | 147,978 | 2,979 | 2.0% | `#052a75` (edge) |
| heart | 159,056 | 2,946 | 1.9% | `#052a75` (edge) |
| gift | 94,217 | ~2,000 | 2.1% | `#052a75` (edge) |
| explosion | 127,497 | ~3,800 | 3.0% | `#052a75` (edge) |
| crystal | 103,880 | 3,510 | 3.4% | `#052a75` (edge) |

When the top lost colour is the OUTLINE colour and the loss is 2–3%, the GIF is correct and you are
seeing the unavoidable cost of 1-bit alpha on antialiased edges. When the top lost colour is an
interior fill (`#ffffff`, `#d2dcfd`) and the loss is >10%, something is genuinely misconfigured.

### An opaque translucent element punches a hole through whatever it covers
A fading colour is deliberately NOT a flood-fill barrier — background behind a
translucent element has to stay reachable (love.gif's gap between heart outline and
pulse ring depends on it). But at FULL opacity such an element occludes, and where it
crosses solid artwork, exempting it opens a corridor the background flood pours through.

Confirmed on `crystal.gif`: an opaque yellow sparkle lying across the crystal's navy
outline **emptied the crystal's white interior in 59 of 130 frames — 24,520 px in one
blob.** A leak map (barrier black / correctly-outside green / leaked red / translucent
corridor yellow) showed the sparkle sitting exactly on the outline.

**Rejected fix:** a plain opacity cut (any pixel at t≥0.95 blocks). Fixes crystal, but
**seals love's gap in 27 frames** — trading one visible bug for another.

**Shipped fix — an ART PRIOR.** Colour alone cannot separate "opaque sparkle over navy"
from "opaque sparkle over background". Position over TIME can: the outline is art in most
frames, background is not. A near-opaque fading pixel (`t ≥ FADE_OPAQUE_BLOCK` 0.90) now
blocks only where solid art is present in ≥30% of frames (`FADE_ART_PRIOR`). Measured:
crystal 59/130 → **0**, love's ramp identical, falsifier still passing, opaque-white
within 0.17%.

### `--verify`'s `looks_fringed` is unreliable — do not decide erosion with it
`--edge-cleanup-erosion`'s 2px default is calibrated for the BAYER path. Under
`--dither-mode none` there is no dither noise to trim and 2px bites thin strokes from
both sides. Measured, non-background px wrongly deleted at erosion 2 vs 1:

| asset | erosion 2 | erosion 1 |
|---|---|---|
| crystal | 931,569 | 466,092 |
| explosion | 448,205 | 223,686 |
| gift | 635,720 | 313,631 |

So erosion was reduced — **to 0, which was wrong**, and Harkirat caught a visible pale
fringe on love.gif immediately. `--verify` reported `looks_fringed: False` at erosion
**0, 1 AND 2**, so it could not have caught this and actively misled the decision.

**Measure the outer opaque ring instead** — for the outermost ring of opaque pixels, how
many are closer to the BACKGROUND colour than to the art colour:

| erosion | mean distance to true outline colour | % of ring closer to background |
|---|---|---|
| 0 | 162.3 | **49.1%** ← visible fringe |
| 1 | 15.6 | 0.2% |
| 2 | 9.0 | 0.7% |

**Resolved defaults: 0 for WebP/AVIF (8-bit alpha needs no fringe trim), 1 under
`--dither-mode none`, 2 for the Bayer path.** ⚠️ `--edge-cleanup-erosion` now defaults to
`None` and resolves explicitly — the previous version could not distinguish "user typed 2"
from "default is 2" and silently overrode an explicit value, which also made a diagnostic
probe return identical numbers for 0 and 2 and nearly produced a second wrong conclusion.

### Bayer 8×8, and why error-diffusion dithers are wrong for ALPHA
`--bayer-size` now defaults to **8** (64 threshold levels vs 4×4's 16), tracking the
intended alpha **2.5× more closely** (mean local-density error 0.0051 vs 0.0128) at
identical temporal stability. `--bayer-size 4` reproduces pre-v5.0.0 output byte-identical.

**Floyd–Steinberg, Jarvis, Sierra, Stucki are disqualified for alpha**, and the test that
shows it must be able to fail. A first attempt nudged one pixel by 2% and scored 0 for
both methods — vacuous, because that pixel never crossed a threshold. Redone across two
frames whose right half is **byte-identical**:

| dither | px changed in the static region |
|---|---|
| Bayer 4×4 | **0** |
| Bayer 8×8 | **0** |
| Floyd–Steinberg | **312 (8.1%)** ← visible crawl |

Error diffusion propagates each pixel's error to its neighbours, so the pattern depends on
scan order and everything upstream: it crawls frame to frame even where the art is static,
and that also defeats GIF inter-frame compression. Ordered dithers are position-indexed and
therefore temporally stable by construction. (gifsicle still uses Floyd–Steinberg for
COLOUR quantization in the tiers — a different problem; see `gif-deferred-list.md` for the
open question of whether even that is right.)

### `--recommend`'s outline gate was too strict — a 22× worse result from being "safe"
The gate refused `--protect-outline-color` whenever `anomalous_frame_count != 0`, treating
"enclosure breaks on some frames" as "unusable". On `crystal.gif` the outline is verified
with `enclosure_ratio` 1.0 but breaks on 75/130 frames (the sparkle crossing it), so
`--recommend` fell through to `--protect-band-only` — **19.99% of the artwork lost against
the outline's 0.91%.**

A nonzero count means "the substitution path will engage", not "reject". Background LEAK
remains a hard reject (it over-protects, with no safe fallback). ⚠️ **A conservative gate
is not automatically the safe choice** — it has to be judged against what the fallback
actually costs.

### Borrowed masks: UNION with the frame's own, and CLAMP to its silhouette
When enclosure is flagged anomalous, the per-frame mask substitution used to REPLACE that
frame's mask with a borrowed one. Two separate defects came out of that, both on crystal:

- **Replacement discards correct information.** The frame's own mask encloses whatever
  that frame does enclose. Pure replacement deleted ~500 px from inside the small left
  crystal in frames 0-19. Fix: `(own | borrowed)`.
- **A borrowed mask describes ANOTHER frame's geometry.** On anything that moves or grows
  it protects background the current frame does not cover — a white wedge floating above
  the tall crystal's tip, ~1,600 px/frame. Fix: `& this-frame's-filled-silhouette`.

Combined: `(own | borrowed) & silhouette`. Measured: hole 502 px → 10-17 px, wedge +1,642
→ 0, art loss 0.95% → 0.89%.

⚠️ **Also tried and REVERTED:** suppressing the bimodal gap detector when the small mode is
the MAJORITY, on the theory that occlusion is the exception. On crystal the small mode IS
the majority (75/130) — and is the BROKEN state. Suppressing took art loss from 0.95% to
7.07% and left an 11,451 px hole. **A majority can be wrong.**

### `--recommend` now recommends the FORMAT, ranked for compatibility not just bytes
It previously suggested flags but never the container — the first decision, not a packaging
afterthought. A `gradient_fade` region means GIF structurally cannot carry the asset.
Ranking (Harkirat's, 2026-08-17):

- **full resolution** → WebP lossless > AVIF q85 > GIF
- **under a byte cap** → AVIF > WebP > GIF (AVIF keeps EVERY frame; the others drop a third
  to two-thirds)
- **maximum compatibility** → WebP > GIF > AVIF
- **GIF** only when required, or a genuine win on size/render-time at near-equal quality

Always report frame counts beside file sizes — under a cap, frames are what actually gets
spent.

---

## 17. A WebP source silently shifted every frame duration by one

**Found 2026-08-17** on the first job whose SOURCE was a WebP rather than a GIF — Harkirat had
manually removed the gamepad from `love.gif` and supplied a lossless WebP export of the result.
Not found by a test; found because the save line printed a total that disagreed with the source.

### What happened
The script read the 124-frame source, processed it correctly, and wrote a WebP whose durations
were:

| | durations | total |
|---|---|---|
| source | `[220, 20 x122, 340]` | 3000 ms |
| output | `[100, 220, 20 x122]` | 2760 ms |

The list is **shifted one position right**: a 100 ms frame that exists nowhere in the source is
prepended, and the final 340 ms frame is dropped. The animation ran 240 ms short with every
frame's timing off by one.

### Root cause — a Pillow API difference that fails silently
`GifImagePlugin` populates `info['duration']` inside `seek()`. `WebPImagePlugin` populates it
only inside `load()`. The script used the same seek-then-read pattern for both:

```python
im.seek(i)
durations.append(im.info.get('duration', 100))   # WebP: returns the PREVIOUS frame's value
```

On a GIF this is correct and always has been. On a WebP it returns whatever the last *loaded*
frame left behind — a one-position lag, with Pillow's 100 ms default standing in for the frame
that was never read. No exception, no warning; just wrong numbers.

**Four call sites shared the bug**, and they concealed each other:
`process()`'s source loader (wrote the wrong output), `load_gif_rgba_frames`,
`read_animation_timing`, and — critically — `describe_written_timing`, the readback added in
§13 precisely to stop the script asserting timing it had not verified. Because the readback
used the same lagged pattern, *intended* and *written* agreed with each other and the script
reported **"durations preserved exactly."** §13's fix was correct in design and still could not
catch this: a readback written with the same faulty assumption as the writer confirms the
assumption, not the file.

### The fix
One helper, used at all four sites:

```python
def frame_duration_ms(im, default=0):
    im.load()                              # load-bearing: WebP/AVIF set duration only here
    return im.info.get('duration', default)
```

Verified: the GIF path is **byte-identical** before and after (compared against the retained
`love_transparent.gif` baseline), so this is a pure no-op wherever it already worked, and the
WebP output now round-trips `[220, 20 x122, 340]` element-wise, not merely by total.

### It also closed a separate open item
The autonomy backlog carried "AVIF durations cannot be read back — Pillow exposes none." That
was the *same* bug wearing a different symptom: seek-only on an AVIF returns `0` for every
frame, so `read_animation_timing` summed to zero and honestly reported the timing as
unverifiable. With `load()` it returns `[220, 20 x122, 340]`, total 3000 ms. **The item was
never an AVIF limitation at all** — it was this missing call, and it sat on the backlog as an
external constraint because nothing had tested the alternative.

### Lessons
- **A readback only verifies if it reads the file by a genuinely different path than the write.**
  Sharing a helper, an assumption, or an API quirk with the writer turns verification into an
  echo. This is §13's lesson one level deeper: §13 stopped the script asserting what it never
  read; §17 shows that reading it back through the same flawed lens is still not evidence.
- **Format plugins differ in WHEN they populate metadata, not just what.** A pattern proven on
  GIF carried to WebP/AVIF without re-testing, and the failure was silent because both APIs
  return a plausible integer.
- **"Cannot be done" on a backlog deserves one falsification attempt before it is recorded as a
  constraint.** This one cost a single `load()` call and had been written down as a property of
  Pillow.
- **Scope check before claiming impact:** every previously delivered file was rendered from a
  GIF source, so all measured correct (3000 ms, `[220, ..., 340]`) — including a 42-frame
  byte-capped WebP whose merged durations still summed correctly. The bug only ever bit a
  WebP/AVIF *source*, which this job was the first to use.

---

## 18. Closing the autonomy backlog: four recommendations that were wrong, and why

**Worked 2026-08-17**, driven by Harkirat's standing goal that the skill run fully
autonomously — `--analyze`/`--recommend` producing correct flags with no human tuning. Each
item below was a case where a manual override was still required. A manual flag tweak is the
*investigation*, never the fix; the fix is whatever makes the tool reach the same answer itself.

### 18.1 `--pixel-art` on antialiased vector art — a second discriminator, not a moved threshold
`edge_hardness.ratio` counts pixels in a narrow band just outside the background tolerance. A
clean vector export built mostly from straight edges needs only a thin antialiasing band, so it
scores low and reads as pixel art: **love 0.425 and heart 0.316 against a 0.5 threshold**, and
`--pixel-art` disables feathering and erosion, which is destructive on curved antialiased art.

Moving the threshold was not safe — measured per frame, love ranges **0.290–7.863** and heart
**0.239–9.008**, and the *median* is below 0.5 for both (0.481, 0.388), so a majority of frames
look hard-edged on this metric. `analyze()` also measured frame 0 alone, making the answer
depend on which frame you happened to sample.

The fix asks a different question: **are there real background-to-art blends at all?** Genuine
pixel art has none by construction — every pixel is a palette colour, never a mixture.

| asset | band ratio (frame 0) | band ratio (max) | blend ratio |
|---|---|---|---|
| synthetic pixel art | 0.000 | 0.000 | **0.000** |
| love | 0.425 | 7.863 | **2.415** |
| heart | 0.316 | 9.008 | **2.529** |
| gift | 1.382 | 3.295 | 1.713 |
| explosion | 6.508 | 10.347 | 1.653 |
| crystal | 8.228 | 10.920 | 1.530 |

`appears_hard_edged` now requires BOTH the band ratio (max across frames) under 0.5 AND the
blend ratio under 0.15. The fixture still gets `--pixel-art`; love and heart no longer do. This
is a margin of KIND (blends exist / do not), not of degree.

### 18.2 `--erosion-exempt-max-size` — classifying regions correctly is not sufficient
The persistence classifier was already right: on love it correctly identified the four
controller buttons as DESIGN (497 of 1070 regions, present in ~every frame at a stable
286–306px). The suggestion was still wrong, because **the flag is a size threshold** — it
exempts every region at or below it. Computed from the transient regions, it came out at
**487px, above the buttons' own size**, so it would have exempted the design anyway and
reintroduced the v3.3.3 fringe.

The rule now: if the suggested threshold reaches the smallest PERSISTENT region, the transient
and design size ranges overlap and **no threshold separates them** — so recommend nothing and
say why, rather than picking a value from one side of an overlap. love is suppressed; heart and
gift (no persistent regions at all) still get it.

**The general lesson: a correct classification does not imply a usable parameter.** Check that
the knob you are about to set can actually express the distinction you just made.

### 18.3 `--feather-band-multiplier` — the clamp was manufacturing the bug
The flag narrows the feather band so a near-background SOLID art colour falls outside it. But
the same band is what gives the antialiasing ramp its partial alpha, so past a point the ramp
stops being removed and survives as a visible fringe. The old value was
`max(1.5, dist/tolerance - 0.5)`, and that clamp silently crossed the line:

| asset | tint distance | multiplier | fringe fraction |
|---|---|---|---|
| explosion, gift | 57–58 | 3.3 (band 15–49.5) | clean — the case the flag was built for |
| **heart** | **27** | **1.3, clamped up to 1.5** (band 15–22.5) | **0.2186 — fringed** |

heart also measured 0.1831 at 2.5, against **0.0000 at the default 4.0**. So the recommendation
was itself producing the fringe that backlog item 3.3 suspected.

`--protect-band-only` — already recommended alongside it — solves the same problem without the
cost: measured on heart it keeps **117,027 of the 119,810** near-background solid pixels the
multiplier keeps (97.7%) with **no fringe**. The multiplier is now only recommended when the
computed value is ≥3.0; below that the evidence says so and points at `--protect-band-only`.

**The clamp was the tell.** A clamp that fires is a value the formula could not produce
honestly — it satisfied the formula while failing the thing the formula was for.

### 18.4 gift's white strip — the union footprint, not the colour detection
`--analyze` reported the strip as design (`enclosure_ratio` 1.0) but returned
`candidate_outline_color: None`, so nothing protected it and `--verify` came back with
**`protected_region_coverage` 0.0** — the region was deleted outright. The working flag
(`--protect-outline-color 052a75`) had been found by eye.

The colour detection was fine. The FOOTPRINT was wrong: `comp_footprint` is a union across
sampled frames, and the union had merged the strip with a neighbouring transient pocket,
inflating it from **21,184px to 25,219px**. Nothing encloses the inflated shape, so
verification correctly failed — on a region that isn't real. Measured directly: `052a75`/
`002864` encloses the strip's own footprint in **40 of 40** sampled frames.

The fix re-verifies against what is ACTUALLY enclosed in each frame (footprint ∩ that frame's
own enclosed-background mask) and accepts a colour only if it verifies in ≥90% of them. This
keeps the conservatism the original note argued for — still a verified containment check, just
run on inputs that correspond to something real. gift now auto-recommends
`--protect-outline-color 002864`; coverage went **0.0 → 0.874** and fringe **0.0388 → 0.007**.

**The union limitation was documented in the code for months as "no cheap, universally reliable
way to distinguish these two cases from the union shape alone."** That was true and remains
true — the escape was not to distinguish them from the union shape, but to stop relying on the
union for this particular question.

### 18.5 `looks_fringed` — replaced, and deliberately made tri-state
The old check asked whether an edge-ring pixel was within `tolerance` of the background colour.
A pale fringe pixel is a BLEND, tens of units from pure background, so it passed: the check
returned False at erosion 0, 1 AND 2 on the same asset, including a level with a fringe visible
by eye, and that false negative was trusted and shipped a regression (§16).

The replacement asks a RELATIVE question — is the pixel closer to the background than to any
real art colour? — over the outermost opaque ring only. Measured:

| asset | erosion 0 | erosion 1 | erosion 2 |
|---|---|---|---|
| love | 0.2647 | 0.0765 | 0.0755 |
| heart | 0.0665 | 0.0000 | 0.0000 |
| gift | 0.4000 | 0.0372 | 0.0362 |
| crystal | 0.1681 | 0.0830 | 0.0823 |

It separates cleanly WITHIN each asset — every erosion-0 value is 2–4× its own clean baseline —
but the ranges **OVERLAP across assets**: heart's fringed 0.0665 sits below crystal's clean
0.0830, because art with a baked-in fade legitimately carries pale near-background pixels at its
boundary. Tightening the ratio does not rescue it: tested at 0.6, 0.4 and 0.25 of the art
distance, and **0.4 and below collapse every asset to 0.0000** — a test that cannot fail, which
§16 already names as the worst possible outcome.

So the check reports **True above 0.15, False below 0.04, and None in between with the reason** —
because inventing a single global threshold here is precisely how the previous version earned
its false negative. An unverifiable answer must present as unverified, never as a pass.

### 18.6 One backlog item was not real
"GIF `--target-kb` discards `--square-pad`" did not reproduce: measured at 128×128 with and
without `--crop`, the padding survives the whole tier cascade. The original 128×110 observation
was a render script that never passed `--square-pad` to the GIF variant in the first place.
**A backlog item is a hypothesis until it is reproduced** — this one cost two commands to
falsify and would have cost a speculative fix to "solve."

---

## 19. `--auto`: verifying the OUTPUT, and calibrating each asset against itself

**Built 2026-08-17, from Harkirat's question** after §18.5 concluded the fringe metric could not
be made a reliable boolean:

> "why don't we make the script do a double verification/analysis? on the original, as it
> currently does, and then again on the output, to decide if it's original recommendation was
> correct or if something needs to be changed... like an automatic post render verification
> analysis?"

That reframes the problem correctly. §18.5 had established the metric **separates cleanly within
one asset** (every erosion-0 reading is 2–4× that asset's own clean baseline) and **overlaps
across assets** (heart's fringed 0.0665 below crystal's clean 0.0830). I had treated that as a
dead end and shipped an "inconclusive" verdict. But it is only a dead end for a *global constant*
— the within-asset signal was never the problem, and comparing an asset against **itself** is
exactly the calibration a constant cannot express.

### The calibration
`calibrate_edge_cleanup_erosion()` measures the asset at each candidate erosion and reads the
answer off its own curve, picking the **smallest** erosion already within 0.02 of that asset's
own floor — smallest because erosion also eats thin strokes, so the goal is the least erosion
that has already removed the fringe. Measured:

| asset | erosion 0 | 1 | 2 | 3 | picked |
|---|---|---|---|---|---|
| love | 0.3688 | 0.0853 | 0.0850 | 0.0847 | **1** |
| heart | 0.0720 | 0.0002 | 0.0002 | 0.0002 | **1** |
| gift | 0.4343 | 0.0078 | 0.0073 | 0.0068 | **1** |
| explosion | 0.2171 | 0.0000 | 0.0000 | 0.0000 | **1** |
| crystal | 0.1928 | 0.0068 | 0.0057 | 0.0047 | **1** |
| love (WebP, 8-bit alpha) | 0.0003 | 0.0003 | 0.0003 | 0.0003 | **0** |

**heart is the proof.** Its fringed reading of 0.072 is what defeated the global threshold — it
sits below crystal's *clean* 0.0830. Against its own floor of 0.0002 it is 360× the baseline and
utterly unambiguous. Same number, same metric; only the reference changed.

The last row matters just as much: the identical rule returns **0** for an 8-bit-alpha output,
because the ring metric only looks at near-opaque pixels (`opaque_min=250`). On WebP/AVIF the
edge is a real alpha ramp that is *supposed* to be pale and semi-transparent, so there is nothing
to erode — and the calibration discovers that rather than being told. Both of last session's
hand-derived defaults (1 for the GIF path, 0 for WebP/AVIF) now fall out of measurement.

**One rule covers both failure directions.** Too little erosion reads far above the floor; too
much shows no further improvement and loses the tie to the smaller candidate. There is no
separate "is it over-eroded?" check to get wrong.

### Why BOTH a pre-encode calibration and a post-render check
The calibration runs on in-memory alpha, so it costs one extra erosion pass per candidate rather
than one extra render — and it corrects before encoding, so nothing is wasted. But it cannot see
the encoder: GIF palette quantization can snap an edge pixel onto a different palette entry (§16
measured that same quantization destroying 90% of an outline's antialiasing), and lossy WebP/AVIF
shifts edge colours. So `--auto` re-measures the **written file** and, if it exceeds the asset's
own pre-encode floor by more than 0.05, escalates erosion once and re-renders.

Across all five assets the encoder agreed (largest gap 0.0021), so the correction never fired on
real content — which is a good result and also means the branch was **untested**. Per §16's own
lesson that a test which cannot fail proves nothing, it was verified by stubbing the post-render
reading high: the branch fires, re-renders, and re-measures to 0.0.

### Design points worth keeping
- **Explicit flags always win.** A recommended flag is applied only where the user left that
  option at its default, computed by diffing three namespaces (defaults / recommended / actual).
  `--auto` fills gaps; it never overrides a deliberate choice, and it prints what it skipped.
- **`--auto` is opt-in, and the default codepath is byte-identical** — re-verified against the
  retained `love_transparent.gif` baseline after every edit in this round.
- **The general lesson: when a measurement has no absolute threshold, look for a relative one
  before declaring it unusable.** "Compare it against itself" was available the whole time, and
  I had written the manual version of it into the inconclusive verdict's own advice text
  ("compare this asset against its own erosion 0/1/2 outputs") without noticing that a machine
  could simply do it.

---

## 20. Auditing §19: five defects found by reviewing my own work

**2026-08-17**, after Harkirat asked how many times `--auto` would loop and then asked for a
full audit. The loop question alone surfaced a wording error; the audit surfaced four more
defects, three of which the tests as written would never have caught.

### 20.1 I called straight-line code "a loop"
`auto_run` has no `while`, no recursion, and no counter — it calls `process()`, measures, and
calls it at most once more. I described it as "the closed loop" in the summary, the docstring
and the handoff, **in the exact context where the distinction mattered**: a question about
runaway risk. Harkirat caught it. A future reader would have gone looking for an iteration cap
that does not exist, or added one.

Bounded-by-shape is stronger than bounded-by-counter — there is no state that can fail to
increment. And two passes is principled rather than cautious: pass 1's calibration is
EXHAUSTIVE over its candidate set (it measures every candidate rather than stepping toward an
answer, so iterating adds nothing), pass 2 exists for the single discrete effect pass 1
structurally cannot see (the encoder), and no third class of error remains. That reasoning is
now in the docstring, along with what a future looping version would have to carry.

### 20.2 The correction could ship a WORSE file than the one it replaced
The corrective re-render overwrote the output in place, then printed a warning if the result was
not an improvement — leaving the inferior file on disk with the better one already destroyed.
Now the first render is preserved, the correction is compared against it, and the loser is
discarded. The message states which render is actually on disk. Same principle as §13/§17:
report what IS, not what was attempted.

### 20.3 The escalation was computed from a value that was never written back
`process()` starts with `args = copy.copy(args)`, so every setting it resolves internally —
including the calibrated erosion — is invisible to the caller. `auto_run` computed
`newe = (args.edge_cleanup_erosion or 0) + 1` from the CALLER's copy, where the value was still
`None`. So the "escalation" re-rendered at erosion 1 when pass 1 had already used 1: **not an
escalation at all**, while reporting one.

Found by reading the test output rather than the assertion — the revert test passed, and the
message beneath it said "the FIRST render (--edge-cleanup-erosion 0)" when pass 1 had used 1.
The assertion checked that the branch fired, not that it did the right thing. The resolved value
now travels back through the diagnostics sink.

**A passing test plus an implausible number in its output is a failing test.**

### 20.4 "Explicit flags always win" was false, twice over
I put that guarantee in the help text and the docstring. Two separate holes:
1. `--auto` decided "the user expressed no opinion" by comparing against the default, so a user
   who explicitly typed the default value was indistinguishable from one who typed nothing, and
   got overridden. argparse keeps no provenance; `typed_option_names()` now reads argv.
2. Worse, and caught only by testing it: an explicitly typed `--edge-cleanup-erosion 2` was
   still recalibrated down to 1, because the calibration is gated on `auto_erosion` and
   `auto_run` set that flag unconditionally — re-enabling what `main()` had just turned off.

The second one is the instructive half: I "fixed" the guarantee in the flag-application code and
declared it done, while the actual override lived somewhere else entirely. **Fixing the
mechanism you were thinking about is not the same as fixing the behaviour.** Only running the
command proved it.

### 20.5 `--auto` knew the format was wrong and said nothing
`recommend()` returns `webp-or-avif` for four of five corpus assets, with evidence that GIF
structurally cannot carry a baked-in fade. `--auto` printed that and then rendered a GIF anyway
if that is what the output path said. The single most consequential decision — the container —
was the one `--auto` did not act on. It now prints a prominent FORMAT CONFLICT warning. It still
does not override the user's chosen filename, which is right: the user named the file. But
proceeding silently when the analysis says the result will be wrong is not.

Related, same audit: pass 2 only measured fringe. For a GIF output the full `verify()` is
available and free, and it covers the duration/frame-count class that §17 was — so `--auto` now
runs it and reports leftover background, protected coverage and timing, rather than letting a
clean fringe reading imply a clean file. For 8-bit-alpha outputs it says explicitly that only
the alpha-aware check ran and this is NOT a full verification.

### 20.6 Limits of this session's calibration, stated plainly
Every threshold set in §18–§19 was calibrated on **five assets from one art family** (flat
vector icons on white, from one emoji set) plus a synthetic pixel-art fixture **I wrote myself**.
That fixture confirms the discriminator does not fire on art with literally zero antialiasing,
but it is not independent evidence about real-world pixel art, which often carries some AA or a
palette dither. The blend-ratio margin (0.000 vs 1.530) is wide enough to survive that; the
narrower constants (feather ≥3.0, fringe bands 0.04/0.15, floor tolerance 0.02, post-render
0.05) rest on 4–5 points from one style, and no dark-background asset was tested at all.

Also worth recording honestly: **every GIF asset calibrated to erosion 1.** That is the correct
answer being stable, not degeneracy — the WebP path returns 0 from the same code, which proves
the rule is not stuck. But it means the calibration mostly re-derives a constant for this corpus,
and its 2/3 branches have never been exercised on real content. Its genuine value is that it
DERIVES rather than assumes, and adapts across alpha depths — not that it finds a different
answer per asset.
