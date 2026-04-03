"""Configuration settings for the trading notifier."""

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid"
    )

    # Slack configuration
    slack_bot_token: str = Field(
        ...,
        description="Slack bot token for sending notifications"
    )

    slack_channel: str = Field(
        default="general",
        description="Default Slack channel for notifications"
    )

    # Trading Configuration
    threshold_percentage: float = Field(
        default=5.0,
        env="THRESHOLD_PERCENTAGE",
        description="Percentage threshold for alerts"
    )

    # Alert configuration
    cooldown_hours: int = Field(
        default=24,
        description="Hours to wait before sending duplicate alerts"
    )

    # Application Configuration
    dry_run: bool = Field(
        default=False,
        env="DRY_RUN",
        description="Run in dry run mode without sending notifications"
    )

    log_level: str = Field(
        default="INFO",
        env="LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # File Paths
    config_file_path: str = Field(
        default="config/symbols.json",
        env="CONFIG_FILE_PATH",
        description="Path to symbols configuration file"
    )

    # API rate limiting
    request_delay_seconds: float = Field(
        default=1.0,
        description="Delay between API requests to avoid rate limiting"
    )

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.log_level.upper() == "DEBUG"

    @property
    def is_dry_run(self) -> bool:
        """Check if running in dry run mode."""
        return self.dry_run


# Global settings instance
settings = Settings()
