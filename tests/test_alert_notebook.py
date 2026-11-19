"""Exercise the shipped notebook expressions and alert SQL using local Spark."""
import ast
import json
import os
from pathlib import Path

import pytest
from pyspark.sql import SparkSession, functions as F

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = json.loads((ROOT / "Predictive_Maintenance/51_Data_Drift_Monitoring.ipynb").read_text())
ALERT = json.loads((ROOT / "Predictive_Maintenance/60_Predictive_Maintenance_Alert.dbalert.json").read_text())


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    session = (SparkSession.builder.master("local[1]").appName("alert-regression-tests")
               .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "1")
               .config("spark.sql.warehouse.dir", str(tmp_path_factory.mktemp("warehouse")))
               .getOrCreate())
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


def code_containing(text):
    return next("".join(cell["source"]) for cell in NOTEBOOK["cells"]
                if cell["cell_type"] == "code" and text in "".join(cell["source"]))


def assignments(source, names, namespace):
    tree = ast.parse(source)
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)]
    nodes.sort(key=lambda node: node.lineno)
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "notebook", "exec"), namespace)
    return namespace


def test_recovery_is_emitted_once_and_can_reopen(spark):
    cases = [
        (0, "OPEN", "HIGH", 0, "NORMAL", "RECOVERY_PENDING", "RECOVERY_PENDING"),
        (1, "RECOVERY_PENDING", "NORMAL", 1, "NORMAL", "RESOLVED", "RESOLVED"),
        (2, "RESOLVED", "NORMAL", 2, "NORMAL", "RESOLVED_CONTINUING", "RESOLVED"),
        (3, "RESOLVED", "NORMAL", 2, "HIGH", "NEW_ALERT", "OPEN"),
        (4, "OPEN", "HIGH", 0, "HIGH", "CONTINUING", "OPEN"),
        (5, "OPEN", "WARNING", 0, "HIGH", "ESCALATED", "OPEN"),
        (6, "RECOVERY_PENDING", "NORMAL", 1, "HIGH", "REOPENED", "OPEN"),
    ]
    previous = spark.createDataFrame([(r[0], "Torque_Nm", *r[1:4]) for r in cases],
        "id int, feature string, alert_status string, current_severity string, consecutive_normal_windows int").alias("s")
    current = spark.createDataFrame([(r[0], r[4]) for r in cases], "id int, alert_severity string").alias("c")
    joined = current.join(previous, F.col("c.id") == F.col("s.id"))
    ns = assignments(code_containing("transition = ("), {
        "has_previous", "active", "previous_status", "previous_severity", "new_severity",
        "normal_count", "next_normal_count", "transition", "new_status",
    }, {"F": F})
    actual = joined.select(F.col("c.id"), ns["transition"].alias("transition"), ns["new_status"].alias("status")).collect()
    assert {r.id: (r.transition, r.status) for r in actual} == {r[0]: (r[5], r[6]) for r in cases}


def test_event_builder_ignores_continuing_recovery(spark):
    schema = ("feature string, feature_type string, last_processed_monitoring_run_id string, "
              "last_transition string, current_severity string, alert_status string, "
              "last_psi double, last_ks_pvalue double, recommended_action string, last_calculated_at timestamp")
    from datetime import datetime
    rows = [("Torque_Nm", "numeric", "run-2", "RESOLVED", "NORMAL", "RESOLVED", 0.02, 0.9, "Recovered", datetime(2026, 11, 19)),
            ("Tool_wear_min", "numeric", "run-2", "RESOLVED_CONTINUING", "NORMAL", "RESOLVED", 0.01, 0.9, "Recovered", datetime(2026, 11, 19))]
    spark.createDataFrame(rows, schema).createOrReplaceTempView("state_snapshot")
    ns = assignments(code_containing("event_source_df = ("), {"event_source_df"}, {
        "spark": spark, "F": F, "DRIFT_ALERT_STATE_TABLE": "state_snapshot", "rolling_run_id": "run-2",
    })
    events = ns["event_source_df"].collect()
    assert len(events) == 1
    assert events[0].feature == "Torque_Nm"
    assert events[0].notification_required is True
    assert events[0].notification_status == "PENDING"


