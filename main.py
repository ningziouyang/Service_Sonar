# =====================================================================
# main.py - Backend-Skelett für das Supervisor-Multi-Agenten-System
# Architektonischer Ansatz: Cloud-basierte Hybrid-LLM-Infrastruktur
# =====================================================================

import os
import sqlite3
import json
from openai import OpenAI

# =====================================================================
# ---- 0. GLOBALE KONFIGURATION & INFRASTRUKTUR-MANAGEMENT ----
# =====================================================================

# Live-Modus vs. Meeting-Simulation (Erlaubt Vorführung ohne API-Kosten)
SIMULATION_MODE = True

# ROUTE A: Open-Source-Infrastruktur via GroqCloud
GROQ_API_KEY = "gsk_xxxx_Hier_deinen_Groq_Key_einfügen"
client_groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# ROUTE B: Proprietary-Model-Infrastruktur via OpenAI
OPENAI_API_KEY = "sk-proj-xxxx_Hier_deinen_OpenAI_Key_einfügen"
client_openai = OpenAI(
    api_key=OPENAI_API_KEY
)

DB_FILE = "service_sonar.db"

def init_db():
    """Initialisiert die lokale SQLite-Datenbank und das tabellarische Zustandsmodell."""
    print("[DB] Initialisiere lokale SQLite-Datenbank...")
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
            -- STATUS MODELL: 0=Raw, 1=Cleaned, 2=Analyzed, 3=Human-Review, -1=Rejected
        )
    """)
    conn.commit()
    conn.close()


# =====================================================================
# ---- 1. DEFINITIONEN DER 4 WORKER-AGENTEN ----
# =====================================================================

def agent_data_fetcher():
    """
    Agent 1: Forum-Scraper & Datensammlung.
    Sammelt Rohdaten aus studentischen Foren und initialisiert Status=0.
    """
    print("[Agent 1] Extrahiere studentische Rohdaten aus Webquellen (Studis Online)...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Demonstrative Testdatensätze (Simuliert die HTML-Extraktion)
    mock_posts = [
        ("https://www.studis-online.de/forum/1", "Ich warte seit Monaten auf einen Wohnheimplatz. Muss bald im Auto schlafen, bin psychisch am Ende!"),
        ("https://www.studis-online.de/forum/2", "Suche Nachmieter für mein WG-Zimmer ab August. 400 Euro warm."),
        ("https://www.studis-online.de/forum/3", "Verkaufe meine alten Skripte für Erstsemester. Meldet euch.")
    ]

    for url, content in mock_posts:
        try:
            cursor.execute("""
                INSERT INTO forum_posts (url, raw_content, status) 
                VALUES (?, ?, 0)
            """, (url, content))
            print(f"[Agent 1] Rohdaten erfolgreich in DB importiert (status=0): {url}")
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


def agent_groq_cleaner():
    """
    Agent 2: Textbereinigung, Reduktion & Human-in-the-Loop Trigger.
    Nutzt Llama 3.2 via GroqCloud. Updates auf status=1, status=-1 (Spam) 
    oder status=3 (Kritischer Fall erfordert menschliches Eingreifen).
    """
    print("[Agent 2] Rufe Open-Source-Modell (Llama 3.2) via Groq-API auf...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, raw_content FROM forum_posts WHERE status = 0")
    records = cursor.fetchall()

    for db_id, raw_text in records:
        if SIMULATION_MODE:
            # --- ACADEMIC SIMULATION: INTEGRATION HUMAN-IN-THE-LOOP ---
            if "Auto schlafen" in raw_text or "psychisch" in raw_text:
                # Ethisch kritischer Fall / Harte Versorgungslücke -> HITL-Trigger
                print(f"[Agent 2 ALERT] Kritischer Härtefall erkannt bei ID {db_id}! Eskaliere zu Status=3 (Human Review Required).")
                cursor.execute("UPDATE forum_posts SET status = 3 WHERE id = ?", (db_id,))
            elif "Nachmieter" in raw_text:
                # Normaler, relevanter Post -> Standard-Workflow
                zusammenfassung = "Student sucht Nachmieter für ein WG-Zimmer für 400 Euro."
                cursor.execute("UPDATE forum_posts SET cleaned_content = ?, status = 1 WHERE id = ?", (zusammenfassung, db_id))
                print(f"[Agent 2] Datensatz ID {db_id} erfolgreich bereinigt (status=1).")
            else:
                # Spam / Unwichtig -> Reject
                cursor.execute("UPDATE forum_posts SET status = -1 WHERE id = ?", (db_id,))
                print(f"[Agent 2] Datensatz ID {db_id} als Spam klassifiziert (status=-1).")
        else:
            # --- LIVE API-ROUTE ---
            try:
                # Hier wird im Prompt verankert, bei Unsicherheit 'NEED_HUMAN' auszugeben
                prompt = f"Analysiere folgenden Text. Wenn es sich um eine akute psychische/existenzielle Krise handelt, antworte NUR mit 'NEED_HUMAN'. Text:\n\n{raw_text}"
                response = client_groq.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "user", "content": prompt}]
                )
                res_content = response.choices[0].message.content.strip()
                
                if "NEED_HUMAN" in res_content:
                    cursor.execute("UPDATE forum_posts SET status = 3 WHERE id = ?", (db_id,))
                # Weiterer Code für status=1 oder -1 ...
            except Exception as e:
                print(f"[Agent 2 Fehler] Cloud-Inferenz fehlgeschlagen: {e}")

    conn.commit()
    conn.close()


def agent_gpt_analyzer():
    """
    Agent 3: Qualitative Tiefenanalyse (Proprietary LLM).
    Nutzt GPT-4o für strukturierte Datenkomponenten. Verarbeitet STRIKT nur status=1.
    Datensätze in status=3 (Human Review) werden hier blockiert und geschützt!
    """
    print("[Agent 3] Rufe Closed-Source-Modell (GPT-4o) via OpenAI-API auf...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # WICHTIG: Verarbeitet nur freigegebene Daten (status=1)
    cursor.execute("SELECT id, cleaned_content FROM forum_posts WHERE status = 1")
    records = cursor.fetchall()

    for db_id, cleaned_text in records:
        print(f"[Agent 3] Analysiere verifizierten Fall-ID {db_id} mit GPT-4o...")
        if SIMULATION_MODE:
            mock_json = {"kategorie": "Wohnungsmarkt / WG-Preise", "schweregrad": 2, "vulnerabilitaet": "Moderat"}
            cursor.execute("UPDATE forum_posts SET analysis_json = ?, status = 2 WHERE id = ?", (json.dumps(mock_json), db_id))
        else:
            # Live OpenAI API-Aufruf mit response_format={ "type": "json_object" }
            pass

    conn.commit()
    conn.close()


def agent_report_generator():
    """
    Agent 4: Aggregation & Berichterstattung.
    Konsolidiert alle Datensätze mit Status=2 und generiert das Abschlussdokument.
    """
    print("[Agent 4] Aggregiere verifizierte Analyseergebnisse (status=2) aus der Datenbank...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT id, cleaned_content, analysis_json FROM forum_posts WHERE status = 2")
    records = cursor.fetchall()

    if records:
        print(f"[Agent 4] Generiere finalen akademischen Evaluierungsbericht im Markdown-Format...")
        # Datei-Export-Logik ...
    else:
        print("[Agent 4] Keine finalisierten Daten (status=2) für Bericht verfügbar.")
        
    conn.close()


# =====================================================================
# ---- 2. INTERVENTIONS-INTERFACE: HUMAN-OVERRIDE ----
# =====================================================================

def human_intervention_interface():
    """
    Schnittstelle für den Human-in-the-Loop.
    Ermöglicht es dem menschlichen Forscher, blockierte Härtefälle (status=3) 
    manuell zu prüfen, zu korrigieren und für die KI-Pipeline freizugeben.
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
        conn.close()
        return

    for db_id, raw_text in blocked_records:
        print(f"\n[MANUELLE PRÜFUNG] Fall-ID: {db_id}")
        print(f"Kritischer Originaltext: '{raw_text}'")
        
        # Simulation der menschlichen Freigabe und manuellen Bereinigung:
        user_input_simulation = "MANUELLE FREIGABE: Akute Obdachlosigkeit und psychische Belastung in Nürnberg."
        print(f"[Forscher-Aktion] Bereinige Text manuell und schalte Fall frei...")
        
        # Auf status=1 setzen, damit Agent 3 (GPT-4o) die Erlaubnis zur Analyse erhält
        cursor.execute("""
            UPDATE forum_posts 
            SET cleaned_content = ?, status = 1 
            WHERE id = ?
        """, (user_input_simulation, db_id))
        print(f"[HITL Interface] Fall {db_id} erfolgreich eskaliert und freigegeben! Status springt auf 1.")

    conn.commit()
    conn.close()


