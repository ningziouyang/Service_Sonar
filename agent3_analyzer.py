import json
import sqlite3
import os
from openai import OpenAI
from dotenv import load_dotenv

# Lädt die Umgebungsvariablen
load_dotenv()

class Agent3Analyzer:
    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file
        
        # ============================================================
        # 🔑 Groq API Konfiguration
        # ============================================================
        self.api_key = os.getenv("GROQ_API_KEY") 
        
        if not self.api_key:
            raise ValueError("[WARNUNG] GROQ_API_KEY wurde nicht in der .env Datei gefunden!")

        self.client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=self.api_key
        )
        
        # ✅ Hier ist das brandneue Llama 3.3 Modell eingetragen!
        self.model_name = "llama-3.3-70b-versatile" 
        # ============================================================

    def _call_llm_api(self, text: str) -> dict:
        """
        Ruft die externe Open-Source-LLM-API auf und erzwingt eine JSON-Antwort.
        """
        system_prompt = """Du bist ein Analytiker für studentische Forenbeiträge. 
        Analysiere den folgenden Text und gib AUSSCHLIESSLICH ein JSON-Objekt zurück. 
        Format:
        {
            "problem_cluster": "Wohnen / Finanzen / Studium / Mentale Gesundheit / Sonstiges",
            "urgency": "Hoch / Mittel / Niedrig",
            "emotional_tone": "Akut belastet / Frustriert / Hilfesuchend / Neutral",
            "stakeholders": ["Studierendenwerk", "BAföG-Amt", "etc."]
        }"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1, # Niedrige Temperatur für sehr konsistente JSON-Ausgabe
                response_format={"type": "json_object"} # Erzwingt JSON
            )
            
            result_text = response.choices[0].message.content
            return json.loads(result_text)

        except Exception as e:
            print(f"[Agent 3 ERROR] API-Aufruf fehlgeschlagen: {e}")
            return {"error": "API Timeout", "problem_cluster": "Unbekannt"}

    def run(self):
        """
        Agent 3 Interface: LLM-basierte semantische Analyse.
        """
        print(f"[Agent 3] Starte semantische Analyse über LLM ({self.model_name})...")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute("SELECT id, cleaned_content FROM forum_posts WHERE status = 1")
        records = cursor.fetchall()

        if not records:
            print("[Agent 3 INFO] Keine bereinigten Beiträge mit status=1 gefunden.")
            conn.close()
            return

        for db_id, cleaned_content in records:
            if not cleaned_content:
                continue

            # 🚀 Hier rufen wir das echte KI-Modell auf!
            analysis_dict = self._call_llm_api(cleaned_content)
            
            # Füge Metadaten hinzu (damit man später sieht, wie es analysiert wurde)
            analysis_dict["analysis_method"] = f"llm_api ({self.model_name})"
            analysis_dict["weak_signal_relevance"] = analysis_dict.get("urgency") in ["Mittel", "Hoch"]
            
            analysis_json = json.dumps(analysis_dict, ensure_ascii=False, indent=2)

            cursor.execute(
                """
                UPDATE forum_posts
                SET analysis_json = ?, status = 2
                WHERE id = ?
                """,
                (analysis_json, db_id)
            )
            print(f"[Agent 3] LLM-Analyse abgeschlossen für ID {db_id} → status=2.")

        conn.commit()
        conn.close()
        print("\n[Agent 3] Verarbeitung abgeschlossen.")

if __name__ == "__main__":
    analyzer = Agent3Analyzer()
    analyzer.run()