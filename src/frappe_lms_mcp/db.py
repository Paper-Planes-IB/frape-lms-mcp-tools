"""SQLite database for the Frappe LMS MCP server.

Stores Frappe connections (with API keys), a course cache (for memory and
cross-instance re-upload), and an operation audit log.

The database file lives at ``data/frappe_lms.db`` relative to the package
data directory.  It is created lazily on first access.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_DB_DIR = _PACKAGE_DIR / ".." / ".." / "data"


def _db_path() -> Path:
    """Resolve the SQLite database path from env or default."""
    env_path = os.environ.get("FRAPPE_LMS_DB_PATH")
    if env_path:
        return Path(env_path)
    return (_DEFAULT_DB_DIR / "frappe_lms.db").resolve()


# Thread-local connection — SQLite connections are not safe to share across
# threads, so each thread gets its own.
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with row factory enabled."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_path = _db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS frappe_connections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    base_url    TEXT NOT NULL,
    site        TEXT NOT NULL DEFAULT 'lms.localhost',
    api_key     TEXT,                 -- nullable: not all users can generate API keys
    api_secret  TEXT,                 -- nullable: same as above
    password    TEXT,                 -- session-auth fallback (when no API keys)
    username    TEXT,                 -- the Frappe user (email)
    is_active   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course_cache (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id     INTEGER NOT NULL,
    frappe_course_id  TEXT NOT NULL,          -- slug in Frappe
    title             TEXT NOT NULL,
    slug              TEXT,
    chapter_count     INTEGER DEFAULT 0,
    lesson_count      INTEGER DEFAULT 0,
    quiz_count        INTEGER DEFAULT 0,
    spec_json         TEXT,                    -- full create_full_course spec
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (connection_id) REFERENCES frappe_connections(id) ON DELETE CASCADE,
    UNIQUE (connection_id, frappe_course_id)
);

CREATE TABLE IF NOT EXISTS operation_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id  INTEGER,
    operation      TEXT NOT NULL,             -- create / update / delete / reupload
    entity_type    TEXT NOT NULL,             -- course / chapter / lesson / quiz
    entity_name    TEXT,
    details_json   TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (connection_id) REFERENCES frappe_connections(id) ON DELETE SET NULL
);
"""

# Migration: add columns that may not exist in older databases.
_MIGRATIONS = [
    "ALTER TABLE frappe_connections ADD COLUMN password TEXT",
]

_initialized = False
_init_lock = threading.Lock()


def init_db() -> None:
    """Create tables if they don't exist yet.  Safe to call multiple times."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        conn = _get_conn()
        conn.executescript(_SCHEMA)
        # Run migrations (add columns to older databases).  Each ALTER TABLE
        # fails silently if the column already exists.
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        _initialized = True


# ---------------------------------------------------------------------------
# Connection CRUD
# ---------------------------------------------------------------------------

def add_connection(
    name: str,
    base_url: str,
    site: str,
    api_key: str = "",
    api_secret: str = "",
    password: str = "",
    username: str = "",
    activate: bool = True,
) -> dict[str, Any]:
    """Insert a new Frappe connection (and optionally activate it).

    Either ``api_key``/``api_secret`` (token auth) or ``password`` (session
    auth) should be provided.  If the user lacks the System Manager role needed
    to generate API keys, ``password`` is stored for session-based login.
    """
    init_db()
    conn = _get_conn()
    if activate:
        conn.execute("UPDATE frappe_connections SET is_active = 0")
    conn.execute(
        """INSERT INTO frappe_connections
               (name, base_url, site, api_key, api_secret, password, username, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, base_url, site, api_key or "", api_secret or "",
         password or "", username, 1 if activate else 0),
    )
    conn.commit()
    return get_connection_by_name(name)  # type: ignore[return-value]


def get_active_connection() -> dict[str, Any] | None:
    """Return the currently active connection, or ``None`` if none set."""
    init_db()
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM frappe_connections WHERE is_active = 1 LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def get_connection_by_name(name: str) -> dict[str, Any] | None:
    init_db()
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM frappe_connections WHERE name = ?", (name,)
    ).fetchone()
    return dict(row) if row else None


def get_connection_by_id(conn_id: int) -> dict[str, Any] | None:
    init_db()
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM frappe_connections WHERE id = ?", (conn_id,)
    ).fetchone()
    return dict(row) if row else None


def list_connections() -> list[dict[str, Any]]:
    """List all connections (api_secret and password masked for safety)."""
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM frappe_connections ORDER BY is_active DESC, name ASC"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        # Don't expose the full secret in listings.
        d["api_secret"] = d["api_secret"][:4] + "****" if d.get("api_secret") else ""
        d["password"] = "****" if d.get("password") else ""
        result.append(d)
    return result


