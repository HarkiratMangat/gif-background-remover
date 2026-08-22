"""Freeze the script under test, so a mid-run edit cannot split a measurement in half.

⚠️ THE TRAP THIS REMOVES, and it has been hit at least three times. Every measurement job
here invokes `remove_gif_background.py` as a subprocess or re-imports it per worker, so it
re-reads the file for each asset. Edit the file while a run is in flight and the result is
half-old and half-new -- and it looks completely normal, because both halves are valid
output. It bit twice in one evening, an hour apart, and the second time was during a run
whose entire purpose was to measure the edits being made.

`render_baseline.py` grew its own private fix for this on 2026-08-18 and the other two
consumers never got one, which is the shape of the failure this repo already has a name
for: **a discipline is not a control.** "Remember not to edit during a run" is not a fix.
Copying the file is, because it cannot be forgotten -- and once every consumer does it, a
long run stops blocking the editing that would otherwise have to wait for it.

The snapshot is byte-identical to the source at start time, so `analysis_cache`'s
script-SHA key is unchanged and a frozen run shares a cache namespace with an unfrozen one.
That is the property that makes freezing free rather than a cache-busting tax.
"""
import hashlib
import os
import shutil
import tempfile


def freeze(script_path, label='under_test'):
    """Return (snapshot_path, source_sha12). The snapshot outlives the caller's edits."""
    snap = os.path.join(tempfile.mkdtemp(prefix='script_snapshot_'), label + '.py')
    shutil.copy2(script_path, snap)
    with open(script_path, 'rb') as fh:
        return snap, hashlib.sha256(fh.read()).hexdigest()[:12]
