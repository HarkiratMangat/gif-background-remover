# Handoff — gate-8 trial run, fixes, and the hurricane investigation

**2026-08-23, Sonnet5-High.** Session hit ~900K context; this is the checkpoint before compacting/continuing. Everything below is either committed on `fix/gate8-trial-findings` or clearly marked as not.

## Where things stand

Branch `fix/gate8-trial-findings`, 3 commits, **not pushed, no PR**:
- `e58e4ed` — 5 confirmed fixes (see below)
- `d81d4fb` — deferred-list update recording the trial run
- `e9f8520` — the `--fade-color` family-absorption fix (hurricane investigation), **not corpus-validated yet**

Live skill is still v6.0.0. This branch is not merged, tagged, or released. All git actions from here (push, merge, tag, release) need Harkirat's explicit go-ahead per this repo's standing convention — none of that happened this session.

## What triggered this session

`gif-deferred-list.md`'s P1 item: run the three-tier gate-8 agent trial against the shipped `local/gif-background-remover-v6.1.1.skill`, since two releases had shipped without it. Method: `docs/investigations/2026-08-19-three-agent-package-trial.md`.

## Part 1 — the trial itself

Three isolated subagents (vague / detailed-prose / expert-with-hazards tiers), each given only the `.skill` package contents, processed the same 10-asset corpus (`galaxy, growth, hurricane, rocket, satellite, paper-plane, megaphone, secure, broadcast, notification`). All three self-reported clean via their own `--verify` checks and STEPLOGs. **Harkirat's manual review of the actual rendered outputs found real, systematic defects none of the automated checks caught** — this is itself the point of gate 8.

Outputs are in `local/2026-08-23-gate8-trial-v6.1.1/agent-{1-vague,2-detailed,3-expert}/`, organized into `deliverables/analysis/diagnostics/logs` subfolders with asset-first, self-describing filenames.

## Part 2 — 5 confirmed defects, fixed and verified (commit `e58e4ed`)

