# The v6.0.0 "session timed out" trial — what actually happened

**Date:** 2026-08-22
**Trigger:** Two claude.ai sessions (Sonnet 5, medium effort) were given one prompt — remove the white background from `secure.gif` and `megaphone.gif`, protect named interiors, deliver cropped WebP/AVIF under 256 KB at ≥128px wide, no GIF — and **both timed out** without delivering.
**Method:** One Sonnet-5 subagent, given only the shipped skill and the identical prompt, with every script invocation wrapped in `time` and logged.
**Artifacts:** `local/2026-08-21-v6-timeout-trial/` — `logs/timeline.md`, `logs/findings.md`, nine numbered command logs, the rejected deliverable kept as evidence.

---

## 1. Executive summary

The skill is not broken. Every artwork decision it made was correct and independently verified at the pixel level. What killed the two sessions is that **one `--target-kb` render on a 144-frame asset costs three and a half minutes of wall clock**, and the natural way to invoke it — the single batched call the skill's own documentation recommends — exceeds a two-minute tool timeout before producing anything.

Three genuine defects surfaced underneath that, and the second is the most serious because it ships bad artwork rather than merely wasting time:

1. **`--target-kb` has no concept of a minimum dimension.** It delivered a 120px-wide file against an explicit 128px floor, silently.
2. **AVIF strictly dominated WebP on both assets**, and the tool ranks neither — it hands the user a quarter-resolution file next to a full-resolution one and says nothing.
3. **`--recommend` proposed protecting regions the user had explicitly asked to remove**, because "is this interior intentional design?" is an intent question, not a pixel question.

One plausible hypothesis was tested and **falsified**, which is worth recording because it would otherwise have driven the wrong fix.

---

## 2. The assets, and why one of them is the whole story

| asset | canvas | frames | source size |
|---|---|---|---|
| `secure.gif` | 640×640 | 50 | 847,901 B |
| `megaphone.gif` | 640×640 | 144 | 2,032,995 B |

`megaphone.gif` carries 2.88× the frames of `secure.gif` at identical canvas size. Every measurement below separates cleanly along that line: `secure.gif` completed inside the call that was killed; `megaphone.gif` is what blew the budget. The frame count, not the canvas, is the cost driver — because the expensive unit in a `--target-kb` fit is one complete re-encode of every frame, repeated once per rung.

**Verification note:** the skill bundle under test was confirmed byte-identical to v6.0.0 on `main` across all six packaged files (`SKILL.md`, `scripts/remove_gif_background.py`, and the four `references/*.md`) before the trial began. The only difference from the two real sessions is the sandbox — this M1 Pro rather than a claude.ai Linux container.

---

## 3. The reproduction

### 3.1 What was killed

The subagent followed the skill's own "one invocation per JOB, not per FILE" guidance (SKILL.md:199-209) and issued a single `--batch` call covering both files × both formats under `--crop --target-kb 256`. It was **killed at 120s with SIGTERM (exit 143)**.

That is the reproduction. A session that follows the documentation lands on exactly this call.

### 3.2 The true cost

Re-scoped to `megaphone.gif` alone, the same work completed:

```
443.05s user  29.27s system  227% cpu  3:27.84 total
```

**207.84s wall clock, 443s of CPU.** Two Python processes were observed live at 209% and 167% CPU with 219 MB and 732 MB RSS.

### 3.3 Where the time goes

`--target-kb` on WebP/AVIF is a **120-rung concurrent grid** (`build_target_rungs`, `scripts/remove_gif_background.py:5915`). The rung space is the cross product of four strides `(1,2,3,4)`, five scales `(1.0, 0.75, 0.5, 0.375, 0.25)`, and a per-format quality ladder — six rungs each. Each rung is a real re-encode of up to 144 frames.

Full-resolution WebP starts at 1617.8 KB lossless and **3675.5 KB at q95** on this asset — roughly 7–14× over the 256 KB cap. The search therefore cannot short-circuit anywhere near the top of the ladder; it walked **~118 of the 120 rungs** before landing.

Mid-run the output directory held 18 simultaneous `rungN.tmp` files sized 1.6 MB – 5.2 MB each. The worker count is memory-aware and self-reported:

```
searching 120 rungs with 6 worker(s): 6 performance cores, 2769 MB free+reclaimable; ~340 MB per encode allows 8
```

On this machine the core count bound the answer at 6. A claude.ai container with fewer cores and less free memory would be bound lower — and since the work is a fixed ~118 full-frame encodes, halving the workers roughly doubles the wall clock. **A three-and-a-half-minute local run is plausibly ten to eighteen minutes there.** That is the mechanism by which both sessions died.

### 3.4 Nothing warns first

Neither `--analyze` nor `--recommend` emits a rung count, an estimated encode count, or a time estimate before a `--target-kb` fit is attempted. A session commits to the call blind, and the first thing it learns is that its tool call died.

---

## 4. Defect 1 — `--target-kb` silently violated a stated minimum dimension

The prompt said **"at least 128px wide x relative height."** The autonomous fit delivered:

```
megaphone_transparent.webp   120x128   36/144 frames   242.3 KB
```

Under the byte cap. Eight pixels short of the stated floor. **No warning of any kind.** It was caught only by measuring the delivered file with PIL after the fact.

### 4.1 Why the autonomous path cannot comply

The scale ladder is a fixed tuple (`scripts/remove_gif_background.py:5997`):

```python
_scales = (1.0,) if _pinned else (1.0, 0.75, 0.5, 0.375, 0.25)
```

Against the cropped 482×513 canvas that yields these candidate widths:

