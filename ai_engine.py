"""Claude-powered EOD result highlights generator."""

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import anthropic
import requests

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_pdf_text(url: str, max_chars: int = 8000) -> str:
    """Download a PDF from NSE and extract its text."""
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages[:8])
        return text[:max_chars]
    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", url, e)
        return ""


# ── Web search fallback ───────────────────────────────────────────────────────

def _web_search_result(company: str, symbol: str, quarter: str) -> str:
    """Use Claude with search to find result highlights when no PDF is available."""
    query = f"{company} ({symbol}) {quarter} financial results revenue profit YoY"
    prompt = (
        f"Search for and summarize the latest quarterly financial results for "
        f"{company} (NSE: {symbol}) for {quarter}. "
        f"Extract: Revenue/Net Sales, Net Profit/PAT, YoY growth percentages, and 1 key business highlight. "
        f"Return ONLY 2 concise lines (no bullet points, no markdown headers)."
    )
    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error("Web search fallback failed for %s: %s", symbol, e)
        return ""


# ── Main highlight generator ──────────────────────────────────────────────────

def generate_highlight(
    symbol: str,
    company: str,
    quarter: str,
    pdf_url: str | None = None,
) -> str:
    """Generate a 2-line highlight for a company's quarterly results."""
    context = ""

    if pdf_url:
        context = _extract_pdf_text(pdf_url)

    if context:
        prompt = (
            f"Here is the financial results announcement for {company} (NSE: {symbol}) for {quarter}:\n\n"
            f"{context}\n\n"
            f"Write EXACTLY 2 lines summarizing: (1) key financial metrics with YoY % change, "
            f"(2) one strategic highlight or management comment. "
            f"Be precise and use numbers. No markdown formatting."
        )
    else:
        return _web_search_result(company, symbol, quarter)

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error("Highlight generation failed for %s: %s", symbol, e)
        return _web_search_result(company, symbol, quarter)


def generate_all_highlights(
    companies: list[dict],
    quarter: str,
    date_str: str,
) -> list[dict]:
    """Generate highlights for all companies that reported today. Returns enriched list."""
    from fetcher import get_result_announcement_url

    results = []
    for i, c in enumerate(companies):
        symbol = c["symbol"]
        name = c.get("name", symbol)
        logger.info("[%d/%d] Generating highlight for %s", i + 1, len(companies), symbol)

        pdf_url = get_result_announcement_url(symbol, date_str)
        highlight = generate_highlight(symbol, name, quarter, pdf_url)

        results.append({**c, "highlight": highlight})
        if i < len(companies) - 1:
            time.sleep(1.5)

    return results
