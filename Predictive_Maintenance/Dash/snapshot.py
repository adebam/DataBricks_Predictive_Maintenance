"""One shared dashboard snapshot, loaded only on first view or manual Refresh.

Snapshots live in a local SQLite database shared by Gunicorn workers on one
EC2 machine. They contain query *results*, not Databricks credentials.
The cache directory must be writable by the app service account and must not
be exposed by the web server. SQLite stores trusted locally-created pickles:
never allow other users to write to this directory.
"""

from contextlib import contextmanager, closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import fcntl
import os
import pickle
import sqlite3

from config import settings
from data import load_dashboard_data
from data_access import clear_query_cache

_CACHE_DIR = Path(os.getenv("DASH_CACHE_DIR", str(Path(__file__).resolve().parent / ".dash_cache")))
_CACHE_DB = _CACHE_DIR / "snapshots.sqlite3"
_LOCK_FILE = _CACHE_DIR / ".refresh.lock"

# Changing source mode, table or warehouse invalidates older snapshots, without
# including token/client secret. Schema version protects changes to cache data.
_source_id = "|".join(str(value) for value in (
    "snapshot-v2-jobs", settings.demo_mode, settings.databricks_host,
    settings.databricks_http_path, settings.predictions_table,
    settings.drift_reference_table, settings.drift_rolling_table,
    settings.current_features_table, settings.bronze_table,
    settings.monitoring_table, settings.alerts_table,
    settings.alert_state_table, settings.alert_events_table,
    settings.pipeline_status_table, settings.monitored_job_ids,
))
KEY = "dashboard:" + sha256(_source_id.encode()).hexdigest()[:24]


def _connect():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(str(_CACHE_DB), timeout=90)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS snapshots ("
        "cache_key TEXT PRIMARY KEY, payload BLOB NOT NULL)"
    )
    return connection


def _get():
    with closing(_connect()) as connection:
        result = connection.execute(
            "SELECT payload FROM snapshots WHERE cache_key = ?", (KEY,)
        ).fetchone()
    return pickle.loads(result[0]) if result else None


def _set(snapshot):
    payload = pickle.dumps(snapshot, protocol=pickle.HIGHEST_PROTOCOL)
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO snapshots (cache_key, payload) VALUES (?, ?)",
            (KEY, payload),
        )
        connection.commit()


@contextmanager
def _exclusive_refresh():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(_LOCK_FILE, "a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _make_snapshot(data):
    return {
        "data": data,
        "loaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "partial": bool(data.get("errors")),
    }


def get_snapshot():
    """Read the existing snapshot; do not query on tab/feature changes."""
    current = _get()
    if current is not None:
        return current
    with _exclusive_refresh():
        current = _get()
        if current is None:
            current = _make_snapshot(load_dashboard_data())
            _set(current)
        return current


def refresh_snapshot():
    """Reload data and replace the snapshot only if no new source fails.

    Returns (snapshot, message). On partial initial loads, save partial data so
    the read-only UI can show diagnostic banners for missing tables/grants.
    """
    with _exclusive_refresh():
        previous = _get()
        clear_query_cache()
        try:
            fresh_data = load_dashboard_data()
        except Exception as exc:
            if previous is not None:
                return previous, f"Refresh failed; previous data preserved ({type(exc).__name__})."
            raise
        errors = fresh_data.get("errors", {})
        if errors and previous is not None and not previous["partial"]:
            return previous, (
                "Refresh incomplete; showing previous successful data. "
                f"{len(errors)} source(s) reported an error."
            )
        current = _make_snapshot(fresh_data)
        _set(current)
        if errors:
            return current, f"Partial load: {len(errors)} data source(s) reported an error."
        return current, None