| scale | width | smallest rung tried | fits 256 KB? | meets 128px? |
|---|---|---|---|---|
| 0.375 | 181px | 314.2 KB | no | yes |
| 0.25 | 120px | 242.3 KB | yes | **no** |

**There is no rung between them.** The compliant zone — a width in [128, 181) that also fits the cap — is unreachable by construction. This is not a tuning miss; the search space does not contain a valid answer.

### 4.2 A compliant answer does exist

A hand-picked override found one immediately:

```
--resize-max-dim 136 --webp-quality 45 --webp-lossy --frame-stride 4
→ 128x136, 207.8 KB, 36/144 frames
```

Both constraints satisfied, with 48 KB of headroom to spare. The autonomous path could not find this because 136 is not on its ladder and q45 is not on its WebP quality list.

### 4.3 Why this is the severe one

A timeout is loud. This is silent. An autonomous run that completes and reports success has, in this case, quietly violated an explicit numeric requirement the user stated in plain language — and the only way to notice is to independently measure the artifact. This is precisely the failure class the project's own release gate 8 exists to catch, and the class that corpus scoring, code review and render diffing all structurally cannot see, because none of them knows what the user asked for.

---

## 5. Defect 2 — AVIF strictly dominates WebP, and nothing says so

| asset | format | dimensions | frames | size |
|---|---|---|---|---|
| megaphone | **avif** | 482×513 | **144/144** | **225.1 KB** |
| megaphone | webp (auto) | 120×128 | 36/144 | 242.3 KB |
| secure | **avif** | 524×531 | **50/50** | **185.8 KB** |
| secure | webp | 524×531 | 17/50 | 240.2 KB |

On both assets the AVIF is better on **every axis simultaneously** — resolution, frame rate, and file size. There is no tradeoff being made; the WebP is simply worse.

The AVIF fits reveal why. On megaphone it needed **six rungs**:

```
stride=1 scale=1 q95: 1274.4 KB
stride=1 scale=1 q85:  759.7 KB
stride=1 scale=1 q75:  532.5 KB
stride=1 scale=1 q65:  400.1 KB
stride=1 scale=1 q55:  308.1 KB
stride=1 scale=1 q45:  225.1 KB   ← hit target, zero resolution or frame loss
```

WebP needed ~118 and still ended up at a sixteenth of the area with a quarter of the frames.

The tool produces both files, prints `2/2 succeeded.`, and offers **no ranking, no comparison, and no recommendation**. An autonomous run therefore hands the user a wrecked deliverable alongside a good one with equal billing. A user who picks the WebP — perhaps for compatibility, perhaps because it is listed first — gets a materially damaged asset with nothing having flagged it.

### 5.1 The tool knew, and said so, and proceeded anyway

During the megaphone WebP fit the script printed:

> downscaling made this file LARGER than full resolution -- flat vector art stops being flat under interpolation. Frame-stride is the lever that pays on this content (references/lessons.md SS42).

It then delivered a **scale=0.25** result. The diagnostic is correct and the outcome contradicts it. The note is emitted as commentary rather than fed back into the search.

---

## 6. Falsified hypothesis — the WebP q60 floor is *not* the cause

The per-format quality ladders are asymmetric (`build_target_rungs`, `scripts/remove_gif_background.py:5926-5938`):

```python
if fmt == 'avif':
    ladder = [(q, False) for q in (95, 85, 75, 65, 55, 45)]
...
else:  # webp
    ladder = [(100, True)] + [(q, False) for q in (95, 90, 80, 70, 60)]
```

WebP floors at **q60**; AVIF runs down to **q45**. Since AVIF hit the cap at exactly q45, the obvious hypothesis was that WebP's early floor forced a cascade it should never have needed — and that extending the ladder would recover full resolution.

**Tested directly.** Full resolution, all 144 frames, `--crop` only, no target-kb / resize / stride:

| rung | size | vs. 256 KB cap |
|---|---|---|
| WebP q45, full res, 144 frames | **1730.1 KB** | 6.8× over |
| WebP q55, full res, 144 frames | **1848.0 KB** | 7.2× over |

**The hypothesis is dead.** Quality alone — even below anything the ladder tries — comes nowhere close. The resolution and frame cascade was *genuinely necessary* for WebP on this asset. Extending the ladder would have bought nothing but more rungs and more time.

(Incidentally: q45 producing a *smaller* file than q55 is a live example of the non-monotonicity the code comments already warn about, and the reason the search walks a real grid rather than bisecting.)

### 6.1 What the falsification actually revealed

AVIF q45 at full resolution is **225 KB**. WebP q45 at full resolution is **1730 KB**. That is a **7.7× gap on byte-identical input at nominally the same quality setting.**

WebP is simply the wrong container for a 144-frame alpha animation of this kind. That reframes Defect 2 from "a nice-to-have ranking line" into the substantive finding: the destruction was not a bug in the search, it was the *correct* answer to an impossible request, and the real error is that the tool accepted the request without ever saying the format could not serve it.

**Method note.** This is why the experiment was worth its 32 seconds. The q60-floor theory was coherent, code-supported, and would have produced a confident, plausible, wrong fix — extending a ladder that was never the constraint.

---

## 7. Defect 3 — `--recommend` cannot infer intent

For `megaphone.gif`, `--recommend` proposed:

```
--protect-outline-color f0c850,002864
```

`f0c850` is the sparkle yellow. The prompt had explicitly said to **remove** the white inside the sparkles, "since that's part of the background." The recommender proposed protecting it.

