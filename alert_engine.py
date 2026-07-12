import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


DB_FILE = "service_sonar.db"


class AlertEngine:
    """
    Rule-based proactive notifications for pipeline and trend anomalies.

    Alerts are intentionally deterministic and cheap: they reuse pipeline status
    counts, Agent-3 JSON and the latest trend snapshot instead of calling an LLM.
    """

    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def _init_table(self, cursor):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                severity TEXT,
                alert_type TEXT,
                title TEXT,
                message TEXT,
                metric_value REAL,
                threshold_value REAL,
                evidence_json TEXT,
                status TEXT DEFAULT 'open'
            )
            """
        )

    def _safe_json_loads(self, raw_json):
        try:
            data = json.loads(raw_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _status_counts(self, cursor):
        cursor.execute("SELECT status, COUNT(*) FROM forum_posts GROUP BY status")
        return {int(status): count for status, count in cursor.fetchall()}

    def _latest_trend_comparison(self, cursor):
        try:
            cursor.execute(
                """
                SELECT id, comparison_json
                FROM trend_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            return None, {}

        if not row:
            return None, {}

        return row[0], self._safe_json_loads(row[1])

    def _cluster_urgency_counts(self, cursor):
        cursor.execute(
            """
            SELECT analysis_json
            FROM forum_posts
            WHERE status = 2 AND analysis_json IS NOT NULL
            """
        )

        cluster_counts = Counter()
        high_urgency_by_cluster = Counter()
        for (raw_json,) in cursor.fetchall():
            analysis = self._safe_json_loads(raw_json)
            cluster = analysis.get("problem_cluster") or "Unbekannt"
            urgency = analysis.get("urgency") or "Unbekannt"
            cluster_counts[cluster] += 1
            if urgency == "Hoch":
                high_urgency_by_cluster[cluster] += 1

        return cluster_counts, high_urgency_by_cluster

    def _add_alert(
        self,
        alerts,
        alert_type,
        severity,
        title,
        message,
        metric_value,
        threshold_value,
        evidence=None,
    ):
        fingerprint = f"{alert_type}:{title}"
        alerts.append(
            {
                "fingerprint": fingerprint,
                "severity": severity,
                "alert_type": alert_type,
                "title": title,
                "message": message,
                "metric_value": metric_value,
                "threshold_value": threshold_value,
                "evidence": evidence or {},
            }
        )

    def evaluate(self):
        conn = self._connect()
        cursor = conn.cursor()
        self._init_table(cursor)

        status_counts = self._status_counts(cursor)
        trend_id, comparison = self._latest_trend_comparison(cursor)
        cluster_counts, high_urgency_by_cluster = self._cluster_urgency_counts(cursor)

        alerts = []
        total_posts = sum(status_counts.values())
        human_review = status_counts.get(3, 0)
        cleaned_queue = status_counts.get(1, 0)

        if human_review > 100:
            self._add_alert(
                alerts,
                "human_review_backlog",
                "critical",
                "Human-Review-Backlog über Schwelle",
                f"{human_review} Fälle warten auf Human Review.",
                human_review,
                100,
            )

        if total_posts and human_review / total_posts >= 0.2:
            self._add_alert(
                alerts,
                "human_review_share",
                "warning",
                "Hoher Anteil an Human-Review-Fällen",
                f"{round((human_review / total_posts) * 100, 1)}% aller Beiträge liegen im Human Review.",
                round((human_review / total_posts) * 100, 1),
                20,
            )

        if cleaned_queue > 100:
            self._add_alert(
                alerts,
                "agent3_queue",
                "warning",
                "Agent-3-Warteschlange wächst",
                f"{cleaned_queue} bereinigte Beiträge warten auf semantische Analyse.",
                cleaned_queue,
                100,
            )

        cluster_delta = comparison.get("cluster_delta", {}) if comparison else {}
        for cluster, values in cluster_delta.items():
            previous = values.get("previous", 0)
            change = values.get("change", 0)
            if previous > 0 and change > 0:
                growth_percent = (change / previous) * 100
                if growth_percent >= 50:
                    self._add_alert(
                        alerts,
                        "cluster_growth",
                        "warning",
                        f"Cluster '{cluster}' wächst auffällig",
                        f"{cluster} ist seit dem letzten Snapshot um {round(growth_percent, 1)}% gewachsen.",
                        round(growth_percent, 1),
                        50,
                        {"trend_snapshot_id": trend_id, "previous": previous, "change": change},
                    )

        total_high = sum(high_urgency_by_cluster.values())
        if total_high:
            cluster, count = high_urgency_by_cluster.most_common(1)[0]
            share = count / total_high
            if count >= 10 and share >= 0.5:
                self._add_alert(
                    alerts,
                    "high_urgency_concentration",
                    "warning",
                    f"High-Urgency-Fälle konzentrieren sich auf '{cluster}'",
                    f"{round(share * 100, 1)}% aller High-Urgency-Signale liegen in diesem Cluster.",
                    round(share * 100, 1),
                    50,
                    {"high_urgency_count": count, "total_high_urgency": total_high},
                )

        now = datetime.now().isoformat(timespec="seconds")
        active_fingerprints = {alert["fingerprint"] for alert in alerts}
        cursor.execute("UPDATE system_alerts SET status = 'resolved' WHERE status = 'open'")

        for alert in alerts:
            cursor.execute(
                """
                INSERT INTO system_alerts
                    (fingerprint, created_at, severity, alert_type, title, message,
                     metric_value, threshold_value, evidence_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                ON CONFLICT(fingerprint) DO UPDATE SET
                    created_at = excluded.created_at,
                    severity = excluded.severity,
                    message = excluded.message,
                    metric_value = excluded.metric_value,
                    threshold_value = excluded.threshold_value,
                    evidence_json = excluded.evidence_json,
                    status = 'open'
                """,
                (
                    alert["fingerprint"],
                    now,
                    alert["severity"],
                    alert["alert_type"],
                    alert["title"],
                    alert["message"],
                    alert["metric_value"],
                    alert["threshold_value"],
                    json.dumps(alert["evidence"], ensure_ascii=False),
                ),
            )

        conn.commit()
        conn.close()

        print(
            f"[Alert Engine] {len(active_fingerprints)} aktive Alerts geprüft/gespeichert."
        )
        return alerts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate proactive Service Sonar notification rules."
    )
    parser.add_argument("--db-file", default=DB_FILE, help="Path to SQLite database.")
    args = parser.parse_args()

    AlertEngine(db_file=args.db_file).evaluate()
