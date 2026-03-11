"""Alerts widget for OpenBB Workspace."""

from fastapi import APIRouter
from sqlalchemy import select

from src.db import async_session
from src.models import NotificationLog

router = APIRouter()


@router.get("/alerts")
async def alerts_widget(limit: int = 50):
    """Recent notifications and warnings."""
    async with async_session() as db:
        result = await db.execute(
            select(NotificationLog)
            .order_by(NotificationLog.sent_at.desc())
            .limit(limit)
        )
        notifications = result.scalars().all()

    return [
        {
            "sent_at": n.sent_at.isoformat(),
            "type": n.type,
            "message": n.message,
            "priority": n.priority,
            "ticker": n.ticker,
            "delivered": n.delivered,
        }
        for n in notifications
    ]
