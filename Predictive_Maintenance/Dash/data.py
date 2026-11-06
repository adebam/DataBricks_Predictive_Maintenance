import pandas as pd

from config import settings
from data_access import query_df
from demo_data import build_demo_data


def _read(name: str, query: str, errors: dict) -> pd.DataFrame:
    try:
        return query_df(query)
    except Exception as exc:
        errors[name] = str(exc).splitlines()[0][:240]
        return pd.DataFrame()


def load_dashboard_data() -> dict:
    if settings.demo_mode:
        return build_demo_data()

    errors = {}
    predictions = _read(
        "predictions",
        f"SELECT * FROM {settings.predictions_table} ORDER BY prediction_timestamp DESC LIMIT 5000",
        errors,
    )
    drift_rolling = _read(
        "rolling drift",
        f"SELECT * FROM {settings.drift_rolling_table} ORDER BY calculated_at DESC LIMIT 3000",
        errors,
    )
    # Notebook 51 persists one row per feature per 1,000-record rolling window.
    # The trend must use these rolling snapshots; the cumulative drift table
    # describes a different population and is not comparable over time.
    drift_history = drift_rolling.copy()
    reference = _read(
        "drift reference",
        f"SELECT * FROM {settings.drift_reference_table} LIMIT 10000",
        errors,
    )
    # Gold deliberately contains engineered features, but its schema does not
    # retain CSV batch filenames or Bronze ingestion timestamps. Resolve those
    # by UDI without multiplying rows if the upstream table has repeats.
    # Use UDI ordering only for limiting returned records, not as chart time.
    current = _read(
        "current features with provenance",
        f"""
        WITH latest_bronze AS (
            SELECT UDI, MIN(_ingest_timestamp) AS _ingest_timestamp
            FROM {settings.bronze_table}
            WHERE UDI IS NOT NULL
            GROUP BY UDI
        ), csv_batches AS (
            SELECT UDI, MAX(batch) AS batch
            FROM {settings.monitoring_table}
            WHERE UDI IS NOT NULL
            GROUP BY UDI
        ), recent_gold AS (
            SELECT * FROM {settings.current_features_table}
            ORDER BY UDI DESC LIMIT 5000
        )
        SELECT g.*, b._ingest_timestamp, m.batch
        FROM recent_gold g
        LEFT JOIN latest_bronze b ON g.UDI = b.UDI
        LEFT JOIN csv_batches m ON g.UDI = m.UDI
        """,
        errors,
    )
    if current.empty and "current features with provenance" in errors:
        # Keep all other tabs usable if these optional provenance joins fail.
        # The feature-time figure will clearly report missing ingest metadata.
        current = _read(
            "current feature data (fallback)",
            f"SELECT * FROM {settings.current_features_table} ORDER BY UDI DESC LIMIT 5000",
            errors,
        )
    # Exactly mirror Notebook 51: latest 1,000 Gold records ordered by Gold
    # processing timestamp, breaking timestamp ties by UDI. Do not reuse the
    # 5,000-row ingestion-trend population for rolling drift comparisons.
    current_rolling = _read(
        "rolling current features",
        f"""SELECT * FROM {settings.current_features_table}
            ORDER BY _gold_processed_at DESC, UDI DESC LIMIT 1000""",
        errors,
    )
    alerts = _read(
        "alerts",
        f"SELECT * FROM {settings.alerts_table} LIMIT 2000",
        errors,
    )
    alert_state = _read(
        "alert state",
        f"SELECT * FROM {settings.alert_state_table} LIMIT 2000",
        errors,
    )
    alert_events = _read(
        "alert events",
        f"SELECT * FROM {settings.alert_events_table} ORDER BY event_timestamp DESC LIMIT 3000",
        errors,
    )

    pipeline = pd.DataFrame()
    if settings.pipeline_status_table:
        pipeline = _read(
            "pipeline status",
            f"SELECT * FROM {settings.pipeline_status_table} LIMIT 100",
            errors,
        )
    elif getattr(settings, "monitored_job_ids", ()):
        # The Jobs system table is SCD2: select the most recent metadata
        # record per job. The run timeline can show more than one row per
        # run_id (for retries / multiple results), so select the latest
        # completed result per run, then the latest completed run per job.
        # Job execution history may lag behind the Jobs UI; this is NOT a
        # real-time 'RUNNING' indicator.
        job_ids = ", ".join(f"'{job_id}'" for job_id in settings.monitored_job_ids)
        timeline = f"""
            WITH run_slices AS (
              SELECT
                workspace_id, job_id, run_id, run_name,
                period_start_time, period_end_time, result_state,
                ROW_NUMBER() OVER (
                  PARTITION BY workspace_id, job_id, run_id
                  ORDER BY period_end_time DESC
                ) AS slice_rank
              FROM system.lakeflow.job_run_timeline
              WHERE period_start_time >= CURRENT_TIMESTAMP() - INTERVAL 30 DAYS
                AND result_state IS NOT NULL
                AND job_id IN ({job_ids})
            ), completed_runs AS (
              SELECT * FROM run_slices WHERE slice_rank = 1
            ), latest_runs AS (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY workspace_id, job_id
                ORDER BY period_end_time DESC, run_id DESC
              ) AS latest_rank
              FROM completed_runs
            )
        """
        named_sql = timeline + """
            , latest_jobs AS (
              SELECT workspace_id, job_id, name, paused, delete_time,
                  ROW_NUMBER() OVER (
                    PARTITION BY workspace_id, job_id
                    ORDER BY change_time DESC
                  ) AS version_rank
              FROM system.lakeflow.jobs
            )
            SELECT
                COALESCE(j.name, NULLIF(r.run_name, ''), CONCAT('Job ', r.job_id)) AS job_name,
                r.job_id, r.run_id, r.result_state,
                r.period_start_time, r.period_end_time,
                j.paused
            FROM latest_runs r
            LEFT JOIN latest_jobs j
              ON r.workspace_id = j.workspace_id
             AND r.job_id = j.job_id
             AND j.version_rank = 1
             AND j.delete_time IS NULL
            WHERE r.latest_rank = 1
            ORDER BY r.period_end_time DESC
        """
        pipeline = _read("Lakeflow job status", named_sql, errors)
        if pipeline.empty and "Lakeflow job status" in errors:
            # Some workspaces allow the run timeline but not the SCD2 jobs
            # metadata. Show IDs instead of mislabeling a job.
            fallback_sql = timeline + """
                SELECT
                    COALESCE(NULLIF(run_name, ''), CONCAT('Job ', job_id)) AS job_name,
                    job_id, run_id, result_state,
                    period_start_time, period_end_time,
                    CAST(NULL AS BOOLEAN) AS paused
                FROM latest_runs WHERE latest_rank = 1
                ORDER BY period_end_time DESC
            """
            fallback = _read("Lakeflow run history fallback", fallback_sql, errors)
            if not fallback.empty:
                pipeline = fallback
                # Metadata access is optional; the fallback still reports
                # the status correctly and must not block a manual refresh.
                errors.pop("Lakeflow job status", None)
                errors.pop("Lakeflow run history fallback", None)

    return {
        "predictions": predictions,
        "drift_rolling": drift_rolling,
        "drift_history": drift_history,
        "reference": reference,
        "current": current,
        "current_rolling": current_rolling,
        "alerts": alerts,
        "alert_state": alert_state,
        "alert_events": alert_events,
        "pipeline": pipeline,
        "errors": errors,
        "source_mode": "LIVE DATABRICKS",
    }
