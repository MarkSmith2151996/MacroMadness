"""Test Pydantic validation models and validate_ticker helper."""

import pytest
from pydantic import ValidationError

from src.validation import OrderInput, PositionInput, TickerInput, TradeInput, validate_ticker


# ---------------------------------------------------------------------------
# TickerInput
# ---------------------------------------------------------------------------
class TestTickerInput:

    def test_valid_simple_ticker(self):
        t = TickerInput(ticker="AAPL")
        assert t.ticker == "AAPL"

    def test_valid_dot_ticker(self):
        """BRK.B style tickers should be valid."""
        t = TickerInput(ticker="BRK.B")
        assert t.ticker == "BRK.B"

    def test_lowercase_auto_uppercase(self):
        """Lowercase input should be auto-uppercased."""
        t = TickerInput(ticker="aapl")
        assert t.ticker == "AAPL"

    def test_mixed_case_auto_uppercase(self):
        t = TickerInput(ticker="aPpL")
        assert t.ticker == "APPL"

    def test_whitespace_stripped(self):
        t = TickerInput(ticker="  AAPL  ")
        assert t.ticker == "AAPL"

    def test_invalid_numeric_prefix(self):
        """Tickers starting with numbers should fail."""
        with pytest.raises(ValidationError):
            TickerInput(ticker="123INVALID")

    def test_invalid_empty(self):
        """Empty ticker should fail."""
        with pytest.raises(ValidationError):
            TickerInput(ticker="")

    def test_invalid_too_long(self):
        """Ticker with more than 5 letters before dot should fail."""
        with pytest.raises(ValidationError):
            TickerInput(ticker="ABCDEF")

    def test_valid_single_letter(self):
        t = TickerInput(ticker="V")
        assert t.ticker == "V"

    def test_valid_five_letter(self):
        t = TickerInput(ticker="GOOGL")
        assert t.ticker == "GOOGL"

    def test_invalid_special_chars(self):
        with pytest.raises(ValidationError):
            TickerInput(ticker="AB@C")

    def test_invalid_numbers_only(self):
        with pytest.raises(ValidationError):
            TickerInput(ticker="12345")

    def test_valid_dot_two_letter_suffix(self):
        t = TickerInput(ticker="BF.AB")
        assert t.ticker == "BF.AB"


# ---------------------------------------------------------------------------
# TradeInput
# ---------------------------------------------------------------------------
class TestTradeInput:

    def test_valid_trade(self):
        t = TradeInput(
            ticker="AAPL",
            shares=10,
            entry_price=150.00,
            stop_loss=140.00,
            target_1=170.00,
            sector="technology",
            thesis_summary="Strong iPhone sales expected",
            conviction_pct=75,
        )
        assert t.ticker == "AAPL"
        assert t.shares == 10
        assert t.entry_price == 150.00
        assert t.stop_loss == 140.00

    def test_stop_loss_above_entry_fails(self):
        """stop_loss >= entry_price should fail."""
        with pytest.raises(ValidationError) as exc_info:
            TradeInput(
                ticker="AAPL",
                shares=10,
                entry_price=150.00,
                stop_loss=160.00,
                target_1=170.00,
                sector="technology",
                thesis_summary="Test",
                conviction_pct=75,
            )
        assert "Stop loss must be below entry price" in str(exc_info.value)

    def test_stop_loss_equal_entry_fails(self):
        """stop_loss == entry_price should fail."""
        with pytest.raises(ValidationError):
            TradeInput(
                ticker="AAPL",
                shares=10,
                entry_price=150.00,
                stop_loss=150.00,
                target_1=170.00,
                sector="technology",
                thesis_summary="Test",
                conviction_pct=75,
            )

    def test_shares_zero_fails(self):
        """shares <= 0 should fail."""
        with pytest.raises(ValidationError):
            TradeInput(
                ticker="AAPL",
                shares=0,
                entry_price=150.00,
                stop_loss=140.00,
                target_1=170.00,
                sector="technology",
                thesis_summary="Test",
                conviction_pct=75,
            )

    def test_shares_negative_fails(self):
        with pytest.raises(ValidationError):
            TradeInput(
                ticker="AAPL",
                shares=-5,
                entry_price=150.00,
                stop_loss=140.00,
                target_1=170.00,
                sector="technology",
                thesis_summary="Test",
                conviction_pct=75,
            )

    def test_conviction_out_of_range(self):
        """conviction_pct > 100 should fail."""
        with pytest.raises(ValidationError):
            TradeInput(
                ticker="AAPL",
                shares=10,
                entry_price=150.00,
                stop_loss=140.00,
                target_1=170.00,
                sector="technology",
                thesis_summary="Test",
                conviction_pct=110,
            )

    def test_ticker_auto_uppercase_in_trade(self):
        t = TradeInput(
            ticker="aapl",
            shares=10,
            entry_price=150.00,
            stop_loss=140.00,
            target_1=170.00,
            sector="technology",
            thesis_summary="Test",
            conviction_pct=75,
        )
        assert t.ticker == "AAPL"

    def test_optional_fields_default(self):
        t = TradeInput(
            ticker="MSFT",
            shares=5,
            entry_price=300.00,
            stop_loss=280.00,
            target_1=350.00,
            sector="technology",
            thesis_summary="Cloud growth",
            conviction_pct=60,
        )
        assert t.catalyst_type == ""
        assert t.market_regime == ""
        assert t.target_2 == 0
        assert t.target_3 == 0
        assert t.account_type == ""
        assert t.research_doc == ""


