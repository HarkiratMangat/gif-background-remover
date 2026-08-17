---
name: gif-background-remover
description: Remove the background color from an animated GIF while protecting a specific interior region of the design (e.g. a white highlight inside a badge) even when that region is the same color as the background. Handles both antialiased vector icon/sticker/emoji art (the default assumption) and hard-edged pixel art (via --pixel-art, which avoids destructively eroding non-antialiased content). Also handles shrinking an animated GIF to fit a platform's file-size limit (e.g. Discord sticker/emoji uploads, which cap at 256KB) via frame-rate reduction and gifsicle-based compression tiers, and batch-processing multiple GIFs at once from a manifest. Outputs GIF, or WebP/AVIF with true 8-bit partial transparency -- including recovering a fade/glow/sparkle whose translucency was already flattened against the background by a GIF export, which GIF itself cannot represent. Use when the user asks to remove/strip the background from a GIF, make a GIF transparent, cut out a GIF's background, convert a GIF to WebP or AVIF, keep a fading/glowing element translucent, turn a GIF into a sticker or emoji, shrink/compress an animated GIF's file size, or process several GIFs the same way in one go.
---

# GIF Background Remover

**Skill version: v5.0.0** (previous: v4.0.0, v3.3.3, v3.3.2, v3.3.1, v3.3.0, v3.2.0,
v3.1.0, v3.0.0, v2.2.2, v2.2.1, v2.2, v2.1, v2, v1). This is a **major**
bump, reasoned against the tier definitions below rather than pattern-matched:
it adds two new OUTPUT FORMATS (WebP and AVIF, both with true 8-bit alpha) and
a new alpha-recovery algorithm that solves a case this skill previously
documented as structurally impossible (`references/lessons.md` §7, "GIF format
has no partial transparency"), plus a byte-cap fitting cascade for those
formats and a real `--recommend` logic fix. Multiple new features and a
reviewed, end-to-end-verified round — squarely major.

**What v5.0.0 adds**, all from one real job (`love.gif` — full case in
`references/lessons.md` §16):
- **`--recover-fade-alpha`** — reconstructs partial transparency that a GIF
  export already flattened against the background (a fading glow/sparkle/pulse
  baked into progressively paler versions of the background colour). Works by
  unmixing each pixel against the art's own flat palette, so the recovered
  alpha is arithmetic, not an estimate. `--fade-color` overrides its
  auto-detection. Requires a `.webp`/`.avif` output.
- **WebP and AVIF output** — `--format {auto,gif,webp,avif}` (auto reads the
  output extension), `--webp-lossy`/`--webp-quality`/`--webp-method`,
  `--avif-quality`, and `--dither-mode continuous` (the default for both new
  formats) which keeps estimated alpha as real 8-bit transparency.
- **`--target-kb` now works for WebP/AVIF**, cascading quality → resolution →
  frames (frames last, since dropping them is the most visible loss), plus
  `--square-pad` for square emoji/sticker slots.
- **`--recommend` no longer suggests `--erosion-exempt-max-size` for regions
  that are actually design.** It now classifies small removed regions by
  PERSISTENCE (present in ~every frame at a stable size = design) rather than
  size alone — the old ≤500px ceiling let four ~287px buttons through and
  recommended erosion-exempting the very detail the user asked to preserve.
- **`--verify` refuses a non-GIF output** instead of reporting a misleading
  pass. Its checks assume 1-bit alpha — "leftover background" means an OPAQUE
  background-coloured pixel, "fringe" means a pale ring to cut — and under
  8-bit alpha a recovered fade is legitimately pale and semi-transparent, so
  those checks would flag correct pixels. Verify an 8-bit-alpha output by
  compositing it over the background AND over a dark solid instead (§16).
- **`--verify` now accepts WebP/AVIF**, not just GIF. Every check is
  partial-alpha aware: leftover background counts only ESSENTIALLY OPAQUE
  (alpha ≥ 250) background-coloured pixels, because on an 8-bit output a pale
  semi-transparent pixel is a recovered fade or an antialiasing ramp — correct
  output, not leftover. The report carries a `scope_note` saying so.
- **`--erosion-exempt-transient`** exempts small removed regions from erosion by
  IDENTITY rather than size — present in ~every frame at a stable size = design
  (eroded normally), comes and goes = incidental (exempt). Use it when the two
  overlap in size, which `--erosion-exempt-max-size` structurally cannot handle:
  on a real asset the design sat at 262–306px while the noise reached 442px, so
  no threshold separated them. Auto-recommended exactly there. §21.4
- ⚠️ **`protected_region_coverage` and leftover-background were both measuring
  the wrong footprint** until 2026-08-17 — a bounding RECTANGLE contains real
  background, and counting it made correct output look half-unprotected
  (gift read 0.874 for a fully protected region; 1.000 once restricted to the
  enclosed footprint). If you are comparing against numbers recorded before
  that date, they are not comparable. §21.1
- **`--auto`: TWO PASSES that verify the OUTPUT, not just the source.**
  ⚠️ Not a loop — there is no iteration construct and no counter. Worst case is
  two renders and exactly one correction, bounded by the code's shape.
  Runs `--recommend`, applies its flags (only where you left that option at
  its default — explicit flags always win, and it prints what it skipped),
  renders, then RE-MEASURES the written file and re-renders once if the
  encoded result disagrees with what the pre-encode calibration predicted.
  Use it when you want the skill to make the call end to end.
- **`--auto-erosion`: `--edge-cleanup-erosion` chosen by measuring the asset
  against ITSELF.** The fringe metric has no honest global threshold (§18.5),
  but within one asset every erosion-0 reading is 2–4× its own clean floor, so
  the calibration reads the answer off that asset's own curve and picks the
  SMALLEST erosion already at the floor — removing the fringe without eating
  thin strokes. It independently reproduces both hand-derived defaults: **1**
  for the GIF path and **0** for WebP/AVIF, the latter because the metric only
  counts near-opaque pixels and an 8-bit alpha ramp is legitimately pale.
  In-memory: one erosion pass per candidate, not one render. Full case: §19.
- **Four `--recommend` outputs that were wrong are now right** (full evidence:
  `references/lessons.md` §18). `--pixel-art` gained the blend-ratio
  discriminator above. `--erosion-exempt-max-size` is suppressed when the
  transient and design size ranges OVERLAP, because the flag is a size
  threshold and cannot then separate them — classifying regions correctly is
  not enough on its own. `--feather-band-multiplier` is only recommended at
  ≥3.0: below that it narrows the band so far that the antialiasing ramp stops
  being removed, and the old `max(1.5, …)` clamp was itself producing a fringe
  (measured 0.2186 at 1.5 vs 0.0000 at the default). Outline-colour
  verification now retries PER FRAME when the union-across-frames footprint
  fails, which is what was hiding a real, protectable region behind
  `candidate_outline_color: null`.
- **`--verify`'s `edge_fringe_check` is now tri-state.** `looks_fringed` is
  `true` / `false` / **`null`**, with `verdict_basis` giving the reason. The
  metric is the fraction of the outermost opaque ring closer to the background
  than to any art colour. It separates cleanly within one asset but the ranges
  overlap across assets, so a middling value reports INCONCLUSIVE instead of
  guessing. ⚠️ Never use it to choose `--edge-cleanup-erosion`; compare the
  asset against its own erosion 0/1/2 outputs, or composite over a dark solid.
- **Frame durations are now read with `im.load()`, not `seek()` alone.**
  Load-bearing for any non-GIF SOURCE: `GifImagePlugin` populates
  `info['duration']` during `seek()`, but WebP/AVIF populate it only in
  `load()`, so seek-only returns the PREVIOUS frame's value. A real
  124-frame WebP source came back `[100, 220, 20 ×122]` against a true
  `[220, 20 ×122, 340]` — one bogus frame prepended, the last one dropped,
  output 240 ms short — and the readback shared the same flaw, so the script
  reported "durations preserved exactly." Fixed at all four read sites; the
  GIF path is byte-identical. Full case: `references/lessons.md` §17.

The default GIF codepath is unchanged — confirmed byte-identical on a real
fixture before and after every edit in this round.

**Earlier version entries (v4.0.0 and back) live in `references/version-history.md`** — moved there in v5.0.0 to keep this file within the progressive-disclosure size convention. Read it when you need to know what a past version changed.

Versioning convention (three-part, `v{major}.{minor}.{correction}` — Harkirat's explicit spec, applies
both to this internal version log AND to whatever gets said in the file handed
back to him after an edit, so the two never drift):
- **Major** (v2 -> v3): a reviewed, end-to-end-verified round with multiple
  serious fixes and/or new features/major functionality changes.
- **Minor** (v2 -> v2.1): a single confirmed bug fix in the script itself that
  doesn't rise to major.
- **Correction / very-minor / note** (v2.2 -> v2.2.1): very, very minor —
  mainly documentation, but NOT required to be documentation-only (corrected
  2026-07-16); a genuinely tiny code tweak, too small to be its own minor
  bump, fits here too. "Mainly docs" describes the common case, not a hard
  rule.

All three tiers require the same bar before shipping: confirmed root cause (for
a fix) or confirmed-true (for a documentation note), and a real fix/finding, not
a guess — the SIZE of the change determines which tier, not the rigor applied.
**When deciding which tier a change fits, reason it through explicitly against
each tier's actual bar for THIS specific change** — don't pattern-match to
whichever tier a similar-sounding past change landed in.

**The version number in this file bumps at "push" (finalize + sync to the live
claude.ai skill), not at every repo commit (added 2026-07-16).** A working
session can commit several real changes to this file without bumping the
number yet — those commits are unreleased work toward the next version. Once
each real push gets git-tagged with its version (e.g. `v2.2.1`), `git
describe --tags` on any later commit shows exactly how many commits past the
last real version you are (e.g. `v2.2.1-3-gabc1234` = 3 unpushed commits past
v2.2.1) automatically, with zero manual bookkeeping — no separately
maintained counter to keep in sync or forget to reset at push time.
At push time, judge the CUMULATIVE tier of everything since the last tag as a
whole, not the sum of each commit's own tier, and bump once, to that.

**A live-skill-only session's exported `gif-background-remover-temp-vX.X.X.skill`
gets its own provisional version bump**, judged the normal way against
whatever that session's edit alone falls under (e.g. a notes-only live-session
fix is a correction, temp-version-wise). That provisional number is NOT
binding on the repo — it gets reconciled later against the repo's own history,
a fresh holistic judgment on what the REPO's actual next version should be
given everything accumulated since its last real tag, which may land on a
different tier than the temp export used.

