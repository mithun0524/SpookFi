"""
MarketDataStream — Real-time Crypto WebSocket via Alpaca.
Supports native async streaming.
"""
import asyncio
from datetime import datetime
from loguru import logger
import pandas as pd
from config import CONFIG
from alpaca.data.live import CryptoDataStream
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

class MarketDataStream:
    """
    Subscribes to Alpaca's Crypto WebSocket and pushes 1-minute bars
    into the asyncio Queue consumed by the engine.
    Also handles historical warmup natively.
    """

    def __init__(self, queue: asyncio.Queue, symbols: list[str] | None = None):
        self.queue = queue
        self._symbols = symbols or list(CONFIG.universe.crypto_symbols)
        self.running = False
        
        # We must initialize the Alpaca stream
        self.stream = CryptoDataStream(CONFIG.alpaca.api_key, CONFIG.alpaca.secret_key)
        self.hist_client = CryptoHistoricalDataClient(CONFIG.alpaca.api_key, CONFIG.alpaca.secret_key)
        
        logger.info(f"Initialized Alpaca Crypto WebSocket for {len(self._symbols)} symbols: {self._symbols}")

    def set_symbols(self, symbols: list[str]):
        """Hot-swap the symbol list (called on regime switch)."""
        logger.warning("Hot-swapping WebSocket symbols requires a restart. Ignoring.")

    async def _bar_handler(self, bar):
        """Callback for new bars from the websocket."""
        try:
            # bar is a CryptoBar object
            b = {
                "timestamp": bar.timestamp,
                "symbol": bar.symbol,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
                "vwap": float(bar.vwap)
            }
            await self.queue.put(b)
        except Exception as e:
            logger.error(f"Error handling websocket bar: {e}")

    async def _warmup_symbols(self):
        """Fetch historical data for warmup (last 40 bars) and enqueue."""
        try:
            logger.info("Fetching historical warmup data from Alpaca...")
            request_params = CryptoBarsRequest(
                symbol_or_symbols=self._symbols,
                timeframe=TimeFrame.Minute,
                start=pd.Timestamp.utcnow() - pd.Timedelta(minutes=50)
            )
            
            # Fetch history in thread
            bars = await asyncio.to_thread(self.hist_client.get_crypto_bars, request_params)
            df = bars.df
            
            if df is None or df.empty:
                logger.warning("Historical fetch returned empty data.")
                return

            for sym in self._symbols:
                if sym in df.index.levels[0]:
                    sym_df = df.loc[sym].dropna()
                    for timestamp, row in sym_df.tail(40).iterrows():
                        b = {
                            "timestamp": timestamp,
                            "symbol": sym,
                            "open": float(row.open),
                            "high": float(row.high),
                            "low": float(row.low),
                            "close": float(row.close),
                            "volume": float(row.volume),
                            "vwap": float(row.vwap)
                        }
                        await self.queue.put(b)
            logger.success("Warmup complete. All historical bars pushed to queue.")
        except Exception as e:
            logger.error(f"Error during warmup: {e}")

    async def start(self):
        """Start the WebSocket and warmup sequence."""
        self.running = True
        
        # 1. Push warmup data to queue
        await self._warmup_symbols()
        
        # 2. Subscribe to live bars
        self.stream.subscribe_bars(self._bar_handler, *self._symbols)
        
        logger.info(f"Starting Alpaca WebSocket loop...")
        # stream.run() is blocking, so we use run_forever inside a thread, or we await it.
        # alpaca-py handles the asyncio event loop gracefully if we run it in a separate thread.
        # Actually, CryptoDataStream uses its own thread internally sometimes, but _run_forever() is async.
        try:
            # We wrap the run in a task
            asyncio.create_task(self.stream._run_forever())
        except Exception as e:
            logger.error(f"Failed to start stream: {e}")
            
        while self.running:
            await asyncio.sleep(1)

    async def stop(self):
        """Stop the stream gracefully."""
        logger.info("Stopping MarketDataStream...")
        self.running = False
        try:
            self.stream.stop()
        except Exception:
            pass
