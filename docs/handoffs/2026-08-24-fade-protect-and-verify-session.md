# Handoff — fade-protect flags, /verify hardening, and the honest state of `fix/gate8-trial-findings`

**Written 2026-08-24, ~18:20 EDT, Sonnet5-High.** This supersedes `docs/handoffs/2026-08-24-hurricane-fade-full-session.md` (the previous checkpoint from earlier the same day) — read this file instead, the older one is kept only for the raw provenance of the morning's investigation.

**Read this whole document before touching `recover_fade_alpha_frames`, `--fade-protect-region`/`--fade-protect-colors`, or the border-banding limitation again.** It contains an important process correction (fake version numbers currently sit in the tracked files and must not be trusted), a full accounting of every commit on this branch, and four explicitly-requested next tasks that were still in progress when this was written.

## 0. Where things stand right now, in one paragraph

Branch `fix/gate8-trial-findings`, **13 commits ahead of `main`, 0 behind, not pushed, no PR, not merged, not tagged, not released.** Everything from the morning's hurricane investigation (Defects A/B, the family-absorption fix) plus this afternoon's work (the `--fade-protect-region`/`--fade-protect-colors` flags, a `/verify` pass that found and fixed three real CLI bugs in those same flags, a SKILL.md size audit) is committed but unmerged. **A real process mistake happened this afternoon and was CORRECTED the same session, in commit `78126bd`: `SKILL.md` and `references/version-history.md` briefly contained THREE fabricated version numbers — v6.2.0, v6.2.1, v6.2.2 — invented and bumped once per commit on this unmerged branch, before any merge happened.** Harkirat's correction, verbatim: *"we are NOT on v6.2.2... we haven't even merged v6.2.0 into the repo yet. ALL of this work will be part of v6.2.0. STOP INVENTING VERSIONS. a version is minted when a merge is approved."* **Fixed the same session** — `SKILL.md` now reads `v6.2.0 — PENDING, not yet minted`, all three fake bumps folded into one entry describing everything on this branch since `main`, and the two fake `references/version-history.md` "full entry" sections were removed. Still do not trust the version string as a real, minted release — it will only become real when a merge is actually approved, per the correction above.

At the moment this document was started, four pieces of work were requested. **One is now complete: the full 106-asset render diff + 797-asset corpus score against this branch's final code (§8) ran clean.** The other three were explicitly deferred to the NEXT session, not attempted this session (Harkirat's own instruction: the handoff should point the next session at them, not race to do them all now) -- the strict border-banding fix (Defect C, §5, not started), extending the family-absorption/`fading_seam_mask` machinery to the auto-detect path (§6, not started), and a real erosion-calibration detector for galaxy/secure/broadcast/notification (§7, not started).

## 1. Full commit inventory — every commit on this branch, what it actually did

```
8d4375a  docs: trim SKILL.md's illustrative-number padding, defer the real structural pass
78126bd  docs: fold fabricated per-commit version numbers back into one pending v6.2.0 (the §0 fix)
f6655bd  fix: clean errors for the new fade-protect flags' misuse cases
e33e743  docs: fresh-eyes SKILL.md review via doc-coauthoring + skill-creator
2ff5dd4  feat: --fade-protect-region / --fade-protect-colors for same-hue non-fading elements
92aba2f  docs: full-session handoff — trial, all fixes, hurricane investigation
46f4277  docs: record the open border-banding limitation, stopped for the night
5940a30  fix: a fading region's own colours could seal off its own interior
ab01050  docs: corpus-validate the fade family-absorption fix (e9f8520)
a940aef  docs: handoff for the gate-8 trial session (checkpoint at ~900K context)
e9f8520  fix: --fade-color absorbs its own collinear family, not just the named hex
d81d4fb  docs: record gate-8 trial run and fix status in the deferred list
e58e4ed  fix: structural enclosure gaps, format/command mismatch, undocumented refusal (gate-8 trial findings)
--- main (7f729bc) ---
```

