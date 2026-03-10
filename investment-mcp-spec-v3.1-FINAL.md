# Investment Research System — Build Specification v3.1

**For:** Claude Code (primary builder) and Antonio (reviewer)
**Stack:** Python · FastAPI · FastMCP · OpenBB ODP · SQLAlchemy · PostgreSQL · Railway
**Status:** BUILD-READY. Every section is implementable. No aspirational features.

---

## ARCHITECTURE OVERVIEW

Single Python process serving two surfaces from one FastAPI application:

1. **Claude** connects via MCP (Streamable HTTP) at `/mcp` — for research, trade planning, analysis
2. **OpenBB Workspace** connects via REST API at `/` — for dashboard widgets, charts, mobile

```
Claude (claude.ai + mobile)                OpenBB Workspace (PWA, mobile)
        │ MCP Streamable HTTP                      │ REST GET endpoints
        ▼                                          ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Application (Railway)               │
│                                                         │
│   app.mount("/mcp", mcp.streamable_http_app())         │
│   app.get("/widgets.json")                              │
│   app.get("/portfolio")                                 │
│   app.get("/calendar")                                  │
│   ... etc                                               │
│                                                         │
│   ┌─────────────┐  ┌──────────┐  ┌──────────────────┐  │
│   │  20 MCP     │  │  OpenBB  │  │  Schwab Client   │  │
│   │  Tools      │  │  ODP     │  │  (read-only)     │  │
│   │  (FastMCP)  │  │  (import)│  │                  │  │
│   └──────┬──────┘  └────┬─────┘  └────────┬─────────┘  │
│          └──────────────┼─────────────────┘             │
│                         ▼                               │
│              SQLAlchemy + PostgreSQL                     │
│                                                         │
│   Ntfy.sh ← push notifications                         │
│   APScheduler ← cron jobs (sync, backups, alerts)       │
└─────────────────────────────────────────────────────────┘
```

### Why This Architecture

- **One language (Python):** OpenBB ODP is Python. FastMCP is Python. No sidecar, no IPC, no two-language builds.
- **One process:** FastMCP mounts directly onto FastAPI. MCP tools and REST endpoints share the same DB connection pool, cache, and auth.
- **OpenBB Workspace is the dashboard:** Free, mobile-ready (PWA), widget-based. No frontend code to write.
- **Ntfy.sh is push notifications:** Free, works on iOS/Android, 20 lines of code.

---

## STACK & DEPENDENCIES

```
# requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
mcp[cli]>=1.9.0                # FastMCP included in official MCP SDK
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.30.0                # Async PostgreSQL driver
alembic>=1.14.0                # Database migrations
pydantic>=2.10.0
httpx>=0.28.0                  # Async HTTP client (Schwab, Ntfy)
openbb>=4.5.0                  # OpenBB ODP — market data
apscheduler>=3.11.0            # Scheduled jobs (sync, alerts, backup)
cryptography>=44.0.0           # AES encryption for Schwab token
python-jose>=3.3.0             # JWT validation for Auth0
```

### Runtime
- **Python:** 3.11+
- **Database:** PostgreSQL 16 (Railway managed)
- **Deployment:** Railway (Dockerfile or Nixpack)
- **Auth (Claude↔Server):** Auth0 OAuth 2.1 with Dynamic Client Registration
- **Auth (OpenBB↔Server):** Bearer token in header

---

## ENTRY POINT PATTERN

This is the core architectural pattern. Claude Code should build everything around this structure.

```python
# src/main.py
import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from src.db import engine, create_tables
from src.scheduler import start_scheduler
from src.tools import register_all_tools
from src.widgets import register_all_widgets

# --- MCP Server (Claude) ---
mcp = FastMCP(
    "InvestMCP",
    stateless_http=True,  # Required for Railway (no sticky sessions)
)

# --- FastAPI App (OpenBB Workspace + health + auth) ---
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    start_scheduler()
    # Mount MCP inside lifespan so session manager is active
    app.mount("/mcp", mcp.streamable_http_app())
    yield
    await engine.dispose()

app = FastAPI(
    title="Investment Research System",
    version="3.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pro.openbb.co"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register MCP tools (Claude surface)
register_all_tools(mcp)

# Register REST endpoints (OpenBB Workspace surface)
register_all_widgets(app)

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Key:** `mcp.streamable_http_app()` is mounted onto FastAPI at `/mcp`. Claude connects to `https://your-server.railway.app/mcp`. OpenBB connects to `https://your-server.railway.app`.

