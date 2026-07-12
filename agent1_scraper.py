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
    )
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
    ):
        self.db_file = db_file
        self.headers = HEADERS
        self.forum_sections = dict(forum_sections or STUDIS_ONLINE_FORUM_SECTIONS)
        self.pages_per_section = self._load_pages_per_section(pages_per_section)
        self._initialisiere_datenbank()

    def _load_pages_per_section(self, pages_per_section):
        if pages_per_section is None:
            pages_per_section = os.getenv("AGENT1_PAGES_PER_SECTION", "5")

        try:
            pages = int(pages_per_section)
        except (TypeError, ValueError):
            pages = 5

        return max(1, pages)

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
            f"{len(self.forum_sections)}; Seiten je Board: {self.pages_per_section}"
        )

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        erfolgreich_gespeichert = 0
        bereits_vorhanden = 0

        for kategorie, base_url in self.forum_sections.items():
            print("\n==================================================")
            print(f"Starte Deep-Scraping: {kategorie}")
            print("==================================================")

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

                    detail_resp = self._safe_get(post_url, timeout=20, retries=2)
                    if detail_resp is None:
                        print("      Detailseite konnte nicht geladen werden. Überspringe Beitrag.")
                        continue

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

                    time.sleep(random.uniform(0.5, 1.5))

                conn.commit()
                time.sleep(random.uniform(2.0, 4.0))

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
