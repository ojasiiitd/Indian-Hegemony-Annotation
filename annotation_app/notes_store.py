import os
import re
import sqlite3
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(BASE_DIR, "data", "drafts")


def _safe_username(username):
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(username or "").strip())
    return cleaned or "user"


def _db_path_for_user(username):
    return os.path.join(NOTES_DIR, f"{_safe_username(username)}_notes.db")


def _ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT NOT NULL,
            state TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _connect_for_user(username):
    os.makedirs(NOTES_DIR, exist_ok=True)
    conn = sqlite3.connect(_db_path_for_user(username))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _human_readable_date(iso_value):
    raw = str(iso_value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%d %b %Y")
    except ValueError:
        # Fallback for unexpected formats.
        return raw[:10]


def list_notes(username, limit=200):
    with _connect_for_user(username) as conn:
        rows = conn.execute(
            """
            SELECT id, prompt, state, created_at
            FROM notes
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    notes = []
    for row in rows:
        item = dict(row)
        item["created_date"] = _human_readable_date(item.get("created_at"))
        notes.append(item)
    return notes


def save_note(username, prompt, state=""):
    clean_prompt = str(prompt or "").strip()
    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    created_at = datetime.utcnow().isoformat()
    with _connect_for_user(username) as conn:
        conn.execute(
            "INSERT INTO notes (prompt, state, created_at) VALUES (?, ?, ?)",
            (clean_prompt, str(state or "").strip(), created_at),
        )
        conn.commit()


def delete_note(username, note_id):
    try:
        parsed_note_id = int(note_id)
    except (TypeError, ValueError):
        return False

    with _connect_for_user(username) as conn:
        cursor = conn.execute("DELETE FROM notes WHERE id = ?", (parsed_note_id,))
        conn.commit()
        return cursor.rowcount > 0
