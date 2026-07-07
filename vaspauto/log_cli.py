"""
``vaspauto log`` command — show job status from global history + Slurm.

Usage::

    vaspauto log               # last 5 jobs (default)
    vaspauto log -a            # all jobs
    vaspauto log --recent 10   # last 10
    vaspauto log --running     # only running / pending
    vaspauto log --failed      # only failed / unexpected-exit
    vaspauto log --json        # machine-readable JSON output
"""

import argparse
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class JobRecord:
    """One submitted job, assembled from history log entries + Slurm query."""
    __slots__ = (
        'job_id', 'job_name', 'submit_ts', 'config', 'work_dir',
        'task_type', 'partition', 'nodes', 'ntasks', 'cpus_per_task',
        'host', 'version', 'script',
        'start_ts', 'end_ts', 'elapsed_s', 'results',
        'slurm_state', 'va_state',
    )

    def __init__(self):
        self.job_id: Optional[str] = None
        self.job_name: str = ''
        self.submit_ts: str = ''
        self.config: str = ''
        self.work_dir: str = ''
        self.task_type: str = ''
        self.partition: str = ''
        self.nodes: int = 0
        self.ntasks: int = 0
        self.cpus_per_task: int = 0
        self.host: str = ''
        self.version: str = ''
        self.script: Optional[str] = None

        # from job_start
        self.start_ts: Optional[str] = None
        # from job_end
        self.end_ts: Optional[str] = None
        self.elapsed_s: Optional[float] = None
        self.results: Optional[dict] = None

        # from Slurm query
        self.slurm_state: Optional[str] = None

        # computed
        self.va_state: str = 'unknown'


# ---------------------------------------------------------------------------
# History file reading
# ---------------------------------------------------------------------------

def _history_path() -> Path:
    return Path.home() / '.config' / 'vaspauto' / 'history.jsonl'


def _read_history() -> list[JobRecord]:
    """Parse the global history log, returning one JobRecord per submit event.

    ``job_start`` and ``job_end`` events are merged into the corresponding
    submit record (matched by ``job_id``).
    """
    path = _history_path()
    if not path.is_file():
        return []

    # First pass: collect events by job_id
    submit_entries: list[dict] = []
    events_by_job: dict[str, list[dict]] = defaultdict(list)

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = entry.get('event')
            if event == 'submit':
                submit_entries.append(entry)
            elif event in ('job_start', 'job_end'):
                jid = entry.get('job_id')
                if jid:
                    events_by_job[jid].append(entry)

    # Build JobRecord list (preserve submit order)
    records: list[JobRecord] = []
    for sub in submit_entries:
        rec = JobRecord()
        rec.job_id = sub.get('job_id')
        rec.job_name = sub.get('job_name', '')
        rec.submit_ts = sub.get('ts', '')
        rec.config = sub.get('config', '')
        rec.work_dir = sub.get('work_dir', '')
        rec.task_type = sub.get('task_type', '')
        rec.partition = sub.get('partition', '')
        rec.nodes = sub.get('nodes', 0)
        rec.ntasks = sub.get('ntasks', 0)
        rec.cpus_per_task = sub.get('cpus_per_task', 0)
        rec.host = sub.get('host', '')
        rec.version = sub.get('version', '')
        rec.script = sub.get('script')

        # Merge job_start / job_end events
        jid = rec.job_id
        if jid and jid in events_by_job:
            for ev in events_by_job[jid]:
                if ev['event'] == 'job_start':
                    rec.start_ts = ev.get('ts')
                elif ev['event'] == 'job_end':
                    rec.end_ts = ev.get('ts')
                    rec.elapsed_s = ev.get('elapsed_s')
                    rec.results = ev.get('results')

        records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Slurm query
# ---------------------------------------------------------------------------

def _slurm_available() -> bool:
    """Check whether Slurm client commands are available."""
    return subprocess.run(['which', 'squeue'],
                          capture_output=True).returncode == 0


