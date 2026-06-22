"""
Phantom — Central Configuration
Single source of truth for all parameters.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


# ─── Alpaca API ──────────────────────────────────────────────────────────────

@dataclass
class AlpacaConfig:
    api_key: str = os.getenv("ALPACA_API_KEY", "")
    secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    trading_mode: str = os.getenv("TRADING_MODE", "paper")

    @property
    def base_url(self) -> str:
        if self.trading_mode == "live":
            return "https://api.alpaca.markets"
        return "https://paper-api.alpaca.markets"

    @property
    def data_url(self) -> str:
        return "https://data.alpaca.markets"

    @property
    def stream_url(self) -> str:
        return "wss://stream.data.alpaca.markets/v2/iex"


# ─── Trading Universe ───────────────────────────────────────────────────────

@dataclass
class UniverseConfig:
    symbols: tuple = ("SPY", "AAPL", "TSLA", "NVDA")
    crypto_symbols: tuple = ("BTC/USD", "ETH/USD", "SOL/USD")
    timeframe: str = "1Min"               # Bar size for features
    history_days: int = 365               # Days of history for training
    retrain_lookback_days: int = 180      # Rolling window for retraining



# ─── Feature Engineering ─────────────────────────────────────────────────────

@dataclass
class FeatureConfig:
    # VWAP Context
    vwap_window: int = 20

    # Momentum
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: int = 2
    stoch_period: int = 14

    # Volatility
    atr_period: int = 14
    adx_period: int = 14
    volatility_window: int = 15

    # Price Action
    return_windows: tuple = (1, 5, 15)    # Minutes
    zscore_window: int = 30

    # Volume
    volume_avg_period: int = 20

    # Market hours (minutes in a trading day: 9:30-16:00 = 390 min)
    market_minutes: int = 390

    # Total expected features
    expected_feature_count: int = 23

    # Feature names (for consistency across training and inference)
    feature_names: tuple = (
        "vwap_deviation",
        "vwap_slope",
        "price_vs_vwap_std",
        "relative_volume",
        "volume_roc",
        "obv_divergence",
        "rsi_14",
        "macd_histogram",
        "bb_percent_b",
        "stochastic_k",
        "atr_14_norm",
        "adx_14",
        "rolling_volatility_15m",
        "return_1m",
        "return_5m",
        "return_15m",
        "rolling_zscore_30m",
        "time_sin",
        "time_cos",
        "minutes_since_open",
        "kalman_diff",
        "avs_signal",
        "efficiency_ratio",
    )


# ─── Model ───────────────────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    # Walk-forward validation
    n_splits: int = 5
    gap: int = 24                        # Bars gap between train/test

    # Signal thresholds (on forward returns)
    buy_threshold: float = 0.003         # +0.3%
    sell_threshold: float = -0.003       # -0.3%

    # Confidence threshold (model probability)
    confidence_threshold: float = 0.6

    # Forward return horizon (in bars)
    forward_horizon: int = 15            # 15-min lookahead for target

    # XGBoost defaults (Optuna will tune these)
    xgb_params: dict = field(default_factory=lambda: {
        "objective": "multi:softprob",
        "num_class": 3,
        "max_depth": 6,
        "learning_rate": 0.05,
        "n_estimators": 500,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "eval_metric": "mlogloss",
        "tree_method": "hist",
        "random_state": 42,
    })

    # Optuna
    optuna_n_trials: int = 50

    # Paths
    model_dir: str = "models"
    model_filename: str = "phantom_xgb.joblib"
    scaler_filename: str = "phantom_scaler.joblib"
    metadata_filename: str = "phantom_meta.json"


# ─── Risk Management ────────────────────────────────────────────────────────

@dataclass
class RiskConfig:
    # Per-trade risk
    risk_per_trade: float = 0.01         # 1% of capital per trade
    stop_loss_atr_mult: float = 2.0      # Stop = entry ± 2×ATR
    trailing_stop_atr_mult: float = 1.5  # Trail = 1.5×ATR

    # Daily limits
    max_daily_drawdown: float = 0.05     # 5% max daily loss → kill switch
    max_open_positions: int = 3

    # Cooldown
    cooldown_minutes: int = 5            # After a losing trade

    # Filters
    min_adx_for_trading: float = 20.0    # No trades when ADX < 20
    no_trade_first_minutes: int = 5      # Skip first 5 min after open
    no_trade_last_minutes: int = 5       # Skip last 5 min before close

    # Capital (paper trading default)
    initial_capital: float = 100_000.0


# ─── Backtest ────────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    slippage_pct: float = 0.0005         # 0.05% slippage
    commission_per_trade: float = 0.0    # Alpaca is commission-free

    # Performance targets
    min_sharpe: float = 1.0
    max_drawdown: float = 0.15           # 15%
    min_win_rate: float = 0.45           # 45%
    min_walk_forward_efficiency: float = 0.5


# ─── Dashboard ───────────────────────────────────────────────────────────────

@dataclass
class DashboardConfig:
    refresh_interval: int = 5            # Seconds
    port: int = 8501
    max_trade_log_rows: int = 50


# ─── Logging ─────────────────────────────────────────────────────────────────

@dataclass
class LogConfig:
    log_dir: str = "logs"
    log_level: str = "INFO"
    trade_log_file: str = "trades.jsonl"
    engine_log_file: str = "phantom.log"


# ─── Master Config ───────────────────────────────────────────────────────────
import json
from pathlib import Path

@dataclass
class PhantomConfig:
    alpaca: AlpacaConfig = field(default_factory=AlpacaConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    log: LogConfig = field(default_factory=LogConfig)
    
    def load_settings(self, path: str = "settings.json"):
        if not Path(path).exists():
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            # Update Alpaca
            if "alpaca" in data:
                for k, v in data["alpaca"].items():
                    setattr(self.alpaca, k, v)
                    
            # Update Universe
            if "universe" in data:
                for k, v in data["universe"].items():
                    if k in ("symbols", "crypto_symbols"):
                        setattr(self.universe, k, tuple(v))
                    else:
                        setattr(self.universe, k, v)
                        
            # Update Risk
            if "risk" in data:
                for k, v in data["risk"].items():
                    setattr(self.risk, k, v)
        except Exception as e:
            print(f"Error loading settings: {e}")

# Singleton
CONFIG = PhantomConfig()
CONFIG.load_settings()
