import argparse
import json
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


DB_FILE = "service_sonar.db"
VALID_CLUSTERS = {
    "Finanzen",
    "Studium",
    "Mentale Gesundheit",
    "Wohnen",
    "Sonstiges",
}
VALID_URGENCIES = {"Hoch", "Mittel", "Niedrig"}


class EvaluationEngine:
    """
    Systematic evaluation for LLM outputs.

    The engine samples Agent-3 records by cluster and checks whether cluster
    labels, urgency labels, stakeholder extraction and Agent-4 ideas are
    complete enough for decision support. It does not call an LLM, so it can run
    after every refresh without spending API quota.
    """

    def __init__(self, db_file=DB_FILE, samples_per_cluster=3, seed=42):
        self.db_file = db_file
        self.samples_per_cluster = max(1, int(samples_per_cluster))
        self.random = random.Random(seed)

    def _connect(self):
        return sqlite3.connect(self.db_file)

    def _init_table(self, cursor):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                report_json TEXT NOT NULL
            )
            """
        )

    def _safe_json_loads(self, raw_json):
        try:
            data = json.loads(raw_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _load_analyzed_records(self, cursor):
        cursor.execute(
            """
            SELECT id, cleaned_content, analysis_json
            FROM forum_posts
            WHERE status = 2 AND analysis_json IS NOT NULL
            ORDER BY id ASC
            """
        )
        return cursor.fetchall()

    def _load_latest_report(self, cursor):
        try:
            cursor.execute(
                """
                SELECT id, created_at, report_json
                FROM system_reports
                ORDER BY id DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        except sqlite3.OperationalError:
            return None

        if not row:
            return None

        return {
            "id": row[0],
            "created_at": row[1],
            "report": self._safe_json_loads(row[2]),
        }

    def _group_records(self, records):
        groups = defaultdict(list)
        parsed_records = []
        for db_id, cleaned_text, analysis_json in records:
            analysis = self._safe_json_loads(analysis_json)
            cluster = analysis.get("problem_cluster") or "Unbekannt"
            item = {
                "id": db_id,
                "text": cleaned_text or "",
                "analysis": analysis,
                "cluster": cluster,
            }
            groups[cluster].append(item)
            parsed_records.append(item)
        return parsed_records, groups

    def _score_record(self, item):
        analysis = item["analysis"]
        cluster = analysis.get("problem_cluster")
        urgency = analysis.get("urgency")
        tone = analysis.get("emotional_tone")
        stakeholders = analysis.get("stakeholders")
        text = item["text"]

        checks = {
            "cluster_present": bool(cluster),
            "cluster_known_or_composite": bool(cluster)
            and all(part.strip() in VALID_CLUSTERS for part in str(cluster).split("/")),
            "urgency_valid": urgency in VALID_URGENCIES,
            "tone_present": bool(tone),
            "stakeholders_present": isinstance(stakeholders, list) and bool(stakeholders),
            "source_text_sufficient": len(text) >= 60,
        }
        passed = sum(1 for value in checks.values() if value)
        return round((passed / len(checks)) * 100, 1), checks

    def _evaluate_clusters(self, groups):
        evaluations = []
        for cluster, items in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
            sample_size = min(self.samples_per_cluster, len(items))
            sample = self.random.sample(items, sample_size)
            scores = []
            failed_checks = Counter()

            for item in sample:
                score, checks = self._score_record(item)
                scores.append(score)
                for name, passed in checks.items():
                    if not passed:
                        failed_checks[name] += 1

            avg_score = round(sum(scores) / len(scores), 1) if scores else 0
            status = "good"
            if avg_score < 70:
                status = "needs_review"
            elif avg_score < 85:
                status = "watch"

            evaluations.append(
                {
                    "cluster": cluster,
                    "total_records": len(items),
                    "sampled_records": [item["id"] for item in sample],
                    "quality_score": avg_score,
                    "status": status,
                    "common_issues": dict(failed_checks.most_common()),
                }
            )

        return evaluations

    def _evaluate_service_ideas(self, latest_report, groups):
        if not latest_report:
            return {
                "available": False,
                "message": "Kein Agent-4-Report vorhanden.",
                "ideas": [],
            }

        report = latest_report["report"]
        innovations = report.get("innovations", [])
        if not isinstance(innovations, list):
            innovations = []

        cluster_names = set(groups.keys())
        idea_evaluations = []
        required_fields = {
            "cluster",
            "opportunity",
            "solution",
            "target",
            "stakeholder",
            "evidence",
            "implementation_steps",
            "risk",
        }

        for idea in innovations:
            if not isinstance(idea, dict):
                continue

            present_fields = {field for field in required_fields if idea.get(field)}
            implementation_steps = idea.get("implementation_steps")
            if not isinstance(implementation_steps, list):
                implementation_steps = []

            score = 0
            score += (len(present_fields) / len(required_fields)) * 40
            score += 20 if idea.get("cluster") in cluster_names else 8
            score += 20 if len(implementation_steps) >= 3 else len(implementation_steps) * 5
            score += 10 if len(str(idea.get("solution", ""))) >= 120 else 4
            score += 10 if len(str(idea.get("risk", ""))) >= 20 else 3
            score = round(min(score, 100), 1)

            if score >= 85:
                status = "strong"
            elif score >= 70:
                status = "usable"
            else:
                status = "needs_review"

            idea_evaluations.append(
                {
                    "opportunity": idea.get("opportunity", "Unbenannte Idee"),
                    "cluster": idea.get("cluster"),
                    "stakeholder": idea.get("stakeholder"),
                    "fit_score": score,
                    "status": status,
                    "missing_fields": sorted(required_fields - present_fields),
                }
            )

        return {
            "available": True,
            "source_report_id": latest_report["id"],
            "source_report_created_at": latest_report["created_at"],
            "ideas": idea_evaluations,
        }

    def run(self):
        conn = self._connect()
        cursor = conn.cursor()
        self._init_table(cursor)

        records = self._load_analyzed_records(cursor)
        parsed_records, groups = self._group_records(records)
        latest_report = self._load_latest_report(cursor)

        cluster_evaluations = self._evaluate_clusters(groups)
        service_idea_evaluation = self._evaluate_service_ideas(latest_report, groups)

        weak_clusters = [
            item for item in cluster_evaluations if item["status"] != "good"
        ]
        idea_scores = [
            item["fit_score"]
            for item in service_idea_evaluation.get("ideas", [])
            if isinstance(item.get("fit_score"), (int, float))
        ]

        report = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "method": "rule_based_sample_evaluator",
            "sample_policy": f"up to {self.samples_per_cluster} records per active cluster",
            "source_records": len(parsed_records),
            "active_clusters": len(groups),
            "cluster_evaluations": cluster_evaluations,
            "service_idea_evaluation": service_idea_evaluation,
            "summary": {
                "clusters_needing_review": len(weak_clusters),
                "average_service_idea_fit": round(sum(idea_scores) / len(idea_scores), 1)
                if idea_scores
                else None,
                "recommendation": (
                    "Cluster mit Status 'watch' oder 'needs_review' manuell prüfen; "
                    "Agent-4-Ideen mit niedrigem Fit-Score vor Stakeholder-Terminen überarbeiten."
                ),
            },
        }

        cursor.execute(
            "INSERT INTO evaluation_reports (report_json) VALUES (?)",
            (json.dumps(report, ensure_ascii=False, indent=2),),
        )
        conn.commit()
        conn.close()

        print(
            "[Evaluation Engine] Report gespeichert: "
            f"{len(cluster_evaluations)} Cluster, "
            f"{len(service_idea_evaluation.get('ideas', []))} Serviceideen bewertet."
        )
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate Agent-3 clusters and Agent-4 service ideas."
    )
    parser.add_argument("--db-file", default=DB_FILE, help="Path to SQLite database.")
    parser.add_argument(
        "--samples-per-cluster",
        type=int,
        default=3,
        help="How many analyzed records to sample from each active cluster.",
    )
    args = parser.parse_args()

    EvaluationEngine(
        db_file=args.db_file,
        samples_per_cluster=args.samples_per_cluster,
    ).run()
