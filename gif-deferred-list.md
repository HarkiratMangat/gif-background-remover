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

**None open right now.**

---

## Resolved (kept for the record, not to re-litigate)

- ~~Phase 1: move SKILL.md's manual checks into `--analyze`/`--recommend`/`--verify`~~ → **SHIPPED
  2026-08-07** on `feat/analyze-recommend-verify` (13 commits over `main`, not yet pushed/merged —
  Harkirat's call). 5 new `--analyze` checks, `--recommend`, `--verify`, all reviewed (including a
  full whole-branch review) and fixed. Three real design bugs found via testing against real
  fixtures rather than written to spec and trusted — see the plan doc and SDD ledger for specifics.
  Phase 2 (prose compression) is the two items above's sibling next step, handed off separately at
  `local/HANDOFF-phase2-prose-compression.md` since it's planned work, not a flagged finding.
