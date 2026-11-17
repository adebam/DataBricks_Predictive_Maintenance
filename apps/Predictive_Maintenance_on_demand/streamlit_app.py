import os
import math
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Predictive Maintenance",
    page_icon="⚙️",
    layout="wide"
)

# ============================================================
# CONFIGURATION
# ============================================================

DATA_PATH = "data/plotting_data.parquet"
API_URL = os.getenv("API_URL", "http://127.0.0.1:8002")


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_parquet(DATA_PATH)

    df["Failure status"] = df["Machine_failure"].map({
        0: "No failure",
        1: "Failure"
    })

    return df


df = load_data()


# ============================================================
# HELPERS
# ============================================================

def padded_slider_bounds(series, pad_frac=0.25, floor_zero=False):
    low = float(series.min())
    high = float(series.max())

    span = high - low
    pad = span * pad_frac if span > 0 else 1.0

    low = low - pad
    high = high + pad

    if floor_zero:
        low = max(0.0, low)

    return low, high


def full_plot_bounds(series, current_value, pad_frac=0.02):
    low = min(float(series.min()), float(current_value))
    high = max(float(series.max()), float(current_value))

    span = high - low
    pad = span * pad_frac if span > 0 else 1.0

    return low - pad, high + pad


@st.cache_data(show_spinner=False)
def calculate_kde(values, x_min, x_max, grid_size=200):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]

    n = len(values)
    if n < 2:
        return np.array([]), np.array([])

    std = np.std(values, ddof=1)
    q25, q75 = np.percentile(values, [25, 75])
    iqr = q75 - q25

    robust_std = min(std, iqr / 1.34) if iqr > 0 else std
    bandwidth = 0.9 * robust_std * n ** (-1 / 5)

    if not np.isfinite(bandwidth) or bandwidth <= 0:
        bandwidth = std * n ** (-1 / 5)

    if not np.isfinite(bandwidth) or bandwidth <= 0:
        bandwidth = 1.0

    x_grid = np.linspace(x_min, x_max, grid_size)

    z = (x_grid[:, None] - values[None, :]) / bandwidth
    density = np.exp(-0.5 * z ** 2).mean(axis=1) / (bandwidth * np.sqrt(2 * np.pi))

    return x_grid, density


