"""US Shariah-compliant stock fetcher — yfinance daily + weekly (SPUS universe only)."""

import logging
from datetime import datetime, timezone

import yfinance as yf

from config import SPUS_STOCKS

log = logging.getLogger(__name__)


def _df_to_ohlcv(df) -> list[dict]:
    rows = []
    for ts, row in df.iterrows():
        rows.append({
            "ts": int(ts.timestamp() * 1000),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row.get("Volume", 0) or 0),
        })
    return rows


def fetch() -> dict | None:
    """Fetch US Shariah-compliant stocks (SPUS universe) — daily + weekly."""
    from indicators.technical import calculate_indicators_from_ohlcv

    assets = []

    try:
        # ── Download index ETFs for context (not for trading) ────────────────
        index_tickers = ["SPY", "QQQ", "SPUS"]
        stock_tickers = SPUS_STOCKS

        all_tickers = index_tickers + stock_tickers

        daily_raw_all = yf.download(
            all_tickers, period="6mo", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False,
        )
        weekly_raw_all = yf.download(
            all_tickers, period="3y", interval="1wk",
            group_by="ticker", auto_adjust=True, progress=False,
        )

        def get_df(data, ticker):
            try:
                df = data[ticker] if len(all_tickers) > 1 else data
                if df is None or df.empty:
                    return None
                # Flatten MultiIndex columns if present (yfinance ≥0.2.50)
                if hasattr(df.columns, "levels"):
                    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                return df.dropna()
            except Exception:
                return None

        for ticker in stock_tickers + index_tickers:
            df_d = get_df(daily_raw_all, ticker)
            if df_d is None or len(df_d) < 20:
                continue

            daily_ohlcv = _df_to_ohlcv(df_d)
            daily_ind = calculate_indicators_from_ohlcv(daily_ohlcv)

            price = daily_ohlcv[-1]["close"]
            price_prev = daily_ohlcv[-2]["close"] if len(daily_ohlcv) >= 2 else price
            change_24h = round((price - price_prev) / price_prev * 100, 2)

            is_index = ticker in index_tickers
            asset = {
                "symbol": ticker,
                "name": _NAMES.get(ticker, ticker),
                "price": price,
                "change_24h": change_24h,
                "shariah_compliant": not is_index,  # Index ETFs are for reference only
                "is_index": is_index,
                "timeframes": {
                    "daily": {
                        "ohlcv": daily_ohlcv[-60:],
                        "indicators": daily_ind,
                    }
                },
            }

            df_w = get_df(weekly_raw_all, ticker)
            if df_w is not None and len(df_w) >= 10:
                weekly_ohlcv = _df_to_ohlcv(df_w)
                weekly_ind = calculate_indicators_from_ohlcv(weekly_ohlcv)
                asset["timeframes"]["weekly"] = {
                    "ohlcv": weekly_ohlcv[-52:],
                    "indicators": weekly_ind,
                }

            assets.append(asset)

    except Exception as e:
        log.error("US market fetch error: %s", e)
        return None

    return {
        "market": "us_market",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
    }


_NAMES = {
    "NVDA": "NVIDIA", "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AVGO": "Broadcom", "TSLA": "Tesla", "LLY": "Eli Lilly", "UNH": "UnitedHealth",
    "ABBV": "AbbVie", "TMO": "Thermo Fisher", "MRK": "Merck", "PFE": "Pfizer",
    "HD": "Home Depot", "COST": "Costco", "PEP": "PepsiCo", "KO": "Coca-Cola",
    "MCD": "McDonald's", "XOM": "ExxonMobil", "CVX": "Chevron", "COP": "ConocoPhillips",
    "AMD": "AMD", "ADBE": "Adobe", "CRM": "Salesforce", "QCOM": "Qualcomm",
    "INTC": "Intel", "CAT": "Caterpillar", "HON": "Honeywell", "UPS": "UPS",
    "SPY": "S&P 500 ETF (reference)", "QQQ": "Nasdaq 100 ETF (reference)",
    "SPUS": "SPUS Shariah ETF",
}
