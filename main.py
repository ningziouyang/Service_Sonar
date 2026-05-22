import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random

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
# 2. KERNLOGIK DES SCRAPERS (AGENT 1)
# =====================================================================
def fetch_forum_data():
    """
    Agent 1: Extrahiert studentische Rohdaten aus Foren (Studis Online).
    Schreibt neue Einträge mit status=0 (Raw) in die Datenbank.
    """
    print("🚀 [Agent 1] Starte Web-Scraper für Studis Online...\n")
    
    # Verbindung zur State-Machine-Datenbank herstellen
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    total_inserted = 0

    # Iteriere über jede konfigurierte Kategorie
    for category, section_url in FORUM_SECTIONS.items():
        print(f"📂 Scrape Kategorie: {category} -> {section_url}")
        
        try:
            # 1. HTTP-GET-Anfrage an die Forenseite senden
            response = requests.get(section_url, headers=HEADERS, timeout=10)
            response.raise_for_status() # Wirft eine Exception bei 4xx/5xx HTTP-Fehlern
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ===============================================================
            # PRÄZISE EXTRAKTION: Basierend auf der DOM-Analyse (F12)
            # Wählt exakt die <a> Tags, die BEIDE Klassen enthalten.
            # ===============================================================
            post_links = soup.select('a.ston-farblinkh.ston-la') 
            
            for link in post_links:
                # Absolute URL zusammensetzen, falls sie relativ ist
                post_url = link.get('href')
                if not post_url.startswith('http'):
                    post_url = "https://www.studis-online.de" + post_url
                
                # Titel bereinigen (Leerzeichen entfernen)
                raw_text = link.text.strip()
                
                # Rauschen reduzieren: Antwort-Präfix "Re: " für saubere KI-Analyse entfernen
                if raw_text.startswith("Re: "):
                    raw_text = raw_text[4:].strip()
                
                # 2. Die "Rohdaten" (Raw) mit status=0 in die DB schreiben
                try:
                    # INSERT OR IGNORE sorgt dank UNIQUE-Constraint auf 'url' 
                    # automatisch für eine Deduplizierung!
                    cursor.execute("""
                        INSERT OR IGNORE INTO forum_posts (url, raw_content, status) 
                        VALUES (?, ?, 0)
                    """, (post_url, raw_text))
                    
                    if cursor.rowcount > 0:
                        print(f"   ✅ Neu importiert: {raw_text[:50]}...")
                        total_inserted += 1
                        
                except sqlite3.Error as db_err:
                    print(f"   ❌ Datenbank-Fehler: {db_err}")
                
            # 3. Höfliche Pause (Polite Delay) einlegen, um einen IP-Bann zu verhindern
            sleep_time = random.uniform(2.0, 4.0)
            print(f"⏳ Pausiere für {sleep_time:.2f} Sekunden (Anti-Scraping-Schutz)...\n")
            time.sleep(sleep_time)
            
        except Exception as e:
            print(f"❌ Netzwerk- oder Parsing-Fehler bei Kategorie '{category}': {e}")

    # Transaktion bestätigen und Verbindung schließen
    conn.commit()
    conn.close()
    
    print(f"\n🎉 [Agent 1] Scraping-Zyklus beendet! {total_inserted} neue Datensätze als 'status=0' gespeichert.")


if __name__ == "__main__":
    print("🛠️ [System] Prüfe/Erstelle Datenbank-Tabellen...")
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

    fetch_forum_data()