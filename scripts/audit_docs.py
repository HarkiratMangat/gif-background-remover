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
  6. the frontmatter description states the primary function and every supported format
  7. the tracker agrees with itself: nothing closed sits in gif-deferred-list.md's Open
     section, nothing open sits in gif-resolved-list.md, every open item carries a
     [Priority · Effort · Model-effort] tag
  8. --diff <base> only: conservation -- an item removed from gif-deferred-list.md must be
     traceable into gif-resolved-list.md. A sweep and a deletion look identical in a diff.
"""
import re
import statistics, os, sys, subprocess

SK, LE, SC = 'SKILL.md', 'references/lessons.md', 'scripts/remove_gif_background.py'
REFS = ['references/lessons.md', 'references/version-history.md',
        'references/compression.md', 'references/flag-reference.md']

def flagset(t):
    return set(re.findall(r'`(--[a-z0-9-]+)', t))          # tolerate `--flag arg` form

def main():
    sk, le, sc = open(SK).read(), open(LE).read(), open(SC).read()
    fails = []
    fails += _self_test()
    fails = check_lessons_keywords(fails)
    fails = check_counted_claims(fails)

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

    # The SCRIPT's own evidence strings point at lessons sections too, spelled `SS<N>`
    # because they avoid the non-ASCII section sign. Those strings are USER-FACING output
    # and are the only documentation an autonomous run ever reads -- but they were never
    # scanned, so v5.3.0 shipped a recommendation citing `references/lessons.md SS25`
    # when no §25 existed (references/lessons.md §26.5). Gate them the same way.
    for a_, b_ in re.findall(r'SS(\d+)(?:\.(\d+))?', open(SC).read()):
        if int(a_) not in secs:
            fails.append(f'{SC}: SS{a_} (lessons §{a_}) does not exist')
        elif b_ and f'{a_}.{b_}' not in subs:
            fails.append(f'{SC}: SS{a_}.{b_} (lessons §{a_}.{b_}) does not exist')

    # A PACKAGED file must never point at a repo file that is not packaged. Only
    # SKILL.md, references/ and scripts/remove_gif_background.py go into the .skill,
    # so a backticked `gif-deferred-list.md` or `scripts/audit_docs.py` is an
    # instruction the claude.ai sandbox cannot follow. This has recurred twice --
    # four such pointers at v5.1.1, one more on the rebuild after the first gate
    # passed, and one again at v5.4.0 -- so it is gated rather than eyeballed.
    # `CLAUDE.md` is allowed: it appears only in the sandbox-boundary paragraphs
    # whose whole point is to name what a live session CANNOT reach.
    packaged = {SK, SC} | {os.path.join('references', f)
                           for f in os.listdir('references')}
    allowed_mentions = {'CLAUDE.md'}
    # ⚠️ A BARE FILENAME is just as unreachable as a path, and this check used to miss
    # every one of them: it tested `os.path.exists(t)`, which is relative to the repo
    # ROOT, so `audit_docs.py` and `render_baseline.py` (really at scripts/ and
    # scripts/harness/) resolved to nothing and passed. Both were sitting in
    # references/lessons.md, naming scripts the package does not contain, while this
    # gate reported clean. Same defect class as the closure-marker gate: matching the
    # SPELLING in front of you rather than the thing you mean.
    # os.path.dirname(__file__)/.. -- NOT '.'. A CWD-relative walk finds nothing when the
    # gate is invoked by absolute path from another directory, and this half then passes
    # VACUOUSLY: no basenames known, so no pointer can ever be flagged. The sibling paths
    # above are CWD-relative too, but those fail LOUDLY with file-not-found; a silent pass
    # is the shape that ships a defect.
    _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_basename = {}
    for dp, dn, fn in os.walk(_repo):
        dn[:] = [d for d in dn if d not in ('.git', 'local', '__pycache__', 'node_modules')]
        for fl in fn:
            repo_basename.setdefault(fl, os.path.relpath(os.path.join(dp, fl), _repo))
    packaged_basenames = {os.path.basename(x) for x in packaged}
    for f in sorted(packaged):
        for tok in sorted(set(re.findall(r'`([^`\n]{2,80})`', open(f).read()))):
            t = tok.strip().lstrip('./').split()[0].rstrip('.,:;')
            if t.endswith('/') or t in packaged or t in allowed_mentions:
                continue
            if not re.search(r'\.(md|py|json|sh|txt)$|/', t):
                continue
            if os.path.exists(t) or t.startswith(('local/', '.remember', '/Users/', '.claude/')):
                fails.append(f'{f}: points at `{t}`, which is NOT in the .skill package')
            elif ('/' not in t and t not in packaged_basenames
                  and t in repo_basename):
                fails.append(f'{f}: names `{t}` (really {repo_basename[t]}), which is a repo '
                             f'file NOT in the .skill package -- a bare filename is no more '
                             f'reachable from the sandbox than a path')

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

    fails += tracker_checks()
    if BASE:
        fails += conservation(BASE)

    for f in fails:
        print('FAIL:', f)
    for w in WARNINGS:
        print('WARN:', w)
    if fails:
        print(f"\n{len(fails)} failure(s)" + (f", {len(WARNINGS)} warning(s)" if WARNINGS else ""))
    else:
        print("\nall doc gates pass" + (f" ({len(WARNINGS)} warning(s) -- read them)" if WARNINGS else ""))
    return 1 if fails else 0

# ------------------------------ tracker gates ------------------------------
# gif-deferred-list.md is REPO-SIDE and never packaged, so these gates are about
# process hygiene rather than about the product. They exist because the tracker
# actively lied on 2026-08-18: three `###` headings read as open above bodies
# that said `✅ CLOSED`, one open item carried no priority tag, and the summary
# line on the AUTONOMY BACKLOG named an item as open directly above that item's
# own closure marker. Every one of those was found by hand, twice, in two days.
ACTIVE, ARCHIVE = 'gif-deferred-list.md', 'gif-resolved-list.md'
WARNINGS = []
# A standing section, not a work item -- it holds a numbered sub-list with its own
# open/closed state and is deliberately exempt from the priority-tag rule.
TAG_EXEMPT_HEADINGS = ('AUTONOMY BACKLOG',)
# ⚠️ The vocabulary is the whole gate. Dior's Builds' equivalent check shipped
# matching neither DONE nor DROPPED -- i.e. it missed the most common marker in
# its own corpus. Counted here 2026-08-18 across both files: CLOSED x17, DONE x4,
# SHIPPED x3, RESOLVED x2, FIXED x2, plus "CONFIRMED FIRING" as a one-off. A
# negation must NOT read as closure: "NOT DONE" and "not yet done" describe
# remaining scope, and the active list's own section heading contains one.
# ⚠️ The word boundary applies to the BARE keywords only. `✅` is not a word
# character, so a `\b` in front of the tick branch never matches after a space or
# a newline -- which is every real occurrence of it. Caught by the falsifier suite.
_CLOSED_WORD = re.compile(r'(?<!NOT )(?<!not )(?<!not yet )'
                          r'(?:\b(?:CLOSED|SHIPPED|RESOLVED)\b'
                          r'|✅\s*\*{0,2}(?:DONE|FIXED|CONFIRMED)\b)')
# ⚠️ TWO defects this vocabulary had, both found 2026-08-18 and both the same
# shape -- the gate matched the WORD rather than the MARKER:
#   * no word boundary, so `ENCLOSED` matched `CLOSED`. In a repo whose main
#     feature is outline ENCLOSURE and whose house style emphasises in caps,
#     that is a spurious failure waiting on the next open item that mentions it.
#   * no position test, so ordinary bolded prose tripped it. Writing the tracker
#     item ABOUT this defect failed the gate twice: once on a sentence using a
#     keyword as an adjective, and again on the sentence that quoted the keyword
#     list. A gate whose own bug report cannot be written is over-broad.
# The fix is NOT to shorten the vocabulary -- that is the failure Dior's Builds'
# equivalent shipped, missing the most common marker in its own corpus. Counted
# here across both files: CLOSED x17, DONE x4, SHIPPED x3, RESOLVED x2, FIXED x2,
# plus "CONFIRMED FIRING" once. Every real one of them sits at the START of a
# bold span or a line, separated from it by nothing but emoji, punctuation and
# ALL-CAPS qualifiers ("**CLOSED 2026-08-18", "✅ **FIXED,", "⚠️ **PARTIALLY
# FIXED"). Prose never does: "the SHIPPED 16-colour floor" has lowercase words
# between the emphasis and the keyword. That is the discriminator below, and it
# is a margin of KIND rather than a tuned distance -- an earlier draft used "the
# keyword must fall within N characters of the bold open", which separates the
# real cases from the false one at N=12 and is exactly the kind of number this
# project keeps having to un-tune.
_MARKERISH = re.compile(r'^[\s*~\-—→#•\d.)\]]*(?:[A-Z]{2,}[\s\-]+)*$')


def _at_marker_position(body, idx):
    """Is the match at `idx` a closure MARKER, or just the word used in prose?"""
    line_start = body.rfind('\n', 0, idx) + 1
    line = body[line_start:idx]
    # everything after the last bold-open on this line, or the whole line so far
    lead = line.rsplit('**', 1)[-1] if '**' in line else line
    lead = ''.join(c for c in lead if c.isascii() or c.isspace())   # drop emoji
    return bool(_MARKERISH.match(lead))


class CLOSED_MARK:
    """Drop-in for the old compiled pattern: `.search(body)` -> match or None."""

    @staticmethod
    def finditer(body):
        """Every marker-position match, so a caller that needs to COUNT them has one."""
        return (m for m in _CLOSED_WORD.finditer(body)
                if _at_marker_position(body, m.start()))

    @staticmethod
    def search(body):
        return next(CLOSED_MARK.finditer(body), None)


# The gate's own falsifier suite, run on EVERY invocation rather than kept in a
# scratch file. Both defects above were introduced by someone (me) reasoning about
# what the pattern ought to do; each case below is one that actually happened or
# actually would have. Eleven string matches cost nothing, and a check that proves
# itself every run is a control -- a check that was proven once is a memory.
_MARK_CASES = [
    ("**CLOSED 2026-08-18 (v5.5.0)**", True, 'bold closure marker'),
    ("\u2705 **FIXED, and the option needed correcting**", True, 'tick + bold FIXED'),
    ("\u2014 **RESOLVED 2026-08-17.** blah", True, 'dash + bold RESOLVED'),
    ("**\u2705 CLOSED 2026-08-18**", True, 'bold wrapping the tick'),
    ("\u2705 **DONE 2026-08-18**", True, 'tick + DONE'),
    ("\u26a0\ufe0f **PARTIALLY FIXED 2026-08-18**", False,
     'partially fixed is still OPEN, and the pre-2026-08-18 gate agreed'),
    ("**That reaches the SHIPPED 16-colour floor too**", False,
     'keyword used as an adjective inside bolded prose'),
    ("The gate fails a body containing `CLOSED|SHIPPED|RESOLVED` anywhere", False,
     'the keyword list quoted in prose -- writing this gate\'s own bug report'),
    ("no colour ENCLOSED this design region on a single frame", False,
     'ENCLOSED contains CLOSED, and this repo is about enclosure'),
    ("**NOT DONE yet**, and here is why", False, 'negation must not read as closure'),
    ("We have not yet RESOLVED the question", False, 'negated prose'),
]


def check_counted_claims(fails):
    """The lessons size claim and README's flag coverage, checked instead of remembered.

    ⚠️ The size claim has now rotted THREE times -- "~32k" while the file was 46k,
    "~63,000" while it was 66k, and "~66,000" within the same session that derived it,
    because sections were added afterwards. It is quoted in three places and it is the
    number a session uses to decide whether it can afford to read the file, so being
    wrong by 5% is worse than saying nothing. Re-deriving it by hand is a discipline,
    and this repo's own rule is that a discipline is not a control.

    README is not packaged, but it is the front door on GitHub and it had drifted two
    releases behind -- 42 of 47 flags, missing the whole translucency group and both
    source-alpha flags.
    """
    text = open(LE).read()
    secs = [x for x in re.split(r'(?m)^## ', text)[1:] if re.match(r'^\d+\.', x)]
    tok = len(text) // 4
    m = re.search(r'It is ~([\d,]+) tokens across (\d+) sections\.'
                  r' The median section is ~(\d+) and the largest ~(\d+)\.', text)
    if not m:
        fails.append(f'{LE}: the "How to read this file" block no longer states its size -- '
                     f'that claim is how a session decides whether it can afford this file')
    else:
        claimed_tok = int(m.group(1).replace(',', ''))
        sizes = sorted(len(x) // 4 for x in secs)
        real = {'tokens': tok, 'sections': len(secs),
                'median': int(statistics.median(sizes)), 'largest': max(sizes)}
        got = {'tokens': claimed_tok, 'sections': int(m.group(2)),
               'median': int(m.group(3)), 'largest': int(m.group(4))}
        # tokens are quoted to the nearest thousand; everything else is exact
        if abs(real['tokens'] - got['tokens']) > 1000:
            fails.append(f'{LE}: claims ~{got["tokens"]:,} tokens, actually ~{real["tokens"]:,} '
                         f'-- re-derive it (wc -c / 4), do not nudge it')
        for k in ('sections', 'median', 'largest'):
            if real[k] != got[k]:
                fails.append(f'{LE}: claims {k}={got[k]}, actually {real[k]}')
        for f in (SK, 'CLAUDE.md'):
            if os.path.exists(f):
                for n in re.findall(r'~(\d+)k tokens|~([\d,]+) tokens', open(f).read()):
                    v = int((n[0] or n[1]).replace(',', '')) * (1000 if n[0] else 1)
                    # >= 10k only: the same sentence also quotes the MEDIAN section size,
                    # and a gate that flags its own neighbouring figure teaches people to
                    # ignore it. Caught by this check firing on itself.
                    if v >= 10000 and abs(v - real['tokens']) > 1000:
                        fails.append(f'{f}: quotes the lessons size as ~{v:,} tokens, '
                                     f'actually ~{real["tokens"]:,}')
    if os.path.exists('README.md'):
        flags = set(re.findall(r"p\.add_argument\('(--[a-z0-9-]+)'", open(SC).read()))
        named = set(re.findall(r'(--[a-z0-9-]+)', open('README.md').read()))
        missing = sorted(flags - named)
        if missing:
            fails.append(f'README.md: does not name {len(missing)} of {len(flags)} flags '
                         f'-- {missing[:6]}{"..." if len(missing) > 6 else ""}')
    return fails


def check_lessons_keywords(fails):
    """Every numbered lessons section carries an 'Also searched as:' line, and no
    phrase on it merely repeats vocabulary its own section already contains.

    The second half is the whole point. `rg` already searches the body, so a tag
    that duplicates a word in the section is dead weight; the index earns its bytes
    only by covering vocabulary the section does NOT use. Measured 2026-08-19: of 60
    plausible search terms, 18 returned nothing from this file -- jaggies, banding,
    ghosting, posterise, quantise, tilemap, atlas, nearest-neighbor, bilinear,
    premultiplied, sub-pixel, anti-alias, frame rate among them.

    Gated rather than trusted because this repo has been bitten twice by
    unmaintained metadata: the symptom table once had 6 of 25 sections unreachable,
    and the lessons size claim has now rotted twice.
    """
    text = open(LE).read()
    parts = re.split(r'(?m)^(?=## \d+\. )', text)[1:]
    for sec in parts:
        num = re.match(r'## (\d+)\.', sec).group(1)
        m = re.search(r'(?m)^\*\*Also searched as:\*\* (.+)$', sec)
        if not m:
            fails.append(f'{LE}: §{num} has no "Also searched as:" line -- a section nobody '
                         f'can find by synonym is a section nobody has')
            continue
        body = sec.replace(m.group(0), '').lower()
        dead = [t.strip() for t in m.group(1).split('·') if t.strip().lower() in body]
        if dead:
            fails.append(f'{LE}: §{num} tags {dead} which its own text already contains -- '
                         f'`rg` finds those already, so the tag is dead weight')
    return fails


def _self_test():
    bad = [why for body, want, why in _MARK_CASES
           if (CLOSED_MARK.search('x\n\n' + body + '\n') is not None) != want]
    return [f'audit_docs.py: the closure-marker gate FAILS ITS OWN falsifier suite '
            f'({len(bad)} of {len(_MARK_CASES)}): {bad}'] if bad else []


def _items(text):
    """[(heading, body)] for every ### block, in order."""
    parts = re.split(r'(?m)^### ', text)[1:]
    return [(p.split('\n')[0], p) for p in parts]


