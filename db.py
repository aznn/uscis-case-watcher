"""
SQLite database module for USCIS Case Watcher.
Stores change history and silent updates for queryable timeline construction.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB_PATH = SCRIPT_DIR / "output" / "history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    case_number TEXT NOT NULL,
    source_key TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    is_silent INTEGER NOT NULL DEFAULT 0,
    diff_json TEXT,
    summary TEXT,
    UNIQUE(nickname, detected_at, source_key)
);

CREATE INDEX IF NOT EXISTS idx_changes_nickname ON changes(nickname);
CREATE INDEX IF NOT EXISTS idx_changes_detected_at ON changes(detected_at);
"""


def get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open or create the history database. Sets WAL mode for concurrent read/write."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def record_change(
    conn: sqlite3.Connection,
    nickname: str,
    case_number: str,
    source_key: str,
    detected_at: str,
    diff_json: Optional[dict] = None,
    summary: Optional[str] = None,
    is_silent: bool = False,
) -> None:
    """Insert a change record. Silently ignores duplicates (same nickname+timestamp+source)."""
    conn.execute(
        """INSERT OR IGNORE INTO changes
           (nickname, case_number, source_key, detected_at, is_silent, diff_json, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            nickname,
            case_number,
            source_key,
            detected_at,
            1 if is_silent else 0,
            json.dumps(diff_json) if diff_json is not None else None,
            summary,
        ),
    )
    conn.commit()


def get_changes(
    conn: sqlite3.Connection,
    nickname: Optional[str] = None,
    source_key: Optional[str] = None,
    since: Optional[str] = None,
    include_silent: bool = True,
    limit: int = 100,
) -> list[dict]:
    """Query change records with optional filters."""
    query = "SELECT * FROM changes WHERE 1=1"
    params: list = []

    if nickname:
        query += " AND nickname = ?"
        params.append(nickname)
    if source_key:
        query += " AND source_key = ?"
        params.append(source_key)
    if since:
        query += " AND detected_at >= ?"
        params.append(since)
    if not include_silent:
        query += " AND is_silent = 0"

    query += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        if d["diff_json"]:
            d["diff_json"] = json.loads(d["diff_json"])
        results.append(d)
    return results


def get_timeline(
    conn: sqlite3.Connection,
    nickname: Optional[str] = None,
) -> list[dict]:
    """Get all changes and silent updates sorted chronologically (oldest first)."""
    query = "SELECT * FROM changes WHERE 1=1"
    params: list = []

    if nickname:
        query += " AND nickname = ?"
        params.append(nickname)

    query += " ORDER BY detected_at ASC"

    rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        if d["diff_json"]:
            d["diff_json"] = json.loads(d["diff_json"])
        results.append(d)
    return results
