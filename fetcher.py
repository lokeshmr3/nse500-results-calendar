"""NSE data fetching: NSE500 constituents, board meetings, announcements, market cap."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.nseindia.com/",
}

MCAP_CACHE = Path("data/mcap_cache.json")
CALENDAR_FILE = Path("data/calendar.json")


# ── Session ──────────────────────────────────────────────────────────────────

def _nse_session() -> requests.Session:
    """NSE APIs require cookies from the homepage + the specific listing page."""
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get(NSE_BASE, timeout=15)
        time.sleep(2)
        s.get(f"{NSE_BASE}/companies-listing/corporate-filings-board-meetings", timeout=15)
        time.sleep(1.5)
    except Exception as e:
        logger.warning("NSE session init failed: %s", e)
    return s


# ── Quarter date range ────────────────────────────────────────────────────────

def current_results_window() -> tuple[str, str]:
    """Return (from_date, to_date) in DD-MM-YYYY for the ongoing results season."""
    today = datetime.today()
    m, y = today.month, today.year
    # Results seasons: Apr-May (Q4), Jul-Aug (Q1), Oct-Nov (Q2), Jan-Feb (Q3)
    if m in (4, 5, 6):
        return f"01-04-{y}", f"30-06-{y}"
    if m in (7, 8, 9):
        return f"01-07-{y}", f"30-09-{y}"
    if m in (10, 11, 12):
        return f"01-10-{y}", f"31-12-{y}"
    return f"01-01-{y}", f"31-03-{y}"


def quarter_label() -> str:
    today = datetime.today()
    m, y = today.month, today.year
    fy = y if m >= 4 else y - 1
    if m in (4, 5, 6):
        return f"Q4 FY{fy}"
    if m in (7, 8, 9):
        return f"Q1 FY{fy + 1}"
    if m in (10, 11, 12):
        return f"Q2 FY{fy + 1}"
    return f"Q3 FY{fy + 1}"


# ── NSE500 list ───────────────────────────────────────────────────────────────

def fetch_nse500() -> dict[str, dict]:
    """Return {symbol: {name, sector}} for all NSE500 constituents."""
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    try:
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        result = {}
        for _, row in df.iterrows():
            sym = str(row.get("Symbol", "")).strip()
            if sym:
                result[sym] = {
                    "name": str(row.get("Company Name", sym)).strip(),
                    "sector": str(row.get("Industry", "")).strip(),
                }
        logger.info("Fetched %d NSE500 symbols", len(result))
        return result
    except Exception as e:
        logger.error("NSE500 fetch failed: %s", e)
        return {}


# ── Board meetings ────────────────────────────────────────────────────────────

def fetch_board_meetings(from_date: str, to_date: str) -> list[dict]:
    """Fetch all board meetings from NSE for the given date range."""
    session = _nse_session()
    url = f"{NSE_BASE}/api/corporate-board-meetings"
    params = {"index": "equities", "from_date": from_date, "to_date": to_date, "symbol": ""}
    try:
        resp = session.get(url, params=params, timeout=20)
        logger.info("Board meetings HTTP %s, body length %d", resp.status_code, len(resp.text))
        if not resp.text.strip():
            logger.error("NSE returned empty body — session/cookie issue")
            return []
        resp.raise_for_status()
        data = resp.json()
        logger.info("Board meetings raw keys: %s", list(data.keys()) if isinstance(data, dict) else f"list len={len(data)}")
        return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        logger.error("Board meetings fetch failed: %s | response: %s", e, resp.text[:200] if 'resp' in dir() else "no response")
        return []


def filter_results_meetings(meetings: list[dict], nse500: set[str]) -> list[dict]:
    """Keep only Financial Results meetings for NSE500 companies.
    Deduplicates by (symbol, date) — NSE returns multiple rows per meeting.
    """
    seen: set[tuple] = set()
    out = []
    for m in meetings:
        symbol = str(m.get("bm_symbol", "")).strip().upper()
        purpose = str(m.get("bm_purpose", "")).lower()
        date = str(m.get("bm_date", "")).strip()
        key = (symbol, date)
        if symbol in nse500 and "financial result" in purpose and key not in seen:
            seen.add(key)
            out.append({
                "symbol": symbol,
                "name": m.get("sm_name", symbol),
                "sector": m.get("sm_indusrty", ""),   # NSE typo: "indusrty"
                "date": date,
                "description": m.get("bm_desc", ""),
                "attachment": m.get("attachment", ""),
            })
    return out


# ── Market cap ────────────────────────────────────────────────────────────────

def load_mcap_cache() -> dict[str, float]:
    if MCAP_CACHE.exists():
        try:
            data = json.loads(MCAP_CACHE.read_text())
            updated = datetime.fromisoformat(data.get("_ts", "2000-01-01"))
            if (datetime.now() - updated).days < 3:
                return data
        except Exception:
            pass
    return {}


def fetch_market_caps(symbols: list[str]) -> dict[str, float]:
    """Fetch market cap (INR) for NSE symbols using yfinance. Uses 3-day cache."""
    cache = load_mcap_cache()
    missing = [s for s in symbols if s not in cache]

    if missing:
        try:
            import yfinance as yf  # optional dependency
        except ImportError:
            logger.warning("yfinance not installed — market cap unavailable")
            return cache

        logger.info("Fetching market cap for %d symbols via yfinance", len(missing))
        for sym in missing:
            try:
                t = yf.Ticker(f"{sym}.NS")
                cap = t.fast_info.market_cap or 0
                cache[sym] = cap
            except Exception:
                cache[sym] = 0
            time.sleep(0.08)

        cache["_ts"] = datetime.now().isoformat()
        MCAP_CACHE.parent.mkdir(exist_ok=True)
        MCAP_CACHE.write_text(json.dumps(cache, indent=2))

    return cache


# ── Corporate announcements (for EOD highlights) ──────────────────────────────

def fetch_announcements(symbol: str, date_str: str) -> list[dict]:
    """Fetch NSE corporate announcements for a symbol on a given date (DD-MM-YYYY)."""
    session = _nse_session()
    url = f"{NSE_BASE}/api/corporate-announcements"
    params = {
        "index": "equities",
        "symbol": symbol,
        "from_date": date_str,
        "to_date": date_str,
    }
    try:
        resp = session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        logger.error("Announcements fetch failed for %s: %s", symbol, e)
        return []


def get_result_announcement_url(symbol: str, date_str: str) -> str | None:
    """Return PDF/attachment URL of the Financial Results announcement, if found."""
    for ann in fetch_announcements(symbol, date_str):
        desc = str(ann.get("desc", "") or ann.get("subject", "")).lower()
        if "financial result" in desc:
            return ann.get("attchmntFile") or ann.get("attachmentUrl")
    return None
