"""Module B: Trade tools (4 tools)."""

from datetime import date as date_type
from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import Trade
from src.validation import TradeInput


def register_trade_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_create_trade_plan(
        ticker: str,
        entry_price: float,
        shares: float,
        stop_loss: float,
        target_1: float,
        sector: str,
        thesis_summary: str,
        catalyst_type: str = "",
        conviction_pct: int = 0,
        market_regime: str = "",
        target_2: float = 0,
        target_3: float = 0,
        account_type: str = "",
        research_doc: str = "",
    ) -> dict:
        """Create a full trade plan. Auto-triggers principle check, candidate screening,
        and correlation impact analysis. Returns trade ID + any violations/flags."""
        # Validate inputs
        try:
            validated = TradeInput(
                ticker=ticker, shares=shares, entry_price=entry_price,
                stop_loss=stop_loss, target_1=target_1, sector=sector,
                thesis_summary=thesis_summary, catalyst_type=catalyst_type,
                conviction_pct=conviction_pct, market_regime=market_regime,
                target_2=target_2, target_3=target_3, account_type=account_type,
                research_doc=research_doc,
            )
            ticker = validated.ticker
        except Exception as e:
            return {"error": f"Validation failed: {e}"}

        # Calculate risk/reward ratios
        risk = entry_price - stop_loss
        rr_t1 = round((target_1 - entry_price) / risk, 2) if risk > 0 else 0
        rr_t2 = round((target_2 - entry_price) / risk, 2) if risk > 0 and target_2 else 0
        rr_t3 = round((target_3 - entry_price) / risk, 2) if risk > 0 and target_3 else 0

        async with async_session() as db:
            trade = Trade(
                ticker=ticker,
                sector=sector,
                catalyst_type=catalyst_type or None,
                market_regime=market_regime or None,
                thesis_summary=thesis_summary,
                decision="waiting",
                entry_price=Decimal(str(entry_price)),
                shares=Decimal(str(shares)),
                stop_loss=Decimal(str(stop_loss)),
                target_1=Decimal(str(target_1)),
                target_2=Decimal(str(target_2)) if target_2 else None,
                target_3=Decimal(str(target_3)) if target_3 else None,
                risk_reward_t1=Decimal(str(rr_t1)),
                risk_reward_t2=Decimal(str(rr_t2)) if rr_t2 else None,
                risk_reward_t3=Decimal(str(rr_t3)) if rr_t3 else None,
                conviction_pct=conviction_pct or None,
                research_doc=research_doc or None,
                research_date=date_type.today() if research_doc else None,
                account_type=account_type or None,
            )
            db.add(trade)
            await db.commit()
            await db.refresh(trade)

        # Auto-trigger checks
        violations = []
        flags = []

        # Check principles
        try:
            from src.tools.principles import _check_principles
            principle_result = await _check_principles(ticker, entry_price, stop_loss, conviction_pct, sector)
            violations = principle_result.get("violations", [])
        except Exception:
            flags.append("principle_check_failed")

        # Screen candidate
        try:
            from src.tools.screening import _run_screen
            screen_result = await _run_screen(ticker, entry_price, catalyst_type, conviction_pct)
            if screen_result.get("pass_fail") == "fail":
                flags.append(f"screening_failed: {screen_result.get('fail_reasons', [])}")
        except Exception:
            flags.append("screening_check_failed")

        # Queue correlation impact
        from src.queue.processor import enqueue
        await enqueue("correlation_impact", {"ticker": ticker, "trade_id": trade.id})

        return {
            "trade_id": trade.id,
            "ticker": ticker,
            "risk_reward": {"t1": rr_t1, "t2": rr_t2, "t3": rr_t3},
            "violations": violations,
            "flags": flags,
            "status": "waiting",
        }

    @mcp.tool()
    async def invest_get_trade(
        trade_id: int = 0,
        ticker: str = "",
    ) -> dict:
        """Get a trade by ID or ticker. Returns full trade with research doc and scores."""
        async with async_session() as db:
            if trade_id:
                trade = await db.get(Trade, trade_id)
            elif ticker:
                result = await db.execute(
                    select(Trade).where(Trade.ticker == ticker)
                    .order_by(Trade.created_at.desc()).limit(1)
                )
                trade = result.scalar_one_or_none()
            else:
                return {"error": "Provide trade_id or ticker"}

            if not trade:
                return {"error": "Trade not found"}

            # Get scores if any
            from src.models import TradeScore
            score_result = await db.execute(
                select(TradeScore).where(TradeScore.trade_id == trade.id)
            )
            scores = score_result.scalars().all()

        return {
            "trade": {
                "id": trade.id,
                "ticker": trade.ticker,
                "company_name": trade.company_name,
                "sector": trade.sector,
                "catalyst_type": trade.catalyst_type,
                "thesis_summary": trade.thesis_summary,
                "decision": trade.decision,
                "entry_price": float(trade.entry_price) if trade.entry_price else None,
                "shares": float(trade.shares) if trade.shares else None,
                "stop_loss": float(trade.stop_loss) if trade.stop_loss else None,
                "target_1": float(trade.target_1) if trade.target_1 else None,
                "target_2": float(trade.target_2) if trade.target_2 else None,
                "target_3": float(trade.target_3) if trade.target_3 else None,
                "risk_reward_t1": float(trade.risk_reward_t1) if trade.risk_reward_t1 else None,
                "conviction_pct": trade.conviction_pct,
                "outcome": trade.outcome,
                "actual_pnl_pct": float(trade.actual_pnl_pct) if trade.actual_pnl_pct else None,
                "actual_pnl_usd": float(trade.actual_pnl_usd) if trade.actual_pnl_usd else None,
                "research_doc": trade.research_doc,
                "execution_date": trade.execution_date.isoformat() if trade.execution_date else None,
                "close_date": trade.close_date.isoformat() if trade.close_date else None,
            },
            "scores": [
                {
                    "composite_score": float(s.composite_score) if s.composite_score else None,
                    "research_quality": s.research_quality_score,
                    "entry_timing": s.entry_timing_score,
                    "position_sizing": s.position_sizing_score,
                    "stop_loss": s.stop_loss_score,
                    "exit_timing": s.exit_timing_score,
                    "process_vs_outcome": s.process_vs_outcome,
                }
                for s in scores
            ],
        }

    @mcp.tool()
    async def invest_list_trades(
        status: str = "",
        sector: str = "",
        catalyst_type: str = "",
        outcome: str = "",
        limit: int = 20,
    ) -> dict:
        """List trades with optional filters. Paginated."""
        async with async_session() as db:
            query = select(Trade)
            if status:
                query = query.where(Trade.decision == status)
            if sector:
                query = query.where(Trade.sector == sector)
            if catalyst_type:
                query = query.where(Trade.catalyst_type == catalyst_type)
            if outcome:
                query = query.where(Trade.outcome == outcome)
            query = query.order_by(Trade.created_at.desc()).limit(limit)

            result = await db.execute(query)
            trades = result.scalars().all()

        return {
            "trades": [
                {
                    "id": t.id,
                    "ticker": t.ticker,
                    "sector": t.sector,
                    "decision": t.decision,
                    "outcome": t.outcome,
                    "entry_price": float(t.entry_price) if t.entry_price else None,
                    "conviction_pct": t.conviction_pct,
                    "actual_pnl_pct": float(t.actual_pnl_pct) if t.actual_pnl_pct else None,
                    "created_at": t.created_at.isoformat(),
                }
                for t in trades
            ],
            "count": len(trades),
        }

    @mcp.tool()
    async def invest_update_trade_plan(
        trade_id: int,
        decision: str = "",
        thesis_summary: str = "",
        research_doc: str = "",
        conviction_pct: int = 0,
        post_research_pct: int = 0,
        entry_price: float = 0,
        shares: float = 0,
        stop_loss: float = 0,
        target_1: float = 0,
        target_2: float = 0,
        target_3: float = 0,
        execution_date: str = "",
        rejection_reason: str = "",
    ) -> dict:
        """Update a trade plan. Versions old research_doc before overwriting."""
        async with async_session() as db:
            trade = await db.get(Trade, trade_id)
            if not trade:
                return {"error": f"Trade {trade_id} not found"}

            # Version old research doc if updating
            if research_doc and trade.research_doc:
                versions = trade.research_versions or []
                versions.append({
                    "doc": trade.research_doc,
                    "date": trade.research_date.isoformat() if trade.research_date else None,
                })
                trade.research_versions = versions
                trade.research_doc = research_doc
                trade.research_date = date_type.today()
            elif research_doc:
                trade.research_doc = research_doc
                trade.research_date = date_type.today()

            if decision:
                trade.decision = decision
            if thesis_summary:
                trade.thesis_summary = thesis_summary
            if conviction_pct:
                trade.conviction_pct = conviction_pct
            if post_research_pct:
                trade.post_research_pct = post_research_pct
            if entry_price:
                trade.entry_price = Decimal(str(entry_price))
            if shares:
                trade.shares = Decimal(str(shares))
            if stop_loss:
                trade.stop_loss = Decimal(str(stop_loss))
            if target_1:
                trade.target_1 = Decimal(str(target_1))
            if target_2:
                trade.target_2 = Decimal(str(target_2))
            if target_3:
                trade.target_3 = Decimal(str(target_3))
            if execution_date:
                trade.execution_date = date_type.fromisoformat(execution_date)
            if rejection_reason:
                trade.rejection_reason = rejection_reason

            # Recalculate R/R if prices changed
            if trade.entry_price and trade.stop_loss and trade.target_1:
                risk = float(trade.entry_price - trade.stop_loss)
                if risk > 0:
                    trade.risk_reward_t1 = Decimal(str(round((float(trade.target_1) - float(trade.entry_price)) / risk, 2)))
                    if trade.target_2:
                        trade.risk_reward_t2 = Decimal(str(round((float(trade.target_2) - float(trade.entry_price)) / risk, 2)))
                    if trade.target_3:
                        trade.risk_reward_t3 = Decimal(str(round((float(trade.target_3) - float(trade.entry_price)) / risk, 2)))

            await db.commit()
            await db.refresh(trade)

        return {
            "trade_id": trade.id,
            "ticker": trade.ticker,
            "decision": trade.decision,
            "updated": True,
        }