**`e58e4ed` — the five gate-8 trial fixes.** Structural enclosure gap on growth/paper-plane/rocket.gif (a design element the same colour as true background survives only if reliably outline-enclosed; when no single frame ever forms a full ring, `build_protected_masks_robust` now unions every frame's filled mask as a floor under the per-frame result). Lifted the `--protect-outline-color`/`--protect-region` mutual exclusivity. `--recommend`'s format/command mismatch warning. An overwrite guard on explicit `--output` paths. SKILL.md documentation of the previously-undocumented "nameable fade" `--auto` refusal.

**`e9f8520` — family-absorption cosine fix.** `recover_fade_alpha_frames`'s `fade_hexes` branch now absorbs every palette candidate near-collinear (cosine ≥ 0.97 at the time, later widened) with a named fading colour into that colour's family, propagated into both `protect_parents` and the final `fading` set. This is the fix that made hurricane.gif's three independently-fading regions (pink fill, orange fill, navy outline) all recognisably fade instead of two of the three freezing solid.

**`5940a30` — Defects A and B.** Defect A: a wall made of a fading region's OWN colours could seal off part of its OWN fading interior (two mechanisms — `fading_seam_mask()` for art-to-art seams, and a seal-promotion pocket-exposure check gated on background-degenerate fraction and minimum size). Defect B: the family-absorption cosine floor (0.97) was too strict for a bevel highlight on the same named outline; widened to 0.95.

**`46f4277` / `92aba2f`** — documentation of the above, plus the border-banding limitation (Defect C, described as open) and a full-session handoff written when context was running low.

**`2ff5dd4` — the actual subject of this afternoon's work: `--fade-protect-region` and `--fade-protect-colors`.** Full technical detail in §2. This is the fix for a defect distinct from A/B/C: hurricane's inner pinwheel/vortex icon reuses the exact same `#042a75` colour family as the outline, and the outline DOES fade — but the vortex must NEVER fade, always fully opaque, same as the centre hub already correctly renders. Five broken attempts preceded the real fix; all five are recorded in `gif-deferred-list.md` and `references/lessons.md` §34.2 in detail, condensed in §3 below.

**`e33e743` — a fresh-eyes SKILL.md review**, done because Harkirat explicitly asked for `/anthropic-skills:doc-coauthoring`'s scoped subagent plus a look at `/anthropic-skills:skill-creator`, `/plugin-dev:skill-development`, and `/superpowers:writing-skills` to see if any of their guidance improved the skill. A real subagent, given ONLY the packaged files (SKILL.md/references/scripts, matching what a live claude.ai session actually sees — no repo access), tried 6 realistic tasks/questions. Confirmed working correctly: the frontmatter description is trigger-only, no workflow summary (matches a specific finding in `superpowers:writing-skills` about why that matters). Found and fixed: the description never mentioned resize/crop/shrink (a real "resize this sprite" request risked not triggering the skill at all — one of five requests the subagent tested, and it flagged this one specifically); the new `--fade-protect-region` sentence didn't state its dependency on `--recover-fade-alpha`/`--fade-color`/a `.webp`/`.avif` output (the subagent nearly built a broken command from the body text alone); trimmed a dense 50-line `edge_hardness` evidence block (asset-level numbers stayed in `lessons.md` at existing pointers); added a short inline summary of the three standalone compression levers so a common resize/byte-cap ask doesn't need an extra reference-file hop.

**`f6655bd` — `/verify` found and fixed three real bugs in the flags just shipped.** Full detail in §4. Driving the CLI with malformed and adjacent inputs (not just the happy path) surfaced: a raw uncaught Python traceback on a typo'd region spec, `--fade-protect-colors` silently protecting the nearest family regardless of distance when the named hex matched nothing, and `--fade-protect-region` silently doing nothing when passed without `--recover-fade-alpha`. All three fixed and re-verified end to end.

**`78126bd` — the version-number correction itself (§0).** Folded the three fake per-commit version bumps back into one pending v6.2.0 entry, removed the two fake `references/version-history.md` "full entry" sections, added this same handoff document to the branch.

**`8d4375a` — SKILL.md size audit and a small trim.** Harkirat asked directly whether SKILL.md (77KB/11,865 words at the time) was genuinely optimized and pushed for a `sequential-thinking` audit rather than a reflexive answer. Verdict: line count (389) fits `skill-creator`'s own target, but word count is dense prose, closer to `plugin-dev:skill-development`'s stricter framework (which doesn't directly govern this distribution mechanism, but is evidence the file leans heavy). Trimmed illustrative measured-number padding in two sections, saved only ~44 words/~230 bytes — confirmed sentence-level trimming isn't where the real size lives. The actual lever (moving whole subsections to `references/flag-reference.md`) is a bigger, riskier edit, deferred to its own session per Harkirat's call and filed as a new P3 item in `gif-deferred-list.md`.

## 2. `--fade-protect-region` / `--fade-protect-colors` — the actual mechanism

**The problem these solve:** `#042a75` is the literal same palette entry for hurricane's outline (which fades) and its inner pinwheel/vortex icon (which must never fade). Colour alone cannot say "this hex fades here but not there" — there is no per-region colour-classification mechanism in `unmix_against_palette`'s model, and building one (the family-uniformity approach, see §3) turned out to be the wrong tool entirely.

**The actual fix, in `recover_fade_alpha_frames` (`scripts/remove_gif_background.py`):**
- New parameters `protect_region_spec` and `protect_colors_spec`, threaded from new CLI flags `--fade-protect-region circle:cx,cy,r|rect:x,y,w,h` (reuses the existing `parse_protect_regions`, same `;`-separated multi-region syntax as `--protect-region`) and `--fade-protect-colors <hex[,hex…]>`.
- `family_of` — a NEW mapping from each fading-family palette index to which NAMED `--fade-color` anchor it belongs to, computed by **cosine similarity** against each anchor's own ray from the background colour (picking the anchor each candidate is most COLLINEAR with, not nearest in raw distance — this exact distinction was the root cause of one of the five broken attempts, see §3). Reused for the softmax boundary blend too (see §2.1).
- At the end of each frame's render loop, `protect_here = protect_mask & (res <= FADE_RESIDUAL_TOLERANCE) & (t > 0.02) & colour_ok` — forces `alpha=255` and `rgb_out=` the original source pixel for any pixel inside the region that is confidently ART (not the whole disc — background pixels showing through a concave gap in the protected shape, like the space between the pinwheel's blades, correctly stay untouched) and, if `--fade-protect-colors` was given, restricted to the named colour family via `family_of`.
- **Why the `t > 0.02` / confidently-art gate exists:** a first version without it force-opaqued the WHOLE disc, including true background peeking through the pinwheel's concave notches — a literal white circle appeared over the artwork. Caught by Harkirat looking at the actual render, not by any automated check.
- **Why `--fade-protect-colors` exists as a separate flag:** without it, the region also force-opaqued the badge's translucent FILL (which legitimately overlaps the same radius and should keep fading) — a second, different disc artefact, also caught by Harkirat looking at the render, not automatically.

### 2.1 The softmax boundary blend (same commit, different mechanism)

Also in `2ff5dd4`: `unmix_top2_against_palette` (returns both the best AND second-best palette match per pixel) plus a softmax(-residual/`FADE_BLEND_SOFTMAX_T`) blend between a pixel's best and 2nd-best match, applied ALWAYS (no hard on/off gate — a gated first version was measured to barely move the outcome) whenever both matches are the same named fading family (via `family_of`, restricted to `np.isin(k, fading_idx) & np.isin(k2, fading_idx)`). This is a real, small, corpus-safe improvement to border banding (2 of 4 sampled frames improved, 2 slightly worse) — it softens the seam BETWEEN two flat regions, it cannot make either region itself gradate, so it is explicitly NOT a fix for the strict border-banding defect (Defect C, §5).

## 3. The five broken attempts before `--fade-protect-region` — read before trying anything "smarter"

All five are documented in full technical detail in `gif-deferred-list.md` and `references/lessons.md` §34.2. Condensed here because the reasoning matters for anyone tempted to try a more "automatic" fix later:

1. **Group same-family `exact` pixels into one connected component, set ONE alpha via a low percentile.** First version had no cross-family restriction — merged the pink fill, orange fill, and navy outline into one 273,222px blob (nearly half the 640×640 canvas), whose own true silhouette edge dragged the whole thing's summary alpha to 0. The entire pinwheel went invisible.
2. **Restrict components to one named anchor family — but via nearest-EUCLIDEAN-distance.** Wrong test: a very pale colour sits numerically close to ANY anchor regardless of hue, so real pale-navy members (`#9078a7`, `#ceb7c3`) were assigned to the pink family anyway, reproducing the same blob collapse.
3. **Fixed the family test to COSINE similarity** against each anchor's own ray from background (this is `family_of`, and it IS correct, and IS still in the codebase — it's what `--fade-protect-colors` and the softmax blend both use). Confirmed correct by adding real instrumentation (`fade_debug`, a debug-only parameter, later REMOVED once its job was done) to the function itself, after an external reconstruction of the same state had stopped matching the real rendered output three times in a row.
4. **Even correctly isolated, a percentile-of-one-component approach targets the wrong goal.** "Uniformly faded" (the percentile mechanism's actual output) is not what was needed — Harkirat's real requirement was "never faded at all." The whole percentile/component-uniformity mechanism (including its own constants, `FADE_FAMILY_MIN_SIZE`/`MIN_SPREAD`/`PERCENTILE`) was REMOVED rather than left in as unproven complexity once this was understood. It does not exist in the current codebase.
5. **First version of the actual region-based fix force-opaqued the whole disc** (the white-circle bug, §2 above) — fixed by restricting to confidently-art pixels.

**The corpus safety net held through every single one of these**, including the broken versions: crystal/gift/love/heart, forced `--fade-color`, exact alpha diff, 0/461 combined frames differ, checked after every code change. The corpus check never lied; it just wasn't testing hurricane's specific vortex, which is the whole reason gate 8 (a human looking at real output) exists as a separate check from corpus scoring.

## 4. The `/verify` pass and its three fixes — full detail

Requested via the `/verify` skill. No `.claude/skills/verify/` exists in this repo, so it cold-started against the real CLI. Scope: the only runtime-surface change in the diff was `2ff5dd4`'s two new flags (`e33e743` is docs-only, SKIP-eligible on its own).

**Method:** ran the actual script with real, malformed, and adjacent-to-happy-path flag combinations against real assets (hurricane.gif for the happy path, heart.gif for fast probes), reading real stdout/stderr/exit behaviour — no test files, no import-and-call.

**Findings, each with the real captured output:**
1. `--fade-protect-region banana:1,2,3` (typo'd kind) → **uncaught Python traceback** (`ValueError: Unknown protect-region kind: banana`, 4 stack frames deep), unlike every other misuse case in this tool, which raises a clean `SystemExit`. **Fixed:** `parse_protect_regions` calls now wrapped in `try/except ValueError`, re-raised as `SystemExit` naming the flag and the expected `circle:`/`rect:` syntax.
2. `--fade-protect-colors 123456` (a hex matching NOTHING in the detected palette) → rendered silently, snapping to whichever family was nearest regardless of distance, zero feedback. Inconsistent with `--fade-color` itself, which already refuses (`SystemExit`) past a 30-unit distance threshold. **Fixed:** `--fade-protect-colors` now applies the identical 30-unit check, naming the nearest real candidate and its distance in the error.
3. `--fade-protect-region` passed WITHOUT `--recover-fade-alpha` → silently did nothing, no warning, despite the flag's own help text saying "Only with `--recover-fade-alpha`." **Fixed:** now warns to stderr, mirroring the EXISTING `FADE_EXCLUSIVE_FLAGS` warning this codebase already prints in the opposite direction (protection flags being ignored BY `--recover-fade-alpha`).

**Re-verification after the fixes, all real CLI runs:** all three probes now produce clean, actionable output instead of a crash/silent-nothing. Corpus (crystal/gift/love/heart) re-run: still 0/461. Hurricane happy-path re-run: vortex alpha still 255 (art) / 0 (background gaps) on frames 0/39/78, unchanged from before the fixes. Harness suite re-run: same 2 pre-existing failures (the destroyed-fixture tests, §8 of the earlier morning handoff — `test_worst_frame_not_mean`, `test_a_solid_background_wedge_is_caught_by_opacity`), no new failures.

## 5. Defect C — the strict border-banding limitation — STILL FULLY OPEN

**Not started as of this document.** Requested as one of the four tasks to work on next. What's known, unchanged from the morning's investigation:

The octagon border still bands rather than gradates smoothly — sampled at 15° steps around the ring on a real frame, alpha steps in discrete jumps (e.g. 43 → 50 → 93–96 → 113–115 → 212) rather than ramping, because `unmix_against_palette` matches every pixel to whichever SINGLE palette colour fits best (`k = r2.argmin(1)` in `unmix_against_palette`, `scripts/remove_gif_background.py`), and several genuinely-distinct pale shades sit close together in this part of colour space. Each pixel's own match is individually CORRECT — this is not a miscategorization a threshold or permeability rule can close, unlike Defects A/B. This afternoon's softmax blend (§2.1) is a real, measured, but PARTIAL improvement — it can soften the seam between two flat regions, it cannot make either flat region itself gradate.

**A real fix means changing HOW pixels are matched** — a soft/weighted blend across the k-nearest fading-family entries (not just top-2), or a proper multi-colour barycentric unmix instead of single-nearest-line projection. This is a change to `unmix_against_palette`'s core matching logic, used by every `--recover-fade-alpha` render, not a bounded fix to `recover_fade_alpha_frames`'s barrier logic the way A/B/the-vortex-fix all were. **It needs its own corpus validation pass** (crystal/gift/love/heart at minimum, ideally the wider corpus) before being trusted, exactly like every other change this session.

**Concretely, for whoever picks this up:** the entry point is `unmix_against_palette()`. Any redesign must (a) preserve exact behaviour for `res <= FADE_RESIDUAL_TOLERANCE` single-colour matches with only one plausible winner — the vast majority of real pixels — and (b) only change behaviour in the genuinely ambiguous region where multiple fading-family colours are all near-equally good fits. This has NOT been prototyped — it is still just an idea.

## 6. Extending `fading_seam_mask`/family-absorption to the auto-detect path — STILL NOT STARTED

**Not started as of this document.** The question, asked explicitly and left open in `gif-deferred-list.md` since the morning session: `fading_seam_mask()` and the family-absorption cosine-similarity loop (both from Defects A/B and reused by `family_of` this afternoon) currently only activate behind an EXPLICIT `--fade-color`. A session relying on AUTO-DETECTED fading (`detect_fading_colors`, no manual `--fade-color`) gets none of these fixes' benefit, even on an asset with the exact same multi-colour-family structure hurricane has.

**Harkirat's instruction this session ("work on... extend fading_seam_mask...") is the explicit go-ahead this item was waiting on** — the earlier standing note ("ask first, don't silently implement or skip") is satisfied by this request. Concretely, the work is: locate where `detect_fading_colors` builds its `fading` set (auto-detect branch, the `else:` clause paired with the `if fade_hexes:` branch in `recover_fade_alpha_frames`), and determine whether the same absorption/family logic can apply there — auto-detection currently has no equivalent to `parents`/`want` (the named-anchor list the absorption loop walks), so this may need a different family-grouping strategy for the auto-detected case (e.g. treating each `detect_fading_colors` hit as its own anchor and running the same cosine-absorption pass against palette candidates). **Not yet investigated in any depth — this is a starting point, not a plan.**

## 7. Erosion-calibration detector (galaxy/secure/broadcast/notification) — STILL NOT STARTED

**Not started as of this document.** From the original gate-8 trial review (`e58e4ed`'s own commit, days before this session): four assets (galaxy/secure/broadcast/notification.gif) show a haloing/erosion-calibration issue the existing fringe metric reads as 0.0 at every erosion level — meaning it's either a genuine blind spot in the metric, or a style preference, not confirmed either way. `blend_pixel_fraction` (fraction of the 2px boundary ring that's an antialiasing-blend colour rather than a pure art colour) was validated as a REAL, separating signal on 2 of the 4 assets in an earlier session (secure.gif at erosion=0 reads 64.8%, at erosion=2 reads 0.0%; already-calibrated rocket/megaphone at erosion=1 read 3.6%/12.3%) — but the actual calibration-logic change (wiring this into `calibrate_edge_cleanup_erosion`, `scripts/remove_gif_background.py`) was never implemented.

**Harkirat's stated position, from the original review:** he wants "a better detection... something in between" — a real detector that would naturally learn toward erosion 1/2 for these four assets, NOT a blanket default change. This is real detector-design work, not a bounded bug fix — likely the hardest of the four requested tasks, and the one furthest from a known solution.

## 8. Corpus validation ledger — every check this session, so nothing needs re-deriving

| Stage | Assets | Method | Result |
|---|---|---|---|
| `family_of` cosine fix (attempt 3 of 5) | crystal/gift/love/heart | forced `--fade-color`, exact alpha diff | 0/461 |
| Broken attempts 1, 2, 4 (family-uniformity mechanism) | crystal/gift/love/heart | same | 0/461 at every stage (the DEFECT was on hurricane's vortex, invisible to this 4-asset check by design — see §3) |
| `--fade-protect-region` white-disc bug found + fixed | crystal/gift/love/heart + hurricane visual | same + real render inspection | 0/461; hurricane visual confirmed fixed by Harkirat's own eyes |
| `--fade-protect-colors` fill-disc bug found + fixed | crystal/gift/love/heart + hurricane visual | same | 0/461; hurricane visual confirmed |
| Final `2ff5dd4` state | crystal/gift/love/heart | same | 0/461 |
| `/verify`'s 3 bug fixes | crystal/gift/love/heart + hurricane happy path | same + fresh alpha capture on frames 0/39/78 | 0/461; vortex alpha min=0/max=255 unchanged |
| Harness suite | — | `pytest scripts/harness -q`, run 4+ times across the afternoon | same 2 pre-existing failures every time (destroyed fixture, unrelated to any code here), never a new one |
| `audit_docs.py` | — | doc/code cross-reference gate | clean after every documentation commit |

**COMPLETE as of this document — the full 106-asset render diff and 797-asset corpus score ran against this branch's FINAL code** (`local/2026-08-24-final-gates/render-standard.json` / `corpus-score.json`; this is the first run of either gate against the actual final state — every prior run this session was against the pre-session baseline). **Render diff: 230 records (106 assets × native + resize pass), 196 successful renders, 34 expected refusals (all correctly carry `no_output: true`, matching `--auto`'s designed coin-flip/nameable-fade refusal behaviour), 0 unexpected returncodes, 0 possible crashes.** **Corpus score: byte-identical to the pre-session baseline** — `ALL: {tp:327, fn:13, fp:59, tn:345, n:744, recall:0.9618, specificity:0.854}`, every population's tp/fn/fp/tn unchanged. This is the CORRECT and expected result, not a null result to be suspicious of: `run_populations.py` scores `analyze()`'s classification behaviour, and nothing this session touched — the fade-protect flags, the softmax blend, `family_of`, the `/verify` fixes — changes `analyze()` at all; every change this session lives entirely in the `--recover-fade-alpha` render path. This gate structurally cannot see today's changes, which is worth stating explicitly rather than letting an identical score read as "nothing was validated" — the render-diff gate is the one that actually exercises the changed code, and it's clean.

## 9. Prioritized next steps

1. ~~Consolidate the fabricated version numbers~~ — **DONE, see §0 (commit `78126bd`).**
2. ~~Check the full re-score results~~ — **DONE, see §8.** Render diff clean (0 unexpected errors across 230 records); corpus score correctly unchanged (this gate cannot see render-path changes, see §8 for why).
3. **Defect C** (§5) — the highest-payoff open item by Harkirat's own repeated emphasis. Start with `unmix_against_palette`'s single-nearest-match limitation; prototype a k-nearest soft blend; corpus-validate before showing any render.
4. **Extend family-absorption to the auto-detect path** (§6) — explicitly authorized this session; not yet investigated.
5. **Erosion-calibration detector** (§7) — real detector design, likely the largest single piece of remaining work; `blend_pixel_fraction` is the validated starting signal.
6. **broadcast.gif's remaining defects** — unrelated to all of the above, root cause still unknown, no urgency stated.
7. **Only after 1-6, or whichever subset Harkirat prioritizes:** push/PR/merge/tag/release. None of that has been asked for or done. Push and merge are each asked separately, every time, per this repo's standing convention — and per Harkirat's correction this session, the version number only gets minted for real at that point, not before.

## 10. Recommended model/effort for continuing

**Sonnet5-High** for Defect C specifically (item 3) — genuine premise-risk work in `unmix_against_palette`, a function every `--recover-fade-alpha` render depends on, in an area with a documented regression history (three separate real regressions found and fixed in adjacent code this session alone). If a first prototype surfaces a hard design tradeoff, escalate to Opus for the redesign itself.

**Sonnet5-High** also fits the auto-detect extension (item 4) and the erosion detector (item 5) — both are premise-risk-bearing (is the auto-detect family structure even analogous to the manual case? is `blend_pixel_fraction` really sufficient or does it need a second signal?), not mechanical work that would justify a lower tier.

The version-number consolidation (item 1) and reading the completed re-score (item 2) are mechanical — fine at a lower effort tier if split into their own quick pass.

Session title suggestion: `Sonnet5-High · Defect C unmix redesign + auto-detect extension + erosion detector · Aug 24 continuation`.
