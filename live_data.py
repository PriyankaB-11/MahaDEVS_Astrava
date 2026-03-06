"""
AirAware – Live data fetcher module.
Fetches real-time AQI & weather data from public APIs:
  1. AQICN (waqi.info) – primary (station-based, most accurate; free token)
  2. Open-Meteo Air Quality + Weather API – free fallback (no key needed)
Falls back gracefully through the chain if APIs are unavailable.

Setup:
  - Get a free AQICN token at https://aqicn.org/data-platform/token/
    Set env var: AQICN_TOKEN=<your-token>
"""

import os
import time
import threading
import requests
from datetime import datetime

# ---------------------------------------------------------------------------
# API Configuration
# ---------------------------------------------------------------------------
AQICN_TOKEN = os.environ.get("AQICN_TOKEN", "")

# City mappings with coordinates
CITY_CONFIG = {
    "Delhi":     {"lat": 28.6139, "lon": 77.2090},
    "Mumbai":    {"lat": 19.0760, "lon": 72.8777},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946},
    "Chennai":   {"lat": 13.0827, "lon": 80.2707},
    "Kolkata":   {"lat": 22.5726, "lon": 88.3639},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "Pune":      {"lat": 18.5204, "lon": 73.8567},
    "Ahmedabad": {"lat": 23.0225, "lon": 72.5714},
    "Jaipur":    {"lat": 26.9124, "lon": 75.7873},
    "Lucknow":   {"lat": 26.8467, "lon": 80.9462},
}

# In-memory cache: city -> {data, timestamp}
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600  # 10 minutes


