import asyncio
import yfinance as yf
from loguru import logger
from datetime import datetime
import pandas as pd

from config import CONFIG
from data.universe import UniverseHunter
from features.engine import FeatureEngine
from model.predictor import Predictor
from model.forge import TheForge
from risk.manager import RiskManager

class SpookFiBrain:
    """
    The Autonomous Brain.
    Zero configuration. Decides what to trade, when to train, and executes it.
    """
    def __init__(self):
        self.hunter = UniverseHunter()
        self.risk_manager = RiskManager()
        self.predictor = Predictor()
        
        # Connect the Forge
        self.forge = TheForge(orchestrator=self)
        
        self.active_symbols = []
        self.feature_engines = {}
        
        self.market_regime = "INIT" # "EQUITY" or "CRYPTO"
        
    async def start(self):
        """Ignite the SpookFi Brain."""
        logger.info("SpookFi Brain: INITIALIZING AUTONOMOUS SYSTEMS")
        
        # Start the background learning forge
        asyncio.create_task(self.forge.run_continuous_learning())
        
        # Main trading loop
        while True:
            try:
                await self._trading_cycle()
            except Exception as e:
                logger.error(f"Brain encountered a critical error in cycle: {e}")
                await asyncio.sleep(5)
                
    async def _trading_cycle(self):
        # 1. Determine Regime
        is_india_open = self.hunter.is_indian_market_open()
        current_regime = "EQUITY" if is_india_open else "CRYPTO"
        
        # 2. Check if we need to hunt for new symbols (regime switch or startup)
        if self.market_regime != current_regime or not self.active_symbols:
            logger.info(f"SpookFi Brain: Switching Regime to {current_regime.upper()}")
            
            # Close all existing positions before switching markets
            for symbol in list(self.risk_manager.positions.keys()):
                # Liquidate at current market price (simplified)
                # In a real system we'd fetch the exact exit price
                self.risk_manager.close_position(symbol, self.risk_manager.positions[symbol].entry_price) 
            
            self.market_regime = current_regime
            self.active_symbols = self.hunter.hunt(top_n=5)
            
            # Re-initialize feature engines
            self.feature_engines = {sym: FeatureEngine(sym) for sym in self.active_symbols}
            
            # Reset daily risk if switching to a new day (e.g. Equity open)
            if current_regime == "EQUITY":
                self.risk_manager.reset_daily()
                
        # 3. Pull Live Market Data (Batch for efficiency)
        logger.debug(f"Brain: Polling data for {self.active_symbols}")
        # To avoid blocking, run yf in thread
        data = await asyncio.to_thread(
            yf.download, 
            tickers=self.active_symbols, 
            period="1d", 
            interval="1m", 
            group_by="ticker", 
            threads=True, 
            progress=False
        )
        
        # 4. Process Signals
        for symbol in self.active_symbols:
            try:
                if len(self.active_symbols) == 1:
                    df = data
                else:
                    if symbol not in data:
                        continue
                    df = data[symbol]
                    
                if df.empty or df['Close'].isna().all():
                    continue
                    
                # Get the latest bar
                latest_bar = df.iloc[-1].to_dict()
                # Rename keys to lowercase
                latest_bar = {k.lower(): v for k, v in latest_bar.items()}
                latest_bar['timestamp'] = df.index[-1]
                
                # Compute features
                engine = self.feature_engines[symbol]
                features_dict = engine.update(latest_bar)
                
                # Predict
                current_price = latest_bar['close']
                signal, confidence = self.predictor.predict(features_dict)
                
                # ATR for risk
                atr = features_dict.get('atr_14_norm', 0.01) * current_price
                adx = features_dict.get('adx_14', 0.0) * 100
                minutes_since_open = features_dict.get('minutes_since_open', 0.5) * 390
                
                # Risk Check
                order = self.risk_manager.validate_signal(
                    symbol=symbol,
                    signal=signal,
                    confidence=confidence,
                    current_price=current_price,
                    atr=atr,
                    adx=adx,
                    minutes_since_open=minutes_since_open
                )
                
                if order:
                    self.risk_manager.open_position(
                        symbol=order['symbol'],
                        side=order['side'],
                        entry_price=current_price,
                        qty=order['qty'],
                        stop_loss=order['stop_loss']
                    )
                    
                # Update open positions PnL and Stops
                close_signal = self.risk_manager.update_position(symbol, current_price, atr)
                if close_signal == 'CLOSE':
                    self.risk_manager.close_position(symbol, current_price)
                    
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                
        # Polling interval (1 minute)
        await asyncio.sleep(60)
