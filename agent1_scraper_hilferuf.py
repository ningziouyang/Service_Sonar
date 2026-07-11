import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random


class Agent1ScraperHilferuf:
    """
    Scraper für hilferuf.de (XenForo-Forum).

    Wichtig zur Struktur (Stand: Juli 2026, XenForo 2.x mit angepasstem Theme):
    - Themenliste: https://www.hilferuf.de/forums/{slug}.{id}/  (Seite 2: .../page-2)
    - Einzelthema:  https://www.hilferuf.de/thema/{thread-slug}.{id}/
    - Erster Beitrag eines Themas liegt im ersten <article class="message--post">,
      der eigentliche Text steckt in <div class="bbWrapper"> innerhalb von
      <div class="message-body">.

    ⚠️ Diese Selektoren sind Standard-XenForo-Klassen (an JS-Funktionalität
    gekoppelt, deshalb i.d.R. auch bei individuellem Theme stabil). Trotzdem:
    vor dem großen Lauf bitte mit "Seitenquelltext anzeigen" an einer echten
    Themen-Seite gegenchecken, falls sich nichts findet.
    """

    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Priorität-A-Foren aus der gemeinsamen Analyse:
        self.forum_sections = {
            "Studium": "https://www.hilferuf.de/forums/studium.74/",
            "Ich": "https://www.hilferuf.de/forums/ich.72/",
            "Finanzen": "https://www.hilferuf.de/forums/finanzen.64/",
            "Beruf": "https://www.hilferuf.de/forums/beruf.65/",
        }
        self._initialisiere_datenbank()

    def _safe_get(self, url, timeout=20, retries=3):
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(url, headers=self.headers, timeout=timeout)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                print(f"Request-Fehler Versuch {attempt}/{retries}: {url} -> {e}")
                time.sleep(random.uniform(2.0, 4.0))
        print(f"Seite nach {retries} Versuchen nicht erreichbar: {url}")
        return None

    def _initialisiere_datenbank(self):
        """Eigene Tabelle, damit die Quelle sauber getrennt bleibt von Studis Online."""
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hilferuf_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                forum_kategorie TEXT,
                raw_content TEXT,
                cleaned_content TEXT,
                analysis_json TEXT,
                status INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    def scrapen(self, max_seiten_pro_forum=5):
        """
        max_seiten_pro_forum: Tiefe pro Forum. Bewusst niedrig gehalten
        (Studium hat allein 219 Seiten!) — lieber öfter kurz laufen lassen
        als einmal riesig.
        """
        print("[Agent 1 - Hilferuf] Starte Scraping...")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        erfolgreich_gespeichert = 0

        for kategorie, base_url in self.forum_sections.items():
            print(f"\n==================================================")
            print(f"Starte Scraping: {kategorie}")
            print(f"==================================================")

            for seite in range(1, max_seiten_pro_forum + 1):
                url = base_url if seite == 1 else f"{base_url}page-{seite}"
                print(f"  📄 Lese Übersichtsseite {seite} -> {url}")

                antwort = self._safe_get(url)
                if antwort is None:
                    print(f"Übersichtsseite {seite} konnte nicht geladen werden. Überspringe.")
                    continue

                soup = BeautifulSoup(antwort.text, 'html.parser')

                # Themen-Links: liegen in structItem-Zeilen, Ziel-URLs enthalten "/thema/"
                thread_links = soup.select('div.structItem-title a[href*="/thema/"]')
                if not thread_links:
                    # Fallback, falls das Theme die Klasse umbenannt hat
                    thread_links = [
                        a for a in soup.select('a[href*="/thema/"]')
                        if '/page-' not in a.get('href', '')
                    ]

                if not thread_links:
                    print(f"Keine Themen mehr gefunden. Breche ab für '{kategorie}'.")
                    break

                seen_urls = set()
                for link in thread_links:
                    thread_url = link.get('href')
                    if not thread_url:
                        continue
                    if not thread_url.startswith('http'):
                        thread_url = "https://www.hilferuf.de" + thread_url
                    if thread_url in seen_urls:
                        continue
                    seen_urls.add(thread_url)

                    thread_title = link.text.strip()
                    if not thread_title or len(thread_title) < 5:
                        continue

                    try:
                        detail_resp = self._safe_get(thread_url, retries=2)
                        if detail_resp is None:
                            print("      Thema konnte nicht geladen werden. Überspringe.")
                            continue

                        detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')

                        # Ersten Beitrag isolieren (Container-Lock wie bei Studis Online)
                        first_post = detail_soup.select_one('article.message--post')
                        post_body = ""
                        if first_post:
                            body_container = first_post.select_one('div.bbWrapper')
                            if body_container:
                                post_body = body_container.get_text(separator='\n', strip=True)

                        if not post_body:
                            post_body = "Kein Textinhalt extrahierbar."

                        full_text = f"Titel: {thread_title}\n\nInhalt:\n{post_body}"

                        cursor.execute(
                            """INSERT OR IGNORE INTO hilferuf_posts
                               (url, forum_kategorie, raw_content, status)
                               VALUES (?, ?, ?, 0)""",
                            (thread_url, kategorie, full_text),
                        )
                        if cursor.rowcount > 0:
                            print(f"      ✅ Gescraped: {thread_title[:35]}...")
                            erfolgreich_gespeichert += 1

                        time.sleep(random.uniform(0.5, 1.5))

                    except Exception as detail_err:
                        print(f"      ❌ Fehler beim Lesen ({thread_url}): {detail_err}")

                conn.commit()
                time.sleep(random.uniform(2.0, 4.0))

        conn.close()
        print(f"\n[Agent 1 - Hilferuf] Fertig! {erfolgreich_gespeichert} Datensätze gespeichert.")
        return erfolgreich_gespeichert


if __name__ == "__main__":
    scraper = Agent1ScraperHilferuf()
    scraper.scrapen(max_seiten_pro_forum=5)
    