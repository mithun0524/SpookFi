import pandas as pd
import numpy as np
from loguru import logger
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import CONFIG
from data.fetcher import fetch_historical
from features.engine import compute_features_batch
from model.predictor import Predictor

class Backtester:
    """
    Vectorized backtesting engine for Phantom.
    """
    def __init__(self):
        self.predictor = Predictor()
        
    def run(self, symbol: str, days: int = 30) -> dict:
        """Run backtest on historical data."""
        logger.info(f"Running backtest for {symbol} over {days} days...")
        
        # 1. Fetch Data
        df = fetch_historical(symbol, days, CONFIG.universe.timeframe.lower())
        if df.empty:
             logger.error("No data for backtest.")
             return {}
             
        # 2. Compute Features
        features_df = compute_features_batch(df)
        
        # 3. Generate Predictions
        # Align dataframes
        df = df.loc[features_df.index].copy()
        predictions = self.predictor.predict_batch(features_df)
        df['signal'] = predictions['signal']
        df['confidence'] = predictions['confidence']
        
        # 4. Simulate Trading with proper state tracking
        # Shift signals by 1 to simulate execution on NEXT bar open
        df['execution_signal'] = df['signal'].shift(1).fillna('HOLD')

        # Stateful position tracking: 0 = flat, 1 = long, -1 = short
        positions = []
        current_pos = 0
        for sig in df['execution_signal']:
            if sig == 'BUY' and current_pos <= 0:
                current_pos = 1
            elif sig == 'SELL' and current_pos >= 0:
                current_pos = -1   # Flip to short or close long
            # If already in direction, stay (no pyramid)
            positions.append(current_pos)

        df['position'] = positions
        
        # Calculate returns
        df['market_return'] = df['close'].pct_change()
        df['strategy_return'] = df['position'].shift(1) * df['market_return']
        
        # Apply costs
        trade_mask = df['position'] != df['position'].shift(1)
        df.loc[trade_mask, 'strategy_return'] -= CONFIG.backtest.slippage_pct
        
        # Cumulative returns
        df['cum_market'] = (1 + df['market_return']).cumprod()
        df['cum_strategy'] = (1 + df['strategy_return']).cumprod()
        
        # 5. Metrics
        total_return = df['cum_strategy'].iloc[-1] - 1
        annualized_return = (1 + total_return) ** (252 * 390 / len(df)) - 1
        
        daily_returns = df['strategy_return'].resample('D').sum()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() != 0 else 0
        
        rolling_max = df['cum_strategy'].cummax()
        drawdown = (df['cum_strategy'] - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        trades = trade_mask.sum() / 2 # entry and exit
        
        metrics = {
            'symbol': symbol,
            'days': days,
            'total_return_pct': total_return * 100,
            'annualized_return_pct': annualized_return * 100,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_drawdown * 100,
            'num_trades': trades
        }
        
        logger.info(f"Backtest Results: {metrics}")
        
        # Generate plot
        self._plot_results(df, symbol)
        
        return metrics
        
    def _plot_results(self, df: pd.DataFrame, symbol: str):
        """Generate interactive Plotly chart."""
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.1, 
                            subplot_titles=(f'{symbol} Price & Signals', 'Cumulative Returns'))

        # Price
        fig.add_trace(go.Scatter(x=df.index, y=df['close'], name='Price', line=dict(color='gray')), row=1, col=1)
        
        # Buy Signals
        buys = df[df['signal'] == 'BUY']
        fig.add_trace(go.Scatter(x=buys.index, y=buys['close'], mode='markers', 
                                 marker=dict(symbol='triangle-up', size=10, color='green'), 
                                 name='Buy'), row=1, col=1)
                                 
        # Sell Signals
        sells = df[df['signal'] == 'SELL']
        fig.add_trace(go.Scatter(x=sells.index, y=sells['close'], mode='markers', 
                                 marker=dict(symbol='triangle-down', size=10, color='red'), 
                                 name='Sell'), row=1, col=1)

        # Returns
        fig.add_trace(go.Scatter(x=df.index, y=df['cum_market'], name='Market', line=dict(color='gray')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['cum_strategy'], name='Strategy', line=dict(color='blue')), row=2, col=1)

        fig.update_layout(height=800, title_text=f"Phantom Backtest: {symbol}")
        fig.write_html(f"logs/backtest_{symbol}.html")
        logger.info(f"Saved interactive plot to logs/backtest_{symbol}.html")
