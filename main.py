import sqlite3
import requests
from bs4 import BeautifulSoup

DB_FILE = "service_sonar.db"

def init_db():
    """Initialisiert die lokale SQLite-Datenbank."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
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

def agent_data_fetcher():
    """
    Agent 1: Forum-Scraper & Datensammlung.
    """
    print("[Agent 1] Starte Web-Scraping auf Studis Online...")
    # -----------------------------------------------------------------
    # TODO: DEIN TASK HEUTE ABEND (BeautifulSoup & requests)
    # -----------------------------------------------------------------
    pass

if __name__ == "__main__":
    init_db()
    agent_data_fetcher()