# Remaining work, ordered by measured impact per unit of effort

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** finish the eight open tracker items in the order that improves real output soonest, rather than in priority-tag order. Written 2026-08-20 after the post-trial plan was executed in full.

**How the order was derived — and it is NOT the priority tags.** Severity alone cannot rank a backlog; a catastrophic failure that fires on 0.7% of assets is worth less than a moderate one that fires on 40%. So every ordering claim below is backed by a frequency measured on real populations today, and two of them moved an item *down* from where the tracker's tag would put it.

## The frequency measurements everything below rests on

`--recommend` run over three populations (104 dark-background assets, 34 labelled white-background assets, the 8 trial assets), counting how often each risky flag is actually emitted:

| flag | dark_bg (104) | white labelled (34) | trial (8) |
|---|---|---|---|
| `--recover-fade-alpha` | **41%** | **24%** | 38% |
| `--erosion-exempt-*` | 55% | 56% | 62% |
| `--pixel-art` | 12% | 71% | 0% |
| `--tumble-safe` | 9% | 6% | 12% |

**Then the half that matters: firing is not failing.** All 25 flat-keyable dark assets where `--recover-fade-alpha` is recommended were rendered through the real `--auto` CLI and scored:

- **6 of 25 (24%) come out substantially wrong** — 5 with `bg_removed_worst` below 0.60 (`_ (7).gif` 0.0000, `_ (10).gif` 0.0004, `_ (18).gif` 0.0064, `_ (11).jpeg` 0.1367, `_ (16).gif` 0.1759) plus `_ (15).jpeg`, which fails to render at all (rc=1).
- That is **~6% of the whole dark population**, not the catastrophe the single asset first suggested.

⚠️ **My own automated verdict rule was too narrow and undercounted, which is worth recording.** It tested only for GHOSTING (`bg_removed` low *and* `bg_not_opaque` high) and reported 3 of 24. But `_ (18).gif` reads 0.0064 on **both** — near-total *opaque* background retention, a worse failure than ghosting — and `_ (16).gif` sits mixed at 0.1759 / 0.8720. A pass/fail rule shaped around the failure you already found will miss the one you have not. Count on the strict figure and inspect the exceptions.

---

## The order, and why

| # | item | tag | effort | fires on | fails | verdict |
|---|---|---|---|---|---|---|
| 1 | dark-background fade misfire | P1 | S | 41% of dark | **24% of those** | **do first** |
| 2 | mid-band "verified" wording (+ the `0% enclosed` string) | P2/P3 | S | every recommendation | n/a — no output change | **cheap multiplier** |
| 3 | changing background detection | P2 | M | 0.75% of corpus | 100% when it fires | silent and total |
| 4 | erosion on thin features | P2 | S | 55–62% | 1 of 13 measured | measure reach first |
| 5 | the escalation pass | P1 | L | unknown | 2 of 3 cases already pass | insurance, not a fix |
| 6 | the fade cliff | P1 | S | subset of #1 | — | needs a new idea |
| 7 | `CatPackFree` 0.250 | P3 | S | 4 assets | — | already decided: leave |

**Why #1 beats the two P1s below it.** It is the only item where the tool *actively steers an autonomous run into destroying the asset*, on a path it recommends unprompted, at a measured 24% failure rate, on a flag it emits for 41% of dark assets and 24% of white ones. Effort is S. Nothing else on the list has that ratio.

**Why the escalation pass (P1, L) drops to #5.** Its three motivating cases were re-tested today and **two already pass**: `for-you.gif` survives its 37-frame outline recolour, and `in-love.gif`'s fades are handled correctly. Only the changing-background case is a live failure, and that is item #3, which can be closed on its own. The escalation pass is real and worth building — but as *insurance for files longer than the corpus contains*, not as a fix for something currently broken. Building it now would spend an L on hypothetical exposure while a measured 24% failure sits at S.

