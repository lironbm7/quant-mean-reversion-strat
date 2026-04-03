"""Slack notification service for trading alerts."""

from typing import List, Optional, Dict

from loguru import logger
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..models.alerts import Alert


class SlackNotifier:
    """Service for sending trading alerts to Slack."""

    def __init__(self, bot_token: str, default_channel: str = "#trading-alerts"):
        """Initialize Slack notifier."""
        self.client = WebClient(token=bot_token)
        self.default_channel = default_channel
        self._verify_connection()

        # Market overview symbols
        self.market_overview_symbols = ["SPY", "QQQ", "^VIX"]

    def _verify_connection(self) -> None:
        """Verify Slack connection is working."""
        try:
            response = self.client.auth_test()
            logger.info(f"Connected to Slack as {response['user']}")
        except SlackApiError as e:
            logger.error(f"Failed to connect to Slack: {e}")
            raise

    async def send_alert(
        self,
        alert: Alert,
        channel: Optional[str] = None
    ) -> bool:
        """Send a single alert to Slack."""
        channel = channel or self.default_channel

        try:
            # Use the formatted Slack message from the Alert model
            message = alert.format_slack_message()

            response = self.client.chat_postMessage(
                channel=channel,
                text=message,
                username="Trading Bot",
                icon_emoji=":chart_with_upwards_trend:"
            )

            if response["ok"]:
                logger.info(
                    f"Successfully sent alert for {alert.symbol} to {channel}"
                )
                return True
            else:
                logger.error(f"Failed to send Slack message: {response}")
                return False

        except SlackApiError as e:
            logger.error(f"Slack API error sending alert for {alert.symbol}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending alert for {alert.symbol}: {e}")
            return False

    async def send_multiple_alerts(
        self,
        alerts: List[Alert],
        channel: Optional[str] = None,
        market_overview: Optional[Dict[str, Dict[str, float]]] = None
    ) -> int:
        """Send multiple alerts to Slack."""
        if not alerts:
            logger.info("No alerts to send")
            return 0

        channel = channel or self.default_channel
        successful_sends = 0

        # Send summary first if multiple alerts
        if len(alerts) > 1:
            summary_message = self._create_summary_message(alerts, market_overview)
            try:
                self.client.chat_postMessage(
                    channel=channel,
                    text=summary_message,
                    username="Trading Bot",
                    icon_emoji=":bell:"
                )
            except SlackApiError as e:
                logger.warning(f"Failed to send summary message: {e}")

        # Send individual alerts
        for alert in alerts:
            if await self.send_alert(alert, channel):
                successful_sends += 1

        logger.info(
            f"Sent {successful_sends}/{len(alerts)} alerts to {channel}"
        )
        return successful_sends

    def _create_summary_message(self, alerts: List[Alert],
                                market_overview: Optional[Dict[str, Dict[str, float]]] = None) -> str:
        """Create a summary message for multiple alerts."""
        symbols = [alert.symbol for alert in alerts]
        unique_symbols = list(set(symbols))  # Remove duplicates

        message = ""

        # Add market overview if provided
        if market_overview:
            overview_parts = []
            for symbol, data in market_overview.items():
                price = data['price']
                change = data['change']

                # Format symbol name (remove ^ prefix for display)
                display_symbol = symbol.replace('^', '')

                if symbol in ['^VIX']:
                    # VIX doesn't use dollar sign
                    if change >= 0:
                        overview_parts.append(f"{display_symbol}: {price:.1f} (+{change:.1f}%)")
                    else:
                        overview_parts.append(f"{display_symbol}: {price:.1f} ({change:.1f}%)")
                else:
                    # ETFs use dollar sign
                    if change >= 0:
                        overview_parts.append(f"${display_symbol}: {price:.0f} (+{change:.1f}%)")
                    else:
                        overview_parts.append(f"${display_symbol}: {price:.0f} ({change:.1f}%)")

            market_line = "  |  ".join(overview_parts)
            message += f"{market_line}\n"

        message += f"🚨 Detected {len(alerts)} signals: {', '.join(unique_symbols)}\n"
        message += "───────────────────────"
        return message

    async def send_error_notification(
        self,
        error_message: str,
        channel: Optional[str] = None
    ) -> bool:
        """Send error notification to Slack."""
        channel = channel or self.default_channel

        try:
            message = f"❌ Trading Bot Error\n{error_message}"

            response = self.client.chat_postMessage(
                channel=channel,
                text=message,
                username="Trading Bot",
                icon_emoji=":x:"
            )

            return response["ok"]

        except SlackApiError as e:
            logger.error(f"Failed to send error notification: {e}")
            return False

    async def send_status_update(
        self,
        status_message: str,
        channel: Optional[str] = None,
        market_overview: Optional[Dict[str, Dict[str, float]]] = None
    ) -> bool:
        """Send status update to Slack."""
        channel = channel or self.default_channel

        try:
            message = f"ℹ️ {status_message}"

            # Add market overview if provided
            if market_overview:
                overview_parts = []
                for symbol, data in market_overview.items():
                    price = data['price']
                    change = data['change']

                    # Format symbol name (remove ^ prefix for display)
                    display_symbol = symbol.replace('^', '')

                    if symbol in ['^VIX']:
                        # VIX doesn't use dollar sign
                        if change >= 0:
                            overview_parts.append(f"{display_symbol}: {price:.1f} (+{change:.1f}%)")
                        else:
                            overview_parts.append(f"{display_symbol}: {price:.1f} ({change:.1f}%)")
                    else:
                        # ETFs use dollar sign
                        if change >= 0:
                            overview_parts.append(f"${display_symbol}: {price:.0f} (+{change:.1f}%)")
                        else:
                            overview_parts.append(f"${display_symbol}: {price:.0f} ({change:.1f}%)")

                market_line = "  |  ".join(overview_parts)
                message += f"\n{market_line}"

            response = self.client.chat_postMessage(
                channel=channel,
                text=message,
                username="Trading Bot",
                icon_emoji=":information_source:"
            )

            return response["ok"]

        except SlackApiError as e:
            logger.error(f"Failed to send status update: {e}")
            return False

    async def get_market_overview(self) -> Dict[str, Dict[str, float]]:
        """Get current prices and daily changes for market overview symbols."""
        # Import here to avoid circular imports
        from .market_data import YFinanceProvider
        import yfinance as yf

        provider = YFinanceProvider()
        market_data = {}

        for symbol in self.market_overview_symbols:
            try:
                # Get current price (now prioritizes extended hours data)
                current_price = await provider.get_current_price(symbol)

                # Get daily change by fetching detailed data (including extended hours)
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d", interval="1m", prepost=True)

                if len(hist) >= 2:
                    # Use the most recent close vs previous day's regular market close
                    # Get last close of previous day (regular market hours)
                    previous_day = hist.index.date[-2] if len(hist) > 1 else hist.index.date[-1]
                    previous_day_data = hist[hist.index.date == previous_day]

                    if not previous_day_data.empty:
                        previous_close = previous_day_data['Close'].iloc[-1]
                        daily_change = ((current_price - previous_close) / previous_close) * 100
                    else:
                        # Simple fallback
                        daily_change = 0.0
                else:
                    # Fallback if can't get historical data
                    daily_change = 0.0

                market_data[symbol] = {
                    'price': current_price,
                    'change': daily_change
                }

                logger.debug(f"Market overview for {symbol}: ${current_price:.2f} ({daily_change:+.2f}%)")

            except Exception as e:
                logger.warning(f"Failed to fetch data for {symbol}: {e}")
                continue

        return market_data
