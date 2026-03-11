"""DB-backed cache with TTL tiers, rate limiting, and stale fallback."""

import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import select

from src.db import async_session
from src.models import ApiCache, ApiRateLimit

# TTL constants (seconds)
TTL_QUOTE = 60           # 1 minute
TTL_TECHNICALS = 900     # 15 minutes
TTL_FUNDAMENTALS = 86400 # 24 hours
TTL_CONSENSUS = 43200    # 12 hours
TTL_EARNINGS = 604800    # 7 days
TTL_MACRO = 21600        # 6 hours
TTL_FILING = 2592000     # 30 days
TTL_GOLD = 60            # 1 minute


async def _check_rate_limit(source: str) -> bool:
    """Check and increment rate limit for a source. Returns True if allowed."""
    async with async_session() as db:
        result = await db.execute(
            select(ApiRateLimit).where(ApiRateLimit.source == source)
        )
        limit = result.scalar_one_or_none()

        if not limit:
            return True  # No limit configured for this source

        today = date.today()

        # Reset daily counter if new day
        if limit.last_reset < today:
            limit.calls_today = 0
            limit.last_reset = today

        if limit.calls_today >= limit.daily_limit:
            return False

        limit.calls_today += 1
        await db.commit()
        return True


async def cached_fetch(
    cache_key: str,
    ttl_seconds: int,
    source: str,
    fetch_fn,
) -> dict:
    """Fetch data with DB-backed caching. Sync fetch_fn is run in a thread pool."""
    cached = None

    # Check cache
    async with async_session() as db:
        result = await db.execute(
            select(ApiCache).where(ApiCache.cache_key == cache_key)
        )
        cached = result.scalar_one_or_none()

        if cached:
            age = (datetime.now(timezone.utc) - cached.fetched_at).total_seconds()
            if age < ttl_seconds:
                return cached.data

    # Check rate limit before making external call
    if not await _check_rate_limit(source):
        if cached:
            return cached.data  # Return stale data when rate limited
        raise RuntimeError(f"Rate limit exceeded for {source} and no cached data available")

    # Cache miss or expired — fetch fresh data
    try:
        data = await asyncio.to_thread(fetch_fn)
        async with async_session() as db:
            result = await db.execute(
                select(ApiCache).where(ApiCache.cache_key == cache_key)
            )
            row = result.scalar_one_or_none()
            if row:
                row.data = data
                row.fetched_at = datetime.now(timezone.utc)
                row.ttl_seconds = ttl_seconds
            else:
                db.add(ApiCache(
                    cache_key=cache_key,
                    data=data,
                    ttl_seconds=ttl_seconds,
                    source=source,
                ))
            await db.commit()
        return data
    except Exception:
        if cached:
            return cached.data  # Stale fallback
        raise


async def cleanup_expired_cache():
    """Remove cache entries that have exceeded 2x their TTL."""
    async with async_session() as db:
        result = await db.execute(select(ApiCache))
        rows = result.scalars().all()
        now = datetime.now(timezone.utc)
        for row in rows:
            age = (now - row.fetched_at).total_seconds()
            if age > row.ttl_seconds * 2:
                await db.delete(row)
        await db.commit()
