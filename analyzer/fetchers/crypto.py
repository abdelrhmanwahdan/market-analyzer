"""Crypto market fetcher — yfinance (OHLCV) + CoinGecko (meta) + Fear & Greed."""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
import yfinance as yf

from config import CRYPTO_TIER1, CRYPTO_TIER2, CRYPTO_TIER3, DAILY_BARS, WEEKLY_BARS

log = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=30"

CRYPTO_ALL = CRYPTO_TIER1 + CRYPTO_TIER2 + CRYPTO_TIER3

_CG_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB",
    "XRP": "XRP", "ADA": "Cardano", "AVAX": "Avalanche", "DOGE": "Dogecoin",
    "DOT": "Polkadot", "LINK": "Chainlink", "ATOM": "Cosmos", "UNI": "Uniswap",
    "LTC": "Litecoin", "NEAR": "NEAR Protocol", "FIL": "Filecoin", "APT": "Aptos",
    "SUI": "Sui", "INJ": "Injective", "SEI": "Sei", "TIA": "Celestia",
    "RNDR": "Render", "FET": "Fetch.ai", "AR": "Arweave", "OP": "Optimism",
    "ARB": "Arbitrum", "STX": "Stacks", "AAVE": "Aave",
}


async def _get(session: aiohttp.ClientSession, url: str, params: dict | None = None) -> dict | list | None:
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                return await r.json()
            log.warning("GET %s → %s", url, r.status)
    except Exception as e:
        log.warning("GET %s failed: %s", url, e)
    return None


async def _fetch_fear_greed(session: aiohttp.ClientSession) -> dict:
    data = await _get(session, FEAR_GREED_URL)
    if data and data.get("data"):
        latest = data["data"][0]
        history = [{"value": int(d["value"]), "ts": int(d["timestamp"])} for d in data["data"]]
        return {"value": int(latest["value"]), "label": latest["value_classification"], "history": history}
    return {"value": 50, "label": "Neutral", "history": []}


async def _fetch_cg_markets(session: aiohttp.ClientSession) -> dict:
    """Map symbol → {market_cap, change_7d, sparkline} from CoinGecko."""
    data = await _get(session, f"{COINGECKO_BASE}/coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": "true",
        "price_change_percentage": "7d",
    })
    if not data:
        return {}
    result = {}
    for coin in data:
        sym = coin.get("symbol", "").upper()
        result[sym] = {
            "market_cap": coin.get("market_cap"),
            "change_7d": coin.get("price_change_percentage_7d_in_currency"),
            "sparkline": coin.get("sparkline_in_7d", {}).get("price", []),
        }
    return result


def _yf_ticker(sym: str) -> str:
    return f"{sym}-USD"


def _download_ohlcv() -> tuple[dict, dict]:
    """Batch download daily + weekly OHLCV for all crypto via yfinance (no geo-block)."""
    all_tickers = [_yf_ticker(s) for s in CRYPTO_ALL]
    tier1_tickers = [_yf_ticker(s) for s in CRYPTO_TIER1]

    def _extract(raw, symbols: list[str]) -> dict:
        if raw is None or raw.empty:
            return {}
        result = {}
        for sym in symbols:
            ticker = _yf_ticker(sym)
            try:
                if len([_yf_ticker(s) for s in symbols]) == 1:
                    df = raw.copy()
                elif hasattr(raw.columns, "levels"):
                    outer = raw.columns.get_level_values(0).unique().tolist()
                    inner = raw.columns.get_level_values(-1).unique().tolist()
                    if ticker in outer:
                        df = raw[ticker]
                    elif ticker in inner:
                        df = raw.xs(ticker, level=-1, axis=1)
                    else:
                        continue
                else:
                    if ticker not in raw.columns:
                        continue
                    df = raw[ticker]

                if hasattr(df.columns, "levels"):
                    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                df = df.dropna()
                if not df.empty:
                    result[sym] = df
            except Exception as e:
                log.warning("yfinance column extract failed for %s: %s", sym, e)
        return result

    # Daily — 1 year covers DAILY_BARS (200) comfortably
    daily_raw = yf.download(all_tickers, period="1y", interval="1d", auto_adjust=True, progress=False)
    daily_data = _extract(daily_raw, CRYPTO_ALL)

    # Weekly — only Tier 1
    weekly_raw = yf.download(tier1_tickers, period="3y", interval="1wk", auto_adjust=True, progress=False)
    weekly_data = _extract(weekly_raw, CRYPTO_TIER1)

    return daily_data, weekly_data


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


