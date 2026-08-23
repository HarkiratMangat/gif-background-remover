"""Falsifiers for the pre-flight fit cost estimate (plan Task 3).

Measured 2026-08-22: the megaphone fit walked ~118 of 120 rungs at 144 frames
and took 207.84s -- and the FIRST attempt died at a 120s tool timeout having
produced nothing. Neither `--analyze` nor `--recommend` said anything
beforehand, so a session learns the cost only by losing a tool call to it.

The estimate is deliberately not in seconds. It does not need to predict a
duration; it needs to let a caller decide to split the job.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import remove_gif_background as R  # noqa: E402


def test_the_megaphone_case_warns():
    est = R.estimate_fit_cost(n_rungs=120, n_frames=144, workers=6)
    assert est['frame_encodes'] == 120 * 144
    assert est['warn'] is True


def test_a_small_asset_does_not_warn():
    """What STAYED: an 8-frame sticker finishes in seconds and must not be flagged."""
    est = R.estimate_fit_cost(n_rungs=120, n_frames=8, workers=6)
    assert est['warn'] is False


def test_more_workers_lowers_the_estimate_but_not_the_work():
    a = R.estimate_fit_cost(n_rungs=120, n_frames=144, workers=2)
    b = R.estimate_fit_cost(n_rungs=120, n_frames=144, workers=8)
    assert a['frame_encodes'] == b['frame_encodes']
    assert a['serial_batches'] > b['serial_batches']


def test_one_worker_never_divides_by_zero():
    assert R.estimate_fit_cost(n_rungs=10, n_frames=10, workers=0)['serial_batches'] >= 1
    assert R.estimate_fit_cost(n_rungs=10, n_frames=10, workers=None)['serial_batches'] >= 1