---

## DATABASE

### ORM: SQLAlchemy 2.0 (async)

NOT Prisma (that's Node.js). NOT raw SQL. SQLAlchemy with asyncpg for async PostgreSQL.

```python
# src/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=5)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
```

### Migrations: Alembic

```bash
alembic init alembic
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

Every schema change goes through Alembic. Never auto-create in production — use `create_tables()` only for initial setup.

### Schema — 19 Tables

All tables defined as SQLAlchemy models in `src/models.py`. Below is the complete schema. Every column, every constraint, every relationship.

```python
# src/models.py
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    String, Integer, BigInteger, Numeric, Boolean, Date, DateTime,
    Text, ForeignKey, Index, CheckConstraint, JSON, ARRAY,
    func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.db import Base


class Portfolio(Base):
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(20))  # roth_ira | custodial | taxable
    broker: Mapped[str] = mapped_column(String(50), default="Schwab")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio")
    cash_balances: Mapped[list["CashBalance"]] = relationship(back_populates="portfolio")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")


class CashBalance(Base):
    __tablename__ = "cash_balances"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    instrument: Mapped[str] = mapped_column(String(20))  # USD | SWVXX
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    as_of_date: Mapped[date] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    portfolio: Mapped["Portfolio"] = relationship(back_populates="cash_balances")


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TradeScore(Base):
    __tablename__ = "trade_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
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


class DimensionWeight(Base):
    __tablename__ = "dimension_weights"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trade_count: Mapped[Optional[int]] = mapped_column(Integer)
    research_quality_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    entry_timing_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    position_sizing_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    stop_loss_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    exit_timing_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    update_reason: Mapped[Optional[str]] = mapped_column(Text)
    update_method: Mapped[Optional[str]] = mapped_column(String(20))  # initial | nudge | recalibration


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"))
    lesson_text: Mapped[str] = mapped_column(Text)
    lesson_type: Mapped[Optional[str]] = mapped_column(String(20))
    sector_tag: Mapped[Optional[str]] = mapped_column(String(50))
    catalyst_tag: Mapped[Optional[str]] = mapped_column(String(30))
    outcome_tag: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Principle(Base):
    __tablename__ = "principles"
    id: Mapped[int] = mapped_column(primary_key=True)
    principle_text: Mapped[str] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(30))
    times_applied: Mapped[int] = mapped_column(Integer, default=0)
    times_violated: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CorrelationSnapshot(Base):
    __tablename__ = "correlation_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tickers: Mapped[Optional[list]] = mapped_column(JSON)
    correlation_matrix: Mapped[Optional[dict]] = mapped_column(JSON)
    tech_concentration_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    portfolio_beta: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    flags: Mapped[Optional[list]] = mapped_column(JSON)


class OrderVerification(Base):
    __tablename__ = "order_verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trades.id"))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    order_type: Mapped[Optional[str]] = mapped_column(String(20))
    shares_ordered: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    price_ordered: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    gtc: Mapped[Optional[bool]] = mapped_column(Boolean)
    result: Mapped[Optional[str]] = mapped_column(String(10))
    discrepancies: Mapped[Optional[list]] = mapped_column(JSON)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    auth0_sub: Mapped[str] = mapped_column(String(200), unique=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10), default="owner")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    tool_name: Mapped[str] = mapped_column(String(100))
    input_summary: Mapped[Optional[dict]] = mapped_column(JSON)
    output_summary: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    __table_args__ = (
        Index("idx_audit_failures", "logged_at", postgresql_where=("success = FALSE")),
    )


class SchwabTokenState(Base):
    __tablename__ = "schwab_token_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    encryption_key_version: Mapped[int] = mapped_column(Integer, default=1)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(20), default="readonly")


class ApiCache(Base):
    __tablename__ = "api_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ttl_seconds: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30))


class ApiRateLimit(Base):
    __tablename__ = "api_rate_limits"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30), unique=True)
    daily_limit: Mapped[int] = mapped_column(Integer)
    calls_today: Mapped[int] = mapped_column(Integer, default=0)
    last_reset: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class NotificationLog(Base):
    __tablename__ = "notification_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    type: Mapped[str] = mapped_column(String(30))
    ticker: Mapped[Optional[str]] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer)
    delivered: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text)
```

---

## MCP TOOLS — 20 TOOLS

### Tool Registration Pattern

Every tool follows this pattern. Claude Code should replicate this for all 20.

```python
# src/tools/portfolio.py
from mcp.server.fastmcp import FastMCP
from src.db import async_session
from src.models import Position, CashBalance, Portfolio
from sqlalchemy import select

