import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
import joblib
import json
import time
from pathlib import Path
from loguru import logger
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.utils.class_weight import compute_sample_weight

from config import CONFIG
from features.engine import compute_features_batch, get_feature_names

def create_target(df: pd.DataFrame, horizon: int, buy_thresh: float, sell_thresh: float) -> pd.Series:
    """
    Create target variable based on forward returns.
    0 = SELL, 1 = HOLD, 2 = BUY
    """
    forward_returns = df['close'].pct_change(horizon).shift(-horizon)
    forward_returns = forward_returns.replace([np.inf, -np.inf], np.nan)
    
    target = pd.Series(1, index=df.index)
    target[forward_returns > buy_thresh] = 2
    target[forward_returns < sell_thresh] = 0
    target[forward_returns.isna()] = np.nan
    return target

def train_model(features_df: pd.DataFrame, target: pd.Series) -> tuple[dict, StandardScaler, dict]:
    """
    Train an Ensemble of models: XGBoost, Random Forest, and LightGBM.
    Returns: (models_dict, scaler, metrics_dict)
    """
    logger.info("Starting Ensemble model training pipeline...")
    start_time = time.time()
    
    # Align features and target
    valid_idx = target.dropna().index
    X = features_df.loc[valid_idx]
    y = target.loc[valid_idx].astype(int)
    
    # Sanitize input: replace infinities with NaN, then fill with 0
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
    
    logger.info(f"Training data shape: X={X.shape}, y={y.shape}")
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Balance classes (critical for financial data where HOLD is dominant)
    sample_weights = compute_sample_weight(class_weight="balanced", y=y)

    models = {}
    metrics = {}

    # 1. Train XGBoost
    logger.info("Training XGBoost...")
    xgb_params = CONFIG.model.xgb_params.copy()
    xgb_params.update({"n_jobs": -1, "objective": "multi:softprob", "num_class": 3, "random_state": 42})
    xgb_model = xgb.XGBClassifier(**xgb_params)
    xgb_model.fit(X_scaled, y, sample_weight=sample_weights)
    models['xgb'] = xgb_model

    # 2. Train Random Forest
    logger.info("Training Random Forest...")
    rf_model = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=10, random_state=42, n_jobs=-1, class_weight='balanced')
    rf_model.fit(X_scaled, y)
    models['rf'] = rf_model

    # 3. Train LightGBM
    logger.info("Training LightGBM...")
    lgb_model = lgb.LGBMClassifier(n_estimators=300, max_depth=8, learning_rate=0.05, class_weight='balanced', random_state=42, n_jobs=-1, verbose=-1)
    lgb_model.fit(X_scaled, y)
    models['lgb'] = lgb_model

    # Compute in-sample metrics for each model
    for name, model in models.items():
        y_pred = model.predict(X_scaled)
        y_prob = model.predict_proba(X_scaled)
        metrics[name] = {
            'accuracy': float(accuracy_score(y, y_pred)),
            'f1_weighted': float(f1_score(y, y_pred, average='weighted')),
            'log_loss': float(log_loss(y, y_prob)),
        }
        logger.info(f"[{name.upper()}] Accuracy: {metrics[name]['accuracy']:.4f} | F1: {metrics[name]['f1_weighted']:.4f}")
    
    metrics['overall'] = {
        'training_time_seconds': time.time() - start_time,
        'timestamp': time.time()
    }
    
    logger.success("Ensemble training complete!")
    return models, scaler, metrics

def save_model(models: dict, scaler: StandardScaler, metrics: dict, model_dir: str = CONFIG.model.model_dir):
    """Save all ensemble artifacts to disk."""
    out_dir = Path(model_dir)
    out_dir.mkdir(exist_ok=True, parents=True)
    
    # Save models
    for name, model in models.items():
        joblib.dump(model, out_dir / f"{name}_phantom.joblib")
        
    # Save common scaler
    joblib.dump(scaler, out_dir / CONFIG.model.scaler_filename)
    
    # Save metrics
    with open(out_dir / CONFIG.model.metadata_filename, 'w') as f:
        json.dump(metrics, f, indent=4)
        
    logger.info(f"Saved Ensemble artifacts to {out_dir}")

def load_model(model_dir: str = CONFIG.model.model_dir) -> tuple[dict, StandardScaler, dict]:
    """Load all ensemble artifacts from disk."""
    in_dir = Path(model_dir)
    
    scaler_path = in_dir / CONFIG.model.scaler_filename
    meta_path = in_dir / CONFIG.model.metadata_filename
    
    if not scaler_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Ensemble artifacts not found in {in_dir}")
        
    scaler = joblib.load(scaler_path)
    
    with open(meta_path, 'r') as f:
        metrics = json.load(f)
        
    models = {}
    for name in ['xgb', 'rf', 'lgb']:
        path = in_dir / f"{name}_phantom.joblib"
        if path.exists():
            models[name] = joblib.load(path)
            
    if not models:
        raise FileNotFoundError("No models found in the ensemble.")
        
    logger.info(f"Loaded {len(models)} models from {in_dir}")
    return models, scaler, metrics
