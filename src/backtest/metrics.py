"""
Aggregation and naive-baseline metrics for the strategy backtest.
Strictly separates realized closed trades from unrealized open positions.
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def compute_naive_baseline(
    dfs: Dict[str, pd.DataFrame],
    avg_holding_weeks: float,
    sma_min_bars: int = 30,
) -> Dict[str, Any]:
    """
    Naive baseline: average return of holding any stock unconditionally
    for `avg_holding_weeks` weeks, starting from any eligible bar.

    'Eligible bar' = bar has at least `avg_holding_weeks` future bars remaining.
    """
    h = max(1, round(avg_holding_weeks))
    returns: List[float] = []

    for sym, df in dfs.items():
        if df is None or len(df) < sma_min_bars + h:
            continue
        closes = df["Close"].values
        n = len(closes)
        for j in range(sma_min_bars, n - h):
            c_entry = closes[j]
            c_exit = closes[j + h]
            if c_entry > 0:
                returns.append((c_exit - c_entry) / c_entry * 100.0)

    if not returns:
        return {
            "baseline_sample_size": 0,
            "baseline_win_rate_pct": np.nan,
            "baseline_avg_return_pct": np.nan,
            "baseline_median_return_pct": np.nan,
        }

    arr = np.array(returns)
    return {
        "baseline_sample_size": len(arr),
        "baseline_win_rate_pct": round(float(np.mean(arr > 0)) * 100, 2),
        "baseline_avg_return_pct": round(float(np.mean(arr)), 2),
        "baseline_median_return_pct": round(float(np.median(arr)), 2),
    }


def aggregate_trades(
    events_df: pd.DataFrame,
    baseline: Dict[str, Any],
    profit_milestone_pct: float = 20.0,
) -> pd.DataFrame:
    """
    Aggregate trade-level records into a structured summary DataFrame.
    Strictly isolates realized closed trades from unrealized open positions.
    """
    if events_df.empty:
        return pd.DataFrame()

    closed_df = events_df[events_df["still_open"] == False]
    open_df = events_df[events_df["still_open"] == True]

    milestone_col = f"hit_{int(profit_milestone_pct)}pct_milestone"

    summary: Dict[str, Any] = {
        "Total Trades Evaluated": len(events_df),
        "Closed Trades (Realized)": len(closed_df),
        "Open Trades (Unrealized)": len(open_df),
    }

    # ── Realized Closed Trades ─────────────────────────────────────────────
    if not closed_df.empty:
        rets = closed_df["trade_return_pct"].values
        mdd = closed_df["max_drawdown_pct"].values
        mdd_close = closed_df["max_close_drawdown_pct"].values if "max_close_drawdown_pct" in closed_df.columns else mdd
        holding = closed_df["holding_weeks"].values

        avg_ret = float(np.mean(rets))
        baseline_avg = baseline.get("baseline_avg_return_pct", np.nan)
        excess = round(avg_ret - baseline_avg, 2) if not np.isnan(baseline_avg) else np.nan

        closed_milestone = (
            closed_df[milestone_col].sum() / len(closed_df) * 100.0
            if milestone_col in closed_df.columns
            else np.nan
        )

        summary.update({
            "Closed: Win Rate (%)": round(float(np.mean(rets > 0)) * 100, 2),
            "Closed: Avg Trade Return (%)": round(avg_ret, 2),
            "Closed: Median Trade Return (%)": round(float(np.median(rets)), 2),
            "Closed: Avg Holding Period (weeks)": round(float(np.mean(holding)), 1),
            "Closed: Median Holding Period (weeks)": round(float(np.median(holding)), 1),
            "Closed: Avg Max Drawdown (%)": round(float(np.mean(mdd)), 2),
            "Closed: Worst Max Drawdown (%)": round(float(np.min(mdd)), 2),
            "Closed: Avg Close-to-Close DD (%)": round(float(np.mean(mdd_close)), 2),
            f"Closed: Hit +{int(profit_milestone_pct)}% Milestone (%)": round(closed_milestone, 2),
            "Baseline: Holding Window (weeks)": round(float(np.mean(holding)), 1),
            "Baseline: Win Rate (%)": baseline.get("baseline_win_rate_pct", np.nan),
            "Baseline: Avg Return (%)": baseline_avg,
            "Excess Return vs Baseline (%)": excess,
        })

    # ── Unrealized Open Trades (Separate reporting) ────────────────────────
    if not open_df.empty:
        open_rets = open_df["trade_return_pct"].values
        open_mdd = open_df["max_drawdown_pct"].values
        open_holding = open_df["holding_weeks"].values

        open_milestone = (
            open_df[milestone_col].sum() / len(open_df) * 100.0
            if milestone_col in open_df.columns
            else np.nan
        )

        summary.update({
            "Open: Unrealized Win Rate (%)": round(float(np.mean(open_rets > 0)) * 100, 2),
            "Open: Avg Unrealized Return (%)": round(float(np.mean(open_rets)), 2),
            "Open: Median Unrealized Return (%)": round(float(np.median(open_rets)), 2),
            "Open: Avg Holding so far (weeks)": round(float(np.mean(open_holding)), 1),
            "Open: Avg Max Drawdown (%)": round(float(np.mean(open_mdd)), 2),
            f"Open: Hit +{int(profit_milestone_pct)}% Milestone (%)": round(open_milestone, 2),
        })

    return pd.DataFrame([summary])
