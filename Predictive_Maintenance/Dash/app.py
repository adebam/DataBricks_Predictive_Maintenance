import os
import json
from pathlib import PurePosixPath

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, dash_table, ctx

from config import settings
from snapshot import get_snapshot, refresh_snapshot

APP_BG = "#0b1220"
PANEL_BG = "#111c2e"
TEXT = "#e8eef7"
MUTED = "#91a1b7"
BLUE = "#4ea1ff"
GREEN = "#42c59a"
AMBER = "#ffbd69"
RED = "#f16d6d"


# All dashboard figures use one responsive width and the same fixed height.
# Additional left space for feature names is configured on the PSI chart only.
CHART_HEIGHT = 430

# Feature provenance is shown in the selectors, not as additional chart colors.
# Machine Type is an original categorical feature, so it is not offered in
# numeric-only charts.
ORIGINAL_FEATURES = (
    "Air_temperature_K", "Process_temperature_K", "Rotational_speed_rpm",
    "Torque_Nm", "Tool_wear_min", "Type",
)
ENGINEERED_FEATURES = (
    "Temperature_difference_K", "Mechanical_power_W", "Torque_wear",
    "Speed_wear", "Power_wear",
)
FEATURE_DISPLAY_NAMES = {
    "Air_temperature_K": "Air temperature (K)",
    "Process_temperature_K": "Process temperature (K)",
    "Rotational_speed_rpm": "Rotational speed (rpm)",
    "Torque_Nm": "Torque (Nm)",
    "Tool_wear_min": "Tool wear (min)",
    "Type": "Machine type",
    "Temperature_difference_K": "Temperature difference (K)",
    "Mechanical_power_W": "Mechanical power (W)",
    "Torque_wear": "Torque × wear",
    "Speed_wear": "Speed × wear",
    "Power_wear": "Power × wear",
}


def _grouped_feature_options(features):
    """Original features first, then engineered; unknown numeric features last."""
    available = set(features)
    result = []
    for group, group_features in (
        ("Original", ORIGINAL_FEATURES),
        ("Engineered", ENGINEERED_FEATURES),
    ):
        for feature in group_features:
            if feature in available:
                result.append({
                    "label": f"{group} · {FEATURE_DISPLAY_NAMES.get(feature, feature)}",
                    "value": feature,
                })
    known = set(ORIGINAL_FEATURES) | set(ENGINEERED_FEATURES)
    for feature in sorted(available - known):
        result.append({"label": f"Other · {feature.replace('_', ' ')}", "value": feature})
    return result


def _figure_layout():
    return {
        "height": CHART_HEIGHT,
        "autosize": True,
        "paper_bgcolor": PANEL_BG,
        "plot_bgcolor": PANEL_BG,
        "font": {"color": TEXT, "family": "Inter, Arial, sans-serif", "size": 11},
        "margin": {"l": 75, "r": 30, "t": 78, "b": 112},
        "title_x": 0.015,
        "title_xanchor": "left",
        "title_font": {"size": 14},
        # Put legends beneath the plotting area rather than across chart titles.
        "legend": {
            "orientation": "h", "yanchor": "top", "y": -0.28,
            "xanchor": "left", "x": 0, "font": {"size": 10},
        },
        "xaxis": {"gridcolor": "#26364d", "zerolinecolor": "#26364d", "automargin": True},
        "yaxis": {"gridcolor": "#26364d", "zerolinecolor": "#26364d", "automargin": True},
    }


def _empty_figure(title, message="No data available from this source yet."):
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font={"color": MUTED, "size": 13},
    )
    fig.update_layout(title=title, **_figure_layout())
    return fig


def _records(frame):
    if frame is None or frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso", date_unit="ms"))


def _table(frame, columns=None, page_size=12, table_id=None, row_selectable=None):
    if frame is None or frame.empty:
        return html.Div("No records available from this source.", className="empty-state")
    shown = frame.copy()
    if columns:
        shown = shown[[column for column in columns if column in shown.columns]]
    shown = shown.head(2000)
    kwargs = {}
    if row_selectable:
        kwargs["row_selectable"] = row_selectable
        kwargs["selected_rows"] = []
    return dash_table.DataTable(
        **({"id": table_id} if table_id is not None else {}),
        data=_records(shown),
        columns=[{"name": c.replace("_", " ").title(), "id": c} for c in shown.columns],
        page_action="native",
        page_size=page_size,
        sort_action="native",
        filter_action="native",
        fixed_rows={"headers": True},
        style_table={"overflowX": "auto", "minWidth": "100%"},
        style_header={
            "backgroundColor": "#18263b", "color": TEXT, "fontWeight": "600",
            "border": "1px solid #26364d", "whiteSpace": "normal", "height": "auto",
        },
        style_cell={
            "backgroundColor": PANEL_BG, "color": TEXT, "border": "1px solid #26364d",
            "padding": "10px", "fontFamily": "Inter, Arial, sans-serif", "fontSize": "12px",
            "textAlign": "left", "minWidth": "100px", "maxWidth": "270px",
            "overflow": "hidden", "textOverflow": "ellipsis",
        },
        style_data_conditional=[
            {"if": {"filter_query": '{alert_status} = "OPEN"', "column_id": "alert_status"},
             "color": AMBER, "fontWeight": "bold"},
            {"if": {"filter_query": '{alert_status} = "ACKNOWLEDGED"', "column_id": "alert_status"},
             "color": BLUE, "fontWeight": "bold"},
            {"if": {"filter_query": '{alert_status} = "RESOLVED"', "column_id": "alert_status"},
             "color": GREEN, "fontWeight": "bold"},
            {"if": {"filter_query": '{psi_status} = "SIGNIFICANT_DRIFT"', "column_id": "psi_status"},
             "color": RED, "fontWeight": "bold"},
            {"if": {"filter_query": '{notification_status} = "PENDING"', "column_id": "notification_status"},
             "color": AMBER, "fontWeight": "bold"},
            {"if": {"filter_query": '{result_state} = "SUCCEEDED"', "column_id": "result_state"},
             "color": GREEN, "fontWeight": "bold"},
            {"if": {"filter_query": '{result_state} = "FAILED"', "column_id": "result_state"},
             "color": RED, "fontWeight": "bold"},
            {"if": {"filter_query": '{result_state} = "ERROR"', "column_id": "result_state"},
             "color": RED, "fontWeight": "bold"},
            {"if": {"filter_query": '{paused} = "Yes"', "column_id": "paused"},
             "color": AMBER, "fontWeight": "bold"},
        ],
        **kwargs,
    )


def _kpi(label, value, helper, tone="blue"):
    return html.Div(
        [
            html.Div(label, className="kpi-label"),
            html.Div(str(value), className=f"kpi-value {tone}"),
            html.Div(helper, className="kpi-helper"),
        ],
        className="kpi-card",
    )


def _family(title, subtitle, cards, tone="blue"):
    return html.Div(
        [
            html.Div(
                [
                    html.Span(className=f"family-dot {tone}"),
                    html.Div(
                        [
                            html.Div(title, className="family-title"),
                            html.Div(subtitle, className="family-subtitle"),
                        ]
                    ),
                ],
                className="family-heading",
            ),
            html.Div(cards, className="family-cards"),
        ],
        className=f"kpi-family {tone}",
    )


