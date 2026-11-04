"""Stage 7: acceptance/rejection tracking and download performance."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


class RunTracker:
    def __init__(self):
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.counts = {
            'fetched': 0, 'qc_passed': 0, 'qc_rejected': 0,
            'duplicate_rejected': 0, 'archived': 0, 'archive_skipped': 0,
        }
        self.rejections: list[dict] = []

    def record(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def record_rejection(self, filename: str, reason: str, stage: str) -> None:
        self.rejections.append({'file': filename, 'reason': reason, 'stage': stage})
        self.record('qc_rejected' if stage == 'qc' else 'duplicate_rejected')

    def finalize(self, state_dir: Path, day: str) -> dict:
        state_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            'day': day,
            'started_at': self.started_at,
            'finished_at': datetime.now(timezone.utc).isoformat(),
            'counts': self.counts,
            'rejections': self.rejections,
        }
        (state_dir / f'run-{day}.json').write_text(json.dumps(summary, indent=2))
        return summary
