# NSE Trend Backtester

A quantitative backtest engine and live weekly scanner for Indian equities
across the Nifty 500 universe, using a momentum-filtered long-only strategy.

---

## Strategy Overview

| Parameter | Value |
|---|---|
| Timeframe | Weekly candles |
| Universe | Nifty 500 |
| Position type | Long only |
| Entry: SMA | 30-week Simple Moving Average |
| Entry: RSI threshold | RSI(14) > 60 |
| Exit | Close drops below 30-week SMA |

### Indicators computed per symbol

| Indicator | Parameters | Role |
|---|---|---|
| SMA 30 | 30 weeks | Entry trigger & exit gate |
| SMA 50 | 50 weeks | Stored for reference |
| SMA 200 | 200 weeks | Trend context (populated from 5y scan data) |
| RSI | 14 weeks, Wilder smoothing | Entry confirmation |
| RSI SMA overlay | 14 weeks | Reference |
| SuperTrend | Period 10, multiplier 3.0 | Stored for reference |

### Entry (Buy)
Both must be true on the same weekly close:
1. **Close > SMA30**
2. **RSI(14) > 60** (strictly above)

Only one open position per symbol at a time — new entry signals are ignored while a position is already active.

### Exit (Sell)
- **Close < SMA30**

### No-Look-Ahead Guarantee
At every bar *t*, all indicators and signals are computed using only data up to and including bar *t*. No future bars are ever referenced.

---

## Project Structure

```
├── config/
│   └── settings.yaml           # Strategy params (SMA windows, RSI threshold, SuperTrend, etc.)
├── data/
│   ├── cache/                  # Local weekly OHLC cache (gitignored)
│   ├── ind_nifty500list.csv    # Offline Nifty 500 fallback symbol list
│   ├── backtest_events.csv     # Trade-by-trade log (gitignored)
│   ├── backtest_summary.csv    # Aggregated performance table (gitignored)
│   └── scan_alerts.csv         # Latest live scan output (gitignored)
├── src/
│   ├── backtest/
│   │   ├── engine.py           # Backtest orchestrator
│   │   ├── metrics.py          # Aggregation & naive-baseline math (strictly separates closed vs open)
│   │   └── trades.py           # Trade simulator (post-entry drawdown & milestone tracking)
│   ├── data/
│   │   ├── fetch.py            # yfinance batch downloader with disk caching
│   │   └── symbols.py          # NSE Nifty 500 list scraper
│   ├── signals/
│   │   └── strategy.py         # Causal SMA, RSI, SuperTrend computation + signal detection
│   └── cli.py                  # Click CLI (scan / backtest)
├── requirements.txt
└── .gitignore
```

---

## Setup

```bash
pip install -r requirements.txt
```

---

## CLI Usage

### Historical Backtest

Run a 3-year backtest across the full Nifty 500 universe:

```bash
python -m src.cli backtest --years 3
```

Display the most recently saved summary report (no re-download):

```bash
python -m src.cli backtest --report
```

### Live Weekly Scanner

Scan all Nifty 500 symbols and print those currently meeting entry criteria
(Close > SMA30 AND RSI(14) > 60) on the latest completed weekly candle:

```bash
python -m src.cli scan
```

Results are printed to the console and saved to `data/scan_alerts.csv`.

---

## Backtest Results — Nifty 500, 3-Year Weekly (Real Data)

> Data source: Yahoo Finance (yfinance). 3 years of weekly OHLC.
> 491 symbols had sufficient history (≥ 44 bars). 8 symbols skipped (delisted/insufficient data).

### 1. Realized Closed Trades (1,244 Trades)
| Metric | Realized Value |
|---|---|
| **Closed Trades Count** | **1,244** |
| **Win Rate** | **33.92 %** |
| **Avg Trade Return** | **+0.50 %** |
| **Median Trade Return** | **−5.17 %** |
| **Avg Holding Period** | **17.6 weeks** (~4 months) |
| **Median Holding Period** | **16.0 weeks** |
| **Avg Max Drawdown (Intra-week)** | **−20.11 %** |
| **Avg Max Drawdown (Close-to-Close)** | **−15.61 %** |
| **Worst Max Drawdown** | **−68.54 %** |
| **Hit +20% Profit Milestone** | **38.02 % of trades** |
| **Naive Baseline Avg Return (17.6w hold)** | **+2.94 %** |
| **Excess Return vs Baseline** | **−2.44 %** |

### 2. Active Open Positions (87 Trades at End of Data)
*Positions that entered but have not yet closed below the 30-week SMA as of the end of the 3-year period:*
| Metric | Unrealized Value |
|---|---|
| **Active Open Positions** | **87** |
| **Unrealized Win Rate** | **88.51 %** (77 wins / 10 losses) |
| **Avg Unrealized Return** | **+60.44 %** |
| **Median Unrealized Return** | **+19.03 %** |
| **Avg Holding Period so far** | **24.1 weeks** |
| **Avg Max Drawdown so far** | **−16.79 %** |
| **Hit +20% Milestone** | **65.52 %** |
