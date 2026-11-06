import numpy as np
import pandas as pd


def build_demo_data() -> dict:
    """Deterministic sample data for UI development; never represents live machine status."""
    rng = np.random.default_rng(42)
    now = pd.Timestamp.now(tz="UTC")

    # Prediction records with enough timestamp span for useful hourly charts.
    n = 360
    udi = np.arange(9657, 9657 + n)
    probabilities = rng.beta(0.45, 55, size=n)
    risk_idx = rng.choice(n, size=22, replace=False)
    probabilities[risk_idx] = rng.uniform(0.006, 0.035, size=len(risk_idx))
    threshold = np.full(n, 0.004751)
    predicted = (probabilities >= threshold).astype(int)
    predictions = pd.DataFrame({
        "UDI": udi,
        "failure_probability": probabilities,
        "predicted_failure": predicted,
        "model_uri": "models:/predictive_maintenance/Production",
        "threshold": threshold,
        "prediction_timestamp": pd.date_range(end=now, periods=n, freq="5min"),
    })

    feature_names = [
        "Temperature_difference_K", "Tool_wear_min", "Mechanical_power_W",
        "Torque_wear", "Speed_wear", "Power_wear", "Air_temperature_K",
        "Process_temperature_K", "Rotational_speed_rpm", "Torque_Nm",
    ]
    psi_values = [0.293, 0.286, 0.271, 0.18, 0.14, 0.08, 0.09, 0.11, 0.14, 0.10]
    drift_rows = []
    history_rows = []
    for i, feature in enumerate(feature_names):
        psi = float(psi_values[i] + rng.normal(0, 0.006))
        if i < 3:
            psi = max(0.255, psi)
        drift_rows.append({
            "feature": feature,
            "feature_type": "numeric",
            "current_records": 1000,
            "psi": psi,
            "ks_statistic": float(rng.uniform(0.08, 0.22)),
            "ks_pvalue": float(10 ** rng.uniform(-35, -2)),
            "psi_status": "SIGNIFICANT_DRIFT" if psi >= 0.25 else "NO_SIGNIFICANT_DRIFT",
            "ks_significant": bool(rng.random() < 0.6),
            "calculated_at": now,
            "monitoring_run_id": "demo-run",
            "reference_records": 8000,
            "rolling_window_size": 1000,
            "minimum_udi": 9657,
            "maximum_udi": 1000900,
        })
        for j, timestamp in enumerate(pd.date_range(end=now, periods=12, freq="6h")):
            history_rows.append({
                "feature": feature,
                "psi": max(0.01, psi * (0.55 + 0.045 * j) + rng.normal(0, 0.012)),
                "calculated_at": timestamp,
                "psi_status": "SIGNIFICANT_DRIFT" if psi >= 0.25 else "NO_SIGNIFICANT_DRIFT",
            })

    # Reference baseline and streaming batches. Source filename and ingestion time
    # are deliberately present so the Overview can demonstrate batch-level trends.
    n_reference = 8000
    reference = pd.DataFrame({
        "UDI": np.arange(1, n_reference + 1),
        "Temperature_difference_K": rng.normal(10.0, 1.8, n_reference),
        "Tool_wear_min": rng.normal(105, 28, n_reference).clip(0, 250),
        "Mechanical_power_W": rng.normal(4200, 450, n_reference),
        "Torque_wear": rng.normal(2800, 550, n_reference),
        "Speed_wear": rng.normal(36000, 6000, n_reference),
        "Power_wear": rng.normal(150000, 24000, n_reference),
        "Air_temperature_K": rng.normal(300, 2, n_reference),
        "Process_temperature_K": rng.normal(310, 2, n_reference),
        "Rotational_speed_rpm": rng.normal(1500, 120, n_reference),
        "Torque_Nm": rng.normal(40, 8, n_reference),
    })

    batch_sizes = [500, 100, 300, 100]
    batch_names = [
        "ai4i_csv_inbox_batch_001.csv",
        "ai4i_csv_inbox_batch_002.csv",
        "ai4i_csv_inbox_batch_003.csv",
        "ai4i_csv_inbox_batch_004.csv",
    ]
    current_parts = []
    next_udi = 1000001
    for i, (size, filename) in enumerate(zip(batch_sizes, batch_names)):
        shift = [0.8, 1.2, 1.7, 2.1][i]
        part = pd.DataFrame({
            "UDI": np.arange(next_udi, next_udi + size),
            "Temperature_difference_K": rng.normal(10.0 + shift, 2.0 + i * 0.1, size),
            "Tool_wear_min": rng.normal(110 + i * 4, 30, size).clip(0, 250),
            "Mechanical_power_W": rng.normal(4250 + i * 110, 470, size),
            "Torque_wear": rng.normal(2850 + i * 90, 570, size),
            "Speed_wear": rng.normal(36000 + i * 500, 6200, size),
            "Power_wear": rng.normal(152000 + i * 3500, 25000, size),
            "Air_temperature_K": rng.normal(300 + i * 0.15, 2, size),
            "Process_temperature_K": rng.normal(310 + i * 0.2, 2, size),
            "Rotational_speed_rpm": rng.normal(1500 - i * 12, 125, size),
            "Torque_Nm": rng.normal(40 + i * 1.2, 8, size),
            "batch": filename,
            "_ingest_timestamp": now - pd.Timedelta(hours=(len(batch_sizes) - i) * 5),
        })
        current_parts.append(part)
        next_udi += size
    current = pd.concat(current_parts, ignore_index=True)

    # Current state is one row per feature. Some alerts are open, acknowledged or resolved.
    alert_state_rows = []
    event_rows = []
    statuses = ["OPEN", "OPEN", "ACKNOWLEDGED", "OPEN", "RESOLVED", "ACKNOWLEDGED", "RESOLVED", "RESOLVED", "OPEN", "RESOLVED"]
    severities = ["HIGH" if v >= 0.25 else "MEDIUM" if v >= 0.10 else "LOW" for v in psi_values]
    for i, row in enumerate(drift_rows):
        status = statuses[i]
        alert = {
            "alert_id": f"DEMO-{i+1:03d}",
            "feature": row["feature"],
            "severity": severities[i],
            "alert_status": status,
            "psi": row["psi"],
            "ks_pvalue": row["ks_pvalue"],
            "recommended_action": "Review recent sensor readings and operating-condition changes",
            "notification_status": "SENT" if i < 7 else "PENDING",
            "first_detected_at": now - pd.Timedelta(days=2 + i),
            "event_timestamp": now - pd.Timedelta(hours=i * 3),
        }
        alert_state_rows.append(alert)
        event_rows.append({
            **alert,
            "event_id": f"EVENT-{i+1:03d}-NEW",
            "event_type": "NEW_ALERT",
            "recorded_at": now - pd.Timedelta(days=2 + i),
        })
        if status in {"ACKNOWLEDGED", "RESOLVED"}:
            event_rows.append({
                **alert,
                "event_id": f"EVENT-{i+1:03d}-{status}",
                "event_type": status,
                "recorded_at": now - pd.Timedelta(hours=i * 3),
            })

    alert_state = pd.DataFrame(alert_state_rows)
    alert_events = pd.DataFrame(event_rows).sort_values("recorded_at", ascending=False).reset_index(drop=True)

    return {
        "predictions": predictions,
        "drift_rolling": pd.DataFrame(drift_rows),
        "drift_history": pd.DataFrame(history_rows),
        "reference": reference,
        "current": current,
        "current_rolling": current.tail(1000).copy(),
        "alerts": alert_state.copy(),
        "alert_state": alert_state,
        "alert_events": alert_events,
        "pipeline": pd.DataFrame(),
        "errors": {},
        "source_mode": "DEMO DATA",
    }
