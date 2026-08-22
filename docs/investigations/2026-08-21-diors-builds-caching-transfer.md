# What transferred back from Dior's Builds' parallelism and caching

**Part 4, Task D. Investigated 2026-08-21.** Harkirat's premise, in his words: Dior's Builds has a parallelism-and-caching implementation *"crafted by looking at our initial implementation of it"*, so there is a downstream version of this repo's own idea that has since diverged — and the question is what came back better. The premise is verified in one place and does not hold in the others, and both halves of that are the result.

## The headline answer

**Yes — they solved dependency-scoped cache invalidation, and it transfers.** `Diors-Builds/utils/algoFingerprint.js` (built 2026-08-11) derives a cache key from the SOURCE of the specific functions and constants that determine an output, rather than from a file hash or a hand-maintained version string. Its own header records that a release-string marker was tried first and rejected by Harkirat, because *"there's a unique versioning for the actual algorithm"* — the key should identify the code that produced the value, not the version it shipped in.

That is exactly the gap this repo's `analysis_cache` had: it keyed on the SHA of the whole of `remove_gif_background.py`, so every edit to the product invalidated all of it, and editing the product is precisely what a session using the harness does.

## The three consumers, kept separate

| Technique | Consumer it serves | What it cost here | Adopted? |
|---|---|---|---|
| Derive the cache key from the algorithm's own source (`algoFingerprint.js`) | **Testing workflow** | ~90 lines + 12 falsifiers | ✅ shipped as `analysis_fingerprint` |
| Strip comments/whitespace before hashing (the same file's `normalize()`) | Testing workflow | one measurement | ❌ **falsified** — see below |
| Shard a self-test across N processes and aggregate (`scripts/docs-audit-test-parallel.mjs`) | **General repo workflow** | — | ❌ not needed — see below |
| Probe capacity rather than hardcode a worker count | **The packaged `.skill`** | ~80 lines | ✅ shipped as `detect_worker_capacity`, independently |

## 1. Testing workflow — adopted, measured at 32.1%

`analysis_fingerprint` hashes every module-level statement that is not a function definition (imports, constants, classes) plus every function transitively reachable from `analyze`, docstrings stripped. **34 of the script's 108 module-level functions are in that closure.**

Measured over the file's real history *before* adopting it, by recomputing both keys at every revision:

- of the **28 commits** that changed `remove_gif_background.py`, a whole-file key invalidates on **all 28**;
- the scoped key invalidates on **19**;
- so **9 commits (32.1%)** keep a warm analysis cache that used to go cold.

For scale: the `trial` population is 31.3s cold and 0.6s warm; a full 797-asset re-score is ~7 minutes warm and roughly an hour cold.

**⚠️ The naive half of the transfer was measured and rejected.** `algoFingerprint.js` strips comments and whitespace before hashing, and this repo is far more comment-dense than that one — so stripping looked like the obvious win. Recomputed over the same 28 commits, a comment-and-docstring-stripped **whole-file** key survives **1 of 28 (3.6%)**. Comment density is not where the cost is; the closure is. Shipping the appealing half without measuring it would have bought almost nothing while feeling like a fix.

**The falsifiers came back with the technique, which was the explicit instruction.** 12 of them, each paired so neither half can pass vacuously: an edit inside the closure must invalidate and one outside must not; a constant and an import always invalidate; prose never does; both fallback paths are exercised; and one end-to-end test drives `cached_analyze` across an out-of-closure edit (expects a hit) and an in-closure edit (expects a miss). It also pins the one case this repo has already been bitten by — `source_transparency_is_the_background`, which gates a band rule from inside `analyze()` (CLAUDE.md release gate 10) — as being inside the closure.

**The error direction is deliberately asymmetric,** copied from `algoFingerprint.js`'s own reasoning: a false invalidation costs one re-analysis; a missed one serves a pre-change answer to the gate meant to detect the change. So an unparseable file, a missing root, or any exception at all falls back to `script_sha`, which invalidates on every byte. A real fingerprint is prefixed `a` and a fallback is not, so `stats()` shows when a run silently fell back.

**What it cannot see, stated rather than assumed:** dispatch the AST does not name — `getattr(module, name)()`, a dict of callables, a C-level hook. None exists in this script today. If one is added on a path `analyze()` reaches, its target has to join `ANALYSIS_ROOTS` or the key drops back to `script_sha`.

## 2. General repo workflow — nothing to transfer, and that is the result

`scripts/docs-audit-test-parallel.mjs` shards their docs audit's 71 checks across N processes, with two aggregation assertions a code review found missing from the first version (every shard reports the same total, and passed+failed summed equals it — so a malformed shard assignment cannot make every shard skip everything and still report clean). It is good work.

**It does not transfer, for a boring reason: our equivalent is already fast enough.** `python3 scripts/audit_docs.py` and the 171-test suite both finish in seconds, and pytest here already runs distributed. The judgement the plan asked for was "does it remove a *wait*" — it does not, because there is no wait. Adopting the sharding machinery would add a wrapper, an aggregation contract and two assertions to maintain, in exchange for nothing measurable.

The **aggregation assertions themselves** are worth remembering as a pattern, though, and one of them is already the standing rule here: *"the shards structurally cannot disagree" was reasoning, not proof.* That is the same rule that made the serial-vs-parallel byte-identity test in `test_target_rung_search.py` mandatory rather than optional.

## 3. The packaged `.skill` — capacity detection, arrived at independently

The plan's hard boundary held: the claude.ai sandbox's CPU and memory profile is unknown and must be probed, never assumed. `scripts/harness/machine.py` already does this for the harness, but it cannot be imported by the product — it is not in the package — so `detect_worker_capacity` in `remove_gif_background.py` is a separate implementation with a wider probe set, because a container can lie in ways a Mac cannot:

- **cgroup v2/v1 CPU quota first.** A container with `cpu.max = 200000 100000` gets 2 cores no matter what `os.cpu_count()` reports, and it commonly reports the host's.
- Then Apple Silicon performance cores, then logical cores.
- Memory from the cgroup limit minus current usage, then Linux `MemAvailable`, then macOS `vm_stat` free+inactive+speculative.
- **Anything unprobeable returns 1 worker** — the serial behaviour that existed before — rather than a guess that could thrash a small container into swap.

Per-worker memory is measured from the actual frame arrays rather than being a constant, so a 64px sticker and a 640px 177-frame animation are not costed the same.

**And the plan's other constraint held too:** script runtime was measured NOT to be the reported bottleneck, so this needed its own justification rather than inheriting Part 4's. It has one — the `--target-kb` grid genuinely walks up to 120 encodes, which is minutes of real work — and it is scoped to that search alone. No other product path gained parallelism.

## What did NOT come back

- Their caches are Mongo/Cloudinary-backed and keyed on a source asset's hash; ours is a local JSON store keyed on path+mtime+size. Nothing in the storage layer transfers.
- Their parallelism is I/O-bound (`Promise.all` over network calls). Ours is CPU-bound image encoding. The shapes have nothing in common beyond the word.
- `feedback_cache_invalidation_on_algorithm_change.md` in their memory folder is worth reading for the failure history — the same mistake recurred five times in one session — but its operational half ("clear the cache scoped to the affected user, never an unscoped `updateMany({})`") is about a shared production database and has no analogue in a gitignored local cache directory that is always safe to wipe.

## Verdict on the premise

*"Their version is better because it started from ours"* is **true for one technique and false as a general claim.** The fingerprint idea is genuinely ahead of what this repo had and is now adopted with its measurement and its falsifiers. The parallelism is a different problem solved for a different bottleneck, and the honest answer there is that nothing transferred — their sharding is not needed and our capacity detection had to be rebuilt from scratch anyway, because the product cannot import the harness.
