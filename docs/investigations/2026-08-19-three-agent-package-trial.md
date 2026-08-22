# Three fresh sessions, five real GIFs: what a 797-asset corpus and an xhigh code review both missed

**Run 2026-08-19.** Three simulated fresh claude.ai sessions were each given the packaged v6.0.0 `.skill` — SKILL.md, `references/`, `scripts/`, nothing else — and the same five real animated icons, under three tiers of user request. Ninety minutes of agent time surfaced **five defects, three of them P1**, on a package that had just passed every gate this repo has.

## The thesis

**Three independent verification regimes all passed, and the product was broken anyway.** Each is blind in the same structural way.

| regime | what it measures | why it saw nothing |
|---|---|---|
| the 797-asset labelled corpus | **classification** — is this pixel art or antialiased? | every defect here lives *downstream* of classification. Recall 0.9644 / specificity 0.9681 was true and irrelevant. |
| the xhigh code review, ten finder angles | **code** | `Region 1: enclosure_ratio 0.825 looks incidental` is correct code producing wrong advice. There is no bug to find in it. |
| `render_baseline.py` PRE/POST | **regression** | every one of these defects is longstanding, so PRE and POST agree and the gate reports "0 changed". |

All three compare the product against **itself, or against a label** — never against what a user wanted. That is the gap, and it is where all five defects live.

> **A corpus tells you the classifier is right. Only a run tells you the product is.**

## The trial

Each agent got its own extracted copy of the package and its own copy of the five GIFs, was forbidden from reading this repo (no `CLAUDE.md`, no tracker, no `scripts/harness`, no memory), and was required to log every step, every re-run, every moment of confusion, and a final self-report.

| agent | request tier |
|---|---|
| **1** | vague — *"remove the white background from these gifs and preserve the colors inside of the design"* |
| **2** | detailed — stickers for a chat app; **stated in prose that interior light areas are artwork**; keep animated; reasonable size |
| **3** | expert — named every hazard per file: interior white inside the navy outline, hurricane's fade toward white, growth leaving the canvas, tumbling on rocket/satellite, thin arcs on galaxy |

**The assets** (640×640, 120–177 frames, flat vector, navy outline, white background): `galaxy` · `growth` (rocket leaves the canvas) · `hurricane` (badge fades toward white and rescales) · `rocket` (tumbles) · `satellite` (tumbles, fading signal arcs).

## Result: only the expert prompt produced correct output

Interior white kept, measured against per-frame ground truth derived from the source:

| | galaxy | growth | hurricane | rocket | satellite |
|---|---|---|---|---|---|
| **1 — vague** | 100% | **16.9%** | 100%\* | **54.2%** | 100% |
| **2 — detailed** | 100% | **16.7%** | 100%\* | **54.2%** | 100% |
| **3 — expert** | 100% | **100%** | 100%\* | **100%** | 100% |

\* **Those three hurricane scores are the SCORER being wrong, not the outputs being right.** Human review called hurricane a disaster on all three agents. See "Where the scorer failed".

**Agents 1 and 2 failed at near-identical percentages.** They did not make mistakes; they followed the same wrong recommendation to the same wrong place. Agent 3, given the identical tool and package, got everything right. The causal variable is isolated: **not agent skill, but whether the user hand-supplied the region knowledge `--recommend` got wrong.**

⚠️ **Agent 2 had been told, in plain language, that interior light areas were artwork.** It ran the tool, read the evidence, followed it, and reported *"every interior light/white element you flagged survived"* while deleting 83% of growth's rocket body. **Prose-level detail does not protect against a tool naming a specific region as background. Only region-level specificity does — and a user cannot supply that per-region, per-file. So it has to come from the tool.**

## The five defects

**1. `--recommend` calls a large interior design region "incidental background".** On growth: `Region 1: enclosure_ratio 0.825 looks incidental, leaving as background.` That region is the rocket's white body. Direct cause of 2 of 3 sessions destroying 2 of 5 assets. The threshold needs conditioning on region **area** — 82.5% enclosure over a region this size is not incidental by any reading.

