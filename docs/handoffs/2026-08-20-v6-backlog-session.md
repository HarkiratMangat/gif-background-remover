# Handoff — the v6 backlog session, 2026-08-20

**Branch `feat/v6-backlog`, 45 commits ahead of `origin/main`, nothing pushed, merged or tagged.** `main` is still at v5.5.0 (`fc66879`); SKILL.md on this branch reads v6.0.0. Working tree clean, every gate green (evidence at the bottom).

**Next, set by Harkirat at the end of this session: items 4 and 6 TOGETHER, then 5. Item 7 stays deferred.** Read "Where to start" below before opening any code — the two items are closer than their tracker tags suggest, and one of them has a blind spot in its acceptance criteria that must be closed first.

---

## What this session executed

`docs/plans/2026-08-20-remaining-work-ordered-by-impact.md`, which is now **history, not a queue** — it carries an outcome table. Four of its seven items closed; two of its own assertions were falsified by carrying them out.

| # | item | outcome |
|---|---|---|
| 1 | dark-background fade misfire | ✅ closed — §35 |
| 2 | mid-band "verified" wording | ✅ closed — §38 |
| 3 | changing-background detection | ✅ closed — §36 |
| 4 | erosion on thin features | ⚠️ **measured, not fixed** — §37, two rejected fixes |
| 5 | the escalation pass | not started (its own session, per the plan) |
| 6 | the fade cliff | not started (research, per the plan) |
| 7 | `CatPackFree` 0.250 | deferred, standing decision |

### 1 — the fade misfire, and a falsified hypothesis

The plan asserted that `detect_fading_colors` over-flags on a dark background, because distance-from-background there *is* brightness. **Measured and false**: on the three worst assets it flagged **nothing at all**, and background luminance does not separate the recommendation (61% of flat-keyable dark assets whose screen fires, against 55% of white ones).

The real fault: `--recommend` gated `--recover-fade-alpha` on `band_interior_regions`' `gradient_fade` verdict — a **cheap screen the renderer never reads**. The renderer keys on `detect_fading_colors`. Across the 34 assets where the flag fired the two **disagree on 16**, and that half held every catastrophic output.

| | before | after |
|---|---|---|
| `_ (7).gif` `bg_removed_worst` | 0.0000 | 0.5043 |
| `_ (10).gif` | 0.0004 | 0.7241 |
| `_ (16).gif` | 0.1759 | 0.9176 |
| `_ (15).jpeg` | exit 1 | 0.9945 |
| 17 confirmed-fade assets | — | unchanged |
| 10 white controls | — | 9 unchanged, 1 improved |

Mechanism, for whoever touches this next: with no fading colour there is nothing to recover, but the flag is not neutral — fade recovery takes its own render path, **ignores every protection flag** (§34.4), and zeroes alpha only below 1/255 instead of at `--tolerance`. On a background carrying dither or JPEG noise that leaves every background pixel alive at alpha 1–9. Measured on `_ (7).gif`: **86.4% of true-background pixels at alpha 1–9, 13.6% at 10–39, none at 0.**

### 2 — "verified" printed over a number that said otherwise

The distribution was measured **before** any band edge was picked: 269 verified-outline regions across five populations, **168 (62.5%) at exactly 1.000**, 6 at exactly 0.000, **95 (35%) between** with no internal cluster. Three bands now, and the mid band names what to check. Changes no output pixel; changes whether a wrong recommendation is auditable.

### 3 — changing background

Built by a worktree subagent and merged. Detects, reports in `analyze()`, steers in `recommend()`, refuses in `process()`, with `--allow-changing-background` as the escape hatch.

⚠️ **Its 71-asset control could not contain the class that broke it** — see "The one that should change how you work" below.

### 4 — erosion: measured, two fixes rejected, still open

The reach is now known rather than guessed, and **the attribution is the part the plan did not contain**:

- **47 of 148** rendered assets exceed `art_lost_over_perimeter` 1.1 — 42% of `dark_bg`, 10% of `labelled`, 0% of `trial` and `corpus`.
- Re-rendering each of those with erosion off attributes **36 of 46 to erosion and 10 to the keyer**. The metric names a symptom, not a cause; without attributing it, either branch of the plan's decision rule would have been chosen on a confounded number.
- The control refuses a blunt reduction: of 41 assets already under 1.1, erosion 0 makes `edge_cleanliness` **worse on 9** (`for-you.gif` 1.000 → 0.688) and leaves background behind on 7.

**Rejected fix 1 — reuse `check_erosion_damage` as a gate.** Its 25px / 30%-survival bar was tuned for a WARNING and as a gate it fires on the dither speckle erosion exists to remove: `edge_cleanliness` **worse on 40 of 147**, better on 2. A warning's threshold is not a gate's threshold.

**Rejected fix 2 — a scale-free `lost / perimeter` overreach measure.** It separates 87 render pairs cleanly (FINE tops out at 1.00, DESTROYED reaches 2.98; a cut at 1.2 catches 16 of 36 with **zero** false positives) and is **arithmetically incapable of firing**: for one iteration the pixels erosion removes *are* the boundary ring, so the ratio is exactly **1.000 on every possible input**, verified on four constructed masks. The clean separation was a proxy for which erosion *level* an asset had used. A synthetic unit test caught what an 87-asset corpus had endorsed.

Both are written up in `references/lessons.md` §37 and on the tracker item.

---

## The one that should change how you work

