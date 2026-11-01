"""Historical price data downloader and local disk cache manager."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf


def get_cache_path(cache_dir: Path, symbol: str) -> Path:
    """Return local cache CSV path for a symbol."""
    safe_symbol = symbol.replace("/", "_").replace("\\", "_")
    return cache_dir / f"{safe_symbol}.csv"


def is_cache_valid(cache_path: Path, max_age_days: int = 3) -> bool:
    """Check if cache file exists, is non-empty, and within max_age_days."""
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        return False
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    return age.total_seconds() < max_age_days * 86400


def clean_dataframe(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Ensure standard OHLC format and sort ascending by date."""
    if df is None or df.empty:
        return None

    # Handle MultiIndex if present
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten multiindex if needed
        if "Close" in df.columns.levels[0]:
            df = df.droplevel(1, axis=1)

    required_cols = ["Open", "High", "Low", "Close"]
    for col in required_cols:
        if col not in df.columns:
            return None

    df = df.dropna(subset=required_cols).copy()
    if df.empty:
        return None

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    # Remove duplicate timestamps if any
    df = df[~df.index.duplicated(keep="last")]
    return df


def fetch_symbol_from_cache(cache_path: Path) -> Optional[pd.DataFrame]:
    """Read cached OHLC dataframe from CSV."""
    try:
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        return clean_dataframe(df)
    except Exception:
        return None


def save_symbol_to_cache(cache_path: Path, df: pd.DataFrame) -> None:
    """Save cleaned OHLC dataframe to CSV cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path)


def fetch_universe_data(
    symbols: List[str],
    period: str = "3y",
    interval: str = "1wk",
    cache_dir: str = "data/cache",
    max_age_days: int = 3,
    force_refresh: bool = False,
    batch_size: int = 40,
) -> Dict[str, pd.DataFrame]:
    """
    Fetch weekly OHLC data for universe with local caching.
    Downloads missing or expired symbols in batches to respect rate limits.
    Returns dictionary mapping symbol -> DataFrame.
    """
    c_dir = Path(cache_dir)
    c_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, pd.DataFrame] = {}
    missing_symbols: List[str] = []

    # 1. Check local cache
    for sym in symbols:
        c_path = get_cache_path(c_dir, sym)
        if not force_refresh and is_cache_valid(c_path, max_age_days):
            df = fetch_symbol_from_cache(c_path)
            if df is not None and not df.empty:
                results[sym] = df
                continue
        missing_symbols.append(sym)

    if missing_symbols:
        print(
            f"[INFO] Fetching {len(missing_symbols)} symbols via yfinance "
            f"(cached: {len(results)}/{len(symbols)})..."
        )
        total_batches = (len(missing_symbols) + batch_size - 1) // batch_size
        for b_idx in range(total_batches):
            batch = missing_symbols[b_idx * batch_size : (b_idx + 1) * batch_size]
            print(
                f"  Batch {b_idx + 1}/{total_batches} ({len(batch)} symbols)...",
                end="",
                flush=True,
            )
            t0 = time.time()
            try:
                if len(batch) == 1:
                    raw = yf.download(
                        batch[0],
                        period=period,
                        interval=interval,
                        progress=False,
                        auto_adjust=True,
                    )
                    cleaned = clean_dataframe(raw)
                    if cleaned is not None:
                        results[batch[0]] = cleaned
                        save_symbol_to_cache(get_cache_path(c_dir, batch[0]), cleaned)
                else:
                    raw = yf.download(
                        batch,
                        period=period,
                        interval=interval,
                        progress=False,
                        auto_adjust=True,
                        group_by="ticker",
                        threads=True,
                    )
                    for sym in batch:
                        try:
                            if sym in raw.columns.levels[0]:
                                sym_df = raw[sym].copy()
                                cleaned = clean_dataframe(sym_df)
                                if cleaned is not None and len(cleaned) > 0:
                                    results[sym] = cleaned
                                    save_symbol_to_cache(
                                        get_cache_path(c_dir, sym), cleaned
                                    )
                        except Exception:
                            pass
                print(f" done ({time.time() - t0:.1f}s)")
            except Exception as e:
                print(f" error: {e}")

            # Brief pause between batches
            if b_idx < total_batches - 1:
                time.sleep(0.5)

    return results
