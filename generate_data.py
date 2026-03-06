"""
Fetch REAL historical AQI & weather data from Open-Meteo APIs.
Uses the free Open-Meteo Historical Air-Quality and Weather APIs
(no API key required) to build a training dataset.
"""

import os
import time

import pandas as pd
import requests
from datetime import datetime, timedelta

CITIES = [
    {"name": "Delhi",     "lat": 28.6139, "lon": 77.2090},
    {"name": "Mumbai",    "lat": 19.0760, "lon": 72.8777},
    {"name": "Bangalore", "lat": 12.9716, "lon": 77.5946},
    {"name": "Chennai",   "lat": 13.0827, "lon": 80.2707},
    {"name": "Kolkata",   "lat": 22.5726, "lon": 88.3639},
    {"name": "Hyderabad", "lat": 17.3850, "lon": 78.4867},
    {"name": "Pune",      "lat": 18.5204, "lon": 73.8567},
    {"name": "Ahmedabad", "lat": 23.0225, "lon": 72.5714},
    {"name": "Jaipur",    "lat": 26.9124, "lon": 75.7873},
    {"name": "Lucknow",   "lat": 26.8467, "lon": 80.9462},
]

# Indian AQI breakpoints for PM2.5 (µg/m³)
AQI_BREAKPOINTS = [
    (0,   30,   0,   50),
    (31,  60,   51,  100),
    (61,  90,   101, 200),
    (91,  120,  201, 300),
    (121, 250,  301, 400),
    (251, 500,  401, 500),
]


def compute_aqi_from_pm25(pm25):
    """Compute Indian AQI from PM2.5 concentration (µg/m³)."""
    if pm25 is None or pm25 < 0:
        return None
    for bp_lo, bp_hi, i_lo, i_hi in AQI_BREAKPOINTS:
        if pm25 <= bp_hi:
            return round(((i_hi - i_lo) / (bp_hi - bp_lo)) * (pm25 - bp_lo) + i_lo, 1)
    return round(pm25 * 1.5, 1)


