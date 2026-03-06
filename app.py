"""
AirAware - Real-Time Air Quality Prediction & Health Advisory System
Flask backend serving API endpoints and frontend pages.
Fetches LIVE data from AQICN and Open-Meteo APIs.
"""

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import joblib
from flask import Flask, render_template, jsonify, request

from live_data import (
    get_live_data, get_all_cities_live, get_supported_cities,
    CITY_CONFIG,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Load model & dataset (dataset kept only for trends / training fallback)
# ---------------------------------------------------------------------------
MODEL_PATH = os.path.join("models", "aqi_model.pkl")
SCALER_PATH = os.path.join("models", "scaler.pkl")
DATASET_PATH = os.path.join("data", "aqi_dataset.csv")

FEATURE_COLS = [
    "PM2.5", "PM10", "NO2", "SO2", "CO", "O3",
    "temperature", "humidity", "wind_speed",
    "hour", "day", "month", "day_of_week"
]

model = None
scaler = None
dataset = None  # used only for historical trends


def load_resources():
    """Load ML model, scaler, and historical dataset."""
    global model, scaler, dataset
    if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
        model = joblib.load(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)
        print("Model and scaler loaded successfully.")
    else:
        print("WARNING: Model not found. Run train_model.py first.")

    if os.path.exists(DATASET_PATH):
        dataset = pd.read_csv(DATASET_PATH, parse_dates=["datetime"])
        print(f"Historical dataset loaded: {len(dataset)} records (used for trends).")
    else:
        print("WARNING: Historical dataset not found. Trends page will be limited.")


load_resources()

# ---------------------------------------------------------------------------
# Health Advisory Engine
# ---------------------------------------------------------------------------
AQI_CATEGORIES = [
    {"min": 0, "max": 50, "label": "Good", "color": "#2ecc71",
     "advice": ["Air quality is satisfactory.", "Enjoy outdoor activities."]},
    {"min": 51, "max": 100, "label": "Moderate", "color": "#f1c40f",
     "advice": ["Acceptable air quality.", "Sensitive individuals should limit prolonged outdoor exertion."]},
    {"min": 101, "max": 200, "label": "Unhealthy", "color": "#e67e22",
     "advice": ["Avoid prolonged outdoor exercise.", "Wear N95 mask outdoors.",
                 "Keep windows closed.", "Use air purifier indoors."]},
    {"min": 201, "max": 300, "label": "Very Unhealthy", "color": "#e74c3c",
     "advice": ["Avoid all outdoor exercise.", "Wear N95 mask if going outside.",
                 "Keep all windows and doors closed.", "Run air purifier continuously.",
                 "Consider staying indoors."]},
    {"min": 301, "max": 999, "label": "Hazardous", "color": "#8e44ad",
     "advice": ["STAY INDOORS.", "Avoid any outdoor activity.",
                 "Seal windows and doors.", "Use air purifier on max setting.",
                 "Seek medical attention if experiencing symptoms."]},
]

VULNERABLE_EXTRA = {
    "asthma": [
        "Keep rescue inhaler accessible at all times.",
        "Monitor breathing closely; seek help if wheezing worsens.",
        "Avoid any exposure to outdoor air.",
    ],
    "children": [
        "Keep children indoors during peak pollution hours.",
        "Cancel outdoor school activities.",
        "Ensure proper hydration.",
    ],
    "elderly": [
        "Limit physical exertion even indoors.",
        "Monitor blood pressure and heart rate.",
        "Keep emergency contacts ready.",
    ],
}


def get_aqi_category(aqi_value):
    """Return the AQI category info for a given AQI value."""
    for cat in AQI_CATEGORIES:
        if cat["min"] <= aqi_value <= cat["max"]:
            return cat
    return AQI_CATEGORIES[-1]


def get_health_advisory(aqi_value, vulnerable_groups=None):
    """Generate health advisory based on AQI and vulnerable groups."""
    cat = get_aqi_category(aqi_value)
    advisory = {
        "aqi": round(aqi_value, 1),
        "status": cat["label"],
        "color": cat["color"],
        "general_advice": cat["advice"],
        "vulnerable_alerts": {},
    }

    if vulnerable_groups:
        for group in vulnerable_groups:
            group_key = group.lower().strip()
            if group_key in VULNERABLE_EXTRA:
                base = VULNERABLE_EXTRA[group_key]
                # Escalate warnings if AQI > 100
                if aqi_value > 100:
                    advisory["vulnerable_alerts"][group_key] = base
                else:
                    advisory["vulnerable_alerts"][group_key] = [base[0]]

    return advisory


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------
def _build_features_from_live(live_data):
    """Convert live API response dict into a features dict for the model."""
    now = datetime.now()
    return {
        "PM2.5":      live_data["pollutants"].get("PM2.5", 0),
        "PM10":       live_data["pollutants"].get("PM10", 0),
        "NO2":        live_data["pollutants"].get("NO2", 0),
        "SO2":        live_data["pollutants"].get("SO2", 0),
        "CO":         live_data["pollutants"].get("CO", 0),
        "O3":         live_data["pollutants"].get("O3", 0),
        "temperature": live_data["weather"].get("temperature", 25),
        "humidity":    live_data["weather"].get("humidity", 50),
        "wind_speed":  live_data["weather"].get("wind_speed", 5),
        "hour":        now.hour,
        "day":         now.day,
        "month":       now.month,
        "day_of_week":  now.weekday(),
    }


def _fallback_data_for_city(city_name):
    """Fall back to the historical dataset if live APIs are down."""
    if dataset is None:
        return None
    city_data = dataset[dataset["city"] == city_name].sort_values("datetime")
    if city_data.empty:
        return None
    row = city_data.iloc[-1]
    return {
        "source": "historical_dataset",
        "aqi": float(row["AQI"]),
        "datetime": str(row["datetime"]),
        "city": city_name,
        "latitude": float(row.get("latitude", 0)),
        "longitude": float(row.get("longitude", 0)),
        "pollutants": {
            "PM2.5": float(row["PM2.5"]),
            "PM10":  float(row["PM10"]),
            "NO2":   float(row["NO2"]),
            "SO2":   float(row["SO2"]),
            "CO":    float(row["CO"]),
            "O3":    float(row["O3"]),
        },
        "weather": {
            "temperature": float(row["temperature"]),
            "humidity":    float(row["humidity"]),
            "wind_speed":  float(row["wind_speed"]),
        },
        "station": city_name,
    }


def get_city_data(city_name):
    """Get current data for a city: live API first, then dataset fallback."""
    live = get_live_data(city_name)
    if live is not None:
        return live
    print(f"[Fallback] Using historical data for {city_name}")
    return _fallback_data_for_city(city_name)


def predict_aqi(features_dict, hours_ahead=0):
    """Predict AQI given feature values and optional hours offset."""
    if model is None or scaler is None:
        return None

    now = datetime.now() + timedelta(hours=hours_ahead)
    features_dict = features_dict.copy()
    features_dict["hour"] = now.hour
    features_dict["day"] = now.day
    features_dict["month"] = now.month
    features_dict["day_of_week"] = now.weekday()

    # Small perturbation for future predictions to simulate change
    if hours_ahead > 0:
        drift = np.random.normal(0, hours_ahead * 0.5)
        features_dict["PM2.5"] = max(5, features_dict["PM2.5"] + drift)
        features_dict["PM10"] = max(10, features_dict["PM10"] + drift * 1.5)

    feature_values = [features_dict.get(col, 0) for col in FEATURE_COLS]
    X = np.array(feature_values).reshape(1, -1)
    X_scaled = scaler.transform(X)
    prediction = model.predict(X_scaled)[0]
    return max(0, round(prediction, 1))


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/trends")
def trends():
    return render_template("trends.html")


@app.route("/map")
def map_page():
    return render_template("map.html")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.route("/aqi/current")
def aqi_current():
    """Return live AQI for a city from AQICN/OpenWeather APIs."""
    city = request.args.get("city", "Delhi")
    vulnerable = request.args.getlist("vulnerable")

    data = get_city_data(city)
    if data is None:
        return jsonify({"error": "No data available – APIs unreachable and no fallback dataset"}), 404

    aqi_value = float(data["aqi"])
    advisory = get_health_advisory(aqi_value, vulnerable)

    return jsonify({
        "city": city,
        "source": data.get("source", "unknown"),
        "station": data.get("station", city),
        "datetime": data.get("datetime", ""),
        "aqi": aqi_value,
        "pollutants": data["pollutants"],
        "weather": data["weather"],
        "advisory": advisory,
    })


@app.route("/aqi/predict")
def aqi_predict():
    """Return predicted AQI for 24h and 48h using live data as model input."""
    city = request.args.get("city", "Delhi")
    vulnerable = request.args.getlist("vulnerable")

    data = get_city_data(city)
    if data is None or model is None:
        return jsonify({"error": "Model or live data not available"}), 503

    features = _build_features_from_live(data)

    current_aqi = float(data["aqi"])
    pred_24h = predict_aqi(features, hours_ahead=24)
    pred_48h = predict_aqi(features, hours_ahead=48)

    # Hourly predictions for chart
    hourly = []
    for h in range(0, 49, 3):
        val = predict_aqi(features, hours_ahead=h)
        hourly.append({"hours_ahead": h, "predicted_aqi": val})

    advisory_24 = get_health_advisory(pred_24h, vulnerable)
    advisory_48 = get_health_advisory(pred_48h, vulnerable)

    return jsonify({
        "city": city,
        "source": data.get("source", "unknown"),
        "current_aqi": current_aqi,
        "prediction_24h": {"aqi": pred_24h, "advisory": advisory_24},
        "prediction_48h": {"aqi": pred_48h, "advisory": advisory_48},
        "hourly_forecast": hourly,
    })


@app.route("/aqi/trends")
def aqi_trends():
    """Return historical pollution data for charts."""
    city = request.args.get("city", "Delhi")
    days = int(request.args.get("days", 30))

    if dataset is None:
        return jsonify({"error": "No data available"}), 404

    city_data = dataset[dataset["city"] == city].sort_values("datetime")
    if city_data.empty:
        return jsonify({"error": f"No data for {city}"}), 404

    # Aggregate daily for trends
    city_data = city_data.copy()
    city_data["date"] = city_data["datetime"].dt.date
    daily = city_data.groupby("date").agg({
        "AQI": "mean",
        "PM2.5": "mean",
        "PM10": "mean",
        "NO2": "mean",
        "SO2": "mean",
        "CO": "mean",
        "O3": "mean",
        "temperature": "mean",
        "humidity": "mean",
        "wind_speed": "mean",
    }).reset_index()

    daily = daily.tail(days)

    return jsonify({
        "city": city,
        "days": days,
        "dates": [str(d) for d in daily["date"]],
        "aqi": [round(v, 1) for v in daily["AQI"]],
        "pm25": [round(v, 1) for v in daily["PM2.5"]],
        "pm10": [round(v, 1) for v in daily["PM10"]],
        "no2": [round(v, 1) for v in daily["NO2"]],
        "so2": [round(v, 1) for v in daily["SO2"]],
        "co": [round(v, 2) for v in daily["CO"]],
        "o3": [round(v, 1) for v in daily["O3"]],
        "temperature": [round(v, 1) for v in daily["temperature"]],
        "humidity": [round(v, 1) for v in daily["humidity"]],
    })


@app.route("/aqi/cities")
def aqi_cities():
    """Return all cities with their LIVE AQI for map markers."""
    result = []
    for city_name in CITY_CONFIG:
        data = get_city_data(city_name)
        if data is None:
            continue
        aqi_val = float(data["aqi"])
        cat = get_aqi_category(aqi_val)
        cfg = CITY_CONFIG[city_name]
        result.append({
            "name": city_name,
            "lat": cfg["lat"],
            "lon": cfg["lon"],
            "aqi": round(aqi_val, 1),
            "status": cat["label"],
            "color": cat["color"],
            "pm25": round(data["pollutants"].get("PM2.5", 0), 1),
            "pm10": round(data["pollutants"].get("PM10", 0), 1),
            "source": data.get("source", "unknown"),
            "station": data.get("station", city_name),
        })

    return jsonify({"cities": result})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
