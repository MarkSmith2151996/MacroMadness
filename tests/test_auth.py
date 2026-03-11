"""Test auth logic — check_tool_access, VIEWER_TOOLS, validate_openbb_token."""

import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# check_tool_access
# ---------------------------------------------------------------------------
class TestCheckToolAccess:

    def test_owner_can_access_everything(self):
        from src.auth.middleware import check_tool_access
        # Owner should have access to ALL tools, including admin-only ones
        all_tools = [
            "invest_get_portfolio",
            "invest_update_position",
            "invest_close_position",
            "invest_update_cash",
            "invest_create_trade_plan",
            "invest_get_trade",
            "invest_list_trades",
            "invest_update_trade_plan",
            "invest_screen_candidate",
            "invest_list_rejected_candidates",
            "invest_weights",
            "invest_lessons",
            "invest_principles",
            "invest_market_data",
            "invest_calendar",
            "invest_correlation",
            "invest_verify_order",
            "invest_schwab",
            "invest_admin",
            "invest_get_filing",
        ]
        for tool in all_tools:
            assert check_tool_access(tool, "owner") is True, f"Owner denied access to {tool}"

    def test_owner_can_access_with_any_action(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_lessons", "owner", "add") is True
        assert check_tool_access("invest_principles", "owner", "add") is True
        assert check_tool_access("invest_calendar", "owner", "add") is True
        assert check_tool_access("invest_weights", "owner", "update") is True

    def test_viewer_can_access_viewer_tools(self):
        from src.auth.middleware import check_tool_access
        viewer_allowed = [
            "invest_get_portfolio",
            "invest_get_trade",
            "invest_list_trades",
            "invest_market_data",
        ]
        for tool in viewer_allowed:
            assert check_tool_access(tool, "viewer") is True, f"Viewer denied access to {tool}"

    def test_viewer_denied_admin_tools(self):
        from src.auth.middleware import check_tool_access
        admin_only = [
            "invest_update_position",
            "invest_close_position",
            "invest_update_cash",
            "invest_create_trade_plan",
            "invest_update_trade_plan",
            "invest_screen_candidate",
            "invest_list_rejected_candidates",
            "invest_verify_order",
            "invest_schwab",
            "invest_admin",
            "invest_get_filing",
        ]
        for tool in admin_only:
            assert check_tool_access(tool, "viewer") is False, f"Viewer allowed access to {tool}"

    def test_viewer_lessons_search_allowed(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_lessons", "viewer", "search") is True

    def test_viewer_lessons_add_denied(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_lessons", "viewer", "add") is False

    def test_viewer_principles_list_allowed(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_principles", "viewer", "list") is True

    def test_viewer_principles_add_denied(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_principles", "viewer", "add") is False

    def test_viewer_calendar_list_allowed(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_calendar", "viewer", "list") is True

    def test_viewer_calendar_add_denied(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_calendar", "viewer", "add") is False

    def test_viewer_weights_get_allowed(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_weights", "viewer", "get") is True

    def test_viewer_weights_update_denied(self):
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_weights", "viewer", "update") is False

    def test_viewer_no_action_on_restricted_tool_allowed(self):
        """Viewer accessing a viewer tool without an action should be allowed."""
        from src.auth.middleware import check_tool_access
        assert check_tool_access("invest_lessons", "viewer") is True
        assert check_tool_access("invest_principles", "viewer") is True
        assert check_tool_access("invest_correlation", "viewer") is True


# ---------------------------------------------------------------------------
# VIEWER_TOOLS set
# ---------------------------------------------------------------------------
class TestViewerTools:

    def test_viewer_tools_is_a_set(self):
        from src.auth.middleware import VIEWER_TOOLS
        assert isinstance(VIEWER_TOOLS, set)

    def test_viewer_tools_count(self):
        from src.auth.middleware import VIEWER_TOOLS
        assert len(VIEWER_TOOLS) == 9

    def test_viewer_tools_contains_expected(self):
        from src.auth.middleware import VIEWER_TOOLS
        expected = {
            "invest_get_portfolio",
            "invest_get_trade",
            "invest_list_trades",
            "invest_lessons",
            "invest_principles",
            "invest_market_data",
            "invest_calendar",
            "invest_correlation",
            "invest_weights",
        }
        assert VIEWER_TOOLS == expected

    def test_viewer_tools_does_not_contain_admin(self):
        from src.auth.middleware import VIEWER_TOOLS
        assert "invest_admin" not in VIEWER_TOOLS
        assert "invest_schwab" not in VIEWER_TOOLS
        assert "invest_update_position" not in VIEWER_TOOLS


# ---------------------------------------------------------------------------
# validate_openbb_token
# ---------------------------------------------------------------------------
class TestValidateOpenbbToken:

    def test_valid_token(self):
        from src.auth.middleware import validate_openbb_token
        with patch.dict(os.environ, {"OPENBB_BACKEND_TOKEN": "my-secret-token"}):
            # Need to reimport to pick up new env var
            import importlib
            import src.auth.middleware as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.validate_openbb_token("my-secret-token") is True

    def test_invalid_token(self):
        from src.auth.middleware import validate_openbb_token
        with patch.dict(os.environ, {"OPENBB_BACKEND_TOKEN": "my-secret-token"}):
            import importlib
            import src.auth.middleware as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.validate_openbb_token("wrong-token") is False

    def test_empty_env_var_returns_false(self):
        """When OPENBB_BACKEND_TOKEN is empty, validation should fail."""
        from src.auth.middleware import validate_openbb_token
        with patch.dict(os.environ, {"OPENBB_BACKEND_TOKEN": ""}):
            import importlib
            import src.auth.middleware as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.validate_openbb_token("") is False

    def test_missing_env_var_returns_false(self):
        """When OPENBB_BACKEND_TOKEN is not set, validation should fail."""
        env = os.environ.copy()
        env.pop("OPENBB_BACKEND_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import src.auth.middleware as auth_mod
            importlib.reload(auth_mod)
            assert auth_mod.validate_openbb_token("any-token") is False
