import pandas as pd

from dashboard.core import ml_model
from dashboard.core.analyzer import detect_trend
from dashboard.core.root_cause import get_root_cause

REQUIRED = ["cpu", "memory", "temperature", "power"]


def analyze_csv(file):
    """
    Run offline anomaly analysis on an uploaded CSV file.

    Expected columns: cpu, memory, temperature, power (time is optional).
    Returns a result dict or {'error': '...'} on failure.
    """
    try:
        df = pd.read_csv(file)
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        return {"error": f"Missing columns: {', '.join(missing)}"}

    df[REQUIRED] = df[REQUIRED].apply(pd.to_numeric, errors="coerce")
    df = df.dropna(subset=REQUIRED).reset_index(drop=True)

    if len(df) < 5:
        return {"error": "Not enough data — upload a file with at least 5 valid rows"}

    history, latest = df.iloc[:-1], df.iloc[-1].to_dict()
    trend = detect_trend(history, latest)
    root = get_root_cause(history, latest)

    summary = []
    if trend:
        summary.append(trend)
    if root["cause"] not in ("Unknown", "Insufficient Data"):
        summary.append(f"{root['cause']} — {root['details']}")

    # Unsupervised pass over the whole file: which rows don't fit the rest?
    anomalous_rows = []
    if len(df) >= ml_model.MIN_TRAIN_ROWS:
        model = ml_model.fit(df)
        flags = model.predict(ml_model.create_features(df)[ml_model.FEATURES])
        anomalous_rows = [int(i) + 1 for i in (flags == -1).nonzero()[0]]  # 1-based
        if anomalous_rows:
            summary.append(
                f"ML: {len(anomalous_rows)} of {len(df)} rows stand out most from the rest "
                f"(expects ~{ml_model.CONTAMINATION:.0%} outliers)"
            )

    return {
        "status": "Analysis Complete",
        "rows": len(df),
        "summary": summary or ["No anomalies detected"],
        "root_cause": root,
        "anomalous_rows": anomalous_rows[:50],
    }
