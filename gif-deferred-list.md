# GIF Background Remover — deferred list

The project-local tracker for flagged findings, real TODOs, and reminders specific to this repo —
split out from `/Applications/Claude Code/meta-deferred-list.md` on 2026-08-07, the same treatment
Dior's Builds got (`docs/db-deferred-list.md`). That file stays the canonical home for things with
no single-project home; this one is for anything a session working *only* in this repo would need.

**Priority & effort tags** (short copy — canonical legend + full model/effort grid at
`meta-deferred-list.md`, section "🏷️ Priority & effort tags"): every open item carries
`[Priority · Effort · Model-effort]`.
- **Priority:** P0 now (broken/blocking) · P1 soon · P2 eventually (real, not pressing) · P3 someday.
- **Effort:** XS minutes · S part of a session · M a session · L its own multi-session job (must
  carry a named first slice — no schedulable "just L" items).
- **Model+effort:** chosen from the priority-tier grid (premise risk × deliberation load), not from
  the effort tier — see the meta file for the full grid.

---

## 🐞 Open — real TODOs with an available fix, not yet done

*Populated 2026-08-07, end of the session that shipped `--analyze`/`--recommend`/`--verify`
(Phase 1 of the optimization work, branch `feat/analyze-recommend-verify`). Both items below were
found during that session's final whole-branch review, genuinely attempted, and correctly NOT
fixed in that session because each needs a real design decision, not just more time. See
`local/HANDOFF-phase2-prose-compression.md` and `local/plans/2026-08-07-analyze-recommend-verify.md`
for full context — this entry is the tracked pointer, not a duplicate of that detail.*

### `[P2 · L (first slice: S) · Sonnet5-XHigh]` `--analyze`'s runtime regression — real cost driver identified, not yet fixed
**Added:** 2026-08-07, from the final whole-branch review of Phase 1.

**The problem, measured:** escalating 3 of `--analyze`'s checks (tumble margin, band-interior
detection, small-region histogram) from a 40-frame sample to every frame — necessary, it's what
fixes real false-negative bugs the checks exist to catch (confirmed real case:
`references/lessons.md` §12's `fff2d1` sparkle was on frame 97, which a 40-frame sample of a
109-frame GIF never lands on) — made `--analyze` **~3-8x slower**: `jewelry.gif` 3.14s → 19.71s,
`gemstone.gif` 2.14s → 18.19s, `ruby.gif` 2.49s → 6.84s (all real fixture measurements, same
machine, before vs. after).

**One real attempt already made and measured, not just theorized:** shared the per-frame
`color_mask()` computation between the tumble-margin and small-region checks (they were each
computing the identical thing independently). Re-measured honestly: **did not help**
(`jewelry.gif` 20.66s after — within noise of the 19.71s baseline). `color_mask` itself is cheap;
it was never the real cost.

**The actual cost driver, identified but not yet fixed:** `ndimage.label`/`binary_fill_holes`
calls running multiple times per frame across DIFFERENT checks, each on a DIFFERENT mask (the raw
background-color mask, the band-interior distance mask, one mask per verified outline color) — they
can't share one labeling pass the way `color_mask` could, because they're not labeling the same
thing.

**First slice (S):** profile which specific call sites actually dominate (which check, `label` vs
`binary_fill_holes`, on which fixture) before attempting to batch/vectorize anything — the current
diagnosis is architectural reasoning, not a profile. `cProfile` or manual per-call timing on
`jewelry.gif` (the slowest fixture) would settle it in well under a session.