def build_pair_plot(df, current_values):
    features = [
        ("Air_temperature_K", "Air Temperature (K)"),
        ("Process_temperature_K", "Process Temperature (K)"),
        ("Rotational_speed_rpm", "Rotational Speed (rpm)"),
        ("Torque_Nm", "Torque (Nm)"),
        ("Tool_wear_min", "Tool Wear (min)")
    ]

    classes = [
        {
            "name": "No failure",
            "value": 0,
            "color": "#3182CE",
            "fill": "rgba(49,130,206,0.20)"
        },
        {
            "name": "Failure",
            "value": 1,
            "color": "#E45756",
            "fill": "rgba(228,87,86,0.20)"
        }
    ]

    n_features = len(features)

    axis_limits = {
        col: full_plot_bounds(df[col], current_values[col], pad_frac=0.02)
        for col, _ in features
    }

    fig = make_subplots(
        rows=n_features,
        cols=n_features,
        horizontal_spacing=0.03,
        vertical_spacing=0.03
    )

    for row, (y_col, y_label) in enumerate(features, start=1):
        for col, (x_col, x_label) in enumerate(features, start=1):

            x_low, x_high = axis_limits[x_col]
            y_low, y_high = axis_limits[y_col]

            # ------------------------------------------------
            # DIAGONAL: KDE DENSITY
            # ------------------------------------------------
            if row == col:
                for cls in classes:
                    subset = df.loc[df["Machine_failure"] == cls["value"], x_col].to_numpy()

                    kde_x, kde_y = calculate_kde(subset, x_low, x_high)

                    if len(kde_x) == 0:
                        continue

                    fig.add_trace(
                        go.Scatter(
                            x=kde_x,
                            y=kde_y,
                            mode="lines",
                            name=cls["name"],
                            legendgroup=cls["name"],
                            line=dict(
                                color=cls["color"],
                                width=2.2,
                                shape="spline",
                                smoothing=0.8
                            ),
                            fill="tozeroy",
                            fillcolor=cls["fill"],
                            showlegend=(row == 1 and col == 1),
                            hovertemplate=(
                                f"{x_label}: %{{x:.2f}}"
                                "<br>Density: %{y:.4f}"
                                f"<extra>{cls['name']}</extra>"
                            )
                        ),
                        row=row,
                        col=col
                    )

                fig.add_vline(
                    x=current_values[x_col],
                    line=dict(color="black", width=2),
                    row=row,
                    col=col
                )

            # ------------------------------------------------
            # OFF-DIAGONAL: SCATTER
            # ------------------------------------------------
            else:
                for cls in classes:
                    subset = df.loc[df["Machine_failure"] == cls["value"]]

                    fig.add_trace(
                        go.Scattergl(
                            x=subset[x_col],
                            y=subset[y_col],
                            mode="markers",
                            name=cls["name"],
                            legendgroup=cls["name"],
                            marker=dict(
                                color=cls["color"],
                                size=3,
                                opacity=0.45
                            ),
                            showlegend=False,
                            hovertemplate=(
                                f"{x_label}: %{{x}}"
                                f"<br>{y_label}: %{{y}}"
                                f"<extra>{cls['name']}</extra>"
                            )
                        ),
                        row=row,
                        col=col
                    )

                fig.add_trace(
                    go.Scatter(
                        x=[current_values[x_col]],
                        y=[current_values[y_col]],
                        mode="markers",
                        name="Current machine",
                        marker=dict(
                            color="black",
                            size=9,
                            symbol="circle",
                            line=dict(color="white", width=1.4)
                        ),
                        showlegend=(row == 1 and col == 2),
                        hovertemplate=(
                            "<b>Current machine</b>"
                            f"<br>{x_label}: %{{x}}"
                            f"<br>{y_label}: %{{y}}"
                            "<extra></extra>"
                        )
                    ),
                    row=row,
                    col=col
                )

            # ------------------------------------------------
            # X AXIS FORMATTING
            # ------------------------------------------------
            x_title = x_label.replace(" ", "<br>", 1)
            fig.update_xaxes(
                range=[x_low, x_high],
                showgrid=False,
                zeroline=False,
                showline=False,
                ticks="outside" if row == n_features else "",
                ticklen=3,
                tickwidth=1,
                tickcolor="#8A8A8A",
                showticklabels=(row == n_features),
                nticks=4,
                tickfont=dict(
                    family="Arial, sans-serif",
                    size=10,
                    color="#202735"
                ),
                title_text=f"<b>{x_title}</b>" if row == n_features else None,
                title_font=dict(
                    family="Arial, sans-serif",
                    size=12,
                    color="#111827"
                ),
                title_standoff=10,
                automargin=True,
                row=row,
                col=col
            )

            # ------------------------------------------------
            # Y AXIS FORMATTING
            # ------------------------------------------------
            show_y_ticks = col == 1 and row != col
            fig.update_yaxes(
                range=[y_low, y_high] if row != col else None,
                showgrid=False,
                zeroline=False,
                showline=False,
                ticks="outside" if show_y_ticks else "",
                ticklen=3,
                tickwidth=1,
                tickcolor="#8A8A8A",
                showticklabels=show_y_ticks,
                nticks=4,
                tickfont=dict(
                    family="Arial, sans-serif",
                    size=10,
                    color="#202735"
                ),
                title_text=f"<b>{y_label}</b>" if col == 1 else None,
                title_font=dict(
                    family="Arial, sans-serif",
                    size=12,
                    color="#111827"
                ),
                title_standoff=8,
                automargin=True,
                row=row,
                col=col
            )

            # Domain coordinates keep the frame on the panel edges when zooming.
            fig.add_shape(
                type="rect",
                xref="x domain", yref="y domain",
                x0=0, x1=1, y0=0, y1=1,
                line=dict(color="#8A8A8A", width=1),
                fillcolor="rgba(0,0,0,0)",
                row=row, col=col
            )

    # --------------------------------------------------------
    # LAYOUT
    # --------------------------------------------------------
    fig.update_layout(
        height=1150,
        autosize=True,
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="closest",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#CBD5E1",
            borderwidth=1,
            font=dict(
                family="Arial, sans-serif",
                size=11,
                color="#111827"
            )
        ),
        margin=dict(
            l=64,
            r=20,
            t=70,
            b=64,
            pad=0
        )
    )

    return fig


# ============================================================
# SLIDER BOUNDS
# ============================================================

air_min, air_max = padded_slider_bounds(df["Air_temperature_K"])
proc_min, proc_max = padded_slider_bounds(df["Process_temperature_K"])
rpm_min, rpm_max = padded_slider_bounds(df["Rotational_speed_rpm"], floor_zero=True)
torque_min, torque_max = padded_slider_bounds(df["Torque_Nm"], floor_zero=True)
wear_min, wear_max = padded_slider_bounds(df["Tool_wear_min"], floor_zero=True)

air_min, air_max = round(air_min, 1), round(air_max, 1)
proc_min, proc_max = round(proc_min, 1), round(proc_max, 1)

rpm_min, rpm_max = int(math.floor(rpm_min)), int(math.ceil(rpm_max))
wear_min, wear_max = int(math.floor(wear_min)), int(math.ceil(wear_max))

torque_min, torque_max = round(float(torque_min), 1), round(float(torque_max), 1)


# ============================================================
# HEADER
# ============================================================

st.title("⚙️ Predictive Maintenance")
st.caption("Interactive machine condition assessment and on-demand failure prediction")


# ============================================================
# API HEALTH
# ============================================================

