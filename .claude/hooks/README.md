# Repo hooks — INSTALLED BUT UNVERIFIED

Registered in `.claude/settings.json`; built 2026-08-17 from mistakes actually made that session.

## ⚠️ Verification status: NOT CONFIRMED FIRING

Project-level `.claude/settings.json` hooks did **not** activate in the session that created them. Proved rather than assumed: a filesystem tracer was added to `release-gate.sh`, a matching command (`git tag --list`) was run, and the trace file was never created — so the hook process never ran at all, as opposed to running and having its output discarded.

They most likely load at session start. **Verify in a fresh session, and do not trust them until you have:**

```
rm -f "${TMPDIR:-/tmp}/gif-repo-hook-trace.log"
git tag --list                                        # any command matching the release patterns
cat "${TMPDIR:-/tmp}/gif-repo-hook-trace.log"         # must exist, with a timestamp
```

A pipe-test (`echo '{...}' | bash hook.sh`) proves only that the SCRIPT works. Two hooks in the global config were dead for weeks while pipe-testing perfectly, because a hook emitting `hookSpecificOutput` without `hookEventName` is discarded silently. Both hooks here emit `hookEventName`.

## What each one is for

| hook | event | fires on |
|---|---|---|
| `release-gate.sh` | PreToolUse(Bash) | `git push`, `git tag`, `gh pr merge` → the ask-every-time rule and release gates 0–6; packaging commands → stage a clean tree and gate the BUILT artifact |
| `md-softwrap-check.sh` | PostToolUse(Write/Edit) | a `.md` file with 5+ mid-sentence line breaks → the soft-wrap convention, with the reflow command |

Both are **non-blocking** by design — Harkirat's standing preference is *"a gate is better than advisory but i dont want it denying things."* They emit `additionalContext`, which reaches Claude; a `systemMessage` would reach only Harkirat and change nothing.
