"""Interactive Telegram bot — responds to commands anytime."""

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _reply(update: Update, text: str) -> None:
    """Send reply, splitting into chunks if over Telegram's 4096 char limit."""
    limit = 4000
    if len(text) <= limit:
        await update.message.reply_text(text, parse_mode="Markdown")
        return
    lines = text.split("\n")
    chunk = []
    for line in lines:
        if sum(len(l) + 1 for l in chunk) + len(line) > limit:
            await update.message.reply_text("\n".join(chunk), parse_mode="Markdown")
            chunk = []
        chunk.append(line)
    if chunk:
        await update.message.reply_text("\n".join(chunk), parse_mode="Markdown")


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, (
        "📊 *NSE 500 Results Calendar*\n\n"
        "Commands:\n"
        "/today — Today's results schedule\n"
        "/week — This week's full calendar\n"
        "/highlights — AI summaries of today's results \\(on demand\\)\n"
        "/company SYMBOL — Details for a specific stock\n\n"
        "_Scheduled alerts: morning list at 8 AM, AI highlights at 6 PM_"
    ))


# ── /today ────────────────────────────────────────────────────────────────────

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from processor import get_todays_results, load_calendar, quarter_label, format_mcap
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()
    companies = get_todays_results()
    date_label = datetime.today().strftime("%d %b %Y")

    if not companies:
        await _reply(update, f"No NSE 500 companies scheduled to report results today \\({date_label}\\)\\.")
        return

    lines = [f"📊 *Results — {date_label}* | {quarter}\n",
             f"_{len(companies)} companies reporting today_\n"]
    for i, c in enumerate(companies, 1):
        mcap = format_mcap(c.get("market_cap_cr", 0)) if c.get("market_cap_cr") else "—"
        sector = f" _{c['sector']}_" if c.get("sector") else ""
        lines.append(f"{i}\\. *{c['symbol']}* — {c['name']}{sector} | {mcap}")
    await _reply(update, "\n".join(lines))


# ── /week ─────────────────────────────────────────────────────────────────────

async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from processor import load_calendar, quarter_label, format_mcap, _parse_date
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()
    today = datetime.today().date()
    week_end = today + timedelta(days=6)

    week_entries = []
    for e in cal.get("entries", []):
        try:
            d = _parse_date(e["date"]).date()
            if today <= d <= week_end:
                week_entries.append((d, e))
        except Exception:
            pass

    if not week_entries:
        await _reply(update, "No NSE 500 results scheduled in the next 7 days\\.")
        return

    lines = [f"📅 *This Week's Results* | {quarter}\n"]
    current_date = None
    for date, e in sorted(week_entries, key=lambda x: (x[0], -x[1].get("market_cap_cr", 0))):
        if date != current_date:
            current_date = date
            label = "Today" if date == today else date.strftime("%a, %d %b")
            lines.append(f"\n*{label}*")
        mcap = format_mcap(e.get("market_cap_cr", 0)) if e.get("market_cap_cr") else "—"
        lines.append(f"  • *{e['symbol']}* {e['name']} | {mcap}")

    await _reply(update, "\n".join(lines))


# ── /highlights ───────────────────────────────────────────────────────────────

async def cmd_highlights(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from processor import get_todays_results, load_calendar, quarter_label
    from ai_engine import generate_all_highlights

    companies = get_todays_results()
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()

    if not companies:
        await _reply(update, "No NSE 500 companies reporting today — nothing to highlight\\.")
        return

    await update.message.reply_text(
        f"⏳ Generating AI highlights for {len(companies)} companies\\. "
        f"This takes 2–3 minutes\\.",
        parse_mode="Markdown",
    )

    date_str = datetime.today().strftime("%d-%m-%Y")
    loop = asyncio.get_event_loop()
    enriched = await loop.run_in_executor(
        None,
        lambda: generate_all_highlights(companies, quarter, date_str),
    )

    lines = [f"🔔 *{quarter} Highlights — {datetime.today().strftime('%d %b')}*\n"]
    for c in enriched:
        highlight = c.get("highlight") or "Highlight not available\\."
        lines.append(f"*{c['symbol']}* \\({c.get('name', '')}\\)")
        lines.append(highlight)
        lines.append("")

    await _reply(update, "\n".join(lines))


# ── /company ──────────────────────────────────────────────────────────────────

async def cmd_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from processor import load_calendar, quarter_label, format_mcap, _parse_date
    from ai_engine import generate_highlight, get_result_announcement_url

    if not context.args:
        await _reply(update, "Usage: /company SYMBOL\nExample: /company RELIANCE")
        return

    symbol = context.args[0].upper().strip()
    cal = load_calendar()
    quarter = cal.get("quarter") or quarter_label()
    matches = [e for e in cal.get("entries", []) if e["symbol"] == symbol]

    if not matches:
        await _reply(update, f"*{symbol}* not found in the NSE 500 results calendar this season\\.")
        return

    e = matches[0]
    mcap = format_mcap(e.get("market_cap_cr", 0)) if e.get("market_cap_cr") else "—"

    lines = [
        f"📊 *{symbol}* — {e.get('name', '')}",
        f"Sector: {e.get('sector', '—')}",
        f"Market Cap: {mcap}",
        f"Result Date: {e.get('date', '—')} | {quarter}",
    ]

    try:
        result_date = _parse_date(e["date"]).date()
        today = datetime.today().date()

        if result_date > today:
            days_left = (result_date - today).days
            lines.append(f"_Results in {days_left} day{'s' if days_left != 1 else ''}_")
            await _reply(update, "\n".join(lines))

        elif result_date == today:
            lines.append("_Results scheduled for today — use /highlights for AI summary_")
            await _reply(update, "\n".join(lines))

        else:
            lines.append("\n_Fetching AI highlight\\.\\.\\._")
            await _reply(update, "\n".join(lines))

            date_str = result_date.strftime("%d-%m-%Y")
            loop = asyncio.get_event_loop()

            pdf_url = await loop.run_in_executor(
                None, lambda: get_result_announcement_url(symbol, date_str)
            )
            highlight = await loop.run_in_executor(
                None, lambda: generate_highlight(symbol, e.get("name", symbol), quarter, pdf_url)
            )
            await _reply(update, f"*AI Highlight:*\n{highlight}")

    except Exception as ex:
        logger.error("cmd_company error: %s", ex)
        await _reply(update, "\n".join(lines))


# ── Bot runner ────────────────────────────────────────────────────────────────

def run_bot() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set — interactive bot not started")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("highlights", cmd_highlights))
    app.add_handler(CommandHandler("company", cmd_company))

    logger.info("Telegram bot polling started")
    app.run_polling(drop_pending_updates=True)


def start_bot_thread() -> None:
    """Launch the bot in a daemon thread — called from app.py or standalone."""
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_bot()  # run directly (blocks)
