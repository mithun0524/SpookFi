/**
 * SpookFi UI — WebSocket Client & Dashboard Logic
 * Handles live equity chart, trade log, positions, and navigation.
 */

// ─── Chart Setup ─────────────────────────────────────────────────────────────

let equityChart = null;
let fullEquityHistory = [];   // All points received from WS
let chartRange = 'all';       // 'all' | number string

function initChart() {
    const ctx = document.getElementById('equity-chart').getContext('2d');

    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, 'rgba(168, 85, 247, 0.35)');
    gradient.addColorStop(1, 'rgba(168, 85, 247, 0.0)');

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Portfolio Equity',
                data: [],
                borderColor: '#a855f7',
                backgroundColor: gradient,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointHoverBackgroundColor: '#a855f7',
                tension: 0.4,
                fill: true,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            animation: { duration: 250 },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 15, 30, 0.95)',
                    borderColor: 'rgba(168, 85, 247, 0.4)',
                    borderWidth: 1,
                    titleColor: '#a0a0c0',
                    bodyColor: '#e0e0ff',
                    callbacks: {
                        label: ctx => `₹${ctx.parsed.y.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#6b7280',
                        maxTicksLimit: 8,
                        maxRotation: 0,
                    }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.04)' },
                    ticks: {
                        color: '#6b7280',
                        callback: v => '₹' + (v / 1000).toFixed(1) + 'k'
                    }
                }
            }
        }
    });
}

function updateChart(history) {
    if (!equityChart || !history || history.length === 0) return;

    // Apply range filter
    let filtered = history;
    if (chartRange !== 'all') {
        const n = parseInt(chartRange);
        filtered = history.slice(-n);
    }

    const labels = filtered.map(p => {
        const d = new Date(p.t);
        return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    });
    const values = filtered.map(p => p.v);

    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = values;
    equityChart.update('none');  // 'none' = no animation for live updates

    // Update perf stats
    if (values.length > 0) {
        const first = values[0];
        const last = values[values.length - 1];
        const peak = Math.max(...values);
        const peakIdx = values.indexOf(peak);
        const troughAfterPeak = Math.min(...values.slice(peakIdx));
        const maxDD = peak > 0 ? ((troughAfterPeak - peak) / peak * 100) : 0;
        const totalReturn = first > 0 ? ((last - first) / first * 100) : 0;

        setText('perf-peak', `₹${peak.toLocaleString('en-IN')}`);
        const ddEl = document.getElementById('perf-maxdd');
        ddEl.textContent = `${maxDD.toFixed(2)}%`;
        ddEl.className = 'chart-stat-value ' + (maxDD < 0 ? 'negative' : '');

        const retEl = document.getElementById('perf-return');
        retEl.textContent = `${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%`;
        retEl.className = 'chart-stat-value ' + (totalReturn >= 0 ? 'positive' : 'negative');
    }
}

// ─── WebSocket Connection ─────────────────────────────────────────────────────

let ws = null;
let reconnectDelay = 1000;
let lastData = null;

function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/status`);

    ws.onopen = () => {
        reconnectDelay = 1000;
        setStatus('live', 'Engine Online');
        console.log('[SpookFi] WebSocket connected');
    };

    ws.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data);
            lastData = data;
            updateDashboard(data);
        } catch (e) {
            console.error('[SpookFi] Parse error:', e);
        }
    };

    ws.onclose = () => {
        setStatus('connecting', 'Reconnecting...');
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
    };

    ws.onerror = () => {
        setStatus('error', 'Connection Error');
        ws.close();
    };
}

// ─── Dashboard Update ─────────────────────────────────────────────────────────

