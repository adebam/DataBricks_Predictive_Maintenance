"""Step 4 source-contract checks, using pandas without needing a Dash server.

These supplement tests/test_dashboard.py, which runs after installing requirements.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def extract(path, names, env):
    """Compile the production function ASTs with only their helper dependencies."""
    tree = ast.parse((ROOT / path).read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = dict(env)
    exec(compile(module, str(ROOT / path), "exec"), namespace)
    return namespace


HELPERS = extract("app.py", [
    "_latest_per_feature", "_psi_classification", "_drift_with_classes",
    "_normalize_alert_state", "_open_alerts", "_alert_counts",
    "_distribution_payload", "_prediction_time_groups",
], {"pd": pd, "np": np})


def test_drift_latest_single_rolling_run_and_categories():
    rows = pd.DataFrame([
        {"feature": "A", "psi": 0.19, "monitoring_run_id": "older", "calculated_at": "2026-11-01T12:00:00"},
        {"feature": "B", "psi": 0.01, "monitoring_run_id": "older", "calculated_at": "2026-11-01T12:00:00"},
        {"feature": "A", "psi": 0.29, "monitoring_run_id": "latest", "calculated_at": "2026-11-02T12:00:00"},
    ])
    actual = HELPERS["_drift_with_classes"](rows)
    assert actual["feature"].tolist() == ["A"]
    assert actual["dashboard_drift_status"].tolist() == ["SIGNIFICANT_DRIFT"]
    f = HELPERS["_psi_classification"]
    assert f(0.099) == "STABLE"
    assert f(0.100) == "MODERATE_DRIFT"
    assert f(0.250) == "SIGNIFICANT_DRIFT"


def test_kde_samples_use_full_baseline_and_correct_rolling_1000():
    reference = pd.DataFrame({"F": range(8000)})
    trend_current = pd.DataFrame({"F": range(5000)})
    rolling = pd.DataFrame({"F": range(1000)})
    payload = HELPERS["_distribution_payload"]({
        "reference": reference, "current": trend_current,
        "current_rolling": rolling,
    }, ["F"])
    assert len(payload["F"]["reference"]) == 8000
    assert len(payload["F"]["current"]) == 1000
    assert payload["F"]["reference"][-1] == 7999


def test_alert_state_naming_and_open_recovery_pending_count():
    state = pd.DataFrame([
        {"feature": "A", "alert_status": "OPEN", "current_severity": "HIGH", "last_psi": .3, "last_ks_pvalue": 1e-10, "last_detected_at": "2026-11-03"},
        {"feature": "B", "alert_status": "RECOVERY_PENDING", "current_severity": "NORMAL", "last_psi": .02},
        {"feature": "C", "alert_status": "NO_ALERT", "current_severity": "NORMAL", "last_psi": .01},
        {"feature": "D", "alert_status": "RESOLVED", "current_severity": "NORMAL", "last_psi": .01},
    ])
    events = pd.DataFrame([
        {"feature": "A", "event_type": "NEW_ALERT"},
        {"feature": "A", "event_type": "ESCALATED"},
        {"feature": "B", "event_type": "NEW_ALERT"},
    ])
    data = {"alert_state": state, "alert_events": events}
    active = HELPERS["_open_alerts"](data)
    assert set(active["feature"]) == {"A", "B"}
    assert active.set_index("feature").loc["A", "psi"] == 0.3
    assert active.set_index("feature").loc["A", "severity"] == "HIGH"
    assert active.set_index("feature").loc["A", "ks_pvalue"] == 1e-10
    assert HELPERS["_alert_counts"](data) == (2, 2, 0, 1)


def test_model_behavior_is_predictions_only():
    frame = pd.DataFrame({
        "prediction_timestamp": pd.to_datetime(["2026-11-01 00:01", "2026-11-01 00:06", "2026-11-01 00:12", "2026-11-01 00:31"]),
        "predicted_failure": [0, 1, 1, 0],
        "failure_probability": [.01, .5, .95, .05],
    })
    out = HELPERS["_prediction_time_groups"](frame)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["predicted_failure_rate_pct"] == 50.
    assert np.isclose(row["median_probability_pct"], 27.5)
    assert np.isclose(row["p95_probability_pct"], 88.25)


def test_source_queries_match_notebook_51_window_and_rolling_history():
    calls = []
    def query_df(sql):
        calls.append(sql)
        return pd.DataFrame()
    settings = SimpleNamespace(
        demo_mode=False,
        predictions_table="c.g.predictions", drift_rolling_table="c.g.rolling",
        drift_reference_table="c.g.reference", bronze_table="c.b.bronze",
        monitoring_table="c.g.monitoring", current_features_table="c.g.gold",
        alerts_table="c.g.alerts", alert_state_table="c.g.state",
        alert_events_table="c.g.events", pipeline_status_table="",
    )
    namespace = extract("data.py", ["_read", "load_dashboard_data"], {
        "pd": pd, "settings": settings, "query_df": query_df,
        "build_demo_data": lambda: {},
    })
    result = namespace["load_dashboard_data"]()
    sql = "\n".join(calls)
    assert "ORDER BY _gold_processed_at DESC, UDI DESC LIMIT 1000" in sql
    assert "SELECT * FROM c.g.reference LIMIT 10000" in sql
    assert "SELECT * FROM c.g.rolling ORDER BY calculated_at DESC LIMIT 3000" in sql
    assert "c.g.drift" not in sql
    assert "current_rolling" in result
