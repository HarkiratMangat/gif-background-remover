# Part 4 — Cutting Agent-Overhead, Not Script Runtime

**Filed 2026-08-21, from a live brainstorming session with Harkirat.** Sequencing, his call: Part 2 (erosion residue + the 40-frame spread) next session, Part 3 (`CatPackFree`, the keyer pair) stays deferred, Part 4 — this document — after Part 2. ⚠️ **Task D was added 2026-08-21, after the rest**, and is explicitly NOT to be investigated before the Part 4 session — filing it was the whole instruction.

## Why this exists, and why it is NOT a `--fast`/parallelism flag

Harkirat's original ask was to speed up a single-GIF job from a reported 15-20 minutes down to seconds. The instinct was a `--fast` flag with parallelism/caching, mirroring the harness speed work (`machine.default_jobs()`, `ThreadPoolExecutor`, the analysis cache). **That instinct targets the wrong bottleneck.** Asked directly, Harkirat confirmed the 15-20 minutes is "mostly agent overhead," not script runtime — and the 2026-08-19 three-agent trial's own `STEPLOG.md` files prove it with real numbers: a 5-GIF job cost **50-74 tool calls** (agent 1: 59, agent 2: 50, agent 3: 74), roughly 10-15 per asset. At any realistic per-call reasoning+latency cost, that alone accounts for the reported time far better than script CPU time does — `--auto` on a real asset this session ran in the range of a minute or two, not tens of minutes.

So this plan is about **reducing round-trips**, not speeding up any single render. Where a genuine, bounded, internal search is unavoidable (Task B), that is also where parallelism/caching legitimately re-enters — scoped to something the *script* controls end-to-end, not something depending on the agent picking the right flags across several separate invocations.

**Evidence this plan is built on**, so it is not re-derived: `local/Corpus Trial Gifs/agent-{1-vague,2-detailed,3-expert}/STEPLOG.md` (raw step logs, "Total tool calls" and "Times I re-ran" sections), `docs/investigations/2026-08-19-three-agent-package-trial.md` (the synthesis), and the verification done THIS session (below) confirming which of the trial's own fixes already cover part of this and which don't.

## What's already shipped, verified this session, not to be re-proposed

