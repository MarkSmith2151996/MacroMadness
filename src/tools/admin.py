"""Module K: Admin tool (1 tool)."""

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from src.db import async_session
from src.models import (
    AuditLog,
    PendingOperation,
    SchwabTokenState,
    User,
    ApiRateLimit,
)


def register_admin_tools(mcp: FastMCP):

    @mcp.tool()
    async def invest_admin(action: str, email: str = "", display_name: str = "", auth0_sub: str = "", user_id: int = 0) -> dict:
        """System administration.
        action: audit_log | users | add_user | revoke_user | backup_status | system_health
        - audit_log: recent tool call log (last 50)
        - users: list all users
        - add_user: add a new user (requires email, auth0_sub)
        - revoke_user: deactivate a user (requires user_id)
        - backup_status: check last backup
        - system_health: overall system status"""
        async with async_session() as db:
            if action == "audit_log":
                result = await db.execute(
                    select(AuditLog).order_by(AuditLog.logged_at.desc()).limit(50)
                )
                logs = result.scalars().all()
                return {
                    "logs": [
                        {
                            "id": l.id,
                            "logged_at": l.logged_at.isoformat(),
                            "tool_name": l.tool_name,
                            "success": l.success,
                            "error_message": l.error_message,
                            "duration_ms": l.duration_ms,
                        }
                        for l in logs
                    ],
                    "count": len(logs),
                }

            elif action == "users":
                result = await db.execute(select(User))
                users = result.scalars().all()
                return {
                    "users": [
                        {
                            "id": u.id,
                            "email": u.email,
                            "display_name": u.display_name,
                            "role": u.role,
                            "is_active": u.is_active,
                            "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
                        }
                        for u in users
                    ]
                }

            elif action == "add_user":
                if not email or not auth0_sub:
                    return {"error": "email and auth0_sub are required"}
                user = User(
                    email=email,
                    auth0_sub=auth0_sub,
                    display_name=display_name or None,
                    role="viewer",
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                return {"user_id": user.id, "added": True}

            elif action == "revoke_user":
                if not user_id:
                    return {"error": "user_id is required"}
                user = await db.get(User, user_id)
                if not user:
                    return {"error": f"User {user_id} not found"}
                user.is_active = False
                await db.commit()
                return {"user_id": user.id, "revoked": True}

            elif action == "system_health":
                # Schwab token status
                token_result = await db.execute(select(SchwabTokenState).limit(1))
                token = token_result.scalar_one_or_none()

                # Pending operations
                pending_result = await db.execute(
                    select(func.count()).select_from(PendingOperation)
                    .where(PendingOperation.status.in_(["pending", "retrying"]))
                )
                pending_count = pending_result.scalar()

                # Failed operations
                failed_result = await db.execute(
                    select(func.count()).select_from(PendingOperation)
                    .where(PendingOperation.status == "failed")
                )
                failed_count = failed_result.scalar()

                # API rate limits
                rate_result = await db.execute(select(ApiRateLimit))
                rates = rate_result.scalars().all()

                # Recent audit failures
                audit_fail_result = await db.execute(
                    select(func.count()).select_from(AuditLog)
                    .where(AuditLog.success == False)
                )
                audit_failures = audit_fail_result.scalar()

                components = [
                    {
                        "component": "Schwab Token",
                        "status": "valid" if (token and token.token_expires_at and token.token_expires_at > datetime.now(timezone.utc)) else "expired" if token else "not_configured",
                        "detail": f"Last sync: {token.last_sync_at.isoformat() if token and token.last_sync_at else 'never'}",
                    },
                    {
                        "component": "Queue",
                        "status": "ok" if pending_count == 0 else "pending",
                        "detail": f"{pending_count} pending, {failed_count} failed",
                    },
                    {
                        "component": "Audit Log",
                        "status": "ok" if audit_failures == 0 else "warnings",
                        "detail": f"{audit_failures} total failures",
                    },
                ]
                for r in rates:
                    components.append({
                        "component": f"API: {r.source}",
                        "status": "ok" if r.calls_today < r.daily_limit else "limit_reached",
                        "detail": f"{r.calls_today}/{r.daily_limit} calls today",
                    })

                return {"components": components}

            elif action == "backup_status":
                return {
                    "message": "Backups are managed via Railway PostgreSQL snapshots and scripts/backup.sh cron",
                    "note": "Check Railway dashboard for latest backup status",
                }

            return {"error": f"Unknown action: {action}"}
