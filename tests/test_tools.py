"""Test MCP tool registration — all 20 tools register correctly."""

import pytest
from mcp.server.fastmcp import FastMCP


# Expected tool names from the spec (20 tools total)
EXPECTED_TOOLS = {
    # Module A: Portfolio (4)
    "invest_get_portfolio",
    "invest_update_position",
    "invest_close_position",
    "invest_update_cash",
    # Module B: Trades (4)
    "invest_create_trade_plan",
    "invest_get_trade",
    "invest_list_trades",
    "invest_update_trade_plan",
    # Module C: Screening (2)
    "invest_screen_candidate",
    "invest_list_rejected_candidates",
    # Module D: Learning (2)
    "invest_weights",
    "invest_lessons",
    # Module E: Principles (1)
    "invest_principles",
    # Module F: Market data (2)
    "invest_market_data",
    "invest_get_filing",
    # Module G: Calendar (1)
    "invest_calendar",
    # Module H: Correlation (1)
    "invest_correlation",
    # Module I: Order verification (1)
    "invest_verify_order",
    # Module J: Schwab (1)
    "invest_schwab",
    # Module K: Admin (1)
    "invest_admin",
}


@pytest.fixture
def mcp_instance():
    """Create a fresh FastMCP instance and register all tools."""
    mcp = FastMCP("TestMCP")
    from src.tools import register_all_tools
    register_all_tools(mcp)
    return mcp


def test_all_20_tools_registered(mcp_instance):
    """All 20 tools should be registered on the FastMCP instance."""
    # FastMCP stores tools in _tool_manager._tools (dict keyed by name)
    tool_manager = mcp_instance._tool_manager
    registered_tools = tool_manager._tools
    registered_names = set(registered_tools.keys())

    assert len(registered_names) == 20, (
        f"Expected 20 tools, got {len(registered_names)}: {registered_names}"
    )


def test_all_expected_tool_names_present(mcp_instance):
    """Every expected tool name should be present."""
    tool_manager = mcp_instance._tool_manager
    registered_names = set(tool_manager._tools.keys())

    missing = EXPECTED_TOOLS - registered_names
    extra = registered_names - EXPECTED_TOOLS

    assert not missing, f"Missing tools: {missing}"
    assert not extra, f"Unexpected tools: {extra}"


def test_tools_have_correct_names(mcp_instance):
    """Each tool's name attribute should match its registration key."""
    tool_manager = mcp_instance._tool_manager
    for name, tool in tool_manager._tools.items():
        assert tool.name == name, f"Tool name mismatch: key={name}, tool.name={tool.name}"


def test_tool_functions_are_callable(mcp_instance):
    """Each registered tool's function should be callable."""
    tool_manager = mcp_instance._tool_manager
    for name, tool in tool_manager._tools.items():
        assert tool.fn is not None, f"Tool {name} has no function"
        assert callable(tool.fn), f"Tool {name}'s function is not callable"


def test_individual_module_registration():
    """Test that individual module registrations work independently."""
    from src.tools.portfolio import register_portfolio_tools
    from src.tools.trades import register_trade_tools
    from src.tools.screening import register_screening_tools
    from src.tools.learning import register_learning_tools
    from src.tools.principles import register_principles_tools
    from src.tools.market_data import register_market_data_tools
    from src.tools.calendar import register_calendar_tools
    from src.tools.correlation import register_correlation_tools
    from src.tools.order_verify import register_order_verify_tools
    from src.tools.schwab import register_schwab_tools
    from src.tools.admin import register_admin_tools

    expected_counts = {
        "portfolio": (register_portfolio_tools, 4),
        "trades": (register_trade_tools, 4),
        "screening": (register_screening_tools, 2),
        "learning": (register_learning_tools, 2),
        "principles": (register_principles_tools, 1),
        "market_data": (register_market_data_tools, 2),
        "calendar": (register_calendar_tools, 1),
        "correlation": (register_correlation_tools, 1),
        "order_verify": (register_order_verify_tools, 1),
        "schwab": (register_schwab_tools, 1),
        "admin": (register_admin_tools, 1),
    }

    for module_name, (register_fn, expected_count) in expected_counts.items():
        mcp = FastMCP(f"Test_{module_name}")
        register_fn(mcp)
        actual = len(mcp._tool_manager._tools)
        assert actual == expected_count, (
            f"Module {module_name}: expected {expected_count} tools, got {actual}"
        )
