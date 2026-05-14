#!/usr/bin/env python3
"""Morning alert: send today's results schedule to Telegram."""

import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

sys.path.insert(0, str(Path(__file__).parent))

from processor import get_todays_results, load_calendar, quarter_label
from notifier import send_morning_alert


def main():
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()
    companies = get_todays_results()

    logging.info("Today's results: %d companies", len(companies))
    send_morning_alert(companies, quarter)


if __name__ == "__main__":
    main()
