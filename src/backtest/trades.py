"""
Trade simulation engine for the weekly SMA30/RSI60 entry, SMA30-cross exit strategy.

Entry  : Close > SMA30 AND RSI(14) > 60
Exit   : Close < SMA30
One open position per symbol at a time.
All logic is strictly causal — bar t only sees data up to bar t.
"""

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.signals.strategy import detect_entry, detect_exit


def simulate_trades(
    df_ind: pd.DataFrame,
    symbol: str,
    sma_entry: int = 30,
    rsi_period: int = 14,
    rsi_threshold: float = 60.0,
    profit_milestone_pct: float = 20.0,
) -> List[Dict[str, Any]]:
    """
    Simulate all trades for a single symbol on a pre-computed indicator DataFrame.

    Walk bar-by-bar in chronological order:
    - If no position open and entry condition met -> open trade at this bar's close.
    - If position open and exit condition met -> close trade at this bar's close.
    - Open trades at end of data are recorded with still_open=True.

    Returns list of trade dicts.
    """
    trades: List[Dict[str, Any]] = []
    in_trade = False
    entry_bar_idx: Optional[int] = None
    entry_close: float = 0.0
    entry_date: str = ""

    closes = df_ind["Close"].values
    highs = df_ind["High"].values
    lows = df_ind["Low"].values
    dates = df_ind.index

    n = len(df_ind)

    for i in range(n):
        row = df_ind.iloc[i]

        if not in_trade:
            if detect_entry(row, sma_entry, rsi_period, rsi_threshold):
                in_trade = True
                entry_bar_idx = i
                entry_close = float(closes[i])
                entry_date = dates[i].strftime("%Y-%m-%d")
        else:
            # Check exit condition on bar i
            if detect_exit(row, sma_entry):
                exit_close = float(closes[i])
                exit_date = dates[i].strftime("%Y-%m-%d")
                trade = _build_trade(
                    symbol=symbol,
                    entry_date=entry_date,
                    exit_date=exit_date,
                    entry_close=entry_close,
                    exit_close=exit_close,
                    entry_idx=entry_bar_idx,
                    exit_idx=i,
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    profit_milestone_pct=profit_milestone_pct,
                    still_open=False,
                )
                trades.append(trade)
                in_trade = False
                entry_bar_idx = None

    # Record any trade still active at the final bar of the dataset
    if in_trade and entry_bar_idx is not None:
        i = n - 1
        exit_close = float(closes[i])
        exit_date = dates[i].strftime("%Y-%m-%d")
        trade = _build_trade(
            symbol=symbol,
            entry_date=entry_date,
            exit_date=exit_date,
            entry_close=entry_close,
            exit_close=exit_close,
            entry_idx=entry_bar_idx,
            exit_idx=i,
            highs=highs,
            lows=lows,
            closes=closes,
            profit_milestone_pct=profit_milestone_pct,
            still_open=True,
        )
        trades.append(trade)

    return trades


def _build_trade(
    symbol: str,
    entry_date: str,
    exit_date: str,
    entry_close: float,
    exit_close: float,
    entry_idx: int,
    exit_idx: int,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    profit_milestone_pct: float,
    still_open: bool,
) -> Dict[str, Any]:
    """
    Build a complete trade record with return, drawdown, and holding period.
    
    Drawdown starts strictly from entry_close (avoiding entry-bar retrospective low):
    - Peak begins at entry_close, updating with post-entry highs.
    - Intra-week max drawdown measures (low - peak) / peak.
    - Close-to-close max drawdown measures (close - peak_close) / peak_close.
    """
    holding_weeks = exit_idx - entry_idx
    trade_return_pct = ((exit_close - entry_close) / entry_close) * 100.0

    if holding_weeks > 0:
        post_highs = highs[entry_idx + 1 : exit_idx + 1]
        post_lows = lows[entry_idx + 1 : exit_idx + 1]
        post_closes = closes[entry_idx + 1 : exit_idx + 1]

        # Intra-week Peak-to-Trough Drawdown
        # Peak equity sequence: starts with entry_close, accumulates post-entry highs
        peaks = np.maximum.accumulate(np.insert(post_highs, 0, entry_close))
        running_peaks = peaks[1:]  # alignment with post_lows
        drawdown_series = (post_lows - running_peaks) / running_peaks * 100.0
        max_drawdown_pct = float(np.min(drawdown_series))

        # Close-to-Close Drawdown
        close_peaks = np.maximum.accumulate(np.insert(post_closes, 0, entry_close))
        running_close_peaks = close_peaks[1:]
        close_dd_series = (post_closes - running_close_peaks) / running_close_peaks * 100.0
        max_close_dd_pct = float(np.min(close_dd_series))

        # +20% milestone: did post-entry high ever reach entry_close * 1.20?
        milestone_target = entry_close * (1.0 + profit_milestone_pct / 100.0)
        hit_milestone = bool(np.any(post_highs >= milestone_target))
    else:
        max_drawdown_pct = 0.0
        max_close_dd_pct = 0.0
        hit_milestone = False

    return {
        "symbol": symbol,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_close": round(entry_close, 2),
        "exit_close": round(exit_close, 2),
        "trade_return_pct": round(trade_return_pct, 2),
        "holding_weeks": holding_weeks,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "max_close_drawdown_pct": round(max_close_dd_pct, 2),
        f"hit_{int(profit_milestone_pct)}pct_milestone": hit_milestone,
        "still_open": still_open,
    }