function updateDashboard(data) {
    // ── Top stats
    const pnl = data.pnl_today || 0;
    const pnlEl = document.getElementById('dash-pnl');
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}₹${Math.abs(pnl).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    pnlEl.className = `value ${pnl >= 0 ? 'positive' : 'negative'}`;

    setText('dash-equity', `₹${(data.equity || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`);
    setText('dash-winrate', `${(data.win_rate || 0).toFixed(1)}%`);
    setText('dash-tradecount', `${data.trade_count || 0} trades`);
    setText('dash-positions-count', (data.active_positions || []).length);
    setText('dash-drawdown', `Drawdown: ${(data.drawdown_pct || 0).toFixed(2)}%`);
    setText('dash-regime', data.regime || 'INIT');

    // Hunted symbols pill list
    const huntedEl = document.getElementById('dash-hunted');
    if (data.hunted_symbols && data.hunted_symbols.length > 0) {
        huntedEl.innerHTML = data.hunted_symbols
            .map(s => `<span class="symbol-pill">${s}</span>`)
            .join('');
    } else {
        huntedEl.textContent = 'Scanning Universe...';
    }

    // Kill switch banner
    const ksEl = document.getElementById('kill-switch-banner');
    if (data.kill_switch) {
        ksEl.style.display = 'flex';
    } else {
        ksEl.style.display = 'none';
    }

    // ── Positions table
    const tbody = document.getElementById('positions-tbody');
    const positions = data.active_positions || [];
    setText('positions-badge', `${positions.length} open`);
    if (positions.length === 0) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="6">No open positions — the ghost is hunting 👻</td></tr>`;
    } else {
        tbody.innerHTML = positions.map(p => {
            const pnlClass = p.pnl >= 0 ? 'positive' : 'negative';
            const sideClass = p.side === 'long' ? 'side-long' : 'side-short';
            return `<tr>
                <td><strong>${p.symbol}</strong></td>
                <td><span class="badge ${sideClass}">${p.side.toUpperCase()}</span></td>
                <td class="text-right">₹${(p.entry || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                <td class="text-right positive">₹${(p.tp || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                <td class="text-right negative">₹${(p.sl || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                <td class="text-right ${pnlClass}"><strong>${p.pnl >= 0 ? '+' : ''}₹${Math.abs(p.pnl).toFixed(2)}</strong></td>
            </tr>`;
        }).join('');
    }

    // ── Equity chart (live update)
    if (data.equity_history && data.equity_history.length > 0) {
        fullEquityHistory = data.equity_history;
        updateChart(fullEquityHistory);
        setText('perf-winrate', `${(data.win_rate || 0).toFixed(1)}%`);
    }

    // ── Trade log
    const trades = data.recent_trades || [];
    setText('trades-badge', `${data.trade_count || 0} total`);
    const tradesTbody = document.getElementById('trades-tbody');
    if (trades.length === 0) {
        tradesTbody.innerHTML = `<tr class="empty-row"><td colspan="7">No trades yet — model is warming up 🔥</td></tr>`;
    } else {
        tradesTbody.innerHTML = [...trades].reverse().map(t => {
            const pnlClass = t.pnl >= 0 ? 'positive' : 'negative';
            const exitTime = t.exit_time ? new Date(t.exit_time).toLocaleTimeString('en-IN', {hour: '2-digit', minute: '2-digit'}) : '—';
            return `<tr>
                <td><strong>${t.symbol}</strong></td>
                <td>${t.side}</td>
                <td class="text-right">₹${(t.entry_price || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                <td class="text-right">₹${(t.exit_price || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                <td class="text-right">${t.quantity || 0}</td>
                <td class="text-right ${pnlClass}"><strong>${t.pnl >= 0 ? '+' : ''}₹${Math.abs(t.pnl).toFixed(2)}</strong></td>
                <td>${exitTime}</td>
            </tr>`;
        }).join('');
    }
}

// ─── Navigation ───────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        const tab = item.dataset.tab;
        document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
        item.classList.add('active');
        document.getElementById(tab).classList.add('active');

        // Fetch roadmap data on demand
        if (tab === 'roadmap' && !document.getElementById('roadmap-container').dataset.loaded) {
            loadRoadmap();
        }
    });
});

// ─── Chart Range Controls ─────────────────────────────────────────────────────

document.querySelectorAll('.chart-range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-range-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        chartRange = btn.dataset.range;
        updateChart(fullEquityHistory);
    });
});

// ─── Theme Toggle ─────────────────────────────────────────────────────────────

const themeToggle = document.getElementById('theme-toggle');
const lightIcon = document.getElementById('theme-icon-light');
const darkIcon = document.getElementById('theme-icon-dark');
const themeText = document.getElementById('theme-text');

themeToggle.addEventListener('click', () => {
    const isDark = document.documentElement.dataset.theme === 'dark';
    document.documentElement.dataset.theme = isDark ? 'light' : 'dark';
    lightIcon.style.display = isDark ? 'none' : '';
    darkIcon.style.display = isDark ? '' : 'none';
    themeText.textContent = isDark ? 'Dark Mode' : 'Light Mode';
});

// ─── Roadmap Loader ───────────────────────────────────────────────────────────

async function loadRoadmap() {
    const container = document.getElementById('roadmap-container');
    try {
        const res = await fetch('/api/roadmap');
        const data = await res.json();
        container.dataset.loaded = 'true';
        container.innerHTML = data.stages.map(s => {
            const icons = { completed: 'ph-check-circle', current: 'ph-spinner', upcoming: 'ph-circle-dashed' };
            const icon = icons[s.status] || 'ph-circle';
            return `<div class="roadmap-item ${s.status}">
                <div class="roadmap-icon"><i class="ph-fill ${icon}"></i></div>
                <div class="roadmap-content">
                    <div class="roadmap-title">Stage ${s.id}: ${s.title}</div>
                    <div class="roadmap-desc">${s.description}</div>
                </div>
                <div class="roadmap-badge ${s.status}">${s.status}</div>
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = `<p style="padding: 1rem; opacity: 0.5;">Could not load roadmap.</p>`;
    }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setStatus(state, label) {
    const indicator = document.querySelector('#connection-status .status-indicator');
    const labelEl = document.getElementById('status-label');
    if (indicator) indicator.className = `status-indicator ${state}`;
    if (labelEl) labelEl.textContent = label;
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

initChart();
connect();