`docs/plans/2026-08-20-post-trial-defects.md` Task 7 claimed to have fixed the FORMAT-boilerplate repetition (agent 2's "the single most wasteful thing I read all session"). **Verified true, but narrower than the outcome table implies:** the dedup (`scripts/remove_gif_background.py:2477`, `global _FORMAT_RANK_EMITTED`) is a **module-level flag scoped to one PROCESS**. It fully suppresses the ~150-word ranking on the 2nd+ job of a single `--batch` manifest run. It does **nothing** when the agent invokes `--recommend`/`--auto` as N separate CLI calls across N separate tool-call turns — which is exactly what the trial's own step logs show happening, and is the default shape of casual multi-file work, because the CLI's `input_gif`/`output_gif` args are single positional args (`nargs='?'`) with no way to pass several files without first hand-building a JSON manifest. **Task A below is the completion of Task 7, not a duplicate of it.**

Also verified still-live: SKILL.md is 338 lines / **75KB**, comfortably under this repo's own "~500 line" convention by line count but still large enough in raw bytes that all three trial agents independently hit a `cat SKILL.md` failure (auto-persisted for size) before falling back to chunked reads — a wasted call, paid by every agent, before real work started.

The COIN-FLIP enclosure wording (§38's fix, the other documentation confusion the trial forced a source-dive over) is confirmed present in the current script — no action needed there.

## Global Constraints

- **No behavior change to what gets recommended or rendered** — this plan touches output text, CLI ergonomics, and SKILL.md workflow guidance. A pixel of any output must not move because of this plan; if a task's own investigation finds it needs to, that is scope creep and gets filed separately.
- **Nothing here assumes the claude.ai sandbox's CPU/memory profile.** Where Task B's internal search could parallelize, it must detect capacity the way `machine.default_jobs()` does, not hardcode a worker count.
- **Every claim about "already shipped" gets checked against the current file, not against the 2026-08-20 plan's outcome table** — that table was itself checked this session and found half-right (Task 7 shipped, but scoped to `--batch` only). Trust behaviour, not a changelog entry.

---

## Task A: Close the gap Task 7 left — dedup that survives across separate CLI invocations

**Files:**
- Modify: `scripts/remove_gif_background.py` — accept multiple positional input files without requiring a hand-built JSON manifest
- Modify: `SKILL.md` — teach the agent when to reach for that, and trim/restructure for the `cat`-failure problem

- [ ] **Step 1: Let the CLI take N files directly, not just one file or a manifest.** `input_gif` currently accepts exactly one path (or none, for `--batch`). Add support for multiple positional paths in the single-file (non-`--batch`) code path, writing each to a name derived from the input (mirroring what `--batch` already does per manifest entry) unless an explicit `output_gif` is given (which only makes sense for exactly one input — keep that combination an error, not a guess). This is the ergonomic gap that pushes agents toward N separate invocations in the first place: building a JSON manifest is real overhead for "just run `--recommend` on these 5 files."
- [ ] **Step 2: Extend `_FORMAT_RANK_EMITTED`-style dedup to this new multi-file path**, exactly as it already works inside `--batch` — same mechanism, now reachable without a manifest.
- [ ] **Step 3: State the convention in SKILL.md explicitly** — "2+ files in one job → pass them all to one invocation (or use `--batch` if they need different flags), never N separate calls" — as a stated rule, not left for the agent to infer. This is the fix for the trial's actual observed pattern (5 separate `--recommend` calls), not just the mechanism Task 7 already built.
- [ ] **Step 4: Address the `cat SKILL.md` failure independently of file size.** All three trial agents hit this before doing anything else. Two real options, not mutually exclusive: (a) add one explicit line near the top of SKILL.md — "this file is too large for a single `cat`; read it in chunks or by section from the start" — cheap, doesn't touch content; (b) re-examine whether SKILL.md's 338 lines can shed more into `references/` the way v5.1.0 already did once (compression.md, flag-reference.md) — only pursue if (a) alone doesn't resolve it, since further splitting has its own cost (more files to orient across). Measure which is actually needed by checking what size threshold the sandbox's `cat`-equivalent trips at, if that's discoverable; otherwise ship (a) first as the cheap, safe default.
- [ ] **Step 5: Verify.** Run `--recommend` on 3+ real files via the new multi-file path in ONE invocation; confirm the ranking block appears exactly once in the combined output (`rg -c 'full resolution ->'` on the captured stdout must read 1, not N). Confirm single-file invocations are byte-identical to before (no regression on the common case). `python3 scripts/audit_docs.py` must still pass.

**Model + effort:** premise Low (the mechanism to extend already exists and is proven inside `--batch`; this is applying it one layer up) · deliberation Medium (touches the CLI's argument parsing and the single-vs-batch code fork, which needs care not to regress the single-file path) → `Sonnet5-High`.

---

## Task B: Fold the compression/size search into one flag — WITH an explicit default and an explicit ask-first rule

**The design constraint Harkirat set, stated precisely so it can't drift while building this:** if the user gave **no** size/format/compression requirement at all, the default is **full-resolution, no compression search, no guessing.** The agent must not infer a target from vibes. When the job is ambiguous on something this flag would need — a size cap, a specific destination format, whether to trim transparent canvas margin, whether to resize — **the agent asks the user directly** (an explicit clarifying question in the live session, equivalent to this harness's own `AskUserQuestion` pattern) rather than picking a plausible-sounding default and rendering it.

**Files:**
- Modify: `scripts/remove_gif_background.py` — a new flag (working name `--target-kb` already exists per `references/compression.md`; this task is about making the SEARCH internal rather than requiring the agent to drive it by hand) plus a canvas-trim option if one doesn't already exist (check `references/flag-reference.md` first — do not build a duplicate of an existing lever)
- Modify: `SKILL.md` — the ask-first rule, stated as a decision gate before any compression flag is chosen

- [ ] **Step 1: Confirm what already exists before building anything.** `--target-kb` is documented in `references/compression.md` already — read it and `--frame-stride`/`--resize-max-dim`'s current behavior first. This task may be "make the existing levers searchable in one call" rather than "invent a new flag" — check before assuming the gap is bigger than it is.
- [ ] **Step 2: Write the ask-first rule into SKILL.md as an explicit gate**, ahead of any compression guidance: "No size/format constraint stated by the user → render at full resolution, no compression flags, full quality. A size cap, a named destination (Discord emoji, a specific chat app), an explicit 'small file', 'trim the canvas', or 'resize' → those are real constraints and may be acted on directly. Anything else that would require GUESSING a target (an unstated but implied size limit, an ambiguous format preference) → ask the user, do not infer." This is the highest-priority sub-item — it prevents Task B's own search from becoming a new source of silent, wrong defaults.
- [ ] **Step 3: Build the internal grid search**, gated behind an explicit user-given target (a byte cap or a named platform). Native resolution/downscale × quality tier × frame-stride, scored by the harness's own existing size/quality tradeoffs (`references/compression.md`'s measured case histories are the reference, not a fresh design) — return ONE recommended render plus a short table of what was tried, not N files for the agent to compare by hand. This directly targets the trial's biggest measured single cost: agent 2's 9-11 manual renders on `galaxy`/`growth` alone.
- [ ] **Step 4: This is where bounded internal parallelism/caching legitimately fits**, if the grid search is slow enough to warrant it — mirror `machine.default_jobs()`'s capacity-detection, not the harness's exact numbers (a live claude.ai sandbox is a different, likely much smaller container than this Mac; detect, don't assume). Only build this if Step 3's serial search is measured too slow to justify skipping it — prove the need before adding the complexity, same standard this repo already holds itself to for the harness's own `--jobs`.
- [ ] **Step 5: Verify.** Render the same asset through the old manual multi-flag path and the new single-flag search; confirm the new path's chosen output is equal-or-better on the same measures `references/compression.md` already uses, and confirm the search only ever RUNS when a real constraint was given (a test asserting "no flag, no constraint stated → output is full-resolution, untouched" is the falsifier for Step 2's rule leaking into Step 3's code).

**Model + effort:** premise Medium (the ask-first rule is a clear product decision already made by Harkirat, but the grid-search's internal design and its interaction with existing compression flags needs real thought) · deliberation High (new search logic, a new SKILL.md gate that must not regress the common no-constraint case, and a possible internal-parallelism decision) → `Opus5-High`.

---

## Task C: Pre-flight checks — a standing principle, not a checklist to re-run

**Files:** none yet — this task is a practice, not a fixed scope.

All five of the 2026-08-19 trial's defects are already shipped or deliberately bounded (checked this session — see the outcome table in `docs/plans/2026-08-20-post-trial-defects.md`, cross-referenced above). **There is no remaining backlog item from that trial to re-fix.** What Task C actually is: the trial and tonight's own session (the frame-coalescing bug, the `Starters!` thin-rim finding) both demonstrate the same pattern — an agent burns many tool calls investigating something the tool could have flagged BEFORE the agent had to discover it by rendering and comparing. The blank-frame scan is the worked example of turning that into a proactive check.

- [ ] **Standing practice, not a task list:** whenever a future live session (a real job, a trial, an audit) produces a multi-step investigation that resolves to "the tool could have said this up front," file it as a candidate pre-flight check the same way the blank-frame scan was filed and built — cheap, every-frame, no sampling gap. Do not wait for a batch of five to accumulate before acting on one.
- [ ] **One concrete candidate already on the table from tonight:** the small/thin-art-component erosion exemption (validated against 20 of 42 residue assets this session) is exactly this pattern — `check_erosion_damage`'s WARNING already detects it, print-only, and nothing acts on it. **This lives in Part 2's scope, not Part 4's** — flagged here only so Part 4 doesn't accidentally re-propose it as new work when Part 2 picks it up next session.

**Model + effort:** not applicable — this is a practice to carry forward, not a scoped implementation task. Re-evaluate model/effort per candidate when one is actually filed.

---

## Task D: Mine Dior's Builds' parallelism/caching implementation for what this repo can reuse *(added 2026-08-21 by Harkirat — DO NOT investigate before the Part 4 session)*

**Files:** `/Applications/Claude Code/Diors-Builds/` (read side), then whichever of `scripts/harness/*.py`, `scripts/remove_gif_background.py` and the packaging path the findings actually reach.

**The premise, in Harkirat's words:** Dior's Builds has its own parallelism-and-caching implementation, *"crafted by looking at our initial implementation of it"* — i.e. it started from this repo's `machine.default_jobs()` / `ThreadPoolExecutor` / `local/.analysis-cache/` work and went further. So there is a downstream version of our own idea that has since diverged, and the question is what came back better.

**Three separate consumers to evaluate it against, and they are NOT the same problem** — a technique that helps one can be irrelevant or harmful to another, so keep the findings attributed:
- [ ] **The testing workflow — the loudest pain, and the reason this is filed.** Re-testing and cold tests take too long. Concrete numbers from THIS session to beat: the 336-asset render set costs **1,272s cold** (and 2,001s with component protection on); a full 797-asset `analyze()` re-score costs ~7 minutes warm but its cold cost is what bites; `analysis_cache` already gives **31.3s cold → 0.6s warm** on the `trial` population, but it is keyed on the script SHA, so **any product edit invalidates every entry** — which is correct for safety and is exactly why a session that edits the product pays cold cost repeatedly. **The interesting question is whether Dior's Builds solved partial//dependency-scoped invalidation**, i.e. a cache that survives an edit that provably cannot reach the cached computation. If it did, that is the single biggest testing win available here.
- [ ] **The general repo workflow** — gates, audits, the release checklist. Cheaper than the render sets, so judge any change here on whether it removes a *wait*, not on raw seconds.
- [ ] **The `.skill` itself** — the packaged product. ⚠️ **This is the one with a hard boundary:** anything adopted here has to work in the claude.ai sandbox, whose CPU/memory profile is unknown and must not be assumed (this plan's own Global Constraints already say so). Capacity has to be detected the way `machine.default_jobs()` does, never hardcoded. And per Part 4's framing, script runtime was measured NOT to be the reported bottleneck — so a product-side speedup needs its own justification rather than inheriting this plan's.

**Method, so this does not become an open-ended read:** start from what Dior's Builds' implementation does that ours does not, not from a general tour. Its own memory folder and `CLAUDE.md` are the entry points (`~/.claude/projects/-Applications-Claude-Code-Diors-Builds/memory/`, `/Applications/Claude Code/Diors-Builds/CLAUDE.md`). Produce a short table — technique, which of the three consumers it could serve, what it would cost here, and whether the measurement to justify it already exists — and only then propose adoptions.

⚠️ **Bring back the falsifiers too, not just the techniques.** This repo's own caching work is only trustworthy because of the ten falsifiers in `scripts/harness/test_harness_infra.py` covering script-change, asset-touch, corrupt-entry and disabled paths — including the one that caught a real defect (a naive `default=str` writing a numpy float64 as its repr and reading it back as a string while reporting a cache hit). **A cache adopted without the test that proves it invalidates is a cache that will serve a pre-change answer to the change's own gate.** If Dior's Builds has a mechanism we adopt, adopt its falsifier or write one before trusting it.

**Model + effort:** `Opus5-High`. Premise risk is the real cost here, not deliberation load — the framing "their version is better because it started from ours" is plausible and unverified, and the honest outcome may be that little transfers. Reading another repo's architecture and judging what genuinely applies across a sandbox boundary is exactly the premise-risk axis.

---

## Self-Review

- **Placeholder scan:** none — every step names a concrete file, function, or verification command already available in this repo.
- **Internal consistency:** Task A and Task 7 (already shipped) are explicitly reconciled — A extends 7's mechanism rather than duplicating it. Task C explicitly hands the erosion-exemption candidate to Part 2 rather than claiming it here, matching Harkirat's own Part 2/4 split.
- **Scope check:** three tasks, each independently shippable and independently reviewable — A touches CLI ergonomics + docs, B is the one real feature (with its guardrail specified precisely enough not to drift), C is a practice with one already-identified but explicitly-not-owned candidate.
- **Ambiguity check:** Task B's default behavior (full-resolution, ask-first) is stated as an exact rule, not a preference, because that was the one place Harkirat corrected the framing directly — restating it loosely here would reintroduce the ambiguity he closed.