def _query_slurm_batch(job_ids: set[str]) -> dict[str, dict]:
    """Query Slurm for a set of job IDs.

    Returns ``{job_id: {'state': ..., 'exit_code': ...}}``.
    If Slurm is unavailable, returns an empty dict.
    """
    if not job_ids or not _slurm_available():
        return {}

    result: dict[str, dict] = {}

    # -- squeue: running / pending jobs --
    try:
        # Filter to only our job IDs to avoid scanning all users' jobs
        cp = subprocess.run(
            ['squeue', '-o', '%i|%T', '--noheader',
             '-u', os.environ.get('USER', '')],
            capture_output=True, text=True, timeout=10,
        )
        if cp.returncode == 0:
            for line in cp.stdout.strip().splitlines():
                parts = line.strip().split('|')
                if len(parts) >= 2 and parts[0] in job_ids:
                    result[parts[0]] = {'state': parts[1], 'exit_code': ''}
    except (OSError, subprocess.TimeoutExpired):
        pass

    # -- sacct: completed / failed jobs --
    remaining = job_ids - set(result.keys())
    if remaining:
        try:
            # Build comma-separated job list
            job_list = ','.join(remaining)
            cp = subprocess.run(
                ['sacct', '-j', job_list, '-o', 'JobID,State,ExitCode',
                 '--noheader', '-P'],
                capture_output=True, text=True, timeout=10,
            )
            if cp.returncode == 0:
                for line in cp.stdout.strip().splitlines():
                    parts = line.strip().split('|')
                    if len(parts) >= 2:
                        jid = parts[0]
                        # Filter out job steps (.batch, .extern, .0, etc.)
                        if '.' in jid:
                            continue
                        if jid in job_ids:
                            exit_code = parts[2] if len(parts) >= 3 else ''
                            result[jid] = {
                                'state': parts[1],
                                'exit_code': exit_code,
                            }
        except (OSError, subprocess.TimeoutExpired):
            pass

    return result


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------

_RUNNING_STATES = {'RUNNING', 'PENDING', 'CONFIGURING', 'COMPLETING',
                   'REQUEUED', 'SUSPENDED'}


def _compute_va_state(rec: JobRecord) -> str:
    """Determine the VaspAuto-level job state."""
    slurm = rec.slurm_state

    if slurm and slurm in _RUNNING_STATES:
        return 'running'
    if slurm == 'COMPLETED':
        if rec.end_ts:
            return 'completed'
        else:
            return 'unexpected_exit'
    if slurm == 'FAILED':
        return 'failed'
    if slurm == 'TIMEOUT':
        return 'timeout'
    if slurm == 'CANCELLED':
        return 'cancelled'
    if slurm == 'NODE_FAIL':
        return 'node_fail'
    if slurm == 'OUT_OF_MEMORY':
        return 'oom'

    # No Slurm data — rely on history alone
    if rec.end_ts:
        return 'completed'
    if rec.start_ts:
        return 'unknown'          # was running, Slurm DB purged
    if rec.job_id:
        return 'unknown'          # submitted, no further info
    return 'script_only'          # -o mode, never submitted


_VA_STATE_LABELS = {
    'running':         'running',
    'completed':       'completed',
    'unexpected_exit': 'unexpected exit',
    'failed':          'failed',
    'timeout':         'timeout',
    'cancelled':       'cancelled',
    'node_fail':       'node fail',
    'oom':             'out of memory',
    'unknown':         'unknown',
    'script_only':     'script only',
}


