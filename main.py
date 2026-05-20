# =====================================================================
# main.py - Vollständige Status-Infrastruktur für das Supervisor-MAS
# Architektonischer Ansatz: SQLite-State-Machine & Cloud-Hybrid-LLM
# =====================================================================

import os
import sqlite3
import json
from openai import OpenAI

# =====================================================================
# ---- 0. INFRASTRUKTUR-INITIALISIERUNG (API & DATABASE) ----
# =====================================================================

# Config: GroqCloud (Open-Source Llama 3.2)
GROQ_API_KEY = "gsk_xxxx_Hier_deinen_Groq_Key_einfügen"
client_groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

# Config: OpenAI (Closed-Source GPT-4o)
OPENAI_API_KEY = "sk-proj-xxxx_Hier_deinen_OpenAI_Key_einfügen"
client_openai = OpenAI(
    api_key=OPENAI_API_KEY
)

DB_FILE = "service_sonar.db"

def init_db():
    """Initialisiert die lokale SQLite-Datenbank und erstellt die Zustandstabelle."""
    print("[DB] Initialisiere SQLite-Datenbank und Tabellen...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS forum_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            raw_content TEXT,
            cleaned_content TEXT,
            analysis_json TEXT,
            status INTEGER DEFAULT 0  -- 0: Raw, 1: Cleaned, 2: Analyzed, -1: Rejected
        )
    """)
    conn.commit()
    conn.close()


# =====================================================================
# ---- 1. DIE 4 WORKER-AGENTEN (ZUSTANDSSTEUERUNG) ----
# =====================================================================

def agent_data_fetcher():
    """
    Agent 1: Forum-Scraper (Reiner Python-Code).
    Sammelt Rohdaten von Studis Online und speichert sie mit status=0.
    """
    print("[Agent 1] Starte Datenakquisition von 'Studis Online'...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Dummy-Mock-Daten für die Demo (Simuliert 2 verschiedene Foren-Beiträge)
    mock_posts = [
        ("https://www.studis-online.de/forum/1", "Ich warte seit 6 Monaten auf einen Platz im Studentenwohnheim in Nürnberg. Muss im Auto schlafen!! Hilfe!"),
        ("https://www.studis-online.de/forum/2", "Verkaufe mein altes BWL-Lehrbuch für 10 Euro. Bei Interesse PM an mich.")
    ]

    for url, content in mock_posts:
        try:
            cursor.execute("""
                INSERT INTO forum_posts (url, raw_content, status) 
                VALUES (?, ?, 0)
            """, (url, content))
            print(f"[Agent 1] Rohdaten erfolgreich in DB importiert (status=0): {url}")
        except sqlite3.IntegrityError:
            # Verhindert Duplikate bei mehrmaligem Ausführen
            pass

    conn.commit()
    conn.close()


def agent_groq_cleaner():
    """
    Agent 2: Datensäuberung & Relevanz-Filter (Llama 3.2 via Groq API).
    Verarbeitet Daten mit status=0. Aktualisiert auf status=1 oder status=-1 (Spam).
    """
    print("[Agent 2] Scanne Datenbank nach neuen Rohdaten (status=0)...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, raw_content FROM forum_posts WHERE status = 0")
    records = cursor.fetchall()

    if not records:
        print("[Agent 2] Keine neuen Rohdaten gefunden.")
        conn.close()
        return

    for db_id, raw_text in records:
        print(f"[Agent 2] Verarbeite Datensatz ID {db_id} via Groq Cloud...")
        try:
            # In der Live-Phase entkommentieren, um die API scharf zu schalten:
            # prompt = f"Analysiere, ob dieser Post studentische Probleme (Wohnnot, Finanzen) beschreibt. Wenn NEIN, antworte NUR mit 'REJECT'. Wenn JA, fasse das Kernproblem auf Deutsch kurz zusammen:\n\n{raw_text}"
            # response = client_groq.chat.completions.create(
            #     model="llama3-8b-8192",
            #     messages=[{"role": "user", "content": prompt}]
            # )
            # result = response.choices[0].message.content.strip()
            
            # --- SIMULATION FÜR DAS MEETING ---
            if "Auto schlafen" in raw_text:
                result = "Student leidet unter extremer Wohnungsnot in Nürnberg, wartet seit 6 Monaten auf Wohnheimplatz."
                new_status = 1
                print(f"[Agent 2] Datensatz ID {db_id} als RELEVANT eingestuft (status=1).")
            else:
                result = "REJECTED_SPAM_LEHRBUCHVERKAUF"
                new_status = -1
                print(f"[Agent 2] Datensatz ID {db_id} als IRRELEVANT gefiltert (status=-1).")
            # ----------------------------------

            cursor.execute("""
                UPDATE forum_posts 
                SET cleaned_content = ?, status = ? 
                WHERE id = ?
            """, (result, new_status, db_id))

        except Exception as e:
            print(f"[Agent 2 Fehler] Fehler bei ID {db_id}: {e}")

    conn.commit()
    conn.close()


def agent_gpt_analyzer():
    """
    Agent 3: Qualitative Tiefenanalyse (GPT-4o via OpenAI API).
    Verarbeitet Daten mit status=1. Extrahiert soziale Versorgungslücken als JSON.
    Aktualisiert auf status=2.
    """
    print("[Agent 3] Scanne Datenbank nach bereinigten Daten (status=1)...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT id, cleaned_content FROM forum_posts WHERE status = 1")
    records = cursor.fetchall()

    if not records:
        print("[Agent 3] Keine zu analysierenden Daten gefunden.")
        conn.close()
        return

    for db_id, cleaned_text in records:
        print(f"[Agent 3] Analysiere Fall-ID {db_id} mit GPT-4o...")
        try:
            # In der Live-Phase entkommentieren (Structured Outputs):
            # response = client_openai.chat.completions.create(
            #     model="gpt-4o",
            #     response_format={"type": "json_object"},
            #     messages=[{"role": "user", "content": f"Erstelle ein JSON mit den Feldern 'kategorie', 'schweregrad' (1-5) und 'vulnerabilität' für folgendes Problem: {cleaned_text}"}]
            # )
            # json_output = response.choices[0].message.content
            
            # --- SIMULATION FÜR DAS MEETING ---
            mock_json = {
                "kategorie": "Wohnnot / Infrastruktur",
                "schweregrad": 5,
                "vulnerabilität": "Extrem hoch (Obdachlosigkeit droht)"
            }
            json_output = json.dumps(mock_json, ensure_ascii=False)
            print(f"[Agent 3] Strukturierte JSON-Analyse für ID {db_id} generiert (status=2).")
            # ----------------------------------

            cursor.execute("""
                UPDATE forum_posts 
                SET analysis_json = ?, status = 2 
                WHERE id = ?
            """, (json_output, db_id))

        except Exception as e:
            print(f"[Agent 3 Fehler] Fehler bei ID {db_id}: {e}")

    conn.commit()
    conn.close()


def agent_report_generator():
    """
    Agent 4: Aggregation & Export (Reiner Python-Code).
    Sammelt alle Datensätze mit status=2 und exportiert einen finalen Markdown-Bericht.
    """
    print("[Agent 4] Generiere finalen akademischen Evaluierungsbericht...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT id, cleaned_content, analysis_json FROM forum_posts WHERE status = 2")
    records = cursor.fetchall()

    if not records:
        print("[Agent 4] Keine finalisierten Daten (status=2) für den Bericht vorhanden.")
        conn.close()
        return

    report_content = "# Akademischer Evaluierungsbericht: Studentische Versorgungslücken 2026\n\n"
    
    for db_id, summary, json_str in records:
        analysis = json.loads(json_str)
        report_content += f"## Fall-Analyse #{db_id}\n"
        report_content += f"- **Zusammenfassung:** {summary}\n"
        report_content += f"- **Kategorie:** {analysis.get('kategorie')}\n"
        report_content += f"- **Schweregrad:** {analysis.get('schweregrad')}/5\n"
        report_content += f"- **Risikobewertung:** {analysis.get('vulnerabilität')}\n\n"
        report_content += "---\n\n"

    # Speichern als Markdown-Datei
    with open("Service_Sonar_Abschlussbericht.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    print("[Agent 4] Bericht erfolgreich exportiert: 'Service_Sonar_Abschlussbericht.md'")
    conn.close()


# =====================================================================
# ---- 2. DER CENTRAL ORCHESTRATOR: SUPERVISOR AGENT ----
# =====================================================================

def supervisor_agent():
    """
    Der Supervisor (Haupt-Agent): Er steuert als zentraler Orchestrator den
    gesamten Lebenszyklus der Daten und delegiert die Aufgaben.
    """
    print("\n=====================================================================")
    print("--- [Supervisor] Haupt-Agent aktiviert: Starte Pipeline-Steuerung ---")
    print("=====================================================================")
    
    # Zustand 0: Initialisierung und Rohdatenerfassung
    init_db()
    agent_data_fetcher()
    
    # Zustand 1: Datenbereinigung und Filterung via Groq Cloud (Open-Source)
    agent_groq_cleaner()
    
    # Zustand 2: Tiefenanalyse via OpenAI Cloud (Closed-Source)
    agent_gpt_analyzer()
    
    # Abschluss: Berichterstattung
    agent_report_generator()
    
    print("\n=====================================================================")
    print("--- [Supervisor] Alle Agenten-Phasen erfolgreich beendet. ---")
    print("=====================================================================\n")

if __name__ == "__main__":
    supervisor_agent()