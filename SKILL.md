---
name: gif-background-remover
description: Remove the background color from an animated GIF while protecting a specific interior region of the design (e.g. a white highlight inside a badge) even when that region is the same color as the background. Handles both antialiased vector icon/sticker art (the default assumption) and hard-edged pixel art (via --pixel-art, which avoids destructively eroding non-antialiased content). Also handles shrinking an animated GIF to fit a platform's file-size limit (e.g. Discord sticker/emoji uploads) via frame-rate reduction and gifsicle-based compression tiers, and batch-processing multiple GIFs from a manifest. Use when the user asks to remove/strip the background from a GIF, make a GIF transparent, cut out a GIF's background, or shrink/compress an animated GIF's file size.
---

# GIF Background Remover

**Skill version: v2.2.1** (previous: v2.2, v2.1, v2, v1). Versioning convention
(three-part, `v{major}.{minor}.{correction}` — Harkirat's explicit spec, applies
both to this internal version log AND to whatever gets said in the file handed
back to him after an edit, so the two never drift):
- **Major** (v2 -> v3): a reviewed, end-to-end-verified round with multiple
  serious fixes and/or new features/major functionality changes — like the
  v1 -> v2 jump below (a new detection algorithm, two regressions found and
  resolved, a root-cause fix, all in one verified batch).
- **Minor** (v2 -> v2.1): a single confirmed bug fix in the script itself that
  doesn't rise to major — e.g. "--edge-cleanup-erosion 0 was a real, silent,
  total-destruction bug" below.
- **Correction / very-minor / note** (v2.2 -> v2.2.1): a documentation-only
  addition, a clarifying note, or a fix too small to be its own minor bump —
  e.g. this bump itself (adding the GIF-partial-transparency finding and the
  gifski-as-compression-alternative note below, neither of which changed the
  script's code).

All three tiers still require the same bar before shipping: confirmed root
cause (for a fix) or confirmed-true (for a documentation note), and a real
fix/finding, not a guess or a workaround — the SIZE of the change determines
which tier, not the amount of rigor applied to verify it.

**Whenever this file is edited, always give Harkirat the latest full file**
(not a diff/patch to apply himself) **and keep the actual skill `name`
unchanged** in the frontmatter — only the version line and body content
change, the skill's identity/invocation name never does, so this never
breaks anything that already references it by name.

## When to use this
The user has an animated GIF and wants its background color (usually white)
removed / made transparent, while preserving some part of the interior
design that happens to be the same or a similar color.

## Check content type FIRST — this determines which defaults are even safe
This script's defaults (feathering on, `--edge-cleanup-erosion 2`, LANCZOS
resizing) assume the source has real antialiasing to clean up — true for
this skill's primary target, antialiased vector icon/sticker art, but
**actively destructive** on hard-edged content like pixel art. Confirmed
directly, not theoretically: run against a real synthetic pixel-art test
file, the DEFAULT settings eroded a 31px shape down to ZERO surviving
pixels (0% survival) — total destruction, not just a quality hit. There
was no antialiasing fringe for feathering/erosion to clean up, just real
art sitting exactly at the erosion boundary with nothing to spare.

