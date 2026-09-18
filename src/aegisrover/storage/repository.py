"""Versioned record repository with optimistic concurrency and cursor pagination.

The repository is the platform's single source of truth for mission records, map
revisions, session state and operational settings. Every write bumps a per-record
version and records an immutable history row, so a caller that read version *n* can
detect that somebody else already wrote version *n + 1* instead of silently
overwriting it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

__all__ = ('Record', 'Page', 'VersionConflict', 'NotFound', 'Repository', 'canonical_json')


def canonical_json(value: Any) -> str:
    """Deterministic JSON used for digests and stored payloads."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _digest(ns: str, key: str, version: int, payload: Any, updated_at: float) -> str:
    material = '\x1f'.join((ns, key, str(version), canonical_json(payload), f'{updated_at:.6f}'))
    return hashlib.sha256(material.encode()).hexdigest()


class VersionConflict(RuntimeError):
    """Raised when a write is based on a stale version."""

    def __init__(self, ns: str, key: str, expected: int, actual: int | None):
        super().__init__(f'{ns}/{key}: expected version {expected}, found {actual}')
        self.ns = ns
        self.key = key
        self.expected = expected
        self.actual = actual


class NotFound(KeyError):
    """Raised when a record does not exist."""

    def __init__(self, ns: str, key: str):
        super().__init__(f'{ns}/{key}')
        self.ns = ns
        self.key = key


@dataclass(frozen=True)
class Record:
    ns: str
    key: str
    version: int
    payload: Any
    etag: str
    updated_at: float
    deleted: bool = False

    def to_dict(self) -> dict:
        return {
            'namespace': self.ns,
            'key': self.key,
            'version': self.version,
            'payload': self.payload,
            'etag': self.etag,
            'updated_at': self.updated_at,
            'deleted': self.deleted,
        }


