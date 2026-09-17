"""The range band behind Net Positions, and the latest-print readout beside it.

The band is the COT index drawn in the units of the bars: one group's rolling
low-to-high over the lookback, shaded behind its own bars. What these pin is the
agreement with the index, since the reading "a bar at the band's top edge is index
100" is only true if both use the same window, and the two hazards a band like this
invites: a window that starts fresh at the left edge of the chart, and an axis
fitted to the bars that clips the band.

Store-free, like test_price_overlay: the frames are built here.
"""

import cotmetrics.constants as const
import cotmetrics.indicators as indicators
import numpy as np
import pandas as pd
import pytest
from plotly.subplots import make_subplots

import components.plot_traces as pt
import viz_config
from components import controls

PALETTE = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
WEEKS = 26


def _frame(n=120, seed=11):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-06", periods=n, freq="7D")
    df = pd.DataFrame(index=idx)
    for col in (const.COMM_NET, const.LARGE_NET, const.SMALL_NET):
        df[col] = rng.uniform(-50_000, 50_000, n).round()
    df[const.OPEN_INTEREST] = rng.uniform(100_000, 200_000, n)
    return df


def _figure(rows=1):
    return make_subplots(rows=rows, cols=1,
                         specs=[[{"secondary_y": True}] for _ in range(rows)])


def _net_pos(fig, df, **kw):
    return pt.get_net_pos_plot(fig, df, const.COMM_NET, const.LARGE_NET,
                               const.SMALL_NET, 1, 1, PALETTE, **kw)


def _band_traces(fig):
    return [t for t in fig.data if "range" in (t.name or "")]


def test_the_band_is_the_window_the_cot_index_is_scored_on():
    """`process_lookback` scores week idx over iloc[idx - weeks : idx + 1], so a
    bar at the band's top is index 100 and one at its bottom index 0. The same
    weeks + 1 rule the crowd board documents."""
    df = _frame()
    lo, hi = pt.net_range_band(df[const.COMM_NET], WEEKS)
    for idx in (WEEKS, 60, len(df) - 1):
        expected = indicators.calculate_cot_index(df[const.COMM_NET], idx - WEEKS, idx)
        got = round((df[const.COMM_NET].iloc[idx] - lo.iloc[idx])
                    / (hi.iloc[idx] - lo.iloc[idx]) * 100)
        assert got == expected
    top = df[const.COMM_NET] == hi
    assert top.any()
    assert (df[const.COMM_NET][top] == hi[top]).all()


def test_the_band_does_not_start_fresh_at_the_left_edge():
    """A trailing window, not one that widens from the first bar shown: rows with
    fewer than weeks + 1 observations behind them are NaN, and every later row
    spans exactly that many."""
    df = _frame()
    lo, hi = pt.net_range_band(df[const.COMM_NET], WEEKS)
    assert lo.iloc[:WEEKS].isna().all() and hi.iloc[:WEEKS].isna().all()
    assert lo.iloc[WEEKS:].notna().all()
    # The window is exactly weeks + 1 wide: the extreme at position 0 leaves the
    # band once weeks + 1 rows have passed.
    s = pd.Series(np.zeros(WEEKS * 3))
    s.iloc[0] = 1.0
    _, hi = pt.net_range_band(s, WEEKS)
    assert hi.iloc[WEEKS] == 1.0
    assert hi.iloc[WEEKS + 1] == 0.0


def test_the_band_is_drawn_behind_the_commercial_bars_and_follows_their_legend_entry():
    df = _frame()
    fig = _net_pos(_figure(), df, range_weeks=WEEKS)

    band = _band_traces(fig)
    assert len(band) == 2
    assert {t.legendgroup for t in band} == {"commercial"}
    assert all(t.hoverinfo == "skip" and t.showlegend is False for t in band)
    assert all(t.zorder < 0 for t in band)
    lo_trace, hi_trace = band
    assert hi_trace.fill == "tonexty" and lo_trace.fill is None
    lo, hi = pt.net_range_band(df[const.COMM_NET], WEEKS)
    np.testing.assert_allclose(np.asarray(hi_trace.y, dtype=float), hi.to_numpy())
    np.testing.assert_allclose(np.asarray(lo_trace.y, dtype=float), lo.to_numpy())