**If you are running as the standalone skill on claude.ai, you are in an
isolated sandbox and this is the whole picture you get (stated here 2026-08-07
because a session cannot read it anywhere else).** You can read these packaged
files — this `SKILL.md`, `references/`, `scripts/` — frozen at whatever version
was uploaded. You cannot read the development repo, its `CLAUDE.md`, its git
history, or any memory folder, and **you cannot write anything to Harkirat's
machine.** So an export does not travel on its own: produce the
`gif-background-remover-temp-vX.X.X.skill` file, hand it and the full text of
anything you changed to Harkirat in the chat, and he moves it across himself.
Don't describe a finding as "saved," "synced," or "logged" — in that context
the chat is the only persistence there is.

**"Always hand Harkirat the latest full file" applies specifically to a
live-skill-only session (claude.ai, no filesystem) — corrected 2026-07-16.**
That convention dates from directly editing the live skill in a single
claude.ai chat, where the chat WAS the only persistent copy of the file, so
handing over the full text after each edit was the only way he'd have a
current copy. In a Claude Code / repo session, the file already persists on
disk — there's no need to re-paste the whole thing into chat after every
edit; just make the edit and say what changed. Full-file handoff still
applies when exporting a live-skill-only session's edits as
`gif-background-remover-temp-vX.X.X.skill` (see the temp-drop note above),
since that context has no other persistence either. Regardless of context,
**keep the actual skill `name` unchanged** in the frontmatter.

