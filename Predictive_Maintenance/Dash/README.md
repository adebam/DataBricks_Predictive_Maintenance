# Predictive Maintenance Monitoring Dashboard — v2.5 (Step 5 SQL Warehouse + Manual Refresh)

A Plotly Dash monitoring application for the Databricks AI4I 2020 predictive-maintenance project.

## Dashboard sections

### 1. Overview
- KPI families: Prediction Activity, Feature Health and Alert Management.
- Connected blue median trend and lightly shaded P10–P90 range on the Bronze ingestion-time axis, with colored markers identifying the original CSV filenames.
- Prediction volume over time.
- Predicted failure rate, median probability and P95 probability over time.
- Current PSI status by feature.
- Explicit note that behavior metrics are not ground-truth model accuracy.

### 2. Predictions
- Failure-probability histogram with the stored threshold.
- Top 15 highest-risk machines.
- Searchable/filterable prediction register.

### 3. Drift Monitoring
- Stable, moderate and significant feature counts.
- PSI by feature with 0.10 and 0.25 reference lines.
- Historical PSI trends using the rolling 1,000-record drift-snapshot history, not the cumulative/all-stream drift table.
- Box plot and overlaid **smooth, lightly shaded KDE curves** comparing all 8,000 historical reference records with the same latest 1,000 streaming Gold records used in Notebook 51. Both curves use a common bandwidth and X-axis for fair comparison.
- Drift statistics table including KS statistics.

### 4. Alert Management
- New-event, open/unresolved, acknowledged and resolved summaries. Acknowledgment is not implemented in Notebook 51, so its live count remains zero unless future lifecycle support is added.
- Selectable active alert inbox.
- Selected-alert detail panel.
- Alert event history and notification status.
- Read-only until backend lifecycle transitions are implemented.

## Important interpretation rules

### Feature drift, not machine drift
PSI and KS compare feature distributions. The dashboard therefore reports the number of **features** with drift, not machines with drift.

### PSI categories
The dashboard currently uses these display categories:
- Stable: PSI < 0.10
- Moderate drift: 0.10 <= PSI < 0.25
- Significant drift: PSI >= 0.25

These are common interpretation bands. They must remain aligned with the thresholds in the Databricks drift-calculation notebook. The UI derives its displayed category from PSI rather than trusting a possibly different label string.

### Model behavior is not model performance
The app tracks prediction volume, predicted failure rate, median failure probability and P95 probability. These do not require actual failure labels. They are behavior/monitoring metrics, not precision, recall, F1 or F2.

True model-performance metrics require delayed ground-truth outcomes from inspections, maintenance work orders or confirmed failure events. Do not calculate live precision/recall without those labels.

### Time axis and CSV batch identity (Step 3)
The Gold feature table in Notebook 50 has `_gold_processed_at`, but **not**
`_ingest_timestamp` or an original CSV filename. The app now assembles a feature
trend dataset by UDI using these Unity Catalog tables:

- **Gold** (`gold_data.streaming`): numeric engineered and original features.
- **Bronze** (`bronze_data_not_quality_checked.streaming`): `_ingest_timestamp` from Notebook 30.
- **Monitoring** (`gold_data.prediction_monitoring`): `batch` containing the CSV filename created by Notebook 50.

The X-axis is ingestion **time** (UTC, grouped by hour), not filenames or UDI.
The **connected blue line** shows medians for successive batch/hour groups; the
**light blue shaded band** shows the P10–P90 range. **Colored dots** identify
CSV filenames in the legend and in hover text. Summaries are deliberate:
many machines in one CSV file can have the *same timestamp*, so connecting
individual machine readings would create misleading vertical zigzags. `Other / Pre-CSV Data` groups non-CSV records. If Bronze
metadata is unavailable, the chart displays a warning instead of describing a
Gold processing time as an ingestion time.

Important: Notebook 30's `_ingest_timestamp` uses Delta landing source-file
modification time, *not* a device/sensor event timestamp. The chart therefore
shows **ingestion behavior**, not the true physical sequence of sensor readings.
When a trustworthy sensor timestamp becomes available, event-time trends should
be built separately.

### Chart sizing and navigation (Steps 1–2)
All Plotly figures use the same 430-pixel height and responsive width. Legends
are placed beneath the plotting area, dates use short tick labels, and the
horizontal PSI feature plot reserves extra left margin for long feature names.
All four tabs share the same navigation and remain compatible with the existing
feature dropdown and alert-detail callbacks. Tab-level verification on your
running Dash server is still recommended after installation.


### Box plot baseline
The reference population shown in the Drift Monitoring page should be the same reference population used by the PSI calculation. Do not automatically substitute the validation dataset: validation was used for model evaluation, not necessarily drift baseline construction.

## Run locally in demo mode

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://127.0.0.1:8050`.

The app binds to `0.0.0.0:8050`, allowing access from another device on the same network if the host firewall permits it. Keep the terminal process running.

