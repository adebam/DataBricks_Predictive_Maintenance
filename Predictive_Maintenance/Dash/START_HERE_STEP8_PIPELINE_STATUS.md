# v2.7: Lakeflow Pipeline Status (SQL system tables)

## What changed
- The Overview **Pipeline status** KPI shows the count of most recent **completed** Job runs that succeeded. It is not a live RUNNING/QUEUED health check.
- New **Lakeflow job execution history** panel shows the latest completion per monitored job (name, ID, completion timestamp in UTC, result, and paused status if Databricks exposes it).
- Data source: `system.lakeflow.job_run_timeline`, joined to the latest job metadata from `system.lakeflow.jobs` (both queried through the existing SQL Warehouse).
- If the jobs metadata table is inaccessible but the run timeline works, the display gracefully falls back to run IDs.
- The default `MONITORED_JOB_IDS` contains the four IDs from the November 6, 2026 SQL results. Confirm that the displayed job names are relevant; remove any unrelated jobs from `.env`.
- All existing chart calculations, the KDE chart, slider, manual refresh, and alert visuals are unchanged.

## First run
1. Extract the ZIP.
2. Copy the **private** `.env` from your previous working v2.6.1 folder to the new `predictive_maintenance_dash` folder. Do not upload it or add it to GitHub.
3. In `.env`, keep `DEMO_MODE=false` and add (or edit):

   ```dotenv
   MONITORED_JOB_IDS=1093257342514742,988061660710201,195467107464674,65480912120821
   PIPELINE_STATUS_TABLE=
   ```
4. Start with `python app.py` and navigate to **Overview**. The first visit loads a snapshot; clicking **Refresh Data** fetches updated SQL results. Tab switching does not trigger queries.
5. Verify displayed job names and latest completion times against the Databricks Jobs & Pipelines UI.

## SQL sanity check (optional)

```sql
WITH current_jobs AS (
    SELECT workspace_id, job_id, name, paused, delete_time,
           ROW_NUMBER() OVER (
               PARTITION BY workspace_id, job_id
               ORDER BY change_time DESC
           ) AS version_rank
    FROM system.lakeflow.jobs
)
SELECT job_id, name, paused, delete_time
FROM current_jobs
WHERE version_rank = 1
  AND job_id IN ('1093257342514742', '988061660710201',
                 '195467107464674', '65480912120821')
ORDER BY name;
```

**Reporting limitation:** Databricks system tables have ingestion delay and represent historical job executions. A `SUCCEEDED` result means the most recently recorded completed run succeeded; it does not establish that the schedule is enabled, the job is currently running, or newly arrived files have been processed. A Jobs API integration would be required for current RUNNING or QUEUED state.

**Testing:** Static Python compilation and 19 source-level tests passed. No local Databricks credentials or full browser environment were available during packaging, so live job-name rendering still needs verification in your workspace.
