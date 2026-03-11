"""OpenBB ODP wrapper — sync calls wrapped in asyncio.to_thread via cached_fetch."""

from openbb import obb

from src.cache import (
    TTL_CONSENSUS,
    TTL_EARNINGS,
    TTL_FILING,
    TTL_FUNDAMENTALS,
    TTL_GOLD,
    TTL_MACRO,
    TTL_QUOTE,
    cached_fetch,
)


async def get_quote(symbol: str) -> dict:
    return await cached_fetch(
        cache_key=f"obb:quote:{symbol}",
        ttl_seconds=TTL_QUOTE,
        source="openbb",
        fetch_fn=lambda: obb.equity.price.quote(symbol, provider="fmp").to_dict(),
    )


async def get_fundamentals(ticker: str) -> dict:
    return await cached_fetch(
        cache_key=f"obb:fundamentals:{ticker}",
        ttl_seconds=TTL_FUNDAMENTALS,
        source="openbb",
        fetch_fn=lambda: obb.equity.fundamental.metrics(ticker, provider="fmp").to_dict(),
    )


async def get_analyst_consensus(ticker: str) -> dict:
    return await cached_fetch(
        cache_key=f"obb:consensus:{ticker}",
        ttl_seconds=TTL_CONSENSUS,
        source="openbb",
        fetch_fn=lambda: obb.equity.estimates.consensus(ticker, provider="fmp").to_dict(),
    )


async def get_earnings_history(ticker: str, quarters: int = 8) -> dict:
    return await cached_fetch(
        cache_key=f"obb:earnings:{ticker}:{quarters}",
        ttl_seconds=TTL_EARNINGS,
        source="openbb",
        fetch_fn=lambda: obb.equity.estimates.historical(ticker, provider="fmp").to_dict(),
    )


async def get_macro(series: str = "CPIAUCSL") -> dict:
    return await cached_fetch(
        cache_key=f"obb:macro:{series}",
        ttl_seconds=TTL_MACRO,
        source="openbb",
        fetch_fn=lambda: obb.economy.fred_series(series).to_dict(),
    )


async def get_gold_price() -> dict:
    return await cached_fetch(
        cache_key="obb:gold",
        ttl_seconds=TTL_GOLD,
        source="openbb",
        fetch_fn=lambda: obb.commodity.price.spot("gold").to_dict(),
    )


async def get_historical_prices(tickers: list[str], period: str = "1y") -> dict:
    """Get historical prices for correlation analysis."""
    key = f"obb:historical:{','.join(sorted(tickers))}:{period}"
    return await cached_fetch(
        cache_key=key,
        ttl_seconds=TTL_FUNDAMENTALS,
        source="openbb",
        fetch_fn=lambda: obb.equity.price.historical(
            ",".join(tickers), provider="fmp", period=period
        ).to_dict(),
    )
