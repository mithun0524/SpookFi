# SpookFi: Autonomous Momentum Synthesizer
**AI Architecture & System Guide**

This document serves as a comprehensive guide for any future AI or developer interacting with the SpookFi repository. It outlines the system architecture, machine learning pipeline, execution engine, and frontend telemetry dashboard.

---

## 1. System Overview

SpookFi is a high-frequency, machine-learning-driven cryptocurrency algorithmic trading engine. It ingests real-time WebSocket market data via Alpaca, computes over 130 technical indicators on the fly, evaluates signals using an ensemble of tree-based ML models (XGBoost, Random Forest, LightGBM), and executes paper trades autonomously.

The system is decoupled into a headless backend trading engine (`main.py`) and a real-time telemetry frontend (`Vite + React`).

---

## 2. Directory Structure & Core Modules

### `data/` (Market Data Ingestion)
- **`stream.py`**: Manages the Alpaca Crypto WebSocket connection. It subscribes to minute-bars for up to 10 crypto assets (e.g., BTC, ETH, SOL). It pushes incoming bars to an `asyncio.Queue` for non-blocking ingestion. It also handles historical "warmup" data fetching so the ML models have enough bars to calculate indicators like the 200-SMA immediately upon booting.

### `features/` (Quantitative Engineering)
- **`engine.py`**: The heart of the quantitative pipeline. It utilizes `pandas-ta` to compute exactly 134 financial indicators (RSI, MACD, Bollinger Bands, ADX, ATR, etc.) per minute bar. 
  - *Crucial AI Note:* The feature engine expects timezone-aware `utc=True` datetime objects to prevent pandas casting crashes. Ensure `pd.to_datetime(utc=True)` is used during ingestion.

### `model/` (Machine Learning Matrix)
- **`trainer.py` (`The Forge`)**: The offline training pipeline. It fetches massive amounts of historical minute bars, computes features, scales them using `StandardScaler`, and balances the target classes using sample weights. It outputs three `.joblib` models (XGB, RF, LGBM) to the `models/` directory.
- **`predictor.py`**: The live inference engine. It loads the pre-trained ensemble and scaling artifacts. It takes real-time feature arrays, wraps them in a Pandas DataFrame (to satisfy Scikit-Learn `feature_names` requirements), and polls all three models. 
  - *Execution Logic:* It requires a strict majority vote (2 out of 3 models) and a specific confidence threshold to issue a `BUY` or `SELL`. Otherwise, it defaults to `HOLD`.

### `engine/` (Execution & Risk)
- **`phantom.py`**: The main asynchronous event loop. It dequeues market bars, feeds them to the `FeatureEngine`, extracts the latest row, runs it through the `Predictor`, checks the `RiskManager`, and finally triggers the `Executor`.
- **`executor.py`**: Interfaces directly with the Alpaca REST API to place market orders, track open positions, and record realized PnL.
- **`risk.py`**: Enforces strict capital preservation. It tracks the global account drawdown. If the session drawdown exceeds a hardcoded limit (e.g., 5%), it trips the `kill_switch` and liquidates all active positions.

### `dashboard/` (Telemetry Server)
- **`api.py`**: A FastAPI server running on `localhost:8000`. It shares state directly with the Phantom Engine (via the singleton `engine.state`) and exposes it via a `/api/state` endpoint. It allows the frontend to poll live equity, PnL, active signals, and historical equity curves.

### `frontend/` (Neural UI)
- A highly modern Vite + React web application.
- **Styling**: Powered by **Tailwind CSS v4** (using native `@import "tailwindcss";` and `@theme` CSS variables). 
- **Animation**: Driven by `framer-motion` for physics-based stagger entry animations and 3D hover effects.
- **Themes**: Features a dual-theme architecture. "Cyberpunk" (neon, glassmorphism) and "Luxury" (charcoal, gold accents). The themes are toggled via a React state and transition via pure CSS.

---

## 3. How to Operate the Engine

### 1. Training the Models (The Forge)
Before the live bot can run, the models must be trained on historical data.
```bash
python main.py forge
```
This will download historical data, engineer features, train the ensemble, and save the artifacts to `models/`.

### 2. Running the Live Bot (The Phantom)
Once models exist, you can start the live execution loop.
```bash
python main.py run
```
This connects to the Alpaca WebSocket, warms up the feature matrix, and begins scanning for trades.

### 3. Starting the Telemetry UI
Open a second terminal to host the FastAPI telemetry server:
```bash
python dashboard/api.py
```
Open a third terminal for the React frontend:
```bash
cd frontend
npx vite --host 127.0.0.1 --port 5173
```

---

## 4. Known Nuances for Future AIs

1. **Scikit-Learn Warnings**: In the past, mixing DataFrames during training and Numpy Arrays during live inference caused verbose `UserWarning`s. `predictor.py` now enforces DataFrame reconstruction and suppresses these warnings natively. Do not revert this.
2. **Tailwind v4 Setup**: The frontend uses Tailwind v4. Do NOT attempt to create `postcss.config.js` or `tailwind.config.js`. Configuration lives strictly inside `index.css` under the `@theme` directive, and the plugin is registered in `vite.config.js`.
3. **Invalid Hook Calls**: If the frontend ever crashes with "Invalid Hook Call", it is almost always due to NPM duplicating the `react` dependency. Fix it by running `rm -rf node_modules package-lock.json && npm install`.
4. **Timezone Awareness**: Financial data from Alpaca arrives timezone-aware. `pandas` requires exact mapping (`utc=True`) before converting to `datetime64`. Never drop timezones blindly in the feature engine.
