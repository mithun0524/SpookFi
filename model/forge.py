import asyncio
import yfinance as yf
import pandas as pd
from loguru import logger
from datetime import datetime, timedelta

from config import CONFIG
from data.alt_data import fetch_fear_greed_history
from features.engine import compute_features_batch
from model.trainer import train_model, create_target, save_model

class TheForge:
    """
    The Forge: A background intelligence that continuously downloads new data
    and retrains the brain (XGBoost model) to adapt to changing market regimes.
    """
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator # To notify when a new model is ready
        self.is_training = False
        self.last_train_time = None
        self.train_interval_hours = 6 # Retrain every 6 hours
        
    async def run_continuous_learning(self):
        """Background loop to periodically retrain the model."""
        logger.info("The Forge ignited. Continuous Learning Pipeline active.")
        while True:
            now = datetime.now()
            
            # Check if it's time to train
            if self.last_train_time is None or (now - self.last_train_time) > timedelta(hours=self.train_interval_hours):
                if not self.is_training:
                    # Fire off training task without blocking the event loop
                    asyncio.create_task(self.train_model())
                    
            await asyncio.sleep(60) # Check every minute
            
    async def train_model(self):
        """
        Gathers data for the current active universe, builds features,
        and trains the model.
        """
        self.is_training = True
        logger.info("The Forge: Commencing Model Training...")
        try:
            # 1. Ask the Hunter what we are currently trading
            if self.orchestrator and hasattr(self.orchestrator, 'active_symbols'):
                symbols = self.orchestrator.active_symbols
            else:
                # Fallback to config
                symbols = list(CONFIG.universe.symbols)
                
            # 1. Determine Universe
            symbols = CONFIG.universe.crypto_symbols
            if not symbols:
                logger.error("No crypto symbols in config!")
                return
            
            # 2. Fetch Base Data
            logger.info(f"The Forge: Fetching historical crypto data for {len(symbols)} symbols...")
            
            from alpaca.data.historical import CryptoHistoricalDataClient
            from alpaca.data.requests import CryptoBarsRequest
            from alpaca.data.timeframe import TimeFrame
            
            client = CryptoHistoricalDataClient(CONFIG.alpaca.api_key, CONFIG.alpaca.secret_key)
            req = CryptoBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Minute,
                start=pd.Timestamp.utcnow() - pd.Timedelta(days=60)
            )
            bars = await asyncio.to_thread(client.get_crypto_bars, req)
            df_multi = bars.df
            
            # 2.5 Fetch Real Alternative Data (Fear & Greed Index)
            logger.info("The Forge: Fetching Fear & Greed Index history...")
            fear_greed_series = await fetch_fear_greed_history(limit=90)
            logger.info(f"The Forge: Got {len(fear_greed_series)} days of F&G data.")
            
            # 3. Compute Features
            logger.info("The Forge: Computing Advanced Mathematical Features...")
            all_features = []
            
            for ticker in symbols:
                if ticker not in df_multi.index.levels[0]:
                    continue
                df = df_multi.loc[ticker].copy()
                
                if df.empty or df['close'].isna().all():
                    continue
                    
                df.index = df.index.tz_localize(None)
                
                try:
                    features_df = await asyncio.to_thread(
                        compute_features_batch, df, True, fear_greed_series
                    )
                    features_df['symbol'] = ticker
                    features_df['close'] = df['close']
                    all_features.append(features_df)
                except Exception as e:
                    logger.error(f"Error computing features for {ticker}: {e}")
                    
            if not all_features:
                logger.error("The Forge: Failed to extract features for any symbol.")
                self.is_training = False
                return
                
            combined_df = pd.concat(all_features)
            
            # 4. Train Model
            logger.info("The Forge: Igniting XGBoost Trainer...")
            
            # We need to create targets for the combined_df
            # We will group by symbol to avoid bleeding forward returns across symbols
            targets = []
            for sym, group in combined_df.groupby('symbol'):
                t = create_target(group, horizon=CONFIG.model.forward_horizon,
                                  buy_thresh=CONFIG.model.buy_threshold,
                                  sell_thresh=CONFIG.model.sell_threshold)
                targets.append(t)
                
            target_series = pd.concat(targets)
            
            # Remove symbols and target from features
            features_df = combined_df.drop(columns=['symbol', 'close'])
            
            # VERY IMPORTANT: Reset index to avoid pandas duplicate index explosion!
            features_df = features_df.reset_index(drop=True)
            target_series = target_series.reset_index(drop=True)
            
            # Run training in thread
            model, scaler, metrics = await asyncio.to_thread(
                train_model, features_df, target_series
            )
            
            # Save the new model
            await asyncio.to_thread(save_model, model, scaler, metrics)
            
            logger.info(f"The Forge: Training Complete! Metrics: {metrics}")
            
            # 5. Hot-swap the model in the Predictor
            if self.orchestrator:
                logger.info("The Forge: Hot-swapping model weights in the Orchestrator...")
                self.orchestrator.predictor.reload_model() # This will reload from disk
                
            self.last_train_time = datetime.now()
            
        except Exception as e:
            logger.error(f"The Forge encountered an error: {e}")
        finally:
            self.is_training = False
            logger.info("The Forge: Returned to standby.")
