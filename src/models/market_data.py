"""Market data models."""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class MarketData(BaseModel):
    """Market data for a trading symbol."""

    symbol: str = Field(..., description="Trading symbol")
    current_price: float = Field(..., description="Current market price")
    timestamp: datetime = Field(..., description="Data timestamp")
    indicator_values: Dict[str, float] = Field(
        default_factory=dict,
        description="Calculated indicator values"
    )
    volume: Optional[float] = Field(None, description="Trading volume")

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def get_indicator_value(self, indicator_key: str) -> Optional[float]:
        """Get indicator value by key."""
        return self.indicator_values.get(indicator_key)

    def add_indicator_value(self, indicator_key: str, value: float) -> None:
        """Add indicator value."""
        self.indicator_values[indicator_key] = value