def _panel(title, body, subtitle=None, class_name="panel"):
    children = [html.Div(title, className="panel-title")]
    if subtitle:
        children.append(html.Div(subtitle, className="panel-subtitle"))
    children.append(body)
    return html.Div(children, className=class_name)


def _error_banner(errors):
    if not errors:
        return html.Div()
    detail = "; ".join(f"{name}: {message}" for name, message in errors.items())
    return html.Div(
        [html.Strong("Some data sources could not be loaded. "), html.Span(detail)],
        className="warning-banner",
    )


def _numeric_features(frame, exclude=None):
    if frame is None or frame.empty:
        return []
    excluded = {
        "UDI", "id", "machine_id", "_batch_order",
        "Machine_failure", "TWF", "HDF", "PWF", "OSF", "RNF",
    }
    if exclude:
        excluded.update(exclude)
    return [
        name for name in frame.columns
        if name not in excluded and pd.api.types.is_numeric_dtype(frame[name])
    ]


def _feature_options(data):
    current = data.get("current_rolling", data.get("current", pd.DataFrame()))
    reference = data.get("reference", pd.DataFrame())
    common = set(_numeric_features(current)).intersection(_numeric_features(reference))
    return sorted(common)


def _latest_per_feature(frame):
    if frame is None or frame.empty or "feature" not in frame.columns:
        return pd.DataFrame()
    result = frame.copy()
    if "calculated_at" in result.columns:
        result["calculated_at"] = pd.to_datetime(result["calculated_at"], errors="coerce")
        result = result.sort_values("calculated_at")
    if "monitoring_run_id" in result.columns:
        # Select one complete latest rolling run, never mix feature statuses
        # from different 1,000-row windows when a run has missing features.
        run_ids = result["monitoring_run_id"].dropna()
        if not run_ids.empty:
            result = result[result["monitoring_run_id"] == run_ids.iloc[-1]]
    return result.drop_duplicates("feature", keep="last")


def _psi_classification(value):
    if pd.isna(value):
        return "UNKNOWN"
    if value >= 0.25:
        return "SIGNIFICANT_DRIFT"
    if value >= 0.10:
        return "MODERATE_DRIFT"
    return "STABLE"


def _drift_with_classes(frame):
    result = _latest_per_feature(frame)
    if result.empty or "psi" not in result.columns:
        return result
    result["psi"] = pd.to_numeric(result["psi"], errors="coerce")
    # Dashboard categories are derived consistently from PSI thresholds:
    # <0.10 stable, 0.10–<0.25 moderate, >=0.25 significant.
    result["dashboard_drift_status"] = result["psi"].apply(_psi_classification)
    return result


def _normalize_alert_state(frame):
    """Expose Notebook 51 state columns under UI-friendly names.

    Notebook 51's state table has last_psi/current_severity etc., whereas
    notifications live in the event history table, not the current state.
    """
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    for raw, display in (
        ("current_severity", "severity"),
        ("last_psi", "psi"),
        ("last_ks_pvalue", "ks_pvalue"),
    ):
        if display not in result.columns and raw in result.columns:
            result[display] = result[raw]
    if "last_detected_at" not in result.columns and "event_timestamp" in result.columns:
        result["last_detected_at"] = result["event_timestamp"]
    return result


def _open_alerts(data):
    state = _normalize_alert_state(data.get("alert_state", pd.DataFrame()))
    events = data.get("alert_events", pd.DataFrame())
    if not state.empty:
        result = state
    else:
        result = events.copy() if events is not None else pd.DataFrame()
        if result.empty:
            result = data.get("alerts", pd.DataFrame()).copy()
        if not result.empty and "feature" in result.columns and "event_timestamp" in result.columns:
            result["event_timestamp"] = pd.to_datetime(result["event_timestamp"], errors="coerce")
            result = result.sort_values("event_timestamp").drop_duplicates("feature", keep="last")
        result = _normalize_alert_state(result)
    if result.empty:
        return result
    status_col = next((c for c in ["alert_status", "status", "state"] if c in result.columns), None)
    if status_col:
        # Recovery pending is unresolved. NO_ALERT is not an active alert.
        active = {"OPEN", "RECOVERY_PENDING", "ACKNOWLEDGED", "NEW_ALERT"}
        result = result[result[status_col].astype(str).str.upper().isin(active)]
    return result


def _feature_batch_trend(current, feature):
    """Connected median trend and P10–P90 shaded band on the ingestion time axis.

    A whole CSV often arrives with one timestamp. Plotting individual records
    as a time-series line would create hundreds of vertical jumps at the same
    instant; one summary per (CSV filename, ingestion hour) preserves meaning.
    """
    title = "Feature behavior by ingestion time"
    if current is None or current.empty or not feature or feature not in current.columns:
        return _empty_figure(title)

    time_col = next(
        (c for c in ["_ingest_timestamp", "ingestion_timestamp", "ingest_timestamp"]
         if c in current.columns), None,
    )
    if not time_col:
        return _empty_figure(
            title,
            "Ingestion timestamps are unavailable. Join Bronze _ingest_timestamp by UDI to Gold features.",
        )

    frame = current.copy()
    frame[feature] = pd.to_numeric(frame[feature], errors="coerce")
    frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce", utc=True)
    frame = frame.dropna(subset=[feature, time_col])
    if frame.empty:
        return _empty_figure(title, "No numeric feature observations with valid ingestion timestamps.")

    # Notebook 50 writes the CSV filename to 'batch'. A Bronze Delta source
    # path is NOT necessarily the original CSV, so label it as pre-CSV instead.
    batch_col = next(
        (c for c in ["batch", "csv_filename", "_csv_filename", "_source_file", "source_file"]
         if c in frame.columns), None,
    )
    if batch_col:
        frame["batch_label"] = frame[batch_col].fillna("").astype(str).map(
            lambda value: (
                PurePosixPath(value.replace("\\", "/")).name
                if value.lower().endswith(".csv") else "Other / Pre-CSV Data"
            )
        )
    else:
        frame["batch_label"] = "Other / Pre-CSV Data"

    frame["ingestion_hour"] = frame[time_col].dt.floor("h")
    grouped = (
        frame.groupby(["batch_label", "ingestion_hour"], dropna=False)[feature]
        .agg(
            median="median",
            p10=lambda values: values.quantile(0.10),
            p90=lambda values: values.quantile(0.90),
            records="count",
        )
        .reset_index()
        .sort_values(["ingestion_hour", "batch_label"])
    )

    fig = go.Figure()
    timestamps = grouped["ingestion_hour"]
    # This is the same original connected median + shaded percentile-range
    # design. CSV batches are identifiable without creating one-point lines.
    fig.add_trace(go.Scatter(
        x=timestamps, y=grouped["p90"], mode="lines",
        line={"color": "rgba(78,161,255,0)", "width": 0},
        hoverinfo="skip", showlegend=False,
        name="P90 boundary",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=grouped["p10"], mode="lines",
        line={"color": "rgba(78,161,255,0)", "width": 0},
        fill="tonexty", fillcolor="rgba(78,161,255,0.16)",
        hoverinfo="skip", name="P10–P90 range",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=grouped["median"], mode="lines",
        line={"color": BLUE, "width": 2.8},
        name="Median trend",
        customdata=grouped[["batch_label", "records", "p10", "p90"]].to_numpy(),
        hovertemplate=(
            "CSV batch: %{customdata[0]}"
            "<br>Ingestion hour: %{x|%Y-%m-%d %H:%M} UTC"
            "<br>Median: %{y:.3f}<br>Records: %{customdata[1]}"
            "<br>P10: %{customdata[2]:.3f}<br>P90: %{customdata[3]:.3f}"
            "<extra></extra>"
        ),
    ))
    palette = px.colors.qualitative.Safe
    batches = grouped.groupby("batch_label")["ingestion_hour"].min().sort_values().index
    for i, batch in enumerate(batches):
        part = grouped[grouped["batch_label"] == batch]
        color = MUTED if batch == "Other / Pre-CSV Data" else palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=part["ingestion_hour"], y=part["median"], mode="markers",
            name=batch, marker={"size": 9, "color": color, "line": {"color": PANEL_BG, "width": 1}},
            customdata=part[["records", "p10", "p90"]].to_numpy(),
            hovertemplate=(
                "CSV batch: " + batch + "<br>Ingestion hour: %{x|%Y-%m-%d %H:%M} UTC"
                "<br>Median: %{y:.3f}<br>Records: %{customdata[0]}"
                "<br>P10: %{customdata[1]:.3f}<br>P90: %{customdata[2]:.3f}"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=f"{feature}: median and P10–P90 by ingestion time",
        xaxis_title="Ingestion timestamp (UTC, hourly bins)",
        yaxis_title=feature, **_figure_layout(),
    )
    fig.update_xaxes(type="date", tickformat="%b %d\n%H:%M", nticks=8)
    return fig


