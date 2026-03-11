from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


# ---------------------------------------------------------------------------
# 1. Portfolio
# ---------------------------------------------------------------------------
class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(20))  # roth_ira | custodial | taxable
    broker: Mapped[str] = mapped_column(String(50), default="Schwab")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio")
    cash_balances: Mapped[list["CashBalance"]] = relationship(back_populates="portfolio")


# ---------------------------------------------------------------------------
# 2. Position
# ---------------------------------------------------------------------------
class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    ticker: Mapped[str] = mapped_column(String(10))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    sector: Mapped[Optional[str]] = mapped_column(String(50))
    shares: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    entry_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_1: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_2: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_3: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed | stopped_out
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")


# ---------------------------------------------------------------------------
# 3. CashBalance
# ---------------------------------------------------------------------------
class CashBalance(Base):
    __tablename__ = "cash_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    instrument: Mapped[str] = mapped_column(String(20))  # USD | SWVXX
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    as_of_date: Mapped[date] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="cash_balances")


# ---------------------------------------------------------------------------
# 4. Trade
# ---------------------------------------------------------------------------
class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    sector: Mapped[Optional[str]] = mapped_column(String(50))
    catalyst_type: Mapped[Optional[str]] = mapped_column(String(30))
    market_regime: Mapped[Optional[str]] = mapped_column(String(20))
    thesis_summary: Mapped[Optional[str]] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(20))  # executed | rejected | passed | waiting
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    shares: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    stop_loss: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_1: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_2: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    target_3: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    risk_reward_t1: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    risk_reward_t2: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    risk_reward_t3: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    conviction_pct: Mapped[Optional[int]] = mapped_column(Integer)
    post_research_pct: Mapped[Optional[int]] = mapped_column(Integer)
    actual_pnl_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    actual_pnl_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    outcome: Mapped[Optional[str]] = mapped_column(String(20))  # win | loss | breakeven
    research_doc: Mapped[Optional[str]] = mapped_column(Text)
    research_versions: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    research_date: Mapped[Optional[date]] = mapped_column(Date)
    execution_date: Mapped[Optional[date]] = mapped_column(Date)
    close_date: Mapped[Optional[date]] = mapped_column(Date)
    account_type: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# 5. TradeScore
# ---------------------------------------------------------------------------
class TradeScore(Base):
    __tablename__ = "trade_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    research_quality_score: Mapped[int] = mapped_column(Integer)
    entry_timing_score: Mapped[int] = mapped_column(Integer)
    position_sizing_score: Mapped[int] = mapped_column(Integer)
    stop_loss_score: Mapped[int] = mapped_column(Integer)
    exit_timing_score: Mapped[int] = mapped_column(Integer)
    research_quality_notes: Mapped[Optional[str]] = mapped_column(Text)
    entry_timing_notes: Mapped[Optional[str]] = mapped_column(Text)
    position_sizing_notes: Mapped[Optional[str]] = mapped_column(Text)
    stop_loss_notes: Mapped[Optional[str]] = mapped_column(Text)
    exit_timing_notes: Mapped[Optional[str]] = mapped_column(Text)
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    outcome: Mapped[Optional[str]] = mapped_column(String(20))
    process_vs_outcome: Mapped[Optional[str]] = mapped_column(String(40))
    # good_process_good_outcome | good_process_bad_outcome
    # bad_process_good_outcome  | bad_process_bad_outcome

    __table_args__ = (
        CheckConstraint("research_quality_score BETWEEN 1 AND 10"),
        CheckConstraint("entry_timing_score BETWEEN 1 AND 10"),
        CheckConstraint("position_sizing_score BETWEEN 1 AND 10"),
        CheckConstraint("stop_loss_score BETWEEN 1 AND 10"),
        CheckConstraint("exit_timing_score BETWEEN 1 AND 10"),
    )


# ---------------------------------------------------------------------------
# 6. DimensionWeight
# ---------------------------------------------------------------------------
class DimensionWeight(Base):
    __tablename__ = "dimension_weights"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    trade_count: Mapped[Optional[int]] = mapped_column(Integer)
    research_quality_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    entry_timing_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    position_sizing_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    stop_loss_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    exit_timing_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    update_reason: Mapped[Optional[str]] = mapped_column(Text)
    update_method: Mapped[Optional[str]] = mapped_column(String(20))  # initial | nudge | recalibration


# ---------------------------------------------------------------------------
# 7. Lesson
# ---------------------------------------------------------------------------
class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"))
    lesson_text: Mapped[str] = mapped_column(Text)
    lesson_type: Mapped[Optional[str]] = mapped_column(String(20))
    sector_tag: Mapped[Optional[str]] = mapped_column(String(50))
    catalyst_tag: Mapped[Optional[str]] = mapped_column(String(30))
    outcome_tag: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# 8. Principle