def _compute_statuses(records: list[JobRecord]) -> None:
    """Enrich records with Slurm state and VA state.

    Mutates records in-place.
    """
    # Collect all numeric job IDs
    job_ids: set[str] = set()
    for rec in records:
        if rec.job_id and rec.job_id.isdigit():
            job_ids.add(rec.job_id)

    # Batch query Slurm
    slurm_data = _query_slurm_batch(job_ids) if job_ids else {}

    for rec in records:
        if rec.job_id and rec.job_id in slurm_data:
            rec.slurm_state = slurm_data[rec.job_id].get('state')
        else:
            rec.slurm_state = None
        rec.va_state = _compute_va_state(rec)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _filter_records(records: list[JobRecord],
                    running_only: bool = False,
                    failed_only: bool = False,
                    ) -> list[JobRecord]:
    if running_only:
        return [r for r in records if r.va_state == 'running']
    if failed_only:
        return [r for r in records if r.va_state in (
            'unexpected_exit', 'failed', 'timeout', 'node_fail', 'oom',
        )]
    return records


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _fmt_ts(iso: str) -> str:
    """Format ISO 8601 timestamp for compact display."""
    if not iso:
        return '-'
    try:
        # Handle both '2026-07-06T15:30:00+08:00' and '2026-07-06T15:30:00'
        s = iso.replace('T', ' ')
        if '+' in s:
            s = s[:s.index('+')]
        elif s.endswith('Z'):
            s = s[:-1]
        dt = datetime.fromisoformat(s)
        return dt.strftime('%m-%d %H:%M')
    except (ValueError, IndexError):
        return iso[:16] if len(iso) >= 16 else iso


def _fmt_elapsed(seconds: Optional[float]) -> str:
    if seconds is None:
        return '-'
    if seconds < 60:
        return f'{seconds:.0f}s'
    if seconds < 3600:
        return f'{seconds / 60:.1f}m'
    return f'{seconds / 3600:.1f}h'


def _fmt_results(results: Optional[dict]) -> str:
    if not results:
        return '-'
    total = results.get('total', 0)
    skipped = results.get('skipped', 0)
    finished = results.get('finished', 0)
    failed = results.get('failed', 0)
    # Exclude skipped calcs (handled by other jobs) from the denominator
    active = total - skipped
    return f'{finished}/{active}' + ('⚠' if failed else '')


_SLURM_COLORS = {
    'RUNNING':     '\033[32m',   # green
    'PENDING':     '\033[33m',   # yellow
    'COMPLETED':   '\033[34m',   # blue
    'FAILED':      '\033[31m',   # red
    'TIMEOUT':     '\033[31m',
    'CANCELLED':   '\033[31m',
    'NODE_FAIL':   '\033[31m',
    'OUT_OF_MEMORY': '\033[31m',
}
_RESET = '\033[0m'


def _shorten_path(path: str) -> str:
    """Return the shortest readable form of *path*.

    Compares the absolute path with a ``~/``-relative form and returns
    whichever is shorter.
    """
    if not path:
        return '-'
    home = str(Path.home())
    if path.startswith(home + os.sep):
        rel = '~' + path[len(home):]
        return rel if len(rel) <= len(path) else path
    return path


