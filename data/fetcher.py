import pandas as pd
import yfinance as yf
from loguru import logger
from pathlib import Path
import os
from config import CONFIG

CACHE_DIR = Path("data_cache")

def fetch_historical(symbol: str, days: int, interval: str = '1m') -> pd.DataFrame:
    """
    Fetch historical data for a symbol.
    Uses yfinance.
    """
    # Map '1min' to '1m', '5min' to '5m'
    interval = interval.replace('min', 'm')
    
    logger.info(f"Fetching {interval} data for {symbol} for {days} days...")
    
    # yfinance limits 1m data to 7 days.
    if interval == '1m' and days > 7:
        logger.warning("yfinance limits 1m data to 7 days. Fetching last 7 days.")
        days = 7
        
    # Map Alpaca crypto format (BTC/USD) to yfinance format (BTC-USD)
    yf_symbol = symbol.replace("/", "-")
        
    try:
        df = yf.download(yf_symbol, period=f'{days}d', interval=interval, progress=False)
        if df.empty:
             logger.warning(f"No data returned for {symbol}")
             return pd.DataFrame()
             
        # Flatten MultiIndex columns if present (yfinance sometimes does this)
        if isinstance(df.columns, pd.MultiIndex):
            # Take the first level if it's Price
            df.columns = df.columns.get_level_values(0)
            
        df.columns = [col.lower() for col in df.columns]
        
        # Ensure we have the required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
             logger.error(f"Missing columns {missing_cols} in data for {symbol}")
             return pd.DataFrame()
             
        df = df[required_cols].copy()
        
        # Drop rows with NaNs in required columns
        df.dropna(subset=required_cols, inplace=True)
        
        # Save to cache
        CACHE_DIR.mkdir(exist_ok=True)
        cache_file = CACHE_DIR / f"{symbol}_{interval}_{days}d.parquet"
        df.to_parquet(cache_file)
        logger.info(f"Saved {len(df)} rows for {symbol} to {cache_file}")
        
        return df
        
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()

def load_cached(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """Load cached data if available."""
    cache_file = CACHE_DIR / f"{symbol}_{interval}_{days}d.parquet"
    if cache_file.exists():
        try:
             df = pd.read_parquet(cache_file)
             logger.info(f"Loaded {len(df)} rows for {symbol} from cache")
             return df
        except Exception as e:
             logger.error(f"Error loading cache for {symbol}: {e}")
    return pd.DataFrame()

def fetch_all_symbols() -> dict[str, pd.DataFrame]:
    """Fetch data for all configured symbols."""
    data = {}
    
    all_symbols = list(CONFIG.universe.symbols) + list(CONFIG.universe.crypto_symbols)
    
    for symbol in all_symbols:
        df = fetch_historical(symbol, CONFIG.universe.history_days, CONFIG.universe.timeframe.lower())
        if not df.empty:
            data[symbol] = df
    return data
