#!/usr/bin/env python3
"""Falsifiers for the two behaviour changes found by the 2026-09-01 four-asset review.

Every test is PAIRED — a positive and a negative that must disagree — so that neither half
can pass vacuously. A filter test that only ever asserts "the list is smaller" would still
pass if the filter deleted everything, and a warning test that only asserts "no warning"
would still pass if the warning had been deleted outright.

Run: python3 scripts/harness/test_four_asset_findings.py
"""
import importlib.util
import inspect
import pathlib
import sys

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'remove_gif_background.py'
_spec = importlib.util.spec_from_file_location('rgb_under_test', _SCRIPT)
rgb = importlib.util.module_from_spec(_spec)
sys.modules['rgb_under_test'] = rgb
_spec.loader.exec_module(rgb)

FAILURES = []


def check(name, cond, detail=''):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# --------------------------------------------------------------------------------------
# --min-quality: the quality-axis mirror of --min-width
# --------------------------------------------------------------------------------------
def test_min_quality():
    print("--min-quality")
    scales = (1.0, 0.75)
    unfloored = rgb.build_target_rungs('avif', scales)
    floored = rgb.build_target_rungs('avif', scales, min_quality=65)

    # Positive: the floor removes exactly the rungs below it, and nothing else.
    below = [r for r in unfloored if r[2] < 65]
    check('avif: rungs below the floor exist to remove',
          len(below) > 0, f'unfloored had {len(unfloored)} rungs, none below 65')
    check('avif: every surviving rung is at or above the floor',
          all(r[2] >= 65 for r in floored), f'{[r for r in floored if r[2] < 65][:3]}')
    check('avif: the floor removed exactly those rungs',
          len(floored) == len(unfloored) - len(below),
          f'{len(unfloored)} - {len(below)} != {len(floored)}')

    # Negative: a floor below the whole ladder must change NOTHING. Without this half, a
    # filter that dropped rungs unconditionally would still pass the positive.
    check('avif: a floor under the whole ladder is a no-op',
          rgb.build_target_rungs('avif', scales, min_quality=1) == unfloored)

    # Order is a TOTAL order and the concurrency argument rests on it. Filtering members
    # must not re-rank the survivors.
    check('avif: filtering preserves the relative order of survivors',
          floored == [r for r in unfloored if r[2] >= 65])

    # An unreachable floor must still deliver a rung rather than crash the run. 999 is
    # deliberately not reachable through the CLI -- `process()` refuses anything outside
    # 0-100 -- but `build_target_rungs` stays tolerant on purpose, so this exercises the
    # fallback directly rather than through a path that would have rejected the input.
    # The stride count is READ from the function's own default rather than written as a
    # literal, so adding a stride rung cannot fail this assertion and point the next reader
    # at the quality floor for a change on an unrelated axis.
    n_strides = len(inspect.signature(rgb.build_target_rungs).parameters['strides'].default)
    top = rgb.build_target_rungs('avif', scales, min_quality=999)
    check('avif: an unreachable floor still yields rungs, not zero',
          len(top) > 0 and len(top) == len(scales) * n_strides,
          f'got {len(top)}, expected {len(scales) * n_strides}')

    # APNG has no quality knob; a floor there must be inert in both directions.
    check('apng: a quality floor is inert',
          rgb.build_target_rungs('apng', scales, min_quality=90)
          == rgb.build_target_rungs('apng', scales))

    # WebP's ladder leads with a LOSSLESS rung, which no floor may exclude.
    wl = rgb.build_target_rungs('webp', scales, min_quality=95)
    check('webp: the lossless rung survives any floor',
          any(r[3] for r in wl), 'no lossless rung survived')


# --------------------------------------------------------------------------------------
# --assume-remove must not be reported as an unprotected-design defect
# --------------------------------------------------------------------------------------
def _coverage(colour):
    return [{
        'region_id': 4,
        'frames_with_data': 171,
        'mean_opacity_fraction': 0.0,
        'looks_unprotected': True,
        'expected_protection': f'--protect-outline-color {colour}',
        'expected_outline_color': colour,
        'residual_nonopaque': 0,
    }]


