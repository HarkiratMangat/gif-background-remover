"""Falsifiers for a nameable-but-undecidable fade (plan Task 12).

Measured 2026-08-22 on notification.gif: the detector identifies the
flattened-fade signature, NAMES the colour `fd6050`, counts 2,706 pixels on
frame 14 and prescribes the flag -- then delivers all of it as an EVIDENCE
STRING, while `--auto` went ahead and cut the falloff. An autonomous run reads
flags, not prose. `CLAUDE.md` already states the rule this broke.

⚠️ THE REFUSAL TO AUTO-APPLY IS CORRECT AND IS PRESERVED. `references/lessons.md`
SS41 measured 91 assets in exactly this branch whose ramp statistics interleave
with ones that render as a translucent ghost of the whole frame; no threshold
separates them. This task changes the DELIVERY CHANNEL, not the decision -- do
not "fix" it by lowering a threshold that has been shown not to exist.

⚠️ Blocked on Task 13 until 2026-08-23, and for a good reason: the answer the
refusal prints has to WORK. It prints `--recover-fade-alpha --fade-color <hex>`,
both flags, because `--fade-color` alone was a silent no-op until Task 13.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
NOTIFICATION = os.path.join(ROOT, 'local/2026-08-22-fade-edge-cases/inputs/notification.gif')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

needs = pytest.mark.skipif(not (os.path.exists(NOTIFICATION) and os.path.exists(SECURE)),
                           reason='the fade-edge-case inputs are gitignored third-party assets')


def _auto(src, out, *flags):
    r = subprocess.run([sys.executable, SCRIPT, src, str(out), '--auto', *flags],
                       capture_output=True, text=True, timeout=3600)
    return r.returncode, r.stdout + r.stderr


@needs
def test_auto_stops_on_a_nameable_fade_and_prints_a_WORKING_answer(tmp_path):
    rc, out = _auto(NOTIFICATION, tmp_path / 'n.webp')
    assert rc != 0, '--auto silently cut a fade it had already named'
    assert '--recover-fade-alpha --fade-color fd6050' in out, \
        'the refusal did not print the ready answer as the PAIR that actually works'
    assert '--assume-no-fade' in out, 'no way for an unattended run to decline'
    assert '2706' in out or '2,706' in out, 'the refusal did not show its evidence'


@needs
def test_the_two_questions_arrive_in_ONE_refusal(tmp_path):
    """An unattended caller pays a tool call per refusal. Asking serially turns two
    questions into two lost calls and a session that thinks the tool is looping."""
    rc, out = _auto(NOTIFICATION, tmp_path / 'q.webp')
    assert rc != 0
    assert 'COIN-FLIP PROTECTION' in out and 'NAMEABLE FADE' in out, \
        'only one of the two questions was asked'
    assert out.count('ERROR:') == 1, 'the refusals were not consolidated'


@needs
def test_declining_the_fade_lets_the_run_proceed(tmp_path):
    out_path = tmp_path / 'y.webp'
    rc, out = _auto(NOTIFICATION, out_path, '--assume-no-fade', '--assume-protect', '002864')
    assert rc == 0 and out_path.exists(), out[-3000:]
    assert 'assumption applied' in out, 'a run that acted on an assumption did not say so'


@needs
def test_an_asset_with_NO_nameable_fade_is_not_made_to_ask(tmp_path):
    """secure.gif has no fade at all. Without this the gate fires on everything."""
    out_path = tmp_path / 's.webp'
    rc, out = _auto(SECURE, out_path)
    assert rc == 0 and out_path.exists(), f'--auto refused an asset with no fade: {out[-2000:]}'
    assert 'NAMEABLE FADE' not in out
