import os
import random
import sqlite3
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


DB_FILE = "service_sonar.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}

STUDIS_ONLINE_FORUM_SECTIONS = {
    "BAföG allgemein": "https://www.studis-online.de/Fragen-Brett/list.php?1",
    "Allgemeines Studium": "https://www.studis-online.de/Fragen-Brett/list.php?3",
    "Rund ums Geld": "https://www.studis-online.de/Fragen-Brett/list.php?4",
    "BAföG Vermögen": "https://www.studis-online.de/Fragen-Brett/list.php?7",
    "Studienwahl & Studienplatztausch": "https://www.studis-online.de/Fragen-Brett/list.php?8",
    "Hochschulstädte & Wohnen": "https://www.studis-online.de/Fragen-Brett/list.php?10",
    "Beruf & Karriere": "https://www.studis-online.de/Fragen-Brett/list.php?11",
    "Bildungs- & Hochschulpolitik": "https://www.studis-online.de/Fragen-Brett/list.php?12",
}

# Backward-compatible name used by older scripts.
FORUM_SECTIONS = STUDIS_ONLINE_FORUM_SECTIONS


class Agent1Scraper:
    def __init__(
        self,
        db_file=DB_FILE,
        forum_sections=None,
        pages_per_section=None,
        max_sections=None,
        max_new_posts_per_section=None,
        stop_on_challenge=None,
    ):
        self.db_file = db_file
        self.headers = HEADERS
        self.forum_sections = self._load_forum_sections(
            forum_sections or STUDIS_ONLINE_FORUM_SECTIONS,
            max_sections=max_sections,
        )
        self.pages_per_section = self._load_pages_per_section(pages_per_section)
        self.max_new_posts_per_section = self._load_optional_int(
            "AGENT1_MAX_NEW_POSTS_PER_SECTION",
            max_new_posts_per_section,
            default=8,
        )
        self.stop_on_challenge = self._load_bool(
            "AGENT1_STOP_ON_CHALLENGE",
            stop_on_challenge,
            default=True,
        )
        self.detail_sleep_range = self._load_sleep_range(
            "AGENT1_DETAIL_SLEEP_MIN",
            "AGENT1_DETAIL_SLEEP_MAX",
            default_min=1.5,
            default_max=3.5,
        )
        self.page_sleep_range = self._load_sleep_range(
            "AGENT1_PAGE_SLEEP_MIN",
            "AGENT1_PAGE_SLEEP_MAX",
            default_min=6.0,
            default_max=12.0,
        )
        self.board_sleep_range = self._load_sleep_range(
            "AGENT1_BOARD_SLEEP_MIN",
            "AGENT1_BOARD_SLEEP_MAX",
            default_min=20.0,
            default_max=45.0,
        )
        self._initialisiere_datenbank()

    def _load_pages_per_section(self, pages_per_section):
        if pages_per_section is None:
            pages_per_section = os.getenv("AGENT1_PAGES_PER_SECTION", "5")

        try:
            pages = int(pages_per_section)
        except (TypeError, ValueError):
            pages = 5

        return max(1, pages)

    def _load_forum_sections(self, forum_sections, max_sections=None):
        sections = dict(forum_sections)
        only_sections = os.getenv("AGENT1_ONLY_SECTIONS", "").strip()

        if only_sections:
            wanted = [
                section.strip().lower()
                for section in only_sections.split(",")
                if section.strip()
            ]
            sections = {
                name: url
                for name, url in sections.items()
                if any(want in name.lower() for want in wanted)
            }

        max_sections = self._load_optional_int(
            "AGENT1_MAX_SECTIONS",
            max_sections,
            default=0,
        )
        if max_sections > 0:
            sections = dict(list(sections.items())[:max_sections])

        return sections

    def _load_optional_int(self, env_name, explicit_value, default):
        value = explicit_value
        if value is None:
            value = os.getenv(env_name, str(default))

        try:
            loaded = int(value)
        except (TypeError, ValueError):
            loaded = default

        return max(0, loaded)

    def _load_bool(self, env_name, explicit_value, default):
        if explicit_value is not None:
            return bool(explicit_value)

        value = os.getenv(env_name)
        if value is None:
            return default

        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    def _load_sleep_range(self, min_env_name, max_env_name, default_min, default_max):
        min_seconds = self._load_float(min_env_name, default_min)
        max_seconds = self._load_float(max_env_name, default_max)

        min_seconds = max(0.0, min_seconds)
        max_seconds = max(0.0, max_seconds)
        if max_seconds < min_seconds:
            min_seconds, max_seconds = max_seconds, min_seconds

        return min_seconds, max_seconds

    def _load_float(self, env_name, default):
        try:
            return float(os.getenv(env_name, str(default)))
        except (TypeError, ValueError):
            return default

    def _sleep_random(self, seconds_range, reason):
        min_seconds, max_seconds = seconds_range
        if max_seconds <= 0:
            return

        seconds = random.uniform(min_seconds, max_seconds)
        print(f"  Warte {seconds:.1f}s ({reason})...")
        time.sleep(seconds)

    def _safe_get(self, url, timeout=20, retries=3):
        """
        Ruft eine Webseite robuster ab.
        Wenn ein Request fehlschlägt, wird er mehrmals wiederholt.
        """
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as error:
                print(f"Request-Fehler Versuch {attempt}/{retries}: {url} -> {error}")
                time.sleep(random.uniform(2.0, 4.0))

        print(f"Seite nach {retries} Versuchen nicht erreichbar: {url}")
        return None

    def _initialisiere_datenbank(self):
        """Initialisiert die Datenbank-Tabellen für die Rohdaten."""
        conn = sqlite3.connect(self.db_file)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS forum_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                raw_content TEXT,
                cleaned_content TEXT,
                analysis_json TEXT,
                status INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()

    def _page_url(self, base_url, page):
        if page == 1:
            return base_url
        return f"{base_url},page={page}"

    def _normalisiere_post_url(self, href):
        return urljoin("https://www.studis-online.de", href or "")

    def _is_security_challenge(self, response):
        text = response.text if response is not None else ""
        return (
            "challenge.php" in getattr(response, "url", "")
            or "Sicherheitsüberprüfung" in text
            or "Sicherheitsprüfung" in text
        )

    def _post_exists(self, cursor, post_url):
        cursor.execute("SELECT 1 FROM forum_posts WHERE url = ? LIMIT 1", (post_url,))
        return cursor.fetchone() is not None

    def _extract_post_body(self, html):
        detail_soup = BeautifulSoup(html, "html.parser")
        first_post_container = detail_soup.find("div", class_="ston-dblock")

        if not first_post_container:
            return "Kein Textinhalt extrahierbar."

        content_divs = first_post_container.find_all("div", class_="ston-p")
        post_paragraphs = [
            div.get_text(separator="\n", strip=True)
            for div in content_divs
            if div.get_text(strip=True)
        ]

        if not post_paragraphs:
            return "Kein Textinhalt extrahierbar."

        return "\n\n".join(post_paragraphs)

    def _build_raw_content(self, category, title, body):
        return (
            "Quelle: Studis Online\n"
            f"Kategorie: {category}\n"
            f"Titel: {title}\n\n"
            f"Inhalt:\n{body}"
        )

    def scrapen(self):
        """Führt den Scraping-Prozess mit Deep-Scraping-Logik aus."""
        print("[Agent 1] Starte Deep-Scraper Prozess...")
        print(
            f"[Agent 1] Konfigurierte Studis-Online-Boards: "
            f"{len(self.forum_sections)}; Seiten je Board: {self.pages_per_section}; "
            f"neue Detailseiten je Board: {self.max_new_posts_per_section or 'unbegrenzt'}"
        )
        if self.stop_on_challenge:
            print("[Agent 1] Sicherheitsprüfung erkannt -> kompletter Lauf stoppt.")

        if not self.forum_sections:
            print("[Agent 1] Keine passenden Boards konfiguriert. Prüfe AGENT1_ONLY_SECTIONS.")
            return 0

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        erfolgreich_gespeichert = 0
        bereits_vorhanden = 0
        stop_requested = False

        for board_index, (kategorie, base_url) in enumerate(self.forum_sections.items(), start=1):
            print("\n==================================================")
            print(f"Starte Deep-Scraping: {kategorie}")
            print("==================================================")
            neue_details_in_board = 0
            challenge_detected = False

            for seite in range(1, self.pages_per_section + 1):
                url = self._page_url(base_url, seite)
                print(f"  Lese Übersichtsseite {seite} -> {url}")

                antwort = self._safe_get(url, timeout=20, retries=3)
                if antwort is None:
                    print(
                        f"Übersichtsseite {seite} konnte nicht geladen werden. "
                        "Überspringe Seite."
                    )
                    continue

                if self._is_security_challenge(antwort):
                    print(
                        "  Studis Online liefert gerade eine Sicherheitsprüfung "
                        "statt der Forenliste."
                    )
                    challenge_detected = True
                    stop_requested = self.stop_on_challenge
                    break

                soup = BeautifulSoup(antwort.text, "html.parser")
                links = soup.select('a.ston-farblinkh[href*="read.php"]')

                if not links:
                    print(f"Keine Posts mehr gefunden. Breche ab für '{kategorie}'.")
                    break

                for link in links:
                    post_url = self._normalisiere_post_url(link.get("href"))
                    post_title = link.get_text(strip=True)

                    if not post_title or len(post_title) < 5:
                        continue
                    if any(
                        marker in post_title
                        for marker in ["Tage her", "Stunden her", "Minuten her"]
                    ):
                        continue
                    if post_title.startswith("Re: "):
                        post_title = post_title[4:].strip()

                    if self._post_exists(cursor, post_url):
                        bereits_vorhanden += 1
                        continue

                    if (
                        self.max_new_posts_per_section
                        and neue_details_in_board >= self.max_new_posts_per_section
                    ):
                        print(
                            "      Limit für neue Detailseiten in diesem Board erreicht. "
                            "Weiter mit dem nächsten Board."
                        )
                        break

                    detail_resp = self._safe_get(post_url, timeout=20, retries=2)
                    if detail_resp is None:
                        print("      Detailseite konnte nicht geladen werden. Überspringe Beitrag.")
                        continue

                    if self._is_security_challenge(detail_resp):
                        print(
                            "      Studis Online liefert bei der Detailseite eine "
                            "Sicherheitsprüfung statt des Beitrags."
                        )
                        challenge_detected = True
                        stop_requested = self.stop_on_challenge
                        break

                    post_body = self._extract_post_body(detail_resp.text)
                    full_text = self._build_raw_content(kategorie, post_title, post_body)

                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO forum_posts (url, raw_content, status)
                        VALUES (?, ?, 0)
                        """,
                        (post_url, full_text),
                    )
                    if cursor.rowcount > 0:
                        print(f"      Gespeichert: {post_title[:45]}...")
                        erfolgreich_gespeichert += 1
                    neue_details_in_board += 1

                    if not (
                        self.max_new_posts_per_section
                        and neue_details_in_board >= self.max_new_posts_per_section
                    ):
                        self._sleep_random(self.detail_sleep_range, "Detailseiten schonen")

                conn.commit()
                if challenge_detected or (
                    self.max_new_posts_per_section
                    and neue_details_in_board >= self.max_new_posts_per_section
                ):
                    break
                if seite < self.pages_per_section:
                    self._sleep_random(self.page_sleep_range, "nächste Übersichtsseite")

            if stop_requested:
                print(
                    "[Agent 1] Sicherheitsprüfung erkannt. Lauf wird beendet, "
                    "damit keine weiteren Requests ausgelöst werden."
                )
                break

            if board_index < len(self.forum_sections):
                self._sleep_random(self.board_sleep_range, "nächstes Board")

        conn.close()
        print(
            "\n[Agent 1] Deep-Scraping beendet! "
            f"{erfolgreich_gespeichert} neue Datensätze gespeichert; "
            f"{bereits_vorhanden} bereits vorhanden."
        )
        return erfolgreich_gespeichert


def fetch_forum_data():
    """Backward-compatible wrapper for older scripts."""
    scraper = Agent1Scraper()
    return scraper.scrapen()


if __name__ == "__main__":
    fetch_forum_data()
