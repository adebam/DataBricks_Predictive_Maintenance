# Step 5: Connect Dash to Databricks SQL Warehouse

This build keeps all approved v2.4 visualizations (including smooth KDE curves).
The only UI change is **Refresh Data** at the top right; the 60-second auto-refresh
has been removed.

## 1. Get your warehouse connection details

In your Databricks workspace, open **SQL Warehouses**, select the warehouse you
want to use, and open its **Connection details** tab. You need the **Server
hostname** (without `https://`) and **HTTP path** (usually starts with
`/sql/1.0/warehouses/`). Do not use the Lakeflow Jobs cluster's HTTP path.

For local setup, make a personal access token in your Databricks user settings
if your workspace allows tokens. The token is a password; keep it on your own
computer, not in screenshots or chats. Ensure the identity can use the SQL
Warehouse and read the project's Unity Catalog tables.

## 2. Configure locally

Open a terminal in the folder containing `app.py`:

```bash
source /path/to/pm_dash/bin/activate    # only if your existing environment is not active
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with a text editor. Change `DEMO_MODE=true` to `DEMO_MODE=false` and
fill in:

```dotenv
DEMO_MODE=false
DATABRICKS_SERVER_HOSTNAME=your-workspace-host.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your-id
DATABRICKS_TOKEN=your-private-token
```

Don't paste your actual token into ChatGPT or GitHub. If using OAuth M2M on EC2,
leave `DATABRICKS_TOKEN` blank and configure `DATABRICKS_CLIENT_ID` and
`DATABRICKS_CLIENT_SECRET` in the EC2 service's secret environment instead.

## 3. Test the connection (before opening the dashboard)

```bash
python test_connection.py
```

A successful output begins with `SQL Warehouse: CONNECTED (SELECT 1 passed)`
and confirms table access. Failures may mean incorrect connection details,
permissions, missing tables, or a stopped warehouse.

## 4. Run the dashboard

```bash
python app.py
```

Open `http://localhost:8050`. The first page load fetches live data. The footer
shows the last load time. Changing tabs and feature selections does not query
the warehouse again. Click **Refresh Data** to fetch updates.

If port 8050 is taken, find the existing process with `lsof -i :8050` and
stop your *previous* dashboard (or press Ctrl+C in its terminal). Don't run two
versions on the same port.

## 5. Check results

Compare Dash's Predictions total, latest rolling PSI and alert counts to the
corresponding Databricks tables. This is Step 6; it cannot be verified without
a live warehouse connection.

## About hosting on EC2

Dash is the Python web application. In production Gunicorn serves Dash/Flask
and Nginx forwards HTTPS requests. FastAPI is unnecessary for this read-only
monitoring dashboard. Give the EC2 app a writable private cache folder, and
add rate limiting or authentication to protect the public Refresh Data action
from excessive SQL Warehouse usage.
