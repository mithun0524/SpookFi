import streamlit as st
import json
import time
import pandas as pd
from pathlib import Path
from config import CONFIG

st.set_page_config(page_title="Phantom Dashboard", layout="wide", page_icon="👻")

# Hide Streamlit elements
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("👻 Phantom | Real-Time Momentum Scanner")

STATE_FILE = Path(CONFIG.log.log_dir) / "phantom_state.json"

def load_state():
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return None

state = load_state()

if not state:
    st.warning("No state file found. Is the Phantom engine running?")
else:
    # Top Row Metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Equity", f"${state.get('equity', 0):,.2f}")
    with col2:
        pnl = state.get('daily_pnl', 0)
        st.metric("Daily PnL", f"${pnl:,.2f}", delta=f"${pnl:,.2f}", delta_color="normal")
    with col3:
        dd = state.get('drawdown_pct', 0)
        st.metric("Daily Drawdown", f"{dd:.2f}%", delta=f"{dd:.2f}%", delta_color="inverse")
    with col4:
        st.metric("Win Rate", f"{state.get('win_rate', 0):.1f}%")
    with col5:
        st.metric("Open Positions", state.get('open_positions_count', 0))

    if state.get('kill_switch_active'):
        st.error("🚨 KILL SWITCH ACTIVE 🚨 - Maximum daily drawdown exceeded. Trading halted.")

    st.markdown("---")

    # Positions and Trades
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Open Positions")
        positions = state.get('positions', [])
        if positions:
            df_pos = pd.DataFrame(positions)
            # Format currency
            df_pos['unrealized_pnl'] = df_pos['unrealized_pnl'].map('${:,.2f}'.format)
            df_pos['entry_price'] = df_pos['entry_price'].map('${:,.2f}'.format)
            st.dataframe(df_pos, use_container_width=True, hide_index=True)
        else:
            st.info("No open positions.")

    with col_right:
        st.subheader("Recent Trades")
        trades = state.get('recent_trades', [])
        if trades:
            df_trades = pd.DataFrame(trades)
            # Sort by entry_time descending
            df_trades = df_trades.sort_values(by='entry_time', ascending=False)
            
            def color_pnl(val):
                color = 'green' if val > 0 else 'red'
                return f'color: {color}'
                
            st.dataframe(
                df_trades[['symbol', 'side', 'entry_price', 'exit_price', 'pnl']].style.map(color_pnl, subset=['pnl']),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No trades today.")

# Auto-refresh
time.sleep(CONFIG.dashboard.refresh_interval)
st.rerun()