def register_portfolio_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_get_portfolio(account_type: str = "") -> dict:
        """Get current portfolio: all positions with live prices, P&L, cash balances.
        Call this on session start. Optional filter by account_type: roth_ira or custodial."""
        async with async_session() as db:
            query = select(Position).where(Position.status == "open")
            if account_type:
                query = query.join(Portfolio).where(Portfolio.account_type == account_type)
            result = await db.execute(query)
            positions = result.scalars().all()
            # Enrich with live prices from OpenBB or Schwab...
            return {"positions": [...], "cash": [...], "total_value": ...}

    @mcp.tool()
    async def invest_update_position(
        ticker: str, shares: float, cost_basis: float,
        stop_loss: float, account_type: str, sector: str,
        target_1: float = 0, target_2: float = 0, target_3: float = 0
    ) -> dict:
        """Create or update a position. Auto-runs correlation check after."""
        # ... implementation
        return {"position": ..., "correlation_flags": ...}

    # ... invest_close_position, invest_update_cash
```

```python
# src/tools/__init__.py
from src.tools.portfolio import register_portfolio_tools
from src.tools.trades import register_trade_tools
# ... all modules

def register_all_tools(mcp):
    register_portfolio_tools(mcp)
    register_trade_tools(mcp)
    register_screening_tools(mcp)
    register_learning_tools(mcp)
    register_principles_tools(mcp)
    register_market_data_tools(mcp)
    register_calendar_tools(mcp)
    register_correlation_tools(mcp)
    register_order_verify_tools(mcp)
    register_schwab_tools(mcp)
    register_admin_tools(mcp)
```

### Complete Tool Registry

**Module A: Portfolio (4 tools)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_get_portfolio` | `account_type?` | Enriches with live prices | Positions + cash + total value |
| `invest_update_position` | ticker, shares, cost_basis, stop_loss, account_type, sector, targets | Queues correlation snapshot | Updated position + flags |
| `invest_close_position` | ticker, exit_price, exit_date, outcome | Queues score_trade → update_weights | Final P&L |
| `invest_update_cash` | portfolio_id, instrument, balance | — | Updated balances |

**Module B: Trades (4 tools)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_create_trade_plan` | Full trade plan object | check_principles + screen_candidate + correlation impact | Trade ID + violations + flags |
| `invest_get_trade` | trade_id OR ticker | — | Full trade with research doc and scores |
| `invest_list_trades` | status?, sector?, catalyst_type?, outcome?, limit? | — | Paginated list |
| `invest_update_trade_plan` | trade_id + fields | Versions old research_doc | Updated record |

**Module C: Screening (2 tools)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_screen_candidate` | ticker, price, catalyst_type, conviction_pct | Fetches consensus+beta from OpenBB | Pass/fail per criterion |
| `invest_list_rejected_candidates` | fail_reason?, sector?, date_range? | — | Paginated list |

**Module D: Learning (2 tools)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_weights` | action: get\|update\|history | Recalibration if action=update | Weights + version |
| `invest_lessons` | action: search\|add, filters | Relevance scoring on search | Ranked lessons or confirmation |

**Module E: Principles (1 tool)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_principles` | action: check\|list\|add\|log_event | — | Per action |

**Module F: Market Data (2 tools)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_market_data` | type: quote\|fundamentals\|earnings_history\|gold\|macro, symbol?, quarters?, series? | Cache layer | Structured data |
| `invest_get_filing` | ticker, filing_type, filing_date? | — | Filing text |

**Module G: Calendar (1 tool)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_calendar` | action: list\|add\|earnings | — | Per action |

**Module H: Correlation (1 tool)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_correlation` | action: impact\|snapshot | Uses OpenBB historical prices | Matrix + beta + flags |

**Module I: Order Verify (1 tool)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_verify_order` | ticker, order_type, shares, prices, account_type | — | Pass/fail per check |

**Module J: Schwab (1 tool)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_schwab` | action: sync\|orders\|detect_changes\|token_status | detect_changes may trigger close_position + ntfy | Per action |

**Module K: Admin (1 tool)**

| Tool | Inputs | Auto-triggers | Returns |
|---|---|---|---|
| `invest_admin` | action: audit_log\|users\|add_user\|revoke_user\|backup_status\|system_health | — | Per action |

---

## OPENBB WORKSPACE — REST ENDPOINTS

OpenBB Workspace connects as a backend. It expects:
1. A `GET /widgets.json` endpoint returning widget definitions
2. `GET` endpoints for each widget returning data

### Widget Endpoint Pattern

```python
# src/widgets/portfolio_widget.py
from fastapi import APIRouter
from src.db import async_session
from src.models import Position, Portfolio
from sqlalchemy import select