def _prediction_time_groups(predictions):
    required = {"prediction_timestamp", "predicted_failure"}
    if predictions is None or predictions.empty or not required.issubset(predictions.columns):
        return pd.DataFrame()
    frame = predictions.copy()
    frame["prediction_timestamp"] = pd.to_datetime(frame["prediction_timestamp"], errors="coerce")
    frame["predicted_failure"] = pd.to_numeric(frame["predicted_failure"], errors="coerce").fillna(0)
    frame = frame.dropna(subset=["prediction_timestamp"])
    if frame.empty:
        return pd.DataFrame()
    frame["failure_probability"] = pd.to_numeric(
        frame.get("failure_probability", pd.Series(index=frame.index, dtype=float)), errors="coerce"
    )
    # Use hourly bins when there is enough timestamp span; otherwise group by date.
    span_hours = (frame["prediction_timestamp"].max() - frame["prediction_timestamp"].min()).total_seconds() / 3600
    frame["time_bucket"] = frame["prediction_timestamp"].dt.floor("h" if span_hours <= 72 else "D")
    grouped = frame.groupby("time_bucket").agg(
        prediction_count=("predicted_failure", "size"),
        predicted_failures=("predicted_failure", "sum"),
        median_probability=("failure_probability", "median"),
        p95_probability=("failure_probability", lambda values: values.quantile(0.95)),
    ).reset_index().sort_values("time_bucket")
    grouped["predicted_failure_rate_pct"] = (
        grouped["predicted_failures"] / grouped["prediction_count"] * 100
    )
    grouped["median_probability_pct"] = grouped["median_probability"] * 100
    grouped["p95_probability_pct"] = grouped["p95_probability"] * 100
    return grouped


def _prediction_volume_figure(predictions, scale="linear"):
    grouped = _prediction_time_groups(predictions)
    if grouped.empty:
        return _empty_figure("Prediction volume over time")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=grouped["time_bucket"], y=grouped["prediction_count"],
        name="Predictions", marker_color="#4ea1ff",
    ))
    fig.add_trace(go.Bar(
        x=grouped["time_bucket"], y=grouped["predicted_failures"],
        name="Predicted failures", marker_color="#f16d6d",
    ))
    fig.update_layout(
        title="Prediction volume by time window", barmode="group",
        xaxis_title="", yaxis_title="Machine predictions", **_figure_layout(),
    )
    # A date axis must stay linear. A logarithmic count axis makes smaller
    # batches visible, but zero counts cannot be plotted on a log scale.
    if scale == "log":
        fig.update_yaxes(type="log", dtick=1, tickformat=",d")
    else:
        fig.update_yaxes(type="linear", rangemode="tozero")
    return fig


def _model_behavior_figure(predictions):
    grouped = _prediction_time_groups(predictions)
    if grouped.empty:
        return _empty_figure("Prediction behavior over time")
    fig = go.Figure()
    # Sample size in the hover resolves the 100% from 1/1 vs. 100/100 ambiguity.
    hover_counts = np.column_stack([
        grouped["prediction_count"].astype(int),
        grouped["predicted_failures"].astype(int),
    ])
    fig.add_trace(go.Scatter(
        x=grouped["time_bucket"], y=grouped["predicted_failure_rate_pct"],
        mode="lines+markers", name="Predicted failure rate (%)",
        line={"color": RED, "width": 2.5}, customdata=hover_counts,
        hovertemplate=("%{x}<br>Predicted failure rate: %{y:.2f}%"
                       "<br>Predictions: %{customdata[0]:,}"
                       "<br>Predicted failures: %{customdata[1]:,}<extra></extra>"),
    ))
    fig.add_trace(go.Scatter(
        x=grouped["time_bucket"], y=grouped["median_probability_pct"],
        mode="lines+markers", name="Median probability (%)",
        line={"color": BLUE, "width": 2},
    ))
    fig.add_trace(go.Scatter(
        x=grouped["time_bucket"], y=grouped["p95_probability_pct"],
        mode="lines+markers", name="P95 probability (%)",
        line={"color": AMBER, "width": 2},
    ))
    fig.update_layout(
        title="Model behavior (no ground-truth labels required)",
        xaxis_title="", yaxis_title="Percentage (%)", **_figure_layout(),
    )
    return fig


def _psi_figure(drift):
    if drift is None or drift.empty or not {"feature", "psi"}.issubset(drift.columns):
        return _empty_figure("PSI by feature")
    frame = drift.copy()
    frame["psi"] = pd.to_numeric(frame["psi"], errors="coerce")
    frame = frame.dropna(subset=["psi"]).sort_values("psi")
    if frame.empty:
        return _empty_figure("PSI by feature")
    frame["drift_category"] = frame["psi"].apply(_psi_classification)
    colors = {
        "STABLE": GREEN,
        "MODERATE_DRIFT": AMBER,
        "SIGNIFICANT_DRIFT": RED,
    }
    fig = go.Figure(go.Bar(
        x=frame["psi"], y=frame["feature"], orientation="h",
        marker_color=[colors.get(v, MUTED) for v in frame["drift_category"]],
        customdata=frame[["drift_category"]].to_numpy(),
        hovertemplate="Feature: %{y}<br>PSI: %{x:.3f}<br>Status: %{customdata[0]}<extra></extra>",
    ))
    fig.add_vline(x=0.10, line_dash="dash", line_color=AMBER, annotation_text="Moderate 0.10")
    fig.add_vline(x=0.25, line_dash="dash", line_color=RED, annotation_text="Significant 0.25")
    fig.update_layout(
        title="Population Stability Index by feature",
        xaxis_title="PSI", yaxis_title="", **_figure_layout(),
    )
    fig.update_layout(margin={"l": 198, "r": 42, "t": 78, "b": 90})
    return fig


