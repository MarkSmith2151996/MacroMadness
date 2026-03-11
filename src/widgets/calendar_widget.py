"""Catalyst calendar widget for OpenBB Workspace."""

from datetime import date, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from src.db import async_session
from src.models import CatalystCalendar

router = APIRouter()


@router.get("/calendar")
async def calendar_widget(days_ahead: int = 30):
    """Upcoming catalysts for all positions and macro events."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)

    async with async_session() as db:
        result = await db.execute(
            select(CatalystCalendar)
            .where(CatalystCalendar.event_date >= today)
            .where(CatalystCalendar.event_date <= cutoff)
            .order_by(CatalystCalendar.event_date)
        )
        events = result.scalars().all()

    return [
        {
            "event_date": e.event_date.isoformat(),
            "event_type": e.event_type,
            "description": e.description,
            "ticker": e.ticker,
            "impact_level": e.impact_level,
        }
        for e in events
    ]
