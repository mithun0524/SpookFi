import yfinance as yf
import pandas as pd
from loguru import logger
from datetime import datetime
import pytz

class UniverseHunter:
    """
    The Hunter: Dynamically scans a large predefined universe and selects
    the top N most volatile and liquid assets to trade right now.
    """
    def __init__(self):
        # Top 25 NSE Liquid Stocks
        self.equities_pool = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
            "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS", "L&T.NS",
            "AXISBANK.NS", "BAJFINANCE.NS", "MARUTI.NS", "ASIANPAINT.NS", "SUNPHARMA.NS",
            "HCLTECH.NS", "TITAN.NS", "TATASTEEL.NS", "ULTRACEMCO.NS", "TATAMOTORS.NS",
            "WIPRO.NS", "NTPC.NS", "POWERGRID.NS", "M&M.NS", "ADANIENT.NS"
        ]
        
        # Top 15 Crypto
        self.crypto_pool = [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", 
            "ADA-USD", "AVAX-USD", "DOGE-USD", "DOT-USD", "MATIC-USD",
            "LINK-USD", "UNI-USD", "LTC-USD", "BCH-USD", "ATOM-USD"
        ]

    def is_indian_market_open(self) -> bool:
        """Check if NSE is currently open (09:15 to 15:30 IST, Mon-Fri)."""
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        
        # Weekend check
        if now.weekday() >= 5: # 5=Sat, 6=Sun
            return False
            
        current_time = now.time()
        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        return market_open <= current_time <= market_close

    def hunt(self, top_n: int = 5) -> list[str]:
        """
        Determines the active market, downloads recent data for the pool,
        and returns the top N symbols ranked by Volatility * Liquidity.
        """
        if self.is_indian_market_open():
            logger.info("Indian Market is OPEN. Hunting Equities...")
            pool = self.equities_pool
            # For yahoo finance, some Indian stocks might need '.NS' suffix, already added.
        else:
            logger.info("Indian Market is CLOSED. Hunting Crypto...")
            pool = self.crypto_pool

        logger.info(f"Scanning {len(pool)} symbols to find the top {top_n}...")
        
        try:
            # Download last 5 days of 1-hour data to calculate recent RVOL and ATR
            # We use group_by='ticker' to get a clean multi-index
            data = yf.download(pool, period="5d", interval="1h", group_by='ticker', threads=True, progress=False)
            
            scores = {}
            for ticker in pool:
                if len(pool) == 1:
                    df = data
                else:
                    df = data[ticker]
                    
                if df.empty or df['Close'].isna().all():
                    continue
                    
                # Calculate metrics
                # 1. Liquidity Proxy (Average Volume * Average Price)
                avg_volume = df['Volume'].mean()
                avg_price = df['Close'].mean()
                liquidity = avg_volume * avg_price
                
                # 2. Volatility Proxy (ATR roughly as High - Low / Close)
                # Just taking average percentage range per hour
                high_low_pct = ((df['High'] - df['Low']) / df['Close']).mean()
                
                # We want high liquidity AND high volatility
                # Normalize them roughly by ranking or just multiplying 
                # (since we just need relative ranking within the pool)
                score = liquidity * high_low_pct
                
                if pd.notna(score) and score > 0:
                    scores[ticker] = score
                    
            # Sort by score descending
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top_symbols = [x[0] for x in ranked[:top_n]]
            
            logger.info(f"HUNT COMPLETE. Top {top_n} targets acquired: {top_symbols}")
            return top_symbols
            
        except Exception as e:
            logger.error(f"Hunter failed: {e}. Falling back to default list.")
            return pool[:top_n]
