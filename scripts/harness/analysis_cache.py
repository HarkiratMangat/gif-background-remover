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

  * a fingerprint of the part of the script `analyze()` can actually REACH -- so any edit that
    could change an analysis invalidates every entry, which matters because editing the product
    is precisely what a session using this harness spends its time doing. A cache that a code
    change cannot invalidate is worse than no cache: it would serve the pre-change answer to
    the measurement meant to detect the change. See `analysis_fingerprint` for exactly what is
    and is not included, and why the fallback is always the whole-file SHA.
  * the asset's path, mtime and size -- so re-exporting or swapping a fixture invalidates it.

Entries live under `local/.analysis-cache/<script-sha>/`, which is gitignored. Wiping it is
always safe; the worst case is that the next run is as slow as every run used to be.
"""
import ast
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_ROOT = os.path.join(ROOT, 'local', '.analysis-cache')


def script_sha(script_path):
    with open(script_path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


ANALYSIS_ROOTS = ('analyze',)


def _reachable(funcs, roots):
    """Every module-level function transitively reachable from `roots`, following both
    plain-Name CALLS and plain-Name REFERENCES (a function passed as a value is a
    dependency too). Nested defs, decorators and default arguments come along inside
    their parent's own AST, so they need no separate walk."""
    seen, stack = set(), list(roots)
    while stack:
        name = stack.pop()
        if name in seen or name not in funcs:
            continue
        seen.add(name)
        for sub in ast.walk(funcs[name]):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                stack.append(sub.func.id)
            elif isinstance(sub, ast.Name) and sub.id in funcs:
                stack.append(sub.id)
    return seen


def _strip_docstrings(node):
    """A docstring cannot change what `analyze()` returns, and this script is deliberately
    comment- and docstring-dense -- prose gets edited constantly. Comments are already
    invisible to the AST; docstrings are not, so they are removed explicitly."""
    for n in ast.walk(node):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, 'body', None)
            if body and isinstance(body[0], ast.Expr) \
               and isinstance(body[0].value, ast.Constant) \
               and isinstance(body[0].value.value, str):
                n.body = body[1:] or [ast.Pass()]
    return node


def analysis_fingerprint(script_path, roots=ANALYSIS_ROOTS):
    """A cache key for `analyze()` derived from the code that DETERMINES an analysis,
    rather than from the whole file.

    Adopted 2026-08-21 from Dior's Builds' `utils/algoFingerprint.js`, which solves the
    same problem for its palette caches: key on the algorithm's own identity, never on a
    file hash or a hand-maintained version string. Measured over this file's real history
    before adopting it -- of the 28 commits that changed `remove_gif_background.py`,
    a whole-file key invalidates on all 28 and this key invalidates on 19, so **9 (32.1%)
    of product commits keep a warm analysis cache that used to go cold**. The naive half of
    the transfer was measured and REJECTED: stripping comments/docstrings from the whole
    file survives only 1 of those 28 (3.6%), so comment-density is not where the cost is.

    What is hashed:
      * EVERY module-level statement that is not a function definition -- imports, constants,
        class definitions, module-level `if`s. Unconditionally, in source order. A constant
        is reachable from anywhere and cheap to include, so it is never analysed for reach.
      * every module-level function transitively reachable from `roots`, sorted by name.
    Docstrings are stripped from both; comments never reach the AST at all.

    What is NOT hashed: functions `analyze()` cannot reach -- `process`, the renderers, the
    compression ladder, `main`. Verified against the one case this repo has already been
    bitten by: `source_transparency_is_the_background` gates a band rule from inside
    `analyze()` (CLAUDE.md release gate 10), and it IS inside the closure.

    ⚠️ **The direction of the error matters and it is not symmetric.** A false invalidation
    costs one re-analysis; a MISSED invalidation serves a pre-change answer to the gate meant
    to detect the change. So every uncertain case resolves toward invalidating: anything that
    cannot be parsed, a root that is not present, any exception at all falls back to
    `script_sha`, which invalidates on every byte.

    ⚠️ It cannot see dispatch the AST does not name -- `getattr(module, name)()`, a call
    through a dict of callables, or a C-level hook. None exists in this script today. If one
    is ever added on a path `analyze()` reaches, add its target to `roots` or drop back to
    `script_sha`; do not assume the closure found it.
    """
    try:
        with open(script_path, 'rb') as fh:
            raw = fh.read()
        tree = ast.parse(raw.decode('utf-8'))
        funcs, ambient = {}, []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs[node.name] = node
            else:
                ambient.append(node)
        missing = [r for r in roots if r not in funcs]
        if missing:
            raise ValueError(f'root(s) not found at module level: {missing}')
        reach = _reachable(funcs, roots)
        material = '|'.join(ast.dump(_strip_docstrings(n)) for n in ambient)
        material += '||' + '|'.join(ast.dump(_strip_docstrings(funcs[n]))
                                    for n in sorted(reach))
        return 'a' + hashlib.sha256(material.encode()).hexdigest()[:15]
    except Exception:
        # Any doubt at all -> the whole-file SHA, which invalidates on every byte.
        return script_sha(script_path)


def _entry_path(script_path, asset_path):
    st = os.stat(asset_path)
    key = f'{os.path.abspath(asset_path)}|{st.st_mtime_ns}|{st.st_size}'
    d = os.path.join(CACHE_ROOT, analysis_fingerprint(script_path))
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
    """(entries, megabytes, key_dirs) currently cached — for a run to report at the end.

    The third element used to be described as script SHAs; the directories are now
    `analysis_fingerprint` values (prefixed `a`) except where it fell back."""
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
