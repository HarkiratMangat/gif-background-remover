"""Falsifiers for --recommend emitting a mutually exclusive flag pair (plan Task 11).

Measured 2026-08-22 on broadcast.gif, --recommend returned:

    --protect-outline-color 002864 --recover-fade-alpha --erosion-exempt-transient

and running that exact command prints a WARNING that --recover-fade-alpha takes
its own render path and is IGNORING the protection -- not weakening it, ignoring
it. The exclusivity is real and long documented (SS34.4); the recommender did
not know about it. An autonomous run pastes suggested_command verbatim and
learns about the conflict only at render time, after committing to the render.

⛔ Protection wins the conflict. A protected region usually comes from an
explicit user instruction; a fade is inferred by the tool. Losing an instruction
is worse than losing an improvement.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
BROADCAST = os.path.join(ROOT, 'local/2026-08-22-fade-edge-cases/inputs/broadcast.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

CONFLICTS = [({'--recover-fade-alpha'},
              {'--protect-outline-color', '--protect-region', '--protect-band-only'})]

needs = pytest.mark.skipif(not (os.path.exists(BROADCAST) and os.path.exists(SECURE)),
                           reason='the trial inputs are gitignored third-party assets')


def _suggested(path):
    r = subprocess.run([sys.executable, SCRIPT, path, '--recommend'],
                       capture_output=True, text=True, timeout=1800)
    assert r.returncode == 0, r.stderr[-3000:]
    # A SINGLE input prints a bare recommendation object; several print a list of
    # per-file records. Neither index('[') nor rindex(']') is safe -- the document is
    # full of nested arrays -- so decode from the first brace and branch on the shape.
    start = min(i for i in (r.stdout.find('{'), r.stdout.find('[')) if i >= 0)
    doc, _ = json.JSONDecoder().raw_decode(r.stdout[start:])
    return doc[0]['recommendation'] if isinstance(doc, list) else doc


@needs
def test_broadcast_does_not_recommend_an_exclusive_pair():
    cmd = _suggested(BROADCAST)['suggested_command'] or ''
    for left, right in CONFLICTS:
        if any(f in cmd for f in left):
            assert not any(f in cmd for f in right), \
                f'suggested_command pairs {left} with {right}: {cmd}'


@needs
def test_the_conflict_is_EXPLAINED_not_just_dropped():
    """Silently dropping one flag would pass the test above and lose information."""
    rec = _suggested(BROADCAST)
    blob = (' '.join(rec.get('evidence', [])) + str(rec.get('not_applicable_reason'))).lower()
    assert 'fade' in blob and 'protect' in blob, \
        'the recommendation dropped a flag without saying which tradeoff was taken'
    assert '34.4' in blob or 'exclusive' in blob or 'pick one' in blob


@needs
def test_the_dropped_flag_is_still_reachable():
    """What STAYED: the user must be told how to take the other side of the tradeoff."""
    blob = ' '.join(_suggested(BROADCAST).get('evidence', [])).lower()
    assert 'recover-fade-alpha' in blob and 'drop' in blob


@needs
def test_an_asset_with_no_conflict_is_unaffected():
    """secure.gif needs protection and no fade -- its command must not change."""
    assert '--protect-outline-color 002864' in (_suggested(SECURE)['suggested_command'] or '')


def test_the_renderer_and_the_recommender_read_ONE_declaration():
    """A guard keyed on a duplicated list is disarmed the day one copy is edited."""
    sys.path.insert(0, os.path.join(HERE, '..'))
    import remove_gif_background as R
    flags = {f for f, _d in R.FADE_EXCLUSIVE_FLAGS}
    assert '--protect-outline-color' in flags and '--protect-region' in flags
    src = open(SCRIPT).read()
    assert src.count("('--protect-band-only', 'protect_band_only')") == 1, \
        'the exclusivity list has been duplicated; the two copies can now drift'


@needs
def test_the_fade_alternative_is_PUBLISHED_complete_and_runnable():
    """What STAYED, and the reason this is not a suppression.

    Dropping --recover-fade-alpha and saying nothing else would suppress it on every asset
    that also wants protection -- most faded assets in this corpus. The other side of the
    tradeoff is published as a complete command, and NEITHER field may hold a pair the
    renderer refuses to honour.
    """
    rec = _suggested(BROADCAST)
    alt = rec.get('alternative_command')
    assert alt and '--recover-fade-alpha' in alt, f'the fade option was discarded: {alt}'
    sys.path.insert(0, os.path.join(HERE, '..'))
    import remove_gif_background as R
    for flag, _dest in R.FADE_EXCLUSIVE_FLAGS:
        assert flag not in alt, f'alternative_command still pairs {flag} with the fade path'
    assert '<output.webp>' in alt, 'the alternative names a container that cannot hold a fade'


PIXEL_SABER = os.path.join(ROOT, 'local/Diors-builds Emojis/others/Pixel Saber.gif')


@pytest.mark.skipif(not os.path.exists(PIXEL_SABER),
                    reason='local/Diors-builds Emojis/ is gitignored third-party material')
def test_the_alternative_receives_the_same_overrides_as_the_suggestion():
    """`alternative_command` is a COMMAND, and must be runnable on the same terms.

    --allow-changing-background was appended to `suggested_command` only, so on a
    changing-background asset the alternative was refused the moment anyone ran it --
    one path fixed, the other not, on a field whose entire purpose is to be runnable.

    ⚠️ FIXTURE PROVENANCE: Pixel Saber is the ONLY asset in the intersection across the
    304 assets of labelled + trial + emoji + small_aa -- 14 have an alternative_command,
    exactly 1 of those also has a changing background. That is why this test names an
    asset instead of sweeping: the sweep was run, and it returned one. Proven non-vacuous
    against the pre-fix code, where the alternative came back WITHOUT the flag.
    """
    def _rec(*flags):
        r = subprocess.run([sys.executable, SCRIPT, PIXEL_SABER, '--recommend', *flags],
                           capture_output=True, text=True, timeout=1800)
        assert r.returncode == 0, r.stderr[-3000:]
        start = min(i for i in (r.stdout.find('{'), r.stdout.find('[')) if i >= 0)
        doc, _ = json.JSONDecoder().raw_decode(r.stdout[start:])
        return doc[0]['recommendation'] if isinstance(doc, list) else doc

    # WITH the override: both commands exist and BOTH carry it.
    rec = _rec('--allow-changing-background')
    alt = rec.get('alternative_command')
    assert alt, 'the fixture no longer produces an alternative_command; this test is vacuous'
    assert '--allow-changing-background' in (rec['suggested_command'] or ''), \
        'the CLI did not forward --allow-changing-background to recommend()'
    assert '--allow-changing-background' in alt, \
        f'the alternative would be refused if run: {alt}'

    # WITHOUT it: the asset is not applicable, and NEITHER field may hold a command.
    # An alternative that outlives the refusal is an escape hatch stapled to a refusal.
    bare = _rec()
    assert bare.get('not_applicable_reason'), 'the fixture stopped being a refusal case'
    assert bare.get('suggested_command') is None
    assert bare.get('alternative_command') is None, \
        f'a runnable command survived a not-applicable verdict: {bare.get("alternative_command")}'
