# Skill version history

Per-version detail for `gif-background-remover`, moved out of `SKILL.md` on
2026-08-17 (v5.0.0) to keep that file within the progressive-disclosure size
convention — it had reached 896 lines, of which 241 were this log. SKILL.md
keeps the CURRENT version's entry and the versioning convention itself; every
earlier entry lives here.

Read this when you need to know what a past version changed or why a rule
exists at all; `references/lessons.md` has the deeper evidence trail behind
each one.

---

**v4.0.0** was a **major**
bump, judged holistically against everything accumulated since v3.2.0 (the
last real tag), not any single commit's own tier: five new `--analyze`
checks, `--recommend`, `--verify`, a full prose-compression pass, and now
one genuinely new capability — **`--remove-region`** (and
`--remove-region-feather`), the inverse of `--protect-region`: force-removes
a manually specified region regardless of what `--protect-outline-color`/
`--protect-region` already decided there. Ported and reconciled from an
independent claude.ai live-skill session that solved the same real job
(`military-tag.gif`) a genuinely different way — see `references/
lessons.md` §15 for the full case, including a real defringing bug that
session found and fixed (`apply_remove_regions()`'s recolor-before-taper
step), and an independent confirmation, found while reconciling this repo's
copy, that the flag's own static-mask caveat is load-bearing: a static
circle at the drop's own worked-example coordinates missed the true target
in 76% of frames on this tumbling asset, needing the geometric-gate
approach from §14 or external per-frame tracking instead. All additive and
opt-in; the default codepath is unchanged. The full detail of each step
along the way is preserved below rather than compressed into one entry,
since each one traces to a real, distinct finding:

**v3.3.3** (previous entry, kept for context) was a **correction**: a
second finding on the same `military-tag.gif` job, found by the user
zooming into the delivered file (`references/lessons.md` §14 addendum) --
`--erosion-exempt-max-size`, applied on `--recommend`'s generic small-region
evidence without checking it corresponded to genuine incidental noise in
the CHOSEN pipeline, skipped the normal edge-cleanup erosion on a punched
hole and left a faint off-white antialiasing fringe at its edge. Dropping
the flag (nothing genuine for it to protect here) let normal erosion clean
the fringe with only a modest, expected size increase, not runaway
inflation. No script or flag behavior changed.

**v3.3.2** (previous entry, kept for context) was a **correction**: one new
confirmed finding documented (`references/lessons.md` §14) from a real job
(`military-tag.gif`) — punching a small interior hole (a pinhole) while
protecting a same-colour, overlapping-size-range animated design element
(a twinkling star) is unreliable via `--keep-bg-blob-if-near`'s colour-
adjacency alone (an antialiased boundary can coincidentally match a keep
colour, and more dilation doesn't fix a match already found at low
dilation); `--hole-size-range`/`--hole-max-aspect`, verified across every
frame rather than sampled, is the robust discriminator when one blob is
physically constant and the other animates. Also notes a real
`--verify` `protected_region_coverage` false-positive on a legitimately
punched sub-hole within a translating candidate region (tracked in
`gif-deferred-list.md`, not fixed here). No script or flag behavior changed.

**v3.3.1** (previous entry, kept for context) was a **correction**: pure
prose compression against v3.3.0's own new fields, no behavior change. Every
manual-check
paragraph in "Animated/rotating content," the erosion-exempt and fade-detect
sections, and the Verification checklist that Phase 1 (v3.3.0) made
mechanically checkable now points at the actual `--analyze`/`--recommend`/
`--verify` field instead of re-describing how to do it by hand; genuinely
manual/visual checks and unverified-case fallbacks were left alone.
`candidate_regions`' `outline_enclosure_all_frames`/`outline_background_leak`
fields (shipped in v3.3.0, never documented) are now documented, and "Run the
real processing" now states the exact three-condition gate `--recommend`
already applies before trusting `outline_color_verified`. `references/
lessons.md` gained a symptom→section lookup table.

**v3.3.0** (previous entry, kept for context) was a **minor** bump:
`--analyze` gained five new checks (tumble/edge-grazing margin, all-frame
outline-color enclosure verification, outline-fill background-leak
detection, feather-band interior region detection covering both §10 Bug 4
and §12's signature, and a small removed-region size histogram), plus two
new modes — `--recommend` (runs `--analyze` and emits a ready-to-confirm
command line with evidence) and `--verify <input.gif> <output.gif>` (runs
the mechanical half of the Verification checklist below: leftover
background, protected-region coverage, edge fringe, small-region inflation,
duration/frame-count). All additive and opt-in; the default processing
codepath is unchanged (verified byte-identical against v3.2.0's output on
all three real fixtures used to build this). No existing flag's behavior
changed.

**v3.2.0** (previous entry, kept for context) was a **minor** bump: one
confirmed bug fix in the script
(the save message asserted a frame count it never read back — it restated the
frame list the script intended to write and claimed "durations preserved
exactly" without opening the output; on a real 170-frame job it reported 170
while the file held 168), now fixed by reading the written file back. Plus one
new confirmed finding documented: art with a fade baked in against the
background renders as a visible dither mesh, distinct from the flat-composite
speckle case §10 already covered. Full case histories: `references/lessons.md`
§12 and §13. No new flags — the fade case is handled by the existing
`--dither-mode none`.

**v3.2.0 is also the first version validated against real GIF jobs since the
skill was restructured** — three 640x640 gem icons processed end to end and
accepted 2026-08-07, exercising `--protect-outline-color` across an
overlapping-elements animation, `--erosion-exempt-max-size` on small isolated
removed regions, and `--dither-mode none` on baked-in fades. The v3.0.0 and
v3.1.0 entries below were live-session exports that had not been reconciled
into the repo before this version; both are folded in here.

v3.1.0 (previous entry, kept for context) was a **minor** bump: a single
confirmed bug fix (edge-cleanup erosion inflating small isolated removed
regions by 50-70x, discovered on a second animated-icon case that didn't even
need `--tumble-safe`), with a new `--erosion-exempt-max-size` flag. Full case
history: `references/lessons.md` §11. Doesn't touch the v3.0.0 tumble-safe
pathway or its flags.

v3.0.0 (previous entry, kept for context) was a **major** bump per the tier
definition below: a new, end-to-end-verified detection/protection pathway
for animated content whose foreground shape rotates or translates
significantly within the canvas (tumbling/falling/spinning icons) — four
separate, confirmed real bugs found and fixed in one delivery (fixed-position
regions breaking under tumble; border-touch background detection breaking
when the foreground grazes the canvas edge; single-frame outline enclosure
breaking under self-overlapping rotated geometry; allowlist-style feather
protection missing solid near-background design colors), plus a fifth
related finding (Bayer dithering reads as noise on flat/solid composite
backgrounds) and a new `--dither-mode none` option that came out of it. Full
case history: `references/lessons.md` §10. New flags: `--tumble-safe`,
`--keep-bg-blob-if-near`, `--hole-size-range`, `--hole-max-aspect`,
`--protect-band-only`, `--dither-mode`.

All flags added across both v3.0.0 and v3.1.0 are additive/opt-in —
confirmed the existing default codepath (no new flags) is byte-identical on
`--analyze` output against the pre-v3.0.0 script on the same test file, so
nothing already shipped should regress.
