import pandas as pd
from dashboard.core.root_cause import get_root_cause
from dashboard.core.analyzer import detect_trend


def analyze_csv(file):
    """
    Run offline anomaly analysis on an uploaded CSV file.

    Expected columns: time, cpu, memory, temperature, power
    Returns a result dict or {'error': '...'} on failure.
    """
    try:
        df = pd.read_csv(file)
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

    required = {"cpu", "memory", "temperature", "power"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        return {"error": f"Missing columns: {', '.join(missing)}"}

    if df.empty or len(df) < 5:
        return {"error": "Not enough data — upload a file with at least 5 rows"}

    latest = df.iloc[-1].to_dict()

    trend = detect_trend(df)
    root = get_root_cause(df, latest)

    summary = []
    if trend:
        summary.append(trend)
    if root.get("cause") and root["cause"] not in ("Unknown", "Insufficient Data"):
        summary.append(root["cause"])

    return {
        "status": "Analysis Complete",
        "summary": summary if summary else ["No anomalies detected"],
        "root_cause": root,
    }
