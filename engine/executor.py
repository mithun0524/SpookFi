from loguru import logger
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from config import CONFIG

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
                 time_in_force=TimeInForce.GTC
             )
             res = self.client.submit_order(order_data=req)
             return {
                 'id': str(res.id),
                 'status': res.status.value,
                 'filled_qty': float(res.filled_qty) if res.filled_qty else 0.0
             }
        except Exception as e:
             logger.error(f"Error submitting order for {symbol}: {e}")
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
        """Get current account equity."""
        if self.client is None:
             return CONFIG.risk.initial_capital
             
        try:
             account = self.client.get_account()
             return float(account.equity)
        except Exception as e:
             logger.error(f"Error getting account: {e}")
             return CONFIG.risk.initial_capital
