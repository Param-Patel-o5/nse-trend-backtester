"""
Trade simulation engine for the weekly SMA30/RSI60 entry, SMA30-cross exit strategy.

Entry  : Close > SMA30 AND RSI(14) > 60
Exit   : Close < SMA30
One open position per symbol at a time.
All logic is strictly causal — bar t only sees data up to bar t.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.signals.strategy import compute_all_indicators, detect_entry, detect_exit


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
    - If no position open and entry condition met → open trade at this bar's close.
    - If position open and exit condition met → close trade at this bar's close.
    - Open trades at end of data are recorded as 'open' (still_open=True).

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
            # Check exit (can fire same bar as entry? No — we entered this bar already)
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

    # Close any open trade at last bar
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
    """Build a complete trade record with return, drawdown, holding period."""
    holding_weeks = exit_idx - entry_idx
    trade_return_pct = ((exit_close - entry_close) / entry_close) * 100.0

    # Sub-window from entry to exit (inclusive)
    win_highs = highs[entry_idx: exit_idx + 1]
    win_lows = lows[entry_idx: exit_idx + 1]
    win_closes = closes[entry_idx: exit_idx + 1]

    # Peak-to-trough max drawdown within trade window
    running_peak = np.maximum.accumulate(win_highs)
    drawdown_series = (win_lows - running_peak) / running_peak * 100.0
    max_drawdown_pct = float(np.min(drawdown_series))

    # +20% milestone: did intra-trade high ever reach entry_close * 1.2?
    milestone_target = entry_close * (1.0 + profit_milestone_pct / 100.0)
    hit_milestone = bool(np.any(win_highs >= milestone_target))

    return {
        "symbol": symbol,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_close": round(entry_close, 2),
        "exit_close": round(exit_close, 2),
        "trade_return_pct": round(trade_return_pct, 2),
        "holding_weeks": holding_weeks,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        f"hit_{int(profit_milestone_pct)}pct_milestone": hit_milestone,
        "still_open": still_open,
    }
