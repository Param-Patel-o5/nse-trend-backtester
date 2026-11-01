"""Backtest engine and performance metrics."""
from src.backtest.engine import run_backtest
from src.backtest.metrics import aggregate_trades, compute_naive_baseline
from src.backtest.trades import simulate_trades
