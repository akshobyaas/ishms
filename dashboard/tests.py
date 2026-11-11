import io
import json
import random
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from django.test import Client, TestCase

from dashboard.core import ml_model
from dashboard.core.analyzer import ML_CAUSE, analyze, detect_trend
from dashboard.core.offline_analyzer import analyze_csv
from dashboard.core.root_cause import get_root_cause
from dashboard.models import TelemetryReading


def normal_history(n=200, seed=0):
    """Readings from a quiet machine: CPU ~20 %, memory ~50 %."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        cpu = 20 + rng.uniform(-5, 5)
        rows.append({
            "cpu": cpu,
            "memory": 50 + rng.uniform(-1, 1),
            "temperature": 40 + cpu * 0.3 + rng.uniform(-2, 2),
            "power": 80 + cpu * 1.5 + rng.uniform(-5, 5),
        })
    return pd.DataFrame(rows)


class TempModelPathMixin:
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_path = ml_model.MODEL_PATH
        ml_model.MODEL_PATH = Path(self._tmp.name) / "model.joblib"
        ml_model.reset()

    def tearDown(self):
        ml_model.MODEL_PATH = self._old_path
        ml_model.reset()
        self._tmp.cleanup()
        super().tearDown()


class MLModelTests(TempModelPathMixin, TestCase):
    def test_prediction_depends_on_the_input_reading(self):
        """Regression: predict() used to ignore its input and score the last stored row."""
        df = normal_history()
        self.assertTrue(ml_model.ensure_model(df))
        quiet = {"cpu": 20, "memory": 50, "temperature": 46, "power": 110}
        busy = {"cpu": 99, "memory": 97, "temperature": 70, "power": 230}
        q_anom, q_conf = ml_model.predict(quiet, df)
        b_anom, b_conf = ml_model.predict(busy, df)
        self.assertFalse(q_anom)
        self.assertTrue(b_anom)
        self.assertGreater(b_conf, q_conf)

    def test_not_trained_on_too_little_data(self):
        self.assertFalse(ml_model.ensure_model(normal_history(10)))

    def test_model_is_saved_and_shared_between_processes(self):
        df = normal_history()
        ml_model.ensure_model(df)
        self.assertTrue(ml_model.MODEL_PATH.exists())
        ml_model.reset()                       # simulate the other process
        self.assertTrue(ml_model.ensure_model(df.head(10)))

    def test_retrains_after_enough_new_readings(self):
        df = normal_history()
        ml_model.ensure_model(df, total_rows=200)
        first = ml_model._bundle["model"]
        ml_model.ensure_model(df, total_rows=220)
        self.assertIs(ml_model._bundle["model"], first)
        ml_model.ensure_model(df, total_rows=250)
        self.assertIsNot(ml_model._bundle["model"], first)


class RootCauseTests(TestCase):
    def test_old_cpu_spike_does_not_keep_reporting_instability(self):
        """Regression: CPU instability used to be computed over all history."""
        df = normal_history(200)
        df.loc[5, "cpu"] = 100          # one spike long ago
        latest = {"cpu": 20, "memory": 50, "temperature": 46, "power": 110}
        self.assertEqual(get_root_cause(df, latest)["cause"], "Unknown")

    def test_single_recent_spike_is_not_instability(self):
        df = normal_history(200)
        df.loc[df.index[-15], "cpu"] = 100
        latest = {"cpu": 20, "memory": 50, "temperature": 46, "power": 110}
        self.assertNotEqual(get_root_cause(df, latest)["cause"], "CPU Instability")

    def test_recent_cpu_swings_are_instability(self):
        df = normal_history(200)
        df.loc[df.index[-20:], "cpu"] = [10, 90] * 10
        latest = {"cpu": 15, "memory": 50, "temperature": 46, "power": 110}
        self.assertEqual(get_root_cause(df, latest)["cause"], "CPU Instability")

    def test_steady_memory_climb_is_a_leak(self):
        df = normal_history(200)
        df.loc[df.index[-30:], "memory"] = np.linspace(50, 70, 30)
        latest = {"cpu": 20, "memory": 71, "temperature": 46, "power": 110}
        self.assertEqual(get_root_cause(df, latest)["cause"], "Memory Leak")

    def test_threshold_rules_use_the_latest_reading(self):
        df = normal_history(50)
        hot = {"cpu": 20, "memory": 50, "temperature": 90, "power": 110}
        self.assertEqual(get_root_cause(df, hot)["cause"], "Overheating")


class TrendTests(TestCase):
    def test_noise_is_not_a_trend(self):
        """Regression: a 0.1 % rise over 5 readings used to count as a trend."""
        df = normal_history(50)
        hits = sum(
            detect_trend(df.iloc[:i]) is not None for i in range(10, 50)
        )
        self.assertEqual(hits, 0)

    def test_clear_cpu_climb_is_a_trend(self):
        df = normal_history(50)
        df.loc[df.index[-10:], "cpu"] = np.linspace(20, 80, 10)
        self.assertEqual(detect_trend(df), "Increasing CPU Trend")


class AnalyzerTests(TempModelPathMixin, TestCase):
    def test_quiet_reading_is_normal(self):
        df = normal_history()
        result = analyze({"cpu": 21, "memory": 50, "temperature": 46, "power": 112}, df)
        self.assertEqual(result["status"], "Normal")
        self.assertTrue(result["model_ready"])

    def test_quieter_than_normal_is_not_an_anomaly(self):
        df = normal_history()
        result = analyze({"cpu": 0, "memory": 49, "temperature": 38, "power": 75}, df)
        self.assertEqual(result["status"], "Normal")

    def test_idle_machine_rarely_alarms(self):
        df = normal_history(400, seed=3)
        statuses = [analyze(df.iloc[i].to_dict(), df.iloc[:i])["status"] for i in range(200, 400)]
        self.assertLessEqual(sum(s != "Normal" for s in statuses), 2)

    def test_critical_rule_fires_without_a_model(self):
        df = normal_history(10)
        result = analyze({"cpu": 95, "memory": 95, "temperature": 60, "power": 200}, df)
        self.assertEqual(result["status"], "Confirmed Anomaly")
        self.assertEqual(result["cause"], "System Overload")
        self.assertFalse(result["model_ready"])

    def test_ml_flags_unusual_reading_rules_miss(self):
        df = normal_history()
        # Nothing crosses a fixed threshold, but this is far from normal.
        result = analyze({"cpu": 35, "memory": 62, "temperature": 50, "power": 135}, df)
        self.assertEqual(result["status"], "Suspicious")
        self.assertEqual(result["cause"], ML_CAUSE)

    def test_ml_plus_rule_gives_specific_anomaly(self):
        df = normal_history()
        df.loc[df.index[-20:], "cpu"] = [10, 90] * 10
        result = analyze({"cpu": 85, "memory": 50, "temperature": 66, "power": 210}, df)
        self.assertEqual(result["status"], "CPU Instability Detected")


class OfflineAnalyzerTests(TestCase):
    def _csv(self, df):
        return io.BytesIO(df.to_csv(index=False).encode())

    def test_missing_columns(self):
        self.assertIn("error", analyze_csv(self._csv(pd.DataFrame({"cpu": [1, 2]}))))

    def test_non_numeric_rows_are_dropped(self):
        df = normal_history(40).astype(object)
        df.loc[3, "cpu"] = "oops"
        result = analyze_csv(self._csv(df))
        self.assertEqual(result["rows"], 39)
        self.assertIn("root_cause", result)


class ApiTests(TempModelPathMixin, TestCase):
    def setUp(self):
        super().setUp()
        for row in normal_history(60).to_dict("records"):
            TelemetryReading.objects.create(**row)

    def test_bad_query_params_do_not_crash(self):
        c = Client()
        self.assertEqual(c.get("/api/latest/?limit=abc").status_code, 200)
        self.assertEqual(len(c.get("/api/latest/?limit=99999").json()["cpu"]), 60)
        self.assertEqual(c.get("/api/history/?page=x&page_size=-4").status_code, 200)

    def test_latest_reports_sensor_source(self):
        self.assertEqual(Client().get("/api/latest/").json()["current"]["temp_source"], "fallback")

    def test_manual_test_result_changes_with_input(self):
        """Regression: the ML part of manual test ignored the entered values."""
        c = Client()
        post = lambda body: c.post("/api/manual-test/", json.dumps(body),
                                   content_type="application/json").json()["result"]
        quiet = post({"cpu": 20, "memory": 50, "temperature": 46, "power": 110})
        busy = post({"cpu": 75, "memory": 80, "temperature": 62, "power": 190})
        self.assertEqual(quiet["status"], "Normal")
        self.assertNotEqual(busy["status"], "Normal")

    def test_manual_test_validation(self):
        c = Client()
        r = c.post("/api/manual-test/", json.dumps({"cpu": 200, "memory": 1, "temperature": 30, "power": 50}),
                   content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/manual-test/", "not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_post_endpoints_require_csrf(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/api/manual-test/", json.dumps({"cpu": 1, "memory": 1, "temperature": 30, "power": 50}),
                   content_type="application/json")
        self.assertEqual(r.status_code, 403)
        c.get("/")                                    # sets the csrftoken cookie
        token = c.cookies["csrftoken"].value
        r = c.post("/api/manual-test/", json.dumps({"cpu": 1, "memory": 1, "temperature": 30, "power": 50}),
                   content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)

    def test_csv_upload_response_shape_matches_frontend(self):
        csv = io.BytesIO(normal_history(40).to_csv(index=False).encode())
        csv.name = "data.csv"
        r = Client().post("/api/upload-csv/", {"file": csv})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("cause", body["root_cause"])    # frontend reads d.root_cause.cause
        self.assertIn("summary", body)