def _psi_history_figure(history):
    if history is None or history.empty or not {"feature", "psi", "calculated_at"}.issubset(history.columns):
        return _empty_figure("Historical feature drift")
    frame = history.copy()
    frame["calculated_at"] = pd.to_datetime(frame["calculated_at"], errors="coerce")
    frame["psi"] = pd.to_numeric(frame["psi"], errors="coerce")
    frame = frame.dropna(subset=["calculated_at", "psi"])
    if frame.empty:
        return _empty_figure("Historical feature drift")
    latest = _latest_per_feature(frame)
    # Display ALL features whose *latest* rolling PSI is significant, rather
    # than an arbitrary top-N ranking. Historic values can cross thresholds.
    significant_features = (
        latest.loc[latest["psi"] >= 0.25]
        .sort_values("psi", ascending=False)["feature"].tolist()
    )
    if not significant_features:
        return _empty_figure(
            "Historical feature drift",
            "No features currently have significant drift (PSI ≥ 0.25).",
        )
    frame = frame[frame["feature"].isin(significant_features)].sort_values("calculated_at")
    fig = px.line(
        frame, x="calculated_at", y="psi", color="feature", markers=True,
        category_orders={"feature": significant_features},
        title=f"PSI history — {len(significant_features)} features with significant drift",
    )
    fig.add_hline(y=0.10, line_dash="dot", line_color=AMBER)
    fig.add_hline(y=0.25, line_dash="dash", line_color=RED)
    fig.update_layout(xaxis_title="", yaxis_title="PSI", **_figure_layout())
    fig.update_layout(margin={"l": 65, "r": 24, "t": 78, "b": 145},
                      legend={"orientation": "h", "yanchor": "top", "y": -0.29,
                              "xanchor": "left", "x": 0, "font": {"size": 9}})
    return fig


def _distribution_payload(data, features):
    reference = data.get("reference", pd.DataFrame())
    current = data.get("current_rolling", data.get("current", pd.DataFrame()))
    payload = {}
    for feature in features:
        payload[feature] = {
            # Full 8,000-row Notebook 51 baseline, not the first 5,000 rows.
            "reference": pd.to_numeric(reference[feature], errors="coerce").dropna().tolist(),
            # Latest 1,000 Gold observations selected in data.py, as in Notebook 51.
            "current": pd.to_numeric(current[feature], errors="coerce").dropna().tolist(),
        }
    return payload


def _boxplot_figure(feature, payload):
    if not feature or not payload or feature not in payload:
        return _empty_figure("Reference vs. streaming distribution", "Raw reference/current samples are not available.")
    reference = payload[feature].get("reference", [])
    current = payload[feature].get("current", [])
    if not reference or not current:
        return _empty_figure(f"{feature}: reference vs. streaming", "No numeric samples available for both populations.")
    fig = go.Figure()
    fig.add_trace(go.Box(
        y=reference, name="Training/reference baseline",
        boxmean=True, marker_color="#60a5fa", line_color="#60a5fa",
    ))
    fig.add_trace(go.Box(
        y=current, name="Current streaming window",
        boxmean=True, marker_color="#f59e0b", line_color="#f59e0b",
    ))
    fig.update_layout(
        title=f"{feature}: reference vs. current streaming data",
        yaxis_title=feature, xaxis_title="", **_figure_layout(),
    )
    return fig


def _gaussian_kde_values(samples, x_grid, bandwidth):
    """Gaussian kernel density on a common grid using NumPy (no extra dependency).

    Chunked evaluation bounds memory use for multi-thousand-record populations.
    """
    values = np.asarray(samples, dtype=float)
    densities = np.zeros(len(x_grid), dtype=float)
    for start in range(0, len(values), 600):
        chunk = values[start:start + 600]
        z = (x_grid[:, None] - chunk[None, :]) / bandwidth
        densities += np.exp(-0.5 * z * z).sum(axis=1)
    densities /= len(values) * bandwidth * np.sqrt(2.0 * np.pi)
    return densities


