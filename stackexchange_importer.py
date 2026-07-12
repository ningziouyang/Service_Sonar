import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone
from html import unescape

import requests
from bs4 import BeautifulSoup


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


DB_FILE = "service_sonar.db"
DEFAULT_SITE = "academia"
DEFAULT_LIMIT = 200
DEFAULT_SLEEP_SECONDS = 1.0


class StackExchangeImporter:
    """
    Imports public Stack Exchange questions into the Service Sonar pipeline table.

    This is the no-key fallback when Reddit or Studis Online are unavailable. It
    stores question title/body/link/tags, but no usernames or profile metadata.
    """

    def __init__(
        self,
        db_file=DB_FILE,
        site=DEFAULT_SITE,
        limit=DEFAULT_LIMIT,
        tagged="",
        sleep_seconds=DEFAULT_SLEEP_SECONDS,
    ):
        self.db_file = db_file
        self.site = site.strip()
        self.limit = max(1, int(limit))
        self.tagged = tagged.strip()
        self.sleep_seconds = max(0.0, float(sleep_seconds))
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "ServiceSonarStudentResearch/0.1"}
        )

    def _initialisiere_datenbank(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS forum_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                raw_content TEXT,
                cleaned_content TEXT,
                analysis_json TEXT,
                status INTEGER DEFAULT 0,
                analysis_attempts INTEGER DEFAULT 0
            )
            """
        )
        try:
            cursor.execute(
                "ALTER TABLE forum_posts ADD COLUMN analysis_attempts INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    def _request_page(self, page):
        params = {
            "order": "desc",
            "sort": "creation",
            "site": self.site,
            "pagesize": min(100, self.limit),
            "page": page,
            "filter": "withbody",
        }
        if self.tagged:
            params["tagged"] = self.tagged

        response = self.session.get(
            "https://api.stackexchange.com/2.3/questions",
            params=params,
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()

        backoff = data.get("backoff")
        if backoff:
            print(f"[StackExchange] Backoff {backoff}s...")
            time.sleep(backoff)

        return data

    def fetch_questions(self):
        questions_by_url = {}
        page = 1

        print(
            f"[StackExchange] Sammle bis zu {self.limit} Fragen von "
            f"{self.site}.stackexchange.com..."
        )

        while len(questions_by_url) < self.limit:
            print(f"[StackExchange] Lade Seite {page}...")
            data = self._request_page(page)
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                normalized = self._normalize_question(item)
                if normalized:
                    questions_by_url[normalized["url"]] = normalized
                if len(questions_by_url) >= self.limit:
                    break

            if not data.get("has_more"):
                break

            page += 1
            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)

        return list(questions_by_url.values())[: self.limit]

    def _normalize_question(self, item):
        title = unescape((item.get("title") or "").strip())
        body_html = item.get("body") or ""
        body_text = BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)
        body_text = unescape(body_text).strip()
        url = item.get("link")
        tags = item.get("tags", [])

        if not title or not body_text or not url:
            return None

        created_at = ""
        created_utc = item.get("creation_date")
        if created_utc:
            created_at = datetime.fromtimestamp(
                created_utc,
                tz=timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S UTC")

        raw_content = (
            f"Quelle: Stack Exchange {self.site}\n"
            f"Kategorie: Tags: {', '.join(tags)}\n"
            f"Titel: {title}\n"
            f"URL: {url}\n"
            f"Erstellt: {created_at}\n"
            f"Score: {item.get('score', 0)}; Antworten: {item.get('answer_count', 0)}\n\n"
            f"Inhalt:\n{body_text}"
        )

        return {"url": url, "raw_content": raw_content, "title": title}

    def save_questions(self, questions):
        self._initialisiere_datenbank()

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        inserted = 0
        skipped = 0

        for question in questions:
            cursor.execute(
                """
                INSERT OR IGNORE INTO forum_posts (url, raw_content, status)
                VALUES (?, ?, 0)
                """,
                (question["url"], question["raw_content"]),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        conn.commit()
        conn.close()
        return inserted, skipped

    def run(self, dry_run=False):
        questions = self.fetch_questions()
        print(f"[StackExchange] Gefunden: {len(questions)} eindeutige Fragen.")

        if dry_run:
            for index, question in enumerate(questions[:10], start=1):
                print(f"{index}. {question['title']}")
            return len(questions), 0

        inserted, skipped = self.save_questions(questions)
        print(
            f"[StackExchange] Import beendet: {inserted} neu gespeichert; "
            f"{skipped} bereits vorhanden."
        )
        return inserted, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import public Stack Exchange questions into Service Sonar."
    )
    parser.add_argument("--db", default=DB_FILE, help="SQLite database path.")
    parser.add_argument(
        "--site",
        default=DEFAULT_SITE,
        help="Stack Exchange site parameter, e.g. academia.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of unique questions to import.",
    )
    parser.add_argument(
        "--tagged",
        default="",
        help="Optional semicolon-separated Stack Exchange tag filter.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Seconds to wait between API pages.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch questions and print sample titles without writing to the database.",
    )

    args = parser.parse_args()

    importer = StackExchangeImporter(
        db_file=args.db,
        site=args.site,
        limit=args.limit,
        tagged=args.tagged,
        sleep_seconds=args.sleep,
    )
    importer.run(dry_run=args.dry_run)
