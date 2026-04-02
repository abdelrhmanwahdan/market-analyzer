# Market Intelligence Dashboard — Workflow Guide

## One-Time Setup

### 1. Python Environment

```bash
cd /home/wahdan/work/investor_strategy/market-analyzer/analyzer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Files

`analyzer/.env` — already configured with your credentials. Verify it exists:

```bash
cat analyzer/.env
# Should show: SUPABASE_URL, SUPABASE_SERVICE_KEY, ALPHA_VANTAGE_API_KEY, NEWS_API_KEY
```

`app/.env.local` — already configured. Verify it exists:

```bash
cat app/.env.local
# Should show: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
```

### 3. Supabase Database

Run your SQL migrations in the Supabase dashboard (SQL Editor) once:
- All tables, views, and functions must be created before first use
- The dashboard URL: https://supabase.com/dashboard/project/zjrrjhlceblvdpmpybek

### 4. Next.js App Dependencies

```bash
cd /home/wahdan/work/investor_strategy/market-analyzer/app
npm install
```

---

## Daily Workflow

### Step 1 — Fetch Market Data

```bash
cd /home/wahdan/work/investor_strategy/market-analyzer/analyzer
source venv/bin/activate
python main.py --fetch
```

Takes ~15 seconds. Output is saved to `output/latest_data.json`.

You'll see a summary like:
```
✓ Data fetched successfully → output/latest_data.json
  Markets fetched: crypto, gold_silver, us_market, egx, whale, news
```

### Step 2 — Analyze with Claude Code

In this Claude Code session, run:

```
analyze my latest market data
```

Claude Code will:
1. Read `ANALYSIS_INSTRUCTIONS.md`
2. Read `output/latest_data.json`
3. Produce `output/signals.json` with BUY signals, market analysis, and risk notes

### Step 3 — Store Signals to Supabase

```bash
python main.py --store-signals output/signals.json
```

This saves the analysis and all BUY signals to your Supabase database.

### Step 4 — Update PNL on Open Positions

```bash
python main.py --update-pnl
```

This fetches current prices for all open signals and records snapshots.

### All-in-One (Steps 1 + 3 + 4)

```bash
python main.py --fetch --store-signals output/signals.json --update-pnl
```

---

## View the Dashboard

### Start the dev server

```bash
cd /home/wahdan/work/investor_strategy/market-analyzer/app
npm run dev
```

Open: **http://localhost:3000**

### Pages

| URL | What you see |
|-----|--------------|
| `/` | Overview — latest analysis, active signals, performance summary |
| `/crypto` | Crypto prices, indicators, whale activity |
| `/commodities` | Gold & Silver (USD + EGP prices), indicators |
| `/us-market` | SPUS Shariah-compliant US stocks |
| `/egx` | Egyptian Exchange (EGX33) stocks |
| `/signals` | All BUY signals — active and closed |
| `/performance` | PNL charts, equity curve, monthly breakdown |

---

## Quick Reference

### Fetch only (no analysis)
```bash
python main.py --fetch
```

### Update PNL only (fast, no fetch)
```bash
python main.py --update-pnl
```

### Store a specific signals file
```bash
python main.py --store-signals output/signals.json
```

### Check the raw data
```bash
cat output/latest_data.json | python3 -m json.tool | head -100
```

---

## File Locations

```
market-analyzer/
├── analyzer/                  # Python data fetcher
│   ├── main.py                # CLI entry point
│   ├── .env                   # Your API keys (gitignored)
│   ├── output/
│   │   ├── latest_data.json   # Raw market data (Step 1 output)
│   │   └── signals.json       # Claude's analysis (Step 2 output)
│   ├── fetchers/              # Per-market data fetchers
│   ├── indicators/            # Technical indicator calculations
│   ├── pnl/                   # PNL tracker
│   └── db/                    # Supabase client
├── app/                       # Next.js dashboard
│   ├── .env.local             # Supabase public keys (gitignored)
│   └── src/app/               # Pages (crypto, egx, signals, etc.)
├── ANALYSIS_INSTRUCTIONS.md   # Claude's analysis prompt
└── steps.md                   # This file
```

---

## Troubleshooting

**`No module named 'supabase'`**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Dashboard shows no data**
- Make sure you've run `--store-signals` at least once
- Check Supabase dashboard for rows in `analyses` and `signals` tables

**EGX stocks showing 0 assets**
- Normal for 9 tickers not covered by Yahoo Finance
- 25/34 EGX33 stocks are available and will show up

**Fetch takes more than 2 minutes**
- Yahoo Finance rate limit hit — wait 5 minutes and retry
- The fetchers are serialized to reduce this, but heavy usage can still trigger it
