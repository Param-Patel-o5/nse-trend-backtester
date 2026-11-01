"""Statistical calculations, performance metrics, and baseline comparisons."""

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def compute_trade_metrics(
    df: pd.DataFrame,
    entry_bar: int,
    horizons: List[int] = [5, 10, 20]
) -> Dict[str, Any]:
    """
    Compute forward returns and max drawdowns for a single crossover entry at entry_bar.
    
    Holding window for horizon H spans bars [entry_bar, entry_bar + H].
    Returns dict containing forward returns and max drawdowns for each horizon.
    If entry_bar + H >= len(df), horizon is marked pending/None.
    """
    n = len(df)
    entry_close = float(df["Close"].iloc[entry_bar])
    metrics: Dict[str, Any] = {}

    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values

    for h in horizons:
        exit_bar = entry_bar + h
        if exit_bar < n:
            exit_close = float(closes[exit_bar])
            ret = (exit_close - entry_close) / entry_close

            # Sub-window from entry_bar to exit_bar
            win_highs = highs[entry_bar : exit_bar + 1]
            win_lows = lows[entry_bar : exit_bar + 1]

            # Peak-to-trough drawdown during the trade window
            running_peak = np.maximum.accumulate(win_highs)
            drawdowns = (win_lows - running_peak) / running_peak
            max_dd = float(np.min(drawdowns))

            # Max adverse excursion from entry price
            mae_from_entry = float(np.min((win_lows - entry_close) / entry_close))

            metrics[f"ret_{h}w"] = round(ret * 100, 2)
            metrics[f"mdd_{h}w"] = round(max_dd * 100, 2)
            metrics[f"mae_{h}w"] = round(mae_from_entry * 100, 2)
            metrics[f"completed_{h}w"] = True
        else:
            metrics[f"ret_{h}w"] = np.nan
            metrics[f"mdd_{h}w"] = np.nan
            metrics[f"mae_{h}w"] = np.nan
            metrics[f"completed_{h}w"] = False

    return metrics


def compute_naive_baseline(
    dfs: Dict[str, pd.DataFrame],
    min_bar: int = 50,
    horizons: List[int] = [5, 10, 20]
) -> Dict[int, Dict[str, float]]:
    """
    Compute naive unconditioned forward returns across all symbols and eligible bars.
    Evaluates: "If you bought on any random week, what is the expected return?"
    """
    baseline_stats: Dict[int, Dict[str, float]] = {}

    for h in horizons:
        returns_h: List[float] = []
        for sym, df in dfs.items():
            if df is None or len(df) < min_bar + h:
                continue
            closes = df["Close"].values
            n = len(closes)
            # Evaluate forward returns for every valid bar j
            for j in range(min_bar, n - h):
                c_entry = closes[j]
                c_exit = closes[j + h]
                if c_entry > 0:
                    returns_h.append(((c_exit - c_entry) / c_entry) * 100)

        if returns_h:
            arr = np.array(returns_h)
            baseline_stats[h] = {
                "sample_size": len(arr),
                "win_rate_pct": round(float(np.mean(arr > 0)) * 100, 2),
                "avg_return_pct": round(float(np.mean(arr)), 2),
                "median_return_pct": round(float(np.median(arr)), 2),
            }
        else:
            baseline_stats[h] = {
                "sample_size": 0,
                "win_rate_pct": 0.0,
                "avg_return_pct": 0.0,
                "median_return_pct": 0.0,
            }

    return baseline_stats


def aggregate_backtest_results(
    events_df: pd.DataFrame,
    baseline_stats: Dict[int, Dict[str, float]],
    horizons: List[int] = [5, 10, 20]
) -> pd.DataFrame:
    """
    Aggregate trade events across all symbols into horizon summary metrics.
    Compares signal performance against naive unconditional baseline.
    """
    rows = []

    for h in horizons:
        col_ret = f"ret_{h}w"
        col_mdd = f"mdd_{h}w"

        if col_ret not in events_df.columns:
            continue

        valid = events_df.dropna(subset=[col_ret])
        n_completed = len(valid)

        if n_completed > 0:
            rets = valid[col_ret].values
            mdds = valid[col_mdd].values

            win_rate = float(np.mean(rets > 0)) * 100
            avg_ret = float(np.mean(rets))
            median_ret = float(np.median(rets))
            avg_mdd = float(np.mean(mdds))
            worst_mdd = float(np.min(mdds))

            base = baseline_stats.get(h, {})
            base_avg = base.get("avg_return_pct", np.nan)
            base_win = base.get("win_rate_pct", np.nan)
            excess_ret = avg_ret - base_avg if not np.isnan(base_avg) else np.nan

            rows.append({
                "Horizon": f"+{h} Weeks",
                "Completed Samples": n_completed,
                "Win Rate (%)": round(win_rate, 2),
                "Avg Return (%)": round(avg_ret, 2),
                "Median Return (%)": round(median_ret, 2),
                "Avg Max DD (%)": round(avg_mdd, 2),
                "Worst Max DD (%)": round(worst_mdd, 2),
                "Baseline Win Rate (%)": round(base_win, 2) if not np.isnan(base_win) else "N/A",
                "Baseline Avg Return (%)": round(base_avg, 2) if not np.isnan(base_avg) else "N/A",
                "Excess Return (%)": round(excess_ret, 2) if not np.isnan(excess_ret) else "N/A",
            })
        else:
            rows.append({
                "Horizon": f"+{h} Weeks",
                "Completed Samples": 0,
                "Win Rate (%)": 0.0,
                "Avg Return (%)": 0.0,
                "Median Return (%)": 0.0,
                "Avg Max DD (%)": 0.0,
                "Worst Max DD (%)": 0.0,
                "Baseline Win Rate (%)": "N/A",
                "Baseline Avg Return (%)": "N/A",
                "Excess Return (%)": "N/A",
            })

    return pd.DataFrame(rows)
