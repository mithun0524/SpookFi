"""
Telegram Trade Alert Notifier
Sends real-time trade notifications to a Telegram chat.

Setup:
  1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
  2. Start a chat with your bot → get TELEGRAM_CHAT_ID (use @userinfobot)
  3. Add to .env:
       TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
       TELEGRAM_CHAT_ID=-100123456789

If not configured, all calls are silently no-ops (no crash).
"""
import asyncio
import os
from datetime import datetime
from loguru import logger

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _is_configured() -> bool:
    return bool(_BOT_TOKEN and _CHAT_ID)


async def _send(text: str) -> None:
    """Low-level async send — fire and forget."""
    if not _is_configured():
        return
    if not _HTTPX_AVAILABLE:
        logger.debug("httpx not available — Telegram alert skipped.")
        return
    try:
        url = _BASE_URL.format(token=_BOT_TOKEN)
        payload = {
            "chat_id": _CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": False,
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception as e:
        # Never crash the engine over a notification failure
        logger.warning(f"Telegram notification failed: {e}")


# ─── Public API ──────────────────────────────────────────────────────────────

async def alert_trade_opened(symbol: str, side: str, qty: int,
                              entry_price: float, stop_loss: float,
                              take_profit: float, confidence: float) -> None:
    """Fire when a new position is opened."""
    side_emoji = "🟢 LONG" if side.lower() in ("buy", "long") else "🔴 SHORT"
    msg = (
        f"👻 <b>SpookFi — Trade Opened</b>\n\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Direction:</b> {side_emoji}\n"
        f"<b>Qty:</b> {qty}\n"
        f"<b>Entry:</b> ₹{entry_price:,.2f}\n"
        f"<b>Stop Loss:</b> ₹{stop_loss:,.2f}\n"
        f"<b>Take Profit:</b> ₹{take_profit:,.2f}\n"
        f"<b>Confidence:</b> {confidence * 100:.1f}%\n"
        f"<i>{datetime.now().strftime('%H:%M:%S IST')}</i>"
    )
    await _send(msg)


async def alert_trade_closed(symbol: str, side: str, entry_price: float,
                              exit_price: float, pnl: float, reason: str = "Stop/TP") -> None:
    """Fire when a position is closed."""
    pnl_emoji = "💰" if pnl >= 0 else "💸"
    pnl_sign = "+" if pnl >= 0 else ""
    msg = (
        f"👻 <b>SpookFi — Trade Closed</b>\n\n"
        f"<b>Symbol:</b> {symbol}\n"
        f"<b>Side:</b> {side}\n"
        f"<b>Entry:</b> ₹{entry_price:,.2f}\n"
        f"<b>Exit:</b> ₹{exit_price:,.2f}\n"
        f"<b>PnL:</b> {pnl_emoji} <b>{pnl_sign}₹{abs(pnl):,.2f}</b>\n"
        f"<b>Reason:</b> {reason}\n"
        f"<i>{datetime.now().strftime('%H:%M:%S IST')}</i>"
    )
    await _send(msg)


async def alert_kill_switch(daily_pnl: float, equity: float) -> None:
    """Fire when the daily kill switch triggers."""
    msg = (
        f"🚨 <b>SpookFi — KILL SWITCH ACTIVATED</b>\n\n"
        f"Daily loss limit breached.\n"
        f"<b>Daily PnL:</b> ₹{daily_pnl:,.2f}\n"
        f"<b>Equity:</b> ₹{equity:,.2f}\n"
        f"<b>Trading halted for today.</b>\n"
        f"<i>{datetime.now().strftime('%H:%M:%S IST')}</i>"
    )
    await _send(msg)


async def alert_engine_status(status: str, detail: str = "") -> None:
    """Fire on engine start/stop/error."""
    emoji = {"started": "🟢", "stopped": "🔴", "error": "⚠️"}.get(status, "ℹ️")
    msg = (
        f"{emoji} <b>SpookFi Engine — {status.upper()}</b>\n"
        + (f"<i>{detail}</i>" if detail else "")
        + f"\n<i>{datetime.now().strftime('%H:%M:%S IST')}</i>"
    )
    await _send(msg)
