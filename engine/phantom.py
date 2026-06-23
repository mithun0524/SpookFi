import asyncio
import json
import time
from datetime import datetime
from loguru import logger
from pathlib import Path
import pandas as pd

from config import CONFIG
from data.stream import MarketDataStream
from features.engine import FeatureEngine
from model.predictor import Predictor
from risk.manager import RiskManager
from engine.executor import Executor

class PhantomEngine:
    """
    Main orchestrator for the Phantom trading system.
    Ties together streaming, features, prediction, risk, and execution.
    """
    def __init__(self):
        logger.info("Initializing Phantom Engine...")
        
        # Core components
        self.queue = asyncio.Queue()
        self.stream = MarketDataStream(self.queue)
        self.predictor = Predictor()
        self.executor = Executor()
        
        # Initialize Risk Manager with actual account equity if available
        equity = self.executor.get_account_equity()
        self.risk_manager = RiskManager(initial_capital=equity)
        
        # Feature Engines (one per symbol to maintain state)
        self.feature_engines = {
            symbol: FeatureEngine(symbol) 
            for symbol in (CONFIG.universe.symbols + CONFIG.universe.crypto_symbols)
        }
        
        # State
        self.is_running = False
        self._last_save_time = 0.0  # epoch seconds of last state save

        # Setup state saving for dashboard
        self.state_file = Path(CONFIG.log.log_dir) / "phantom_state.json"
        self.state_file.parent.mkdir(exist_ok=True)
        
    async def process_bar(self, bar: dict):
        """Process a single incoming bar."""
        symbol = bar['symbol']
        current_price = bar['close']
        
        # 1. Update features
        engine = self.feature_engines[symbol]
        features = engine.update(bar)
        
        # 2. Predict Signal
        signal, confidence = self.predictor.predict(features)
        
        # Capture latest signal for dashboard
        if not hasattr(self, 'latest_signals'):
            self.latest_signals = {}
        self.latest_signals[symbol] = {'signal': signal, 'confidence': float(confidence)}
        
        # 3. Get required metrics for risk management
        # Note: if feature engine hasn't warmed up, these might be 0
        atr = features.get('atr_14_norm', 0.0) * current_price # denormalize
        adx = features.get('adx_14', 0.0) * 100.0 # denormalize
        
        # Calculate raw minutes since open (from timestamp)
        dt = pd.to_datetime(bar['timestamp'], utc=True).tz_convert('America/New_York')
        mins_from_midnight = dt.hour * 60 + dt.minute
        mins_since_open = mins_from_midnight - 570 # 9:30 AM
        
        # 4. Check existing positions for stops
        action = self.risk_manager.update_position(symbol, current_price, atr)
        if action == 'CLOSE':
             # Stop hit!
             pos = self.risk_manager.positions[symbol]
             side = 'sell' if pos.side == 'long' else 'buy'
             
             # Execute close
             res = self.executor.submit_order({'symbol': symbol, 'side': side, 'qty': pos.quantity})
             if res:
                  self.risk_manager.close_position(symbol, current_price)
                  
        # 5. Process new signals
        if signal != 'HOLD':
             order_params = self.risk_manager.validate_signal(
                 symbol=symbol,
                 signal=signal,
                 confidence=confidence,
                 current_price=current_price,
                 atr=atr,
                 adx=adx,
                 minutes_since_open=mins_since_open
             )
             
             if order_params:
                  # Execute order
                  res = self.executor.submit_order(order_params)
                  if res:
                       # Record position
                       self.risk_manager.open_position(
                           symbol=symbol,
                           side=order_params['side'],
                           entry_price=current_price,
                           qty=order_params['qty'],
                           stop_loss=order_params['stop_loss'],
                           take_profit=order_params.get('take_profit'),
                       )

    async def _event_loop(self):
        """Main asynchronous event loop processing the queue."""
        while self.is_running:
            try:
                # Wait for new bar from stream
                bar = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self.process_bar(bar)
                self.queue.task_done()
                
                # Periodically save state for dashboard (every ~5 seconds)
                now = time.time()
                if now - self._last_save_time >= 5.0:
                    self._save_state()
                    self._last_save_time = now
                    
            except asyncio.TimeoutError:
                # Normal timeout, just check running flag
                continue
            except Exception as e:
                logger.error(f"Error in event loop: {e}")

    def _save_state(self):
        """Save state to disk for the Streamlit dashboard."""
        try:
            state = self.risk_manager.get_status()
            if hasattr(self, 'latest_signals'):
                state['latest_signals'] = self.latest_signals
                
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    async def start(self):
        """Start the engine."""
        logger.info("Starting Phantom Engine...")
        self.is_running = True
        
        # Start stream in background
        stream_task = asyncio.create_task(self.stream.start())
        
        # Start event loop
        await self._event_loop()

    async def stop(self):
        """Stop the engine gracefully."""
        logger.info("Stopping Phantom Engine...")
        self.is_running = False
        await self.stream.stop()
        
        # Save final state
        self._save_state()
