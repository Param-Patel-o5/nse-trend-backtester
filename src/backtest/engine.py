"""Backtest engine orchestrating data loading, signal generation, and performance aggregation."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.backtest.metrics import (
    aggregate_backtest_results,
    compute_naive_baseline,
    compute_trade_metrics,
)
from src.data.fetch import fetch_universe_data
from src.data.symbols import get_nifty500_symbols, load_config
from src.signals.sma_crossover import find_all_crossovers


def run_backtest(
    config: Optional[Dict[str, Any]] = None,
    years: int = 3,
    limit: Optional[int] = None,
    force_refresh: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Run historical backtest of weekly SMA crossover across universe.
    Returns (summary_df, events_df, run_metadata).
    """
    if config is None:
        config = load_config()

    sig_cfg = config.get("signal", {})
    bt_cfg = config.get("backtest", {})
    cache_cfg = config.get("cache", {})

    fast_sma = int(sig_cfg.get("fast_sma", 30))
    slow_sma = int(sig_cfg.get("slow_sma", 50))
    min_bars = int(sig_cfg.get("min_bars", 55))
    interval = sig_cfg.get("interval", "1wk")
    horizons: List[int] = bt_cfg.get("horizons", [5, 10, 20])
    period = f"{years}y"

    cache_dir = cache_cfg.get("cache_dir", "data/cache")
    max_cache_age_days = int(cache_cfg.get("max_cache_age_days", 3))

    events_csv = bt_cfg.get("output_events_csv", "data/backtest_events.csv")
    summary_csv = bt_cfg.get("output_summary_csv", "data/backtest_summary.csv")

    # 1. Fetch universe symbols
    symbols = get_nifty500_symbols(config, limit=limit)
    print(f"\n[BACKTEST] Universe: {len(symbols)} symbols | Lookback: {period} | Interval: {interval}")
    print(f"[BACKTEST] Strategy: SMA({fast_sma}) Golden Cross over SMA({slow_sma}) | Horizons: +{horizons} weeks")

    # 2. Fetch price data
    dfs = fetch_universe_data(
        symbols=symbols,
        period=period,
        interval=interval,
        cache_dir=cache_dir,
        max_age_days=max_cache_age_days,
        force_refresh=force_refresh,
    )

    valid_dfs: Dict[str, pd.DataFrame] = {}
    skipped_count = 0

    for sym, df in dfs.items():
        if df is not None and len(df) >= min_bars:
            valid_dfs[sym] = df
        else:
            skipped_count += 1

    print(
        f"[BACKTEST] Clean symbols with >= {min_bars} weekly bars: {len(valid_dfs)} "
        f"(skipped/insufficient: {skipped_count})"
    )

    # 3. Find historical crossovers and compute forward returns
    all_events: List[Dict[str, Any]] = []

    for sym, df in valid_dfs.items():
        cross_events = find_all_crossovers(
            df=df,
            symbol=sym,
            fast_period=fast_sma,
            slow_period=slow_sma,
            min_bars=min_bars,
        )
        for ev in cross_events:
            entry_bar = ev["bar_index"]
            metrics = compute_trade_metrics(df, entry_bar=entry_bar, horizons=horizons)
            record = {
                "symbol": ev["symbol"],
                "crossover_date": ev["date_str"],
                "entry_close": ev["close"],
                f"sma{fast_sma}": ev[f"sma{fast_sma}"],
                f"sma{slow_sma}": ev[f"sma{slow_sma}"],
            }
            record.update(metrics)
            all_events.append(record)

    events_df = pd.DataFrame(all_events)
    total_events = len(events_df)
    print(f"[BACKTEST] Total golden-cross crossover events found: {total_events}")

    # 4. Compute naive baseline across universe
    print("[BACKTEST] Computing unconditioned naive baseline forward returns...")
    baseline_stats = compute_naive_baseline(
        dfs=valid_dfs,
        min_bar=slow_sma,
        horizons=horizons,
    )

    # 5. Aggregate summary stats
    if not events_df.empty:
        summary_df = aggregate_backtest_results(
            events_df=events_df,
            baseline_stats=baseline_stats,
            horizons=horizons,
        )
    else:
        summary_df = pd.DataFrame()

    # 6. Save results to CSV
    Path(events_csv).parent.mkdir(parents=True, exist_ok=True)
    Path(summary_csv).parent.mkdir(parents=True, exist_ok=True)

    events_df.to_csv(events_csv, index=False)
    summary_df.to_csv(summary_csv, index=False)

    metadata = {
        "symbols_requested": len(symbols),
        "symbols_processed": len(valid_dfs),
        "symbols_skipped": skipped_count,
        "total_crossovers": total_events,
        "years": years,
        "fast_sma": fast_sma,
        "slow_sma": slow_sma,
        "horizons": horizons,
        "baseline_stats": baseline_stats,
    }

    return summary_df, events_df, metadata
