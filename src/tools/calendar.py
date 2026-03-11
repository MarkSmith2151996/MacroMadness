"""Module G: Calendar tool (1 tool)."""

from datetime import date as date_type, timedelta

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import CatalystCalendar


def register_calendar_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_calendar(
        action: str,
        event_date: str = "",
        event_type: str = "",
        ticker: str = "",
        description: str = "",
        impact_level: str = "medium",
        days_ahead: int = 30,
    ) -> dict:
        """Manage the catalyst calendar.
        action: list | add | earnings
        - list: show upcoming events (default 30 days)
        - add: add a calendar event
        - earnings: show only earnings events"""
        async with async_session() as db:
            if action == "list":
                today = date_type.today()
                cutoff = today + timedelta(days=days_ahead)
                result = await db.execute(
                    select(CatalystCalendar)
                    .where(CatalystCalendar.event_date >= today)
                    .where(CatalystCalendar.event_date <= cutoff)
                    .order_by(CatalystCalendar.event_date)
                )
                events = result.scalars().all()
                return {
                    "events": [
                        {
                            "id": e.id,
                            "event_date": e.event_date.isoformat(),
                            "event_type": e.event_type,
                            "ticker": e.ticker,
                            "description": e.description,
                            "impact_level": e.impact_level,
                        }
                        for e in events
                    ],
                    "count": len(events),
                    "range": f"{today.isoformat()} to {cutoff.isoformat()}",
                }

            elif action == "add":
                if not event_date or not description:
                    return {"error": "event_date and description are required"}
                event = CatalystCalendar(
                    event_date=date_type.fromisoformat(event_date),
                    event_type=event_type or None,
                    ticker=ticker or None,
                    description=description,
                    impact_level=impact_level,
                    source="manual",
                )
                db.add(event)
                await db.commit()
                await db.refresh(event)
                return {"event_id": event.id, "added": True}

            elif action == "earnings":
                today = date_type.today()
                cutoff = today + timedelta(days=days_ahead)
                result = await db.execute(
                    select(CatalystCalendar)
                    .where(CatalystCalendar.event_type == "earnings")
                    .where(CatalystCalendar.event_date >= today)
                    .where(CatalystCalendar.event_date <= cutoff)
                    .order_by(CatalystCalendar.event_date)
                )
                events = result.scalars().all()
                return {
                    "earnings_events": [
                        {
                            "id": e.id,
                            "event_date": e.event_date.isoformat(),
                            "ticker": e.ticker,
                            "description": e.description,
                            "impact_level": e.impact_level,
                        }
                        for e in events
                    ],
                    "count": len(events),
                }

            return {"error": f"Unknown action: {action}. Use list, add, or earnings."}