@dataclass(frozen=True)
class Page:
    items: tuple[Record, ...]
    cursor: str | None
    has_more: bool

    def to_dict(self) -> dict:
        return {'items': [i.to_dict() for i in self.items], 'cursor': self.cursor, 'has_more': self.has_more}


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    ns TEXT NOT NULL,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    etag TEXT NOT NULL,
    updated_at REAL NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ns, key)
);
CREATE TABLE IF NOT EXISTS record_history (
    ns TEXT NOT NULL,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload TEXT NOT NULL,
    etag TEXT NOT NULL,
    updated_at REAL NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    recorded_at REAL NOT NULL,
    PRIMARY KEY (ns, key, version)
);
CREATE INDEX IF NOT EXISTS records_ns_key ON records (ns, key);
"""


class Repository:
    """SQLite-backed versioned repository.

    Parameters
    ----------
    path:
        Filesystem path for the database, or ``':memory:'`` for tests.
    clock:
        Callable returning the current time; injectable so tests are deterministic.
    """

    def __init__(self, path: str = ':memory:', clock=time.time):
        self.path = path
        self._clock = clock
        self._conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA foreign_keys=ON')
        self._conn.executescript(SCHEMA)

    # -- reads -----------------------------------------------------------------
    def get(self, ns: str, key: str, *, include_deleted: bool = False) -> Record:
        row = self._conn.execute(
            'SELECT ns, key, version, payload, etag, updated_at, deleted FROM records WHERE ns=? AND key=?',
            (ns, key),
        ).fetchone()
        if row is None or (row['deleted'] and not include_deleted):
            raise NotFound(ns, key)
        return self._record(row)

    def maybe_get(self, ns: str, key: str) -> Record | None:
        try:
            return self.get(ns, key)
        except NotFound:
            return None

    def history(self, ns: str, key: str) -> tuple[Record, ...]:
        rows = self._conn.execute(
            'SELECT ns, key, version, payload, etag, updated_at, deleted FROM record_history'
            ' WHERE ns=? AND key=? ORDER BY version',
            (ns, key),
        ).fetchall()
        return tuple(self._record(r) for r in rows)

    def namespaces(self) -> tuple[str, ...]:
        rows = self._conn.execute('SELECT DISTINCT ns FROM records ORDER BY ns').fetchall()
        return tuple(r['ns'] for r in rows)

    # -- writes ----------------------------------------------------------------
    def put(self, ns: str, key: str, payload: Any, *, expected: int | None = None) -> Record:
        """Insert or update ``payload``.

        ``expected=None`` means "create or overwrite unconditionally"; pass the
        version you read to get optimistic concurrency instead.
        """
        self._conn.execute('BEGIN IMMEDIATE')
        try:
            row = self._conn.execute(
                'SELECT version, deleted FROM records WHERE ns=? AND key=?', (ns, key)
            ).fetchone()
            current = None if row is None else int(row['version'])
            if expected is not None:
                if current is None or current != expected:
                    raise VersionConflict(ns, key, expected, current)
            version = 1 if current is None else current + 1
            updated_at = self._clock()
            etag = _digest(ns, key, version, payload, updated_at)
            body = canonical_json(payload)
            self._conn.execute(
                'INSERT INTO records (ns, key, version, payload, etag, updated_at, deleted)'
                ' VALUES (?,?,?,?,?,?,0)'
                ' ON CONFLICT(ns, key) DO UPDATE SET version=excluded.version, payload=excluded.payload,'
                ' etag=excluded.etag, updated_at=excluded.updated_at, deleted=0',
                (ns, key, version, body, etag, updated_at),
            )
            self._conn.execute(
                'INSERT INTO record_history (ns, key, version, payload, etag, updated_at, deleted, recorded_at)'
                ' VALUES (?,?,?,?,?,?,0,?)',
                (ns, key, version, body, etag, updated_at, self._clock()),
            )
            self._conn.execute('COMMIT')
        except Exception:
            self._conn.execute('ROLLBACK')
            raise
        return Record(ns, key, version, payload, etag, updated_at)

    def delete(self, ns: str, key: str, *, expected: int | None = None) -> Record:
        """Tombstone a record. History is preserved."""
        self._conn.execute('BEGIN IMMEDIATE')
        try:
            row = self._conn.execute(
                'SELECT version, payload FROM records WHERE ns=? AND key=? AND deleted=0', (ns, key)
            ).fetchone()
            if row is None:
                raise NotFound(ns, key)
            current = int(row['version'])
            if expected is not None and expected != current:
                raise VersionConflict(ns, key, expected, current)
            version = current + 1
            updated_at = self._clock()
            etag = _digest(ns, key, version, None, updated_at)
            self._conn.execute(
                'UPDATE records SET version=?, deleted=1, etag=?, updated_at=? WHERE ns=? AND key=?',
                (version, etag, updated_at, ns, key),
            )
            self._conn.execute(
                'INSERT INTO record_history (ns, key, version, payload, etag, updated_at, deleted, recorded_at)'
                ' VALUES (?,?,?,?,?,?,1,?)',
                (ns, key, version, row['payload'], etag, updated_at, self._clock()),
            )
            self._conn.execute('COMMIT')
        except Exception:
            self._conn.execute('ROLLBACK')
            raise
        return Record(ns, key, version, None, etag, updated_at, deleted=True)

    # -- paging ----------------------------------------------------------------
    def page(self, ns: str, *, limit: int = 50, cursor: str | None = None, prefix: str = '') -> Page:
        """Stable keyset pagination ordered by key.

        ``cursor`` is an opaque encoding of the last key returned. Callers must treat
        it as opaque; the implementation is free to change it.
        """
        if limit <= 0:
            raise ValueError('limit must be positive')
        after = _decode_cursor(cursor) if cursor else ''
        rows = self._conn.execute(
            'SELECT ns, key, version, payload, etag, updated_at, deleted FROM records'
            ' WHERE ns=? AND deleted=0 AND key>? AND key LIKE ? ORDER BY key LIMIT ?',
            (ns, after, f'{prefix}%', limit + 1),
        ).fetchall()
        has_more = len(rows) > limit
        selected = rows[:limit]
        items = tuple(self._record(r) for r in selected)
        next_cursor = _encode_cursor(selected[-1]['key']) if selected else None
        return Page(items, next_cursor if has_more else None, has_more)

    def scan(self, ns: str, prefix: str = '') -> Iterator[Record]:
        cursor = None
        while True:
            page = self.page(ns, limit=200, cursor=cursor, prefix=prefix)
            yield from page.items
            if not page.has_more:
                return
            cursor = page.cursor

    def count(self, ns: str, prefix: str = '') -> int:
        row = self._conn.execute(
            'SELECT COUNT(*) AS n FROM records WHERE ns=? AND deleted=0 AND key LIKE ?',
            (ns, f'{prefix}%'),
        ).fetchone()
        return int(row['n'])

    def last_key(self, ns: str) -> str | None:
        """Highest key in ``ns``; append-only logs use this to find their head."""
        row = self._conn.execute(
            'SELECT key FROM records WHERE ns=? AND deleted=0 ORDER BY key DESC LIMIT 1', (ns,)
        ).fetchone()
        return None if row is None else row['key']

    def close(self) -> None:
        self._conn.close()

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _record(row: sqlite3.Row) -> Record:
        return Record(
            ns=row['ns'],
            key=row['key'],
            version=int(row['version']),
            payload=json.loads(row['payload']) if row['payload'] is not None else None,
            etag=row['etag'],
            updated_at=float(row['updated_at']),
            deleted=bool(row['deleted']),
        )


def _encode_cursor(key: str) -> str:
    import base64

    return base64.urlsafe_b64encode(key.encode()).decode().rstrip('=')


def _decode_cursor(cursor: str) -> str:
    import base64

    padding = '=' * (-len(cursor) % 4)
    return base64.urlsafe_b64decode(cursor + padding).decode()
