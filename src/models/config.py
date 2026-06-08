"""Configuration models for the trading notifier."""

import re
from enum import Enum
from typing import List, Optional, Tuple

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
    """Common technical indicators (convenience constants).

    Indicators are NOT restricted to these — any EMA/SMA period is accepted
    as a string (e.g. "EMA40", "SMA125"). These members exist for readability
    and backward compatibility; validation is done by `parse_indicator`.
    """

    EMA50 = "EMA50"
    EMA100 = "EMA100"
    EMA200 = "EMA200"
    SMA50 = "SMA50"
    SMA200 = "SMA200"
    VWAP = "VWAP"


# Accepts any positive period: EMA<n> / SMA<n> (1-9999), or bare VWAP.
_INDICATOR_RE = re.compile(r"^(EMA|SMA)([1-9]\d{0,3})$")


def parse_indicator(name: str) -> Tuple[str, Optional[int]]:
    """Parse an indicator string into (kind, period).

    "EMA40" -> ("EMA", 40); "SMA200" -> ("SMA", 200); "VWAP" -> ("VWAP", None).
    Accepts plain strings or IndicatorType members. Raises ValueError otherwise.
    """
    if isinstance(name, Enum):
        name = name.value  # str(StrEnum) is "Class.MEMBER" on py3.12+, so unwrap
    name = str(name).strip().upper()
    if name == "VWAP":
        return "VWAP", None
    m = _INDICATOR_RE.match(name)
    if not m:
        raise ValueError(
            f"Invalid indicator {name!r}; expected EMA<n>, SMA<n> (e.g. 'EMA40'), or 'VWAP'"
        )
    return m.group(1), int(m.group(2))


class IndicatorConfig(BaseModel):
    """Configuration for a technical indicator.

    `indicator` is any EMA/SMA period as a string ("EMA40", "SMA125") or "VWAP".
    """

    bar: BarPeriod = Field(..., description="Time period for the indicator")
    indicator: str = Field(..., description="Indicator: EMA<n>, SMA<n>, or VWAP")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    @validator("indicator", pre=True)
    def validate_indicator(cls, v: object) -> str:
        """Normalize and validate the indicator string (any period allowed)."""
        kind, period = parse_indicator(v)
        return "VWAP" if kind == "VWAP" else f"{kind}{period}"

    @property
    def kind(self) -> str:
        """Indicator family: 'EMA', 'SMA', or 'VWAP'."""
        return parse_indicator(self.indicator)[0]

    @property
    def period(self) -> Optional[int]:
        """Indicator period (None for VWAP)."""
        return parse_indicator(self.indicator)[1]


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