**This file is the lean, actionable core.** The full evidence trail behind its
rules — bug postmortems, tool evaluations, measured numbers, reverted attempts —
lives in `references/lessons.md`. Check that file's table of contents before
re-diagnosing anything that smells like a past case (flicker/gap in a protected
region, erosion eating detail, jagged edges, wrong duration, a tool/quantizer
question) — this skill's history is long and specific, and several fixes were
tried, looked right, and later regressed; re-deriving from scratch risks
repeating that.

## When to use this
The user has an animated GIF and wants its background color (usually white)
removed / made transparent, while preserving some part of the interior design
that happens to be the same or a similar color.

## Check content type FIRST — this determines which defaults are even safe
This script's defaults (feathering on, `--edge-cleanup-erosion 2`, LANCZOS
resizing) assume the source has real antialiasing to clean up — true for this
skill's primary target, antialiased vector icon/sticker art, but **actively
destructive** on hard-edged content like pixel art. Confirmed directly: the
DEFAULT settings eroded a 31px pixel-art shape down to ZERO surviving pixels
(0% survival) on a real synthetic test file — total destruction, not just a
quality hit.

**Before choosing settings, always check `--analyze`'s `edge_hardness` field:**
```json
"edge_hardness": {
  "ratio": 0.0,                      // frame 0, kept for continuity
  "ratio_max_across_frames": 0.0,    // the one the DECISION uses
  "antialiasing_blend_ratio": 0.0,   // the second discriminator
  "appears_hard_edged": true
}
```
**Two measures must agree before art is called hard-edged, and `appears_hard_edged`
already applies both** — trust that field over reading `ratio` yourself:
- `ratio_max_across_frames` under 0.5 — the transition band is empty. Measured
  across every sampled frame, not frame 0: love ranges 0.290–7.863 and heart
  0.239–9.008, so a single frame decides nothing.
- AND `antialiasing_blend_ratio` under 0.15 — there are essentially no genuine
  background-to-art blend pixels. Genuine pixel art measures **0.000** (it has
  none by construction); the lowest real vector asset measured **1.530**.

`ratio` alone produced two false positives on real antialiased vector art —
love 0.425 and heart 0.316 against the 0.5 threshold — because a clean export
made mostly of straight edges needs only a thin band. `--pixel-art` disables
feathering and erosion, so applying it there is destructive. The blend ratio
closes that gap by a margin of KIND (blends exist / do not) rather than degree.
See `references/lessons.md` §1 and §18.1.

**If `appears_hard_edged` is true → use `--pixel-art`** (bundles `--no-feather`,
`--edge-cleanup-erosion 0`, and nearest-neighbor resizing into one flag).

If content doesn't fit either bucket well — genuine photographic or full-bleed
content with no distinguishable background at all (shows up as the "four corner
pixels don't all agree" warning, or an obviously-wrong detected color) — that's
a real boundary of what this script does. It performs chroma-key style
background removal, not general image segmentation. Say so plainly rather than
forcing chroma-key settings onto content that structurally doesn't have a
keyable background.

## Animated/rotating content — check this SECOND, right after content type
Everything above is about ART STYLE. This is about ANIMATION STYLE: does the
foreground shape's position/orientation change significantly across frames
(rotating, tumbling, falling, spinning, translating across a large fraction
of the canvas), as opposed to a mostly-static icon with only minor internal
motion? Eyeball a handful of widely-spaced frames, not just frame 0. **If
yes, several of this skill's normal default assumptions become actively
dangerous, not just imprecise.** Confirmed on a real 124-frame tumbling
calendar/gamepad icon that took seven full rounds to fully fix — full case
history in `references/lessons.md` §10; this is the lean rule.

- **Never derive a fixed-position region (bbox/circle/rect) from one frame
  and apply it to other frames.** Any region needing frame-specific handling
  must be re-derived per frame from position-independent signals (size,
  shape, bordering color) — extends the existing `--protect-region`
  geometry-mismatch caution (below) to a new axis: position, not just shape.
- **Don't rely on border-touching as "is background"** once the foreground
  can graze the canvas edge — it can sweep real content into "background"
  and delete it. Use `--tumble-safe`, which defines background as the single
  largest connected bg-colored component per frame instead. `--analyze`'s
  `tumble_risk` field now measures this automatically across every frame
  (`worst_margin_ratio`, `likely_tumble_risk`) — check it on a new asset
  instead of eyeballing frames by hand.
- **`--protect-outline-color`'s per-frame enclosure can fail under
  self-overlapping/rotating geometry** in a way that doesn't trigger the
  existing flicker/anomaly detection (that detection is for a *different*
  shape briefly crossing a stable outline, not the outline's own shape
  rotating — see `references/lessons.md` §10 for why these are genuinely
  different failure signatures). Each candidate region's
  `outline_enclosure_all_frames.anomalous_frame_count` now checks this
  across every frame automatically — nonzero means the outline's own shape
  is breaking enclosure somewhere, the exact signature this bullet
  describes. `--tumble-safe` bypasses single-frame flood-fill enclosure
  entirely for this case; keep using `--protect-outline-color` for the
  stable-shape-crossed-by-something-else case it already handles well.
- **To selectively remove one small bg-colored region while keeping
  another** (e.g. a real hole/cutout vs. a same-colored decorative detail),
  add `--keep-bg-blob-if-near <hex[,hex,...]>` (only valid with
  `--tumble-safe`), narrowed with `--hole-size-range`/`--hole-max-aspect` to
  the real target's measured size/shape. **The distinguishing color has no
  default — identify it manually** the same way outline-color verification's
  fallback already works: zoom in, sample pixels bordering what should stay
  vs. what should go, use whatever genuinely differs.
- **If a solid design color might coincidentally sit near the background
  color** (a pale tint, a shadow/glow shape, a light gradient), add
  `--protect-band-only <px>` (4px was sufficient on the motivating case) —
  protects everything except a thin ring around the actual removal, instead
  of allowlisting specific safe regions, so no future near-background color
  can be silently mistaken for an antialiasing blend.
- **If a solid-color composite check (not checkerboard) shows speckle/noise
  on an otherwise-correct edge, try `--dither-mode none`** before assuming
  it's a mask bug — Bayer dithering can look like noise, not softness, over
  a flat background.
- **Verify against every frame, not a spot-check sample.** `tumble_risk`,
  `outline_enclosure_all_frames`, and `band_interior_regions` all scan every
  frame automatically now (not a sample) — see "Run analysis first" below.
  Still manually composite against a SOLID-color background in addition to
  checkerboard (see the Verification section) — that part stays visual.
  Every bug in this case was localized to specific rotation phases or
  specific colors; a normal spot-check would not reliably have caught any
  of them.

## Small removed regions can be inflated by edge-cleanup erosion — check this whenever a fix produces one
This is a separate pitfall from "Animated/rotating content" above, though it
was found on the same kind of content (an animated icon) and can compound
with it. It applies any time a fix removes a small, isolated bg-colored
region — an incidental gap where two independently-moving parts of the SAME
icon transiently graze each other (confirmed real case: an animated gear
rotating/bouncing near a static book's page edge, pinching off a tiny gap of
background at certain frames — nothing to do with a deliberate design hole),
not just `--tumble-safe`'s `--keep-bg-blob-if-near` case.

`--edge-cleanup-erosion` (default 2px) shrinks the OPAQUE region uniformly by
a fixed pixel count at every boundary, with no regard for how small the
removed region on the other side is. That's correct for its intended case (a
couple of pixels off a large silhouette's outer edge is proportionally
tiny). For a small, isolated removed region well under the erosion radius's
own scale, the same operation doesn't trim it proportionally — it consumes
the thin opaque wall around it instead, INFLATING it. Confirmed directly: a
single original 1px removed pixel became a 49-70px hole after a normal 2px
erosion pass — a 50-70x size inflation that turned an imperceptible artifact
into a visibly distracting "speckle." A naive fix — just raising the minimum
size before a region counts as removable at all — trades this for the
opposite failure: the same tiny features now stay solid opaque, which reads
as its own kind of visible speckle at exactly the points (like where the
gear teeth and book outline nearly touch) a person is most likely to be
looking closely. Neither "always remove, let it erode" nor "never remove,
leave it solid" is correct — the region needs to be removed at its own true,
tiny, native size, un-inflated.