**Why the fade cliff (P1, S) drops to #6.** Not because it is unimportant, but because it is not schedulable. The mechanism is known (a six-rung fade ladder, `references/lessons.md` §34.2), the obvious fix was built and measured at **0.688 → 0.477** and reverted, and what remains needs a different idea rather than another attempt. Scheduling a research task ahead of measured defects is how a backlog stalls.

---

### Task 1: Stop `--recommend` asking for fade recovery where it destroys the asset

**Files:** `scripts/remove_gif_background.py` — `detect_fading_colors`, and the `--recover-fade-alpha` branch of `recommend()`.

**The question to answer before changing anything: does `detect_fading_colors` have ANY specificity on a non-white background?** It has never been measured off white — the whole corpus was white-ish until 2026-08-20. Against black, "distance from the background" *is* brightness, so every lit pixel in the image is a candidate fade stage. That is a hypothesis with a mechanism, not a finding, and it must be measured before it drives a change.

- [ ] **Step 1: Write the failing test**

```python
def test_fade_recovery_is_not_recommended_where_it_ghosts():
    """Measured 2026-08-20: 6 of 25 flat-keyable dark assets where --recommend asks for
    --recover-fade-alpha come out with bg_removed_worst below 0.60."""
    import json, subprocess
    src = os.path.join(ROOT, 'local', 'corpus dark', '_ (7).gif')
    j = json.loads(subprocess.run([sys.executable, SCRIPT, src, '--recommend'],
                                  capture_output=True, text=True).stdout)
    assert '--recover-fade-alpha' not in j['suggested_command']
```

- [ ] **Step 2: Measure the detector's specificity on the dark population**

For each of the 105 dark assets: how many provisional palette colours does `detect_fading_colors` flag, as a share of the palette? Compare against the 34 white-background labelled assets. **hurricane flags 8 of 10 on a white background**, so a high share is not by itself a dark-background phenomenon — the comparison is the point.

⚠️ **Split the dark population by border flatness first** (the population definition in `scripts/harness/populations.py` carries the caveat and the number: only 13 of a 24-asset falsifier sample are ≥90% flat). A pooled figure over photographs will report this tool failing at content it does not claim to handle.

- [ ] **Step 3: Decide from the measurement, and write the decision into the code comment**

Three outcomes are all acceptable; an unmeasured compromise is not.
- The detector is no worse on dark backgrounds → the fault is elsewhere (the flood, the palette, the barrier prior); re-scope to whichever the 6 failures share.
- The detector is materially worse → gate the recommendation on background luminance/chroma, or on the flagged-share itself, and say so in the evidence string.
- The flagged share does not separate the 6 failures from the 19 successes at all → **say "unverified" and do not gate on it.** A check that cannot discriminate must report that, never a confident wrong answer (`references/lessons.md` §13, §16, §17).

- [ ] **Step 4: Verify against BOTH populations, not just the one that motivated it**

Re-render the 25 flat-keyable dark candidates AND the 8 white-background assets where the flag currently fires. **Acceptance: the 6 failures improve and none of the 19 dark successes or the 8 white ones regress.** A fix that trades one family for another is not a fix — that is the standing rule from §34.5 and it has already been enforced once today.

- [ ] **Step 5: `love.gif --auto` must remain `2fd526b6fb3b191c`; `python3 scripts/audit_docs.py` must exit 0 — read the EXIT CODE, never pipe it to `tail`.**

---

### Task 2: Say "unsure" where the numbers already say unsure

**Files:** `scripts/remove_gif_background.py` — the outline-verification and candidate-region evidence strings.

Two filed items, same shape, done together. `for-you.gif` produces `Region 1: outline c83c78 verified across 144 frames (68% enclosed)` — the number is honest, the sentence is not, and an autonomous run reads "verified". Separately, rocket and satellite emit `verified across 177 frames (0% enclosed)`, which reads as nonsense.

**This is the cheapest item on the list and it multiplies every other one**, because it is what makes a wrong recommendation *auditable* rather than confident. It changes no output pixel and needs no new analysis — every value involved is already computed.