The geometric evidence was genuinely weak in both directions — across 144 frames the two sparkle regions recorded `frames_enclosed` of **2** and **0**, against the microphone's **102** (70.8%). But weak evidence is not the point: no amount of pixel evidence can distinguish "a white interior the artist intended" from "a white interior the user considers background." That is a statement about intent, and it lives outside the image.

The same ambiguity reappears from the verification side. After the override, `--verify` emitted:

> WARNING: region 1 was identified as intentional design but came out 0.0% opaque -- it received NO protection, not weak protection.

That warning is **correct about the pixels and wrong about the goal.** The region was removed deliberately, at the user's explicit request. An autonomous run reading that warning would be pushed to "fix" a correct output.

---

## 8. The artwork itself: verified clean

### 8.1 A trap in the verification path

`--verify` skips all pixel checks when the output dimensions differ from the source. Every delivered file is `--crop`ped, so **all four initial `--verify` runs were vacuous** — they ran in 0.9–2.0s and checked nothing. The trial re-rendered both assets **uncropped** specifically so the real per-frame geometric-mask checks would execute (13.9s and 39.0s respectively — two orders of magnitude more work, which is itself the tell).

Anyone verifying a cropped deliverable with `--verify` and reading a clean result is reading a pass that was never computed.

### 8.2 Results

**`secure.gif`** — gear's white circle and shield interior, both protected via outline `002864`:

```
region 1: mean_opacity_fraction 1.0
region 2: mean_opacity_fraction 1.0
leftover_background_opaque_px: clean, looks_fringed: false
```

A fraction cannot exceed 1.0, so a mean of exactly 1.0 across 50 frames proves **every individual frame, including the worst, is also 1.0.** This is the rare case where a mean is a valid worst-case statement, and only because the metric is bounded above at the target value.

**`megaphone.gif`** — microphone interior protected, sparkle interiors removed:

```
microphone (region 2): mean_opacity_fraction 1.0   across all 144 frames
sparkles  (region 1):  mean_opacity_fraction 0.0
sparkles  (region 3):  mean_opacity_fraction 0.002
```

The microphone held at full opacity across all 144 frames **despite only 70.8% single-frame outline enclosure** — the documented per-frame occlusion-substitution behaviour working exactly as claimed, through the tilt and skew. The sparkles came out transparent as requested.

Both intent requirements from the original prompt were met.

### 8.3 A verification trap the trial walked into and out of

The subagent's first verification attempt used a naive bounding-box mean-alpha script and produced ambiguous values in the 0.27–0.64 range that looked like partial, unreliable protection. A bounding box around a non-rectangular region includes background pixels, which dilute the signal toward the middle.

This is the exact bbox-versus-real-interior-mask trap `SKILL.md`'s Verification section warns about. The agent recognised it, **discarded its own numbers**, and re-ran through `--verify`'s mask-based `protected_region_coverage`, which was unambiguous. Recording it because it happened here under real conditions, not as a citation — the wrong instrument produced a plausible, actionable, entirely false reading.

---

## 9. Full timing table

| # | step | real | exit |
|---|---|---|---|
| 01 | `--recommend`, both files, one invocation | 45.35s | 0 |
| 02 | `--batch` 2 files × 2 formats, `--crop --target-kb 256` | **killed at 120s** | 143 |
| 03 | `--batch` megaphone only (webp+avif) | **207.84s** | 0 |
| 04 | manual 128px-floor test (1 rung) | 13.09s | 0 |
| 05/06 | `--verify` on cropped deliverables ×4 | 0.89–1.97s | 0 |
| 07 | uncropped re-renders for real verification | 9.36s / 23.80s | 0 |
| 08 | `--verify` against uncropped renders | 13.94s / **39.02s** | 0 |
| 09 | full-res all-frames WebP @ q45 / q55 | 15.76s / 15.98s | 0 |

**~44 tool calls total.** The cost was never call count — it was one command's duration. Step 03 alone is longer than every other step in the trial combined.

---

## 10. What would have kept the two real sessions alive

- **Split the batch** by file, and by format, whenever `--target-kb` meets an asset above roughly 100 frames. The skill's "one invocation per JOB" guidance is correct for tool-call overhead and actively harmful here; the two pieces of advice collide and nothing mediates them.
- **Surface a cost estimate** — rung count and estimated encodes — before committing to a `--target-kb` render, so a session can choose to split before it dies rather than after.
- **Pick the flags manually instead of running the search**, when the constraints are already known. This is what the claude.ai session eventually did for AVIF, and it is the correct pattern there.

⚠️ **A backgrounding workaround does NOT work on claude.ai, and this trial nearly recommended it.** It worked here, on macOS, which is why the earlier draft of this section proposed it. The claude.ai session tried exactly that — `nohup ... &` — and the follow-up tool call found **an empty log and no running process**; `ps aux` showed nothing. Each `bash_tool` invocation appears to run in its own process group that is torn down when the call returns, independent of `nohup`'s usual SIGHUP survival. **Long-running jobs spanning separate tool calls are not reliable in that sandbox.** This is a durable environment finding, and it is a direct example of why a fix validated on the development machine is not validated for the deployment target.

---

## 11. Trial process notes

**A harness slip, not a skill defect.** One attempt to background the megaphone render used a trailing shell `&` *in addition to* the tool's own backgrounding flag. The wrapper returned almost immediately, looking like success; the orphaned child took SIGHUP and died after writing two log lines and a zero-byte output stub. It was caught by checking `ps` and file sizes rather than by trusting the completion message, then discarded and re-run correctly. Worth recording because the false signal was a *success* signal.

