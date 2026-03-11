"""Test all 19 SQLAlchemy models — instantiation, required fields, and relationships."""

import pytest
import pytest_asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db import Base
from src.models import (
    ApiCache,
    ApiRateLimit,
    AuditLog,
    CandidateScreen,
    CashBalance,
    CatalystCalendar,
    CorrelationSnapshot,
    DimensionWeight,
    Lesson,
    NotificationLog,
    OrderVerification,
    PendingOperation,
    Portfolio,
    Position,
    Principle,
    SchwabTokenState,
    Trade,
    TradeScore,
    User,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def engine():
    """Fresh in-memory SQLite engine per test."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


# ---------------------------------------------------------------------------
# 1. Portfolio
# ---------------------------------------------------------------------------
async def test_portfolio_create(session):
    p = Portfolio(account_name="Main IRA", account_type="roth_ira", broker="Schwab")
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.account_name == "Main IRA"
    assert p.account_type == "roth_ira"
    assert p.broker == "Schwab"


async def test_portfolio_default_broker(session):
    p = Portfolio(account_name="Test", account_type="taxable")
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.broker == "Schwab"


# ---------------------------------------------------------------------------
# 2. Position
# ---------------------------------------------------------------------------
async def test_position_create(session):
    port = Portfolio(account_name="Test", account_type="roth_ira")
    session.add(port)
    await session.commit()
    await session.refresh(port)

    pos = Position(
        portfolio_id=port.id,
        ticker="AAPL",
        shares=Decimal("10.0000"),
        cost_basis=Decimal("150.0000"),
        status="open",
    )
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    assert pos.id is not None
    assert pos.ticker == "AAPL"
    assert pos.portfolio_id == port.id


async def test_position_optional_fields(session):
    port = Portfolio(account_name="Test", account_type="custodial")
    session.add(port)
    await session.commit()
    await session.refresh(port)

    pos = Position(
        portfolio_id=port.id,
        ticker="MSFT",
        shares=Decimal("5.0000"),
        cost_basis=Decimal("300.0000"),
        company_name="Microsoft",
        sector="technology",
        stop_loss=Decimal("280.0000"),
        target_1=Decimal("350.0000"),
        target_2=Decimal("400.0000"),
        target_3=Decimal("450.0000"),
        status="open",
    )
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    assert pos.company_name == "Microsoft"
    assert pos.stop_loss == Decimal("280.0000")
    assert pos.target_3 == Decimal("450.0000")


# ---------------------------------------------------------------------------
# 3. CashBalance
# ---------------------------------------------------------------------------
async def test_cash_balance_create(session):
    port = Portfolio(account_name="Test", account_type="roth_ira")
    session.add(port)
    await session.commit()
    await session.refresh(port)

    cb = CashBalance(
        portfolio_id=port.id,
        instrument="USD",
        balance=Decimal("5000.00"),
        as_of_date=date.today(),
    )
    session.add(cb)
    await session.commit()
    await session.refresh(cb)
    assert cb.id is not None
    assert cb.instrument == "USD"
    assert cb.balance == Decimal("5000.00")


# ---------------------------------------------------------------------------
# 4. Trade
# ---------------------------------------------------------------------------
async def test_trade_create(session):
    t = Trade(
        ticker="NVDA",
        decision="waiting",
        entry_price=Decimal("800.0000"),
        shares=Decimal("5.0000"),
        stop_loss=Decimal("750.0000"),
        target_1=Decimal("900.0000"),
        thesis_summary="AI demand surge",
        sector="semiconductors",
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    assert t.id is not None
    assert t.ticker == "NVDA"
    assert t.decision == "waiting"


async def test_trade_optional_fields(session):
    t = Trade(ticker="AMD", decision="rejected", rejection_reason="Beta too high")
    session.add(t)
    await session.commit()
    await session.refresh(t)
    assert t.rejection_reason == "Beta too high"
    assert t.entry_price is None
    assert t.outcome is None


# ---------------------------------------------------------------------------
# 5. TradeScore
# ---------------------------------------------------------------------------
async def test_trade_score_create(session):
    t = Trade(ticker="TST", decision="executed")
    session.add(t)
    await session.commit()
    await session.refresh(t)

    score = TradeScore(
        trade_id=t.id,
        research_quality_score=8,
        entry_timing_score=7,
        position_sizing_score=6,
        stop_loss_score=9,
        exit_timing_score=5,
        composite_score=Decimal("7.00"),
        outcome="win",
        process_vs_outcome="good_process_good_outcome",
    )
    session.add(score)
    await session.commit()
    await session.refresh(score)
    assert score.id is not None
    assert score.research_quality_score == 8
    assert score.composite_score == Decimal("7.00")


# ---------------------------------------------------------------------------
# 6. DimensionWeight
# ---------------------------------------------------------------------------
async def test_dimension_weight_create(session):
    dw = DimensionWeight(
        version=1,
        research_quality_weight=Decimal("0.2000"),
        entry_timing_weight=Decimal("0.2000"),
        position_sizing_weight=Decimal("0.2000"),
        stop_loss_weight=Decimal("0.2000"),
        exit_timing_weight=Decimal("0.2000"),
        update_method="initial",
    )
    session.add(dw)
    await session.commit()
    await session.refresh(dw)
    assert dw.version == 1
    assert dw.research_quality_weight == Decimal("0.2000")


# ---------------------------------------------------------------------------
# 7. Lesson
# ---------------------------------------------------------------------------
async def test_lesson_create(session):
    lesson = Lesson(
        lesson_text="Always set a stop-loss before entering a trade",
        lesson_type="risk_management",
        sector_tag="technology",
        outcome_tag="loss",
    )
    session.add(lesson)
    await session.commit()
    await session.refresh(lesson)
    assert lesson.id is not None
    assert lesson.lesson_text.startswith("Always")


# ---------------------------------------------------------------------------
# 8. Principle
# ---------------------------------------------------------------------------
async def test_principle_create(session):
    p = Principle(
        principle_text="Never trade with conviction below 55%",
        category="risk",
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    assert p.id is not None
    assert p.active is True
    assert p.times_applied == 0
    assert p.times_violated == 0


# ---------------------------------------------------------------------------
# 9. CandidateScreen
# ---------------------------------------------------------------------------
async def test_candidate_screen_create(session):
    cs = CandidateScreen(
        ticker="GOOG",
        screened_at=date.today(),
        price_at_screen=Decimal("180.0000"),
        conviction_score=70,
        pass_fail="pass",
    )
    session.add(cs)
    await session.commit()
    await session.refresh(cs)
    assert cs.id is not None
    assert cs.pass_fail == "pass"


# ---------------------------------------------------------------------------
# 10. CatalystCalendar
# ---------------------------------------------------------------------------
async def test_catalyst_calendar_create(session):
    event = CatalystCalendar(
        event_date=date(2026, 4, 15),
        event_type="earnings",
        ticker="AAPL",
        description="Q2 Earnings",
        impact_level="high",
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    assert event.id is not None
    assert event.event_type == "earnings"


# ---------------------------------------------------------------------------
# 11. CorrelationSnapshot
# ---------------------------------------------------------------------------
async def test_correlation_snapshot_create(session):
    snap = CorrelationSnapshot(
        tickers=["AAPL", "MSFT"],
        correlation_matrix={"AAPL": {"AAPL": 1.0, "MSFT": 0.85}, "MSFT": {"AAPL": 0.85, "MSFT": 1.0}},
        tech_concentration_pct=Decimal("45.00"),
        portfolio_beta=Decimal("1.10"),
        flags=["High correlation: AAPL/MSFT = 0.85"],
    )
    session.add(snap)
    await session.commit()
    await session.refresh(snap)
    assert snap.id is not None
    assert snap.tickers == ["AAPL", "MSFT"]


# ---------------------------------------------------------------------------
# 12. OrderVerification
# ---------------------------------------------------------------------------
async def test_order_verification_create(session):
    t = Trade(ticker="TEST", decision="executed")
    session.add(t)
    await session.commit()
    await session.refresh(t)

    ov = OrderVerification(
        trade_id=t.id,
        order_type="limit_buy",
        shares_ordered=Decimal("10.0000"),
        price_ordered=Decimal("150.0000"),
        stop_price=Decimal("140.0000"),
        gtc=True,
        result="pass",
    )
    session.add(ov)
    await session.commit()
    await session.refresh(ov)
    assert ov.id is not None
    assert ov.result == "pass"


# ---------------------------------------------------------------------------
# 13. User
# ---------------------------------------------------------------------------
async def test_user_create(session):
    u = User(
        auth0_sub="auth0|1234567890",
        email="test@example.com",
        display_name="Test User",
        role="owner",
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    assert u.id is not None
    assert u.role == "owner"
    assert u.is_active is True


# ---------------------------------------------------------------------------
# 14. AuditLog
# ---------------------------------------------------------------------------
async def test_audit_log_create(session):
    # BigInteger PK requires explicit id on SQLite (no auto-increment for BigInteger)
    al = AuditLog(
        id=1,
        tool_name="invest_get_portfolio",
        success=True,
        duration_ms=42,
        input_summary={"account_type": "roth_ira"},
        output_summary="5 positions returned",
    )
    session.add(al)
    await session.commit()
    await session.refresh(al)
    assert al.id == 1
    assert al.tool_name == "invest_get_portfolio"
    assert al.success is True


# ---------------------------------------------------------------------------
# 15. SchwabTokenState
# ---------------------------------------------------------------------------
async def test_schwab_token_state_create(session):
    sts = SchwabTokenState(
        encrypted_refresh_token="gAAAA...",
        encryption_key_version=1,
        scope="readonly",
    )
    session.add(sts)
    await session.commit()
    await session.refresh(sts)
    assert sts.id is not None
    assert sts.scope == "readonly"
    assert sts.encryption_key_version == 1


# ---------------------------------------------------------------------------
# 16. ApiCache
# ---------------------------------------------------------------------------
async def test_api_cache_create(session):
    ac = ApiCache(
        cache_key="obb:quote:AAPL",
        data={"results": [{"last_price": 195.5}]},
        ttl_seconds=60,
        source="openbb",
    )
    session.add(ac)
    await session.commit()
    await session.refresh(ac)
    assert ac.id is not None
    assert ac.cache_key == "obb:quote:AAPL"
    assert ac.data["results"][0]["last_price"] == 195.5


# ---------------------------------------------------------------------------
# 17. ApiRateLimit
# ---------------------------------------------------------------------------
async def test_api_rate_limit_create(session):
    rl = ApiRateLimit(
        source="openbb",
        daily_limit=500,
        calls_today=42,
        last_reset=date.today(),
    )
    session.add(rl)
    await session.commit()
    await session.refresh(rl)
    assert rl.id is not None
    assert rl.daily_limit == 500
    assert rl.calls_today == 42


# ---------------------------------------------------------------------------
# 18. PendingOperation
# ---------------------------------------------------------------------------
async def test_pending_operation_create(session):
    po = PendingOperation(
        operation="correlation_snapshot",
        payload={"trigger": "position_update:AAPL"},
        status="pending",
        max_attempts=3,
    )
    session.add(po)
    await session.commit()
    await session.refresh(po)
    assert po.id is not None
    assert po.operation == "correlation_snapshot"
    assert po.status == "pending"
    assert po.attempts == 0


# ---------------------------------------------------------------------------
# 19. NotificationLog
# ---------------------------------------------------------------------------
async def test_notification_log_create(session):
    nl = NotificationLog(
        type="earnings_alert",
        message="AAPL earnings tomorrow",
        priority=4,
        ticker="AAPL",
        delivered=True,
    )
    session.add(nl)
    await session.commit()
    await session.refresh(nl)
    assert nl.id is not None
    assert nl.type == "earnings_alert"
    assert nl.delivered is True


# ---------------------------------------------------------------------------
# Relationship tests
# ---------------------------------------------------------------------------
async def test_portfolio_positions_relationship(session):
    port = Portfolio(account_name="Test", account_type="roth_ira")
    session.add(port)
    await session.commit()
    await session.refresh(port)

    pos1 = Position(
        portfolio_id=port.id, ticker="AAPL",
        shares=Decimal("10"), cost_basis=Decimal("150"), status="open",
    )
    pos2 = Position(
        portfolio_id=port.id, ticker="MSFT",
        shares=Decimal("5"), cost_basis=Decimal("300"), status="open",
    )
    session.add_all([pos1, pos2])
    await session.commit()

    # Query positions via portfolio
    result = await session.execute(
        select(Position).where(Position.portfolio_id == port.id)
    )
    positions = result.scalars().all()
    assert len(positions) == 2
    tickers = {p.ticker for p in positions}
    assert tickers == {"AAPL", "MSFT"}


async def test_portfolio_cash_relationship(session):
    port = Portfolio(account_name="Test", account_type="custodial")
    session.add(port)
    await session.commit()
    await session.refresh(port)

    cb = CashBalance(
        portfolio_id=port.id, instrument="USD",
        balance=Decimal("10000"), as_of_date=date.today(),
    )
    session.add(cb)
    await session.commit()
    await session.refresh(cb)
    assert cb.portfolio_id == port.id


async def test_pending_operation_dependency(session):
    """Test self-referencing depends_on FK."""
    op1 = PendingOperation(
        operation="score_trade",
        payload={"trade_id": 1},
        status="pending",
        max_attempts=3,
    )
    session.add(op1)
    await session.commit()
    await session.refresh(op1)

    op2 = PendingOperation(
        operation="update_weights",
        payload={"trigger": "close"},
        depends_on=op1.id,
        status="pending",
        max_attempts=3,
    )
    session.add(op2)
    await session.commit()
    await session.refresh(op2)
    assert op2.depends_on == op1.id


async def test_all_19_models_count():
    """Verify we have exactly 19 model classes inheriting from Base."""
    from src.db import Base
    # Base.metadata.tables contains all registered tables
    tables = Base.metadata.tables
    assert len(tables) == 19, f"Expected 19 tables, got {len(tables)}: {list(tables.keys())}"
