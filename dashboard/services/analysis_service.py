import pandas as pd
from dashboard.core.analyzer import analyze


def _get_history_df():
    """Load recent readings from the DB into a DataFrame for ML training."""
    from dashboard.models import TelemetryReading

    qs = TelemetryReading.objects.order_by('timestamp').values(
        'cpu', 'memory', 'temperature', 'power', 'status'
    )
    return pd.DataFrame.from_records(list(qs)) if qs.exists() else pd.DataFrame()


def run_analyze(data):
    """
    Analyze a live telemetry reading against DB history.
    Called by the collect_telemetry management command.
    """
    df = _get_history_df()
    return analyze(data, df)


def run_manual_test(cpu, memory, temperature, power):
    """
    Run anomaly detection for manually entered values.
    Called by the manual-test API endpoint.
    """
    test_data = {
        "time": None,
        "cpu": float(cpu),
        "memory": float(memory),
        "temperature": float(temperature),
        "power": float(power),
        "temp_source": "manual",
        "power_source": "manual",
    }
    df = _get_history_df()
    result = analyze(test_data, df)
    return {
        "status": result.get("status"),
        "cause": result.get("cause"),
        "confidence": result.get("confidence"),
    }
