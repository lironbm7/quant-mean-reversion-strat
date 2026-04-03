"""Main application entry point for the quantitative trading notifier."""

from src.utils.logging import setup_logging
from src.utils.helpers import (
    get_config_summary,
    load_config,
    symbols_config_to_dict,
    validate_environment,
)
from src.services.notification import SlackNotifier
from src.services.market_data import MarketDataService
from src.services.alert_engine import AlertEngine
from src.models.alerts import Alert
from config.settings import settings
import asyncio
import sys
from typing import List

from loguru import logger

from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent.parent))


class TradingNotifier:
    """Main trading notifier application."""

    def __init__(self):
        """Initialize the trading notifier."""
        self.market_data_service = MarketDataService()
        self.slack_notifier = None
        self.alert_engine = None
        self.trading_config = None

    async def initialize(self) -> bool:
        """Initialize all components."""
        try:
            # Setup logging
            setup_logging(
                level=settings.log_level,
                log_file="logs/trading_notifier.log" if not settings.is_development else None
            )

            logger.info("🚀 Initializing Trading Notifier")

            # Validate environment
            if not validate_environment(settings):
                logger.error("Environment validation failed")
                return False

            # Load configuration
            self.trading_config = load_config(settings.config_file_path)
            logger.info(get_config_summary(self.trading_config))

            # Initialize Slack notifier (unless in dry run mode)
            if not settings.is_dry_run:
                self.slack_notifier = SlackNotifier(
                    bot_token=settings.slack_bot_token,
                    default_channel=settings.slack_channel
                )

            else:
                logger.info("Running in dry run mode - Slack notifications disabled")

            # Initialize alert engine
            self.alert_engine = AlertEngine(self.trading_config.settings)

            # Connect Slack notifier to alert engine for duplicate checking
            if self.slack_notifier:
                self.alert_engine.set_slack_notifier(self.slack_notifier)

            logger.info("✅ Trading Notifier initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Trading Notifier: {e}")
            return False

    async def run_scan(self) -> List[Alert]:
        """Run a single scan for trading signals."""
        try:
            logger.info("🔍 Starting market scan")

            # Convert config to dict for easier processing
            symbols_indicators = symbols_config_to_dict(self.trading_config)

            # Fetch market data for all symbols
            logger.info(f"Fetching data for {len(symbols_indicators)} symbols")
            market_data_dict = await self.market_data_service.get_multiple_market_data(
                symbols_indicators
            )

            if not market_data_dict:
                logger.warning("No market data retrieved")
                return []

            # Process signals
            logger.info("Processing signals")
            alerts = await self.alert_engine.process_multiple_symbols(
                market_data_dict,
                symbols_indicators
            )

            logger.info(f"Generated {len(alerts)} alerts")

            # Send notifications
            if alerts and self.slack_notifier:
                await self._send_notifications(alerts)
            elif alerts and settings.is_dry_run:
                self._log_dry_run_alerts(alerts)

            return alerts

        except Exception as e:
            logger.error(f"Error during market scan: {e}")

            # Send error notification
            if self.slack_notifier:
                await self.slack_notifier.send_error_notification(
                    f"Market scan failed: {str(e)}"
                )

            raise

    async def _send_notifications(self, alerts: List[Alert]) -> None:
        """Send alerts to Slack."""
        try:
            # Get market overview data for the notification
            market_overview = await self.slack_notifier.get_market_overview()

            successful_sends = await self.slack_notifier.send_multiple_alerts(alerts, market_overview=market_overview)

            if successful_sends < len(alerts):
                logger.warning(
                    f"Only {successful_sends}/{len(alerts)} alerts sent successfully"
                )
            else:
                logger.info(f"All {len(alerts)} alerts sent successfully")

        except Exception as e:
            logger.error(f"Error sending notifications: {e}")
            raise

    def _log_dry_run_alerts(self, alerts: List[Alert]) -> None:
        """Log alerts in dry run mode."""
        logger.info("📝 DRY RUN - Alerts that would be sent:")

        for i, alert in enumerate(alerts, 1):
            logger.info(f"Alert {i}:")
            logger.info(f"  Symbol: {alert.symbol}")
            logger.info(f"  Current Price: ${alert.current_price:.2f}")
            logger.info(f"  Target Level: ${alert.target_level:.2f}")
            logger.info(f"  Distance: {alert.percentage_difference:+.1f}%")
            logger.info(f"  Indicator: {alert.indicator_name} ({alert.bar_period})")
            logger.info("  " + "-" * 40)

    async def send_status_update(self, message: str, include_market_overview: bool = False) -> None:
        """Send status update to Slack."""
        if self.slack_notifier and not settings.is_dry_run:
            market_overview = None
            if include_market_overview:
                try:
                    market_overview = await self.slack_notifier.get_market_overview()
                except Exception as e:
                    logger.warning(f"Failed to get market overview: {e}")

            await self.slack_notifier.send_status_update(message, market_overview=market_overview)
        else:
            logger.info(f"Status: {message}")

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("🧹 Cleaning up resources")
        # Add any cleanup logic here if needed


async def main() -> int:
    """Main application entry point."""
    notifier = TradingNotifier()

    try:
        # Initialize
        if not await notifier.initialize():
            logger.error("Initialization failed")
            return 1

        # Run scan
        await notifier.run_scan()

        logger.info("✅ Trading Notifier completed successfully")
        return 0

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
        return 0

    except Exception as e:
        logger.error(f"Unexpected error: {e}")

        # Try to send error notification
        try:
            if notifier.slack_notifier:
                await notifier.slack_notifier.send_error_notification(
                    f"Trading Notifier crashed: {str(e)}"
                )
        except Exception:
            pass  # Don't fail on notification error

        return 1

    finally:
        await notifier.cleanup()


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
