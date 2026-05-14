#!/usr/bin/env python3
"""EOD highlights: generate AI summaries of today's results and send via Telegram."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

sys.path.insert(0, str(Path(__file__).parent))

from processor import get_todays_results, load_calendar, quarter_label
from ai_engine import generate_all_highlights
from notifier import send_eod_highlights


def main():
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()
    companies = get_todays_results()

    if not companies:
        logging.info("No companies reporting today — skipping EOD highlights")
        from notifier import _send
        from datetime import datetime
        _send(
            f"🔔 *EOD — {datetime.today().strftime('%d %b %Y')}*\n\n"
            f"No NSE 500 results were scheduled today."
        )
        return

    date_str = datetime.today().strftime("%d-%m-%Y")
    logging.info("Generating highlights for %d companies", len(companies))
    enriched = generate_all_highlights(companies, quarter, date_str)
    send_eod_highlights(enriched, quarter)


if __name__ == "__main__":
    main()