def _format_table(records: list[JobRecord],
                  slurm_ok: bool) -> str:
    """Build a human-readable table."""
    if not records:
        return '(no jobs found)'

    # Pre-compute display paths
    display_paths = [_shorten_path(r.work_dir or '') for r in records]

    # Column widths (dynamically computed)
    widths = {
        'job_id': 8,
        'name': 12,
        'submit': 11,
        'slurm': 10,
        'va': 15,
        'results': 7,
        'elapsed': 6,
        'work_dir': 20,
    }

    # Compute max column widths from data
    for r, wd in zip(records, display_paths):
        widths['job_id'] = max(widths['job_id'], len(r.job_id or '-'))
        widths['name'] = max(widths['name'], len(r.job_name or ''))
        widths['slurm'] = max(widths['slurm'],
                              len(r.slurm_state or '(no slurm)'))
        widths['va'] = max(widths['va'],
                           len(_VA_STATE_LABELS.get(r.va_state, r.va_state)))
        widths['work_dir'] = max(widths['work_dir'], len(wd))

    # Cap work_dir width to avoid excessively wide tables
    widths['work_dir'] = min(widths['work_dir'], 50)

    def _row(cols: list[str]) -> str:
        return '  '.join(cols)

    def _header(col: str, w: int) -> str:
        return col.ljust(w)

    header = _row([
        _header('Job ID', widths['job_id']),
        _header('Name', widths['name']),
        _header('Submit', widths['submit']),
        _header('Slurm', widths['slurm']),
        _header('VA State', widths['va']),
        _header('Results', widths['results']),
        _header('Elap', widths['elapsed']),
        _header('Work Dir', widths['work_dir']),
    ])

    lines = [header, '-' * len(header)]

    for r, wd_display in zip(records, display_paths):
        job_id = r.job_id or '-'
        name = (r.job_name or '')[:widths['name']]
        submit = _fmt_ts(r.submit_ts)

        # Slurm state (with color)
        slurm_raw = r.slurm_state or ('-' if slurm_ok else '(no slurm)')
        slurm_color = _SLURM_COLORS.get(slurm_raw, '')
        slurm_str = f'{slurm_color}{slurm_raw}{_RESET}' if slurm_color else slurm_raw
        slurm_pad = slurm_str + ' ' * (widths['slurm'] - len(slurm_raw))

        va_label = _VA_STATE_LABELS.get(r.va_state, r.va_state)

        results_str = _fmt_results(r.results)
        elapsed_str = _fmt_elapsed(r.elapsed_s)

        # Truncate if still too long
        wd = wd_display
        if len(wd) > widths['work_dir']:
            wd = '…' + wd[-(widths['work_dir'] - 1):]

        lines.append(_row([
            job_id.ljust(widths['job_id']),
            name.ljust(widths['name']),
            submit.ljust(widths['submit']),
            slurm_pad,
            va_label.ljust(widths['va']),
            results_str.ljust(widths['results']),
            elapsed_str.ljust(widths['elapsed']),
            wd,
        ]))

    return '\n'.join(lines)


def _format_json(records: list[JobRecord]) -> str:
    """Output as JSON array."""
    out = []
    for r in records:
        out.append({
            'job_id': r.job_id,
            'job_name': r.job_name,
            'submit_ts': r.submit_ts,
            'start_ts': r.start_ts,
            'end_ts': r.end_ts,
            'config': r.config,
            'work_dir': r.work_dir,
            'task_type': r.task_type,
            'partition': r.partition,
            'nodes': r.nodes,
            'ntasks': r.ntasks,
            'cpus_per_task': r.cpus_per_task,
            'host': r.host,
            'slurm_state': r.slurm_state,
            'va_state': r.va_state,
            'elapsed_s': r.elapsed_s,
            'results': r.results,
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description='show job status from global history log + Slurm',
        prog='vaspauto log',
    )
    parser.add_argument('-a', '--all', dest='show_all', action='store_true',
                        help='show all jobs (default: last 5)')
    parser.add_argument('--recent', dest='recent', type=int, default=5,
                        help='show last N jobs (default: 5)')
    parser.add_argument('--running', dest='running', action='store_true',
                        help='only show running / pending jobs')
    parser.add_argument('--failed', dest='failed', action='store_true',
                        help='only show failed / unexpected-exit jobs')
    parser.add_argument('--json', dest='json_out', action='store_true',
                        help='output as JSON')
    args = parser.parse_args(argv)

    # Read history
    records = _read_history()
    if not records:
        print('(no job history found)', flush=True)
        return

    # Most recent first
    records.reverse()

    # Enrich with Slurm data
    _compute_statuses(records)

    # Filter
    records = _filter_records(records,
                              running_only=args.running,
                              failed_only=args.failed)

    # Limit
    if not args.show_all and not args.running and not args.failed:
        limit = args.recent
        records = records[:limit]

    # Output
    slurm_ok = _slurm_available()
    if args.json_out:
        print(_format_json(records))
    else:
        print(_format_table(records, slurm_ok))
        if not slurm_ok:
            print('\n[Slurm commands not available — Slurm state from history only]')


if __name__ == '__main__':
    main()
