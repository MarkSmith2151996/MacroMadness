"""Pydantic input validation models for MCP tools."""

import re

from pydantic import BaseModel, Field, field_validator


class TickerInput(BaseModel):
    ticker: str = Field(max_length=10)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v):
        v = v.upper().strip()
        if not re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", v):
            raise ValueError(f"Invalid ticker format: {v}")
        return v


class TradeInput(BaseModel):
    ticker: str
    shares: float = Field(gt=0, le=100000)
    entry_price: float = Field(gt=0, le=1000000)
    stop_loss: float = Field(gt=0, le=1000000)
    conviction_pct: int = Field(ge=0, le=100)
    target_1: float = Field(gt=0, le=1000000)
    sector: str = Field(max_length=50)
    thesis_summary: str = Field(max_length=5000)
    catalyst_type: str = Field(default="", max_length=30)
    market_regime: str = Field(default="", max_length=20)
    target_2: float = Field(default=0, ge=0, le=1000000)
    target_3: float = Field(default=0, ge=0, le=1000000)
    account_type: str = Field(default="", max_length=20)
    research_doc: str = Field(default="", max_length=50000)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v):
        v = v.upper().strip()
        if not re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", v):
            raise ValueError(f"Invalid ticker format: {v}")
        return v

    @field_validator("stop_loss")
    @classmethod
    def stop_below_entry(cls, v, info):
        entry = info.data.get("entry_price")
        if entry and v >= entry:
            raise ValueError("Stop loss must be below entry price")
        return v


class PositionInput(BaseModel):
    ticker: str = Field(max_length=10)
    shares: float = Field(gt=0, le=100000)
    cost_basis: float = Field(gt=0, le=1000000)
    stop_loss: float = Field(gt=0, le=1000000)
    account_type: str = Field(max_length=20)
    sector: str = Field(max_length=50)
    target_1: float = Field(default=0, ge=0, le=1000000)
    target_2: float = Field(default=0, ge=0, le=1000000)
    target_3: float = Field(default=0, ge=0, le=1000000)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v):
        v = v.upper().strip()
        if not re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", v):
            raise ValueError(f"Invalid ticker format: {v}")
        return v


class OrderInput(BaseModel):
    ticker: str = Field(max_length=10)
    order_type: str = Field(max_length=20)
    shares: float = Field(gt=0, le=100000)
    price: float = Field(gt=0, le=1000000)
    stop_price: float = Field(default=0, ge=0, le=1000000)
    account_type: str = Field(default="", max_length=20)
    gtc: bool = True

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v):
        v = v.upper().strip()
        if not re.match(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$", v):
            raise ValueError(f"Invalid ticker format: {v}")
        return v


def validate_ticker(ticker: str) -> str:
    """Quick ticker validation — returns cleaned uppercase ticker or raises."""
    return TickerInput(ticker=ticker).ticker
