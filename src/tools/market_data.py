"""Module F: Market data tools (2 tools)."""

from mcp.server.fastmcp import FastMCP


def register_market_data_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_market_data(
        type: str,
        symbol: str = "",
        quarters: int = 8,
        series: str = "CPIAUCSL",
    ) -> dict:
        """Get market data from OpenBB ODP.
        type: quote | fundamentals | earnings_history | gold | macro
        - quote: live price for symbol
        - fundamentals: key metrics for symbol
        - earnings_history: past earnings for symbol
        - gold: current gold spot price
        - macro: FRED economic series"""
        from src.integrations.market_data import (
            get_analyst_consensus,
            get_earnings_history,
            get_fundamentals,
            get_gold_price,
            get_macro,
            get_quote,
        )

        if type == "quote":
            if not symbol:
                return {"error": "symbol is required for quote"}
            return await get_quote(symbol)

        elif type == "fundamentals":
            if not symbol:
                return {"error": "symbol is required for fundamentals"}
            data = await get_fundamentals(symbol)
            # Also fetch consensus for context
            try:
                consensus = await get_analyst_consensus(symbol)
                data["consensus"] = consensus
            except Exception:
                pass
            return data

        elif type == "earnings_history":
            if not symbol:
                return {"error": "symbol is required for earnings_history"}
            return await get_earnings_history(symbol, quarters)

        elif type == "gold":
            return await get_gold_price()

        elif type == "macro":
            return await get_macro(series)

        return {"error": f"Unknown type: {type}. Use quote, fundamentals, earnings_history, gold, or macro."}

    @mcp.tool()
    async def invest_get_filing(
        ticker: str,
        filing_type: str = "10-K",
        filing_date: str = "",
    ) -> dict:
        """Get an SEC filing for a ticker. Uses OpenBB ODP."""
        from src.cache import TTL_FILING, cached_fetch

        cache_key = f"obb:filing:{ticker}:{filing_type}:{filing_date}"
        try:
            from openbb import obb
            data = await cached_fetch(
                cache_key=cache_key,
                ttl_seconds=TTL_FILING,
                source="openbb",
                fetch_fn=lambda: obb.equity.fundamental.filings(
                    ticker, type=filing_type, provider="fmp"
                ).to_dict(),
            )
            return data
        except Exception as e:
            return {"error": str(e)}
