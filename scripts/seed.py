"""Seed script — populates initial data on first deployment."""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from src.db import async_session, create_tables
from src.models import (
    CandidateScreen,
    CashBalance,
    CatalystCalendar,
    DimensionWeight,
    Lesson,
    Portfolio,
    Position,
    Principle,
)


async def seed():
    await create_tables()
    async with async_session() as db:
        # Check if already seeded
        existing = await db.execute(select(Portfolio))
        if existing.scalars().first():
            print("Database already seeded — skipping.")
            return

        # --- Portfolios ---
        roth = Portfolio(account_name="Roth IRA", account_type="roth_ira", broker="Schwab")
        custodial = Portfolio(account_name="Custodial", account_type="custodial", broker="Schwab")
        db.add_all([roth, custodial])
        await db.flush()  # get IDs

        # --- Positions (Roth IRA) ---
        db.add_all([
            Position(
                portfolio_id=roth.id, ticker="RBRK", company_name="Rubrik",
                sector="cybersecurity", shares=Decimal("74"), cost_basis=Decimal("47.0000"),
                stop_loss=Decimal("44.0000"), status="open",
            ),
            Position(
                portfolio_id=roth.id, ticker="DKNG", company_name="DraftKings",
                sector="gaming", shares=Decimal("140"), cost_basis=Decimal("22.5800"),
                stop_loss=Decimal("19.0000"), status="open",
            ),
        ])

        # --- Positions (Custodial) ---
        db.add_all([
            Position(
                portfolio_id=custodial.id, ticker="MRVL", company_name="Marvell Technology",
                sector="semiconductors", shares=Decimal("15"), cost_basis=Decimal("0.0000"),
                status="open",
            ),
            Position(
                portfolio_id=custodial.id, ticker="TSM", company_name="TSMC",
                sector="semiconductors", shares=Decimal("6"), cost_basis=Decimal("0.0000"),
                status="open",
            ),
        ])

        # --- Cash Balances ---
        today = date.today()
        db.add_all([
            CashBalance(
                portfolio_id=roth.id, instrument="USD",
                balance=Decimal("3522.00"), as_of_date=today,
            ),
            CashBalance(
                portfolio_id=custodial.id, instrument="SWVXX",
                balance=Decimal("5014.00"), as_of_date=today,
            ),
            CashBalance(
                portfolio_id=custodial.id, instrument="USD",
                balance=Decimal("5000.00"), as_of_date=today,
            ),
        ])

        # --- Rejected Candidates ---
        db.add_all([
            CandidateScreen(
                ticker="ROST", screened_at=today, pass_fail="fail",
                fail_reasons=["Price above analyst consensus"],
            ),
            CandidateScreen(
                ticker="LLY", screened_at=today, pass_fail="fail",
                fail_reasons=["Position size too small at current price"],
            ),
            CandidateScreen(
                ticker="SOFI", screened_at=today, pass_fail="fail",
                fail_reasons=["Conviction below 55% threshold"],
                conviction_score=50,
            ),
            CandidateScreen(
                ticker="LMT", screened_at=today, pass_fail="fail",
                fail_reasons=["Risk/reward ratio below minimum"],
            ),
        ])

        # --- Lessons ---
        db.add(Lesson(
            lesson_text="Size down on strong thesis / uncertain magnitude. "
                        "LNG position was too large relative to catalyst uncertainty.",
            lesson_type="sizing",
            sector_tag="energy",
            catalyst_tag="earnings",
            outcome_tag="loss",
        ))

        # --- Principles ---
        db.add_all([
            Principle(
                principle_text="Never enter a position with conviction below 55%.",
                category="entry",
            ),
            Principle(
                principle_text="Price must be below analyst consensus target to enter.",
                category="entry",
            ),
            Principle(
                principle_text="Position size must match conviction level — higher conviction = larger size.",
                category="sizing",
            ),
            Principle(
                principle_text="Maintain sector diversification — no single sector above 40% of portfolio.",
                category="risk",
            ),
            Principle(
                principle_text="Consider post-earnings dips as entry opportunities, not panic signals.",
                category="entry",
            ),
            Principle(
                principle_text="Set stop-loss before entry and never widen it.",
                category="risk",
            ),
        ])

        # --- Catalyst Calendar ---
        db.add_all([
            CatalystCalendar(
                event_date=date(2025, 3, 17), event_type="macro",
                description="FOMC Meeting Mar 17-18", impact_level="high", source="manual",
            ),
            CatalystCalendar(
                event_date=date(2025, 3, 12), event_type="earnings",
                ticker="RBRK", description="RBRK Q4 Earnings (estimated)",
                impact_level="high", source="manual",
            ),
            CatalystCalendar(
                event_date=date(2025, 4, 30), event_type="earnings",
                ticker="DKNG", description="DKNG Q1 Earnings (estimated)",
                impact_level="high", source="manual",
            ),
            CatalystCalendar(
                event_date=date(2025, 5, 6), event_type="earnings",
                description="Barrick Gold Q1 Earnings", impact_level="medium", source="manual",
            ),
            CatalystCalendar(
                event_date=date(2025, 6, 11), event_type="macro",
                description="FIFA Club World Cup Jun 11 - Jul 19",
                impact_level="low", source="manual",
            ),
        ])

        # --- Dimension Weights (v1 — all equal) ---
        db.add(DimensionWeight(
            version=1, trade_count=0,
            research_quality_weight=Decimal("0.2000"),
            entry_timing_weight=Decimal("0.2000"),
            position_sizing_weight=Decimal("0.2000"),
            stop_loss_weight=Decimal("0.2000"),
            exit_timing_weight=Decimal("0.2000"),
            update_reason="Initial equal weights",
            update_method="initial",
        ))

        await db.commit()
        print("Seed data loaded successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
