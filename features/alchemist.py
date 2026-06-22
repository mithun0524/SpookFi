import numpy as np
import pandas as pd
from loguru import logger

class MathAlchemist:
    """
    The Alchemist: Injects advanced quantitative mathematics into the Feature Engine.
    """
    
    @staticmethod
    def apply_kalman_filter(prices: pd.Series, process_variance: float = 1e-5, measurement_variance: float = 1e-3) -> pd.Series:
        """
        1D Kalman Filter for price noise reduction.
        Provides a lag-free smoothing alternative to Moving Averages.
        """
        n = len(prices)
        if n == 0:
            return prices
            
        filtered_prices = np.zeros(n)
        P = np.zeros(n) # Error covariance
        
        # Initial guesses
        filtered_prices[0] = prices.iloc[0]
        P[0] = 1.0
        
        for i in range(1, n):
            # Prediction
            pred_p = filtered_prices[i-1]
            pred_P = P[i-1] + process_variance
            
            # Update
            K = pred_P / (pred_P + measurement_variance) # Kalman Gain
            filtered_prices[i] = pred_p + K * (prices.iloc[i] - pred_p)
            P[i] = (1 - K) * pred_P
            
        return pd.Series(filtered_prices, index=prices.index)
        
    @staticmethod
    def calculate_hurst_exponent(prices: pd.Series, max_lag: int = 20) -> float:
        """
        Simplified Hurst Exponent calculation using variance of log returns over different lags.
        H < 0.5: Mean Reverting
        H = 0.5: Random Walk
        H > 0.5: Trending
        """
        if len(prices) < max_lag * 2:
            return 0.5
            
        lags = range(2, max_lag)
        tau = []
        
        for lag in lags:
            diff = prices.diff(lag).dropna()
            if len(diff) == 0:
                continue
            tau.append(np.sqrt(np.std(diff)))
            
        if len(tau) < 2:
            return 0.5
            
        # Perform linear regression in log-log scale
        m = np.polyfit(np.log(list(lags[:len(tau)])), np.log(tau), 1)
        hurst = m[0] * 2.0
        
        # Bound it between 0 and 1
        return min(max(hurst, 0.0), 1.0)
        
    @staticmethod
    def rolling_hurst(prices: pd.Series, window: int = 60, max_lag: int = 15) -> pd.Series:
        """
        Rolling Hurst Exponent for dynamic regime detection.
        """
        # This can be slow, so we optimize by applying it only when necessary or 
        # using a fast rolling apply.
        def _hurst(x):
            return MathAlchemist.calculate_hurst_exponent(pd.Series(x), max_lag)
            
        return prices.rolling(window=window).apply(_hurst, raw=True)

    @staticmethod
    def adaptive_volatility_surface(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
        """
        Adaptive Volatility Surface (AVS).
        A dynamic band that adjusts its width based on the Hurst exponent (Regime).
        If trending (H > 0.5), bands widen to avoid false breakouts.
        If mean-reverting (H < 0.5), bands tighten to capture quick scalps.
        """
        df = df.copy()
        
        # 1. Kalman smoothed baseline
        df['kalman_base'] = MathAlchemist.apply_kalman_filter(df['close'])
        
        # 2. Base volatility (Standard Deviation)
        base_vol = df['close'].rolling(window=window).std()
        
        # 3. Regime multiplier (Simplified proxy for speed)
        # Using a fast proxy for Hurst to avoid extreme CPU load on every tick
        # Proxy: Ratio of net price change to sum of absolute price changes
        net_change = abs(df['close'].diff(window))
        sum_abs_change = abs(df['close'].diff(1)).rolling(window=window).sum()
        efficiency_ratio = net_change / (sum_abs_change + 1e-8) # Bounded 0 to 1
        
        # Map Efficiency Ratio (0 to 1) to a Band Multiplier (e.g., 1.5 to 3.0)
        # Low efficiency (choppy) -> tight bands (e.g. 1.5)
        # High efficiency (trending) -> wide bands (e.g. 3.0)
        band_multiplier = 1.5 + (efficiency_ratio * 1.5)
        
        df['avs_upper'] = df['kalman_base'] + (base_vol * band_multiplier)
        df['avs_lower'] = df['kalman_base'] - (base_vol * band_multiplier)
        
        # Signal: 1 if breaking upper (buy in trend), -1 if breaking lower
        # But wait, in choppy, breaking upper means sell.
        # We define a smart AVS signal:
        conditions = [
            (df['close'] > df['avs_upper']) & (efficiency_ratio > 0.5),  # Trend Breakout BUY
            (df['close'] > df['avs_upper']) & (efficiency_ratio <= 0.5), # Chop Mean Reversion SELL
            (df['close'] < df['avs_lower']) & (efficiency_ratio > 0.5),  # Trend Breakout SELL
            (df['close'] < df['avs_lower']) & (efficiency_ratio <= 0.5)  # Chop Mean Reversion BUY
        ]
        choices = [1, -1, -1, 1]
        df['avs_signal'] = np.select(conditions, choices, default=0)
        
        return df
