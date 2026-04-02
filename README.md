# Market Intelligence Dashboard

A local-first, AI-powered investment dashboard for multi-market analysis.

**Claude Code is the AI engine.** No paid AI API calls. No GitHub Actions.
Python fetches data → Claude Code reads it and outputs signals → Next.js displays everything.

---

## Architecture

```
analyzer/          Python CLI — fetches market data, stores to Supabase, tracks PNL
app/               Next.js dashboard — deployed to Vercel, reads from Supabase
supabase/          Database migrations
```

### Daily Workflow

```
1. python main.py --fetch             # Fetch all market data → output/latest_data.json
2. claude                             # Open Claude Code in analyzer/
3. (Claude reads latest_data.json + ANALYSIS_INSTRUCTIONS.md → outputs output/signals.json)
4. python main.py --store-signals output/signals.json   # Write signals to Supabase
5. python main.py --update-pnl        # Update PNL for all active signals
```

---

## Setup

### 1. Supabase

1. Create a free project at [supabase.com](https://supabase.com)
2. Run the migration in the SQL editor:

```bash
# Copy contents of supabase/migrations/001_initial.sql → paste into Supabase SQL Editor → Run
```

3. Get your keys from **Settings → API**:
   - `URL` → `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`
   - `anon public` key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_KEY` (keep secret — never commit)

### 2. Python Analyzer

```bash
cd analyzer
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in .env:
#   SUPABASE_URL=https://YOUR_PROJECT.supabase.co
#   SUPABASE_SERVICE_KEY=eyJ...
#   ALPHA_VANTAGE_API_KEY=        # Optional — free tier (25 req/day)
#   NEWS_API_KEY=                 # Optional — free tier (100 req/day)
```

### 3. Next.js App (local dev)

```bash
cd app
npm install

cp .env.local.example .env.local
# Fill in .env.local:
#   NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...

npm run dev
```

---

## Python CLI Reference

```bash
# Fetch all market data and save to output/latest_data.json
python main.py --fetch

# Store signals from a JSON file into Supabase
python main.py --store-signals output/signals.json

# Update PNL for all active BUY signals
python main.py --update-pnl
```

### What `--fetch` collects

| Market | Source | Data |
|--------|--------|------|
| Crypto (BTC, ETH, SOL, …) | Binance + CoinGecko | Daily + weekly OHLCV, market cap, fear & greed |
| Gold & Silver | yfinance (GC=F, SI=F) | Daily + weekly OHLCV, USD/EGP rate |
| US Stocks (SPUS universe) | yfinance | Daily + weekly, 28 Shariah-compliant tickers |
| EGX (Egyptian Exchange) | egxpy | EGX33 Shariah Index, 34 tickers |
| DeFi | DeFiLlama | TVL, stablecoin supply, protocol flows |
| News | Alpha Vantage + NewsAPI | Sentiment, headlines |

All technical indicators (RSI, MACD, EMA, Bollinger Bands, ADX, ATR, OBV, volatility score) are computed locally with pandas-ta.

---

## Claude Code Analysis

After running `--fetch`, open Claude Code in the `analyzer/` directory:

```bash
cd analyzer
claude
```

Then say: **"Read output/latest_data.json and follow the ANALYSIS_INSTRUCTIONS.md to produce signals."**

Claude will:
1. Read `output/latest_data.json` (all fetched market data)
2. Read `ANALYSIS_INSTRUCTIONS.md` (full analysis framework)
3. Optionally do web searches for news/context
4. Output `output/signals.json` with structured BUY/SELL/HOLD signals

### Signal JSON format

```json
[
  {
    "type": "BUY",
    "asset": "BTC",
    "asset_name": "Bitcoin",
    "market": "crypto",
    "shariah_status": "COMPLIANT",
    "current_price": 65000,
    "entry_zone_low": 63000,
    "entry_zone_high": 65500,
    "stop_loss": 59000,
    "take_profit_1": 72000,
    "take_profit_2": 78000,
    "take_profit_3": 85000,
    "confidence": "HIGH",
    "timeframe": "SWING",
    "risk_reward_ratio": 2.8,
    "position_size_pct": 6,
    "position_size_usd": 180,
    "reasoning": "...",
    "urgency": "TODAY",
    "volatility_score": 7,
    "volume_ratio": 1.8,
    "volume_confirms_price": true
  }
]
```

---

## Performance Tracking

Every BUY signal is tracked automatically via `--update-pnl`:

- Fetches current price (Binance / yfinance / egxpy)
- Saves a `signal_snapshot` to Supabase
- Closes the signal if SL or TP is hit
- Dashboard `/performance` shows: win rate, total PNL, Sharpe ratio, equity curve, monthly PNL

Run `--update-pnl` regularly (e.g., after market close each day):

```bash
python main.py --update-pnl
```

---

## Markets Covered

| Market | Universe | Shariah |
|--------|----------|---------|
| Crypto | BTC, ETH, SOL, BNB, XRP + 25 more | All halal (no USDT interest products) |
| Gold | GC=F (spot), GLD (ETF) | Always halal |
| Silver | SI=F (spot), SLV (ETF) | Always halal |
| US Stocks | SPUS 28 holdings + SPY/QQQ reference | SPUS-only (S&P 500 Shariah) |
| Egypt EGX | EGX33 Shariah Index (34 stocks) | EGX33-only |

---

## Deploy to Vercel

The `app/` directory is a standalone Next.js app:

1. Push to GitHub
2. Import into [vercel.com](https://vercel.com) — set root directory to `app/`
3. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Deploy

The dashboard is read-only (anon key). RLS policies ensure no writes from the frontend.

---

## Dashboard Pages

| Page | URL | Description |
|------|-----|-------------|
| Overview | `/` | Active signals, fear & greed gauge, market overview |
| Crypto | `/crypto` | Tier 1-3 coins, whale activity |
| Commodities | `/commodities` | Gold & silver with EGP prices |
| US Market | `/us-market` | SPUS holdings performance |
| EGX | `/egx` | Egyptian Exchange EGX33 stocks |
| Portfolio | `/portfolio` | Open and closed positions tracker |
| Performance | `/performance` | Win rate, PNL, equity curve, Sharpe ratio |
| History | `/history` | Signal archive and analysis runs |

---

## API Rate Limits (free tiers)

| API | Limit | Used for |
|-----|-------|---------|
| Binance | Generous (no key needed) | Crypto OHLCV |
| CoinGecko | 30 req/min (no key) | Market caps, sparklines |
| yfinance | Unofficial, generous | Stocks, gold, silver |
| Alpha Vantage | 25 req/day | News sentiment |
| NewsAPI | 100 req/day | Headlines |
| DeFiLlama | No limit | DeFi TVL data |

---

## No Paid Services Required

- No Anthropic API key (Claude Code runs locally)
- No GitHub Actions (analysis is manual via Claude Code CLI)
- No paid data providers (all free APIs)
- Supabase free tier: 500MB DB, 2GB bandwidth, sufficient for this workload
