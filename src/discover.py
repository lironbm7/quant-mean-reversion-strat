"""Standalone script for discovering reliable indicators for stocks."""

from src.services.discovery import IndicatorDiscoveryService
from loguru import logger
import asyncio
import sys
import json
from pathlib import Path
from typing import List

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

# Import loguru directly instead of using utils


def setup_basic_logging(level: str = "INFO"):
    """Setup basic logging for discovery script."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        colorize=True
    )


# Predefined stock lists
MAG7_STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"]

TECH_CYBER_STOCKS = [
    # MAG7
    *MAG7_STOCKS,
    # Additional tech giants
    "PANW", "CRWD", "CRM", "AVGO", "TSM", "DDOG", "AMD", "DIS", "NFLX",
    "ZS", "PLTR", "RDDT",
    # Market ETFs
    "SPY", "QQQ", "IBIT",
    # Traditional tech
    "BA"
]

CUSTOM_PORTFOLIO = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",  # MAG7
    "PANW", "CRWD", "CRM", "SPY", "QQQ"  # Key positions
]


async def discover_indicators(
    stock_list: List[str],
    min_confidence: float = 50.0,
    output_file: str = None
) -> None:
    """Run indicator discovery for a list of stocks."""

    # Setup logging
    setup_basic_logging(level="INFO")

    logger.info(f"🚀 Starting indicator discovery for {len(stock_list)} stocks")
    logger.info(f"Stock list: {', '.join(stock_list)}")

    # Initialize discovery service
    discovery_service = IndicatorDiscoveryService()

    try:
        # Run discovery
        recommendations = await discovery_service.discover_best_indicators(
            symbols=stock_list,
            min_confidence=min_confidence,
            max_concurrent=2  # Conservative to avoid rate limits
        )

        # Generate report
        report = discovery_service.format_discovery_report(recommendations)

        # Output results
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)

        # Save to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                f.write(report)

            logger.info(f"📄 Report saved to: {output_path}")

        # Generate configuration suggestions
        if recommendations:
            print("\n🔧 CONFIGURATION SUGGESTIONS:")
            print("Add these to your config/symbols.json:")
            print()

            # Build JSON structure
            symbols_config = []
            for symbol, rec in recommendations.items():
                if rec.overall_confidence >= 60:  # Only suggest high-confidence stocks
                    # Show top 2 indicators with 70%+ confidence
                    indicators_config = []
                    for indicator in rec.best_indicators[:2]:  # Top 2 max
                        if indicator.confidence_score >= 70:  # High confidence only
                            indicators_config.append({
                                "bar": indicator.timeframe.value,
                                "indicator": indicator.indicator.value
                            })

                    if indicators_config:  # Only add if we have high-confidence indicators
                        symbols_config.append({
                            "symbol": symbol,
                            "indicators": indicators_config
                        })

            # Output properly formatted JSON
            config_json = json.dumps({"symbols": symbols_config}, indent=2)
            print(config_json)

            print("\nAlso consider updating your threshold_percentage to the recommended values!")

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        sys.exit(1)


async def main():
    """Main entry point for discovery script."""
    import argparse

    parser = argparse.ArgumentParser(description="Discover reliable indicators for stocks")
    parser.add_argument(
        "--stocks",
        choices=["mag7", "tech", "custom", "list"],
        default="custom",
        help="Predefined stock list to analyze"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Custom list of symbols (use with --stocks list)"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=50.0,
        help="Minimum confidence score for recommendations (default: 50.0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for the report"
    )

    args = parser.parse_args()

    # Select stock list
    if args.stocks == "mag7":
        stock_list = MAG7_STOCKS
        logger.info("Using MAG7 stocks")
    elif args.stocks == "tech":
        stock_list = TECH_CYBER_STOCKS
        logger.info("Using tech/cyber stocks")
    elif args.stocks == "custom":
        stock_list = CUSTOM_PORTFOLIO
        logger.info("Using custom portfolio")
    elif args.stocks == "list":
        if not args.symbols:
            print("Error: --symbols required when using --stocks list")
            sys.exit(1)
        stock_list = [s.upper() for s in args.symbols]
        logger.info(f"Using custom symbol list: {stock_list}")

    # Run discovery
    await discover_indicators(
        stock_list=stock_list,
        min_confidence=args.min_confidence,
        output_file=args.output
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Discovery interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
