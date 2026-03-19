"""SQLite database layer for speed test results."""
import sqlite3
import threading
from datetime import datetime, timezone

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    download_mbps REAL NOT NULL,
    upload_mbps   REAL NOT NULL,
    ping_ms       REAL NOT NULL,
    jitter_ms     REAL,
    packet_loss   REAL,
    server_id     INTEGER,
    server_name   TEXT,
    server_host   TEXT,
    isp           TEXT,
    external_ip   TEXT,
    result_url    TEXT,
    raw_json      TEXT
);
CREATE INDEX IF NOT EXISTS idx_results_ts ON results(timestamp);
"""


def get_db_path():
    import os
    return os.environ.get("SPEEDGAUGE_DB", "/data/speedgauge.db")


def _connect(db_path: str | None = None):
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | None = None):
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)


def save_result(result: dict, db_path: str | None = None) -> int:
    with _lock:
        with _connect(db_path) as conn:
            cur = conn.execute(
                """INSERT INTO results
                   (timestamp, download_mbps, upload_mbps, ping_ms, jitter_ms,
                    packet_loss, server_id, server_name, server_host,
                    isp, external_ip, result_url, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result["timestamp"],
                    result["download_mbps"],
                    result["upload_mbps"],
                    result["ping_ms"],
                    result.get("jitter_ms"),
                    result.get("packet_loss"),
                    result.get("server_id"),
                    result.get("server_name"),
                    result.get("server_host"),
                    result.get("isp"),
                    result.get("external_ip"),
                    result.get("result_url"),
                    result.get("raw_json"),
                ),
            )
            conn.commit()
            return cur.lastrowid


SORTABLE_COLUMNS = {"timestamp", "download_mbps", "upload_mbps", "ping_ms"}


def get_results(limit: int = 100, offset: int = 0, from_ts: str | None = None,
                to_ts: str | None = None, sort_by: str = "timestamp",
                sort_dir: str = "desc", db_path: str | None = None) -> list[dict]:
    if sort_by not in SORTABLE_COLUMNS:
        sort_by = "timestamp"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    with _connect(db_path) as conn:
        query = "SELECT * FROM results WHERE 1=1"
        params = []
        if from_ts:
            query += " AND timestamp >= ?"
            params.append(from_ts)
        if to_ts:
            query += " AND timestamp <= ?"
            params.append(to_ts)
        query += f" ORDER BY {sort_by} {sort_dir.upper()} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_latest(db_path: str | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM results ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_result_by_id(result_id: int, db_path: str | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM results WHERE id = ?", (result_id,)).fetchone()
        return dict(row) if row else None


def delete_result(result_id: int, db_path: str | None = None) -> bool:
    with _lock:
        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM results WHERE id = ?", (result_id,))
            conn.commit()
            return cur.rowcount > 0


def get_stats(period: str = "24h", db_path: str | None = None) -> dict:
    hours_map = {"24h": 24, "7d": 168, "30d": 720, "all": 0}
    hours = hours_map.get(period, 24)

    with _connect(db_path) as conn:
        query = """SELECT
            COUNT(*) as count,
            AVG(download_mbps) as avg_download,
            MIN(download_mbps) as min_download,
            MAX(download_mbps) as max_download,
            AVG(upload_mbps) as avg_upload,
            MIN(upload_mbps) as min_upload,
            MAX(upload_mbps) as max_upload,
            AVG(ping_ms) as avg_ping,
            MIN(ping_ms) as min_ping,
            MAX(ping_ms) as max_ping
            FROM results"""
        params = []
        if hours > 0:
            cutoff = datetime.now(timezone.utc).isoformat()
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            query += " WHERE timestamp >= ?"
            params.append(cutoff)
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else {}


def get_result_count(db_path: str | None = None) -> int:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM results").fetchone()
        return row["cnt"]


def cleanup_old_results(days: int, db_path: str | None = None) -> int:
    if days <= 0:
        return 0
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _lock:
        with _connect(db_path) as conn:
            cur = conn.execute("DELETE FROM results WHERE timestamp < ?", (cutoff,))
            conn.commit()
            return cur.rowcount
