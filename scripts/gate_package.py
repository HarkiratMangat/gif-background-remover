#!/usr/bin/env python3
"""Gate a BUILT .skill package -- release gates 1-3 and 6, on the artifact that ships.

⚠️ THE WORKING TREE IS NOT THE PACKAGE, and that is the entire reason this exists.
"tracked but not packaged" is invisible from the repo: `scripts/harness/`,
`gif-deferred-list.md`, `docs/` and `README.md` are all real files here and none of them
reach the claude.ai sandbox. Every leak this repo has shipped was visible only in the zip.

`audit_docs.py` gates the SOURCES; this gates the ARTIFACT. Run both, and re-run this on
every REBUILD -- on 2026-08-17 the rebuild after a passing gate carried one more leak.

    python3 scripts/gate_package.py local/gif-background-remover-vX.Y.Z.skill
"""
import os
import re
import sys
import tempfile
import zipfile

#: Repo directories whose contents never enter the package. A pointer into one of these is
#: an instruction the sandbox cannot follow, however correct it is on this machine.
UNPACKAGED_DIRS = ('local/', 'docs/', 'scripts/harness/', '.remember', '.claude/',
                   '/Users/', 'others/')
#: How a home directory can be spelled. ⚠️ `~/` was missing from this list until 2026-08-18
#: and a real leak shipped because of it -- a gate that greps for /Users/ cannot see a tilde.
#: When adding a private-path check, enumerate the SPELLINGS, not the one in front of you.
PRIVATE = [r'/Users/', r'(?<![\w`/])~/', r'(?<![\w./-])local/', r'\.remember']
#: The skill's PRIMARY purpose. A checklist that omits the primary case manufactures
#: confidence -- an earlier audit of the description built its terms from the NEW features
#: and never tested this one.
PRIMARY = ['remove the background', 'transparent']


def gate(pkg_path):
    fails = []
    with tempfile.TemporaryDirectory() as d:
        with zipfile.ZipFile(pkg_path) as z:
            z.extractall(d)
        roots = [os.path.join(d, x) for x in os.listdir(d)
                 if os.path.isdir(os.path.join(d, x))]
        if len(roots) != 1:
            return [f'expected exactly one top-level directory in the package, got {roots}']
        root = roots[0]
        files = [os.path.join(dp, f) for dp, _, fn in os.walk(root) for f in fn]
        rel = {os.path.relpath(f, root) for f in files}
        print(f'{len(files)} files: {", ".join(sorted(rel))}')

        for f in files:
            body = open(f, encoding='utf-8', errors='replace').read()
            name = os.path.relpath(f, root)
            for pat in PRIVATE:
                for m in re.finditer(pat, body):
                    ln = body[:m.start()].count('\n') + 1
                    fails.append(f'PRIVATE PATH {name}:{ln} [{pat}] '
                                 f'{body.splitlines()[ln - 1][:120]}')
            # Backticked AND bare tokens -- a Python docstring uses no backticks, and that
            # is where the 2026-08-23 leak lived.
            toks = set(re.findall(r'`([^`\n]{2,80})`', body))
            toks |= set(re.findall(
                r'(?<![`\w/.-])([\w][\w./-]{1,79}\.(?:md|py|json|sh|txt))\b', body))
            for tok in sorted(toks):
                t = tok.strip().lstrip('./').split()[0].rstrip('.,:;')
                # A bare DIRECTORY name is prose, not an instruction to open something --
                # `references/` and `others/` are how provenance describes where a corpus
                # lives. audit_docs.py skips these deliberately; matching it keeps the two
                # gates from disagreeing about what counts as a pointer.
                if t.endswith('/'):
                    continue
                if t.startswith(UNPACKAGED_DIRS):
                    fails.append(f'UNREACHABLE POINTER {name} -> {t}')
                if t.startswith('references/') and t not in rel:
                    fails.append(f'BROKEN POINTER {name} -> {t} (not in the zip)')

        skill = os.path.join(root, 'SKILL.md')
        if not os.path.exists(skill):
            fails.append('SKILL.md is not in the package')
        else:
            body = open(skill, encoding='utf-8').read().lower()
            for term in PRIMARY:
                if term not in body:
                    fails.append(f'PRIMARY CASE missing from SKILL.md: {term!r}')
    return fails


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    bad = gate(sys.argv[1])
    if bad:
        print(f'\n{len(bad)} FAILURE(S):')
        for x in sorted(set(bad)):
            print('  ' + x)
        sys.exit(1)
    print('built-artifact gates PASS (private paths, unreachable pointers, '
          'references resolve, primary case present)')
