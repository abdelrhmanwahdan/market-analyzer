"""Supabase client — read/write operations for the market analyzer."""

import logging
from datetime import datetime, timezone
from typing import Any

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

log = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


# ── Analysis ──────────────────────────────────────────────────────────────────

def save_analysis(analysis: dict) -> str | None:
    """Insert analysis record. Returns new analysis UUID."""
    try:
        row = {
            "market_overview": analysis.get("market_overview", ""),
            "fear_greed_crypto": analysis.get("fear_greed", {}).get("crypto", {}).get("value"),
            "fear_greed_label": analysis.get("fear_greed", {}).get("crypto", {}).get("label"),
            "overall_sentiment": analysis.get("fear_greed", {}).get("overall_assessment"),
            "whale_summary": analysis.get("whale_activity", {}).get("summary"),
            "defi_flows": str(analysis.get("whale_activity", {}).get("defi_flows", "")),
            "risk_warnings": analysis.get("risk_warnings", []),
            "upcoming_catalysts": analysis.get("upcoming_catalysts", []),
            "portfolio_allocation": analysis.get("portfolio_allocation_suggestion"),
            "raw_response": analysis,
        }
        resp = get_client().table("analyses").insert(row).execute()
        return resp.data[0]["id"] if resp.data else None
    except Exception as e:
        log.error("save_analysis failed: %s", e)
        return None


# ── Signals ───────────────────────────────────────────────────────────────────

def save_signals(signals: list[dict], analysis_id: str | None = None) -> list[str]:
    """Insert signals. Returns list of inserted UUIDs."""
    if not signals:
        return []
    saved_ids = []
    for sig in signals:
        try:
            row = {
                "analysis_id": analysis_id,
                "type": sig.get("type"),
                "asset": sig.get("asset"),
                "asset_name": sig.get("asset_name", sig.get("asset")),
                "market": sig.get("market"),
                "shariah_status": sig.get("shariah_status", "COMPLIANT"),
                "current_price": sig.get("current_price"),
                "entry_zone_low": sig.get("entry_zone", {}).get("low") if sig.get("entry_zone") else None,
                "entry_zone_high": sig.get("entry_zone", {}).get("high") if sig.get("entry_zone") else None,
                "stop_loss": sig.get("stop_loss"),
                "take_profit_1": sig.get("take_profit_1"),
                "take_profit_2": sig.get("take_profit_2"),
                "take_profit_3": sig.get("take_profit_3"),
                "confidence": sig.get("confidence"),
                "timeframe": sig.get("timeframe"),
                "risk_reward_ratio": sig.get("risk_reward_ratio"),
                "position_size_pct": sig.get("position_size_pct"),
                "position_size_usd": sig.get("position_size_usd"),
                "reasoning": sig.get("reasoning", ""),
                "urgency": sig.get("urgency"),
                "volatility_score": sig.get("volatility", {}).get("score") if sig.get("volatility") else None,
                "volatility_label": sig.get("volatility", {}).get("label") if sig.get("volatility") else None,
                "atr_pct": sig.get("volatility", {}).get("atr_pct") if sig.get("volatility") else None,
                "hist_vol_30d": sig.get("volatility", {}).get("hist_vol_30d") if sig.get("volatility") else None,
                "volume_ratio": sig.get("volume", {}).get("ratio_vs_avg") if sig.get("volume") else None,
                "volume_signal": sig.get("volume", {}).get("signal") if sig.get("volume") else None,
                "volume_confirms_price": sig.get("volume", {}).get("confirms_price", True) if sig.get("volume") else True,
                "status": "ACTIVE",
            }
            resp = get_client().table("signals").insert(row).execute()
            if resp.data:
                saved_ids.append(resp.data[0]["id"])
        except Exception as e:
            log.error("save_signal failed (%s): %s", sig.get("asset"), e)
    return saved_ids


def get_active_signals() -> list[dict]:
    """Fetch all active BUY signals for PNL tracking."""
    try:
        resp = (
            get_client()
            .table("signals")
            .select("*")
            .eq("status", "ACTIVE")
            .eq("type", "BUY")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        log.error("get_active_signals failed: %s", e)
        return []


def close_signal(signal_id: str, close_price: float, close_reason: str, entry_price: float) -> None:
    """Mark a signal as CLOSED and record realized PNL."""
    try:
        pnl_pct = round((close_price - entry_price) / entry_price * 100, 2) if entry_price else None
        get_client().table("signals").update({
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "close_price": close_price,
            "close_reason": close_reason,
            "realized_pnl_pct": pnl_pct,
        }).eq("id", signal_id).execute()
    except Exception as e:
        log.error("close_signal failed (%s): %s", signal_id, e)


# ── Signal Snapshots (PNL tracking) ──────────────────────────────────────────

def save_snapshot(signal_id: str, current_price: float, entry_price: float,
                  stop_loss: float | None, take_profit_1: float | None) -> None:
    """Insert a PNL snapshot for an active signal."""
    try:
        unrealized_pnl_pct = round((current_price - entry_price) / entry_price * 100, 2) if entry_price else None
        row: dict[str, Any] = {
            "signal_id": signal_id,
            "current_price": current_price,
            "unrealized_pnl_pct": unrealized_pnl_pct,
        }
        if stop_loss and current_price:
            row["distance_to_sl_pct"] = round((current_price - stop_loss) / current_price * 100, 2)
        if take_profit_1 and current_price:
            row["distance_to_tp1_pct"] = round((take_profit_1 - current_price) / current_price * 100, 2)
        get_client().table("signal_snapshots").insert(row).execute()
    except Exception as e:
        log.error("save_snapshot failed (%s): %s", signal_id, e)


# ── Market Data ───────────────────────────────────────────────────────────────

def save_market_data(assets: list[dict], market: str) -> None:
    """Upsert market data snapshots."""
    for asset in assets:
        try:
            row = {
                "asset": asset.get("symbol"),
                "market": market,
                "price": asset.get("price") or asset.get("price_usd") or asset.get("price_egp"),
                "change_24h": asset.get("change_24h") or asset.get("change_daily"),
                "volume_24h": asset.get("volume_24h"),
                "market_cap": asset.get("market_cap"),
                "indicators": asset.get("timeframes", {}).get("daily", {}).get("indicators"),
                "ohlcv_daily": asset.get("timeframes", {}).get("daily", {}).get("ohlcv", [])[-30:],
                "key_levels": {
                    "high_20": asset.get("timeframes", {}).get("daily", {}).get("indicators", {}).get("level_high_20"),
                    "low_20": asset.get("timeframes", {}).get("daily", {}).get("indicators", {}).get("level_low_20"),
                    "price_per_gram_usd": asset.get("price_per_gram_usd"),
                    "price_per_gram_egp_fair": asset.get("price_per_gram_egp_fair"),
                    "egypt_local_per_gram": asset.get("egypt_local_per_gram"),
                },
            }
            get_client().table("market_data").insert(row).execute()
        except Exception as e:
            log.warning("save_market_data failed (%s): %s", asset.get("symbol"), e)


# ── Run Logs ──────────────────────────────────────────────────────────────────

def save_run_log(status: str, duration: float, fetchers_status: dict,
                 error_details: str | None = None) -> None:
    try:
        get_client().table("run_logs").insert({
            "run_type": "manual",
            "status": status,
            "duration_seconds": duration,
            "fetchers_status": fetchers_status,
            "error_details": error_details,
        }).execute()
    except Exception as e:
        log.error("save_run_log failed: %s", e)
