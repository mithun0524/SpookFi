import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Settings, Zap, Shield, ChevronDown, Check, Activity } from 'lucide-react';
import './index.css';

export default function App() {
  const [state, setState] = useState(null);
  const [theme, setTheme] = useState('cyber'); // 'cyber' or 'luxury'

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
      <div className={`theme-${theme} flex h-screen w-full items-center justify-center`}>
        <motion.div 
          animate={{ scale: [0.95, 1.05, 0.95], opacity: [0.5, 1, 0.5] }}
          transition={{ repeat: Infinity, duration: 2 }}
          className="flex flex-col items-center gap-4"
        >
          <Activity size={48} className={theme === 'cyber' ? 'text-cyber-accent' : 'text-luxury-accent'} />
          <div className="font-display text-xl tracking-widest uppercase">Initializing Neural Core...</div>
        </motion.div>
      </div>
    );
  }

  const equityHist = state.equity_history || [];
  const signals = state.latest_signals || {};
  const activePairs = Object.keys(signals).length;
  const positions = state.positions || [];
  const trades = state.recent_trades || [];

  // Theme-specific config
  const chartColor = theme === 'cyber' ? '#22d3ee' : '#d4af37';
  const chartFill = theme === 'cyber' ? 'rgba(34, 211, 238, 0.1)' : 'rgba(212, 175, 55, 0.1)';

  return (
    <div className={`theme-${theme} min-h-screen transition-colors duration-700`}>
      <div className="max-w-[1600px] mx-auto p-6 lg:p-12 relative z-10">
        
        {/* HEADER */}
        <motion.header 
          initial={{ y: -50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          className="flex justify-between items-end mb-12"
        >
          <div>
            <h1 className="text-5xl font-bold font-display tracking-tighter mb-2">
              <span className="gradient-text">SpookFi</span> Engine
            </h1>
            <p className="font-body text-sm uppercase tracking-widest opacity-60">Autonomous Momentum Synthesizer</p>
          </div>
          
          <div className="flex gap-4">
            <button 
              onClick={() => setTheme('cyber')}
              className={`px-4 py-2 rounded-full font-body text-xs font-bold uppercase tracking-wider transition-all ${theme === 'cyber' ? 'bg-cyber-accent text-black shadow-[0_0_15px_rgba(34,211,238,0.5)]' : 'bg-white/5 hover:bg-white/10'}`}
            >
              Cyberpunk
            </button>
            <button 
              onClick={() => setTheme('luxury')}
              className={`px-4 py-2 rounded-full font-body text-xs font-bold uppercase tracking-wider transition-all ${theme === 'luxury' ? 'bg-luxury-accent text-black shadow-[0_0_15px_rgba(212,175,55,0.3)]' : 'bg-white/5 hover:bg-white/10'}`}
            >
              Luxury
            </button>
          </div>
        </motion.header>

        {/* KILL SWITCH ALERT */}
        <AnimatePresence>
          {state.kill_switch_active && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className={`mb-8 overflow-hidden`}
            >
              <div className={`p-4 rounded-xl flex items-center gap-4 ${theme === 'cyber' ? 'bg-cyber-danger/20 border border-cyber-danger text-cyber-danger' : 'bg-luxury-danger/10 border border-luxury-danger text-luxury-danger'}`}>
                <Shield size={24} />
                <span className="font-display font-bold uppercase tracking-wider">Maximum drawdown reached. Trading suspended.</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* METRICS ROW */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-10"
        >
          <MetricCard theme={theme} title="Net Equity" value={`$${state.equity.toLocaleString(undefined, {minimumFractionDigits: 2})}`} />
          <MetricCard theme={theme} title="Session PnL" value={`$${(state.daily_pnl || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}`} highlight={(state.daily_pnl || 0) >= 0} />
          <MetricCard theme={theme} title="Drawdown" value={`${(state.drawdown_pct || 0).toFixed(2)}%`} isDanger />
          <MetricCard theme={theme} title="Win Rate" value={`${(state.win_rate || 0).toFixed(1)}%`} />
          <MetricCard theme={theme} title="Active Assets" value={activePairs} />
        </motion.div>

        {/* CHARTS ROW */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10"
        >
          <div className="lg:col-span-1 glass-panel flex flex-col h-[400px]">
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <h3 className="font-display font-bold text-lg tracking-wide uppercase opacity-90">Signal Matrix</h3>
              <Zap size={18} className="opacity-50" />
            </div>
            <div className="overflow-y-auto flex-1 p-2 custom-scrollbar">
              <table className="w-full text-left font-body text-sm">
                <tbody>
                  {Object.entries(signals).map(([sym, data], idx) => (
                    <motion.tr 
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.05 }}
                      key={sym} 
                      className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors"
                    >
                      <td className="p-4 font-medium">{sym.replace('/USD', '')}</td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded text-xs font-bold uppercase tracking-wider ${
                          data.signal === 'BUY' ? (theme==='cyber'?'bg-cyber-accent/20 text-cyber-accent':'bg-luxury-accent/20 text-luxury-accent') :
                          data.signal === 'SELL' ? (theme==='cyber'?'bg-cyber-danger/20 text-cyber-danger':'bg-luxury-danger/20 text-luxury-danger') :
                          'bg-white/10 opacity-50'
                        }`}>
                          {data.signal}
                        </span>
                      </td>
                      <td className="p-4 opacity-70 text-right">{(data.confidence * 100).toFixed(1)}%</td>
                    </motion.tr>
                  ))}
                  {Object.keys(signals).length === 0 && (
                    <tr><td colSpan="3" className="p-8 text-center opacity-50">Calibrating matrix...</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="lg:col-span-2 glass-panel flex flex-col h-[400px]">
             <div className="p-6 border-b border-white/5 flex justify-between items-center">
              <h3 className="font-display font-bold text-lg tracking-wide uppercase opacity-90">Live Equity Curve</h3>
            </div>
            <div className="p-6 flex-1">
              {equityHist.length > 1 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityHist}>
                    <defs>
                      <linearGradient id="colorEq" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={chartColor} stopOpacity={0.4}/>
                        <stop offset="95%" stopColor={chartColor} stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="t" hide />
                    <YAxis domain={['auto', 'auto']} stroke="rgba(255,255,255,0.1)" tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12, fontFamily: 'Outfit'}} width={60} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: theme==='cyber'?'#0a0a0c':'#0f1115', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', fontFamily: 'Outfit' }} 
                      formatter={(value) => [`$${value.toFixed(2)}`, 'Equity']}
                      labelFormatter={() => ''}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="v" 
                      stroke={chartColor} 
                      strokeWidth={3} 
                      fill="url(#colorEq)" 
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center opacity-50">Mapping telemetry points...</div>
              )}
            </div>
          </div>
        </motion.div>

        {/* LEDGERS ROW */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="grid grid-cols-1 lg:grid-cols-2 gap-6"
        >
          <div className="glass-panel">
            <div className="p-5 border-b border-white/5">
              <h3 className="font-display font-bold text-base uppercase opacity-80">Active Operations</h3>
            </div>
            <div className="p-2 overflow-x-auto">
              <table className="w-full text-left font-body text-sm">
                <thead>
                  <tr className="opacity-50 text-xs uppercase tracking-wider">
                    <th className="p-4 font-normal">Asset</th>
                    <th className="p-4 font-normal">Side</th>
                    <th className="p-4 font-normal">Entry</th>
                    <th className="p-4 font-normal text-right">Unrealized PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos, idx) => (
                    <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="p-4 font-bold">{pos.symbol}</td>
                      <td className="p-4 uppercase text-xs tracking-wider opacity-80">{pos.side}</td>
                      <td className="p-4 font-mono text-xs opacity-70">${pos.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                      <td className={`p-4 font-bold text-right ${pos.unrealized_pnl >= 0 ? (theme==='cyber'?'text-cyber-accent':'text-luxury-accent') : (theme==='cyber'?'text-cyber-danger':'text-luxury-danger')}`}>
                        ${pos.unrealized_pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}
                      </td>
                    </tr>
                  ))}
                  {positions.length === 0 && <tr><td colSpan="4" className="p-8 text-center opacity-40 italic">No active vectors.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass-panel">
            <div className="p-5 border-b border-white/5">
              <h3 className="font-display font-bold text-base uppercase opacity-80">Execution Ledger</h3>
            </div>
            <div className="p-2 overflow-x-auto max-h-[300px] overflow-y-auto custom-scrollbar">
              <table className="w-full text-left font-body text-sm">
                <thead>
                  <tr className="opacity-50 text-xs uppercase tracking-wider">
                    <th className="p-4 font-normal">Asset</th>
                    <th className="p-4 font-normal">Side</th>
                    <th className="p-4 font-normal">Exit</th>
                    <th className="p-4 font-normal text-right">Realized PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {[...trades].reverse().map((t, idx) => (
                    <tr key={idx} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="p-4 font-bold">{t.symbol}</td>
                      <td className="p-4 uppercase text-xs tracking-wider opacity-80">{t.side}</td>
                      <td className="p-4 font-mono text-xs opacity-70">${t.exit_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                      <td className={`p-4 font-bold text-right ${t.pnl >= 0 ? (theme==='cyber'?'text-cyber-accent':'text-luxury-accent') : (theme==='cyber'?'text-cyber-danger':'text-luxury-danger')}`}>
                        ${t.pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}
                      </td>
                    </tr>
                  ))}
                  {trades.length === 0 && <tr><td colSpan="4" className="p-8 text-center opacity-40 italic">Awaiting execution...</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </motion.div>

      </div>
    </div>
  );
}

function MetricCard({ theme, title, value, highlight, isDanger }) {
  let valColor = "text-white";
  if (highlight) valColor = theme === 'cyber' ? "text-cyber-accent" : "text-luxury-accent";
  if (isDanger) valColor = theme === 'cyber' ? "text-cyber-danger" : "text-luxury-danger";

  return (
    <motion.div 
      whileHover={{ y: -5, scale: 1.02 }}
      className="glass-panel p-6"
    >
      <div className="font-body text-xs uppercase tracking-widest opacity-50 mb-2">{title}</div>
      <div className={`font-display text-3xl font-bold tracking-tight ${valColor}`}>{value}</div>
    </motion.div>
  );
}
