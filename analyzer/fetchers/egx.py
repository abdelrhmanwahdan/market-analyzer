"""Egyptian Stock Market fetcher — yfinance with .CA (Cairo) tickers."""

import logging
from datetime import datetime, timezone

import yfinance as yf

from config import EGX33_STOCKS

log = logging.getLogger(__name__)


def _df_to_ohlcv(df) -> list[dict]:
    rows = []
    for ts, row in df.iterrows():
        try:
            rows.append({
                "ts": int(ts.timestamp() * 1000),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume", 0) or 0),
            })
        except Exception:
            continue
    return rows


def fetch() -> dict | None:
    from indicators.technical import calculate_indicators_from_ohlcv

    assets = []
    errors = []

    # EGX market hours: Sun-Thu 10:00-14:30 EET (UTC+2)
    weekday = datetime.now().weekday()  # 0=Mon, 6=Sun
    market_open = weekday in (6, 0, 1, 2, 3)  # Sun, Mon, Tue, Wed, Thu

    # Batch download all EGX tickers at once (much faster than one-by-one)
    ca_tickers = [f"{s}.CA" for s in EGX33_STOCKS]
    try:
        raw = yf.download(
            ca_tickers, period="1y", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False,
        )
    except Exception as e:
        log.error("EGX batch download failed: %s", e)
        raw = None

    for symbol in EGX33_STOCKS:
        ticker = f"{symbol}.CA"
        try:
            if raw is None or raw.empty:
                errors.append(f"{symbol}: batch download failed")
                continue

            # Extract per-ticker DataFrame
            try:
                df = raw[ticker] if len(ca_tickers) > 1 else raw
            except KeyError:
                errors.append(f"{symbol}: not in batch result")
                continue

            if df is None or df.empty:
                errors.append(f"{symbol}: no data")
                continue

            # Flatten MultiIndex columns if present
            if hasattr(df.columns, "levels"):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

            df = df.dropna()
            ohlcv = _df_to_ohlcv(df)

            if len(ohlcv) < 20:
                errors.append(f"{symbol}: insufficient data ({len(ohlcv)} bars)")
                continue

            indicators = calculate_indicators_from_ohlcv(ohlcv)
            price = ohlcv[-1]["close"]
            price_prev = ohlcv[-2]["close"] if len(ohlcv) >= 2 else price

            assets.append({
                "symbol": symbol,
                "name": _EGX_NAMES.get(symbol, symbol),
                "sector": _EGX_SECTORS.get(symbol, "Unknown"),
                "price_egp": price,
                "change_daily": round((price - price_prev) / price_prev * 100, 2) if price_prev else 0,
                "shariah_compliant": True,
                "timeframes": {
                    "daily": {
                        "ohlcv": ohlcv[-60:],
                        "indicators": indicators,
                    }
                },
            })

        except Exception as e:
            errors.append(f"{symbol}: {e}")
            log.warning("EGX fetch error for %s: %s", symbol, e)

    return {
        "market": "egx",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_open": market_open,
        "market_hours": "Sun-Thu 10:00-14:30 EET",
        "assets": assets,
        "errors": errors,
    }


_EGX_NAMES = {
    "SWDY": "El Sewedy Electric", "TMGH": "TMG Holding", "ETEL": "Telecom Egypt",
    "PHDC": "Palm Hills Development", "ABUK": "Abu Qir Fertilizers",
    "ORWE": "Oriental Weavers", "MNHD": "Madinet Nasr Housing", "JUFO": "Juhayna Food",
    "OCDI": "SODIC", "SKPC": "Sidi Kerir Petrochem", "GBCO": "GB Auto",
    "GTHE": "Egyptian Transport", "RAYA": "Raya Holding", "CLHO": "Cleopatra Hospital",
    "ISPH": "Ibnsina Pharma", "FWRY": "Fawry", "EGCH": "Egypt Gas",
    "MFPC": "Misr Fertilizers", "EGAL": "Egypt Aluminum", "AMOC": "Alex Mineral Oils",
    "ACGC": "Arab Cotton Ginning", "ORAS": "Orascom Construction",
    "ORHD": "Orascom Hotels", "EMFD": "Emaar Misr", "EDFO": "Edita Food",
    "OBOR": "Obour Land", "MMGR": "MM Group", "RACC": "Raya Contact Center",
    "TALM": "Taaleem Management", "AIIB": "Abu Dhabi Islamic Bank EGY",
    "FAIT": "Faisal Islamic Bank EGP", "FAIS": "Faisal Islamic Bank USD",
    "BAOB": "Al Baraka Bank", "GEMM": "Al Ezz Ceramics",
}

_EGX_SECTORS = {
    "SWDY": "Industrials", "TMGH": "Real Estate", "ETEL": "Telecom",
    "PHDC": "Real Estate", "ABUK": "Materials", "ORWE": "Consumer",
    "MNHD": "Real Estate", "JUFO": "Consumer Staples", "OCDI": "Real Estate",
    "SKPC": "Energy", "GBCO": "Consumer", "GTHE": "Transport",
    "RAYA": "Technology", "CLHO": "Healthcare", "ISPH": "Healthcare",
    "FWRY": "Fintech", "EGCH": "Energy", "MFPC": "Materials",
    "EGAL": "Materials", "AMOC": "Energy", "ACGC": "Industrials",
    "ORAS": "Industrials", "ORHD": "Tourism", "EMFD": "Real Estate",
    "EDFO": "Consumer Staples", "OBOR": "Consumer Staples", "MMGR": "Industrial Services",
    "RACC": "Technology", "TALM": "Education", "AIIB": "Islamic Banking",
    "FAIT": "Islamic Banking", "FAIS": "Islamic Banking", "BAOB": "Islamic Banking",
    "GEMM": "Materials",
}
