import json
import sqlite3
import os
import argparse
import time

try:
    from openai import OpenAI
except ModuleNotFoundError:
    OpenAI = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

# Lädt lokale .env-Dateien, wenn python-dotenv installiert ist.
if load_dotenv:
    load_dotenv()

class Agent3Analyzer:
    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file

        if OpenAI is None:
            raise ValueError("[WARNUNG] Das Python-Paket 'openai' ist nicht installiert.")
        
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

    def run(self, limit=None, offset=0, sleep_seconds=0.0):
        """
        Agent 3 Interface: LLM-basierte semantische Analyse.
        """
        print(f"[Agent 3] Starte semantische Analyse über LLM ({self.model_name})...")
        if limit is not None:
            print(f"[Agent 3] Batch-Modus aktiv: limit={limit}, offset={offset}, sleep={sleep_seconds}s")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        query = """
            SELECT id, cleaned_content
            FROM forum_posts
            WHERE status = 1
            ORDER BY id ASC
        """
        params = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor.execute(query, params)
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

            # Wenn der API-Aufruf fehlschlägt, darf der Beitrag nicht als erfolgreich analysiert gelten.
            if "error" in analysis_dict:
                error_json = json.dumps(analysis_dict, ensure_ascii=False, indent=2)

                cursor.execute(
                    """
                    UPDATE forum_posts
                    SET analysis_json = ?, status = 1
                    WHERE id = ?
                    """,
                    (error_json, db_id)
                )

                print(f"[Agent 3 ERROR] Analyse für ID {db_id} fehlgeschlagen -> bleibt status=1.")
                continue

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

            print(f"[Agent 3] LLM-Analyse abgeschlossen für ID {db_id} -> status=2.")

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        conn.commit()
        conn.close()
        print("\n[Agent 3] Verarbeitung abgeschlossen.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Agent 3 semantic LLM analysis on cleaned forum posts.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of status=1 records to process.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many status=1 records before processing.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to wait between LLM calls.")
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be a positive integer.")
    if args.offset < 0:
        raise ValueError("--offset must not be negative.")
    if args.sleep < 0:
        raise ValueError("--sleep must not be negative.")

    analyzer = Agent3Analyzer()
    analyzer.run(limit=args.limit, offset=args.offset, sleep_seconds=args.sleep)
