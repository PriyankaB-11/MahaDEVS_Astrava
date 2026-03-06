"""
Train RandomForestRegressor for AQI prediction.
Loads dataset, trains model, evaluates MAPE, and saves model as aqi_model.pkl.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_percentage_error, mean_absolute_error, r2_score
import joblib
import os


FEATURE_COLS = [
    "PM2.5", "PM10", "NO2", "SO2", "CO", "O3",
    "temperature", "humidity", "wind_speed",
    "hour", "day", "month", "day_of_week"
]
TARGET_COL = "AQI"


def load_data(filepath="data/aqi_dataset.csv"):
    """Load and preprocess the AQI dataset."""
    print(f"Loading dataset from {filepath}...")
    df = pd.read_csv(filepath)
    print(f"  Loaded {len(df)} records with columns: {list(df.columns)}")

    # Handle missing values
    for col in FEATURE_COLS + [TARGET_COL]:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].median())

    # Drop rows where target is missing
    df = df.dropna(subset=[TARGET_COL])

    print(f"  After cleaning: {len(df)} records")
    return df


def train_model(df):
    """Train a RandomForestRegressor on the dataset."""
    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    print("\nTraining RandomForestRegressor...")
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=30,
        min_samples_split=3,
        min_samples_leaf=1,
        max_features=0.8,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train_scaled, y_train)

    # Evaluate
    y_pred = model.predict(X_test_scaled)
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    print(f"\n{'='*50}")
    print(f"Model Evaluation Results:")
    print(f"{'='*50}")
    print(f"  MAPE:  {mape:.2f}%")
    print(f"  MAE:   {mae:.2f}")
    print(f"  R²:    {r2:.4f}")
    print(f"{'='*50}")

    if mape < 15:
        print(f"  ✓ MAPE {mape:.2f}% is below 15% target!")
    else:
        print(f"  ✗ MAPE {mape:.2f}% exceeds 15% target. Consider tuning.")

    # Feature importance
    importances = model.feature_importances_
    feat_imp = sorted(zip(FEATURE_COLS, importances), key=lambda x: x[1], reverse=True)
    print(f"\nFeature Importances:")
    for feat, imp in feat_imp:
        bar = "█" * int(imp * 50)
        print(f"  {feat:15s} {imp:.4f} {bar}")

    return model, scaler


def save_model(model, scaler, model_dir="models"):
    """Save the trained model and scaler."""
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "aqi_model.pkl")
    scaler_path = os.path.join(model_dir, "scaler.pkl")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    print(f"\nModel saved to {model_path}")
    print(f"Scaler saved to {scaler_path}")


def main():
    # Check if dataset exists, if not fetch real data
    if not os.path.exists("data/aqi_dataset.csv"):
        print("Dataset not found. Fetching real data from Open-Meteo APIs...")
        from generate_data import main as gen_main
        gen_main()

    df = load_data()
    model, scaler = train_model(df)
    save_model(model, scaler)
    print("\nTraining complete!")


if __name__ == "__main__":
    main()