async def fetch_meta() -> dict:
    """Fetch CoinGecko meta + Fear & Greed (async, no geo-block, fast).

    Call this concurrently with other async tasks.
    Then call build_result(meta, daily_data, weekly_data) after yfinance downloads.
    """
    async with aiohttp.ClientSession() as session:
        fear_greed, cg_data = await asyncio.gather(
            _fetch_fear_greed(session),
            _fetch_cg_markets(session),
        )
    return {"fear_greed": fear_greed, "cg_data": cg_data}


def fetch_ohlcv() -> tuple[dict, dict]:
    """Download crypto OHLCV via yfinance (sync).

    Call this from the sequential yfinance thread in main.py to avoid
    rate-limit conflicts with gold/silver/EGX downloads.
    """
    return _download_ohlcv()


def build_result(meta: dict, daily_data: dict, weekly_data: dict) -> dict:
    """Combine CoinGecko meta with yfinance OHLCV into the final crypto dict."""
    from indicators.technical import calculate_indicators_from_ohlcv

    fear_greed = meta.get("fear_greed", {"value": 50, "label": "Neutral", "history": []})
    cg_data = meta.get("cg_data", {})
    assets = []
    errors = []

    for tier, symbols in [(1, CRYPTO_TIER1), (2, CRYPTO_TIER2), (3, CRYPTO_TIER3)]:
        for sym in symbols:
            try:
                df_d = daily_data.get(sym)
                if df_d is None or df_d.empty:
                    log.warning("No daily data for %s", sym)
                    errors.append(f"{sym}: no data")
                    continue

                daily_raw = _df_to_ohlcv(df_d)
                if len(daily_raw) < 20:
                    errors.append(f"{sym}: insufficient bars ({len(daily_raw)})")
                    continue

                daily_ind = calculate_indicators_from_ohlcv(daily_raw)
                price = daily_raw[-1]["close"]
                price_prev = daily_raw[-2]["close"] if len(daily_raw) >= 2 else price

                asset: dict = {
                    "symbol": sym,
                    "name": _CG_NAMES.get(sym, sym),
                    "tier": tier,
                    "price": price,
                    "change_24h": round((price - price_prev) / price_prev * 100, 2),
                    "change_7d": cg_data.get(sym, {}).get("change_7d"),
                    "volume_24h": daily_raw[-1]["volume"],
                    "market_cap": cg_data.get(sym, {}).get("market_cap"),
                    "sparkline_7d": cg_data.get(sym, {}).get("sparkline", []),
                    "timeframes": {
                        "daily": {
                            "ohlcv": daily_raw[-60:],
                            "indicators": daily_ind,
                        }
                    },
                }

                if tier == 1:
                    df_w = weekly_data.get(sym)
                    if df_w is not None and not df_w.empty:
                        weekly_raw = _df_to_ohlcv(df_w)
                        if len(weekly_raw) >= 10:
                            weekly_ind = calculate_indicators_from_ohlcv(weekly_raw)
                            asset["timeframes"]["weekly"] = {
                                "ohlcv": weekly_raw[-52:],
                                "indicators": weekly_ind,
                            }

                assets.append(asset)

            except Exception as e:
                errors.append(f"{sym}: {e}")
                log.warning("Error processing %s: %s", sym, e)

    return {
        "market": "crypto",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fear_greed": fear_greed,
        "assets": assets,
        "errors": errors,
    }


async def fetch() -> dict | None:
    """Convenience wrapper — used when calling standalone (not from main.py)."""
    meta = await fetch_meta()
    daily_data, weekly_data = _download_ohlcv()
    return build_result(meta, daily_data, weekly_data)
