"""Claude-powered EOD result highlights generator."""

import io
import json
import logging
import os
import time
from datetime import datetime, timedelta

import anthropic
import pdfplumber

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ── Data fetching ─────────────────────────────────────────────────────────────

def _extract_pdf_text(url: str, max_chars: int = 8000) -> str:
    from fetcher import _nse_session
    session = _nse_session()  # need NSE cookies for the archive server
    try:
        resp = session.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        content = resp.content
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages[:8])
        return text[:max_chars]
    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", url, e)
        return ""


def _fetch_nse_financial_results(symbol: str) -> str:
    """Pull structured quarterly financials from NSE's results API."""
    from fetcher import _nse_session
    session = _nse_session()
    today = datetime.today()
    from_date = (today - timedelta(days=120)).strftime("%d-%m-%Y")
    to_date = today.strftime("%d-%m-%Y")
    url = "https://www.nseindia.com/api/corporates-financial-results"
    params = {"index": "equities", "period": "Quarterly", "symbol": symbol,
              "from_date": from_date, "to_date": to_date}
    try:
        resp = session.get(url, params=params, timeout=15)
        if resp.ok and resp.text.strip() and resp.text.strip()[0] in "[{":
            data = resp.json()
            # Take the most recent entry
            latest = data[0] if isinstance(data, list) and data else data
            return json.dumps(latest, indent=2)[:6000]
    except Exception as e:
        logger.warning("NSE financial results API failed for %s: %s", symbol, e)
    return ""


_RESULT_FILE_PATTERNS = ("_FR_Final.pdf", "_FR.pdf", "_QR.pdf", "_FinancialResult", "_Results.pdf")
_RESULT_DESC_KEYWORDS = ("outcome of board meeting", "financial result", "quarterly result")

def _find_announcement_pdf(symbol: str, board_date_str: str) -> str | None:
    """Search NSE announcements ±3 days around the board meeting date.

    NSE uses filename suffixes (_FR.pdf, _QR.pdf) to identify results PDFs,
    not the description field, so we match on both.
    """
    from fetcher import fetch_announcements
    target = datetime.strptime(board_date_str, "%d-%m-%Y")

    candidates: list[tuple[int, str]] = []   # (priority, url)

    for delta in range(-1, 4):
        check = (target + timedelta(days=delta)).strftime("%d-%m-%Y")
        for ann in fetch_announcements(symbol, check):
            url = ann.get("attchmntFile") or ann.get("attachmentUrl") or ""
            if not url.lower().endswith(".pdf"):
                continue
            desc = str(ann.get("desc", "")).lower()
            url_upper = url.upper()

            if "_FR_FINAL" in url_upper:
                candidates.append((1, url))
            elif "_FR.PDF" in url_upper or url_upper.endswith("_FR.PDF"):
                candidates.append((2, url))
            elif "_QR.PDF" in url_upper:
                candidates.append((3, url))
            elif any(k in desc for k in _RESULT_DESC_KEYWORDS):
                candidates.append((4, url))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        chosen = candidates[0][1]
        logger.info("Found results PDF for %s: %s", symbol, chosen)
        return chosen
    return None


def _gather_context(symbol: str, date_str: str) -> str:
    """Try three sources in order; return the richest context found."""

    # 1. NSE structured financial results API (fastest, most reliable)
    logger.info("  Trying NSE financial results API for %s", symbol)
    ctx = _fetch_nse_financial_results(symbol)
    if ctx and len(ctx) > 100:
        return f"[NSE Quarterly Financial Data]\n{ctx}"

    # 2. PDF from NSE announcement (actual filing document)
    logger.info("  Trying NSE announcement PDF for %s", symbol)
    pdf_url = _find_announcement_pdf(symbol, date_str)
    if pdf_url:
        ctx = _extract_pdf_text(pdf_url)
        if ctx and len(ctx) > 100:
            return f"[NSE Filing PDF]\n{ctx}"

    logger.warning("  No data found for %s — highlight will be unavailable", symbol)
    return ""


# ── Highlight generation ──────────────────────────────────────────────────────

def generate_highlight(
    symbol: str,
    company: str,
    quarter: str,
    date_str: str,
) -> str:
    """Generate a 2-line highlight using the best available data source."""
    context = _gather_context(symbol, date_str)

    if not context:
        return f"Data not yet available on NSE for {company} ({quarter}). Check NSE/BSE filings directly."

    prompt = (
        f"Here is the {quarter} financial results data for {company} (NSE: {symbol}):\n\n"
        f"{context}\n\n"
        f"Write EXACTLY 2 lines:\n"
        f"Line 1: Key financials — Revenue/Net Sales and Net Profit/PAT with YoY % change.\n"
        f"Line 2: One notable business highlight, management comment, or strategic development.\n"
        f"Use actual numbers from the data. No markdown. No bullet points."
    )

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error("Claude API call failed for %s: %s", symbol, e)
        return "Highlight generation failed — please retry."


def generate_all_highlights(
    companies: list[dict],
    quarter: str,
    date_str: str,
) -> list[dict]:
    results = []
    for i, c in enumerate(companies):
        symbol = c["symbol"]
        name = c.get("name", symbol)
        logger.info("[%d/%d] Generating highlight for %s", i + 1, len(companies), symbol)
        highlight = generate_highlight(symbol, name, quarter, date_str)
        results.append({**c, "highlight": highlight})
        if i < len(companies) - 1:
            time.sleep(1.5)
    return results
