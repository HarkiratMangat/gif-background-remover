"""Disk cache for `analyze()`, so a deterministic answer is computed once per script version.

⚠️ The waste this exists to remove is real and was counted, not guessed. In one session on
2026-08-20, `--analyze`/`--recommend` was run as a full pass over overlapping populations
**six separate times**. The clearest case: a sweep measured which dark-corpus assets get
`--recover-fade-alpha` recommended, printed a COUNT, and discarded the table -- so the next
sweep recomputed the identical answer from scratch over all 105 assets at ~22s each. Same
script, same bytes, same result, roughly 40 minutes of pure recomputation.

`analyze()` is a pure function of (the asset's bytes, the script's code). Nothing else. So a
cache keyed on exactly those two things cannot be wrong, and it removes the whole class of
waste rather than one instance of it.

**The key is what makes this safe, and it is not negotiable:**

  * the SHA of the script under test -- so ANY edit to the product invalidates every entry,
    which matters because editing the product is precisely what a session using this harness
    spends its time doing. A cache that a code change cannot invalidate is worse than no
    cache: it would serve the pre-change answer to the measurement meant to detect the change.
  * the asset's path, mtime and size -- so re-exporting or swapping a fixture invalidates it.

Entries live under `local/.analysis-cache/<script-sha>/`, which is gitignored. Wiping it is
always safe; the worst case is that the next run is as slow as every run used to be.
"""
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_ROOT = os.path.join(ROOT, 'local', '.analysis-cache')


def script_sha(script_path):
    with open(script_path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def _entry_path(script_path, asset_path):
    st = os.stat(asset_path)
    key = f'{os.path.abspath(asset_path)}|{st.st_mtime_ns}|{st.st_size}'
    d = os.path.join(CACHE_ROOT, script_sha(script_path))
    return os.path.join(d, hashlib.sha256(key.encode()).hexdigest()[:24] + '.json')


def _jsonable(o):
    """analyze() returns numpy scalars in places; json.dump refuses them.

    Converting is correct here and stringifying would NOT be -- a float64 written as its repr
    would come back as a string and silently break every downstream comparison. So this
    handles the numeric cases explicitly and raises on anything it does not recognise, rather
    than guessing.
    """
    if hasattr(o, 'item'):
        return o.item()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(f'not JSON-serialisable and not a numpy scalar: {type(o).__name__}')


def cached_analyze(module, asset_path, script_path, enabled=True):
    """`module.analyze(asset_path)`, served from disk when the script and asset are unchanged.

    Returns `(result, was_cached)`. Any cache failure -- unreadable entry, unwritable
    directory, a value that will not serialise -- falls through to computing the real answer.
    A cache is an optimisation and must never be able to fail a run.
    """
    if not enabled:
        return module.analyze(asset_path), False
    try:
        p = _entry_path(script_path, asset_path)
    except OSError:
        return module.analyze(asset_path), False
    if os.path.exists(p):
        try:
            with open(p) as fh:
                return json.load(fh), True
        except Exception:
            pass  # corrupt or truncated entry: recompute and overwrite below
    result = module.analyze(asset_path)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + f'.{os.getpid()}.tmp'
        with open(tmp, 'w') as fh:
            json.dump(result, fh, default=_jsonable)
        os.replace(tmp, p)   # atomic, so concurrent workers cannot read a half-written entry
    except Exception:
        pass
    return result, False


def stats():
    """(entries, megabytes, script_shas) currently cached — for a run to report at the end."""
    n = size = 0
    shas = []
    if os.path.isdir(CACHE_ROOT):
        for sha in sorted(os.listdir(CACHE_ROOT)):
            d = os.path.join(CACHE_ROOT, sha)
            if not os.path.isdir(d):
                continue
            shas.append(sha)
            for f in os.listdir(d):
                n += 1
                try:
                    size += os.path.getsize(os.path.join(d, f))
                except OSError:
                    pass
    return n, size / (1024 * 1024), shas


if __name__ == '__main__':
    n, mb, shas = stats()
    print(f'{n} entries, {mb:.1f} MB, across {len(shas)} script version(s)')
    for s in shas:
        print(f'  {s}')
    print(f'cache root: {CACHE_ROOT}  (gitignored; safe to delete)')
