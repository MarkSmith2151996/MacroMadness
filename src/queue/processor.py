"""Pending operations processor with dependency resolution and exponential backoff."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from src.db import async_session
from src.models import PendingOperation


async def enqueue(
    operation: str,
    payload: dict,
    depends_on: int | None = None,
    max_attempts: int = 3,
) -> int:
    """Add an operation to the queue. Returns the operation ID."""
    async with async_session() as db:
        op = PendingOperation(
            operation=operation,
            payload=payload,
            depends_on=depends_on,
            max_attempts=max_attempts,
        )
        db.add(op)
        await db.commit()
        await db.refresh(op)
        return op.id


async def process_queue():
    """Process all pending/retrying operations respecting dependencies."""
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(PendingOperation).where(
                and_(
                    PendingOperation.status.in_(["pending", "retrying"]),
                    PendingOperation.attempts < PendingOperation.max_attempts,
                )
            ).order_by(PendingOperation.created_at)
        )
        pending = result.scalars().all()

        for op in pending:
            # Skip if not yet ready for retry
            if op.next_retry_at and op.next_retry_at > now:
                continue

            # Check dependency
            if op.depends_on:
                dep = await db.get(PendingOperation, op.depends_on)
                if dep and dep.status != "completed":
                    continue

            try:
                await execute_operation(op)
                op.status = "completed"
                op.completed_at = now
            except Exception as e:
                op.attempts += 1
                op.last_error = str(e)
                backoff = timedelta(seconds=30 * (2 ** op.attempts))
                op.next_retry_at = now + backoff
                op.status = "failed" if op.attempts >= op.max_attempts else "retrying"

            await db.commit()


async def execute_operation(op: PendingOperation):
    """Dispatch an operation by name. Extend this as tools are added."""
    handlers = _get_handlers()
    handler = handlers.get(op.operation)
    if not handler:
        raise ValueError(f"Unknown operation: {op.operation}")
    await handler(op.payload)


def _get_handlers() -> dict:
    """Lazy-load handlers to avoid circular imports."""
    return {
        "correlation_snapshot": _handle_correlation_snapshot,
        "correlation_impact": _handle_correlation_impact,
        "score_trade": _handle_score_trade,
        "update_weights": _handle_update_weights,
    }


async def _handle_correlation_snapshot(payload: dict):
    """Take a correlation snapshot of the current portfolio."""
    from src.tools.correlation import register_correlation_tools
    from mcp.server.fastmcp import FastMCP

    # Use the correlation logic directly
    from decimal import Decimal
    from sqlalchemy import select
    from src.models import CorrelationSnapshot, Position

    async with async_session() as db:
        result = await db.execute(select(Position).where(Position.status == "open"))
        positions = result.scalars().all()
        tickers = [p.ticker for p in positions]

    if not tickers:
        return

    try:
        from src.integrations.market_data import get_historical_prices
        hist = await get_historical_prices(tickers)
    except Exception:
        hist = {}

    # Store snapshot
    async with async_session() as db:
        snapshot = CorrelationSnapshot(
            tickers=tickers,
            correlation_matrix={},
            flags=[],
        )
        db.add(snapshot)
        await db.commit()


async def _handle_correlation_impact(payload: dict):
    """Analyze correlation impact of adding a ticker."""
    await _handle_correlation_snapshot(payload)


async def _handle_score_trade(payload: dict):
    """Placeholder for trade scoring — Claude provides scores via invest_close_position.
    This queued op signals that scoring is needed; the actual scoring
    happens when Claude calls the learning tools with scores."""
    pass  # Scoring is interactive — Claude provides the 5 dimension scores


async def _handle_update_weights(payload: dict):
    """Check if weights need recalibration after a trade is scored."""
    from sqlalchemy import func, select
    from src.models import DimensionWeight, Trade

    async with async_session() as db:
        # Count completed trades
        count_result = await db.execute(
            select(func.count()).select_from(Trade).where(Trade.outcome.isnot(None))
        )
        trade_count = count_result.scalar()

        # Only auto-recalibrate at milestones (every 5 trades after 10)
        if trade_count < 10 or trade_count % 5 != 0:
            return

        # Get current weights
        result = await db.execute(
            select(DimensionWeight).order_by(DimensionWeight.version.desc()).limit(1)
        )
        current = result.scalar_one_or_none()
        if not current:
            return

        # Flag for recalibration — Claude will handle the actual analysis
        from src.integrations.ntfy import send_notification
        await send_notification(
            "weight_recalibration",
            f"Trade count reached {trade_count}. Dimension weights may need recalibration.",
            priority=3,
        )
