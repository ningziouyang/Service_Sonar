import argparse
import time
from datetime import datetime

from agent1_scraper import Agent1Scraper
from agent2_cleaner import Agent2Cleaner
from agent3_analyzer import Agent3Analyzer
from agent4_innovator import Agent4Innovator
from main import init_db, human_intervention_interface


def run_pipeline_refresh(
    scrape: bool = False,
    clean: bool = True,
    review: bool = False,
    analyze: bool = True,
    innovate: bool = False,
    agent3_limit: int | None = 20,
    agent3_sleep: float = 1.0,
):
    """
    Runs one controlled refresh of the Service Sonar pipeline.

    This is one refresh cycle:
    - optionally scrape new posts
    - clean raw posts
    - optionally run Human Review
    - analyze cleaned posts in a limited Agent 3 batch
    - optionally update Agent 4 service opportunities
    """
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n============================================================")
    print(f"[Refresh] Service Sonar pipeline refresh started at {started_at}")
    print("============================================================")

    print("\n[Refresh] Initialisiere Datenbank...")
    init_db()

    if scrape:
        print("\n[Refresh] Agent 1: Sammle neue Rohdaten...")
        scraper = Agent1Scraper()
        scraper.scrapen()
    else:
        print("\n[Refresh] Agent 1 übersprungen. Nutze vorhandene Rohdaten.")

    if clean:
        print("\n[Refresh] Agent 2: Bereinige neue Rohdaten...")
        cleaner = Agent2Cleaner()
        cleaner.run()
    else:
        print("\n[Refresh] Agent 2 übersprungen.")

    if review:
        print("\n[Refresh] Human Review: Prüfe blockierte Fälle...")
        human_intervention_interface()
    else:
        print("\n[Refresh] Human Review übersprungen, damit der Refresh automatisch laufen kann.")

    if analyze:
        print("\n[Refresh] Agent 3: Analysiere bereinigte Beiträge...")
        analyzer = Agent3Analyzer()
        analyzer.run(
            limit=agent3_limit,
            sleep_seconds=agent3_sleep,
            max_attempts=3,
        )
    else:
        print("\n[Refresh] Agent 3 übersprungen.")

    if innovate:
        print("\n[Refresh] Agent 4: Aktualisiere Service Opportunities...")
        innovator = Agent4Innovator()
        innovator.run()
    else:
        print("\n[Refresh] Agent 4 übersprungen.")

    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n============================================================")
    print(f"[Refresh] Pipeline refresh finished at {finished_at}")
    print("============================================================\n")


def run_watch_mode(
    interval_minutes: int,
    scrape: bool,
    clean: bool,
    review: bool,
    analyze: bool,
    innovate: bool,
    agent3_limit: int | None,
    agent3_sleep: float,
):
    """
    Runs the refresh repeatedly.

    This is the prototype version of near-real-time processing:
    instead of a true live stream, the system refreshes itself periodically.
    """
    print("\n============================================================")
    print("[Watch] Service Sonar near-real-time mode started")
    print(f"[Watch] Refresh interval: every {interval_minutes} minute(s)")
    print("[Watch] Stop with CTRL + C")
    print("============================================================\n")

    while True:
        try:
            run_pipeline_refresh(
                scrape=scrape,
                clean=clean,
                review=review,
                analyze=analyze,
                innovate=innovate,
                agent3_limit=agent3_limit,
                agent3_sleep=agent3_sleep,
            )
        except Exception as error:
            print("\n[Watch ERROR] Refresh cycle failed, but watch mode will continue.")
            print(f"[Watch ERROR] {error}")

        print(f"\n[Watch] Waiting {interval_minutes} minute(s) until next refresh...")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a controlled or periodic Service Sonar pipeline refresh."
    )

    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and refresh the pipeline repeatedly."
    )

    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Refresh interval in minutes when --watch is used."
    )

    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Run Agent 1 scraper before cleaning."
    )

    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip Agent 2 cleaning."
    )

    parser.add_argument(
        "--review",
        action="store_true",
        help="Run Human Review. Not recommended for automatic watch mode because it may block execution."
    )

    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Skip Agent 3 analysis."
    )

    parser.add_argument(
        "--innovate",
        action="store_true",
        help="Run Agent 4 innovation generation after analysis."
    )

    parser.add_argument(
        "--agent3-limit",
        type=int,
        default=20,
        help="Maximum number of status=1 records Agent 3 should process per refresh cycle."
    )

    parser.add_argument(
        "--agent3-sleep",
        type=float,
        default=1.0,
        help="Seconds to wait between Agent 3 LLM calls."
    )

    args = parser.parse_args()

    if args.interval_minutes <= 0:
        raise ValueError("--interval-minutes must be positive.")

    if args.agent3_limit <= 0:
        raise ValueError("--agent3-limit must be positive.")

    if args.agent3_sleep < 0:
        raise ValueError("--agent3-sleep must not be negative.")

    clean = not args.no_clean
    analyze = not args.no_analyze

    if args.watch:
        run_watch_mode(
            interval_minutes=args.interval_minutes,
            scrape=args.scrape,
            clean=clean,
            review=args.review,
            analyze=analyze,
            innovate=args.innovate,
            agent3_limit=args.agent3_limit,
            agent3_sleep=args.agent3_sleep,
        )
    else:
        run_pipeline_refresh(
            scrape=args.scrape,
            clean=clean,
            review=args.review,
            analyze=analyze,
            innovate=args.innovate,
            agent3_limit=args.agent3_limit,
            agent3_sleep=args.agent3_sleep,
        )