router = APIRouter()

@router.get("/portfolio")
async def portfolio_widget(account_type: str = ""):
    """Portfolio overview — all positions with P&L."""
    async with async_session() as db:
        query = select(Position).where(Position.status == "open")
        if account_type:
            query = query.join(Portfolio).where(Portfolio.account_type == account_type)
        result = await db.execute(query)
        positions = result.scalars().all()

    return [
        {
            "ticker": p.ticker,
            "shares": float(p.shares),
            "cost_basis": float(p.cost_basis),
            "current_price": 0,  # enriched by OpenBB
            "unrealized_pnl": 0,
            "stop_loss": float(p.stop_loss) if p.stop_loss else None,
            "sector": p.sector,
            "account": p.portfolio.account_type if p.portfolio else None,
        }
        for p in positions
    ]
```

### widgets.json

Served at `GET /widgets.json`. Defines what OpenBB Workspace renders.

```python
# src/widgets/__init__.py
from fastapi import APIRouter, FastAPI

WIDGETS = {
    "portfolio_overview": {
        "name": "Portfolio Overview",
        "description": "All open positions with live P&L, stop distances, and targets",
        "endpoint": "portfolio",
        "data": {
            "table": {
                "enableCharts": True,
                "showAll": True,
                "columnsDefs": [
                    {"field": "ticker", "headerName": "Ticker", "cellDataType": "text", "pinned": "left", "width": 80},
                    {"field": "shares", "headerName": "Shares", "cellDataType": "number"},
                    {"field": "cost_basis", "headerName": "Basis", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "current_price", "headerName": "Price", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "unrealized_pnl", "headerName": "P&L", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "stop_loss", "headerName": "Stop", "cellDataType": "number", "formatterFn": "currency"},
                    {"field": "sector", "headerName": "Sector", "cellDataType": "text"},
                    {"field": "account", "headerName": "Account", "cellDataType": "text"},
                ]
            }
        },
        "params": [
            {"paramName": "account_type", "value": "", "label": "Account", "show": True, "type": "text"}
        ],
    },
    "catalyst_calendar": {
        "name": "Catalyst Calendar",
        "description": "Upcoming catalysts for all positions and macro events",
        "endpoint": "calendar",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "event_date", "headerName": "Date", "cellDataType": "text", "width": 100},
                    {"field": "event_type", "headerName": "Type", "cellDataType": "text", "width": 80},
                    {"field": "description", "headerName": "Event", "cellDataType": "text"},
                    {"field": "ticker", "headerName": "Ticker", "cellDataType": "text", "width": 80},
                    {"field": "impact_level", "headerName": "Impact", "cellDataType": "text", "width": 80},
                ]
            }
        },
    },
    "alert_feed": {
        "name": "Alerts",
        "description": "Recent notifications and warnings",
        "endpoint": "alerts",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "sent_at", "headerName": "Time", "cellDataType": "text", "width": 120},
                    {"field": "type", "headerName": "Type", "cellDataType": "text", "width": 100},
                    {"field": "message", "headerName": "Message", "cellDataType": "text"},
                    {"field": "priority", "headerName": "Priority", "cellDataType": "number", "width": 80},
                ]
            }
        },
    },
    "trade_scores": {
        "name": "Trade Scores",
        "description": "Closed trades with 5-dimension scoring and process vs outcome",
        "endpoint": "scores",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "ticker", "headerName": "Ticker", "cellDataType": "text", "width": 80},
                    {"field": "outcome", "headerName": "Outcome", "cellDataType": "text", "width": 80},
                    {"field": "composite_score", "headerName": "Score", "cellDataType": "number", "width": 80},
                    {"field": "research", "headerName": "Research", "cellDataType": "number", "width": 80},
                    {"field": "entry", "headerName": "Entry", "cellDataType": "number", "width": 80},
                    {"field": "sizing", "headerName": "Sizing", "cellDataType": "number", "width": 80},
                    {"field": "stop", "headerName": "Stop", "cellDataType": "number", "width": 80},
                    {"field": "exit", "headerName": "Exit", "cellDataType": "number", "width": 80},
                    {"field": "process_vs_outcome", "headerName": "Process", "cellDataType": "text"},
                ]
            }
        },
    },
    "system_health": {
        "name": "System Health",
        "description": "Schwab token, API budgets, backups, pending operations",
        "endpoint": "system-health",
        "data": {
            "table": {
                "showAll": True,
                "columnsDefs": [
                    {"field": "component", "headerName": "Component", "cellDataType": "text"},
                    {"field": "status", "headerName": "Status", "cellDataType": "text"},
                    {"field": "detail", "headerName": "Detail", "cellDataType": "text"},
                ]
            }
        },
    },
}