def fetch_city_data(city, start_date, end_date):
    """
    Fetch real hourly air-quality and weather data for a city
    from the Open-Meteo Historical APIs.
    """
    lat, lon = city["lat"], city["lon"]
    s = start_date.strftime("%Y-%m-%d")
    e = end_date.strftime("%Y-%m-%d")

    # --- Air quality (historical archive) ---
    aq_url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    aq_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,pm10,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide,ozone",
        "start_date": s,
        "end_date": e,
    }

    # --- Weather (historical archive) ---
    wx_url = "https://archive-api.open-meteo.com/v1/archive"
    wx_params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "start_date": s,
        "end_date": e,
    }

    try:
        aq_resp = requests.get(aq_url, params=aq_params, timeout=60)
        aq_resp.raise_for_status()
        aq_json = aq_resp.json()
    except requests.RequestException as exc:
        print(f"  [ERROR] Air-quality API failed for {city['name']}: {exc}")
        return pd.DataFrame()

    # small pause to be polite to the free API
    time.sleep(1)

    try:
        wx_resp = requests.get(wx_url, params=wx_params, timeout=60)
        wx_resp.raise_for_status()
        wx_json = wx_resp.json()
    except requests.RequestException as exc:
        print(f"  [ERROR] Weather API failed for {city['name']}: {exc}")
        return pd.DataFrame()

    aq_hourly = aq_json.get("hourly", {})
    wx_hourly = wx_json.get("hourly", {})

    timestamps = aq_hourly.get("time", [])
    if not timestamps:
        print(f"  [WARN] No data returned for {city['name']}")
        return pd.DataFrame()

    n = len(timestamps)

    # Build a list aligned by timestamp length
    def _safe(lst):
        """Pad / trim list to match timestamp count."""
        if lst is None:
            return [None] * n
        if len(lst) < n:
            return lst + [None] * (n - len(lst))
        return lst[:n]

    pm25_vals = _safe(aq_hourly.get("pm2_5"))
    pm10_vals = _safe(aq_hourly.get("pm10"))
    no2_vals  = _safe(aq_hourly.get("nitrogen_dioxide"))
    so2_vals  = _safe(aq_hourly.get("sulphur_dioxide"))
    co_vals   = _safe(aq_hourly.get("carbon_monoxide"))
    o3_vals   = _safe(aq_hourly.get("ozone"))

    wx_times  = wx_hourly.get("time", [])
    temp_vals = _safe(wx_hourly.get("temperature_2m"))
    hum_vals  = _safe(wx_hourly.get("relative_humidity_2m"))
    wind_vals = _safe(wx_hourly.get("wind_speed_10m"))

    # If weather timestamps are shorter / longer, build a lookup
    wx_lookup_temp = {}
    wx_lookup_hum  = {}
    wx_lookup_wind = {}
    for i, t in enumerate(wx_times):
        if i < len(temp_vals):
            wx_lookup_temp[t] = temp_vals[i]
        if i < len(hum_vals):
            wx_lookup_hum[t] = hum_vals[i]
        if i < len(wind_vals):
            wx_lookup_wind[t] = wind_vals[i]

    records = []
    for i, ts in enumerate(timestamps):
        dt = datetime.fromisoformat(ts)
        pm25 = pm25_vals[i]
        aqi = compute_aqi_from_pm25(pm25) if pm25 is not None else None

        records.append({
            "datetime":   dt,
            "city":       city["name"],
            "latitude":   lat,
            "longitude":  lon,
            "PM2.5":      pm25_vals[i],
            "PM10":       pm10_vals[i],
            "NO2":        no2_vals[i],
            "SO2":        so2_vals[i],
            "CO":         co_vals[i],
            "O3":         o3_vals[i],
            "temperature": wx_lookup_temp.get(ts),
            "humidity":    wx_lookup_hum.get(ts),
            "wind_speed":  wx_lookup_wind.get(ts),
            "hour":       dt.hour,
            "day":        dt.day,
            "month":      dt.month,
            "day_of_week": dt.weekday(),
            "AQI":        aqi,
        })

    return pd.DataFrame(records)


def main():
    # Fetch ~2 years of real data (Open-Meteo keeps ~2-3 years of history)
    end_date = datetime.now() - timedelta(days=5)      # leave a few days margin
    start_date = end_date - timedelta(days=729)         # ~2 years

    print(f"Fetching REAL historical data from Open-Meteo APIs")
    print(f"  Period: {start_date.date()} to {end_date.date()}")
    print(f"  Cities: {len(CITIES)}\n")

    os.makedirs("data", exist_ok=True)
    all_frames = []

    for city in CITIES:
        print(f"  Fetching {city['name']}...")
        df = fetch_city_data(city, start_date, end_date)
        if not df.empty:
            print(f"    -> {len(df)} hourly records")
            all_frames.append(df)
        # polite delay between cities
        time.sleep(2)

    if not all_frames:
        print("ERROR: No data fetched from any city. Check your internet connection.")
        return

    combined = pd.concat(all_frames, ignore_index=True)

    # Drop rows where critical columns are all null
    before = len(combined)
    combined = combined.dropna(subset=["PM2.5", "AQI"])
    after = len(combined)
    print(f"\n  Dropped {before - after} rows with missing PM2.5/AQI")

    # Fill remaining nulls with column medians
    for col in ["PM10", "NO2", "SO2", "CO", "O3", "temperature", "humidity", "wind_speed"]:
        if col in combined.columns:
            combined[col] = combined[col].fillna(combined[col].median())

    combined.to_csv("data/aqi_dataset.csv", index=False)
    print(f"\nDataset saved: data/aqi_dataset.csv ({len(combined)} records)")

    # Also save city info
    city_df = pd.DataFrame(CITIES)
    city_df.to_csv("data/cities.csv", index=False)
    print(f"City info saved: data/cities.csv")


if __name__ == "__main__":
    main()
