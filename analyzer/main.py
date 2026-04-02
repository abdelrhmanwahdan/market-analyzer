#!/usr/bin/env python3
"""
Market Analyzer — Local-first data fetcher and signal tracker.

Usage:
  python main.py --fetch                          # Fetch all market data → output/latest_data.json
  python main.py --fetch --update-pnl             # Fetch data + update open signal PNL
  python main.py --update-pnl                     # Update PNL only (fast, no data fetch)
  python main.py --store-signals output/signals.json  # Save Claude Code's signals to Supabase
  python main.py --fetch --store-signals output/signals.json --update-pnl  # All-in-one

After --fetch:
  Read output/latest_data.json, then ask Claude Code:
  "analyze my latest market data"
  Claude Code follows ANALYSIS_INSTRUCTIONS.md and outputs output/signals.json
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure we can import from the analyzer package
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
LATEST_DATA_PATH = OUTPUT_DIR / "latest_data.json"


# ── Fetch all markets ─────────────────────────────────────────────────────────

async def fetch_all_data() -> dict:
    """Run all fetchers concurrently. Each returns its market dict or None on failure."""
    from fetchers import crypto, gold_silver, us_market, egx, whale_tracker, news
    from db.supabase_client import get_active_signals

    log.info("Starting data fetch for all markets...")
    start = time.time()
    fetchers_status = {}

    # Run async (crypto) and non-yfinance fetchers in parallel.
    # yfinance fetchers (gold, us, egx) run sequentially in a single thread
    # to avoid Yahoo Finance rate-limit conflicts from concurrent connections.
    crypto_task = asyncio.create_task(crypto.fetch())
    loop = asyncio.get_event_loop()

    def run_yfinance_fetchers():
        """Gold, US, EGX run one after another to avoid Yahoo rate limits."""
        gold = gold_silver.fetch()
        us = us_market.fetch()
        egx_result = egx.fetch()
        return gold, us, egx_result

    yf_task = loop.run_in_executor(None, run_yfinance_fetchers)
    whale_task = loop.run_in_executor(None, whale_tracker.fetch)
    news_task = loop.run_in_executor(None, news.fetch)

    crypto_data = await crypto_task
    fetchers_status["crypto"] = "ok" if crypto_data else "error"

    gold_data, us_data, egx_data = await yf_task
    fetchers_status["gold_silver"] = "ok" if gold_data else "error"
    fetchers_status["us_market"] = "ok" if us_data else "error"
    fetchers_status["egx"] = "ok" if egx_data else "error"

    whale_data = await whale_task
    fetchers_status["whale"] = "ok" if whale_data else "error"

    news_data = await news_task
    fetchers_status["news"] = "ok" if news_data else "error"

    # Load active signals from Supabase (for position review in analysis)
    active_positions = []
    try:
        from db.supabase_client import get_active_signals
        active_positions = get_active_signals()
        log.info("Loaded %d active signals from Supabase", len(active_positions))
    except Exception as e:
        log.warning("Could not load active signals: %s", e)

    duration = round(time.time() - start, 1)
    log.info("Fetch complete in %.1fs. Status: %s", duration, fetchers_status)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fetch_duration_seconds": duration,
        "fetchers_status": fetchers_status,
        "crypto": crypto_data,
        "commodities": gold_data,
        "us_market": us_data,
        "egx": egx_data,
        "whale_activity": whale_data,
        "news": news_data,
        "active_positions": active_positions,
    }


# ── Store signals from Claude Code output ─────────────────────────────────────

def store_signals(signals_path: str) -> None:
    """Read signals JSON (Claude Code's output) and save to Supabase."""
    from db.supabase_client import save_analysis, save_signals, save_market_data

    path = Path(signals_path)
    if not path.exists():
        log.error("Signals file not found: %s", path)
        sys.exit(1)

    with open(path) as f:
        analysis = json.load(f)

    log.info("Storing analysis + signals to Supabase...")

    analysis_id = save_analysis(analysis)
    log.info("Analysis saved: %s", analysis_id)

    signals = analysis.get("signals", [])
    buy_signals = [s for s in signals if s.get("type") == "BUY"]
    if buy_signals:
        ids = save_signals(buy_signals, analysis_id=analysis_id)
        log.info("Saved %d BUY signals: %s", len(ids), ids)
    else:
        log.info("No BUY signals to save.")

    # Also save market data from the latest fetch if available
    if LATEST_DATA_PATH.exists():
        with open(LATEST_DATA_PATH) as f:
            latest = json.load(f)
        for market_key, market_data in [
            ("crypto", "crypto"),
            ("commodities", "commodities"),
            ("us_market", "us_stocks"),
            ("egx", "egx"),
        ]:
            data = latest.get(market_key)
            if data and data.get("assets"):
                save_market_data(data["assets"], market_data)

        # Save USD/EGP rate as a standalone FX record
        usd_egp = latest.get("commodities", {}).get("usd_egp")
        if usd_egp:
            save_market_data([{"symbol": "USDEGP", "price_usd": usd_egp}], "fx")

        log.info("Market data snapshots saved.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Market Analyzer CLI")
    parser.add_argument("--fetch", action="store_true", help="Fetch all market data")
    parser.add_argument("--update-pnl", action="store_true", help="Update PNL for active signals")
    parser.add_argument("--store-signals", metavar="FILE", help="Store Claude Code signals JSON to Supabase")
    args = parser.parse_args()

    if not any([args.fetch, args.update_pnl, args.store_signals]):
        parser.print_help()
        sys.exit(0)

    # ── Fetch ─────────────────────────────────────────────────────────────────
    if args.fetch:
        data = asyncio.run(fetch_all_data())

        with open(LATEST_DATA_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

        log.info("✓ Data saved to %s", LATEST_DATA_PATH)
        print(f"\n✓ Data fetched successfully → {LATEST_DATA_PATH}")
        print("\nNext steps:")
        print("  1. Ask Claude Code: \"analyze my latest market data\"")
        print("  2. Claude Code reads ANALYSIS_INSTRUCTIONS.md and outputs signals.json")
        print("  3. Run: python main.py --store-signals output/signals.json")

        # Quick summary
        markets_ok = [k for k, v in data.get("fetchers_status", {}).items() if v == "ok"]
        markets_err = [k for k, v in data.get("fetchers_status", {}).items() if v != "ok"]
        if markets_ok:
            print(f"\n  Markets fetched: {', '.join(markets_ok)}")
        if markets_err:
            print(f"  Markets failed: {', '.join(markets_err)}")

    # ── Store signals ──────────────────────────────────────────────────────────
    if args.store_signals:
        store_signals(args.store_signals)

    # ── PNL update ────────────────────────────────────────────────────────────
    if args.update_pnl:
        from pnl.tracker import update_pnl
        summary = update_pnl()
        print(f"\n✓ PNL update complete:")
        print(f"  Snapshots recorded: {summary['updated']}")
        print(f"  Signals closed:     {summary['closed']}")
        if summary.get("errors"):
            print(f"  Errors:             {len(summary['errors'])}")


if __name__ == "__main__":
    main()