def _histogram_figure(feature, payload):
    """Smooth, lightly shaded KDE distributions, preserving legacy graph callbacks.

    Uses the *same* kernel bandwidth and X-grid for both populations so the
    curves can be compared fairly. This is a visual smoothing step only; PSI
    and KS remain computed on unsmoothed data by the Databricks notebooks.
    """
    if not feature or not payload or feature not in payload:
        return _empty_figure("Reference vs. streaming distribution")
    reference = pd.to_numeric(pd.Series(payload[feature].get("reference", [])), errors="coerce")
    current = pd.to_numeric(pd.Series(payload[feature].get("current", [])), errors="coerce")
    reference = reference.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
    current = current.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
    if len(reference) == 0 or len(current) == 0:
        return _empty_figure(f"{feature}: distribution shape comparison", "No numeric samples available for both populations.")

    # Choose a single robust Silverman-like bandwidth from the combined sample.
    # A shared bandwidth avoids artificially smoothing one group more than the
    # other merely because it has fewer rows.
    pooled = np.concatenate([reference, current])
    low = float(np.min(pooled))
    high = float(np.max(pooled))
    span = high - low
    std = float(np.std(pooled, ddof=1)) if len(pooled) > 1 else 0.0
    q25, q75 = np.percentile(pooled, [25, 75])
    robust_std = float((q75 - q25) / 1.349)
    positive_scales = [v for v in (std, robust_std) if np.isfinite(v) and v > 0]
    scale = min(positive_scales) if positive_scales else max(abs(low) * 0.05, 1.0)
    bandwidth = max(0.9 * scale * (len(pooled) ** (-0.2)), span / 300.0, 1e-8)

    grid_low = low - 3.0 * bandwidth
    if low >= 0:
        grid_low = max(0.0, grid_low)
    grid_high = high + 3.0 * bandwidth
    x_grid = np.linspace(grid_low, grid_high, 280)

    fig = go.Figure()
    for values, name, outline, shade in (
        (reference, "Training/reference baseline", "rgb(96,165,250)", "rgba(96,165,250,0.15)"),
        (current, "Current streaming window", "rgb(241,109,109)", "rgba(241,109,109,0.15)"),
    ):
        density = _gaussian_kde_values(values, x_grid, bandwidth)
        fig.add_trace(go.Scatter(
            x=x_grid, y=density, mode="lines", name=name,
            line={"color": outline, "width": 2.5},
            fill="tozeroy", fillcolor=shade,
            hovertemplate="%{x:.2f}<br>Estimated density: %{y:.4f}<extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(
        title=f"{feature}: smooth distribution comparison (KDE)",
        xaxis_title=feature, yaxis_title="Estimated probability density",
        **_figure_layout(),
    )
    fig.update_yaxes(rangemode="tozero")
    return fig


def _prediction_time_range(predictions):
    """UTC whole-hour bounds for the range slider; no extra SQL calls."""
    if predictions is None or predictions.empty or "prediction_timestamp" not in predictions:
        return None
    stamps = pd.to_datetime(predictions["prediction_timestamp"], errors="coerce", utc=True).dropna()
    if stamps.empty:
        return None
    lo = int(stamps.min().floor("h").timestamp() // 3600)
    hi = int(stamps.max().floor("h").timestamp() // 3600)
    return lo, hi


def _hour_label(hour):
    return pd.Timestamp(int(hour), unit="h", tz="UTC").strftime("%b %d %H:%M")


def _prediction_time_slider(predictions):
    """The two handles control inclusive UTC hours; selected dates appear separately.

    Suppress native hour-value tooltips and dense slider marks: they display
    large epoch-hour integers and overlap on the narrow left-hand chart card.
    """
    bounds = _prediction_time_range(predictions)
    if bounds is None:
        return dcc.RangeSlider(id="prediction-time-range", min=0, max=1, value=[0, 1],
                               disabled=True, marks={})
    lo, hi = bounds
    hi_for_slider = max(lo + 1, hi)
    return dcc.RangeSlider(
        id="prediction-time-range", min=lo, max=hi_for_slider,
        value=[lo, hi_for_slider], marks={}, step=1,
        allowCross=False, updatemode="mouseup", disabled=(lo == hi),
    )


def _predictions_in_time_range(predictions, selected_hours):
    """Return only stored predictions inside inclusive UTC slider-hour bins."""
    if predictions is None or predictions.empty or "prediction_timestamp" not in predictions:
        return pd.DataFrame() if predictions is None else predictions.iloc[0:0].copy()
    if not selected_hours or len(selected_hours) != 2:
        return predictions.copy()
    start_hour, end_hour = sorted(int(v) for v in selected_hours)
    timestamps = pd.to_datetime(predictions["prediction_timestamp"], errors="coerce", utc=True)
    start = pd.Timestamp(start_hour, unit="h", tz="UTC")
    end_exclusive = pd.Timestamp(end_hour + 1, unit="h", tz="UTC")
    return predictions.loc[(timestamps >= start) & (timestamps < end_exclusive)].copy()


def _prediction_probability_figure(predictions):
    if predictions is None or predictions.empty or "failure_probability" not in predictions.columns:
        return _empty_figure("Failure probability distribution")
    frame = predictions.copy()
    frame["failure_probability"] = pd.to_numeric(frame["failure_probability"], errors="coerce")
    frame = frame.dropna(subset=["failure_probability"])
    if frame.empty:
        return _empty_figure("Failure probability distribution")
    fig = px.histogram(
        frame, x="failure_probability", nbins=40,
        title="Failure probability distribution",
    )
    threshold = None
    if "threshold" in frame.columns:
        values = pd.to_numeric(frame["threshold"], errors="coerce").dropna()
        if not values.empty:
            threshold = float(values.median())
    if threshold is not None:
        fig.add_vline(
            x=threshold, line_dash="dash", line_color=RED, line_width=2,
            annotation_text=f"Median stored threshold: {threshold:.5f}",
        )
    fig.update_layout(
        xaxis_title="Predicted failure probability", yaxis_title="Number of machines",
        **_figure_layout(),
    )
    return fig


def _top_risk_figure(predictions):
    required = {"UDI", "failure_probability"}
    if predictions is None or predictions.empty or not required.issubset(predictions.columns):
        return _empty_figure("Highest-risk machines")
    frame = predictions.copy()
    frame["failure_probability"] = pd.to_numeric(frame["failure_probability"], errors="coerce")
    frame = frame.dropna(subset=["failure_probability"]).nlargest(15, "failure_probability")
    if frame.empty:
        return _empty_figure("Highest-risk machines")
    frame["UDI"] = frame["UDI"].astype(str)
    frame = frame.sort_values("failure_probability")
    if "predicted_failure" in frame.columns:
        flagged = pd.to_numeric(frame["predicted_failure"], errors="coerce").fillna(0).astype(int)
    else:
        flagged = pd.Series(0, index=frame.index)
    colors = [RED if value == 1 else BLUE for value in flagged]
    fig = go.Figure(go.Bar(
        x=frame["failure_probability"], y=frame["UDI"], orientation="h",
        marker_color=colors,
        customdata=frame[["threshold"]].to_numpy() if "threshold" in frame.columns else None,
        hovertemplate="UDI: %{y}<br>Probability: %{x:.5f}<extra></extra>",
    ))
    fig.update_layout(
        title="15 highest predicted failure probabilities",
        xaxis_title="Failure probability", yaxis_title="Machine UDI",
        **_figure_layout(),
    )
    return fig


def _pipeline_status(pipeline, source_mode="LIVE DATABRICKS"):
    """Summarize latest *completed* executions, never claim a job is live."""
    if source_mode == "DEMO DATA":
        return "Demo mode"
    if pipeline is None or pipeline.empty:
        return "No run history"
    if "result_state" not in pipeline.columns:
        return "Run history available"
    states = pipeline["result_state"].fillna("UNKNOWN").astype(str).str.upper()
    success_count = int((states == "SUCCEEDED").sum())
    total = len(states)
    return f"{success_count}/{total} succeeded"


def _pipeline_run_table(data):
    """One row per monitored job; timestamps from Databricks are UTC."""
    if data.get("source_mode") == "DEMO DATA":
        return html.Div("Demo mode — live Lakeflow job history is unavailable.", className="empty-state")
    frame = data.get("pipeline", pd.DataFrame())
    if frame is None or frame.empty:
        return html.Div(
            "No completed runs found in the configured monitoring window, or system-table access is unavailable.",
            className="empty-state",
        )
    out = frame.copy()
    if "period_end_time" in out.columns:
        out["period_end_time"] = pd.to_datetime(out["period_end_time"], utc=True, errors="coerce")
        out = out.sort_values("period_end_time", ascending=False)
        out["completed_utc"] = out["period_end_time"].dt.strftime("%Y-%m-%d %H:%M UTC")
    if "paused" in out.columns:
        out["paused"] = out["paused"].map({True: "Yes", False: "No"}).fillna("Unknown")
    return _table(out, ["job_name", "job_id", "result_state", "completed_utc", "paused"], page_size=10)


def _alert_counts(data):
    # New alerts are EVENTS, never a persisted state label in Notebook 51.
    state = _normalize_alert_state(data.get("alert_state", pd.DataFrame()))
    events = data.get("alert_events", pd.DataFrame())
    if events is None:
        events = pd.DataFrame()
    new_count = (
        int((events["event_type"].astype(str).str.upper() == "NEW_ALERT").sum())
        if "event_type" in events.columns else 0
    )
    open_count = len(_open_alerts(data))
    statuses = (
        state["alert_status"].astype(str).str.upper()
        if "alert_status" in state.columns else pd.Series(dtype=str)
    )
    acknowledged = int((statuses == "ACKNOWLEDGED").sum())
    resolved = int(statuses.isin({"RESOLVED", "CLOSED", "RECOVERED"}).sum())
    return new_count, open_count, acknowledged, resolved


def overview_page(data):
    predictions = data["predictions"]
    drift = _drift_with_classes(data["drift_rolling"])
    active_alerts = _open_alerts(data)
    features = _numeric_features(data.get("current", pd.DataFrame()))
    feature = "Temperature_difference_K" if "Temperature_difference_K" in features else (features[0] if features else None)

    machine_count = predictions["UDI"].nunique() if "UDI" in predictions.columns else 0
    flagged_count = (
        int(pd.to_numeric(predictions["predicted_failure"], errors="coerce").fillna(0).sum())
        if "predicted_failure" in predictions.columns else 0
    )
    significant_count = int((drift.get("dashboard_drift_status", pd.Series(dtype=str)) == "SIGNIFICANT_DRIFT").sum())
    moderate_count = int((drift.get("dashboard_drift_status", pd.Series(dtype=str)) == "MODERATE_DRIFT").sum())
    new_count, open_count, acknowledged, resolved = _alert_counts(data)

    source_note = (
        "DEMO DATA — illustrative values for interface development."
        if data["source_mode"] == "DEMO DATA"
        else "LIVE DATABRICKS DATA — values reflect the configured Unity Catalog tables."
    )

    feature_control = dcc.Dropdown(
        id="overview-feature",
        options=_grouped_feature_options(features),
        value=feature,
        clearable=False,
        disabled=not bool(features),
        placeholder="Select a numeric feature",
        className="feature-dropdown",
    )

    families = html.Div(
        [
            _family(
                "Prediction activity", "What the model is flagging",
                [
                    _kpi("Machines monitored", f"{machine_count:,}", "Unique UDIs in recent predictions", "blue"),
                    _kpi("Predicted failures", f"{flagged_count:,}", "Predictions above their stored threshold", "red"),
                ],
                "blue",
            ),
            _family(
                "Feature health", "Distribution drift across monitored features",
                [
                    _kpi("Moderate drift", f"{moderate_count:,}", "PSI from 0.10 to below 0.25", "amber"),
                    _kpi("Significant drift", f"{significant_count:,}", "PSI at or above 0.25", "red"),
                ],
                "amber",
            ),
            _family(
                "Alert management", "Items requiring operational attention",
                [
                    _kpi("Active alerts", f"{len(active_alerts):,}", "Unresolved alert records", "amber"),
                    _kpi("Pipeline status", _pipeline_status(data["pipeline"], data["source_mode"]), "Latest completed runs · system-table reporting may lag", "green"),
                ],
                "green",
            ),
        ],
        className="family-grid",
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div([html.H2("Operational overview"), html.P(source_note, className="muted")]),
                    html.Div("REFRESH ON DEMAND", className="refresh-label"),
                ],
                className="page-heading heading-with-meta",
            ),
            _error_banner(data["errors"]),
            families,
            html.Div(
                [
                    _panel(
                        "Feature behavior by ingestion time",
                        html.Div([feature_control, dcc.Graph(
                            id="overview-feature-trend",
                            figure=_feature_batch_trend(data.get("current"), feature),
                            config={"displayModeBar": False},
                        )]),
                        "Line shows feature medians over Bronze ingestion time; the shaded band is P10–P90. Colored markers identify each CSV batch (not individual machine readings).",
                    ),
                    _panel(
                        "Prediction volume over time",
                        html.Div([
                            html.Div([
                                html.Span("Y-axis scale", className="axis-scale-label"),
                                dcc.RadioItems(
                                    id="prediction-volume-scale",
                                    options=[{"label": "Log", "value": "log"},
                                             {"label": "Linear", "value": "linear"}],
                                    value="log", inline=True, className="axis-scale-options",
                                ),
                            ], className="axis-scale-row"),
                            dcc.Graph(id="prediction-volume-graph",
                                      figure=_prediction_volume_figure(predictions, "log"),
                                      config={"displayModeBar": False}),
                        ]),
                        "Counts of predictions and predicted failures by timestamp. Log Y-axis reveals smaller batches; zero counts are not visible on log axes. Switch to Linear to see zeros. X-axis remains chronological.",
                    ),
                ],
                className="two-column",
            ),
            html.Div(
                [
                    _panel(
                        "Model behavior over time",
                        dcc.Graph(figure=_model_behavior_figure(predictions), config={"displayModeBar": False}),
                        "Tracks predicted failure rate, median score and P95 score. Hover over the red series for machine counts per time window. Lines connect observed windows, not intervening predictions. These are behavior metrics, not measured model accuracy.",
                    ),
                    _panel(
                        "Current feature drift",
                        dcc.Graph(figure=_psi_figure(drift), config={"displayModeBar": False}),
                        "Features are classified using PSI thresholds: 0.10 moderate and 0.25 significant.",
                    ),
                ],
                className="two-column",
            ),
            _panel(
                "Lakeflow job execution history",
                _pipeline_run_table(data),
                "Most recent completed run for each monitored Job ID (UTC). Historical results may arrive with a reporting delay; this does not indicate whether a job is currently running. Paused status comes from job metadata when available.",
            ),
            html.Div(
                "Ground-truth failure labels are not available at prediction time. Precision, recall, F1 and F2 are therefore not presented as live metrics.",
                className="info-banner",
            ),
        ]
    )


