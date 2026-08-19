# File-size optimization — the detail

`SKILL.md` keeps the decision half of this topic: when to raise optimization at all, and the three named `--compress` tiers with their comparison table. This file holds the standalone levers and their measured case histories.

Read this when a tier alone is not the right answer — the user wants only a frame-rate cut, or only a resize, or a hard byte target — or when you need the evidence behind a tier's numbers.

### The standalone lever: frame-rate reduction (`--frame-stride`)
Works independently of any tier — for when the user wants ONLY the frame-drop treatment without cropping/resizing/gifsicle:
```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    --protect-outline-color <hex> --frame-stride 2
```
- Drops every Nth frame and **folds the dropped frames' durations into the kept frame**, so total playback length is exactly preserved (choppier, not faster). Always verify the folding actually happened (verification step 3) before trusting any tool's frame-drop output, including this script's.
- A real case: a 161-frame badge animation (mostly 20ms/frame, 3.6s total) dropped to 81 frames at stride 2 cut file size roughly in half (1868KB → 994KB) with imperceptible visual difference.
- Stops escalating once the average post-fold delay would exceed ~120ms/frame (~8fps) — beyond that, dropped frames read as genuinely choppy. If the source is already slow (100ms+/frame), mention this tradeoff explicitly.
- **`--frame-stride 1` explicitly forces keeping every frame even combined with a tier whose own default would drop frames** (e.g. `--compress medium --frame-stride 1`). The flag has a `None` default specifically so "unset" and "explicitly 1" are never conflated — if a future edit to the stride-resolution logic reintroduces a truthy check (`stride_override and stride_override > 1`) instead of `stride_override is not None`, that bug is back.
- **A common reason to want this combo:** `medium`/`heavy`'s colour reduction can look bad on fine vector linework (see the graininess note above) — if someone wants every frame kept AND the lightest possible palette handling, `optimize` (not `medium`/`heavy` + `--frame-stride 1`) is usually the cleaner single fix. ⚠️ Neither tier dithers any more: Floyd-Steinberg was removed 2026-08-19 after measuring it on 23 gradient assets and 5 flat vector sources — it cost 11–24% file size and 2.6–5x more frame-to-frame crawl to buy a ~6% banding improvement.

### The standalone lever: arbitrary resize target (`--resize-max-dim`)
The two named tiers only bake in 512px (`optimize`/`medium`) and 256px (`heavy`). For anything else (a platform wanting exactly 128px, say):
```
python scripts/remove_gif_background.py <input.gif> <output.gif> \
    --protect-outline-color <hex> --crop --resize-max-dim 128
```
- Fits the longer dimension to the given size, preserving aspect ratio, only ever downscaling.
- Always followed by the same 1px post-resize cleanup erosion the tiers use.
- Works standalone or combined with a tier (overrides that tier's own resize target rather than stacking).
- Doesn't crop on its own — pair with `--crop` if there's transparent margin to remove first.
- **On a thin/high-curvature design element, skipping resize (setting this high enough to avoid downscaling) can improve BOTH quality and file size at once** — confirmed on two structurally different real icons. See `references/lessons.md` §5 before assuming resize is always harmless.

### Automatic target-fitting (`--target-kb`)
Pass `--target-kb <n>` to cascade through: baseline → `optimize` → `medium` → `heavy` → escalating frame-stride (3→4→6, stopping short of ~120ms/frame) → escalating resize floor below `heavy`'s 256px (192→128→96px) as a last resort. Prints every attempt and the resulting size; leaves whatever it landed on saved even if the target couldn't be fully reached. Always re-check the result (preview or otherwise) after a `--target-kb` pass — degradation is cumulative, and the user should see the actual tradeoff, not just be told the size hit the number.
