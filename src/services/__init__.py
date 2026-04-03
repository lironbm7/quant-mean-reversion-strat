"""Trading services package."""

from .market_data import MarketDataService, MarketDataProvider, YFinanceProvider, IndicatorCalculator
from .alert_engine import AlertEngine
from .notification import SlackNotifier
from .discovery import IndicatorDiscoveryService, IndicatorAnalysis, StockRecommendation

__all__ = [
    # Market data services
    "MarketDataService",
    "MarketDataProvider",
    "YFinanceProvider",
    "IndicatorCalculator",
    # Alert services
    "AlertEngine",
    # Notification services
    "SlackNotifier",
    # Discovery services
    "IndicatorDiscoveryService",
    "IndicatorAnalysis",
    "StockRecommendation"
]