**Model pick reasoning:** premise Med (the general cause is identified and real, but the specific
call-by-call breakdown that would drive a batching design isn't measured yet) · deliberation High
(vectorizing/batching `ndimage` operations across frames for several structurally different checks
is a real design task, not mechanical) → `Sonnet5-XHigh`. Re-score once the profile (first slice)
is done — that measurement may well drop this to a lower cell.

### `[P2 · M · Sonnet5-XHigh]` `band_interior_regions`' cross-frame grouping doesn't know about verified candidate regions
**Added:** 2026-08-07, from the final whole-branch review of Phase 1 (found, partially mitigated,
then the mitigation itself was re-reviewed and two smaller regressions in it were fixed same
session — see the plan doc's Task 6 section and the SDD ledger for the full sequence).

**The problem:** `detect_band_interior_regions`'s per-frame detections are grouped across frames by
bbox-center proximity (currently 40px) into `band_interior_regions`. This grouping runs BEFORE
`analyze()` computes its candidate-region list (`candidate_regions`, the enclosed/protected areas),
so it has no way to know a given band-interior detection is actually inside a region that's already
protected by a verified `--protect-outline-color`. Confirmed real consequence on `jewelry.gif`:
what's genuinely 1-2 physical regions (the protected highlight itself) fragmented into up to 17
separate `band_interior_regions` entries, producing misleading evidence text in `--recommend`'s
output ("17 solid-tint region(s) observed") even though `recommend()` correctly avoids adding a
wrong CLI flag for it (already gated: `--protect-band-only` is suppressed whenever a verified
outline color is also being recommended, so this doesn't currently ship a WRONG command — it ships
a wordier, less precise one).

**The real fix:** reorder `analyze()` so the union-mask/candidate-region detection (the loop that
builds `results`/`candidate_regions`) runs BEFORE the tumble-margin/band-interior/small-region
checks, then thread the resulting candidate bboxes (or footprints) into
`detect_band_interior_regions`'s grouping step as an exclusion, the same technique `verify()`
already uses successfully for its own `leftover_background_opaque_px`/`protected_region_coverage`
checks. Not done in Phase 1 — genuinely a reordering of a ~450-line function's internal structure,
not a small patch.

**Model pick reasoning:** premise Low-risk (the fix shape is well-understood and already proven
elsewhere in the same function for a structurally similar problem) · deliberation High (reordering
a large function's internals without regressing its existing, already-reviewed checks needs real
care, and the byte-identical/behavior-preservation discipline this whole project runs on) →
`Sonnet5-XHigh`.

### `[P3 · M · Sonnet5-High]` `--verify`'s `protected_region_coverage` false-positives on a legitimately punched sub-hole inside a translating candidate region

**✅ CLOSED 2026-08-17 — confirmed against this item's own asset.** `military-tag.gif` IS on this
machine (`~/Downloads/Diors-builds Emojis/`); the earlier "not on this machine" note was wrong.
Re-rendering §14's pipeline uncropped and running `--verify` with both scripts: **0.462 →
0.757**, `looks_unprotected` **true → false**. The 0.462 reproduces §14's recorded 46.2% exactly,
so this is a real reproduction, not two clean runs agreeing by luck.

⚠️ Verifying against the DELIVERED file would have been a vacuous pass — it is cropped (536x570 vs
640x640), so `--verify` skips every pixel check and reports only timing.

**The residual 0.757 is correct, and now self-explaining.** Decomposed, the non-opaque remainder is
ONE blob per frame in all 126 frames, 441–457px — the punched pinhole, which is background-coloured
and *should* be transparent. A new additive `residual_nonopaque` field reports persistence, blob
count, size CV and footprint fraction so this reads as a cutout rather than an unexplained defect;
falsified against a deliberately unprotected render (1.00 blob/cv 0.025/0.243 → cutout; 2.13/0.586/
1.000 → not). **Correction to the original diagnosis below:** cause (1), the translating bbox,
contributes nothing measurable here — cause (2) was doing all of it. Full case: `references/
lessons.md` §22.

**Added:** 2026-08-07, from `military-tag.gif` production job (see `references/lessons.md` §14 for
the full case).

**The problem:** `protected_region_coverage` measures opacity for background-colored-in-input pixels
within a candidate region's bbox. Two things break this on a real asset: (1) the region's footprint
is tied to one fixed reference frame, but if the design translates/swings across the animation, real
outer background can fall inside that same fixed bbox in other frames and get correctly removed --
inflating the "not opaque" count with pixels that were never really part of the region; (2) if a
verified region legitimately contains its own interior sub-hole (punched via
`--hole-size-range`/`--hole-max-aspect`, not `--protect-outline-color`), the hole's pixels are
*supposed* to go transparent, but the check has no concept of an intentional sub-hole and just counts
it as unprotected coverage. Confirmed false positive: flagged `looks_unprotected: true` at 46.2%
opacity on an output independently verified (via a frame-by-frame true-component check, not the bbox
metric) to have the protected element at 100% opacity in all 126 frames.

**Why not fixed now:** same root architectural cause as the `band_interior_regions` gap above
(candidate-region detection ties to one fixed-frame bbox/footprint) -- a real fix needs `verify()` to
either re-derive the region's footprint per-frame the way `outline_enclosure_all_frames` does, or
accept an explicit "known intentional sub-hole" input. Genuinely a design question, not a quick patch,
and lower priority than the two items above since it only produces a misleading warning (evidence
text), never a wrong processing command.

**Model pick reasoning:** premise Medium (root cause understood, but the right API shape for
"this region has an intentional sub-hole" isn't obvious yet) · deliberation Medium (touches
`verify()`'s existing, reviewed logic, but is more contained than the `band_interior_regions`
reorder) -> `Sonnet5-High`.

### `[P3 · L (first slice: S) · Opus5-High]` No answer yet for a moving hole with neither geometric separability nor external tracking
**Added:** 2026-08-08, from reconciling the v4.0.0 live-skill-drop (`references/lessons.md` §15).

**The problem:** this repo now has two real solutions to "punch a hole shared with same-color
decoration that needs opposite treatment" -- §14's geometric-gate approach (`--tumble-safe` +
`--keep-bg-blob-if-near` + tight `--hole-size-range`/`--hole-max-aspect`), which needs the hole and
the decoration to differ measurably in size/aspect across every frame; and §15's `--remove-region`,
which needs either a static target or an external per-frame tracking script (confirmed: a static
circle alone missed the true target in 76% of frames on a real tumbling asset). Neither covers a
moving hole that ISN'T geometrically separable from its decoration and has no available tracking
tooling -- a real, currently-unsolved case, not yet encountered on a real asset but now a known gap
rather than a silent one.

**First slice (S):** wait for a real asset that actually needs this before designing a fix --
speculative design against a hypothetical case risks solving the wrong shape of problem, the same
mistake `--keep-bg-blob-if-near`'s color-adjacency approach made when first reached for on §14's
own asset. If/when a real case arrives, the likely direction is a lighter-weight, script-native
per-frame tracking primitive (a lower-effort analog to the live session's `cv2.HoughCircles` step)
rather than requiring bespoke external tooling every time.

**Model pick reasoning:** premise High (no real case yet, so even the shape of the right fix is
speculative) · deliberation High (a script-native tracking primitive is real algorithm design) ->
`Opus5-High`, and only once a concrete motivating case exists.

---

## ✅ Considered and NOT fixed — a real decision, not an oversight

*Findings that were surfaced, genuinely weighed, and deliberately left alone — listed here so they
don't get re-flagged as forgotten work by a future review.*

- **`--verify` on a missing/unreadable file surfaces a raw `FileNotFoundError`/
  `PIL.UnidentifiedImageError` traceback**, found in the same 2026-08-07 whole-branch review.
  **Decision: not a defect, don't fix.** Confirmed every other file-reading path in
  `scripts/remove_gif_background.py` already behaves the same way (no defensive validation
  anywhere in the file) — adding it only to `--verify` would be a new inconsistency, not a fix, per
  this codebase's own established convention (trust internal/framework guarantees, validate only at
  a real system boundary the rest of the file already treats as one). Revisit only if this
  convention itself changes project-wide, not in isolation for this one flag.

---

## 🔔 Reminders / watch-for

### AUTONOMY BACKLOG — `--recommend` still needs manual correction on these (opened 2026-08-17)
**Six of the nine items below were CLOSED on 2026-08-17** — see `references/lessons.md` §18 for
the measurements behind each. Remaining open: 5 and 9.

1. ~~`--pixel-art` emitted on thin-AA vector art~~ — **CLOSED.** Added a second discriminator,
   `antialiasing_blend_ratio` (are there real background-to-art blends at all?). Synthetic pixel
   art 0.000; the lowest real asset 1.530. `appears_hard_edged` now needs BOTH measures. The
   fixture still gets the flag; love and heart no longer do. §18.1
2. ~~`--erosion-exempt-max-size` emitted for love~~ — **CLOSED.** The classifier was already
   right (love's 4 buttons ARE detected as design); the SIZE THRESHOLD was the problem — 487px
   sat above the buttons' own 286–306px, so it would have exempted them anyway. Now suppressed
   whenever the transient and persistent size ranges overlap. §18.2
3. ~~heart's `--feather-band-multiplier 1.5` unverified~~ — **CLOSED, and it was actively
   harmful.** Measured fringe fraction 0.2186 at 1.5 and 0.1831 at 2.5 against 0.0000 at the
   default — the recommendation was producing the fringe. The `max(1.5, ...)` clamp was the bug.
   Only recommended at ≥3.0 now; `--protect-band-only` carries the rest (97.7% of the same
   protection, no fringe). §18.3
4. ~~gift's white strip never surfaced~~ — **CLOSED.** Not a colour-detection failure: the
   union-across-frames footprint had merged the strip with a transient pocket (21,184px →
   25,219px), and nothing encloses a shape that never exists. Added per-frame re-verification.
   gift now auto-recommends `--protect-outline-color 002864`; protected coverage 0.0 → 0.874,
   fringe 0.0388 → 0.007. §18.4
5. **STILL OPEN — gift's sparkle colour never appears at full opacity.** The curved sparkle is
   `#052a75`, the SAME navy as the box outline, drawn at partial opacity; one colour is
   simultaneously solid artwork and a translucent element, so marking it fading would stop the
   outline blocking anything. The 4-dot sparkle separately needs `--fade-color 6969f2` because
   its true colour never clears the palette frequency floor. **Do:** the per-pixel art prior
   built for the flood barrier (§16) is the plausible basis — high prior ⇒ outline, low prior ⇒
   sparkle. ⚠️ Read the REVERTED "saturation promotion" experiment in §16 first; the naive
   version of this idea is measurably net-harmful. This is the one genuinely unsolved item and
   it is a research task, not a parameter fix.
6. ~~GIF `--target-kb` discards `--square-pad`~~ — **CLOSED: did not reproduce.** Measured
   128×128 with and without `--crop`; padding survives the tier cascade. The original 128×110
   came from a render script that never passed the flag to the GIF variant. §18.6
7. ~~`--verify`'s `looks_fringed` is unreliable~~ — **CLOSED.** Replaced with the outer-ring
   relative metric, and made TRI-STATE: True >0.15, False <0.04, None in between with the
   reason. The bands overlap across assets (heart's fringed 0.0665 < crystal's clean 0.0830),
   and tightening the ratio collapses every asset to 0.0000 — a test that cannot fail. Reporting
   "inconclusive" is the honest answer. §18.5
8. ~~**AVIF durations cannot be read back**~~ — **RESOLVED 2026-08-17.** Never an AVIF
   limitation: Pillow populates `info['duration']` only in `load()`, and the reader used
   seek-only, so every frame returned 0. Adding `load()` returns the true durations
   (3000 ms, `[220, 20 x122, 340]`). Same root cause as the WebP source-duration shift —
   see `references/lessons.md` §17.
9. ~~**`--verify` has no 8-bit-alpha mode**~~ — **CLOSED 2026-08-17.** *(was: partially addressed)* the fringe
   metric itself is now alpha-aware (`measure_outer_ring_background_fraction` counts only
   near-opaque pixels, so a legitimate alpha ramp is not flagged), and `--auto`'s post-render
   check runs on WebP/AVIF using it. `--verify` proper still refuses non-GIF because its OTHER
   checks (leftover background, protected coverage) remain 1-bit assumptions. **Do:** give
   those two the same partial-alpha treatment, then lift the refusal. (opened 2026-08-17, replaces the stale
   duration-based reason). Now that WebP/AVIF durations read correctly, the ONLY thing
   blocking `--verify` on those formats is that its checks are written for 1-bit alpha:
   "leftover background" tests for an opaque background-coloured pixel, "fringe" for a pale
   ring — and a recovered fade is legitimately both. **Do:** give each check a partial-alpha
   definition (leftover background = alpha≈255 AND background-coloured; fringe = the
   outer-opaque-ring metric from §16, which is already alpha-aware) rather than lifting the
   refusal. Lifting it without redefining the checks reintroduces exactly the misleading pass
   the refusal exists to prevent.

10. ~~**`--verify`'s leftover-background count flags intentionally protected design**~~ — **CLOSED 2026-08-17.** Now also excludes the verified outline's own filled area (gift worst frame 14,243 → 0) and requires alpha>=250 so a partly transparent background-coloured pixel counts as the fade/ramp it is. §21.2. Original note:
    (opened 2026-08-17). On gift, `leftover_background_opaque_px` reports 14,243px on its worst
    frame; 73% of them are inside the protected white-strip region's own bbox. The strip is
    background-COLOURED design that is *supposed* to stay opaque, so counting it as leftover
    background is a false alarm — visually confirmed correct output. `analyze()`'s own leak
    check agrees (`leaked_pixel_count: 0`). **Do:** exclude pixels inside a verified
    protected region's per-frame footprint from the leftover count, the same way
    `bbox_scope`-restricted enclosure already does for part of it. Low severity (a noisy
    metric, not a bad output) but it undermines trust in an autonomous run's self-check.

11. ~~**Replace the erosion-exempt SIZE threshold with per-region masks**~~ — **CLOSED 2026-08-17** via `--erosion-exempt-transient` + `find_transient_removed_regions()`, auto-recommended wherever the size threshold is refused. §21.4. Original note: (opened 2026-08-17
    during the §20 audit — a better fix than the guard shipped in §18.2). The overlap guard
    picks the safer side of a conflict rather than dissolving it: when transient noise and
    design occupy the same size range, love gets no exemption at all, so the v3.1.0
    small-region inflation bug can return. **The machinery to do it properly already exists** —
    `find_tiny_removed_regions` produces per-frame MASKS and
    `erode_alpha_edge_exempting_tiny_regions` consumes masks, so a size threshold is not
    actually required. **Do:** classify each region persistent-vs-transient (the classifier is
    already correct), build the exemption mask from the transient regions ONLY, and drop the
    size threshold entirely. That exempts exactly the noise regardless of how big they are or
    what size the design happens to be.

12. ~~**gift's protected-region coverage is 0.874, not 1.0**~~ — **CLOSED 2026-08-17: it was never real.** Coverage was measured over every background-coloured pixel in the bounding RECTANGLE (12,371 at frame 0) instead of the enclosed footprint (10,257); the extra pixels are genuine background, correctly transparent. Restricted to the footprint it reads 1.000, so item 4 is genuinely closed. §21.1. Original note: (opened 2026-08-17). §18.4 took it
    from 0.0, which is a real fix, but 12.6% of the region still is not opaque and I did not
    check why. It may be legitimate (frames where the strip is genuinely occluded) or a real
    remainder. **Do:** identify which frames and which pixels account for the gap before
    treating item 4 as fully closed. "Improved" was reported; "resolved" was not established.

13. **The whole threshold set rests on one art family** (opened 2026-08-17, §20.6). Five flat
    vector icons on white plus a self-authored pixel-art fixture. No dark-background asset, no
    real-world pixel art, no photographic-ish source was tested. The blend-ratio margin (0.000
    vs 1.530) is wide; the rest (feather ≥3.0, fringe bands 0.04/0.15, floor tolerance 0.02,
    post-render margin 0.05) are 4–5 points from one style. **Do:** re-measure against a
    genuinely different asset before trusting any of the narrow constants on new content —
    especially a non-white background, which the ring metric has never seen.

### ~~PARKED: remove the controller from love.gif~~ — CLOSED 2026-08-17 (Harkirat edited it manually; skill rendered the deliverables). Retained below only for the mask-isolation findings, which stay valid if this is ever automated.
Boundary reconstruction and the encoding path are SOLVED (static-in-canvas divide, degree-6
fit at 0.33px RMS, no GIF round-trip). **Unsolved: isolating the controller mask on frames
26–34**, where it touches the heart outline. Four approaches measured — see the handoff.


### Re-test gifsicle's colour dither on a GRADIENT-heavy corpus (opened 2026-08-17)
The `medium`/`heavy` tiers use `gifsicle --dither=floyd-steinberg` for COLOUR quantization. Spot-
measured on `love.gif` at `medium` settings, Floyd-Steinberg came out **worst on both** axes that
matter for animation:

| dither | KiB | mean colour err | frame-to-frame instability in static regions |
|---|---|---|---|
| floyd-steinberg (current default) | 1649.3 | 0.039 | 1.32% |
| atkinson | 1655.7 | 0.028 | 1.12% |
| ordered / o8 | 1658.4 | **0.026** | **0.97%** |
| none | 1654.1 | 0.026 | 1.01% |

i.e. it buys ~0.6% file size for the worst colour fidelity AND the most temporal crawl — the same
error-diffusion instability that disqualified it for ALPHA (measured separately: Floyd-Steinberg
changed 8.1% of pixels in a region that was byte-identical between frames; both Bayer sizes changed
0). Crawl also fights GIF inter-frame compression, so the size win may not even survive on other
content.

**NOT acted on, deliberately.** `love.gif` is flat 6-colour vector art, so a 200-colour palette
reproduces it almost exactly and dithering barely engages — all five options sit within 0.7% size
and 0.013 colour error, too close to call. The tiers exist precisely for content where quantization
DOES bite, and that content is what should decide this.

**What a future session should do:** assemble a corpus with real gradients/soft shading (not the
flat vector icons this skill is usually pointed at), run the same three measurements (bytes, colour
error against the pre-quantization frames, and static-region frame-to-frame instability) across
`floyd-steinberg` / `atkinson` / `o8` / `ordered` / none at both `medium` and `heavy`, and change
the tier default only if a clear winner emerges on gradient content without regressing flat art.

⚠️ **Jarvis, Sierra and Stucki are NOT options here** — verified by enumeration against the
installed gifsicle 1.6.0: it implements only `floyd-steinberg` and `atkinson` as error-diffusion
kernels (plus `ordered`/`o3`/`o4`/`o8`/`halftone`/`squarehalftone`/`diagonal`/`ro64`). Using them
would mean doing colour reduction outside gifsicle entirely, which is a much larger change than a
flag and should be scoped separately if the corpus test suggests error diffusion is worth
improving at all.

---

## Resolved (kept for the record, not to re-litigate)

- ~~Phase 1: move SKILL.md's manual checks into `--analyze`/`--recommend`/`--verify`~~ → **SHIPPED
  2026-08-07** on `feat/analyze-recommend-verify` (not yet pushed/merged — Harkirat's call). 5 new
  `--analyze` checks, `--recommend`, `--verify`, all reviewed (including a full whole-branch review)
  and fixed. Three real design bugs found via testing against real fixtures rather than written to
  spec and trusted — see the plan doc and SDD ledger for specifics.
- ~~Phase 2: compress SKILL.md's manual-check prose against Phase 1's new fields~~ → **SHIPPED
  2026-08-08** (fresh session, on the same branch, v3.3.0 → v3.3.1). Every check-by-hand paragraph
  Phase 1 made mechanically checkable now points at the real field name; also closed a real
  documentation gap (two `candidate_regions` fields shipped in Phase 1 but never documented, and
  `--recommend`'s actual outline-trust gate wasn't stated in "Run the real processing"). Pure docs
  change, no script touched. `references/lessons.md` gained a symptom→section lookup table.

---

### `[P1 · L · Opus5-High]` `edge_hardness` misclassifies pixel art on coloured backgrounds — 6 of 8 real assets

**Added 2026-08-17.** Harkirat supplied `local/Diors-builds Emojis/others/` — 9 real assets, 8 of
them genuine pixel art on COLOURED backgrounds. The tool calls 6 of the 8 antialiased. Full ground-
truth table, both failure mechanisms, and the measured numbers: `references/lessons.md` §23.

**Why P1 despite being pre-existing:** it is a correctness failure on a whole content class the
skill explicitly claims to support, and it fails toward the destructive setting (feather + 2px
erosion + LANCZOS on hard-edged art). §18's second discriminator was validated against a synthetic
fixture generated in-session, which is circular — this is what that circularity was hiding.

**Shipped 2026-08-17 (two rounds, still partial):** (1) zero transition band is dispositive;
(2) `change_line_density` — a geometric, palette-free measure — is dispositive below 0.5. Scored
against 37 labelled assets: **17/37 -> 30/37, pixel art 5/25 -> 18/25, false positives 0/12
throughout.** Corpus renders unchanged; love still byte-identical.

**Remaining: 7 assets, all one class** — dithered or photographic pixel art, where dithering puts a
change on every line and saturates the density measure (0.592-1.000).

**Next action:** measure density on a dither-suppressed copy (small median filter, or count only
changes persisting across several adjacent lines) and re-score against the same 37. The corpus and
labels are in `local/Diors-builds Emojis/others/` with `LABELS.json` + `README.md`.

**Two structural ideas were tried and scored before one was believed** (§23.4): modal run length
is DEAD (the vector corpus scores k=19-20, so a `k>=4` rule flags all six vector icons — §18's
catastrophe reintroduced); an integer-lattice fit is sound but narrow (0 false positives, 11/25,
because a 500x500 export of a 32px sprite is a 15.625x upscale on no integer grid).

⚠️ **Do not ship a bare blend-ratio threshold.** It looks tempting — pixel art spans
   0.000–1.074 and the antialiased corpus 1.530–2.529, so ~1.3 would score 13 of 14 — but the sole
   overlap is the jar (antialiased, 0.999) against DFB2A5D7 (pixel art, 1.074), and a threshold
   justified by a 0.075 gap between two assets is a margin of DEGREE, the exact trap §18 set out to
   escape and then fell into.

---

### `[P2 · L · Opus5-High]` Translucent glass/jar: three roles for identical `#ffffff` pixels

**Added 2026-08-17**, from `local/Diors-builds Emojis/others/2d4a092f5494a8d2455703857ee83d5c.gif`
(Harkirat's own framing): a bunny holding a transparent bag of popcorn. The same `#ffffff` plays
three different roles — outer background (remove entirely), bunny body (keep fully opaque), and jar
interior (make TRANSLUCENT, so it reads as glass). Current behaviour does one or the other: either
the jar interior is removed with the background, or it is protected and stays solid white.

**No pixel-level threshold can separate these** — the pixels are byte-identical. The distinction is
semantic, so this needs either a region/colour flag naming the glass, or a structural signal.

**Only expressible in WebP/AVIF.** GIF's 1-bit alpha cannot hold "20% opaque", so this sits on top
of the 8-bit alpha pathway added in v5.0.0 (§16), and is a natural extension of it rather than a
new subsystem.

**Cheap first measurement, not yet done:** check whether the jar's interior is topologically
CONNECTED to the outer background through the bag's opening. If it is, flood-fill-from-border
reaches straight into it, which would exactly explain the "removes the white inside the jar"
half of the observed behaviour and would point at the fix.

**Notable:** this asset is also the only ANTIALIASED file in `others/`, so it doubles as the
negative control for the pixel-art item above (`blend` 0.999, `ratio_max` 0.649).
