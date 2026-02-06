"""SQLite database setup and CRUD operations."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH: Optional[Path] = None


def get_db_path() -> Path:
    """Get the database path."""
    if DB_PATH is None:
        return Path("archiver.db")
    return DB_PATH


def set_db_path(path: Path) -> None:
    """Set the database path."""
    global DB_PATH
    DB_PATH = path


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL UNIQUE,
            original_path TEXT NOT NULL,
            suggested_destination TEXT NOT NULL,
            final_destination TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'REVIEW',
            action_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL UNIQUE,
            summary_text TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_hash ON decisions(file_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summaries_hash ON summaries(file_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_file_hash ON chat_messages(file_hash)")

    conn.commit()
    conn.close()


# Decision CRUD operations

def get_decision(file_hash: str) -> Optional[dict]:
    """Get a decision by file hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM decisions WHERE file_hash = ?", (file_hash,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_decisions() -> list[dict]:
    """Get all decisions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM decisions")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_decision(
    file_hash: str,
    original_path: str,
    suggested_destination: str,
    final_destination: str,
    status: str = "REVIEW",
    action_type: Optional[str] = None,
) -> None:
    """Insert or update a decision."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO decisions (file_hash, original_path, suggested_destination, final_destination, status, action_type, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_hash) DO UPDATE SET
            final_destination = excluded.final_destination,
            status = excluded.status,
            action_type = excluded.action_type,
            updated_at = excluded.updated_at
    """, (file_hash, original_path, suggested_destination, final_destination, status, action_type, now))

    conn.commit()
    conn.close()


def update_decision_status(file_hash: str, status: str, action_type: str, final_destination: str) -> bool:
    """Update decision status and action."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE decisions
        SET status = ?, action_type = ?, final_destination = ?, updated_at = ?
        WHERE file_hash = ?
    """, (status, action_type, final_destination, now, file_hash))

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


# Summary CRUD operations

def get_cached_summary(file_hash: str) -> Optional[str]:
    """Get cached summary by file hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT summary_text FROM summaries WHERE file_hash = ?", (file_hash,))
    row = cursor.fetchone()
    conn.close()
    return row["summary_text"] if row else None


def cache_summary(file_hash: str, summary_text: str, model: str) -> None:
    """Cache a summary."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO summaries (file_hash, summary_text, model)
        VALUES (?, ?, ?)
        ON CONFLICT(file_hash) DO UPDATE SET
            summary_text = excluded.summary_text,
            model = excluded.model
    """, (file_hash, summary_text, model))

    conn.commit()
    conn.close()


# Stats

def get_decision_stats() -> dict:
    """Get decision statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM decisions")
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as approved FROM decisions WHERE status = 'APPROVED'")
    approved = cursor.fetchone()["approved"]

    cursor.execute("SELECT COUNT(*) as review FROM decisions WHERE status = 'REVIEW'")
    review = cursor.fetchone()["review"]

    conn.close()
    return {"total": total, "approved": approved, "review": review}


# Chat CRUD operations

def get_chat_history(file_hash: str) -> list[dict]:
    """Get chat history for a file."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, created_at FROM chat_messages WHERE file_hash = ? ORDER BY created_at ASC",
        (file_hash,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_chat_message(file_hash: str, role: str, content: str) -> None:
    """Add a chat message."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_messages (file_hash, role, content) VALUES (?, ?, ?)",
        (file_hash, role, content)
    )
    conn.commit()
    conn.close()


def clear_chat_history(file_hash: str) -> None:
    """Clear chat history for a file."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE file_hash = ?", (file_hash,))
    conn.commit()
    conn.close()
