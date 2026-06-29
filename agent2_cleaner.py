import re
import sqlite3
from html import unescape


STATUS_REJECTED = -1
STATUS_RAW = 0
STATUS_CLEANED = 1
STATUS_HUMAN_REVIEW = 3


class Agent2Cleaner:
    """
    Agent 2: Cleaning, Anonymisierung und Routing.

    Wichtig:
    - Agent 2 macht KEINE semantische Klassifikation.
    - Agent 2 entscheidet nur, ob ein Beitrag sauber genug für Agent 3 ist,
      verworfen wird oder zuerst durch Human Review gehen muss.
    """

    def __init__(self, db_file="service_sonar.db"):
        self.db_file = db_file

    def _clean_text(self, raw_text: str) -> str:
        """
        Bereinigt Rohtext aus Forenbeiträgen.
        Entfernt einfache HTML-Reste, URLs und überflüssige Leerzeichen.
        """
        if not raw_text:
            return ""

        text = unescape(raw_text)

        # HTML-Tags entfernen
        text = re.sub(r"<[^>]+>", " ", text)

        # URLs maskieren
        text = re.sub(r"https?://\S+|www\.\S+", "[URL]", text)

        # Mehrfache Leerzeichen vereinheitlichen
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _anonymize_text(self, text: str) -> str:
        """
        Anonymisiert mögliche personenbezogene Daten.
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

    def _is_critical_case(self, text: str) -> bool:
        """
        Erkennt sensible Fälle, die nicht automatisch weiterverarbeitet werden sollen.
        Diese Funktion macht keine finale Bewertung, sondern setzt nur status=3.
        """
        critical_keywords = [
            "suizid",
            "suizidal",
            "obdachlos",
            "wohnungslos",
            "auto schlafen",
            "notfall",
            "krise",
            "am ende",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in critical_keywords)

    def _is_irrelevant_post(self, text: str) -> bool:
        """
        Erkennt offensichtlich irrelevante Beiträge wie Werbung, Verkaufsanzeigen
        oder reine Umfrage-/Studienaufrufe.
        """
        irrelevant_keywords = [
            "verkaufe",
            "zu verkaufen",
            "nachmieter gesucht",
            "suche nachmieter",
            "wg-zimmer abzugeben",
            "rabattcode",
            "werbung",
            "skripte verkaufen",
            "umfrage",
            "teilnehmer gesucht",
            "masterarbeit",
            "bachelorarbeit",
            "studie zu",
            "ki-gestützter chatbot",
            "chatbot auf unserer seite",
        ]

        irrelevant_title_patterns = [
            "sekunden her",
            "minuten her",
            "stunden her",
            "tage her",
            "wochen her",
            "monate her",
            "jahr her",
            "jahre her",
        ]

        text_lower = text.lower()
        first_part = text_lower[:120]

        if any(pattern in first_part for pattern in irrelevant_title_patterns):
            return True

        return any(keyword in text_lower for keyword in irrelevant_keywords)

    def run(self):
        """
        Input:  forum_posts mit status=0
        Output: status=1, status=3 oder status=-1
        """
        print("[Agent 2] Starte Cleaning, Anonymisierung und Routing...")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute("SELECT id, raw_content FROM forum_posts WHERE status = ?", (STATUS_RAW,))
        records = cursor.fetchall()

        if not records:
            print("[Agent 2 INFO] Keine neuen Rohdaten mit status=0 gefunden.")
            conn.close()
            return

        cleaned_count = 0
        human_review_count = 0
        rejected_count = 0
        empty_count = 0

        for db_id, raw_text in records:
            cleaned = self._clean_text(raw_text)
            cleaned = self._remove_forum_metadata(cleaned)
            anonymized = self._anonymize_text(cleaned)

            if not anonymized:
                cursor.execute(
                    "UPDATE forum_posts SET cleaned_content = ?, status = ? WHERE id = ?",
                    ("", STATUS_REJECTED, db_id),
                )
                rejected_count += 1
                empty_count += 1
                continue

            if self._is_critical_case(anonymized):
                cursor.execute(
                    "UPDATE forum_posts SET cleaned_content = ?, status = ? WHERE id = ?",
                    (anonymized, STATUS_HUMAN_REVIEW, db_id),
                )
                human_review_count += 1
                continue

            if self._is_irrelevant_post(anonymized):
                cursor.execute(
                    "UPDATE forum_posts SET cleaned_content = ?, status = ? WHERE id = ?",
                    (anonymized, STATUS_REJECTED, db_id),
                )
                rejected_count += 1
                continue

            cursor.execute(
                "UPDATE forum_posts SET cleaned_content = ?, status = ? WHERE id = ?",
                (anonymized, STATUS_CLEANED, db_id),
            )
            cleaned_count += 1

        conn.commit()
        conn.close()

        print("\n========== Agent 2 Report ==========")
        print(f"Gesamt verarbeitet: {len(records)}")
        print(f"✓ Bereinigt & freigegeben (Status 1): {cleaned_count}")
        print(f"⚠ Human Review erforderlich (Status 3): {human_review_count}")
        print(f"✗ Irrelevant verworfen (Status -1): {rejected_count}")
        print(f"∅ Leer / unlesbar (Status -1): {empty_count}")
        print("====================================")


if __name__ == "__main__":
    cleaner = Agent2Cleaner()
    cleaner.run()
