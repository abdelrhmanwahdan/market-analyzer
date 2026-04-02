"""Technical indicators calculator using pandas-ta.

All indicators are calculated from OHLCV data on any timeframe (daily/weekly).
Input: list of {"ts", "open", "high", "low", "close", "volume"}
Output: dict of indicator values for the latest bar.
"""

import logging

import pandas as pd

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logging.warning("pandas-ta not installed — indicators will be minimal. Run: pip install pandas-ta")

log = logging.getLogger(__name__)


def calculate_indicators_from_ohlcv(ohlcv: list[dict]) -> dict:
    """
    Calculate technical indicators from OHLCV list.

    Returns a dict with all indicator values for the most recent bar.
    Returns minimal dict if data is insufficient or pandas-ta is unavailable.
    """
    if not ohlcv or len(ohlcv) < 5:
        return {"error": "insufficient data"}

    df = pd.DataFrame(ohlcv)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"ts": "date"})
    df["date"] = pd.to_datetime(df["date"], unit="ms")
    df = df.set_index("date").sort_index()

    # Ensure numeric types
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])

    n = len(df)
    current = df.iloc[-1]
    price = float(current["close"])

    if not PANDAS_TA_AVAILABLE or n < 5:
        return _minimal_indicators(df, price)

    result: dict = {"price": price}

    # ── Trend: EMAs ────────────────────────────────────────────────────────────
    for length in [20, 50, 200]:
        if n >= length:
            ema = ta.ema(df["close"], length=length)
            if ema is not None and not ema.empty:
                result[f"ema_{length}"] = _safe_float(ema.iloc[-1])

    # ── Trend direction ────────────────────────────────────────────────────────
    ema20 = result.get("ema_20")
    ema50 = result.get("ema_50")
    ema200 = result.get("ema_200")
    if ema20 and ema50:
        if ema20 > ema50 and (ema200 is None or price > ema200):
            result["trend"] = "BULLISH"
        elif ema20 < ema50 and (ema200 is None or price < ema200):
            result["trend"] = "BEARISH"
        else:
            result["trend"] = "MIXED"
    else:
        result["trend"] = "UNKNOWN"

    # ── Momentum: RSI ──────────────────────────────────────────────────────────
    if n >= 14:
        rsi = ta.rsi(df["close"], length=14)
        if rsi is not None and not rsi.empty:
            rsi_val = _safe_float(rsi.iloc[-1])
            result["rsi"] = rsi_val
            result["rsi_signal"] = (
                "OVERSOLD" if (rsi_val or 50) < 30 else
                "OVERBOUGHT" if (rsi_val or 50) > 70 else
                "NEUTRAL"
            )

    # ── Momentum: MACD ─────────────────────────────────────────────────────────
    if n >= 26:
        macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            cols = macd.columns.tolist()
            result["macd"] = _safe_float(macd[cols[0]].iloc[-1])
            result["macd_signal"] = _safe_float(macd[cols[1]].iloc[-1])
            result["macd_histogram"] = _safe_float(macd[cols[2]].iloc[-1])

    # ── Volatility: Bollinger Bands ────────────────────────────────────────────
    if n >= 20:
        bb = ta.bbands(df["close"], length=20, std=2)
        if bb is not None and not bb.empty:
            cols = bb.columns.tolist()
            result["bb_lower"] = _safe_float(bb[cols[0]].iloc[-1])
            result["bb_mid"] = _safe_float(bb[cols[1]].iloc[-1])
            result["bb_upper"] = _safe_float(bb[cols[2]].iloc[-1])

    # ── Trend strength: ADX ────────────────────────────────────────────────────
    if n >= 14:
        adx = ta.adx(df["high"], df["low"], df["close"], length=14)
        if adx is not None and not adx.empty:
            result["adx"] = _safe_float(adx.iloc[:, 0].iloc[-1])

    # ── Volatility: ATR ────────────────────────────────────────────────────────
    if n >= 14:
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        if atr is not None and not atr.empty:
            atr_val = _safe_float(atr.iloc[-1])
            result["atr"] = atr_val
            if atr_val and price:
                atr_pct = round(atr_val / price * 100, 2)
                result["atr_pct"] = atr_pct

    # ── Volume analysis ────────────────────────────────────────────────────────
    vol_current = float(current.get("volume", 0) or 0)
    result["volume_current"] = vol_current
    if n >= 20:
        vol_sma = ta.sma(df["volume"], length=20)
        if vol_sma is not None and not vol_sma.empty:
            avg_vol = _safe_float(vol_sma.iloc[-1]) or vol_current
            result["volume_avg_20d"] = avg_vol
            vol_ratio = round(vol_current / avg_vol, 2) if avg_vol > 0 else 1.0
            result["volume_ratio"] = vol_ratio
            result["volume_signal"] = (
                "HIGH" if vol_ratio > 2.0 else
                "ELEVATED" if vol_ratio > 1.5 else
                "NORMAL" if vol_ratio >= 0.5 else
                "LOW"
            )

    # ── Historical volatility (30-period rolling std, annualized) ─────────────
    if n >= 30:
        log_returns = df["close"].pct_change().apply(lambda x: x)
        hist_vol = float(log_returns.rolling(30).std().iloc[-1] * (252 ** 0.5) * 100)
        result["hist_volatility_30d"] = round(hist_vol, 2)

    # ── Volatility score (1-10) ────────────────────────────────────────────────
    atr_pct = result.get("atr_pct", 0) or 0
    if atr_pct < 0.5:
        score = 1
    elif atr_pct < 1.0:
        score = 2
    elif atr_pct < 1.5:
        score = 3
    elif atr_pct < 2.5:
        score = 5
    elif atr_pct < 4.0:
        score = 6
    elif atr_pct < 5.5:
        score = 7
    elif atr_pct < 8.0:
        score = 8
    elif atr_pct < 12.0:
        score = 9
    else:
        score = 10

    result["volatility_score"] = score
    result["volatility_label"] = (
        "EXTREME" if score >= 9 else
        "HIGH" if score >= 7 else
        "MODERATE" if score >= 4 else
        "LOW"
    )

    # ── Key levels (simple swing high/low) ────────────────────────────────────
    if n >= 20:
        recent = df["close"].tail(20)
        result["level_high_20"] = round(float(recent.max()), 4)
        result["level_low_20"] = round(float(recent.min()), 4)

    return result


def _minimal_indicators(df: pd.DataFrame, price: float) -> dict:
    """Fallback when pandas-ta is not available."""
    result: dict = {"price": price}
    closes = df["close"]

    if len(closes) >= 2:
        chg = float(closes.iloc[-1] - closes.iloc[-2]) / float(closes.iloc[-2]) * 100
        result["change_pct"] = round(chg, 2)
        result["trend"] = "BULLISH" if chg > 0 else "BEARISH"

    return result


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return round(f, 6) if not (f != f) else None  # NaN check
    except (TypeError, ValueError):
        return None