def predictions_page(data):
    predictions = data["predictions"]
    count = len(predictions)
    flagged = (
        int(pd.to_numeric(predictions["predicted_failure"], errors="coerce").fillna(0).sum())
        if "predicted_failure" in predictions.columns else 0
    )
    rate = (flagged / count * 100) if count else 0
    threshold_text = "—"
    if "threshold" in predictions.columns:
        thresholds = pd.to_numeric(predictions["threshold"], errors="coerce").dropna()
        if not thresholds.empty:
            threshold_text = f"{thresholds.median():.5f}"
    preferred = [
        "UDI", "failure_probability", "predicted_failure", "threshold",
        "prediction_timestamp", "model_uri",
    ]
    time_bounds = _prediction_time_range(predictions)
    earliest_time = f"{_hour_label(time_bounds[0])} UTC" if time_bounds else "—"
    latest_time = f"{_hour_label(time_bounds[1])} UTC" if time_bounds else "—"
    return html.Div(
        [
            html.Div(
                [
                    html.H2("Machine predictions"),
                    html.P("Identify machines with the highest predicted failure risk and inspect the stored decision threshold.", className="muted"),
                ],
                className="page-heading",
            ),
            _error_banner(data["errors"]),
            html.Div(
                [
                    _kpi("Prediction records", f"{count:,}", "Most recent records returned (up to 5,000)", "blue"),
                    _kpi("Predicted failures", f"{flagged:,}", "Predictions above stored thresholds", "red"),
                    _kpi("Predicted failure rate", f"{rate:.2f}%", "Share flagged within loaded records", "amber"),
                    _kpi("Median stored threshold", threshold_text, "Threshold recorded with predictions", "blue"),
                ],
                className="kpi-grid four",
            ),
            html.Div(
                [
                    _panel(
                        "Failure probability distribution",
                        html.Div([
                            html.Div([
                                html.Div("Prediction time range (UTC)", className="time-range-label"),
                                html.Div([
                                    html.Div([
                                        html.Span("FROM", className="time-range-date-caption"),
                                        html.Span(earliest_time, id="prediction-range-start",
                                                  className="time-range-date-value"),
                                    ], className="time-range-date"),
                                    html.Div([
                                        html.Span("TO", className="time-range-date-caption"),
                                        html.Span(latest_time, id="prediction-range-end",
                                                  className="time-range-date-value"),
                                    ], className="time-range-date"),
                                ], className="time-range-selected"),
                                _prediction_time_slider(predictions),
                                html.Div([
                                    html.Span("Earliest available", className="time-range-boundary"),
                                    html.Span("Latest available", className="time-range-boundary"),
                                ], className="time-range-endpoints"),
                                html.Div([
                                    html.Span(id="prediction-range-summary", children=(
                                        f"{len(predictions):,} of {len(predictions):,} predictions in selected period")),
                                    html.Button("Reset to all", id="prediction-range-reset",
                                                n_clicks=0, className="range-reset-button"),
                                ], className="time-range-footer"),
                            ], className="time-range-control"),
                            dcc.Graph(id="prediction-probability-graph",
                                      figure=_prediction_probability_figure(predictions),
                                      config={"displayModeBar": False}),
                        ]),
                        "Use the slider to filter this histogram by prediction timestamp (UTC). Only this chart is filtered; the KPIs, risk ranking and register remain full-snapshot. The vertical reference line shows the median stored threshold.",
                    ),
                    _panel(
                        "Highest-risk machines",
                        dcc.Graph(figure=_top_risk_figure(predictions), config={"displayModeBar": False}),
                        "The 15 largest predicted probabilities. Red bars indicate records flagged as failures.",
                    ),
                ],
                className="two-column",
            ),
            _panel(
                "Prediction register",
                _table(predictions, preferred, page_size=15, table_id="predictions-table"),
                "Search, filter and sort by machine UDI, failure probability, prediction status or timestamp.",
            ),
        ]
    )


