"""Module I: Order verification tool (1 tool)."""

from decimal import Decimal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.db import async_session
from src.models import OrderVerification, Trade
from src.validation import OrderInput


def register_order_verify_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_verify_order(
        ticker: str,
        order_type: str,
        shares: float,
        price: float,
        stop_price: float = 0,
        account_type: str = "",
        gtc: bool = True,
    ) -> dict:
        """Verify an order against the trade plan before placing it.
        Checks: shares match plan, price within range, stop matches, correct account."""
        # Validate inputs
        try:
            validated = OrderInput(
                ticker=ticker, order_type=order_type, shares=shares,
                price=price, stop_price=stop_price, account_type=account_type, gtc=gtc,
            )
            ticker = validated.ticker
        except Exception as e:
            return {"error": f"Validation failed: {e}"}

        discrepancies = []

        # Find the trade plan
        async with async_session() as db:
            result = await db.execute(
                select(Trade)
                .where(Trade.ticker == ticker, Trade.decision.in_(["waiting", "executed"]))
                .order_by(Trade.created_at.desc())
                .limit(1)
            )
            trade = result.scalar_one_or_none()

        if not trade:
            discrepancies.append(f"No active trade plan found for {ticker}")
        else:
            # Check shares
            if trade.shares and abs(float(trade.shares) - shares) > 0.01:
                discrepancies.append(
                    f"Shares mismatch: plan={float(trade.shares)}, order={shares}"
                )

            # Check price (within 2% of plan)
            if trade.entry_price:
                plan_price = float(trade.entry_price)
                pct_diff = abs(price - plan_price) / plan_price * 100
                if pct_diff > 2:
                    discrepancies.append(
                        f"Price {pct_diff:.1f}% from plan: plan=${plan_price}, order=${price}"
                    )

            # Check stop
            if trade.stop_loss and stop_price:
                if abs(float(trade.stop_loss) - stop_price) > 0.01:
                    discrepancies.append(
                        f"Stop mismatch: plan=${float(trade.stop_loss)}, order=${stop_price}"
                    )
            elif trade.stop_loss and not stop_price:
                discrepancies.append("Stop-loss in plan but not in order!")

            # Check account
            if trade.account_type and account_type and trade.account_type != account_type:
                discrepancies.append(
                    f"Account mismatch: plan={trade.account_type}, order={account_type}"
                )

        pass_fail = "pass" if not discrepancies else "fail"

        # Log verification
        async with async_session() as db:
            verification = OrderVerification(
                trade_id=trade.id if trade else None,
                order_type=order_type,
                shares_ordered=Decimal(str(shares)),
                price_ordered=Decimal(str(price)),
                stop_price=Decimal(str(stop_price)) if stop_price else None,
                gtc=gtc,
                result=pass_fail,
                discrepancies=discrepancies if discrepancies else None,
            )
            db.add(verification)
            await db.commit()

        return {
            "ticker": ticker,
            "result": pass_fail,
            "discrepancies": discrepancies,
            "verification_id": verification.id,
        }
