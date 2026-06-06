import json
import sqlite3


def detect_urgency(text: str) -> str:
    """
    Erkennt eine grobe Dringlichkeitsstufe anhand einfacher Schlüsselwörter.
    Diese Regel ist bewusst transparent und nachvollziehbar.
    """
    text_lower = text.lower()

    high_keywords = [
        "notfall",
        "krise",
        "obdachlos",
        "wohnungslos",
        "auto schlafen",
        "kein geld",
        "psychisch",
        "am ende",
        "panik"
    ]

    medium_keywords = [
        "stress",
        "überforderung",
        "miete",
        "kaution",
        "bafög",
        "prüfung",
        "durchfallen",
        "finanzielle probleme"
    ]

    if any(keyword in text_lower for keyword in high_keywords):
        return "Hoch"

    if any(keyword in text_lower for keyword in medium_keywords):
        return "Mittel"

    return "Niedrig"


def detect_stakeholders(text: str) -> list[str]:
    """
    Leitet mögliche betroffene oder zuständige Stakeholder ab.
    Das dient später dem Stakeholder-Mapping im Service-Sonar-Konzept.
    """
    text_lower = text.lower()
    stakeholders = []

    if any(word in text_lower for word in ["wohnung", "miete", "wohnheim", "wg", "kaution"]):
        stakeholders.extend([
            "Studierendenwerk",
            "Wohnheime",
            "Vermieter",
            "Studentische Beratungsstellen"
        ])

    if any(word in text_lower for word in ["bafög", "geld", "finanz", "job", "kosten"]):
        stakeholders.extend([
            "BAföG-Amt",
            "Sozialberatung",
            "Universität",
            "Studierendenwerk"
        ])

    if any(word in text_lower for word in ["prüfung", "studium", "semester", "modul", "durchfallen"]):
        stakeholders.extend([
            "Studienberatung",
            "Prüfungsamt",
            "Fachbereich",
            "Dozierende"
        ])

    if any(word in text_lower for word in ["psychisch", "stress", "depression", "angst", "überforderung"]):
        stakeholders.extend([
            "Psychologische Beratungsstelle",
            "Studierendenwerk",
            "Universität",
            "Krisenberatung"
        ])

    if not stakeholders:
        stakeholders.append("Allgemeine studentische Beratung")

    # Doppelte Einträge entfernen, Reihenfolge behalten
    return list(dict.fromkeys(stakeholders))


def detect_problem_cluster(text: str) -> str:
    """
    Ordnet den Beitrag einem Problemcluster zu.
    Diese Cluster können später für Weak-Signal-Detection und Dashboard-Visualisierung genutzt werden.
    """
    text_lower = text.lower()

    if any(word in text_lower for word in ["wohnung", "miete", "wohnheim", "wg", "kaution", "zimmer"]):
        return "Wohnungsmarkt und studentisches Wohnen"

    if any(word in text_lower for word in ["bafög", "geld", "finanz", "job", "kosten", "miete zahlen"]):
        return "Finanzielle Belastung"

    if any(word in text_lower for word in ["prüfung", "studium", "semester", "modul", "durchfallen"]):
        return "Studienorganisation und Prüfungsdruck"

    if any(word in text_lower for word in ["psychisch", "stress", "depression", "angst", "überforderung"]):
        return "Mentale Gesundheit und Belastung"

    return "Sonstige studentische Unterstützungsbedarfe"


def detect_emotional_tone(text: str) -> str:
    """
    Erkennt eine grobe emotionale Lage im Beitrag.
    Das ist keine medizinische Diagnose, sondern nur eine textbasierte Einschätzung.
    """
    text_lower = text.lower()

    if any(word in text_lower for word in ["panik", "am ende", "krise", "notfall", "verzweifelt"]):
        return "Akut belastet"

    if any(word in text_lower for word in ["stress", "überfordert", "angst", "frustriert", "wütend"]):
        return "Belastet / frustriert"

    if any(word in text_lower for word in ["suche", "frage", "weiß jemand", "hilfe"]):
        return "Hilfesuchend"

    return "Neutral / unklar"


def build_analysis_json(cleaned_content: str) -> dict:
    """
    Erstellt eine strukturierte Analyse aus einem bereinigten Beitrag.
    Dieses JSON ist der zentrale Output von Agent 3.
    """
    problem_cluster = detect_problem_cluster(cleaned_content)
    urgency = detect_urgency(cleaned_content)
    emotional_tone = detect_emotional_tone(cleaned_content)
    stakeholders = detect_stakeholders(cleaned_content)

    analysis = {
        "problem_cluster": problem_cluster,
        "urgency": urgency,
        "emotional_tone": emotional_tone,
        "stakeholders": stakeholders,
        "weak_signal_relevance": urgency in ["Mittel", "Hoch"],
        "analysis_method": "rule_based_simulation"
    }

    return analysis


def agent_analyzer(db_file: str):
    """
    Agent 3: Semantische Analyse und Strukturierung.

    Input:
        Beiträge aus der Datenbank mit status = 1

    Output:
        analysis_json mit Problemcluster, Dringlichkeit, emotionaler Lage,
        Stakeholdern und Weak-Signal-Relevanz.
        Danach wird der Beitrag auf status = 2 gesetzt.
    """

    print("[Agent 3] Starte semantische Analyse und Clusterbildung...")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT id, cleaned_content FROM forum_posts WHERE status = 1")
    records = cursor.fetchall()

    if not records:
        print("[Agent 3 INFO] Keine bereinigten Beiträge mit status=1 gefunden.")
        conn.close()
        return

    for db_id, cleaned_content in records:
        print(f"\n[Agent 3] Analysiere Datensatz ID {db_id}...")

        if not cleaned_content:
            print(f"[Agent 3 WARNUNG] Datensatz {db_id} hat keinen bereinigten Inhalt. Überspringe.")
            continue

        analysis = build_analysis_json(cleaned_content)
        analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)

        cursor.execute(
            """
            UPDATE forum_posts
            SET analysis_json = ?, status = 2
            WHERE id = ?
            """,
            (analysis_json, db_id)
        )

        print(f"[Agent 3] Analyse abgeschlossen → status=2.")
        print(analysis_json)

    conn.commit()
    conn.close()

    print("\n[Agent 3] Verarbeitung abgeschlossen.")