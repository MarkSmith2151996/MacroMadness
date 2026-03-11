"""Self-service Schwab OAuth re-authentication flow."""

import os

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from src.db import async_session
from src.models import SchwabTokenState

router = APIRouter(prefix="/auth/schwab")

SCHWAB_APP_KEY = os.environ.get("SCHWAB_APP_KEY", "")
SCHWAB_APP_SECRET = os.environ.get("SCHWAB_APP_SECRET", "")
SERVER_URL = os.environ.get("SERVER_URL", "")
SCHWAB_TOKEN_ENCRYPTION_KEY = os.environ.get("SCHWAB_TOKEN_ENCRYPTION_KEY", "")


@router.get("/login")
async def schwab_login():
    """Redirect to Schwab OAuth consent screen."""
    auth_url = (
        f"https://api.schwabapi.com/v1/oauth/authorize"
        f"?client_id={SCHWAB_APP_KEY}"
        f"&redirect_uri={SERVER_URL}/auth/schwab/callback"
        f"&response_type=code&scope=readonly"
    )
    return RedirectResponse(auth_url)


@router.get("/callback")
async def schwab_callback(code: str):
    """Exchange authorization code for tokens, encrypt and store refresh token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.schwabapi.com/v1/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{SERVER_URL}/auth/schwab/callback",
            },
            auth=(SCHWAB_APP_KEY, SCHWAB_APP_SECRET),
        )
        resp.raise_for_status()
        tokens = resp.json()

    # Encrypt refresh token
    fernet = Fernet(SCHWAB_TOKEN_ENCRYPTION_KEY.encode())
    encrypted = fernet.encrypt(tokens["refresh_token"].encode()).decode()

    from datetime import datetime, timedelta, timezone
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 1800))

    async with async_session() as db:
        from sqlalchemy import select
        result = await db.execute(select(SchwabTokenState).limit(1))
        state = result.scalar_one_or_none()
        if state:
            state.encrypted_refresh_token = encrypted
            state.token_expires_at = expires_at
            state.last_sync_status = "token_refreshed"
        else:
            db.add(SchwabTokenState(
                encrypted_refresh_token=encrypted,
                token_expires_at=expires_at,
                last_sync_status="token_refreshed",
            ))
        await db.commit()

    return HTMLResponse("Schwab re-authentication successful. You can close this tab.")
