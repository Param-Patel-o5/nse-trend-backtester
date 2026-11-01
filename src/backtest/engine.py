"""
Backtest engine: orchestrates data loading, indicator computation,
trade simulation, and result aggregation.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.backtest.metrics import aggregate_trades, compute_naive_baseline
from src.backtest.trades import simulate_trades
from src.data.fetch import fetch_universe_data
from src.data.symbols import get_nifty500_symbols, load_config
from src.signals.strategy import compute_all_indicators


def run_backtest(
    config: Optional[Dict[str, Any]] = None,
    years: int = 3,
    limit: Optional[int] = None,
    force_refresh: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Run full historical backtest.

    Returns
    -------
    summary_df   : single-row aggregate stats
    events_df    : trade-by-trade log
    metadata     : run info dict
    """
    if config is None:
        config = load_config()

    sig = config.get("signal", {})
    bt = config.get("backtest", {})
    cache = config.get("cache", {})

    sma_entry = int(sig.get("sma_entry", 30))
    sma_slow = int(sig.get("sma_slow", 50))
    sma_trend = int(sig.get("sma_trend", 200))
    rsi_period = int(sig.get("rsi_period", 14))
    rsi_sma_period = int(sig.get("rsi_sma_period", 14))
    rsi_threshold = float(sig.get("rsi_entry_threshold", 60.0))
    st_period = int(sig.get("supertrend_period", 10))
    st_mult = float(sig.get("supertrend_multiplier", 3.0))
    min_bars = int(sig.get("min_bars", 215))
    interval = sig.get("interval", "1wk")

    profit_milestone = float(bt.get("profit_milestone_pct", 20.0))
    events_csv = bt.get("output_events_csv", "data/backtest_events.csv")
    summary_csv = bt.get("output_summary_csv", "data/backtest_summary.csv")
    period_str = f"{years}y"

    # ── 1. Load symbols ────────────────────────────────────────────────────
    symbols = get_nifty500_symbols(config, limit=limit)
    print(f"\n[BACKTEST] Universe: {len(symbols)} symbols | Lookback: {period_str} | {interval}")
    print(f"[BACKTEST] Entry: Close > SMA{sma_entry} AND RSI({rsi_period}) > {rsi_threshold}")
    print(f"[BACKTEST] Exit : Close < SMA{sma_entry}")

    # ── 2. Fetch price data ────────────────────────────────────────────────
    dfs = fetch_universe_data(
        symbols=symbols,
        period=period_str,
        interval=interval,
        cache_dir=cache.get("cache_dir", "data/cache"),
        max_age_days=int(cache.get("max_cache_age_days", 3)),
        force_refresh=force_refresh,
    )

    valid_dfs: Dict[str, pd.DataFrame] = {}
    skipped = 0
    for sym, df in dfs.items():
        if df is not None and len(df) >= min_bars:
            valid_dfs[sym] = df
        else:
            skipped += 1

    print(f"[BACKTEST] Symbols with >= {min_bars} bars: {len(valid_dfs)} "
          f"(skipped/insufficient: {skipped})")

    # ── 3. Compute indicators + simulate trades ────────────────────────────
    all_trades: List[Dict[str, Any]] = []

    for sym, df in valid_dfs.items():
        try:
            df_ind = compute_all_indicators(
                df,
                sma_entry=sma_entry,
                sma_slow=sma_slow,
                sma_trend=sma_trend,
                rsi_period=rsi_period,
                rsi_sma_period=rsi_sma_period,
                supertrend_period=st_period,
                supertrend_multiplier=st_mult,
            )
            trades = simulate_trades(
                df_ind=df_ind,
                symbol=sym.replace(".NS", ""),
                sma_entry=sma_entry,
                rsi_period=rsi_period,
                rsi_threshold=rsi_threshold,
                profit_milestone_pct=profit_milestone,
            )
            all_trades.extend(trades)
        except Exception as e:
            print(f"  [WARN] {sym}: {e}")

    events_df = pd.DataFrame(all_trades)
    print(f"[BACKTEST] Total trades simulated: {len(events_df)}")

    # ── 4. Naive baseline ──────────────────────────────────────────────────
    avg_hold = float(events_df["holding_weeks"].mean()) if not events_df.empty else 10.0
    print(f"[BACKTEST] Avg holding period: {avg_hold:.1f} weeks — computing baseline...")
    baseline = compute_naive_baseline(
        dfs=valid_dfs,
        avg_holding_weeks=avg_hold,
        sma_min_bars=sma_entry,
    )

    # ── 5. Aggregate summary ───────────────────────────────────────────────
    if not events_df.empty:
        summary_df = aggregate_trades(events_df, baseline, profit_milestone)
    else:
        summary_df = pd.DataFrame()

    # ── 6. Persist CSVs ───────────────────────────────────────────────────
    Path(events_csv).parent.mkdir(parents=True, exist_ok=True)
    events_df.to_csv(events_csv, index=False)
    summary_df.to_csv(summary_csv, index=False)
    print(f"[BACKTEST] Saved events  -> {events_csv}")
    print(f"[BACKTEST] Saved summary -> {summary_csv}")

    metadata = {
        "symbols_requested": len(symbols),
        "symbols_processed": len(valid_dfs),
        "symbols_skipped": skipped,
        "total_trades": len(events_df),
        "avg_hold_weeks": round(avg_hold, 1),
        "baseline": baseline,
        "years": years,
    }
    return summary_df, events_df, metadata
