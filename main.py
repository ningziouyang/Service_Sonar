# =====================================================================
# main.py - Backend-Skelett für das Supervisor-Multi-Agenten-System
# Architektonischer Ansatz: Cloud-basierte LLM-Infrastruktur (Modular)
# =====================================================================

import sqlite3

# 1. Importiere unsere gekapselten Agenten-Klassen
from agent1_scraper import Agent1Scraper
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
            status INTEGER DEFAULT 0  
        )
    """)
    
    # Tabelle für die Ergebnisse von Agent 4 (Für das Dashboard)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            report_json TEXT
        )
    """)
    conn.commit()
    conn.close()

# =====================================================================
# ---- 1. INTERVENTIONS-INTERFACE: HUMAN-OVERRIDE ----
# =====================================================================

def human_intervention_interface():
    """
    Schnittstelle für den Human-in-the-Loop.
    Ermöglicht es dem menschlichen Forscher, sensible Härtefälle (status=3) 
    manuell zu prüfen, zu anonymisieren und für die KI freizugeben.
    """
    print("\n---------------------------------------------------------------------")
    print("[HITL Interface] Starte manuelle Überprüfung für blockierte Fälle (status=3)...")
    print("---------------------------------------------------------------------")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, raw_content FROM forum_posts WHERE status = 3")
    blocked_records = cursor.fetchall()

    if not blocked_records:
        print("[HITL Interface] Keine Fälle in der Warteschlange für Human Review.")
    else:
        for db_id, raw_text in blocked_records:
            print(f"\n[MANUELLE PRÜFUNG] Fall-ID: {db_id}")
            print(f"Sensibler Text: '{raw_text}'")
            
            # Simulation einer menschlichen Aktion (Anonymisierung & Freigabe)
            user_input_simulation = "[MANUELL BEREINIGT] Bestätigter Fall von akuter Belastung. Freigegeben für Agent 3."
            print(f"[Forscher-Aktion] Fall geprüft, bereinigt und freigegeben (status=1).")
            
            # Update der Datenbank: Setzt den Status auf 1, damit Agent 3 übernehmen kann
            cursor.execute("UPDATE forum_posts SET cleaned_content = ?, status = 1 WHERE id = ?", (user_input_simulation, db_id))
    
    conn.commit()
    conn.close()

# =====================================================================
# ---- 2. ZENTRALE ORCHESTRIERUNG: SUPERVISOR AGENT ----
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
    
    # INTERVENTION: Menschliche Überprüfung der blockierten Fälle
    human_intervention_interface()
    
    # PHASE 3: Semantische Analyse (Verarbeitet status=1 -> 2)
    print("\n>>> STARTE PHASE 3: SEMANTISCHE ANALYSE (LLM) <<<")
    analyzer = Agent3Analyzer()
    analyzer.run()
    
    # PHASE 4: Innovations-Generierung (Verarbeitet status=2 -> system_reports)
    print("\n>>> STARTE PHASE 4: INNOVATIONS-GENERIERUNG (LLM) <<<")
    innovator = Agent4Innovator()
    innovator.run()
    
    print("\n=====================================================================")
    print("--- [Supervisor] Alle Agenten-Phasen inklusive HITL erfolgreich durchlaufen. ---")
    print("=====================================================================\n")

if __name__ == "__main__":
    supervisor_agent()