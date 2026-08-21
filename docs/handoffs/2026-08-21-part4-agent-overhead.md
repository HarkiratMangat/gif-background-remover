# Handoff — Part 4: cutting agent-overhead

**Written 2026-08-21 at the close of Part 2.** Part 3 stays deferred by Harkirat's own sequencing, so Part 4 is next.

## Read these, in this order, and nothing else first

1. **`docs/plans/2026-08-21-part4-agent-overhead-reduction.md`** — the plan. Four tasks, each with its own steps, verification and model/effort. It is current and was written from a live brainstorming session; do not re-derive its premises.
2. **`gif-deferred-list.md`** — its header carries the current ORDER OF WORK and the Task D note. Read the items directly, never through an older handoff.

⚠️ **Every other handoff in `docs/handoffs/` is stale.** `2026-08-20-v6-backlog-session.md` in particular frames `Cut loop.gif` as a confirmed outlier; that was retracted 2026-08-21.

## The one thing Part 4 is about, and the thing it is NOT

Harkirat's original ask was to take a single-GIF job from a reported 15-20 minutes down to seconds. **The bottleneck is agent tool-call overhead, not script runtime** — he confirmed this directly, and the 2026-08-19 three-agent trial's step logs measure it: a 5-GIF job cost **50-74 tool calls**, roughly 10-15 per asset. `--auto` on a real asset runs in a minute or two.

So Part 4 reduces **round-trips**. It is not a `--fast` flag and it is not parallelism for its own sake. Task B is the one place a bounded internal search legitimately re-introduces parallelism, because it is something the *script* controls end-to-end.

## State of the repo

**Branch `feat/v6-backlog`, nothing committed.** 8 modified files, 4 new, all folded into the **unreleased v6.0.0**. `main` is still at v5.5.0. The live claude.ai skill is v5.4.0.

**Gates as of handoff:** 130 tests pass, `python3 scripts/audit_docs.py` passes. Run both before touching anything, to confirm you are on the same baseline.

### What Part 2 shipped, so it is not re-proposed or re-measured

- **Erosion component exemption** — a small/thin *kept* art component is exempt from edge-cleanup erosion at whatever level was already chosen. Warning 56 → 0 across 336 assets; 22 clean controls score-identical. `references/lessons.md` §37.9.
- **An EARNED erosion-2 ceiling** — level 2 unlocks only on a convex knee in the asset's own fringe curve, only from level 1. 3 of 336 promote. Harkirat reviewed the renders and confirmed it. §37.10.
- **`--edge-softening`** — a 1px alpha ramp restored whenever resolved erosion is ≥2, on 8-bit-alpha containers only. §37.11.
- **Frame nomination** — a cheap dense pass names frames the 40-sample spread would step over. 1 of 910 assets affected, median 3ms. §40.
- **A pre-existing `--analyze` crash**, on 3 corpus assets. §40.
- **The soft-glow candidate** — `--recommend` now names the exact `--fade-color` value instead of claiming there is nothing to recover. Deriving it automatically is FALSIFIED against 92 assets; do not rebuild it. §41.

⚠️ **Task C in the plan hands the erosion exemption to Part 2 as "not Part 4's work". That is now DONE** — strike it rather than picking it up.

## Task D, added last and least specified

Harkirat, 2026-08-21: mine **Dior's Builds' parallelism/caching implementation** — which he notes was crafted by looking at this repo's initial version — for what transfers back. Three separate consumers, kept attributed because a technique that helps one can be irrelevant to another:

1. **The testing workflow** — the loudest pain. Re-tests and cold tests take too long. The concrete open question: `analysis_cache` is keyed on the script SHA, so **any product edit invalidates every entry** — correct for safety, and exactly why a session that edits the product pays cold cost repeatedly. **Did they solve dependency-scoped invalidation?** If so that is the single biggest win available.
2. **The general repo workflow** — judge on whether it removes a *wait*, not on raw seconds.
3. **The packaged `.skill`** — hard boundary: the claude.ai sandbox's CPU/memory profile is unknown and must be detected, never assumed. And script runtime was measured NOT to be the reported bottleneck, so a product-side speedup needs its own justification.

⚠️ **Bring back the falsifiers, not just the techniques.** This repo's caching is only trustworthy because of ten falsifiers covering script-change, asset-touch and corrupt-entry paths — one of which caught a real defect (a numpy float64 written as its repr and read back as a string, while reporting a cache hit). A cache adopted without the test that proves it invalidates will serve a pre-change answer to the change's own gate.

## Standing conventions that bit during Part 2

- **Push, merge and tag are each asked, every time.** Approval never carries over. Branch commits are free.
- **Prove a claim against the PRE code before crediting a fix with it.** A "recovered 8 assets" claim turned out to be 3 — two overlapping failure lists were treated as one. See the memory `feedback_overlapping_failure_lists_are_not_one_list`.
- **Two numbers of the same shape are not comparable until you check they are fractions of the same thing.** A recall of 0.9618 read as a drop from a published 0.9644 until the PRE run landed on 0.9618 exactly; the published figure was over a different population.
- **Run `sequential-thinking` as a distinct pass after the direct work.** It found three real errors in Part 2, none of which any gate caught.
- **Soft-wrap every markdown file, including prose inside fenced blocks.** Nothing gates the fenced case.

## Model + effort

**`Opus5-High`.**

Derived from the grid rather than felt: deliberation is Medium-to-High (four tasks, one of which is a new internal search), but the driver is **premise risk**, which is genuinely High and concentrated in two places. Task D rests on an unverified premise — *"their version is better because it started from ours"* — and the honest outcome may be that little transfers; judging another repo's architecture across a sandbox boundary is exactly that axis. Task B carries a product rule (ask-first, never infer a size target) that must not leak into the search code. Task A alone would be `Sonnet5-High` and the plan says so; if the session ends up being only Task A, step down.

Escalate on events only: a premise proved false → stay at Opus and re-plan rather than pushing on. If Task D's investigation comes back "nothing transfers", that is a result — write it up and stop, do not go looking for something to adopt.

**Session title, ready to paste:**

```
Opus5-High · v6 backlog part 4 — agent overhead + Diors-Builds caching · Aug 21
```
