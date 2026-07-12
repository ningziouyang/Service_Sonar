import re
import sqlite3
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class Agent1ScraperGutefrage:
    """
    Liest manuell gespeicherte HTML-Seiten von gutefrage.net
    und speichert die gefundenen Fragen in die bestehende
    Tabelle `gutefrage_posts`.

    Erwartete Ordnerstruktur:

        Service_Sonar/
        ├── agent1_scraper_gutefrage.py
        ├── service_sonar.db
        └── gutefrage_html/
            ├── studium_1.html
            ├── studium_2.html
            ├── studium_3.html
            └── ...

    Die HTML-Dateien werden lokal ausgewertet.
    Es werden keine weiteren Requests an gutefrage.net gesendet.
    """

    BASE_URL = "https://www.gutefrage.net"
    TABLE_NAME = "gutefrage_posts"

    def __init__(
        self,
        db_file="service_sonar.db",
        html_ordner="gutefrage_html",
    ):
        base_dir = Path(__file__).resolve().parent

        self.db_file = base_dir / db_file
        self.html_ordner = base_dir / html_ordner

        print(
            "Verwendete Datenbank:",
            self.db_file.resolve(),
        )

        print(
            "HTML-Ordner:",
            self.html_ordner.resolve(),
        )

        self._pruefe_datenbank()

    def _pruefe_datenbank(self):
        if not self.db_file.exists():
            raise FileNotFoundError(
                f"Datenbank nicht gefunden: "
                f"{self.db_file.resolve()}"
            )

        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                AND name = ?
                """,
                (self.TABLE_NAME,),
            )

            table = cursor.fetchone()

            if table is None:
                print(
                    f"Tabelle '{self.TABLE_NAME}' existiert noch nicht "
                    "-> wird jetzt angelegt."
                )
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT UNIQUE,
                        forum_kategorie TEXT,
                        raw_content TEXT,
                        cleaned_content TEXT,
                        analysis_json TEXT,
                        status INTEGER DEFAULT 0
                    )
                    """
                )
                conn.commit()

            spalten = self._hole_tabellen_spalten(conn)

            notwendige_spalten = {
                "url",
                "raw_content",
            }

            fehlende_spalten = (
                notwendige_spalten - spalten
            )

            if fehlende_spalten:
                raise RuntimeError(
                    "In der Tabelle "
                    f"'{self.TABLE_NAME}' fehlen Spalten: "
                    f"{', '.join(sorted(fehlende_spalten))}"
                )

            print(
                "Gefundene Spalten in gutefrage_posts:",
                ", ".join(sorted(spalten)),
            )

    def _hole_tabellen_spalten(self, conn):
        cursor = conn.execute(
            f"""
            PRAGMA table_info({self.TABLE_NAME})
            """
        )

        return {
            row[1]
            for row in cursor.fetchall()
        }

    @staticmethod
    def _bereinige_text(text):
        """
        Entfernt doppelte Leerzeichen, Zeilenumbrüche
        und unnötige Abstände.
        """

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

    @staticmethod
    def _datei_informationen(dateipfad):
        """
        Liest Kategorie und Seitennummer aus dem Dateinamen.

        Beispiele:

        studium_1.html
            -> Kategorie: Studium
            -> Seite: 1

        beruf_ausbildung_2.html
            -> Kategorie: Beruf Ausbildung
            -> Seite: 2
        """

        dateiname = dateipfad.stem

        treffer = re.match(
            r"^(?P<kategorie>.+?)_(?P<seite>\d+)$",
            dateiname,
        )

        if not treffer:
            kategorie = (
                dateiname
                .replace("_", " ")
                .strip()
                .title()
            )

            return kategorie, None

        kategorie = (
            treffer
            .group("kategorie")
            .replace("_", " ")
            .strip()
            .title()
        )

        seite = int(
            treffer.group("seite")
        )

        return kategorie, seite

    def _lese_html(self, dateipfad):
        try:
            return dateipfad.read_text(
                encoding="utf-8",
            )

        except UnicodeDecodeError:
            return dateipfad.read_text(
                encoding="utf-8",
                errors="replace",
            )

    def _extrahiere_fragen(self, dateipfad):
        html = self._lese_html(
            dateipfad
        )

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        fragen = []
        bereits_gesehen = set()

        # Hauptselektor für die eigentlichen Fragenkarten.
        frage_links = soup.select(
            'a.ListingElement-questionLink[href^="/frage/"]'
        )

        # Fallback, falls Gutefrage den Klassennamen ändert.
        if not frage_links:
            frage_links = soup.select(
                'a[href^="/frage/"]'
            )

        for link in frage_links:
            href = (
                link.get("href", "")
                .strip()
            )

            if not re.match(
                r"^/frage/[^/?#]+/?$",
                href,
            ):
                continue

            url = urljoin(
                self.BASE_URL,
                href,
            )

            if url in bereits_gesehen:
                continue

            raw_content = self._bereinige_text(
                link.get_text(
                    separator=" ",
                    strip=True,
                )
            )

            # Links wie "3 Antworten" ignorieren.
            if re.fullmatch(
                r"\d+\s+Antwort(?:en)?",
                raw_content,
                flags=re.IGNORECASE,
            ):
                continue

            if len(raw_content) < 10:
                continue

            bereits_gesehen.add(url)

            fragen.append(
                {
                    "url": url,
                    "raw_content": raw_content,
                }
            )

        return fragen

    def _baue_insert_daten(
        self,
        frage,
        kategorie,
        seite,
        dateiname,
        vorhandene_spalten,
    ):
        """
        Fügt nur Werte für Spalten hinzu,
        die in forum_posts tatsächlich existieren.
        """

        daten = {
            "url": frage["url"],
            "raw_content": frage["raw_content"],
        }

        if "status" in vorhandene_spalten:
            daten["status"] = 0

        if "forum_kategorie" in vorhandene_spalten:
            daten["forum_kategorie"] = kategorie

        if "source" in vorhandene_spalten:
            daten["source"] = "gutefrage.net"

        if "source_name" in vorhandene_spalten:
            daten["source_name"] = "gutefrage.net"

        if "source_file" in vorhandene_spalten:
            daten["source_file"] = dateiname

        if "source_page" in vorhandene_spalten:
            daten["source_page"] = seite

        return daten

    def _speichere_frage(
        self,
        cursor,
        daten,
    ):
        url = daten["url"]

        cursor.execute(
            f"""
            SELECT 1
            FROM {self.TABLE_NAME}
            WHERE url = ?
            LIMIT 1
            """,
            (url,),
        )

        if cursor.fetchone() is not None:
            return False

        spalten = list(daten.keys())

        spalten_sql = ", ".join(spalten)
        platzhalter = ", ".join(
            ["?"] * len(spalten)
        )

        werte = [
            daten[spalte]
            for spalte in spalten
        ]

        cursor.execute(
            f"""
            INSERT INTO {self.TABLE_NAME}
            ({spalten_sql})
            VALUES ({platzhalter})
            """,
            werte,
        )

        return True

    def scrapen(self):
        if not self.html_ordner.exists():
            print(
                "\nHTML-Ordner wurde nicht gefunden:"
            )

            print(
                self.html_ordner.resolve()
            )

            return 0

        html_dateien = sorted(
            self.html_ordner.glob("*.html")
        )

        if not html_dateien:
            print(
                "\nKeine HTML-Dateien gefunden in:"
            )

            print(
                self.html_ordner.resolve()
            )

            return 0

        print(
            f"\n[Agent 1 - gutefrage lokal] "
            f"{len(html_dateien)} HTML-Dateien gefunden."
        )

        insgesamt_gefunden = 0
        insgesamt_neu = 0
        insgesamt_duplikate = 0

        with sqlite3.connect(
            self.db_file
        ) as conn:
            cursor = conn.cursor()

            vorhandene_spalten = (
                self._hole_tabellen_spalten(
                    conn
                )
            )

            for dateipfad in html_dateien:
                kategorie, seite = (
                    self._datei_informationen(
                        dateipfad
                    )
                )

                fragen = self._extrahiere_fragen(
                    dateipfad
                )

                insgesamt_gefunden += len(
                    fragen
                )

                neu_in_datei = 0
                duplikate_in_datei = 0

                print(
                    "\n"
                    "========================================"
                )

                print(
                    f"Datei: {dateipfad.name}"
                )

                print(
                    f"Kategorie laut Dateiname: {kategorie}"
                )

                print(
                    f"Seite: {seite}"
                )

                print(
                    f"Gefundene Fragen: {len(fragen)}"
                )

                print(
                    "========================================"
                )

                for frage in fragen:
                    daten = self._baue_insert_daten(
                        frage=frage,
                        kategorie=kategorie,
                        seite=seite,
                        dateiname=dateipfad.name,
                        vorhandene_spalten=vorhandene_spalten,
                    )

                    wurde_gespeichert = (
                        self._speichere_frage(
                            cursor,
                            daten,
                        )
                    )

                    if wurde_gespeichert:
                        neu_in_datei += 1
                        insgesamt_neu += 1

                        print(
                            "Gespeichert:",
                            frage["raw_content"][:80],
                        )

                    else:
                        duplikate_in_datei += 1
                        insgesamt_duplikate += 1

                conn.commit()

                print(
                    f"\nNeu gespeichert: {neu_in_datei}"
                )

                print(
                    f"Bereits vorhanden: "
                    f"{duplikate_in_datei}"
                )

        print(
            "\n"
            "[Agent 1 - gutefrage lokal] Fertig!"
        )

        print(
            f"Gefunden: {insgesamt_gefunden}"
        )

        print(
            f"Neu gespeichert: {insgesamt_neu}"
        )

        print(
            f"Bereits vorhanden: "
            f"{insgesamt_duplikate}"
        )

        return insgesamt_neu


if __name__ == "__main__":
    scraper = Agent1ScraperGutefrage(
        db_file="service_sonar.db",
        html_ordner="gutefrage_html",
    )

    scraper.scrapen()