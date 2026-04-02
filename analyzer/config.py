"""Central configuration for the market analyzer."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# ── Optional news APIs (free tiers) ──────────────────────────────────────────
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ── Crypto assets to track ────────────────────────────────────────────────────
CRYPTO_TIER1 = ["BTC", "ETH", "SOL", "BNB", "XRP"]
CRYPTO_TIER2 = ["ADA", "AVAX", "DOGE", "DOT", "LINK", "ATOM", "UNI", "LTC", "NEAR"]
CRYPTO_TIER3 = ["FIL", "APT", "SUI", "INJ", "SEI", "TIA", "RNDR", "FET", "AR", "OP", "ARB", "STX", "AAVE"]

CRYPTO_ALL = CRYPTO_TIER1 + CRYPTO_TIER2 + CRYPTO_TIER3

# ── US Shariah-compliant stocks (SPUS universe) ───────────────────────────────
SPUS_STOCKS = [
    # Mega-caps (always track)
    "NVDA", "AAPL", "MSFT", "GOOGL", "AVGO", "TSLA",
    # Healthcare
    "LLY", "UNH", "ABBV", "TMO", "MRK", "PFE",
    # Consumer
    "HD", "COST", "PEP", "KO", "MCD",
    # Energy
    "XOM", "CVX", "COP",
    # Tech extended
    "AMD", "ADBE", "CRM", "QCOM", "INTC",
    # Industrial
    "CAT", "HON", "UPS",
]

# ── EGX33 Shariah Index stocks ────────────────────────────────────────────────
EGX33_STOCKS = [
    "SWDY", "TMGH", "ETEL", "PHDC", "ABUK", "ORWE", "MNHD", "JUFO",
    "OCDI", "SKPC", "GBCO", "GTHE", "RAYA", "CLHO", "ISPH", "FWRY",
    "EGCH", "MFPC", "EGAL", "AMOC", "ACGC", "ORAS", "ORHD", "EMFD",
    "EDFO", "OBOR", "MMGR", "RACC", "TALM", "AIIB", "FAIT", "FAIS",
    "BAOB", "GEMM",
]

# ── Timeframes ────────────────────────────────────────────────────────────────
# Binance intervals
BINANCE_DAILY = "1d"
BINANCE_WEEKLY = "1w"

# yfinance periods
YF_DAILY_PERIOD = "6mo"
YF_WEEKLY_PERIOD = "2y"
YF_DAILY_INTERVAL = "1d"
YF_WEEKLY_INTERVAL = "1wk"

# egxpy intervals
EGX_DAILY = "Daily"
EGX_WEEKLY = "Weekly"
EGX_BARS = 120  # enough for indicators

# ── Output paths ──────────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
LATEST_DATA_PATH = os.path.join(OUTPUT_DIR, "latest_data.json")

# ── Indicators lookback ───────────────────────────────────────────────────────
DAILY_BARS = 200   # enough for EMA200
WEEKLY_BARS = 104  # 2 years of weekly bars