**Three separate fixes this session each reached one of two consumers and looked complete.** In every case every intermediate-level number said the fix had landed; only diffing the **rendered output** found the second consumer.

1. **§35** — the recommender gated a destructive flag on a screen the renderer never reads.
2. **§37** — fixing `calibrate_edge_cleanup_erosion` left `--auto`'s post-render correction escalating straight back into the level calibration had just rejected, printing 40 damage warnings and keeping the file because the one number it reads had improved.
3. **§36** — gating the changing-background refusal in `analyze()` left `process()`'s deliberately-duplicated copy still refusing, so `--analyze` reported UNVERIFIED while the render refused. Worse than either answer alone.

**Before calling a fix complete: grep for every call site of the decision you changed, and re-run the render gate — not the unit-level score.**

And the companion lesson, which is the reason the erosion acceptance below has a caveat: **a validation corpus can only falsify what it contains.** The changing-background rule was validated on 71 OPAQUE animated assets and shipped refusing **9 of 37 already-background-removed ones** — a whole false-positive class its control could not express, caught only by a PRE/POST render diff. Two distinct causes, and fixing the first left the second:

- under `alpha == 0` the RGB is whatever the encoder left there, and for a GIF that is a palette entry that can differ frame to frame, so voting on a transparent corner reads noise as a background colour;
- a large piece of **artwork** touching three corners on frame 0 reads as a background and then animates away.

After both: **0 of 37 alphas fire, 6 of 6 positives still do, 0 of 105 dark negatives do.**

---

## Where to start on 4 and 6

**They are closer than their tags suggest, and there is a third item in the same family.** Read all three before opening code:

- item 4 — erosion has no term for what it destroys (`references/lessons.md` §37);
- item 6 — `--recover-fade-alpha` maps colour-distance to alpha as a **cliff**, and treats *pale* as *translucent* (§34.2);
- AUTONOMY BACKLOG item 5 — gift's sparkle: one colour that is **simultaneously solid artwork and a translucent element**.

All three are the tool failing to describe a translucent element correctly, in three different directions. The asset that sits between 4 and 6 is `local/corpus dark/_ (17).gif`, a neon streak with a soft glow on flat black: the fade path cannot see the glow (it is a multi-colour ramp, not one flat palette entry at partial alpha), and the normal path's erosion then cuts its outer falloff — `art_kept_worst` 1.000 → 0.761, `art_lost_over_perimeter` 2.972. **Whichever of 4 or 6 is worked first, that asset is the shared test case**, and it is filed as its own P2 on the tracker.

⚠️ **Before trusting any third erosion cost term, add the `alphas` population to its acceptance.** The 149-asset measurement behind item 4 covers `labelled`, `trial`, `corpus` and `dark_bg` only — precisely the blind spot that let the changing-background rule ship refusing 9 of 37 already-background-removed assets. A cost term validated on the same four populations inherits the same hole.

**The acceptance for item 4 is fixed and both halves are required:** the 36 erosion-caused assets improve, AND `edge_cleanliness` does not fall on the 41 controls. Do not re-derive the two rejected fixes.

**Do not re-derive item 6's fade ladder.** It was built, measured at **0.688 → 0.477**, and reverted (§34.2 and the tracker item).

---

## Harness changes you inherit

- **`scripts/harness/snapshot.py::freeze()`** — the script under test is now frozen by `run_populations.py` as well as `render_baseline.py`. Until this session only the latter did, so a 12-minute analyze pass silently forbade editing the file it was measuring. **The practical win is overlap: a long render or score pass no longer blocks editing.** Freezing is free — the snapshot is byte-identical, so it shares `analysis_cache`'s script-SHA namespace, asserted by a test rather than assumed. `candidates.py` is unaffected; it never invokes the script.
- **`render_baseline.py --compare` no longer crashes** on the first diff that spans a change adding a refusal (`100.0 * None` when an asset rendered on one side and was refused on the other — it printed "19 changed" and died before naming a single asset).
- **`test_score_outputs.rendered()` writes atomically.** Two `-n 6` workers on a cold cache could corrupt a shared entry; it surfaced as `UnidentifiedImageError`, which reads as a product regression and is not.
- **Suite is 68 tests** (was 32 at session start).

## Standing traps that bit again

- `rg -r` is `--replace`, not recursive. It silently rewrote grep output mid-session.
- `iter_assets` skips `ambiguous`/`unsuitable_no_edges` labels unless `include_excluded=True` — a first scan returned 44 assets instead of 149 and looked like a fast success.
- `audit_docs.py` rejects an `**Also searched as:**` tag the section's own prose already contains. Three sections needed retagging.

## Gates, run fresh at the end of this session

```
pytest (68 tests, -n 6)      all passed
audit_docs.py                exit 0
audit_docs.py --diff v5.5.0  exit 0
reflow-prose --check         0 would change (6 files)
love.gif --auto              2fd526b6fb3b191c (unchanged)
render diff PRE/POST         3 of 230 records changed, every one explained
```

The three render changes: `PandaBobba.png` native (alpha changed, same opaque count) and `[resize]` (43106 → 42824, 99.3%) — the §35 fade gate acting on an asset outside the population it was measured on, scoring `bg_removed_worst` 1.0 and `art_kept_worst` 1.0; and `Pixel Saber.gif`, which now refuses. That last is a **true positive** found outside the original control: full-canvas white flash on frames 58–60 and 153–155 of 213, and its previous render was the worst `art_lost_over_perimeter` in the entire 149-asset set at 68.263.
