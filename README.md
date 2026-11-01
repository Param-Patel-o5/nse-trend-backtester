# NSE Trend Backtester

A quantitative backtest engine and weekly golden-cross scanner for Indian equities across the Nifty 500 universe.

## Strategy Overview

- **Universe**: Nifty 500 (scraped live from NSE India with local fallback)
- **Timeframe**: Weekly OHLC candles (`interval="1wk"`)
- **Signal**: 30-period SMA crossing above 50-period SMA (Golden Cross)
- **Causality**: Strictly avoids look-ahead bias — signals at week $t$ evaluate moving averages computed exclusively on bars $\le t$
- **Horizons**: Multi-horizon forward returns evaluated at +5, +10, and +20 weekly candles
- **Baseline**: Benchmarked against unconditional random weekly forward returns (market drift) across the entire universe

---

## Project Structure

```
├── config/
│   └── settings.yaml          # Strategy settings, SMA windows, horizons, paths
├── data/
│   ├── cache/                 # Local weekly OHLC data cache (gitignored)
│   ├── ind_nifty500list.csv   # Offline Nifty 500 fallback symbol list
│   ├── backtest_events.csv    # Trade-by-trade log with returns & drawdowns
│   ├── backtest_summary.csv   # Aggregated performance summary table
│   └── golden_cross_alerts.csv# Latest live weekly scan output
├── src/
│   ├── backtest/
│   │   ├── engine.py          # Backtest orchestrator
│   │   └── metrics.py         # Forward returns, drawdown, win rate & baseline math
│   ├── data/
│   │   ├── fetch.py           # yfinance batch downloader with disk caching
│   │   └── symbols.py         # NSE Nifty 500 list scraper
│   ├── signals/
│   │   └── sma_crossover.py   # Causal SMA calculation & crossover detector
│   └── cli.py                 # Command-line interface
├── requirements.txt           # Pinned dependencies
└── .gitignore
```

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Usage

### 1. Historical Backtest
Run full 3-year historical backtest across the Nifty 500 universe:
```bash
python -m src.cli backtest --years 3
```

Display saved report from the latest run:
```bash
python -m src.cli backtest --report
```

### 2. Live Weekly Scanner
Scan the universe for stocks triggering a golden cross on the latest completed weekly candle:
```bash
python -m src.cli scan
```
Results are printed to console and saved to `data/golden_cross_alerts.csv`.
