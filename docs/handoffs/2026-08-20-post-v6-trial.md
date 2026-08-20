# Handoff — after v6.0.0 and the three-agent trial

**Branch:** `feat/v6-backlog`. **State:** v6.0.0 built, packaged, gated, committed — and then a real-world trial found seven more defects, so it is a good checkpoint rather than a finished release.

## Start here, in this order

1. `docs/investigations/2026-08-19-three-agent-package-trial.md` — **read this first.** It is why the plan exists and why the priorities are what they are.
2. `docs/plans/2026-08-20-post-trial-defects.md` — the executable plan. **Task 1 is the scorer and it is not optional**: the current grader reports the worst asset 100% correct, so any fade fix validated against it gets a false green light.
3. `gif-deferred-list.md` — 8 open. Count by enumeration, never from memory.

## What happened this session

**Fourteen tracker items closed, v6.0.0 built and gated.** The 2px band kept with its benefit measured for the first time; `_src_bg_transparent` decided over sampled frames with a constructed falsifier; `--translucent-region`'s six untested cases plus a silent-no-op warning; APNG proven animated by Blink's own decoder against a passing control; **Floyd-Steinberg removed from both compress tiers** on four measured axes; the leak gate moved to the border-touching union; **the partial-alpha promotion fixed** (218 of 249 sources were losing their fade; now 207 of 249 keep 90%+); composite keying with a measured distribution showing 0.0% of removed pixels above half opacity; **62 label disagreements inspected by eye** taking `small_aa` specificity 0.887 → 0.970; **the 16-colour floor measured and deliberately NOT moved**; **a seventh discriminator** worth +7 points of independent recall, taking one sprite pack 0.235 → 0.941; **`--remove-region-track`** at 24/24 against a static region's 1/24; and `--jobs` defaulted across the harness, each default proven equal to serial first.

**Then three fresh sessions were handed the built package and five real GIFs, and found seven defects in ninety minutes.** Three severe. The tracker went 14 open → 1 → 8, and the eight are better items than the fourteen were, because they came from use rather than from audit.

## The one thing to understand before touching anything

**Two of three trial sessions destroyed the same two assets by correctly following `--recommend`**, which called a rocket's white body `enclosure_ratio 0.825 looks incidental, leaving as background`. Both reported success afterwards, because every check they ran measured the removal they had been told to perform. The session that got it right had been handed a per-region list by the user.

**Prose-level detail does not protect against a tool naming a specific region as background.** Agent 2 was told in plain language that interior light areas were artwork, and still shipped the broken file. So the fix has to be in the product, not the documentation — which is why the plan starts where it does.

## Standing traps for the next session

- **Read gate exit codes.** Never pipe a gate to `tail`; that shipped a red gate once already.
- **Report the WORST frame, never a mean.** A defect on 16 consecutive frames averaged to 99.9% and vanished.
- **Before using any scorer to validate a fix, check it can FAIL on the defect that fix targets.**
- **`--jobs` now defaults to `min(8, cpu_count)`** in `render_baseline.py`, `run_populations.py` and `candidates.py`. Full corpus ≈ 7 min; the standard render set ≈ 10 min.
- **`love.gif --auto` must stay `2fd526b6fb3b191c`.** It is the byte-level control for "nothing else moved".
- **Seven pixel-art discriminators are dead.** Do not re-derive them — `references/lessons.md` §29.2, §29.12, and `candidates.py`'s banner.
- **A derived population cannot falsify a change to the thing it was derived from.** That check is what stopped the 16-colour floor from being moved on an artefact.

## Release status

**GitHub Releases still shows v5.4.0 deliberately.** v5.5.0 is merged and tagged but unpublished; **v6.0.0 is built and committed but the trial found defects after the build**, so publishing it now would ship known-broken fade handling and a GIF path that can truncate. Decide explicitly: publish v6.0.0 as-is with the defects documented, or hold the release until the plan's Task 2 and Task 3 land.

## The one long-standing gap that just closed

`local/corpus dark/` arrived 2026-08-20 and closes the narrow-constants item (autonomy backlog #13), which had been blocked on a corpus since 2026-08-17. **119 files, all opaque-background, 107 keyable, 59 dark and 63 saturated** — against a previous corpus that held **5 dark assets total**, all from one population.

**Register it as `ambiguous`, like `gradient_beds`** — its job is the ring metric and the fringe constants on a non-white background, not classification. Do NOT blanket-label 119 assets; §32 is the record of why. The 12 non-keyable full-bleed illustrations are already moved to `_excluded/`, so the folder holds exactly the 107 that score. Task 8 of the plan has the entry, the exclusions and the acceptance criterion — including that **"the constants are fine on dark backgrounds too" is a valid outcome**, not a failure to find something.

## Artefacts

- Trial outputs and per-agent step logs: `local/Corpus Trial Gifs/agent-{1-vague,2-detailed,3-expert}/`
- The built package: `local/gif-background-remover-v6.0.0.skill` (previous versions in `local/skills-archive/`)
- Latest corpus score: `local/pixelart-probe/analyze-2026-08-19-v34.json`
