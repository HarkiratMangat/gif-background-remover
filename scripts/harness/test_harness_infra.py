"""Falsifiers for the harness's own speed infrastructure.

A cache that serves a stale answer is far worse than a slow run: it would hand the
pre-change result to the very measurement meant to detect the change. So the tests that
matter here are the INVALIDATION ones, not the hit-rate one.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, 'scripts', 'remove_gif_background.py')

import analysis_cache as AC  # noqa: E402
import machine as M  # noqa: E402


def _fake_module(counter):
    m = types.SimpleNamespace()

    def analyze(path):
        counter['n'] += 1
        return {'called': counter['n'], 'path': os.path.basename(path)}
    m.analyze = analyze
    return m


def _fake_script(tmp_path, body):
    p = tmp_path / 'fake_script.py'
    p.write_text(body)
    return str(p)


def _asset(tmp_path, name='a.bin', data=b'x'):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# --------------------------------------------------------------------- the cache

def test_second_call_is_served_from_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    c = {'n': 0}
    mod, sc, a = _fake_module(c), _fake_script(tmp_path, 'v1'), _asset(tmp_path)
    r1, hit1 = AC.cached_analyze(mod, a, sc)
    r2, hit2 = AC.cached_analyze(mod, a, sc)
    assert (hit1, hit2) == (False, True)
    assert c['n'] == 1, 'analyze ran twice — the cache did not serve the second call'
    assert r1 == r2


def test_a_script_change_invalidates_every_entry(tmp_path, monkeypatch):
    """THE test. Editing the product is exactly what a session using this harness does, and a
    cache that survived that would serve the pre-change answer to the change's own gate."""
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    c = {'n': 0}
    mod, a = _fake_module(c), _asset(tmp_path)
    AC.cached_analyze(mod, a, _fake_script(tmp_path, 'v1'))
    r, hit = AC.cached_analyze(mod, a, _fake_script(tmp_path, 'v2 -- one byte different'))
    assert hit is False, 'a script edit did NOT invalidate the cache'
    assert c['n'] == 2


def test_touching_the_asset_invalidates_it(tmp_path, monkeypatch):
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    c = {'n': 0}
    mod, sc, a = _fake_module(c), _fake_script(tmp_path, 'v1'), _asset(tmp_path)
    AC.cached_analyze(mod, a, sc)
    os.utime(a, (0, 0))
    _, hit = AC.cached_analyze(mod, a, sc)
    assert hit is False, 'a modified asset was served from cache'


def test_a_corrupt_entry_recomputes_instead_of_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    c = {'n': 0}
    mod, sc, a = _fake_module(c), _fake_script(tmp_path, 'v1'), _asset(tmp_path)
    AC.cached_analyze(mod, a, sc)
    p = AC._entry_path(sc, a)
    open(p, 'w').write('{ truncated')
    r, hit = AC.cached_analyze(mod, a, sc)
    assert hit is False and r['path'] == 'a.bin'


def test_disabled_never_touches_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    c = {'n': 0}
    mod, sc, a = _fake_module(c), _fake_script(tmp_path, 'v1'), _asset(tmp_path)
    AC.cached_analyze(mod, a, sc, enabled=False)
    AC.cached_analyze(mod, a, sc, enabled=False)
    assert c['n'] == 2 and not os.path.exists(str(tmp_path / 'cache'))


def test_a_real_analyze_result_round_trips_unchanged(tmp_path, monkeypatch):
    """The one that uses the REAL product. analyze() returns numpy scalars in places, and a
    naive `default=str` would write a float64 as its repr and bring it back as a STRING --
    silently breaking every downstream comparison while the cache reported a hit."""
    monkeypatch.setattr(AC, 'CACHE_ROOT', str(tmp_path / 'cache'))
    import importlib.util
    spec = importlib.util.spec_from_file_location('under_test', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    asset = os.path.join(ROOT, 'local', 'Corpus Trial Gifs', 'growth.gif')
    fresh, hit1 = AC.cached_analyze(mod, asset, SCRIPT)
    served, hit2 = AC.cached_analyze(mod, asset, SCRIPT)
    assert (hit1, hit2) == (False, True)
    assert json.dumps(fresh, sort_keys=True, default=AC._jsonable) == \
        json.dumps(served, sort_keys=True, default=AC._jsonable), \
        'the cached value differs from a fresh compute'


# --------------------------------------------------------------------- machine sizing

def test_default_jobs_never_exceeds_the_performance_cores():
    """os.cpu_count() reports 8 on an M1 Pro but only 6 are performance cores; scheduling
    CPU-bound work onto an E-core makes it the run's long tail."""
    assert M.MIN_JOBS <= M.default_jobs() <= M.performance_cores()


def test_performance_cores_never_exceeds_logical_cores():
    assert 1 <= M.performance_cores() <= (os.cpu_count() or 1)


def test_it_says_why_it_chose_that_number():
    """A run's log must name which limit bound the answer, or the next reader guesses."""
    jobs, why = M.default_jobs(explain=True)
    assert isinstance(jobs, int) and jobs >= M.MIN_JOBS
    assert ('core' in why or 'memory' in why) and str(jobs) in why


def test_a_tiny_memory_budget_binds_before_the_cores_do():
    """The negative half: with an absurd per-worker estimate the answer must fall to the
    floor, or the memory term is not actually being applied."""
    if M.available_mb() is None:
        import pytest
        pytest.skip('no memory probe on this platform')
    assert M.default_jobs(per_worker_mb=10 ** 7) == M.MIN_JOBS
