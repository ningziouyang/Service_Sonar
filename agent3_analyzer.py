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
    # Tabellen, die Agent 3 kennt. Neue Quellen einfach hier ergänzen,
    # dann per --table ansprechbar.
    KNOWN_TABLES = {"forum_posts", "hilferuf_posts", "gutefrage_posts"}

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
        Gibt bei Fehlern (Rate-Limit, Netzwerk, ungültiges JSON) immer ein
        dict mit "error"-Schlüssel zurück, nie None -> _store_failed_analysis
        kann das direkt als error_payload weiterverwenden.
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
                temperature=0.1,  # Niedrige Temperatur für sehr konsistente JSON-Ausgabe
                response_format={"type": "json_object"}  # Erzwingt JSON
            )

            result_text = response.choices[0].message.content
            return json.loads(result_text)

        except Exception as e:
            print(f"[Agent 3 ERROR] API-Aufruf fehlgeschlagen: {e}")
            return {
                "error": "API_CALL_FAILED",
                "reason": str(e),
                "problem_cluster": "Unbekannt"
            }

    def _validate_analysis_schema(self, analysis: dict) -> tuple[bool, dict]:
        """
        Prüft, ob die LLM-Antwort die erwartete Agent-3-Struktur hat.
        Nur valide Analysen dürfen als status=2 in die weitere Pipeline.
        """
        required_fields = {
            "problem_cluster": str,
            "urgency": str,
            "emotional_tone": str,
            "stakeholders": list,
        }

        if not isinstance(analysis, dict):
            return False, {
                "error": "INVALID_SCHEMA",
                "reason": "LLM response is not a JSON object."
            }

        missing_fields = [
            field for field in required_fields
            if field not in analysis or analysis[field] in [None, ""]
        ]

        if missing_fields:
            return False, {
                "error": "INVALID_SCHEMA",
                "reason": f"Missing required fields: {', '.join(missing_fields)}",
                "received": analysis
            }

        wrong_types = [
            field for field, expected_type in required_fields.items()
            if not isinstance(analysis[field], expected_type)
        ]

        if wrong_types:
            return False, {
                "error": "INVALID_SCHEMA",
                "reason": f"Wrong field types: {', '.join(wrong_types)}",
                "received": analysis
            }

        allowed_urgencies = {"Hoch", "Mittel", "Niedrig"}
        normalized_urgency = analysis["urgency"].strip().capitalize()

        if normalized_urgency not in allowed_urgencies:
            return False, {
                "error": "INVALID_SCHEMA",
                "reason": f"Invalid urgency value: {analysis['urgency']}",
                "received": analysis
            }

        analysis["urgency"] = normalized_urgency  # store the cleaned-up value
        return True, analysis

    def _store_failed_analysis(self, cursor, table_name: str, db_id: int, error_payload: dict,
                                current_attempts: int, max_attempts: int):
        """
        Speichert fehlgeschlagene Agent-3-Analysen und erhöht den Attempt-Zähler.
        Nach max_attempts wird der Beitrag in zukünftigen Refresh-Runs übersprungen.
        """
        next_attempts = current_attempts + 1
        retry_blocked = next_attempts >= max_attempts

        error_payload["analysis_attempts"] = next_attempts
        error_payload["max_attempts"] = max_attempts
        error_payload["retry_blocked"] = retry_blocked

        error_json = json.dumps(error_payload, ensure_ascii=False, indent=2)

        cursor.execute(
            f"""
            UPDATE {table_name}
            SET analysis_json = ?, status = 1, analysis_attempts = ?
            WHERE id = ?
            """,
            (error_json, next_attempts, db_id)
        )

        if retry_blocked:
            print(
                f"[Agent 3 ERROR] Analyse für ID {db_id} ({table_name}) fehlgeschlagen "
                f"({next_attempts}/{max_attempts}) -> wird in zukünftigen Refresh-Runs übersprungen."
            )
        else:
            print(
                f"[Agent 3 ERROR] Analyse für ID {db_id} ({table_name}) fehlgeschlagen "
                f"({next_attempts}/{max_attempts}) -> bleibt status=1."
            )

    def _ensure_analysis_attempts_column(self, cursor, table_name: str):
        """
        Ensures older Tabellen auch die analysis_attempts-Spalte haben.
        Wird gebraucht, wenn Agent 3 direkt läuft, ohne dass main.py/init_db()
        die Spalte schon angelegt hat.
        """
        try:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN analysis_attempts INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists.

    def run(self, table_name="forum_posts", limit=None, offset=0, sleep_seconds=0.0, max_attempts=3):
        """
        Agent 3 Interface: LLM-basierte semantische Analyse.
        Verarbeitet eine einzelne Quelltabelle (forum_posts, hilferuf_posts,
        gutefrage_posts, ...). Validiert die LLM-Antwort gegen das erwartete
        Schema und respektiert einen Retry-Zähler (max_attempts) pro Beitrag.
        """
        if table_name not in self.KNOWN_TABLES:
            raise ValueError(
                f"Unbekannte Tabelle '{table_name}'. Bekannt: {sorted(self.KNOWN_TABLES)}"
            )

        print(f"[Agent 3] Starte semantische Analyse über LLM ({self.model_name}) für Tabelle '{table_name}'...")
        if limit is not None:
            print(f"[Agent 3] Batch-Modus aktiv: limit={limit}, offset={offset}, sleep={sleep_seconds}s")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        self._ensure_analysis_attempts_column(cursor, table_name)
        conn.commit()

        query = f"""
            SELECT id, cleaned_content, COALESCE(analysis_attempts, 0)
            FROM {table_name}
            WHERE status = 1
            AND COALESCE(analysis_attempts, 0) < ?
            ORDER BY id ASC
        """
        params = [max_attempts]

        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        cursor.execute(query, params)
        records = cursor.fetchall()

        if not records:
            print(f"[Agent 3 INFO] Keine bereinigten Beiträge mit status=1 in '{table_name}' gefunden.")
            conn.close()
            return

        for db_id, cleaned_content, analysis_attempts in records:
            if not cleaned_content:
                continue

            # 🚀 Hier rufen wir das echte KI-Modell auf!
            analysis_dict = self._call_llm_api(cleaned_content)

            # Wenn der API-Aufruf fehlschlägt, darf der Beitrag nicht als
            # erfolgreich analysiert gelten.
            if "error" in analysis_dict:
                self._store_failed_analysis(
                    cursor=cursor,
                    table_name=table_name,
                    db_id=db_id,
                    error_payload=analysis_dict,
                    current_attempts=analysis_attempts,
                    max_attempts=max_attempts,
                )
                conn.commit()
                continue

            is_valid, validated_result = self._validate_analysis_schema(analysis_dict)

            if not is_valid:
                self._store_failed_analysis(
                    cursor=cursor,
                    table_name=table_name,
                    db_id=db_id,
                    error_payload=validated_result,
                    current_attempts=analysis_attempts,
                    max_attempts=max_attempts,
                )
                conn.commit()
                continue

            analysis_dict = validated_result

            # Füge Metadaten hinzu (damit man später sieht, wie es analysiert wurde)
            analysis_dict["analysis_method"] = f"llm_api ({self.model_name})"
            analysis_dict["weak_signal_relevance"] = analysis_dict.get("urgency") in ["Mittel", "Hoch"]

            analysis_json = json.dumps(analysis_dict, ensure_ascii=False, indent=2)

            cursor.execute(
                f"""
                UPDATE {table_name}
                SET analysis_json = ?, status = 2
                WHERE id = ?
                """,
                (analysis_json, db_id)
            )
            conn.commit()  # nach jedem Post committen, damit bei Abbruch nichts verloren geht

            print(f"[Agent 3] LLM-Analyse abgeschlossen für ID {db_id} ({table_name}) -> status=2.")

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        conn.close()
        print(f"\n[Agent 3] Verarbeitung von '{table_name}' abgeschlossen.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Agent 3 semantic LLM analysis on cleaned forum posts.")
    parser.add_argument("--table", type=str, default="forum_posts",
                         help="Quelltabelle: forum_posts, hilferuf_posts oder gutefrage_posts.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of status=1 records to process.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many status=1 records before processing.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to wait between LLM calls.")
    parser.add_argument("--max-attempts", type=int, default=3,
                         help="Maximum failed Agent 3 attempts before a record is skipped.")
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be a positive integer.")
    if args.offset < 0:
        raise ValueError("--offset must not be negative.")
    if args.sleep < 0:
        raise ValueError("--sleep must not be negative.")
    if args.max_attempts <= 0:
        raise ValueError("--max-attempts must be a positive integer.")

    analyzer = Agent3Analyzer()
    analyzer.run(
        table_name=args.table,
        limit=args.limit,
        offset=args.offset,
        sleep_seconds=args.sleep,
        max_attempts=args.max_attempts,
    )