"""Shared test fixtures for MacroMadness test suite."""

import os
import sys

# Override DATABASE_URL before any src imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
# Disable external service env vars
os.environ["AUTH0_DOMAIN"] = ""
os.environ["AUTH0_AUDIENCE"] = ""
os.environ["OPENBB_BACKEND_TOKEN"] = ""
os.environ["NTFY_TOPIC"] = ""
os.environ["SCHWAB_APP_KEY"] = ""
os.environ["SCHWAB_APP_SECRET"] = ""
os.environ["SCHWAB_TOKEN_ENCRYPTION_KEY"] = ""

# Monkey-patch create_async_engine before src.db is imported
# SQLite does not accept pool_size/max_overflow
import sqlalchemy.ext.asyncio as _sa_async

_original_create_async_engine = _sa_async.create_async_engine


def _patched_create_async_engine(url, **kwargs):
    # Remove pool_size and max_overflow for SQLite URLs
    if "sqlite" in str(url):
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
    return _original_create_async_engine(url, **kwargs)


_sa_async.create_async_engine = _patched_create_async_engine

# Also need to patch it in the sqlalchemy.ext.asyncio.engine module
import sqlalchemy.ext.asyncio.engine as _sa_engine_mod

_sa_engine_mod.create_async_engine = _patched_create_async_engine

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db import Base


# Create a test engine using in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"



@pytest_asyncio.fixture
async def test_engine():
    """Create a fresh test engine for each test."""
    engine = _original_create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """Create a test database session."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def patched_db(test_engine):
    """Patch src.db.async_session to use the test engine.
    Returns the session factory for direct use if needed."""
    from unittest.mock import patch

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    with patch("src.db.async_session", session_factory):
        yield session_factory
