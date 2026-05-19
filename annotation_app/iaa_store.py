import sqlite3
from pathlib import Path

from config import BASE_DIR


IAA_DB_PATH = Path(BASE_DIR) / "data" / "iaa_reviews.db"

PROMPT_FIELDS = [
    "prompt_q1_clarity_format",
    "prompt_q2_cultural_context",
    "prompt_q3_identity_relevance",
]

OUTPUT_FIELD_SUFFIXES = [
    "output_q1_hegemony_presence",
    "output_q2_axes_match",
    "output_q3_reasoning_quality",
    "output_q4_hegemony_severity",
]

OUTPUT_TARGETS = [
    "gemini_base",
    "gemini_identity",
    "gpt_base",
    "gpt_identity",
    "llama_base",
    "llama_identity",
    "deepseek_base",
    "deepseek_identity",
]

OUTPUT_FIELDS = [
    f"{target}_{suffix}"
    for target in OUTPUT_TARGETS
    for suffix in OUTPUT_FIELD_SUFFIXES
]

GROUND_TRUTH_FIELDS = [
    "groundtruth_q1_corrective_quality",
]

OPTIONAL_FIELDS = [
    "optional_comment",
    "reviewer_confidence",
    "admin_notes",
]

IAA_REVIEW_COLUMNS = (
    [
        "annotation_id",
        "reviewer_name",
        "reviewer_state",
        "annotation_creator",
        "review_timestamp",
        "editable",
        "completed",
    ]
    + PROMPT_FIELDS
    + OUTPUT_FIELDS
    + GROUND_TRUTH_FIELDS
    + OPTIONAL_FIELDS
)


def _connect():
    IAA_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(IAA_DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn):
    question_columns = ",\n        ".join(
        [f"{column} INTEGER" for column in (PROMPT_FIELDS + OUTPUT_FIELDS + GROUND_TRUTH_FIELDS)]
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS iaa_reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            annotation_id TEXT NOT NULL,
            reviewer_name TEXT NOT NULL,
            reviewer_state TEXT,
            annotation_creator TEXT,
            review_timestamp TEXT,
            editable INTEGER NOT NULL DEFAULT 1,
            completed INTEGER NOT NULL DEFAULT 0,
            {question_columns},
            optional_comment TEXT,
            reviewer_confidence INTEGER,
            admin_notes TEXT,
            UNIQUE(annotation_id, reviewer_name)
        )
        """
    )
    conn.commit()


def initialize_iaa_storage():
    with _connect():
        return str(IAA_DB_PATH)


def fetch_iaa_review(annotation_id, reviewer_name):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM iaa_reviews
            WHERE annotation_id = ? AND reviewer_name = ?
            LIMIT 1
            """,
            (str(annotation_id or "").strip(), str(reviewer_name or "").strip()),
        ).fetchone()
    return dict(row) if row else None


def list_completed_iaa_annotation_ids_for_reviewer(reviewer_name):
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT annotation_id
            FROM iaa_reviews
            WHERE reviewer_name = ? AND completed = 1
            """,
            (str(reviewer_name or "").strip(),),
        ).fetchall()
    return {
        str(row["annotation_id"]).strip()
        for row in rows
        if str(row["annotation_id"]).strip()
    }


def count_completed_iaa_reviews_by_annotation():
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT annotation_id, COUNT(*) AS review_count
            FROM iaa_reviews
            WHERE completed = 1
            GROUP BY annotation_id
            """
        ).fetchall()
    return {
        str(row["annotation_id"]).strip(): int(row["review_count"] or 0)
        for row in rows
        if str(row["annotation_id"]).strip()
    }


def save_iaa_review(payload):
    annotation_id = str(payload.get("annotation_id") or "").strip()
    reviewer_name = str(payload.get("reviewer_name") or "").strip()
    if not annotation_id or not reviewer_name:
        raise ValueError("annotation_id and reviewer_name are required.")

    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT review_id, completed, editable
            FROM iaa_reviews
            WHERE annotation_id = ? AND reviewer_name = ?
            LIMIT 1
            """,
            (annotation_id, reviewer_name),
        ).fetchone()

        if existing and int(existing["completed"] or 0) and not int(existing["editable"] or 0):
            raise PermissionError("This IAA review has already been submitted and locked.")

        values = [payload.get(column) for column in IAA_REVIEW_COLUMNS]
        if existing:
            set_clause = ", ".join(f"{column} = ?" for column in IAA_REVIEW_COLUMNS)
            conn.execute(
                f"""
                UPDATE iaa_reviews
                SET {set_clause}
                WHERE review_id = ?
                """,
                values + [int(existing["review_id"])],
            )
            conn.commit()
            return int(existing["review_id"]), "updated"

        placeholders = ", ".join("?" for _ in IAA_REVIEW_COLUMNS)
        conn.execute(
            f"""
            INSERT INTO iaa_reviews ({", ".join(IAA_REVIEW_COLUMNS)})
            VALUES ({placeholders})
            """,
            values,
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0]), "created"


def list_iaa_reviews_for_export():
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT review_id, {", ".join(IAA_REVIEW_COLUMNS)}
            FROM iaa_reviews
            ORDER BY review_id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
