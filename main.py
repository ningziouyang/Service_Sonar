import sqlite3
import json
from openai import OpenAI

# =====================================================================
# ---- 0. INFRASTRUKTUR-KONFIGURATION (REIN OPEN-SOURCE VIA GROQ) ----
# =====================================================================

GROQ_API_KEY = "gsk_xxxx_Hier_deinen_Groq_Key_einfügen"
client_groq = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY
)

DB_FILE = "service_sonar.db"


# =====================================================================
# ---- 🌟 AGENT 4: GENERATIVER INNOVATIONS-AGENT ----
# =====================================================================
def agent_report_generator():
    """
    Agent 4: Aggregation & Generierung innovativer Lösungsansätze.
    Zuständigkeit: Teammitglied B
    Task: Liest alle quantitativen Analyseergebnisse (status=2) aus, nutzt Llama 3.3 (70B)
          für die cross-analytische Synthese und generiert konkrete, innovative Konzepte.
    """
    print("[Agent 4] Aggregiere verifizierte Ergebnisse (status=2) für die Innovations-Synthese...")
    
    # 1. Verbindung zur Datenbank
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 2. Nur Daten abfragen, die von Agent 3 fertig analysiert und strukturiert wurden (status=2)
    cursor.execute("SELECT id, cleaned_content, analysis_json FROM forum_posts WHERE status = 2")
    records = cursor.fetchall()
    
    if not records:
        print("[Agent 4 INFO] Keine ausreichend analysierten Daten (status=2) für die Innovationsgenerierung vorhanden.")
        conn.close()
        return

    # 3. Forschungsdaten für den Kontext des Modells bündeln
    forschungskontext = ""
    for db_id, cleaned_text, json_str in records:
        forschungskontext += f"--- DATENSATZ HARTE FAKTEN ID {db_id} ---\n"
        forschungskontext += f"Empirischer Text: {cleaned_text}\n"
        forschungskontext += f"Strukturierte KI-Analyse: {json_str}\n\n"

    # 4. Groq-API Aufruf mit starker Innovations-Direktive im System Prompt
    print("[Agent 4] Rufe Llama 3.3 (70B) via Groq auf für den kreativen Denkprozess...")
    try:
        # Fest verankerte akademische Struktur für maximale Innovationskraft
        system_prompt = """
        Du bist ein renommierter Professor für Sozialwissenschaften und Innovationsmanagement an einer deutschen Universität.
        Deine Aufgabe ist es, basierend auf den quantitativen Daten von Agent 3 einen hochgradig innovativen Forschungsbericht zu schreiben.

        Der Bericht MUSS im Markdown-Format verfasst sein und zwingend folgende akademische Struktur aufweisen:
        1. Executive Summary
        2. Aggregierte Analyse der studentischen Versorgungslücken (Clustering nach Problemfeldern)
        3. 🌟 INNOVATIVE LÖSUNGSANSÄTZE (Der wichtigste Teil):
           - Entwickle mindestens 3 konkrete, technologiegestützte oder sozial-innovative Konzepte, die diese Lücken schließen können (z.B. plattformbasierte Ansätze, Peer-to-Peer-Modelle oder Reformvorschläge).
           - Jede Lösung muss eine 'Machbarkeitsanalyse' (Feasibility) und den 'erwarteten Impact' enthalten.
        4. Kritische Würdigung & Ausblick

        Schreibe in einem anspruchsvollen, präzisen wissenschaftlichen Fließtext auf Deutsch. Vermeide reine, kontextlose Aufzählungen.
        """
        
        user_prompt = f"Hier sind die empirischen Daten aus unserer Datenbank. Generiere daraus die innovativen Lösungsansätze:\n\n{forschungskontext}"
        
        # Inferenz über das extrem leistungsstarke Llama 3.3 70B Modell
        response = client_groq.chat.completions.create(
            model="llama-3.3-70b-specdec",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7 # Leicht erhöhte Kreativität für innovativere Ansätze
        )
        
        innovations_bericht = response.choices[0].message.content
        
        # 5. Den von der KI generierten Innovationsbericht als .md Datei auf die Festplatte schreiben
        report_filename = "Service_Sonar_Innovationsbericht.md"
        with open(report_filename, "w", encoding="utf-8") as file:
            file.write(innovations_bericht)
            
        print("\n=====================================================================")
        print(f"🎉 🎉 SUCCESS: Innovationsbericht erfolgreich generiert! 🎉 🎉")
        print(f"-> Datei gespeichert unter: [ {report_filename} ]")
        print("=====================================================================\n")
        
    except Exception as e:
        print(f"[Agent 4 Fehler] Open-Source Innovations-Generierung fehlgeschlagen: {e}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    agent_report_generator()