"""Module E: Principles tool (1 tool)."""

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import Principle


async def _check_principles(
    ticker: str,
    entry_price: float,
    stop_loss: float,
    conviction_pct: int,
    sector: str,
) -> dict:
    """Internal principle check — also called by trade plan creation."""
    violations = []
    async with async_session() as db:
        result = await db.execute(select(Principle).where(Principle.active == True))
        principles = result.scalars().all()

    for p in principles:
        text_lower = p.principle_text.lower()
        # Auto-check known patterns
        if "conviction below 55" in text_lower and conviction_pct < 55:
            violations.append({
                "principle_id": p.id,
                "text": p.principle_text,
                "violation": f"Conviction is {conviction_pct}%",
            })
        if "stop-loss" in text_lower and "never widen" in text_lower:
            if stop_loss <= 0:
                violations.append({
                    "principle_id": p.id,
                    "text": p.principle_text,
                    "violation": "No stop-loss set",
                })

    return {"violations": violations, "checked": len(principles)}


def register_principles_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_principles(
        action: str,
        principle_text: str = "",
        category: str = "",
        principle_id: int = 0,
        event_type: str = "",
    ) -> dict:
        """Manage trading principles.
        action: check | list | add | log_event
        - check: check a trade against all active principles (use invest_create_trade_plan instead)
        - list: list all active principles
        - add: add a new principle
        - log_event: record that a principle was applied or violated"""
        async with async_session() as db:
            if action == "list":
                result = await db.execute(
                    select(Principle).where(Principle.active == True)
                )
                principles = result.scalars().all()
                return {
                    "principles": [
                        {
                            "id": p.id,
                            "text": p.principle_text,
                            "category": p.category,
                            "times_applied": p.times_applied,
                            "times_violated": p.times_violated,
                        }
                        for p in principles
                    ]
                }

            elif action == "add":
                if not principle_text:
                    return {"error": "principle_text is required"}
                p = Principle(
                    principle_text=principle_text,
                    category=category or None,
                )
                db.add(p)
                await db.commit()
                await db.refresh(p)
                return {"principle_id": p.id, "added": True}

            elif action == "log_event":
                if not principle_id:
                    return {"error": "principle_id is required"}
                p = await db.get(Principle, principle_id)
                if not p:
                    return {"error": f"Principle {principle_id} not found"}
                if event_type == "applied":
                    p.times_applied += 1
                elif event_type == "violated":
                    p.times_violated += 1
                else:
                    return {"error": "event_type must be 'applied' or 'violated'"}
                await db.commit()
                return {"principle_id": p.id, "event_type": event_type, "logged": True}

            elif action == "check":
                return {"message": "Use invest_create_trade_plan for automatic principle checking"}

            return {"error": f"Unknown action: {action}. Use check, list, add, or log_event."}