**2. A fully-transparent frame truncates the GIF.** `growth.gif --auto` → `gifsicle: unknown block type 71`, **85 of 123 frames**, 1700ms of 2920ms. Pillow's GIF writer; confirmed by three independent synthetic controls (mine and two agents'). Not flag-dependent. The script warns loudly and writes the broken file anyway, and **nothing in `--analyze`/`--recommend` predicts it before the render** — an unattended run ships a file missing 31% of its animation.

**3. `--recover-fade-alpha` is a cliff, not a ramp.** Sampling hurricane's octagon fill:

| frame | source distance from white | output alpha |
|---|---|---|
| 0 | 347.8 | 255 |
| 12 | 258.7 | **255** |
| 20 | 197.8 | 140.5 |
| 32 | 105.1 | 70.5 |
| 40 | 44.3 | 24.2 |

The colour moves smoothly; alpha holds flat then drops 255 → 140 in eight frames. **All three agents produced byte-identical output here** (same SHA over every frame) — one product behaviour, zero prompt leverage.

⚠️ **The root error may not be tunable.** `--recover-fade-alpha` treats *pale* as *translucent*. Hurricane's badge is a solid pale shape the animator drew getting lighter, not a see-through one. Reconstructing alpha from paleness composites identically over white and wrongly over anything else. **For a fade drawn against the background colour, alpha recovery and colour fidelity are different goals.**

**4. `--auto` calibrates erosion by default while SKILL.md says `--auto-erosion` enables it.** Code: `auto_erosion = 'edge_cleanup_erosion' not in _typed`. Measured cost on growth's WebP: **2,878 art pixels** versus explicit `--edge-cleanup-erosion 0`, overriding the documented WebP default of 0 to do it.

**5. `--recover-fade-alpha` silently disables `--tumble-safe`** and every other protection flag — the render loop takes the `recovered_rgb` branch and skips `protected_masks`. On growth the two are needed together and cannot be combined.

Plus two smaller ones: WebP's erosion-0 default leaves visible outline artefacting (which **contradicts** defect 4 — they must be settled together), and `--recommend` prints `verified across 177 frames (0% enclosed)`.

## Format reasoning — and an unwritten rule

From the step logs:

- **Agent 1 hedged.** The user said *"these **gifs**"*; it read that as a format requirement, hit a conflict with the tool on two assets, and shipped both plus a `rejected/` folder.
- **Agent 2 served the destination.** *"Stickers in a chat app — format is a real decision"*; WebP for all five for set consistency, GIF fallbacks where faithful, plus a 256KB set.
- **Agent 3 measured and refused.** WebP for all five, GIF companions only for the two where GIF carries the art honestly, explicit refusal for the other three.

**Variant sprawl is inversely proportional to how much the user constrained the goal.** Agent 1 produced the most files because it knew the least.

⚠️ **"gifs" was a noun, not a format request** — the user meant "these animated images". Agent 1 spent renders resolving a constraint nobody imposed, because **SKILL.md has no delivery convention for "user said GIF, tool says WebP"**. All three agents hit that fork and invented three different, incompatible conventions. That is what an unwritten rule looks like.

**Cheapest fix on the list**, from agent 2's log: `--recommend`'s FORMAT boilerplate is ~150 words, identical per asset. Read five times in one job. It called this *"the single most wasteful thing I read all session"*.

## Where the scorer failed — three separate causes

The automated grader gave hurricane **100% on all three agents**. Human review: *"a disaster across all 3."* Both are consistent, because the grader is wrong three ways:

1. **Wrong ground truth for fades.** It classifies "white not connected to the border" as *must stay opaque*. For a fading element that is backwards — it should become progressively **translucent**. A binary keep/remove truth cannot grade a ramp, so it scored the fade bug as perfect.
2. **No edge-quality measure at all.** Blind to outline artefacting, which the human noticed first on three of five assets.
3. **Mean instead of worst frame.** Growth's agent-3 output holds an opaque background wedge on **16 consecutive frames**; averaged over 12 samples it reads as 99.9% and disappears.

