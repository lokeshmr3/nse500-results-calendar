"""Flask web dashboard for the NSE 500 Results Calendar."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

load_dotenv()

from processor import build_calendar, format_mcap, load_calendar, quarter_label

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from bot import start_bot_thread
start_bot_thread()

app = Flask(__name__)


def _enrich_for_ui(entries: list[dict]) -> list[dict]:
    today = datetime.today().date()
    out = []
    for e in entries:
        d = dict(e)
        try:
            from processor import _parse_date
            dt = _parse_date(d["date"]).date()
            d["date_fmt"] = dt.strftime("%d %b")
            d["status"] = "today" if dt == today else ("past" if dt < today else "upcoming")
        except Exception:
            d["date_fmt"] = d.get("date", "")
            d["status"] = "upcoming"
        d["mcap_label"] = format_mcap(d.get("market_cap_cr", 0)) if d.get("market_cap_cr") else "—"
        out.append(d)
    return out


@app.route("/")
def index():
    cal = load_calendar()
    entries = _enrich_for_ui(cal.get("entries", []))
    return render_template(
        "index.html",
        entries=entries,
        quarter=cal.get("quarter", quarter_label()),
        updated_at=cal.get("updated_at", ""),
        total=len(entries),
    )


@app.route("/api/calendar")
def api_calendar():
    cal = load_calendar()
    return jsonify(cal)


@app.route("/api/today")
def api_today():
    from processor import get_todays_results
    return jsonify(get_todays_results())


@app.route("/refresh")
def trigger_refresh():
    """Manual refresh endpoint (protect with a secret in production)."""
    secret = os.environ.get("REFRESH_SECRET", "")
    from flask import request, abort
    if secret and request.args.get("key") != secret:
        abort(403)
    entries = build_calendar()
    return jsonify({"status": "ok", "entries": len(entries)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
