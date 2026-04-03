"""Alert engine for mean reversion signal detection."""

from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from ..models.alerts import Alert
from ..models.config import IndicatorConfig, TradingSettings
from ..models.market_data import MarketData


class AlertEngine:
    """Engine for detecting mean reversion signals and generating alerts."""

    def __init__(self, settings: TradingSettings):
        """Initialize alert engine."""
        self.settings = settings
        self._slack_notifier = None  # Will be set by main app

    def set_slack_notifier(self, slack_notifier):
        """Set the Slack notifier for checking recent messages."""
        self._slack_notifier = slack_notifier

    async def detect_signals(
        self,
        market_data: MarketData,
        indicators: List[IndicatorConfig]
    ) -> List[Alert]:
        """Detect mean reversion signals for a symbol."""
        alerts = []

        for indicator_config in indicators:
            try:
                alert = self._check_indicator_signal(
                    market_data, indicator_config
                )
                if alert:
                    alerts.append(alert)

            except Exception as e:
                logger.error(
                    f"Error checking {indicator_config.indicator} "
                    f"signal for {market_data.symbol}: {e}"
                )
                continue

        return alerts

    def _check_indicator_signal(
        self,
        market_data: MarketData,
        indicator_config: IndicatorConfig
    ) -> Optional[Alert]:
        """Check if an indicator generates a signal."""
        indicator_key = f"{indicator_config.indicator}_{indicator_config.bar}"
        indicator_value = market_data.get_indicator_value(indicator_key)

        if indicator_value is None:
            logger.warning(
                f"No indicator value found for {indicator_key} "
                f"in {market_data.symbol} data"
            )
            return None

        current_price = market_data.current_price

        # Calculate percentage difference
        percentage_diff = ((current_price - indicator_value) / indicator_value) * 100

        # For mean reversion LONG plays: alert when price is near the moving average
        # This includes:
        # 1. Price approaching from above (positive %)
        # 2. Price touching/slightly below the MA (negative %, but within threshold)
        # This catches the actual bounce setups where price dips to/below MA levels
        if abs(percentage_diff) <= self.settings.threshold_percentage:
            # Create alert
            alert = Alert(
                symbol=market_data.symbol,
                current_price=current_price,
                target_level=indicator_value,
                percentage_difference=percentage_diff,
                indicator_name=indicator_config.indicator,
                bar_period=indicator_config.bar,
                message=self._generate_alert_message(
                    market_data.symbol,
                    current_price,
                    indicator_value,
                    percentage_diff,
                    indicator_config
                ),
                timestamp=datetime.now()
            )

            logger.info(
                f"Signal detected for {market_data.symbol}: "
                f"{indicator_config.indicator} at {percentage_diff:+.1f}%"
            )

            return alert

        logger.debug(
            f"No signal for {market_data.symbol} "
            f"({indicator_config.indicator}): {percentage_diff:+.1f}% "
            f"(threshold: ±{self.settings.threshold_percentage}% for mean reversion)"
        )

        return None

    def _generate_alert_message(
        self,
        symbol: str,
        current_price: float,
        target_level: float,
        percentage_diff: float,
        indicator_config: IndicatorConfig
    ) -> str:
        """Generate human-readable alert message."""
        if current_price < target_level:
            # Price below MA - potential bounce setup
            direction = "below"
            setup_type = "oversold bounce setup"
        else:
            # Price above MA - approaching support
            direction = "above"
            setup_type = "approaching support"

        return (
            f"{symbol} is {abs(percentage_diff):.1f}% {direction} "
            f"{indicator_config.indicator} ({indicator_config.bar}) "
            f"level of ${target_level:.2f} - {setup_type}. "
            f"Current price: ${current_price:.2f}"
        )

    async def process_multiple_symbols(
        self,
        market_data_dict: Dict[str, MarketData],
        symbols_indicators: Dict[str, List[IndicatorConfig]]
    ) -> List[Alert]:
        """Process multiple symbols and return all alerts."""
        all_alerts = []

        for symbol, market_data in market_data_dict.items():
            if symbol not in symbols_indicators:
                logger.warning(f"No indicators configured for {symbol}")
                continue

            try:
                indicators = symbols_indicators[symbol]
                alerts = await self.detect_signals(market_data, indicators)
                all_alerts.extend(alerts)

            except Exception as e:
                logger.error(f"Error processing signals for {symbol}: {e}")
                continue

        logger.info(f"Generated {len(all_alerts)} alerts from {len(market_data_dict)} symbols")
        return all_alerts