⚠️ **A fix to defect 3 would be certified as working by this grader.** Fix the grader first: worst-frame reporting, an edge-cleanliness measure, and a fade-aware truth comparing the alpha ramp against the source's colour ramp.

## Session context — what this trial followed

The trial is only meaningful against what preceded it in the same session. Before it: **fourteen tracker items closed**, every gate green, v6.0.0 built, packaged and verified.

- **Group A** — the 2px band kept with its benefit measured for the first time (693 px across 20 assets, zero art cost); `_src_bg_transparent` decided over sampled frames with a constructed falsifier when the corpus moved zero verdicts; `--translucent-region`'s six untested cases plus a silent-no-op warning; APNG proven animated by Blink's own decoder with a passing control; **Floyd-Steinberg removed from both compress tiers** on four measured axes; the leak gate moved to the border-touching union.
- **Group B** — the partial-alpha promotion: **218 of 249** sources carrying a fade lost it, fixed with a minimum-not-assignment (now 207 of 249 keep 90%+), and the erosion calibrator's 6,844-pixel fallout caught by the render gate.
- **Labels** — 62 disagreements inspected by eye; 9 real mislabels, 7 marked ambiguous; `small_aa` specificity **0.887 → 0.970**; the Blox-Fruits family finding that killed the "0.615 collapse" reading.
- **The 16-colour floor** — measured against real negatives for the first time and **deliberately not moved**: the entire apparent win was inside a derived population.
- **A seventh discriminator** — +7 points of independent recall; one sprite pack **0.235 → 0.941**.
- **`--remove-region-track`** — 24/24 against a static region's 1/24.

**The tracker went 14 open → 1 → 8. That is not backsliding.** The eight are better items than the fourteen were, because they came from *use* rather than from *audit*.

## What this changes

1. **A three-tier agent trial on real assets is a release gate this repo did not have**, and it is now the highest-yield one per unit time. It belongs before a release, not after.
2. **Recommendation accuracy outranks documentation.** Agent 1 read **4% of lessons.md** and ruined two assets; agent 3 read barely more and got everything right. A planned lessons-retrieval optimisation would have saved **zero** of these five assets.
3. **⚠️ The tension this write-up does not resolve, and should not pretend to.** Conclusion 2 says recommendation accuracy outranks documentation — and then the remedy shipped for three of these defects is `references/lessons.md` §34, which is documentation, whose advice depends on a session reading it and then overriding the tool by eye. **The trial is direct evidence that this does not happen**: agent 2 was told in prose and still followed the tool. So §34 is a stopgap that buys time for the product fixes; it is not the fix, and treating it as one would repeat the error this document is about. A reader-test of this very document caught the contradiction, which is the argument for reader-testing the ones that ship.

4. **Grade against the artefact.** Every failure in this write-up — the roleplay that predicted less than one run, the mean that hid a 16-frame defect, the region count that missed the outline — is the same error: trusting a derived signal over the thing itself.

## Caveats, stated rather than buried

- **n = 1 per tier.** The growth/rocket determinism is solid (near-identical percentages across two agents); *"tier-2 prompts fail"* is one data point.
- **All five assets are one family** — flat vector, navy outline, white background, 640×640. Nothing here tests pixel art, coloured backgrounds, or small icons.
- **The agents ran on Claude Code tooling, not the real claude.ai sandbox.** The GIF corruption is Pillow-12.3.0-specific; the live sandbox may differ, and that should be checked before treating the version as the cause.
- **Isolation is self-reported.** The access-time check intended to prove which files each agent really opened returned nothing — this filesystem does not update atimes. Their logs are consistent with the rule, but it is not proven.

## Artefacts

- Outputs and per-agent `STEPLOG.md`: `local/Corpus Trial Gifs/agent-{1-vague,2-detailed,3-expert}/`
- Tracker items: the seven filed 2026-08-19 in `gif-deferred-list.md`
- Product-side mechanisms, for a live session: `references/lessons.md` §34