- [ ] **Step 1:** Establish the distribution of `enclosure_ratio_all_frames` across the labelled populations before picking band edges. **Do not pick a threshold before seeing it** — that is how §34.3's wrong "1% of canvas" figure got published.
- [ ] **Step 2:** Three bands, three sentences: below the floor say it plainly failed; above the ceiling say verified; in between say it is a coin-flip **and name what to check**.
- [ ] **Step 3:** Fix the `0% enclosed` contradiction in the same pass — `anomalous_frame_count: 0` beside `enclosure_ratio_all_frames: 0.0` is two different fields reading as one claim.
- [ ] **Step 4:** Assert the exact strings in tests, on `for-you.gif` (mid band) and on `rocket.gif` (the contradiction). A wording change with no test is a wording change that regresses.

---

### Task 3: Detect a background that changes colour, and refuse

**Files:** `scripts/remove_gif_background.py` — `analyze()`.

`--bg-color` is one value and `detect_bg_color` reads frame 0, so an animation whose background cycles cannot be processed at all — and nothing reports it. Measured on `Pew Pew Pew.gif`: magenta → pink → red → orange → yellow → green across frames 11–15 of 30, with the frame-0 colour covering **0.0% of the canvas at frame 12**.

Only ~0.75% of the corpus, which is why it sits at #3 rather than #1 — but when it fires the output is *silently and totally* wrong, and detection alone captures most of the value. The six demonstrating assets are isolated in `local/corpus dark/_changing_bg/`.

- [ ] **Step 1:** Scan **every** frame's detected background colour. ⚠️ **A spread cannot see a transient** — the first attempt at this measurement sampled 10 frames of 30 and read 78.6% at frame 10 while frame 12 was 0.0%. Piggyback on the per-frame loop that already exists, the way the blank-frame scan added today does.
- [ ] **Step 2:** Report it in `analyze()`, steer in `--recommend`, and refuse in `process()` — the same three-place pattern the truncating-GIF fix used, for the same reason: prediction and prevention are different jobs.
- [ ] **Step 3:** Verify on all six `_changing_bg/` assets, **and on the 65 animated dark assets that must NOT trigger it.** A detector that fires on everything is not a detector.

---

### Task 4: Erosion on thin features — measure the reach before fixing

**Files:** `scripts/remove_gif_background.py` — `calibrate_edge_cleanup_erosion`.

`Team Valor` loses a flame wisp: `art_lost_over_perimeter` **1.977**, nearly two perimeter rings, against 0.70–0.97 across the white-background assets. The calibrator optimises the fringe metric and has **no term for thin-feature survival**; `check_erosion_damage` already detects components that lose most of their pixels and only WARNS.

- [ ] **Step 1: Measure how many assets are actually exposed, before changing a calibrator that is otherwise 5-for-5.** Erosion fires on 55–62% of every population, but the failure was 1 of 13 flat-keyable dark assets. Compute `art_lost_over_perimeter` across the labelled populations and count how many exceed 1.1. **If the answer is a handful, make `check_erosion_damage` refuse rather than warn; if it is broad, the calibrator needs a cost term.** The two are different changes and the measurement chooses.
- [ ] **Step 2:** Re-check against the white assets, where erosion 1 is measurably correct on 2 of 5 (§34.5). Do not trade one family for another.

---

### Task 5: The dense-nomination pass (its own session — do not start it at the tail of another)

**Files:** `scripts/remove_gif_background.py` — `analyze()`; `scripts/harness/*` for re-scoring.

The full design and its rationale are on the tracker item. In short: the failure is a **ratio** — a transient of length *L* in an *N*-frame file is invisible when `40/N < 1/L` — so a "this looks hard" trigger computed *from* the 40 samples cannot see the cases that need it. Make the cheap pass dense and let it nominate frames for the expensive one.

⚠️ **Scope warning, and it is why this is its own session:** changing `sample_idxs` feeds the hardness measures, forcing a full 797-asset re-score (~7 min) plus a standard render diff (~10 min at `--jobs 8`).

