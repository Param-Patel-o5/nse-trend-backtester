"""SMA Golden Cross signal detection without look-ahead bias."""

from typing import Any, Dict, List, Optional

import pandas as pd


def compute_smas(
    df: pd.DataFrame,
    fast_period: int = 30,
    slow_period: int = 50
) -> pd.DataFrame:
    """
    Compute rolling simple moving averages on Close prices.
    Strictly causal (no look-ahead): bar t rolling mean uses only bars <= t.
    """
    df = df.copy()
    df[f"SMA{fast_period}"] = df["Close"].rolling(window=fast_period).mean()
    df[f"SMA{slow_period}"] = df["Close"].rolling(window=slow_period).mean()
    return df


def find_all_crossovers(
    df: pd.DataFrame,
    symbol: str,
    fast_period: int = 30,
    slow_period: int = 50,
    min_bars: int = 55
) -> List[Dict[str, Any]]:
    """
    Find all historical golden cross events in the series.
    A golden cross occurs at bar t if:
      SMA_fast[t-1] <= SMA_slow[t-1] and SMA_fast[t] > SMA_slow[t].

    Only bars up to and including t are evaluated. Future bars are never inspected.
    Returns list of crossover events with bar index and metadata.
    """
    if df is None or len(df) < min_bars:
        return []

    df_calc = compute_smas(df, fast_period, slow_period)
    fast_col = f"SMA{fast_period}"
    slow_col = f"SMA{slow_period}"

    # Drop bars before slow SMA is mature
    # Note: slow_period - 1 is the first index where slow SMA is non-NaN
    events: List[Dict[str, Any]] = []

    # Iterate through chronological bars
    # i represents bar index in df_calc
    closes = df_calc["Close"].values
    fast_vals = df_calc[fast_col].values
    slow_vals = df_calc[slow_col].values
    dates = df_calc.index

    clean_symbol = symbol.replace(".NS", "")

    for i in range(slow_period, len(df_calc)):
        prev_fast = fast_vals[i - 1]
        prev_slow = slow_vals[i - 1]
        curr_fast = fast_vals[i]
        curr_slow = slow_vals[i]

        # Valid numeric check
        if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
            continue

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            events.append({
                "symbol": clean_symbol,
                "raw_symbol": symbol,
                "bar_index": i,
                "date": dates[i],
                "date_str": dates[i].strftime("%Y-%m-%d"),
                "close": round(float(closes[i]), 2),
                f"sma{fast_period}": round(float(curr_fast), 2),
                f"sma{slow_period}": round(float(curr_slow), 2),
            })

    return events


def check_latest_crossover(
    df: pd.DataFrame,
    symbol: str,
    fast_period: int = 30,
    slow_period: int = 50,
    min_bars: int = 55
) -> Optional[Dict[str, Any]]:
    """
    Check if a golden cross occurred on the most recent completed weekly candle.
    Used for live scanner alerts.
    """
    events = find_all_crossovers(
        df=df,
        symbol=symbol,
        fast_period=fast_period,
        slow_period=slow_period,
        min_bars=min_bars
    )
    if not events:
        return None

    # Check if the last detected event occurred on the last candle of df
    last_event = events[-1]
    if last_event["bar_index"] == len(df) - 1:
        return {
            "symbol": last_event["symbol"],
            "week_ending": last_event["date_str"],
            "close": last_event["close"],
            "sma30": last_event[f"sma{fast_period}"],
            "sma50": last_event[f"sma{slow_period}"],
        }

    return None

