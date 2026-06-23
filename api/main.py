"""
SpookFi FastAPI — Web UI Server
Serves the HTML frontend and streams live engine state via WebSocket.
"""
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG
from core.brain import SpookFiBrain
from notifications.telegram import alert_engine_status

app = FastAPI(title="SpookFi UI API")

# Initialize the Autonomous Brain
brain = SpookFiBrain()


@app.on_event("startup")
async def startup_event():
    """Start the background trading loop and notify Telegram."""
    asyncio.create_task(brain.start())
    asyncio.create_task(
        alert_engine_status("started", "SpookFi engine is live and hunting.")
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Notify Telegram on shutdown."""
    asyncio.create_task(
        alert_engine_status("stopped", "SpookFi engine shut down.")
    )


# Mount the UI directory as static files
ui_dir = Path(__file__).parent.parent / "ui"
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(ui_dir / "index.html") as f:
        return f.read()


@app.get("/api/roadmap")
async def get_roadmap():
    return {
        "stages": [
            {"id": 1, "title": "Core Engine & ML Pipeline",
             "description": "Built the backtester, XGBoost model, and data ingestion.",
             "status": "completed"},
            {"id": 2, "title": "Frontend UI & Onboarding",
             "description": "Developed a premium neo-brutalist interface with live WebSocket.",
             "status": "completed"},
            {"id": 3, "title": "Live Paper Trading",
             "description": "Running live on yfinance streams with full risk management.",
             "status": "current"},
            {"id": 4, "title": "Live Execution",
             "description": "Connect to live Alpaca funds for real capital deployment.",
             "status": "upcoming"},
        ]
    }


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """Streams real-time engine status (positions, equity curve, trades) to the UI."""
    await websocket.accept()
    try:
        while True:
            status = brain.risk_manager.get_status()

            ui_payload = {
                # Core metrics
                "pnl_today": status.get("daily_pnl", 0.0),
                "win_rate": status.get("win_rate", 0.0),
                "equity": status.get("equity", 0.0),
                "drawdown_pct": status.get("drawdown_pct", 0.0),
                "trade_count": status.get("trade_count", 0),
                "kill_switch": status.get("kill_switch_active", False),

                # Engine context
                "regime": brain.market_regime,
                "hunted_symbols": brain.active_symbols,

                # Live chart data (last 200 points max for payload size)
                "equity_history": status.get("equity_history", [])[-200:],

                # Positions table
                "active_positions": [
                    {
                        "symbol": p["symbol"],
                        "side": p["side"],
                        "pnl": p["unrealized_pnl"],
                        "entry": p["entry_price"],
                        "tp": p.get("take_profit", 0),
                        "sl": p.get("trailing_stop", 0),
                    }
                    for p in status.get("positions", [])
                ],

                # Recent trades table
                "recent_trades": status.get("recent_trades", [])[-20:],
            }

            await websocket.send_json(ui_payload)
            await asyncio.sleep(1.0)  # Push update every second

    except WebSocketDisconnect:
        pass
    except Exception as e:
        pass