- [ ] **First slice (M): nomination (1) only** — background colour drift — which is Task 3 above. If Task 3 is done first, this task starts with its cheap pass already built and only the nomination plumbing left.
- [ ] ⚠️ **The dense pass must be MEASURED cheap, not assumed cheap** by analogy with the blank-frame scan, which reused a mask that already existed. A per-frame palette histogram is new work.
- [ ] ⚠️ **Each nomination must be shown to fire on the asset that motivated it.** A signal that cannot flag its own case is not a signal.

---

### Task 6: The fade cliff — research, not scheduling

Do not re-derive the fade ladder; it is measured in `references/lessons.md` §34.2 and on the tracker item, along with the fix that was built and rejected at **0.688 → 0.477**. Pick this up when there is a new idea, not on a schedule. Note that Task 1 may reduce its blast radius by preventing the flag from firing where it should not, which is another reason Task 1 comes first.

---

### Not scheduled

**`CatPackFree` 0.250** — already decided and recorded: leave the threshold alone. Raising the band ceiling to 0.25 buys 2 detections and costs independent specificity 0.9681 → 0.9645, and 3 assets is not a population to build a new measure against.

---

## Executed 2026-08-20 — outcome of each task

| # | item | outcome |
|---|---|---|
| 1 | dark-background fade misfire | **DONE** — the plan's hypothesis was FALSIFIED. `detect_fading_colors` does not over-flag on dark backgrounds; on the three worst assets it flagged nothing, and background luminance does not separate the recommendation (61% dark vs 55% white). The real fault was that `--recommend` gated on a cheap SCREEN the renderer never reads; they disagree on 16 of 34 assets and that half held every catastrophic output. `references/lessons.md` §35 |
| 2 | mid-band "verified" wording | **DONE** — distribution measured first: 168 of 269 regions at exactly 1.000, 6 at 0.000, 95 (35%) between. Three bands. §38 |
| 3 | changing-background detection | **DONE** — built in an isolated worktree and merged. §36. ⚠️ Its 71-asset control could not contain already-background-removed sources, and a render diff later caught it refusing 9 of 37 of them; fixed, 0 of 37 now. |
| 4 | erosion on thin features | **MEASURED, NOT FIXED.** Reach and attribution are now known (47 of 148 over 1.1; 36 of 46 attributable to erosion, 10 to the keyer), and TWO cost terms were built, measured and reverted — one failed on a population, one on arithmetic. §37 records both dead ends. Still open. |
| 5 | the escalation pass | not started — its own session, as specified |
| 6 | the fade cliff | not started — research, as specified |
| 7 | `CatPackFree` 0.250 | not scheduled, as specified |

**What the plan got right:** ordering by measured frequency put the highest-yield item first, and Task 1 did have the ratio claimed for it. **What it got wrong:** Task 1's stated hypothesis was the wrong mechanism, and Task 4's decision rule ("a handful → refuse; broad → a cost term") assumed `art_lost_over_perimeter` names a cause. It does not — attributing it was a step the plan did not contain and without which either branch would have been taken on a confounded number.

## Self-Review

**Ordering.** Every position is backed by a frequency measured today on a real population, and two items moved *down* from their tracker tags on that evidence: the escalation pass (two of its three motivating cases already pass) and the fade cliff (needs an idea, not a slot). The one item that moved *up* — the mid-band wording — did so because it costs almost nothing and makes every other item's failures auditable.

**What this plan does NOT claim.** The 24% failure rate in Task 1 is measured on flat-keyable **dark** assets only. The same flag fires on 24% of white-background assets and that population's failure rate was **not** measured — Task 1 Step 4 requires it as a regression control, but if it turns out to be high there too, this plan's ordering was right for the wrong reason and Task 1 grows in scope.

**Placeholders.** Tasks 1, 2 and 4 deliberately leave a number unfixed, because the number is the deliverable of a measurement step inside the task and the decision criterion is stated up front. A plan that pre-picked those thresholds would be inventing evidence.
