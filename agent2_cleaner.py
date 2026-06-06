import re
import sqlite3
from html import unescape


def clean_text(raw_text: str) -> str:
    """
    Bereinigt Rohtext aus Forenbeiträgen.
    Entfernt einfache HTML-Reste, URLs und überflüssige Leerzeichen.
    """
    if not raw_text:
        return ""

    text = unescape(raw_text)

    # HTML-Tags entfernen, falls Agent 1 später HTML-Ausschnitte speichert
    text = re.sub(r"<[^>]+>", " ", text)

    # URLs maskieren
    text = re.sub(r"https?://\S+|www\.\S+", "[URL]", text)

    # Mehrfache Leerzeichen vereinheitlichen
    text = re.sub(r"\s+", " ", text).strip()

    return text


def anonymize_text(text: str) -> str:
    """
    Anonymisiert mögliche personenbezogene Daten.
    Das ist wichtig, weil Forenbeiträge Namen, E-Mails,
    Telefonnummern oder Adressen enthalten können.
    """

    # E-Mail-Adressen maskieren
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL]",
        text
    )

    # Telefonnummern grob erkennen und maskieren
    text = re.sub(
        r"(\+?\d[\d\s()./-]{6,}\d)",
        "[PHONE]",
        text
    )

    # Einfache deutsche Adressmuster maskieren
    text = re.sub(
        r"\b[A-ZÄÖÜ][a-zäöüß]+straße\s+\d+\b",
        "[ADDRESS]",
        text
    )

    return text


def is_critical_case(text: str) -> bool:
    """
    Erkennt sensible oder kritische Fälle.
    Solche Beiträge sollen nicht automatisch weiterverarbeitet,
    sondern an eine menschliche Prüfung übergeben werden.
    """
    critical_keywords = [
        "psychisch",
        "depression",
        "suizid",
        "suizidal",
        "am ende",
        "auto schlafen",
        "obdachlos",
        "wohnungslos",
        "kein geld",
        "existenz",
        "krise",
        "panik",
        "angststörung",
        "notfall"
    ]

    text_lower = text.lower()
    return any(keyword in text_lower for keyword in critical_keywords)


def is_irrelevant_post(text: str) -> bool:
    """
    Erkennt irrelevante Beiträge.
    Dazu gehören z. B. Verkaufsanzeigen, Werbung oder reine Marktplatz-Posts.
    """
    irrelevant_keywords = [
        "verkaufe",
        "zu verkaufen",
        "nachmieter gesucht",
        "suche nachmieter",
        "wg-zimmer abzugeben",
        "rabattcode",
        "werbung",
        "kaufen",
        "angebot",
        "skripte verkaufen"
    ]

    text_lower = text.lower()
    return any(keyword in text_lower for keyword in irrelevant_keywords)


def classify_need_category(text: str) -> str:
    """
    Ordnet den Beitrag einer groben Bedarfskategorie zu.
    Das ist noch keine tiefe semantische Analyse.
    Die genauere Clusterbildung kann später Agent 3 übernehmen.
    """
    text_lower = text.lower()

    if any(word in text_lower for word in ["wohnung", "miete", "wohnheim", "wg", "zimmer", "kaution"]):
        return "Wohnen"

    if any(word in text_lower for word in ["bafög", "geld", "finanz", "job", "miete zahlen", "kosten"]):
        return "Finanzen"

    if any(word in text_lower for word in ["prüfung", "studium", "uni", "modul", "semester", "durchfallen"]):
        return "Studium"

    if any(word in text_lower for word in ["psychisch", "stress", "depression", "angst", "überforderung"]):
        return "Mentale Gesundheit"

    return "Sonstiges"


def build_cleaned_summary(text: str) -> str:
    """
    Erstellt einen einfach strukturierten bereinigten Output.
    Dieser Output wird später von Agent 3 weiter analysiert.
    """
    category = classify_need_category(text)

    return (
        f"Kategorie: {category}\n"
        f"Bereinigter Beitrag: {text}"
    )


def agent_cleaner(db_file: str):
    """
    Agent 2: Bereinigung, Anonymisierung, Relevanzprüfung und Human-in-the-Loop-Routing.

    Input:
        Beiträge aus der Datenbank mit status = 0

    Output:
        status = 1  bereinigt und relevant
        status = 3  kritisch / sensibel, menschliche Prüfung erforderlich
        status = -1 irrelevant / abgelehnt
    """

    print("[Agent 2] Starte Bereinigung, Anonymisierung und Relevanzprüfung...")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT id, raw_content FROM forum_posts WHERE status = 0")
    records = cursor.fetchall()

    if not records:
        print("[Agent 2 INFO] Keine neuen Rohdaten mit status=0 gefunden.")
        conn.close()
        return

    for db_id, raw_text in records:
        print(f"\n[Agent 2] Verarbeite Datensatz ID {db_id}...")

        cleaned = clean_text(raw_text)
        anonymized = anonymize_text(cleaned)

        if not anonymized:
            cursor.execute(
                "UPDATE forum_posts SET status = -1 WHERE id = ?",
                (db_id,)
            )
            print(f"[Agent 2] Datensatz {db_id} ist leer oder unlesbar → status=-1.")
            continue

        if is_critical_case(anonymized):
            cursor.execute(
                """
                UPDATE forum_posts
                SET cleaned_content = ?, status = 3
                WHERE id = ?
                """,
                (anonymized, db_id)
            )
            print(f"[Agent 2 ALERT] Kritischer Fall erkannt → status=3 Human Review.")
            continue

        if is_irrelevant_post(anonymized):
            cursor.execute(
                """
                UPDATE forum_posts
                SET cleaned_content = ?, status = -1
                WHERE id = ?
                """,
                (anonymized, db_id)
            )
            print(f"[Agent 2] Irrelevanter Beitrag erkannt → status=-1.")
            continue

        summary = build_cleaned_summary(anonymized)

        cursor.execute(
            """
            UPDATE forum_posts
            SET cleaned_content = ?, status = 1
            WHERE id = ?
            """,
            (summary, db_id)
        )

        print(f"[Agent 2] Beitrag bereinigt und freigegeben → status=1.")

    conn.commit()
    conn.close()

    print("\n[Agent 2] Verarbeitung abgeschlossen.")