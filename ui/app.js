document.addEventListener("DOMContentLoaded", () => {
    
    // --- Theme Toggling Logic ---
    const themeToggleBtn = document.getElementById('theme-toggle');
    const themeIconLight = document.getElementById('theme-icon-light');
    const themeIconDark = document.getElementById('theme-icon-dark');
    const themeText = document.getElementById('theme-text');
    const htmlEl = document.documentElement;

    // Check localStorage for saved theme, default to dark
    const savedTheme = localStorage.getItem('spookfi-theme') || 'dark';
    setTheme(savedTheme);

    themeToggleBtn.addEventListener('click', () => {
        const currentTheme = htmlEl.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    });

    function setTheme(theme) {
        htmlEl.setAttribute('data-theme', theme);
        localStorage.setItem('spookfi-theme', theme);
        
        if (theme === 'dark') {
            themeIconLight.style.display = 'block';
            themeIconDark.style.display = 'none';
            themeText.textContent = 'Light Mode';
        } else {
            themeIconLight.style.display = 'none';
            themeIconDark.style.display = 'block';
            themeText.textContent = 'Dark Mode';
        }
    }

    // --- Tab Switching Logic ---
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active from all
            navItems.forEach(n => n.classList.remove('active'));
            tabContents.forEach(t => t.classList.remove('active'));

            // Add active to clicked
            item.classList.add('active');
            const targetId = item.getAttribute('data-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });



    // --- Live WebSocket Streaming ---
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/status`;
    
    function connectWebSocket() {
        const socket = new WebSocket(wsUrl);
        
        socket.onopen = () => {
            console.log("WebSocket connected to SpookFi Engine.");
            document.querySelector('.status-indicator').classList.add('live');
        };
        
        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            // Update Dashboard PnL
            const pnlEl = document.getElementById('dash-pnl');
            pnlEl.textContent = `${data.pnl_today >= 0 ? '+' : '-'}₹${Math.abs(data.pnl_today).toFixed(2)}`;
            pnlEl.className = `value ${data.pnl_today >= 0 ? 'positive' : 'negative'}`;

            // Update Metrics
            document.getElementById('dash-winrate').textContent = `${(data.win_rate * 100).toFixed(1)}%`;
            document.getElementById('dash-positions-count').textContent = data.active_positions.length;
            
            // Update Brain Specifics
            if (data.regime) {
                document.getElementById('dash-regime').textContent = data.regime.toUpperCase();
            }
            if (data.hunted_symbols && data.hunted_symbols.length > 0) {
                document.getElementById('dash-hunted').textContent = data.hunted_symbols.join(', ');
            }

            // Update Positions Table
            const tbody = document.getElementById('positions-tbody');
            tbody.innerHTML = '';
            data.active_positions.forEach(pos => {
                const tr = document.createElement('tr');
                const pnlClass = pos.pnl >= 0 ? 'positive' : 'negative';
                tr.innerHTML = `
                    <td><strong>${pos.symbol}</strong></td>
                    <td style="text-transform: capitalize;">
                        <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--${pos.side==='long'?'positive':'negative'}); margin-right:6px;"></span>
                        ${pos.side}
                    </td>
                    <td class="text-right ${pnlClass}">${pos.pnl >= 0 ? '+' : '-'}₹${Math.abs(pos.pnl).toFixed(2)}</td>
                `;
                tbody.appendChild(tr);
            });
        };
        
        socket.onclose = () => {
            console.log("WebSocket disconnected. Reconnecting in 2s...");
            document.querySelector('.status-indicator').classList.remove('live');
            setTimeout(connectWebSocket, 2000);
        };
    }
    
    // Start connection
    connectWebSocket();

    // Load Roadmap
    fetch('/api/roadmap')
        .then(res => res.json())
        .then(data => {
            const container = document.getElementById('roadmap-container');
            container.innerHTML = '';
            
            data.stages.forEach((stage, idx) => {
                const html = `
                    <div class="roadmap-item ${stage.status}">
                        <div class="roadmap-status-col">
                            <div class="stage-dot"></div>
                            <div class="stage-line"></div>
                        </div>
                        <div class="roadmap-content">
                            <div class="roadmap-header">
                                <h3>Stage ${stage.id}: ${stage.title}</h3>
                                <span class="badge ${stage.status}">${stage.status}</span>
                            </div>
                            <p>${stage.description}</p>
                        </div>
                    </div>
                `;
                container.innerHTML += html;
            });
        });
});
