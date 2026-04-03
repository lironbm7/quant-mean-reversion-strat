"""Alert models for notifications."""

from datetime import datetime

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Alert for mean reversion opportunity."""

    symbol: str = Field(..., description="Trading symbol")
    current_price: float = Field(..., description="Current market price")
    target_level: float = Field(..., description="Target indicator level")
    percentage_difference: float = Field(..., description="Percentage difference from target")
    indicator_name: str = Field(..., description="Name of the indicator")
    bar_period: str = Field(..., description="Time period of the indicator")
    message: str = Field(..., description="Human-readable alert message")
    timestamp: datetime = Field(default_factory=datetime.now, description="Alert timestamp")

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    @property
    def is_below_target(self) -> bool:
        """Check if current price is below target level."""
        return self.current_price < self.target_level

    @property
    def is_above_target(self) -> bool:
        """Check if current price is above target level."""
        return self.current_price > self.target_level

    def format_slack_message(self) -> str:
        """Format alert for Slack notification."""
        return (
            f"📈 ${self.symbol}\n"
            f"Current Price: ${self.current_price:.2f}\n"
            f"{self.indicator_name} ({self.bar_period}): ${self.target_level:.2f}\n"
            f"Distance: {self.percentage_difference:+.1f}%\n"
        )
