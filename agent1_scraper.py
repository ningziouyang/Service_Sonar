import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random


class Agent1Scraper:
    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.forum_sections = {
            "BAföG & Finanzen": "https://www.studis-online.de/Fragen-Brett/list.php?1",
            "Wohnungsmarkt": "https://www.studis-online.de/Fragen-Brett/list.php?2",
            "Studium & Psyche": "https://www.studis-online.de/Fragen-Brett/list.php?3"
        }
        self._initialisiere_datenbank()

    def _initialisiere_datenbank(self):
        """Initialisiert die Datenbank-Tabellen für die Rohdaten."""
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forum_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                raw_content TEXT,
                cleaned_content TEXT,
                analysis_json TEXT,
                status INTEGER DEFAULT 0  
            )
        """)
        conn.commit()
        conn.close()

    def scrapen(self):
        """Führt den Scraping-Prozess mit Deep-Scraping-Logik aus."""
        print("[Agent 1] Starte Deep-Scraper Prozess...")
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        erfolgreich_gespeichert = 0

        for kategorie, base_url in self.forum_sections.items():
            print(f"\n==================================================")
            print(f"Starte Deep-Scraping: {kategorie}")
            print(f"==================================================")
            
            for seite in range(1, 6): 
                url = base_url if seite == 1 else f"{base_url},page={seite}"
                print(f"  📄 Lese Übersichtsseite {seite} -> {url}")
                
                try:
                    antwort = requests.get(url, headers=self.headers, timeout=(10, 60))
                    antwort.raise_for_status()
                    soup = BeautifulSoup(antwort.text, 'html.parser')
                    links = soup.select('a.ston-farblinkh[href*="read.php"]')
                    
                    if not links:
                        print(f"Keine Posts mehr gefunden. Breche ab für '{kategorie}'.")
                        break

                    for link in links:
                        post_url = link.get('href')
                        if not post_url.startswith('http'):
                            post_url = "https://www.studis-online.de" + post_url
                            
                        post_title = link.text.strip()
                        
                        # FILTERUNG 1: Deine originale Filterlogik
                        if not post_title or len(post_title) < 5: continue
                        if any(x in post_title for x in ["Tage her", "Stunden her", "Minuten her"]): continue
                        if post_title.startswith("Re: "): post_title = post_title[4:].strip()
                        
                        # DEEP SCRAPING: In den Post hineingehen
                        try:
                            detail_resp = requests.get(post_url, headers=self.headers, timeout=(10, 60))
                            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                            first_post_container = detail_soup.find('div', class_='ston-dblock')
                            
                            post_body = ""
                            if first_post_container:
                                content_divs = first_post_container.find_all('div', class_='ston-p')
                                post_paragraphs = [div.get_text(separator='\n', strip=True) for div in content_divs if div.get_text(strip=True)]
                                post_body = "\n\n".join(post_paragraphs)
                                
                            if not post_body:
                                post_body = "Kein Textinhalt extrahierbar."
                                
                            full_text = f"Titel: {post_title}\n\nInhalt:\n{post_body}"
                            
                            # Speichern in DB
                            cursor.execute("INSERT OR IGNORE INTO forum_posts (url, raw_content, status) VALUES (?, ?, 0)", (post_url, full_text))
                            if cursor.rowcount > 0:
                                print(f"      ✅ Deep Scraped: {post_title[:35]}...")
                                erfolgreich_gespeichert += 1
                                
                            time.sleep(random.uniform(0.5, 1.5))
                            
                        except Exception as detail_err:
                            print(f"      ❌ Fehler beim Lesen des Inhalts ({post_url}): {detail_err}")
                    
                    conn.commit()
                    time.sleep(random.uniform(2.0, 4.0))
                    
                except Exception as e:
                    print(f"Netzwerkfehler auf Seite {seite}: {e}")
                    break
                    
        conn.close()
        print(f"\n[Agent 1] Deep-Scraping beendet! {erfolgreich_gespeichert} Datensätze gespeichert.")
        return erfolgreich_gespeichert

if __name__ == "__main__":
    scraper = Agent1Scraper()
    scraper.scrapen()

# =====================================================================
# 1. ZENTRALE KONFIGURATION
# =====================================================================
DB_FILE = "service_sonar.db"

# Tarnung als normaler Chrome-Browser, um HTTP-429-Blockaden zu vermeiden
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Die Ziel-Kategorien des Forums (URLs können jederzeit dynamisch erweitert werden)
FORUM_SECTIONS = {
    "BAföG & Finanzen": "https://www.studis-online.de/Fragen-Brett/list.php?1",
    "Wohnungsmarkt": "https://www.studis-online.de/Fragen-Brett/list.php?2",
    "Studium & Psyche": "https://www.studis-online.de/Fragen-Brett/list.php?3"
}

# =====================================================================
# 2. KERNLOGIK DES SCRAPERS (AGENT 1) - DEEP SCRAPING & CHECKPOINTS
# =====================================================================
def fetch_forum_data():
    """
    Agent 1: Deep Scraper für Studis Online.
    - Extrahiert präzise den Original-Text (Container-Lock).
    - Filtert Störgeräusche ("Antworten", Zeitstempel) heraus.
    - Speichert Daten seitenweise (Checkpoints), um Datenverlust bei Abbruch zu verhindern.
    """
    print("[Agent 1] Starte Deep-Scraper für Studis Online...\n")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    total_inserted = 0

    # Iteriere über jede konfigurierte Kategorie
    for category, base_url in FORUM_SECTIONS.items():
        print(f"\n==================================================")
        print(f"Starte Deep-Scraping: {category}")
        print(f"==================================================")
        
        # Blättern durch Seiten 1 bis 5 (kann beliebig erhöht werden)
        for page in range(1, 6): 
            if page == 1:
                page_url = base_url
            else:
                page_url = f"{base_url},page={page}"
                
            print(f"   📄 Lese Übersichtsseite {page} -> {page_url}")
            
            try:
                # HTTP-GET-Anfrage an die Übersichtsseite
                response = requests.get(page_url, headers=HEADERS, timeout=(10, 60))
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Spezifischer CSS-Selektor: Nur echte Foren-Links, die "read.php" enthalten
                post_links = soup.select('a.ston-farblinkh[href*="read.php"]') 
                
                if not post_links:
                    print(f"Keine Posts mehr gefunden. Breche Pagination für '{category}' ab.")
                    break 
                
                for link in post_links:
                    post_url = link.get('href')
                    if not post_url.startswith('http'):
                        post_url = "https://www.studis-online.de" + post_url
                    
                    post_title = link.text.strip()
                    
                    # FILTERUNG 1: Zeitstempel und leere/zu kurze Titel knallhart aussortieren
                    if not post_title or len(post_title) < 5:
                        continue
                    if "Tage her" in post_title or "Stunden her" in post_title or "Minuten her" in post_title:
                        continue
                    if post_title.startswith("Re: "):
                        post_title = post_title[4:].strip()
                    
                    # =======================================================
                    # 🚀 DEEP SCRAPING: In den Post hineingehen
                    # =======================================================
                    try:
                        detail_resp = requests.get(post_url, headers=HEADERS, timeout=(10, 60))
                        detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                        
                        # ULTIMATIVER FIX: Scope eingrenzen! (Container-Lock)
                        first_post_container = detail_soup.find('div', class_='ston-dblock')
                        
                        post_body = ""
                        if first_post_container:
                            # Wir holen alle Text-Absätze NUR aus diesem isolierten Container
                            content_divs = first_post_container.find_all('div', class_='ston-p')
                            
                            post_paragraphs = []
                            for div in content_divs:
                                # <br> Tags sauber in echte Zeilenumbrüche umwandeln
                                text = div.get_text(separator='\n', strip=True)
                                if text: 
                                    post_paragraphs.append(text)
                                    
                            # Alle validen Absätze zu einem durchgehenden Textblock zusammenfügen
                            post_body = "\n\n".join(post_paragraphs)
                            
                        # Fallback, falls der Post wirklich komplett leer sein sollte
                        if not post_body:
                            post_body = "Kein Textinhalt extrahierbar."
                            
                        # Titel und strukturierten Inhalt für das LLM (Agent 2) vorbereiten
                        full_text = f"Titel: {post_title}\n\nInhalt:\n{post_body}"
                        
                        # Speichern in der DB
                        cursor.execute("""
                            INSERT OR IGNORE INTO forum_posts (url, raw_content, status) 
                            VALUES (?, ?, 0)
                        """, (post_url, full_text))
                        
                        if cursor.rowcount > 0:
                            print(f"      ✅ Deep Scraped: {post_title[:35]}...")
                            total_inserted += 1
                        
                        # PFLICHT-PAUSE: 0.5 bis 1.5 Sekunden nach jedem Post (Anti-DDoS)
                        time.sleep(random.uniform(0.5, 1.5))
                        
                    except Exception as detail_err:
                        print(f"      ❌ Fehler beim Lesen des Inhalts ({post_url}): {detail_err}")
                
                # =======================================================
                #  Automatisches Speichern (Checkpoint)
                # =======================================================
                conn.commit()
                print(f"[Checkpoint] Seite {page} sicher in der DB gespeichert.")
                
                # Höfliche Pause zwischen den einzelnen Seiten
                print(f"Seite {page} fertig. Kurze Pause...\n")
                time.sleep(random.uniform(2.0, 4.0))
                
            except Exception as e:
                print(f"Netzwerkfehler auf Seite {page}: {e}")
                break 

    # Ein letzter Commit zur Sicherheit und Verbindung schließen
    conn.commit()
    conn.close()
    print(f"\n[Agent 1] Deep-Scraping beendet! Insgesamt {total_inserted} hochwertige Datensätze gespeichert.")

# =====================================================================
# 3. INITIALISIERUNG & AUSFÜHRUNG
# =====================================================================
if __name__ == "__main__":
    # 1. Sicherstellen, dass die Datenbank und Tabelle existieren
    print("[System] Prüfe/Erstelle Datenbank-Tabellen...")
    setup_conn = sqlite3.connect(DB_FILE)
    setup_conn.execute("""
        CREATE TABLE IF NOT EXISTS forum_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            raw_content TEXT,
            cleaned_content TEXT,
            analysis_json TEXT,
            status INTEGER DEFAULT 0  
        )
    """)
    setup_conn.commit()
    setup_conn.close()

    # 2. Scraping-Pipeline starten
    fetch_forum_data()