# ---------------------------------------------------------------------------
# AQICN API (primary – station-based, most accurate)
# ---------------------------------------------------------------------------
def fetch_aqicn(city_name):
    """
    Fetch real-time data from AQICN / WAQI API using geo-based lookup.
    Requires a free token set via AQICN_TOKEN env var.
    Get one at https://aqicn.org/data-platform/token/
    """
    if not AQICN_TOKEN or AQICN_TOKEN.lower() == "demo":
        return None

    config = CITY_CONFIG.get(city_name)
    if not config:
        return None

    lat, lon = config["lat"], config["lon"]
    url = f"https://api.waqi.info/feed/geo:{lat};{lon}/"
    params = {"token": AQICN_TOKEN}

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        body = resp.json()

        if body.get("status") != "ok":
            return None

        data = body["data"]
        iaqi = data.get("iaqi", {})

        return {
            "source": "aqicn",
            "aqi": float(data.get("aqi", 0)),
            "datetime": data.get("time", {}).get("iso", datetime.utcnow().isoformat()),
            "city": city_name,
            "latitude": lat,
            "longitude": lon,
            "pollutants": {
                "PM2.5": _extract_iaqi(iaqi, "pm25"),
                "PM10":  _extract_iaqi(iaqi, "pm10"),
                "NO2":   _extract_iaqi(iaqi, "no2"),
                "SO2":   _extract_iaqi(iaqi, "so2"),
                "CO":    _extract_iaqi(iaqi, "co"),
                "O3":    _extract_iaqi(iaqi, "o3"),
            },
            "weather": {
                "temperature": _extract_iaqi(iaqi, "t"),
                "humidity":    _extract_iaqi(iaqi, "h"),
                "wind_speed":  _extract_iaqi(iaqi, "w"),
            },
            "station": data.get("city", {}).get("name", city_name),
        }

    except requests.RequestException as e:
        print(f"[AQICN] Request failed for {city_name}: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        print(f"[AQICN] Parse error for {city_name}: {e}")
        return None


def _extract_iaqi(iaqi_dict, key):
    """Safely extract a numeric value from AQICN iaqi sub-object."""
    entry = iaqi_dict.get(key)
    if entry and isinstance(entry, dict):
        return float(entry.get("v", 0))
    return 0.0


# ---------------------------------------------------------------------------
# Open-Meteo Air Quality + Weather API (free fallback – no key needed)
# ---------------------------------------------------------------------------
def fetch_open_meteo(city_name):
    """
    Fetch real-time air quality from Open-Meteo Air Quality API
    and weather from Open-Meteo Forecast API. Both free, no key needed.
    Used as fallback when AQICN is unavailable.
    """
    config = CITY_CONFIG.get(city_name)
    if not config:
        return None

    lat, lon = config["lat"], config["lon"]

    try:
        # Fetch air quality data
        aq_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        aq_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "pm2_5,pm10,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide,ozone",
        }
        aq_resp = requests.get(aq_url, params=aq_params, timeout=10)
        aq_resp.raise_for_status()
        aq_data = aq_resp.json().get("current", {})

        # Fetch weather data
        wx_url = "https://api.open-meteo.com/v1/forecast"
        wx_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        }
        wx_resp = requests.get(wx_url, params=wx_params, timeout=10)
        wx_resp.raise_for_status()
        wx_data = wx_resp.json().get("current", {})

        pm25 = float(aq_data.get("pm2_5", 0) or 0)
        aqi = _compute_aqi_from_pm25(pm25)

        return {
            "source": "open-meteo",
            "aqi": aqi,
            "datetime": aq_data.get("time", datetime.utcnow().isoformat()),
            "city": city_name,
            "latitude": lat,
            "longitude": lon,
            "pollutants": {
                "PM2.5": pm25,
                "PM10":  float(aq_data.get("pm10", 0) or 0),
                "NO2":   float(aq_data.get("nitrogen_dioxide", 0) or 0),
                "SO2":   float(aq_data.get("sulphur_dioxide", 0) or 0),
                "CO":    float(aq_data.get("carbon_monoxide", 0) or 0),
                "O3":    float(aq_data.get("ozone", 0) or 0),
            },
            "weather": {
                "temperature": float(wx_data.get("temperature_2m", 0) or 0),
                "humidity":    float(wx_data.get("relative_humidity_2m", 0) or 0),
                "wind_speed":  float(wx_data.get("wind_speed_10m", 0) or 0),
            },
            "station": f"{city_name} (Open-Meteo Grid)",
        }

    except requests.RequestException as e:
        print(f"[Open-Meteo] Request failed for {city_name}: {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        print(f"[Open-Meteo] Parse error for {city_name}: {e}")
        return None


def _compute_aqi_from_pm25(pm25):
    """Compute Indian AQI from PM2.5 concentration (µg/m³) using standard breakpoints."""
    breakpoints = [
        (0,   30,   0,   50),
        (31,  60,   51,  100),
        (61,  90,   101, 200),
        (91,  120,  201, 300),
        (121, 250,  301, 400),
        (251, 500,  401, 500),
    ]
    for bp_lo, bp_hi, i_lo, i_hi in breakpoints:
        if pm25 <= bp_hi:
            aqi = ((i_hi - i_lo) / (bp_hi - bp_lo)) * (pm25 - bp_lo) + i_lo
            return round(aqi, 1)
    return round(pm25 * 1.5, 1)  # fallback for extreme values


# ---------------------------------------------------------------------------
# Unified fetch with caching + fallback chain
# ---------------------------------------------------------------------------
def get_live_data(city_name):
    """
    Get live AQI data for a city. Tries in order:
      1. Cache (if fresh, < 10 min old)
      2. AQICN API (station-based, most accurate)
      3. Open-Meteo Air Quality API (free fallback, no key needed)
      4. None (caller should fall back to historical dataset)
    """
    with _cache_lock:
        cached = _cache.get(city_name)
        if cached and (time.time() - cached["timestamp"]) < CACHE_TTL:
            cached_data = cached["data"].copy()
            cached_data["source"] = cached_data.get("source", "unknown") + " (cached)"
            return cached_data

    # Try AQICN first (station-based, most accurate)
    data = fetch_aqicn(city_name)

    # Fallback to Open-Meteo (free, no key needed)
    if data is None:
        data = fetch_open_meteo(city_name)

    # Cache successful results
    if data is not None:
        with _cache_lock:
            _cache[city_name] = {"data": data, "timestamp": time.time()}
        print(f"[Live] Fetched {city_name} AQI={data['aqi']} from {data['source']} ({data['station']})")

    return data


def get_all_cities_live():
    """Fetch live data for all configured cities."""
    results = []
    for city_name in CITY_CONFIG:
        data = get_live_data(city_name)
        if data:
            results.append(data)
    return results


def clear_cache():
    """Clear the in-memory cache."""
    with _cache_lock:
        _cache.clear()


def get_supported_cities():
    """Return list of supported city configs."""
    return [
        {"name": name, "lat": cfg["lat"], "lon": cfg["lon"]}
        for name, cfg in CITY_CONFIG.items()
    ]
