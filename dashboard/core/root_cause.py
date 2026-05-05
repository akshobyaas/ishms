def increasing_trend(values, threshold=0.7):
    increases = sum(y > x for x, y in zip(values, values[1:]))
    return increases > len(values) * threshold


def high_variation(values, threshold=10):
    return (max(values) - min(values)) > threshold


def get_root_cause(df, latest_data):
    if df.empty or len(df) < 5:
        return {
            "cause": "Insufficient Data",
            "details": "Not enough data for diagnosis",
            "confidence": 0.0,
        }

    df = df.fillna(0)
    cpu    = df["cpu"].values
    memory = df["memory"].values

    causes = []

    if increasing_trend(memory):
        causes.append(("Memory Leak", 0.8))

    if high_variation(cpu, threshold=10):
        causes.append(("CPU Instability", 0.75))

    if float(latest_data.get("temperature", 0)) > 80:
        causes.append(("Overheating", 0.9))

    if float(latest_data.get("power", 0)) > 300:
        causes.append(("Power Spike", 0.85))

    if float(latest_data.get("cpu", 0)) > 85 and float(latest_data.get("memory", 0)) > 85:
        causes.append(("System Overload", 0.9))

    if not causes:
        return {
            "cause": "Unknown",
            "details": "No clear failure pattern detected",
            "confidence": 0.3,
        }

    best = max(causes, key=lambda x: x[1])
    return {
        "cause": best[0],
        "details": f"Detected pattern: {best[0]}",
        "confidence": best[1],
    }
