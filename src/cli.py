"""Command-line interface for live scanning and historical backtesting."""

import os
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
import pandas as pd

from src.alerts.telegram import format_scan_message, send_telegram_alert
from src.backtest.engine import run_backtest
from src.data.fetch import fetch_universe_data
from src.data.symbols import get_nifty500_symbols, load_config
from src.signals.sma_crossover import check_latest_crossover

# Load environment variables (.env)
load_dotenv()


def print_banner(title: str) -> None:
    """Print standard section banner."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def print_summary_table(summary_df: pd.DataFrame) -> None:
    """Print clean formatted summary table."""
    if summary_df.empty:
        print("\n[INFO] No crossover events found or summary is empty.")
        return

    print_banner("QUANT SIGNAL BACKTEST SUMMARY REPORT")
    print(summary_df.to_string(index=False))
    print("=" * 70)


@click.group()
def cli():
    """Quant Signal Backtester: Weekly SMA Crossover Scanner & Engine."""
    pass


@cli.command("scan")
@click.option("--limit", default=None, type=int, help="Limit number of symbols to scan")
@click.option("--force-refresh", is_flag=True, default=False, help="Force re-download price data")
def scan_cmd(limit: Optional[int], force_refresh: bool):
    """
    Live weekly scan: check which symbols triggered a golden cross (SMA30 > SMA50)
    in the latest completed weekly candle.
    """
    print_banner("NIFTY 500 WEEKLY GOLDEN-CROSS SCANNER")
    config = load_config()

    sig_cfg = config.get("signal", {})
    scan_cfg = config.get("scan", {})
    cache_cfg = config.get("cache", {})

    fast_sma = int(sig_cfg.get("fast_sma", 30))
    slow_sma = int(sig_cfg.get("slow_sma", 50))
    min_bars = int(sig_cfg.get("min_bars", 55))
    output_csv = scan_cfg.get("output_csv", "data/golden_cross_alerts.csv")

    symbols = get_nifty500_symbols(config, limit=limit)
    print(f"[SCAN] Universe loaded: {len(symbols)} symbols")

    dfs = fetch_universe_data(
        symbols=symbols,
        period="2y",
        interval=sig_cfg.get("interval", "1wk"),
        cache_dir=cache_cfg.get("cache_dir", "data/cache"),
        max_age_days=1,
        force_refresh=force_refresh,
    )

    alerts = []
    for sym, df in dfs.items():
        if df is None or len(df) < min_bars:
            continue
        res = check_latest_crossover(
            df=df,
            symbol=sym,
            fast_period=fast_sma,
            slow_period=slow_sma,
            min_bars=min_bars,
        )
        if res:
            alerts.append(res)
            print(f"  [+] Golden Cross Detected: {res['symbol']} (Close: {res['close']})")

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    if alerts:
        out_df = pd.DataFrame(alerts)
        out_df.to_csv(output_csv, index=False)
        print(f"\n[SCAN] Found {len(alerts)} crossover(s). Saved to: {output_csv}\n")
        print(out_df.to_string(index=False))

        msg = format_scan_message(alerts, fast_sma=fast_sma, slow_sma=slow_sma)
        send_telegram_alert(message=msg)
    else:
        print(f"\n[SCAN] No symbols triggered a golden cross in the latest week.")
        pd.DataFrame(columns=["symbol", "week_ending", "close", "sma30", "sma50"]).to_csv(
            output_csv, index=False
        )


@cli.command("backtest")
@click.option("--years", default=3, type=int, help="Historical lookback period in years (default: 3)")
@click.option("--report", is_flag=True, default=False, help="Display existing backtest report if available")
@click.option("--limit", default=None, type=int, help="Limit number of symbols (for rapid testing)")
@click.option("--force-refresh", is_flag=True, default=False, help="Force refresh downloaded price data")
def backtest_cmd(years: int, report: bool, limit: Optional[int], force_refresh: bool):
    """
    Run historical backtest across Nifty 500 universe or display latest summary report.
    """
    config = load_config()
    summary_csv = config.get("backtest", {}).get(
        "output_summary_csv", "data/backtest_summary.csv"
    )

    if report and Path(summary_csv).exists() and not force_refresh and limit is None:
        print_banner(f"LOADING SAVED REPORT ({summary_csv})")
        df_summary = pd.read_csv(summary_csv)
        print_summary_table(df_summary)
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

