"""NSE 500 Results Calendar — premium Streamlit dashboard."""

import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="NSE 500 Results Calendar",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Premium CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Header strip */
.app-header {
    background: linear-gradient(135deg, #1a1f36 0%, #2d3561 60%, #1a56db 100%);
    border-radius: 16px;
    padding: 28px 32px 22px;
    margin-bottom: 24px;
    color: white;
}
.app-header h1 { font-size: 2rem; font-weight: 800; margin: 0 0 4px; color: white; }
.app-header .sub  { font-size: 0.85rem; opacity: 0.7; margin: 0; }
.app-header .quarter-badge {
    display: inline-block;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-top: 8px;
}

/* Metric cards */
.metric-row { display: flex; gap: 14px; margin-bottom: 24px; }
.metric-card {
    flex: 1;
    border-radius: 12px;
    padding: 18px 20px;
    border: 1px solid #e8ecf4;
    background: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.metric-card .val  { font-size: 2rem; font-weight: 700; line-height: 1; }
.metric-card .lbl  { font-size: 0.75rem; font-weight: 500; color: #6b7280; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.6px; }
.card-today    { border-top: 3px solid #f59e0b; }
.card-upcoming { border-top: 3px solid #10b981; }
.card-past     { border-top: 3px solid #6b7280; }
.card-total    { border-top: 3px solid #1a56db; }
.val-today    { color: #d97706; }
.val-upcoming { color: #059669; }
.val-past     { color: #4b5563; }
.val-total    { color: #1a56db; }

/* Search bar */
.stTextInput input {
    border-radius: 10px !important;
    border: 1.5px solid #e0e7ff !important;
    padding: 10px 16px !important;
    font-size: 0.9rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.stTextInput input:focus { border-color: #1a56db !important; box-shadow: 0 0 0 3px rgba(26,86,219,0.1) !important; }

/* Status badges in table */
.badge {
    display: inline-block;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.badge-today    { background: #fef3c7; color: #92400e; }
.badge-upcoming { background: #d1fae5; color: #065f46; }
.badge-past     { background: #f3f4f6; color: #374151; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #f8faff;
    border-right: 1px solid #e8ecf4;
}
[data-testid="stSidebar"] .block-container { padding-top: 2rem; }

/* Divider */
hr { border: none; border-top: 1px solid #e8ecf4; margin: 16px 0; }

/* Results table */
.cal-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #e8ecf4;
}
.cal-table thead tr {
    background: linear-gradient(135deg, #1a1f36 0%, #2d3561 70%, #1a56db 100%);
    color: white;
}
.cal-table th {
    padding: 12px 14px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    text-align: left;
    white-space: nowrap;
}
.cal-table td {
    padding: 9px 14px;
    border-bottom: 1px solid #f0f2f8;
    vertical-align: middle;
}
.cal-table tbody tr:hover { background: #f0f4ff !important; }
.cal-table tbody tr:last-child td { border-bottom: none; }
.row-today { background: #fffbeb; }
.row-even  { background: #ffffff; }
.row-odd   { background: #f9fafb; }
.sym { font-weight: 700; color: #1a1f36; }
.date-cell { font-weight: 600; color: #374151; }
.mcap-cell { font-weight: 600; color: #1a56db; }
.sector-cell { font-size: 0.8rem; color: #6b7280; }
.seq { color: #d1d5db; font-size: 0.75rem; }
</style>
""", unsafe_allow_html=True)


# ── Supabase ──────────────────────────────────────────────────────────────────

def _headers(write: bool = False) -> dict:
    key = (os.environ.get("SUPABASE_SERVICE_KEY") if write
           else os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"))
    return {"apikey": key, "Authorization": f"Bearer {key}"}

def _sb(table: str) -> str:
    return f"{os.environ['SUPABASE_URL']}/rest/v1/{table}"


@st.cache_data(ttl=300)
def load_data() -> tuple[pd.DataFrame, dict]:
    meta_r   = requests.get(_sb("calendar_meta"),    headers=_headers(), params={"id": "eq.1"}).json()
    entries  = requests.get(_sb("calendar_entries"), headers=_headers(),
                            params={"select": "*", "order": "date", "limit": 1000}).json()
    meta = meta_r[0] if isinstance(meta_r, list) and meta_r else {}
    df   = pd.DataFrame(entries if isinstance(entries, list) else [])
    return df, meta


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_mcap(cr) -> str:
    if pd.isna(cr) or cr == 0:
        return "—"
    if cr >= 100_000:
        return f"₹{cr / 100_000:.1f}L Cr"
    if cr >= 1_000:
        return f"₹{cr / 1_000:.1f}K Cr"
    return f"₹{int(cr):,} Cr"

def get_status(d) -> str:
    if pd.isna(d):
        return "—"
    today = datetime.today().date()
    if d == today:   return "Today"
    if d < today:    return "Past"
    return "Upcoming"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        df, meta = load_data()
    except Exception as e:
        st.error(f"Could not connect to Supabase: {e}")
        return

    if df.empty:
        st.info("No data yet — run `python refresh.py` to populate.")
        return

    # Parse + enrich
    df["_date"]  = pd.to_datetime(df["date"], format="%d-%b-%Y", errors="coerce").dt.date
    df["Status"] = df["_date"].apply(get_status)
    df["Date"]   = df["_date"].apply(lambda d: d.strftime("%d %b") if pd.notna(d) else "—")
    df["Mkt Cap"]= df["market_cap_cr"].apply(fmt_mcap)

    quarter    = meta.get("quarter", "")
    updated_at = (meta.get("updated_at") or "")[:16].replace("T", " ")

    n_today    = (df["Status"] == "Today").sum()
    n_upcoming = (df["Status"] == "Upcoming").sum()
    n_past     = (df["Status"] == "Past").sum()

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="app-header">
        <h1>📊 NSE 500 Results Calendar</h1>
        <p class="sub">Last updated {updated_at} IST · Data from NSE India · Highlights by Lokesh Maru</p>
        <span class="quarter-badge">{quarter}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Metric cards ──────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-card card-today">
            <div class="val val-today">{n_today}</div>
            <div class="lbl">🟡 Reporting Today</div>
        </div>
        <div class="metric-card card-upcoming">
            <div class="val val-upcoming">{n_upcoming}</div>
            <div class="lbl">🟢 Upcoming</div>
        </div>
        <div class="metric-card card-past">
            <div class="val val-past">{n_past}</div>
            <div class="lbl">⚫ Already Reported</div>
        </div>
        <div class="metric-card card-total">
            <div class="val val-total">{len(df)}</div>
            <div class="lbl">📋 Total This Season</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Search bar (top of main area) ─────────────────────────────────────────
    search = st.text_input("", placeholder="🔍  Search by company name or NSE symbol…",
                           label_visibility="collapsed")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Filters")
        st.markdown("<hr>", unsafe_allow_html=True)

        status_sel = st.multiselect(
            "Status",
            ["Today", "Upcoming", "Past"],
            default=["Today", "Upcoming", "Past"],
        )

        st.markdown("---")
        sectors = sorted(df["sector"].dropna().unique().tolist())
        sector_sel = st.multiselect("Sector", sectors, placeholder="All sectors")

        st.markdown("---")
        sort_by = st.radio("Sort by", ["Date → Mkt Cap", "Market Cap ↓", "Date ↑"])

        st.markdown("---")
        st.markdown(
            "<small style='color:#9ca3af'>🕗 Morning alerts: 8 AM IST<br>"
            "📩 EOD highlights: 6 PM IST<br>"
            "🤖 Powered by Lokesh Maru</small>",
            unsafe_allow_html=True,
        )

    # ── Filter + sort ─────────────────────────────────────────────────────────
    view = df.copy()
    if search:
        mask = (view["symbol"].str.contains(search, case=False, na=False) |
                view["name"].str.contains(search, case=False, na=False))
        view = view[mask]
    if status_sel:
        view = view[view["Status"].isin(status_sel)]
    if sector_sel:
        view = view[view["sector"].isin(sector_sel)]

    if sort_by == "Market Cap ↓":
        view = view.sort_values("market_cap_cr", ascending=False)
    elif sort_by == "Date ↑":
        view = view.sort_values(["_date", "market_cap_cr"], ascending=[True, False])
    else:  # Date → Mkt Cap (default)
        view = view.sort_values(["_date", "market_cap_cr"], ascending=[True, False])

    st.caption(f"Showing **{len(view)}** of {len(df)} companies")

    # ── Table ─────────────────────────────────────────────────────────────────
    rows_html = ""
    for i, (_, row) in enumerate(view.iterrows(), 1):
        status = row["Status"]
        badge_cls  = {"Today": "badge-today", "Upcoming": "badge-upcoming", "Past": "badge-past"}.get(status, "")
        badge_icon = {"Today": "🟡", "Upcoming": "🟢", "Past": "⚫"}.get(status, "")
        row_cls    = "row-today" if status == "Today" else ("row-even" if i % 2 == 0 else "row-odd")
        rows_html += f"""<tr class="{row_cls}">
            <td class="seq">{i}</td>
            <td class="date-cell">{row['Date']}</td>
            <td class="sym">{row['symbol']}</td>
            <td>{row['name']}</td>
            <td class="sector-cell">{row['sector'] or '—'}</td>
            <td class="mcap-cell">{row['Mkt Cap']}</td>
            <td><span class="badge {badge_cls}">{badge_icon} {status}</span></td>
        </tr>"""

    st.markdown(f"""
    <table class="cal-table">
        <thead><tr>
            <th>#</th><th>Date</th><th>Symbol</th><th>Company</th>
            <th>Sector</th><th>Market Cap</th><th>Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table>""", unsafe_allow_html=True)

    st.markdown(
        "<p style='color:#9ca3af; font-size:0.75rem; margin-top:8px'>"
        "Market cap via yfinance · Board meetings via NSE India · "
        "Telegram alerts active · <a href='?refresh=1' style='color:#6366f1'>Force refresh</a></p>",
        unsafe_allow_html=True,
    )


main()
