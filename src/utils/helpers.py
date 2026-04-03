"""Helper utilities for configuration and validation."""

import json
from pathlib import Path
from typing import Dict, List

from loguru import logger
from pydantic import ValidationError

from ..models.config import TradingConfig, IndicatorConfig
from config.settings import Settings


def load_config(config_path: str) -> TradingConfig:
    """Load and validate trading configuration from JSON file."""
    try:
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, 'r') as f:
            config_data = json.load(f)

        trading_config = TradingConfig(**config_data)
        logger.info(f"Loaded configuration with {len(trading_config.symbols)} symbols")

        return trading_config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file {config_path}: {e}")
        raise
    except ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        raise


def validate_environment(settings: Settings) -> bool:
    """Validate that all required environment variables are set."""
    validation_errors = []

    # Check required Slack configuration
    if not settings.slack_bot_token:
        validation_errors.append("SLACK_BOT_TOKEN is required")

    # Check optional but recommended settings
    warnings = []

    if settings.threshold_percentage > 10.0:
        warnings.append(
            f"High threshold percentage: {settings.threshold_percentage}% "
            "(consider values between 1-10%)"
        )

    if settings.cooldown_hours < 1:
        warnings.append(
            f"Very short cooldown period: {settings.cooldown_hours} hours "
            "(consider at least 1 hour)"
        )

    # Log warnings
    for warning in warnings:
        logger.warning(warning)

    # Log validation errors
    if validation_errors:
        for error in validation_errors:
            logger.error(error)
        return False

    logger.info("Environment validation passed")
    return True


def symbols_config_to_dict(
    trading_config: TradingConfig
) -> Dict[str, List[IndicatorConfig]]:
    """Convert TradingConfig to a dictionary for easier processing."""
    symbols_dict = {}

    for symbol_config in trading_config.symbols:
        symbols_dict[symbol_config.symbol] = symbol_config.indicators

    return symbols_dict


def format_percentage(value: float) -> str:
    """Format percentage value for display."""
    return f"{value:+.1f}%"


def format_price(value: float) -> str:
    """Format price value for display."""
    return f"${value:.2f}"


def create_indicator_key(indicator_type: str, bar_period: str) -> str:
    """Create a standardized indicator key."""
    return f"{indicator_type}_{bar_period}"


def is_market_hours() -> bool:
    """Check if it's currently market hours (basic implementation)."""
    from datetime import datetime, time

    now = datetime.now()

    # Skip weekends
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False

    # Check if between 9:30 AM and 4:00 PM ET (simplified)
    current_time = now.time()
    market_open = time(9, 30)
    market_close = time(16, 0)

    return market_open <= current_time <= market_close


def sanitize_symbol(symbol: str) -> str:
    """Sanitize and validate a trading symbol."""
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string")

    # Remove whitespace and convert to uppercase
    clean_symbol = symbol.strip().upper()

    # Basic validation - alphanumeric characters and common symbols
    if not clean_symbol.replace(".", "").replace("-", "").isalnum():
        logger.warning(f"Symbol contains unusual characters: {clean_symbol}")

    return clean_symbol


def calculate_percentage_difference(current: float, target: float) -> float:
    """Calculate percentage difference between current and target values."""
    if target == 0:
        raise ValueError("Target value cannot be zero")

    return ((current - target) / target) * 100


def get_config_summary(trading_config: TradingConfig) -> str:
    """Get a summary of the trading configuration."""
    symbols = [sc.symbol for sc in trading_config.symbols]
    total_indicators = sum(len(sc.indicators) for sc in trading_config.symbols)

    return (
        f"Trading Configuration Summary:\n"
        f"- Symbols: {', '.join(symbols)}\n"
        f"- Total indicators: {total_indicators}\n"
        f"- Threshold: {trading_config.settings.threshold_percentage}%\n"
        f"- Cooldown: {trading_config.settings.cooldown_hours} hours\n"
        f"- Slack channel: {trading_config.settings.slack_channel}\n"
        f"- Dry run: {trading_config.settings.dry_run}"
    )
