# Handoff — Defect C closed, code-review fixes, lessons.md structural audit, and the next two tasks

**Written 2026-08-24, ~23:10 EDT, Sonnet5-High.** This supersedes both other 2026-08-24 handoffs in this directory (`2026-08-24-fade-protect-and-verify-session.md`, `2026-08-24-hurricane-fade-full-session.md`) — read this file instead; the older two are kept only for the raw provenance of the morning/afternoon investigation this session continued from.

**Read this whole document before touching `scripts/remove_gif_background.py`'s fade-recovery code, or before starting the two tasks Harkirat explicitly queued next (§7).** It contains the full accounting of this session's 4 commits, the real numbers behind every validation claim, a harsh structural self-audit of `references/lessons.md` §45 (two real bugs found and fixed in it), and the exact starting point for the next session.

## 0. Where things stand right now, in one paragraph

Branch `fix/gate8-trial-findings`, **18 commits ahead of `main`, 0 behind, not pushed, no PR, not merged, not tagged, not released.** This session (continuing from the `a92e20a` checkpoint) added 4 commits: `0b94419` (auto-detect fade-family absorption + erosion blend-fraction detector + border-banding family-blend generalization, bundled as one feature commit), `d3f5a83` (two real correctness bugs found by an 8-angle code review, fixed), `47d7936` (Defect C — border banding — closed via real visual inspection, not just pixel forensics), `9762bfc` (a harsh self-audit of `lessons.md` §45 found and fixed a real ordering bug and a direct self-contradiction, both self-inflicted by how the section was edited). **Every gate that exists for this repo was run against the final combined state and is clean**: 797-asset corpus score byte-identical to baseline, 106-asset render-diff shows only the 3 expected/intentional changes (0 crashes), full `pytest scripts/harness` shows the same 2 pre-existing unrelated failures and 0 new ones, `audit_docs.py` and the soft-wrap checker both pass. Full ledger in §6.

**Harkirat's explicit direction for the NEXT session (verbatim intent, not paraphrased away): feature work is done for now. The next two tasks are (1) SKILL.md's deferred structural pass (already filed as a P3 item, see §7.1) and (2) an audit of `lessons.md` for repo-specific content, gaps, and staleness — a CONTENT audit, distinct from the structural ordering/contradiction fix already done in commit `9762bfc` (see §7.2 for exactly what is and isn't already covered).** Nothing else was requested — do not resume Defect C, the erosion detector, or the auto-detect absorption work without being asked; all three are closed and validated (§1-§3).

## 1. This session's actual work — what changed and why, per commit

### 1.1 `0b94419` — three continuations of the gate-8 trial's open items, bundled

Three independent fixes, all touching the same fade-recovery/edge-quality machinery in `scripts/remove_gif_background.py`, documented together in `references/lessons.md` §45 (§45.1-45.3):

**§45.1 — auto-detect fade-family absorption.** The collinear-family absorption loop (folds a palette candidate into a named fading anchor's family when near-collinear, cosine ≥0.95, and paler than it) previously only ran behind an explicit `--fade-color`. Extended to the auto-detect (`detect_fading_colors`, no named hex) branch too, anchored on `_auto_anchors` (a snapshot of each auto-detected colour's own pre-absorption colour). `family_of`'s anchor list generalised to `_family_anchors = want if fade_hexes else _auto_anchors`, one shared cosine-nearest-anchor computation instead of two. **Corpus-validated** on crystal/gift/love in pure auto-detect mode: crystal/love byte-identical (single-anchor families, no absorbable candidate — structural no-op, as predicted); gift genuinely absorbs `fa7fa0` into `fd6050`'s family now (36,990 alpha px, 77/172 frames, every delta 1-3 units — small, bounded, matches the SAME absorption already validated safe on the named-hex path). **Known limitation: gift is the only real corpus asset that exercises this fix with an actual behaviour change** — crystal/love are structural no-ops, and no second real multi-member auto-detected-family asset was found or tested. This is a real, standing gap in test coverage for this specific fix, not something resolved this session.

**§45.2 — erosion-calibration detector, the P1 open since the original gate-8 trial.** `calibrate_edge_cleanup_erosion` picked its level from ONE signal, `measure_outer_ring_background_fraction` ("is this ring pixel closer to background than to art") — blind by construction to a halo pixel that's more than half art but still an unresolved antialiasing mix. Measured directly against real `--auto --edge-cleanup-erosion N` output (N=0,1,2): **galaxy.gif read 0.0000 on this signal at EVERY level.** New signal `measure_outer_ring_blend_fraction` (does this ring pixel unmix as a genuine partial blend at all — reuses `detect_fading_colors`'s own blend vocabulary) reads **0.5989 → 0.1359 → 0.0003** on galaxy, a clean monotone separation. `calibrate_edge_cleanup_erosion` now takes the per-frame MAX of both signals. **Confirmed via the real CLI's own calibration log line** (not a probe): galaxy now correctly selects erosion=1 (was 0); the two healthy controls rocket.gif/secure.gif land on the identical erosion=1 they already got, unchanged. broadcast.gif's own separate defect (unrelated, enclosed-region classification, still open — §5.3) is untouched, as expected. **notification.gif and megaphone.gif could not be probed at all** — both hit `--auto`'s v6.1.0 refusal gates (nameable fade / partial enclosure) before erosion calibration is ever reached. This is an orthogonal, pre-existing gap this fix does not cause or resolve — **notification.gif's actual erosion/haloing status remains genuinely unknown**, not just untested.