Use `--erosion-exempt-max-size <px>` for this: it excludes any removed
region at or below that size from erosion's INPUT entirely (erosion behaves
exactly as if it were never flagged as removable, identical to how the
surrounding area is normally treated), then restores it to its own exact
pre-erosion pixels afterward. This is deliberately not "restore nearby
reclaimed pixels after the fact" — that was tried first and was measurably
incomplete (a 1px notch still came out ~40-50px) because erosion's actual
spillover pattern around a small feature isn't a clean uniform ring,
especially near other nearby geometry. Pass a rough ceiling comfortably
above the size of incidental noise and comfortably below any genuinely
large/visible removed region on the same asset (30px worked on the
motivating case, where noise measured 1-11px and the two real gaps measured
69px and 137px). `--analyze`'s
`small_removed_regions.suggested_erosion_exempt_max_size` now computes this
ceiling from the real region-size histogram on a new asset instead of
reusing 30 blindly. Full case history: `references/lessons.md` §11.

## Art that FADES toward the background colour — check this on anything with sparkles, glows or twinkles
Distinct from both sections above, and from the `--dither-mode none` note in
"Animated/rotating content." That note is about a correct EDGE looking speckly
once composited on flat paint. This is about a large INTERIOR region of the art
meshing no matter what you view it over.

GIF has no partial alpha, so an artist's fade-out is flattened against the
background at authoring time — a fading element literally becomes progressively
paler versions of the background colour. If a fade stage's solid body colour
lands inside the feather band (`--tolerance` to `--tolerance x
--feather-band-multiplier`, Euclidean RGB distance), the script assigns it
partial alpha and dithers it, and a spatial dither across a solid interior reads
as a **visible grid/mesh**, not as translucency. Confirmed real case: a sparkle
whose mid-fade body is `fff2d1`, distance 47.8 from white, inside the default
15–60 band.

- **Detect it before delivering:** `--analyze`'s `band_interior_regions`
  measures this automatically — grouped across every frame and classified
  `gradient_fade` vs `solid_tint`, with a plain-language `recommendation`
  per region. A thin edge band is normal; an interior `gradient_fade`
  region is the signature.
- **The real fix is to stop using GIF.** If the deliverable can be WebP or AVIF,
  use `--recover-fade-alpha` with a `.webp`/`.avif` output: it reconstructs the
  original alpha exactly rather than approximating it, and the fade renders as
  actual translucency. **No GIF setting can represent a fade correctly** — on the
  confirmed case the fade's colour-distance range (36→146) straddled a solid art
  colour at 121.7, so no feather band separates them. See the "Output format"
  section below and `references/lessons.md` §16.
- **If it MUST be a GIF, fix with `--dither-mode none`** — hard 50% cutoff on the
  already-defringed alpha. On the real case, faded bodies went from 47–68% opaque to 95–96%.
  Faintest stages drop out a beat earlier instead of meshing, which is the right
  trade.
- **Price it first: `--dither-mode none` changes EVERY edge in the file.** It
  was nearly free on an icon whose silhouette is mostly straight lines
  (`edge_hardness` 0.506) — verified by zooming the outer silhouette before and
  after. On curve-heavy art, measure narrowing `--feather-band-multiplier`
  instead. Full case history: `references/lessons.md` §12.

## Output format: GIF vs WebP vs AVIF — decide this BEFORE tuning anything
The output container is chosen by the output filename's extension (or `--format`).
It is not a late packaging detail: it decides whether partial transparency is
even representable, and therefore whether several of this skill's other rules
apply at all.

- **GIF** — 1 bit of alpha. Every pixel is fully opaque or fully transparent.
  Correct when the deliverable must be a GIF; everything about feathering,
  Bayer dithering and `--dither-mode` exists to cope with that limit.