def register_all_widgets(app: FastAPI):
    from src.widgets.portfolio_widget import router as portfolio_router
    from src.widgets.calendar_widget import router as calendar_router
    from src.widgets.alerts_widget import router as alerts_router
    from src.widgets.scores_widget import router as scores_router
    from src.widgets.health_widget import router as health_router

    app.include_router(portfolio_router)
    app.include_router(calendar_router)
    app.include_router(alerts_router)
    app.include_router(scores_router)
    app.include_router(health_router)

    @app.get("/widgets.json")
    async def get_widgets():
        return WIDGETS
```

---

## OPENBB ODP — MARKET DATA

Import directly. No sidecar. No HTTP calls to localhost.

```python
# src/integrations/market_data.py
from openbb import obb
from src.cache import cached_fetch

# Configure providers on startup
# Credentials loaded from env vars via OpenBB's config system

async def get_quote(symbol: str) -> dict:
    return await cached_fetch(
        cache_key=f"obb:quote:{symbol}",
        ttl_seconds=60,
        source="openbb",
        fetch_fn=lambda: obb.equity.price.quote(symbol, provider="fmp").to_dict(),
    )

async def get_fundamentals(ticker: str) -> dict:
    return await cached_fetch(
        cache_key=f"obb:fundamentals:{ticker}",
        ttl_seconds=86400,  # 24 hours
        source="openbb",
        fetch_fn=lambda: obb.equity.fundamental.metrics(ticker, provider="fmp").to_dict(),
    )

async def get_analyst_consensus(ticker: str) -> dict:
    return await cached_fetch(
        cache_key=f"obb:consensus:{ticker}",
        ttl_seconds=43200,  # 12 hours
        source="openbb",
        fetch_fn=lambda: obb.equity.estimates.consensus(ticker, provider="fmp").to_dict(),
    )

async def get_earnings_history(ticker: str, quarters: int = 8) -> dict:
    return await cached_fetch(
        cache_key=f"obb:earnings:{ticker}:{quarters}",
        ttl_seconds=604800,  # 7 days
        source="openbb",
        fetch_fn=lambda: obb.equity.estimates.historical(ticker, provider="fmp").to_dict(),
    )

async def get_macro(series: str = "CPIAUCSL") -> dict:
    return await cached_fetch(
        cache_key=f"obb:macro:{series}",
        ttl_seconds=21600,  # 6 hours
        source="openbb",
        fetch_fn=lambda: obb.economy.fred_series(series).to_dict(),
    )

async def get_gold_price() -> dict:
    return await cached_fetch(
        cache_key="obb:gold",
        ttl_seconds=60,
        source="openbb",
        fetch_fn=lambda: obb.commodity.price.spot("gold").to_dict(),
    )
```

**Note on sync vs async:** OpenBB ODP calls are synchronous. Wrap them in `asyncio.to_thread()` inside `cached_fetch` to avoid blocking the event loop:

```python
import asyncio

async def cached_fetch(cache_key, ttl_seconds, source, fetch_fn):
    # Check cache first (async DB call)
    cached = await get_from_cache(cache_key)
    if cached and not expired(cached, ttl_seconds):
        return cached.data

    # ODP calls are sync — run in thread pool
    try:
        data = await asyncio.to_thread(fetch_fn)
        await set_cache(cache_key, data, ttl_seconds, source)
        return data
    except Exception:
        if cached:  # Return stale on failure
            return cached.data
        raise
```

---

## SCHWAB CLIENT

Custom async client. Read-only. No order functions exist.

```python
# src/integrations/schwab.py
import httpx
from cryptography.fernet import Fernet
from src.db import async_session
from src.models import SchwabTokenState

