"""Market data service with YFinance integration and technical indicators."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from loguru import logger

from ..models.config import BarPeriod, IndicatorConfig, IndicatorType
from ..models.market_data import MarketData


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        pass

    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        period: BarPeriod,
        days: int = 252
    ) -> pd.DataFrame:
        """Get historical price data."""
        pass


class YFinanceProvider(MarketDataProvider):
    """YFinance implementation of market data provider."""

    def __init__(self):
        """Initialize YFinance provider."""
        self._session = None

    async def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        try:
            ticker = yf.Ticker(symbol)

            # First try to get the most recent price from history (including extended hours)
            # This ensures we get premarket/after-hours data when available
            hist = ticker.history(period="1d", interval="1m", prepost=True)
            if not hist.empty:
                latest_price = float(hist['Close'].iloc[-1])
                logger.debug(f"Got latest price for {symbol} from history: ${latest_price:.2f}")
                return latest_price

            # Fallback to info fields if history is unavailable
            info = ticker.info
            price_fields = ['currentPrice', 'regularMarketPrice', 'previousClose']
            for field in price_fields:
                if field in info and info[field]:
                    logger.debug(f"Got price for {symbol} from {field}: ${info[field]:.2f}")
                    return float(info[field])

            raise ValueError(f"No price data available for {symbol}")

        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            raise

    # Map BarPeriod -> (yfinance interval, yfinance period, optional
    # pandas-resample target). Yahoo only allows "max" on daily+ bars
    # and caps intraday data at 730 days; "4h" is not a native interval
    # so we fetch 1h and resample.
    _PERIOD_SPEC = {
        BarPeriod.ONE_MINUTE:      ("1m",  "7d",   None),
        BarPeriod.FIVE_MINUTES:    ("5m",  "60d",  None),
        BarPeriod.FIFTEEN_MINUTES: ("15m", "60d",  None),
        BarPeriod.THIRTY_MINUTES:  ("30m", "60d",  None),
        BarPeriod.ONE_HOUR:        ("1h",  "730d", None),
        BarPeriod.FOUR_HOURS:      ("1h",  "730d", "4h"),
        BarPeriod.ONE_DAY:         ("1d",  "max",  None),
        BarPeriod.ONE_WEEK:        ("1wk", "max",  None),
        BarPeriod.ONE_MONTH:       ("1mo", "max",  None),
    }

    async def get_historical_data(
        self,
        symbol: str,
        period: BarPeriod,
        days: int = 252
    ) -> pd.DataFrame:
        """Get historical price data."""
        try:
            ticker = yf.Ticker(symbol)

            interval, yf_period, resample_to = self._PERIOD_SPEC.get(
                period, ("1d", "max", None)
            )

            # Use auto_adjust=False for more accurate historical calculations
            # Include extended hours data (prepost=True) for pre-market and after-hours
            hist = ticker.history(
                period=yf_period,
                interval=interval,
                auto_adjust=False,
                prepost=True
            )

            if hist.empty:
                raise ValueError(f"No historical data available for {symbol}")

            if resample_to is not None:
                hist = self._resample_ohlcv(hist, resample_to)
                if hist.empty:
                    raise ValueError(f"No historical data available for {symbol}")

            return hist

        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            raise

    @staticmethod
    def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Resample OHLCV bars to a coarser interval (e.g. 1h -> 4h)."""
        agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
        if "Volume" in df.columns:
            agg["Volume"] = "sum"
        return df.resample(rule).agg(agg).dropna(subset=["Close"])