try:
    health_response = requests.get(f"{API_URL}/health", timeout=3)
    health_response.raise_for_status()
    health_data = health_response.json()

    if health_data.get("model_loaded"):
        st.success("Prediction API connected — model loaded")
    else:
        st.warning("API is reachable, but the model is not loaded.")
except requests.RequestException:
    st.error(f"Cannot connect to prediction API at {API_URL}")


# ============================================================
# SUMMARY METRICS
# ============================================================

m1, m2, m3 = st.columns(3)

m1.metric("Reference observations", f"{len(df):,}")
m2.metric("Observed failures", f"{int(df['Machine_failure'].sum()):,}")
m3.metric("Historical failure rate", f"{df['Machine_failure'].mean():.2%}")

st.divider()


# ============================================================
# SIDEBAR INPUTS
# ============================================================

st.sidebar.header("Machine operating conditions")

machine_type = st.sidebar.selectbox(
    "Machine Type",
    ["L", "M", "H"],
    index=["L", "M", "H"].index(df["Type"].mode().iloc[0])
)

air_temp = st.sidebar.slider(
    "Air temperature (K)",
    min_value=float(air_min),
    max_value=float(air_max),
    value=float(df["Air_temperature_K"].median()),
    step=0.1
)

process_temp = st.sidebar.slider(
    "Process temperature (K)",
    min_value=float(proc_min),
    max_value=float(proc_max),
    value=float(df["Process_temperature_K"].median()),
    step=0.1
)

rpm = st.sidebar.slider(
    "Rotational speed (rpm)",
    min_value=int(rpm_min),
    max_value=int(rpm_max),
    value=int(df["Rotational_speed_rpm"].median()),
    step=1
)

torque = st.sidebar.slider(
    "Torque (Nm)",
    min_value=float(torque_min),
    max_value=float(torque_max),
    value=float(df["Torque_Nm"].median()),
    step=0.1
)

wear = st.sidebar.slider(
    "Tool wear (min)",
    min_value=int(wear_min),
    max_value=int(wear_max),
    value=int(df["Tool_wear_min"].median()),
    step=1
)

st.sidebar.divider()

predict_clicked = st.sidebar.button(
    "Predict Failure Risk",
    type="primary",
    use_container_width=True
)


# ============================================================
# CURRENT MACHINE VALUES
# ============================================================

current_values = {
    "Air_temperature_K": float(air_temp),
    "Process_temperature_K": float(process_temp),
    "Rotational_speed_rpm": int(rpm),
    "Torque_Nm": float(torque),
    "Tool_wear_min": int(wear)
}

payload = {
    "Type": machine_type,
    "Air_temperature_K": float(air_temp),
    "Process_temperature_K": float(process_temp),
    "Rotational_speed_rpm": int(rpm),
    "Torque_Nm": float(torque),
    "Tool_wear_min": int(wear)
}


# ============================================================
# PREDICTION
# ============================================================

if predict_clicked:
    st.session_state.pop("prediction", None)

    try:
        response = requests.post(
            f"{API_URL}/predict",
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        st.session_state["prediction"] = {
            "payload": payload.copy(),
            "result": response.json()
        }

    except requests.RequestException as exc:
        st.error(f"Prediction request failed: {exc}")

        if exc.response is not None:
            st.code(exc.response.text)

prediction = st.session_state.get("prediction")

if prediction:
    if prediction["payload"] != payload:
        st.info(
            "Machine inputs have changed. "
            "Click Predict Failure Risk to update the prediction."
        )
    else:
        st.subheader("Prediction result")

        result = prediction["result"]
        probability = float(result["failure_probability"])
        predicted_failure = int(result["predicted_failure"])

        c1, c2 = st.columns(2)

        c1.metric("Failure probability", f"{probability:.4%}")

        if predicted_failure == 1:
            c2.error("Potential machine failure predicted")
        else:
            c2.success("No failure predicted")

        st.caption(
            "The classification uses the decision threshold configured "
            "in the deployed model."
        )


# ============================================================
# PAIR PLOT SECTION
# ============================================================

st.divider()

st.subheader("Machine Operating Conditions")

st.caption(
    f"Training dataset ({len(df):,} observations): "
    "Explore relationships between machine operating conditions. "
    "Blue = No failure | Red = Failure | Black dot = Current machine."
)

st.caption(
    "Diagonal curves show the normalized density distributions "
    "of the two failure classes in the training dataset."
)

st.caption(
    "All training observations are shown. "
    "Axes use the full data range, with small padding to keep the current machine visible."
)

# Frame the responsive chart element so its legend and axis titles stay inside.
st.html("""
    <style>
    .st-key-operating_conditions_chart {
        overflow-x: auto;
    }
    .st-key-operating_conditions_chart > [data-testid="stElementContainer"] {
        min-width: 36rem;
        box-sizing: border-box;
        border: 2px solid #5F5F5F;
    }
    </style>
""")
with st.container(key="operating_conditions_chart"):
    st.plotly_chart(
        build_pair_plot(df, current_values),
        use_container_width=True,
        config={
            "displaylogo": False,
            "responsive": True
        }
    )