**Before choosing settings, always check `--analyze`'s `edge_hardness`
field** (added specifically because of the case above):
```json
"edge_hardness": {"ratio": 0.0, "appears_hard_edged": true}
```
- `ratio` under ~0.5 → hard-edged (pixel art, or any flat art exported
  with no antialiasing) → use `--pixel-art` (bundles `--no-feather`,
  `--edge-cleanup-erosion 0`, and nearest-neighbor resizing into one
  flag — don't try to remember the three separately).
- `ratio` of a few units or more → real antialiasing present, this
  skill's normal defaults are correct as-is. Real measurements for
  reference: a genuine pixel-art test file measured 0.0; two real
  antialiased vector icon test files measured 4.5 and 17.6.
- The gap between these is large and clean in practice — this hasn't
  needed a judgment call so far, just reading the number.
- **Caveat, found on a real icon pack that was otherwise entirely normal
  vector art:** the ratio is sensitive to how much of the icon's perimeter
  is curved vs. straight, not purely to "is there antialiasing." A
  straight axis-aligned edge only needs a thin 1px antialiasing transition
  regardless of style, while a curved or diagonal edge needs a wider
  graduated band — so an icon dominated by straight lines (a trash can, a
  rectangular sweep effect) can score LOW (e.g. 0.17-0.39, under the ~0.5
  threshold) despite being entirely ordinary antialiased vector art from the
  same consistent design system as icons in the same set scoring 2-17+.
  Confirmed directly: two icons from an otherwise uniform icon pack
  triggered the hard-edged threshold this way, and applying `--pixel-art`
  to them would have been wrong. When a ratio comes back hard-edged but
  the icon is visually part of a set with other icons that scored
  normally, or the source is a professional/exported vector asset rather
  than something hand-drawn pixel-by-pixel, look at it directly (zoom in)
  before trusting the ratio alone -- geometry-heavy icons are the false-
  positive case to watch for.

If content doesn't fit either bucket well — e.g. genuine photographic or
full-bleed content with no distinguishable background at all, where
`detect_bg_color`'s corner-sampling approach doesn't apply (this shows up
as the "four corner pixels don't all agree" warning, or as a background
color that's clearly wrong for the actual image) — that's a real boundary
of what this script does. It performs chroma-key style background removal
(distinguish a background color from a foreground design), not general
image segmentation (distinguish a subject from an arbitrary/non-uniform
background, which needs a fundamentally different approach, e.g. an ML
matting model). Say so plainly rather than trying to force chroma-key
settings to work on content that structurally doesn't have a keyable
background.

## Workflow: infer first, then confirm — don't just ask the user upfront

Don't open by asking the user to specify the background color and protected
region from scratch. Instead:

### 1. Run analysis first
```
python scripts/remove_gif_background.py <input.gif> --analyze
```
This scans the GIF and returns JSON with:
- `detected_bg_color` — auto-sampled from the corner pixels.
- `candidate_regions` — background-colored areas that are enclosed by other
  colors somewhere in the animation, each with:
  - `enclosure_ratio` — the fraction of sampled frames where it's actually
    enclosed (not connected to the image border).
  - `likely_intentional_design` — `true` when `enclosure_ratio >= 0.9`
    (consistently enclosed → almost certainly a real design element, e.g.
    a highlight inside a ring). `false` when only occasionally enclosed
    (e.g. an animated element like a moving swoosh temporarily cutting off
    a pocket of real background — this should stay transparent).
  - `suggested_protect_region` — a ready-to-use `circle:cx,cy,r` value.
  - `candidate_outline_color` — a guess at a bordering outline color, if
    one exists nearby (not always reliable — treat as a hint, not a fact).

This step also prints warnings to stderr worth reading before proceeding:
- If the four corner pixels don't unanimously agree on a background color,
  auto-detection may have picked the wrong one (e.g. a diagonal
  composition) — double check `detected_bg_color` looks right.
- If the source GIF already has its own transparency index, its
  pre-existing transparent pixels are automatically carried through as
  transparent in the output, regardless of this script's own background-
  color detection (confirmed with a real test: a genuinely transparent
  hole no longer comes back opaque with a garbage fill color, which is
  what naive RGB-flattening used to produce before this was fixed). The
  `source_has_pre_existing_transparency` field in `--analyze`'s report
  and an informational NOTE printed during processing both flag when this
  is happening — no action needed, just awareness.

Each candidate region now also reports:
- `outline_color_verified` — `true` only if `candidate_outline_color` was
  actually simulated (built its mask, ran the same `binary_fill_holes`
  used at process time, checked it truly encloses the region) rather than
  just guessed from nearby pixels. Treat `candidate_outline_color` as
  unusable when this is `false` — see step 3 below for what to do instead.
- `circularity_ratio` (0–1) and `circle_region_safe` — how well a plain
  circle would approximate the region's true shape. Low values mean
  scalloped/pointed/star-shaped/irregular outlines (badge rosettes, gems,
  stars...), where `--protect-region circle:...` is a poor fit. See the
  next section for why this matters and what to do instead.

### 2. Form a recommendation, then confirm with the user in one short message
First, check `edge_hardness` (see "Check content type FIRST" above) — if
it comes back hard-edged, that changes the recommendation itself (mention
`--pixel-art` up front) rather than just being a footnote after the fact.

Summarize what was found in plain language, e.g.:
> "Looks like white is the background. There's also a white/light area in
> the middle of the badge enclosed by a ring — that's enclosed in 100% of
> frames, so it looks intentional and I'd keep it. There's also a gap
> between the ribbon tails that's occasionally enclosed by an animated
> swoosh (~20% of frames) — that looks incidental, so I'd treat it as
> background. Sound right, or should I handle either differently?"

Use `ask_user_input_v0` for this when there are multiple regions to confirm
(one question, options like "Keep it opaque" / "Make it transparent" per
region) rather than a wall of text. Only skip confirmation entirely if
there's exactly one obvious candidate region with `enclosure_ratio` at or
near 1.0 and the user's request already implied preserving an interior
highlight (use judgment — a quick confirmation is cheap and prevents
redoing work).

**Multiple candidate regions with different outline colors are common on
icons with more than one enclosed highlight** (e.g. a badge with both a
ring interior AND a separate gear/hole cutout, each outlined in a
different color) — a real case, not a hypothetical. `--analyze` reports
each region independently with its own `candidate_outline_color`; when two
or more come back `outline_color_verified: true`, do NOT run the script
once per color (there's no way to compose separate runs — the second run
has no memory of what the first one protected, so it would just remove
whatever the first run protected but the second doesn't recognize). Pass
`--protect-outline-color` ONE time with all the verified colors joined by
a comma (e.g. `--protect-outline-color c8dcf0,8cb4f0`) — the script unions
every color's enclosed region in a single pass. Same idea for
`--protect-region` if you ever end up there for more than one region, but
join those with `;` instead of `,` since `,` is already used inside a
single region's own coordinates.

### 3. Run the real processing with confirmed settings

**`--protect-outline-color` is the default choice. `--protect-region` is a
last resort, not an alternative style — reach for it only when there is
genuinely no usable outline color, and even then treat the result as
provisional until step-by-step verified (below).**

Why so strong: `--protect-region circle:cx,cy,r` assumes the true protected
shape IS a circle of that exact radius in every direction from the center.
Almost no real icon interior actually is. A badge/rosette ring is
scalloped (the true boundary can easily range e.g. 86–183px from center
depending on direction, even though it "looks roughly round" at a glance);
a gem/diamond has a pointed apex; stars, seals, and most decorative icon
interiors are similarly non-circular. Picking one fixed radius means:
- In directions where the true edge is CLOSER than that radius, the circle
  overshoots past the real boundary and keeps background-colored pixels
  opaque that should have been removed — a bleed/halo that sits flush
  against the art (easy to mistake for part of the design at a glance).
- In directions where the true edge is FARTHER than that radius, the
  circle falls short and clips into what should have been protected,
  leaving a notch or gap.
This is not a hypothetical: it happened twice in the same session on two
different icons that both "looked round enough" at a glance — a badge
rosette (scalloped ring, true radius 86–183px) rendered with a fixed
radius-126 circle left a visible extra white lobe bulging past the ring on
one side, and a diamond gem's pointed white facet rendered as a bounding
circle left a large stray white disc floating in the background above the
diamond's point. Both looked fine in a quick glance at the preview
thumbnail and were only caught on user report / closer pixel inspection.
`rect:x,y,w,h` has the same failure mode for anything not truly
axis-aligned rectangular.

So, concretely:
- **Always try `--protect-outline-color` first**, using the analyzed
  `candidate_outline_color` IF `outline_color_verified` is `true` for that
  region. `true` means the script already simulated the exact fill-holes
  logic `--protect-outline-color` uses at process time and confirmed that
  color's closed shape actually encloses the region — this is a real
  check, not a guess, so it's safe to use directly without re-deriving the
  color yourself.
- **If `outline_color_verified` is `false`** (a hex value may still be
  printed, but treat it as unusable): don't fall back to
  `--protect-region` yet. Instead, open the source frame yourself
  (`view` an extracted frame, or zoom into one) and identify the true
  enclosing outline color by eye — sample a pixel a short distance outward
  from the protected area in a couple of different directions and check
  they agree. This is exactly how the badge/rosette case above was
  actually fixed: the true navy ring color was found by sampling pixels at
  increasing radius from the interior's center until the color stabilized,
  then used directly with `--protect-outline-color`. This one extra manual
  step is far cheaper than debugging a bleed after the fact.
- **Only use `--protect-region`** when there is truly no enclosing outline
  in the art (a soft glow/gradient with no hard edge, for instance) —
  and even then, check `circularity_ratio` / `circle_region_safe` first.
  If `circle_region_safe` is `false`, a circle is a known-poor fit; either
  use `rect:` if the true shape is actually axis-aligned rectangular, or
  warn the user this region's protection may not be pixel-perfect and
  needs extra-careful verification (below) before delivering.
- For a region the user wants left as background: do nothing extra — it's
  already removed by default (nothing outside the protected region survives).
- If `--bg-color` wasn't confirmed differently, just omit it — the script
  auto-detects it the same way `--analyze` did.
- **Edge feathering is ON by default; cropping is NOT.** Feathering is a
  pure quality improvement with no tradeoff, so it stays on unconditionally
  unless the user wants the old hard-edge look. Cropping, resizing,
  frame-dropping, and gifsicle are all now bundled into the opt-in
  `--compress` tiers (see "File-size optimization" below) rather than
  applied by default — a plain run changes nothing about the canvas, frame
  count, or timing versus the source.

```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    [--bg-color <hex>] \
    [--protect-outline-color <hex[,hex,...]>] \
    [--protect-region circle:cx,cy,r | rect:x,y,w,h [;more-regions]] \
    [--tolerance 15] [--outline-tolerance 40] \
    [--feather-band-multiplier 4.0] [--no-feather] \
    [--edge-cleanup-erosion 2] [--pixel-art] \
    [--crop] [--frame-stride 1] [--resize-max-dim <px>] \
    [--compress optimize|medium|heavy] \
    [--quantizer pil|pngquant] \
    [--target-kb <n>] [--preview <path.png>]
```

For processing several GIFs in one invocation, see `--batch <manifest.json>`
in its own subsection further below ("Batch processing multiple GIFs") —
different mechanism (a JSON manifest, not more CLI flags), so it isn't in
the flag list above.

`--crop`, `--frame-stride`, `--resize-max-dim`, `--compress`, and
`--target-kb` are all about
file size and covered in their own section below ("File-size
optimization") — none of them apply by default; a plain run is just
background removal (plus the always-on feathering quality improvement).

**Edge feathering** (default on): a hard color-distance cutoff leaves a
jagged/staircase boundary wherever the source art had smooth antialiasing
against the background, since GIF only supports on/off transparency per
pixel. The script instead estimates a continuous alpha in a transition
band around the cutoff (color-unmixing against the background), de-fringes
those edge pixels (removes background color bleed from their RGB), and
converts the band to a binary transparent/opaque pattern using a spatially
fixed Bayer dither instead of one hard threshold — so the edge reads as
soft rather than blocky, without flickering between animation frames. Use
`--feather-band-multiplier` (default 4.0, i.e. 4x `--tolerance`) to widen
or narrow the transition band if the edge still looks too hard or too soft.
Pass `--no-feather` only if the user explicitly wants the old hard-cutoff
behavior (e.g. for pixel-art style GIFs where crisp edges are the point).

**Crop** (default OFF): standalone `--crop` crops to the transparent
bounding box without any of the other tier steps. Any `--compress` tier
also includes cropping automatically regardless of this flag — it doesn't
need to be passed alongside `--compress`.

**Output size reporting**: every run prints the final dimensions and file
size in KB to stderr automatically — use this instead of a separate `ls`/
`os.path.getsize` check, and use it as the signal for whether file-size
optimization (below) is worth raising with the user.

**Preview contact sheet** (`--preview <path.png>`, off by default): saves
a single PNG with a handful of frames (evenly sampled across the
animation) composited over a checkerboard and laid out side by side. Use
this instead of hand-rolling a compositing script for verification — pass
it on the same run that produces the final GIF so you get it for free.

## Delivery file naming, when reprocessing the same source
If a user reports a problem with a delivered result and asks for a fix,
the corrected file's name should make its iteration obvious rather than
silently overwriting the same filename: first attempt is
`name_transparent.gif`, a second pass after a reported fix is
`name_transparent_v2.gif`, a third `name_transparent_v3.gif`, and so on.
This is about the delivered OUTPUT file naming, not the skill's own
version number above — the two counters are independent (a single output
file could go through several reprocessing rounds within one skill
version, or vice versa).

## Verification (always do this before delivering the result)
1. Composite a handful of frames (first, middle, last, plus any frame
   flagged with animation near a protected region) over a dark background
   and visually confirm — `--preview <path.png>` does this automatically
   in one run; use it instead of writing a one-off compositing script:
   - The intended background is fully transparent.
   - The protected interior region is still fully opaque with no holes.
   - Any region the user chose to treat as background is fully transparent
     in every frame, not just some.
   - Edges look soft/dithered rather than jagged (zoom into a diagonal or
     curved edge at high magnification to check — a good spot-check is
     cropping a small region and resizing it up with nearest-neighbor).
   - **Zoom into a straight edge (not just curved/diagonal ones) at high
     magnification and check the outermost ring of opaque pixels is the
     TRUE art color, not a lighter/tinted fringe color.** Background
     color-unmixing doesn't perfectly recover the true foreground color on
     every antialiased boundary pixel, and this shows up most obviously as
     a thin mis-colored line along a long straight edge (e.g. the side of
     a rectangular icon) where it reads as a deliberate stray line rather
     than noise — a real case that reached a user before being caught. The
     default `--edge-cleanup-erosion 2` (applied unconditionally whenever
     feathering is on, independent of any `--compress` tier) exists
     specifically to prevent this; if it's still visible, don't just crank
     the erosion further blindly -- pull actual pixel values at the edge
     (e.g. sample the last few opaque pixels along several rows/columns)
     to confirm it's actually gone rather than eyeballing a thumbnail.
   - **If the source canvas is small (roughly under 200px on its shorter
     side) — e.g. a Discord emoji-sized GIF that's small to begin with,
     not one this script resized down — check that fine details (thin
     strokes, small dots, small gaps between shapes) survived the default
     erosion.** `--edge-cleanup-erosion`'s default of 2px is a FIXED pixel
     count, not scaled to resolution: a detail that's a comfortable 16px
     across on a 640px icon is only ~3px across on a 128px one, and 2px of
     erosion on a 3px-wide detail can erase most or all of it. The script
     prints its own warning to stderr when this situation is detected
     (small canvas + non-zero erosion) — don't ignore it. If a detail did
     get eaten, redo with `--edge-cleanup-erosion 1` or `0` rather than
     trying to patch it after the fact.
2. **If you used `--protect-region` (circle or rect) anywhere — not just
   outline-color — specifically look for a bulge, halo, disc, or straight
   edge that doesn't follow the artwork's own silhouette.** This is the
   signature of a circle/rect protect-region not matching the true shape,
   and it is easy to miss on a quick glance: in this exact skill's own
   development, a large stray white disc sitting behind a diamond icon's
   point, and a smooth extra lobe bulging past one side of a scalloped
   badge ring, BOTH slipped past an initial visual check of the preview
   thumbnail and were only caught afterward. Don't just glance at the
   thumbnail — for each `--protect-region` use, do at least one of:
   - Composite the frame over a plain dark background (not checkerboard —
     checkerboard can visually camouflage a soft-edged bleed) and check
     the protected area's outline traces the actual art, not a smooth
     circular/rectangular arc anywhere.
   - Or, mechanically: reload the output, take the alpha channel, and
     check that every opaque pixel is either part of a single connected
     component matching the visible art (no stray disconnected blobs), and
     that the shape doesn't extend past where the source art's own
     outline color exists nearby. A quick way: for several angles from the
     protect-region's center, walk outward in the ORIGINAL source frame
     and find where the source art's outline color actually starts; compare
     that against the radius you used. If they disagree by more than a few
     pixels in any direction, the circle doesn't match and you should
     switch to `--protect-outline-color` (see step 3 above).
3. **Confirm every frame's duration in the output matches the source
   exactly, reading them the RIGHT way.** GIFs frequently use variable
   per-frame timing (a real example: mostly 20ms/frame with the first
   frame at 140ms, NOT a uniform value), so don't assume a constant. There
   is a well-known Pillow footgun here that produced completely wrong
   numbers during this skill's own development, so it's worth stating
   explicitly:
   - **`PIL.ImageSequence.Iterator` yields the SAME underlying image
     object every time**, just seeked to a new position — it does not
     return independent per-frame copies. `frames = list(ImageSequence.
     Iterator(im)); [f.info['duration'] for f in frames]` looks reasonable
     but is WRONG: by the time the second line runs, every `f` is the same
     object, now seeked to the last frame, so every entry silently returns
     the LAST frame's duration. This produced a totally fabricated "total
     animation length" that was off by more than 10x in one real case, and
     was reported to a user before being caught.
   - The correct pattern reads `.info['duration']` *immediately* after each
     `.seek(i)`, in the same loop iteration — never after materializing a
     list of frames first:
     ```python
     im = Image.open(path)
     durations = []
     for i in range(im.n_frames):
         im.seek(i)
         durations.append(im.info.get('duration', 100))
     ```
   - For a fully independent, Pillow-bug-proof ground truth (worth using
     whenever duration correctness actually matters for a claim you're
     about to make to the user), parse the GIF's raw Graphic Control
     Extension delay bytes directly instead of trusting any decoder:
     each `0x21 0xF9` block has delay as a little-endian 16-bit value at
     offset+4 in centiseconds; multiply by 10 for milliseconds. This is
     what actually resolved the discrepancy above.
   - Compare the resulting list between input and output exactly — not
     just the total — since folded/dropped-frame durations should match a
     specific per-frame pattern, not just sum correctly by coincidence.
4. If a `--compress` tier or standalone `--crop` was used, confirm the
   crop removed the intended blank margin without clipping any part of
   the design — check the reported `WxH -> W'xH'` line the script prints
   to stderr against expectations. If a tier's resize step also ran,
   check the final dimensions match the expected max-side target too.
5. **When investigating a reported "this part flickers / goes transparent
   when it shouldn't" complaint, don't sample pixels by bounding box alone
   — use the actual geometric interior mask.** A candidate region's
   reported `bbox_xyxy` is a rectangle; the real enclosed shape usually
   isn't, so pixels that are white-in-source-and-inside-the-bbox can
   still be legitimate background sitting just outside the true enclosed
   area (e.g. the gap between two nearby design elements that both fall
   inside one bounding rectangle). Checking those naively produces a
   false "it's flickering!" signal — this happened for real while
   debugging a user report, where a bbox-based check showed opacity
   swinging from 0.0 to 1.0 across frames, looking exactly like a bug,
   until re-checking with the proper mask (`binary_fill_holes` on the
   outline-color mask, same as the actual processing code) showed the
   TRUE interior pixels were 100% opaque in every single frame — no bug
   at all. Reproduce the actual protection logic (fill-holes on the
   outline mask) rather than approximating it with a bounding box when
   the distinction matters for a real diagnosis, not just a rough check.
6. If anything fails verification, adjust `--tolerance` /
   `--outline-tolerance` / `--feather-band-multiplier` or the protect
   region and rerun rather than patching the output gif directly.

## File-size optimization: default vs. named tiers

**The default output is plain background removal, plus one correctness
fix, nothing else.** No crop, no resize, no frame-dropping, no gifsicle
pass — every original frame and its exact original timing survive
untouched, at the original canvas size. The one exception is edge cleanup
erosion (`--edge-cleanup-erosion`, default 2px): unlike everything else in
this list, that's not a size/compression tradeoff, it's fixing a real
color artifact in the feathering math itself (see Verification above), so
it applies whether or not any `--compress` tier is used. A plain "remove
the background" request should get exactly that; don't apply any tier
below unless the user asks, or there's a clear signal a platform limit is
in play (see below).

### When to raise file-size optimization at all
Use judgment about whether to bring it up — don't ask by default on every
request, but do ask when the conversation gives a reasonable signal it
might matter:
- The user mentioned a platform with known constraints (Discord stickers/
  emojis, Slack emojis, a CMS with an upload limit, etc.).
- The printed size is large enough that a common constraint (e.g.
  Discord's 256KB sticker limit — the exact error is `[50138]: Failed to
  resize asset below the maximum size: 262144`, so 262144 bytes = 256KB is
  the real ceiling there, not the 512KB sometimes quoted for other asset
  types) would plausibly be an issue.
- The user's phrasing suggests the GIF is going somewhere specific ("for
  my Discord server", "as a sticker", "to embed in the app").

If none of those signals are present, just deliver the plain file without
asking. When you do ask, keep it short and concrete, e.g. "This came out
to 2.7 MB — want me to optimize it for a specific target, like Discord's
256KB sticker limit?"

### The three named tiers (`--compress optimize|medium|heavy`)
Each tier is a fixed, tested bundle — not independent flags to mix by
hand. `medium` and `heavy` both include every step from `optimize`, then
add more:

| Step | `optimize` | `medium` | `heavy` |
|---|---|---|---|
| Frame-stride | — (every frame kept) | 2 | 2 |
| Crop to transparent bounds | ✓ | ✓ | ✓ |
| Resize to fit (longer side) | 512px | 512px | **256px** |
| 1px edge erosion | ✓ | ✓ | ✓ |
| `gifsicle -O3` | ✓ | ✓ | ✓ |
| `gifsicle --lossy` | — | 30 | 80 |
| Color palette | native | **200 colors** | **128 colors** |
| Dithering | — | Floyd-Steinberg | Floyd-Steinberg |

`optimize` deliberately does NOT drop frames — it's the tier for someone
who wants a smaller file with zero motion-quality tradeoff (crop, resize,
erosion, and lossless gifsicle only touch redundant/invisible data).
Frame-stride is a real, visible tradeoff (choppier playback, especially on
fast source animations), so it's reserved for `medium` and `heavy`, where
the user has already signaled they want more aggressive size reduction.
If `optimize`'s frame-preserving steps alone aren't enough, step up to
`medium` rather than reaching for standalone `--frame-stride` on top of
`optimize`.

`medium`'s 200-color cap exists specifically so its dithering does
something: confirmed directly that gifsicle's `--dither` is a no-op unless
the palette is actually being reduced (byte-identical output with/without
it when only `--lossy` was set, no `-k`) — an earlier version of this tier
specified dithering with no color cap, which meant it silently did
nothing. 200 is a deliberately light touch: most of this skill's source
art uses well under 200 colors in the interior even before any reduction,
so this mainly dithers the antialiased/feathered edge transition (which
commonly DOES exceed 200 distinct shades from the alpha blending) rather
than visibly flattening the interior art the way `heavy`'s 128-color cap
can.

**But "mainly the edge transition" can still mean "most of a thin
element,"** and that's a real failure mode, not a hypothetical: a thin
design element (a lightning bolt, a small icon detail with a high
edge-to-area ratio) is proportionally MOSTLY edge transition — there's
barely any "flat interior" for a thin stroke, so dithering that's
lightweight relative to a bulky shape's interior can still visibly wreck
a thin one. Confirmed directly on a real animated lightning-bolt icon
element: `medium` tier made it visibly grainy/noisy with edges that no
longer matched the source art, measured concretely as 100+ unique colors
in that specific region vs. 3 with `optimize` on identical source content.
If someone reports fine details looking "grainy," "messy," or like they
"don't match the original" after `medium`/`heavy`, don't reach for a
different dithering setting or a color-cap tweak — step DOWN to `optimize`
first and see if that alone resolves it (it also keeps every frame by
default, so it's often the single fix for both a graininess complaint and
a choppiness complaint at once).

Why each piece, in the order they're actually applied (frame-stride → crop
→ resize → erosion → render → gifsicle; note this differs slightly from
the order they're listed above, because gifsicle can only run on an
already-encoded file, so it's always technically last regardless of tier;
`optimize` simply skips the frame-stride step since its default is 1):

- **Frame-stride 2 (`medium`/`heavy` only)**, same technique as the
  standalone flag below — folds dropped frames' durations into kept
  frames, so total playback length is preserved (choppier motion, not
  sped-up). This was empirically the single biggest lever for real fast
  icon/sticker animations (see the standalone section below for the
  measured case) — but it's also the one step in these tiers that's a
  genuine perceptual tradeoff rather than a free size win, which is why
  it's held back from `optimize` and only applies once the user has opted
  into `medium` or `heavy`.
- **Resize-to-fit** scales the LONGER dimension down to the target and
  scales the other proportionally — it only ever downscales, never
  upscales an already-small source. `heavy`'s 256px override (rather than
  512) is what makes it meaningfully smaller than `medium` beyond just the
  lossy/color settings.
- **1px edge erosion** shaves the outermost ring of opaque pixels off
  every frame to fully transparent (verified on a synthetic 20×20 square:
  erodes to exactly 18×18, uniformly on all sides including corners).
  This targets "rugged edges" — the boundary ring is where feathering
  dither and resize resampling fuzz both concentrate, so trimming it
  gives a visibly cleaner silhouette, especially after the resize step
  above has already softened that edge once.
- **`--lossy`** lets gifsicle alter pixel values slightly to improve
  run-length compressibility — `30` is mild, `80` is aggressive but still
  generally clean for flat/icon-style art (this skill's typical use case,
  not photographic content where 80 would show more artifacting).
- **128-color palette + Floyd-Steinberg (`heavy` only)**: Floyd-Steinberg
  is the right dithering choice here over gifsicle's other modes
  (`ordered`, `halftone`, `o8x8`) because it's an error-diffusion
  algorithm that spreads quantization error into neighboring pixels,
  reading as smooth noise rather than a visible repeating pattern —
  important specifically because this skill's own edge feathering already
  produces soft antialiased gradients, and gradients are exactly where
  ordered/pattern dithering looks worst (visible grid artifacts).

Practical notes:
- All three tiers only touch RGB/frame/canvas data in ways that keep alpha
  clean — confirmed directly (binary 0/255 alpha throughout, transparent
  corners, no stray artifacts) on a real test file at every tier.
- An explicit `--frame-stride N` overrides a tier's own default stride (1
  for `optimize`, 2 for `medium`/`heavy`) rather than stacking with it
  (e.g. `--compress heavy --frame-stride 3` uses 3, not 2-then-3; and
  `--compress optimize --frame-stride 2` will drop frames even though
  `optimize` doesn't by default).
- If `gifsicle` isn't available in the environment, the non-gifsicle parts
  of the tier (crop/stride/resize/erosion) still apply, with a clear
  warning that the gifsicle-dependent size reduction didn't happen —
  never a silent partial failure or a hard error.
- Always look at the actual result after applying a tier (preview or
  otherwise) rather than assuming — `heavy` in particular is a real
  quality tradeoff (256px cap, 128 colors), appropriate for a strict
  platform limit but not something to reach for by default.
- **The GIF palette is built ONCE across all frames combined, not
  independently per frame.** This matters more than it sounds: for
  animations where most of the frame is static and only a small part
  moves (e.g. a spinning gear on an otherwise-still icon), an
  independently-quantized per-frame palette can assign a DIFFERENT
  palette index to the exact same visual color in consecutive frames
  (the moving part shifts the frame's overall color histogram slightly,
  nudging the adaptive quantizer's choices even for unrelated static
  pixels). That makes every pixel look "changed" to the GIF encoder even
  when nothing moved, defeating disposal-based frame-diffing and
  producing a MUCH larger file than the same animation with a consistent
  index for a given color — confirmed on a real test case where fixing
  this dropped output size by ~40% and brought it below the original
  source file's size, whereas the per-frame-palette version had been
  ~50% LARGER than the source despite otherwise-identical processing. If
  a future edit to `render_frames_to_gif` ever reintroduces a per-frame
  `convert('P', palette=Image.ADAPTIVE, ...)` call instead of quantizing
  every frame against one shared palette, treat that as a regression.

### The standalone lever: frame-rate reduction (`--frame-stride`)
Works independently of any tier too — useful when the user wants ONLY the
frame-drop treatment without cropping/resizing/gifsicle (a real prior
request: "do the frame stuff but don't do the compression"):

```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    --protect-outline-color <hex> --frame-stride 2
```

- Drops every Nth frame and **folds the dropped frames' durations into the
  kept frame**, so total playback length is exactly preserved — the
  animation gets choppier (less in-between motion), not faster. This
  matters: some third-party tools drop frames WITHOUT this compensation,
  which visibly speeds up the animation; always verify the folding
  actually happened (see verification step 3 above) before trusting any
  tool's frame-drop output, including this script's.
- A real case: a 161-frame badge animation (mostly 20ms/frame, 3.6s total)
  dropped to 81 frames at stride 2 cut file size roughly in half (1868KB →
  994KB) with imperceptible visual difference, because the source was
  massively over-sampled relative to what the eye needs for that motion.
- Won't silently push this too far: it warns (and both `--target-kb` and
  the tiers' own stride escalation stop advancing) once the average
  post-fold delay exceeds ~120ms/frame (~8fps), since beyond that dropped
  frames start reading as genuinely choppy rather than just marginally
  less smooth. If the source is already slow (say 100ms+/frame), mention
  this tradeoff to the user explicitly rather than applying it silently.
- **`--frame-stride 1` explicitly forces keeping every frame even when
  combined with a tier whose own default would drop frames** (e.g.
  `--compress medium --frame-stride 1` gets medium's crop/resize/lossy/
  dither treatment but zero frame-dropping). This is worth knowing about
  explicitly: a bug existed where `1` was indistinguishable from "flag not
  passed at all" (both looked like the argparse default), so this exact
  invocation silently fell back to the tier's own stride instead of
  honoring the explicit `1` -- fixed by giving the flag a `None` default
  instead of `1`, so "unset" and "explicitly 1" are no longer conflated.
  If a future edit to `--frame-stride`'s argparse definition or the
  `stride_override` resolution logic in `apply_tier`/`process()`
  reintroduces a truthy check like `stride_override and stride_override >
  1` instead of `stride_override is not None`, that's this bug coming
  back.
- **A real, common reason to want this combo:** medium/heavy's Floyd-
  Steinberg dithering can look genuinely bad on fine vector linework —
  thin strokes (a lightning bolt, small icon details) came back visibly
  grainy/noisy with edges that no longer matched the source design,
  confirmed directly on a real icon (a lightning-bolt animation element)
  by comparing unique-color counts in the same region: over 100 with
  dithering vs. 3 without, on identical source content. If someone reports
  "grainy," "messy," or "doesn't match the original" specifically on thin
  details after a `medium`/`heavy` pass, dithering is the first suspect --
  try `optimize` (no dithering, no forced color cap) instead of reaching
  for more aggressive settings, especially if they also want every frame
  kept (`optimize` defaults to no frame-drop anyway, so this is often a
  clean single fix for both complaints at once: switch tiers down, not
  just drop `--frame-stride`).

### The standalone lever: arbitrary resize target (`--resize-max-dim`)
The two named tiers only bake in 512px (`optimize`/`medium`) and 256px
(`heavy`) as resize targets. For anything else — a platform that wants
exactly 128px, say — use this instead of reaching for a tier that happens
to be close:

```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    --protect-outline-color <hex> --crop --resize-max-dim 128
```

- Fits the LONGER dimension to the given size, preserving aspect ratio,
  same as the tiers' own resize step — only ever downscales, never
  upscales an already-small source.
- Always followed by the same 1px post-resize cleanup erosion the tiers
  use, to remove fuzz the LANCZOS resampling reintroduces at the boundary.
- Works standalone (no tier, no gifsicle pass — just crop if requested +
  resize + cleanup) or combined with a tier, where it overrides that
  tier's own resize target rather than stacking with it (e.g.
  `--compress optimize --resize-max-dim 128` still gets `optimize`'s
  lossless gifsicle pass, just at 128px instead of 512px).
- Doesn't crop on its own — pair with `--crop` (or a tier, which crops
  automatically) if the source has transparent margin you want gone
  before the resize target is applied to it.

### Automatic target-fitting (`--target-kb`)
If the user gives a specific KB target, pass `--target-kb <n>` and let the
script cascade through the tiers automatically:
1. Baseline (plain background removal, nothing else) — check.
2. `optimize` tier — check.
3. `medium` tier — check.
4. `heavy` tier — check.
5. Still over target: keep `heavy`'s settings but escalate frame-stride
   further (3 → 4 → 6, stopping if average delay would exceed ~120ms/frame)
   — check after each.
6. Still over target: keep escalating past `heavy`'s 256px floor (192 →
   128 → 96px) as an absolute last resort — check after each.

This means `--target-kb` results are always consistent with what
`--compress` would produce at whichever stage it stops on, rather than an
independent, undocumented combination of levers. It prints every attempt
and the resulting size, and leaves whatever it landed on saved at the
output path even if the target couldn't be fully reached. Always re-run
`--preview` (or otherwise check the result) after a `--target-kb` pass —
degradation is cumulative across stages, and the user should see the
actual trade-off before you consider the task done, not just be told the
size hit the number.

## Batch processing multiple GIFs
For several GIFs in one invocation, use `--batch <manifest.json>` instead
of separate commands:

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

**The split that matters: per-file settings go in the manifest, shared
settings go on the command line.** `--compress optimize --edge-cleanup-
erosion 1` alongside `--batch` applies to every file in the manifest
unless a specific entry overrides it. But do NOT put
`protect_outline_color`/`bg_color` on the shared command line expecting it
to apply to every file — those almost always differ art to art (verified
throughout this skill's own real usage: every icon processed needed its
own analyzed outline color), so they belong per-entry in the manifest,
found the normal way (`--analyze` each file first, same as the
single-file workflow — batch mode doesn't skip that step, it just avoids
re-typing the shared quality flags once you know each file's settings).
Manifest keys match this script's own flag names with underscores instead
of dashes (`protect_outline_color`, not `protect-outline-color`).

One job failing (bad path, conflicting settings, etc.) doesn't abort the
rest — it's reported in the summary table at the end and every other job
still completes. Check that summary before telling the user the batch is
done; don't assume all-succeeded just because the command exited cleanly.

## Protected regions can flicker if an animated element crosses the
outline — partially mitigated, still has a known gap, and the history of
attempted fixes here matters
This started as a real, confirmed bug reported by a user, went through
THREE implementations, and the current one is deliberately the most
conservative of the three after the other two caused real regressions on
real files. Read this before touching `build_protected_masks_robust`
again.

**The mechanism:** `--protect-outline-color` works by finding all pixels
matching that color, then running `binary_fill_holes` to identify what's
enclosed. This requires the outline to form a fully CLOSED ring in that
specific frame. If any other animated design element (confirmed real
cases: a wifi-signal pulse; a "wipe" sweep effect) happens to visually
cross or overlap the outline at some frames, it locally replaces outline
pixels with its own color, punching a gap — and `binary_fill_holes`
doesn't degrade gracefully, it can leak interior out. Symptom: the
protected region intermittently goes transparent or shows a gap.

**Attempt 1 (reverted): whole-frame substitution, gated on 70% of
median area.** Flag frames whose color-mask area drops under 70% of that
color's own median, substitute the WHOLE mask from the nearest
non-anomalous frame. Confirmed to fix a severe case (wifi pulse breaking
a cloud's enclosure on 16/120 frames, area dropping to ~56% of median)
without breaking a legitimately-animated icon (a rotating design element
that stays within +/-0.35% of its own median area throughout). Confirmed
gap: MISSES smaller, localized holes that don't move the aggregate area
much — a real case had a clearly visible hole (source solid white, output
transparent) on frames still at 93-95% of median, comfortably above even
a 90% threshold.

**Attempt 2 (reverted): local connected-component patching against a
majority-vote reference, gated at 98% of median.** Built a per-pixel
majority-vote reference shape from near-full-size frames, and for any
frame below the 98% gate, patched in specific missing connected
components (over a 50px floor) rather than substituting the whole frame.
This DID fix the attempt-1 gap in isolated testing — verified the
specific reported hole closed, verified the previously-known rotating-
icon case still correctly stayed ungated. But delivered to the user
end-to-end across a full batch, it produced a NEW, different regression
("random white parts appearing behind the gifs") that was not caught by
the isolated per-case testing done before shipping it. The exact
mechanism was not pinned down before reverting — the decision was to stop
layering increasingly complex, incompletely-understood fixes on real
user files rather than keep guessing. **The lesson: verifying a fix
against the specific case that motivated it, and against one or two known
prior regressions, is not the same as verifying it end-to-end across a
full real batch.** Both matter; only doing the former is how this
shipped a second regression.

**Current state (attempt 1, restored):** back to whole-frame substitution
at a 70%-of-median gate. This is the version with actual confirmed
history of not causing a regression. Known limitation, accepted
deliberately rather than silently: it will NOT catch a hole on a frame
whose aggregate area is still 70%+ of median, even if that hole is
visibly real (confirmed real example above at 93-95%). If asked to fix
this gap again, do NOT reach straight for reference-diffing without a
full end-to-end batch re-verification pass (all files this skill has
touched, not just the one motivating case) before calling it done or
telling the user it's fixed.

**Why `--analyze` doesn't catch this ahead of time:** `outline_color_
verified` only checks the candidate color against a SINGLE frame (the
first sampled one). That result gets applied uniformly across every frame
during real processing, with no check that the color reliably encloses
the region on frames it was never tested against.

**Practical guidance for verification and reporting:**
- If a user reports a protected area "flashing," a gap that
  "disappears," or white/background patches appearing where they
  shouldn't, check the NOTE in stderr output first to see whether the
  current (conservative) fix fired, and don't assume "no NOTE" means "no
  problem" — the 70% gate has a known blind spot.
- Before concluding a specific reported artifact isn't reproducible,
  double- and triple-check the exact crop/coordinate offset used for any
  diagnostic comparison — confirmed directly, an incorrectly-assumed crop
  offset (derived from frame-0-only foreground detection instead of the
  TRUE union-of-all-frames crop this script actually uses) produced a
  spurious "artifact" in one location while masking a real one elsewhere.
  Re-derive the offset from the script's own logged crop coordinates.
- Frame-number correspondence between a user's own sprite-sheet/export
  tool and this script's own frame indexing is NOT guaranteed to be a
  simple fixed offset — confirmed needing composite-and-MSE matching
  against a candidate frame range to find the true correspondence, and
  the offset drifted slightly (+4 vs +5) across the same sprite sheet,
  consistent with accumulated rounding in a hand-estimated row pitch.
  Don't assume "the user's frame 40" is "this script's frame 40."
- Any future change to this function needs verification against: (a) the
  specific case motivating the change, (b) every prior confirmed
  regression case (the rotating-icon false-positive, at minimum), and (c)
  a fresh full end-to-end batch run across real files, not just the
  isolated case — in that order, all three, before it's called fixed.

**v2 update — the detection mechanism improved again, this time without a
regression** (unlike attempts 2 and 3 above, which is why this one is
folded in and those weren't). Two more real cases exposed the v1 (70%-of-
median) threshold's blind spot in different ways:
- A gradually/dramatically MOVING design element (a cloud shifting
  position, not just occluded) has natural filled-area variation that can
  swing even more than a rotating shape — confirmed 0.50 to 1.06 of
  median on a real icon, i.e. legitimate variation that dips WELL under
  v1's 70% gate. Distinguishing signal that separates this from a real
  bug: legitimate variation is GRADUAL across many consecutive frames; a
  real bug is a SHARP, often single-frame outlier against its own local
  neighborhood, even when it's embedded inside a smooth large-amplitude
  cycle (confirmed: a real one-frame anomaly on this exact icon was still
  correctly caught this way).
- A SUSTAINED occlusion spanning many consecutive frames (confirmed real
  case: a continuous "wipe" sweep effect) doesn't produce a sharp local
  outlier at all, so the local-neighborhood check alone can't see it —
  confirmed catching only 1 of ~15 visibly-bad frames with that check in
  isolation.

v2 detection combines BOTH, independently per color, taking the union of
frames either one flags: (a) a local-neighborhood check (sharp, isolated
drop vs. a small window of nearby frames -- safe for gradual/large-
amplitude legitimate motion), and (b) a whole-distribution statistical-
gap check (a sorted-value jump of >=8% separating a low cluster from a
high cluster -- catches sustained occlusion that (a) can't). Both were
verified independently to produce zero false positives across every
legitimate-animation case available (a rotation, and two large-amplitude
smooth pulse/shift cycles) before being combined. Substitution mechanism
is unchanged from v1 (single nearest non-anomalous frame, never a
blended/combined reference).

**Known remaining gap, carried from v1, now narrower but not zero:** the
sustained-occlusion (gap) detector needs a genuine statistical gap; a
sustained-but-mild occlusion that blends smoothly into the animation's
own natural variation (confirmed real case: a handful of frames on the
same "wipe" icon sitting in a transition zone between the bad and normal
clusters) still won't be caught. Don't claim "fully fixed" for a
sustained-occlusion case without checking the specific frames a user
reports, the way both regressions above were originally caught by user
inspection, not by this detector's own confidence.

**A SEPARATE, more direct fix was also found for the sustained-occlusion
case, and it's worth trying FIRST before reaching for detection/
substitution at all:** if the outline is fading toward background color
gradually (rather than being replaced outright by a differently-colored
crossing element), widening `--outline-tolerance` alone can keep the
ring topologically closed through the fade with NO cross-frame logic
needed at all — confirmed on the real "wipe" case: tolerance 40->80
brought the minimum per-frame filled-area ratio from 0.79 to 0.93, and a
rigorous full-animation check (every true-interior pixel against source,
not just an aggregate area proxy) found zero remaining mismatches across
all 124 frames. This is strictly safer than substitution (no risk of
cross-frame position mismatches at all, since nothing is borrowed from
another frame) and should be tried first whenever the root cause looks
like a fade rather than an occlusion by a separately-colored element —
check by sampling a point that's outline-colored in a good frame across
several bad frames and seeing whether it shifts toward background color
gradually (fade -> try tolerance first) or gets replaced by an unrelated
solid color (occlusion -> detection/substitution is the right tool).

**Confirmed generalizing to a second, structurally different real case —
not just a fade toward background, but a full color SHIFT between two
saturated colors:** a star icon's own outline animated smoothly between
navy and a distinct purple (`104,100,247`), as an intentional design
effect, not occlusion. First instinct was to reach for multi-color
`--protect-outline-color` (list both navy and purple, relying on the
union mechanism documented above) — this seemed like the obvious tool
since it exists specifically for multiple colors, but it was the WRONG
lever here and didn't work: both colors independently still showed heavy
substitution (32/46 and 34/46 frames respectively), because the outline
passes through a continuous gradient of intermediate colors between the
two named endpoints, not a discrete switch between exactly two colors —
naming just the two endpoints leaves every in-between frame still
unmatched by either. Tolerance widening on the single base color (navy
alone, no purple needed) fixed it completely instead: tolerance 40->150
brought the minimum ratio from 0.216 to 0.865, and confirmed zero
substitution needed at all, checked and stable (opaque, no flicker)
across all 46 frames. **Takeaway: when the outline's own color visibly
changes across frames — whether fading toward background or shifting
toward a completely different saturated color — try widening
`--outline-tolerance` on the ORIGINAL single color FIRST, before reaching
for multi-color protection. Multi-color protection is for when multiple
DISTINCT, STABLE outline colors coexist (confirmed real case: a folder
icon whose folder and triangle badge happened to share one outline
color but could equally have used two) — not for one outline that
continuously drifts.** The right tolerance value itself is case-specific
(80 sufficed for the fade-to-white case, this color-shift case needed
150) — test a few values and check the resulting min-ratio rather than
assuming a fixed number transfers.

**Widening `--outline-tolerance` has its own real interaction with
`--edge-cleanup-erosion`, confirmed the hard way:** on the same "wipe"
icon, after fixing the enclosure via tolerance widening, a DIFFERENT
artifact appeared — a visibly lighter, blended outline color staying
fully opaque right at the true silhouette edge before the cutoff to
transparent (a real fringe artifact, confirmed via direct pixel
comparison to NOT be present at that severity with the default erosion).
This icon had already been set to `--edge-cleanup-erosion 1` (reduced
from the default 2) earlier in the same investigation, specifically to
preserve a different thin design element — but erosion=1 turned out to
be insufficient to clean up the NEW fringe exposed by the wider
tolerance. Reverting to the default erosion=2 fixed it (confirmed: direct
navy-to-transparent transition, no blended pixel, re-checked across the
full image) at the cost of the thin element shrinking from 137px back to
126px (87% of the original source's 145px -- a real but acceptable
tradeoff, not destruction). **Lesson: `--outline-tolerance` and
`--edge-cleanup-erosion` are not independent settings for a given icon —
changing one can require re-checking the other, especially on icons that
already needed a non-default erosion value for unrelated reasons.**

## `--edge-cleanup-erosion 0` was a real, silent, total-destruction bug
(fixed in v2.1) — know the mechanism before trusting any future edit here
Confirmed directly: `--edge-cleanup-erosion 0` on a real icon produced a
completely blank, fully-transparent output (a 47-frame GIF that shrank to
1.9 KB) with NO error or warning. Root cause: `erode_alpha_edge` passed
`iterations` straight through to `scipy.ndimage.binary_erosion`, and
scipy's own documented behavior for `iterations < 1` is "repeat until the
result no longer changes" — NOT "no-op." For any bounded opaque region,
repeated erosion always converges to nothing, so `iterations=0` silently
eroded every frame's content away completely. Confirmed the mechanism in
isolation: a 10x10 filled square went from 100px to 0px at
`iterations=0`.

**Why this wasn't caught earlier despite `--pixel-art` also using
`--edge-cleanup-erosion 0` internally:** `--pixel-art` additionally sets
`feather=False`, and the erosion call site is guarded by `if
args.feather:` for an unrelated reason (the erosion is specifically
feather-fringe cleanup, so it's skipped when there's no feathering to
clean up). That guard happened to also prevent `--pixel-art`'s use of
erosion=0 from ever reaching the buggy scipy call. The bug was only
reachable by passing `--edge-cleanup-erosion 0` directly, with feathering
still on (the default) — a real, unremarkable-looking combination that
came up naturally while trying to preserve a tiny, delicate animated
element (a sparkle icon that shrinks to a few hundred pixels at the start/
end of its own pop-in/pop-out animation).

**Fix:** `erode_alpha_edge` now has an explicit `if iterations <= 0:
return list(alpha_frames)` guard at the top, making it a true no-op
regardless of what scipy would otherwise do. Verified: erosion=0 now
correctly returns the full, undamaged content (confirmed on the real
triggering case), and existing behavior at erosion>=1 and `--pixel-art`
are both unchanged (re-checked against baseline).

**The generalizable lesson:** a library function's behavior at a
boundary/degenerate input value (0, empty, None, negative) is not
guaranteed to match the caller's intuition even when the non-degenerate
behavior is well understood and has been correct for a long time. This
bug shipped silently through v1 and v2 because every prior real-world
case happened to either use erosion>=1, or use erosion=0 exclusively via
the one path (`--pixel-art`) that never actually reached the vulnerable
call. Don't assume a parameter's "obvious" meaning at its extreme values
without checking the underlying library's actual documented behavior
there, especially for a value (0/off) that reads as if it should be the
safest, simplest case.

## Reduced erosion for thin/geometry-light icons, even when NOT full
pixel art
`--pixel-art`'s `edge_hardness` check is a binary "is this pixel art"
signal, but erosion damage isn't actually binary — it's a spectrum tied
to how much "bulk" a design has to absorb a fixed pixel-count shave. A
real confirmed case: two icons from an otherwise normal antialiased
vector icon pack (NOT flagged as pixel art, correctly so — they're not)
still had thin elements (a lightning bolt, a folder's back-flap outline
line) that came back visibly more jagged/thinner than the source under
the DEFAULT `--edge-cleanup-erosion 2`, because thin elements have much
less interior "padding" to lose before the erosion eats into the visible
shape itself. Measured directly: a thin line's opaque run-length was 145px
in the source, 129px after default erosion (2px), and 137px at
`--edge-cleanup-erosion 1` — noticeably closer to source without
reintroducing the fringe-color artifact the default erosion exists to
prevent (confirmed: re-checked for fringe colors at erosion=1 on both
affected files, none found).

**Practical signal:** both affected icons also happened to have low
`edge_hardness` ratios (0.39 and 0.17) — below the ~0.5 pixel-art
threshold, but not by a huge margin, and this is the SAME "straight-line-
heavy geometry" pattern documented in the edge_hardness caveat above (a
trash can, a rectangular sweep effect). Treat a low-but-not-hard-edged
ratio as a signal to consider `--edge-cleanup-erosion 1` even when
`--pixel-art` itself would be wrong, rather than only ever using the
default 2 or the pixel-art-preset 0. This isn't automatic (unlike the
transient-enclosure fix above) — it needs a judgment call per icon, since
erosion=1 is a real quality/fringe-cleanup tradeoff, not a pure
correctness fix like the enclosure bug was.

**Resize is a second, independent contributor for the same thin-element
problem — check it separately from erosion.** A user specifically
reported a thin lightning-bolt element looking "jagged and rough" versus
a smooth original even AFTER erosion was reduced to 1. Measured directly
with a scale-invariant roundness proxy (edge-pixel-count / sqrt(area),
isolated to just the thin element, not the whole icon): source measured
7.276, the SAME icon processed with NO resize measured 7.313 (~0.5%
worse, essentially unchanged), but the SAME icon WITH the tier's normal
512px-target resize measured 7.514 (~3.3% worse) and also lost ~24% of
the element's pixel area outright. The mechanism: this script's alpha
decision is computed at full source resolution, THEN resized with
LANCZOS, THEN re-binarized (`alpha > 127`) -- resizing an
already-effectively-binary mask and re-thresholding is a well-known
recipe for staircasing on thin/high-curvature shapes, unlike resizing a
naturally continuous-tone image. If the icon's crop is only modestly
above a tier's resize target (e.g. 536px vs a 512px target — an ~5%
overage), consider `--resize-max-dim` set high enough to skip the resize
entirely (confirmed on the real case: skipping resize was not just
higher quality but also produced a SMALLER file — 1292.9 KB vs 1443.7 KB
— since a cleaner, less-aliased edge compresses better via LZW than a
staircased one, so this isn't even a pure quality-vs-size tradeoff in
every case; check both).

**Confirmed a second time on a differently-shaped icon** (curved star
points, not a thin bolt) after a user asked for "smoother animation" with
no more specific complaint than that: measured the same roughness proxy
on the star's outer silhouette and found the identical pattern — 11.28
resized vs. 10.48 source, improving to 10.99 with `--resize-max-dim` set
to skip the resize, again with a smaller file as a side benefit (562 KB
vs. 680 KB). This is now confirmed on two structurally different icons
(a thin straight-line element, and a curved/pointed outer silhouette),
which is enough to treat "check whether skipping resize helps, whenever
the crop is only modestly over a tier's target" as a general check worth
running by default when a user's complaint is about smoothness/
roughness/jaggedness, not just something to reach for after a specific
lightning-bolt-shaped precedent.

## Tools considered, and how each was actually resolved
Documented here so these aren't re-researched or re-tested from scratch
without new evidence — both were investigated seriously, not dismissed on
sight.

**gifski** (libimagequant-based GIF encoder, same engine family as
pngquant). Its own maintainer, responding to a bug report about jagged
edges from transparent PNG input, said plainly: "This is unavoidable. The
GIF format doesn't support alpha transparency" — meaning gifski does its
own alpha thresholding on whatever it's handed rather than preserving an
input mask exactly, which conflicts with this script's protected-region /
feathered-edge alpha decisions (gifski would potentially re-derive the
transparency boundary rather than respect the one already computed).
Separately, its docs describe "cross-frame palettes" designed to combat
per-frame palette drift — a reasonable design, but not verified against
this skill's mostly-static-content case, and not worth the risk to
transparency handling to find out. **Not integrated, at all.**

**pngquant / libimagequant** (used directly, not via gifski) for building
`render_frames_to_gif`'s shared master palette, in place of Pillow's
`Image.ADAPTIVE`. This one WAS implemented and empirically tested, not
just reasoned about abstractly. Short version: **implemented as an
explicit opt-in (`--quantizer pngquant`), NOT the default** — the full
reasoning:
- Isolated quantization-error measurement (MSE against the original,
  color-only, no GIF encoding involved) showed pngquant meaningfully
  outperforming Pillow's median-cut at every color count tested: 38% lower
  error at 16 colors, up to 81% lower at 128 colors.
- But swapped into the real end-to-end pipeline on real test art
  (identical settings, same source, only the master-palette algorithm
  changed) it produced LARGER output files at every tier tested — +4.0%
  at `optimize`, +6.8% at `heavy` — not smaller, the opposite of what the
  isolated MSE numbers implied.
- Working theory: pngquant optimizes for perceptual color accuracy, not
  for how well the resulting palette's indices compress via GIF's LZW.
  This skill's actual content (flat vector icon/sticker art, not photos
  or gradients) is exactly the case where index run-length/predictability
  matters more than marginal per-pixel color error, and `medium`/`heavy`
  tiers already run their own further gifsicle `--lossy`/`--dither` pass
  on top, which dilutes whatever quality edge the master palette had
  going in. Checked the color histogram directly on real test art too:
  only ~8 colors actually do real design work (the flat fills); the rest
  of the ~150 distinct colors are a long tail of antialiasing/blend fringe
  shades. Either quantizer preserves those 8 core colors losslessly within
  any of this skill's color budgets (128+), so the measured MSE gap is
  concentrated in secondary edge-fringe fidelity, not core design accuracy
  — a real difference, but a narrow one for THIS content type.
- Given that, defaulting to it wasn't justified — but the underlying
  case for it wasn't zero either, just narrower than "always better."
  **`--quantizer pngquant` exists for**: content this skill hasn't
  primarily been validated against (genuine gradients/soft shading, where
  more real colors compete for the budget rather than a long tail of
  minor blend noise), or whenever the person explicitly says quality
  matters more than file size. Falls back to `pil` with a clear warning
  if pngquant isn't installed/available or the call fails. Works from
  `--batch` manifests too (any per-file override key works generically,
  `"quantizer": "pngquant"` included — nothing special-cased for it).
- **The lesson generalized, not just about this one tool:** a component
  that wins on an isolated, narrower benchmark (quantization MSE) can
  still lose on the metric that actually matters for the full pipeline
  (final file size on this skill's real content) if the two aren't
  measuring the same thing. Prefer re-testing swaps like this end-to-end
  on real output before adopting them, even when the underlying algorithm
  is well-regarded and the component-level numbers look unambiguous.

## GIF format has NO partial transparency — confirmed directly, not from docs alone
Every pixel in a GIF frame is binary opaque-or-transparent; there is no such thing as a real
semi-transparent pixel the way PNG/WebP support. Confirmed hands-on while trying to fake a
"background bleeds through a highlight" effect on a recolored icon: wrote a pixel at alpha 114/255
intending a soft blended look, saved via Pillow's GIF encoder, and re-read the output — the alpha
came back rounded to 255 (fully opaque), byte-identical to a version that never attempted partial
alpha at all. This isn't a Pillow limitation specifically — it's the GIF format's own single-bit
transparency index, the same fact this skill's "Tools considered" section above already cites from
gifski's maintainer in a different context (gifski's alpha-thresholding behavior on transparent PNG
input is a symptom of this same underlying format limitation, not an unrelated gifski quirk).

**Workaround for "I want it to look like the background bleeds through"**: if the final background
color is fixed and known ahead of time (e.g. a specific Discord button color), bake a literal flat
blend of that background color with the foreground color as an opaque pixel value, in place of
relying on real partial alpha. This achieves the same visual read without needing the format to do
something it structurally can't — confirmed working end-to-end on a real delivered asset (a
recolored eyedropper icon's highlight stripe, blended toward Discord blurple instead of left pure
white). This is a real constraint to flag to the user up front whenever a "soft"/"bleeding"/
"translucent" effect is requested against a GIF deliverable, not something to attempt and discover
mid-task.

## gifski as a compression-tier alternative for a smooth-animation + tight-KB-budget case
The "Tools considered" section above documents gifski being rejected for the TRANSPARENCY step
specifically (its own alpha-thresholding conflicts with this script's protected-region/feathering
decisions) — that finding still holds and gifski should NOT be used for the background-removal
pass itself. But a separate, later use case surfaced: as a COMPRESSION-ONLY step applied AFTER
transparency is already finalized (i.e. gifski re-encoding an already-transparent GIF, not
deriving transparency itself), where it's a genuinely different tradeoff than what was evaluated
above and deserves its own note.

Real comparison, same source asset, same target ("keep it smooth, hit Discord's 256KB emoji
limit"): this skill's own `--compress` tiers, working from `--target-kb 200`'s automatic cascade,
had to drop frames to hit budget — `--target-kb 200` alone jumped straight to a stride-4 frame-drop
(180 → 45 frames, 12.5fps) to reach 79.8KB; manually dialing in `--compress heavy
--frame-stride 3` did better (180 → 60 frames, 16.7fps, ~144KB) but still threw away 2 of every 3
frames. A user's own manual pipeline outside this skill — crop transparent margin → resize to
128px width → **gifski** re-encode at quality 68 — kept ALL 180 original frames (zero frame drops,
full smoothness) at 248.26KB, comfortably under the 256KB limit with real margin. gifski (a
libimagequant-based encoder tuned specifically for GIF output) at a well-chosen quality setting
outperformed this skill's own gifsicle-based frame-stride/lossy-dither tiers for this specific
"smooth motion matters more than absolute minimum size" case.

**Not yet integrated into this script** — flagging as a real, evidence-backed option to reach for
next time a user explicitly prioritizes animation smoothness over squeezing every last KB: for that
specific ask, after transparency is finalized via this script's normal removal pass, piping the
transparent output through an external `gifski --quality <N>` pass (tuning quality rather than
frame-stride to hit the target size) is worth trying as an alternative to escalating this script's
own `--compress heavy`/`--frame-stride` further. Not validated across a range of source assets yet
— this is one confirmed real-world data point, not a new default recommendation to reach for
unconditionally.

