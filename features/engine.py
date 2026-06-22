import pandas as pd
import numpy as np
import ta
from collections import deque
from loguru import logger
from config import CONFIG
from features.alchemist import MathAlchemist

def get_feature_names() -> list[str]:
    """Return the exact list of feature names configured."""
    return list(CONFIG.features.feature_names)

def compute_features_batch(df: pd.DataFrame, is_crypto: bool = False) -> pd.DataFrame:
    """
    Compute all 20 features on a full DataFrame in batch mode.
    Used for training and backtesting.
    Input df must have columns: open, high, low, close, volume.
    Optionally: vwap.
    """
    logger.info(f"Computing features for dataframe of shape {df.shape}")
    
    # Work on a copy
    df = df.copy()
    
    # Ensure required columns exist
    required = ['open', 'high', 'low', 'close', 'volume']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
            
    # Calculate typical price for VWAP fallback if needed
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    
    # 1. VWAP Context
    if 'vwap' not in df.columns:
        # Simple cumulative VWAP as fallback
        df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
        
    # Replace zeros in VWAP to avoid division by zero
    df['vwap'] = df['vwap'].replace(0, np.nan).bfill()
        
    df['vwap_deviation'] = (df['close'] - df['vwap']) / df['vwap']
    df['vwap_slope'] = df['vwap'].pct_change(5)
    
    rolling_std_vwap_dev = (df['close'] - df['vwap']).rolling(window=20).std()
    # Avoid division by zero
    rolling_std_vwap_dev = rolling_std_vwap_dev.replace(0, np.nan)
    df['price_vs_vwap_std'] = (df['close'] - df['vwap']) / rolling_std_vwap_dev

    # 2. Volume
    rolling_vol_mean = df['volume'].rolling(window=20).mean().replace(0, np.nan)
    df['relative_volume'] = df['volume'] / rolling_vol_mean
    df['volume_roc'] = df['volume'].pct_change(5)
    
    obv = ta.volume.OnBalanceVolumeIndicator(close=df['close'], volume=df['volume']).on_balance_volume()
    obv_slope = obv.diff(10)
    price_slope = df['close'].diff(10)
    df['obv_divergence'] = (np.sign(obv_slope) != np.sign(price_slope)).astype(int)

    # 3. Momentum
    df['rsi_14'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi() / 100.0
    
    macd = ta.trend.MACD(close=df['close'])
    df['macd_histogram'] = macd.macd_diff()
    
    bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_percent_b'] = bb.bollinger_pband()
    
    stoch = ta.momentum.StochasticOscillator(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['stochastic_k'] = stoch.stoch() / 100.0

    # 4. Volatility
    atr = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['atr_14_norm'] = atr.average_true_range() / df['close']
    
    adx = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['adx_14'] = adx.adx() / 100.0
    
    log_returns = np.log(df['close'] / df['close'].shift(1))
    df['rolling_volatility_15m'] = log_returns.rolling(window=15).std()

    # 5. Price Action
    df['return_1m'] = df['close'].pct_change(1)
    df['return_5m'] = df['close'].pct_change(5)
    df['return_15m'] = df['close'].pct_change(15)
    
    rolling_mean_ret = df['return_1m'].rolling(window=30).mean()
    rolling_std_ret = df['return_1m'].rolling(window=30).std().replace(0, np.nan)
    df['rolling_zscore_30m'] = (df['return_1m'] - rolling_mean_ret) / rolling_std_ret

    # 6. Time Context
    # Handle both DatetimeIndex and 'timestamp' column
    timestamps = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.to_datetime(df['timestamp'])
    
    # Calculate minutes from midnight
    minutes_from_midnight = timestamps.hour * 60 + timestamps.minute
    
    if is_crypto:
        # Crypto is 24/7. Use full 1440 minutes of the day.
        df['time_sin'] = np.sin(2 * np.pi * minutes_from_midnight / 1440)
        df['time_cos'] = np.cos(2 * np.pi * minutes_from_midnight / 1440)
        df['minutes_since_open'] = minutes_from_midnight / 1440.0
    else:
        # Stocks: Calculate minutes since open (9:30 AM = 9*60 + 30 = 570 minutes)
        minutes_since_open_raw = minutes_from_midnight - 570
        
        # Clip to trading hours (0 to 390)
        minutes_since_open_raw = np.clip(minutes_since_open_raw, 0, 390)
        
        df['time_sin'] = np.sin(2 * np.pi * minutes_since_open_raw / 390)
        df['time_cos'] = np.cos(2 * np.pi * minutes_since_open_raw / 390)
        df['minutes_since_open'] = minutes_since_open_raw / 390.0

    # 7. Advanced Mathematics (The Alchemist)
    df_avs = MathAlchemist.adaptive_volatility_surface(df, window=20)
    df['kalman_diff'] = (df['close'] - df_avs['kalman_base']) / df['close']
    df['avs_signal'] = df_avs['avs_signal']
    
    # Re-calculate efficiency ratio here or get from AVS
    net_change = abs(df['close'].diff(20))
    sum_abs_change = abs(df['close'].diff(1)).rolling(window=20).sum()
    df['efficiency_ratio'] = (net_change / (sum_abs_change + 1e-8)).fillna(0)

    # Extract exactly the configured features
    features = get_feature_names()
    
    # Check if all features were computed
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise ValueError(f"Failed to compute features: {missing}")
        
    df_features = df[features].copy()
    
    # Forward fill NaNs (e.g., from zero division before replacement), then fill 0
    df_features.ffill(inplace=True)
    df_features.fillna(0, inplace=True)
    
    return df_features

class FeatureEngine:
    """
    Incremental feature engine for real-time use.
    Maintains state and computes features efficiently on each new bar.
    """
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.is_crypto = "/" in symbol  # e.g., BTC/USD
        self.max_window = 40 # Max lookback needed (30 + buffer)
        self.history = pd.DataFrame()
        logger.info(f"Initialized FeatureEngine for {symbol} (Crypto: {self.is_crypto})")
        
    def update(self, bar_dict: dict) -> dict[str, float]:
        """
        Update with a new bar and compute features.
        Returns a dictionary of the 20 features.
        """
        # Convert single bar to DataFrame row
        new_row = pd.DataFrame([bar_dict])
        
        # Ensure timestamp is datetime
        if 'timestamp' in new_row.columns:
            new_row['timestamp'] = pd.to_datetime(new_row['timestamp'])
            new_row.set_index('timestamp', inplace=True)
            
        # Append to history
        if self.history.empty:
            self.history = new_row
        else:
            self.history = pd.concat([self.history, new_row])
            
        # Truncate history to max_window
        if len(self.history) > self.max_window:
            self.history = self.history.iloc[-self.max_window:]
            
        # We need at least the max window to compute all features reliably
        # If not enough history, we compute what we can but some will be 0
        
        # Re-use the batch compute function on the rolling window
        # In a hyper-optimized system, we would maintain running sums/vars,
        # but for 40 rows pandas is fast enough (< 10ms)
        try:
            features_df = compute_features_batch(self.history, is_crypto=self.is_crypto)
            # Get the features for the latest bar
            latest_features = features_df.iloc[-1].to_dict()
            return latest_features
        except Exception as e:
            logger.error(f"Error computing incremental features for {self.symbol}: {e}")
            # Return zeros as fallback
            return {f: 0.0 for f in get_feature_names()}