# ---------------------------------------------------------------------------
class Principle(Base):
    __tablename__ = "principles"

    id: Mapped[int] = mapped_column(primary_key=True)
    principle_text: Mapped[str] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(30))
    times_applied: Mapped[int] = mapped_column(Integer, default=0)
    times_violated: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# 9. CandidateScreen
# ---------------------------------------------------------------------------
class CandidateScreen(Base):
    __tablename__ = "candidate_screens"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10))
    screened_at: Mapped[Optional[date]] = mapped_column(Date)
    price_at_screen: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    analyst_consensus: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    price_vs_consensus: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    conviction_score: Mapped[Optional[int]] = mapped_column(Integer)
    catalyst_type: Mapped[Optional[str]] = mapped_column(String(30))
    catalyst_quality: Mapped[Optional[str]] = mapped_column(String(20))
    sector_fit: Mapped[Optional[bool]] = mapped_column(Boolean)
    pass_fail: Mapped[Optional[str]] = mapped_column(String(10))
    fail_reasons: Mapped[Optional[list]] = mapped_column(JSON)
    escalated_to_trade: Mapped[bool] = mapped_column(Boolean, default=False)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"))


# ---------------------------------------------------------------------------
# 10. CatalystCalendar
# ---------------------------------------------------------------------------
class CatalystCalendar(Base):
    __tablename__ = "catalyst_calendar"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date)
    event_type: Mapped[Optional[str]] = mapped_column(String(20))
    ticker: Mapped[Optional[str]] = mapped_column(String(10))
    description: Mapped[Optional[str]] = mapped_column(Text)
    impact_level: Mapped[Optional[str]] = mapped_column(String(10))
    position_ids: Mapped[Optional[list]] = mapped_column(JSON)
    source: Mapped[Optional[str]] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# 11. CorrelationSnapshot
# ---------------------------------------------------------------------------
class CorrelationSnapshot(Base):
    __tablename__ = "correlation_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    tickers: Mapped[Optional[list]] = mapped_column(JSON)
    correlation_matrix: Mapped[Optional[dict]] = mapped_column(JSON)
    tech_concentration_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    portfolio_beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    flags: Mapped[Optional[list]] = mapped_column(JSON)


# ---------------------------------------------------------------------------
# 12. OrderVerification
# ---------------------------------------------------------------------------
class OrderVerification(Base):
    __tablename__ = "order_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"))
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    order_type: Mapped[Optional[str]] = mapped_column(String(20))
    shares_ordered: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    price_ordered: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    gtc: Mapped[Optional[bool]] = mapped_column(Boolean)
    result: Mapped[Optional[str]] = mapped_column(String(10))
    discrepancies: Mapped[Optional[list]] = mapped_column(JSON)


# ---------------------------------------------------------------------------
# 13. User
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    auth0_sub: Mapped[str] = mapped_column(String(200), unique=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10), default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 14. AuditLog
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    tool_name: Mapped[str] = mapped_column(String(100))
    input_summary: Mapped[Optional[dict]] = mapped_column(JSON)
    output_summary: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        Index(
            "idx_audit_failures",
            "logged_at",
            postgresql_where=text("success = FALSE"),
        ),
    )


# ---------------------------------------------------------------------------
# 15. SchwabTokenState
# ---------------------------------------------------------------------------
class SchwabTokenState(Base):
    __tablename__ = "schwab_token_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    encryption_key_version: Mapped[int] = mapped_column(Integer, default=1)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(20), default="readonly")


# ---------------------------------------------------------------------------
# 16. ApiCache
# ---------------------------------------------------------------------------
class ApiCache(Base):
    __tablename__ = "api_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ttl_seconds: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30))


# ---------------------------------------------------------------------------
# 17. ApiRateLimit
# ---------------------------------------------------------------------------
class ApiRateLimit(Base):
    __tablename__ = "api_rate_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), unique=True)
    daily_limit: Mapped[int] = mapped_column(Integer)
    calls_today: Mapped[int] = mapped_column(Integer, default=0)
    last_reset: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# 18. PendingOperation
# ---------------------------------------------------------------------------
class PendingOperation(Base):
    __tablename__ = "pending_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    depends_on: Mapped[Optional[int]] = mapped_column(ForeignKey("pending_operations.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 19. NotificationLog
# ---------------------------------------------------------------------------
class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    type: Mapped[str] = mapped_column(String(30))
    ticker: Mapped[Optional[str]] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer)
    delivered: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text)
