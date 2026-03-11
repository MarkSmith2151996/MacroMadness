"""Auth0 JWT RBAC middleware for MCP and REST endpoints."""

import os
from functools import wraps

import httpx
from jose import jwt, JWTError

from src.db import async_session
from src.models import User

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")
OPENBB_BACKEND_TOKEN = os.environ.get("OPENBB_BACKEND_TOKEN", "")

# RBAC role → allowed tools
VIEWER_TOOLS = {
    "invest_get_portfolio",
    "invest_get_trade",
    "invest_list_trades",
    "invest_lessons",       # search only
    "invest_principles",    # list only
    "invest_market_data",
    "invest_calendar",      # list only
    "invest_correlation",   # snapshot only
    "invest_weights",       # get only
}

_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    """Fetch and cache Auth0 JWKS."""
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
        resp.raise_for_status()
        _jwks_cache = resp.json()
        return _jwks_cache


async def validate_jwt(token: str) -> dict:
    """Validate an Auth0 JWT and return the payload."""
    jwks = await _get_jwks()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise ValueError("Invalid token header")

    rsa_key = {}
    for key in jwks.get("keys", []):
        if key["kid"] == unverified_header.get("kid"):
            rsa_key = key
            break

    if not rsa_key:
        raise ValueError("Unable to find matching key")

    payload = jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        audience=AUTH0_AUDIENCE,
        issuer=f"https://{AUTH0_DOMAIN}/",
    )
    return payload


async def get_user_from_token(token: str) -> User | None:
    """Validate JWT and return the User record."""
    payload = await validate_jwt(token)
    sub = payload.get("sub")
    if not sub:
        return None
    async with async_session() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.auth0_sub == sub))
        return result.scalar_one_or_none()


def check_tool_access(tool_name: str, role: str, action: str | None = None) -> bool:
    """Check if a role can access a tool. Owner can access everything."""
    if role == "owner":
        return True
    if tool_name not in VIEWER_TOOLS:
        return False
    # Viewer restrictions on specific actions
    if tool_name == "invest_lessons" and action and action != "search":
        return False
    if tool_name == "invest_principles" and action and action != "list":
        return False
    if tool_name == "invest_calendar" and action and action != "list":
        return False
    if tool_name == "invest_weights" and action and action != "get":
        return False
    return True


def validate_openbb_token(token: str) -> bool:
    """Validate a bearer token for OpenBB Workspace requests."""
    return token == OPENBB_BACKEND_TOKEN and bool(OPENBB_BACKEND_TOKEN)