class IndicatorCalculator:
    """Technical indicator calculations."""

    @staticmethod
    def calculate_sma(data: pd.Series, window: int) -> pd.Series:
        """Calculate Simple Moving Average."""
        return data.rolling(window=window).mean()

    @staticmethod
    def calculate_ema(data: pd.Series, window: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return data.ewm(span=window, adjust=False).mean()

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """Calculate Volume Weighted Average Price."""
        if 'Volume' not in df.columns or df['Volume'].sum() == 0:
            # Fallback to simple average if no volume data
            return (df['High'] + df['Low'] + df['Close']) / 3

        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        return (typical_price * df['Volume']).cumsum() / df['Volume'].cumsum()

    @classmethod
    def calculate_indicator(
        cls,
        df: pd.DataFrame,
        indicator_type: IndicatorType
    ) -> float:
        """Calculate indicator value and return the latest value."""
        try:
            if indicator_type == IndicatorType.SMA50:
                series = cls.calculate_sma(df['Close'], 50)
            elif indicator_type == IndicatorType.SMA200:
                series = cls.calculate_sma(df['Close'], 200)
            elif indicator_type == IndicatorType.EMA50:
                series = cls.calculate_ema(df['Close'], 50)
            elif indicator_type == IndicatorType.EMA100:
                series = cls.calculate_ema(df['Close'], 100)
            elif indicator_type == IndicatorType.EMA200:
                series = cls.calculate_ema(df['Close'], 200)
            elif indicator_type == IndicatorType.VWAP:
                series = cls.calculate_vwap(df)
            else:
                raise ValueError(f"Unsupported indicator type: {indicator_type}")

            # Return the latest non-NaN value
            latest_value = series.dropna().iloc[-1] if not series.dropna().empty else None
            if latest_value is None:
                raise ValueError(f"Could not calculate {indicator_type}")

            return float(latest_value)

        except Exception as e:
            logger.error(f"Error calculating {indicator_type}: {e}")
            raise


class MarketDataService:
    """Service for fetching market data and calculating indicators."""

    def __init__(self, provider: Optional[MarketDataProvider] = None):
        """Initialize market data service."""
        self.provider = provider or YFinanceProvider()
        self.calculator = IndicatorCalculator()

    async def get_market_data(
        self,
        symbol: str,
        indicators: List[IndicatorConfig],
        current_price: Optional[float] = None
    ) -> MarketData:
        """Get market data with calculated indicators."""
        try:
            # Get current price
            if current_price is None:
                current_price = await self.provider.get_current_price(symbol)

            # Create market data object
            market_data = MarketData(
                symbol=symbol,
                current_price=current_price,
                timestamp=datetime.now()
            )

            # Calculate indicators
            for indicator_config in indicators:
                indicator_value = await self._calculate_indicator(
                    symbol, indicator_config
                )

                # Create indicator key
                indicator_key = f"{indicator_config.indicator}_{indicator_config.bar}"
                market_data.add_indicator_value(indicator_key, indicator_value)

            logger.info(
                f"Fetched market data for {symbol}: "
                f"price=${current_price:.2f}, "
                f"indicators={len(market_data.indicator_values)}"
            )

            return market_data

        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {e}")
            raise

    async def _calculate_indicator(
        self,
        symbol: str,
        indicator_config: IndicatorConfig
    ) -> float:
        """Calculate a single indicator value."""
        try:
            # Get historical data
            historical_data = await self.provider.get_historical_data(
                symbol, indicator_config.bar
            )

            # Calculate indicator
            indicator_value = self.calculator.calculate_indicator(
                historical_data, indicator_config.indicator
            )

            logger.debug(
                f"Calculated {indicator_config.indicator} "
                f"({indicator_config.bar}) for {symbol}: {indicator_value:.2f}"
            )

            return indicator_value

        except Exception as e:
            logger.error(
                f"Error calculating {indicator_config.indicator} "
                f"for {symbol}: {e}"
            )
            raise

    async def get_multiple_market_data(
        self,
        symbols_config: Dict[str, List[IndicatorConfig]]
    ) -> Dict[str, MarketData]:
        """Get market data for multiple symbols."""
        results = {}

        for symbol, indicators in symbols_config.items():
            try:
                market_data = await self.get_market_data(symbol, indicators)
                results[symbol] = market_data
            except Exception as e:
                logger.error(f"Failed to fetch data for {symbol}: {e}")
                # Continue with other symbols
                continue

        return results
