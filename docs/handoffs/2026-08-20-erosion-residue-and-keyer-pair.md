# Handoff — the erosion residue (42 assets) and the keyer pair (2 assets)

**Branch `feat/v6-backlog`, 53 commits ahead of `origin/main`, nothing pushed, merged or tagged. Working tree clean, every gate green.**

Two items, both the residue of the erosion investigation that closed on 2026-08-20. Neither is a fresh problem — both are populations that have already been measured, and the measurement is archived. **Read this whole file before opening code: item 1's obvious next step has already been tried and it did not work.**

## Recommended setup

**`Sonnet5-High`.** Ready-to-paste session title:

```
Sonnet5-H · erosion residue + keyer pair · <session-start date>
```

Derived from dioreo's grid, not from a feeling. **Premise risk: MODERATE** — both populations are already attributed, and the open questions are "is this ring bite acceptable?" and "what removes this blob?", neither of which requires re-framing anything. **Deliberation load: MODERATE** — 43 assets total, with a procedure that already exists and archived data for all of them. Torn between `Sonnet5-High` and `Opus5-High`, so the grid's own anti-over-spec rule takes the lower cell. **Escalate to `Opus5-High` on an event**: if the `Cut loop.gif` mechanism is not obvious after one pass, or if the two keyer assets turn out to share a mechanism that needs a new discriminator.

---

## What already shipped, so you do not re-derive it

`EROSION_MAX_AUTO = 1` bounds both the calibrator's selectable set and `--auto`'s post-render escalation. Settled by 448 renders (112 assets × erosion 0/1/2/3): erosion is monotonically destructive on all 104 assets that scored at every level, going above 1 buys at most 0.021 of background removal, going 0 → 1 buys up to +0.622. PRE/POST on 186 assets: 37 move, 28 of the erosion-caused population better, 0 worse, controls worse on none of four measures. `references/lessons.md` §37.4.

⛔ **Do NOT reach for a third erosion cost term.** Two are recorded as dead ends in §37.1 and §37.2, and the search space is now bounded by measurement rather than by a rule.

---

## ITEM 1 — the 42 assets still over `art_lost_over_perimeter` 1.1

**Population:** assets whose damage is attributable to erosion (rescued at erosion 0) and which are still over 1.1 at the level that now ships. Keys: `local/erosion-residue-keys-2026-08-20.txt`. Per-asset measurements: `local/erosion-residue-2026-08-20.json`.

⚠️ **The published figure was 23 and that was WRONG — it is 42.** 23 is the count of erosion-caused assets whose ratio did not CHANGE between PRE and POST (their calibrated level was already 1). Two different quantities, one number. Corrected in the tracker and in §37.4.

⚠️ **The obvious next step has been tried and it did not work.** The tracker's own instruction was to re-read these 42 through `art_lost_faint_share`, the field that dissolved 14 of the 20 keyer-attributed assets. It was run on all 42, and it clears **1 of 42**. The other 41 sit in the middle:

| | faint share | solid share | largest solid component | lost-pixel median distance |
|---|---|---|---|---|
| keyer population (for contrast) | 98.7–100% *or* 0–28% | — | 0 *or* 2,072–164,804 | 33–71 *or* 145–420 |
| **these 41** | **22–93%** | 3–60% | **6–2,925 px** | 40–438 |

**Why they differ, and it is the finding:** erosion removes a RING at the silhouette, and a silhouette ring legitimately contains both antialiased and solid-coloured pixels — so a mixed faint share is what a correct 1px erosion looks like. The keyer population removes whole REGIONS, which is why it split categorically. `art_lost_faint_share` is the right discriminator for region loss and the wrong one for ring loss.

**So the open question is not "is this damage?" — it is "is a one-ring bite that carries 22–60% solid pixels a defect at all?"** That is a product judgement, and it may well be "no".

**The one asset that is NOT a ring, and where to start:** `labelled/Cut loop.gif` — ratio 2.880, **98.4% solid**, a **2,925 px** solid component, lost-pixel median distance **438**. Every other asset in the set is under 2,000 px and most are under 700. Diagnose that one by hand first; if it has its own mechanism, it is a separate finding and the other 41 are a threshold question.

