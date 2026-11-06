"""Regression checks for the legible prediction time slider without a Dash server."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'app.py').read_text()


def extract(names, scope):
    tree = ast.parse(SRC)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []  # execute callback body without requiring Dash
    result = dict(scope)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'app.py'), 'exec'), result)
    return result


def test_slider_hides_unreadable_epoch_hour_tooltips_and_dense_ticks():
    fake_dcc = SimpleNamespace(RangeSlider=lambda **kwargs: kwargs)
    functions = extract(
        ['_prediction_time_range', '_prediction_time_slider'],
        {'pd': pd, 'dcc': fake_dcc},
    )
    predictions = pd.DataFrame({'prediction_timestamp': [
        '2026-11-05T15:30:00Z', '2026-11-06T21:15:00Z',
    ]})
    slider = functions['_prediction_time_slider'](predictions)
    assert slider['marks'] == {}
    assert 'tooltip' not in slider
    assert slider['value'] == [slider['min'], slider['max']]
    assert slider['max'] - slider['min'] == 30
    assert slider['step'] == 1


def test_selected_time_labels_and_histogram_count_update_together():
    functions = extract(
        ['_prediction_time_range', '_hour_label', '_predictions_in_time_range',
         '_figure_layout', '_empty_figure', '_prediction_probability_figure',
         'update_prediction_time_range'],
        {
            'pd': pd, 'px': px, 'go': go,
            'CHART_HEIGHT': 430, 'PANEL_BG': '#111c2e', 'TEXT': '#e8eef7',
            'MUTED': '#91a1b7',
            'BLUE': '#4ea1ff', 'RED': '#f16d6d',
        },
    )
    predictions = pd.DataFrame({
        'prediction_timestamp': ['2026-11-05T15:30:00Z',
                                 '2026-11-05T16:30:00Z',
                                 '2026-11-06T21:15:00Z'],
        'failure_probability': [0.01, 0.3, 0.9],
        'threshold': [0.004751] * 3,
    })
    functions['get_snapshot'] = lambda: {'data': {'predictions': predictions}}
    # Extracted functions refer to their own global namespace.
    callback = functions['update_prediction_time_range']
    callback.__globals__.update(functions)
    bounds = functions['_prediction_time_range'](predictions)
    figure, summary, start, end = callback([bounds[0], bounds[0] + 1])
    assert figure.layout.height == 430
    assert summary == '2 of 3 predictions in selected period'
    assert start == 'Nov 05 15:00 UTC'
    assert end == 'Nov 05 16:00 UTC'
    assert len(predictions) == 3


def test_layout_has_readable_labels_and_no_old_dense_mark_css():
    css = (ROOT / 'assets' / 'style.css').read_text()
    assert 'id="prediction-range-start"' in SRC
    assert 'id="prediction-range-end"' in SRC
    assert '.time-range-selected' in css
    assert '.time-range-date-value' in css
    assert '.time-range-endpoints' in css
    assert '.time-range-control .rc-slider-mark-text' not in css
