"""Contract tests for v2.6 charts, no Dash web-server dependency required."""
from pathlib import Path
import ast

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]


def extract(names, env):
    tree = ast.parse((ROOT / 'app.py').read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    scope = dict(env)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'app.py'), 'exec'), scope)
    return scope


colors = dict(APP_BG='#0b1220', PANEL_BG='#111c2e', TEXT='#e8eef7', MUTED='#91a1b7',
              BLUE='#4ea1ff', GREEN='#42c59a', AMBER='#ffbd69', RED='#f16d6d',
              CHART_HEIGHT=430, np=np, pd=pd, go=go, px=px)
helpers = extract([
    '_figure_layout', '_empty_figure', '_latest_per_feature',
    '_prediction_time_groups', '_prediction_volume_figure',
    '_model_behavior_figure', '_psi_history_figure',
    '_prediction_time_range', '_hour_label', '_predictions_in_time_range',
    '_prediction_probability_figure',
], colors)


def test_log_and_linear_volume_preserve_data_and_time_axis():
    data = pd.DataFrame({
        'prediction_timestamp': pd.to_datetime([
            '2026-10-31 23:30:00Z'] * 2000 +
            ['2026-11-02 16:01:00Z'] * 100 +
            ['2026-11-03 01:15:00Z'] * 100,
            utc=True,
        ),
        'predicted_failure': [1] * 90 + [0] * 1910 + [1] * 200,
        'failure_probability': [0.01] * 2200,
    })
    for scale, axis_type in [('log', 'log'), ('linear', 'linear')]:
        figure = helpers['_prediction_volume_figure'](data, scale)
        assert figure.layout.yaxis.type == axis_type
        assert figure.layout.height == 430
        assert figure.data[0].y.tolist() == [2000, 100, 100]
        assert figure.data[1].y.tolist() == [90, 100, 100]
    behavior = helpers['_model_behavior_figure'](data)
    assert behavior.data[0].y.tolist() == [4.5, 100.0, 100.0]
    assert [list(row) for row in behavior.data[0].customdata] == [
        [2000, 90], [100, 100], [100, 100]
    ]


def test_slider_filters_hour_bins_without_affecting_original_data():
    data = pd.DataFrame({
        'prediction_timestamp': pd.to_datetime([
            '2026-11-01 00:05Z', '2026-11-01 00:50Z',
            '2026-11-01 02:15Z', '2026-11-01 03:20Z'], utc=True),
        'failure_probability': [0.1, 0.2, 0.5, 0.99],
        'predicted_failure': [0, 0, 1, 1],
        'threshold': [0.004751] * 4,
    })
    start, end = helpers['_prediction_time_range'](data)
    assert end - start == 3
    subset = helpers['_predictions_in_time_range'](data, [start, start + 2])
    assert len(subset) == 3
    assert len(data) == 4
    assert subset['failure_probability'].tolist() == [0.1, 0.2, 0.5]
    assert helpers['_prediction_probability_figure'](subset).layout.height == 430
    assert len(helpers['_predictions_in_time_range'](data, [start, end])) == 4
    assert helpers['_hour_label'](start).startswith('Nov 01')


def test_seven_significant_history_lines_and_dynamic_selection():
    rows = []
    for feature_idx in range(11):
        for t, psi in [('2026-11-01T00:00:00Z', 0.03),
                       ('2026-11-03T00:00:00Z', 0.26 if feature_idx < 7 else 0.17)]:
            rows.append(dict(feature=f'F{feature_idx}', calculated_at=t, psi=psi))
    data = pd.DataFrame(rows)
    figure = helpers['_psi_history_figure'](data)
    assert len(figure.data) == 7
    assert set(t.name for t in figure.data) == set(f'F{i}' for i in range(7))
    assert '7 features' in figure.layout.title.text
    last = data['calculated_at'] == '2026-11-03T00:00:00Z'
    data.loc[last, 'psi'] = 0.01
    no_drift = helpers['_psi_history_figure'](data)
    assert len(no_drift.data) == 0
    assert 'No features' in no_drift.layout.annotations[0].text


def test_controls_do_not_query_sql_directly():
    app_src = (ROOT / 'app.py').read_text()
    for name in ['update_volume_scale', 'update_prediction_time_range',
                 'reset_prediction_time_range']:
        fn = next(n for n in ast.parse(app_src).body
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        fn_src = ast.get_source_segment(app_src, fn)
        assert 'query_df' not in fn_src
        assert 'refresh_snapshot' not in fn_src
    assert 'prediction-time-range' in app_src
    assert 'prediction-range-reset' in app_src
    assert 'prediction-volume-scale' in app_src
