"""System health widget for OpenBB Workspace."""

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from src.db import async_session
from src.models import ApiRateLimit, AuditLog, PendingOperation, SchwabTokenState

router = APIRouter()


@router.get("/system-health")
async def health_widget():
    """Schwab token, API budgets, pending operations."""
    async with async_session() as db:
        # Schwab token
        token_result = await db.execute(select(SchwabTokenState).limit(1))
        token = token_result.scalar_one_or_none()

        # Pending ops
        pending_result = await db.execute(
            select(func.count()).select_from(PendingOperation)
            .where(PendingOperation.status.in_(["pending", "retrying"]))
        )
        pending_count = pending_result.scalar()

        failed_result = await db.execute(
            select(func.count()).select_from(PendingOperation)
            .where(PendingOperation.status == "failed")
        )
        failed_count = failed_result.scalar()

        # Rate limits
        rate_result = await db.execute(select(ApiRateLimit))
        rates = rate_result.scalars().all()

    now = datetime.now(timezone.utc)
    rows = [
        {
            "component": "Schwab Token",
            "status": "valid" if (token and token.token_expires_at and token.token_expires_at > now)
                else "expired" if token else "not configured",
            "detail": f"Expires: {token.token_expires_at.isoformat() if token and token.token_expires_at else 'N/A'}",
        },
        {
            "component": "Queue",
            "status": "ok" if pending_count == 0 else "active",
            "detail": f"{pending_count} pending, {failed_count} failed",
        },
    ]

    for r in rates:
        rows.append({
            "component": f"API: {r.source}",
            "status": "ok" if r.calls_today < r.daily_limit else "limit reached",
            "detail": f"{r.calls_today}/{r.daily_limit} today",
        })

    return rows
