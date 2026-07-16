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
