"""Immutable SQLite storage for normalized market detail rows."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class RawStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._migrate(connection)
        return connection

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                item_key TEXT NOT NULL,
                security_code TEXT,
                event_time TEXT NOT NULL,
                target_date TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                UNIQUE(kind, item_key, event_time, source, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_raw_query
                ON raw_observations(kind, security_code, event_time);

            CREATE TABLE IF NOT EXISTS bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                security_code TEXT NOT NULL,
                period TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                turnover_yuan REAL,
                amplitude_pct REAL,
                change_pct REAL,
                turnover_rate_pct REAL,
                adjust TEXT NOT NULL,
                source TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                UNIQUE(security_code, period, timestamp, adjust, source, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_bars_query
                ON bars(security_code, period, timestamp, adjust);

            PRAGMA user_version = 1;
            """
        )
        connection.commit()

    def insert_observations(
        self,
        kind: str,
        rows: Iterable[dict[str, Any]],
        *,
        target_date: str,
        observed_at: str,
        source: str,
    ) -> int:
        inserted = 0
        with self.connect() as connection:
            for row in rows:
                payload = dict(row.get("payload") or {})
                digest = content_hash(payload)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO raw_observations
                    (kind, item_key, security_code, event_time, target_date, observed_at,
                     source, payload_json, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        kind,
                        str(row["item_key"]),
                        row.get("security_code"),
                        str(row["event_time"]),
                        target_date,
                        observed_at,
                        source,
                        canonical_json(payload),
                        digest,
                    ),
                )
                inserted += int(cursor.rowcount > 0)
        return inserted

    def insert_bars(
        self,
        security_code: str,
        period: str,
        rows: Iterable[dict[str, Any]],
        *,
        adjust: str,
        source: str,
        observed_at: str,
    ) -> int:
        inserted = 0
        with self.connect() as connection:
            for row in rows:
                payload = {
                    key: row.get(key)
                    for key in (
                        "timestamp", "open", "high", "low", "close", "volume",
                        "turnover_yuan", "amplitude_pct", "change_pct", "turnover_rate_pct",
                    )
                }
                digest = content_hash(payload)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO bars
                    (security_code, period, timestamp, open, high, low, close, volume,
                     turnover_yuan, amplitude_pct, change_pct, turnover_rate_pct,
                     adjust, source, observed_at, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        security_code,
                        period,
                        str(row["timestamp"]),
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        row.get("close"),
                        row.get("volume"),
                        row.get("turnover_yuan"),
                        row.get("amplitude_pct"),
                        row.get("change_pct"),
                        row.get("turnover_rate_pct"),
                        adjust,
                        source,
                        observed_at,
                        digest,
                    ),
                )
                inserted += int(cursor.rowcount > 0)
        return inserted

    def query_observations(
        self,
        kind: str,
        *,
        security_code: str | None = None,
        start: str | None = None,
        end: str | None = None,
        at: str | None = None,
        target_date: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses = ["kind = ?"]
        parameters: list[Any] = [kind]
        if security_code:
            clauses.append("security_code = ?")
            parameters.append(security_code)
        if target_date:
            clauses.append("target_date = ?")
            parameters.append(target_date)
        if start:
            clauses.append("event_time >= ?")
            parameters.append(start)
        upper = at or end
        if upper:
            clauses.append("event_time <= ?")
            parameters.append(upper)
        parameters.append(limit)
        with self.connect() as connection:
            selected = connection.execute(
                f"""
                WITH ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY kind, item_key, event_time
                        ORDER BY observed_at DESC, id DESC
                    ) AS revision_rank
                    FROM raw_observations
                    WHERE {' AND '.join(clauses)}
                ), latest AS (
                    SELECT * FROM ranked
                    WHERE revision_rank = 1
                    ORDER BY event_time DESC, item_key DESC
                    LIMIT ?
                )
                SELECT * FROM latest
                ORDER BY event_time ASC, item_key ASC
                """,
                parameters,
            ).fetchall()
        return [{
            "kind": row["kind"],
            "item_key": row["item_key"],
            "security_code": row["security_code"],
            "event_time": row["event_time"],
            "target_date": row["target_date"],
            "observed_at": row["observed_at"],
            "source": row["source"],
            "fields": json.loads(row["payload_json"]),
        } for row in selected]

    def query_bars(
        self,
        security_code: str,
        period: str,
        *,
        adjust: str,
        start: str | None = None,
        end: str | None = None,
        at: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses = ["security_code = ?", "period = ?", "adjust = ?"]
        parameters: list[Any] = [security_code, period, adjust]
        if start:
            clauses.append("timestamp >= ?")
            parameters.append(start)
        upper = at or end
        if upper:
            clauses.append("timestamp <= ?")
            parameters.append(upper)
        parameters.append(limit)
        with self.connect() as connection:
            selected = connection.execute(
                f"""
                WITH ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY security_code, period, timestamp, adjust
                        ORDER BY observed_at DESC, id DESC
                    ) AS revision_rank
                    FROM bars
                    WHERE {' AND '.join(clauses)}
                )
                SELECT * FROM ranked
                WHERE revision_rank = 1
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        fields = (
            "security_code", "period", "timestamp", "open", "high", "low", "close",
            "volume", "turnover_yuan", "amplitude_pct", "change_pct", "turnover_rate_pct",
            "adjust", "source", "observed_at",
        )
        return [{field: row[field] for field in fields} for row in reversed(selected)]
