"""Discovery service for finding statistically reliable indicators."""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from ..models.config import BarPeriod, IndicatorType
from ..services.market_data import MarketDataService, IndicatorCalculator


@dataclass
class IndicatorAnalysis:
    """Results of indicator analysis for a stock."""

    symbol: str
    indicator: IndicatorType
    timeframe: BarPeriod
    total_tests: int
    successful_bounces: int
    success_rate: float
    avg_bounce_percentage: float
    avg_days_to_bounce: float
    false_breakdowns: int
    max_drawdown: float
    confidence_score: float
    sample_period_days: int


@dataclass
class StockRecommendation:
    """Recommendation for a stock's best indicators."""

    symbol: str
    best_indicators: List[IndicatorAnalysis]
    overall_confidence: float
    recommended_threshold: float
    notes: str


class IndicatorDiscoveryService:
    """Service for discovering statistically reliable indicators."""

    def __init__(self, market_data_service: Optional[MarketDataService] = None):
        """Initialize discovery service."""
        self.market_data_service = market_data_service or MarketDataService()
        self.calculator = IndicatorCalculator()

    async def analyze_stock(
        self,
        symbol: str,
        analysis_period_days: int = 1095,  # 3 years
        bounce_threshold: float = 5.0,  # Within 5% to be considered "touching"
        min_bounce_percentage: float = 2.0,  # Minimum 2% bounce to count as success
        max_days_for_bounce: int = 10  # Must bounce within 10 days
    ) -> List[IndicatorAnalysis]:
        """Analyze a single stock for indicator reliability."""
        logger.info(f"🔍 Analyzing {symbol} for indicator reliability...")

        results = []

        # Test different indicators and timeframes
        test_cases = [
            (IndicatorType.EMA200, BarPeriod.ONE_WEEK),
            (IndicatorType.EMA200, BarPeriod.ONE_DAY),
            (IndicatorType.EMA50, BarPeriod.ONE_WEEK),
            (IndicatorType.EMA50, BarPeriod.ONE_DAY),
            (IndicatorType.SMA200, BarPeriod.ONE_WEEK),
            (IndicatorType.SMA200, BarPeriod.ONE_DAY),
            (IndicatorType.SMA50, BarPeriod.ONE_WEEK),
            (IndicatorType.SMA50, BarPeriod.ONE_DAY),
        ]

        for indicator_type, timeframe in test_cases:
            try:
                analysis = await self._analyze_indicator(
                    symbol=symbol,
                    indicator_type=indicator_type,
                    timeframe=timeframe,
                    analysis_period_days=analysis_period_days,
                    bounce_threshold=bounce_threshold,
                    min_bounce_percentage=min_bounce_percentage,
                    max_days_for_bounce=max_days_for_bounce
                )
                if analysis:
                    results.append(analysis)

            except Exception as e:
                logger.warning(f"Failed to analyze {indicator_type} {timeframe} for {symbol}: {e}")
                continue

        # Sort by confidence score
        results.sort(key=lambda x: x.confidence_score, reverse=True)

        logger.info(f"✅ Completed analysis for {symbol}: {len(results)} indicators analyzed")
        return results

    async def _analyze_indicator(
        self,
        symbol: str,
        indicator_type: IndicatorType,
        timeframe: BarPeriod,
        analysis_period_days: int,
        bounce_threshold: float,
        min_bounce_percentage: float,
        max_days_for_bounce: int
    ) -> Optional[IndicatorAnalysis]:
        """Analyze a specific indicator for a stock."""
        try:
            # Get historical data
            historical_data = await self.market_data_service.provider.get_historical_data(
                symbol, timeframe, days=analysis_period_days
            )

            if len(historical_data) < 200:
                logger.warning(f"Insufficient data for {symbol} {indicator_type} {timeframe}")
                return None

            # Calculate the indicator
            if indicator_type == IndicatorType.EMA200:
                indicator_series = self.calculator.calculate_ema(historical_data['Close'], 200)
            elif indicator_type == IndicatorType.EMA100:
                indicator_series = self.calculator.calculate_ema(historical_data['Close'], 100)
            elif indicator_type == IndicatorType.EMA50:
                indicator_series = self.calculator.calculate_ema(historical_data['Close'], 50)
            elif indicator_type == IndicatorType.SMA200:
                indicator_series = self.calculator.calculate_sma(historical_data['Close'], 200)
            elif indicator_type == IndicatorType.SMA50:
                indicator_series = self.calculator.calculate_sma(historical_data['Close'], 50)
            else:
                logger.warning(f"Unsupported indicator type: {indicator_type}")
                return None

            # Find touch points and analyze bounces
            touch_points = self._find_touch_points(
                historical_data['Close'],
                indicator_series,
                bounce_threshold
            )

            if len(touch_points) < 5:  # Need at least 5 samples
                logger.debug(
                    f"Insufficient touch points for {symbol} {indicator_type} {timeframe}: {len(touch_points)}")
                return None

            # Analyze each touch point
            bounce_results = []
            for touch_idx in touch_points:
                result = self._analyze_bounce(
                    historical_data,
                    touch_idx,
                    min_bounce_percentage,
                    max_days_for_bounce
                )
                bounce_results.append(result)

            # Calculate statistics
            successful_bounces = sum(1 for r in bounce_results if r['success'])
            success_rate = successful_bounces / len(bounce_results)

            avg_bounce_percentage = np.mean([
                r['bounce_percentage'] for r in bounce_results if r['success']
            ]) if successful_bounces > 0 else 0.0

            avg_days_to_bounce = np.mean([
                r['days_to_bounce'] for r in bounce_results if r['success']
            ]) if successful_bounces > 0 else 0.0

            false_breakdowns = sum(1 for r in bounce_results if not r['success'])

            max_drawdown = max([
                r['max_drawdown'] for r in bounce_results
            ]) if bounce_results else 0.0

            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(
                success_rate=success_rate,
                total_tests=len(bounce_results),
                avg_bounce_percentage=avg_bounce_percentage,
                max_drawdown=max_drawdown
            )

            return IndicatorAnalysis(
                symbol=symbol,
                indicator=indicator_type,
                timeframe=timeframe,
                total_tests=len(bounce_results),
                successful_bounces=successful_bounces,
                success_rate=success_rate,
                avg_bounce_percentage=avg_bounce_percentage,
                avg_days_to_bounce=avg_days_to_bounce,
                false_breakdowns=false_breakdowns,
                max_drawdown=max_drawdown,
                confidence_score=confidence_score,
                sample_period_days=analysis_period_days
            )

        except Exception as e:
            logger.error(f"Error analyzing {symbol} {indicator_type} {timeframe}: {e}")
            return None

    def _find_touch_points(
        self,
        price_series: pd.Series,
        indicator_series: pd.Series,
        threshold: float
    ) -> List[int]:
        """Find points where price touched the indicator level."""
        touch_points = []

        # Calculate percentage difference from indicator
        pct_diff = ((price_series - indicator_series) / indicator_series) * 100

        # Find where price is within threshold of indicator
        within_threshold = abs(pct_diff) <= threshold

        # Find the start of each touch sequence (to avoid counting consecutive days as multiple touches)
        touch_starts = []
        in_touch = False

        for i, is_touching in enumerate(within_threshold):
            if is_touching and not in_touch:
                touch_starts.append(i)
                in_touch = True
            elif not is_touching:
                in_touch = False

        # Filter touch points to ensure we have enough future data to analyze bounces
        min_future_days = 15  # Need at least 15 days of future data
        for touch_idx in touch_starts:
            if touch_idx < len(price_series) - min_future_days:
                touch_points.append(touch_idx)

        return touch_points

    def _analyze_bounce(
        self,
        historical_data: pd.DataFrame,
        touch_idx: int,
        min_bounce_percentage: float,
        max_days_for_bounce: int
    ) -> Dict:
        """Analyze if a touch point resulted in a bounce."""
        touch_price = historical_data['Close'].iloc[touch_idx]

        # Look at future prices to see if it bounced
        future_end_idx = min(touch_idx + max_days_for_bounce, len(historical_data) - 1)
        future_prices = historical_data['Close'].iloc[touch_idx + 1:future_end_idx + 1]

        if len(future_prices) == 0:
            return {
                'success': False,
                'bounce_percentage': 0.0,
                'days_to_bounce': max_days_for_bounce,
                'max_drawdown': 0.0
            }

        # Calculate bounce metrics
        max_future_price = future_prices.max()
        min_future_price = future_prices.min()

        bounce_percentage = ((max_future_price - touch_price) / touch_price) * 100
        max_drawdown = ((min_future_price - touch_price) / touch_price) * 100

        # Find days to reach peak - handle both DatetimeIndex and integer index
        peak_idx = future_prices.idxmax()
        try:
            if hasattr(future_prices.index, 'get_loc'):
                days_to_bounce = future_prices.index.get_loc(peak_idx) + 1
            else:
                # For simple integer index, calculate position difference
                days_to_bounce = peak_idx - (touch_idx + 1) + 1
        except (KeyError, ValueError):
            # Fallback: find position of max value
            days_to_bounce = future_prices.tolist().index(max_future_price) + 1

        # Success if bounced at least min_bounce_percentage
        success = bounce_percentage >= min_bounce_percentage

        return {
            'success': success,
            'bounce_percentage': bounce_percentage,
            'days_to_bounce': days_to_bounce,
            'max_drawdown': abs(max_drawdown)  # Make positive for readability
        }

    def _calculate_confidence_score(
        self,
        success_rate: float,
        total_tests: int,
        avg_bounce_percentage: float,
        max_drawdown: float
    ) -> float:
        """Calculate confidence score for an indicator."""
        # Base score from success rate
        base_score = success_rate * 100

        # Bonus for sample size (more tests = more confidence)
        sample_bonus = min(total_tests / 20 * 10, 20)  # Up to 20 points for 20+ tests

        # Bonus for strong bounces
        bounce_bonus = min(avg_bounce_percentage * 2, 20)  # Up to 20 points

        # Penalty for high drawdown risk
        drawdown_penalty = min(max_drawdown, 30)  # Up to 30 point penalty

        confidence_score = base_score + sample_bonus + bounce_bonus - drawdown_penalty

        # Cap between 0 and 100
        return max(0, min(100, confidence_score))

    async def discover_best_indicators(
        self,
        symbols: List[str],
        min_confidence: float = 50.0,
        max_concurrent: int = 3  # Limit concurrent requests to avoid rate limiting
    ) -> Dict[str, StockRecommendation]:
        """Discover best indicators for a list of stocks."""
        logger.info(f"🚀 Starting indicator discovery for {len(symbols)} stocks...")

        recommendations = {}

        # Process stocks in batches to avoid overwhelming the API
        for i in range(0, len(symbols), max_concurrent):
            batch = symbols[i:i + max_concurrent]
            logger.info(f"Processing batch {i // max_concurrent + 1}: {batch}")

            # Process batch concurrently
            tasks = [self.analyze_stock(symbol) for symbol in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for symbol, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to analyze {symbol}: {result}")
                    continue

                # Filter by minimum confidence and get top recommendations
                high_confidence_indicators = [
                    analysis for analysis in result
                    if analysis.confidence_score >= min_confidence
                ]

                if high_confidence_indicators:
                    # Take top 3 indicators
                    best_indicators = high_confidence_indicators[:3]

                    # Calculate overall confidence
                    overall_confidence = np.mean([ind.confidence_score for ind in best_indicators])

                    # Recommend threshold based on historical performance
                    recommended_threshold = self._recommend_threshold(best_indicators)

                    # Generate notes
                    notes = self._generate_recommendation_notes(best_indicators)

                    recommendations[symbol] = StockRecommendation(
                        symbol=symbol,
                        best_indicators=best_indicators,
                        overall_confidence=overall_confidence,
                        recommended_threshold=recommended_threshold,
                        notes=notes
                    )

                    logger.info(f"✅ {symbol}: {len(best_indicators)} reliable indicators found")
                else:
                    logger.warning(f"⚠️ {symbol}: No indicators meet minimum confidence threshold")

        logger.info(f"🎯 Discovery complete: {len(recommendations)} stocks with reliable indicators")
        return recommendations

    def _recommend_threshold(self, indicators: List[IndicatorAnalysis]) -> float:
        """Recommend alert threshold based on indicator performance."""
        # Use the average bounce percentage as a guide, but be conservative
        avg_bounces = [ind.avg_bounce_percentage for ind in indicators]

        if avg_bounces:
            # Recommend threshold that's about 60% of average bounce
            # This gives good signal without being too noisy
            recommended = np.mean(avg_bounces) * 0.6
            return max(2.0, min(8.0, recommended))  # Clamp between 2% and 8%

        return 5.0  # Default fallback

    def _generate_recommendation_notes(self, indicators: List[IndicatorAnalysis]) -> str:
        """Generate human-readable notes about the recommendations."""
        if not indicators:
            return "No reliable indicators found."

        best = indicators[0]
        notes = []

        # Convert enums to user-friendly strings
        indicator_str = best.indicator.value  # Use the enum value
        timeframe_str = best.timeframe.value  # Use the enum value

        notes.append(f"Best indicator: {indicator_str} ({timeframe_str})")
        notes.append(f"Success rate: {best.success_rate:.1%}")
        notes.append(f"Avg bounce: {best.avg_bounce_percentage:.1f}%")
        notes.append(f"Based on {best.total_tests} historical tests")

        if best.success_rate >= 0.7:
            notes.append("High reliability - strong historical performance")
        elif best.success_rate >= 0.5:
            notes.append("Moderate reliability - decent track record")
        else:
            notes.append("Lower reliability - use with caution")

        return " | ".join(notes)

    def format_discovery_report(self, recommendations: Dict[str, StockRecommendation]) -> str:
        """Format discovery results into a readable report."""
        if not recommendations:
            return "❌ No reliable indicators discovered for any stocks."

        report_lines = [
            "📊 INDICATOR DISCOVERY REPORT",
            "=" * 50,
            f"Analyzed stocks: Found reliable indicators for {len(recommendations)} stocks",
            "",
        ]

        # Sort by overall confidence
        sorted_recommendations = sorted(
            recommendations.items(),
            key=lambda x: x[1].overall_confidence,
            reverse=True
        )

        for symbol, rec in sorted_recommendations:
            report_lines.extend([
                f"🎯 {symbol} (Confidence: {rec.overall_confidence:.1f}%)",
                f"   Recommended threshold: {rec.recommended_threshold:.1f}%",
                f"   Notes: {rec.notes}",
                ""
            ])

            for i, indicator in enumerate(rec.best_indicators, 1):
                report_lines.append(
                    f"   {i}. {indicator.indicator} ({indicator.timeframe}): "
                    f"{indicator.success_rate:.1%} success, "
                    f"{indicator.avg_bounce_percentage:.1f}% avg bounce, "
                    f"{indicator.total_tests} tests"
                )

            report_lines.append("")

        report_lines.extend([
            "💡 RECOMMENDATIONS:",
            "- Add high-confidence indicators to your config/symbols.json",
            "- Use recommended thresholds for optimal signal quality",
            "- Focus on stocks with 60%+ overall confidence",
            "- Monitor performance and adjust thresholds as needed"
        ])

        return "\n".join(report_lines)
