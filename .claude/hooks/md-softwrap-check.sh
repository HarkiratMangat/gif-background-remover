#!/bin/bash
# PostToolUse(Write|Edit) — markdown in this repo is SOFT-wrapped (one line per paragraph).
# Fires because the rule was broken by the very session that established it: memory files were
# hand-wrapped while the soft-wrap migration was running. Harkirat caught it, not a gate.
F=$(jq -r '.tool_input.file_path // ""' 2>/dev/null)
case "$F" in *.md) ;; *) exit 0 ;; esac
[ -f "$F" ] || exit 0

# count prose lines that break mid-sentence: the signature of hard wrapping
N=$(awk '
  /^```/ {f=!f; next} f {next}
  /^[[:space:]]*$/ {prev=""; next}
  /^[|#>]/ {prev=""; next}
  { if (prev != "" && prev !~ /[.:!?]$/ && $0 !~ /^[-*|#>]/) c++; prev=$0 }
  END {print c+0}' "$F")
[ "${N:-0}" -lt 5 ] && exit 0

jq -n --arg f "$F" --arg n "$N" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:
("SOFT-WRAP: " + $f + " has " + $n + " prose lines breaking mid-sentence — the signature of hard wrapping. This repo soft-wraps markdown (one physical line per paragraph) because measured 2026-08-17, 75.5% of prose lines broke mid-sentence and rg could not match most multi-word phrases. Memory files count. Fix with:\n  node \"/Applications/Claude Code/Diors-Builds/scripts/reflow-prose.mjs\" --check " + $f + "   # then --write")}}'
