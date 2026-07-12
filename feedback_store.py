"""
DSR Stakeholder-Feedback-Loop for Service Sonar.

Stores an institution's decision about each Agent 4 Service Opportunity.
This is the *evaluate* half of the design-science cycle: the artifact proposes
a service idea, a stakeholder responds, and that response is captured as
evaluation data (and can later feed back into prioritisation).

The feedback is a judgement about the proposed *idea*, never about whether the
underlying student need is valid.
"""

import sqlite3
from datetime import datetime

DB_FILE = "service_sonar.db"

# Respectful, idea-focused decision states (never a verdict on the problem):
#   Aufgegriffen         -> the institution is acting on this idea
#   Vorgemerkt           -> acknowledged, on the radar, not acting yet
#   Nicht zuständig      -> wrong owner for us; route elsewhere, keep the idea
#   Andere Lösung nötig  -> the need is valid but THIS idea misses -> ask Agent 4 for a new one
DECISIONS = ["Aufgegriffen", "Vorgemerkt", "Nicht zuständig", "Andere Lösung nötig"]


def make_key(title: str) -> str:
    """Stable-ish identifier for an opportunity, derived from its title."""
    return " ".join((title or "").strip().lower().split())


def _connect(db_file: str = DB_FILE) -> sqlite3.Connection:
    return sqlite3.connect(db_file)


def init_feedback_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS opportunity_feedback (
            opportunity_key   TEXT PRIMARY KEY,
            opportunity_title TEXT,
            decision          TEXT,
            note              TEXT,
            updated_at        TEXT
        )
        """
    )
    conn.commit()


def set_feedback(opportunity_key: str, opportunity_title: str,
                 decision: str, note: str = "", db_file: str = DB_FILE) -> None:
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
                decision          = excluded.decision,
                note              = excluded.note,
                updated_at        = excluded.updated_at
            """,
            (opportunity_key, opportunity_title, decision, note,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def get_feedback_map(db_file: str = DB_FILE) -> dict:
    """Returns {opportunity_key: {title, decision, note, updated_at}}."""
    conn = _connect(db_file)
    try:
        init_feedback_table(conn)
        rows = conn.execute(
            "SELECT opportunity_key, opportunity_title, decision, note, updated_at "
            "FROM opportunity_feedback"
        ).fetchall()
    finally:
        conn.close()
    return {
        r[0]: {"title": r[1], "decision": r[2], "note": r[3], "updated_at": r[4]}
        for r in rows
    }

FEEDBACK_MIN_SIGNALS = 5  # stay silent until this many decisions exist

def summarize_feedback_for_prompt(db_file: str = DB_FILE) -> str:
    """
    Returns a short German nudge describing which kinds of ideas stakeholders
    took up vs. rejected. Returns "" until there is enough feedback, so it
    cannot bias generation on thin data.
    """
    fb = get_feedback_map(db_file)
    if len(fb) < FEEDBACK_MIN_SIGNALS:
        return ""

    liked, rejected = [], []
    for entry in fb.values():
        decision = entry.get("decision")
        title = entry.get("title") or ""
        if decision == "Aufgegriffen":
            liked.append(title)
        elif decision in ("Nicht zuständig", "Andere Lösung nötig"):
            rejected.append(title)

    if not liked and not rejected:
        return ""

    parts = []
    if liked:
        parts.append("Von Stakeholdern aufgegriffen (mehr in dieser Richtung): "
                     + "; ".join(liked[:8]))
    if rejected:
        parts.append("Von Stakeholdern abgelehnt (anderen Ansatz waehlen): "
                     + "; ".join(rejected[:8]))
    return "\n".join(parts)