import argparse
import json
import sqlite3
import sys
from datetime import datetime


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


class TrendTracker:
    """
    Speichert Snapshots des aktuellen Datenbankstands und vergleicht sie mit dem vorherigen Lauf.

    Ziel:
    Nicht nur den aktuellen Stand anzeigen, sondern Veränderungen zwischen Refresh-Runs erkennen.
    """

    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def _init_table(self, cursor):
        """
        Erstellt eine Tabelle für Trend-Snapshots, falls sie noch nicht existiert.
        """
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                snapshot_json TEXT NOT NULL,
                comparison_json TEXT
            )
            """
        )

    def _count_by_status(self, cursor):
        """
        Zählt Beiträge nach Pipeline-Status.
        """
        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM forum_posts
            GROUP BY status
            ORDER BY status
            """
        )

        return {str(status): count for status, count in cursor.fetchall()}

    def _count_by_cluster(self, cursor):
        """
        Zählt analysierte Beiträge nach problem_cluster aus analysis_json.
        """
        cursor.execute(
            """
            SELECT analysis_json
            FROM forum_posts
            WHERE status = 2
              AND analysis_json IS NOT NULL
            """
        )

        cluster_counts = {}

        for (raw_json,) in cursor.fetchall():
            data = self._safe_json_loads(raw_json)
            cluster = data.get("problem_cluster", "Unbekannt")

            if not cluster:
                cluster = "Unbekannt"

            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

        return dict(sorted(cluster_counts.items(), key=lambda item: item[1], reverse=True))

    def _count_by_urgency(self, cursor):
        """
        Zählt analysierte Beiträge nach Dringlichkeit.
        """
        cursor.execute(
            """
            SELECT analysis_json
            FROM forum_posts
            WHERE status = 2
              AND analysis_json IS NOT NULL
            """
        )

        urgency_counts = {}

        for (raw_json,) in cursor.fetchall():
            data = self._safe_json_loads(raw_json)
            urgency = data.get("urgency", "Unbekannt")

            if not urgency:
                urgency = "Unbekannt"

            urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1

        return dict(sorted(urgency_counts.items(), key=lambda item: item[1], reverse=True))

    def _count_by_stakeholder(self, cursor):
        """
        Zählt, wie oft Stakeholder in analysierten Beiträgen genannt werden.
        """
        cursor.execute(
            """
            SELECT analysis_json
            FROM forum_posts
            WHERE status = 2
              AND analysis_json IS NOT NULL
            """
        )

        stakeholder_counts = {}

        for (raw_json,) in cursor.fetchall():
            data = self._safe_json_loads(raw_json)
            stakeholders = data.get("stakeholders", [])

            if not isinstance(stakeholders, list):
                continue

            for stakeholder in stakeholders:
                if not stakeholder:
                    continue

                stakeholder_counts[stakeholder] = stakeholder_counts.get(stakeholder, 0) + 1

        sorted_stakeholders = sorted(
            stakeholder_counts.items(),
            key=lambda item: item[1],
            reverse=True
        )

        top_stakeholders = {
            stakeholder: count
            for stakeholder, count in sorted_stakeholders
            if count >= 2
        }

        return dict(list(top_stakeholders.items())[:20])

    def _safe_json_loads(self, raw_json):
        """
        Wandelt JSON-Strings sicher in Dictionaries um.
        """
        try:
            data = json.loads(raw_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _load_previous_snapshot(self, cursor):
        """
        Lädt den letzten gespeicherten Snapshot.
        """
        cursor.execute(
            """
            SELECT id, created_at, snapshot_json
            FROM trend_snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        )

        row = cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "created_at": row[1],
            "snapshot": self._safe_json_loads(row[2]),
        }

    def _calculate_delta(self, current_counts, previous_counts):
        """
        Berechnet Differenzen zwischen aktuellem und vorherigem Snapshot.
        """
        all_keys = set(current_counts.keys()) | set(previous_counts.keys())
        delta = {}

        for key in all_keys:
            current_value = current_counts.get(key, 0)
            previous_value = previous_counts.get(key, 0)
            change = current_value - previous_value

            if change != 0:
                delta[key] = {
                    "previous": previous_value,
                    "current": current_value,
                    "change": change,
                }

        return dict(sorted(delta.items(), key=lambda item: abs(item[1]["change"]), reverse=True))

    def _compare_snapshots(self, current_snapshot, previous_snapshot):
        """
        Vergleicht den aktuellen Snapshot mit dem vorherigen Snapshot.
        """
        if not previous_snapshot:
            return {
                "available": False,
                "message": "Kein vorheriger Snapshot vorhanden. Dieser Lauf erstellt die Baseline.",
            }

        previous = previous_snapshot["snapshot"]

        comparison = {
            "available": True,
            "previous_snapshot_id": previous_snapshot["id"],
            "previous_created_at": previous_snapshot["created_at"],
            "total_posts_change": (
                current_snapshot["total_posts"] - previous.get("total_posts", 0)
            ),
            "analyzed_posts_change": (
                current_snapshot["analyzed_posts"] - previous.get("analyzed_posts", 0)
            ),
            "human_review_change": (
                current_snapshot["human_review_posts"] - previous.get("human_review_posts", 0)
            ),
            "status_delta": self._calculate_delta(
                current_snapshot["status_counts"],
                previous.get("status_counts", {}),
            ),
            "cluster_delta": self._calculate_delta(
                current_snapshot["cluster_counts"],
                previous.get("cluster_counts", {}),
            ),
            "urgency_delta": self._calculate_delta(
                current_snapshot["urgency_counts"],
                previous.get("urgency_counts", {}),
            ),
            "stakeholder_delta": self._calculate_delta(
                current_snapshot["stakeholder_counts"],
                previous.get("stakeholder_counts", {}),
            ),
        }

        comparison["highlights"] = self._build_highlights(comparison)
        return comparison

    def _build_highlights(self, comparison):
        """
        Erstellt kurze, lesbare Hinweise zu auffälligen Veränderungen.
        """
        highlights = []

        if not comparison.get("available"):
            return highlights

        if comparison["total_posts_change"] > 0:
            highlights.append(
                f"{comparison['total_posts_change']} neue Beiträge seit dem letzten Snapshot."
            )

        cleaned_delta = comparison.get("status_delta", {}).get("1")
        if cleaned_delta and cleaned_delta["change"] > 0:
            highlights.append(
                f"{cleaned_delta['change']} neue bereinigte Beiträge warten auf Agent-3-Analyse."
            )

        if comparison["analyzed_posts_change"] > 0:
            highlights.append(
                f"{comparison['analyzed_posts_change']} neue analysierte Beiträge seit dem letzten Snapshot."
            )

        if comparison["human_review_change"] > 0:
            highlights.append(
                f"{comparison['human_review_change']} zusätzliche Human-Review-Fälle."
            )

        for cluster, values in list(comparison["cluster_delta"].items())[:3]:
            if values["change"] > 0:
                highlights.append(
                    f"Cluster '{cluster}' ist um {values['change']} Beiträge gewachsen."
                )

        for urgency, values in comparison["urgency_delta"].items():
            if urgency == "Hoch" and values["change"] > 0:
                highlights.append(
                    f"Beiträge mit hoher Dringlichkeit sind um {values['change']} gestiegen."
                )

        if not highlights:
            highlights.append("Keine auffälligen Veränderungen seit dem letzten Snapshot.")

        return highlights

    def create_snapshot(self):
        """
        Erstellt einen neuen Snapshot des aktuellen Datenbankstands.
        """
        conn = self._connect()
        cursor = conn.cursor()
        self._init_table(cursor)

        cursor.execute("SELECT COUNT(*) FROM forum_posts")
        total_posts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM forum_posts WHERE status = 2")
        analyzed_posts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM forum_posts WHERE status = 3")
        human_review_posts = cursor.fetchone()[0]

        snapshot = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total_posts": total_posts,
            "analyzed_posts": analyzed_posts,
            "human_review_posts": human_review_posts,
            "status_counts": self._count_by_status(cursor),
            "cluster_counts": self._count_by_cluster(cursor),
            "urgency_counts": self._count_by_urgency(cursor),
            "stakeholder_counts": self._count_by_stakeholder(cursor),
        }

        previous_snapshot = self._load_previous_snapshot(cursor)
        comparison = self._compare_snapshots(snapshot, previous_snapshot)

        cursor.execute(
            """
            INSERT INTO trend_snapshots (snapshot_json, comparison_json)
            VALUES (?, ?)
            """,
            (
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                json.dumps(comparison, ensure_ascii=False, indent=2),
            )
        )

        conn.commit()
        conn.close()

        report = {
            "snapshot": snapshot,
            "comparison": comparison,
        }

        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("\n[Trend Tracker] Snapshot gespeichert und Vergleich abgeschlossen.")

        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Speichert einen Trend-Snapshot und vergleicht ihn mit dem vorherigen Lauf."
    )
    parser.add_argument(
        "--db-file",
        default="service_sonar.db",
        help="Pfad zur SQLite-Datenbank."
    )

    args = parser.parse_args()

    tracker = TrendTracker(db_file=args.db_file)
    tracker.create_snapshot()
