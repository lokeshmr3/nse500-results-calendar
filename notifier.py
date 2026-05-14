"""Telegram notifications: morning results alert and EOD highlights."""

import logging
import os
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


def _send(text: str, parse_mode: str = "Markdown") -> bool:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Telegram message sent (%d chars)", len(text))
        return True
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


def _split_and_send(text: str) -> None:
    """Send in chunks if message exceeds Telegram's 4096 char limit."""
    limit = 4000
    if len(text) <= limit:
        _send(text)
        return
    lines = text.split("\n")
    chunk, chunks = [], []
    for line in lines:
        if sum(len(l) + 1 for l in chunk) + len(line) > limit:
            chunks.append("\n".join(chunk))
            chunk = []
        chunk.append(line)
    if chunk:
        chunks.append("\n".join(chunk))
    for c in chunks:
        _send(c)


# ── Morning alert ──────────────────────────────────────────────────────────────

def send_morning_alert(companies: list[dict], quarter: str) -> None:
    date_label = datetime.today().strftime("%d %b %Y")

    if not companies:
        msg = (
            f"📊 *Results Calendar — {date_label}*\n\n"
            f"No NSE 500 companies scheduled to report results today ({quarter})."
        )
        _send(msg)
        return

    lines = [f"📊 *Results Calendar — {date_label}* | {quarter}\n"]
    lines.append(f"_{len(companies)} NSE 500 companies reporting today (sorted by market cap)_\n")

    from processor import format_mcap
    for i, c in enumerate(companies, 1):
        mcap = format_mcap(c.get("market_cap_cr", 0)) if c.get("market_cap_cr") else "—"
        sector = c.get("sector", "")
        sector_tag = f" _{sector}_" if sector else ""
        lines.append(f"{i}\\. *{c['symbol']}* — {c['name']}{sector_tag} | {mcap}")

    _split_and_send("\n".join(lines))


# ── EOD highlights ────────────────────────────────────────────────────────────

def send_eod_highlights(enriched: list[dict], quarter: str) -> None:
    date_label = datetime.today().strftime("%d %b %Y")

    if not enriched:
        _send(f"🔔 *EOD Results — {date_label}*\n\nNo result highlights available today.")
        return

    lines = [f"🔔 *{quarter} Results Highlights — {date_label}*\n"]

    for c in enriched:
        symbol = c["symbol"]
        name = c.get("name", symbol)
        highlight = c.get("highlight", "Highlights not available.")
        lines.append(f"*{symbol}* ({name})")
        lines.append(highlight)
        lines.append("")

    _split_and_send("\n".join(lines))
