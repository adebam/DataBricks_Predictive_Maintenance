# Dashboard v2.6 — reviewed plot corrections

This update builds on v2.5, keeping the same SQL Warehouse authentication, manual Refresh Data button, KPI calculations, four tabs, and approved KDE curves.

## Changes

1. **Prediction volume over time:** Default log Y-axis; select **Linear** to compare absolute counts or see zero counts. X-axis stays chronological. Note that zero values are not rendered on logarithmic axes. The display selector recalculates the chart from the **existing dashboard snapshot**, without querying Databricks.
2. **Model behavior over time:** No changes to the percentage calculations (the 100% last two windows match verified SQL results). Hover over the red line to see the total number of predictions and flagged failures in each time bin. The plotted line connects observed time windows only; it does not imply there were predictions between observed windows.
3. **Failure probability distribution:** Added a two-ended **UTC time-range slider** and Reset to all. It filters **only this probability histogram**, based on `prediction_timestamp`, using the already loaded prediction rows. The top risk list, register, and KPIs retain all records in the loaded snapshot. The slider and all UI controls perform **no SQL query**; only initial load / Refresh Data does.
4. **Historical Drift:** Displays all features whose **latest rolling PSI >= 0.25**, not just the highest six. If none are significant, an informative empty chart appears. The data source remains `gold_data.prediction_monitoring_drift_rolling`.

## Run

1. Extract the ZIP to a new folder.
2. Reuse your **existing local `.env`** from v2.5 by copying it directly into the new `predictive_maintenance_dash` folder. The download deliberately contains **no `.env` or credentials**.
3. With `(pm_dash)` active: `python app.py`
4. Open `http://localhost:8050`. If port 8050 is already occupied by v2.5, stop that process first (`Ctrl+C` in its terminal, or identify its PID with `lsof -i :8050`).
5. Check the time slider, log/linear selector, Historical Drift legend, and the unchanged behavior values; clicking the selectors should not run Databricks SQL.

## Source reference (draft; final chart-to-table mapping after dashboard completion)

- Prediction volume, model behavior, probability distribution, risk ranking, register: `predictivemaintenancecatalog.gold_data.test_failure_predictions` (latest 5,000 records loaded, ordered by prediction timestamp).
- Historical Drift and current PSI: `predictivemaintenancecatalog.gold_data.prediction_monitoring_drift_rolling`.
- Reference-vs-current distributions: `predictivemaintenancecatalog.gold_data.all_features` against the latest 1,000 records from `predictivemaintenancecatalog.gold_data.streaming`.

The final source mapping will document every plot and KPI, its source tables, aggregation, time windows, notebook and refresh policy.
