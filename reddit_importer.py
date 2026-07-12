import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from html import unescape

import requests


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


DB_FILE = "service_sonar.db"
DEFAULT_SUBREDDIT = "Studium"
DEFAULT_LIMIT = 200
DEFAULT_SLEEP_SECONDS = 1.2

DEFAULT_SEARCH_TERMS = [
    "BAföG",
    "Bafög",
    "Wohnung",
    "Erstsemester",
    "überfordert",
    "Prüfungsangst",
    "Studienabbruch",
    "psychologische Beratung",
    "Beratung",
    "Wartezeit",
    "Ausländerbehörde",
    "Nebenjob",
]

DEFAULT_USER_AGENT = (
    "ServiceSonarStudentResearch/0.1 "
    "(local academic prototype; set REDDIT_USER_AGENT for your Reddit username)"
)


class RedditImporter:
    """
    Imports public Reddit posts into the existing forum_posts pipeline table.

    The importer intentionally stores no Reddit usernames. It keeps only the
    title, body text, permalink, and lightweight post metadata needed by the
    Service Sonar pipeline.
    """

    def __init__(
        self,
        db_file=DB_FILE,
        subreddit=DEFAULT_SUBREDDIT,
        limit=DEFAULT_LIMIT,
        search_terms=None,
        sleep_seconds=DEFAULT_SLEEP_SECONDS,
        require_body=False,
        user_agent=None,
    ):
        self.db_file = db_file
        self.subreddit = subreddit.strip()
        if self.subreddit.lower().startswith("r/"):
            self.subreddit = self.subreddit[2:]
        self.limit = max(1, int(limit))
        self.search_terms = search_terms or DEFAULT_SEARCH_TERMS
        self.sleep_seconds = max(0.0, float(sleep_seconds))
        self.require_body = require_body
        self.user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", DEFAULT_USER_AGENT)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.access_token = None

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

    def _authenticate_if_possible(self):
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")

        if not client_id or not client_secret:
            print(
                "[Reddit] Keine OAuth-Daten gefunden. Versuche öffentlichen "
                ".json-Zugriff. Falls Reddit blockt: REDDIT_CLIENT_ID und "
                "REDDIT_CLIENT_SECRET setzen."
            )
            return

        response = self.session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            timeout=20,
        )
        response.raise_for_status()
        token_data = response.json()
        self.access_token = token_data["access_token"]
        print("[Reddit] OAuth aktiv.")

    def _request_json(self, path, params):
        params = dict(params)
        params["raw_json"] = 1

        headers = {}
        if self.access_token:
            base_url = "https://oauth.reddit.com"
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:
            base_url = "https://www.reddit.com"

        url = f"{base_url}{path}"
        for attempt in range(1, 4):
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=25,
            )

            if response.status_code == 429:
                wait_seconds = int(response.headers.get("Retry-After", "30"))
                print(f"[Reddit] Rate limit. Warte {wait_seconds}s...")
                time.sleep(wait_seconds)
                continue

            if response.status_code in {401, 403} and not self.access_token:
                raise RuntimeError(
                    "Reddit blockt den öffentlichen Zugriff. Bitte OAuth-Daten setzen: "
                    "REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET und REDDIT_USER_AGENT."
                )

            try:
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as error:
                print(f"[Reddit] Request-Fehler Versuch {attempt}/3: {error}")
                time.sleep(2 * attempt)

        raise RuntimeError(f"Reddit konnte nicht geladen werden: {url}")

    def _collect_from_listing(self, path, params, target, source_label):
        after = None
        count = 0

        while len(target) < self.limit:
            page_params = dict(params)
            page_params["limit"] = min(100, self.limit - len(target))
            if after:
                page_params["after"] = after
                page_params["count"] = count

            data = self._request_json(path, page_params)
            listing = data.get("data", {})
            children = listing.get("children", [])

            if not children:
                break

            for child in children:
                post = child.get("data", {})
                normalized = self._normalize_post(post, source_label)
                if normalized:
                    target[normalized["url"]] = normalized
                if len(target) >= self.limit:
                    break

            after = listing.get("after")
            count += len(children)
            if not after:
                break

            if self.sleep_seconds:
                time.sleep(self.sleep_seconds)

    def _normalize_post(self, post, source_label):
        if post.get("stickied") or post.get("over_18"):
            return None

        title = unescape((post.get("title") or "").strip())
        body = unescape((post.get("selftext") or "").strip())
        if body.lower() in {"[removed]", "[deleted]"}:
            body = ""

        if not title:
            return None
        if self.require_body and not body:
            return None

        permalink = post.get("permalink")
        if not permalink:
            return None

        url = f"https://www.reddit.com{permalink}"
        created_utc = post.get("created_utc")
        created_at = ""
        if created_utc:
            created_at = datetime.fromtimestamp(
                created_utc,
                tz=timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S UTC")

        raw_content = self._build_raw_content(
            source_label=source_label,
            title=title,
            body=body,
            url=url,
            created_at=created_at,
            score=post.get("score", 0),
            comments=post.get("num_comments", 0),
        )
        return {"url": url, "raw_content": raw_content, "title": title}

    def _build_raw_content(
        self,
        source_label,
        title,
        body,
        url,
        created_at,
        score,
        comments,
    ):
        body_text = body or "(Kein Fließtext vorhanden; Signal stammt aus dem Titel.)"
        return (
            f"Quelle: Reddit r/{self.subreddit}\n"
            f"Kategorie: {source_label}\n"
            f"Titel: {title}\n"
            f"URL: {url}\n"
            f"Erstellt: {created_at}\n"
            f"Score: {score}; Kommentare: {comments}\n\n"
            f"Inhalt:\n{body_text}"
        )

    def fetch_posts(self):
        self._authenticate_if_possible()
        posts_by_url = {}

        print(
            f"[Reddit] Sammle bis zu {self.limit} Posts aus r/{self.subreddit}..."
        )
        for term in self.search_terms:
            if len(posts_by_url) >= self.limit:
                break

            print(f"[Reddit] Suche: {term}")
            self._collect_from_listing(
                path=f"/r/{self.subreddit}/search.json",
                params={
                    "q": term,
                    "restrict_sr": "1",
                    "sort": "new",
                    "t": "year",
                },
                target=posts_by_url,
                source_label=f"Reddit-Suche: {term}",
            )

        if len(posts_by_url) < self.limit:
            print(f"[Reddit] Fülle mit aktuellen r/{self.subreddit}-Posts auf...")
            self._collect_from_listing(
                path=f"/r/{self.subreddit}/new.json",
                params={},
                target=posts_by_url,
                source_label=f"Reddit r/{self.subreddit} aktuell",
            )

        return list(posts_by_url.values())[: self.limit]

    def save_posts(self, posts):
        self._initialisiere_datenbank()

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        inserted = 0
        skipped = 0

        for post in posts:
            cursor.execute(
                """
                INSERT OR IGNORE INTO forum_posts (url, raw_content, status)
                VALUES (?, ?, 0)
                """,
                (post["url"], post["raw_content"]),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        conn.commit()
        conn.close()
        return inserted, skipped

    def run(self, dry_run=False):
        posts = self.fetch_posts()
        print(f"[Reddit] Gefunden: {len(posts)} eindeutige Posts.")

        if dry_run:
            for index, post in enumerate(posts[:10], start=1):
                print(f"{index}. {post['title']}")
            return len(posts), 0

        inserted, skipped = self.save_posts(posts)
        print(
            f"[Reddit] Import beendet: {inserted} neu gespeichert; "
            f"{skipped} bereits vorhanden."
        )
        return inserted, skipped


def parse_search_terms(raw_terms):
    if not raw_terms:
        return DEFAULT_SEARCH_TERMS

    return [term.strip() for term in raw_terms.split(",") if term.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import public Reddit posts into the Service Sonar database."
    )
    parser.add_argument("--db", default=DB_FILE, help="SQLite database path.")
    parser.add_argument(
        "--subreddit",
        default=DEFAULT_SUBREDDIT,
        help="Subreddit name without r/ prefix.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Maximum number of unique posts to import.",
    )
    parser.add_argument(
        "--terms",
        default="",
        help="Comma-separated search terms. Defaults to student-service keywords.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Seconds to wait between Reddit listing pages.",
    )
    parser.add_argument(
        "--require-body",
        action="store_true",
        help="Skip title-only posts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch posts and print sample titles without writing to the database.",
    )

    args = parser.parse_args()

    importer = RedditImporter(
        db_file=args.db,
        subreddit=args.subreddit,
        limit=args.limit,
        search_terms=parse_search_terms(args.terms),
        sleep_seconds=args.sleep,
        require_body=args.require_body,
    )
    importer.run(dry_run=args.dry_run)
