import os
import json
import sqlite3
from openai import OpenAI
from dotenv import load_dotenv

# Lädt die versteckten Umgebungsvariablen aus der .env-Datei (z.B. GROQ_API_KEY)
load_dotenv()

class Agent4Innovator:
    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file
        self.api_key = os.getenv("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError("[WARNUNG] GROQ_API_KEY fehlt in der .env Datei!")
            
        # Initialisierung des OpenAI-Clients, umgeleitet auf die Groq-Infrastruktur
        self.client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=self.api_key
        )
        self._init_report_table()

    def _init_report_table(self):
        """Erstellt eine neue Tabelle exklusiv für die generierten Dashboard-Insights."""
        conn = sqlite3.connect(self.db_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                report_json TEXT
            )
        """)
        conn.commit()
        conn.close()

    def run(self):
        """
        Agent 4 Interface: Aggregation verifizierter Daten und Generierung von Lösungsansätzen.
        """
        print("\n---------------------------------------------------------------------")
        print("[Agent 4] Starte Innovations-Generator (Llama 3.3 via Groq)...")
        print("---------------------------------------------------------------------")
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Hole alle verifizierten und von Agent 3 analysierten Datensätze (status=2)
        cursor.execute("SELECT cleaned_content, analysis_json FROM forum_posts WHERE status = 2")
        records = cursor.fetchall()

        if not records:
            print("[Agent 4 INFO] Keine ausreichenden Daten (status=2) für die Innovationsgenerierung vorhanden.")
            conn.close()
            return

        # 1. Empirischen Kontext für das LLM aufbauen
        print(f"[Agent 4] Aggregiere {len(records)} Fallbeispiele für die KI-Inferenz...")
        context_data = []
        for text, j_str in records:
            context_data.append(f"Text: {text}\nAnalyse: {j_str}")
        
        # Begrenzung der Zeichenlänge, um Context-Window-Limits (Token-Limits) zu vermeiden
        context_text = "\n\n".join(context_data)[:10000] 

        # 2. System Prompt mit striktem Zwang zur JSON-Ausgabe
        system_prompt = """Du bist ein Innovations-Stratege für studentische Services. 
        Analysiere die empirischen Daten und generiere EINE konkrete, technologische oder soziale Service-Lösung.
        Du MUSST ein reines JSON-Objekt zurückgeben. Das Format MUSS exakt so aussehen:
        {
            "cluster": "Name des Hauptproblem-Clusters (z.B. Wohnungsnot & Bürokratie)",
            "opportunity": "Einprägsamer Name der Lösung (z.B. Bürokratie-Navigator)",
            "solution": "2-3 Sätze architektonische Beschreibung des Konzepts",
            "target": "Zielgruppe (z.B. Internationale Erstsemester)",
            "stakeholder": "Zuständige Akteure (z.B. Studierendenwerk, IT-Zentrum)"
        }"""

        try:
            # 3. LLM API Call über Groq (Nutzung des großen Llama 3.3 Modells)
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Hier sind die Daten:\n{context_text}"}
                ],
                response_format={"type": "json_object"}, # Erzwingt maschinenlesbares JSON!
                temperature=0.7 # Höhere Temperatur für kreativere Lösungsansätze
            )
            
            result_json_str = response.choices[0].message.content
            
            # 4. Das generierte JSON in der Datenbank speichern (für das Streamlit Dashboard)
            cursor.execute("INSERT INTO system_reports (report_json) VALUES (?)", (result_json_str,))
            conn.commit()
            print("[Agent 4 SUCCESS] Neue Service-Innovation erfolgreich generiert und in der DB gespeichert!")
            
        except Exception as e:
            print(f"[Agent 4 ERROR] Innovations-Generierung fehlgeschlagen: {e}")
            
        conn.close()

if __name__ == "__main__":
    innovator = Agent4Innovator()
    innovator.run()