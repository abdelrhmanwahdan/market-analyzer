"""Gold & Silver fetcher — yfinance daily + weekly OHLCV."""

import logging
from datetime import datetime, timezone

import requests
import yfinance as yf

log = logging.getLogger(__name__)

TROY_OZ_TO_GRAM = 31.1035  # 1 troy oz = 31.1035 grams


def _fetch_egypt_local_prices() -> dict | None:
    """Fetch Egypt local gold & silver prices (EGP per gram).

    Tries goldprice.org first (two endpoints), then metals.live as fallback.
    Returns None if all attempts fail — caller will use calculated fair price.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://goldprice.org/",
        "Origin": "https://goldprice.org",
        "Accept": "application/json, text/plain, */*",
    }

    # Attempt 1: goldprice.org primary endpoint
    for url in [
        "https://data-asg.goldprice.org/dbXRates/EGP",
        "https://data-asg.goldprice.org/GetData/EGP/1",
    ]:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                # dbXRates format
                if "items" in data:
                    item = data["items"][0]
                    return {
                        "gold_egp_per_gram": round(item["xauPrice"] / TROY_OZ_TO_GRAM, 2),
                        "silver_egp_per_gram": round(item["xagPrice"] / TROY_OZ_TO_GRAM, 2),
                    }
                # GetData format: list of [ts, price] pairs
                if isinstance(data, list) and data:
                    gold_oz = float(data[0][1])
                    silver_oz = float(data[1][1]) if len(data) > 1 else None
                    result = {"gold_egp_per_gram": round(gold_oz / TROY_OZ_TO_GRAM, 2)}
                    if silver_oz:
                        result["silver_egp_per_gram"] = round(silver_oz / TROY_OZ_TO_GRAM, 2)
                    return result
        except Exception as e:
            log.debug("goldprice.org %s failed: %s", url, e)

    log.warning("Egypt local gold price fetch failed: all endpoints returned empty or errored")
    return None


def _download(tickers: list[str], period: str, interval: str) -> dict:
    """Batch download via yfinance; returns {ticker: DataFrame}."""
    try:
        raw = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return {}
    except Exception as e:
        log.warning("yfinance download failed (%s %s): %s", period, interval, e)
        return {}

    result = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw.copy()
            elif ticker in raw.columns.get_level_values(0):
                # Old format: outer level = ticker
                df = raw[ticker]
            elif ticker in raw.columns.get_level_values(-1):
                # New format (yfinance ≥0.2.50): outer level = field, inner = ticker
                df = raw.xs(ticker, level=-1, axis=1)
            else:
                continue
            # Flatten any remaining MultiIndex
            if hasattr(df.columns, "levels"):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.dropna()
            if not df.empty:
                result[ticker] = df
        except Exception as e:
            log.warning("column extract failed for %s: %s", ticker, e)
    return result


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
    """Fetch gold and silver market data (daily + weekly)."""
    from indicators.technical import calculate_indicators_from_ohlcv

    assets = []
    usd_egp = None

    try:
        # ── Egypt local gold/silver prices ───────────────────────────────────
        egypt_prices = _fetch_egypt_local_prices()

        # ── USD/EGP exchange rate ────────────────────────────────────────────
        egp_data = _download(["USDEGP=X"], "1mo", "1d")
        if "USDEGP=X" in egp_data and not egp_data["USDEGP=X"].empty:
            df_egp = egp_data["USDEGP=X"].dropna()
            if not df_egp.empty:
                usd_egp = float(df_egp["Close"].iloc[-1])

        symbols = {
            "GC=F": {"name": "Gold Futures", "symbol_out": "GOLD"},
            "SI=F": {"name": "Silver Futures", "symbol_out": "SILVER"},
            "GLD": {"name": "SPDR Gold ETF", "symbol_out": "GLD"},
            "SLV": {"name": "iShares Silver ETF", "symbol_out": "SLV"},
        }

        daily_data = _download(list(symbols.keys()), "6mo", "1d")
        weekly_data = _download(list(symbols.keys()), "3y", "1wk")

        for ticker, meta in symbols.items():
            df_d = daily_data.get(ticker)
            if df_d is None or df_d.empty:
                log.warning("No daily data for %s", ticker)
                continue

            df_d = df_d.dropna()
            daily_raw = _df_to_ohlcv(df_d)
            if len(daily_raw) < 20:
                continue

            daily_ind = calculate_indicators_from_ohlcv(daily_raw)
            price = daily_raw[-1]["close"]
            price_prev = daily_raw[-2]["close"] if len(daily_raw) >= 2 else price
            change_24h = round((price - price_prev) / price_prev * 100, 2)

            # Per-gram 24k calculations
            price_per_gram_usd = round(price / TROY_OZ_TO_GRAM, 4)
            price_per_gram_egp = round(price_per_gram_usd * usd_egp, 2) if usd_egp else None

            # Egypt local price (from live fetch, or fall back to calculated)
            is_gold = meta["symbol_out"] == "GOLD"
            is_silver = meta["symbol_out"] == "SILVER"
            if egypt_prices and is_gold:
                egypt_local_per_gram = egypt_prices["gold_egp_per_gram"]
            elif egypt_prices and is_silver:
                egypt_local_per_gram = egypt_prices["silver_egp_per_gram"]
            else:
                egypt_local_per_gram = price_per_gram_egp  # fallback to calculated

            asset: dict = {
                "symbol": meta["symbol_out"],
                "ticker": ticker,
                "name": meta["name"],
                "price_usd": price,
                "price_egp": round(price * usd_egp, 2) if usd_egp else None,
                "price_per_gram_usd": price_per_gram_usd,
                "price_per_gram_egp_fair": price_per_gram_egp,
                "egypt_local_per_gram": egypt_local_per_gram,
                "change_24h": change_24h,
                "timeframes": {
                    "daily": {
                        "ohlcv": daily_raw[-60:],
                        "indicators": daily_ind,
                    }
                },
            }

            df_w = weekly_data.get(ticker)
            if df_w is not None and not df_w.empty:
                df_w = df_w.dropna()
                weekly_raw = _df_to_ohlcv(df_w)
                if len(weekly_raw) >= 10:
                    weekly_ind = calculate_indicators_from_ohlcv(weekly_raw)
                    asset["timeframes"]["weekly"] = {
                        "ohlcv": weekly_raw[-52:],
                        "indicators": weekly_ind,
                    }

            assets.append(asset)

    except Exception as e:
        log.error("Gold/silver fetch error: %s", e)
        return None

    return {
        "market": "commodities",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "usd_egp": usd_egp,
        "assets": assets,
    }
