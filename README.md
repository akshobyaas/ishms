# Intelligent System Health Monitoring System (ISHMS)

A real-time system telemetry and anomaly detection platform built with Django. ISHMS continuously monitors CPU usage, memory consumption, temperature, and power draw — and uses a machine learning model to automatically detect anomalies and diagnose their root cause.

---

## Screenshots

### Dashboard — Normal State
![Dashboard Normal](screenshots/dashboard_normal.png)

### Dashboard — Anomaly Detected
![Dashboard Anomaly](screenshots/dashboard_anomaly.png)

### Dashboard — Suspicious State
![Dashboard Suspicious](screenshots/dashboard_suspicious.png)

### Live Metrics Panel
![Metrics Panel](screenshots/metrics_panel.png)

### Anomaly Events
![Anomaly Events](screenshots/anomaly_events.png)

### Manual Test
![Manual Test](screenshots/manual_test.png)

### CSV Upload & Offline Analysis
![CSV Upload](screenshots/csv_upload.png)

---

## Features

- **Real-time monitoring** — collects system metrics every 2 seconds via `psutil`
- **ML-based anomaly detection** — an unsupervised `IsolationForest` learns this machine's normal behaviour from its own history and flags readings that don't fit
- **Root cause analysis** — rule-based engine identifies Memory Leak, CPU Instability, Overheating, Power Spike, or System Overload
- **Live dashboard** — browser-based UI with real-time charts, current metrics, and anomaly history
- **Offline analysis** — upload a CSV file to run anomaly analysis without live collection
- **Manual testing** — enter custom CPU/memory/temperature/power values and get an instant prediction
- **Data export** — download all collected readings as a CSV file
- **REST API** — all data accessible via clean JSON endpoints

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 |
| Database | SQLite |
| ML Model | scikit-learn (IsolationForest) |
| Data Processing | pandas |
| System Metrics | psutil |
| Sensor Data (optional) | LibreHardwareMonitor |
| Frontend | HTML, CSS, JavaScript, Chart.js |

---

## Project Structure

```
ishms/
├── manage.py                          # Django entry point
├── run.py                             # Starts collector + server together
├── requirements.txt
├── screenshots/                       # README screenshots
├── telemetry/                         # Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── dashboard/                         # Main Django app
    ├── models.py                      # TelemetryReading database model
    ├── tests.py                       # Unit and API tests
    ├── views.py                       # All API endpoints and dashboard view
    ├── urls.py                        # URL routing
    ├── core/                          # Pure logic — no Django dependency
    │   ├── data_collector.py          # Reads CPU, memory, temperature, power
    │   ├── analyzer.py                # Orchestrates ML + rule-based detection
    │   ├── ml_model.py                # IsolationForest train, save and predict
    │   ├── root_cause.py              # Rule-based root cause diagnosis
    │   └── offline_analyzer.py        # CSV upload analysis
    ├── services/                      # Business logic layer
    │   ├── analysis_service.py        # run_analyze() — bridges collector and ML
    │   └── monitoring_service.py      # get_history() — paginated DB queries
    ├── management/commands/
    │   └── collect_telemetry.py       # Custom Django command for data collection
    ├── migrations/
    └── templates/dashboard/
        └── index.html                 # Dashboard UI
```

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- pip

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/akshobyaas/ishms.git
cd ishms

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up the database
python manage.py migrate

# 5. Start the application
python run.py
```

Then open **http://127.0.0.1:8000** in your browser.

---

## Running Components Separately

If you want to run the collector and web server in separate terminals:

```bash
# Terminal 1 — Web server
python manage.py runserver

# Terminal 2 — Data collector
python manage.py collect_telemetry

# With custom interval (default is 2 seconds)
python manage.py collect_telemetry --interval 5
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/latest/` | Latest readings for live charts and current metric values |
| GET | `/api/anomalies/` | Last 20 detected anomaly events |
| GET | `/api/stats/` | Session statistics — totals, averages, anomaly rate |
| GET | `/api/history/` | Paginated and filterable reading history |
| GET | `/api/export/` | Download all readings as a CSV file |
| POST | `/api/manual-test/` | Run anomaly detection on custom input values |
| POST | `/api/upload-csv/` | Upload a CSV file for offline analysis |

---

## How It Works

### Data Collection
`psutil` reads CPU and memory every 2 seconds. Temperature and power are sourced from LibreHardwareMonitor if it is running, otherwise estimated from CPU load as a fallback.

### Anomaly Detection
Detection combines an unsupervised ML model with rule-based diagnosis:

- **IsolationForest (ML)** — once 30 readings exist, a model is trained on the most recent 500 readings and retrained every 50 new readings. It needs no labels: it learns what is normal *for this machine* and scores how far each new reading departs from that. The model is saved to `ishms_model.joblib`, so the collector and the web server share it and it survives restarts. Only readings where some metric is *above* its recent median count, since running quieter than usual isn't a problem.
- **Rules** — explain *what kind* of problem it is. Pattern rules look at the last 30 readings; threshold rules look at the current reading.

| Status | When |
|---|---|
| Normal | Nothing unusual |
| Suspicious | ML says the reading is unusual but no rule explains it, CPU is swinging, or CPU/memory is clearly climbing |
| Memory Leak Suspected | Memory rose ≥ 5 points over the last 30 readings, mostly step by step |
| CPU Instability Detected | ML flags the reading **and** CPU swings > 10 points per reading on average |
| Abnormal Thermal Rise | Temperature > 80 °C |
| Power Spike Detected | Power > 300 W |
| Confirmed Anomaly | CPU and memory both > 85 % (system overload) |

Before the model is trained, the rules run on their own.

### Root Cause Analysis
Each diagnosis includes the cause, a short explanation (for example "Memory rose 12.4 points over the last 30 readings") and a confidence score.

---

## Real Sensor Data (Optional)

By default, temperature and power are **estimated from CPU load**, and the dashboard marks them `SIMULATED`. In that mode they carry no information beyond CPU, and the overheating and power-spike rules can't trigger from live data (you can still test them with Manual Test). To get real sensor readings on Windows, download and run [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) with its web server enabled on port `8085`. ISHMS will automatically detect and use it.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev key | Set a strong random key before deploying |
| `DEBUG` | `true` | Set to `false` in production |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated list of allowed hosts |

---

## Running Tests

```bash
python manage.py test dashboard
```

---

## License

This project is licensed under the MIT License.