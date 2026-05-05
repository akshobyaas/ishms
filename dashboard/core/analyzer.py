import threading
import pandas as pd
from dashboard.core.ml_model import train_model, predict
from dashboard.core.root_cause import get_root_cause

_model_trained = False
_readings_at_last_train = 0
_train_lock = threading.Lock()

CAUSE_TO_STATUS = {
    "Memory Leak":     "Memory Leak Suspected",
    "CPU Instability": "CPU Instability Detected",
    "Overheating":     "Abnormal Thermal Rise",
    "Power Spike":     "Power Spike Detected",
    "System Overload": "Confirmed Anomaly",
}


def detect_trend(df):
    if len(df) < 5:
        return None
    if df["cpu"].iloc[-1] > df["cpu"].iloc[-5]:
        return "Increasing CPU Trend"
    if df["memory"].iloc[-1] > df["memory"].iloc[-5]:
        return "Increasing Memory Trend"
    return None


def analyze(data, df=None):
    """
    Analyze a single telemetry reading against historical data.

    Args:
        data: dict with keys cpu, memory, temperature, power
        df:   pandas DataFrame of historical readings (from DB query)
              If None, analysis runs without ML (rules-only).
    """
    global _model_trained, _readings_at_last_train

    if df is None:
        df = pd.DataFrame()

    n = len(df)

    with _train_lock:
        if not _model_trained and n >= 30:
            train_model(df)
            _model_trained = True
            _readings_at_last_train = n
        elif _model_trained and n - _readings_at_last_train >= 50:
            train_model(df)
            _readings_at_last_train = n

    is_anomaly, prob = predict(data, df) if _model_trained else (False, 0.0)

    trend = detect_trend(df)
    root = get_root_cause(df, data)
    cause_name = root.get("cause", "Unknown")

    if is_anomaly:
        status = CAUSE_TO_STATUS.get(cause_name, "Confirmed Anomaly")
    elif trend:
        status = "Suspicious"
    else:
        status = "Normal"

    return {
        "status": status,
        "cause": cause_name if status != "Normal" else "None",
        "confidence": round(prob if prob else root.get("confidence", 0), 2),
    }
