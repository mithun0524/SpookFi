import pandas as pd
import numpy as np
from loguru import logger
import time
from collections import Counter

from config import CONFIG
from model.trainer import load_model
from features.engine import get_feature_names

class Predictor:
    """
    Real-time Ensemble Prediction Engine for Phantom.
    """
    def __init__(self, model_dir: str = CONFIG.model.model_dir):
        logger.info(f"Initializing Ensemble Predictor from {model_dir}")
        self.model_dir = model_dir
        self.feature_names = get_feature_names()
        self.signal_map = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}
        
        self.models = {}
        self.scaler = None
        self.metrics = None
        
        try:
            self.reload_model()
        except FileNotFoundError:
            logger.warning("No trained ensemble found! Outputting HOLD until The Forge completes.")
            
    def reload_model(self):
        """Hot-swap the ensemble weights from disk."""
        self.models, self.scaler, self.metrics = load_model(self.model_dir)
        logger.info(f"Predictor successfully loaded {list(self.models.keys())} ensemble.")
        
    def predict(self, features: dict[str, float]) -> tuple[str, float]:
        """
        Make a real-time ensemble prediction.
        Uses majority voting (2 out of 3).
        Returns (signal: str, confidence: float).
        """
        if not self.models or self.scaler is None:
            return 'HOLD', 0.0
            
        start_time = time.time()
        
        # Ensure features are in the exact order
        try:
            feature_array = np.array([[features[f] for f in self.feature_names]])
        except KeyError as e:
            logger.error(f"Missing feature: {e}. Returning HOLD.")
            return 'HOLD', 0.0
            
        # Sanitize infinities
        feature_array = np.nan_to_num(feature_array, nan=0.0, posinf=0.0, neginf=0.0)
            
        # Scale features
        scaled_features = self.scaler.transform(feature_array)
        
        votes = []
        confidences = []
        
        # Poll each model
        for name, model in self.models.items():
            probs = model.predict_proba(scaled_features)[0]
            class_idx = np.argmax(probs)
            signal = self.signal_map[class_idx]
            confidence = probs[class_idx]
            
            # Apply individual model threshold
            if signal != 'HOLD' and confidence < CONFIG.model.confidence_threshold:
                signal = 'HOLD'
                
            votes.append(signal)
            confidences.append(confidence)
            
        # Ensemble Logic: Majority Rules
        vote_counts = Counter(votes)
        top_signal, top_count = vote_counts.most_common(1)[0]
        
        # Require strict majority (e.g., 2 out of 3)
        if top_count > len(self.models) / 2 and top_signal != 'HOLD':
            final_signal = top_signal
            # Average confidence of the models that agreed
            final_conf = np.mean([c for s, c in zip(votes, confidences) if s == top_signal])
        else:
            final_signal = 'HOLD'
            final_conf = np.mean(confidences)
             
        latency = (time.time() - start_time) * 1000
        logger.debug(f"Ensemble Votes: {votes} -> {final_signal} ({final_conf:.2f}) | Latency: {latency:.2f}ms")
        
        return final_signal, float(final_conf)
        
    def predict_batch(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        Batch prediction for backtesting.
        Uses soft-voting probabilities.
        """
        if not self.models or self.scaler is None:
            out_df = pd.DataFrame(index=features_df.index)
            out_df['signal'] = 'HOLD'
            out_df['confidence'] = 0.0
            return out_df
            
        # Ensure columns are in correct order
        X = features_df[self.feature_names]
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Scale
        X_scaled = self.scaler.transform(X)
        
        # Average probabilities across all models
        avg_probs = np.zeros((len(X_scaled), 3))
        for model in self.models.values():
            avg_probs += model.predict_proba(X_scaled)
        avg_probs /= len(self.models)
        
        class_idxs = np.argmax(avg_probs, axis=1)
        confidences = np.max(avg_probs, axis=1)
        
        out_df = pd.DataFrame(index=features_df.index)
        out_df['raw_signal_idx'] = class_idxs
        out_df['confidence'] = confidences
        out_df['signal'] = out_df['raw_signal_idx'].map(self.signal_map)
        
        mask = (out_df['signal'] != 'HOLD') & (out_df['confidence'] < CONFIG.model.confidence_threshold)
        out_df.loc[mask, 'signal'] = 'HOLD'
        
        return out_df
