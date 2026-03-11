"""Module H: Correlation tool (1 tool)."""

import asyncio
from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import CorrelationSnapshot, Portfolio, Position


def _compute_correlation(hist_data: dict, tickers: list[str]) -> dict:
    """Compute pairwise correlation matrix from historical price data using pandas."""
    import pandas as pd

    results = hist_data.get("results", [])
    if not results:
        # Return identity if no data
        return {t: {t2: 1.0 if t == t2 else 0.0 for t2 in tickers} for t in tickers}

    # Build a DataFrame of daily close prices per ticker
    # OpenBB returns a list of dicts with date, open, high, low, close, volume, symbol
    rows = []
    for r in results:
        if isinstance(r, dict):
            rows.append(r)
        elif isinstance(r, list):
            rows.extend(r)

    if not rows:
        return {t: {t2: 1.0 if t == t2 else 0.0 for t2 in tickers} for t in tickers}

    df = pd.DataFrame(rows)

    # Handle different OpenBB response formats
    if "symbol" in df.columns and "close" in df.columns and "date" in df.columns:
        pivot = df.pivot_table(index="date", columns="symbol", values="close")
    elif "close" in df.columns:
        # Single ticker — can't correlate
        return {t: {t2: 1.0 if t == t2 else 0.0 for t2 in tickers} for t in tickers}
    else:
        return {t: {t2: 1.0 if t == t2 else 0.0 for t2 in tickers} for t in tickers}

    # Calculate daily returns
    returns = pivot.pct_change().dropna()

    if returns.empty or len(returns) < 5:
        return {t: {t2: 1.0 if t == t2 else 0.0 for t2 in tickers} for t in tickers}

    # Correlation matrix
    corr = returns.corr()

    # Convert to nested dict, handling tickers that might not be in the data
    matrix = {}
    for t in tickers:
        matrix[t] = {}
        for t2 in tickers:
            if t in corr.columns and t2 in corr.columns:
                val = corr.loc[t, t2]
                matrix[t][t2] = round(float(val), 4) if not pd.isna(val) else 0.0
            else:
                matrix[t][t2] = 1.0 if t == t2 else 0.0

    return matrix


def _compute_portfolio_beta(hist_data: dict, tickers: list[str], shares_map: dict) -> float | None:
    """Compute weighted portfolio beta using SPY as benchmark."""
    import pandas as pd

    results = hist_data.get("results", [])
    if not results:
        return None

    df = pd.DataFrame(results if isinstance(results[0], dict) else [r for sublist in results for r in sublist])

    if "symbol" not in df.columns or "close" not in df.columns:
        return None

    pivot = df.pivot_table(index="date", columns="symbol", values="close")
    returns = pivot.pct_change().dropna()

    if "SPY" not in returns.columns or returns.empty:
        return None

    spy_returns = returns["SPY"]
    spy_var = spy_returns.var()
    if spy_var == 0:
        return None

    total_value = sum(shares_map.values())
    if total_value == 0:
        return None

    portfolio_beta = 0.0
    for t in tickers:
        if t in returns.columns and t != "SPY":
            beta = returns[t].cov(spy_returns) / spy_var
            weight = shares_map.get(t, 0) / total_value
            portfolio_beta += float(beta) * weight

    return round(portfolio_beta, 3)


def register_correlation_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_correlation(
        action: str,
        ticker: str = "",
    ) -> dict:
        """Portfolio correlation analysis.
        action: impact | snapshot
        - impact: what adding ticker would do to portfolio correlation
        - snapshot: current correlation matrix + concentration + beta"""
        async with async_session() as db:
            result = await db.execute(
                select(Position).where(Position.status == "open")
            )
            positions = result.scalars().all()
            tickers = [p.ticker for p in positions]

            if not tickers:
                return {"error": "No open positions for correlation analysis"}

            if action == "impact" and ticker:
                analysis_tickers = tickers + [ticker] if ticker not in tickers else tickers
            else:
                analysis_tickers = tickers

        # Shares map for beta weighting
        shares_map = {p.ticker: float(p.shares * p.cost_basis) for p in positions}

        # Fetch historical prices (include SPY for beta)
        fetch_tickers = list(set(analysis_tickers + ["SPY"]))
        try:
            from src.integrations.market_data import get_historical_prices
            hist = await get_historical_prices(fetch_tickers)
        except Exception as e:
            return {"error": f"Failed to fetch historical prices: {e}"}

        # Compute correlation (CPU-bound, run in thread)
        correlation_matrix = await asyncio.to_thread(_compute_correlation, hist, analysis_tickers)
        portfolio_beta = await asyncio.to_thread(_compute_portfolio_beta, hist, tickers, shares_map)

        # Sector concentration
        sectors = {}
        for p in positions:
            s = p.sector or "unknown"
            val = float(p.shares * p.cost_basis)
            sectors[s] = sectors.get(s, 0) + val
        total = sum(sectors.values()) or 1
        tech_pct = round(sectors.get("technology", 0) / total * 100, 2)
        semi_pct = round(sectors.get("semiconductors", 0) / total * 100, 2)
        tech_concentration = tech_pct + semi_pct

        # Flags
        flags = []
        if tech_concentration > 40:
            flags.append(f"Tech+semi concentration at {tech_concentration}% (limit 40%)")
        for sector, val in sectors.items():
            pct = round(val / total * 100, 2)
            if pct > 40:
                flags.append(f"{sector} concentration at {pct}% (limit 40%)")

        # Flag highly correlated pairs (>0.8)
        for i, t1 in enumerate(analysis_tickers):
            for t2 in analysis_tickers[i + 1:]:
                corr_val = correlation_matrix.get(t1, {}).get(t2, 0)
                if abs(corr_val) > 0.8:
                    flags.append(f"High correlation: {t1}/{t2} = {corr_val}")

        # Store snapshot
        async with async_session() as db:
            snapshot = CorrelationSnapshot(
                tickers=analysis_tickers,
                correlation_matrix=correlation_matrix,
                tech_concentration_pct=Decimal(str(tech_concentration)),
                portfolio_beta=Decimal(str(portfolio_beta)) if portfolio_beta is not None else None,
                flags=flags if flags else None,
            )
            db.add(snapshot)
            await db.commit()

        result_data = {
            "tickers": analysis_tickers,
            "correlation_matrix": correlation_matrix,
            "sector_breakdown": {k: round(v / total * 100, 2) for k, v in sectors.items()},
            "tech_concentration_pct": tech_concentration,
            "portfolio_beta": portfolio_beta,
            "flags": flags,
        }

        if action == "impact" and ticker:
            result_data["impact_ticker"] = ticker
            result_data["impact_note"] = f"Analysis includes hypothetical {ticker} addition"

        return result_data
