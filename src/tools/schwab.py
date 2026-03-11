"""Module J: Schwab tool (1 tool)."""

from mcp.server.fastmcp import FastMCP

from src.integrations.schwab import schwab_client


def register_schwab_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_schwab(action: str) -> dict:
        """Schwab brokerage integration (read-only).
        action: sync | orders | detect_changes | token_status
        - sync: pull current positions from Schwab
        - orders: get recent orders
        - detect_changes: compare Schwab positions to DB and flag differences
        - token_status: check if Schwab token is valid"""
        if action == "token_status":
            return await schwab_client.get_token_status()

        elif action == "sync":
            try:
                accounts = await schwab_client.get_accounts()
                positions_data = []
                for acct in accounts.get("accounts", accounts) if isinstance(accounts, dict) else [accounts]:
                    acct_id = acct.get("accountNumber", acct.get("accountId", ""))
                    if acct_id:
                        positions = await schwab_client.get_positions(acct_id)
                        positions_data.append({
                            "account_id": acct_id,
                            "positions": positions,
                        })

                # Update last sync status
                from datetime import datetime, timezone
                from sqlalchemy import select
                from src.db import async_session
                from src.models import SchwabTokenState
                async with async_session() as db:
                    result = await db.execute(select(SchwabTokenState).limit(1))
                    state = result.scalar_one_or_none()
                    if state:
                        state.last_sync_at = datetime.now(timezone.utc)
                        state.last_sync_status = "success"
                        await db.commit()

                return {"synced": True, "accounts": positions_data}
            except Exception as e:
                # Log failure
                from datetime import datetime, timezone
                from sqlalchemy import select
                from src.db import async_session
                from src.models import SchwabTokenState
                async with async_session() as db:
                    result = await db.execute(select(SchwabTokenState).limit(1))
                    state = result.scalar_one_or_none()
                    if state:
                        state.last_sync_at = datetime.now(timezone.utc)
                        state.last_sync_status = f"error: {str(e)[:100]}"
                        await db.commit()
                return {"error": str(e)}

        elif action == "orders":
            try:
                accounts = await schwab_client.get_accounts()
                all_orders = []
                for acct in accounts.get("accounts", accounts) if isinstance(accounts, dict) else [accounts]:
                    acct_id = acct.get("accountNumber", acct.get("accountId", ""))
                    if acct_id:
                        orders = await schwab_client.get_orders(acct_id)
                        all_orders.append({"account_id": acct_id, "orders": orders})
                return {"orders": all_orders}
            except Exception as e:
                return {"error": str(e)}

        elif action == "detect_changes":
            try:
                # Get Schwab positions
                accounts = await schwab_client.get_accounts()
                schwab_positions = {}
                for acct in accounts.get("accounts", accounts) if isinstance(accounts, dict) else [accounts]:
                    acct_id = acct.get("accountNumber", acct.get("accountId", ""))
                    if acct_id:
                        pos = await schwab_client.get_positions(acct_id)
                        for p in pos.get("positions", pos) if isinstance(pos, dict) else []:
                            ticker = p.get("instrument", {}).get("symbol", "")
                            if ticker:
                                schwab_positions[ticker] = float(p.get("longQuantity", 0))

                # Get DB positions
                from sqlalchemy import select
                from src.db import async_session
                from src.models import Position
                async with async_session() as db:
                    result = await db.execute(
                        select(Position).where(Position.status == "open")
                    )
                    db_positions = {p.ticker: float(p.shares) for p in result.scalars().all()}

                # Compare
                changes = []
                for ticker, schwab_shares in schwab_positions.items():
                    db_shares = db_positions.get(ticker)
                    if db_shares is None:
                        changes.append({"ticker": ticker, "type": "new_in_schwab", "schwab_shares": schwab_shares})
                    elif abs(schwab_shares - db_shares) > 0.01:
                        changes.append({
                            "ticker": ticker, "type": "shares_changed",
                            "db_shares": db_shares, "schwab_shares": schwab_shares,
                        })

                for ticker in db_positions:
                    if ticker not in schwab_positions:
                        changes.append({"ticker": ticker, "type": "missing_in_schwab"})

                if changes:
                    # Send notification
                    from src.integrations.ntfy import send_notification
                    msg = f"Detected {len(changes)} position changes between DB and Schwab"
                    await send_notification("schwab_drift", msg, priority=4)

                return {"changes": changes, "count": len(changes)}
            except Exception as e:
                return {"error": str(e)}

        return {"error": f"Unknown action: {action}. Use sync, orders, detect_changes, or token_status."}