**§45.3 — border-banding, generalised from top-2 to the whole family, then CLOSED via visual inspection (see §2 — this is where the real methodological lesson of the session lives).** The already-shipped top-2 softmax blend was traced on two REAL adjacent hurricane pixels and found to still step 22→122 — each pixel's own blend was individually correct, but WHICH TWO of the border's 9 absorbed family members ranked "top-2" flipped between neighbours, since a family this size isn't well served by only ever blending the best pair. Generalised `unmix_top2_against_palette` (deleted, now dead) into `unmix_family_blend` — softmax over the WHOLE family, a strict generalisation (reduces to old behaviour with ≤2 close members, confirmed by corpus diff). Same traced pixel pair improved to 22→97 (Δ100→Δ76); frame-wide large jumps fell from 2,460 to 2,149 (~13%). **This was initially documented as "not a full fix"** — see §2 for why that framing was itself wrong, corrected the same session.

### 1.2 `d3f5a83` — an 8-angle code review of `0b94419` found two real bugs

Requested via `/code-review medium effort` against `main...HEAD`. 8 finder agents in parallel (3 correctness angles, reuse, simplification, efficiency, altitude, CLAUDE.md conventions), each candidate independently re-verified by direct execution (not trusted from the agent's report). **7 findings survived verification, all fixed:**

1. **`unmix_family_blend` NaN hazard (CONFIRMED, correctness).** Summing softmax weights across the whole family, with no floor on the per-member `dd` denominator, means a family member at/near the background colour (reachable via `force_include` injecting a named `--fade-color` or an absorbed collinear stage with no distance-from-background floor) produces `NaN` for the WHOLE pixel's output. Unlike the old `argmin`-based path (which naturally skips a NaN candidate), summing does not self-protect. **Reproduced directly** (a 2-member family with one member equal to `bg` → `alpha=nan` for every pixel). **Fixed:** `dd = np.maximum((d*d).sum(1), 1e-6)`.
2. **`--fade-protect-colors` wrong-family selection (CONFIRMED, correctness).** Matched the typed hex to the nearest palette entry via raw EUCLIDEAN distance, then read THAT entry's (correctly cosine-computed) family — reproducing, at the user-facing boundary, the exact pale-colour-nearest-wrong-anchor bug `family_of`'s own cosine fix exists to prevent internally. **Demonstrated on hurricane's real palette**: `#9078a7`/`#ceb7c3`/`#816d8e` are cosine-family navy but Euclidean-nearest to the unrelated pink anchor. **Fixed:** extracted `_nearest_anchor_by_cosine` as a shared helper, used by both `family_of` and `--fade-protect-colors`; the Euclidean check is kept only for its original purpose (does the typed hex match a real detected colour at all, refuse past 30 units).
3. **Test-coverage gap (CONFIRMED).** `test_erosion_component_protection.py` only ever monkeypatched `measure_outer_ring_background_fraction`; the new `measure_outer_ring_blend_fraction` ran for real against a fixture whose alpha never clears `opaque_min=250`, so it always silently returned `None` and the whole dual-signal max() combination had zero coverage. **Fixed:** added `_BlendCurve`/`_calibrate_dual` plus two real tests exercising the combination directly (one mirrors galaxy's exact shape — bg-fraction blind, blend-fraction not — the other guards the already-correct rocket/secure case against regression).
4-5. **Two real duplication findings**, both fixed by extraction: the collinear-family absorption loop (near-identical between the `fade_hexes` and auto-detect branches) → `_absorb_collinear_paler_stages`; the cosine-nearest-anchor math (written 3 times: twice in the absorption loops, once in `family_of`) → the same `_nearest_anchor_by_cosine` helper reused everywhere (also closes finding 2 above, since it's the SAME fix). 6-7. **Two efficiency findings**, both fixed: `unmix_family_blend`'s render-loop call restricted to the `blend`-masked pixel subset instead of the whole frame (`rgb[blend][None,:,:]` in, unpack `[0]` out); `calibrate_edge_cleanup_erosion`'s new signal given a **lazy** per-frame unmix cache shared across erosion candidates, since the unmix result is candidate-invariant.

**⚠️ One real bump worth knowing about if you touch this area again:** the FIRST version of the efficiency fix for #7 used an EAGER precompute (`unmix_against_palette` called unconditionally for every frame before any candidate ran) and broke all 32 tests in `test_erosion_component_protection.py`, because the synthetic test fixtures are `(4,4)` arrays with no RGB channel (they never needed real pixel math before, since every real measurement function was always mocked). The lazy-cache redesign (compute-on-first-real-need, respecting the function's own empty-ring early-return) fixed it correctly. **Lesson, recorded in `linksee` memory too:** a function that SUMS over candidates is not automatically NaN-safe just because a similar `argmin`-based function was; and prefer a lazy cache over an eager precompute when hoisting work out of a loop, so a callee's own short-circuit still protects test fixtures that don't look like production data.

One review candidate (a claimed `NameError` on an undefined `want` variable) was investigated and **REFUTED by actually running the code end to end** — it succeeds. The reviewer agent had found a same-named-but-different, earlier-scoped `_want` and missed the real, later `want = [...]` assignment the flagged line actually pairs with. Kept in the record (`references/lessons.md` §45.4) as a reminder that an agent's static trace of a large function is not the same as running it.

### 1.3 `47d7936` — Defect C (border banding) actually CLOSED, and how

This is the most important methodological result of the session, worth internalising before doing more forensic pixel work on this codebase. After `0b94419`'s family-blend fix, a broader scan still found ~2,100 large (>60-unit) neighbour-pixel alpha jumps in hurricane frame 35's mid-alpha region. Individually tracing a sample of these (real instrumentation, real palette, real `unmix_family_blend` weights — not a reconstruction) found a real, consistent signature: the still-jumping pixels have a MUCH worse best-single-ray fit than their clean neighbours (e.g. `res=6.61` vs `res=1.08`, six times worse) — consistent with genuine antialiasing between two DIFFERENT design elements (the pink fill touching the navy border), not within-family ambiguity a wider blend can smooth.

**Pixel-level forensics alone cannot distinguish "this is still a bug" from "this is correctly rendering a real multi-element boundary" at the scale of ~2,100 candidate pixels.** What actually settled it: the real render was composited over a checkerboard (so partial alpha is visible) and inspected directly — full-canvas views at frame 0 (fully opaque baseline), frame 35 (the original motivating frame), frame 39 (the documented worst tumble-risk frame), frame 78 (mid-tumble, heavy fade), plus 4x-zoomed crops of the SPECIFIC traced boundary pixels. **None show jarring banding.** The border reads as a smooth, uniformly-toned translucent ring at every fade depth checked. The pink/orange split down the badge's middle is genuine two-colour design, not an artefact. The zoomed crop of the traced boundary shows a normal antialiased diagonal edge between two elements — not a stepped artefact. **Conclusion: the family-blend generalisation from `0b94419` is the complete fix for the original defect.** The k-nearest/barycentric `unmix_against_palette` redesign that had been flagged as the likely next step was NOT needed — a wrong conclusion pixel forensics alone was heading toward, corrected by actually looking at the rendered output.

**If a future session's forensic pixel scan of THIS codebase's fade-recovery output again finds a large count of "unexplained" jumps: render it, composite over a checkerboard, and LOOK before assuming there's still a bug.** The images are saved at `/tmp/hurricane_frame{0,35,39,78}_full.png` and `/tmp/hurricane_crop_*.png` on this machine if still present (not committed — regenerate via the same method if gone: see the render script pattern in `references/lessons.md` §45.3's own commit history, or ask — the exact script isn't saved anywhere durable, this note is the only record of the method).

### 1.4 `9762bfc` — a harsh self-audit of `lessons.md` §45 found and fixed two real bugs Harkirat asked to be found

Requested explicitly: "actively invoke sequential thinking and HARSHLY audit your lessons.md... structure, organization, gaps, things you didn't consider, angles not checked." Ran `sequential-thinking` (mandatory per this repo's standing convention for audits) and found, by directly re-reading the section rather than trusting memory of having written it correctly:

1. **§45.4 (a code-review bug report ABOUT §45.1-45.3) physically sat BEFORE §45.1-45.3 in the file.** Caused by every one of the 3 separate edits to this section anchoring on the `## 45.` heading string and prepending — each new insertion pushed earlier content down, so the LAST subsection written ended up FIRST. A linear reader would hit "here are 2 bugs found in this work" before ever reading what the work was.
2. **A direct self-contradiction.** The section's own overview paragraph (itself misplaced per #1) still said *"§45.3 is... NOT a full fix"* after the `47d7936` commit had already updated §45.3 itself to say CLOSED. Same file, same section, contradicting itself.

**Both fixed:** reordered to 45.1→45.2→45.3→45.4 (matching this file's own established forward-ordering convention, verified against §44's 44.1-44.9), overview paragraph corrected to state all four subsections' real status. `audit_docs.py` passed clean through all 3 prior edits despite both defects being live the whole time — **it checks pointer/reachability integrity (ToC/symptom-table/§N resolution), not subsection order or cross-subsection content consistency.** This is a real, generalisable gap in that gate, reported to Harkirat but deliberately NOT patched into the gate this session (a rushed gate change without the file's own falsifier-suite discipline would be worse than leaving it named).

**Scope note: this audit covered ONLY the session's own new content (§45), not sections 1-44.** No evidence of drift was found or looked for there. This is the load-bearing distinction for §7.2 below — the audit Harkirat wants next is different in kind and scope from this one.

## 2. Full validation ledger — every gate run this session, against the FINAL combined state (all 4 commits)

| Gate | Result |
|---|---|
| `pytest scripts/harness` (full suite) | Same 2 pre-existing failures (`test_worst_frame_not_mean`, `test_a_solid_background_wedge_is_caught_by_opacity` — destroyed-fixture tests from an unrelated `rsync` incident weeks ago), 0 new. Run 3+ times across the session, always identical. |
| `scripts/harness/run_populations.py` (797-asset corpus score) | Byte-identical to the documented pre-session baseline: `{tp:327, fn:13, fp:59, tn:345, n:744, recall:0.9618, specificity:0.854}`. Correctly unchanged — none of this session's code touches `analyze()`'s classification path (everything lives in the render/`--auto` path); this is the SAME structural-blindness reasoning already documented for the afternoon session's work. |
| `scripts/harness/render_baseline.py --set standard` (106-asset render-diff) | 230 records (106 assets × native + resize), compared against the pre-session baseline: **exactly 6 changed** — `galaxy.gif` native+resize (the intended erosion fix, opaque count drops ~3.7-3.9%) and 2 `unsuitable_no_edges` sprite files (`Overlay/15.png`, `Overlay/20.png`, 0.3-1.0% opaque-count change, plausibly the fade-absorption path triggering slightly differently on a borderline case — flagged, not root-caused, see §5). 0 crashes, 0 unexpected returncodes, 196/230 produced output (34 expected refusals, same count as baseline). Run TWICE (once after `0b94419`+review-fix, once after Defect-C-closure+lessons-audit) — identical result both times, confirming the docs-only final 2 commits changed nothing render-relevant, as expected. |
| `python3 scripts/audit_docs.py` | Clean, run after every documentation-touching commit (5 times total this session). |
| `node reflow-prose.mjs --check` (soft-wrap) | Clean on every `.md` file touched, every time. |
| Forced-`--fade-color` corpus diff (crystal/gift/love, exact alpha diff) | Run 3 times across the session (after `0b94419`, after `d3f5a83`, implicitly unaffected by the docs-only commits): byte-identical on crystal/love throughout; gift shows the same small, bounded, already-explained delta each time (max alpha delta 32, mean 2.65, no wild swings, no 0↔255 flips). |
| Auto-detect corpus diff (crystal/gift/love, no `--fade-color`) | Run twice: after `0b94419` (validates §45.1 in isolation) and after `d3f5a83` (validates the review fixes don't regress it) — crystal/love unchanged both times; gift's delta is small and bounded both times. |
| Direct NaN-hazard repro | Confirmed broken before the fix (`unmix_family_blend` on a degenerate 2-member family → all-NaN output), confirmed fixed after (finite output, no warning). |
| Direct wrong-family repro | Confirmed broken before the fix (hurricane's `9078a7`/`ceb7c3`/`816d8e` Euclidean-mismatch to the wrong anchor), confirmed fixed after (all three now correctly resolve to the navy family via the shared cosine helper). |
| Real end-to-end erosion-selection log line | `galaxy.gif` → erosion=1 (was 0, confirmed via a REAL `--auto` run's own printed calibration line, not a probe); `rocket.gif`/`secure.gif` → erosion=1 (unchanged, confirmed the same way). |
| Visual inspection (Defect C closure) | 4 full-canvas composited frames (0/35/39/78) + zoomed crops of the traced boundary — no jarring banding found at any fade depth. |

## 3. Backlog, unchanged in scope from before this session, not touched

These were already known before this session and remain open — nothing here is new:

1. **notification.gif's erosion/haloing status is genuinely unknown**, not just untested (§1.1, §45.2) — blocked by an unrelated `--auto` refusal gate that fires before erosion calibration is ever reached.
2. **broadcast.gif's own defect** (an enclosed-region classification issue, unrelated to fade or erosion) — root cause still not found, not investigated this session.
3. **The auto-detect absorption fix (§45.1) has only one real test case** (gift.gif) — crystal/love are structural no-ops for it, and no second real multi-member auto-detected-family asset has been found or tested.
4. **The 2 sprite files' small render delta** (§2, render-diff table) — flagged as plausibly related to the fade-absorption path, never actually traced to confirm why.

None of these are queued for the next session per Harkirat's explicit direction (§0) — do not pick them up without being asked.

## 4. Skill version / release status — unchanged, do not infer otherwise

Still exactly as the last several handoffs described: repo `main`/git tag at **v6.1.0**, live claude.ai skill at **v6.0.0** (uploaded 2026-08-21). **This session's 4 commits are NOT yet a minted version** — per the correction earlier this same day (commit `78126bd`), a version is minted only when a merge is approved, and none of this session's commits have been merged, pushed, or even had a PR opened. If a version number matters for the next session's work (it shouldn't, for the two tasks in §7), do not bump `SKILL.md`'s pending-version line without an actual merge happening first.

## 5. What did NOT happen this session (be precise about this before assuming otherwise)

- No push, no PR, no merge, no tag, no release. Explicitly deferred by Harkirat ("nothing pushed" — his own words, this session's final message).
- No work on notification.gif, broadcast.gif, or widening auto-detect test coverage (§3) — not requested.
- No SKILL.md structural pass — filed as a P3 backlog item BEFORE this session (`gif-deferred-list.md` line ~242) and is now the explicit next task (§7.1), not started.
- No `lessons.md` CONTENT audit (repo-specific staleness, gaps in coverage) — the audit done this session (`9762bfc`) was STRUCTURAL, scoped to §45 only, and explicitly distinct from what's being asked for next (§7.2).

## 6. Model/effort recommendation for the next session

**Sonnet5-High** for both queued tasks, and they can reasonably be done in the same session (they're both careful, low-premise-risk editing/auditing work on markdown, not a design decision with real uncertainty):

- **SKILL.md structural pass (§7.1):** mechanical-leaning (move whole subsections to `references/flag-reference.md`, keep rule+pointer in SKILL.md) but genuinely needs care per Harkirat's own framing of the risk ("checking nothing load-bearing — a threshold value, a verbatim error-text block a reader needs to recognise — gets cut in the move"). Not Opus-tier premise risk, but not a mechanical find-replace either — Sonnet5-High fits.
- **lessons.md content audit (§7.2):** this is closer to genuine judgment work (what's stale, what's a real gap, what repo-specific content doesn't belong) than the structural fix just done, and benefits from the same `sequential-thinking`-mandatory discipline just used. Sonnet5-High, not a lower tier — this file is large (2,862 lines, ~75K words) and has a documented history of exactly this kind of subtle self-inflicted defect (§1.4).

If either task surfaces a hard design tradeoff (e.g. a genuine ambiguity about whether a whole section of SKILL.md should move or stay), escalate to Opus for that specific decision rather than the whole session.

Session title suggestion: `Sonnet5-High · SKILL.md structural pass + lessons.md content audit · Aug 24 continuation`.

## 7. The two next tasks — full detail

### 7.1 SKILL.md's structural pass (filed as a P3 backlog item, `gif-deferred-list.md` line ~242, 2026-08-24)

**Current size** (re-measured at the end of this session): 391 lines, 12,015 words. **Verdict already reached and NOT to be re-litigated:** line count is fine (within `skill-creator`'s own target for this distribution mechanism — an `anthropic-skills:`-namespaced claude.ai package), but word density (~30 words/line) is far denser than a lean reference should be. A same-day sentence-level trim pass earlier this session (the afternoon's `8d4375a` commit) saved only ~44 words / ~230 bytes — **genuinely negligible, already tried, do not repeat that approach.**

**The real lever, per Harkirat's own call:** move WHOLE SUBSECTIONS (identified candidates: the WebP method-tuning detail, byte-count tables) into `references/flag-reference.md`, keeping only the decision-relevant rule + one-clause why + pointer in SKILL.md's body. This is `skill-creator`'s own progressive-disclosure principle, applied directly — not a novel technique, just not yet done at the structural level.

**Concrete first steps for the next session:**
1. Read `SKILL.md` in full (via `grep -n "^##"` for the outline first, per the file's own stated reading convention at its own top — do NOT `cat`/read-whole without that, and remember `grep` not `rg` if simulating what claude.ai's sandbox would see, since `rg` is not present there).
2. Identify every subsection that is (a) not itself the decision rule a reader needs at trigger time, and (b) already has a natural home in `references/flag-reference.md` or another existing reference file.
3. Before moving anything, check for exactly the failure mode Harkirat named: does this subsection contain a threshold VALUE, a verbatim ERROR-TEXT block, or other content a reader needs to literally recognise at the point of use (not just understand once)? If yes, the move needs a pointer PLUS the load-bearing fragment kept inline, not a bare "see references/X" redirect.
4. After each move, run `python3 scripts/audit_docs.py` (checks packaged-file pointers resolve) and the soft-wrap checker — both must stay clean.
5. This is a repo-side-only editing task, not a code change — no corpus/render gates apply, but the packaging safety check (release gate 3/4 in `CLAUDE.md`, "every `references/…` pointer in the packaged SKILL.md must resolve inside the zip") matters if this work reaches a real package build.

### 7.2 `lessons.md` audited for repo-specific content, gaps, and staleness — a CONTENT audit, NOT the structural fix already done

**This is explicitly distinct from `9762bfc` (§1.4 above), which only fixed a physical-ordering bug and one self-contradiction in the ONE section this session added.** What Harkirat is asking for next is broader and different in kind:

- **"Repo-specific content"** — likely means: does this file (which is meant to be a general lessons/postmortem record for THIS skill's development) contain anything that has drifted into being repo-workflow-specific rather than skill-behaviour-specific, given `CLAUDE.md`'s own explicit "Repo conventions... REPO SIDE ONLY, do not move these into packaged files" boundary (this file IS one of the 3 packaged files a live claude.ai session can see — `SKILL.md` + `references/` + `scripts/`). Check whether any section describes a REPO-SIDE process (git workflow, release gates, corpus-harness mechanics) rather than a lesson about the SKILL's actual behaviour — that would need to move to `CLAUDE.md` or `gif-deferred-list.md`, not live in a packaged reference file.
- **"Gaps"** — sections/lessons that are referenced from elsewhere (SKILL.md, the symptom table, other lessons sections) but don't actually exist, or exist but are unreachable from the ToC/symptom table (this file's own stated failure mode, previously measured at "6 of 25 sections had become unreachable"). `audit_docs.py` already checks SOME of this (ToC/symptom-table resolution) — the audit should look for what that gate does NOT check: is the symptom table actually comprehensive, or does it just happen to route to sections that already exist without covering realistic symptom phrasings?
- **"Staleness"** — content describing behaviour that has since changed (a constant that was retuned, a function that was renamed/deleted/generalised — e.g. `unmix_top2_against_palette` no longer exists as of this session; do any OLDER sections still reference it by name expecting it to exist?), a measured number that's since been superseded by a later, more accurate measurement, or a "still open" framing for something that's since been closed (exactly the class of bug `9762bfc` just fixed for §45 specifically — the content audit should check whether OTHER sections have the same kind of staleness that §45 briefly had).

**Suggested starting method, given the file's size (2,862 lines) makes a full read expensive:** grep for known stale markers first — every `⚠️` (correction/reversal marker, per the file's own convention), every "still open"/"not yet"/"NOT resolved" phrase, cross-check each against whether a LATER section or a `gif-deferred-list.md`/`git log` entry shows it was actually resolved since. Also grep for every function/constant name the CURRENT `scripts/remove_gif_background.py` no longer contains (a fast `rg` diff between names mentioned in `lessons.md` and names that `rg -n "^def |^[A-Z_]+ = "` finds in the live script would surface real staleness mechanically, not just plausibly).

**Use `sequential-thinking` for this, mandatorily, per the repo's own standing convention for audits** — it found two real, non-obvious defects in a MUCH smaller scope (one section) just this session; a whole-file audit without it risks missing exactly the same class of self-inflicted, plausible-looking-but-wrong content.

## 8. Ready-to-paste starting prompt for the next session

```
Continuing on fix/gate8-trial-findings in Gif-Background-Remover.
Read docs/handoffs/2026-08-24-defect-c-closure-review-fixes-and-lessons-audit.md
in full before doing anything else — it has the complete state, what was
validated and how, and full detail on the two tasks below.

Two tasks, in order:

1. SKILL.md's deferred structural pass (handoff section 7.1). Move whole
subsections (WebP method-tuning detail, byte-count tables) into
references/flag-reference.md, keeping only rule + one-clause why + pointer
in SKILL.md's body. Watch for threshold values or verbatim error-text
blocks that need to stay inline rather than move behind a pointer. Run
audit_docs.py and the soft-wrap checker after every move.

2. Audit references/lessons.md for repo-specific content that should live
in CLAUDE.md instead, unreachable or stale sections, and lessons describing
behaviour that has since changed (handoff section 7.2 has the full
definition and a suggested grep-based starting method). This is broader
than the structural ordering fix already done in commit 9762bfc — do not
just re-check that.

Use sequential-thinking for both, mandatorily, per this repo's standing
convention for audits.

Nothing gets pushed or merged without asking first, per the usual
convention. Branch commits are free.
```