def test_monitoring_merge_preserves_concurrent_delivery_timestamp(spark, monkeypatch):
    """Run the real lifecycle cell; inspect only the Delta write boundary."""
    from datetime import datetime
    import sys
    import types
    now = datetime(2026, 11, 19)
    spark.createDataFrame([
        ("Torque_Nm", "numeric", "new-run", "NORMAL", now, 0.02, 0.9, "Recovered")
    ], "feature string, feature_type string, monitoring_run_id string, alert_severity string, "
       "calculated_at timestamp, psi double, ks_pvalue double, recommended_action string").createOrReplaceTempView("current_alerts")
    spark.createDataFrame([
        ("Torque_Nm", "OPEN", "HIGH", 0, "old-run", now, now, now, 0.4)
    ], "feature string, alert_status string, current_severity string, consecutive_normal_windows int, "
       "last_processed_monitoring_run_id string, first_detected_at timestamp, "
       "last_detected_at timestamp, last_notified_at timestamp, last_psi double").createOrReplaceTempView("existing_state")
    writes = {}
    class Merge:
        @classmethod
        def forName(cls, *args): return cls()
        def alias(self, *args): return self
        def merge(self, source, condition):
            writes["source"] = source.collect()
            return self
        def whenMatchedUpdate(self, set):
            writes["set"] = set
            return self
        def whenNotMatchedInsertAll(self): return self
        def execute(self): writes["executed"] = True
    module = types.ModuleType("delta.tables")
    module.DeltaTable = Merge
    monkeypatch.setitem(sys.modules, "delta", types.ModuleType("delta"))
    monkeypatch.setitem(sys.modules, "delta.tables", module)
    exec(code_containing("transition = ("), {
        "spark": spark, "DRIFT_ALERTS_TABLE": "current_alerts",
        "DRIFT_ALERT_STATE_TABLE": "existing_state", "rolling_run_id": "new-run", "display": lambda df: None,
    })
    assert writes["executed"]
    assert writes["source"][0].last_transition == "RECOVERY_PENDING"
    assert "last_notified_at" not in writes["set"]
    assert writes["set"]["alert_status"] == "source.alert_status"


def load_events(spark, rows):
    schema = ("event_id string, feature string, event_type string, severity string, psi double, "
              "ks_pvalue double, recommended_action string, event_timestamp timestamp, "
              "notification_required boolean, notification_status string")
    spark.createDataFrame(rows, schema).createOrReplaceTempView("alert_events")


def evaluate(spark):
    query = "\n".join(ALERT["query_lines"]).replace(
        "predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alert_events", "alert_events")
    rows = spark.sql(query).collect()
    source = ALERT["evaluation"]["source"]["name"]
    threshold = ALERT["evaluation"]["threshold"]["value"]["double_value"]
    return rows[0][source] > threshold, rows


def test_recovery_only_triggers_and_sent_recovery_clears(spark):
    from datetime import datetime
    event = ("one", "Torque_Nm", "RESOLVED", "NORMAL", 0.02, 0.9, "Recovered", datetime(2026, 11, 19), True)
    load_events(spark, [(*event, "PENDING")])
    triggered, rows = evaluate(spark)
    assert triggered
    assert rows[0].event_type == "RESOLVED"
    load_events(spark, [(*event, "SENT")])
    triggered, rows = evaluate(spark)
    assert not triggered
    assert len(rows) == 1 and rows[0].has_pending_event == 0


def test_empty_queue_does_not_trigger(spark):
    load_events(spark, [])
    triggered, rows = evaluate(spark)
    assert not triggered
    assert len(rows) == 1


def test_nonactionable_events_do_not_trigger(spark):
    from datetime import datetime
    load_events(spark, [("one", "Torque_Nm", "DOWNGRADED", "WARNING", 0.2, 0.1,
                        "Monitor", datetime(2026, 11, 19), False, "NOT_REQUIRED")])
    assert not evaluate(spark)[0]


def test_monitoring_never_retires_old_pending_events(spark):
    from datetime import datetime
    load_events(spark, [("old", "Torque_Nm", "NEW_ALERT", "HIGH", 0.4, 0.01,
                        "Investigate", datetime(2000, 1, 1), True, "PENDING")])
    before = spark.table("alert_events").collect()
    captured = []
    exec(code_containing("Notifications awaiting confirmed delivery"), {
        "spark": spark, "DRIFT_ALERT_EVENTS_TABLE": "alert_events", "display": captured.append,
    })
    assert spark.table("alert_events").collect() == before
    assert captured[0].collect()[0].event_id == "old"


def test_schedule_and_notebook_preview_match_exported_alert():
    assert ALERT["schedule"]["quartz_cron_schedule"] == "0 0/10 * * * ?"
    assert ALERT["evaluation"]["notification"]["retrigger_seconds"] == 1
    preview = code_containing("%sql\n\nWITH pending_events")
    assert preview.removeprefix("%sql\n\n").strip() == "\n".join(ALERT["query_lines"]).strip()
