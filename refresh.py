#!/usr/bin/env python3
"""Refresh the calendar data from NSE — run daily or on-demand."""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

sys.path.insert(0, str(Path(__file__).parent))

from processor import build_calendar


def main():
    entries = build_calendar()
    logging.info("Calendar refreshed: %d entries", len(entries))


if __name__ == "__main__":
    main()