## Step 5: connect to Databricks SQL Warehouse

The app **does not use real data until you configure credentials**. It does not
need access to an interactive cluster or the Lakeflow Jobs compute. It uses a
SQL Warehouse, which reads tables that your separate pipeline writes.

1. In Databricks, open **SQL Warehouses** in the left navigation. Select an
   existing running warehouse (or create one if you have permission). Under
   **Connection details**, copy its **Server hostname** and **HTTP path**.
2. Copy `.env.example` to `.env` in this app folder. Enter the hostname and
   HTTP path, and change `DEMO_MODE` from `true` to `false`.
3. For initial **local** testing, create a personal access token under your
   Databricks user settings (if your workspace permits tokens), and put it in
   `DATABRICKS_TOKEN` in `.env`. Do **not** share the token in chats, screenshots,
   GitHub, or client-side JavaScript. Ensure the identity can `USE CATALOG`,
   `USE SCHEMA`, and `SELECT` on the relevant Unity Catalog tables, and can use
   the warehouse.
4. Run `python test_connection.py`. This executes read-only `SELECT 1` and
   `SELECT * ... LIMIT 1` queries for the nine required source tables. It prints
   statuses, not your token. Resolve any missing-table or permission errors.
5. Start the application using `python app.py`. On the **first visit**, it loads
   a snapshot of the Databricks results; it will reuse that snapshot until
   someone clicks **Refresh Data**. Changing tabs, changing feature dropdowns,
   and revisiting the app do not issue additional warehouse queries.

Example `.env` settings for local PAT testing:

```dotenv
DEMO_MODE=false
DATABRICKS_SERVER_HOSTNAME=your-workspace-host.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your-warehouse-id
DATABRICKS_TOKEN=your-private-token
DATABRICKS_CLIENT_ID=
DATABRICKS_CLIENT_SECRET=
```

For **AWS EC2 deployment**, prefer a dedicated Databricks service principal and
OAuth machine-to-machine authentication. The connector supports this when you
set `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET` instead of the PAT.
The service principal needs SQL Warehouse `CAN USE` and read-only Unity Catalog
permissions. Put secrets in server environment/secret management, not Git.

```dotenv
DEMO_MODE=false
DATABRICKS_SERVER_HOSTNAME=your-workspace-host.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your-warehouse-id
DATABRICKS_TOKEN=
DATABRICKS_CLIENT_ID=service-principal-application-id
DATABRICKS_CLIENT_SECRET=private-oauth-secret
```

The **Refresh Data** button is read-only: it executes the dashboard's SELECT
queries but cannot trigger ingestion, inference, monitoring Jobs, or modify a
table. If any source fails during an update, the app keeps the previous fully
successful snapshot and shows a warning. Initial partial loads show diagnostic
banners where data is unavailable. A timestamp in the footer identifies the
last successful or partial load. All Gunicorn workers on one EC2 machine share
the snapshot through a local SQLite file in `.dash_cache/` (or `DASH_CACHE_DIR`).
This directory must be writable by the app service account and not be publicly
served, and the credentials must remain server-side. To limit public refresh
abuse and warehouse costs, add access controls / Nginx rate-limiting before
opening an EC2 deployment to the internet.

**Costs:** the initial data load and each manual refresh can start the
warehouse. Disabling automatic refresh does not make SQL queries free.

## Default data sources

| Purpose | Default table |
|---|---|
| Predictions | `predictivemaintenancecatalog.gold_data.test_failure_predictions` |
| Drift reference raw samples (8,000) | `predictivemaintenancecatalog.gold_data.all_features` |
| Drift results | `predictivemaintenancecatalog.gold_data.prediction_monitoring_drift` |
| Rolling drift | `predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_rolling` |
| Alert records | `predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alerts` |
| Alert state | `predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alert_state` |
| Alert events | `predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_alert_events` |
| Current feature samples | `predictivemaintenancecatalog.gold_data.streaming` |
| Original CSV batch names | `predictivemaintenancecatalog.gold_data.prediction_monitoring` |
| Bronze ingestion timestamps | `predictivemaintenancecatalog.bronze_data_not_quality_checked.streaming` |

Override table names in `.env` if your actual catalog/schema differs. Confirm the full table names and schemas before setting `DEMO_MODE=false`.

The live feature query joins Gold with Bronze `_ingest_timestamp` and the
Notebook 50 monitoring table's `batch` column on `UDI`. The query collapses
repeated UDIs in its metadata joins so a duplicate Bronze row cannot inflate
feature counts. Ensure Notebook 50 has populated the batch column before using
live mode. These joins are read-only; no Databricks notebook or table is modified
by the Dash app.

The app fetches up to 5,000 Gold observations and up to 10,000 raw reference
observations (the source currently has about 8,000). The distribution plots
compare the full baseline with the most recent 1,000 Gold rows ordered by
`_gold_processed_at DESC, UDI DESC`, matching Notebook 51's current window.

