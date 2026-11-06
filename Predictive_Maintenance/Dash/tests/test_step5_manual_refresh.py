"""Step 5: no automatic re-queries after initial snapshot, even across workers."""

import ast
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import snapshot as s


def test_manual_refresh_does_not_query_on_navigation(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(s, "_CACHE_DB", tmp_path / "snapshots.sqlite3")
    monkeypatch.setattr(s, "_LOCK_FILE", tmp_path / ".lock")
    monkeypatch.setattr(s, "KEY", "test-demo-snapshot")
    calls = []
    source_values = [1, 2, 3]

    def loader():
        calls.append("query")
        return {"predictions": pd.DataFrame({"value": [source_values[0]]}), "errors": {}}

    monkeypatch.setattr(s, "load_dashboard_data", loader)
    monkeypatch.setattr(s, "clear_query_cache", lambda: None)
    first = s.get_snapshot()
    assert len(calls) == 1
    assert first["data"]["predictions"].iloc[0, 0] == 1
    source_values[0] = 2
    assert s.get_snapshot()["data"]["predictions"].iloc[0, 0] == 1
    assert len(calls) == 1

    new_snapshot, error = s.refresh_snapshot()
    assert error is None
    assert len(calls) == 2
    assert new_snapshot["data"]["predictions"].iloc[0, 0] == 2
    assert s.get_snapshot()["data"]["predictions"].iloc[0, 0] == 2
    assert len(calls) == 2


def test_failed_refresh_keeps_last_successful_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(s, "_CACHE_DB", tmp_path / "snapshots.sqlite3")
    monkeypatch.setattr(s, "_LOCK_FILE", tmp_path / ".lock")
    monkeypatch.setattr(s, "KEY", "test-failure-snapshot")
    monkeypatch.setattr(s, "clear_query_cache", lambda: None)
    monkeypatch.setattr(s, "load_dashboard_data", lambda: {"predictions": pd.DataFrame({"UDI": [1]}), "errors": {}})
    first = s.get_snapshot()
    monkeypatch.setattr(s, "load_dashboard_data", lambda: {"predictions": pd.DataFrame(), "errors": {"predictions": "denied"}})
    second, error = s.refresh_snapshot()
    assert "previous successful" in error
    assert second["data"]["predictions"].equals(first["data"]["predictions"])
    assert not second["partial"]


def test_no_interval_refresh_or_browser_dataset_store():
    source = (ROOT / "app.py").read_text()
    assert 'dcc.Interval(id="refresh-timer"' not in source
    assert 'id="refresh-button"' in source
    assert 'ctx.triggered_id == "refresh-button"' in source
    assert 'get_snapshot()["data"]' in source
    assert 'Output("last-refresh", "children")' in source


def test_sql_connector_supports_oauth_service_principal():
    source = (ROOT / "data_access.py").read_text()
    assert 'credentials_provider' in source
    assert 'oauth_service_principal' in source
    assert 'access_token' in source
