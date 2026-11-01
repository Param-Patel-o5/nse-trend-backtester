"""
Aggregation and naive-baseline metrics for the strategy backtest.
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
    Aggregate trade-level records into a single-row summary DataFrame.
    Includes comparison to naive unconditional baseline.
    """
    if events_df.empty:
        return pd.DataFrame()

    rets = events_df["trade_return_pct"].values
    mdd = events_df["max_drawdown_pct"].values
    holding = events_df["holding_weeks"].values

    milestone_col = f"hit_{int(profit_milestone_pct)}pct_milestone"
    milestone_rate = (
        events_df[milestone_col].sum() / len(events_df) * 100.0
        if milestone_col in events_df.columns
        else np.nan
    )

    still_open = int(events_df["still_open"].sum()) if "still_open" in events_df.columns else 0

    avg_ret = float(np.mean(rets))
    baseline_avg = baseline.get("baseline_avg_return_pct", np.nan)
    excess = round(avg_ret - baseline_avg, 2) if not np.isnan(baseline_avg) else np.nan

    summary = {
        "Total Trades": len(events_df),
        "Closed Trades": len(events_df) - still_open,
        "Still Open (at end of data)": still_open,
        "Win Rate (%)": round(float(np.mean(rets > 0)) * 100, 2),
        "Avg Trade Return (%)": round(avg_ret, 2),
        "Median Trade Return (%)": round(float(np.median(rets)), 2),
        "Avg Holding Period (weeks)": round(float(np.mean(holding)), 1),
        "Median Holding Period (weeks)": round(float(np.median(holding)), 1),
        "Avg Max Drawdown (%)": round(float(np.mean(mdd)), 2),
        "Worst Max Drawdown (%)": round(float(np.min(mdd)), 2),
        f"Hit +{int(profit_milestone_pct)}% Milestone (%)": round(milestone_rate, 2),
        "Baseline Win Rate (%)": baseline.get("baseline_win_rate_pct", np.nan),
        "Baseline Avg Return (%)": baseline_avg,
        "Excess Return vs Baseline (%)": excess,
    }

    return pd.DataFrame([summary])
