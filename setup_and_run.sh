#!/bin/bash
set -e

echo "👻 Starting Phantom Multi-Market Setup..."

cd /Users/mithunchavan/algoTrade

echo "[1/4] Creating virtual environment and installing dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -q

echo "[2/4] Fetching historical data (Stocks & Crypto)..."
python3 main.py fetch

echo "[3/4] Training XGBoost model..."
python3 main.py train

echo "[4/4] Running backtest for BTC/USD to verify crypto edge..."
python3 main.py backtest --symbol BTC/USD --days 30

echo "✅ Setup Complete! Check the logs/ folder for the backtest HTML report."
echo "To run live: source venv/bin/activate && python3 main.py run"
echo "To view dashboard: source venv/bin/activate && streamlit run dashboard/app.py"
