"""
Combines the ML model and the rule-based checks into one verdict per reading.

    critical rule fires (overheat / power spike / overload) -> that anomaly
    ML flags the reading AND a pattern rule explains it     -> that anomaly
    memory-leak pattern                                     -> Memory Leak Suspected
    ML flags the reading, no rule explains it               -> Suspicious
    CPU instability or a clear rising trend                 -> Suspicious
    otherwise                                               -> Normal

The ML model answers "is this unusual for this machine?"; the rules answer
"what kind of problem is it?". A confirmed anomaly needs a concrete cause.
"""

import pandas as pd

from dashboard.core import ml_model
from dashboard.core.root_cause import CRITICAL_CAUSES, get_root_cause, recent_window, slope

CAUSE_TO_STATUS = {
    "Memory Leak":     "Memory Leak Suspected",
    "CPU Instability": "CPU Instability Detected",
    "Overheating":     "Abnormal Thermal Rise",
    "Power Spike":     "Power Spike Detected",
    "System Overload": "Confirmed Anomaly",
}

TREND_WINDOW = 10
CPU_TREND_SLOPE = 2.0      # % points per reading (~ +20 points over 10 readings)
MEMORY_TREND_SLOPE = 0.5   # % points per reading (~ +5 points over 10 readings)
ML_CAUSE = "Unusual Behaviour (ML)"

# IsolationForest flags anything unusual, including a machine that is *quieter*
# than normal. Only treat an ML flag as a health problem if at least one metric
# is meaningfully above its recent median.
ELEVATION_MARGIN = {"cpu": 10.0, "memory": 3.0, "temperature": 5.0, "power": 15.0}


def is_elevated(df, data):
    window = recent_window(df, None, size=100)
    if window.empty:
        return True
    median = window.median()
    return any(float(data[k]) > median[k] + m for k, m in ELEVATION_MARGIN.items())


def detect_trend(df, latest_data=None):
    """Return a trend label if CPU or memory is clearly climbing, else None."""
    window = recent_window(df, latest_data, size=TREND_WINDOW)
    if len(window) < 5:
        return None
    if slope(window["cpu"].values) > CPU_TREND_SLOPE:
        return "Increasing CPU Trend"
    if slope(window["memory"].values) > MEMORY_TREND_SLOPE:
        return "Increasing Memory Trend"
    return None


def analyze(data, df=None, total_rows=None):
    """
    Analyze a single reading against recent history.

    data:       dict with cpu, memory, temperature, power (not yet in df)
    df:         DataFrame of recent stored readings, oldest first
    total_rows: total readings stored, used for the retrain schedule
    """
    if df is None:
        df = pd.DataFrame(columns=["cpu", "memory", "temperature", "power"])

    model_ready = ml_model.ensure_model(df, total_rows)
    ml_anomaly, ml_conf = ml_model.predict(data, df) if model_ready else (False, 0.0)
    ml_anomaly = ml_anomaly and is_elevated(df, data)

    root = get_root_cause(df, data)
    cause = root["cause"]
    trend = detect_trend(df, data)

    if cause in CRITICAL_CAUSES:
        status, conf = CAUSE_TO_STATUS[cause], max(root["confidence"], ml_conf)
    elif ml_anomaly and cause in CAUSE_TO_STATUS:
        status, conf = CAUSE_TO_STATUS[cause], ml_conf
    elif ml_anomaly:
        status, cause, conf = "Suspicious", ML_CAUSE, ml_conf
        root["details"] = "Reading doesn't match this machine's recent normal behaviour"
    elif cause == "Memory Leak":
        status, conf = CAUSE_TO_STATUS[cause], root["confidence"]
    elif cause == "CPU Instability" or trend:
        status = "Suspicious"
        cause = cause if cause == "CPU Instability" else trend
        conf = root["confidence"] if cause == "CPU Instability" else 0.5
    else:
        status, cause = "Normal", "None"
        conf = ml_conf if model_ready else 0.0

    return {
        "status": status,
        "cause": cause,
        "confidence": round(float(conf), 2),
        "details": root["details"] if status != "Normal" else "",
        "model_ready": model_ready,
    }
