"""Lakeflow monitoring via SQL system tables, without needing a browser."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _extract(file, functions, namespace):
    tree = ast.parse((ROOT / file).read_text())
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in functions]
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, str(ROOT / file), "exec"), namespace)
    return namespace


def test_pipeline_kpi_is_specific_about_completed_runs():
    fn = _extract("app.py", ["_pipeline_status"], {"pd": pd})["_pipeline_status"]
    frame = pd.DataFrame({"result_state": ["SUCCEEDED", "SUCCEEDED", "FAILED", "ERROR"]})
    assert fn(frame) == "2/4 succeeded"
    assert fn(pd.DataFrame()) == "No run history"
    assert fn(frame, "DEMO DATA") == "Demo mode"


def _settings():
    return SimpleNamespace(
        demo_mode=False,
        predictions_table="c.g.predictions",
        drift_rolling_table="c.g.rolling",
        drift_reference_table="c.g.reference",
        bronze_table="c.b.bronze",
        monitoring_table="c.g.monitoring",
        current_features_table="c.g.gold",
        alerts_table="c.g.alerts",
        alert_state_table="c.g.state",
        alert_events_table="c.g.events",
        pipeline_status_table="",
        monitored_job_ids=("1093257342514742", "988061660710201"),
    )


def test_job_query_has_scd2_names_and_run_deduping():
    sql_calls = []

    def query_df(sql):
        sql_calls.append(sql)
        if "FROM system.lakeflow.job_run_timeline" in sql:
            return pd.DataFrame({"job_id": ["1093257342514742"], "job_name": ["Test job"],
                                 "result_state": ["SUCCEEDED"]})
        return pd.DataFrame()

    fn = _extract("data.py", ["_read", "load_dashboard_data"], {
        "pd": pd, "settings": _settings(), "query_df": query_df,
        "build_demo_data": lambda: {},
    })["load_dashboard_data"]
    data = fn()
    job_sql = next(sql for sql in sql_calls if "system.lakeflow.job_run_timeline" in sql)
    assert "system.lakeflow.jobs" in job_sql
    assert "PARTITION BY workspace_id, job_id, run_id" in job_sql
    assert "ORDER BY period_end_time DESC" in job_sql
    assert "result_state IS NOT NULL" in job_sql
    assert "change_time DESC" in job_sql
    assert "1093257342514742" in job_sql
    assert data["pipeline"].iloc[0]["result_state"] == "SUCCEEDED"
    assert not data["errors"]


def test_job_names_fallback_still_returns_runs():
    sql_calls = []

    def query_df(sql):
        sql_calls.append(sql)
        if "system.lakeflow.jobs" in sql:
            raise PermissionError("jobs metadata denied")
        if "FROM system.lakeflow.job_run_timeline" in sql:
            return pd.DataFrame({"job_id": ["1093257342514742"],
                                 "job_name": ["Job 1093257342514742"],
                                 "result_state": ["SUCCEEDED"]})
        return pd.DataFrame()

    fn = _extract("data.py", ["_read", "load_dashboard_data"], {
        "pd": pd, "settings": _settings(), "query_df": query_df,
        "build_demo_data": lambda: {},
    })["load_dashboard_data"]
    data = fn()
    assert data["pipeline"].iloc[0]["result_state"] == "SUCCEEDED"
    assert "Lakeflow job status" not in data["errors"]
    assert len([s for s in sql_calls if "FROM system.lakeflow.job_run_timeline" in s]) == 2
