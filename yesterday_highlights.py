#!/usr/bin/env python3
"""Send AI highlights for a specific past date."""

import logging
import sys
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from processor import load_calendar, _parse_date, quarter_label
from ai_engine import generate_all_highlights
from notifier import send_eod_highlights

TARGET_DATE = date(2026, 5, 13)

def main():
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()
    companies = [
        e for e in cal["entries"]
        if _parse_date(e["date"]).date() == TARGET_DATE
    ]
    logging.info("Companies that reported on %s: %d", TARGET_DATE.strftime("%d %b"), len(companies))
    for c in companies:
        logging.info("  %s — %s", c["symbol"], c["name"])

    if not companies:
        logging.info("No companies found for that date.")
        return

    date_str = TARGET_DATE.strftime("%d-%m-%Y")
    enriched = generate_all_highlights(companies, quarter, date_str)
    send_eod_highlights(enriched, quarter)

if __name__ == "__main__":
    main()
