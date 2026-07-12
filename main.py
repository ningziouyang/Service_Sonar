# =====================================================================
# main.py - Backend-Skelett für das Supervisor-Multi-Agenten-System
# Architektonischer Ansatz: Cloud-basierte LLM-Infrastruktur (Modular)
# =====================================================================

import sqlite3

from migrate_database import ensure_feature_tables

# 1. Importiere unsere gekapselten Agenten-Klassen
from agent1_scraper_studis_online import Agent1Scraper
from agent2_cleaner import Agent2Cleaner
from agent3_analyzer import Agent3Analyzer
from agent4_innovator import Agent4Innovator

# =====================================================================
# ---- 0. GLOBALE KONFIGURATION & INFRASTRUKTUR-MANAGEMENT ----
# =====================================================================

DB_FILE = "service_sonar.db"

def init_db():
    """
    Initialisiert die lokale SQLite-Datenbank und das tabellarische Zustandsmodell.
    Erstellt sowohl die Tabelle für Posts als auch für System-Reports.
    """
    print("[DB] Initialisiere lokale SQLite-Datenbank und Tabellen...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Haupttabelle für den Datenfluss (Status 0 bis 3)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS forum_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            raw_content TEXT,
            cleaned_content TEXT,
            analysis_json TEXT,
            status INTEGER DEFAULT 0 , 
            analysis_attempts INTEGER DEFAULT 0
        )
    """)

    # Add analysis_attempts to older databases that were created before this column existed.
    try:
        cursor.execute("ALTER TABLE forum_posts ADD COLUMN analysis_attempts INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists — nothing to do.
    
    # Tabelle für die Ergebnisse von Agent 4 (Für das Dashboard)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            report_json TEXT
        )
    """)
    ensure_feature_tables(conn)
    conn.commit()
    conn.close()

# =====================================================================
# ---- 1. ZENTRALE ORCHESTRIERUNG: SUPERVISOR AGENT ----
# =====================================================================

def supervisor_agent():
    """
    Supervisor: Der primäre Orchestrator. Steuert den gesamten asynchronen 
    Datenfluss und ruft die jeweiligen Agenten-Module nacheinander auf.
    """
    print("\n=====================================================================")
    print("--- [Supervisor] System gestartet: Initiiere Multi-Agenten-Workflow ---")
    print("=====================================================================")
    
    # 0. Infrastruktur vorbereiten
    init_db()

    # PHASE 1: Datenakquise (Speichert als status=0)
    print("\n>>> STARTE PHASE 1: DATA SCRAPING <<<")
    scraper = Agent1Scraper()
    scraper.scrapen()
    
    # PHASE 2: Triage & Bereinigung (Verarbeitet status=0 -> 1, 3, oder -1)
    print("\n>>> STARTE PHASE 2: BEREINIGUNG & KLASSIFIZIERUNG <<<")
    cleaner = Agent2Cleaner()
    cleaner.run()
    
    # PHASE 3: Semantische Analyse (Verarbeitet status=1 -> 2)
    print("\n>>> STARTE PHASE 3: SEMANTISCHE ANALYSE (LLM) <<<")
    analyzer = Agent3Analyzer()
    analyzer.run()
    
    # PHASE 4: Innovations-Generierung (Verarbeitet status=2 -> system_reports)
    print("\n>>> STARTE PHASE 4: INNOVATIONS-GENERIERUNG (LLM) <<<")
    innovator = Agent4Innovator()
    innovator.run()
    
    print("\n=====================================================================")
    print("--- [Supervisor] Automatische Agenten-Phasen abgeschlossen. ---")
    print("Hinweis: Fälle mit status=3 bleiben in der Human-Review-Queue.")

def run_after_review():
    """
    Wird nach manueller Prüfung ausgeführt.
    Neu freigegebene Beiträge mit status=1 werden von Agent 3 verarbeitet.
    """

    print("\n=====================================================================")
    print("--- [Supervisor] Starte Pipeline nach Human Review ---")
    print("=====================================================================")

    print("\n>>> PHASE 3: SEMANTISCHE ANALYSE <<<")
    analyzer = Agent3Analyzer()
    analyzer.run()

    print("\n>>> PHASE 4: INNOVATIONS-GENERIERUNG <<<")
    innovator = Agent4Innovator()
    innovator.run()

    print("\n=====================================================================")
    print("--- [Supervisor] Nachverarbeitung abgeschlossen. ---")
    print("=====================================================================\n")

if __name__ == "__main__":
    mode = input(
        "1 = Full Pipeline\n"
        "2 = After Human Review\n"
        "Auswahl: "
    )

    if mode == "1":
        supervisor_agent()

    elif mode == "2":
        run_after_review()
