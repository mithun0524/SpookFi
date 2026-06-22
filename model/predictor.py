import pandas as pd
import numpy as np
from loguru import logger
import time

from config import CONFIG
from model.trainer import load_model
from features.engine import get_feature_names

class Predictor:
    """
    Real-time prediction engine for Phantom.
    """
    def __init__(self, model_dir: str = CONFIG.model.model_dir):
        logger.info(f"Initializing Predictor from {model_dir}")
        self.model_dir = model_dir
        self.feature_names = get_feature_names()
        self.signal_map = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}
        
        self.model = None
        self.scaler = None
        self.metrics = None
        
        try:
            self.reload_model()
        except FileNotFoundError:
            logger.warning("No trained model found! Predictor will output HOLD until The Forge completes its first training cycle.")
            
    def reload_model(self):
        """Hot-swap the model weights from disk."""
        self.model, self.scaler, self.metrics = load_model(self.model_dir)
        logger.info("Predictor successfully loaded new model weights.")
        
    def predict(self, features: dict[str, float]) -> tuple[str, float]:
        """
        Make a real-time prediction from a feature dictionary.
        Returns (signal: str, confidence: float).
        """
        if self.model is None or self.scaler is None:
            return 'HOLD', 0.0
            
        start_time = time.time()
        
        # Ensure features are in the exact order expected by the model
        try:
            feature_array = np.array([[features[f] for f in self.feature_names]])
        except KeyError as e:
            logger.error(f"Missing feature: {e}. Returning HOLD.")
            return 'HOLD', 0.0
            
        # Scale features
        scaled_features = self.scaler.transform(feature_array)
        
        # Predict probability
        probs = self.model.predict_proba(scaled_features)[0]
        
        # Get class with highest probability
        class_idx = np.argmax(probs)
        confidence = probs[class_idx]
        
        # Map to string signal
        signal = self.signal_map[class_idx]
        
        # Apply confidence threshold - if below threshold, force HOLD
        if signal != 'HOLD' and confidence < CONFIG.model.confidence_threshold:
             logger.debug(f"Signal {signal} rejected due to low confidence ({confidence:.2f} < {CONFIG.model.confidence_threshold})")
             signal = 'HOLD'
             
        latency = (time.time() - start_time) * 1000
        logger.debug(f"Prediction: {signal} ({confidence:.2f}) | Latency: {latency:.2f}ms")
        
        return signal, float(confidence)
        
    def predict_batch(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        Batch prediction for backtesting.
        """
        if self.model is None or self.scaler is None:
            out_df = pd.DataFrame(index=features_df.index)
            out_df['signal'] = 'HOLD'
            out_df['confidence'] = 0.0
            return out_df
            
        # Ensure columns are in correct order
        X = features_df[self.feature_names]
        
        # Scale
        X_scaled = self.scaler.transform(X)
        
        # Predict
        probs = self.model.predict_proba(X_scaled)
        class_idxs = np.argmax(probs, axis=1)
        confidences = np.max(probs, axis=1)
        
        # Create output dataframe
        out_df = pd.DataFrame(index=features_df.index)
        out_df['raw_signal_idx'] = class_idxs
        out_df['confidence'] = confidences
        
        # Map to strings
        out_df['signal'] = out_df['raw_signal_idx'].map(self.signal_map)
        
        # Apply threshold
        mask = (out_df['signal'] != 'HOLD') & (out_df['confidence'] < CONFIG.model.confidence_threshold)
        out_df.loc[mask, 'signal'] = 'HOLD'
        
        return out_df
