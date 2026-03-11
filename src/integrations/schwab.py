"""Schwab API client — read-only. No order placement methods exist."""

import os
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from src.db import async_session
from src.models import SchwabTokenState


class SchwabClient:
    BASE_URL = "https://api.schwabapi.com/trader/v1"

    def __init__(self):
        self.app_key = os.environ.get("SCHWAB_APP_KEY", "")
        self.app_secret = os.environ.get("SCHWAB_APP_SECRET", "")
        self.encryption_key = os.environ.get("SCHWAB_TOKEN_ENCRYPTION_KEY", "")
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def get_accounts(self) -> dict:
        return await self._get("/accounts")

    async def get_positions(self, account_id: str) -> dict:
        return await self._get(f"/accounts/{account_id}")

    async def get_orders(self, account_id: str) -> dict:
        return await self._get(f"/accounts/{account_id}/orders")

    async def get_token_status(self) -> dict:
        """Check the state of the stored Schwab token."""
        async with async_session() as db:
            result = await db.execute(select(SchwabTokenState).limit(1))
            state = result.scalar_one_or_none()
            if not state:
                return {"status": "not_configured", "message": "No Schwab token stored"}
            now = datetime.now(timezone.utc)
            if state.token_expires_at and state.token_expires_at < now:
                return {
                    "status": "expired",
                    "expired_at": state.token_expires_at.isoformat(),
                    "last_sync": state.last_sync_at.isoformat() if state.last_sync_at else None,
                }
            return {
                "status": "valid",
                "expires_at": state.token_expires_at.isoformat() if state.token_expires_at else None,
                "last_sync": state.last_sync_at.isoformat() if state.last_sync_at else None,
                "last_sync_status": state.last_sync_status,
            }

    # No order placement methods. They do not exist in this file.
    # SCHWAB_TRADING_ENABLED must be true AND order methods must be
    # explicitly added before any trading is possible.

    async def _get(self, path: str) -> dict:
        token = await self._ensure_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def _ensure_access_token(self) -> str:
        """Refresh access token if expired using stored encrypted refresh token."""
        now = datetime.now(timezone.utc)
        if self._access_token and self._token_expires_at and self._token_expires_at > now:
            return self._access_token

        # Get refresh token from DB
        async with async_session() as db:
            result = await db.execute(select(SchwabTokenState).limit(1))
            state = result.scalar_one_or_none()
            if not state or not state.encrypted_refresh_token:
                raise RuntimeError("No Schwab refresh token. Visit /auth/schwab/login to authenticate.")

        # Decrypt refresh token
        fernet = Fernet(self.encryption_key.encode())
        refresh_token = fernet.decrypt(state.encrypted_refresh_token.encode()).decode()

        # Exchange for access token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.schwabapi.com/v1/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                auth=(self.app_key, self.app_secret),
            )
            resp.raise_for_status()
            tokens = resp.json()

        self._access_token = tokens["access_token"]
        self._token_expires_at = now + timedelta(seconds=tokens.get("expires_in", 1800))

        # Update stored token if a new refresh token was issued
        if "refresh_token" in tokens and tokens["refresh_token"] != refresh_token:
            new_encrypted = fernet.encrypt(tokens["refresh_token"].encode()).decode()
            async with async_session() as db:
                result = await db.execute(select(SchwabTokenState).limit(1))
                state = result.scalar_one_or_none()
                if state:
                    state.encrypted_refresh_token = new_encrypted
                    state.token_expires_at = self._token_expires_at
                    await db.commit()

        return self._access_token


# Module-level singleton
schwab_client = SchwabClient()
