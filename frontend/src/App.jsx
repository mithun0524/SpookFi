import React, { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import './index.css';

export default function App() {
  const [state, setState] = useState(null);

  useEffect(() => {
    const fetchState = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/state');
        if (res.ok) {
          const data = await res.json();
          setState(data);
        }
      } catch (err) {
        console.error("Failed to fetch state", err);
      }
    };
    
    fetchState();
    const interval = setInterval(fetchState, 1000);
    return () => clearInterval(interval);
  }, []);

  if (!state || state.status === "waiting" || !state.equity) {
    return (
      <div className="loading-screen">
        <div className="animate-pulse">Awaiting telemetry from the Phantom Engine...</div>
      </div>
    );
  }

  const equityHist = state.equity_history || [];
  const signals = state.latest_signals || {};
  const activePairs = Object.keys(signals).length;
  const positions = state.positions || [];
  const trades = state.recent_trades || [];

  return (
    <div className="dashboard-container">
      <header className="header">
        <h1>SpookFi Analytics</h1>
        <p>Real-time crypto momentum intelligence engine</p>
      </header>

      {state.kill_switch_active && (
        <div className="alert-error">
          <strong>Maximum daily drawdown exceeded. Trading halted.</strong>
        </div>
      )}

      {/* TOP METRICS ROW */}
      <div className="metrics-row">
        <MetricCard title="Total Equity" value={`$${state.equity.toLocaleString(undefined, {minimumFractionDigits: 2})}`} />
        <MetricCard 
          title="Daily PnL" 
          value={`$${(state.daily_pnl || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}`} 
        />
        <MetricCard 
          title="Daily Drawdown" 
          value={`${(state.drawdown_pct || 0).toFixed(2)}%`} 
        />
        <MetricCard title="Win Rate" value={`${(state.win_rate || 0).toFixed(1)}%`} />
        <MetricCard title="Active Pairs" value={activePairs} />
      </div>

      <hr className="divider" />

      {/* CHARTS & ANALYTICS */}
      <div className="analytics-row">
        <div>
          <h3 className="section-title">Ensemble Signals</h3>
          <div className="panel panel-scrollable">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Signal</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(signals).map(([sym, data], idx) => (
                  <tr key={idx}>
                    <td>{sym.replace('/USD', '')}</td>
                    <td className={data.signal === 'BUY' ? 'text-blue' : data.signal === 'SELL' ? 'text-red' : 'text-gray'}>
                      {data.signal}
                    </td>
                    <td>{(data.confidence * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {Object.keys(signals).length === 0 && (
              <div className="empty-state">Scanning market data...</div>
            )}
          </div>
        </div>

        <div>
          <h3 className="section-title">Equity Curve</h3>
          <div className="panel panel-padded">
            {equityHist.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityHist} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
                  <XAxis dataKey="t" hide />
                  <YAxis domain={['auto', 'auto']} stroke="#eaeaea" tick={{fill: '#666', fontSize: 12}} width={80} />
                  <Tooltip 
                    contentStyle={{ borderRadius: '6px', border: '1px solid #eaeaea', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }} 
                    formatter={(value) => [`$${value.toFixed(2)}`, 'Equity']}
                    labelFormatter={() => ''}
                  />
                  <Area type="monotone" dataKey="v" stroke="#000" fill="rgba(0,0,0,0.04)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty-state">
                Gathering historical equity data points...
              </div>
            )}
          </div>
        </div>
      </div>

      <hr className="divider" />

      {/* POSITIONS & EXECUTIONS */}
      <div className="positions-row">
        <div>
          <h3 className="section-title">Open Positions</h3>
          <div className="panel">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Entry Price</th>
                  <th>Unrealized PnL</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx}>
                    <td>{pos.symbol}</td>
                    <td className="capitalize">{pos.side}</td>
                    <td>${pos.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                    <td className={pos.unrealized_pnl >= 0 ? 'text-blue' : 'text-red'}>
                      ${pos.unrealized_pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {positions.length === 0 && (
              <div className="empty-state" style={{ height: 'auto', padding: '1.5rem' }}>No active positions.</div>
            )}
          </div>
        </div>

        <div>
          <h3 className="section-title">Execution Ledger</h3>
          <div className="panel">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Exit Price</th>
                  <th>Realized PnL</th>
                </tr>
              </thead>
              <tbody>
                {[...trades].reverse().map((t, idx) => (
                  <tr key={idx}>
                    <td>{t.symbol}</td>
                    <td className="capitalize">{t.side}</td>
                    <td>${t.exit_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                    <td className={t.pnl >= 0 ? 'text-blue' : 'text-red'}>
                      ${t.pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {trades.length === 0 && (
              <div className="empty-state" style={{ height: 'auto', padding: '1.5rem' }}>No executions today.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value }) {
  return (
    <div className="metric-card">
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
