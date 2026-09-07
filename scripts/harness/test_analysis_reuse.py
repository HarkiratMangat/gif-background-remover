"""`--auto` must not analyse a file the caller already analysed.

Two mechanisms, one question. Inside a single run, `verify()` recomputed pass 1's
analysis; ACROSS runs, a front end that ran `--recommend` to show its user the
questions made `--auto` recompute the identical report seconds later. The first is a
parameter, the second is `--analysis-json`.

⚠️ EVERY ASSERTION HERE IS RUN AGAINST THE STATE THAT SHOULD BREAK IT. A reuse test
that only checks the happy path proves the fast path works and says nothing about the
one that matters -- a document that has gone stale must be REFUSED, loudly, and the
run must analyse anyway. Each refusal is asserted to fire for ITS OWN reason: an
earlier draft of this file touched the fixture's mtime and never restored the
document, so three later cases refused for the input check instead and passed
vacuously.
"""
import contextlib
import importlib.util
import io
import json
import os
import sys

import pytest
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'remove_gif_background.py')


def _load(tag):
    """A FRESH module per run, so nothing carries between cases."""
    spec = importlib.util.spec_from_file_location(f'rgb_reuse_{tag}', SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def _run(argv, tag):
    """(analyze() call count, stderr). Counts the REAL function, wrapped on the module."""
    m = _load(tag)
    n = {'c': 0}
    real = m.analyze
    m.analyze = lambda *a, **k: (n.__setitem__('c', n['c'] + 1), real(*a, **k))[1]
    saved, sys.argv = sys.argv, argv
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            m.main()
    except SystemExit:
        pass
    finally:
        sys.argv = saved
    return n['c'], err.getvalue()


@pytest.fixture(scope='module')
def asset(tmp_path_factory):
    """A tiny two-frame GIF: white ground, one navy square. Small enough to analyse
    in well under a second, and real enough that `analyze()` finds a background."""
    d = tmp_path_factory.mktemp('reuse')
    frames = []
    for dx in (0, 4):
        im = Image.new('RGB', (64, 64), (255, 255, 255))
        for y in range(20, 44):
            for x in range(20 + dx, 44 + dx):
                im.putpixel((x, y), (0, 40, 100))
        frames.append(im.convert('P', palette=Image.ADAPTIVE))
    p = d / 'square.gif'
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return p


def test_auto_alone_analyses_once_not_twice(asset, tmp_path):
    """The parameter half. `verify()` used to recompute pass 1's analysis; passing it
    in is the whole fix, and the count is the only thing that can prove it."""
    n, _ = _run([SCRIPT, str(asset), str(tmp_path / 'o.gif'), '--auto'], 'a1')
    assert n == 1, f'expected one analysis for the whole run, got {n}'


def test_a_supplied_document_removes_the_last_analysis(asset, tmp_path):
    doc = tmp_path / 'a.json'
    _run([SCRIPT, str(asset), '--recommend', '--analysis-json', str(doc)], 'w1')
    assert doc.exists(), '--recommend --analysis-json wrote nothing'

    n, err = _run([SCRIPT, str(asset), str(tmp_path / 'o.gif'),
                   '--auto', '--analysis-json', str(doc)], 'r1')
    assert n == 0, f'a valid document should leave nothing to analyse, got {n}'
    assert '--analysis-json accepted' in err, 'acceptance must be stated, not silent'


def test_analyze_can_write_the_document_too(asset, tmp_path):
    doc = tmp_path / 'b.json'
    _run([SCRIPT, str(asset), '--analyze', '--analysis-json', str(doc)], 'w2')
    d = json.loads(doc.read_text())
    assert d['schema'] == 'gif-background-remover/analysis@1'
    assert 'candidate_regions' in d['analysis']


# --------------------------------------------------------------------------
# The refusals. `mutate` receives the parsed document and returns it; the fixture
# is rewritten from scratch for every case so no case can inherit another's damage.
# --------------------------------------------------------------------------
def _tamper(doc_path, fn):
    d = json.loads(doc_path.read_text())
    fn(d)
    doc_path.write_text(json.dumps(d))


@pytest.mark.parametrize('label,mutate,expect', [
    ('tolerance', lambda d: d.update(tolerance=99), 'written at --tolerance 99'),
    ('script', lambda d: d.update(script_sha256='0' * 16), 'this script changed'),
    ('other input', lambda d: d['input'].update(path='/nope/x.gif'), 'a different input'),
    ('not ours', lambda d: d.update(schema='other/thing@1'), 'not a document this tool wrote'),
    ('gutted', lambda d: d.update(analysis={'a': 1}), 'is not an analyze() report'),
])
def test_a_stale_document_is_refused_loudly_and_the_run_analyses_anyway(
        asset, tmp_path, label, mutate, expect):
    doc = tmp_path / f'{label.replace(" ", "_")}.json'
    _run([SCRIPT, str(asset), '--recommend', '--analysis-json', str(doc)], f'w_{label}')
    _tamper(doc, mutate)
    n, err = _run([SCRIPT, str(asset), str(tmp_path / 'o.gif'),
                   '--auto', '--analysis-json', str(doc)], f'r_{label}')
    assert 'NOT USED' in err, f'{label}: refused silently, which is the SS44 shape'
    assert expect in err, f'{label}: refused for the wrong reason -- {err.strip()[:160]}'
    assert n == 1, f'{label}: refused and then did not analyse ({n})'


def test_an_unreadable_document_is_refused_not_raised(asset, tmp_path):
    doc = tmp_path / 'broken.json'
    doc.write_text('{ not json')
    n, err = _run([SCRIPT, str(asset), str(tmp_path / 'o.gif'),
                   '--auto', '--analysis-json', str(doc)], 'broken')
    assert 'NOT USED' in err and 'unreadable' in err
    assert n == 1


def test_a_touched_input_is_refused(asset, tmp_path):
    """Kept apart from the parametrised cases on purpose: it mutates the SHARED
    module-scoped fixture's mtime, and a case that damages state its neighbours read
    is how the first draft of this file passed three assertions vacuously."""
    import time
    doc = tmp_path / 'touch.json'
    _run([SCRIPT, str(asset), '--recommend', '--analysis-json', str(doc)], 'w_t')
    os.utime(asset, (time.time() + 1, time.time() + 1))
    n, err = _run([SCRIPT, str(asset), str(tmp_path / 'o.gif'),
                   '--auto', '--analysis-json', str(doc)], 'r_t')
    assert 'the input file changed' in err
    assert n == 1


def test_the_flag_refuses_a_mode_that_cannot_use_it(asset, tmp_path):
    """SS44: a flag must fail loudly when it cannot take effect. --verify has no
    analysis to write and none to read, so this is an argparse error, not a shrug."""
    n, err = _run([SCRIPT, str(asset), str(asset), '--verify',
                   '--analysis-json', str(tmp_path / 'x.json')], 'mode')
    assert 'only means something with' in err
