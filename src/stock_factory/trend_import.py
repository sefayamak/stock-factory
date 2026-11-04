"""Stage 1b: manual-import adapter for Magnific Search Trends.

contributor.magnific.com/search-trends is a JS-rendered, login-gated SPA
(confirmed BLOCKED in docs/PLATFORM_RULES.md -- no static fetch or official
export API exists). Scraping an authenticated contributor session is not
attempted here: it would require bypassing login/anti-bot protections,
which this project does not do.

The reliable, authorized alternative: the account owner opens the page in
their own authenticated browser, and either copies the visible trend terms
or exports them (if the UI ever offers one) into a small JSON/CSV snapshot
file dropped into TREND_SNAPSHOT_DIR. This module ingests that snapshot,
keeps a historical record of every import (never silently overwriting a
prior snapshot), de-duplicates identical re-imports, and scores what moved
between the two most recent snapshots -- new terms, dropped terms, and
rank/volume changes.

This is explicitly NOT live monitoring: it is only as fresh as the most
recent human-provided snapshot. Callers must not represent it as such.
"""
from __future__ import annotations
import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config

SNAPSHOT_EXTS = {'.json', '.csv'}


@dataclass
class TrendTerm:
    term: str
    category: str = ''
    rank: int | None = None
    volume: float | None = None

    def key(self) -> str:
        return self.term.strip().lower()


@dataclass
class Snapshot:
    imported_at: str
    source_file: str
    sha256: str
    terms: list[TrendTerm] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'imported_at': self.imported_at,
            'source_file': self.source_file,
            'sha256': self.sha256,
            'terms': [vars(t) for t in self.terms],
        }

    @staticmethod
    def from_dict(d: dict) -> 'Snapshot':
        return Snapshot(
            imported_at=d['imported_at'],
            source_file=d['source_file'],
            sha256=d['sha256'],
            terms=[TrendTerm(**t) for t in d.get('terms', [])],
        )


def _history_dir() -> Path:
    return config.STATE_DIR / 'trend_history'


def _index_path() -> Path:
    return _history_dir() / 'index.jsonl'


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_terms(path: Path, data: bytes) -> list[TrendTerm]:
    if path.suffix.lower() == '.json':
        payload = json.loads(data.decode('utf-8'))
        rows = payload if isinstance(payload, list) else payload.get('terms', [])
        return [
            TrendTerm(
                term=str(r['term']),
                category=str(r.get('category', '')),
                rank=int(r['rank']) if r.get('rank') is not None else None,
                volume=float(r['volume']) if r.get('volume') is not None else None,
            )
            for r in rows
        ]
    if path.suffix.lower() == '.csv':
        text = data.decode('utf-8')
        reader = csv.DictReader(text.splitlines())
        return [
            TrendTerm(
                term=str(r['term']),
                category=str(r.get('category') or ''),
                rank=int(r['rank']) if r.get('rank') else None,
                volume=float(r['volume']) if r.get('volume') else None,
            )
            for r in reader
        ]
    raise ValueError(f'unsupported snapshot format: {path.suffix}')


def load_history() -> list[Snapshot]:
    index_path = _index_path()
    if not index_path.exists():
        return []
    snapshots = []
    for line in index_path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            snapshots.append(Snapshot.from_dict(json.loads(line)))
    return snapshots


def import_snapshot(path: Path) -> dict:
    """Ingest one manually-provided trend snapshot file. Returns a status
    dict. A byte-identical re-import of the same snapshot is recorded as a
    duplicate and skipped, so re-running an import job is always safe."""
    if path.suffix.lower() not in SNAPSHOT_EXTS:
        raise ValueError(f'unsupported snapshot format: {path.suffix}')

    data = path.read_bytes()
    digest = _sha256_bytes(data)

    history = load_history()
    if any(s.sha256 == digest for s in history):
        return {'imported': False, 'reason': 'duplicate_snapshot', 'sha256': digest, 'file': path.name}

    terms = _parse_terms(path, data)
    snapshot = Snapshot(
        imported_at=datetime.now(timezone.utc).isoformat(),
        source_file=path.name,
        sha256=digest,
        terms=terms,
    )

    _history_dir().mkdir(parents=True, exist_ok=True)
    with _index_path().open('a', encoding='utf-8') as f:
        f.write(json.dumps(snapshot.to_dict()) + '\n')

    return {'imported': True, 'sha256': digest, 'file': path.name, 'term_count': len(terms)}


def score_trend_changes(previous: Snapshot, current: Snapshot) -> list[dict]:
    """Compares two snapshots and scores what changed: new terms, dropped
    terms, and rank/volume movement for terms present in both."""
    prev_by_key = {t.key(): t for t in previous.terms}
    curr_by_key = {t.key(): t for t in current.terms}
    changes = []

    for key, curr in curr_by_key.items():
        prev = prev_by_key.get(key)
        if prev is None:
            changes.append({'term': curr.term, 'status': 'new', 'rank': curr.rank, 'volume': curr.volume})
            continue
        rank_delta = (prev.rank - curr.rank) if (prev.rank is not None and curr.rank is not None) else None
        volume_delta = (curr.volume - prev.volume) if (prev.volume is not None and curr.volume is not None) else None
        if rank_delta is not None and rank_delta > 0:
            status = 'rising'
        elif rank_delta is not None and rank_delta < 0:
            status = 'falling'
        else:
            status = 'stable'
        changes.append({
            'term': curr.term, 'status': status,
            'rank': curr.rank, 'prev_rank': prev.rank, 'rank_delta': rank_delta,
            'volume': curr.volume, 'prev_volume': prev.volume, 'volume_delta': volume_delta,
        })

    for key, prev in prev_by_key.items():
        if key not in curr_by_key:
            changes.append({'term': prev.term, 'status': 'dropped', 'rank': None, 'prev_rank': prev.rank})

    # Rising/new terms first, by rank (lower rank number = more prominent).
    def sort_key(c: dict):
        order = {'new': 0, 'rising': 1, 'stable': 2, 'falling': 3, 'dropped': 4}
        return (order.get(c['status'], 5), c.get('rank') if c.get('rank') is not None else 999)

    return sorted(changes, key=sort_key)


def import_pending_snapshots(snapshot_dir: Path | None = None) -> list[dict]:
    """Scans snapshot_dir (default: config.TREND_SNAPSHOT_DIR) for new
    snapshot files, imports each one, and moves it to _claimed/ so a
    rerun never double-imports the same file -- mirrors the manual_inbox
    image adapter's claim pattern."""
    directory = snapshot_dir or config.TREND_SNAPSHOT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    claimed_dir = directory / '_claimed'
    claimed_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SNAPSHOT_EXTS):
        result = import_snapshot(path)
        results.append(result)
        path.rename(claimed_dir / path.name)
    return results


def latest_trend_report() -> dict | None:
    """Returns the most recent snapshot's trend-change report relative to
    the one before it, or None if fewer than two snapshots exist yet."""
    history = load_history()
    if len(history) < 2:
        return None
    previous, current = history[-2], history[-1]
    return {
        'previous_imported_at': previous.imported_at,
        'current_imported_at': current.imported_at,
        'changes': score_trend_changes(previous, current),
    }
