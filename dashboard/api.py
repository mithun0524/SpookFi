import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json

# Add the parent directory (project root) to sys.path so it can find `config.py`
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import CONFIG

app = FastAPI(title="SpookFi Phantom API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE_FILE = Path(CONFIG.log.log_dir) / "phantom_state.json"

@app.get("/api/state")
def get_state():
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        return {"error": str(e)}
    return {"status": "waiting"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
