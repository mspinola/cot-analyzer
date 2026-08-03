"""The N-category panel builders, exercised against a real Plotly figure.

Store-free: these build their own frame and never touch the indexer. The first test
pins that property, because every other test in this file depends on it.
"""

import importlib
import sys

import numpy as np
import pandas as pd
import pytest
from cotmetrics import categories as cot_categories

import components.category_traces as ct
import components.plot_layout as layout_helpers
import viz_config

PALETTE = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
HEADER = " 52"


def test_module_imports_without_the_data_layer():
    """category_traces must not drag in the indexer.

    CI runs against an empty COTDATA_STORE, so a builder module that reaches for the
    store at import would take the whole test file down with it. This is also what
    lets the panels be tested at all: nothing else in this app tests a figure.
    """
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(ct)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


def _frame(report, n=80, seed=3):
    """A category frame shaped like CotIndexer.get_category_data returns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-05", periods=n, freq="7D")
    df = pd.DataFrame(index=idx)
    df["Open Interest"] = rng.integers(400_000, 600_000, n)
    df["Closing Price"] = rng.uniform(90, 110, n)
    for spec in cot_categories.categories_for(report):
        longs = rng.integers(10_000, 90_000, n)
        shorts = rng.integers(10_000, 90_000, n)
        df[cot_categories.long_col(spec)] = longs
        df[cot_categories.short_col(spec)] = shorts
        df[cot_categories.net_col(spec)] = longs - shorts
        df[cot_categories.pct_oi_col(spec)] = (longs - shorts) / 5_000
        df[cot_categories.index_col(spec, HEADER)] = rng.uniform(0, 100, n)
        df[cot_categories.zscore_col(spec, HEADER)] = rng.normal(0, 1, n)
        df[cot_categories.momentum_col(spec, HEADER)] = rng.normal(0, 10, n)
        if spec.spread_col:
            df[cot_categories.spread_col(spec)] = rng.integers(1_000, 9_000, n)
        if spec.traders_long_col:
            df[cot_categories.traders_long_col(spec)] = rng.integers(5, 90, n)
            df[cot_categories.traders_short_col(spec)] = rng.integers(5, 90, n)
    return df


def _figure(plot_id, show_price=True):
    specs = ct.subplot_specs([plot_id], show_price=show_price, num_cols=1)
    return layout_helpers.get_make_subplots_for_plots(1, 1, [plot_id], specs)


def _named_traces(fig):
    """Real traces only. Legend entries are empty scatters with x=[None]."""
    out = []
    for t in fig.data:
        x = getattr(t, "x", None)
        if x is not None and len(x) and x[0] is not None:
            out.append(t)
    return out


@pytest.mark.parametrize("report", list(cot_categories.REPORT_CHOICES))
@pytest.mark.parametrize("plot_id", list(ct.CATEGORY_SPECS))
def test_every_panel_draws_a_trace_per_category(report, plot_id):
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)
    fig = ct.build_panel(plot_id, _figure(plot_id), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=False)

    labels = {s.label for s in series}
    drawn = _named_traces(fig)
    assert drawn, plot_id
    # Every drawn series belongs to a selected category or is the price/OI overlay.
    assert {t.name for t in drawn} <= labels | {"Price", "Open Interest"}
    assert labels & {t.name for t in drawn}


@pytest.mark.parametrize("report", list(cot_categories.REPORT_CHOICES))
def test_selecting_fewer_categories_draws_fewer_traces(report):
    df = _frame(report)
    keys = [s.key for s in cot_categories.categories_for(report)]

    def count(selected):
        series = ct.category_series(report, selected, PALETTE, frame=df)
        fig = ct.build_panel("index", _figure("index"), df, series, HEADER, 1, 1,
                             PALETTE, showlegend=False)
        return len([t for t in _named_traces(fig) if t.name != "Price"])

    assert count(None) == len(keys)
    assert count({keys[0]}) == 1


def test_missing_category_columns_are_skipped_not_raised():
    """A frame short a category renders the rest, matching build_category_frame."""
    report = cot_categories.REPORT_TFF
    df = _frame(report)
    dealer = next(s for s in cot_categories.categories_for(report)
                  if s.key == "dealer")
    df = df.drop(columns=[c for c in df.columns if c.startswith(dealer.prefix)])

    series = ct.category_series(report, None, PALETTE, frame=df)
    assert "dealer" not in {s.key for s in series}

    fig = ct.build_panel("net_pos", _figure("net_pos"), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=False)
    assert "Dealer/Intermediary" not in {t.name for t in _named_traces(fig)}


def test_spreading_panel_omits_the_spreadless_categories():
    report = cot_categories.REPORT_DISAGG
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)
    fig = ct.build_panel("spread", _figure("spread"), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=False)

    names = {t.name for t in _named_traces(fig)} - {"Price"}
    assert names == {"Swap Dealers", "Managed Money", "Other Reportable"}


def test_gross_long_short_puts_shorts_below_the_axis():
    report = cot_categories.REPORT_DISAGG
    df = _frame(report)
    mm = next(s for s in cot_categories.categories_for(report)
              if s.key == "managed_money")
    series = ct.category_series(report, {"managed_money"}, PALETTE, frame=df)
    fig = ct.build_panel("long_short", _figure("long_short"), df, series, HEADER,
                         1, 1, PALETTE, showlegend=False)

    values = [np.asarray(t.y, dtype=float) for t in _named_traces(fig)
              if t.name == mm.label]
    assert any((v > 0).all() for v in values)
    assert any((v < 0).all() for v in values)


def test_net_pos_keeps_its_secondary_axis_without_price():
    """Net Positions puts Open Interest on the secondary axis, not price.

    So its cell needs that axis whether or not the price overlay is on. A boolean
    "needs secondary if show_price" would silently drop the OI series.
    """
    assert ct.uses_secondary_y("net_pos", show_price=False)
    assert not ct.uses_secondary_y("index", show_price=False)
    assert ct.uses_secondary_y("index", show_price=True)
    assert not ct.uses_secondary_y("traders", show_price=True)


def test_subplot_specs_grid_shape_matches_the_selection():
    grid = ct.subplot_specs(["net_pos", "index", "traders"], True, 2)
    assert len(grid) == 2 and all(len(r) == 2 for r in grid)
    assert grid[0][0]["secondary_y"] is True     # net_pos
    assert grid[1][0]["secondary_y"] is False    # traders
    assert grid[1][1]["secondary_y"] is False    # empty cell


def test_sanitize_selection_drops_unknown_ids():
    assert ct.sanitize_selection(["index", "no_such_plot"]) == ["index"]
    assert ct.sanitize_selection([]) == list(ct.DEFAULT_PLOTS)
    assert ct.sanitize_selection(None) == list(ct.DEFAULT_PLOTS)


def test_labels_for_covers_every_spec():
    assert set(ct.labels_for()) == set(ct.CATEGORY_SPECS)
    assert all(isinstance(v, str) and v for v in ct.labels_for().values())
