"""
Rule-based root cause diagnosis.

Pattern rules (memory leak, CPU instability) look only at a recent window of
readings, so one spike from an hour ago can't keep firing forever. Threshold
rules (overheating, power spike, overload) look at the current reading.
"""

import numpy as np
import pandas as pd

WINDOW = 30                     # readings used for pattern rules

MEMORY_LEAK_MIN_RISE = 5.0      # memory must rise at least this many % points
MEMORY_LEAK_MIN_RATIO = 0.6     # share of steps that must be increases
CPU_INSTABILITY_STEP = 10.0     # mean absolute change between readings (% points)
OVERHEAT_C = 80.0
POWER_SPIKE_W = 300.0
OVERLOAD_PCT = 85.0

METRICS = ["cpu", "memory", "temperature", "power"]


def recent_window(df, latest_data=None, size=WINDOW):
    """Last `size` readings, with latest_data appended if it isn't stored yet."""
    if df is None or df.empty:
        window = pd.DataFrame(columns=METRICS)
    else:
        window = df[METRICS].astype(float).tail(size)
    if latest_data is not None:
        row = {k: float(latest_data.get(k, 0) or 0) for k in METRICS}
        window = pd.concat([window, pd.DataFrame([row])], ignore_index=True).tail(size)
    return window.fillna(0).reset_index(drop=True)


def slope(values):
    """Least-squares slope per reading."""
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(values)), values, 1)[0])


def is_memory_leak(memory):
    if len(memory) < 10:
        return False
    steps = np.diff(memory)
    rising_share = (steps > 0).mean()
    total_rise = memory[-1] - memory[0]
    return (
        rising_share >= MEMORY_LEAK_MIN_RATIO
        and total_rise >= MEMORY_LEAK_MIN_RISE
        and slope(memory) > 0
    )


def is_cpu_unstable(cpu):
    """
    Repeated large swings, measured as the average reading-to-reading change.
    A single spike only adds two big steps, so it doesn't count on its own.
    """
    return len(cpu) >= 10 and float(np.mean(np.abs(np.diff(cpu)))) > CPU_INSTABILITY_STEP


def get_root_cause(df, latest_data):
    window = recent_window(df, latest_data)
    if len(window) < 5:
        return {
            "cause": "Insufficient Data",
            "details": "Not enough data for diagnosis",
            "confidence": 0.0,
        }

    cpu = window["cpu"].values
    memory = window["memory"].values
    latest = window.iloc[-1]

    causes = []

    if is_memory_leak(memory):
        causes.append(("Memory Leak", 0.8,
                       f"Memory rose {memory[-1] - memory[0]:.1f} points over the last {len(memory)} readings"))

    if is_cpu_unstable(cpu):
        causes.append(("CPU Instability", 0.75,
                       f"CPU swings {np.mean(np.abs(np.diff(cpu))):.1f} points per reading on average"))

    if latest["temperature"] > OVERHEAT_C:
        causes.append(("Overheating", 0.9, f"Temperature {latest['temperature']:.1f} °C > {OVERHEAT_C:.0f} °C"))

    if latest["power"] > POWER_SPIKE_W:
        causes.append(("Power Spike", 0.85, f"Power {latest['power']:.1f} W > {POWER_SPIKE_W:.0f} W"))

    if latest["cpu"] > OVERLOAD_PCT and latest["memory"] > OVERLOAD_PCT:
        causes.append(("System Overload", 0.9,
                       f"CPU {latest['cpu']:.1f}% and memory {latest['memory']:.1f}% both above {OVERLOAD_PCT:.0f}%"))

    if not causes:
        return {
            "cause": "Unknown",
            "details": "No clear failure pattern detected",
            "confidence": 0.3,
        }

    name, confidence, details = max(causes, key=lambda c: c[1])
    return {"cause": name, "details": details, "confidence": confidence}


# Causes that are serious enough to flag even when the ML model disagrees
# (or hasn't been trained yet).
CRITICAL_CAUSES = {"Overheating", "Power Spike", "System Overload"}