# ⚠️ THE PRODUCT'S OWN PREDICATE, not a copy of it. The first version of this file
# re-implemented the filter, which meant deleting the --assume-remove clause from the
# shipped code left this suite still reporting "all falsifiers pass" -- a test certifying a
# reconstruction rather than the thing that runs. `verify()` calls this same function.
_dead = rgb.unprotected_design_regions


def test_assume_remove():
    print("--assume-remove vs the unprotected-design warning")
    cov = _coverage('002864')
    # Negative half: with no assumption the warning MUST still fire. Without this, a filter
    # that suppressed the warning always would pass the positive half.
    check('un-answered: a 0.0%-opaque design region is still reported',
          len(_dead(cov, ())) == 1)
    # Positive half: the caller answered this colour, so it is not a defect.
    check('answered: the same region is NOT reported',
          len(_dead(cov, {'002864'})) == 0)
    check('answered with a leading #: still matched',
          len(_dead(cov, {'#002864'})) == 0)
    check('a DIFFERENT colour answered: still reported',
          len(_dead(cov, {'ff00ff'})) == 1)
    # A region nothing was recommended for carries no colour; an assumption must not
    # silently swallow it.
    none_cov = [dict(cov[0], expected_protection='none was recommended',
                     expected_outline_color=None)]
    check('no expected outline colour: still reported under any assumption',
          len(_dead(none_cov, {'002864'})) == 1)
    # A bare string must be read as ONE colour, not as five characters. Paired: the
    # matching string suppresses, a non-matching one does not.
    check('a bare string colour is read as one colour, not characters',
          len(_dead(cov, '002864')) == 0)
    check('a bare non-matching string still reports',
          len(_dead(cov, 'ff00ff')) == 1)


# --------------------------------------------------------------------------------------
# The hint text must carry the tracker, and must no longer claim to be the only option
# --------------------------------------------------------------------------------------
def test_unprotect_hint():
    print("_unprotect_hint")
    txt = rgb._unprotect_hint(4, (287, 200, 468, 484), 0.46, 171)
    check('offers --remove-region-track with a seed',
          '--remove-region-track rect:287,200,181,284' in txt, txt[:120])
    check('still offers the static --unprotect-region box',
          '--unprotect-region rect:287,200,181,284' in txt)
    check('no longer claims to be the ONLY flag that composes with the fade path',
          'only region flag that composes' not in txt)
    check('warns that one region id can hold two blobs',
          'per-frame connectivity' in txt)


def test_min_quality_range():
    """The CLI boundary refuses a floor no encoder rung could ever satisfy."""
    print("--min-quality range validation")
    import subprocess
    src = pathlib.Path('/Users/harkirat/Downloads/Diors-builds Emojis/SmallDot.webp')
    if not src.exists():
        print("  SKIP  (fixture not present on this machine)")
        return
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        def run(q):
            return subprocess.run(
                [sys.executable, str(_SCRIPT), str(src), f'{td}/o{q}.avif',
                 '--avif-quality', '85', '--target-kb', '250', '--min-quality', str(q)],
                capture_output=True, text=True)
        # Positive: out of range is refused, and the message names the real bounds.
        bad = run(150)
        check('a floor above 100 is refused', bad.returncode != 0, f'rc={bad.returncode}')
        check('the refusal names the real range, not the typed value',
              '0-100' in bad.stderr and 'Raise --avif-quality to 150' not in bad.stderr,
              bad.stderr[-200:])
        neg = run(-5)
        check('a negative floor is refused', neg.returncode != 0, f'rc={neg.returncode}')
        # Negative half: an IN-range floor must still be accepted, or the check is too broad.
        ok = run(65)
        check('an in-range floor is still accepted', ok.returncode == 0,
              ok.stderr[-200:])


if __name__ == '__main__':
    test_min_quality()
    test_min_quality_range()
    test_assume_remove()
    test_unprotect_hint()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILING: {FAILURES}")
        sys.exit(1)
    print("all falsifiers pass")