def set_active_connection(conn_id: int) -> bool:
    """Activate a connection and deactivate all others."""
    init_db()
    conn = _get_conn()
    exists = conn.execute(
        "SELECT 1 FROM frappe_connections WHERE id = ?", (conn_id,)
    ).fetchone()
    if not exists:
        return False
    conn.execute("UPDATE frappe_connections SET is_active = 0")
    conn.execute(
        "UPDATE frappe_connections SET is_active = 1, updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), conn_id),
    )
    conn.commit()
    return True


def delete_connection(conn_id: int) -> bool:
    """Delete a connection. Returns True if a row was removed."""
    init_db()
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM frappe_connections WHERE id = ?", (conn_id,)
    )
    conn.commit()
    return cur.rowcount > 0


def update_connection(conn_id: int, **fields: Any) -> bool:
    """Update fields on a connection (e.g. rotate api_key)."""
    init_db()
    if not fields:
        return False
    conn = _get_conn()
    allowed = {"name", "base_url", "site", "api_key", "api_secret", "password", "username"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [conn_id]
    cur = conn.execute(
        f"UPDATE frappe_connections SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Course cache CRUD
# ---------------------------------------------------------------------------

def cache_course(
    connection_id: int,
    frappe_course_id: str,
    title: str,
    slug: str = "",
    chapter_count: int = 0,
    lesson_count: int = 0,
    quiz_count: int = 0,
    spec_json: str = "",
) -> dict[str, Any]:
    """Insert or update a cached course.  Returns the cached row."""
    init_db()
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    # Upsert: if (connection_id, frappe_course_id) exists, update; else insert.
    existing = conn.execute(
        "SELECT id FROM course_cache WHERE connection_id = ? AND frappe_course_id = ?",
        (connection_id, frappe_course_id),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE course_cache SET
                   title = ?, slug = ?, chapter_count = ?, lesson_count = ?,
                   quiz_count = ?, spec_json = ?, updated_at = ?
               WHERE id = ?""",
            (title, slug, chapter_count, lesson_count, quiz_count, spec_json, now, existing["id"]),
        )
        conn.commit()
        return dict(conn.execute(
            "SELECT * FROM course_cache WHERE id = ?", (existing["id"],)
        ).fetchone())
    cur = conn.execute(
        """INSERT INTO course_cache
               (connection_id, frappe_course_id, title, slug,
                chapter_count, lesson_count, quiz_count, spec_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (connection_id, frappe_course_id, title, slug,
         chapter_count, lesson_count, quiz_count, spec_json, now, now),
    )
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM course_cache WHERE id = ?", (cur.lastrowid,)
    ).fetchone())


def list_cached_courses(connection_id: int | None = None) -> list[dict[str, Any]]:
    """List cached courses, optionally filtered by connection."""
    init_db()
    conn = _get_conn()
    if connection_id is not None:
        rows = conn.execute(
            """SELECT cc.*, fc.name AS connection_name
               FROM course_cache cc
               JOIN frappe_connections fc ON fc.id = cc.connection_id
               WHERE cc.connection_id = ?
               ORDER BY cc.updated_at DESC""",
            (connection_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT cc.*, fc.name AS connection_name
               FROM course_cache cc
               JOIN frappe_connections fc ON fc.id = cc.connection_id
               ORDER BY cc.updated_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_cached_course(course_id: int) -> dict[str, Any] | None:
    """Get a single cached course by its cache ID."""
    init_db()
    conn = _get_conn()
    row = conn.execute(
        """SELECT cc.*, fc.name AS connection_name
           FROM course_cache cc
           JOIN frappe_connections fc ON fc.id = cc.connection_id
           WHERE cc.id = ?""",
        (course_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_cached_course(course_id: int) -> bool:
    """Remove a course from the cache (does NOT delete from Frappe)."""
    init_db()
    conn = _get_conn()
    cur = conn.execute("DELETE FROM course_cache WHERE id = ?", (course_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Operation log
# ---------------------------------------------------------------------------

def log_operation(
    connection_id: int | None,
    operation: str,
    entity_type: str,
    entity_name: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Append an entry to the audit log."""
    init_db()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO operation_log
               (connection_id, operation, entity_type, entity_name, details_json)
           VALUES (?, ?, ?, ?, ?)""",
        (
            connection_id,
            operation,
            entity_type,
            entity_name,
            json.dumps(details, ensure_ascii=False) if details else None,
        ),
    )
    conn.commit()


def list_operations(limit: int = 100) -> list[dict[str, Any]]:
    """List recent operations (most recent first)."""
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT ol.*, fc.name AS connection_name
           FROM operation_log ol
           LEFT JOIN frappe_connections fc ON fc.id = ol.connection_id
           ORDER BY ol.created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
