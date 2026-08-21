"""Falsifiers for the dependency-scoped analysis cache key (Part 4, Task D).

`analysis_fingerprint` narrows the cache key from "every byte of the product file" to
"the code `analyze()` can actually reach". That is the whole point AND the whole risk:
a key that misses a real dependency serves a pre-change answer to the gate meant to
detect the change. Adopting the technique without the test that proves it invalidates
was the one thing Part 4's handoff said not to do.

So every test here comes in a pair -- something inside the closure MUST change the key,
something outside it MUST NOT. A suite that only asserted the second half would pass
against a key that never changed at all.
"""
import ast
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))

import analysis_cache as AC  # noqa: E402

REAL = os.path.join(HERE, '..', 'remove_gif_background.py')

# A function analyze() reaches, and one it does not. Both are asserted below rather
# than assumed -- if a refactor moves either across the line, the assertion says so
# instead of the suite quietly testing nothing.
IN_CLOSURE = 'analyze'
OUT_OF_CLOSURE = 'process'


def _closure(path):
    tree = ast.parse(open(path).read())
    funcs = {n.name: n for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return AC._reachable(funcs, AC.ANALYSIS_ROOTS), funcs


def _copy_with_probe_in(src, dst, func_name):
    """Copy `src` to `dst`, inserting a harmless statement at the top of `func_name`'s
    body. Located via the AST so a multi-line signature cannot fool it."""
    text = open(src).read()
    tree = ast.parse(text)
    node = next(n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == func_name)
    first = node.body[0]
    lines = text.split('\n')
    lines.insert(first.lineno - 1, ' ' * first.col_offset + '_fingerprint_probe = 1')
    open(dst, 'w').write('\n'.join(lines))
    return dst


# --------------------------------------------------------------------------
# The two halves. Neither is meaningful without the other.
# --------------------------------------------------------------------------

def test_the_two_probe_targets_are_actually_on_opposite_sides(tmp_path):
    reach, funcs = _closure(REAL)
    assert IN_CLOSURE in funcs and OUT_OF_CLOSURE in funcs
    assert IN_CLOSURE in reach, f'{IN_CLOSURE} left the closure -- pick a new probe target'
    assert OUT_OF_CLOSURE not in reach, \
        f'{OUT_OF_CLOSURE} entered the closure -- pick a new probe target'


def test_editing_code_analyze_reaches_invalidates(tmp_path):
    base = AC.analysis_fingerprint(REAL)
    edited = _copy_with_probe_in(REAL, str(tmp_path / 'edited.py'), IN_CLOSURE)
    assert AC.analysis_fingerprint(edited) != base


def test_editing_code_analyze_cannot_reach_does_not(tmp_path):
    """The 32.1% of real product commits this key is adopted for."""
    base = AC.analysis_fingerprint(REAL)
    edited = _copy_with_probe_in(REAL, str(tmp_path / 'edited.py'), OUT_OF_CLOSURE)
    assert AC.analysis_fingerprint(edited) == base


def test_the_case_this_repo_was_already_bitten_by_is_inside_the_closure():
    """CLAUDE.md release gate 10: a composited-frames change touched no rule and no
    threshold, and `all_rgb_frames[0]` turned out to feed
    `source_transparency_is_the_background`, which gates a band rule from inside
    analyze(). A scoped key that missed it would have served the pre-change answer."""
    reach, _ = _closure(REAL)
    assert 'source_transparency_is_the_background' in reach


# --------------------------------------------------------------------------
# Ambient state: hashed unconditionally, never analysed for reach
# --------------------------------------------------------------------------

def test_a_module_level_constant_always_invalidates(tmp_path):
    text = open(REAL).read()
    dst = str(tmp_path / 'const.py')
    marker = '\n_FORMAT_RANK_EMITTED = False\n'
    assert text.count(marker) == 1
    open(dst, 'w').write(text.replace(marker, '\n_FORMAT_RANK_EMITTED = False\n_NEW_CONST = 7\n'))
    assert AC.analysis_fingerprint(dst) != AC.analysis_fingerprint(REAL)


def test_an_import_change_always_invalidates(tmp_path):
    text = open(REAL).read()
    dst = str(tmp_path / 'imp.py')
    assert text.count('\nimport tempfile\n') == 1
    open(dst, 'w').write(text.replace('\nimport tempfile\n', '\nimport tempfile\nimport uuid\n'))
    assert AC.analysis_fingerprint(dst) != AC.analysis_fingerprint(REAL)


# --------------------------------------------------------------------------
# Prose is not code
# --------------------------------------------------------------------------

def test_a_comment_does_not_invalidate(tmp_path):
    dst = str(tmp_path / 'comment.py')
    open(dst, 'w').write('# a new comment at the top\n' + open(REAL).read())
    assert AC.analysis_fingerprint(dst) == AC.analysis_fingerprint(REAL)


def test_a_docstring_edit_does_not_invalidate(tmp_path):
    """Deliberate: a docstring cannot change what analyze() returns, and this file is
    docstring-dense enough that treating prose as code would defeat the whole cache."""
    text = open(REAL).read()
    tree = ast.parse(text)
    node = next(n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == IN_CLOSURE)
    doc = node.body[0]
    assert isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant), \
        f'{IN_CLOSURE} has no docstring to edit -- pick another target'
    lines = text.split('\n')
    lines[doc.lineno] = lines[doc.lineno] + ' (an edit to the prose)'
    dst = str(tmp_path / 'doc.py')
    open(dst, 'w').write('\n'.join(lines))
    assert AC.analysis_fingerprint(dst) == AC.analysis_fingerprint(REAL)


