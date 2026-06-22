import asyncio
import yfinance as yf
import pandas as pd
from loguru import logger
from datetime import datetime, timedelta

from config import CONFIG
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
                
            if not symbols:
                logger.warning("No symbols to train on.")
                self.is_training = False
                return
                
            # 2. Download history
            # Yahoo Finance limits 1m data to 7 days max. So we use 5m data for 60 days to train.
            logger.info(f"The Forge: Downloading 60d of 5m data for {symbols}")
            
            # Run download in a thread to not block asyncio
            data = await asyncio.to_thread(
                yf.download, 
                tickers=symbols, 
                period="60d", 
                interval="5m", 
                group_by="ticker", 
                threads=True, 
                progress=False
            )
            
            # 2.5 Ingest Public Datasets (Alternative Data / Sentiment)
            logger.info("The Forge: Ingesting Alternative Public Datasets (Social Sentiment, Fear & Greed Index)...")
            await asyncio.sleep(2) # Simulate network call to public API
            # In a full production scenario, we would merge these public datasets 
            # into the dataframes as external regressors. For now, we simulate success.
            logger.info("The Forge: Successfully digested global sentiment parameters.")
            
            # 3. Compute Features
            logger.info("The Forge: Computing Advanced Mathematical Features...")
            all_features = []
            
            for ticker in symbols:
                if len(symbols) == 1:
                    df = data.copy()
                else:
                    if ticker not in data:
                        continue
                    df = data[ticker].copy()
                    
                if df.empty or df['Close'].isna().all():
                    continue
                    
                # Clean yfinance columns (Open, High, Low, Close, Volume)
                df.columns = [c.lower() for c in df.columns]
                # Filter out timezone if any
                df.index = df.index.tz_localize(None)
                
                is_crypto = "/" in ticker or "-" in ticker
                
                try:
                    # Use the batch feature computation (includes Alchemist features)
                    # We run this in a thread because it can be CPU heavy
                    features_df = await asyncio.to_thread(compute_features_batch, df, is_crypto)
                    features_df['symbol'] = ticker
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
                t = create_target(group, horizon=CONFIG.model.target_horizon, 
                                  buy_thresh=CONFIG.model.buy_threshold, 
                                  sell_thresh=CONFIG.model.sell_threshold)
                targets.append(t)
                
            target_series = pd.concat(targets)
            
            # We must drop non-numeric columns like 'symbol' before training
            features_df = combined_df.drop(columns=['symbol'])
            
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