def test_no_band_without_a_lookback():
    """Aggregation passes None: a sum over markets with different custom lookbacks
    has no single window."""
    df = _frame()
    fig = _net_pos(_figure(), df)
    assert not _band_traces(fig)


def test_the_axis_covers_the_band_where_it_exceeds_the_visible_bars():
    """The band's edges at the left of the view carry bars from before it. Fitted to
    the visible bars alone the axis clipped them."""
    df = _frame(n=200)
    # A spike just outside the opening window drives the band above every visible bar.
    visible = pt.visible_weeks()
    spike_at = len(df) - visible - 5
    df.iloc[spike_at, df.columns.get_loc(const.COMM_NET)] = 500_000.0

    fig = _net_pos(_figure(), df, range_weeks=WEEKS)
    y_range = fig.layout.yaxis.range
    assert y_range[1] > 500_000


def test_the_readout_carries_each_groups_latest_print_and_names_the_band():
    df = _frame()
    df.iloc[-1, df.columns.get_loc(const.COMM_NET)] = -45_420.0
    df.iloc[-1, df.columns.get_loc(const.LARGE_NET)] = 25_890.0
    df.iloc[-1, df.columns.get_loc(const.SMALL_NET)] = 19_530.0
    fig = _net_pos(_figure(), df, range_weeks=WEEKS)

    readout = [a for a in fig.layout.annotations if a.name == "net_latest_readout"]
    assert len(readout) == 1
    text = readout[0].text
    assert "Commercial (45,420)" in text
    assert "Non-Commercial 25,890" in text
    assert "Non-Reportable 19,530" in text
    assert f"Commercial {WEEKS}-wk range" in text
    assert readout[0].xref == "x domain" and readout[0].yref == "y domain"


def test_the_readout_sits_on_its_own_panel_in_a_stack():
    df = _frame()
    fig = _figure(rows=2)
    fig = pt.get_index_plot(fig, df.assign(comms_idx=50.0, lrg_idx=50.0, sml_idx=50.0),
                            "comms_idx", "lrg_idx", "sml_idx", 1, 1, PALETTE,
                            show_price=False)
    fig = pt.get_net_pos_plot(fig, df, const.COMM_NET, const.LARGE_NET,
                              const.SMALL_NET, 2, 1, PALETTE, range_weeks=WEEKS)
    readout = [a for a in fig.layout.annotations if a.name == "net_latest_readout"]
    assert len(readout) == 1
    assert readout[0].yref == "y3 domain"


def test_the_band_does_not_disturb_the_legend_reconciliation():
    """The band traces are named for their group and window, never "Open Interest"
    or "Price", so the figure-wide legend pass still counts one of each."""
    df = _frame()
    fig = _net_pos(_figure(), df, range_weeks=WEEKS)
    pt.reconcile_legend_entries(fig, PALETTE)
    entries = [t for t in fig.data if t.showlegend]
    assert [t.name for t in entries].count("Open Interest") == 1
    assert not [t for t in entries if t.name == "Price"]


@pytest.mark.parametrize("value, text", [
    (25_890, "25,890"),
    (-45_420, "(45,420)"),
    (0, "0"),
    (-0.153, "(0.153)"),
    (0.2, "0.200"),
    (float("nan"), "n/a"),
    (None, "n/a"),
])
def test_accounting_style_formatting(value, text):
    assert pt.format_net(value) == text


class _Instrument:
    custom_lookback = 39


class _Indexer:
    def get_instrument_from_name(self, name):
        return _Instrument() if name == "Gold" else None


def test_lookback_weeks_names_the_window_the_control_means(monkeypatch):
    import cotmetrics.indexer as indexer_mod
    monkeypatch.setattr(indexer_mod, "get_indexer", lambda: _Indexer())
    assert controls.lookback_weeks("26", "Gold") == 26
    assert controls.lookback_weeks("52", "Gold") == 52
    assert controls.lookback_weeks("Custom", "Gold") == 39
    assert controls.lookback_weeks(None, "Gold") == 39
    assert controls.lookback_weeks("bogus", "Gold") == 39
    assert controls.lookback_weeks("Custom", "Nowhere") is None
