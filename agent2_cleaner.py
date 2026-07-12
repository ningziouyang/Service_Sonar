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

    Unterstützt jetzt mehrere Quelltabellen (z.B. forum_posts von Studis Online
    und hilferuf_posts von hilferuf.de), da beide dasselbe Grundschema haben
    (id, raw_content, cleaned_content, status).
    """

    # Tabellen, die verarbeitet werden sollen, plus ob ein zusätzlicher
    # "ist das überhaupt studienbezogen"-Check nötig ist. Studis Online und
    # das "Studium"-Forum von Hilferuf sind schon thematisch eng genug,
    # aber breite Hilferuf-Foren wie "Ich" oder "Finanzen" brauchen den
    # zusätzlichen Check, weil dort auch komplett studienfremde Themen landen.
    # gutefrage_posts enthält teils die allgemeine Kategorie "Beruf Ausbildung"
    # (Schulalltag, Ausbildung, Jobsuche etc. gemischt) -> ebenfalls Check nötig.
    SOURCE_TABLES = {
        "forum_posts": {"require_student_context": False},
        "hilferuf_posts": {"require_student_context": True},
        "gutefrage_posts": {"require_student_context": True},
    }

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

    def _remove_forum_metadata(self, text: str) -> str:
        """
        Entfernt typische Forensoftware-Reste, die kein eigentlicher
        Beitragsinhalt sind (Zeitstempel-Reste, "Antworten"-Links, etc.),
        die trotz Container-Lock im Scraper gelegentlich mitkommen.
        """
        if not text:
            return ""

        noise_patterns = [
            r"\bAntworten\b",
            r"\bZitieren\b",
            r"\bTeilen\b",
            r"\b\d+\s*(Sekunden|Minuten|Stunden|Tage|Wochen|Monate|Jahre)\s*her\b",
            r"\bGestartet von\b.*?(?=\s{2,}|$)",
        ]
        for pattern in noise_patterns:
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

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
            "nachmieter gesucht",
            "suche nachmieter",
            "wg-zimmer abzugeben",
            "rabattcode",
            "werbung",
            "skripte verkaufen",
            "umfrage",
            "teilnehmer gesucht",
            "studie zu",
            "ki-gestützter chatbot",
            "chatbot auf unserer seite",
        ]

        # "zu verkaufen" ist als Vollsatz-Suche zu riskant: trifft auch normale
        # Sätze wie "Produkte besser zu verkaufen" (Beruf/Marketing-Kontext),
        # nicht nur Kleinanzeigen ("Zimmer zu verkaufen"). Echte Anzeigen nennen
        # den Artikel fast immer gleich zu Beginn -> nur im Titel/Anfang prüfen.
        irrelevant_title_keywords = ["zu verkaufen"]

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

        # "masterarbeit"/"bachelorarbeit" NICHT pauschal als Spam werten:
        # Das trifft sonst auch echte Notlagen-Posts ("Ich habe Angst, meine
        # Bachelorarbeit nicht zu schaffen"), nicht nur Umfrage-Spam
        # ("Ich schreibe meine Bachelorarbeit, bitte macht meine Umfrage").
        # Nur werfen, wenn zusätzlich ein Umfrage-/Rekrutierungs-Muster da ist.
        umfrage_muster = ["umfrage", "teilnehmer gesucht", "studie zu", "befragung"]
        abschlussarbeit_erwaehnt = any(
            k in text_lower for k in ["masterarbeit", "bachelorarbeit"]
        )
        if abschlussarbeit_erwaehnt and any(m in text_lower for m in umfrage_muster):
            return True

        if any(pattern in first_part for pattern in irrelevant_title_patterns):
            return True

        if any(
            re.search(r"\b" + re.escape(kw) + r"\b", first_part)
            for kw in irrelevant_title_keywords
        ):
            return True

        # Wortgrenzen-Suche statt naiver Teilstring-Suche: verhindert False
        # Positives wie "werbung" als Treffer innerhalb von "Bewerbung"
        # (Uni-Bewerbung != Werbung/Spam).
        return any(
            re.search(r"\b" + re.escape(keyword) + r"\b", text_lower)
            for keyword in irrelevant_keywords
        )

    def _has_student_context(self, text: str) -> bool:
        """
        Nur für breite, nicht-studienspezifische Quellen relevant (z.B. die
        Hilferuf-Foren "Ich" oder "Finanzen", die auch komplett studienfremde
        Themen enthalten). Prüft, ob der Beitrag überhaupt einen erkennbaren
        Bezug zum Studentenleben hat, bevor er weiterverarbeitet wird.
        """
        student_keywords = [
            "studium", "studiere", "studentin", "student ",
            "uni", "universität", "hochschule", "fh ",
            "bachelor", "master", "semester", "klausur", "prüfung",
            "seminar", "vorlesung", "bafög", "immatrikul",
            "wg-zimmer", "campus", "dozent", "kommiliton",
            "abschlussarbeit", "hausarbeit",
            # ergänzt nach Stichprobenprüfung (echte Studium-Posts, die durchgerutscht sind):
            "studiengang", "studienplatz", "studienfach", "studienwahl",
            "bewerbung", "zulassung", "einschreibung", "wintersemester",
            "sommersemester", "nc ", "abitur", "examen", "fachschaft",
            "erstsemester", "hochschulstart",
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in student_keywords)

    def run(self, table_name="forum_posts", require_student_context=False):
        """
        Verarbeitet eine einzelne Quelltabelle.

        Input:  <table_name> mit status=0
        Output: status=1, status=3 oder status=-1
        """
        print(f"[Agent 2] Starte Cleaning für Tabelle '{table_name}'...")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute(f"SELECT id, raw_content FROM {table_name} WHERE status = ?", (STATUS_RAW,))
        records = cursor.fetchall()

        if not records:
            print(f"[Agent 2 INFO] Keine neuen Rohdaten mit status=0 in '{table_name}' gefunden.")
            conn.close()
            return

        cleaned_count = 0
        human_review_count = 0
        rejected_count = 0
        empty_count = 0
        no_context_count = 0

        for db_id, raw_text in records:
            cleaned = self._clean_text(raw_text)
            cleaned = self._remove_forum_metadata(cleaned)
            anonymized = self._anonymize_text(cleaned)

            if not anonymized:
                cursor.execute(
                    f"UPDATE {table_name} SET cleaned_content = ?, status = ? WHERE id = ?",
                    ("", STATUS_REJECTED, db_id),
                )
                rejected_count += 1
                empty_count += 1
                continue

            if self._is_critical_case(anonymized):
                cursor.execute(
                    f"UPDATE {table_name} SET cleaned_content = ?, status = ? WHERE id = ?",
                    (anonymized, STATUS_HUMAN_REVIEW, db_id),
                )
                human_review_count += 1
                continue

            if self._is_irrelevant_post(anonymized):
                cursor.execute(
                    f"UPDATE {table_name} SET cleaned_content = ?, status = ? WHERE id = ?",
                    (anonymized, STATUS_REJECTED, db_id),
                )
                rejected_count += 1
                continue

            # Zusätzlicher Check nur für breite, nicht-studienspezifische Quellen
            if require_student_context and not self._has_student_context(anonymized):
                cursor.execute(
                    f"UPDATE {table_name} SET cleaned_content = ?, status = ? WHERE id = ?",
                    (anonymized, STATUS_REJECTED, db_id),
                )
                rejected_count += 1
                no_context_count += 1
                continue

            cursor.execute(
                f"UPDATE {table_name} SET cleaned_content = ?, status = ? WHERE id = ?",
                (anonymized, STATUS_CLEANED, db_id),
            )
            cleaned_count += 1

        conn.commit()
        conn.close()

        print(f"\n========== Agent 2 Report ({table_name}) ==========")
        print(f"Gesamt verarbeitet: {len(records)}")
        print(f"✓ Bereinigt & freigegeben (Status 1): {cleaned_count}")
        print(f"⚠ Human Review erforderlich (Status 3): {human_review_count}")
        print(f"✗ Irrelevant verworfen (Status -1): {rejected_count}")
        print(f"  ∅ davon leer/unlesbar: {empty_count}")
        if require_student_context:
            print(f"  ∅ davon ohne Studienbezug: {no_context_count}")
        print("====================================================")

    def run_all(self):
        """
        Verarbeitet nacheinander alle konfigurierten Quelltabellen
        (SOURCE_TABLES). Praktisch, um nach einem Scraping-Lauf über
        mehrere Quellen hinweg einmal alles durchzucleanen.
        """
        for table_name, config in self.SOURCE_TABLES.items():
            self.run(
                table_name=table_name,
                require_student_context=config["require_student_context"],
            )


if __name__ == "__main__":
    cleaner = Agent2Cleaner()
    cleaner.run_all()