def drift_page(data):
    drift = _drift_with_classes(data["drift_rolling"])
    features = _feature_options(data)
    default_feature = "Temperature_difference_K" if "Temperature_difference_K" in features else (features[0] if features else None)
    payload = _distribution_payload(data, features)
    moderate = int((drift.get("dashboard_drift_status", pd.Series(dtype=str)) == "MODERATE_DRIFT").sum())
    significant = int((drift.get("dashboard_drift_status", pd.Series(dtype=str)) == "SIGNIFICANT_DRIFT").sum())
    stable = int((drift.get("dashboard_drift_status", pd.Series(dtype=str)) == "STABLE").sum())

    drift_columns = [
        "feature", "feature_type", "current_records", "psi", "dashboard_drift_status",
        "ks_statistic", "ks_pvalue", "psi_status", "ks_significant", "calculated_at",
        "rolling_window_size", "minimum_udi", "maximum_udi",
    ]
    selector = dcc.Dropdown(
        id="drift-feature",
        options=_grouped_feature_options(features),
        value=default_feature,
        clearable=False,
        disabled=not bool(features),
        placeholder="Select a feature",
        className="feature-dropdown",
    )
    return html.Div(
        [
            html.Div(
                [
                    html.H2("Drift monitoring"),
                    html.P("Compare the training/reference population with incoming streaming data and monitor distribution changes over time.", className="muted"),
                ],
                className="page-heading",
            ),
            _error_banner(data["errors"]),
            html.Div(
                [
                    _kpi("Stable features", f"{stable:,}", "PSI below 0.10", "green"),
                    _kpi("Moderate drift", f"{moderate:,}", "PSI from 0.10 to below 0.25", "amber"),
                    _kpi("Significant drift", f"{significant:,}", "PSI at or above 0.25", "red"),
                ],
                className="kpi-grid three",
            ),
            html.Div(
                [
                    _panel(
                        "PSI by feature",
                        dcc.Graph(figure=_psi_figure(drift), config={"displayModeBar": False}),
                        "The thresholds shown are the dashboard's current classification rules; keep them aligned with the drift calculation notebook.",
                    ),
                    _panel(
                        "Historical drift",
                        dcc.Graph(figure=_psi_history_figure(data["drift_history"]), config={"displayModeBar": False}),
                        "Trend of rolling PSI for all features whose latest PSI is at least 0.25. The number of lines changes with the current drift state.",
                    ),
                ],
                className="two-column",
            ),
            _panel(
                "Reference vs. current streaming distribution",
                html.Div(
                    [
                        selector,
                        dcc.Store(id="distribution-data", data=payload),
                        html.Div(
                            [
                                dcc.Graph(
                                    id="feature-boxplot",
                                    figure=_boxplot_figure(default_feature, payload),
                                    config={"displayModeBar": False},
                                ),
                                dcc.Graph(
                                    id="feature-histogram",
                                    figure=_histogram_figure(default_feature, payload),
                                    config={"displayModeBar": False},
                                ),
                            ],
                            className="two-column chart-pair",
                        ),
                    ]
                ),
                "Compare the full 8,000-record PSI reference with the latest 1,000 Gold records (same ordering as Notebook 51). KDE uses a shared bandwidth and 15%-opacity shading. Smoothing is visual only; PSI/KS calculations are unchanged. Machine Type is categorical and excluded from numeric comparisons.",
            ),
            _panel(
                "Drift statistics",
                _table(drift, drift_columns, page_size=15),
                "One latest monitoring result per feature, with PSI and KS statistics.",
            ),
        ]
    )


def _alert_detail_content(record):
    if not record:
        return html.Div("Select an alert in the inbox to inspect its details.", className="empty-state")
    fields = [
        ("Feature", "feature"),
        ("Severity", "severity"),
        ("Status", "alert_status"),
        ("PSI", "psi"),
        ("KS p-value", "ks_pvalue"),
        ("First detected", "first_detected_at"),
        ("Last detected", "last_detected_at"),
        ("Recommended action", "recommended_action"),
        ("Notification status", "notification_status"),
    ]
    cells = []
    for label, key in fields:
        value = record.get(key)
        if value is None:
            continue
        cells.append(
            html.Div(
                [html.Div(label, className="detail-label"), html.Div(str(value), className="detail-value")],
                className="detail-cell",
            )
        )
    return html.Div(cells, className="detail-grid")