class SchwabClient:
    BASE_URL = "https://api.schwabapi.com/trader/v1"

    def __init__(self):
        self.app_key = os.environ["SCHWAB_APP_KEY"]
        self.app_secret = os.environ["SCHWAB_APP_SECRET"]
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def get_accounts(self) -> dict:
        return await self._get("/accounts")

    async def get_positions(self, account_id: str) -> dict:
        return await self._get(f"/accounts/{account_id}/positions")

    async def get_orders(self, account_id: str) -> dict:
        return await self._get(f"/accounts/{account_id}/orders")

    async def _get(self, path: str) -> dict:
        token = await self._ensure_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    # No order placement methods. They do not exist in this file.
    # SCHWAB_TRADING_ENABLED must be true AND order methods must be
    # explicitly added before any trading is possible.
```

### Self-Service Refresh

```python
# src/auth/schwab_oauth.py — mounted on the FastAPI app
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse

router = APIRouter(prefix="/auth/schwab")

@router.get("/login")
async def schwab_login():
    # Redirect to Schwab OAuth consent screen
    auth_url = (
        f"https://api.schwabapi.com/v1/oauth/authorize"
        f"?client_id={os.environ['SCHWAB_APP_KEY']}"
        f"&redirect_uri={os.environ['SERVER_URL']}/auth/schwab/callback"
        f"&response_type=code&scope=readonly"
    )
    return RedirectResponse(auth_url)

@router.get("/callback")
async def schwab_callback(code: str):
    # Exchange code for tokens, encrypt refresh token, store in DB
    # ... implementation
    return HTMLResponse("Schwab re-authentication successful. You can close this tab.")
```

---

## NOTIFICATIONS

```python
# src/integrations/ntfy.py
import httpx
from src.db import async_session
from src.models import NotificationLog

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

async def send_notification(type: str, message: str, priority: int, ticker: str = None):
    if not NTFY_TOPIC:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://ntfy.sh/{NTFY_TOPIC}",
                content=message,
                headers={
                    "Title": f"INVEST: {type.upper()}",
                    "Priority": str(priority),
                    "Tags": f"chart,{ticker}" if ticker else "warning",
                },
            )
        await _log(type, message, priority, ticker, True)
    except Exception as e:
        await _log(type, message, priority, ticker, False, str(e))
```

---

## CACHE LAYER

```python
# src/cache.py
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, text
from src.db import async_session
from src.models import ApiCache

async def cached_fetch(cache_key: str, ttl_seconds: int, source: str, fetch_fn):
    async with async_session() as db:
        result = await db.execute(select(ApiCache).where(ApiCache.cache_key == cache_key))
        cached = result.scalar_one_or_none()

        if cached:
            age = (datetime.now(timezone.utc) - cached.fetched_at).total_seconds()
            if age < ttl_seconds:
                return cached.data

    # Cache miss or expired
    try:
        data = await asyncio.to_thread(fetch_fn)
        async with async_session() as db:
            existing = await db.execute(select(ApiCache).where(ApiCache.cache_key == cache_key))
            row = existing.scalar_one_or_none()
            if row:
                row.data = data
                row.fetched_at = datetime.now(timezone.utc)
                row.ttl_seconds = ttl_seconds
            else:
                db.add(ApiCache(cache_key=cache_key, data=data, ttl_seconds=ttl_seconds, source=source))
            await db.commit()
        return data
    except Exception:
        if cached:
            return cached.data  # Stale fallback
        raise

# TTL constants
TTL_QUOTE = 60           # 1 minute
TTL_TECHNICALS = 900     # 15 minutes
TTL_FUNDAMENTALS = 86400 # 24 hours
TTL_CONSENSUS = 43200    # 12 hours
TTL_EARNINGS = 604800    # 7 days
TTL_MACRO = 21600        # 6 hours
TTL_FILING = 2592000     # 30 days
TTL_GOLD = 60            # 1 minute
```

---

## QUEUE PROCESSOR

```python
# src/queue/processor.py
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from src.db import async_session
from src.models import PendingOperation

async def process_queue():
    async with async_session() as db:
        result = await db.execute(
            select(PendingOperation).where(
                and_(
                    PendingOperation.status.in_(["pending", "retrying"]),
                    PendingOperation.attempts < PendingOperation.max_attempts,
                )
            ).order_by(PendingOperation.created_at)
        )
        pending = result.scalars().all()

        for op in pending:
            if op.depends_on:
                dep = await db.get(PendingOperation, op.depends_on)
                if dep and dep.status != "completed":
                    continue

            try:
                await execute_operation(op)
                op.status = "completed"
                op.completed_at = datetime.now(timezone.utc)
            except Exception as e:
                op.attempts += 1
                op.last_error = str(e)
                backoff = timedelta(seconds=30 * (2 ** op.attempts))
                op.next_retry_at = datetime.now(timezone.utc) + backoff
                op.status = "failed" if op.attempts >= op.max_attempts else "retrying"

            await db.commit()
