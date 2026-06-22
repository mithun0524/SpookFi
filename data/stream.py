import asyncio
import yfinance as yf
from datetime import datetime, timezone
from loguru import logger
from config import CONFIG
import pandas as pd

class MarketDataStream:
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.running = False
        logger.info("Initialized Yahoo Finance Polling Stream for Indian Market.")

    async def _fetch_and_process(self, symbols):
        """Fetch 1-minute data for all symbols and push the latest bar to queue."""
        if not symbols: return
        
        try:
            # yfinance allows downloading multiple tickers at once
            # e.g., 'RELIANCE.NS TCS.NS'
            tickers_str = " ".join(symbols)
            
            # Fetch the last 1 day of 1-minute data
            # Run in executor to avoid blocking the asyncio loop
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, 
                lambda: yf.download(tickers=tickers_str, period="1d", interval="1m", progress=False)
            )
            
            if df.empty:
                return

            # yfinance returns a MultiIndex column DataFrame if multiple tickers are requested.
            # Columns: (PriceType, Ticker)
            # If only 1 ticker, it's single index. Let's handle both.
            
            if isinstance(df.columns, pd.MultiIndex):
                for sym in symbols:
                    try:
                        # Extract data for this specific symbol
                        sym_df = df.xs(sym, level=1, axis=1).dropna()
                        if sym_df.empty: continue
                        
                        # Get the absolute latest minute bar
                        latest = sym_df.iloc[-1]
                        timestamp = sym_df.index[-1]
                        
                        bar_dict = {
                            'timestamp': timestamp,
                            'symbol': sym,
                            'open': float(latest['Open']),
                            'high': float(latest['High']),
                            'low': float(latest['Low']),
                            'close': float(latest['Close']),
                            'volume': float(latest['Volume']),
                            'vwap': float(latest['Close']) # yf doesn't give VWAP at 1m, use close
                        }
                        await self.queue.put(bar_dict)
                    except Exception as e:
                        logger.warning(f"Could not parse yfinance data for {sym}: {e}")
            else:
                # Single ticker fallback
                sym = symbols[0]
                latest = df.iloc[-1]
                timestamp = df.index[-1]
                bar_dict = {
                    'timestamp': timestamp,
                    'symbol': sym,
                    'open': float(latest['Open']),
                    'high': float(latest['High']),
                    'low': float(latest['Low']),
                    'close': float(latest['Close']),
                    'volume': float(latest['Volume']),
                    'vwap': float(latest['Close'])
                }
                await self.queue.put(bar_dict)
                
        except Exception as e:
            logger.error(f"Error fetching yfinance data: {e}")

    async def start(self):
        """Start the polling loop."""
        self.running = True
        symbols = list(CONFIG.universe.symbols)
        logger.info(f"Starting yfinance 1m polling for: {symbols}")
        
        while self.running:
            await self.fetch_cycle(symbols)
            # Wait for 60 seconds before polling again
            await asyncio.sleep(60)
            
    async def fetch_cycle(self, symbols):
        logger.debug("Polling Yahoo Finance...")
        await self._fetch_and_process(symbols)

    async def stop(self):
        """Stop the polling loop."""
        logger.info("Stopping Yahoo Finance Polling Stream...")
        self.running = False

# Helper functions
async def start_stream(queue: asyncio.Queue):
    stream = MarketDataStream(queue)
    await stream.start()

async def stop_stream(stream: MarketDataStream):
    await stream.stop()