def alerts_page(data):
    events = data["alert_events"]
    state = data["alert_state"]
    current = state.copy() if state is not None and not state.empty else _open_alerts(data)
    new_count, open_count, acknowledged, resolved = _alert_counts(data)

    if current is None:
        current = pd.DataFrame()
    active = _open_alerts(data)
    inbox_columns = [
        "feature", "severity", "alert_status", "psi", "ks_pvalue",
        "first_detected_at", "last_detected_at", "last_transition",
        "consecutive_normal_windows", "recommended_action", "last_notified_at",
    ]
    event_columns = [
        "event_id", "feature", "event_type", "severity", "alert_status",
        "psi", "notification_status", "event_timestamp", "recorded_at",
    ]
    inbox = _table(
        active, inbox_columns, page_size=10, table_id="alert-inbox", row_selectable="single"
    )
    return html.Div(
        [
            html.Div(
                [
                    html.H2("Alert management"),
                    html.P("An operational inbox for drift events that need review, follow-up or confirmation of recovery.", className="muted"),
                ],
                className="page-heading",
            ),
            _error_banner(data["errors"]),
            html.Div(
                [
                    _kpi("New alert events", f"{new_count:,}", "NEW_ALERT events in loaded event history", "blue"),
                    _kpi("Open alerts", f"{open_count:,}", "Unresolved alerts awaiting review", "amber"),
                    _kpi("Acknowledged", f"{acknowledged:,}", "Review actions not yet enabled in live data", "blue"),
                    _kpi("Resolved", f"{resolved:,}", "Resolved records in current state", "green"),
                ],
                className="kpi-grid four",
            ),
            html.Div(
                [
                    _panel(
                        "Active alert inbox",
                        inbox,
                        "Select a row to inspect the alert. Acknowledgment and resolution controls are intentionally not enabled until backend state transitions are implemented.",
                    ),
                    _panel(
                        "Selected alert details",
                        html.Div(id="alert-details", children=_alert_detail_content(None)),
                        "Current feature severity, drift statistics and lifecycle state. Notification status is shown in the event history.",
                    ),
                ],
                className="two-column alert-layout",
            ),
            _panel(
                "Alert event history",
                _table(events, event_columns, page_size=15),
                "Chronological audit trail of NEW_ALERT, ACKNOWLEDGED, ESCALATED, REOPENED and RESOLVED events when present.",
            ),
            html.Div(
                "The dashboard is read-only in this version. Databricks remains responsible for creating alerts, sending notifications and updating lifecycle state.",
                className="info-banner",
            ),
        ]
    )


app = Dash(__name__, title="Predictive Maintenance Monitor", suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.Div("PM", className="brand-mark"),
                        html.Div(
                            [
                                html.Div("PREDICTIVE MAINTENANCE", className="eyebrow"),
                                html.Div("Monitoring Console", className="brand-title"),
                            ]
                        ),
                    ],
                    className="brand",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Span("●", className="status-dot"),
                                html.Span("DEMO MODE" if settings.demo_mode else "LIVE MODE", className="mode-label"),
                            ],
                            className="mode-pill",
                        ),
                        html.Button("Refresh Data", id="refresh-button", n_clicks=0,
                                    className="refresh-button", title="Retrieve fresh Databricks data"),
                    ],
                    className="topbar-actions",
                ),
            ],
            className="topbar",
        ),
        html.Div(
            [
                dcc.Tabs(
                    id="nav-tabs",
                    value="overview",
                    children=[
                        dcc.Tab(label="Overview", value="overview"),
                        dcc.Tab(label="Predictions", value="predictions"),
                        dcc.Tab(label="Drift Monitoring", value="drift"),
                        dcc.Tab(label="Alert Management", value="alerts"),
                    ],
                    className="nav-tabs",
                    parent_className="tabs-container",
                ),
                html.Div(id="page-content", className="page-content"),
            ],
            className="app-container",
        ),
        html.Div(
            [
                html.Span("AI4I 2020 · Databricks · Delta Lake · MLflow"),
                html.Span(id="last-refresh", children="Data loading… · Manual refresh"),
            ],
            className="footer",
        ),
        html.Div(id="refresh-feedback", className="refresh-feedback", role="status"),
    ],
    className="app-shell",
)


@app.callback(
    Output("page-content", "children"),
    Output("last-refresh", "children"),
    Output("refresh-feedback", "children"),
    Input("nav-tabs", "value"),
    Input("refresh-button", "n_clicks"),
)
def render_page(active_tab, _refresh_clicks):
    # A new visitor loads the warehouse snapshot once. Changing tabs only reads
    # that snapshot; subsequent warehouse queries require the Refresh Data button.
    if ctx.triggered_id == "refresh-button":
        snapshot, error = refresh_snapshot()
    else:
        snapshot, error = get_snapshot(), None
    data = snapshot["data"]
    if active_tab == "predictions":
        page = predictions_page(data)
    elif active_tab == "drift":
        page = drift_page(data)
    elif active_tab == "alerts":
        page = alerts_page(data)
    else:
        page = overview_page(data)
    label = f"Last data load: {snapshot['loaded_at']} · Manual refresh"
    if snapshot["partial"]:
        label += " · PARTIAL DATA"
    feedback = html.Div(error, className="warning-banner") if error else ""
    return page, label, feedback


@app.callback(
    Output("prediction-volume-graph", "figure"),
    Input("prediction-volume-scale", "value"),
)
def update_volume_scale(scale):
    return _prediction_volume_figure(get_snapshot()["data"]["predictions"], scale)


@app.callback(
    Output("prediction-probability-graph", "figure"),
    Output("prediction-range-summary", "children"),
    Output("prediction-range-start", "children"),
    Output("prediction-range-end", "children"),
    Input("prediction-time-range", "value"),
)
def update_prediction_time_range(selected_hours):
    predictions = get_snapshot()["data"]["predictions"]
    filtered = _predictions_in_time_range(predictions, selected_hours)
    if selected_hours and len(selected_hours) == 2 and _prediction_time_range(predictions):
        lo, hi = sorted(int(x) for x in selected_hours)
        start_text, end_text = f"{_hour_label(lo)} UTC", f"{_hour_label(hi)} UTC"
    else:
        bounds = _prediction_time_range(predictions)
        start_text = f"{_hour_label(bounds[0])} UTC" if bounds else "—"
        end_text = f"{_hour_label(bounds[1])} UTC" if bounds else "—"
    summary = f"{len(filtered):,} of {len(predictions):,} predictions in selected period"
    return _prediction_probability_figure(filtered), summary, start_text, end_text


@app.callback(
    Output("prediction-time-range", "value"),
    Input("prediction-range-reset", "n_clicks"),
    State("prediction-time-range", "min"),
    State("prediction-time-range", "max"),
    prevent_initial_call=True,
)
def reset_prediction_time_range(_clicks, minimum, maximum):
    return [minimum, maximum]


@app.callback(
    Output("overview-feature-trend", "figure"),
    Input("overview-feature", "value"),
)
def update_overview_feature(feature):
    data = get_snapshot()["data"]
    return _feature_batch_trend(data.get("current"), feature)


@app.callback(
    Output("feature-boxplot", "figure"),
    Output("feature-histogram", "figure"),
    Input("drift-feature", "value"),
    State("distribution-data", "data"),
)
def update_drift_feature(feature, payload):
    return _boxplot_figure(feature, payload), _histogram_figure(feature, payload)


@app.callback(
    Output("alert-details", "children"),
    Input("alert-inbox", "selected_rows"),
    State("alert-inbox", "data"),
)
def update_alert_details(selected_rows, rows):
    if not selected_rows or not rows:
        return _alert_detail_content(None)
    index = selected_rows[0]
    if index < 0 or index >= len(rows):
        return _alert_detail_content(None)
    return _alert_detail_content(rows[index])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=False)
