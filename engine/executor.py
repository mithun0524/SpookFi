from loguru import logger
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from config import CONFIG
import os

class Executor:
    """
    Handles order execution via Alpaca REST API.
    """
    def __init__(self):
        self.is_paper = CONFIG.alpaca.trading_mode == 'paper'
        logger.info(f"Initializing Executor. Mode: {'PAPER' if self.is_paper else 'LIVE'}")
        
        if not CONFIG.alpaca.api_key or not CONFIG.alpaca.secret_key:
             logger.warning("Alpaca API keys missing! Executor will operate in MOCK mode.")
             self.client = None
        else:
             self.client = TradingClient(
                 CONFIG.alpaca.api_key, 
                 CONFIG.alpaca.secret_key, 
                 paper=self.is_paper
             )
             
    def submit_order(self, order_params: dict) -> dict | None:
        """
        Submit a market order.
        order_params: {'symbol': str, 'side': 'buy'|'sell', 'qty': int}
        """
        symbol = order_params['symbol']
        side = OrderSide.BUY if order_params['side'] == 'buy' else OrderSide.SELL
        qty = order_params['qty']
        
        logger.info(f"Submitting Market Order: {side} {qty} {symbol}")
        
        if self.client is None:
             logger.info(f"[MOCK] Executed {side} {qty} {symbol}")
             return {'status': 'filled', 'filled_qty': qty} # Mock return
             
        try:
             req = MarketOrderRequest(
                 symbol=symbol,
                 qty=qty,
                 side=side,
                 time_in_force=TimeInForce.DAY,  # DAY required for equities on Alpaca paper
             )
             res = self.client.submit_order(order_data=req)
             logger.info(f"Order submitted: {res.id} | Status: {res.status}")
             return {
                 'id': str(res.id),
                 'status': res.status.value,
                 'filled_qty': float(res.filled_qty) if res.filled_qty else 0.0
             }
        except Exception as e:
             logger.error(f"Order submission failed for {symbol}: {e}")
             return None

    def close_all_positions(self):
        """Emergency close all positions."""
        logger.warning("Emergency closing all positions!")
        if self.client is None:
             logger.info("[MOCK] Closed all positions.")
             return
             
        try:
             self.client.close_all_positions(cancel_orders=True)
        except Exception as e:
             logger.error(f"Error closing positions: {e}")
             
    def get_account_equity(self) -> float:
        """Get current account equity from Alpaca."""
        if self.client is None:
             return CONFIG.risk.initial_capital

        try:
             account = self.client.get_account()
             equity = float(account.equity)
             logger.info(f"Alpaca account equity: ${equity:,.2f} | Buying power: ${float(account.buying_power):,.2f}")
             return equity
        except Exception as e:
             logger.error(f"Error getting account equity: {e}")
             return CONFIG.risk.initial_capital

    def get_open_positions(self) -> list[dict]:
        """Fetch all open positions from Alpaca (used to sync state on restart)."""
        if self.client is None:
             return []
        try:
             positions = self.client.get_all_positions()
             return [
                 {
                     'symbol': p.symbol,
                     'side': 'long' if p.side.value == 'long' else 'short',
                     'qty': abs(float(p.qty)),
                     'avg_entry': float(p.avg_entry_price),
                     'market_value': float(p.market_value),
                     'unrealized_pnl': float(p.unrealized_pl),
                 }
                 for p in positions
             ]
        except Exception as e:
             logger.error(f"Error fetching open positions: {e}")
             return []
