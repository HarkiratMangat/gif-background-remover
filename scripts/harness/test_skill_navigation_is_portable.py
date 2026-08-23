"""The first executable instruction in SKILL.md must work in the DEPLOYMENT sandbox.

`rg` is not present on claude.ai. The recipe that used to be here was
`rg -n '^#{2,3} ' SKILL.md`, and a session that substituted `grep` got
**zero matches and exit 0** -- `#{2,3}` is ERE and plain `grep` is BRE, so it is
a literal string that matches nothing. Verified 2026-08-22: 0 under `grep`, 20
under `grep -E`.

A silent failure at the entry point of the whole skill is the worst possible
place for one, and it is invisible from this repo, where `rg` is installed.
"""
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
SKILL = os.path.join(ROOT, 'SKILL.md')


def _first_block():
    text = open(SKILL).read()
    m = re.search(r'```\n(.*?)```', text, re.S)
    assert m, 'SKILL.md has no navigation code block'
    return [ln for ln in m.group(1).splitlines()
            if ln.strip() and not ln.strip().startswith('#')]


def test_the_navigation_recipe_does_not_depend_on_ripgrep():
    for line in _first_block():
        assert not re.match(r'\s*rg\b', line), \
            f'the navigation recipe calls rg, which the claude.ai sandbox lacks: {line}'


def test_the_outline_command_actually_returns_an_outline_under_PLAIN_grep():
    """The real falsifier. A command that returns nothing and exits 0 passes any
    check that only looks at the exit status."""
    cmd = next((l for l in _first_block() if 'grep' in l), None)
    assert cmd, 'the navigation recipe has no grep command'
    # Strip only a TRAILING comment. Splitting on the first '#' breaks the command
    # itself, whose whole point is that it greps for '^##'.
    cmd = re.sub(r'\s{2,}#.*$', '', cmd).strip()
    r = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert len(lines) >= 10, \
        f'the outline command returned {len(lines)} lines under plain grep -- ' \
        f'this is the silent failure the recipe exists to avoid'
    assert all(re.match(r'^\d+:#{2,}', l) for l in lines), \
        'the outline command returned something that is not a heading list'


def test_the_ERE_form_is_the_one_that_fails_so_this_test_is_not_vacuous():
    """Proves plain grep really does treat #{2,3} as a literal. Without this the
    test above could be passing for an unrelated reason."""
    bad = subprocess.run(["grep", "-c", "^#{2,3} ", "SKILL.md"],
                         cwd=ROOT, capture_output=True, text=True)
    good = subprocess.run(["grep", "-cE", "^#{2,3} ", "SKILL.md"],
                          cwd=ROOT, capture_output=True, text=True)
    assert bad.stdout.strip() == '0', f'expected the BRE form to find nothing, got {bad.stdout!r}'
    assert int(good.stdout.strip()) > 10, good.stdout
