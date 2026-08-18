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
import re, os, sys, subprocess

SK, LE, SC = 'SKILL.md', 'references/lessons.md', 'scripts/remove_gif_background.py'
REFS = ['references/lessons.md', 'references/version-history.md',
        'references/compression.md', 'references/flag-reference.md']

def flagset(t):
    return set(re.findall(r'`(--[a-z0-9-]+)', t))          # tolerate `--flag arg` form

def main():
    sk, le, sc = open(SK).read(), open(LE).read(), open(SC).read()
    fails = []

    # Ground truth is the REAL CLI, not the source text. Reading add_argument() calls checks a
    # SIGNATURE; running --help checks BEHAVIOUR, which is gate 5's own rule turned on this gate.
    # A conditionally-registered or shadowed flag would pass the source check and fail for a user.
    try:
        _h = subprocess.run([sys.executable, SC, '--help'], capture_output=True, text=True, timeout=60).stdout
        real = set(re.findall(r'(--[a-z0-9-]+)', _h)) & set(re.findall(r"add_argument\('(--[a-z0-9-]+)'", sc))
    except Exception as e:
        fails.append(f'could not run {SC} --help to enumerate real flags: {e}')
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

    # 6. the frontmatter description must claim the skill's PRIMARY function and every
    # format it supports on BOTH sides. Two real defects motivated this, found by Harkirat
    # within minutes of each other: the description named GIF as the input NINE times while
    # the reader is format-agnostic and a WebP source had been processed that same session;
    # and an earlier audit of this very string built its checklist from the NEW capabilities
    # and never tested "remove the background", the skill's whole purpose. A checklist that
    # omits the primary case manufactures confidence -- so the primary case is asserted here.
    desc = re.search(r'^description: (.+)$', sk, re.M)
    if not desc:
        fails.append('SKILL.md has no frontmatter description -- the skill cannot trigger')
    else:
        # HARD PLATFORM LIMIT, learned the expensive way: claude.ai refuses the upload with
        # "field 'description' in SKILL.md must be at most 1024 characters". Nothing local knew
        # this, so the description grew to 1364 while every gate passed -- the failure surfaced
        # only in Harkirat's browser, after a merge, a tag and a package build. Gate the
        # CONSTRAINT, not just the content.
        _raw = desc.group(1)
        if len(_raw) > 1024:
            fails.append(f'description is {len(_raw)} chars; claude.ai rejects anything over 1024')
        d = _raw.lower()
        if not re.search(r'remove\b.{0,20}\bbackground|background removal', d):
            fails.append('description never states the PRIMARY function (removing a background)')
        for fmt in ('gif', 'webp', 'avif'):
            if fmt not in d:
                fails.append(f'description never mentions {fmt.upper()}, which the script supports')
        if 'animated image' not in d and 'gif, webp or avif' not in d:
            fails.append('description implies a single input format; the reader is format-agnostic')

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
