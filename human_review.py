import sqlite3
from datetime import datetime


STATUS_REJECTED = -1
STATUS_CLEANED = 1
STATUS_HUMAN_REVIEW = 3


class HumanReviewQueue:
    """
    Separater Human-Review-Schritt.

    Zweck:
    - Beiträge mit status=3 ansehen.
    - Mensch entscheidet: freigeben oder verwerfen.
    - Jede Entscheidung wird in human_review_log dokumentiert.
    """

    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file

    def _connect(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS human_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                reviewer_note TEXT,
                reviewed_at TEXT NOT NULL
            )
            """
        )
        return conn

    def list_pending(self, limit=10):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, cleaned_content
            FROM forum_posts
            WHERE status = ?
            ORDER BY id
            LIMIT ?
            """,
            (STATUS_HUMAN_REVIEW, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("[Human Review] Keine offenen Fälle mit status=3.")
            return

        print(f"[Human Review] Offene Fälle: {len(rows)} angezeigt\n")
        for post_id, content in rows:
            preview = (content or "")[:800]
            print("=" * 80)
            print(f"ID: {post_id}")
            print(preview)
            print("=" * 80)
            print()

    def approve(self, post_id: int, note: str = ""):
        """Gibt einen geprüften Beitrag frei. Danach kann Agent 3 ihn verarbeiten."""
        self._set_decision(post_id, STATUS_CLEANED, "approved", note)

    def reject(self, post_id: int, note: str = ""):
        """Verwirft einen geprüften Beitrag. Danach verlässt er die Pipeline."""
        self._set_decision(post_id, STATUS_REJECTED, "rejected", note)

    def _set_decision(self, post_id: int, new_status: int, decision: str, note: str):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE forum_posts SET status = ? WHERE id = ? AND status = ?",
            (new_status, post_id, STATUS_HUMAN_REVIEW),
        )

        if cursor.rowcount == 0:
            print(f"[Human Review WARNUNG] ID {post_id} ist nicht in status=3 oder existiert nicht.")
            conn.close()
            return

        cursor.execute(
            """
            INSERT INTO human_review_log (post_id, decision, reviewer_note, reviewed_at)
            VALUES (?, ?, ?, ?)
            """,
            (post_id, decision, note, datetime.now().isoformat(timespec="seconds")),
        )

        conn.commit()
        conn.close()
        print(f"[Human Review] ID {post_id} → {decision}, neuer Status: {new_status}")

    def report(self):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute("SELECT status, COUNT(*) FROM forum_posts GROUP BY status ORDER BY status")
        status_rows = cursor.fetchall()

        cursor.execute("SELECT decision, COUNT(*) FROM human_review_log GROUP BY decision")
        review_rows = cursor.fetchall()

        conn.close()

        print("\n========== Pipeline Status ==========")
        for status, count in status_rows:
            print(f"Status {status}: {count}")

        print("\n========== Human Review Log ==========")
        if not review_rows:
            print("Noch keine Review-Entscheidungen.")
        else:
            for decision, count in review_rows:
                print(f"{decision}: {count}")
        print("======================================")


if __name__ == "__main__":
    review = HumanReviewQueue()

    print("Befehle:")
    print("  list")
    print("  approve <id> [note]")
    print("  reject <id> [note]")
    print("  report")
    print("  quit")

    while True:
        command = input("human-review> ").strip()

        if command in {"quit", "exit", "q"}:
            break

        if command == "list":
            review.list_pending()
            continue

        if command == "report":
            review.report()
            continue

        if command.startswith("approve "):
            parts = command.split(maxsplit=2)
            post_id = int(parts[1])
            note = parts[2] if len(parts) > 2 else ""
            review.approve(post_id, note)
            continue

        if command.startswith("reject "):
            parts = command.split(maxsplit=2)
            post_id = int(parts[1])
            note = parts[2] if len(parts) > 2 else ""
            review.reject(post_id, note)
            continue

        print("Unbekannter Befehl. Nutze: list, approve <id>, reject <id>, report, quit")
