"""Tests for service layer components."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd

from src.models.config import BarPeriod, IndicatorConfig, IndicatorType, TradingSettings
from src.models.market_data import MarketData
from src.models.alerts import Alert
from src.services.market_data import (
    YFinanceProvider,
    IndicatorCalculator,
    MarketDataService
)
from src.services.alert_engine import AlertEngine
from src.services.notification import SlackNotifier


class TestIndicatorCalculator:
    """Test IndicatorCalculator class."""

    def setup_method(self):
        """Setup test data."""
        # Create sample DataFrame
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        self.sample_df = pd.DataFrame({
            'Open': [100 + i for i in range(100)],
            'High': [105 + i for i in range(100)],
            'Low': [95 + i for i in range(100)],
            'Close': [102 + i for i in range(100)],
            'Volume': [1000000 + i * 10000 for i in range(100)]
        }, index=dates)

    def test_calculate_sma(self):
        """Test SMA calculation."""
        sma = IndicatorCalculator.calculate_sma(self.sample_df['Close'], 10)

        # Check that SMA is calculated
        assert not sma.empty
        assert sma.iloc[-1] > 0

        # Check that first 9 values are NaN (need 10 periods for SMA10)
        assert sma.iloc[:9].isna().all()
        assert not sma.iloc[9:].isna().any()

    def test_calculate_ema(self):
        """Test EMA calculation."""
        ema = IndicatorCalculator.calculate_ema(self.sample_df['Close'], 10)

        # Check that EMA is calculated
        assert not ema.empty
        assert ema.iloc[-1] > 0

        # EMA should have values from the beginning (after first value)
        assert not ema.iloc[1:].isna().any()

    def test_calculate_vwap(self):
        """Test VWAP calculation."""
        vwap = IndicatorCalculator.calculate_vwap(self.sample_df)

        # Check that VWAP is calculated
        assert not vwap.empty
        assert vwap.iloc[-1] > 0

    def test_calculate_vwap_no_volume(self):
        """Test VWAP calculation with no volume data."""
        df_no_volume = self.sample_df.drop('Volume', axis=1)
        vwap = IndicatorCalculator.calculate_vwap(df_no_volume)

        # Should fallback to typical price
        expected = (df_no_volume['High'] + df_no_volume['Low'] + df_no_volume['Close']) / 3
        pd.testing.assert_series_equal(vwap, expected)

    def test_calculate_indicator_sma50(self):
        """Test calculating SMA50 indicator."""
        value = IndicatorCalculator.calculate_indicator(
            self.sample_df, IndicatorType.SMA50
        )

        assert isinstance(value, float)
        assert value > 0

    def test_calculate_indicator_ema200(self):
        """Test calculating EMA200 indicator."""
        value = IndicatorCalculator.calculate_indicator(
            self.sample_df, IndicatorType.EMA200
        )

        assert isinstance(value, float)
        assert value > 0

    def test_calculate_indicator_arbitrary_period(self):
        """Arbitrary EMA periods (not just 50/100/200) compute a value."""
        ema40 = IndicatorCalculator.calculate_indicator(self.sample_df, "EMA40")
        ema45 = IndicatorCalculator.calculate_indicator(self.sample_df, "EMA45")
        assert isinstance(ema40, float) and ema40 > 0
        # Different periods should generally give different levels.
        assert ema40 != ema45

    def test_calculate_indicator_invalid(self):
        """Test error handling for invalid indicator type."""
        with pytest.raises(ValueError):
            IndicatorCalculator.calculate_indicator(
                self.sample_df, "INVALID"
            )


class TestYFinanceProvider:
    """Test YFinanceProvider class."""

    @pytest.mark.asyncio
    async def test_get_current_price_success(self):
        """Test successful price fetching."""
        provider = YFinanceProvider()

        with patch('yfinance.Ticker') as mock_ticker:
            # Mock ticker response
            mock_instance = MagicMock()
            mock_instance.info = {'currentPrice': 150.50}
            mock_ticker.return_value = mock_instance

            price = await provider.get_current_price('AAPL')
            assert price == 150.50

    @pytest.mark.asyncio
    async def test_get_current_price_fallback_to_history(self):
        """Test fallback to historical data when info is unavailable."""
        provider = YFinanceProvider()

        with patch('yfinance.Ticker') as mock_ticker:
            # Mock ticker with no price in info but has history
            mock_instance = MagicMock()
            mock_instance.info = {}

            # Create mock history DataFrame
            mock_history = pd.DataFrame({
                'Close': [150.25]
            })
            mock_instance.history.return_value = mock_history
            mock_ticker.return_value = mock_instance

            price = await provider.get_current_price('AAPL')
            assert price == 150.25

    @pytest.mark.asyncio
    async def test_get_current_price_error(self):
        """Test error handling when price cannot be fetched."""
        provider = YFinanceProvider()

        with patch('yfinance.Ticker') as mock_ticker:
            # Mock ticker that raises exception
            mock_ticker.side_effect = Exception("Network error")

            with pytest.raises(Exception):
                await provider.get_current_price('INVALID')

    @pytest.mark.asyncio
    async def test_get_historical_data_success(self):
        """Test successful historical data fetching."""
        provider = YFinanceProvider()

        with patch('yfinance.Ticker') as mock_ticker:
            # Mock ticker with historical data
            mock_instance = MagicMock()
            mock_history = pd.DataFrame({
                'Open': [100, 101, 102],
                'High': [105, 106, 107],
                'Low': [95, 96, 97],
                'Close': [102, 103, 104],
                'Volume': [1000000, 1100000, 1200000]
            })
            mock_instance.history.return_value = mock_history
            mock_ticker.return_value = mock_instance

            data = await provider.get_historical_data('AAPL', BarPeriod.ONE_DAY)
            assert not data.empty
            assert 'Close' in data.columns


class TestMarketDataService:
    """Test MarketDataService class."""

    def setup_method(self):
        """Setup test dependencies."""
        self.mock_provider = AsyncMock()
        self.service = MarketDataService(provider=self.mock_provider)

    @pytest.mark.asyncio
    async def test_get_market_data_success(self):
        """Test successful market data retrieval."""
        # Setup mocks
        self.mock_provider.get_current_price.return_value = 150.0

        # Mock historical data
        mock_df = pd.DataFrame({
            'Close': [140, 145, 150, 155, 160] * 50  # 250 data points
        })
        self.mock_provider.get_historical_data.return_value = mock_df

        # Create indicator config
        indicators = [
            IndicatorConfig(bar=BarPeriod.ONE_DAY, indicator=IndicatorType.SMA50)
        ]

        # Get market data
        result = await self.service.get_market_data('AAPL', indicators)

        # Verify result
        assert isinstance(result, MarketData)
        assert result.symbol == 'AAPL'
        assert result.current_price == 150.0
        assert 'SMA50_1d' in result.indicator_values

    @pytest.mark.asyncio
    async def test_get_market_data_with_override_price(self):
        """Test market data with price override."""
        # Mock historical data only (no price fetch needed)
        mock_df = pd.DataFrame({
            'Close': [140, 145, 150, 155, 160] * 50
        })
        self.mock_provider.get_historical_data.return_value = mock_df

        indicators = [
            IndicatorConfig(bar=BarPeriod.ONE_DAY, indicator=IndicatorType.SMA50)
        ]

        # Get market data with price override
        result = await self.service.get_market_data('AAPL', indicators, current_price=175.0)

        # Should use override price
        assert result.current_price == 175.0

        # Should not call get_current_price
        self.mock_provider.get_current_price.assert_not_called()


class TestAlertEngine:
    """Test AlertEngine class."""

    def setup_method(self):
        """Setup test data."""
        self.settings = TradingSettings(
            threshold_percentage=5.0,
            cooldown_hours=24
        )
        self.engine = AlertEngine(self.settings)

    @pytest.mark.asyncio
    async def test_detect_signals_within_threshold(self):
        """Test signal detection when price is within threshold."""
        # Create market data with price close to indicator
        market_data = MarketData(
            symbol='AAPL',
            current_price=95.0,  # 5% below 100
            timestamp=datetime.now()
        )
        market_data.add_indicator_value('SMA50_1d', 100.0)

        indicators = [
            IndicatorConfig(bar=BarPeriod.ONE_DAY, indicator=IndicatorType.SMA50)
        ]

        alerts = await self.engine.detect_signals(market_data, indicators)

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.symbol == 'AAPL'
        assert alert.current_price == 95.0
        assert alert.target_level == 100.0
        assert alert.percentage_difference == -5.0
        assert alert.indicator_name == 'SMA50'
        assert alert.bar_period == '1d'

    @pytest.mark.asyncio
    async def test_detect_signals_outside_threshold(self):
        """Test no signal when price is outside threshold."""
        # Create market data with price far from indicator
        market_data = MarketData(
            symbol='AAPL',
            current_price=90.0,  # 10% below 100 (outside 5% threshold)
            timestamp=datetime.now()
        )
        market_data.add_indicator_value('SMA50_1d', 100.0)

        indicators = [
            IndicatorConfig(bar=BarPeriod.ONE_DAY, indicator=IndicatorType.SMA50)
        ]

        alerts = await self.engine.detect_signals(market_data, indicators)

        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_cooldown_functionality(self):
        """Test that we can detect signals without cooldown interference."""
        market_data = MarketData(
            symbol='AAPL',
            current_price=95.0,
            timestamp=datetime.now()
        )
        market_data.add_indicator_value('SMA50_1d', 100.0)

        indicators = [
            IndicatorConfig(bar=BarPeriod.ONE_DAY, indicator=IndicatorType.SMA50)
        ]

        # Since we removed cooldowns, both calls should return alerts
        alerts1 = await self.engine.detect_signals(market_data, indicators)
        assert len(alerts1) == 1

        # Second call should also return alert (no cooldown)
        alerts2 = await self.engine.detect_signals(market_data, indicators)
        assert len(alerts2) == 1

    @pytest.mark.asyncio
    async def test_process_multiple_symbols(self):
        """Test processing multiple symbols."""
        # Create market data for multiple symbols
        market_data_dict = {
            'AAPL': MarketData(
                symbol='AAPL',
                current_price=95.0,
                timestamp=datetime.now(),
                indicator_values={'SMA50_1d': 100.0}
            ),
            'GOOGL': MarketData(
                symbol='GOOGL',
                current_price=190.0,  # 5% below 200
                timestamp=datetime.now(),
                indicator_values={'EMA200_1w': 200.0}
            )
        }

        symbols_indicators = {
            'AAPL': [IndicatorConfig(bar=BarPeriod.ONE_DAY, indicator=IndicatorType.SMA50)],
            'GOOGL': [IndicatorConfig(bar=BarPeriod.ONE_WEEK, indicator=IndicatorType.EMA200)]
        }

        alerts = await self.engine.process_multiple_symbols(market_data_dict, symbols_indicators)

        assert len(alerts) == 2
        symbols = [alert.symbol for alert in alerts]
        assert 'AAPL' in symbols
        assert 'GOOGL' in symbols


class TestSlackNotifier:
    """Test SlackNotifier class."""

    def setup_method(self):
        """Setup test dependencies."""
        with patch('src.services.notification.WebClient') as mock_webclient:
            mock_client = MagicMock()
            mock_client.auth_test.return_value = {'ok': True, 'user': 'test_bot'}
            mock_webclient.return_value = mock_client

            self.notifier = SlackNotifier('fake_token', '#test-channel')
            self.mock_client = mock_client

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """Test successful alert sending."""
        # Setup successful response
        self.mock_client.chat_postMessage.return_value = {'ok': True}

        # Create test alert
        alert = Alert(
            symbol='AAPL',
            current_price=95.0,
            target_level=100.0,
            percentage_difference=-5.0,
            indicator_name='SMA50',
            bar_period='1d',
            message='Test alert'
        )

        result = await self.notifier.send_alert(alert)

        assert result is True
        self.mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_failure(self):
        """Test alert sending failure."""
        # Setup failed response
        self.mock_client.chat_postMessage.return_value = {'ok': False}

        alert = Alert(
            symbol='AAPL',
            current_price=95.0,
            target_level=100.0,
            percentage_difference=-5.0,
            indicator_name='SMA50',
            bar_period='1d',
            message='Test alert'
        )

        result = await self.notifier.send_alert(alert)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_multiple_alerts(self):
        """Test sending multiple alerts."""
        # Setup successful responses
        self.mock_client.chat_postMessage.return_value = {'ok': True}

        alerts = [
            Alert(
                symbol='AAPL',
                current_price=95.0,
                target_level=100.0,
                percentage_difference=-5.0,
                indicator_name='SMA50',
                bar_period='1d',
                message='Test alert 1'
            ),
            Alert(
                symbol='GOOGL',
                current_price=190.0,
                target_level=200.0,
                percentage_difference=-5.0,
                indicator_name='EMA200',
                bar_period='1w',
                message='Test alert 2'
            )
        ]

        successful_sends = await self.notifier.send_multiple_alerts(alerts)

        assert successful_sends == 2
        # Should send summary + 2 individual alerts = 3 total calls
        assert self.mock_client.chat_postMessage.call_count == 3

    @pytest.mark.asyncio
    async def test_send_multiple_alerts_with_market_overview(self):
        """Test sending multiple alerts with market overview."""
        # Setup successful responses
        self.mock_client.chat_postMessage.return_value = {'ok': True}

        alerts = [
            Alert(
                symbol='AAPL',
                current_price=95.0,
                target_level=100.0,
                percentage_difference=-5.0,
                indicator_name='SMA50',
                bar_period='1d',
                message='Test alert 1'
            ),
            Alert(
                symbol='GOOGL',
                current_price=190.0,
                target_level=200.0,
                percentage_difference=-5.0,
                indicator_name='EMA200',
                bar_period='1w',
                message='Test alert 2'
            )
        ]

        market_overview = {
            'SPY': {'price': 450.0, 'change': 1.2},
            'QQQ': {'price': 380.0, 'change': -0.5},
            'VIX': {'price': 18.5, 'change': 2.1},
            'DJI': {'price': 34500.0, 'change': 0.8}
        }

        successful_sends = await self.notifier.send_multiple_alerts(alerts, market_overview=market_overview)

        assert successful_sends == 2
        # Should send summary + 2 individual alerts = 3 total calls
        assert self.mock_client.chat_postMessage.call_count == 3

        # Check that the summary message contains market overview
        summary_call = self.mock_client.chat_postMessage.call_args_list[0]
        summary_text = summary_call[1]['text']
        assert '$SPY: 450' in summary_text
        assert '$QQQ: 380' in summary_text
        assert 'VIX: 18' in summary_text  # VIX doesn't have $ sign
        assert '$DJI: 34500' in summary_text
        # Check that daily changes are included
        assert '(+1.2%)' in summary_text or '(-0.5%)' in summary_text

    @pytest.mark.asyncio
    async def test_send_status_update_with_market_overview(self):
        """Test sending status update with market overview."""
        # Setup successful response
        self.mock_client.chat_postMessage.return_value = {'ok': True}

        market_overview = {
            'SPY': {'price': 450.0, 'change': 1.2},
            'QQQ': {'price': 380.0, 'change': -0.5},
            'VIX': {'price': 18.5, 'change': 2.1}
        }

        result = await self.notifier.send_status_update(
            "Test status message",
            market_overview=market_overview
        )

        assert result is True
        self.mock_client.chat_postMessage.assert_called_once()

        # Check that the message contains market overview
        call_args = self.mock_client.chat_postMessage.call_args
        message_text = call_args[1]['text']
        assert 'Test status message' in message_text
        assert '$SPY: 450' in message_text
        assert '$QQQ: 380' in message_text
        assert 'VIX: 18' in message_text
        # Check that daily changes are included
        assert '(+1.2%)' in message_text or '(-0.5%)' in message_text

    @pytest.mark.asyncio
    async def test_get_market_overview(self):
        """Test getting market overview data."""
        with patch('src.services.market_data.YFinanceProvider') as mock_provider_class:
            # Setup mock provider
            mock_provider = AsyncMock()
            mock_provider.get_current_price.side_effect = [450.0, 380.0, 18.5, 34500.0]
            mock_provider_class.return_value = mock_provider

            # Mock yfinance Ticker for historical data
            with patch('yfinance.Ticker') as mock_ticker_class:
                mock_ticker = MagicMock()
                mock_history = MagicMock()
                mock_history.__len__ = MagicMock(return_value=2)
                mock_history.__getitem__ = MagicMock(
                    side_effect=lambda key: MagicMock(
                        iloc=MagicMock(
                            __getitem__=lambda self, idx: [
                                440.0, 450.0][idx] if key == 'Close' else None)))
                mock_ticker.history.return_value = mock_history
                mock_ticker_class.return_value = mock_ticker

                market_overview = await self.notifier.get_market_overview()

                # Should fetch prices for all overview symbols
                assert len(market_overview) == 4
                assert market_overview['SPY']['price'] == 450.0
                assert market_overview['QQQ']['price'] == 380.0
                assert market_overview['^VIX']['price'] == 18.5
                assert market_overview['^DJI']['price'] == 34500.0
                # Check that daily changes are calculated
                assert 'change' in market_overview['SPY']

    @pytest.mark.asyncio
    async def test_get_market_overview_with_failures(self):
        """Test getting market overview data with some failures."""
        with patch('src.services.market_data.YFinanceProvider') as mock_provider_class:
            # Setup mock provider with some failures
            mock_provider = AsyncMock()
            mock_provider.get_current_price.side_effect = [
                450.0,  # SPY success
                Exception("Network error"),  # QQQ fails
                18.5,  # VIX success
                34500.0  # DJI success
            ]
            mock_provider_class.return_value = mock_provider

            # Mock yfinance Ticker for historical data
            with patch('yfinance.Ticker') as mock_ticker_class:
                mock_ticker = MagicMock()
                mock_history = MagicMock()
                mock_history.__len__ = MagicMock(return_value=2)
                mock_history.__getitem__ = MagicMock(
                    side_effect=lambda key: MagicMock(
                        iloc=MagicMock(
                            __getitem__=lambda self, idx: [
                                440.0, 450.0][idx] if key == 'Close' else None)))
                mock_ticker.history.return_value = mock_history
                mock_ticker_class.return_value = mock_ticker

                market_overview = await self.notifier.get_market_overview()

                # Should only have successful fetches
                assert len(market_overview) == 3
                assert market_overview['SPY']['price'] == 450.0
                assert market_overview['^VIX']['price'] == 18.5
                assert market_overview['^DJI']['price'] == 34500.0
                assert 'QQQ' not in market_overview

    def test_create_summary_message_with_market_overview(self):
        """Test creating summary message with market overview."""
        alerts = [
            Alert(
                symbol='AAPL',
                current_price=95.0,
                target_level=100.0,
                percentage_difference=-5.0,
                indicator_name='SMA50',
                bar_period='1d',
                message='Test alert 1'
            ),
            Alert(
                symbol='GOOGL',
                current_price=190.0,
                target_level=200.0,
                percentage_difference=-5.0,
                indicator_name='EMA200',
                bar_period='1w',
                message='Test alert 2'
            )
        ]

        market_overview = {
            'SPY': {'price': 450.0, 'change': 1.2},
            'QQQ': {'price': 380.0, 'change': -0.5},
            'VIX': {'price': 18.5, 'change': 2.1},
            'DJI': {'price': 34500.0, 'change': 0.8}
        }

        message = self.notifier._create_summary_message(alerts, market_overview)

        # Should contain the detected signals
        assert '🚨 Detected 2 signals: AAPL, GOOGL' in message or '🚨 Detected 2 signals: GOOGL, AAPL' in message

        # Should contain market overview
        assert '$SPY: 450' in message
        assert '$QQQ: 380' in message
        assert 'VIX: 18' in message  # VIX without $ sign
        assert '$DJI: 34500' in message
        # Should contain daily changes
        assert '(+1.2%)' in message or '(-0.5%)' in message

        # Should have separator
        assert '───────────────────────' in message

    def test_create_summary_message_without_market_overview(self):
        """Test creating summary message without market overview."""
        alerts = [
            Alert(
                symbol='AAPL',
                current_price=95.0,
                target_level=100.0,
                percentage_difference=-5.0,
                indicator_name='SMA50',
                bar_period='1d',
                message='Test alert 1'
            )
        ]

        message = self.notifier._create_summary_message(alerts, None)

        # Should contain the detected signals
        assert '🚨 Detected 1 signals: AAPL' in message

        # Should not contain market prices
        assert '$SPY:' not in message
        assert '$QQQ:' not in message
        assert 'VIX:' not in message

        # Should have separator
        assert '───────────────────────' in message

    @pytest.mark.asyncio
    async def test_has_recent_alert_for_symbol_indicator_found(self):
        """Test detecting recent alerts in channel history."""
        # Mock successful channel history response with matching message
        self.mock_client.conversations_history.return_value = {
            'ok': True,
            'messages': [
                {
                    'text': '📈 $AAPL\nCurrent Price: $145.00\nEMA200 (1w): $150.00\nDistance: -3.3%\n',
                    'username': 'Trading Bot',
                    'ts': '1640995200'  # Recent timestamp
                }
            ]
        }

        result = await self.notifier.has_recent_alert_for_symbol_indicator('AAPL', 'EMA200')

        assert result is True
        self.mock_client.conversations_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_has_recent_alert_for_symbol_indicator_not_found(self):
        """Test when no recent alerts found."""
        # Mock successful response with no matching messages
        self.mock_client.conversations_history.return_value = {
            'ok': True,
            'messages': [
                {
                    'text': '📈 $GOOGL\nCurrent Price: $190.00\nSMA50 (1d): $200.00\nDistance: -5.0%\n',
                    'username': 'Trading Bot',
                    'ts': '1640995200'
                }
            ]
        }

        result = await self.notifier.has_recent_alert_for_symbol_indicator('AAPL', 'EMA200')

        assert result is False

    @pytest.mark.asyncio
    async def test_has_recent_alert_for_symbol_indicator_api_error(self):
        """Test handling API errors gracefully."""
        # Mock API error
        self.mock_client.conversations_history.return_value = {
            'ok': False,
            'error': 'channel_not_found'
        }

        result = await self.notifier.has_recent_alert_for_symbol_indicator('AAPL', 'EMA200')

        # Should fail open (return False to allow sending)
        assert result is False
