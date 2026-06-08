"""Tests for data models."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.models.config import (
    BarPeriod,
    IndicatorType,
    IndicatorConfig,
    SymbolConfig,
    TradingConfig,
    TradingSettings,
)
from src.models.market_data import MarketData
from src.models.alerts import Alert


class TestBarPeriod:
    """Test BarPeriod enum."""

    def test_bar_period_values(self):
        """Test all bar period values are valid."""
        assert BarPeriod.ONE_MINUTE == "1m"
        assert BarPeriod.FIVE_MINUTES == "5m"
        assert BarPeriod.FIFTEEN_MINUTES == "15m"
        assert BarPeriod.THIRTY_MINUTES == "30m"
        assert BarPeriod.ONE_HOUR == "1h"
        assert BarPeriod.FOUR_HOURS == "4h"
        assert BarPeriod.ONE_DAY == "1d"
        assert BarPeriod.ONE_WEEK == "1w"
        assert BarPeriod.ONE_MONTH == "1mo"


class TestIndicatorType:
    """Test IndicatorType enum."""

    def test_indicator_type_values(self):
        """Test all indicator type values are valid."""
        assert IndicatorType.EMA50 == "EMA50"
        assert IndicatorType.EMA100 == "EMA100"
        assert IndicatorType.EMA200 == "EMA200"
        assert IndicatorType.SMA50 == "SMA50"
        assert IndicatorType.SMA200 == "SMA200"
        assert IndicatorType.VWAP == "VWAP"


class TestIndicatorConfig:
    """Test IndicatorConfig model."""

    def test_valid_indicator_config(self):
        """Test creating valid indicator config."""
        config = IndicatorConfig(
            bar=BarPeriod.ONE_WEEK,
            indicator=IndicatorType.EMA200
        )
        assert config.bar == BarPeriod.ONE_WEEK
        assert config.indicator == IndicatorType.EMA200

    def test_indicator_config_with_strings(self):
        """Test creating indicator config with string values."""
        config = IndicatorConfig(bar="1w", indicator="EMA200")
        assert config.bar == BarPeriod.ONE_WEEK
        assert config.indicator == IndicatorType.EMA200

    def test_arbitrary_ema_period(self):
        """Any EMA/SMA period is accepted, not just the enum constants."""
        config = IndicatorConfig(bar="4h", indicator="EMA120")
        assert config.indicator == "EMA120"
        assert config.kind == "EMA"
        assert config.period == 120

        sma = IndicatorConfig(bar="1d", indicator="sma45")  # normalized to upper
        assert sma.indicator == "SMA45"
        assert (sma.kind, sma.period) == ("SMA", 45)

    def test_vwap_has_no_period(self):
        config = IndicatorConfig(bar="1d", indicator="VWAP")
        assert config.kind == "VWAP"
        assert config.period is None

    def test_invalid_indicator_rejected(self):
        for bad in ("EMA", "EMA0", "RSI14", "EMA-5", ""):
            with pytest.raises(ValidationError):
                IndicatorConfig(bar="1d", indicator=bad)


class TestSymbolConfig:
    """Test SymbolConfig model."""

    def test_valid_symbol_config(self):
        """Test creating valid symbol config."""
        indicators = [
            IndicatorConfig(bar="1w", indicator="EMA200"),
            IndicatorConfig(bar="1d", indicator="SMA50")
        ]
        config = SymbolConfig(
            symbol="AAPL",
            price=150.0,
            indicators=indicators
        )
        assert config.symbol == "AAPL"
        assert config.price == 150.0
        assert len(config.indicators) == 2

    def test_symbol_normalization(self):
        """Test symbol is normalized to uppercase."""
        config = SymbolConfig(
            symbol="  aapl  ",
            indicators=[IndicatorConfig(bar="1d", indicator="SMA50")]
        )
        assert config.symbol == "AAPL"

    def test_empty_symbol_validation(self):
        """Test empty symbol raises validation error."""
        with pytest.raises(ValidationError):
            SymbolConfig(
                symbol="",
                indicators=[IndicatorConfig(bar="1d", indicator="SMA50")]
            )

    def test_negative_price_validation(self):
        """Test negative price raises validation error."""
        with pytest.raises(ValidationError):
            SymbolConfig(
                symbol="AAPL",
                price=-10.0,
                indicators=[IndicatorConfig(bar="1d", indicator="SMA50")]
            )

    def test_empty_indicators_validation(self):
        """Test empty indicators list raises validation error."""
        with pytest.raises(ValidationError):
            SymbolConfig(symbol="AAPL", indicators=[])


class TestTradingSettings:
    """Test TradingSettings model."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = TradingSettings()
        assert settings.threshold_percentage == 5.0
        assert settings.slack_channel == "#trading-alerts"
        assert settings.cooldown_hours == 24
        assert settings.dry_run is False

    def test_custom_settings(self):
        """Test custom settings values."""
        settings = TradingSettings(
            threshold_percentage=10.0,
            slack_channel="#custom-alerts",
            cooldown_hours=12,
            dry_run=True
        )
        assert settings.threshold_percentage == 10.0
        assert settings.slack_channel == "#custom-alerts"
        assert settings.cooldown_hours == 12
        assert settings.dry_run is True

    def test_threshold_validation(self):
        """Test threshold percentage validation."""
        with pytest.raises(ValidationError):
            TradingSettings(threshold_percentage=0.0)

        with pytest.raises(ValidationError):
            TradingSettings(threshold_percentage=100.0)


