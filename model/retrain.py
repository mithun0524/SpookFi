import pandas as pd
from loguru import logger
import argparse
import sys

from config import CONFIG
from data.fetcher import fetch_historical
from features.engine import compute_features_batch
from model.trainer import create_target, train_model, save_model, load_model

def retrain(symbols: list[str] = None):
    """
    Automated retraining pipeline.
    """
    logger.info("Starting automated retraining pipeline...")
    
    if symbols is None:
        symbols = list(CONFIG.universe.symbols)
        
    all_features = []
    all_targets = []
    
    # 1. Fetch data and compute features
    for symbol in symbols:
        logger.info(f"Processing data for {symbol}...")
        
        # Fetch data
        df = fetch_historical(symbol, CONFIG.universe.retrain_lookback_days, CONFIG.universe.timeframe.lower())
        
        if df.empty:
            continue
            
        # Compute features
        try:
             features_df = compute_features_batch(df)
        except Exception as e:
             logger.error(f"Error computing features for {symbol}: {e}")
             continue
             
        # Create target
        target = create_target(
            df, 
            CONFIG.model.forward_horizon, 
            CONFIG.model.buy_threshold, 
            CONFIG.model.sell_threshold
        )
        
        # Align features and target
        valid_idx = target.dropna().index
        features_df = features_df.loc[valid_idx]
        target = target.loc[valid_idx]
        
        all_features.append(features_df)
        all_targets.append(target)
        
    if not all_features:
        logger.error("No valid data available for retraining.")
        return
        
    # Combine all symbols
    X_full = pd.concat(all_features)
    y_full = pd.concat(all_targets)
    
    logger.info(f"Combined dataset: {len(X_full)} samples")
    
    # 2. Train new model
    logger.info("Training new model...")
    new_model, new_scaler, new_metrics = train_model(X_full, y_full)
    
    # 3. Compare with existing model (if it exists)
    try:
        _, _, old_metrics = load_model()
        logger.info(f"Current model F1: {old_metrics.get('f1_weighted', 0):.4f}")
        logger.info(f"New model F1: {new_metrics.get('f1_weighted', 0):.4f}")
        
        if new_metrics.get('f1_weighted', 0) > old_metrics.get('f1_weighted', 0):
            logger.info("New model is better! Saving...")
            save_model(new_model, new_scaler, new_metrics)
        else:
            logger.info("New model did not improve performance. Keeping old model.")
            # Still save it as a backup timestamped version perhaps in a real system
            
    except FileNotFoundError:
        logger.info("No existing model found. Saving new model...")
        save_model(new_model, new_scaler, new_metrics)
        
    logger.info("Retraining pipeline complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Retrain Phantom Model")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to retrain on")
    args = parser.parse_args()
    
    retrain(args.symbols)
