# Dashboard v2.6.1 — prediction time-slider readability fix

This small revision changes **only the presentation of the Prediction tab's Failure probability distribution time slider**. All four tabs, SQL Warehouse/manual-refresh behavior, existing queries, data filters, prediction calculations, and the histogram itself remain unchanged.

## What was fixed

- Removed raw epoch-hour tooltips (large numbers like `498303`) that covered the slider.
- Removed overlapping timestamp tick labels under the slider.
- Added readable **FROM** and **TO** date/time boxes above the slider, updated as you drag.
- Added clear **Earliest available** and **Latest available** captions underneath.
- Improved slider handle contrast, spacing, and small-screen wrapping.
- Kept the selected prediction count and **Reset to all** button.

The slider filters the histogram **only**; it does not filter prediction KPI cards, the 15 highest-risk machines, or the prediction register. The slider operates on cached data and does not issue new SQL Warehouse queries.

## Run

1. Extract this ZIP and enter its `predictive_maintenance_dash` directory.
2. Reuse your `.env` from the previous version if you want **LIVE MODE**; without that configuration, it will show **DEMO MODE** as expected.
3. Activate your `(pm_dash)` virtual environment.
4. Run `python app.py` and open `http://localhost:8050`. Stop any previous Dash process using 8050 first.
5. Hard-refresh the page (`Ctrl+Shift+R`) if your browser is still showing the previous CSS.

## Verification performed

Python syntax and source-level regression checks passed, including slider time-window filtering and label updates. Full browser rendering was not tested in the packaging environment (Dash is not installed there).
