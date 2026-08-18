# GIF Background Remover

## What this is
A skill + script for removing/making transparent the background of animated GIFs (icon/sticker/ emoji art, usually antialiased vector art, sometimes pixel art) while protecting interior design elements, plus optional file-size optimization for platform limits (e.g. Discord's 256KB sticker cap). Built and maintained by Harkirat, the sole user. The skill is also uploaded standalone to claude.ai — this repo is the working copy where it actually gets developed and versioned.

**Before doing anything else this session, read `~/.claude/projects/-Applications-Claude-Code-Gif-Background-Remover/memory/user_working_agreement.md`** (start of that folder's `MEMORY.md` index) — it's the living summary of how Harkirat works and what this project expects, with links to every other memory file. `SKILL.md` is the deepest source of truth for the skill's actual operating instructions; `references/lessons.md` holds the full bug-postmortem/tool-evaluation history behind those instructions; this memory folder is the collaboration layer on top of both.

## THE END GOAL — full autonomy (Harkirat, stated 2026-08-17, reiterated the same day)
> "the end goal of this skill is to be completely automatically run-able, with it doing the analysis and recommendation itself correctly. So these edge cases and minor edits/fixes are essentially training and improvement meant to help it reach that completely autonomous phase. As such these fixes need to be considered and implemented properly into the skill's script so it can genuinely catch them and not repeat them. we need it to learn these mishaps, improve it, and stop them from happening again. We can't be manually force-tweaking things to get the correct output when edge cases like this happen. the manual tweaks are essentially just a verification/investigation layer to figure out *how* the mishap occured and how to fix it in the skill"

**What this means in practice, and it changes what counts as "done":**
- A manual flag tweak that fixes an output is **not the fix** — it is the *investigation result*. The fix is whatever change to `--analyze`/`--recommend`/the script makes the tool reach that same answer by itself next time. Delivering the corrected file while leaving the skill unable to derive it is an unfinished job, not a completed one.
- **Never hand back a good output produced by flags the skill did not recommend without also closing the gap that made the override necessary** — or, if it genuinely cannot be closed this session, recording it in `gif-deferred-list.md`'s AUTONOMY BACKLOG with the measured evidence and a concrete next action. Silent overrides are how the same edge case gets rediscovered.
- A *warning* in `--recommend`'s evidence does not count as a fix on its own: an autonomous run takes the suggested flags verbatim, so a warning nobody reads changes nothing. Prefer a real discriminator; emit evidence in addition, never instead.
- When a check cannot be made reliable, it is better for it to say so than to return a confident wrong answer — an unverifiable check must report "unverified", never a vacuous pass (`references/lessons.md` §13, §16, §17).

## File layout
- `SKILL.md` — the skill itself: lean, actionable core instructions (kept under ~500 lines per Anthropic's progressive-disclosure convention for skills — this is what loads into context whenever the skill triggers, so it stays focused on "what to do," not "why," or "what we tried before").
- `references/version-history.md` — per-version detail for every release before the current one, moved out of SKILL.md in v5.0.0 (it had grown to 241 of that file's 896 lines). SKILL.md keeps only the current version's entry plus the versioning convention itself.
- `references/compression.md` — the standalone file-size levers (`--frame-stride`, `--resize-max-dim`, `--target-kb`) and their measured case histories; split out of SKILL.md in v5.1.0.
- `references/flag-reference.md` — what the individual quality/output flags actually do; split out of SKILL.md in v5.1.0.
- `references/lessons.md` — long-form bug postmortems, tool-evaluation writeups (gifski vs. pngquant, etc.), and measured evidence. Read on demand — see the memory folder's `feedback_check_lessons_before_rediagnosing.md` for when. Has its own table of contents.
- `scripts/remove_gif_background.py` — the actual processing script (Python 3; `Pillow`, `numpy`, `scipy.ndimage` as Python deps; `gifsicle` and optionally `pngquant` as external binaries the script shells out to, auto-installed via `apt-get` if missing and `shutil.which` can't find them — that install path assumes a Debian/Ubuntu-family sandbox, not this Mac). **Confirmed on this Mac (2026-07-16) via Homebrew:** `gifsicle`, `pngquant` (3.0.3), `gifski` (1.34.0, not wired into the script yet — see `references/lessons.md` §8 for the confirmed real case it's worth reaching for), `ffmpeg`, and ImageMagick (`magick`) are all on `PATH` — the latter two aren't used by the script but are useful for independent frame-timing/pixel cross-checks during verification. Don't re-verify this later without a reason; if a tool call fails with "not found," that's the actual signal something changed, not a reason to assume it was never installed.
- `local/` (gitignored) — Harkirat's scratch folder: old `.skill` package backups (v1 through the current version), ad-hoc notes he drops in directly (e.g. a `.rtf`/`.txt` file with a question or correction — a real one was missed for part of a session because nothing prompted a check; see the "Live skill sync workflow" section below), and `live-skill-drops/` (see below). **Check `local/` for anything new at the start of a session and periodically during a long one** — don't rely on stumbling onto it by chance.
- `gif-deferred-list.md` (tracked, repo root) — this project's own flagged-findings/TODO tracker, split out 2026-08-07 from the shared `/Applications/Claude Code/meta-deferred-list.md` (same treatment Dior's Builds' `docs/db-deferred-list.md` got). Check it alongside `local/` at session start — same "don't rely on stumbling onto it" reasoning.

## Live skill sync workflow (claude.ai standalone skill ↔ this repo)
This repo is the dev copy. The live skill on claude.ai only gets updated at a repo session's version-bump/push point (a one-directional sync, repo → live, same moment as any other "push").

### What a claude.ai live-skill session can and cannot see (corrected 2026-08-07)
**A claude.ai session runs in its own isolated Linux sandbox. It has no reach into this Mac at all — not to read, and not to write.** Earlier wording here got this wrong in both directions and sent at least one session looking for things that cannot exist; treat the boundary as absolute:

- **It CAN read** `SKILL.md`, `references/`, and `scripts/` — but only the copies bundled inside the `.skill` package that was uploaded to claude.ai, frozen at whatever version that upload was. Not this repo's working copy, and not anything committed since.
- **It CANNOT read** this repo's `CLAUDE.md`, the `~/.claude/projects/.../memory/` folder, `.git` history, or `local/`. None of those are in the package.
- **It CANNOT write anywhere on this Mac** — not `local/live-skill-drops/`, not the repo, nothing.

**The load-bearing consequence: any convention a live session must actually follow has to live inside the packaged files (`SKILL.md` or `references/`), because that is the only thing it ever sees.** A rule that exists only in this `CLAUDE.md` or in the memory folder is invisible to every live session by construction. When adding a rule, decide which side of that line it belongs on.

A live-skill-only session can still produce a real discovery, fix, or edit. That doesn't get saved back into the live skill directly — instead: log the issue/finding to a notepad during that session, implement whatever edit is needed and use it live if relevant, then export the resulting skill as `gif-background-remover-temp-vX.X.X.skill` (plus a companion notes file if there's a notepad worth keeping).

**That export reaches this Mac exactly one way: Harkirat downloads it out of the claude.ai session and puts it in `local/live-skill-drops/` himself.** There is no automated path and no other agent that can place it there. Still check the folder itself rather than waiting to be told a drop arrived — he may well have dropped one in without mentioning it.

**At the start of every Claude Code session on this repo, check `local/live-skill-drops/` for anything not yet in `local/live-skill-drops/reconciled/`, and ALWAYS report the result to Harkirat** — don't just silently reconcile or silently find nothing. Say plainly whether anything new was found. If nothing: a one-line "checked, nothing new" is enough. If something was found: diff its SKILL.md (and any companion notes) against this repo's current SKILL.md/`references/lessons.md`/script, then report concisely what actually happened in that live-skill session (the real discoveries/lessons/edits, not just "found a drop") and what you recommend doing with it (merge as-is, refine further first, or discard) — keep this compact, not a full re-narration, but enough that he actually knows what happened without having to ask. Either merge genuinely new lessons/fixes into the repo version (documenting them the normal way — see `feedback_document_at_change_time.md`) or keep refining before merging, per what was agreed. Once reconciled, move the drop into `local/live-skill-drops/reconciled/` so pending vs. done stays unambiguous.

**Packaging safety, for whenever a repo→live sync actually happens:** don't run skill-creator's `package_skill.py` directly against this directory — it walks the entire tree with no gitignore awareness and would silently bundle `.git` (full repo history), `.remember` (session logs), and `local/` (old `.skill` backups, live-skill-drops) into the new package. Stage a clean copy first (`SKILL.md` + `references/` + `scripts/` only) and package from that.

Those three staged paths are also exactly what a live session will be able to read (see the sandbox-boundary note above) — so treat the staging step as the moment to ask "is everything a live session needs actually inside these three?", not just "is anything private leaking out?"

## Skill versioning (already defined in SKILL.md itself — don't duplicate the logic here)
Three-part `v{major}.{minor}.{correction}`, defined at the top of SKILL.md, including the commit-vs-push distinction (version number bumps at push/finalize, not every repo commit) and how a live-skill temp-drop's provisional version relates to the repo's own final judgment at reconciliation. **Whenever SKILL.md is edited, hand Harkirat the latest full file** (not a diff), and keep the skill's `name` in the frontmatter unchanged. Follow SKILL.md's own definition for what counts as major vs. minor vs. correction — it's the canonical source, this file just flags where to look.

**No separate CHANGELOG.md/DEVLOG.md for this project (decided 2026-07-16).** Unlike Dior's Builds (a running service where a multi-file, sprawling-codebase diff is much less legible than a curated changelog entry), this skill's changes are concentrated in 1-3 files — `git diff`/`git log` between two version tags is already a practical, legible changelog, PROVIDED: (1) every push/ version-bump commit gets git-tagged with its version — **actually in effect starting 2026-07-16**: `v2.2.1` is tagged on the original commit (`b7f6c5c`), so "what changed since the last version" is `git describe --tags` / `git log v2.2.1..HEAD`, not something requiring a maintained separate file, and (2) commit messages at push time are genuinely detailed (a summary line + real bullets on what changed and why), not terse one-liners. `references/lessons.md` and SKILL.md's own internal version log already carry the "why," same role Diors-Builds' DEVLOG plays there.

## Git workflow — follows Dior's Builds (adopted 2026-08-07, Harkirat's instruction)
This repo uses dioreo's working agreement, git flow and conventions. They are the standing convention here now, not a one-off. Canonical sources live in that repo and its memory folder — do not re-derive them from this summary if the detail matters:

| What | Where |
|---|---|
| Working agreement (read first) | `~/.claude/projects/-Applications-Claude-Code-Diors-Builds/memory/user_working_agreement.md` |
| Git lifecycle | `/Applications/Claude Code/Diors-Builds/CLAUDE.md`, git-workflow section |
| Commit / branch / PR naming | `/Applications/Claude Code/Diors-Builds/docs/reference/commit-and-branch-naming.md` |
| Full lifecycle + versioning spec | `/Applications/Claude Code/Diors-Builds/docs/superpowers/specs/2026-07-24-git-branch-pr-workflow-design.md` |
| Model/effort grid | `…-Diors-Builds/memory/reference_priority_tier_system.md` + `feedback_suggest_model_switch.md` |

- **`main` only ever advances through a PR.** Never commit directly to `main`.
- **Branch commits are free. Push, merge, and tag are each asked, every time** — approval never carries over, not even within one session.
- **Conventional Commits v1.0.0 as specified**, only the 11 standard types, `<type>(<scope>): <desc>` — colon and exactly one space, imperative, lowercase, no trailing period. Branches are `<type>/<kebab-description>`. Never rename a branch that has an open PR.
- **Every merge gets a version — the judgement is the SIZE, never whether.**
- **ONE commit + ONE tag per release.** The version bump is the final pre-merge checkpoint ON the branch, so the tag lands on a commit whose SKILL.md already reads the tagged version. Never a follow-up bump commit on `main` after merging.
- `gh pr merge --squash --delete-branch` → `git tag -a vX.Y.Z <squash-sha>` → refresh local refs with `git fetch origin main:main`.
- **Commit trailers carry the real second account:** `Co-Authored-By: diorswrld <310361322+diorswrld@users.noreply.github.com>`, plus the Claude trailer.

**Two adaptations, because dioreo's flow assumes things this repo doesn't have:**
1. **No `package.json`, and deliberately no `CHANGELOG.md`** (see the section above). Dioreo's "changelog entry + version bump on the branch" step maps to **SKILL.md's own version header** — that is this repo's running-version signal.
2. **No dev bot.** Dioreo's pre-PR "test on the dev bot" step maps to **running real GIF fixtures and confirming byte-identical output** against known-good files.

⚠️ **`gh pr merge` has been blocked by the auto-mode classifier** (2026-08-07) as an irreversible GitHub action. Expect it; hand Harkirat the command rather than trying to route around the denial.

## Working rules for this repo
These are the load-bearing ones; the full reasoning for each lives in the memory folder's `feedback_*.md` files, linked from `user_working_agreement.md`.
- **Git flow follows Dior's Builds (dioreo) — adopted 2026-08-07, standing convention.** See the "Git workflow" section below for the full lifecycle. The gate that matters: **branch commits are free; push, PR-merge, and tag are each asked, every time, and approval never carries over.** ⚠️ This bullet used to read "never commit or push without asking first, every time." That predates the dioreo adoption and was superseded by it — the free-branch-commits half is the change; the asked-every-time half still holds for push/merge/tag.
- **Check `local/` (especially `local/live-skill-drops/`) at session start** for anything new — see "Live skill sync workflow" above.
- **Document at the time a real finding lands** — SKILL.md, `references/lessons.md`, memory, and the version bump all get updated in the same turn as the fix/discovery, not as a deferred cleanup pass.
- **Check `references/lessons.md` before re-diagnosing** anything that smells like a past case (flicker, erosion damage, jagged edges, wrong duration, a tool/quantizer tradeoff) — this skill's development history is long and specific, and re-deriving a fix from scratch risks retrying an approach already known to regress.
- **Use `sequential-thinking` whenever auditing or verifying** (standing convention, Harkirat 2026-08-17). Run it as a distinct pass AFTER the direct work, aimed at three questions: what did I get wrong, what did I assert without checking the BEHAVIOUR rather than the signature, and what has neither of us considered? It has surfaced something real nearly every time it has been used here — including reversing one of this session's own findings and catching a defect that only appears in the claude.ai sandbox, the skill's actual deployment target. Cost is negligible and it is unrestricted per the global CLAUDE.md.
- **Verify with real numbers, not a glance** — `--analyze`'s actual fields, real pixel/duration reads, the real interior mask (not a bounding-box approximation) — before claiming something is right or fixed.
- **Test the naive/simpler option end-to-end on real content before a bigger algorithm rebuild.**
- **Be usage-conscious**: batch tool calls, don't re-read what's already in context, and don't spin up a heavyweight session for one small edit or one GIF. Long, continuous single-workspace sessions across real GIF jobs are the actual preference here (so lessons accumulate with full context) — usage-consciousness is what makes that affordable, not shorter sessions.
- **Proactively recommend a model/effort level** when the task calls for a different fit than what's currently running — one clear recommendation, not a range, given *before* starting the work. If part of a batch is a poor fit for the session's setup, recommend deferring it to its own session rather than switching models mid-flow (a mid-session switch reprocesses the whole conversation at full price, no cache carryover).
- **Mark chat chapters at real phase shifts** (setup → a specific GIF job → a bug investigation → a version bump), not every message.

## Repo conventions established 2026-08-17 — REPO SIDE ONLY, do not move these into packaged files
These govern how work is done in this repo. A claude.ai session neither needs them nor can act on them, so they must NOT go into `SKILL.md` or `references/` — that is the sandbox-boundary rule in the "Live skill sync workflow" section, applied in the other direction. (One of these lessons was written into `references/lessons.md` §24 first and had to be lifted back out; Harkirat's correction: "that's a lesson specific for the repo and belongs in repo read files.")

### Markdown is SOFT-WRAPPED
One physical line per paragraph, list item or quoted paragraph; the editor wraps for display. Adopted from Dior's Builds, whose reasoning applies here more strongly than there: measured 2026-08-17, **2,239 of 2,965 prose lines (75.5%) broke mid-sentence**, so `rg` could not match most multi-word phrases (Dior's Builds decided the same at 64.6%). After migration: 2-9%.

Reflow with that repo's script, `--check` before `--write`; its token-preservation invariant is what makes the migration trustworthy, and it passed on all 28 files with 0 failures:
```
node "/Applications/Claude Code/Diors-Builds/scripts/reflow-prose.mjs" --check <files>
```
**This applies to every `.md` in scope, including the memory folder** — those were hand-wrapped during the very session that ran the migration, which Harkirat caught.

### `references/lessons.md` upkeep — it is ~51k tokens and must stay navigable

⚠️ **The size claim in this heading, in SKILL.md and in the file's own "how to read this" block is a COUNTED CLAIM that nothing gates.** It read "~32k" in all three places while the file had grown to ~46k — a 44% understatement in exactly the number a session uses to decide whether it can afford to read the file. Re-derive it (`wc -c` / 4) whenever sections are added, or it silently rots again. Whenever a section is ADDED to it:
1. Add a **ToC entry** and at least one **symptom-table row**. Measured: 6 of 25 sections had become unreachable from the symptom table, including that session's own work — a lesson nobody can find is a lesson nobody has.
2. If the section will exceed roughly 1,500 tokens, give its subsections **numbered anchors** (`### 16.5 …`) so a reader can extract a part. §16 was 6,500 tokens in 21 unnumbered subsections; numbering made §16.5 a 245-token read.
3. Keep the "How to read this file" block accurate — a session must be told to grep or extract, never to read the file whole.

### Release gates — run these BEFORE merging, not after
0. **`python3 scripts/audit_docs.py` must pass.** ⚠️ **It now also covers two things this checklist used to ask you to do BY HAND — do not re-do them manually, and do not assume they are still manual:** (a) every `SS<N>` lessons pointer the SCRIPT prints in its own evidence strings resolves to a real section, and (b) no packaged file (`SKILL.md`, `references/`, `scripts/remove_gif_background.py`) points at a repo file that is NOT packaged. Both were added 2026-08-18, after v5.3.0 shipped a recommendation citing a `references/lessons.md SS25` that had never been written: the gate checked the prose files and never the product's own output, which is the half an autonomous run actually reads. `CLAUDE.md` is allowlisted in (b) because it appears only in the sandbox-boundary paragraphs whose point is to name what a live session cannot reach. Both are proven non-vacuous — reintroducing either defect exits 1. It gates the packaged docs against the script: every argparse flag reachable from SKILL.md's instructional BODY (not just its changelog), every `§N` and `references/*.md` pointer resolving, every lessons section reachable from both the ToC and the symptom table. It exists because the docs passed every structural check while SIX flags — including `--auto` and `--auto-erosion`, the autonomy feature this project is aimed at — appeared nowhere but SKILL.md's version changelog. **A changelog reads like documentation and is not.** Proven non-vacuous: reintroducing the real defect makes it exit 1.

The v5.1.1 release exists only because these ran after the v5.1.0 tag instead of before it, which cost two extra version bumps and two extra merges:
1. **Build the `.skill` and gate the BUILT artifact** — not the working tree. Only the package shows what actually ships: it caught a private path (`local/Diors-builds Emojis/…`) and four pointers to `gif-deferred-list.md`, which is tracked but not packaged. Re-run the gate on every REBUILD; trusting the previous run missed one.
2. **Every `references/…` pointer in the packaged `SKILL.md` must resolve inside the zip.**
3. **No private paths** (`/Users/…`, `local/…`, `.remember`) and no pointers to unpackaged repo files.
4. **Reconcile the version entry against the commits** — check whether an earlier bullet contradicts a later one, and whether any bullet describes as a FIX something later measurement reclassified. When correcting a stale claim, grep for the CLAIM, not the paragraph.
5. **A checklist that omits the primary case manufactures confidence.** Auditing the frontmatter description, the term list was built from the NEW capabilities — WebP, AVIF, `--auto`, pixel art — and never tested "remove the background", the skill's entire purpose. The tidy column of pass/fail marks implied the core had been checked when it had not been looked at once; Harkirat caught it. **Before trusting a checklist, ask what the single most important case is and confirm it is ON the list.** Same failure as §23's circular fixture and the repo-root-only path test — reproduced while auditing for that exact class of error.
5. **Confirm behaviour, not signatures.** A changed argparse default nearly caused six correct statements to be "fixed"; the default was a sentinel that resolves to the old value.

### Merge discipline — the failure that motivated writing this down
`main` advances only through a PR, and **push, merge and tag are each asked, every time; approval never carries over.** On 2026-08-17 one authorization ("commit, push, pr, tag, and merge") was treated as covering three consecutive releases, two of which were merged while Harkirat still had open questions. Batch audit findings into ONE release; ask again for each subsequent one.

## Validation status
**Validated in practice on 2026-08-07** — the first real GIF jobs since the 2026-07-14/16 setup session. Three 640x640 white-background gem icons (`ruby`, `jewelry`, `gemstone`) were processed end to end with the v3.1.0 drop's script and accepted by Harkirat. What that exercised: `--protect-outline-color` enclosure verified per-frame across an overlapping-elements animation, `--erosion-exempt-max-size` on small isolated removed regions, and `--dither-mode none` on art with a fade baked in against the background. Two real findings came out of it — `references/lessons.md` §12 and §13.

**A version bump and a GitHub push are still NOT the same thing as syncing to the live claude.ai skill.** The repo can be versioned/pushed as the real, current state of the code without that implying it's been redistributed to claude.ai (Harkirat's explicit call, 2026-07-16). The repo→live sync is a separate, manual upload step — see "Live skill sync workflow" above, and note the sandbox-boundary section there for why the packaged files are the only thing a live session sees.