## Run tests

After installing the requirements, from the application folder run:

```bash
python -m pytest -q
```

This validates four-tab rendering, CSV/time grouping, chart heights, the
missing-timestamp empty state, and the manual-refresh server snapshot. Full
browser interaction tests and live Databricks integration verification still
require running the app locally with your own configured credentials.


## Pipeline status

The Overview tab now displays the most recent **completed** Lakeflow run for each monitored Job ID from `system.lakeflow.job_run_timeline`, joined to the latest job metadata in `system.lakeflow.jobs` for names and paused flags. Configure `MONITORED_JOB_IDS` in `.env` to choose tracked jobs. The default IDs correspond to the four IDs surfaced in the November 6, 2026 SQL query; review their names in the dashboard and remove unrelated jobs.

The `Pipeline status` KPI shows **N/M succeeded** (last completed runs, not real-time health). The table includes job name, Job ID, completion time UTC and paused status. A separate Jobs API integration would be necessary to report up-to-the-second running/queued states. `system.lakeflow` reports can arrive with a lag. If job metadata isn't accessible, the code falls back to run history with IDs; a missing run history is displayed as unknown rather than 'healthy'.

The warehouse token must be able to `SELECT` from the Lakeflow system tables. No separate Jobs API token is required for this setup.

## Alert lifecycle

The Alert Management page is read-only. It displays current alert state and event history. It does not create, acknowledge, resolve or escalate alerts. Implement and verify backend state transitions before exposing action buttons.

## Run on EC2

```bash
gunicorn app:server --bind 127.0.0.1:8050 --workers 2 --timeout 120
```

Use EC2 secrets/environment configuration for credentials. Configure a reverse proxy, TLS and restrictive security-group rules before exposing the app publicly.

### Reviewed chart styles (v2.2)
- **Original** features are listed before **Engineered** features in both numeric dropdowns. The group appears in each option label, without using additional chart colors. Machine Type is categorical and is therefore excluded from the numerical feature selectors.
- **Feature trend** restores the earlier connected median line and transparent percentile band, while retaining the agreed ingestion-time X-axis and CSV batch identity.
- **Distribution shape** uses smooth Gaussian KDE curves with blue/reference and red/current outlines and 15%-opacity fills. Both populations share one bandwidth and X-grid; smoothing only changes display, not PSI/KS drift metrics.
- Predictions, PSI, and alert calculations and their charts were not altered in this patch.

## Step 4 source verification / limitations

- **Predictions:** latest up to 5,000 rows from `gold_data.test_failure_predictions`.
  Predicted failure rate and scores are model behavior, not precision/recall.
- **PSI / current drift:** last *complete* monitoring run from
  `gold_data.prediction_monitoring_drift_rolling`; report PSI categories of all
  11 features, including categorical `Type`.
- **PSI history:** reads the same rolling-snapshot table across runs; never
  mix cumulative full-Gold PSI with rolling PSI on one line.
- **KDE / box:** full raw baseline (`gold_data.all_features`, 8,000 rows),
  compared with the latest 1,000 rows from `gold_data.streaming` sorted by
  `_gold_processed_at DESC, UDI DESC` (the exact Notebook 51 rule).
  Machine Type stays in PSI, but is excluded from numeric KDE and box plots.
- **Alert inbox:** state table stores `current_severity`, `last_psi`,
  `last_ks_pvalue`, `last_detected_at`, `last_transition`, etc. They are mapped
  to appropriate UI names. `OPEN`, `RECOVERY_PENDING` and any future
  `ACKNOWLEDGED` status count as unresolved. `NO_ALERT` and `RESOLVED` do not.
- **Events / notifications:** notifications are event-history fields, not
  state fields. The dashboard is read-only. `NEW_ALERT` counts are derived from
  event rows; counts are scoped to the latest queried 3,000 records.
- **Live validation still pending:** all code checks use demo data. Confirm
  runtime schemas and counts against the Databricks SQL Warehouse in Step 6.

## Step 5 verification (manual-refresh design)

- Initial page view: query the SQL Warehouse once and persist a snapshot.
- All four tabs and feature dropdown changes: use the snapshot; **no SQL**.
- Refresh Data: clear query-result cache, query new values and update snapshot.
- Failed refresh: display a warning without discarding the last successful data.
- Deployment: Nginx routes HTTPS requests to Gunicorn on localhost; Dash
  serves the user interface and handles callbacks (no FastAPI needed).
- Databricks live access is **not yet verified**; run `python test_connection.py`
  using your environment, then validate source counts for Step 6.


## v2.6 chart review revisions

See [START_HERE_STEP6_REVISIONS.md](START_HERE_STEP6_REVISIONS.md) for the log/linear volume selector, prediction-time-range slider, and dynamic significant-drift history. These controls use the current cached snapshot and do not run additional SQL.
