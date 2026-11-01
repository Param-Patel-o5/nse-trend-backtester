"""Symbol retrieval and universe loading."""

import os
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from settings YAML file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_nifty500_symbols(
    config: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None
) -> List[str]:
    """
    Fetch Nifty 500 symbol list from NSE India or fall back to local CSV.
    Returns list of Yahoo-compatible ticker symbols (e.g. ['RELIANCE.NS', ...]).
    """
    if config is None:
        config = load_config()

    univ_cfg = config.get("universe", {})
    url = univ_cfg.get("csv_url", "https://archives.nseindia.com/content/indices/ind_nifty500list.csv")
    fallback_path = univ_cfg.get("fallback_csv", "data/ind_nifty500list.csv")
    suffix = univ_cfg.get("symbol_suffix", ".NS")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    symbols: List[str] = []
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        col = "Symbol" if "Symbol" in df.columns else df.columns[2]
        symbols = [str(s).strip() + suffix for s in df[col].dropna().tolist()]
    except Exception as e:
        print(f"[WARNING] NSE symbol download failed ({e}). Attempting fallback...")
        alt_paths = [
            Path(fallback_path),
            Path("data/ind_nifty500list.csv"),
            Path("ind_nifty500list.csv"),
        ]
        found = False
        for p in alt_paths:
            if p.exists():
                df = pd.read_csv(p)
                col = "Symbol" if "Symbol" in df.columns else df.columns[0]
                symbols = [str(s).strip() + suffix for s in df[col].dropna().tolist()]
                print(f"[INFO] Loaded {len(symbols)} symbols from fallback file: {p}")
                found = True
                break
        if not found:
            raise RuntimeError(
                f"Could not load Nifty 500 symbols from NSE or fallback file ({fallback_path})."
            )

    cfg_limit = limit if limit is not None else univ_cfg.get("limit")
    if cfg_limit and isinstance(cfg_limit, int) and cfg_limit > 0:
        symbols = symbols[:cfg_limit]

    return symbols
