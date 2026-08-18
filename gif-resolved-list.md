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

## Where these came from

*Two section preambles from the active list are kept here because the sections they described no longer exist.*

- *On the two oldest items (`--analyze`'s runtime regression, `band_interior_regions`' grouping):* "Populated 2026-08-07, end of the session that shipped `--analyze`/`--recommend`/`--verify` (Phase 1 of the optimization work, branch `feat/analyze-recommend-verify`). Both items below were found during that session's final whole-branch review, genuinely attempted, and correctly NOT fixed in that session because each needs a real design decision, not just more time. See `local/HANDOFF-phase2-prose-compression.md` and `local/plans/2026-08-07-analyze-recommend-verify.md` for full context."
- *On the 2026-08-17/18 audit batches, which used to live in a "🔬 Findings ledger" section of the active list:* "These sat under 'Resolved' with no heading of their own until 2026-08-18, so a session skimming for open work could skip live P1 items." That section was **dissolved on 2026-08-18** by this split: its closed items are below, and its one open item (`edge_hardness` misclassifies pixel art) moved into the active list's Open section under P2. A section whose stated purpose was "OPEN and closed mixed" has no reason to exist once they are separated.

---

## Shipped / fixed / closed

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
