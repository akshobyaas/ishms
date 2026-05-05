import psutil
import random
from datetime import datetime
import requests


def get_real_temp_power():
    """Try to read real CPU temperature and power from LibreHardwareMonitor."""
    try:
        response = requests.get("http://localhost:8085/data.json", timeout=2)
        data = response.json()

        temperature = None
        power = None

        def extract(node):
            nonlocal temperature, power
            if isinstance(node, dict):
                text = node.get("Text", "")
                value = node.get("Value", "")
                if "CPU Package" in text and "°C" in value:
                    temperature = float(value.replace(" °C", ""))
                if "CPU Package" in text and "W" in value:
                    power = float(value.replace(" W", ""))
                for child in node.get("Children", []):
                    extract(child)

        extract(data)
        return temperature, power

    except Exception:
        return None, None


def get_data():
    cpu = psutil.cpu_percent(interval=None)
    memory = psutil.virtual_memory().percent

    temperature, power = get_real_temp_power()

    if temperature is None:
        temperature = 40 + (cpu * 0.3) + random.uniform(-2, 2)
        temp_source = "fallback"
    else:
        temp_source = "real"

    if power is None:
        power = 80 + (cpu * 1.5) + random.uniform(-5, 5)
        power_source = "fallback"
    else:
        power_source = "real"

    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu": cpu,
        "memory": memory,
        "temperature": round(temperature, 2),
        "power": round(power, 2),
        "temp_source": temp_source,
        "power_source": power_source,
    }