1. **Structural enclosure gap** (growth.gif, paper-plane.gif, rocket.gif). A design element the same colour as the true background (a body panel, a motion-trail fill, a fin highlight) only survives if reliably detected as fully enclosed by its outline colour — but on these three assets the outline never forms a full closed ring on **any single frame** (best case 45-70% per `--recommend`'s own `partial_outline` evidence), not an occasional glitch the existing `build_protected_masks_robust` anomaly-correction can fix (it borrows from a "good" frame, and there is no good frame here). Fix: an unconditional, safe-by-construction supplemental step in `build_protected_masks_robust` — union every frame's filled mask (clamped to each frame's own silhouette) as a floor under the per-frame result. Verified with real pixel-exact before/after diffs (not the flawed color-distance proxy I started with — see the mistakes section): rocket recovers ~590K px across all 177 frames, paper-plane ~3.8K px on 40/98 frames, growth ~1.5K px at frame 71 (not frame 74 — an earlier claim about frame 74 was itself wrong, corrected below).
2. Lifted `--protect-outline-color`/`--protect-region` mutual exclusivity (prerequisite for #1, both in CLI dispatch and in `build_protected_mask`/`build_protected_masks_robust`) — strictly additive.
3. `--recommend`'s `suggested_command` can silently produce a GIF while `recommended_format` still says webp/avif is needed (satellite.gif, likely broadcast.gif) — the fade-vs-protect resolver demotes the fade path to `alternative_command` with no warning connecting the two fields. Added an explicit `FORMAT NOTE` evidence bullet when this fires.
4. Explicit `--output` paths had no overwrite guard — only derived names got the existing `_v2`/`_v3` escalation. Added a stderr WARNING (not a refusal, to avoid breaking legitimate re-render workflows).
5. SKILL.md: documented the previously-undocumented "nameable fade" `--auto` refusal (`--assume-no-fade`/`--fade-color`) that three fresh trial sessions hit blind; clarified the "0. Start with `--auto`" step-numbering confusion; noted `--recommend` already embeds `--analyze`'s full report so calling both wastes a duplicate analysis pass (all three trial sessions did).

**Verification run for this batch:** `audit_docs.py` clean. Harness suite 72/74 (2 pre-existing failures, see mistakes section, unrelated to these changes). Render-diff on the 31-asset fast set: clean — only rocket.gif and satellite.gif's fingerprints moved, both by a small opacity *increase* (100.2-100.7%), zero decreases, zero crashes. **Full 106-asset standard set and 797-asset corpus not run this session.**

## Part 3 — the hurricane investigation (commit `e9f8520`, NOT corpus-validated)

This deserves its own section because it went through several real, corrected mistakes and ended in a genuine reversal — read this before touching hurricane.gif again.

**Starting question:** should hurricane.gif use `--recover-fade-alpha` (its badge fades toward pale — is that a real translucency effect the tool should reconstruct, or a painted colour-lightening animation that should stay opaque)?

**What I got wrong, in order, each caught by Harkirat pushing back — don't re-litigate these without new evidence:**
1. First concluded "current opaque treatment is correct" by quoting the tool's own historical `lessons.md §34.2` measurement (`bg_removed_worst 0.39` when forced) without checking it against fresh data. Harkirat: "ignore the history, work using your present knowledge."
2. Redid it "fresh" with a **flawed single-fixed-pixel probe** that happened to land on the outline at some frames, producing a spuriously clean "converges exactly to pure white" result. Corrected with a robust per-frame dominant-colour trace (75 distinct values, smooth, genuinely real animation, no discrete jumps).
3. Rendered `--recover-fade-alpha --fade-color e04886` (matched to palette entry `db4b86`) and declared it broken (a "ghost" effect at frame 60) — **this used the wrong anchor colour**. `db4b86` was a separate, weaker-fitting design element; the real fade family (`fd6050/fd7e71/f7978f/feb0a8/fec7c2`) was mutually collinear at cosine 0.999-1.0000 and sitting unflagged in the "solid" bucket the whole time.
4. Harkirat then supplied the actual answer directly: **there are three independently-fading regions** — left half `#DA4B85`, right half `#FD6252`, outline `#042A75`. Re-rendered with all three named; looked much better (real, coherent translucency, zero pinwheel-icon damage) but a new "ghost octagon" artifact appeared at frame 39 (the asset's own documented worst tumble-risk frame, margin 1.22) — the *outline's own* paler stages (`2f377d, 5a4f8c, 79679c, 937d99, 9f8bb3, bdabc8`, cosine 0.978-0.998 with `052a75`) were themselves stuck as frozen "solid" colours, same bug one level deeper. Harkirat confirmed by eye this is the original boundary re-fading in on the shrunk badge (source frames ~36-51 show a real, dramatic size change, not just colour).
5. Traced the mechanism precisely by reading `build_art_palette`'s actual rejection math (`FADE_RESIDUAL_TOLERANCE=10.0`, tested per-candidate against already-accepted entries) — confirmed a real hand-animated fade's stages routinely sit >10 units off the exact blend line and survive as independent entries even when clearly the same physical fade.
6. **Implemented the real fix**: absorb every palette candidate near-collinear (cosine ≥0.97) with a named/detected fading colour, and paler (closer to background), into the same fading family — propagated through both `protect_parents` (prevents re-merging) and the final `fading` set (a first version of this fix only did the former, which was itself a bug caught and fixed in the same pass — the family survived as separate entries but rendered fully opaque anyway because nothing told the unmix step they were fading).
7. Re-rendered with the fix: ghost octagon gone across the full shrink/grow window (frames 30-51), zero pinwheel-icon damage across all 120 frames (checked programmatically).

**Current honest state:** the fix works and is visually verified on hurricane.gif specifically, including its hardest frames. **It has NOT been run against the repo's other real `--recover-fade-alpha` assets** (the crystal/gift/love/heart-class cases this exact code area has a documented history of regressing on — see the "SATURATION PROMOTION WAS TRIED HERE AND REVERTED" comment in `build_art_palette`). That corpus check is the next required step before this is trusted, and I don't have those specific assets in the trial-scratch sandbox — they're in the repo's real corpus, findable via `scripts/harness/populations.py`.

**Also open from this thread, not yet done:** should `detect_fading_colors`/the auto-detection path get the same family-absorption logic (so a session that doesn't manually name 3 colours still finds all of them)? Currently the fix only applies inside the `--fade-color` (`fade_hexes`) branch, not the auto-detect branch.

## Part 4 — real mistakes made this session (also logged to memory)

- **Accidentally overwrote the 2026-08-19 trial's `STEPLOG.md` files** in `local/Corpus Trial Gifs/agent-{1,2,3}-*/` via an `rsync` that didn't check existing folder contents first. No backup (local/ is gitignored, no Time Machine on this host). Caused a second-order consequence: it also overwrote a harness test fixture (`agent-3-expert/growth_transparent.webp`) that 2 falsifier tests depend on — those 2 tests now fail against the replaced fixture (unrelated to any code change, don't "fix" them by touching the assertions, the fixture itself is gone). Memory: `feedback_never_overwrite_without_permission.md`.
- Two wrong visual claims about a rocket.gif fin before finding the real bug (both retracted, both from trusting a compressed/rendered image over real pixel sampling). Memory: `feedback_verify_the_correction_too.md`.
- An earlier claim that growth.gif's "smoking gun" was frame 74 with near-total loss was also wrong (frame 74 was actually antialiasing-rim noise, byte-identical between old/fixed code); the real, smaller, fix-relevant defect is at frame 71.

## Part 5 — items 6/7/8 from Harkirat's original review, status

- **Item 6, erosion/haloing (galaxy/secure/broadcast/notification):** confirmed real via a measured signal — `blend_pixel_fraction` (fraction of the 2px boundary ring that's an antialiasing blend colour rather than a pure art colour): secure.gif at erosion=0 reads 64.8%, at erosion=2 reads 0.0%; already-calibrated assets (rocket, megaphone at erosion=1) read 3.6%/12.3%, giving real separation. **Harkirat wants a proper detector that naturally learns toward erosion 1/2 for these cases, not a blanket default change.** This metric is validated on 2 assets but the actual calibration-logic change (in `calibrate_edge_cleanup_erosion`, `scripts/remove_gif_background.py:7010`) was not implemented this session — next step.
- **Item 7, hurricane's classification:** resolved, see Part 3 above — reversed from "current behaviour is correct" to "needs `--recover-fade-alpha` with all 3 colours plus the family-absorption fix," pending corpus validation.
- **Item 8, broadcast's remaining defects:** not investigated this session (its regions are fully verified/enclosed, so it's NOT the same mechanism as fix #1 — root cause still unknown). Harkirat confirmed he doesn't have anything additional to add; this can be picked up independently whenever.

## Immediate next steps, in priority order

1. **Corpus-validate the fade family-absorption fix** (`e9f8520`) against real crystal/gift/love/heart-class assets before trusting it broadly.
2. Consider extending family-absorption to the auto-detect path (`detect_fading_colors`), not just `--fade-color`.
3. Design and implement the erosion-calibration fix for item 6 (a real detector, not a blanket default), using `blend_pixel_fraction` or a validated variant as the signal.
4. Investigate broadcast.gif's remaining defects (item 8) — not urgent, no one blocking on it.
5. Run the full 106-asset standard render set and 797-asset corpus score before this branch is considered release-ready — the fast-set check this session was a checkpoint, not the full gate.
6. Re-run `scripts/harness -m pytest -q` once the fade fix is corpus-validated, expect the same 2 pre-existing fixture failures (unrelated).
7. Only then: ask Harkirat about push/merge/tag/release for this branch — none of that has been requested or done.

## Recommended model/effort for continuing

**Sonnet5-High** for the corpus validation and erosion-detector work (steps 1-3 above) — this is premise-risk-bearing work in code with a documented regression history, not just breadth. If the corpus validation surfaces a real regression on another asset, escalate to Opus for redesigning the family-absorption heuristic. Session title: `Sonnet5-High · gate8 fixes: corpus-validate fade fix, erosion detector · Aug 23 session`.