# ---------------------------------------------------------------------------
# PositionInput
# ---------------------------------------------------------------------------
class TestPositionInput:

    def test_valid_position(self):
        p = PositionInput(
            ticker="NVDA",
            shares=10.0,
            cost_basis=800.0,
            stop_loss=750.0,
            account_type="roth_ira",
            sector="semiconductors",
        )
        assert p.ticker == "NVDA"
        assert p.shares == 10.0

    def test_position_shares_zero_fails(self):
        with pytest.raises(ValidationError):
            PositionInput(
                ticker="NVDA",
                shares=0,
                cost_basis=800.0,
                stop_loss=750.0,
                account_type="roth_ira",
                sector="semiconductors",
            )

    def test_position_ticker_uppercase(self):
        p = PositionInput(
            ticker="nvda",
            shares=5,
            cost_basis=800.0,
            stop_loss=750.0,
            account_type="roth_ira",
            sector="semiconductors",
        )
        assert p.ticker == "NVDA"

    def test_position_optional_targets(self):
        p = PositionInput(
            ticker="AAPL",
            shares=10,
            cost_basis=150.0,
            stop_loss=140.0,
            account_type="taxable",
            sector="technology",
            target_1=170.0,
            target_2=190.0,
            target_3=210.0,
        )
        assert p.target_1 == 170.0
        assert p.target_2 == 190.0
        assert p.target_3 == 210.0


# ---------------------------------------------------------------------------
# OrderInput
# ---------------------------------------------------------------------------
class TestOrderInput:

    def test_valid_order(self):
        o = OrderInput(
            ticker="AAPL",
            order_type="limit_buy",
            shares=10,
            price=150.00,
            stop_price=140.00,
            gtc=True,
        )
        assert o.ticker == "AAPL"
        assert o.order_type == "limit_buy"
        assert o.shares == 10
        assert o.gtc is True

    def test_order_no_stop_price(self):
        o = OrderInput(
            ticker="MSFT",
            order_type="market_buy",
            shares=5,
            price=300.00,
        )
        assert o.stop_price == 0
        assert o.account_type == ""
        assert o.gtc is True

    def test_order_shares_zero_fails(self):
        with pytest.raises(ValidationError):
            OrderInput(
                ticker="AAPL",
                order_type="limit_buy",
                shares=0,
                price=150.00,
            )

    def test_order_ticker_uppercase(self):
        o = OrderInput(
            ticker="goog",
            order_type="limit_buy",
            shares=3,
            price=180.00,
        )
        assert o.ticker == "GOOG"

    def test_order_price_zero_fails(self):
        with pytest.raises(ValidationError):
            OrderInput(
                ticker="AAPL",
                order_type="limit_buy",
                shares=10,
                price=0,
            )


# ---------------------------------------------------------------------------
# validate_ticker helper
# ---------------------------------------------------------------------------
class TestValidateTicker:

    def test_valid(self):
        assert validate_ticker("AAPL") == "AAPL"

    def test_uppercase(self):
        assert validate_ticker("aapl") == "AAPL"

    def test_dot_ticker(self):
        assert validate_ticker("BRK.B") == "BRK.B"

    def test_invalid_raises(self):
        with pytest.raises(ValidationError):
            validate_ticker("123INVALID")

    def test_empty_raises(self):
        with pytest.raises(ValidationError):
            validate_ticker("")
