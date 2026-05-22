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
# 2. KERNLOGIK DES SCRAPERS (AGENT 1) - INKLUSIVE PAGINATION
# =====================================================================
def fetch_forum_data():
    """
    Agent 1: Extrahiert studentische Rohdaten aus Foren (Studis Online).
    Schreibt neue Einträge mit status=0 (Raw) in die Datenbank.
    Beinhaltet automatische Pagination und eine robuste (bulletproof) Extraktionslogik.
    """
    print("🚀 [Agent 1] Starte Web-Scraper für Studis Online...\n")
    
    # Verbindung zur State-Machine-Datenbank herstellen
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    total_inserted = 0

    # Iteriere über jede konfigurierte Kategorie
    for category, base_url in FORUM_SECTIONS.items():
        print(f"\n==================================================")
        print(f"📂 Starte Scraping für Kategorie: {category}")
        print(f"==================================================")
        
        # 🌟 NEUE LOGIK: Automatisches Pagination (Blättern durch Seiten 1 bis 5)
        # Ändere '6' auf z.B. '11', um 10 Seiten pro Kategorie abzurufen.
        for page in range(1, 6): 
            
            # 1. Dynamische URL-Generierung für die jeweilige Seite
            if page == 1:
                page_url = base_url
            else:
                # Struktur für Folgeseiten bei Studis-Online
                page_url = f"{base_url},page={page}"
                
            print(f"   📄 Lese Seite {page} -> {page_url}")
            
            try:
                # 2. HTTP-GET-Anfrage an die Forenseite senden
                response = requests.get(page_url, headers=HEADERS, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # ===============================================================
                # 🔍 BULLETPROOF EXTRAKTION: Ignoriert wechselnde CSS-Klassen!
                # Sucht gezielt nach <a>-Tags, die "read.php" im Link enthalten.
                # ===============================================================
                post_links = soup.select('a[href*="read.php"]') 
                
                # Wenn eine Seite keine Links mehr enthält, ist das Ende des Forums erreicht
                if not post_links:
                    print(f"   ⚠️ Keine Posts auf Seite {page} gefunden. Breche Pagination für '{category}' ab.")
                    break 
                
                for link in post_links:
                    post_url = link.get('href')
                    if not post_url.startswith('http'):
                        post_url = "https://www.studis-online.de" + post_url
                    
                    raw_text = link.text.strip()
                    
                    # 🚀 NEU: Filtert leere oder extrem kurze Texte heraus (z.B. Seitenzahlen "1", "2")
                    if not raw_text or len(raw_text) < 5:
                        continue
                        
                    # Rauschen reduzieren ("Re: " abschneiden)
                    if raw_text.startswith("Re: "):
                        raw_text = raw_text[4:].strip()
                    
                    # 4. Speichern in der DB
                    try:
                        # Automatische Deduplizierung durch UNIQUE-Constraint auf 'url'
                        cursor.execute("""
                            INSERT OR IGNORE INTO forum_posts (url, raw_content, status) 
                            VALUES (?, ?, 0)
                        """, (post_url, raw_text))
                        
                        if cursor.rowcount > 0:
                            print(f"      ✅ Neu: {raw_text[:45]}...")
                            total_inserted += 1
                            
                    except sqlite3.Error:
                        pass # Stiller Fehler bei Duplikaten (gewünschtes Verhalten)
                
                # 5. Höfliche Pause NACH JEDER SEITE (Extrem wichtig für Pagination!)
                sleep_time = random.uniform(2.5, 4.5)
                print(f"   ⏳ Pausiere für {sleep_time:.2f}s (Anti-Scraping-Schutz)...\n")
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"   ❌ Fehler auf Seite {page}: {e}")
                break # Bei schweren Netzwerkfehlern (z.B. 404) zur nächsten Kategorie springen

    # Transaktion bestätigen und Verbindung schließen
    conn.commit()
    conn.close()
    
    print(f"\n🎉 [Agent 1] Scraping-Zyklus beendet! {total_inserted} neue Datensätze als 'status=0' gespeichert.")


# =====================================================================
# 3. INITIALISIERUNG & AUSFÜHRUNG
# =====================================================================
if __name__ == "__main__":
    # 1. Sicherstellen, dass die Datenbank und Tabelle existieren
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

    # 2. Scraping-Pipeline starten
    fetch_forum_data()