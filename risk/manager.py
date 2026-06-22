from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger
from threading import Lock

from config import CONFIG

@dataclass
class Position:
    symbol: str
    side: str          # 'long' or 'short'
    entry_price: float
    quantity: int
    stop_loss: float
    trailing_stop: float
    entry_time: datetime
    unrealized_pnl: float = 0.0

class RiskManager:
    """
    The Gatekeeper. Every signal must pass through here.
    """
    def __init__(self, initial_capital: float = CONFIG.risk.initial_capital):
        self.lock = Lock()
        self.positions: dict[str, Position] = {}
        self.daily_pnl: float = 0.0
        self.trade_log: list[dict] = []
        self.last_loss_time: datetime | None = None
        
        self.initial_capital = initial_capital
        self.daily_start_equity = initial_capital
        self.current_equity = initial_capital
        
        logger.info(f"Initialized RiskManager with {initial_capital} capital.")

    def reset_daily(self, new_start_equity: float = None):
        """Reset daily counters (call at market open)."""
        with self.lock:
            if new_start_equity:
                 self.daily_start_equity = new_start_equity
                 self.current_equity = new_start_equity
                 
            self.daily_pnl = 0.0
            self.trade_log = []
            self.last_loss_time = None
            logger.info(f"Reset daily counters. Start equity: {self.daily_start_equity}")

    def is_kill_switch_active(self) -> bool:
        """Check if daily drawdown limit is exceeded."""
        drawdown_pct = self.daily_pnl / self.daily_start_equity
        return drawdown_pct <= -CONFIG.risk.max_daily_drawdown

    def validate_signal(self, symbol: str, signal: str, confidence: float, current_price: float, 
                        atr: float, adx: float, minutes_since_open: float) -> dict | None:
        """
        Validate a signal and return order params if approved.
        minutes_since_open is raw minutes (0-390), not normalized here.
        """
        with self.lock:
            if signal == 'HOLD':
                 return None
                 
            # 1. Kill switch
            if self.is_kill_switch_active():
                 logger.warning("KILL SWITCH ACTIVE. Signal rejected.")
                 return None
                 
            # 2. Max open positions
            if len(self.positions) >= CONFIG.risk.max_open_positions and symbol not in self.positions:
                 logger.debug(f"Max positions ({CONFIG.risk.max_open_positions}) reached. Signal rejected.")
                 return None
                 
            # 3. Already in position
            if symbol in self.positions:
                 logger.debug(f"Already holding {symbol}. Signal rejected.")
                 return None
                 
            # 4. Cooldown
            if self.last_loss_time:
                 cooldown_end = self.last_loss_time + timedelta(minutes=CONFIG.risk.cooldown_minutes)
                 if datetime.now() < cooldown_end:
                     logger.debug(f"In cooldown until {cooldown_end}. Signal rejected.")
                     return None
                     
            # 5. Regime filter
            if adx < CONFIG.risk.min_adx_for_trading:
                 logger.debug(f"ADX ({adx:.2f}) < {CONFIG.risk.min_adx_for_trading}. Chop regime. Signal rejected.")
                 return None
                 
            # 6. Time filter
            if minutes_since_open < CONFIG.risk.no_trade_first_minutes:
                 logger.debug(f"Too close to open. Signal rejected.")
                 return None
            if minutes_since_open > (CONFIG.features.market_minutes - CONFIG.risk.no_trade_last_minutes):
                 logger.debug(f"Too close to close. Signal rejected.")
                 return None
                 
            # -- ALL CHECKS PASSED. COMPUTE ORDER PARAMS --
            
            side = 'buy' if signal == 'BUY' else 'sell'
            
            # Position sizing
            risk_amount = self.current_equity * CONFIG.risk.risk_per_trade
            dollar_risk = atr * CONFIG.risk.stop_loss_atr_mult
            
            if dollar_risk <= 0:
                 logger.error(f"Invalid ATR ({atr}) for risk calculation.")
                 return None
                 
            qty = int(risk_amount / dollar_risk)
            
            if qty < 1:
                 logger.debug(f"Calculated qty < 1. Adjusting to 1.")
                 qty = 1
                 
            # Stop loss
            if side == 'buy':
                stop_loss = current_price - dollar_risk
            else:
                stop_loss = current_price + dollar_risk
                
            order = {
                'symbol': symbol,
                'side': side,
                'qty': qty,
                'stop_loss': stop_loss,
                'reason': f"Signal: {signal} ({confidence:.2f}), ATR: {atr:.2f}"
            }
            
            logger.info(f"Signal APPROVED: {order}")
            return order

    def open_position(self, symbol: str, side: str, entry_price: float, qty: int, stop_loss: float):
        """Record a new position."""
        with self.lock:
             self.positions[symbol] = Position(
                 symbol=symbol,
                 side='long' if side == 'buy' else 'short',
                 entry_price=entry_price,
                 quantity=qty,
                 stop_loss=stop_loss,
                 trailing_stop=stop_loss,
                 entry_time=datetime.now()
             )
             logger.info(f"Opened {side} position in {symbol}: {qty} @ {entry_price}")

    def update_position(self, symbol: str, current_price: float, atr: float) -> str | None:
        """
        Update PnL and check stops.
        Returns 'CLOSE' if a stop is hit.
        """
        with self.lock:
             if symbol not in self.positions:
                  return None
                  
             pos = self.positions[symbol]
             
             # Update PnL
             if pos.side == 'long':
                  pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
                  
                  # Check Stop Loss / Trailing Stop
                  if current_price <= pos.trailing_stop:
                       logger.info(f"Trailing stop hit for {symbol} at {current_price}")
                       return 'CLOSE'
                       
                  # Update Trailing Stop (only moves up)
                  new_trail = current_price - (atr * CONFIG.risk.trailing_stop_atr_mult)
                  if new_trail > pos.trailing_stop:
                       pos.trailing_stop = new_trail
                       
             else: # short
                  pos.unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
                  
                  # Check Stop Loss / Trailing Stop
                  if current_price >= pos.trailing_stop:
                       logger.info(f"Trailing stop hit for {symbol} at {current_price}")
                       return 'CLOSE'
                       
                  # Update Trailing Stop (only moves down)
                  new_trail = current_price + (atr * CONFIG.risk.trailing_stop_atr_mult)
                  if new_trail < pos.trailing_stop:
                       pos.trailing_stop = new_trail
                       
             return None

    def close_position(self, symbol: str, exit_price: float) -> dict | None:
        """Close position and record PnL."""
        with self.lock:
             if symbol not in self.positions:
                  return None
                  
             pos = self.positions.pop(symbol)
             
             # Calculate final PnL
             if pos.side == 'long':
                  realized_pnl = (exit_price - pos.entry_price) * pos.quantity
             else:
                  realized_pnl = (pos.entry_price - exit_price) * pos.quantity
                  
             self.daily_pnl += realized_pnl
             self.current_equity += realized_pnl
             
             # Set cooldown if loss
             if realized_pnl < 0:
                  self.last_loss_time = datetime.now()
                  
             summary = {
                 'symbol': symbol,
                 'side': pos.side,
                 'entry_price': pos.entry_price,
                 'exit_price': exit_price,
                 'quantity': pos.quantity,
                 'pnl': realized_pnl,
                 'entry_time': pos.entry_time.isoformat(),
                 'exit_time': datetime.now().isoformat()
             }
             
             self.trade_log.append(summary)
             logger.info(f"Closed {symbol} {pos.side}. PnL: ${realized_pnl:.2f}")
             
             return summary

    def get_status(self) -> dict:
        """Get current status for dashboard."""
        with self.lock:
             drawdown_pct = (self.daily_pnl / self.daily_start_equity) * 100 if self.daily_start_equity > 0 else 0
             
             # Calculate win rate
             wins = sum(1 for t in self.trade_log if t['pnl'] > 0)
             total = len(self.trade_log)
             win_rate = (wins / total * 100) if total > 0 else 0.0
             
             return {
                 'equity': self.current_equity,
                 'daily_pnl': self.daily_pnl,
                 'drawdown_pct': drawdown_pct,
                 'kill_switch_active': self.is_kill_switch_active(),
                 'open_positions_count': len(self.positions),
                 'trade_count': total,
                 'win_rate': win_rate,
                 'positions': [
                     {
                         'symbol': p.symbol,
                         'side': p.side,
                         'unrealized_pnl': p.unrealized_pnl,
                         'entry_price': p.entry_price
                     } for p in self.positions.values()
                 ],
                 'recent_trades': self.trade_log[-CONFIG.dashboard.max_trade_log_rows:]
             }
