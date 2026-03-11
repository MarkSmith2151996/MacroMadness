"""Module A: Portfolio tools (4 tools)."""

from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import CashBalance, CorrelationSnapshot, Portfolio, Position
from src.queue.processor import enqueue
from src.validation import PositionInput


def register_portfolio_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_get_portfolio(account_type: str = "") -> dict:
        """Get current portfolio: all positions with P&L, cash balances.
        Call this on session start. Optional filter by account_type: roth_ira or custodial."""
        async with async_session() as db:
            query = select(Position).where(Position.status == "open")
            if account_type:
                query = query.join(Portfolio).where(Portfolio.account_type == account_type)
            result = await db.execute(query)
            positions = result.scalars().all()

            # Get cash balances
            cash_query = select(CashBalance)
            if account_type:
                cash_query = cash_query.join(Portfolio).where(Portfolio.account_type == account_type)
            cash_result = await db.execute(cash_query)
            cash_balances = cash_result.scalars().all()

        # Enrich with live prices
        enriched = []
        total_value = Decimal("0")
        for p in positions:
            try:
                from src.integrations.market_data import get_quote
                quote = await get_quote(p.ticker)
                current_price = Decimal(str(quote.get("results", [{}])[0].get("last_price", 0)))
            except Exception:
                current_price = Decimal("0")

            market_value = p.shares * current_price
            cost_total = p.shares * p.cost_basis
            unrealized_pnl = market_value - cost_total
            pnl_pct = (unrealized_pnl / cost_total * 100) if cost_total else Decimal("0")
            total_value += market_value

            enriched.append({
                "ticker": p.ticker,
                "company_name": p.company_name,
                "sector": p.sector,
                "shares": float(p.shares),
                "cost_basis": float(p.cost_basis),
                "current_price": float(current_price),
                "market_value": float(market_value),
                "unrealized_pnl": float(unrealized_pnl),
                "pnl_pct": float(pnl_pct),
                "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                "target_1": float(p.target_1) if p.target_1 else None,
                "target_2": float(p.target_2) if p.target_2 else None,
                "target_3": float(p.target_3) if p.target_3 else None,
                "status": p.status,
            })

        cash_total = sum(float(c.balance) for c in cash_balances)
        total_value += Decimal(str(cash_total))

        return {
            "positions": enriched,
            "cash": [
                {
                    "instrument": c.instrument,
                    "balance": float(c.balance),
                    "as_of_date": c.as_of_date.isoformat(),
                }
                for c in cash_balances
            ],
            "total_value": float(total_value),
            "position_count": len(enriched),
        }

    @mcp.tool()
    async def invest_update_position(
        ticker: str,
        shares: float,
        cost_basis: float,
        stop_loss: float,
        account_type: str,
        sector: str,
        target_1: float = 0,
        target_2: float = 0,
        target_3: float = 0,
    ) -> dict:
        """Create or update a position. Auto-runs correlation check after."""
        # Validate inputs
        try:
            validated = PositionInput(
                ticker=ticker, shares=shares, cost_basis=cost_basis,
                stop_loss=stop_loss, account_type=account_type, sector=sector,
                target_1=target_1, target_2=target_2, target_3=target_3,
            )
            ticker = validated.ticker
        except Exception as e:
            return {"error": f"Validation failed: {e}"}

        async with async_session() as db:
            # Find portfolio
            result = await db.execute(
                select(Portfolio).where(Portfolio.account_type == account_type)
            )
            portfolio = result.scalar_one_or_none()
            if not portfolio:
                return {"error": f"No portfolio found for account_type={account_type}"}

            # Check for existing open position
            result = await db.execute(
                select(Position).where(
                    Position.portfolio_id == portfolio.id,
                    Position.ticker == ticker,
                    Position.status == "open",
                )
            )
            position = result.scalar_one_or_none()

            if position:
                position.shares = Decimal(str(shares))
                position.cost_basis = Decimal(str(cost_basis))
                position.stop_loss = Decimal(str(stop_loss))
                position.sector = sector
                if target_1:
                    position.target_1 = Decimal(str(target_1))
                if target_2:
                    position.target_2 = Decimal(str(target_2))
                if target_3:
                    position.target_3 = Decimal(str(target_3))
            else:
                position = Position(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    shares=Decimal(str(shares)),
                    cost_basis=Decimal(str(cost_basis)),
                    stop_loss=Decimal(str(stop_loss)),
                    sector=sector,
                    target_1=Decimal(str(target_1)) if target_1 else None,
                    target_2=Decimal(str(target_2)) if target_2 else None,
                    target_3=Decimal(str(target_3)) if target_3 else None,
                    status="open",
                )
                db.add(position)

            await db.commit()
            await db.refresh(position)

        # Queue correlation snapshot
        await enqueue("correlation_snapshot", {"trigger": f"position_update:{ticker}"})

        return {
            "position": {
                "id": position.id,
                "ticker": position.ticker,
                "shares": float(position.shares),
                "cost_basis": float(position.cost_basis),
                "stop_loss": float(position.stop_loss),
                "sector": position.sector,
            },
            "correlation_queued": True,
        }

    @mcp.tool()
    async def invest_close_position(
        ticker: str,
        exit_price: float,
        exit_date: str,
        outcome: str,
    ) -> dict:
        """Close a position. Queues score_trade and update_weights operations.
        outcome: win | loss | breakeven"""
        from datetime import date as date_type

        async with async_session() as db:
            result = await db.execute(
                select(Position).where(
                    Position.ticker == ticker,
                    Position.status == "open",
                )
            )
            position = result.scalar_one_or_none()
            if not position:
                return {"error": f"No open position found for {ticker}"}

            position.exit_price = Decimal(str(exit_price))
            position.exit_date = date_type.fromisoformat(exit_date)
            position.status = "closed"

            # Calculate P&L
            cost_total = position.shares * position.cost_basis
            exit_total = position.shares * position.exit_price
            pnl_usd = float(exit_total - cost_total)
            pnl_pct = float((exit_total - cost_total) / cost_total * 100) if cost_total else 0

            # Update linked trade if exists
            if position.trade_id:
                from src.models import Trade
                trade = await db.get(Trade, position.trade_id)
                if trade:
                    trade.actual_pnl_usd = Decimal(str(pnl_usd))
                    trade.actual_pnl_pct = Decimal(str(pnl_pct))
                    trade.outcome = outcome
                    trade.close_date = position.exit_date

            await db.commit()

        # Queue scoring and weight update
        score_op = await enqueue("score_trade", {
            "ticker": ticker,
            "trade_id": position.trade_id,
            "outcome": outcome,
        })
        await enqueue(
            "update_weights",
            {"trigger": f"close_position:{ticker}"},
            depends_on=score_op,
        )

        return {
            "ticker": ticker,
            "exit_price": exit_price,
            "pnl_usd": pnl_usd,
            "pnl_pct": round(pnl_pct, 2),
            "outcome": outcome,
            "scoring_queued": True,
        }

    @mcp.tool()
    async def invest_update_cash(
        portfolio_id: int,
        instrument: str,
        balance: float,
    ) -> dict:
        """Update a cash balance for a portfolio."""
        from datetime import date as date_type

        async with async_session() as db:
            result = await db.execute(
                select(CashBalance).where(
                    CashBalance.portfolio_id == portfolio_id,
                    CashBalance.instrument == instrument,
                )
            )
            cash = result.scalar_one_or_none()

            if cash:
                cash.balance = Decimal(str(balance))
                cash.as_of_date = date_type.today()
            else:
                cash = CashBalance(
                    portfolio_id=portfolio_id,
                    instrument=instrument,
                    balance=Decimal(str(balance)),
                    as_of_date=date_type.today(),
                )
                db.add(cash)

            await db.commit()
            await db.refresh(cash)

        return {
            "portfolio_id": portfolio_id,
            "instrument": instrument,
            "balance": float(cash.balance),
            "as_of_date": cash.as_of_date.isoformat(),
        }