- **WebP** — 8-bit alpha. Use `--webp-lossy` only when fitting a byte cap:
  at native resolution lossy is *bigger* than lossless on flat vector art
  (measured 2675 KB at q85 vs 2114 KB lossless), though the ordering reverses
  once downscaled (at 128px: 650 KB lossy vs 1190 KB lossless).
  `--bayer-size` (GIF, `--dither-mode bayer`) defaults to **8** — 64 threshold
  levels against 4×4's 16, tracking the intended alpha 2.5× more closely at
  identical temporal stability. Pass `4` to reproduce pre-v5.0.0 output
  byte-identical. Error-diffusion dithers (Floyd–Steinberg, Jarvis, Sierra,
  Stucki) are deliberately NOT offered for alpha: measured, Floyd–Steinberg
  changed 8.1% of pixels in a region byte-identical between frames — visible
  crawl on every edge — where both Bayer sizes changed 0.

  `--edge-cleanup-erosion` now resolves its default by context: **0** for
  WebP/AVIF (8-bit alpha needs no fringe trim), **1** under `--dither-mode none`
  (no Bayer noise to trim, and 2 deletes thin strokes), **2** for the Bayer path.
  ⚠️ Do NOT use `--verify`'s `looks_fringed` to pick this — it reported False at
  every erosion level including one with a clearly visible fringe. Measure the
  outer opaque ring instead (`references/lessons.md` §16).

  `--webp-method` defaults to **2** — measured across 5 real assets, m2 costs
  0.6–8.3% more bytes than m4 for ~2× the speed. **Do not raise it to 6**
  (45× slower for 2.3% smaller). Method 0 is faster still but its size cost is
  wildly content-dependent (+134% on one asset, +14% on another) — measure
  before using it.
- **AVIF** — 8-bit alpha, and roughly **3× the frame budget of WebP under a hard
  byte cap**: all 124 frames of a real asset fit Discord's 256 KB emoji limit at
  128×128, where WebP had to drop to 42. ⚠️ `--avif-quality 100` is NOT lossless
  and produces the largest file of all — never use it as a "best quality" knob.

**Decision procedure** (measured on 5 real assets — the direction generalises,
the exact numbers do not, so measure rather than quoting a ratio):
1. **Full fidelity / "no compression"** → WebP lossless (`-m 2`). The only
   bit-exact option; AVIF has no true lossless mode.
2. **Full resolution, minor optimization** → AVIF q85. Smaller than WebP
   lossless on every asset tested, but by anywhere from 28% to 72%.
3. **Hard byte cap (e.g. Discord's 256 KB emoji)** → AVIF at 128×128, keeping
   every frame, trying q85 then q70. All five test assets fit that way — two at
   q85, three at q70. `--target-kb` runs this cascade for you. Must ship a GIF →
accept the 1-bit-alpha consequences and read the fade section above.

⚠️ **Platform acceptance is not playback.** A platform listing a format as an
accepted upload type does not prove its clients animate it inline — verify with
a real upload before shipping. (Discord accepting *and animating* AVIF emoji was
confirmed by real test, not assumed.)

⚠️ **`--verify` only understands GIF** and refuses other formats rather than
reporting a pass it cannot substantiate. For WebP/AVIF check instead:
`webpmux -info out.webp` for real frame count/durations (Pillow reports 0),
that compositing the output over the background reproduces the source, and that
recovered alpha levels match the source's fade stages.

## Workflow: infer first, then confirm — don't just ask the user upfront
Don't open by asking the user to specify the background color and protected
region from scratch.

### 1. Run analysis first
```
python scripts/remove_gif_background.py <input.gif> --analyze
```
For a ready-to-confirm suggestion instead of reasoning across `--analyze`'s
fields by hand, use `--recommend` — it runs `--analyze` internally and returns
`suggested_command` plus an `evidence` list justifying each flag:
```
python scripts/remove_gif_background.py <input.gif> --recommend
```
Returns JSON with:
- `detected_bg_color` — auto-sampled from the corner pixels.
- `candidate_regions` — background-colored areas enclosed by other colors
  somewhere in the animation, each with:
  - `enclosure_ratio` — fraction of sampled frames where it's actually
    enclosed. `>= 0.9` → `likely_intentional_design: true` (keep it).
    Occasionally enclosed (e.g. an animated swoosh temporarily cutting off a
    pocket of background) → should stay transparent.
  - `suggested_protect_region` — a ready-to-use `circle:cx,cy,r` value.
  - `candidate_outline_color` — a guess at a bordering outline color (a hint,
    not a fact — see `outline_color_verified` below).
  - `outline_color_verified` — `true` only if the color was actually
    simulated (built its mask, ran `binary_fill_holes`, confirmed it truly
    encloses the region) rather than guessed. Treat `candidate_outline_color`
    as unusable when `false`.
  - `outline_enclosure_all_frames` — the same simulation re-run across EVERY
    frame, not just the one it was first verified on.
    `anomalous_frame_count == 0` means the outline holds everywhere;
    nonzero is the rotating/self-overlapping-geometry failure described
    above under "Animated/rotating content" — treat
    `outline_color_verified: true` with a nonzero count here as NOT safe to
    use unreviewed.
  - `outline_background_leak` — `over_protects_background: true` means this
    outline color's flood-fill also swallows real background somewhere, not
    just the intended interior — don't use it even if otherwise verified.
  - `circularity_ratio` (0-1) and `circle_region_safe` — how well a plain
    circle approximates the region's true shape. Low values mean
    scalloped/pointed/star-shaped outlines, where `--protect-region circle:...`
    is a poor fit (see "Run the real processing" below).

Warnings worth reading from stderr:
- If the four corner pixels don't unanimously agree on a background color,
  double-check `detected_bg_color` looks right.
- If the source GIF already has its own transparency index, its pre-existing
  transparent pixels are carried through automatically — no action needed, the
  `source_has_pre_existing_transparency` field and a printed NOTE just flag
  that it's happening.

### 2. Form a recommendation, then confirm with the user in one short message
Check `edge_hardness` first — if hard-edged, mention `--pixel-art` up front
rather than as an afterthought.

Summarize what was found in plain language, e.g.:
> "Looks like white is the background. There's also a white/light area in the
> middle of the badge enclosed by a ring — that's enclosed in 100% of frames,
> so it looks intentional and I'd keep it. There's also a gap between the
> ribbon tails that's occasionally enclosed by an animated swoosh (~20% of
> frames) — that looks incidental, so I'd treat it as background. Sound right,
> or should I handle either differently?"

