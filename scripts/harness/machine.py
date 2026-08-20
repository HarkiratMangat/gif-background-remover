"""How many workers this machine can actually run, measured rather than assumed.

⚠️ Every `--jobs` default in this harness used to be `min(8, os.cpu_count())`, and on the
machine this project is developed on that constant is wrong in BOTH directions at once:

  * `os.cpu_count()` reports 8 on an M1 Pro, but only **6 are performance cores** -- the other
    two are efficiency cores, several times slower, and a unit scheduled onto one becomes the
    run's long tail. `analyze()` is measured at 21.0s user of 22.5s real, i.e. 93% CPU-bound
    and single-threaded, so the useful lane count is the PERFORMANCE core count, not the
    logical one.
  * The constant ignores memory entirely. One `analyze` on a 177-frame 640x640 asset peaks at
    **488 MB RSS**. Eight of those is ~3.9 GB, and this is a 16 GB machine that has been
    observed with 0.8 GB free and 8.6 GB of swap in use. Past the point where the working set
    stops fitting, more workers make a run SLOWER, not faster, and unpredictably so -- the
    same 107-asset render set was measured at 976s and 488s on consecutive runs.

So the ceiling is `min(performance_cores, free_memory / per_worker_estimate)`, computed at
call time. A constant cannot express either half: the core split is hardware and the memory
headroom changes minute to minute with whatever else is running.

Everything degrades to the old behaviour on a platform where the probes are unavailable.
"""
import os
import subprocess

# Peak RSS of one `analyze()` on the largest asset in the corpus (177 frames at 640x640),
# measured 2026-08-20 with /usr/bin/time -l. Renders run lighter than this, so using the
# analyze figure everywhere is deliberately conservative.
PER_WORKER_MB = 500

# Never hand back fewer than this. One worker is always runnable, and dropping to 1 on a
# transiently busy machine would make a routine gate take an hour.
MIN_JOBS = 2


def _sysctl_int(name):
    try:
        return int(subprocess.run(['sysctl', '-n', name], capture_output=True,
                                  text=True, timeout=5).stdout.strip())
    except Exception:
        return None


def performance_cores():
    """Cores worth scheduling CPU-bound work onto.

    On Apple Silicon `hw.perflevel0.logicalcpu` is the P-core count and perflevel1 is the
    E-cores. Elsewhere this returns the logical count, which is the old behaviour.
    """
    return _sysctl_int('hw.perflevel0.logicalcpu') or os.cpu_count() or 1


def available_mb():
    """Memory that can be handed to workers without forcing compression or swap.

    Counts free + inactive + speculative pages: inactive pages are reclaimable, so treating
    them as unavailable would under-provision badly on a machine that has been up for weeks.
    Returns None where vm_stat is unavailable, which callers read as "no memory constraint".
    """
    try:
        out = subprocess.run(['vm_stat'], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    page = 4096
    counts = {}
    for line in out.splitlines():
        if 'page size of' in line:
            try:
                page = int(line.split('page size of')[1].split('bytes')[0].strip())
            except Exception:
                pass
        if ':' in line:
            k, _, v = line.partition(':')
            v = v.strip().rstrip('.')
            if v.isdigit():
                counts[k.strip()] = int(v)
    pages = sum(counts.get(k, 0) for k in
                ('Pages free', 'Pages inactive', 'Pages speculative'))
    return (pages * page) / (1024 * 1024) if pages else None


def default_jobs(per_worker_mb=PER_WORKER_MB, explain=False):
    """Worker count for this machine, right now.

    `explain=True` also returns a one-line string naming which limit bound the answer, so a
    run's log says WHY it chose a number instead of leaving the next reader to guess.
    """
    cores = performance_cores()
    mem = available_mb()
    if mem is None:
        jobs, why = cores, f'{cores} performance cores (memory probe unavailable)'
    else:
        by_mem = int(mem // per_worker_mb)
        if by_mem < cores:
            jobs = max(MIN_JOBS, by_mem)
            why = (f'{jobs} = {mem:.0f} MB available / {per_worker_mb} MB per worker '
                   f'(memory-bound; {cores} performance cores idle)')
            if by_mem < MIN_JOBS:
                why += f' -- floored at MIN_JOBS={MIN_JOBS}, expect swapping'
        else:
            jobs, why = cores, f'{cores} performance cores (memory allows {by_mem})'
    return (jobs, why) if explain else jobs


if __name__ == '__main__':
    j, why = default_jobs(explain=True)
    print(f'default_jobs() -> {j}')
    print(f'  because: {why}')
    print(f'  performance cores : {performance_cores()}')
    print(f'  logical cores     : {os.cpu_count()}')
    mb = available_mb()
    print(f'  available memory  : {mb:.0f} MB' if mb else '  available memory  : unknown')
