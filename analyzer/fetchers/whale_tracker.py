"""Whale & smart money tracker — DeFiLlama only (free, no API key needed)."""

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

LLAMA_BASE = "https://api.llama.fi"
STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoins"
TIMEOUT = 15


def _get(url: str) -> dict | list | None:
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        log.warning("DeFiLlama %s → %s", url, r.status_code)
    except Exception as e:
        log.warning("DeFiLlama request failed: %s", e)
    return None


def _format_usd(value: float) -> str:
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def fetch() -> dict | None:
    """Fetch DeFi TVL, stablecoin flows, protocol changes."""

    # ── Total DeFi TVL ────────────────────────────────────────────────────────
    tvl_data = _get(f"{LLAMA_BASE}/v2/historicalChainTvl")
    total_tvl = None
    tvl_change_24h = None
    tvl_history = []
    if tvl_data and isinstance(tvl_data, list) and len(tvl_data) >= 2:
        latest = tvl_data[-1]
        prev = tvl_data[-2]
        # /v2/historicalChainTvl uses "tvl" field
        total_tvl = latest.get("tvl") or latest.get("totalLiquidityUSD")
        prev_tvl = prev.get("tvl") or prev.get("totalLiquidityUSD")
        if total_tvl and prev_tvl:
            tvl_change_24h = round((total_tvl - prev_tvl) / prev_tvl * 100, 2)
        tvl_history = [
            {"ts": int(d["date"]) * 1000, "tvl": d.get("tvl") or d.get("totalLiquidityUSD")}
            for d in tvl_data[-30:]
        ]

    # ── Chain TVL breakdown ───────────────────────────────────────────────────
    chains_data = _get(f"{LLAMA_BASE}/v2/chains")
    top_chains = []
    if chains_data and isinstance(chains_data, list):
        sorted_chains = sorted(chains_data, key=lambda x: x.get("tvl", 0), reverse=True)[:10]
        for chain in sorted_chains:
            top_chains.append({
                "name": chain.get("name"),
                "tvl": chain.get("tvl"),
                "tvl_display": _format_usd(chain.get("tvl", 0)),
                "change_1d": chain.get("change_1d"),
                "change_7d": chain.get("change_7d"),
            })

    # ── Stablecoin supply ─────────────────────────────────────────────────────
    stable_data = _get(STABLECOINS_URL)
    total_stablecoin_mcap = None
    stablecoin_breakdown = []
    if stable_data and isinstance(stable_data, dict):
        pegged_assets = stable_data.get("peggedAssets", [])
        total_stablecoin_mcap = sum(
            a.get("circulating", {}).get("peggedUSD", 0) for a in pegged_assets
        )
        top_stables = sorted(
            pegged_assets,
            key=lambda x: x.get("circulating", {}).get("peggedUSD", 0),
            reverse=True,
        )[:5]
        for s in top_stables:
            cap = s.get("circulating", {}).get("peggedUSD", 0)
            stablecoin_breakdown.append({
                "name": s.get("name"),
                "symbol": s.get("symbol"),
                "market_cap": cap,
                "display": _format_usd(cap),
            })

    # ── Top protocol TVL changes ──────────────────────────────────────────────
    protocols_data = _get(f"{LLAMA_BASE}/protocols")
    notable_flows = []
    if protocols_data and isinstance(protocols_data, list):
        # Find protocols with big 24h changes
        protocols_with_change = [
            p for p in protocols_data
            if p.get("change_1d") is not None and p.get("tvl", 0) > 100_000_000
        ]
        big_movers = sorted(
            protocols_with_change,
            key=lambda x: abs(x.get("change_1d", 0)),
            reverse=True,
        )[:5]
        for p in big_movers:
            notable_flows.append({
                "protocol": p.get("name"),
                "tvl": p.get("tvl"),
                "tvl_display": _format_usd(p.get("tvl", 0)),
                "change_1d_pct": p.get("change_1d"),
                "category": p.get("category"),
                "chains": p.get("chains", [])[:3],
                "interpretation": (
                    f"{'Capital inflow' if (p.get('change_1d') or 0) > 0 else 'Capital outflow'}: "
                    f"{p.get('name')} TVL changed {p.get('change_1d', 0):.1f}% in 24h"
                ),
            })

    # ── Build smart money interpretation ─────────────────────────────────────
    summary_parts = []
    if total_tvl:
        direction = "up" if (tvl_change_24h or 0) > 0 else "down"
        summary_parts.append(
            f"Total DeFi TVL: {_format_usd(total_tvl)} ({direction} {abs(tvl_change_24h or 0):.1f}% in 24h)"
        )
    if total_stablecoin_mcap:
        summary_parts.append(f"Total stablecoin supply: {_format_usd(total_stablecoin_mcap)}")
    if top_chains:
        top = top_chains[0]
        summary_parts.append(
            f"Largest chain: {top['name']} ({top['tvl_display']}, {top.get('change_1d') or 0:.1f}% 24h)"
        )

    return {
        "market": "whale_activity",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": ". ".join(summary_parts),
        "total_defi_tvl": total_tvl,
        "total_defi_tvl_display": _format_usd(total_tvl) if total_tvl else "N/A",
        "tvl_change_24h_pct": tvl_change_24h,
        "tvl_history_30d": tvl_history,
        "top_chains": top_chains,
        "total_stablecoin_mcap": total_stablecoin_mcap,
        "stablecoin_breakdown": stablecoin_breakdown,
        "notable_protocol_flows": notable_flows,
        # Note: On-chain whale tx data available via web search during Claude analysis
        "note": "Large on-chain transactions: search 'whale alert bitcoin large transactions today' during Claude Code analysis",
    }
