import pandas as pd

from dashboard.core.analyzer import analyze

HISTORY_WINDOW = 500   # recent readings used for training and analysis


def _get_history_df(limit=HISTORY_WINDOW):
    """
    Load the most recent readings (oldest first) plus the total row count.
    Only the last `limit` rows are loaded so each analysis stays fast as the
    database grows.
    """
    from dashboard.models import TelemetryReading

    total = TelemetryReading.objects.count()
    rows = list(
        TelemetryReading.objects.order_by('-timestamp', '-id')
        .values('cpu', 'memory', 'temperature', 'power')[:limit]
    )
    rows.reverse()
    df = pd.DataFrame.from_records(rows, columns=['cpu', 'memory', 'temperature', 'power'])
    return df, total


def run_analyze(data):
    """Analyze a live reading. Called by the collect_telemetry command."""
    df, total = _get_history_df()
    return analyze(data, df, total_rows=total)


def run_manual_test(cpu, memory, temperature, power):
    """Analyze manually entered values against the current history."""
    test_data = {
        "cpu": float(cpu),
        "memory": float(memory),
        "temperature": float(temperature),
        "power": float(power),
    }
    df, total = _get_history_df()
    result = analyze(test_data, df, total_rows=total)
    return {
        "status": result["status"],
        "cause": result["cause"],
        "confidence": result["confidence"],
        "details": result["details"],
        "model_ready": result["model_ready"],
    }
