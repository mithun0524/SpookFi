import argparse
import asyncio
from loguru import logger
import sys

from config import CONFIG
from data.fetcher import fetch_historical
from model.forge import TheForge
from backtest.runner import Backtester
from engine.phantom import PhantomEngine

def setup_logging():
    """Configure loguru."""
    logger.remove()
    logger.add(sys.stderr, level=CONFIG.log.log_level)
    logger.add(f"{CONFIG.log.log_dir}/{CONFIG.log.engine_log_file}", rotation="10 MB", level="DEBUG")

def main():
    parser = argparse.ArgumentParser(description="👻 Phantom Trading Engine")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Fetch
    parser_fetch = subparsers.add_parser("fetch", help="Fetch historical data for training")
    
    # Train
    parser_train = subparsers.add_parser("train", help="Train/retrain XGBoost model")
    
    # Backtest
    parser_backtest = subparsers.add_parser("backtest", help="Run backtest")
    parser_backtest.add_argument("--symbol", type=str, required=True, help="Symbol to backtest")
    parser_backtest.add_argument("--days", type=int, default=30, help="Days of history")
    
    # Run Live Engine
    parser_run = subparsers.add_parser("run", help="Start real-time trading engine")
    
    args = parser.parse_args()
    setup_logging()
    
    if args.command == "fetch":
        logger.info("Fetching data for all universe symbols...")
        for symbol in CONFIG.universe.symbols:
             fetch_historical(symbol, CONFIG.universe.history_days, CONFIG.universe.timeframe.lower())
             
    elif args.command == "train":
        logger.info("Running advanced training pipeline via The Forge...")
        asyncio.run(TheForge().train_model())
        
    elif args.command == "backtest":
        runner = Backtester()
        runner.run(args.symbol, args.days)
        
    elif args.command == "run":
        engine = PhantomEngine()

        async def _run():
            try:
                await engine.start()
            except Exception as exc:
                logger.error(f"Engine error: {exc}")
            finally:
                await engine.stop()

        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Engine will stop cleanly.")
            
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
