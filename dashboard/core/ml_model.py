import threading
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

model = None
_lock = threading.Lock()


def create_features(df):
    df = df.copy()
    df["cpu_trend"]    = df["cpu"].diff()
    df["memory_trend"] = df["memory"].diff()
    df["temp_trend"]   = df["temperature"].diff()
    df["power_trend"]  = df["power"].diff()
    df["cpu_avg"]      = df["cpu"].rolling(5).mean()
    df["memory_avg"]   = df["memory"].rolling(5).mean()
    df["cpu_std"]      = df["cpu"].rolling(5).std()
    df["memory_std"]   = df["memory"].rolling(5).std()
    return df.fillna(0)


def label_data(df):
    """
    Label rows as anomalous (1) or normal (0).
    Uses OR conditions so the model sees enough positive examples to be useful.
    """
    df = df.copy()
    df["label"] = 0
    df.loc[df["cpu"] > 80, "label"] = 1
    df.loc[df["memory"] > 85, "label"] = 1
    df.loc[df["temperature"] > 75, "label"] = 1
    df.loc[(df["cpu"] > 70) & (df["memory"] > 70), "label"] = 1
    return df


FEATURES = [
    "cpu", "memory", "temperature", "power",
    "cpu_trend", "memory_trend", "temp_trend", "power_trend",
    "cpu_avg", "memory_avg", "cpu_std", "memory_std",
]


def train_model(df):
    global model
    df = create_features(df)
    df = label_data(df)
    X = df[FEATURES]
    y = df["label"]
    with _lock:
        m = RandomForestClassifier(n_estimators=100, random_state=42)
        m.fit(X, y)
        model = m


def predict(data, df):
    with _lock:
        if model is None:
            return False, 0.0
        m = model

    df = create_features(df)
    latest = df.iloc[-1]
    X = pd.DataFrame([latest[FEATURES]], columns=FEATURES)

    prediction = m.predict(X)[0]
    probs = m.predict_proba(X)[0]
    prob = probs[1] if len(probs) > 1 else 0.0

    return prediction == 1, float(prob)
