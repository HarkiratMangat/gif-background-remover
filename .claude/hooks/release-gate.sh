#!/bin/bash
# PreToolUse(Bash) — fires on release actions. NON-BLOCKING by design: Harkirat's standing
# preference is "a gate is better than advisory but i dont want it denying things."
#
# Every line below is a mistake actually made on 2026-08-17, not a hypothetical.
# Liveness tracer. A pipe-test proves the SCRIPT runs, never that the HOOK fires -- two hooks in
# the global config were dead for weeks while pipe-testing perfectly. To verify: delete this log,
# run any `git tag`/`git push`/`gh pr merge` command, then check the file exists.
echo "$(date +%FT%T) $CLAUDE_PROJECT_DIR" >> "${TMPDIR:-/tmp}/gif-repo-hook-trace.log" 2>/dev/null || true
CMD=$(jq -r '.tool_input.command // ""' 2>/dev/null)
[ -z "$CMD" ] && exit 0

MSG=""
case "$CMD" in
  *"gh pr merge"*|*"git push"*|*"git tag"*)
    MSG="RELEASE GATE — push, merge and tag are each ASKED, EVERY TIME; approval never carries over.
On 2026-08-17 one authorization (\"commit, push, pr, tag, and merge\") was treated as covering THREE
consecutive releases, two of them merged while Harkirat still had open questions. That produced
v5.1.0 and v5.1.1 where one release would have done.
  · Has Harkirat approved THIS action, in THIS turn? If not, stop and ask.
  · Batch audit findings into ONE release instead of merging then finding more.
Before tagging, gates 0-6 in CLAUDE.md must have RUN, not just been intended:
  0. python3 scripts/audit_docs.py            (flags reachable from the BODY, not the changelog)
  1. build the .skill and gate the BUILT artifact, and RE-gate every rebuild
  2. every references/*.md pointer resolves INSIDE the zip
  3. no private paths (/Users/, local/, .remember) and no pointers to unpackaged files
  4. reconcile the version entry against the commits (grep the CLAIM, not the paragraph)
  5. confirm BEHAVIOUR, not signatures (a changed default may be a sentinel)
  6. before trusting a checklist, confirm the PRIMARY case is on it"
    ;;
  *zip*skill*|*package_skill*)
    MSG="PACKAGING GATE — never run skill-creator's package_skill.py against this directory: it has no
gitignore awareness and would bundle .git, .remember and local/. Stage SKILL.md + references/ +
scripts/ only. Then gate the BUILT artifact, not the working tree — that is the only place
\"tracked but not packaged\" is visible; it caught a private path and four pointers to
gif-deferred-list.md on 2026-08-17, and one more on the REBUILD after the first gate passed."
    ;;
esac

[ -z "$MSG" ] && exit 0
jq -n --arg m "$MSG" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$m}}'
