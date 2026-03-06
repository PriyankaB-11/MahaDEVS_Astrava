# 🌬️ AirAware – Real-Time Air Quality Prediction & Health Advisory System

A complete MVP that predicts AQI for the next 24–48 hours using sensor data, weather patterns, and machine learning, with health advisories for vulnerable populations.

## Features

- **AQI Prediction** – RandomForestRegressor model predicting AQI for 24h and 48h ahead
- **Health Advisory Engine** – Context-aware recommendations based on AQI levels
- **Vulnerable Population Alerts** – Specialized warnings for asthma, children, and elderly
- **Interactive Map** – Leaflet.js map with color-coded AQI markers for 10 Indian cities
- **Pollution Trend Dashboard** – Chart.js visualizations for AQI, PM2.5, PM10, and more
- **REST API** – JSON endpoints for current AQI, predictions, and historical trends

## Tech Stack

| Layer    | Technologies                                |
| -------- | ------------------------------------------- |
| Backend  | Python, Flask, Pandas, NumPy, Scikit-learn  |
| Frontend | HTML, CSS, JavaScript, Chart.js, Leaflet.js |
| ML Model | RandomForestRegressor                       |

## Project Structure

```
AirAware/
├── app.py                  # Flask server & API endpoints
├── live_data.py            # Live API fetcher (AQICN + Open-Meteo fallback)
├── train_model.py          # Model training script
├── generate_data.py        # Synthetic dataset generator
├── requirements.txt        # Python dependencies
├── data/
│   ├── aqi_dataset.csv     # Training dataset (fallback for trends)
│   └── cities.csv          # City coordinates
├── models/
│   ├── aqi_model.pkl       # Trained model
│   └── scaler.pkl          # Feature scaler
├── templates/
│   ├── dashboard.html      # Main dashboard page
│   ├── trends.html         # Pollution trends page
│   └── map.html            # Interactive map page
└── static/
    ├── css/
    │   └── style.css       # Global styles
    └── js/
        └── charts.js       # Chart.js helper functions
```

## Quick Start

### 1. Install Dependencies

```bash
cd Airaware
pip install -r requirements.txt
```

### 2. Generate Dataset & Train Model

```bash
python generate_data.py
python train_model.py
```

You should see MAPE < 15% in the training output.

### 3. Run the Application

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

## Pages

| Page      | URL       | Description                                                   |
| --------- | --------- | ------------------------------------------------------------- |
| Dashboard | `/`       | Current AQI, predictions, health advisories, pollutant levels |
| Trends    | `/trends` | Historical charts for AQI, PM2.5, PM10, weather overlay       |
| Map       | `/map`    | Interactive Leaflet map with AQI markers for all cities       |

## API Endpoints

| Endpoint       | Method | Parameters             | Description                        |
| -------------- | ------ | ---------------------- | ---------------------------------- |
| `/aqi/current` | GET    | `city`, `vulnerable[]` | Current AQI with health advisory   |
| `/aqi/predict` | GET    | `city`, `vulnerable[]` | 24h and 48h AQI predictions        |
| `/aqi/trends`  | GET    | `city`, `days`         | Historical pollution data          |
| `/aqi/cities`  | GET    | —                      | All cities with latest AQI for map |

### Example API Response

```json
GET /aqi/current?city=Delhi&vulnerable=asthma

{
  "city": "Delhi",
  "aqi": 165.3,
  "advisory": {
    "status": "Unhealthy",
    "color": "#e67e22",
    "general_advice": [
      "Avoid prolonged outdoor exercise.",
      "Wear N95 mask outdoors.",
      "Keep windows closed.",
      "Use air purifier indoors."
    ],
    "vulnerable_alerts": {
      "asthma": [
        "Keep rescue inhaler accessible at all times.",
        "Monitor breathing closely; seek help if wheezing worsens.",
        "Avoid any exposure to outdoor air."
      ]
    }
  }
}
```

## Live Data Sources

AirAware fetches **real-time** air quality and weather data from public APIs:

| Source                         | Data                              | Auth        | Priority |
| ------------------------------ | --------------------------------- | ----------- | -------- |
| **AQICN / WAQI API**           | Full AQI + pollutants + weather   | Free token  | Primary  |
| **Open-Meteo Air Quality API** | PM2.5, PM10, NO2, SO2, CO, O3     | None (free) | Fallback |
| **Open-Meteo Weather API**     | Temperature, Humidity, Wind Speed | None (free) | Fallback |

### Setup API Key

Only the AQICN token is required. Open-Meteo (fallback) needs no key.

1. Get a free AQICN token at https://aqicn.org/data-platform/token/
2. Set it as an environment variable before running:

```bash
# Windows
set AQICN_TOKEN=your_aqicn_token_here

# Linux/Mac
export AQICN_TOKEN=your_aqicn_token_here
```

AQICN is used as the primary source (station-based, most accurate). Open-Meteo is the free fallback when AQICN is unavailable.

The synthetic dataset (`data/aqi_dataset.csv`) is used as a fallback for trends and when APIs are unavailable.

## Model Details

- **Algorithm**: RandomForestRegressor (200 trees, max_depth=30)
- **Features**: PM2.5, PM10, NO2, SO2, CO, O3, temperature, humidity, wind_speed, hour, day, month, day_of_week
- **Target**: AQI
- **Target MAPE**: < 15%

## Health Advisory Rules

| AQI Range | Status         | Color     |
| --------- | -------------- | --------- |
| 0–50      | Good           | 🟢 Green  |
| 51–100    | Moderate       | 🟡 Yellow |
| 101–200   | Unhealthy      | 🟠 Orange |
| 201–300   | Very Unhealthy | 🔴 Red    |
| 300+      | Hazardous      | 🟣 Purple |