def _sections(text):
    """{'## heading': text} preserving order."""
    out, cur = {}, None
    for line in text.split('\n'):
        if line.startswith('## '):
            cur = line
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: '\n'.join(v) for k, v in out.items()}


def tracker_checks():
    fails = []
    if not (os.path.exists(ACTIVE) and os.path.exists(ARCHIVE)):
        return [f'{ACTIVE} or {ARCHIVE} is missing -- the split tracker needs both halves']
    act, arc = open(ACTIVE).read(), open(ARCHIVE).read()
    secs = _sections(act)
    open_sec = next((v for k, v in secs.items() if 'Open' in k), None)
    if open_sec is None:
        fails.append(f'{ACTIVE} has no "Open" section heading')
        open_sec = ''
    for head, body in _items(open_sec):
        if head.startswith('~~'):
            fails.append(f'{ACTIVE}: "{head[:70]}" is struck through but still filed under Open -- '
                         f'move it to {ARCHIVE}')
            continue
        m = CLOSED_MARK.search(body)
        if m:
            fails.append(f'{ACTIVE}: "{head[:60]}" reads as OPEN but its body says {m.group(0)!r} '
                         f'-- heading/body drift, the exact defect this gate exists for')
        if not re.search(r'\[P\d', head) and not any(x in head for x in TAG_EXEMPT_HEADINGS):
            fails.append(f'{ACTIVE}: "{head[:70]}" carries no [Priority · Effort · Model-effort] tag')
    # the inverse spelling: an OPEN item filed in the archive is silently lost work
    for head, body in _items(arc):
        if not head.startswith('~~') and not CLOSED_MARK.search(body):
            fails.append(f'{ARCHIVE}: "{head[:70]}" is neither struck through nor marked closed -- '
                         f'an open item in the archive is work nobody will find')
    return fails


