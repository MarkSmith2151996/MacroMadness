"""Test cached_fetch logic, rate limiting, and cleanup."""

import pytest
import pytest_asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db import Base
from src.models import ApiCache, ApiRateLimit

pytestmark = pytest.mark.asyncio


def _naive_utcnow():
    """Return current UTC time as a naive datetime (SQLite compatible)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory


@pytest_asyncio.fixture
async def db_patch(session_factory):
    """Patch async_session in both src.db and src.cache, and patch datetime
    to return naive datetimes (matching what SQLite stores/returns)."""
    import src.cache as cache_mod

    # Save original datetime class
    _OrigDatetime = datetime

    class NaiveDatetime(_OrigDatetime):
        """datetime subclass that returns naive UTC datetimes for now()."""
        @classmethod
        def now(cls, tz=None):
            result = _OrigDatetime.now(timezone.utc)
            return result.replace(tzinfo=None)

    with patch("src.db.async_session", session_factory):
        with patch("src.cache.async_session", session_factory):
            with patch("src.cache.datetime", NaiveDatetime):
                yield session_factory


# ---------------------------------------------------------------------------
# cached_fetch tests
# ---------------------------------------------------------------------------
async def test_cache_miss_calls_fetch_fn(db_patch):
    """Cache miss should call fetch_fn and store result."""
    from src.cache import cached_fetch

    fetch_fn = MagicMock(return_value={"price": 195.5})

    result = await cached_fetch(
        cache_key="test:cache_miss",
        ttl_seconds=60,
        source="test",
        fetch_fn=fetch_fn,
    )

    assert result == {"price": 195.5}
    fetch_fn.assert_called_once()

    # Verify stored in DB
    async with db_patch() as session:
        db_result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == "test:cache_miss")
        )
        cached = db_result.scalar_one_or_none()
        assert cached is not None
        assert cached.data == {"price": 195.5}
        assert cached.ttl_seconds == 60
        assert cached.source == "test"


async def test_cache_hit_skips_fetch_fn(db_patch):
    """Cache hit (not expired) should return cached data without calling fetch_fn."""
    from src.cache import cached_fetch

    # First call: cache miss, populates cache
    fetch_fn = MagicMock(return_value={"cached": True})
    result1 = await cached_fetch(
        cache_key="test:cache_hit",
        ttl_seconds=3600,
        source="test",
        fetch_fn=fetch_fn,
    )
    assert result1 == {"cached": True}
    assert fetch_fn.call_count == 1

    # Second call: cache hit, should NOT call fetch_fn again
    fetch_fn2 = MagicMock(return_value={"fresh": True})
    result2 = await cached_fetch(
        cache_key="test:cache_hit",
        ttl_seconds=3600,
        source="test",
        fetch_fn=fetch_fn2,
    )
    assert result2 == {"cached": True}
    fetch_fn2.assert_not_called()


async def test_expired_cache_calls_fetch_fn(db_patch):
    """Expired cache should call fetch_fn again."""
    from src.cache import cached_fetch

    # First call populates cache
    fetch_fn1 = MagicMock(return_value={"old": True})
    await cached_fetch(
        cache_key="test:expired",
        ttl_seconds=60,
        source="test",
        fetch_fn=fetch_fn1,
    )

    # Manually age the cache entry
    async with db_patch() as session:
        result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == "test:expired")
        )
        cached = result.scalar_one()
        # Set fetched_at to 2 minutes ago (past 60s TTL), naive datetime
        cached.fetched_at = _naive_utcnow() - timedelta(seconds=120)
        await session.commit()

    # Second call: expired cache, should call fetch_fn
    fetch_fn2 = MagicMock(return_value={"fresh": True})
    result2 = await cached_fetch(
        cache_key="test:expired",
        ttl_seconds=60,
        source="test",
        fetch_fn=fetch_fn2,
    )
    assert result2 == {"fresh": True}
    fetch_fn2.assert_called_once()


async def test_failed_fetch_returns_stale_data(db_patch):
    """If fetch_fn raises, return stale cached data if available."""
    from src.cache import cached_fetch

    # Populate cache
    fetch_fn1 = MagicMock(return_value={"stale": True})
    await cached_fetch(
        cache_key="test:stale_fallback",
        ttl_seconds=60,
        source="test",
        fetch_fn=fetch_fn1,
    )

    # Age the cache entry
    async with db_patch() as session:
        result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == "test:stale_fallback")
        )
        cached = result.scalar_one()
        cached.fetched_at = _naive_utcnow() - timedelta(seconds=120)
        await session.commit()

    # Now try to fetch with a failing function - should return stale data
    fetch_fn2 = MagicMock(side_effect=RuntimeError("API down"))
    result = await cached_fetch(
        cache_key="test:stale_fallback",
        ttl_seconds=60,
        source="test",
        fetch_fn=fetch_fn2,
    )
    assert result == {"stale": True}


async def test_failed_fetch_no_cache_raises(db_patch):
    """If fetch_fn raises and no cached data, re-raise the exception."""
    from src.cache import cached_fetch

    fetch_fn = MagicMock(side_effect=RuntimeError("API down"))

    with pytest.raises(RuntimeError, match="API down"):
        await cached_fetch(
            cache_key="test:no_stale",
            ttl_seconds=60,
            source="test",
            fetch_fn=fetch_fn,
        )


# ---------------------------------------------------------------------------
# Rate limit tests
# ---------------------------------------------------------------------------
async def test_rate_limit_allows_under_limit(db_patch):
    """Calls under the daily limit should be allowed."""
    from src.cache import _check_rate_limit

    async with db_patch() as session:
        session.add(ApiRateLimit(
            source="test_source",
            daily_limit=100,
            calls_today=50,
            last_reset=date.today(),
        ))
        await session.commit()

    result = await _check_rate_limit("test_source")
    assert result is True


async def test_rate_limit_blocks_at_limit(db_patch):
    """Calls at or above the daily limit should be blocked."""
    from src.cache import _check_rate_limit

    async with db_patch() as session:
        session.add(ApiRateLimit(
            source="blocked_source",
            daily_limit=100,
            calls_today=100,
            last_reset=date.today(),
        ))
        await session.commit()

    result = await _check_rate_limit("blocked_source")
    assert result is False


async def test_rate_limit_no_config_allows(db_patch):
    """If no rate limit is configured for a source, allow the call."""
    from src.cache import _check_rate_limit

    result = await _check_rate_limit("unconfigured_source")
    assert result is True


async def test_rate_limit_resets_on_new_day(db_patch):
    """Rate limit counter should reset on a new day."""
    from src.cache import _check_rate_limit

    async with db_patch() as session:
        session.add(ApiRateLimit(
            source="reset_source",
            daily_limit=100,
            calls_today=100,
            last_reset=date.today() - timedelta(days=1),  # Yesterday
        ))
        await session.commit()

    result = await _check_rate_limit("reset_source")
    assert result is True  # Should reset and allow


# ---------------------------------------------------------------------------
# cleanup_expired_cache tests
# ---------------------------------------------------------------------------
async def test_cleanup_expired_cache_removes_old(db_patch):
    """Entries older than 2x TTL should be removed."""
    from src.cache import cached_fetch, cleanup_expired_cache

    # Populate cache via cached_fetch (fresh entry)
    fetch_fn1 = MagicMock(return_value={"keep": True})
    await cached_fetch(
        cache_key="fresh",
        ttl_seconds=3600,
        source="test",
        fetch_fn=fetch_fn1,
    )

    # Populate another entry and then age it past 2x TTL
    fetch_fn2 = MagicMock(return_value={"remove": True})
    await cached_fetch(
        cache_key="expired",
        ttl_seconds=60,
        source="test",
        fetch_fn=fetch_fn2,
    )

    # Age the "expired" entry past 2x TTL
    async with db_patch() as session:
        result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == "expired")
        )
        cached = result.scalar_one()
        cached.fetched_at = _naive_utcnow() - timedelta(seconds=180)  # 3x TTL
        await session.commit()

    await cleanup_expired_cache()

    async with db_patch() as session:
        result = await session.execute(select(ApiCache))
        remaining = result.scalars().all()
        keys = [r.cache_key for r in remaining]
        assert "fresh" in keys
        assert "expired" not in keys


async def test_cleanup_keeps_within_2x_ttl(db_patch):
    """Entries within 2x TTL should be kept."""
    from src.cache import cached_fetch, cleanup_expired_cache

    # Populate cache
    fetch_fn = MagicMock(return_value={"keep": True})
    await cached_fetch(
        cache_key="borderline",
        ttl_seconds=100,
        source="test",
        fetch_fn=fetch_fn,
    )

    # Age to 1.5x TTL (still under 2x)
    async with db_patch() as session:
        result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == "borderline")
        )
        cached = result.scalar_one()
        cached.fetched_at = _naive_utcnow() - timedelta(seconds=150)
        await session.commit()

    await cleanup_expired_cache()

    async with db_patch() as session:
        result = await session.execute(
            select(ApiCache).where(ApiCache.cache_key == "borderline")
        )
        assert result.scalar_one_or_none() is not None