**Instruction-provenance handling.** The subagent received mid-task guidance through the system-reminder channel framed as coming from a coordinator. It correctly noted that only genuine user messages carry authorization, judged the messages benign and record-only, carried out the underlying steps, and **verified every number independently against its own logs rather than trusting the asserted values.** That discipline paid off directly: the quality-floor experiment those messages proposed **contradicted the hypothesis behind them** (§6). Had it copied the coordinator's numbers instead of measuring, the falsification would never have surfaced.

---

## 12. Cross-check against the real claude.ai session

Harkirat completed a claude.ai run after this trial and supplied its outputs and a 45 KB self-audit (`local/2026-08-21-v6-timeout-trial/claude ai session/`). It confirms three findings independently, in the actual deployment sandbox, and adds one this trial missed.

### 12.1 The skill is deterministic across sandboxes

`secure_transparent.webp` from the claude.ai container is **byte-identical** to the one produced here — same 245,968 bytes, same MD5. Different OS, different CPU, different Python build, identical output. Whatever is wrong is wrong everywhere, and nothing here is environment-specific flakiness.

### 12.2 Defect 1 reproduced exactly, in production

| | this trial | claude.ai |
|---|---|---|
| `megaphone_transparent.webp` | 120×128, 36/144, 242.3 KB | 120×128, 36/144, 242.3 KB |
| winning rung | stride=4 scale=0.25 q80 | stride=4 scale=0.25 q80 |

The same asset, the same cap, the same 128px floor, the same silent violation. The claude.ai session's own audit reaches the identical conclusion — the grid "literally cannot reach a rung that satisfies both the byte cap and the width floor for this asset."

It also went one step further and named a consequence this trial did not: having accepted the file on byte size alone, the session then **reported it to the user as 482×513 in a structured summary table**. The number came from an unrelated diagnostic render and was never re-checked against the file actually sitting in the outputs folder. A silent constraint violation became an actively false claim of compliance. Its own audit calls that the most serious issue of the session, and that judgement is correct: the missing dimension check is one trivial tool call, and without it the failure is invisible to the person being handed the file.

### 12.3 Defect 3 reproduced: the tool-call timeout is real, not a local artifact

The claude.ai session hit a tool-call timeout on the megaphone AVIF render and fell back to a background workaround, which then failed. That is the same failure this trial reproduced at the 120s mark, occurring in the environment the two original timed-out sessions ran in.

### 12.4 Defect 2, in a worse form than this trial found

| asset | format | this trial | claude.ai |
|---|---|---|---|
| megaphone | avif | 482×513, **144/144**, 225.1 KB | 180×192, 36/144, 161.4 KB |
| secure | avif | 524×531, **50/50**, 185.8 KB | 524×531, 17/50, 155.0 KB |

Both claude.ai AVIFs are dramatically worse than what the tool produces when `--target-kb` is allowed to fit AVIF on its own — quarter resolution on megaphone, a third of the frames on secure.

The cause is visible in the session's own log: it applied `--frame-stride 3` and `--frame-stride 4 --resize-max-dim 192` to the AVIF renders manually, explicitly **"same frame-stride as the WebP for visual consistency across formats."** That is a reasonable-sounding instinct and it cost the user roughly 4× the resolution and 4× the frames, because AVIF never needed the degradation — measured here, it fits at full resolution and all 144 frames at q45.

This is Defect 2 doing damage through a second mechanism. It is not only that a dominated file ships unlabelled; it is that **nothing tells a session the two formats have wildly different alpha compression**, so a session reasons about them as interchangeable and drags the good one down to match the bad one. The 7.7× WebP/AVIF gap at equal nominal quality (§6.1) is the fact that would have prevented this, and it is documented nowhere the session could see it.

### 12.5 New defect — `--webp-quality` is silently ignored without `--webp-lossy`

The session ran the same render at `--webp-quality 70` and `--webp-quality 45` and got **byte-identical 403.1 KB output both times**, then correctly concluded the flag had done nothing.

Confirmed in code here. At `scripts/remove_gif_background.py:7906` the encoder is called with `lossless=not args.webp_lossy`, and the lossless branch at `:5610` hard-overrides the caller's value with `quality=100`. So `--webp-quality` is accepted, parsed, and discarded on the default path. A user tuning it sees no change and no warning.

This is the silent-failure class the project already legislates against elsewhere: an argument that cannot take effect must say so rather than be quietly dropped. This trial did not find it because the trial's manual override happened to pass `--webp-lossy` alongside `--webp-quality`, which is exactly the combination that masks it.

### 12.6 The sandbox has ONE logical CPU — the timeout prediction is now a measurement

This trial predicted "a claude.ai container with fewer cores would be bound lower." The session's own investigation confirms it precisely: **only 1 logical CPU is available**, and the skill's worker probe fell back to serial execution. A 120-rung grid over AVIF's slower encoder, run serially on one core, cannot finish inside one tool call.

That closes the loop on the original question. On this M1 Pro the same fit runs 6-wide and takes 207s. Serial on one core it is not a slow call — it is an impossible one.

### 12.7 The stride axis is capped at 4, which is the other half of the empty compliant zone

`build_target_rungs` takes `strides=(1, 2, 3, 4)` (`scripts/remove_gif_background.py:5915`). §4.1 of this report attributed the unreachable compliant zone to the granularity of the scale ladder alone; the session's fact table names the stride cap as well, and both are load-bearing. With stride capped at 4, the search cannot buy enough bytes on the frame axis to stay at 181px, so it is forced onto the scale axis and lands at 120px. **Neither axis alone explains the failure — the two ceilings meet and leave no valid rung.**

