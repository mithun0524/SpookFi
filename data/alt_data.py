"""
Alternative Market Data — Fear & Greed Index
Fetches the Crypto/Market Fear & Greed Index from Alternative.me (free, no auth).
Used as an additional sentiment feature in the XGBoost model.
"""
import asyncio
from datetime import datetime, timezone
from loguru import logger

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    import urllib.request
    import json as _json

import pandas as pd
import numpy as np

_FNG_URL = "https://api.alternative.me/fng/"
_CACHE: dict = {"value": 50.0, "last_fetched": None}
_CACHE_TTL_HOURS = 1.0  # Refresh at most once per hour


def _fng_raw_to_float(value_str: str) -> float:
    """Normalise the raw 0-100 integer string to a 0-1 float."""
    try:
        return float(value_str) / 100.0
    except (ValueError, TypeError):
        return 0.5  # Neutral fallback


async def fetch_fear_greed_current() -> float:
    """
    Fetch the latest Fear & Greed value (0-1 normalised).
    Returns 0.5 (neutral) if the API is unavailable.
    Respects a 1-hour cache to avoid hammering the endpoint.
    """
    global _CACHE

    now = datetime.now(timezone.utc)
    if _CACHE["last_fetched"] is not None:
        age_hours = (now - _CACHE["last_fetched"]).total_seconds() / 3600.0
        if age_hours < _CACHE_TTL_HOURS:
            return _CACHE["value"]

    try:
        if _HTTPX_AVAILABLE:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(_FNG_URL, params={"limit": 1})
                resp.raise_for_status()
                data = resp.json()
        else:
            # Fallback to stdlib (sync in thread)
            def _fetch():
                url = f"{_FNG_URL}?limit=1"
                with urllib.request.urlopen(url, timeout=5) as r:
                    return _json.loads(r.read())
            data = await asyncio.to_thread(_fetch)

        value = _fng_raw_to_float(data["data"][0]["value"])
        _CACHE = {"value": value, "last_fetched": now}
        logger.debug(f"Fear & Greed Index fetched: {value:.2f} ({data['data'][0].get('value_classification', '')})")
        return value

    except Exception as e:
        logger.warning(f"Could not fetch Fear & Greed Index: {e}. Using neutral (0.5).")
        return _CACHE.get("value", 0.5)


async def fetch_fear_greed_history(limit: int = 90) -> pd.Series:
    """
    Fetch historical Fear & Greed values.
    Returns a pd.Series indexed by UTC date (datetime.date), values 0-1 normalised.
    Falls back to a constant neutral series if unavailable.
    """
    try:
        if _HTTPX_AVAILABLE:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(_FNG_URL, params={"limit": limit})
                resp.raise_for_status()
                data = resp.json()
        else:
            def _fetch():
                url = f"{_FNG_URL}?limit={limit}"
                with urllib.request.urlopen(url, timeout=10) as r:
                    return _json.loads(r.read())
            data = await asyncio.to_thread(_fetch)

        records = data.get("data", [])
        dates = []
        values = []
        for record in records:
            ts = int(record["timestamp"])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            val = _fng_raw_to_float(record["value"])
            dates.append(dt)
            values.append(val)

        series = pd.Series(values, index=pd.to_datetime(dates), name="fear_greed_index")
        series = series.sort_index()
        logger.info(f"Fetched {len(series)} days of Fear & Greed history.")
        return series

    except Exception as e:
        logger.warning(f"Could not fetch historical Fear & Greed data: {e}. Using neutral fallback.")
        # Return a neutral constant series for today
        today = pd.Timestamp.now(tz="UTC").normalize()
        return pd.Series([0.5], index=[today], name="fear_greed_index")
