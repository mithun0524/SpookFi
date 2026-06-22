import pandas as pd
import numpy as np
import xgboost as xgb
import optuna
import joblib
import json
import time
from pathlib import Path
from loguru import logger
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, f1_score, log_loss

from config import CONFIG
from features.engine import compute_features_batch, get_feature_names

def create_target(df: pd.DataFrame, horizon: int, buy_thresh: float, sell_thresh: float) -> pd.Series:
    """
    Create target variable based on forward returns.
    0 = SELL, 1 = HOLD, 2 = BUY
    """
    # Calculate forward returns
    forward_returns = df['close'].pct_change(horizon).shift(-horizon)
    
    # Initialize as HOLD (1)
    target = pd.Series(1, index=df.index)
    
    # Assign BUY (2) and SELL (0) labels
    target[forward_returns > buy_thresh] = 2
    target[forward_returns < sell_thresh] = 0
    
    # Set NaNs at the end (due to shift) to NaN so we can drop them
    target[forward_returns.isna()] = np.nan
    
    return target

def train_model(features_df: pd.DataFrame, target: pd.Series) -> tuple[xgb.XGBClassifier, StandardScaler, dict]:
    """
    Train XGBoost model using walk-forward validation and Optuna.
    """
    logger.info("Starting model training pipeline...")
    start_time = time.time()
    
    # Align features and target, drop rows with NaN targets (the end of the series)
    valid_idx = target.dropna().index
    X = features_df.loc[valid_idx]
    y = target.loc[valid_idx].astype(int)
    
    logger.info(f"Training data shape: X={X.shape}, y={y.shape}")
    
    # TimeSeriesSplit for walk-forward validation
    tscv = TimeSeriesSplit(n_splits=CONFIG.model.n_splits, gap=CONFIG.model.gap)
    
    def objective(trial):
        # Hyperparameter search space
        params = {
            'objective': 'multi:softprob',
            'num_class': 3,
            'max_depth': trial.suggest_int('max_depth', 3, 10),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'reg_alpha': trial.suggest_float('reg_alpha', 0, 1),
            'reg_lambda': trial.suggest_float('reg_lambda', 0.5, 2.0),
            'tree_method': 'hist',
            'random_state': 42,
            'n_jobs': -1 # Use all cores
        }
        
        cv_scores = []
        
        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            
            # Fit scaler ONLY on train to prevent data leakage
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # Train model
            model = xgb.XGBClassifier(**params)
            model.fit(X_train_scaled, y_train, eval_set=[(X_test_scaled, y_test)], verbose=False)
            
            # Predict
            y_pred = model.predict(X_test_scaled)
            
            # Metric: Weighted F1 Score
            score = f1_score(y_test, y_pred, average='weighted')
            cv_scores.append(score)
            
        return np.mean(cv_scores)
        
    logger.info("Running Optuna hyperparameter optimization...")
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=CONFIG.model.optuna_n_trials)
    
    best_params = study.best_params
    logger.info(f"Best params: {best_params}")
    
    # Train final model on full dataset
    logger.info("Training final model on all data...")
    final_params = CONFIG.model.xgb_params.copy()
    final_params.update(best_params)
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    final_model = xgb.XGBClassifier(**final_params)
    final_model.fit(X_scaled, y)
    
    # Compute in-sample metrics
    y_pred = final_model.predict(X_scaled)
    y_prob = final_model.predict_proba(X_scaled)
    
    metrics = {
        'accuracy': float(accuracy_score(y, y_pred)),
        'f1_weighted': float(f1_score(y, y_pred, average='weighted')),
        'log_loss': float(log_loss(y, y_prob)),
        'best_params': best_params,
        'training_time_seconds': time.time() - start_time,
        'timestamp': time.time()
    }
    
    logger.info(f"Final model metrics: {metrics}")
    
    return final_model, scaler, metrics

def save_model(model: xgb.XGBClassifier, scaler: StandardScaler, metrics: dict, model_dir: str = CONFIG.model.model_dir):
    """Save model artifacts to disk."""
    out_dir = Path(model_dir)
    out_dir.mkdir(exist_ok=True, parents=True)
    
    model_path = out_dir / CONFIG.model.model_filename
    scaler_path = out_dir / CONFIG.model.scaler_filename
    meta_path = out_dir / CONFIG.model.metadata_filename
    
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    
    with open(meta_path, 'w') as f:
        json.dump(metrics, f, indent=4)
        
    logger.info(f"Saved model artifacts to {out_dir}")

def load_model(model_dir: str = CONFIG.model.model_dir) -> tuple[xgb.XGBClassifier, StandardScaler, dict]:
    """Load model artifacts from disk."""
    in_dir = Path(model_dir)
    
    model_path = in_dir / CONFIG.model.model_filename
    scaler_path = in_dir / CONFIG.model.scaler_filename
    meta_path = in_dir / CONFIG.model.metadata_filename
    
    if not all(p.exists() for p in [model_path, scaler_path, meta_path]):
        raise FileNotFoundError(f"Model artifacts not found in {in_dir}")
        
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    
    with open(meta_path, 'r') as f:
        metrics = json.load(f)
        
    logger.info(f"Loaded model artifacts from {in_dir}")
    return model, scaler, metrics
