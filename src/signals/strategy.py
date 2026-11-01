"""
Causal (no look-ahead) indicator computation for the weekly strategy.

Indicators computed per bar t using only data up to and including bar t:
  - SMA(30), SMA(50), SMA(200)
  - RSI(14) and its 14-period SMA overlay
  - SuperTrend(10, 3.0)
"""

from typing import Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# SMA helpers
# ---------------------------------------------------------------------------

def add_smas(df: pd.DataFrame, periods: list) -> pd.DataFrame:
    """
    Add SMA columns for each period.  Rolling mean is fully causal.
    Column names: SMA30, SMA50, SMA200, etc.
    """
    df = df.copy()
    for p in periods:
        df[f"SMA{p}"] = df["Close"].rolling(window=p).mean()
    return df


# ---------------------------------------------------------------------------
# RSI (Wilder / smoothed, causal)
# ---------------------------------------------------------------------------

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's RSI — exponential smoothing with alpha = 1/period.
    Result at bar t depends only on bars 0..t.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Wilder smoothing: alpha = 1/period, com = period-1
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def add_rsi(df: pd.DataFrame, rsi_period: int = 14, sma_period: int = 14) -> pd.DataFrame:
    """
    Add RSI and its SMA overlay.
    Columns added: RSI14, RSI14_SMA14 (names include periods).
    """
    df = df.copy()
    rsi_col = f"RSI{rsi_period}"
    sma_col = f"RSI{rsi_period}_SMA{sma_period}"
    df[rsi_col] = compute_rsi(df["Close"], rsi_period)
    df[sma_col] = df[rsi_col].rolling(window=sma_period).mean()
    return df


# ---------------------------------------------------------------------------
# SuperTrend (causal loop)
# ---------------------------------------------------------------------------

def compute_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> Tuple[pd.Series, pd.Series]:
    """
    SuperTrend with Wilder ATR.  Pure Python loop guarantees causality.

    Returns
    -------
    supertrend : pd.Series  — the SuperTrend line value at each bar
    direction  : pd.Series  — +1 (uptrend / bullish) or -1 (downtrend / bearish)
    """
    n = len(df)
    close = df["Close"].values
    high = df["High"].values
    low = df["Low"].values

    # True range
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))

    # Wilder ATR: seed first value then smooth
    atr = np.empty(n)
    atr[0] = tr[0]
    alpha = 1.0 / period
    for i in range(1, n):
        atr[i] = alpha * tr[i] + (1.0 - alpha) * atr[i - 1]

    # Basic upper/lower bands
    hl2 = (high + low) / 2.0
    basic_ub = hl2 + multiplier * atr
    basic_lb = hl2 - multiplier * atr

    final_ub = np.empty(n)
    final_lb = np.empty(n)
    supertrend = np.empty(n)
    direction = np.ones(n, dtype=np.int8)

    final_ub[0] = basic_ub[0]
    final_lb[0] = basic_lb[0]
    supertrend[0] = final_ub[0]
    direction[0] = -1  # undefined for first bar; default downtrend

    for i in range(1, n):
        # Final upper band
        if basic_ub[i] < final_ub[i - 1] or close[i - 1] > final_ub[i - 1]:
            final_ub[i] = basic_ub[i]
        else:
            final_ub[i] = final_ub[i - 1]

        # Final lower band
        if basic_lb[i] > final_lb[i - 1] or close[i - 1] < final_lb[i - 1]:
            final_lb[i] = basic_lb[i]
        else:
            final_lb[i] = final_lb[i - 1]

        # Direction
        if direction[i - 1] == 1:
            direction[i] = -1 if close[i] < final_lb[i] else 1
        else:
            direction[i] = 1 if close[i] > final_ub[i] else -1

        supertrend[i] = final_lb[i] if direction[i] == 1 else final_ub[i]

    return (
        pd.Series(supertrend, index=df.index, name="SuperTrend"),
        pd.Series(direction.astype(int), index=df.index, name="ST_Direction"),
    )


def add_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """Add SuperTrend and ST_Direction columns to dataframe."""
    df = df.copy()
    st, direction = compute_supertrend(df, period, multiplier)
    df["SuperTrend"] = st
    df["ST_Direction"] = direction
    return df


