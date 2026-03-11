"""Audit log writer — every tool call is logged synchronously."""

from datetime import datetime, timezone

from src.db import async_session
from src.models import AuditLog


async def log_tool_call(
    tool_name: str,
    input_summary: dict | None,
    output_summary: str | None,
    success: bool,
    error_message: str | None = None,
    duration_ms: int | None = None,
    user_id: int | None = None,
):
    """Write an audit log entry. If this fails, the tool call should fail."""
    async with async_session() as db:
        db.add(AuditLog(
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            user_id=user_id,
        ))
        await db.commit()
