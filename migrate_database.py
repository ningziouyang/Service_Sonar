"""Idempotent SQLite schema migration for Service Sonar."""

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


DB_FILE = Path(__file__).with_name("service_sonar.db")

FEATURE_TABLES = {
    "trend_snapshots": """
        CREATE TABLE IF NOT EXISTS trend_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            snapshot_json TEXT NOT NULL,
            comparison_json TEXT
        )
    """,
    "evaluation_reports": """
        CREATE TABLE IF NOT EXISTS evaluation_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            report_json TEXT NOT NULL
        )
    """,
    "system_alerts": """
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
    """,
}


def ensure_feature_tables(connection: sqlite3.Connection) -> list[str]:
    """Create missing feature tables and return the tables that were added."""
    existing = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    created = [name for name in FEATURE_TABLES if name not in existing]

    with connection:
        for statement in FEATURE_TABLES.values():
            connection.execute(statement)

    return created


def migrate_database(db_file: str | Path = DB_FILE, backup: bool = True) -> dict:
    db_path = Path(db_file).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_path = None
    if backup:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = db_path.with_name(f"{db_path.stem}.before-migration-{timestamp}.db")
        shutil.copy2(db_path, backup_path)

    connection = sqlite3.connect(db_path)
    try:
        created = ensure_feature_tables(connection)
        verified = {
            name: connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            ).fetchone()[0]
            == 1
            for name in FEATURE_TABLES
        }
    finally:
        connection.close()

    return {
        "database": str(db_path),
        "backup": str(backup_path) if backup_path else None,
        "created": created,
        "verified": verified,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate the Service Sonar database schema.")
    parser.add_argument("--db-file", default=str(DB_FILE))
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    result = migrate_database(args.db_file, backup=not args.no_backup)
    print(f"Database: {result['database']}")
    if result["backup"]:
        print(f"Backup: {result['backup']}")
    print("Created: " + (", ".join(result["created"]) or "none (already current)"))
    for table, ok in result["verified"].items():
        print(f"{table}: {'OK' if ok else 'MISSING'}")