class TestTradingConfig:
    """Test TradingConfig model."""

    def test_valid_trading_config(self):
        """Test creating valid trading config."""
        symbols = [
            SymbolConfig(
                symbol="AAPL",
                indicators=[IndicatorConfig(bar="1d", indicator="SMA50")]
            )
        ]
        config = TradingConfig(symbols=symbols)
        assert len(config.symbols) == 1
        assert config.settings.threshold_percentage == 5.0

    def test_empty_symbols_validation(self):
        """Test empty symbols list raises validation error."""
        with pytest.raises(ValidationError):
            TradingConfig(symbols=[])


class TestMarketData:
    """Test MarketData model."""

    def test_valid_market_data(self):
        """Test creating valid market data."""
        timestamp = datetime.now()
        data = MarketData(
            symbol="AAPL",
            current_price=150.0,
            timestamp=timestamp,
            volume=1000000.0
        )
        assert data.symbol == "AAPL"
        assert data.current_price == 150.0
        assert data.timestamp == timestamp
        assert data.volume == 1000000.0
        assert len(data.indicator_values) == 0

    def test_add_indicator_value(self):
        """Test adding indicator values."""
        data = MarketData(
            symbol="AAPL",
            current_price=150.0,
            timestamp=datetime.now()
        )
        data.add_indicator_value("EMA200_1w", 145.0)
        data.add_indicator_value("SMA50_1d", 152.0)

        assert data.get_indicator_value("EMA200_1w") == 145.0
        assert data.get_indicator_value("SMA50_1d") == 152.0
        assert data.get_indicator_value("nonexistent") is None


class TestAlert:
    """Test Alert model."""

    def test_valid_alert(self):
        """Test creating valid alert."""
        alert = Alert(
            symbol="AAPL",
            current_price=145.0,
            target_level=150.0,
            percentage_difference=-3.33,
            indicator_name="EMA200",
            bar_period="1w",
            message="Test alert"
        )
        assert alert.symbol == "AAPL"
        assert alert.current_price == 145.0
        assert alert.target_level == 150.0
        assert alert.percentage_difference == -3.33
        assert alert.is_below_target is True
        assert alert.is_above_target is False

    def test_alert_above_target(self):
        """Test alert when price is above target."""
        alert = Alert(
            symbol="AAPL",
            current_price=155.0,
            target_level=150.0,
            percentage_difference=3.33,
            indicator_name="EMA200",
            bar_period="1w",
            message="Test alert"
        )
        assert alert.is_below_target is False
        assert alert.is_above_target is True

    def test_format_slack_message_below_target(self):
        """Test Slack message formatting for price below target."""
        alert = Alert(
            symbol="AAPL",
            current_price=145.0,
            target_level=150.0,
            percentage_difference=-3.3,
            indicator_name="EMA200",
            bar_period="1w",
            message="Test alert"
        )
        message = alert.format_slack_message()

        assert "📈 $AAPL" in message
        assert "Current Price: $145.00" in message
        assert "EMA200 (1w): $150.00" in message
        assert "Distance: -3.3%" in message

    def test_format_slack_message_above_target(self):
        """Test Slack message formatting for price above target."""
        alert = Alert(
            symbol="AAPL",
            current_price=155.0,
            target_level=150.0,
            percentage_difference=3.3,
            indicator_name="EMA200",
            bar_period="1w",
            message="Test alert"
        )
        message = alert.format_slack_message()

        assert "📈 $AAPL" in message
        assert "Current Price: $155.00" in message
        assert "EMA200 (1w): $150.00" in message
        assert "Distance: +3.3%" in message
