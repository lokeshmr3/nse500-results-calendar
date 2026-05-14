# NSE 500 Results Calendar

AI-powered earnings calendar for NSE 500 companies with Telegram alerts and a web dashboard.

## What it does

| Feature | Detail |
|---|---|
| **Calendar** | NSE 500 companies reporting financial results this quarter, sorted by date + market cap |
| **Web dashboard** | Filterable table with status (Today / Upcoming / Past), sector filter, search |
| **Morning alert** | 8:00 AM IST Telegram message: which NSE 500 companies report today |
| **EOD highlights** | 6:00 PM IST Telegram message: 2-line AI summary of each company's results |
| **AI engine** | Claude reads NSE announcement PDFs and extracts key financials automatically |

---

## Setup

### 1. Clone and install

```bash
git clone <your-repo-url>
cd results-calendar
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in:
#   ANTHROPIC_API_KEY  — from console.anthropic.com
#   TELEGRAM_BOT_TOKEN — from @BotFather on Telegram
#   TELEGRAM_CHAT_ID   — send /start to @userinfobot to get your chat ID
```

### 3. Load initial calendar data

```bash
python refresh.py
```

### 4. Run the dashboard locally

```bash
python app.py
# Open http://localhost:5000
```

### 5. Test Telegram alerts

```bash
python morning.py   # sends today's schedule
python eod.py       # sends AI highlights
```

---

## Deploy to Render (free web dashboard)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Web Service → connect your repo
3. Render auto-detects `render.yaml` — click **Apply**
4. In Render dashboard → Environment, add:
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `REFRESH_SECRET` (any random string)
5. Deploy — your dashboard will be live at `https://results-calendar.onrender.com`

> **Note:** Render free tier sleeps after 15 min of inactivity. The first visit after sleep takes ~30s to wake up.

---

## GitHub Actions (automated scheduling — free)

Add these **Secrets** in your GitHub repo → Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic key |
| `TELEGRAM_BOT_TOKEN` | Your bot token |
| `TELEGRAM_CHAT_ID` | Your chat ID |

Three workflows run automatically:

| Workflow | Schedule | What it does |
|---|---|---|
| `refresh.yml` | 6:00 AM IST daily | Fetches latest NSE board meetings & market caps |
| `morning.yml` | 8:00 AM IST Mon–Fri | Sends today's results schedule to Telegram |
| `eod.yml` | 6:00 PM IST Mon–Fri | AI-generates highlights and sends to Telegram |

You can also trigger any workflow manually via GitHub → Actions → Run workflow.

---

## Project structure

```
results-calendar/
├── fetcher.py          NSE API wrapper (board meetings, NSE500 list, market cap)
├── processor.py        Calendar builder and query helpers
├── ai_engine.py        Claude API — PDF parsing + highlight generation
├── notifier.py         Telegram message sender
├── app.py              Flask web dashboard
├── morning.py          Morning alert runner
├── eod.py              EOD highlights runner
├── refresh.py          Calendar data refresher
├── templates/index.html  Dashboard HTML
├── static/style.css
├── data/               Auto-created cache directory
│   ├── calendar.json
│   └── mcap_cache.json
└── .github/workflows/  GitHub Actions
    ├── refresh.yml
    ├── morning.yml
    └── eod.yml
```

---

## How the AI highlights work

1. Identifies NSE 500 companies that reported results today
2. Fetches the NSE corporate announcement (PDF) for each company
3. Extracts text from the first 8 pages of the PDF using `pdfplumber`
4. Sends the text to Claude (claude-sonnet-4-6) with a prompt to extract:
   - Revenue / Net Sales with YoY %
   - Net Profit / PAT with YoY %
   - One strategic highlight or management comment
5. Formats into 2 concise lines and sends to Telegram

---

## Customisation

- **Change notification times**: Edit the `cron:` lines in `.github/workflows/morning.yml` and `eod.yml`
- **Change the universe**: Swap NSE500 CSV URL in `fetcher.py → fetch_nse500()` for NIFTY50, NIFTY200, etc.
- **Add more columns** to the dashboard: Edit `templates/index.html` and `processor.py → _enrich_for_ui()`
