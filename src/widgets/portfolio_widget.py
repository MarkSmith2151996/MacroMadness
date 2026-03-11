"""Portfolio overview widget for OpenBB Workspace."""

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from src.db import async_session
from src.models import Portfolio, Position

router = APIRouter()


@router.get("/portfolio")
async def portfolio_widget(account_type: str = ""):
    """Portfolio overview — all positions with P&L."""
    async with async_session() as db:
        query = select(Position).where(Position.status == "open")
        if account_type:
            query = query.join(Portfolio).where(Portfolio.account_type == account_type)
        result = await db.execute(query)
        positions = result.scalars().all()

    rows = []
    for p in positions:
        try:
            from src.integrations.market_data import get_quote
            quote = await get_quote(p.ticker)
            current_price = float(quote.get("results", [{}])[0].get("last_price", 0))
        except Exception:
            current_price = 0

        cost_total = float(p.shares * p.cost_basis)
        market_value = float(p.shares) * current_price
        unrealized_pnl = market_value - cost_total

        rows.append({
            "ticker": p.ticker,
            "shares": float(p.shares),
            "cost_basis": float(p.cost_basis),
            "current_price": current_price,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "stop_loss": float(p.stop_loss) if p.stop_loss else None,
            "sector": p.sector,
            "account": None,  # Loaded separately to avoid N+1
        })

    return rows
