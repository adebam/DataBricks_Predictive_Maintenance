"""Test Databricks SQL Warehouse connectivity without exposing credentials.

Usage: python test_connection.py
Requires values in .env and DEMO_MODE=false (or equivalent environment vars).
All SQL statements are read-only.
"""

import sys
from config import settings
from data_access import query_df


def main():
    if settings.demo_mode:
        print("Set DEMO_MODE=false in .env to test the live SQL Warehouse connection.")
        return 1
    if not settings.has_databricks_credentials:
        print("Missing SQL Warehouse hostname, HTTP path, or authentication settings.")
        return 1

    try:
        result = query_df("SELECT 1 AS connection_ok")
        assert int(result.iloc[0, 0]) == 1
        print("SQL Warehouse: CONNECTED (SELECT 1 passed)")
    except Exception as exc:
        print(f"SQL Warehouse connection failed: {type(exc).__name__}")
        print("Check hostname, HTTP path, warehouse access, network and credentials.")
        return 1

    tables = {
        "Predictions": settings.predictions_table,
        "Reference features": settings.drift_reference_table,
        "Current Gold features": settings.current_features_table,
        "Bronze ingestion metadata": settings.bronze_table,
        "Monitoring / CSV batches": settings.monitoring_table,
        "Rolling drift": settings.drift_rolling_table,
        "Alert evaluations": settings.alerts_table,
        "Alert state": settings.alert_state_table,
        "Alert events": settings.alert_events_table,
    }
    failures = 0
    for label, name in tables.items():
        try:
            query_df(f"SELECT * FROM {name} LIMIT 1")
            print(f"  OK  {label}: {name}")
        except Exception as exc:
            failures += 1
            print(f"  FAIL  {label}: {name} ({type(exc).__name__})")
    if failures:
        print(f"Connectivity works, but {failures} table access check(s) failed.")
        return 2
    print("All nine source table access checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
