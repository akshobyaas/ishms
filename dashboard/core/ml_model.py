"""
Unsupervised anomaly detection with IsolationForest.

The model learns what *this machine's* normal behaviour looks like from its
own recent history and flags readings that don't fit that pattern. There are
no hand-written labels, so the model can catch combinations the
rule-based checks in root_cause.py don't describe.

The trained model is saved to disk so the collector process and the web
server process share the same model, and so it survives restarts.
"""

import os
import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

MIN_TRAIN_ROWS = 30      # don't train on less history than this
RETRAIN_EVERY = 50       # retrain after this many new readings
CONTAMINATION = 0.01     # expected share of outliers in history (~0.2% false alarms when idle)

MODEL_PATH = Path(os.environ.get(
    "ISHMS_MODEL_PATH",
    Path(__file__).resolve().parents[2] / "ishms_model.joblib",
))

FEATURES = [
    "cpu", "memory", "temperature", "power",
    "cpu_trend", "memory_trend", "temp_trend", "power_trend",
    "cpu_avg", "memory_avg", "cpu_std", "memory_std",
]

_lock = threading.Lock()
_bundle = None          # {"model": IsolationForest, "n_trained": int}
_bundle_mtime = None


def create_features(df):
    df = df[["cpu", "memory", "temperature", "power"]].astype(float).copy()
    df["cpu_trend"]    = df["cpu"].diff()
    df["memory_trend"] = df["memory"].diff()
    df["temp_trend"]   = df["temperature"].diff()
    df["power_trend"]  = df["power"].diff()
    df["cpu_avg"]      = df["cpu"].rolling(5, min_periods=1).mean()
    df["memory_avg"]   = df["memory"].rolling(5, min_periods=1).mean()
    df["cpu_std"]      = df["cpu"].rolling(5, min_periods=2).std()
    df["memory_std"]   = df["memory"].rolling(5, min_periods=2).std()
    return df.fillna(0)


def fit(df):
    """Fit and return a fresh IsolationForest on a history DataFrame."""
    model = IsolationForest(
        n_estimators=150, contamination=CONTAMINATION, random_state=42,
    )
    model.fit(create_features(df)[FEATURES])
    return model


def score_to_confidence(decision):
    """
    Map IsolationForest's decision_function (negative = anomalous, roughly
    -0.5..0.5) to a 0..1 anomaly confidence, with 0.5 at the boundary.
    """
    return float(np.clip(0.5 - decision * 2, 0.0, 1.0))


def _load_from_disk():
    global _bundle, _bundle_mtime
    try:
        mtime = MODEL_PATH.stat().st_mtime
    except FileNotFoundError:
        return
    if mtime != _bundle_mtime:
        try:
            _bundle = joblib.load(MODEL_PATH)
            _bundle_mtime = mtime
        except Exception:
            pass  # half-written or corrupt file: keep whatever we had


def _save_to_disk(bundle):
    global _bundle_mtime
    tmp = MODEL_PATH.with_suffix(".tmp")
    joblib.dump(bundle, tmp)
    os.replace(tmp, MODEL_PATH)          # atomic, so readers never see half a file
    _bundle_mtime = MODEL_PATH.stat().st_mtime


def ensure_model(history_df, total_rows=None):
    """
    Make sure a model is available, training or retraining when needed.

    history_df: recent readings used for training
    total_rows: total readings collected so far (drives the retrain schedule);
                defaults to len(history_df)
    Returns True if a model is ready.
    """
    global _bundle
    n = len(history_df) if total_rows is None else total_rows

    with _lock:
        _load_from_disk()
        if len(history_df) < MIN_TRAIN_ROWS:
            return _bundle is not None
        if _bundle is None or n - _bundle["n_trained"] >= RETRAIN_EVERY:
            _bundle = {"model": fit(history_df), "n_trained": n}
            try:
                _save_to_disk(_bundle)
            except OSError:
                pass  # still usable in memory
        return True


def predict(data, history_df):
    """
    Score one reading against recent history.

    The reading is appended to the history before features are built, so
    trend and rolling features describe *this* reading, not the previous one.
    Returns (is_anomaly, confidence).
    """
    with _lock:
        bundle = _bundle
    if bundle is None:
        return False, 0.0

    row = {k: float(data[k]) for k in ("cpu", "memory", "temperature", "power")}
    tail = history_df[["cpu", "memory", "temperature", "power"]].tail(10)
    window = pd.concat([tail, pd.DataFrame([row])], ignore_index=True)
    X = create_features(window)[FEATURES].tail(1)

    model = bundle["model"]
    is_anomaly = model.predict(X)[0] == -1
    confidence = score_to_confidence(model.decision_function(X)[0])
    return bool(is_anomaly), round(confidence, 2)


def reset():
    """Forget the in-memory model (used by tests)."""
    global _bundle, _bundle_mtime
    with _lock:
        _bundle = None
        _bundle_mtime = None