# =====================================================================
# ---- 3. ZENTRALE ORCHESTRIERUNG: SUPERVISOR AGENT ----
# =====================================================================

def supervisor_agent():
    """
    Supervisor: Der primäre Orchestrator.
    Steuert den Datenfluss und schaltet das Human-in-the-Loop Interventions-Interface 
    gezielt zwischen den Agenten-Phasen ein.
    """
    print("\n=====================================================================")
    print("--- [Supervisor] Haupt-Agent gestartet: Initiiere System-Scan ---")
    print("=====================================================================")
    
    # 1. Infrastruktur & Datenerfassung
    init_db()
    agent_data_fetcher()     # Schritt 1: Extraktion (Ergibt status=0)
    
    # 2. KI-Erstprüfung & HITL-Filterung
    agent_groq_cleaner()     # Schritt 2: Groq Filter (Ergibt status=1, status=-1 ODER status=3)
    
    # =================================================================
    # INTERVENTION: Hier übernimmt der Mensch die Kontrolle über die DB!
    # =================================================================
    human_intervention_interface()
    
    # 3. Tiefenanalyse & Export der bereinigten + manuell freigegebenen Daten
    agent_gpt_analyzer()     # Schritt 3: OpenAI Analyse (Verarbeitet alle status=1 -> status=2)
    agent_report_generator()  # Schritt 4: Abschlussbericht
    
    print("\n=====================================================================")
    print("--- [Supervisor] Alle Agenten-Phasen inklusive HITL erfolgreich durchlaufen. ---")
    print("=====================================================================\n")


if __name__ == "__main__":
    supervisor_agent()