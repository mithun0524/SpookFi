import pandas as pd
import numpy as np
import ta
from collections import deque
from datetime import datetime, timezone
from loguru import logger
from config import CONFIG
from features.alchemist import MathAlchemist

def get_feature_names() -> list[str]:
    """Return the exact list of feature names configured."""
    return list(CONFIG.features.feature_names)

def compute_features_batch(
    df: pd.DataFrame,
    is_crypto: bool = False,
    fear_greed: float | pd.Series | None = None,
) -> pd.DataFrame:
    """
    Compute all features on a full DataFrame in batch mode.
    Used for training and backtesting.
    Input df must have columns: open, high, low, close, volume.

    Args:
        fear_greed: Optional sentiment signal.
            - float (0-1): applied as a constant to every row (real-time use)
            - pd.Series with DatetimeIndex: merged by date (training use)
            - None: defaults to 0.5 (neutral)
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

    net_change = abs(df['close'].diff(20))
    sum_abs_change = abs(df['close'].diff(1)).rolling(window=20).sum()
    df['efficiency_ratio'] = (net_change / (sum_abs_change + 1e-8)).fillna(0)

    # 8. Alternative Data — Fear & Greed Index
    if fear_greed is None:
        df['fear_greed_index'] = 0.5  # Neutral
    elif isinstance(fear_greed, (int, float)):
        df['fear_greed_index'] = float(fear_greed)
    elif isinstance(fear_greed, pd.Series):
        # Align by date: forward-fill missing trading days
        fg_daily = fear_greed.copy()
        fg_daily.index = pd.to_datetime(fg_daily.index).normalize()
        bar_dates = df.index.normalize() if isinstance(df.index, pd.DatetimeIndex) \
            else pd.to_datetime(df.get('timestamp', df.index)).normalize()
        df['fear_greed_index'] = bar_dates.map(
            lambda d: fg_daily.asof(d) if d >= fg_daily.index[0] else 0.5
        ).fillna(0.5).values
    else:
        df['fear_greed_index'] = 0.5

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
    Maintains a fixed-size ring buffer and computes features on each new bar.
    Caches the Fear & Greed Index (refreshed hourly via asyncio task).
    """
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.is_crypto = "/" in symbol
        self.max_window = 100
        self._buffer: deque = deque(maxlen=self.max_window)
        # Fear & Greed cache
        self._fear_greed: float = 0.5
        self._fg_last_fetched: datetime | None = None
        logger.info(f"Initialized FeatureEngine for {symbol} (Crypto: {self.is_crypto})")

    async def _maybe_refresh_fear_greed(self) -> None:
        """Refresh cached F&G value at most once per hour."""
        now = datetime.now(timezone.utc)
        if self._fg_last_fetched is None or \
                (now - self._fg_last_fetched).total_seconds() > 3600:
            try:
                from data.alt_data import fetch_fear_greed_current
                self._fear_greed = await fetch_fear_greed_current()
                self._fg_last_fetched = now
            except Exception as e:
                logger.warning(f"F&G refresh failed for {self.symbol}: {e}")

    def update(self, bar_dict: dict) -> dict[str, float]:
        """
        Update with a new bar and compute features.
        Returns a dictionary of the configured features.
        Note: F&G refresh is best-effort via sync call to cached value.
        """
        self._buffer.append(bar_dict)

        if len(self._buffer) < 35:
            return {f: 0.0 for f in get_feature_names()}

        history = pd.DataFrame(list(self._buffer))

        if "timestamp" in history.columns:
            history["timestamp"] = pd.to_datetime(history["timestamp"], utc=True)
            history.set_index("timestamp", inplace=True)

        try:
            features_df = compute_features_batch(
                history,
                is_crypto=self.is_crypto,
                fear_greed=self._fear_greed,
            )
            return features_df.iloc[-1].to_dict()
        except Exception as e:
            logger.error(f"Error computing incremental features for {self.symbol}: {e}")
            return {f: 0.0 for f in get_feature_names()}

