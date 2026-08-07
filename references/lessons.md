# GIF Background Remover — Lessons, Postmortems & Tool Evaluations

This file holds the full evidence trail behind SKILL.md's rules: bug postmortems, tool
evaluations, and measured numbers from this skill's real development history. SKILL.md states the
resulting *rule* concisely and points here; this file has the *why*, including approaches that
were tried and reverted — read those before re-attempting them.

**When to read this file:** before re-diagnosing anything that smells like a past case (flicker or
a gap in a protected region, erosion eating fine detail, jagged edges surviving a resize, a wrong
animation-length claim, a "grainy/messy" complaint after compression, a which-tool-or-quantizer
question). Check the table of contents below for a matching section first — see the memory
folder's `feedback_check_lessons_before_rediagnosing.md` for the full reasoning on why this matters.

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

---

## 1. Edge-hardness caveat: geometry-heavy false positives
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
  the underlying algorithm is well-regarded and the component-level numbers look unambiguous. See
  the memory folder's `feedback_test_naive_alternative_first.md`.

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
