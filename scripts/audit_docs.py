#!/usr/bin/env python3
"""Gate the PACKAGED docs against the script. Run before any release.

Exists because the docs passed every structural check — no dangling refs, no orphaned sections,
correct defaults — while SIX flags, including `--auto` and `--auto-erosion`, appeared nowhere
except SKILL.md's version changelog. A changelog reads like documentation and is not: a session
looking for what to run reads the instructional body, and the body never mentioned them.

That is also a time bomb, because this repo's convention migrates old version entries into
references/version-history.md. When a version entry moves, anything documented only there stops
being documented at all.

Checks (all falsifiable, all cheap):
  1. every argparse flag appears in SKILL.md's BODY (after the version block) or in a packaged
     reference the body points at
  2. every §N / §N.M reference resolves to a real section
  3. every `references/*.md` pointer resolves to a file that exists
  4. every section is reachable from BOTH the table of contents and the symptom table
  5. no flag is documented that does not exist in argparse
"""
import re, os, sys

SK, LE, SC = 'SKILL.md', 'references/lessons.md', 'scripts/remove_gif_background.py'
REFS = ['references/lessons.md', 'references/version-history.md',
        'references/compression.md', 'references/flag-reference.md']

def flagset(t):
    return set(re.findall(r'`(--[a-z0-9-]+)', t))          # tolerate `--flag arg` form

def main():
    sk, le, sc = open(SK).read(), open(LE).read(), open(SC).read()
    fails = []

    real = set(re.findall(r"add_argument\('(--[a-z0-9-]+)'", sc))
    lines = sk.split('\n')
    body = '\n'.join(lines[next(i for i, l in enumerate(lines) if l.startswith('## ')):])
    # references the BODY points at are fair game for documenting a flag
    pointed = {r for r in REFS if os.path.basename(r) in body}
    documented = flagset(body) | set().union(*[flagset(open(r).read()) for r in pointed]) if pointed else flagset(body)
    missing = sorted(real - documented - {'--help'})
    if missing:
        fails.append(f"flags in argparse but NOT in SKILL.md's body or a pointed-to reference: {missing}")

    ghosts = sorted((flagset(sk) | flagset(le)) - real - {'--help', '--dither', '--lossy'})
    if ghosts:
        fails.append(f"flags documented that do not exist in argparse: {ghosts}")

    secs = {int(n) for n in re.findall(r'^## (\d+)\.', le, re.M)}
    subs = set(re.findall(r'^### (\d+\.\d+)', le, re.M))
    for f in [SK] + REFS:
        for a, b in re.findall(r'§(\d+)(?:\.(\d+))?', open(f).read()):
            if int(a) not in secs:
                fails.append(f'{f}: §{a} does not exist')
            elif b and f'{a}.{b}' not in subs:
                fails.append(f'{f}: §{a}.{b} does not exist')
        for r in set(re.findall(r'`(references/[a-z-]+\.md)`', open(f).read())):
            if not os.path.exists(r):
                fails.append(f'{f}: pointer to missing {r}')

    toc = {int(n) for n in re.findall(r'^(\d+)\. \[', le, re.M)}
    cov = set()
    for t in re.findall(r'^\| .+ \| (§[^|]+) \|$', le, re.M):
        cov |= {int(x) for x in re.findall(r'§(\d+)', t)}
    if secs - toc:
        fails.append(f'sections missing from the table of contents: {sorted(secs - toc)}')
    if secs - cov:
        fails.append(f'sections unreachable from the symptom table: {sorted(secs - cov)}')

    for f in fails:
        print('FAIL:', f)
    print(f"\n{len(fails)} failure(s)" if fails else "\nall doc gates pass")
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(main())