Use a short multiple-choice confirmation (one question, options like "Keep it
opaque" / "Make it transparent" per region) when there are multiple regions,
rather than a wall of text. Only skip confirmation entirely if there's exactly
one obvious candidate region with `enclosure_ratio` at or near 1.0 and the
user's request already implied preserving an interior highlight.

**Multiple candidate regions with different outline colors are common** (e.g.
a badge with both a ring interior AND a separate gear/hole cutout, each
outlined differently) — a real case, not hypothetical. When two or more come
back `outline_color_verified: true`, do NOT run the script once per color
(a second run has no memory of what the first protected). Pass
`--protect-outline-color` ONE time with all verified colors joined by a comma
(e.g. `--protect-outline-color c8dcf0,8cb4f0`) — the script unions every
color's enclosed region in a single pass. Same idea for `--protect-region` if
needed for more than one region, joined with `;` instead (since `,` is already
used inside a single region's own coordinates).

### 3. Run the real processing with confirmed settings

**`--protect-outline-color` is the default choice. `--protect-region` is a
last resort, not an alternative style** — reach for it only when there is
genuinely no usable outline color, and even then treat the result as
provisional until step-by-step verified (below). A fixed-radius circle/rect
almost never matches a real icon interior's true (usually irregular) shape —
two real, initially-unnoticed bleeds/gaps from exactly this are documented in
`references/lessons.md` §2. Concretely:
- **Always try `--protect-outline-color` first** using the analyzed
  `candidate_outline_color` IF `outline_color_verified` is `true` AND
  `outline_enclosure_all_frames.anomalous_frame_count == 0` AND
  `outline_background_leak.over_protects_background` is `false` — that's
  the exact gate `--recommend` applies before suggesting the flag, safe to
  use directly when all three hold.
- **If `outline_color_verified` is `false`**: don't fall back to
  `--protect-region` yet. Open the source frame yourself and identify the true
  enclosing outline color by eye — sample a pixel a short distance outward
  from the protected area in a couple of directions and check they agree —
  then use that with `--protect-outline-color`. Cheaper than debugging a
  bleed after the fact.
- **Only use `--protect-region`** when there's truly no enclosing outline (a
  soft glow/gradient with no hard edge) — and check `circularity_ratio` /
  `circle_region_safe` first. If `circle_region_safe` is `false`, either use
  `rect:` if the true shape is axis-aligned rectangular, or warn the user this
  region's protection may not be pixel-perfect and needs extra-careful
  verification.
- A region the user wants left as background needs nothing extra — it's
  already removed by default.
- **If two different design features are enclosed by the SAME outline color
  but need opposite treatment** (one kept, one removed — e.g. a highlight
  star and a separate pin/grommet hole both ringed in the same navy), that's
  not a bug in `--protect-outline-color` (it correctly unions the whole
  area one color encloses); run it as normal, then carve the unwanted
  sub-region back out with `--remove-region` (below). Confirmed real case:
  `references/lessons.md` §15. **`--remove-region` is a STATIC mask, same
  caution as `--protect-region`** — do not use it alone on a target that
  moves/resizes across frames without re-deriving the region per frame
  yourself first (confirmed: a static circle missed the true target in 76%
  of frames on a real tumbling asset). For a moving target with no external
  per-frame tracking available, `--tumble-safe` + `--keep-bg-blob-if-near`
  with a tight `--hole-size-range`/`--hole-max-aspect` (§14) is the more
  robust choice when the hole and the decoration differ measurably in size
  or aspect across the whole animation — check `references/lessons.md` §14
  vs §15 for which fits.
- If `--bg-color` wasn't confirmed differently, omit it — auto-detected the
  same way `--analyze` does.
- **Edge feathering is ON by default; cropping is NOT.** Feathering is a pure
  quality improvement, so it stays on unconditionally. Cropping, resizing,
  frame-dropping, and gifsicle are opt-in via `--compress` tiers (see below) —
  a plain run changes nothing about canvas, frame count, or timing.

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
For several GIFs in one invocation, see "Batch processing" below — a JSON
manifest, not more CLI flags.

*(`--no-gifsicle-optimize` also exists in `--help` output but isn't listed
above — it's a confirmed no-op, kept only for backward compatibility with old
invocations now that gifsicle only ever runs as part of a `--compress` tier.
Don't spend time trying to use it for anything.)*

**Edge feathering** (default on): a hard color-distance cutoff leaves a
jagged/staircase boundary wherever the source art had smooth antialiasing,
since GIF only supports on/off transparency per pixel. The script instead
estimates a continuous alpha in a transition band around the cutoff
(color-unmixing against the background), de-fringes those edge pixels, and
converts the band to a binary transparent/opaque pattern using a spatially
fixed Bayer dither — so the edge reads as soft rather than blocky, without
flickering between frames. `--feather-band-multiplier` (default 4.0, i.e. 4x
`--tolerance`) widens/narrows the transition band. `--no-feather` only if the
user explicitly wants the old hard-cutoff look (e.g. true pixel-art style).

**Crop** (default OFF): standalone `--crop` crops to the transparent bounding
box without any other tier step. Any `--compress` tier crops automatically
regardless of this flag.

**Output size reporting**: every run prints final dimensions and file size in
KB to stderr — use this instead of a separate size check, and as the signal
for whether file-size optimization (below) is worth raising.

**Preview contact sheet** (`--preview <path.png>`, off by default): saves a
single PNG with evenly-sampled frames composited over a checkerboard,
side by side. Pass it on the same run that produces the final GIF.

## Delivery file naming, when reprocessing the same source
If a user reports a problem and asks for a fix, name the corrected file so
its iteration is obvious rather than silently overwriting: first attempt
`name_transparent.gif`, a fix `name_transparent_v2.gif`, `_v3.gif`, and so on.
Independent from the skill's own version number above.

## Verification (always do this before delivering the result)
Run `--verify` first — it covers the mechanical half of the checks below
(leftover background, protected-region coverage, edge fringe, small-region
inflation, duration/frame-count) across every frame automatically:
```
python scripts/remove_gif_background.py <input.gif> <output.gif> --verify
```
It does NOT replace the visual checks (soft-vs-jagged edges, a
`--protect-region` bulge following the art's own silhouette) — those still
need a human/agent's eyes, below.

**For animated/rotating content (see that section above), do two things
more thoroughly, not skip them:** `--verify` already checks every frame
automatically (not a first/middle/last sample) for the fields below — the
bugs in `references/lessons.md` §10 were each localized to specific
rotation phases, which only a full-frame check reliably catches. Still
manually composite against a SOLID flat color (e.g. pure green) at least
once, not just checkerboard — checkerboard camouflages dithering noise and
unstable partial-alpha artifacts the same way it camouflages soft bleed
(point 2 below), and both need checking, each catches what the other
hides.

1. `--verify`'s `leftover_background_opaque_px`, `protected_region_coverage`,
   and `edge_fringe_check.looks_fringed` now mechanically cover: background
   fully transparent everywhere it should be, the protected interior region
   fully opaque with no holes, and the outermost opaque ring being the TRUE
   art color rather than a lighter/tinted fringe left by imperfect
   color-unmixing (the default `--edge-cleanup-erosion 2` exists to prevent
   this; if `looks_fringed` is still true, pull actual edge pixel values
   rather than cranking erosion blind). What's left to check by eye: composite
   a handful of frames (first, middle, last, plus any frame flagged near a
   protected region) over a dark background — `--preview <path.png>` does
   this automatically — and check edges look soft/dithered, not jagged
   (zoom into a diagonal/curved edge). **If the source canvas is small
   (roughly under 200px on its shorter side), also check fine details (thin
   strokes, small dots, small gaps) survived the default erosion** —
   `--edge-cleanup-erosion`'s 2px default is a FIXED pixel count, not scaled
   to resolution, so a detail comfortable on a 640px icon can be nearly
   erased on a 128px one. The script warns to stderr when this situation is
   detected — don't ignore it; redo with `--edge-cleanup-erosion 1` or `0`
   if a detail got eaten.
2. **If you used `--protect-region` (circle or rect) anywhere, specifically
   look for a bulge, halo, disc, or straight edge that doesn't follow the
   artwork's own silhouette** — the signature of a mismatched protect-region,
   easy to miss on a quick glance (see `references/lessons.md` §2 for two
   real cases that slipped past an initial check). `--verify`'s
   `leftover_background_opaque_px` and `protected_region_coverage` now catch
   most of this mechanically; also composite over a plain dark background
   (not checkerboard, which can camouflage a soft-edged bleed) and check the
   protected area's outline traces the actual art. Disagreement of more than
   a few pixels in any direction → switch to `--protect-outline-color`.
3. **Duration/frame-count**: `--verify`'s `timing` field (via
   `describe_written_timing`) and `frame_alignment` cover this mechanically
   now — trust its verdict over comparing frame counts by eye. **A lower
   output frame count is not automatically a bug**: Pillow's encoder
   coalesces consecutive frames that come out byte-identical after
   quantization and folds their delays into the survivor (confirmed real
   case: 170 in, 168 out, nothing visually lost). Total playback length
   changing is the real defect signal, frame count alone is not — the
   `timing` field's verdict already reflects this distinction. Full
   Pillow-duration-read footgun and raw-bytes ground-truth method:
   `references/lessons.md` §9 and §13.
4. If a `--compress` tier or standalone `--crop` was used, confirm the crop
   removed the intended blank margin without clipping the design — check the
   `WxH -> W'xH'` line the script prints to stderr. If resize also ran, check
   final dimensions match the expected max-side target. (`--verify` skips its
   pixel-position checks entirely when input/output dimensions differ — see
   its `note` field — so this one stays manual.)
5. **When investigating a reported flicker/gap complaint, use the actual
   geometric interior mask, not a bounding-box sample** — `--verify`'s own
   `protected_region_coverage` already does this internally (a real
   per-frame enclosed-region footprint, not a bbox rectangle), so a
   `looks_unprotected` finding from `--verify` is trustworthy as-is; this
   matters if you're hand-rolling a check instead. See
   `references/lessons.md` §9 for a real case a bbox-based check
   false-positived on. If the flicker is real, the root cause and fix live
   in §3, not §9 — start by sampling the outline color itself on a good
   frame vs. a bad one: fading toward background → widen
   `--outline-tolerance` first; replaced by an unrelated solid color →
   occlusion, the built-in detection/substitution is the right tool.
6. If anything fails verification, adjust `--tolerance` / `--outline-tolerance`
   / `--feather-band-multiplier` or the protect region and rerun — don't patch
   the output GIF directly.

## File-size optimization: default vs. named tiers
**The default output is plain background removal, plus one correctness fix,
nothing else.** No crop, resize, frame-drop, or gifsicle pass — every frame
and its exact timing survive untouched at the original canvas size. The one
exception is `--edge-cleanup-erosion` (default 2px): not a size tradeoff, it's
fixing a real color artifact in the feathering math, so it applies regardless
of any `--compress` tier.

### When to raise file-size optimization at all
Don't ask by default on every request — do ask when there's a reasonable
signal it matters: the user mentioned a platform with known constraints
(Discord stickers = 256KB, exact error `[50138]... 262144` bytes; Slack
emojis; a CMS upload limit), the printed size is large enough that a common
constraint would plausibly bite, or the phrasing suggests a specific
destination ("for my Discord server", "as a sticker"). Otherwise just deliver
the plain file. When you do ask, keep it short: "This came out to 2.7 MB —
want me to optimize it for a specific target, like Discord's 256KB sticker
limit?"

### The three named tiers (`--compress optimize|medium|heavy`)
Each is a fixed, tested bundle, not independent flags to mix by hand.
`medium`/`heavy` include every `optimize` step, then add more:

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

`optimize` deliberately keeps every frame — it's for someone who wants a
smaller file with zero motion-quality tradeoff (crop/resize/erosion/lossless
gifsicle only touch redundant/invisible data). Frame-stride is a real,
visible tradeoff (choppier playback), reserved for `medium`/`heavy`. If
`optimize` alone isn't enough, step up a tier rather than adding standalone
`--frame-stride` on top of `optimize`.

**If someone reports fine details looking "grainy," "messy," or not matching
the original after `medium`/`heavy`, step DOWN to `optimize` first** rather
than tweaking dither/color-cap settings — thin design elements (a lightning
bolt, a small icon detail) are proportionally mostly edge transition, so even
`medium`'s relatively light 200-color dithering can visibly wreck them
(confirmed: 100+ unique colors in a thin region under `medium` vs. 3 under
`optimize` on identical content). `optimize` also keeps every frame by
default, so it's often a single fix for both a graininess and a choppiness
complaint at once. Full measurement details and the reasoning behind each
tier's specific choices (why Floyd-Steinberg, why 200 vs. 128 colors, why
frame-stride waits for `medium`) are in `references/lessons.md` §6 and the
"Tools considered" material there.

Order steps actually run in: frame-stride → crop → resize → erosion → render
→ gifsicle (gifsicle is always last regardless of tier, since it needs an
already-encoded file; `optimize` simply skips frame-stride).

Practical notes:
- All three tiers keep alpha clean (binary 0/255, transparent corners) —
  confirmed at every tier on real test files.
- An explicit `--frame-stride N` overrides a tier's own default (1 for
  `optimize`, 2 for `medium`/`heavy`) rather than stacking with it.
