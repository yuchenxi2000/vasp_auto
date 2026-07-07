"""
Global job history log, written to ~/.config/vaspauto/history.jsonl.

One line per event (JSONL).  Three event types:
  - submit    — job submitted or script generated (by submit.py)
  - job_start — Job.run() begins execution (by job.py inside Slurm job)
  - job_end   — Job.run() completes with result summary (by job.py)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class JobLogger:
    """Append-only JSONL logger for VaspAuto job history.

    Writes to a *global* file (all projects share one log), so users can
    inspect their full submission / execution history in one place.
    """

    _instance = None

    def __init__(self):
        self._log_path = (
            Path.home() / '.config' / 'vaspauto' / 'history.jsonl'
        )

    @property
    def path(self) -> Path:
        return self._log_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, entry: dict) -> None:
        """Append a JSON record with an auto-added ``ts`` field."""
        entry['ts'] = self._now_iso()
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n'
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, 'a') as f:
                f.write(line)
        except Exception as exc:
            print(f'[vaspauto] warning: failed to write history log: {exc}',
                  file=sys.stderr)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        """ISO 8601 with local timezone offset, seconds precision.

        Example: ``"2026-07-06T15:30:00+08:00"``
        """
        tz = datetime.now(timezone.utc).astimezone().tzinfo
        return datetime.now(tz).isoformat(timespec='seconds')