# --------------------------- archive conservation --------------------------
# Ported from Dior's Builds' docs-audit.mjs `archive-conservation`, keeping the
# three corrections that check learned the hard way: a unified diff renders an
# EDIT as a removal plus an addition, a markdown heading is structure and never
# an item, and BOTH the fingerprint window and the haystack must be normalised
# the same way or nothing can ever match.
def _words(sx):
    return [w for w in re.sub(r'[^a-z0-9]+', ' ', sx.lower()).split() if len(w) > 2]


def _fp_in(line, haystack_words, n=6):
    w = _words(line)
    if len(w) < n:
        return True                       # too short to fingerprint; do not guess
    hay = ' '.join(haystack_words)
    return any(' '.join(w[i:i + n]) in hay for i in range(len(w) - n + 1))


def conservation(base):
    def git(*a):
        return subprocess.run(['git'] + list(a), capture_output=True, text=True).stdout
    diff = git('diff', '--unified=0', f'{base}...HEAD', '--', ACTIVE)
    if not diff:
        return []
    minus = [l[1:].strip() for l in diff.split('\n') if l.startswith('-') and not l.startswith('---')]
    plus = [l[1:].strip() for l in diff.split('\n') if l.startswith('+') and not l.startswith('+++')]
    plus_words = _words(' '.join(plus))
    removed = [l for l in minus
               if not re.match(r'^#{1,6}\s', l)      # a heading is structure, not an item
               and len(l) > 40                        # ignore rewrap/whitespace churn
               and not _fp_in(l, plus_words)]         # an in-place edit is not a removal
    if not removed:
        return []
    arc_diff = git('diff', '--unified=0', f'{base}...HEAD', '--', ARCHIVE)
    added = [l[1:] for l in arc_diff.split('\n') if l.startswith('+') and not l.startswith('+++')]
    if not added:
        return [f'this branch removes {len(removed)} substantive line(s) from {ACTIVE} and adds '
                f'NOTHING to {ARCHIVE}. An item leaves the active list only by being resolved into '
                f'the archive -- otherwise the tidy-up silently DELETED it. First: "{removed[0][:90]}…"']
    arc_words = _words(' '.join(added))
    orphans = [l for l in removed if not _fp_in(l, arc_words)]
    if orphans and len(orphans) == len(removed):
        return [f'this branch removes {len(removed)} item(s) from {ACTIVE} and DOES add to {ARCHIVE}, '
                f'but none of the removed text can be traced into it. That is a deletion wearing a '
                f'sweep\'s clothes. First untraceable: "{orphans[0][:90]}…"']
    if orphans:
        # ADVISORY, deliberately. Measured on this gate's own first real run: the
        # 12-item split tripped it once, on a summary line that was REWRITTEN
        # rather than moved (its replacement shares no six-word window with it, so
        # the in-place-edit pairing cannot see it). That is a true positive worth
        # printing and a bad reason to fail a branch -- the same false-positive
        # class Dior's Builds hit when a rename read as a deletion. Hard failure
        # is reserved for "nothing was archived" and "nothing traces at all",
        # both of which are proven to still fire.
        WARNINGS.append(f'{len(orphans)} of {len(removed)} line(s) removed from {ACTIVE} could not be '
                        f'traced into {ARCHIVE}. Rewording during a sweep is normal, so confirm each '
                        f'landed. First: "{orphans[0][:90]}…"')
    return []


BASE = None
if __name__ == '__main__':
    if '--diff' in sys.argv:
        BASE = sys.argv[sys.argv.index('--diff') + 1]
    sys.exit(main())
