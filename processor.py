"""Build, cache, and query the results calendar. Persists to local JSON + Supabase."""

import json
import logging
import os
from datetime import datetime

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


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> datetime:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return datetime.max


# ── Supabase ──────────────────────────────────────────────────────────────────

def _sb_headers(write: bool = False) -> dict | None:
    """Return Supabase REST headers. Writes use service_role key to bypass RLS."""
    url = os.environ.get("SUPABASE_URL")
    if not url:
        return None
    key = (os.environ.get("SUPABASE_SERVICE_KEY") if write
           else os.environ.get("SUPABASE_KEY"))
    if not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _sb_url(table: str) -> str:
    return f"{os.environ['SUPABASE_URL']}/rest/v1/{table}"


def push_to_supabase(entries: list[dict], quarter: str, from_date: str, to_date: str) -> None:
    import requests as req
    headers = _sb_headers(write=True)
    if not headers:
        logger.warning("Supabase not configured — skipping push")
        return

    rows = [
        {
            "symbol":        e.get("symbol", ""),
            "name":          e.get("name", ""),
            "sector":        e.get("sector", ""),
            "date":          e.get("date", ""),
            "description":   (e.get("description") or "")[:500],
            "attachment":    e.get("attachment", ""),
            "market_cap":    e.get("market_cap", 0) or 0,
            "market_cap_cr": e.get("market_cap_cr", 0) or 0,
            "quarter":       quarter,
        }
        for e in entries
    ]

    try:
        # Delete all existing rows
        req.delete(_sb_url("calendar_entries"), headers=headers,
                   params={"symbol": "neq.placeholder"}).raise_for_status()

        # Insert in batches of 100
        ins_headers = {**headers, "Prefer": "return=minimal"}
        for i in range(0, len(rows), 100):
            req.post(_sb_url("calendar_entries"), json=rows[i:i + 100],
                     headers=ins_headers).raise_for_status()

        # Upsert metadata
        meta = {"id": 1, "quarter": quarter,
                "updated_at": datetime.now().isoformat(),
                "from_date": from_date, "to_date": to_date}
        req.post(_sb_url("calendar_meta"), json=meta,
                 headers={**headers, "Prefer": "resolution=merge-duplicates"}).raise_for_status()

        logger.info("Pushed %d entries to Supabase", len(rows))
    except Exception as e:
        logger.error("Supabase push failed: %s", e)


def load_from_supabase() -> dict:
    import requests as req
    headers = _sb_headers()
    if not headers:
        return {}
    try:
        meta = req.get(_sb_url("calendar_meta"), headers=headers,
                       params={"id": "eq.1"}).json()
        meta = meta[0] if meta else {}
        entries = req.get(_sb_url("calendar_entries"), headers=headers,
                          params={"select": "*", "order": "date"}).json()
        return {
            "quarter":    meta.get("quarter", quarter_label()),
            "updated_at": meta.get("updated_at"),
            "from_date":  meta.get("from_date"),
            "to_date":    meta.get("to_date"),
            "entries":    entries if isinstance(entries, list) else [],
        }
    except Exception as e:
        logger.error("Supabase load failed: %s", e)
        return {}


# ── Calendar build / load ─────────────────────────────────────────────────────

def build_calendar() -> list[dict]:
    """Fetch fresh data from NSE, enrich with market cap, save to disk + Supabase."""
    from_date, to_date = current_results_window()
    logger.info("Fetching board meetings %s → %s", from_date, to_date)

    nse500 = fetch_nse500()
    meetings = fetch_board_meetings(from_date, to_date)
    filtered = filter_results_meetings(meetings, set(nse500.keys()))

    for entry in filtered:
        sym = entry["symbol"]
        info = nse500.get(sym, {})
        entry["sector"] = info.get("sector", "")
        if not entry.get("name") or entry["name"] == sym:
            entry["name"] = info.get("name", sym)

    symbols = list({e["symbol"] for e in filtered})
    mcaps = fetch_market_caps(symbols)
    for entry in filtered:
        entry["market_cap"] = mcaps.get(entry["symbol"], 0)
        entry["market_cap_cr"] = round(entry["market_cap"] / 1e7, 0) if entry["market_cap"] else 0

    filtered.sort(key=lambda x: (_parse_date(x["date"]), -x["market_cap"]))

    q = quarter_label()
    payload = {
        "quarter":    q,
        "updated_at": datetime.now().isoformat(),
        "from_date":  from_date,
        "to_date":    to_date,
        "entries":    filtered,
    }

    CALENDAR_FILE.parent.mkdir(exist_ok=True)
    CALENDAR_FILE.write_text(json.dumps(payload, indent=2))
    logger.info("Saved %d entries to local JSON", len(filtered))

    push_to_supabase(filtered, q, from_date, to_date)
    return filtered


def load_calendar() -> dict:
    """Load from local JSON; fall back to Supabase when running on Streamlit Cloud."""
    if CALENDAR_FILE.exists():
        try:
            return json.loads(CALENDAR_FILE.read_text())
        except Exception:
            pass
    logger.info("Local calendar not found — loading from Supabase")
    data = load_from_supabase()
    return data if data else {"quarter": quarter_label(), "updated_at": None, "entries": []}


def get_todays_results() -> list[dict]:
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
