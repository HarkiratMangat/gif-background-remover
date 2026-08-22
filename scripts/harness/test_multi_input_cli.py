"""
Falsifiers for the multi-input CLI path (Part 4, Task A).

The point of that path is to cut AGENT round-trips, not script runtime: the
2026-08-19 three-agent trial measured 50-74 tool calls on a five-asset job. The
saving is only real if (a) the single-file path is untouched, (b) N inputs in one
invocation genuinely produce N results, and (c) the per-run boilerplate that
`_FORMAT_RANK_EMITTED` dedups is actually deduped -- which is a property of being
ONE PROCESS and cannot be tested by reading the code that sets the flag.

The dedup test therefore runs the SAME two assets both ways -- one invocation and
two -- and asserts the counts differ. A test that only checked the one-invocation
count would pass just as happily if the ranking had been deleted outright.
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', 'remove_gif_background.py')
sys.path.insert(0, os.path.join(HERE, '..'))

import remove_gif_background as R  # noqa: E402


class _Args:
    def __init__(self, **kw):
        self.analyze = self.recommend = self.verify = self.auto = False
        self.out_dir = None
        self.format = 'auto'
        self.__dict__.update(kw)


def _err(*a, **k):
    raise AssertionError('parser.error: ' + ' '.join(str(x) for x in a))


# --------------------------------------------------------------------------
# resolve_positional_paths -- which positional is an input and which the output
# --------------------------------------------------------------------------

def test_two_paths_still_mean_input_then_output():
    """The one genuinely ambiguous case, and the historical meaning must win --
    re-reading it as two inputs would silently stop writing the file the user named."""
    ins, out = R.resolve_positional_paths(['a.gif', 'b.gif'], _Args(), _err)
    assert ins == ['a.gif'] and out == 'b.gif'


def test_three_paths_are_three_inputs():
    """There is no such thing as two outputs, so 3+ paths is not a guess."""
    ins, out = R.resolve_positional_paths(['a.gif', 'b.gif', 'c.gif'], _Args(), _err)
    assert ins == ['a.gif', 'b.gif', 'c.gif'] and out is None


def test_out_dir_makes_even_two_paths_two_inputs():
    ins, out = R.resolve_positional_paths(
        ['a.gif', 'b.gif'], _Args(out_dir='/tmp/x'), _err)
    assert ins == ['a.gif', 'b.gif'] and out is None


def test_read_only_modes_take_every_path_as_an_input():
    """Before this, --analyze's second path was parsed into output_gif and then
    silently ignored -- the mode writes nothing, so it was never an output."""
    for mode in ('analyze', 'recommend'):
        ins, out = R.resolve_positional_paths(
            ['a.gif', 'b.gif'], _Args(**{mode: True}), _err)
        assert ins == ['a.gif', 'b.gif'] and out is None, mode


def test_out_dir_is_refused_where_it_cannot_mean_anything():
    for mode in ('analyze', 'recommend', 'verify'):
        with pytest.raises(AssertionError, match='out-dir'):
            R.resolve_positional_paths(['a.gif', 'b.gif'],
                                       _Args(out_dir='/tmp/x', **{mode: True}), _err)


def test_verify_still_demands_exactly_two_paths():
    """--verify compares one source to one already-written output. A third path used
    to be an argparse 'unrecognized arguments' error; with nargs='*' it would be
    silently swallowed instead."""
    ok_ins, ok_out = R.resolve_positional_paths(['a.gif', 'b.gif'],
                                                _Args(verify=True), _err)
    assert ok_ins == ['a.gif'] and ok_out == 'b.gif'
    for bad in (['a.gif'], ['a.gif', 'b.gif', 'c.gif']):
        with pytest.raises(AssertionError, match='exactly two'):
            R.resolve_positional_paths(bad, _Args(verify=True), _err)


# --------------------------------------------------------------------------
# derive_output_path -- the name chosen when the caller named no output
# --------------------------------------------------------------------------

def test_derived_name_follows_the_delivery_convention(tmp_path):
    src = tmp_path / 'seal.gif'
    src.write_bytes(b'x')
    got = R.derive_output_path(str(src), _Args())
    assert os.path.basename(got) == 'seal_transparent.gif'
    assert os.path.dirname(got) == str(tmp_path)


def test_derived_name_escalates_rather_than_overwriting(tmp_path):
    """SKILL.md's delivery convention: a re-run names _v2, it does not silently
    overwrite a file the user may already have shipped."""
    src = tmp_path / 'seal.gif'
    src.write_bytes(b'x')
    (tmp_path / 'seal_transparent.gif').write_bytes(b'y')
    assert os.path.basename(R.derive_output_path(str(src), _Args())) == \
        'seal_transparent_v2.gif'
    (tmp_path / 'seal_transparent_v2.gif').write_bytes(b'y')
    assert os.path.basename(R.derive_output_path(str(src), _Args())) == \
        'seal_transparent_v3.gif'


def test_explicit_format_picks_the_extension(tmp_path):
    """--format auto reads the OUTPUT extension, so a derived name that changed the
    container on its own would make the filename the thing that decided the format."""
    src = tmp_path / 'seal.gif'
    src.write_bytes(b'x')
    assert R.derive_output_path(str(src), _Args(format='webp')).endswith('.webp')
    assert R.derive_output_path(str(src), _Args(format='avif')).endswith('.avif')


def test_a_jpeg_source_derives_a_gif_not_a_jpeg(tmp_path):
    """A .jpg has no animated container to write back to; keeping the extension would
    produce a name this script cannot honour."""
    src = tmp_path / 'photo.jpeg'
    src.write_bytes(b'x')
    assert R.derive_output_path(str(src), _Args()).endswith('.gif')


def test_out_dir_relocates_the_derived_name(tmp_path):
    src = tmp_path / 'seal.gif'
    src.write_bytes(b'x')
    dest = tmp_path / 'out'
    dest.mkdir()
    got = R.derive_output_path(str(src), _Args(), out_dir=str(dest))
    assert got == str(dest / 'seal_transparent.gif')


# --------------------------------------------------------------------------
# run_read_only -- N inputs, one process, isolation on failure
# --------------------------------------------------------------------------

def test_one_failing_input_does_not_abort_the_rest():
    """Same contract --batch already holds. SystemExit is included deliberately:
    every deliberate refusal in this script raises SystemExit, which is NOT an
    Exception, so an `except Exception` here would abort every later file."""
    def fn(p):
        if p == 'b':
            raise SystemExit('refused')
        return {'ok': p}
    out = R.run_read_only(['a', 'b', 'c'], 'analysis', fn)
    assert [x['input'] for x in out] == ['a', 'b', 'c']
    assert out[0]['analysis'] == {'ok': 'a'}
    assert 'refused' in out[1]['error']
    assert out[2]['analysis'] == {'ok': 'c'}


# --------------------------------------------------------------------------
# The whole point: per-run boilerplate is emitted ONCE per process
# --------------------------------------------------------------------------

def _tiny_gif(path, colour=(255, 255, 255), dot=(200, 40, 40)):
    frames = []
    for shift in (0, 2):
        im = Image.new('RGB', (48, 48), colour)
        for y in range(18 + shift, 30 + shift):
            for x in range(18, 30):
                im.putpixel((x, y), dot)
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=80, loop=0)


RANK = 'full resolution ->'
BACKREF = 'as printed for the first asset'


def test_the_format_ranking_is_emitted_once_per_process_not_once_per_asset():
    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, 'a.gif'), os.path.join(td, 'b.gif')
        _tiny_gif(a)
        _tiny_gif(b, dot=(40, 90, 220))

        one = subprocess.run([sys.executable, SCRIPT, a, b, '--recommend'],
                             capture_output=True, text=True)
        assert one.returncode == 0, one.stderr[-2000:]
        recs = json.loads(one.stdout)
        assert len(recs) == 2 and all('recommendation' in r for r in recs), recs
        blob = json.dumps(recs)

        # Two separate invocations: the shape the trial's agents actually used.
        sep = ''
        for p in (a, b):
            r = subprocess.run([sys.executable, SCRIPT, p, '--recommend'],
                               capture_output=True, text=True)
            assert r.returncode == 0, r.stderr[-2000:]
            sep += r.stdout

        # The falsifier: if the ranking were simply gone, both counts would be 0 and a
        # one-sided assertion would still pass. It must be present N times separately
        # and exactly once when the same work is done in one process.
        assert sep.count(RANK) == 2, f'separate invocations emitted {sep.count(RANK)}'
        assert blob.count(RANK) == 1, f'one invocation emitted {blob.count(RANK)}'
        assert blob.count(BACKREF) == 1, blob.count(BACKREF)
