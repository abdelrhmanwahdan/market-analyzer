"""Signal PNL tracker — fetches current prices and updates open signal statuses.

Lifecycle:
  ACTIVE (BUY signal generated)
    → insert snapshot every run
    → if price ≤ stop_loss  → CLOSED (hit_sl)
    → if price ≥ tp1        → CLOSED (hit_tp1)
    → if price ≥ tp2        → CLOSED (hit_tp2)
    → if price ≥ tp3        → CLOSED (hit_tp3)
"""

import logging
from datetime import datetime, timezone

import requests
import yfinance as yf

log = logging.getLogger(__name__)


def _fetch_current_prices(signals: list[dict]) -> dict[str, float]:
    """Return {symbol: current_price} for all unique symbols in active signals."""
    prices: dict[str, float] = {}

    crypto_symbols = set()
    yf_symbols = set()
    egx_symbols = set()

    for sig in signals:
        market = sig.get("market", "")
        asset = sig.get("asset", "")
        if market == "crypto":
            crypto_symbols.add(asset)
        elif market in ("gold", "silver", "us_stocks"):
            yf_symbols.add(asset)
        elif market == "egx":
            egx_symbols.add(asset)

    # ── Crypto prices from Binance ─────────────────────────────────────────────
    for sym in crypto_symbols:
        try:
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": f"{sym}USDT"},
                timeout=10,
            )
            if r.status_code == 200:
                prices[sym] = float(r.json()["price"])
        except Exception as e:
            log.warning("Price fetch failed for %s: %s", sym, e)

    # ── Gold/Silver/US stocks from yfinance ───────────────────────────────────
    # Map output symbols back to yfinance tickers
    symbol_to_ticker = {
        "GOLD": "GC=F", "SILVER": "SI=F", "GLD": "GLD", "SLV": "SLV",
    }
    yf_fetch = set()
    for sym in yf_symbols:
        ticker = symbol_to_ticker.get(sym, sym)  # stocks use their own ticker
        yf_fetch.add(ticker)

    if yf_fetch:
        try:
            data = yf.download(list(yf_fetch), period="2d", interval="1d", auto_adjust=True, progress=False)
            for sym in yf_symbols:
                ticker = symbol_to_ticker.get(sym, sym)
                try:
                    if len(yf_fetch) == 1:
                        price = float(data["Close"].iloc[-1])
                    else:
                        price = float(data["Close"][ticker].iloc[-1])
                    prices[sym] = price
                except Exception:
                    pass
        except Exception as e:
            log.warning("yfinance price fetch failed: %s", e)

    # ── EGX prices from egxpy ─────────────────────────────────────────────────
    if egx_symbols:
        try:
            from egxpy.download import get_OHLCV_data
            for sym in egx_symbols:
                try:
                    df = get_OHLCV_data(symbol=sym, exchange="EGX", interval="Daily", n_bars=5)
                    if df is not None and not df.empty:
                        prices[sym] = float(df["Close"].iloc[-1])
                except Exception as e:
                    log.warning("EGX price fetch failed for %s: %s", sym, e)
        except ImportError:
            log.warning("egxpy not available for EGX price updates")

    return prices


def _determine_close_reason(current_price: float, signal: dict) -> str | None:
    """Return close reason if signal should be closed, else None."""
    entry = signal.get("current_price") or signal.get("entry_zone_low")
    stop = signal.get("stop_loss")
    tp3 = signal.get("take_profit_3")
    tp2 = signal.get("take_profit_2")
    tp1 = signal.get("take_profit_1")

    if not entry:
        return None

    # Check stop loss hit
    if stop and current_price <= stop:
        return "hit_sl"

    # Check take profits (highest first)
    if tp3 and current_price >= tp3:
        return "hit_tp3"
    if tp2 and current_price >= tp2:
        return "hit_tp2"
    if tp1 and current_price >= tp1:
        return "hit_tp1"

    return None


def update_pnl() -> dict:
    """
    Main PNL update function:
    1. Load all active BUY signals from Supabase
    2. Fetch current prices
    3. Insert snapshots
    4. Close any that hit SL/TP
    Returns summary dict.
    """
    from db.supabase_client import get_active_signals, save_snapshot, close_signal

    start = datetime.now(timezone.utc)
    log.info("Starting PNL update...")

    active_signals = get_active_signals()
    if not active_signals:
        log.info("No active signals to update.")
        return {"updated": 0, "closed": 0, "errors": []}

    log.info("Found %d active signals", len(active_signals))

    prices = _fetch_current_prices(active_signals)
    log.info("Fetched %d prices", len(prices))

    updated = 0
    closed = 0
    errors = []

    for sig in active_signals:
        asset = sig["asset"]
        signal_id = sig["id"]
        entry_price = sig.get("current_price") or sig.get("entry_zone_low")

        current_price = prices.get(asset)
        if current_price is None:
            errors.append(f"No price for {asset}")
            continue

        if not entry_price:
            errors.append(f"No entry price for {asset} ({signal_id})")
            continue

        # Insert snapshot
        save_snapshot(
            signal_id=signal_id,
            current_price=current_price,
            entry_price=entry_price,
            stop_loss=sig.get("stop_loss"),
            take_profit_1=sig.get("take_profit_1"),
        )
        updated += 1

        # Check if should close
        close_reason = _determine_close_reason(current_price, sig)
        if close_reason:
            close_signal(
                signal_id=signal_id,
                close_price=current_price,
                close_reason=close_reason,
                entry_price=entry_price,
            )
            closed += 1
            pnl_pct = round((current_price - entry_price) / entry_price * 100, 2)
            result = "WIN" if close_reason.startswith("hit_tp") else "LOSS"
            log.info("CLOSED %s (%s): %s | PNL: %+.2f%% [%s]", asset, signal_id, close_reason, pnl_pct, result)

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    summary = {
        "updated": updated,
        "closed": closed,
        "errors": errors,
        "duration_seconds": round(duration, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    log.info("PNL update complete: %s", summary)
    return summary
