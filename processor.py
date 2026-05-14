"""Build, cache, and query the results calendar."""

import json
import logging
from datetime import datetime
from pathlib import Path

from fetcher import (
    CALENDAR_FILE,
    current_results_window,
    fetch_board_meetings,
    fetch_market_caps,
    fetch_nse500,
    filter_results_meetings,
    quarter_label,
)

logger = logging.getLogger(__name__)


def _parse_date(date_str: str) -> datetime:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.max


def build_calendar() -> list[dict]:
    """Fetch fresh data from NSE, enrich with market cap, save to disk."""
    from_date, to_date = current_results_window()
    logger.info("Fetching board meetings %s → %s", from_date, to_date)

    nse500 = fetch_nse500()
    meetings = fetch_board_meetings(from_date, to_date)
    filtered = filter_results_meetings(meetings, set(nse500.keys()))

    # Enrich with sector info from NSE500 list
    for entry in filtered:
        sym = entry["symbol"]
        info = nse500.get(sym, {})
        entry["sector"] = info.get("sector", "")
        if not entry.get("name") or entry["name"] == sym:
            entry["name"] = info.get("name", sym)

    # Fetch market caps
    symbols = list({e["symbol"] for e in filtered})
    mcaps = fetch_market_caps(symbols)
    for entry in filtered:
        entry["market_cap"] = mcaps.get(entry["symbol"], 0)
        entry["market_cap_cr"] = round(entry["market_cap"] / 1e7, 0) if entry["market_cap"] else 0

    # Sort: date ascending, then market cap descending
    filtered.sort(key=lambda x: (_parse_date(x["date"]), -x["market_cap"]))

    payload = {
        "quarter": quarter_label(),
        "updated_at": datetime.now().isoformat(),
        "from_date": from_date,
        "to_date": to_date,
        "entries": filtered,
    }

    CALENDAR_FILE.parent.mkdir(exist_ok=True)
    CALENDAR_FILE.write_text(json.dumps(payload, indent=2))
    logger.info("Saved %d entries to calendar", len(filtered))
    return filtered


def load_calendar() -> dict:
    """Load calendar from disk cache."""
    if CALENDAR_FILE.exists():
        try:
            return json.loads(CALENDAR_FILE.read_text())
        except Exception:
            pass
    return {"quarter": quarter_label(), "updated_at": None, "entries": []}


def get_todays_results() -> list[dict]:
    """Return entries where the board meeting date is today."""
    today_str = datetime.today().strftime("%d-%b-%Y")
    cal = load_calendar()
    return [
        e for e in cal.get("entries", [])
        if _parse_date(e["date"]).date() == datetime.today().date()
    ]


def format_mcap(cap_cr: float) -> str:
    if cap_cr >= 100_000:
        return f"₹{cap_cr / 100_000:.1f}L Cr"
    if cap_cr >= 1_000:
        return f"₹{cap_cr / 1_000:.1f}K Cr"
    return f"₹{cap_cr:.0f} Cr"
