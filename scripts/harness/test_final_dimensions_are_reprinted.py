"""Falsifiers for stale dimensions after a --target-kb fit (plan Task 7).

`Output: {w}x{h}` is printed BEFORE the fit runs. When the fit lands it reported
only `Final: 242.3 KB`, so the last dimensions the tool printed were stale.
Measured consequence 2026-08-22: a session reported 482x513 as the delivered
dimensions of a file that was 120x128 -- and the tool had printed exactly
`Output: 482x513` in that same run. A session reporting faithfully what the tool
said would still have been wrong.

The dimensions are read back from the WRITTEN FILE, not from the winning rung: a
rung records what it asked for, the encoder records what it wrote.
"""
import os
import re
import subprocess
import sys

import pytest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
ROOT = os.path.join(HERE, '..', '..')
SECURE = os.path.join(ROOT, 'local/2026-08-21-v6-timeout-trial/inputs/secure.gif')

needs = pytest.mark.skipif(not os.path.exists(SECURE),
                           reason='the trial inputs are gitignored third-party assets')


@needs
def test_a_fit_that_changes_dimensions_reprints_them(tmp_path):
    out = tmp_path / 'm.webp'
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out),
                        '--protect-outline-color', '002864', '--target-kb', '40'],
                       capture_output=True, text=True, timeout=3600)
    log = r.stdout + r.stderr
    assert r.returncode == 0, log[-3000:]
    with Image.open(out) as im:
        real = f'{im.size[0]}x{im.size[1]}'
    finals = re.findall(r'Final:.*?(\d+x\d+)', log)
    assert finals, 'the Final: line never reported dimensions'
    assert finals[-1] == real, f'last reported {finals[-1]} but the delivered file is {real}'

    # Non-vacuity: this fixture must actually EXERCISE the staleness, or the assertion
    # above would hold trivially on a fit that never resized anything.
    pre = re.findall(r'Output: (\d+x\d+)', log)
    assert pre and pre[-1] != real, \
        f'the fit did not change dimensions ({pre} -> {real}); this fixture no longer falsifies'
    assert 'BEFORE --target-kb fitting' in log, \
        'the pre-fit Output: line is not marked provisional'


@needs
def test_a_run_with_no_fit_is_unchanged(tmp_path):
    """What STAYED: no --target-kb means no Final: line and no provisional note."""
    out = tmp_path / 's.webp'
    r = subprocess.run([sys.executable, SCRIPT, SECURE, str(out),
                        '--protect-outline-color', '002864'],
                       capture_output=True, text=True, timeout=1800)
    log = r.stdout + r.stderr
    assert r.returncode == 0, log[-3000:]
    assert log.count('Final:') == 0
    assert 'BEFORE --target-kb fitting' not in log
