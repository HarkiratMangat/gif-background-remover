# GIF Background Remover

## What this is
A skill + script for removing/making transparent the background of animated GIFs (icon/sticker/
emoji art, usually antialiased vector art, sometimes pixel art) while protecting interior design
elements, plus optional file-size optimization for platform limits (e.g. Discord's 256KB sticker
cap). Built and maintained by Harkirat, the sole user. The skill is also uploaded standalone to
claude.ai — this repo is the working copy where it actually gets developed and versioned.

**Before doing anything else this session, read
`~/.claude/projects/-Applications-Claude-Code-Gif-Background-Remover/memory/user_working_agreement.md`**
(start of that folder's `MEMORY.md` index) — it's the living summary of how Harkirat works and
what this project expects, with links to every other memory file. `SKILL.md` is the deepest source
of truth for the skill's actual operating instructions; `references/lessons.md` holds the full
bug-postmortem/tool-evaluation history behind those instructions; this memory folder is the
collaboration layer on top of both.

## File layout
- `SKILL.md` — the skill itself: lean, actionable core instructions (kept under ~500 lines per
  Anthropic's progressive-disclosure convention for skills — this is what loads into context
  whenever the skill triggers, so it stays focused on "what to do," not "why," or "what we tried
  before").
- `references/lessons.md` — long-form bug postmortems, tool-evaluation writeups (gifski vs.
  pngquant, etc.), and measured evidence. Read on demand — see the memory folder's
  `feedback_check_lessons_before_rediagnosing.md` for when. Has its own table of contents.
- `scripts/remove_gif_background.py` — the actual processing script (Python 3; `Pillow`, `numpy`,
  `scipy.ndimage` as Python deps; `gifsicle` and optionally `pngquant` as external binaries the
  script shells out to, auto-installed via `apt-get` if missing and `shutil.which` can't find
  them — that install path assumes a Debian/Ubuntu-family sandbox, not this Mac). **Confirmed on
  this Mac (2026-07-16) via Homebrew:** `gifsicle`, `pngquant` (3.0.3), `gifski` (1.34.0, not
  wired into the script yet — see `references/lessons.md` §8 for the confirmed real case it's
  worth reaching for), `ffmpeg`, and ImageMagick (`magick`) are all on `PATH` — the latter two
  aren't used by the script but are useful for independent frame-timing/pixel cross-checks during
  verification. Don't re-verify this later without a reason; if a tool call fails with
  "not found," that's the actual signal something changed, not a reason to assume it was never
  installed.
- `local/` (gitignored) — Harkirat's scratch folder: old `.skill` package backups (v1 through the
  current version), ad-hoc notes he drops in directly (e.g. a `.rtf`/`.txt` file with a question
  or correction — a real one was missed for part of a session because nothing prompted a check;
  see the "Live skill sync workflow" section below), and `live-skill-drops/` (see below). **Check
  `local/` for anything new at the start of a session and periodically during a long one** — don't
  rely on stumbling onto it by chance.

## Live skill sync workflow (claude.ai standalone skill ↔ this repo)
This repo is the dev copy. The live skill on claude.ai only gets updated at a repo session's
version-bump/push point (a one-directional sync, repo → live, same moment as any other "push").

### What a claude.ai live-skill session can and cannot see (corrected 2026-08-07)
**A claude.ai session runs in its own isolated Linux sandbox. It has no reach into this Mac at
all — not to read, and not to write.** Earlier wording here got this wrong in both directions and
sent at least one session looking for things that cannot exist; treat the boundary as absolute:

- **It CAN read** `SKILL.md`, `references/`, and `scripts/` — but only the copies bundled inside
  the `.skill` package that was uploaded to claude.ai, frozen at whatever version that upload was.
  Not this repo's working copy, and not anything committed since.
- **It CANNOT read** this repo's `CLAUDE.md`, the `~/.claude/projects/.../memory/` folder, `.git`
  history, or `local/`. None of those are in the package.
- **It CANNOT write anywhere on this Mac** — not `local/live-skill-drops/`, not the repo, nothing.

**The load-bearing consequence: any convention a live session must actually follow has to live
inside the packaged files (`SKILL.md` or `references/`), because that is the only thing it ever
sees.** A rule that exists only in this `CLAUDE.md` or in the memory folder is invisible to every
live session by construction. When adding a rule, decide which side of that line it belongs on.

A live-skill-only session can still produce a real discovery, fix, or edit. That doesn't get saved
back into the live skill directly — instead: log the issue/finding to a notepad during that
session, implement whatever edit is needed and use it live if relevant, then export the resulting
skill as `gif-background-remover-temp-vX.X.X.skill` (plus a companion notes file if there's a
notepad worth keeping).

**That export reaches this Mac exactly one way: Harkirat downloads it out of the claude.ai session
and puts it in `local/live-skill-drops/` himself.** There is no automated path and no other agent
that can place it there. Still check the folder itself rather than waiting to be told a drop
arrived — he may well have dropped one in without mentioning it.

**At the start of every Claude Code session on this repo, check `local/live-skill-drops/` for
anything not yet in `local/live-skill-drops/reconciled/`, and ALWAYS report the result to
Harkirat** — don't just silently reconcile or silently find nothing. Say plainly whether anything
new was found. If nothing: a one-line "checked, nothing new" is enough. If something was found:
diff its SKILL.md (and any companion notes) against this repo's current
SKILL.md/`references/lessons.md`/script, then report concisely what actually happened in that
live-skill session (the real discoveries/lessons/edits, not just "found a drop") and what you
recommend doing with it (merge as-is, refine further first, or discard) — keep this compact, not a
full re-narration, but enough that he actually knows what happened without having to ask. Either
merge genuinely new lessons/fixes into the repo version (documenting them the normal way — see
`feedback_document_at_change_time.md`) or keep refining before merging, per what was agreed. Once
reconciled, move the drop into `local/live-skill-drops/reconciled/` so pending vs. done stays
unambiguous.

**Packaging safety, for whenever a repo→live sync actually happens:** don't run skill-creator's
`package_skill.py` directly against this directory — it walks the entire tree with no gitignore
awareness and would silently bundle `.git` (full repo history), `.remember` (session logs), and
`local/` (old `.skill` backups, live-skill-drops) into the new package. Stage a clean copy first
(`SKILL.md` + `references/` + `scripts/` only) and package from that.

Those three staged paths are also exactly what a live session will be able to read (see the
sandbox-boundary note above) — so treat the staging step as the moment to ask "is everything a
live session needs actually inside these three?", not just "is anything private leaking out?"

## Skill versioning (already defined in SKILL.md itself — don't duplicate the logic here)
Three-part `v{major}.{minor}.{correction}`, defined at the top of SKILL.md, including the
commit-vs-push distinction (version number bumps at push/finalize, not every repo commit) and how
a live-skill temp-drop's provisional version relates to the repo's own final judgment at
reconciliation. **Whenever SKILL.md is edited, hand Harkirat the latest full file** (not a diff),
and keep the skill's `name` in the frontmatter unchanged. Follow SKILL.md's own definition for
what counts as major vs. minor vs. correction — it's the canonical source, this file just flags
where to look.

**No separate CHANGELOG.md/DEVLOG.md for this project (decided 2026-07-16).** Unlike Dior's
Builds (a running service where a multi-file, sprawling-codebase diff is much less legible than a
curated changelog entry), this skill's changes are concentrated in 1-3 files — `git diff`/`git log`
between two version tags is already a practical, legible changelog, PROVIDED: (1) every push/
version-bump commit gets git-tagged with its version — **actually in effect starting 2026-07-16**:
`v2.2.1` is tagged on the original commit (`b7f6c5c`), so "what changed since the last version" is
`git describe --tags` / `git log v2.2.1..HEAD`, not something requiring a maintained separate file,
and (2) commit messages at push time are genuinely detailed (a summary line + real bullets on what
changed and why), not terse one-liners. `references/lessons.md` and SKILL.md's own internal
version log already carry the "why," same role Diors-Builds' DEVLOG plays there.

## Working rules for this repo
These are the load-bearing ones; the full reasoning for each lives in the memory folder's
`feedback_*.md` files, linked from `user_working_agreement.md`.
- **Never commit or push without asking first, every time** — approval doesn't carry over between
  asks, even within one session.
- **Check `local/` (especially `local/live-skill-drops/`) at session start** for anything new —
  see "Live skill sync workflow" above.
- **Document at the time a real finding lands** — SKILL.md, `references/lessons.md`, memory, and
  the version bump all get updated in the same turn as the fix/discovery, not as a deferred
  cleanup pass.
- **Check `references/lessons.md` before re-diagnosing** anything that smells like a past case
  (flicker, erosion damage, jagged edges, wrong duration, a tool/quantizer tradeoff) — this
  skill's development history is long and specific, and re-deriving a fix from scratch risks
  retrying an approach already known to regress.
- **Verify with real numbers, not a glance** — `--analyze`'s actual fields, real pixel/duration
  reads, the real interior mask (not a bounding-box approximation) — before claiming something is
  right or fixed.
- **Test the naive/simpler option end-to-end on real content before a bigger algorithm rebuild.**
- **Be usage-conscious**: batch tool calls, don't re-read what's already in context, and don't
  spin up a heavyweight session for one small edit or one GIF. Long, continuous single-workspace
  sessions across real GIF jobs are the actual preference here (so lessons accumulate with full
  context) — usage-consciousness is what makes that affordable, not shorter sessions.
- **Proactively recommend a model/effort level** when the task calls for a different fit than
  what's currently running — one clear recommendation, not a range, given *before* starting the
  work. If part of a batch is a poor fit for the session's setup, recommend deferring it to its
  own session rather than switching models mid-flow (a mid-session switch reprocesses the whole
  conversation at full price, no cache carryover).
- **Mark chat chapters at real phase shifts** (setup → a specific GIF job → a bug investigation →
  a version bump), not every message.

## Validation status
**Validated in practice on 2026-08-07** — the first real GIF jobs since the 2026-07-14/16 setup
session. Three 640x640 white-background gem icons (`ruby`, `jewelry`, `gemstone`) were processed
end to end with the v3.1.0 drop's script and accepted by Harkirat. What that exercised:
`--protect-outline-color` enclosure verified per-frame across an overlapping-elements animation,
`--erosion-exempt-max-size` on small isolated removed regions, and `--dither-mode none` on
art with a fade baked in against the background. Two real findings came out of it —
`references/lessons.md` §12 and §13.

**A version bump and a GitHub push are still NOT the same thing as syncing to the live claude.ai
skill.** The repo can be versioned/pushed as the real, current state of the code without that
implying it's been redistributed to claude.ai (Harkirat's explicit call, 2026-07-16). The repo→live
sync is a separate, manual upload step — see "Live skill sync workflow" above, and note the
sandbox-boundary section there for why the packaged files are the only thing a live session sees.