- If `gifsicle` isn't available, the non-gifsicle parts of a tier still
  apply, with a clear warning that gifsicle-dependent size reduction didn't
  happen — never a silent partial failure.
- Always check the actual result after a tier — `heavy` is a real quality
  tradeoff (256px cap, 128 colors), for a strict platform limit, not a
  default reach.
- **The GIF palette is built ONCE across all frames combined, not
  independently per frame.** An independently-quantized per-frame palette can
  assign different indices to the same visual color across otherwise-static
  frames, defeating disposal-based frame-diffing — confirmed a real case
  where fixing this dropped output size ~40% (from ~50% LARGER than source to
  smaller than it). If a future edit to `render_frames_to_gif` reintroduces a
  per-frame `convert('P', palette=Image.ADAPTIVE, ...)` call instead of one
  shared palette, treat that as a regression.
- **gifski** (external, quality-based re-encode after transparency is
  finalized) beat this script's own tiers in one confirmed real case where
  smooth motion mattered more than absolute minimum size — not integrated
  into this script yet. See `references/lessons.md` §8 before reaching for
  `--compress heavy`/aggressive `--frame-stride` on a "keep it smooth" ask.

### The standalone lever: frame-rate reduction (`--frame-stride`)
Works independently of any tier — for when the user wants ONLY the frame-drop
treatment without cropping/resizing/gifsicle:
```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    --protect-outline-color <hex> --frame-stride 2
```
- Drops every Nth frame and **folds the dropped frames' durations into the
  kept frame**, so total playback length is exactly preserved (choppier, not
  faster). Always verify the folding actually happened (verification step 3)
  before trusting any tool's frame-drop output, including this script's.
