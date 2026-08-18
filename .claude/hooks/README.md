# Repo hooks — INSTALLED BUT UNVERIFIED

Registered in `.claude/settings.json`; built 2026-08-17 from mistakes actually made that session.

## ⚠️ Verification status: NOT CONFIRMED FIRING

Project-level `.claude/settings.json` hooks did **not** activate in the session that created them. Proved rather than assumed: a filesystem tracer was added to `release-gate.sh`, a matching command (`git tag --list`) was run, and the trace file was never created — so the hook process never ran at all, as opposed to running and having its output discarded.

**The cause is NOT known, and one plausible-sounding explanation is already disproven.** "Project settings load at session start" is FALSE — Dior's Builds proved live that editing `settings.json` IS picked up mid-session (`reference_enforcement_hooks` memory: *"the 'settings watcher ignores mid-side edits' claim is false, disproven live"*). Do not repeat that theory.

What IS established, by test rather than inference:
- both hooks are silent — neither the PreToolUse(Bash) one on a matching `git tag` command, nor the PostToolUse one on a `Write` to a hard-wrapped `.md`;
- the hook PROCESS never runs (a filesystem tracer never appears), so this is not the `hookEventName` discard bug — both scripts do emit it;
- `settings.json` is valid JSON, the scripts are executable, and both produce correct output when piped input directly;
- there is no competing `settings.local.json`.

**Compared against Dior's Builds' demonstrably-working config; the structure is not the problem.** Same shape (`hooks` → event → optional `matcher` → `hooks[]` → `{type, command, timeout}`), same invocation form (`bash "${CLAUDE_PROJECT_DIR:-<abs>}/.claude/hooks/x.sh"`), same tracked location, not gitignored. `timeout` was the only delta and adding it changed nothing. The `permissions` key Dior's Builds also carries is unrelated to hooks.

**The one hypothesis consistent with every observation: a `settings.json` that did not EXIST at session start is not discovered mid-session.** This is NOT the claim that was disproven — that one was about *edits to an existing file* being picked up, which they are. Creation is a different event and was never tested.

⚠️ It remains a HYPOTHESIS. The only way to settle it is a fresh session; do that before trusting these hooks.

**Verify before trusting them:**

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
