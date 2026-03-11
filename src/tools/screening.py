"""Module C: Screening tools (2 tools)."""

from datetime import date as date_type
from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import CandidateScreen
from src.validation import validate_ticker


async def _run_screen(
    ticker: str,
    price: float,
    catalyst_type: str,
    conviction_pct: int,
) -> dict:
    """Internal screening logic — also called by trade plan creation."""
    ticker = validate_ticker(ticker)
    fail_reasons = []

    # Fetch consensus + beta from OpenBB
    consensus_target = None
    beta = None
    try:
        from src.integrations.market_data import get_analyst_consensus, get_fundamentals
        consensus = await get_analyst_consensus(ticker)
        results = consensus.get("results", [])
        if results:
            consensus_target = results[0].get("target_consensus")

        fundamentals = await get_fundamentals(ticker)
        fund_results = fundamentals.get("results", [])
        if fund_results:
            beta = fund_results[0].get("beta")
    except Exception:
        pass

    # Check criteria
    if conviction_pct < 55:
        fail_reasons.append(f"Conviction {conviction_pct}% below 55% threshold")

    price_vs_consensus = None
    if consensus_target and consensus_target > 0:
        price_vs_consensus = round((price / consensus_target - 1) * 100, 2)
        if price > consensus_target:
            fail_reasons.append(f"Price ${price} above consensus ${consensus_target}")

    pass_fail = "fail" if fail_reasons else "pass"

    # Store screening result
    async with async_session() as db:
        screen = CandidateScreen(
            ticker=ticker,
            screened_at=date_type.today(),
            price_at_screen=Decimal(str(price)),
            analyst_consensus=Decimal(str(consensus_target)) if consensus_target else None,
            price_vs_consensus=Decimal(str(price_vs_consensus)) if price_vs_consensus is not None else None,
            beta=Decimal(str(beta)) if beta else None,
            conviction_score=conviction_pct,
            catalyst_type=catalyst_type or None,
            pass_fail=pass_fail,
            fail_reasons=fail_reasons if fail_reasons else None,
        )
        db.add(screen)
        await db.commit()
        await db.refresh(screen)

    return {
        "screen_id": screen.id,
        "ticker": ticker,
        "pass_fail": pass_fail,
        "fail_reasons": fail_reasons,
        "consensus_target": consensus_target,
        "price_vs_consensus": price_vs_consensus,
        "beta": beta,
    }


def register_screening_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_screen_candidate(
        ticker: str,
        price: float,
        catalyst_type: str = "",
        conviction_pct: int = 0,
    ) -> dict:
        """Screen a candidate ticker. Fetches consensus + beta from OpenBB.
        Returns pass/fail per criterion."""
        return await _run_screen(ticker, price, catalyst_type, conviction_pct)

    @mcp.tool()
    async def invest_list_rejected_candidates(
        fail_reason: str = "",
        sector: str = "",
        limit: int = 20,
    ) -> dict:
        """List rejected candidates with optional filters."""
        async with async_session() as db:
            query = select(CandidateScreen).where(CandidateScreen.pass_fail == "fail")
            query = query.order_by(CandidateScreen.id.desc()).limit(limit)
            result = await db.execute(query)
            screens = result.scalars().all()

        filtered = screens
        if fail_reason:
            filtered = [
                s for s in screens
                if s.fail_reasons and any(fail_reason.lower() in r.lower() for r in s.fail_reasons)
            ]

        return {
            "rejected": [
                {
                    "id": s.id,
                    "ticker": s.ticker,
                    "screened_at": s.screened_at.isoformat() if s.screened_at else None,
                    "price_at_screen": float(s.price_at_screen) if s.price_at_screen else None,
                    "fail_reasons": s.fail_reasons,
                    "conviction_score": s.conviction_score,
                }
                for s in filtered
            ],
            "count": len(filtered),
        }
