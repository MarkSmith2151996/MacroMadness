"""Test app initialization -- title, version, routes."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestAppInitialization:

    def test_app_title(self):
        from src.main import app
        assert app.title == "Investment Research System"

    def test_app_version(self):
        from src.main import app
        assert app.version == "3.1"

    def test_routes_registered(self):
        """The app should have routes for widgets, health, and Schwab OAuth."""
        from src.main import app

        route_paths = [route.path for route in app.routes if hasattr(route, "path")]

        # Health endpoint
        assert "/health" in route_paths, "Missing /health route"

        # Widget endpoints
        assert "/portfolio" in route_paths, "Missing /portfolio route"
        assert "/calendar" in route_paths, "Missing /calendar route"
        assert "/alerts" in route_paths, "Missing /alerts route"
        assert "/scores" in route_paths, "Missing /scores route"
        assert "/system-health" in route_paths, "Missing /system-health route"

        # Schwab OAuth
        assert "/auth/schwab/login" in route_paths, "Missing /auth/schwab/login route"
        assert "/auth/schwab/callback" in route_paths, "Missing /auth/schwab/callback route"

        # widgets.json
        assert "/widgets.json" in route_paths, "Missing /widgets.json route"

    def test_cors_middleware_added(self):
        """CORS middleware should be configured."""
        from src.main import app

        middleware_classes = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middleware_classes

    def test_mcp_instance_created(self):
        """The MCP server instance should exist with correct name."""
        from src.main import mcp
        assert mcp.name == "InvestMCP"

    def test_app_has_lifespan(self):
        """The app should have a lifespan context manager."""
        from src.main import app
        assert app.router.lifespan_context is not None

    def test_mcp_tools_registered_on_instance(self):
        """The MCP server from main should have 20 tools registered."""
        from src.main import mcp
        registered = mcp._tool_manager._tools
        assert len(registered) == 20, f"Expected 20 tools, got {len(registered)}"
