"""Test widget REST endpoints using FastAPI TestClient."""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db import Base


@pytest.fixture
def client():
    """Create a test client with a real in-memory SQLite DB for widgets."""
    import asyncio

    # Create a fresh in-memory DB and session factory
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def setup_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(setup_db())

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Build a minimal FastAPI app with patched DB
    test_app = FastAPI(title="Test App")

    from src.widgets import register_all_widgets
    from src.auth.schwab_oauth import router as schwab_router

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    with patch("src.db.async_session", session_factory):
        # Patch async_session in all widget modules
        with patch("src.widgets.portfolio_widget.async_session", session_factory):
            with patch("src.widgets.calendar_widget.async_session", session_factory):
                with patch("src.widgets.alerts_widget.async_session", session_factory):
                    with patch("src.widgets.scores_widget.async_session", session_factory):
                        with patch("src.widgets.health_widget.async_session", session_factory):
                            register_all_widgets(test_app)
                            test_app.include_router(schwab_router)
                            with TestClient(test_app) as c:
                                yield c

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(engine.dispose())


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# widgets.json
# ---------------------------------------------------------------------------
def test_widgets_json_returns_200(client):
    resp = client.get("/widgets.json")
    assert resp.status_code == 200


def test_widgets_json_contains_all_widgets(client):
    resp = client.get("/widgets.json")
    data = resp.json()
    assert isinstance(data, dict)

    expected_keys = {
        "portfolio_overview",
        "catalyst_calendar",
        "alert_feed",
        "trade_scores",
        "system_health",
    }
    assert set(data.keys()) == expected_keys


def test_widgets_json_structure(client):
    """Each widget definition should have name, description, endpoint, and data."""
    resp = client.get("/widgets.json")
    data = resp.json()

    for key, widget in data.items():
        assert "name" in widget, f"Widget {key} missing 'name'"
        assert "description" in widget, f"Widget {key} missing 'description'"
        assert "endpoint" in widget, f"Widget {key} missing 'endpoint'"
        assert "data" in widget, f"Widget {key} missing 'data'"


def test_widgets_json_endpoints(client):
    """Verify the endpoint values in widget definitions."""
    resp = client.get("/widgets.json")
    data = resp.json()

    expected_endpoints = {
        "portfolio_overview": "portfolio",
        "catalyst_calendar": "calendar",
        "alert_feed": "alerts",
        "trade_scores": "scores",
        "system_health": "system-health",
    }

    for key, expected_endpoint in expected_endpoints.items():
        assert data[key]["endpoint"] == expected_endpoint


# ---------------------------------------------------------------------------
# Widget endpoints exist and respond (not 404)
# ---------------------------------------------------------------------------
def test_portfolio_endpoint_exists(client):
    """GET /portfolio should exist and return data."""
    resp = client.get("/portfolio")
    assert resp.status_code != 404, "/portfolio endpoint not registered"


def test_calendar_endpoint_exists(client):
    resp = client.get("/calendar")
    assert resp.status_code != 404, "/calendar endpoint not registered"


def test_alerts_endpoint_exists(client):
    resp = client.get("/alerts")
    assert resp.status_code != 404, "/alerts endpoint not registered"


def test_scores_endpoint_exists(client):
    resp = client.get("/scores")
    assert resp.status_code != 404, "/scores endpoint not registered"


def test_system_health_endpoint_exists(client):
    resp = client.get("/system-health")
    assert resp.status_code != 404, "/system-health endpoint not registered"


# ---------------------------------------------------------------------------
# Schwab OAuth routes exist
# ---------------------------------------------------------------------------
def test_schwab_login_route_exists(client):
    """GET /auth/schwab/login should exist."""
    resp = client.get("/auth/schwab/login", follow_redirects=False)
    assert resp.status_code != 404, "/auth/schwab/login endpoint not registered"
