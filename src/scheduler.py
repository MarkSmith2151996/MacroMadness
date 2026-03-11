"""APScheduler cron jobs — Schwab sync, queue processing, alerts, cache cleanup."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def start_scheduler():
    scheduler = AsyncIOScheduler()

    # Schwab sync — every 30 minutes during market hours
    scheduler.add_job(
        _schwab_periodic_sync,
        "cron", hour="9-16", minute="*/30", timezone="US/Eastern",
        id="schwab_sync",
    )

    # Queue processor — every 5 minutes
    scheduler.add_job(
        _process_queue,
        "interval", minutes=5,
        id="queue_processor",
    )

    # Token expiry check — every 6 hours
    scheduler.add_job(
        _check_schwab_token_expiry,
        "interval", hours=6,
        id="token_check",
    )

    # Earnings proximity alert — daily at 8 AM ET
    scheduler.add_job(
        _check_earnings_proximity,
        "cron", hour=8, timezone="US/Eastern",
        id="earnings_alert",
    )

    # Cache cleanup — daily at 3 AM ET
    scheduler.add_job(
        _cleanup_cache,
        "cron", hour=3, timezone="US/Eastern",
        id="cache_cleanup",
    )

    scheduler.start()
    return scheduler


async def _schwab_periodic_sync():
    """Sync positions from Schwab and detect changes."""
    try:
        from src.integrations.schwab import schwab_client
        status = await schwab_client.get_token_status()
        if status.get("status") != "valid":
            return
        await schwab_client.get_accounts()
    except Exception:
        pass


async def _process_queue():
    from src.queue.processor import process_queue
    await process_queue()


async def _check_schwab_token_expiry():
    """Alert if Schwab token is expiring soon."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from src.db import async_session
    from src.models import SchwabTokenState

    async with async_session() as db:
        result = await db.execute(select(SchwabTokenState).limit(1))
        state = result.scalar_one_or_none()
        if not state or not state.token_expires_at:
            return

        now = datetime.now(timezone.utc)
        days_left = (state.token_expires_at - now).days

        if days_left <= 3:
            from src.integrations.ntfy import send_notification
            await send_notification(
                "token_expiry",
                f"Schwab token expires in {days_left} days! Visit /auth/schwab/login to refresh.",
                priority=5,
            )


async def _check_earnings_proximity():
    """Alert for earnings within 3 days of held positions."""
    from datetime import date, timedelta

    from sqlalchemy import select

    from src.db import async_session
    from src.models import CatalystCalendar, Position

    today = date.today()
    cutoff = today + timedelta(days=3)

    async with async_session() as db:
        # Get open position tickers
        pos_result = await db.execute(
            select(Position.ticker).where(Position.status == "open")
        )
        held_tickers = {r[0] for r in pos_result.all()}

        # Get upcoming earnings
        earnings_result = await db.execute(
            select(CatalystCalendar)
            .where(CatalystCalendar.event_type == "earnings")
            .where(CatalystCalendar.event_date >= today)
            .where(CatalystCalendar.event_date <= cutoff)
        )
        earnings = earnings_result.scalars().all()

    for e in earnings:
        if e.ticker and e.ticker in held_tickers:
            from src.integrations.ntfy import send_notification
            await send_notification(
                "earnings_alert",
                f"{e.ticker} earnings on {e.event_date.isoformat()}: {e.description}",
                priority=4,
                ticker=e.ticker,
            )


async def _cleanup_cache():
    from src.cache import cleanup_expired_cache
    await cleanup_expired_cache()
