import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class Agent4Innovator:
    """
    LLM-only innovation generator.

    The final report is always produced by an LLM. To survive Groq limits, this
    agent compresses Agent 3 outputs before the call, caches reports by source
    signature, retries 429/transient failures, and can fall back to additional
    OpenAI-compatible providers configured through environment variables.
    """

    REQUIRED_INNOVATION_FIELDS = ("cluster", "opportunity", "solution", "target", "stakeholder")

    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file
        self.max_retries = int(os.getenv("AGENT4_MAX_RETRIES", "3"))
        self.retry_base_seconds = float(os.getenv("AGENT4_RETRY_BASE_SECONDS", "4"))
        self.max_retry_sleep = float(os.getenv("AGENT4_MAX_RETRY_SLEEP", "45"))
        self.temperature = float(os.getenv("AGENT4_TEMPERATURE", "0.65"))
        self.max_examples = int(os.getenv("AGENT4_MAX_EXAMPLES", "6"))
        self.max_example_chars = int(os.getenv("AGENT4_MAX_EXAMPLE_CHARS", "420"))
        self.providers = self._load_providers()

        if not self.providers:
            raise ValueError(
                "[Agent 4 ERROR] No LLM provider configured. Add GROQ_API_KEY, "
                "OPENAI_API_KEY, OPENROUTER_API_KEY, DEEPSEEK_API_KEY, or enable "
                "local Ollama with OLLAMA_ENABLED=true."
            )

        self._init_report_table()

    def _load_providers(self):
        provider_defs = {
            "groq": {
                "api_key": os.getenv("GROQ_API_KEY"),
                "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            },
            "openai": {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "base_url": os.getenv("OPENAI_BASE_URL"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            },
            "openrouter": {
                "api_key": os.getenv("OPENROUTER_API_KEY"),
                "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            },
            "deepseek": {
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            },
            "ollama": {
                "enabled": self._env_enabled("OLLAMA_ENABLED") or bool(os.getenv("OLLAMA_MODEL")),
                "api_key": os.getenv("OLLAMA_API_KEY", "ollama"),
                "base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
                "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
            },
        }

        order = os.getenv("AGENT4_PROVIDER_ORDER", "groq,openai,openrouter,deepseek,ollama")
        providers = []
        for name in [item.strip().lower() for item in order.split(",") if item.strip()]:
            config = provider_defs.get(name)
            if not config or not config.get("enabled", True) or not config["api_key"]:
                continue

            client_kwargs = {"api_key": config["api_key"]}
            if config["base_url"]:
                client_kwargs["base_url"] = config["base_url"]

            providers.append(
                {
                    "name": name,
                    "model": config["model"],
                    "client": OpenAI(**client_kwargs),
                }
            )
        return providers

    def _env_enabled(self, name):
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    def _init_report_table(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                report_json TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def _load_analyzed_records(self, cursor):
        cursor.execute(
            """
            SELECT id, cleaned_content, analysis_json
            FROM forum_posts
            WHERE status = 2 AND analysis_json IS NOT NULL
            ORDER BY id ASC
            """
        )
        return cursor.fetchall()

    def _latest_report(self, cursor):
        cursor.execute("SELECT id, created_at, report_json FROM system_reports ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return None

        try:
            report = json.loads(row[2])
        except json.JSONDecodeError:
            report = {}

        return {"id": row[0], "created_at": row[1], "report": report, "raw": row[2]}

    def _source_signature(self, records):
        digest = hashlib.sha256()
        for db_id, cleaned_text, analysis_json in records:
            digest.update(str(db_id).encode("utf-8"))
            digest.update(b"\0")
            digest.update((analysis_json or "").encode("utf-8", errors="ignore"))
            digest.update(b"\0")
            digest.update((cleaned_text or "")[:120].encode("utf-8", errors="ignore"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _parse_analysis(self, analysis_json):
        try:
            data = json.loads(analysis_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _shorten(self, text, limit):
        clean = " ".join(str(text or "").split())
        if len(clean) <= limit:
            return clean
        return clean[: limit - 1].rstrip() + "..."

    def _limit_description(self, text, max_sentences=2, max_chars=180):
        clean = " ".join(str(text or "").split())
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        shortened = " ".join(sentences[:max_sentences]).strip()

        if len(shortened) <= max_chars:
            return shortened

        return shortened[: max_chars - 1].rstrip() + "…"

    def _build_evidence_bundle(self, records, source_signature):
        clusters = Counter()
        urgencies = Counter()
        tones = Counter()
        stakeholders = Counter()
        stakeholder_clusters = defaultdict(Counter)
        stakeholder_examples = defaultdict(list)
        cluster_urgencies = defaultdict(Counter)
        representative_pool = []

        for db_id, cleaned_text, analysis_json in records:
            analysis = self._parse_analysis(analysis_json)
            cluster = analysis.get("problem_cluster") or "Unbekannt"
            urgency = analysis.get("urgency") or "Unbekannt"
            tone = analysis.get("emotional_tone") or "Unbekannt"
            stakeholder_list = analysis.get("stakeholders")
            if not isinstance(stakeholder_list, list):
                stakeholder_list = []

            clusters[cluster] += 1
            urgencies[urgency] += 1
            tones[tone] += 1
            cluster_urgencies[cluster][urgency] += 1

            clean_stakeholders = [
                str(item).strip()
                for item in stakeholder_list
                if str(item).strip()
            ]
            stakeholders.update(clean_stakeholders)

            for stakeholder in clean_stakeholders:
                stakeholder_clusters[stakeholder][cluster] += 1
                if len(stakeholder_examples[stakeholder]) < 2:
                    stakeholder_examples[stakeholder].append(
                        self._shorten(cleaned_text, 220)
                    )

            priority = 0
            if urgency == "Hoch":
                priority += 3
            elif urgency == "Mittel":
                priority += 2
            if tone == "Akut belastet":
                priority += 2
            elif tone == "Hilfesuchend":
                priority += 1

            representative_pool.append(
                {
                    "priority": priority,
                    "id": db_id,
                    "cluster": cluster,
                    "urgency": urgency,
                    "emotional_tone": tone,
                    "stakeholders": stakeholder_list[:4],
                    "text_excerpt": self._shorten(cleaned_text, self.max_example_chars),
                }
            )

        representative_pool.sort(key=lambda item: (item["priority"], item["id"]), reverse=True)
        representative_cases = []
        seen_clusters = set()

        for item in representative_pool:
            if len(representative_cases) >= self.max_examples:
                break
            if item["cluster"] not in seen_clusters or len(representative_cases) < 3:
                item = dict(item)
                item.pop("priority", None)
                representative_cases.append(item)
                seen_clusters.add(item["cluster"])

        if len(representative_cases) < self.max_examples:
            used_ids = {item["id"] for item in representative_cases}
            for item in representative_pool:
                if len(representative_cases) >= self.max_examples:
                    break
                if item["id"] in used_ids:
                    continue
                item = dict(item)
                item.pop("priority", None)
                representative_cases.append(item)

        cluster_summary = []
        total = len(records)
        for cluster, count in clusters.most_common():
            cluster_summary.append(
                {
                    "cluster": cluster,
                    "count": count,
                    "share_percent": round((count / total) * 100, 1) if total else 0,
                    "urgency_distribution": dict(cluster_urgencies[cluster].most_common()),
                }
            )

        return {
            "source_count": total,
            "source_signature": source_signature,
            "aggregation_strategy": "agent3_json_compressed_for_llm",
            "cluster_summary": cluster_summary,
            "urgency_distribution": dict(urgencies.most_common()),
            "emotional_tone_distribution": dict(tones.most_common()),
            "top_stakeholders": [
                {
                    "name": name,
                    "mentions": count,
                    "top_clusters": [
                        cluster_name
                        for cluster_name, _ in stakeholder_clusters[name].most_common(3)
                    ],
                    "examples": stakeholder_examples[name],
                }
                for name, count in stakeholders.most_common(6)
            ],
            "representative_cases": representative_cases,
        }

    def _build_messages(self, evidence_bundle):
        system_prompt = """
You are a service innovation strategist for student support systems in Germany.

Your task is not to summarize complaints. Your task is to generate a portfolio
of 3-5 concrete, implementable service innovations based on the empirical weak
signals produced by Agent 3.

Use only the provided aggregated evidence. Create exactly one stakeholder profile for every name in top_stakeholders. Do not skip any name and do not add new names:
- problem clusters
- urgency distribution
- emotional tone distribution
- stakeholders
- representative anonymized cases

Return exactly one JSON object. No markdown, no commentary, no text outside JSON.
All JSON values must be written in German and should use German institutional
terms where appropriate, for example Studierendenwerk, BAföG-Amt,
Hochschulberatung, International Office, Prüfungsamt, Sozialberatung.

The JSON must contain these top-level fields:
{
  "portfolio_summary": "2-3 Sätze, welche Service-Lücken das Portfolio insgesamt adressiert",
  "stakeholder_profiles": [
    {
      "name": "Exakter Name aus top_stakeholders",
      "description": "Maximal 2 kurze datenbasierte Sätze und höchstens 180 Zeichen: Rolle im Problemfeld und häufige zugeordnete Themen",
      "task_areas": [
        {
          "title": "Kurzer Name eines Arbeitsfelds",
          "status": "active | overloaded | service_gap",
          "evidence": "Ein kurzer datenbasierter Satz aus Clustern oder Beispielen",
          "recommendation": "Ein konkreter Verbesserungsvorschlag in einem Satz"
        }
      ]
    }
  ],
  "innovations": [
    {
      "cluster": "Zentrales systemisches Problemcluster",
      "opportunity": "Einprägsamer Name einer konkreten Serviceidee",
      "solution": "2-4 Sätze zur Servicearchitektur und zum konkreten Konzept",
      "target": "Primäre Zielgruppe",
      "stakeholder": "Zuständige oder beteiligte Akteure",
      "evidence": "1-2 konkrete Sätze ausschließlich zur Problemlage: Welche wiederkehrenden Bedarfe, Beschwerden, Cluster oder Stakeholder-Konflikte begründen die Idee? Die vorgeschlagene Lösung oder ihre Vorteile dürfen hier nicht erwähnt werden.",
      "implementation_steps": [
        "Pilot: konkreter erster Test mit benanntem Verantwortlichen und klarer Zielgruppe",
        "Integration: konkrete Einbindung in einen bestehenden Prozess oder Kanal",
        "Evaluation: messbares Erfolgskriterium und Entscheidung über Skalierung"
      ],
      "risk": "Zentrales Umsetzungsrisiko oder ethische Grenze"
    }
  ]
}

The number of stakeholder_profiles must exactly match the number of entries in top_stakeholders.
Each stakeholder profile must contain 3 or 4 task_areas.
Use status "active" for an existing responsibility without a strong gap signal, "overloaded" for an existing but problematic process, and "service_gap" for a recurring need without a clearly covered service.
For "overloaded", recommend one concrete process improvement. For "service_gap", recommend one concrete new service idea. Keep all evidence and recommendations short.
The innovation portfolio must:
1. address the strongest systemic service gaps in the evidence,
2. be feasible for a German university / Studierendenwerk context,
3. reduce friction in an existing process or connect existing stakeholders,
4. be more specific than an awareness campaign or generic counselling offer,
5. explain why the data supports this idea,
6. avoid inventing raw data, statistics, laws, or institutional procedures.
7. In "evidence", explain the underlying recurring need or service gap, not the proposed solution itself.
8. Make every implementation step operational: name an actor, an action, and an observable output or decision. Avoid generic steps such as "Tool entwickeln", "integrieren" or "Mitarbeitende schulen" without further specification.
9. Structure implementation_steps as Pilot, Integration and Evaluation whenever possible.

Diversity constraints:
- Generate at least 3 innovations if at least 3 problem clusters exist.
- Each innovation should address a different problem cluster whenever possible.
- Do not generate more than one financial-aid / BAföG / Finanzen idea.
- Include smaller but meaningful clusters if they reveal a distinct service gap.
- Prefer a balanced portfolio over repeating the dominant cluster.
"""

        user_prompt = (
            "Here is the compressed evidence bundle generated from Agent 3 JSON analyses:\n"
            f"{json.dumps(evidence_bundle, ensure_ascii=False, indent=2)}"
        )

        return [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt},
        ]
    
    def generate_from_signal(self, signal_text):
        signal_text = " ".join(str(signal_text or "").split())

        if len(signal_text) < 12:
            raise ValueError(
                "Bitte beschreibe die beobachtete Lücke in mindestens 12 Zeichen."
            )

        system_prompt = """
Du bist ein Service-Innovation-Stratege für studentische Unterstützungssysteme
an deutschen Hochschulen.

Analysiere genau ein vom Nutzer beschriebenes Signal oder eine vermutete
Versorgungslücke. Entwickle daraus genau eine konkrete und realistisch
umsetzbare Serviceinnovation.

Return exactly one JSON object. No markdown, no commentary, no text outside JSON.
All values must be written in German.

Use exactly this structure:
{
  "cluster": "Passendes systemisches Problemcluster",
  "gap_summary": "1-2 Sätze zur erkannten Versorgungslücke",
  "opportunity": "Einprägsamer Name einer konkreten Serviceidee",
  "solution": "2-4 konkrete Sätze zur Funktionsweise und Servicearchitektur",
  "target": "Primäre Zielgruppe",
  "stakeholder": "Zuständige oder beteiligte Akteure",
  "evidence": "Warum der eingegebene Hinweis auf eine relevante Lücke deutet; nur Problemlage, keine Wiederholung der Lösung",
  "implementation_steps": [
    "Pilot: benannter Akteur, konkrete Testgruppe und beobachtbares Ergebnis",
    "Integration: konkrete Einbindung in einen bestehenden Prozess oder Kanal",
    "Evaluation: messbares Erfolgskriterium und Entscheidung über Skalierung"
  ],
  "risk": "Zentrales Umsetzungsrisiko oder ethische Grenze"
}

Rules:
1. Do not invent statistics, laws, existing services, institutional procedures or facts not contained in the signal.
2. If the signal is ambiguous, state the uncertainty in gap_summary or risk instead of inventing details.
3. The concept must be more specific than a generic information campaign or counselling offer.
4. Every implementation step must name an actor, an action and an observable output or decision.
5. Evidence must describe the underlying need or service gap, not advertise the proposed solution.
"""

        messages = [
            {
                "role": "system",
                "content": system_prompt.strip(),
            },
            {
                "role": "user",
                "content": (
                    "Vom Nutzer beschriebenes Signal oder Versorgungslücke:\n\n"
                    f"{signal_text}"
                ),
            },
        ]

        errors = []

        for provider in self.providers:
            try:
                raw_response = self._call_provider(
                    provider,
                    messages,
                )

                result = self._extract_json_object(
                    raw_response
                )

                required_fields = (
                    "cluster",
                    "gap_summary",
                    "opportunity",
                    "solution",
                    "target",
                    "stakeholder",
                    "evidence",
                    "implementation_steps",
                    "risk",
                )

                missing = [
                    field
                    for field in required_fields
                    if not result.get(field)
                ]

                if missing:
                    raise ValueError(
                        "Signal innovation missing required fields: "
                        + ", ".join(missing)
                    )

                if not isinstance(
                    result.get("implementation_steps"),
                    list,
                ):
                    result["implementation_steps"] = [
                        str(result["implementation_steps"])
                    ]

                result["llm_metadata"] = {
                    "generated_by_llm": True,
                    "mode": "single_signal",
                    "provider": provider["name"],
                    "model": provider["model"],
                    "created_at_utc": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

                return result

            except Exception as exc:
                errors.append(
                    f"{provider['name']} failed: {exc}"
                )

        raise RuntimeError(
            "Keine LLM-Verbindung konnte die Serviceidee generieren. "
            + " | ".join(errors)
        )


    def _retry_after_seconds(self, exc):
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return None

        value = None
        try:
            value = headers.get("retry-after") or headers.get("Retry-After")
        except AttributeError:
            value = None

        if not value:
            return None

        try:
            return min(float(value), self.max_retry_sleep)
        except ValueError:
            return None

    def _is_retryable(self, exc):
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        return status_code in {408, 409, 429, 500, 502, 503, 504} or status_code is None

    def _completion_create(self, provider, messages, use_response_format=True):
        kwargs = {
            "model": provider["model"],
            "messages": messages,
            "temperature": self.temperature,
        }
        if use_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        return provider["client"].chat.completions.create(**kwargs)

    def _call_provider(self, provider, messages):
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._completion_create(provider, messages, use_response_format=True)
                return response.choices[0].message.content
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()

                # Some OpenAI-compatible gateways do not support response_format.
                # The prompt still enforces JSON, so retry once without that param.
                if "response_format" in message or "json_object" in message:
                    try:
                        response = self._completion_create(provider, messages, use_response_format=False)
                        return response.choices[0].message.content
                    except Exception as fallback_exc:
                        last_error = fallback_exc

                if attempt >= self.max_retries or not self._is_retryable(last_error):
                    break

                sleep_seconds = self._retry_after_seconds(last_error)
                if sleep_seconds is None:
                    sleep_seconds = min(self.retry_base_seconds * (2 ** (attempt - 1)), self.max_retry_sleep)

                print(
                    f"[Agent 4 WARN] {provider['name']} attempt {attempt}/{self.max_retries} failed. "
                    f"Retrying in {sleep_seconds:.1f}s..."
                )
                time.sleep(sleep_seconds)

        raise last_error

    def _extract_json_object(self, text):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed

        raise ValueError("LLM response did not contain a valid JSON object.")

    def _validate_report(self, report):
        # Backward compatibility: older prompts returned a single innovation at
        # the top level. Normalize that shape into the new portfolio format.
        if "innovations" not in report and all(
            report.get(field) for field in self.REQUIRED_INNOVATION_FIELDS
        ):
            report = {
                "portfolio_summary": "Ein einzelner Service-Innovationsvorschlag wurde aus den stärksten Signalen generiert.",
                "innovations": [report],
            }

        stakeholder_profiles = report.get("stakeholder_profiles", [])
        if not isinstance(stakeholder_profiles, list):
            report["stakeholder_profiles"] = []
        else:
            normalized_profiles = []

            for profile in stakeholder_profiles:
                if not isinstance(profile, dict):
                    continue
                if not profile.get("name") or not profile.get("description"):
                    continue

                normalized_areas = []
                task_areas = profile.get("task_areas", [])

                if isinstance(task_areas, list):
                    for area in task_areas[:4]:
                        if not isinstance(area, dict) or not area.get("title"):
                            continue

                        status = str(area.get("status", "active")).strip().lower()
                        if status not in {"active", "overloaded", "service_gap"}:
                            status = "active"

                        normalized_areas.append(
                            {
                                "title": self._shorten(area.get("title"), 60),
                                "status": status,
                                "evidence": self._shorten(area.get("evidence"), 160),
                                "recommendation": self._shorten(area.get("recommendation"), 180),
                            }
                        )

                normalized_profiles.append(
                    {
                        "name": profile["name"],
                        "description": self._limit_description(profile["description"], 2, 180),
                        "task_areas": normalized_areas,
                    }
                )

            report["stakeholder_profiles"] = normalized_profiles

        innovations = report.get("innovations")
        if not isinstance(innovations, list) or not innovations:
            raise ValueError("LLM report must contain a non-empty 'innovations' list.")

        for index, innovation in enumerate(innovations, start=1):
            if not isinstance(innovation, dict):
                raise ValueError(f"Innovation #{index} is not a JSON object.")

            missing = [
                field
                for field in self.REQUIRED_INNOVATION_FIELDS
                if not innovation.get(field)
            ]
            if missing:
                raise ValueError(
                    f"Innovation #{index} missing required fields: {', '.join(missing)}"
                )

            if not isinstance(innovation.get("implementation_steps", []), list):
                innovation["implementation_steps"] = [str(innovation["implementation_steps"])]

        if not report.get("portfolio_summary"):
            report["portfolio_summary"] = (
                "Das Portfolio bündelt mehrere LLM-generierte Serviceideen aus den "
                "stärksten analysierten Bedarfssignalen."
            )

        return report

    def _metadata(self, provider, source_signature, source_count):
        return {
            "generated_by_llm": True,
            "provider": provider["name"],
            "model": provider["model"],
            "source_count": source_count,
            "source_signature": source_signature,
            "prompt_strategy": "aggregated_agent3_signals_portfolio",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    def _has_current_cached_report(self, latest_report, source_signature):
        if not latest_report:
            return False
        metadata = latest_report["report"].get("llm_metadata", {})
        return (
            metadata.get("generated_by_llm") is True
            and metadata.get("source_signature") == source_signature
            and metadata.get("prompt_strategy") == "aggregated_agent3_signals_portfolio"
        )

    def run(self, force=False):
        print("\n---------------------------------------------------------------------")
        print("[Agent 4] Starting LLM innovation generator")
        print("---------------------------------------------------------------------")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        records = self._load_analyzed_records(cursor)
        if not records:
            print("[Agent 4 INFO] No status=2 records available for LLM innovation generation.")
            conn.close()
            return None

        source_signature = self._source_signature(records)
        latest_report = self._latest_report(cursor)

        if not force and self._has_current_cached_report(latest_report, source_signature):
            metadata = latest_report["report"].get("llm_metadata", {})
            print(
                "[Agent 4 CACHE] Current LLM report already exists "
                f"({metadata.get('provider')}/{metadata.get('model')}, source_count={metadata.get('source_count')})."
            )
            conn.close()
            return latest_report["report"]

        evidence_bundle = self._build_evidence_bundle(records, source_signature)
        messages = self._build_messages(evidence_bundle)

        print(
            f"[Agent 4] Built compressed evidence bundle from {len(records)} analyzed records. "
            f"Trying providers: {', '.join(p['name'] for p in self.providers)}"
        )

        errors = []
        for provider in self.providers:
            try:
                print(f"[Agent 4] Calling {provider['name']} / {provider['model']}...")
                raw_response = self._call_provider(provider, messages)
                report = self._extract_json_object(raw_response)
                report = self._validate_report(report)
                report["llm_metadata"] = self._metadata(provider, source_signature, len(records))

                report_json = json.dumps(report, ensure_ascii=False, indent=2)
                cursor.execute("INSERT INTO system_reports (report_json) VALUES (?)", (report_json,))
                conn.commit()
                conn.close()

                print("[Agent 4 SUCCESS] New LLM-generated service innovation saved to system_reports.")
                return report
            except Exception as exc:
                error_message = f"{provider['name']} failed: {exc}"
                errors.append(error_message)
                print(f"[Agent 4 ERROR] {error_message}")

        if latest_report and latest_report["report"]:
            print("[Agent 4 STALE] All providers failed. Keeping the latest existing LLM report in the dashboard.")
            conn.close()
            return latest_report["report"]

        conn.close()
        print("[Agent 4 FAILED] No provider produced a report, and no previous LLM report exists.")
        print("[Agent 4 FAILED] Provider errors:")
        for error in errors:
            print(f"  - {error}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an LLM-based Service Sonar innovation report.")
    parser.add_argument("--force", action="store_true", help="Ignore cache and generate a fresh LLM report.")
    args = parser.parse_args()

    innovator = Agent4Innovator()
    innovator.run(force=args.force)
