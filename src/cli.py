"""Command-line interface for live scanning and historical backtesting."""

from pathlib import Path
from typing import Optional

import click
import pandas as pd

from src.backtest.engine import run_backtest
from src.data.fetch import fetch_universe_data
from src.data.symbols import get_nifty500_symbols, load_config
from src.signals.strategy import get_live_signals


def print_banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def print_summary_table(summary_df: pd.DataFrame) -> None:
    if summary_df is None or summary_df.empty:
        print("\n[INFO] No trades found — summary is empty.")
        return
    print_banner("NSE TREND BACKTEST SUMMARY REPORT")
    # Transpose for readability when there is only one row
    print(summary_df.T.to_string(header=False))
    print("=" * 72)


@click.group()
def cli():
    """NSE Trend Backtester: Weekly SMA30/RSI60 Strategy Scanner & Engine."""
    pass


# ── scan ───────────────────────────────────────────────────────────────────

@cli.command("scan")
@click.option("--limit", default=None, type=int,
              help="Cap number of symbols to scan (useful for testing)")
@click.option("--force-refresh", is_flag=True, default=False,
              help="Force re-download price data ignoring cache")
def scan_cmd(limit: Optional[int], force_refresh: bool):
    """
    Live weekly scan: flag Nifty 500 symbols meeting entry criteria
    (Close > SMA30 AND RSI(14) > 60) on the latest completed weekly candle.
    Results saved to data/scan_alerts.csv.
    """
    print_banner("NIFTY 500 LIVE ENTRY SIGNAL SCANNER")
    config = load_config()

    sig = config.get("signal", {})
    scan_cfg = config.get("scan", {})
    cache_cfg = config.get("cache", {})

    sma_entry = int(sig.get("sma_entry", 30))
    sma_slow = int(sig.get("sma_slow", 50))
    sma_trend = int(sig.get("sma_trend", 200))
    rsi_period = int(sig.get("rsi_period", 14))
    rsi_sma_period = int(sig.get("rsi_sma_period", 14))
    rsi_threshold = float(sig.get("rsi_entry_threshold", 60.0))
    st_period = int(sig.get("supertrend_period", 10))
    st_mult = float(sig.get("supertrend_multiplier", 3.0))
    min_bars = int(sig.get("min_bars", 215))
    output_csv = scan_cfg.get("output_csv", "data/scan_alerts.csv")

    symbols = get_nifty500_symbols(config, limit=limit)
    print(f"[SCAN] Universe: {len(symbols)} symbols")
    print(f"[SCAN] Entry condition: Close > SMA{sma_entry} AND RSI({rsi_period}) > {rsi_threshold}")

    dfs = fetch_universe_data(
        symbols=symbols,
        period="5y",   # need extra history for SMA200 warm-up
        interval=sig.get("interval", "1wk"),
        cache_dir=cache_cfg.get("cache_dir", "data/cache"),
        max_age_days=1,
        force_refresh=force_refresh,
    )

    hits = []
    for sym, df in dfs.items():
        result = get_live_signals(
            df=df,
            sma_entry=sma_entry,
            sma_slow=sma_slow,
            sma_trend=sma_trend,
            rsi_period=rsi_period,
            rsi_sma_period=rsi_sma_period,
            rsi_threshold=rsi_threshold,
            supertrend_period=st_period,
            supertrend_multiplier=st_mult,
            min_bars=min_bars,
        )
        if result and result["entry_signal"]:
            clean = sym.replace(".NS", "")
            result["symbol"] = clean
            hits.append(result)
            rsi_col = f"RSI{rsi_period}"
            print(f"  [ENTRY] {clean:15s}  Close={result['close']:>10.2f}  "
                  f"SMA{sma_entry}={result.get(f'SMA{sma_entry}'):>10.2f}  "
                  f"RSI={result.get(rsi_col, 'N/A')}")

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    out_df = pd.DataFrame(hits)
    out_df.to_csv(output_csv, index=False)

    if hits:
        print(f"\n[SCAN] {len(hits)} signal(s) found. Saved → {output_csv}")
    else:
        print("\n[SCAN] No entry signals on the latest completed weekly candle.")


# ── backtest ───────────────────────────────────────────────────────────────

@cli.command("backtest")
@click.option("--years", default=3, type=int,
              help="Lookback period in years (default: 3)")
@click.option("--report", is_flag=True, default=False,
              help="Display the most recently saved summary report")
@click.option("--limit", default=None, type=int,
              help="Cap number of symbols — useful for quick smoke-tests")
@click.option("--force-refresh", is_flag=True, default=False,
              help="Ignore cache and re-download all price data")
def backtest_cmd(years: int, report: bool, limit: Optional[int], force_refresh: bool):
    """
    Run or display historical backtest of the weekly SMA30/RSI60 strategy.
    """
    config = load_config()
    summary_csv = config.get("backtest", {}).get(
        "output_summary_csv", "data/backtest_summary.csv"
    )

    if report and Path(summary_csv).exists() and not force_refresh and limit is None:
        print_banner(f"SAVED REPORT — {summary_csv}")
        df = pd.read_csv(summary_csv)
        print_summary_table(df)
        return

    summary_df, events_df, metadata = run_backtest(
        config=config,
        years=years,
        limit=limit,
        force_refresh=force_refresh,
    )
    print_summary_table(summary_df)


if __name__ == "__main__":
    cli()
