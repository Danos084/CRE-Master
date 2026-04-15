"""
Bayside Commercial Listings Agent – Orchestrator
================================================
Two modes:
  python main.py --mode weekly    Full scrape → Excel → PPTX → email
  python main.py --mode daily     Refresh only (update last_updated) → email

Designed to run via:
  - GitHub Actions cron
  - Cowork scheduled task
  - crontab:
      0 7 * * *  cd /path/to/agent && python main.py --mode daily
      0 6 * * 1  cd /path/to/agent && python main.py --mode weekly
"""

import argparse
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


def run_weekly():
    log.info("═══ WEEKLY RUN started ═══")

    log.info("Step 1/4 – Scraping listings…")
    from scraper import run_scrape
    listings = run_scrape(headless=True)

    log.info("Step 2/4 – Building Excel workbook…")
    from excel_builder import build_excel
    build_excel(listings)

    log.info("Step 3/4 – Building PowerPoint report…")
    from pptx_builder import build_pptx
    build_pptx(listings)

    log.info("Step 4/4 – Sending email…")
    from emailer import send_report
    send_report("Weekly Report")

    log.info("═══ WEEKLY RUN complete ═══")


def run_daily():
    log.info("═══ DAILY REFRESH started ═══")
    import json
    from pathlib import Path
    from datetime import datetime

    # Load existing, rebuild outputs, email
    LISTINGS_FILE = Path("data/listings.json")
    if not LISTINGS_FILE.exists():
        log.warning("No listings.json found – running full weekly scrape instead")
        run_weekly()
        return

    with open(LISTINGS_FILE) as f:
        listings = json.load(f)

    log.info(f"  Loaded {len(listings)} listings from cache")

    log.info("Step 1/3 – Rebuilding Excel…")
    from excel_builder import build_excel
    build_excel(listings)

    log.info("Step 2/3 – Rebuilding PowerPoint…")
    from pptx_builder import build_pptx
    build_pptx(listings)

    log.info("Step 3/3 – Sending daily email…")
    from emailer import send_report
    send_report("Daily Update")

    log.info("═══ DAILY REFRESH complete ═══")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bayside Commercial Listings Agent")
    parser.add_argument(
        "--mode",
        choices=["weekly", "daily"],
        default="weekly",
        help="weekly = full scrape; daily = rebuild + email from cache"
    )
    args = parser.parse_args()

    if args.mode == "weekly":
        run_weekly()
    else:
        run_daily()