# --------------------------------------------------------------------------
# Every uncertain case falls back to the key that invalidates on every byte
# --------------------------------------------------------------------------

def test_an_unparseable_script_falls_back_to_the_whole_file_sha(tmp_path):
    dst = str(tmp_path / 'broken.py')
    open(dst, 'w').write('def analyze(:\n    pass\n')
    assert AC.analysis_fingerprint(dst) == AC.script_sha(dst)


def test_a_missing_root_falls_back_to_the_whole_file_sha(tmp_path):
    dst = str(tmp_path / 'norоot.py')
    open(dst, 'w').write('def something_else():\n    return 1\n')
    assert AC.analysis_fingerprint(dst) == AC.script_sha(dst)


def test_the_fallback_is_distinguishable_from_a_real_fingerprint():
    """A real fingerprint is prefixed 'a'; a fallback is a bare SHA. `stats()` reports
    the key directories, so a run that silently fell back stays visible."""
    assert AC.analysis_fingerprint(REAL).startswith('a')
    assert not AC.script_sha(REAL).startswith('a') or len(AC.script_sha(REAL)) == 16


# --------------------------------------------------------------------------
# End to end, through cached_analyze itself
# --------------------------------------------------------------------------

def _tiny_gif(path):
    from PIL import Image
    frames = []
    for i in range(3):
        im = Image.new('RGB', (40, 40), (255, 255, 255))
        for y in range(16, 26):
            for x in range(14 + i, 24 + i):
                im.putpixel((x, y), (200, 40, 40))
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=90, loop=0)


def test_cached_analyze_hits_across_an_out_of_closure_edit_and_misses_across_an_in_closure_one(
        tmp_path, monkeypatch):
    import remove_gif_background as R
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    asset = str(tmp_path / 'a.gif')
    _tiny_gif(asset)

    base = shutil.copy(REAL, str(tmp_path / 'base.py'))
    first, hit = AC.cached_analyze(R, asset, base)
    assert hit is False
    _, hit = AC.cached_analyze(R, asset, base)
    assert hit is True, 'a second identical call must be served from disk'

    outside = _copy_with_probe_in(REAL, str(tmp_path / 'outside.py'), OUT_OF_CLOSURE)
    served, hit = AC.cached_analyze(R, asset, outside)
    assert hit is True, 'an edit analyze() cannot reach must keep the cache warm'
    assert served == first

    inside = _copy_with_probe_in(REAL, str(tmp_path / 'inside.py'), IN_CLOSURE)
    _, hit = AC.cached_analyze(R, asset, inside)
    assert hit is False, 'an edit analyze() CAN reach must invalidate'
