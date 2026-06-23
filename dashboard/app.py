import sys
from pathlib import Path
import streamlit as st
import json
import time
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# Add the parent directory (project root) to sys.path so it can find `config.py`
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import CONFIG

st.set_page_config(page_title="SpookFi Analytics", layout="wide", page_icon="▲")

# Vercel-style Enterprise SaaS CSS
custom_css = """
<style>
    /* Global Backgrounds & Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    .stApp {
        background-color: #fafafa;
        color: #111111;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Hide Streamlit Header & Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Metrics Boxes */
    div[data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        color: #000000 !important;
        letter-spacing: -0.02em;
    }
    div[data-testid="stMetricDelta"] {
        font-size: 1rem !important;
        font-weight: 500 !important;
    }
    
    /* Headers */
    h1 {
        color: #000000 !important;
        font-weight: 700;
        font-size: 2rem !important;
        letter-spacing: -0.02em;
        margin-bottom: 0px !important;
        padding-bottom: 0px !important;
    }
    h3 {
        color: #444444 !important;
        font-weight: 600;
        font-size: 1.1rem !important;
        text-transform: none;
        letter-spacing: 0px;
        margin-top: 20px;
    }
    
    /* Subtitle */
    .subtitle {
        color: #666666;
        font-size: 0.95rem;
        font-weight: 400;
        margin-bottom: 30px;
    }
    
    /* Dataframe overrides */
    .stDataFrame {
        border-radius: 6px;
        overflow: hidden;
        border: 1px solid #eaeaea;
        background-color: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    
    /* Dividers */
    hr {
        border-color: #eaeaea !important;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

st.markdown("<h1>SpookFi Analytics</h1>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Real-time crypto momentum intelligence engine</div>", unsafe_allow_html=True)

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
    st.info("Awaiting telemetry from the Phantom Engine...")
else:
    # ---------------------------------------------------------
    # TOP METRICS ROW
    # ---------------------------------------------------------
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Equity", f"${state.get('equity', 0):,.2f}")
    with col2:
        pnl = state.get('daily_pnl', 0)
        st.metric("Daily PnL", f"${pnl:,.2f}", delta=f"${pnl:,.2f}")
    with col3:
        dd = state.get('drawdown_pct', 0)
        st.metric("Daily Drawdown", f"{dd:.2f}%", delta=f"{dd:.2f}%", delta_color="inverse")
    with col4:
        st.metric("Win Rate", f"{state.get('win_rate', 0):.1f}%")
    with col5:
        st.metric("Active Pairs", len(CONFIG.universe.crypto_symbols))

    if state.get('kill_switch_active'):
        st.error("Maximum daily drawdown exceeded. Trading halted.")

    st.markdown("---")

    # ---------------------------------------------------------
    # CHARTS & ANALYTICS ROW
    # ---------------------------------------------------------
    col_matrix, col_chart = st.columns([1, 2])
    
    with col_matrix:
        st.markdown("### Ensemble Signals")
        signals = state.get('latest_signals', {})
        if signals:
            sig_list = []
            for sym, data in signals.items():
                sig_list.append({
                    "Asset": sym.replace("/USD", ""),
                    "Signal": data['signal'],
                    "Confidence": f"{data['confidence']*100:.1f}%"
                })
            df_sig = pd.DataFrame(sig_list)
            
            def color_signal(val):
                if val == 'BUY':
                    return 'color: #0070f3; font-weight: 600;' # Vercel Blue
                elif val == 'SELL':
                    return 'color: #e00; font-weight: 600;'    # Vercel Red
                return 'color: #666;'
                
            st.dataframe(
                df_sig.style.map(color_signal, subset=['Signal']),
                use_container_width=True,
                hide_index=True,
                height=350
            )
        else:
            st.markdown("<span style='color:#666; font-size: 0.9rem;'>Scanning market data...</span>", unsafe_allow_html=True)
            
    with col_chart:
        st.markdown("### Equity Curve")
        equity_hist = state.get('equity_history', [])
        if equity_hist and len(equity_hist) > 1:
            df_eq = pd.DataFrame(equity_hist)
            df_eq['t'] = pd.to_datetime(df_eq['t'])
            fig = px.area(
                df_eq, x='t', y='v', 
                color_discrete_sequence=['#000000'],
                template='plotly_white'
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="",
                yaxis_title="Account Balance ($)",
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(gridcolor='#eaeaea', zerolinecolor='#eaeaea', color='#666'),
                xaxis=dict(gridcolor='#eaeaea', zerolinecolor='#eaeaea', color='#666')
            )
            fig.update_traces(fillcolor='rgba(0, 0, 0, 0.04)', line=dict(width=2))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("<span style='color:#666; font-size: 0.9rem;'>Gathering historical equity data points...</span>", unsafe_allow_html=True)

    st.markdown("---")

    # ---------------------------------------------------------
    # POSITIONS & EXECUTIONS
    # ---------------------------------------------------------
    col_pos, col_trades = st.columns(2)
    with col_pos:
        st.markdown("### Open Positions")
        positions = state.get('positions', [])
        if positions:
            df_pos = pd.DataFrame(positions)
            df_pos['unrealized_pnl'] = df_pos['unrealized_pnl'].map('${:,.2f}'.format)
            df_pos['entry_price'] = df_pos['entry_price'].map('${:,.2f}'.format)
            st.dataframe(df_pos[['symbol', 'side', 'entry_price', 'unrealized_pnl']], use_container_width=True, hide_index=True)
        else:
            st.markdown("<span style='color:#666; font-size: 0.9rem;'>No active positions.</span>", unsafe_allow_html=True)

    with col_trades:
        st.markdown("### Execution Ledger")
        trades = state.get('recent_trades', [])
        if trades:
            df_trades = pd.DataFrame(trades)
            df_trades = df_trades.sort_values(by='entry_time', ascending=False)
            
            def color_pnl(val):
                color = '#0070f3' if val > 0 else '#e00'
                return f'color: {color}; font-weight: 500;'
                
            st.dataframe(
                df_trades[['symbol', 'side', 'entry_price', 'exit_price', 'pnl']].style.map(color_pnl, subset=['pnl']),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.markdown("<span style='color:#666; font-size: 0.9rem;'>No executions today.</span>", unsafe_allow_html=True)

# Auto-refresh loop
time.sleep(1)
st.rerun()
