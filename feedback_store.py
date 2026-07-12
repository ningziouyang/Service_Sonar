"""Stakeholder feedback storage for Agent 4 service opportunities."""

import sqlite3
from datetime import datetime


DB_FILE = "service_sonar.db"

DECISIONS = [
    "Aufgegriffen",
    "Vorgemerkt",
    "Nicht zuständig",
    "Andere Lösung nötig",
]

FEEDBACK_MIN_SIGNALS = 5


def make_key(title: str) -> str:
    """Create a stable-ish identifier from an opportunity title."""
    return " ".join((title or "").strip().lower().split())


def _connect(db_file: str = DB_FILE) -> sqlite3.Connection:
    return sqlite3.connect(db_file)


def init_feedback_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_feedback (
            opportunity_key TEXT PRIMARY KEY,
            opportunity_title TEXT,
            decision TEXT,
            note TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()


def set_feedback(
    opportunity_key: str,
    opportunity_title: str,
    decision: str,
    note: str = "",
    db_file: str = DB_FILE,
) -> None:
    conn = _connect(db_file)
    try:
        init_feedback_table(conn)
        conn.execute(
            """
            INSERT INTO opportunity_feedback
                (opportunity_key, opportunity_title, decision, note, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(opportunity_key) DO UPDATE SET
                opportunity_title = excluded.opportunity_title,
                decision = excluded.decision,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                opportunity_key,
                opportunity_title,
                decision,
                note,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_feedback_map(db_file: str = DB_FILE) -> dict:
    """Return feedback keyed by opportunity_key."""
    conn = _connect(db_file)
    try:
        init_feedback_table(conn)
        rows = conn.execute(
            """
            SELECT opportunity_key, opportunity_title, decision, note, updated_at
            FROM opportunity_feedback
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        row[0]: {
            "title": row[1],
            "decision": row[2],
            "note": row[3],
            "updated_at": row[4],
        }
        for row in rows
    }


def summarize_feedback_for_prompt(db_file: str = DB_FILE) -> str:
    """Summarize enough stakeholder feedback as a soft Agent 4 generation hint."""
    feedback = get_feedback_map(db_file)
    if len(feedback) < FEEDBACK_MIN_SIGNALS:
        return ""

    liked = []
    rejected = []

    for entry in feedback.values():
        decision = entry.get("decision")
        title = entry.get("title") or ""

        if decision == "Aufgegriffen":
            liked.append(title)
        elif decision in {"Nicht zuständig", "Andere Lösung nötig"}:
            rejected.append(title)

    if not liked and not rejected:
        return ""

    parts = []
    if liked:
        parts.append(
            "Von Stakeholdern aufgegriffen (mehr in dieser Richtung): "
            + "; ".join(liked[:8])
        )
    if rejected:
        parts.append(
            "Von Stakeholdern abgelehnt (anderen Ansatz wählen): "
            + "; ".join(rejected[:8])
        )

    return "\n".join(parts)