```

---

## SCHEDULED JOBS

```python
# src/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

def start_scheduler():
    scheduler = AsyncIOScheduler()

    # Schwab sync — every 30 minutes during market hours
    scheduler.add_job(schwab_periodic_sync, "cron", hour="9-16", minute="*/30", timezone="US/Eastern")

    # Queue processor — every 5 minutes
    scheduler.add_job(process_queue, "interval", minutes=5)

    # Token expiry check — every 6 hours
    scheduler.add_job(check_schwab_token_expiry, "interval", hours=6)

    # Earnings proximity alert — daily at 8 AM ET
    scheduler.add_job(check_earnings_proximity, "cron", hour=8, timezone="US/Eastern")

    # Cache cleanup — daily at 3 AM ET
    scheduler.add_job(cleanup_expired_cache, "cron", hour=3, timezone="US/Eastern")

    scheduler.start()
```

---

## SECURITY

### Credentials in Railway env vars only:
`DATABASE_URL`, `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`, `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`, `SCHWAB_TOKEN_ENCRYPTION_KEY`, `OPENBB_BACKEND_TOKEN`, `FMP_API_KEY`, `FRED_API_KEY`, `NTFY_TOPIC`, `SERVER_URL`, `SCHWAB_TRADING_ENABLED=false`

### RBAC:
```
owner → all tools
viewer → invest_get_portfolio, invest_get_trade, invest_list_trades,
         invest_lessons(search), invest_principles(list),
         invest_market_data, invest_calendar(list),
         invest_correlation(snapshot), invest_weights(get)
```

### Input Validation (Pydantic):
```python
from pydantic import BaseModel, Field, field_validator
import re

class TickerInput(BaseModel):
    ticker: str = Field(max_length=10)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v):
        if not re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", v):
            raise ValueError("Invalid ticker format")
        return v

class TradeInput(BaseModel):
    ticker: str
    shares: float = Field(gt=0, le=100000)
    entry_price: float = Field(gt=0, le=1000000)
    stop_loss: float = Field(gt=0, le=1000000)
    conviction_pct: int = Field(ge=0, le=100)