Their manual fix ladder is the direct evidence: at `--resize-max-dim 192` (180px wide, compliant) with `--webp-lossy`, quality 70 → 335.0 KB, 45 → 297.5 KB, 30 → 270.0 KB. Still over the cap, and walking down. A compliant answer exists somewhere near quality 15-20 — well below the q60 floor the rung ladder stops at. So for *this* asset at *this* width the q60 floor does bite, even though §6 correctly established it was not what caused the resolution collapse at full resolution. Both statements are true and they are about different rungs.

### 12.8 The tool's own last-printed dimension is STALE after a `--target-kb` fit

This is the mechanism behind the claude.ai session's misreport, and it is a tool defect rather than only an operator lapse.

`scripts/remove_gif_background.py:7922` prints:

```
Output: 482x513, 466.6 KB
```

The `--target-kb` fit begins at `:7944` — **after** that line. When the fit lands it prints only bytes:

```
Final: 242.3 KB (saved over outputs/megaphone_transparent.webp)
```

The file on disk is now 120×128. The last dimensions the tool printed are 482×513, and they are wrong. The claude.ai session reported 482×513 in its delivery table, and its own audit describes that figure as having come from "an unrelated diagnostic render." It did not need to: **the tool printed exactly that number, in the same run, as `Output:`.**

A session reading its own console output and reporting what the tool said would produce the false claim. Reprinting the final dimensions after a fit is a one-line change that would have prevented the most serious failure in that session.

### 12.9 A verification discrepancy worth not smoothing over

This trial measured the microphone interior at `mean_opacity_fraction: 1.0` across all 144 frames. The claude.ai session measured **0.993**, with 0.7% residual, on its own uncropped verify render.

