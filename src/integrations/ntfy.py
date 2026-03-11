"""Push notifications via ntfy.sh."""

import os

import httpx

from src.db import async_session
from src.models import NotificationLog

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")


async def send_notification(
    type: str,
    message: str,
    priority: int,
    ticker: str | None = None,
):
    """Send a push notification via ntfy.sh and log it."""
    if not NTFY_TOPIC:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                content=message,
                headers={
                    "Title": f"INVEST: {type.upper()}",
                    "Priority": str(priority),
                    "Tags": f"chart,{ticker}" if ticker else "warning",
                },
            )
        await _log(type, message, priority, ticker, True)
    except Exception as e:
        await _log(type, message, priority, ticker, False, str(e))


async def _log(
    type: str,
    message: str,
    priority: int,
    ticker: str | None,
    delivered: bool,
    error: str | None = None,
):
    async with async_session() as db:
        db.add(NotificationLog(
            type=type,
            message=message,
            priority=priority,
            ticker=ticker,
            delivered=delivered,
            error=error,
        ))
        await db.commit()
