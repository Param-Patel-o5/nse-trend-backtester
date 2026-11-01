"""Telegram notification dispatch and alert formatting."""

import os
from typing import Any, Dict, List, Optional
import requests


def send_telegram_alert(
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    message: str = "",
    timeout: int = 10,
) -> bool:
    """
    Send Markdown-formatted notification to Telegram chat.
    Reads credentials from arguments or environment variables.
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat:
        print("[ALERTS] Telegram credentials not set. Skipping Telegram notification.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, data=payload, timeout=timeout)
        resp.raise_for_status()
        print("[ALERTS] Telegram alert dispatched successfully.")
        return True
    except Exception as e:
        print(f"[ALERTS] Failed to dispatch Telegram alert: {e}")
        return False


def format_scan_message(
    crossover_alerts: List[Dict[str, Any]],
    fast_sma: int = 30,
    slow_sma: int = 50,
) -> str:
    """Format detected live crossover alerts into a clean Telegram Markdown message."""
    if not crossover_alerts:
        return f"No SMA{fast_sma}/SMA{slow_sma} Golden Cross detected this week."

    lines = [
        f"🚨 *Weekly Golden Cross Alert (SMA{fast_sma} > SMA{slow_sma})*",
        f"Count: {len(crossover_alerts)} stock(s)\n",
    ]
    for r in crossover_alerts:
        lines.append(
            f"• *{r['symbol']}* | Close: ₹{r['close']} | "
            f"SMA{fast_sma}: {r.get(f'sma{fast_sma}', r.get('sma30'))} | "
            f"SMA{slow_sma}: {r.get(f'sma{slow_sma}', r.get('sma50'))}"
        )
    return "\n".join(lines)
