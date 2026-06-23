"""
PhantomOrchestrator — MOCK / STAGE-3 TESTING HARNESS

This orchestrator uses a simulated (yfinance polling) market stream and an
optional mock predictor so the frontend UI can be tested without real Alpaca
credentials or a trained model.

For production live trading, use engine/phantom.py (PhantomEngine) which
connects to Alpaca's WebSocket stream and the real Executor.
"""
import asyncio
import random
from datetime import datetime, timezone
from loguru import logger
from config import CONFIG
from data.stream import MarketDataStream
from features.engine import FeatureEngine
from model.predictor import Predictor
from risk.manager import RiskManager

class PhantomOrchestrator:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.feature_engines = {} # Dictionary mapping symbol -> FeatureEngine
        self.risk_manager = RiskManager()
        # Try to load model, fallback to mock predictions if not trained yet
        self.use_mock_predictor = False
        try:
            self.predictor = Predictor(CONFIG.model.model_dir)
            logger.info("Loaded XGBoost Predictor.")
        except Exception as e:
            logger.warning(f"Failed to load XGBoost model: {e}. Falling back to MOCK Predictor for Stage 3 UI testing.")
            self.use_mock_predictor = True

        # We are using yfinance, no API keys needed!
        self.stream = MarketDataStream(self.queue)

    def _get_mock_prediction(self):
        """Random prediction for UI testing when actual model isn't trained."""
        rand = random.random()
        if rand > 0.8: return "BUY", random.uniform(0.7, 0.99)
        if rand < 0.2: return "SELL", random.uniform(0.7, 0.99)
        return "HOLD", random.uniform(0.3, 0.6)

    async def process_loop(self):
        """The core event loop of Phantom."""
        logger.info("Phantom Orchestrator Event Loop Started.")
        while True:
            bar = await self.queue.get()
            
            try:
                sym = bar['symbol']
                if sym not in self.feature_engines:
                    self.feature_engines[sym] = FeatureEngine(sym)
                
                # 1. Compute features
                features = self.feature_engines[sym].update(bar)
                
                # Update positions (unrealized PnL / Trailing stops)
                # For mock data, we need fake ATR, let's use 1.5
                mock_atr = 1.5 
                action = self.risk_manager.update_position(bar['symbol'], bar['close'], mock_atr)
                if action == 'CLOSE':
                    self.risk_manager.close_position(bar['symbol'], bar['close'])
                    continue

                # 2. Get Prediction
                if self.use_mock_predictor:
                    signal, conf = self._get_mock_prediction()
                else:
                    signal, conf = self.predictor.predict(features)
                    
                # 3. Risk Management & Execution
                if signal in ['BUY', 'SELL']:
                    # Fake ADX for mock mode to pass regime filter
                    order = self.risk_manager.validate_signal(
                        symbol=bar['symbol'],
                        signal=signal,
                        confidence=conf,
                        current_price=bar['close'],
                        atr=mock_atr,
                        adx=30.0, # Pass regime filter
                        minutes_since_open=120 # Pass time filter
                    )
                    
                if order:
                        logger.info(f"EXECUTING PAPER TRADE: {order}")
                        self.risk_manager.open_position(
                            symbol=order['symbol'],
                            side=order['side'],
                            entry_price=bar['close'],
                            qty=order['qty'],
                            stop_loss=order['stop_loss'],
                            take_profit=order.get('take_profit'),
                        )

            except Exception as e:
                logger.error(f"Error processing bar for {bar['symbol']}: {e}")
            
            finally:
                self.queue.task_done()

    async def start(self):
        # Start the appropriate stream
        stream_task = asyncio.create_task(self.stream.start())
            
        # Start the processing loop
        process_task = asyncio.create_task(self.process_loop())
        
        await asyncio.gather(stream_task, process_task)