Both numbers are correct for their own render — the flag sets differ (their verify render carried `--erosion-exempt-max-size 549`; this trial's did not). Recording it rather than quoting the flatter number, because "1.0 across 144 frames" is a stronger claim than the evidence supports in general: it is true of one specific render, not a property of the asset. Their reading of the 0.7% — the microphone's own shape changing during the tilt and skew — is the plausible explanation and neither session tested it.

### 12.10 Two smaller observations

**The fringe check declined to answer, correctly.** On megaphone their `edge_fringe_check` returned `looks_fringed: null` at 0.083, inside the documented 0.04–0.15 band where fringed and clean outputs overlap, with explicit instructions not to tune erosion from it. This is the "report unverified rather than a vacuous pass" principle working as designed — worth noting because §8.1 of this report is about the same principle *failing* elsewhere in the same tool.

**A choppiness guard exists and fired.** At stride 6 the tool warned at ~7.9fps. That guard is what kept their fix ladder at stride 4 and therefore on the harder side of the size problem. It is behaving correctly; it is simply another constraint the automatic search does not know it is trading against.

### 12.11 An unattributable artifact

The session's audit flags a `megaphone_transparent_v7.webp` at 245,898 bytes, 180×192 — clearing both constraints — whose **generating command appears nowhere in its tool-call record**. It correctly refused to adopt it on file size alone. Worth recording as a process observation: a file that satisfies the constraints is not a deliverable if nobody can say how it was made.

---

## 12.12 The packaged file itself: a silent failure at the entry point, and 29% dead weight

Raised by Harkirat on reading `SKILL.md` directly. Both halves measured here.

### The first executable instruction fails silently off this machine

`SKILL.md:10` gives exactly one navigation recipe, immediately under a warning never to `cat` the file:

```
rg -n '^#{2,3} ' SKILL.md
```

`rg` is not in the claude.ai sandbox. Harkirat's session substituted `grep`, keeping the pattern — its §4 records running `grep -n '^#{2,3} ' SKILL.md`. Measured here:

```
$ grep -c  '^#{2,3} ' SKILL.md   ->  0     (exit 0)
$ grep -cE '^#{2,3} ' SKILL.md   ->  20
```

`#{2,3}` is ERE; plain `grep` is BRE and reads it as a literal. **Zero matches, exit 0, no error.** A session that cannot run `rg` therefore receives an empty outline of a file it has just been told not to read whole, with nothing indicating failure — it looks like the file has no headings.

This is a silent failure at the entry point of the entire skill, and it is structurally invisible from this repo because `rg` is installed here and the pattern works under it. The same file's `references/lessons.md:18` already gets this right by offering `grep` first — the one place it matters most is the one place with no fallback.

### 28.9% of the file is release notes

| | words |
|---|---|
| lines 1–52 (everything before `## When to use this`) | **3,863** |
| actionable body | 9,488 |
| total | 13,351 |

Almost all of the header is the v6.0.0 changelog — 21 bullets, several of them multi-hundred-word measurement writeups whose own `§N` pointers lead to `references/lessons.md` — plus one-line summaries back to v5.0.0. `references/version-history.md` exists for exactly this and already holds v5.3.0 and earlier; the current release simply never gets moved down when the next one lands. `CLAUDE.md` already states SKILL.md should keep "only the current version's entry plus the versioning convention itself."

**The nuance that makes this more than tidying.** Several changelog bullets are the only statement of a live behaviour — the `--target-kb` rung structure and the `--recommend` three-tier enclosure wording among them — and the claude.ai session pulled both from the changelog into its working fact table. So the block is simultaneously 29% overhead and load-bearing in places. The fix is not deletion: it is moving provenance to `references/version-history.md` while promoting anything a session needs *today* into the body as a present-tense rule. This is the v5.3.0 failure inverted — there, six flags including `--auto` lived only in a changelog and no autonomous run could see them.

Task 8 of the plan implements both halves.

---

## 12.13 Audit pass — what the trial itself got wrong or never checked

Run as a distinct pass after the report was written, per the repo's standing convention. Four things changed as a result, and three of them came from running something rather than re-reading.

### 12.13.1 `--auto` produces a WRONG output on megaphone — measured, not inferred

Neither session ever ran `--auto`; both went manual. So the autonomy path — **this project's stated end goal** — was never exercised on either asset, and the report described Defect 3 far too softly as "the recommender cannot infer intent."

Run here. `--auto`'s own log, line 9:

```
applying: --protect-outline-color f0c850,002864 --feather-band-multiplier 3.3 --erosion-exempt-max-size 549
```

It applies the sparkle colour. **An autonomous run on this asset silently produces an output that contradicts an explicit instruction in the user's prompt**, and reports success. That is the correct severity for this finding, and it belongs at the top of the list rather than in the middle.

⚠️ **A self-caught error, recorded because it is the same trap the report praises the trial agent for catching.** Having confirmed the flag, I then measured sparkle opacity with a **bounding-box mean** — 0.550 under `--auto` against 0.502 under the override. Those numbers are near-meaningless: a bbox spans the sparkle's own opaque yellow body plus surrounding background, so the signal is diluted. They are directionally consistent (the mic bbox moved 0.004, the two sparkle bboxes moved +0.048 and +0.029) and nothing more. **The log line is the evidence; the bbox numbers are not**, and they are recorded here only so nobody later mistakes them for a measurement. The authoritative instrument is `--verify`'s interior mask.

### 12.13.2 `--verify` itself exceeds a tool call on a 144-frame asset

The `--verify` intended to settle §12.13.1 properly **timed out at 2 minutes**. §9 already records it at 39.0s on this machine against an uncropped render; run against the `--auto` output it did not finish.

That extends Defect 3's runtime problem past rendering: on a 144-frame source, **verifying** is also a multi-minute operation. A session on a 1-CPU sandbox cannot render *or* check its work inside one call.

### 12.13.3 The min-dimension fix as planned reaches only one of several consumers

Checked in code rather than assumed, and the result splits.

**Resolved in the plan's favour, but by luck.** Task 1 binds the floor against `alpha_frames[0].shape[:2]`. Crop is at `:7754`, resize at `:7789`, the fit call at `:7954` — so those frames really are the cropped, resized 482×513 ones and the plan's rung table is right. **But this was asserted without checking.** Had the ordering been reversed, the floor would have been computed against 640×640, every rung would have survived, and the fix would have been a silent no-op that still passed all five of its unit tests, because those call the pure function with hand-passed dimensions. The end-to-end test is the load-bearing one; the unit tests structurally cannot see a wrong binding.

**A real gap, unresolved.** `--resize-max-dim` is applied at `:7789` **independently of any fit**, sizing the LONGER side. On an extreme aspect ratio — 900×200 at `--resize-max-dim 192` → 192×43 — the shorter side is 43 and nothing checks it. Worse, `--compress heavy` sets `resize_max_dim: 256` and `optimize`/`medium` set `512` automatically (`:6894-6896`), so a tier can trigger this with no resize flag from the user at all. Filtering rungs inside `fit_to_target_bytes` cannot cover any of that.

**This is the repo's own "count the consumers" failure, committed again while auditing for exactly that class.** The plan now carries a second enforcement point: one check after every resolution-changing step, immediately before the file is reported, asserting the delivered shorter side meets the floor. That covers paths not yet written, which rung filtering never can.

### 12.13.4 An unmade decision, now made explicit

The user said "at least 128px **wide**." The plan implemented `min(width, height)`. For megaphone the two coincide (120×128, so `min` catches the width violation). For a wide short asset they do not: 600×100 passes a width test and fails a `min` test. The plan chose `min` silently and encoded that choice in a test name. It is now stated as a decision with its reasoning — a floor on the shorter side is the safer reading of "at least this big" for a sticker or emoji slot — and flagged as one Harkirat may want to overrule.

### 12.13.5 What was NOT checked, by anyone

Stated plainly rather than left implicit, because several of these are load-bearing for claims already made:

- **Colour fidelity of the delivered files.** Neither session sampled art colours in the compressed output. AVIF at q45 is the specific worry the claude.ai session raised and it remains open.
- **The delivered files' pixels, until this audit.** Both sessions verified against *uncompressed uncropped intermediates* and said so. Contact sheets of all four actual deliverables now exist in `local/2026-08-21-v6-timeout-trial/audit/` — the first time anyone has looked at what was handed over.
- **The gear spin at stride 3, beyond a weak proxy.** Median inter-frame rotation goes 1.57° (source, 50 frames) → 4.24° (WebP, 17 frames), sign stays positive, so there is **no wagon-wheel reversal**. But the measure — angle of the farthest gear-coloured pixel from its centroid — is noisy enough that the *source itself* shows 37 positive and 12 negative steps. It rules out a gross reversal and nothing finer.
- **`--auto` combined with `--target-kb` end to end.** Never run by anyone. The two defects have only been observed separately.
- **Any third asset.** Every generalisation here rests on **n = 2**, both flat vector art on white with a navy outline. In particular "AVIF is 7.7× smaller than WebP at equal nominal quality" is one measurement on one asset, not a property of the format pair.

### 12.13.6 Severity is now derived from a stated rule

The earlier ranking asserted "high" six times with no rule behind it. The rule: **high = ships wrong artwork, or a false claim about it, silently.** Re-ranked against it, `--auto` protecting the sparkles moves from medium to high — it is the only defect that produces a wrong *artistic* result with no user action at all.

---

## 12. Findings, ranked

**Severity rule:** *high = ships wrong artwork, or a false claim about it, silently.* Everything else is medium or below regardless of how annoying it is.

| # | finding | severity | fixable in-tool |
|---|---|---|---|
| 1 | Edge-cleanup erosion defaults to 0 on every 8-bit-alpha output, leaving a ~1px light fringe; `edge_fringe_check` reports it clean | **high** — visible on every WebP/AVIF the manual path has ever produced, and the check that should catch it does not | yes |
| 1 | `--auto` applies `--protect-outline-color f0c850` and protects the sparkles the user asked to remove | **high** — the autonomy path produces wrong art, silently | partly |
| 1b | Frame-stride damage is priced by file size, not by visible damage; stride 3-4 is plainly choppy to a viewer | medium — a destructiveness ordering that does not match perception | needs measurement |
| 2 | `--target-kb` has no min-dimension constraint; silently violates a stated floor | **high** — ships wrong artwork silently | yes |
| 3 | Final dimensions never reprinted after a fit; the last printed `Output:` line is stale | **high** — directly caused a false compliance report | yes |
| 4 | `SKILL.md`'s navigation recipe is `rg`-only; the `grep` substitute returns 0 matches at exit 0 | **high** — silent failure at the skill's entry point | yes |
| 5 | `--webp-quality` silently ignored unless `--webp-lossy` is also passed | **high** — a flag that does nothing, with no warning | yes |
| 6 | No ranking between format outputs; a strictly-dominated file ships with equal billing | **high** — user cannot tell which file is damaged | yes |
| 7 | `--target-kb` runtime exceeds tool timeouts on >100-frame assets, with no pre-flight estimate; `--verify` does too | medium — kills sessions, but loudly | partly |
| 8 | `--verify` silently vacuous on cropped output | medium — a pass that was never computed | yes |
| 9 | 28.9% of `SKILL.md` is release notes a working session does not need | medium — context cost, with load-bearing facts buried in it | yes |
| 10 | Correct in-run diagnostic ("downscaling made this LARGER") not fed back into the search | low | yes |
| 11 | Min-dimension enforcement must cover `--resize-max-dim` and the compress tiers, not only the fit | medium — the planned fix reaches one consumer of several | yes |

Findings 1, 1b, 2, 3, 4, 5, 6, 8, 9 and 11 are covered by `docs/plans/2026-08-22-target-kb-constraints-and-format-ranking.md`. Findings 1, 7 and 10 are partly covered and partly open — see the OPEN QUESTIONS section below, which must be settled before the plan is executed.


---

## 13. Harkirat's own review of the outputs — one new defect, and two re-weightings

Asked directly, with contact sheets of the four delivered files in front of him. His answer found something ten measurements had not.

> "the actual removal is fine. but i do not like the idea that the claude.ai session reduced the frame count so drastically, it's visually detectable when viewing the full playback. also the output of both the claude.ai session and the agent had a ~1 px anti-aliasing edge around the entire artwork which should have been eroded away/removed. Right now the outline does not look 'clean' on any of the outputs."

### 13.1 NEW DEFECT — a 1px light fringe on every 8-bit-alpha output, which the fringe check reports as clean

**The tool said the edge was fine.** `--verify`'s `edge_fringe_check` returned `looks_fringed: false` at 0.0000 for secure — "lower than every measured fringed output, edge is clean" — and `null` at 0.083 for megaphone. A human looked at the same files and saw a fringe on all of them immediately.

**Root cause, and it is a defaults decision rather than a bug in the erosion code.** At `scripts/remove_gif_background.py:7190-7195`, edge-cleanup erosion defaults to **0** for every 8-bit-alpha format, printing:

```
edge-cleanup erosion defaulted to 0 (8-bit alpha needs no fringe trim)
```

That reasoning — partial alpha represents the antialiased edge, so nothing needs trimming — is the assumption Harkirat's eye contradicts.

**Measured, on a controlled pair: the same asset, same flags, erosion 0 against erosion 1.**

| megaphone render | outer opaque ring vs interior art | partial-alpha halo |
|---|---|---|
| delivered AVIF (erosion **0**) | ring is **16.9% closer to white** | **624 px** |
| `--auto` render (erosion **1**) | ring is 26.8% *darker* than interior | **0 px** |

Erosion 1 removes the halo completely. Erosion 0 leaves it. **`--auto` gets this right and the manual path does not** — `--auto` calibrates erosion against the asset's own fringe curve and chose 1 (`auto: --edge-cleanup-erosion 0 -> 1`), while a manual run takes the format default of 0 and keeps the fringe.

⚠️ **Caveat on the instrument, stated rather than buried.** The same ring measure on `secure` shows the outer ring *darker* than the interior (−28.6%), which looks like "no fringe" and is really the metric being confounded: secure's outermost ring is its navy outline, and its "interior" includes white and pink fills. **The metric is only trustworthy as a within-asset comparison between two erosion levels**, which is how the megaphone pair above is read. It is not a cross-asset fringe detector, and it should not be turned into one without a proper negative population.

**Why this is the most consequential finding in the report.** It is not specific to these two assets or to `--target-kb`. Every WebP, AVIF and APNG the skill has produced through the manual path has taken erosion 0 by default. And the check that exists to catch it reports clean.

### 13.2 Frame-stride is more visible than the cost table prices it

> "i do not like the idea that the claude.ai session reduced the frame count so drastically, it's visually detectable when viewing the full playback."

The delivered secure WebP is 17 of 50 frames; the megaphone WebP 36 of 144. §12.13.5 measured no wagon-wheel reversal on the gear and treated that as reassuring. **It was the wrong question** — the defect is not reversal, it is plainly visible choppiness, and a human sees it on the full playback where a six-frame contact sheet cannot show it.

This bears directly on `_SCALE_COST` / `_STRIDE_COST` (`:5887-5888`). The 2026-08-21 reordering demoted a deep downscale *below* frame-stride on the strength of a byte measurement on `galaxy.gif`. That measurement stands — but it prices the two axes by **file size**, and the destructiveness ordering is supposed to price them by **damage**. Harkirat's reaction is direct evidence that stride 3-4 is more damaging than its weights assume. The ordering should not be changed on one reaction either; §14 records this as needing its own measurement, not a taste edit.

### 13.3 Min dimension: default is free, the explicit request is not

> "i meant at least 128 px wide, keeping the same aspect ratio as the original artwork (after cropping the transparent canvas), and whatever height that respectively concluded. but to be fair, thats an explicit ask. as the default method, you can use whichever one you want. but it does need to support explicit requests such as this."

So open question 2 resolves as a **requirement on expressiveness, not on the default**: the tool must be able to express "width ≥ N, aspect preserved." A single shorter-side floor cannot say that. The plan now specifies `--min-width` and `--min-height` alongside `--min-dimension`.

### 13.4 `--auto` should ask

Harkirat chose **ask the user** for a coin-flip enclosure region.

⚠️ **This is in tension with the project's stated end goal and the tension is worth naming rather than smoothing.** `CLAUDE.md`'s end-goal section says the skill should be "completely automatically run-able," and an unattended run has nobody to ask. The plan resolves it by making the question *answerable in advance*: `--auto` refuses with a precise question naming the region and both options, and two new flags (`--assume-protect` / `--assume-remove`, taking colours) let an unattended caller pre-answer it. A run that neither asks nor was pre-answered stops instead of guessing — which is the behaviour Harkirat chose, and it fails loudly rather than shipping wrong art.


---

## 14. OPEN QUESTIONS — settle these before executing the plan

**1. ✅ ANSWERED 2026-08-22 — see §13.** The removal is correct; the fringe and the frame-count reduction are not. Two new findings came out of it. The questions below are what remains open.

This is the first question, and it is not a courtesy. **Every measurement in this report grades the tool against the tool, or against a number you stated.** Not one of them grades it against whether you like the result. That is precisely the structural blindness this repo already recorded from the three-agent trial — the corpus score, the code review and the render diff all compare the product to itself or to a label, and none can see the axis a person sees immediately.

Contact sheets of all four delivered files are in `local/2026-08-21-v6-timeout-trial/audit/`, composited over dark. Specifically worth your eye:
- The **megaphone WebP at 128×136** — is a file this small usable at all, or is WebP simply not worth delivering for this asset?
- The **secure WebP at 17 of 50 frames** — does the gear spin still read correctly, or is it visibly choppy? No reversal was detected, but the measure was weak.
- The **megaphone AVIF at q45** — any visible artefacts? Nobody has checked colour fidelity on any delivered file.
- Whether the **sparkle removal and mic preservation** actually look right to you, as opposed to scoring right.

**Your answer can change what the plan should do.** If the WebP is unusable at any size that fits, then Task 2's format ranking should become a refusal, not a warning. If 17 frames is fine, the frame axis is cheaper than assumed and the stride cap matters less.

**2. ✅ ANSWERED — §13.3.** Default is free; the tool must be able to express "width >= N, aspect preserved." **Still open:** what the DEFAULT should be when no axis is named.

**2b. Min dimension: shorter side, or width specifically?** You said "at least 128px wide x relative height." The plan enforces a floor on the **shorter side**, which is stricter. §12.13.4 has the reasoning. Overrule it if you meant width literally.

**3. ✅ ANSWERED — §13.4.** Ask. The autonomy tension is recorded there. **Still open:** whether a pre-answered unattended run should be allowed to proceed silently, or should still log that it acted on an assumption.

**3b. Should `--auto` refuse, ask, or annotate** when a candidate region's enclosure evidence is a coin flip? On megaphone it protects the sparkles and reports success. Refusing would be safest and would also refuse legitimate work; annotating changes nothing for an autonomous run that reads flags. This is a design decision, not a measurement, and it is the one that most directly affects the project's autonomy goal.

**4. Do findings 1, 7 and 10 get filed to `gif-deferred-list.md`** rather than living only in this document? The repo convention says the tracker is the queue; this report is not.

**5. Should the erosion default change for 8-bit-alpha formats, or should `--auto`'s calibration simply always run?** §13.1 shows `--auto` reaches erosion 1 and a clean edge while the manual path takes 0 and keeps a fringe. Flipping the default to 1 is the blunt fix; making the calibration unconditional is the better one but is slower. This needs a PRE/POST render diff over the corpus before either is chosen — a fringe is not the only thing erosion changes, and this repo has 448 renders' worth of evidence that erosion above 1 destroys artwork.

**6. Does `_STRIDE_COST` need re-weighting after §13.2?** One person's reaction on one asset is a signal, not a measurement. Deciding this needs the same treatment `galaxy.gif` got: a real comparison, on real assets, of what a viewer notices at stride 2, 3 and 4 against what a deep downscale costs. Do not edit the weights on the strength of this report alone.