- A real case: a 161-frame badge animation (mostly 20ms/frame, 3.6s total)
  dropped to 81 frames at stride 2 cut file size roughly in half (1868KB →
  994KB) with imperceptible visual difference.
- Stops escalating once the average post-fold delay would exceed ~120ms/frame
  (~8fps) — beyond that, dropped frames read as genuinely choppy. If the
  source is already slow (100ms+/frame), mention this tradeoff explicitly.
- **`--frame-stride 1` explicitly forces keeping every frame even combined
  with a tier whose own default would drop frames** (e.g.
  `--compress medium --frame-stride 1`). The flag has a `None` default
  specifically so "unset" and "explicitly 1" are never conflated — if a
  future edit to the stride-resolution logic reintroduces a truthy check
  (`stride_override and stride_override > 1`) instead of
  `stride_override is not None`, that bug is back.
- **A common reason to want this combo:** `medium`/`heavy`'s dithering can
  look bad on fine vector linework (see the graininess note above) — if
  someone wants every frame kept AND no dithering artifacts, `optimize` (not
  `medium`/`heavy` + `--frame-stride 1`) is usually the cleaner single fix.

### The standalone lever: arbitrary resize target (`--resize-max-dim`)
The two named tiers only bake in 512px (`optimize`/`medium`) and 256px
(`heavy`). For anything else (a platform wanting exactly 128px, say):
```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    --protect-outline-color <hex> --crop --resize-max-dim 128
```
- Fits the longer dimension to the given size, preserving aspect ratio, only
  ever downscaling.
- Always followed by the same 1px post-resize cleanup erosion the tiers use.
- Works standalone or combined with a tier (overrides that tier's own resize
  target rather than stacking).
- Doesn't crop on its own — pair with `--crop` if there's transparent margin
  to remove first.
- **On a thin/high-curvature design element, skipping resize (setting this
  high enough to avoid downscaling) can improve BOTH quality and file size at
  once** — confirmed on two structurally different real icons. See
  `references/lessons.md` §5 before assuming resize is always harmless.

### Automatic target-fitting (`--target-kb`)
Pass `--target-kb <n>` to cascade through: baseline → `optimize` → `medium` →
`heavy` → escalating frame-stride (3→4→6, stopping short of ~120ms/frame) →
escalating resize floor below `heavy`'s 256px (192→128→96px) as a last
resort. Prints every attempt and the resulting size; leaves whatever it
landed on saved even if the target couldn't be fully reached. Always re-check
the result (preview or otherwise) after a `--target-kb` pass — degradation is
cumulative, and the user should see the actual tradeoff, not just be told the
size hit the number.

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
**Per-file settings go in the manifest, shared settings go on the command
line.** `--compress optimize --edge-cleanup-erosion 1` alongside `--batch`
applies to every file unless an entry overrides it. But don't put
`protect_outline_color`/`bg_color` on the shared command line expecting it to
apply everywhere — those almost always differ art to art, so they belong
per-entry, found the normal way (`--analyze` each file first — batch mode
doesn't skip that step). Manifest keys match this script's flag names with
underscores instead of dashes.

One job failing doesn't abort the rest — it's reported in the summary table
at the end. Check that summary before telling the user the batch is done.