```

### Audit: Every tool call logged synchronously. If logging fails, tool call fails.

---

## LEARNING SYSTEM

### Weight Algorithm (Hybrid)
- **Trades 1–4:** All weights 0.20. No updates.
- **Trades 5–9:** Per-trade nudge ±0.005/±0.003.
- **Trade 10+:** Recalibration every 5 trades via point-biserial correlation. Floor 0.10, ceiling 0.35.

### Lesson Relevance
```
relevance = (sector_match × 0.35) + (catalyst_match × 0.30) + (recency × 0.20) + (severity × 0.15)
recency = e^(-0.693 × days_since / 90)
severity = 1.0 if loss else 0.6
```

### Trade Scoring Rubric
Applied by Claude when `invest_close_position` triggers scoring. Five dimensions, 1–10 each:
- **Research Quality:** Thesis accuracy, primary sources, risk identification
- **Entry Timing:** Price vs plan, technical confirmation
- **Position Sizing:** Size matched conviction level
- **Stop-Loss Discipline:** Set before entry, never widened, honored
- **Exit Timing:** Sold at targets, trailed stop properly

### Process vs Outcome
- composite ≥ 7.0 = good process. Flag "bad_process_good_outcome" prominently.

---

## SEED DATA

Pre-populate on first deployment:

**Portfolios:** Roth IRA, Custodial (both Schwab)

**Positions (Roth IRA):** RBRK 74sh @ $47 stop $44 cybersecurity, DKNG 140sh @ $22.58 stop $19 gaming

**Positions (Custodial):** MRVL 15sh semiconductors, TSM 6sh semiconductors, SWVXX $5,014

**Cash:** Roth ~$3,522, Bank ~$5,000

**Rejected:** ROST (above consensus), LLY (too small), SOFI (<55% conviction), LMT (bad R/R)

**Lessons:** LNG — "Size down on strong thesis / uncertain magnitude"

**Principles:** 6 established rules (conviction threshold, price vs consensus, sizing = conviction, diversification, post-earnings dips, stop discipline)

**Calendar:** FOMC Mar 17-18, RBRK earnings ~Mar 12, DKNG earnings Apr 30, Barrick Q1 May 6, FIFA Jun 11-Jul 19

**Weights:** Version 1, all 0.20

---

## CLAUDE BEHAVIORAL INSTRUCTIONS

Embed in MCP tool descriptions and maintain as `docs/CLAUDE_INSTRUCTIONS.md`:

**On session start:** sync Schwab, check token, show upcoming 7-day calendar.
**New ticker mentioned:** screen candidate, get quote, get fundamentals.
**Trade plan finalized:** create plan, check principles, check correlation.
**Order details described:** verify order immediately.
**Position closed:** close position, present scores, flag bad-process-good-outcome.
**Never:** add before binary catalyst, widen stop, skip screening, present trade without stop+targets.

---

## FILE STRUCTURE

```
investment-mcp-server/
├── src/
│   ├── main.py                 # FastAPI + FastMCP entry point
│   ├── db.py                   # SQLAlchemy async engine + session
│   ├── models.py               # All 19 SQLAlchemy models
│   ├── tools/
│   │   ├── __init__.py         # register_all_tools()
│   │   ├── portfolio.py        # Module A (4 tools)
│   │   ├── trades.py           # Module B (4 tools)
│   │   ├── screening.py        # Module C (2 tools)
│   │   ├── learning.py         # Module D (2 tools) + internal scoring
│   │   ├── principles.py       # Module E (1 tool)
│   │   ├── market_data.py      # Module F (2 tools)
│   │   ├── calendar.py         # Module G (1 tool)
│   │   ├── correlation.py      # Module H (1 tool)
│   │   ├── order_verify.py     # Module I (1 tool)
│   │   ├── schwab.py           # Module J (1 tool)
│   │   └── admin.py            # Module K (1 tool)
│   ├── widgets/
│   │   ├── __init__.py         # WIDGETS dict + register_all_widgets()
│   │   ├── portfolio_widget.py
│   │   ├── calendar_widget.py
│   │   ├── alerts_widget.py
│   │   ├── scores_widget.py
│   │   └── health_widget.py
│   ├── integrations/
│   │   ├── market_data.py      # OpenBB ODP wrapper with cache
│   │   ├── schwab.py           # Schwab API client (read-only)
│   │   └── ntfy.py             # Push notifications
│   ├── auth/
│   │   ├── middleware.py       # RBAC + Auth0 JWT validation
│   │   ├── audit.py            # Audit log writer
│   │   └── schwab_oauth.py     # Self-service Schwab re-auth
│   ├── queue/
│   │   └── processor.py        # Pending operations with retry
│   ├── cache.py                # cached_fetch + TTL constants
│   └── scheduler.py            # APScheduler cron jobs
├── alembic/
│   ├── alembic.ini
│   └── versions/
├── scripts/
│   ├── seed.py                 # Initial data seeder
│   └── backup.sh               # Daily pg_dump
├── docs/
│   └── CLAUDE_INSTRUCTIONS.md
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
└── railway.toml
```

---

## BUILD ORDER

1. `db.py` + `models.py` — all 19 tables
2. `seed.py` — populate initial data
3. `cache.py` — cached_fetch with TTL tiers
4. `queue/processor.py` — pending operations
5. `auth/middleware.py` + `auth/audit.py` — RBAC + logging
6. `integrations/market_data.py` — OpenBB ODP with cache
7. `tools/market_data.py` — invest_market_data + invest_get_filing
8. `tools/portfolio.py` — 4 portfolio tools
9. `tools/correlation.py`
10. `integrations/schwab.py` + `auth/schwab_oauth.py`
11. `tools/schwab.py`
12. `tools/trades.py` + `tools/screening.py`
13. `tools/principles.py`
14. `tools/learning.py` (scoring + weights + lessons)
15. `tools/calendar.py` + `tools/order_verify.py`
16. `tools/admin.py`
17. `integrations/ntfy.py` + `scheduler.py`
18. `widgets/` — all 5 widget endpoints + widgets.json
19. `main.py` — wire everything together
20. Deploy to Railway, register at claude.ai/settings/connectors, connect OpenBB Workspace

---

## COST

| Service | Cost |
|---|---|
| Railway | ~$7-8/mo |
| Everything else | $0 |
| **Total** | **~$7-8/mo** |

---

*Single source of truth. Python everywhere. Build in order. Don't skip steps.*
