"""Configuration models for the trading notifier."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class BarPeriod(str, Enum):
    """Time period for bar data."""

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1mo"


class IndicatorType(str, Enum):
    """Supported technical indicators."""

    EMA50 = "EMA50"
    EMA100 = "EMA100"
    EMA200 = "EMA200"
    SMA50 = "SMA50"
    SMA200 = "SMA200"
    VWAP = "VWAP"


class IndicatorConfig(BaseModel):
    """Configuration for a technical indicator."""

    bar: BarPeriod = Field(..., description="Time period for the indicator")
    indicator: IndicatorType = Field(..., description="Type of technical indicator")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class SymbolConfig(BaseModel):
    """Configuration for a trading symbol."""

    symbol: str = Field(..., description="Trading symbol (e.g., 'AAPL', 'CRM')")
    price: Optional[float] = Field(None, description="Optional price override")
    indicators: List[IndicatorConfig] = Field(
        ...,
        description="List of indicators to monitor",
        min_items=1
    )

    @validator('symbol')
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol format."""
        if not v or not v.strip():
            raise ValueError("Symbol cannot be empty")
        return v.upper().strip()

    @validator('price')
    def validate_price(cls, v: Optional[float]) -> Optional[float]:
        """Validate price is positive."""
        if v is not None and v <= 0:
            raise ValueError("Price must be positive")
        return v


class TradingConfig(BaseModel):
    """Main configuration for the trading notifier."""

    symbols: List[SymbolConfig] = Field(
        ...,
        description="List of symbols to monitor",
        min_items=1
    )
    settings: 'TradingSettings' = Field(
        default_factory=lambda: TradingSettings(),
        description="Global settings"
    )


class TradingSettings(BaseModel):
    """Global settings for the trading system."""

    threshold_percentage: float = Field(
        default=5.0,
        description="Percentage threshold for alerts",
        ge=0.1,
        le=50.0
    )
    slack_channel: str = Field(
        default="#trading-alerts",
        description="Slack channel for notifications"
    )
    cooldown_hours: int = Field(
        default=24,
        description="Hours between duplicate alerts",
        ge=1,
        le=168  # 1 week max
    )
    dry_run: bool = Field(
        default=False,
        description="Run in test mode without sending alerts"
    )


# Update forward reference
try:
    TradingConfig.model_rebuild()
except AttributeError:
    # For older versions of Pydantic
    TradingConfig.update_forward_refs()
