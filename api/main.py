import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG
from core.brain import SpookFiBrain

app = FastAPI(title="SpookFi UI API")

# Initialize the Autonomous Brain
brain = SpookFiBrain()

@app.on_event("startup")
async def startup_event():
    # Start the background trading loop when FastAPI starts
    asyncio.create_task(brain.start())

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
            {"id": 1, "title": "Core Engine & ML Pipeline", "description": "Built the backtester, XGBoost model, and data ingestion.", "status": "completed"},
            {"id": 2, "title": "Frontend UI & Onboarding", "description": "Develop a premium interface to control Phantom.", "status": "completed"},
            {"id": 3, "title": "Live Paper Trading", "description": "Run the bot live on simulated streams.", "status": "current"},
            {"id": 4, "title": "Live Execution", "description": "Connect to live Alpaca funds.", "status": "upcoming"}
        ]
    }

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """Streams real-time engine status to the UI."""
    await websocket.accept()
    try:
        while True:
            # Fetch real live data from Risk Manager
            status = brain.risk_manager.get_status()
            
            # Add active regime and symbols to status
            status['regime'] = brain.market_regime
            status['active_symbols'] = brain.active_symbols
            
            # Convert status format to what the UI expects
            ui_payload = {
                "pnl_today": status.get('daily_pnl', 0.0),
                "win_rate": status.get('win_rate', 0.0),
                "active_positions": [],
                "regime": status.get('regime', 'INIT'),
                "hunted_symbols": status.get('active_symbols', [])
            }
            
            for pos in status.get('positions', []):
                ui_payload["active_positions"].append({
                    "symbol": pos.get("symbol"),
                    "side": pos.get("side"),
                    "pnl": pos.get("unrealized_pnl")
                })
                
            await websocket.send_json(ui_payload)
            await asyncio.sleep(0.5) # Update UI every 500ms
    except WebSocketDisconnect:
        pass
