"""
Falsifiers for the size/format gate's DEFAULT (Part 4, Task B, step 5).

SKILL.md's gate says: no size/format/compression requirement stated -> full
resolution, no compression flags, full quality. That rule lives in prose, and prose
cannot stop a future edit from making some compression lever fire on its own. These
tests pin the behaviour the rule describes, through the real CLI.

Each assertion is paired with a POSITIVE CONTROL that moves the same measurement, so
a test cannot pass by measuring something that never changes -- the vacuous-pass trap
this repo has hit before (see the fixture note in CLAUDE.md's repo conventions).
"""
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')

W = H = 64
N_FRAMES = 6


def _asset(path):
    """A flat-vector-ish source: white background, a moving coloured square, and a
    generous transparent-able margin so a crop would visibly change the canvas."""
    frames = []
    for i in range(N_FRAMES):
        im = Image.new('RGB', (W, H), (255, 255, 255))
        for y in range(26, 38):
            for x in range(20 + i, 32 + i):
                im.putpixel((x, y), (30, 90, 200))
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=70, loop=0)


def _render(tmp_path, name, extra=()):
    src = str(tmp_path / 'src.gif')
    if not os.path.exists(src):
        _asset(src)
    out = str(tmp_path / name)
    r = subprocess.run([sys.executable, SCRIPT, src, out, *extra],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    im = Image.open(out)
    return im.size, getattr(im, 'n_frames', 1), out


def test_no_constraint_means_full_resolution_and_every_frame(tmp_path):
    """The default. Nothing about the source being large, or the art looking like a
    sticker, may cause a crop/resize/frame-drop to happen on its own."""
    size, n, _ = _render(tmp_path, 'plain.gif')
    assert size == (W, H), f'canvas moved with no size flag: {size}'
    assert n == N_FRAMES, f'frames dropped with no stride flag: {n}'


def test_auto_alone_is_still_full_resolution(tmp_path):
    """--auto assembles flags from --recommend. It must not assemble a SIZE flag:
    a byte cap is the user's constraint to state, never the tool's to infer."""
    size, n, _ = _render(tmp_path, 'auto.gif', ('--auto',))
    assert size == (W, H), f'--auto resized without being asked: {size}'
    assert n == N_FRAMES, f'--auto dropped frames without being asked: {n}'


def test_the_measurements_above_can_actually_move(tmp_path):
    """The positive control. Without this, both tests above would pass just as
    happily against a build where resizing and frame-dropping were impossible."""
    resized, _, _ = _render(tmp_path, 'resized.gif', ('--resize-max-dim', '32'))
    assert max(resized) == 32, resized
    _, strided, _ = _render(tmp_path, 'strided.gif', ('--frame-stride', '2'))
    assert strided < N_FRAMES, strided
