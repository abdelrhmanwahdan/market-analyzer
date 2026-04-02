"""Crypto market fetcher — Binance (daily/weekly OHLCV) + CoinGecko + Fear & Greed."""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from config import CRYPTO_TIER1, CRYPTO_TIER2, CRYPTO_TIER3, DAILY_BARS, WEEKLY_BARS

log = logging.getLogger(__name__)

BINANCE_BASE = "https://api.binance.com/api/v3"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=30"


async def _get(session: aiohttp.ClientSession, url: str, params: dict | None = None) -> dict | list | None:
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status == 200:
                return await r.json()
            log.warning("GET %s → %s", url, r.status)
    except Exception as e:
        log.warning("GET %s failed: %s", url, e)
    return None


async def _fetch_klines(session: aiohttp.ClientSession, symbol: str, interval: str, limit: int) -> list:
    """Fetch Binance OHLCV — returns list of [ts, open, high, low, close, volume]."""
    data = await _get(session, f"{BINANCE_BASE}/klines", {
        "symbol": f"{symbol}USDT",
        "interval": interval,
        "limit": limit,
    })
    if not data:
        return []
    return [
        {
            "ts": int(c[0]),
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        }
        for c in data
    ]


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
            "coingecko_id": coin.get("id"),
        }
    return result


async def fetch() -> dict | None:
    """Fetch crypto market data (daily + weekly) for all tiers."""
    from indicators.technical import calculate_indicators_from_ohlcv

    assets = []
    errors = []

    async with aiohttp.ClientSession() as session:
        fear_greed, cg_data = await asyncio.gather(
            _fetch_fear_greed(session),
            _fetch_cg_markets(session),
        )

        # Fetch daily + weekly for Tier 1 (all), Tier 2 (daily only), Tier 3 (daily only)
        for tier, symbols in [
            (1, CRYPTO_TIER1),
            (2, CRYPTO_TIER2),
            (3, CRYPTO_TIER3),
        ]:
            for sym in symbols:
                try:
                    # Always fetch daily
                    daily_raw = await _fetch_klines(session, sym, "1d", DAILY_BARS)
                    if not daily_raw:
                        log.warning("No daily data for %s", sym)
                        continue

                    daily_ind = calculate_indicators_from_ohlcv(daily_raw)

                    asset: dict = {
                        "symbol": sym,
                        "name": sym,  # will be enriched from CoinGecko below
                        "tier": tier,
                        "price": daily_raw[-1]["close"],
                        "change_24h": round(
                            (daily_raw[-1]["close"] - daily_raw[-2]["close"]) / daily_raw[-2]["close"] * 100, 2
                        ) if len(daily_raw) >= 2 else 0,
                        "change_7d": cg_data.get(sym, {}).get("change_7d"),
                        "volume_24h": daily_raw[-1]["volume"],
                        "market_cap": cg_data.get(sym, {}).get("market_cap"),
                        "sparkline_7d": cg_data.get(sym, {}).get("sparkline", []),
                        "timeframes": {
                            "daily": {
                                "ohlcv": daily_raw[-60:],  # last 60 days in output
                                "indicators": daily_ind,
                            }
                        },
                    }

                    # Weekly only for Tier 1
                    if tier == 1:
                        weekly_raw = await _fetch_klines(session, sym, "1w", WEEKLY_BARS)
                        if weekly_raw:
                            weekly_ind = calculate_indicators_from_ohlcv(weekly_raw)
                            asset["timeframes"]["weekly"] = {
                                "ohlcv": weekly_raw[-52:],
                                "indicators": weekly_ind,
                            }

                    assets.append(asset)
                    await asyncio.sleep(0.1)  # stay under rate limits

                except Exception as e:
                    errors.append(f"{sym}: {e}")
                    log.warning("Error fetching %s: %s", sym, e)

    # Enrich names from CoinGecko
    cg_names = {
        "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB",
        "XRP": "XRP", "ADA": "Cardano", "AVAX": "Avalanche", "DOGE": "Dogecoin",
        "DOT": "Polkadot", "LINK": "Chainlink", "ATOM": "Cosmos", "UNI": "Uniswap",
        "LTC": "Litecoin", "NEAR": "NEAR Protocol", "FIL": "Filecoin", "APT": "Aptos",
        "SUI": "Sui", "INJ": "Injective", "SEI": "Sei", "TIA": "Celestia",
        "RNDR": "Render", "FET": "Fetch.ai", "AR": "Arweave", "OP": "Optimism",
        "ARB": "Arbitrum", "STX": "Stacks", "AAVE": "Aave",
    }
    for a in assets:
        a["name"] = cg_names.get(a["symbol"], a["symbol"])

    return {
        "market": "crypto",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fear_greed": fear_greed,
        "assets": assets,
        "errors": errors,
    }