# ---------------------------------------------------------------------------
# Master: compute all indicators at once
# ---------------------------------------------------------------------------

def compute_all_indicators(
    df: pd.DataFrame,
    sma_entry: int = 30,
    sma_slow: int = 50,
    sma_trend: int = 200,
    rsi_period: int = 14,
    rsi_sma_period: int = 14,
    supertrend_period: int = 10,
    supertrend_multiplier: float = 3.0,
) -> pd.DataFrame:
    """
    Compute all strategy indicators on a weekly OHLC DataFrame.
    All computations are strictly causal.
    """
    df = add_smas(df, [sma_entry, sma_slow, sma_trend])
    df = add_rsi(df, rsi_period, rsi_sma_period)
    df = add_supertrend(df, supertrend_period, supertrend_multiplier)
    return df


# ---------------------------------------------------------------------------
# Signal detection: entry / exit
# ---------------------------------------------------------------------------

def detect_entry(row: pd.Series, sma_entry: int = 30, rsi_period: int = 14,
                 rsi_threshold: float = 60.0) -> bool:
    """
    Entry condition at a single bar (already computed indicators):
      - Close > SMA{sma_entry}
      - RSI{rsi_period} > rsi_threshold  (strictly above)
    Returns False if any indicator is NaN.
    """
    sma = row.get(f"SMA{sma_entry}", np.nan)
    rsi = row.get(f"RSI{rsi_period}", np.nan)
    close = row["Close"]
    if any(np.isnan(v) for v in [sma, rsi, close]):
        return False
    return float(close) > float(sma) and float(rsi) > rsi_threshold


def detect_exit(row: pd.Series, sma_entry: int = 30) -> bool:
    """
    Exit condition at a single bar:
      - Close < SMA{sma_entry}
    Returns False if any indicator is NaN (conservative: stay in trade).
    """
    sma = row.get(f"SMA{sma_entry}", np.nan)
    close = row["Close"]
    if np.isnan(float(sma)) or np.isnan(float(close)):
        return False
    return float(close) < float(sma)


def get_live_signals(
    df: pd.DataFrame,
    sma_entry: int = 30,
    sma_slow: int = 50,
    sma_trend: int = 200,
    rsi_period: int = 14,
    rsi_sma_period: int = 14,
    rsi_threshold: float = 60.0,
    supertrend_period: int = 10,
    supertrend_multiplier: float = 3.0,
    min_bars: int = 215,
) -> dict:
    """
    Evaluate entry signal on the latest completed weekly candle.
    Returns a dict with all indicator values and a boolean 'entry_signal'.
    Returns None if insufficient data.
    """
    if df is None or len(df) < min_bars:
        return None

    df_ind = compute_all_indicators(
        df,
        sma_entry=sma_entry,
        sma_slow=sma_slow,
        sma_trend=sma_trend,
        rsi_period=rsi_period,
        rsi_sma_period=rsi_sma_period,
        supertrend_period=supertrend_period,
        supertrend_multiplier=supertrend_multiplier,
    )

    last = df_ind.iloc[-1]
    entry = detect_entry(last, sma_entry, rsi_period, rsi_threshold)

    rsi_col = f"RSI{rsi_period}"
    rsi_sma_col = f"RSI{rsi_period}_SMA{rsi_sma_period}"

    return {
        "date": df_ind.index[-1].strftime("%Y-%m-%d"),
        "close": round(float(last["Close"]), 2),
        f"SMA{sma_entry}": round(float(last[f"SMA{sma_entry}"]), 2) if not np.isnan(last[f"SMA{sma_entry}"]) else None,
        f"SMA{sma_slow}": round(float(last[f"SMA{sma_slow}"]), 2) if not np.isnan(last[f"SMA{sma_slow}"]) else None,
        f"SMA{sma_trend}": round(float(last[f"SMA{sma_trend}"]), 2) if not np.isnan(last[f"SMA{sma_trend}"]) else None,
        rsi_col: round(float(last[rsi_col]), 2) if not np.isnan(last[rsi_col]) else None,
        rsi_sma_col: round(float(last[rsi_sma_col]), 2) if not np.isnan(last[rsi_sma_col]) else None,
        "SuperTrend": round(float(last["SuperTrend"]), 2),
        "ST_Direction": int(last["ST_Direction"]),
        "entry_signal": entry,
    }
