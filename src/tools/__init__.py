from src.tools.admin import register_admin_tools
from src.tools.calendar import register_calendar_tools
from src.tools.correlation import register_correlation_tools
from src.tools.learning import register_learning_tools
from src.tools.market_data import register_market_data_tools
from src.tools.order_verify import register_order_verify_tools
from src.tools.portfolio import register_portfolio_tools
from src.tools.principles import register_principles_tools
from src.tools.screening import register_screening_tools
from src.tools.schwab import register_schwab_tools
from src.tools.trades import register_trade_tools


def register_all_tools(mcp):
    register_portfolio_tools(mcp)       # Module A (4 tools)
    register_trade_tools(mcp)           # Module B (4 tools)
    register_screening_tools(mcp)       # Module C (2 tools)
    register_learning_tools(mcp)        # Module D (2 tools)
    register_principles_tools(mcp)      # Module E (1 tool)
    register_market_data_tools(mcp)     # Module F (2 tools)
    register_calendar_tools(mcp)        # Module G (1 tool)
    register_correlation_tools(mcp)     # Module H (1 tool)
    register_order_verify_tools(mcp)    # Module I (1 tool)
    register_schwab_tools(mcp)          # Module J (1 tool)
    register_admin_tools(mcp)           # Module K (1 tool)
