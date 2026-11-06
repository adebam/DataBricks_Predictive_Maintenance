"""Demo-only smoke checks; run with python -m pytest -q after pip install."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from app import (
    CHART_HEIGHT,
    _grouped_feature_options,
    _feature_batch_trend,
    _model_behavior_figure,
    _prediction_probability_figure,
    _prediction_volume_figure,
    _psi_figure,
    _psi_history_figure,
    _top_risk_figure,
    _boxplot_figure,
    _histogram_figure,
    render_page,
)
from demo_data import build_demo_data


@pytest.fixture(scope="module")
def sample():
    return build_demo_data()


def test_four_tab_rendering(monkeypatch, sample):
    import app as app_module
    from types import SimpleNamespace
    monkeypatch.setattr(app_module, "get_snapshot", lambda: {
        "data": sample, "loaded_at": "2026-11-06 12:00:00 UTC", "partial": False,
    })
    monkeypatch.setattr(app_module, "ctx", SimpleNamespace(triggered_id="nav-tabs"))
    tab_titles = {
        "overview": "Operational overview",
        "predictions": "Machine predictions",
        "drift": "Drift monitoring",
        "alerts": "Alert management",
    }
    for tab, heading in tab_titles.items():
        result, label, feedback = render_page(tab, 0)
        assert heading in str(result), f"Tab {tab} did not display its page"
        assert "Manual refresh" in label
        assert feedback == ""


def test_ingestion_axis_and_csv_legend(sample):
    fig = _feature_batch_trend(sample["current"], "Tool_wear_min")
    assert fig.layout.height == CHART_HEIGHT
    assert fig.layout.xaxis.type == "date"
    assert "ingestion" in fig.layout.xaxis.title.text.lower()
    assert len(fig.data) == 7  # P90, P10 shaded band, median line, four CSV marker traces
    assert fig.data[1].fill == "tonexty"
    assert fig.data[2].mode == "lines"
    assert fig.data[2].line.color == "#4ea1ff"
    assert any("batch_001.csv" in trace.name for trace in fig.data)
    assert all(trace.mode == "markers" for trace in fig.data[3:])
    for trace in fig.data:
        assert pd.to_datetime(trace.x, errors="coerce", utc=True).notna().all()


def test_no_silent_gold_timestamp_substitution(sample):
    without_ingest = sample["current"].drop(columns=["_ingest_timestamp"])
    without_ingest["_gold_processed_at"] = pd.Timestamp.now(tz="UTC")
    fig = _feature_batch_trend(without_ingest, "Tool_wear_min")
    assert len(fig.data) == 0
    assert "Ingestion timestamps are unavailable" in fig.layout.annotations[0].text


def test_common_chart_height(sample):
    figs = [
        _feature_batch_trend(sample["current"], "Torque_Nm"),
        _prediction_volume_figure(sample["predictions"]),
        _model_behavior_figure(sample["predictions"]),
        _psi_figure(sample["drift_rolling"]),
        _psi_history_figure(sample["drift_history"]),
        _prediction_probability_figure(sample["predictions"]),
        _top_risk_figure(sample["predictions"]),
        _boxplot_figure("Torque_Nm", {"Torque_Nm": {"reference": [1, 2, 3], "current": [2, 3, 4]}}),
        _histogram_figure("Torque_Nm", {"Torque_Nm": {"reference": [1, 2, 3], "current": [2, 3, 4]}}),
    ]
    assert all(fig.layout.height == CHART_HEIGHT for fig in figs)


def test_grouped_original_and_engineered_dropdowns(sample):
    options = _grouped_feature_options(list(sample["current"].select_dtypes("number").columns))
    groups = {option["value"]: option["label"].split(" · ")[0] for option in options}
    assert groups["Air_temperature_K"] == "Original"
    assert groups["Tool_wear_min"] == "Original"
    assert groups["Temperature_difference_K"] == "Engineered"
    assert groups["Power_wear"] == "Engineered"
    # Machine Type is categorical and should not appear on numeric selectors.
    assert "Type" not in groups
    assert list(groups.values()).index("Engineered") > list(groups.values()).index("Original")


def test_kde_curves_are_smooth_and_lightly_filled_with_common_grid(sample):
    payload = {"Torque_Nm": {
        "reference": sample["reference"]["Torque_Nm"].tolist(),
        "current": sample["current"]["Torque_Nm"].tolist(),
    }}
    fig = _histogram_figure("Torque_Nm", payload)
    assert len(fig.data) == 2
    assert all(trace.type == "scatter" and trace.mode == "lines" for trace in fig.data)
    assert all(trace.fill == "tozeroy" for trace in fig.data)
    assert [trace.fillcolor for trace in fig.data] == [
        "rgba(96,165,250,0.15)", "rgba(241,109,109,0.15)",
    ]
    assert all(trace.line.width >= 2 for trace in fig.data)
    assert len(fig.data[0].x) >= 250
    assert list(fig.data[0].x) == list(fig.data[1].x)
    assert all(y >= 0 for trace in fig.data for y in trace.y)


def test_kde_handles_single_valued_and_missing_features():
    fig = _histogram_figure("Tool_wear_min", {
        "Tool_wear_min": {"reference": [100] * 20, "current": [100] * 10},
    })
    assert len(fig.data) == 2
    assert all(max(trace.y) > 0 for trace in fig.data)
    empty = _histogram_figure("unavailable", {})
    assert len(empty.data) == 0
