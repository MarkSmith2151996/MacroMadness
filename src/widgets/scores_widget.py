"""Trade scores widget for OpenBB Workspace."""

from fastapi import APIRouter
from sqlalchemy import select

from src.db import async_session
from src.models import Trade, TradeScore

router = APIRouter()


@router.get("/scores")
async def scores_widget():
    """Closed trades with 5-dimension scoring and process vs outcome."""
    async with async_session() as db:
        result = await db.execute(
            select(TradeScore).order_by(TradeScore.scored_at.desc())
        )
        scores = result.scalars().all()

        # Get trade tickers
        trade_ids = [s.trade_id for s in scores]
        trades_result = await db.execute(
            select(Trade).where(Trade.id.in_(trade_ids)) if trade_ids else select(Trade).where(False)
        )
        trades_map = {t.id: t for t in trades_result.scalars().all()}

    return [
        {
            "ticker": trades_map[s.trade_id].ticker if s.trade_id in trades_map else "?",
            "outcome": s.outcome,
            "composite_score": float(s.composite_score) if s.composite_score else None,
            "research": s.research_quality_score,
            "entry": s.entry_timing_score,
            "sizing": s.position_sizing_score,
            "stop": s.stop_loss_score,
            "exit": s.exit_timing_score,
            "process_vs_outcome": s.process_vs_outcome,
        }
        for s in scores
    ]