**What would settle the ring question** (suggestion, not a plan — brainstorm it first): a measure of whether the lost pixels form a 1px-wide shell around the surviving artwork or a compact blob. The data to build it against is already archived, and both classes are present in the same file.

⚠️ **Two instrument corrections that apply to anything you measure here**, both found by running the acceptance rather than reading it:
- **`edge_cleanliness` cannot vary on a GIF render.** It counts alpha strictly between 12 and 243, and a 1-bit container has none — 0 of 104 assets vary across four erosion levels. Use `bg_removed_worst` and the render gate's opaque counts instead, or render to WebP where it can actually move.
- **`score_outputs` is not valid on the `alphas` population at all.** Its ground truth comes from the source's RGB, which under `alpha == 0` is encoder noise, so it reports `art_lost_over_perimeter` of 19, 29, 63 and 71 on assets rendering correctly. That population's gate is `render_baseline.py`'s alpha fingerprint.

---

## ITEM 2 — the two assets where the keyer removes solid artwork

**Population: exactly two.** All that survives of the 20-asset "keyer damage" set after attribution (§37.5): 20 → 14 metric artefact → 4 not flat-background content → **2 genuine**. Per-asset measurements: `local/keyer-attribution-2026-08-20.json`.

| asset | background | border flatness | largest solid component removed | solid share | lost-pixel median distance | `--auto` applies |
|---|---|---|---|---|---|---|
| `local/corpus dark/_ (25).gif` | `ff6666` | **1.000** | 2,072 px | 88.2% | 153 | `--protect-outline-color f064f0 --erosion-exempt-max-size 3` |
| `local/corpus dark/_ (10).gif` | `921219` | **0.945** | 4,164 px | 74.9% | 189 | `--tumble-safe --erosion-exempt-transient` |

Both are `appears_hard_edged: False`, both get real recommendations, and both survive erosion 0 — so this is neither a "no flags emitted" case nor an erosion case. The removed pixels are far from the background, so it is not the classic "artwork the same colour as the background" that the `--protect-*` family exists for either.

⚠️ **TWO assets is not enough population to build a measure against**, which is the same call this project already made about a 3-asset sprite pack. **Do:** diagnose each by hand — instrument which stage actually removes the blob (colour mask, band-only removal, a region verdict, or the transient-region exemption) — and only THEN ask whether the two share a mechanism. If they do not, record both as known limitations rather than inventing a rule from a sample of two.

---

## Tools you inherit

- **`scripts/harness/render_levels.py`** — renders assets through the real CLI at FORCED erosion levels and scores every output, so any policy mapping an asset to a measured level can be evaluated exactly with no further rendering. `--levels 0` isolates keyer damage from erosion damage. `--keys-file` takes either key list above. The script under test is frozen at startup, so a long run does not block editing.
- **`score_outputs.score()`** now reports `art_lost_faint_share` and `art_lost_solid_largest_component` beside the ratio, read at the frame the RATIO is worst. Falsifier pair in `test_score_outputs.py`: one synthetic source carrying both a faint ramp and a saturated blob, scored twice, differing only in which the output removes.
- Archived measurements in `local/`: `erosion-levels-2026-08-20.json` (the 448-render table), `erosion-residue-2026-08-20.json`, `keyer-attribution-2026-08-20.json`, plus both key lists.

## Gates, run fresh at the end of the session that produced this

```
pytest (80 tests)            exit 0
audit_docs.py                exit 0
reflow-prose --check         0 would change
love.gif --auto              2fd526b6fb3b191c (unchanged)
render gate --set standard   230 vs 230, 6 changed, all three moved assets in both passes
```

## Also still open, and not part of these two items

- **Item 5** — the 40-frame spread cannot see a transient, and the trigger for looking harder cannot be computed from the spread. P1, untouched, first slice sized M.
- **`CatPackFree` 0.250** — deferred, standing decision.
- **53 commits unpushed.** Push, PR, merge and tag are each asked separately, every time.
