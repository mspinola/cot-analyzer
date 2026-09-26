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
from cotmetrics import flows

import components.category_traces as ct
import components.plot_layout as layout_helpers
import viz_config
import viz_constants as vc

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

    # The flow family, shaped as cotmetrics.flows.build_flow_frame shapes it, so a
    # builder reading a column the frame lacks fails here and not in production.
    # The warm-up is NaN for the first FLOW_Z_MIN_PERIODS rows, as the real z is.
    specs = cot_categories.categories_for(report)
    for i, spec in enumerate(specs):
        df[flows.flow_col(spec)] = rng.normal(0, 5000, n)
        df[flows.flow_long_col(spec)] = rng.normal(0, 5000, n)
        df[flows.flow_short_col(spec)] = rng.normal(0, 5000, n)
        df[flows.flow_z_col(spec)] = _warmup(rng.normal(0, 1, n))
        df[flows.flow_thin_col(spec)] = pd.array([i == THIN_SPEC_INDEX] * n,
                                                 dtype="boolean")
    df[flows.counterparty_flow_col()] = rng.normal(0, 5000, n)
    df[flows.counterparty_flow_z_col()] = _warmup(rng.normal(0, 1, n))
    df.attrs["report"] = report
    df.attrs["flow_roles"] = {
        "report": report,
        "symbol": "GC" if report == cot_categories.REPORT_DISAGG else "6E",
        "counterparty": tuple(s.key for s in specs[:2]),
        "opinion": tuple(s.key for s in specs[2:5]),
        "state_eligible": True,
        "source": "measured",
    }
    return df


# Which category the store-free frame flags as thin, by report order.
THIN_SPEC_INDEX = 1
WARMUP = 26


def _warmup(values):
    values = np.asarray(values, dtype=float)
    values[:WARMUP] = np.nan
    return values


def _is_blank(v):
    return v is None or (isinstance(v, float) and np.isnan(v))


def _counterparty_hover_label(report):
    """The composite's hover title: the bare tick label plus its summed members."""
    labels = {s.key: s.label for s in cot_categories.categories_for(report)}
    members = [labels[k] for k in _frame(report).attrs["flow_roles"]["counterparty"]]
    return f"Counterparty ({' + '.join(members)})"


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
    if plot_id == "flow":
        # One heatmap carries every category as a row, plus the counterparty. The
        # composite's tick label is the bare word; its members are in the hover.
        assert len(drawn) == 1 and drawn[0].type == "heatmap"
        assert list(drawn[0].y) == [s.label for s in series] + ["Counterparty"]
        assert list(drawn[0].x) == list(df.index)
        assert drawn[0].text[-1][-1].startswith(_counterparty_hover_label(report))
        return
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


def _yrange(fig, secondary=False):
    return (fig.layout.yaxis2 if secondary else fig.layout.yaxis).range


@pytest.mark.parametrize("plot_id", ["spread", "traders", "net_pos", "pct_oi",
                                     "zscore", "momentum", "long_short"])
def test_panels_fit_the_visible_window_not_all_history(plot_id):
    """The axis must fit what the chart opens on, not every point in the trace.

    Plotly autoranges y over the whole trace while get_update_xaxes_for_plots opens
    the chart on the last visible_weeks() only. Measured over the real 42-market
    universe, that left the worst spreading panel using 7% of its axis. The clientside
    autoscale only fires on a pan or zoom, so the first render, which is the view most
    people never touch, was the one that looked wrong.
    """
    report = cot_categories.REPORT_DISAGG
    df = _frame(report, n=400, seed=11)
    # A historical spike far outside the visible window: the axis must ignore it.
    spike = df.columns[df.columns.str.contains("Net Pos|Long|Short|Spread|Traders|Idx|Zscore|Move")]
    df.loc[df.index[:50], spike] = df[spike].abs().max().max() * 50

    series = ct.category_series(report, None, PALETTE, frame=df)
    fig = ct.build_panel(plot_id, _figure(plot_id), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=False)

    rng = _yrange(fig)
    assert rng is not None, f"{plot_id} left the axis autoranged"

    window = df.iloc[-ct.visible_weeks():]
    drawn = [np.asarray(t.y, dtype=float) for t in _named_traces(fig)
             if t.name not in ("Price", "Open Interest")]
    vis_lo = min(v[-len(window):].min() for v in drawn)
    vis_hi = max(v[-len(window):].max() for v in drawn)

    assert rng[0] <= vis_lo and rng[1] >= vis_hi, (
        f"{plot_id} clips visible data: range {rng} vs data [{vis_lo}, {vis_hi}]")
    span = rng[1] - rng[0]
    assert (vis_hi - vis_lo) / span >= 0.5, (
        f"{plot_id} visible data uses only {(vis_hi - vis_lo) / span:.0%} of its axis")


def test_zero_stays_in_range_only_where_a_zero_line_is_drawn():
    """Anchoring a trader-count axis at zero is what wasted its height.

    Counts and spreading never approach zero, so their axes should not reach for it.
    Net positions and gross long/short draw a zero line, so theirs must.
    """
    report = cot_categories.REPORT_DISAGG
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)

    def rng(pid):
        return _yrange(ct.build_panel(pid, _figure(pid), df, series, HEADER, 1, 1,
                                      PALETTE, showlegend=False))

    # Counts and contract totals cannot be negative, so padding must not invent
    # negative space. Whether the axis is tight enough is pinned by
    # test_panels_fit_the_visible_window_not_all_history, which measures utilisation.
    for pid in ("traders", "spread"):
        lo, _ = rng(pid)
        assert lo >= 0, f"{pid} axis goes negative ({lo}) for a non-negative quantity"

    for pid in ("net_pos", "long_short"):
        lo, hi = rng(pid)
        assert lo <= 0 <= hi, f"{pid} draws a zero line but zero is off-axis"


def test_index_panel_keeps_its_fixed_scale():
    """The 0-100 index is a bounded scale, so it must not be refitted to the data."""
    report = cot_categories.REPORT_TFF
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)
    fig = ct.build_panel("index", _figure("index"), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=False)
    assert tuple(_yrange(fig)) == (0, 100)


def _facet(df, series, plots, show_price=True):
    rows, cols = ct.facet_shape(plots, series, show_price)
    fig = layout_helpers.get_make_subplots_for_facets(
        rows, cols, ct.facet_titles(plots, series, show_price),
        ct.facet_specs(plots, series, show_price))
    return ct.build_facet_figure(fig, df, series, plots, HEADER, PALETTE,
                                 show_price=show_price), rows, cols


@pytest.mark.parametrize("report", list(cot_categories.REPORT_CHOICES))
def test_facet_gives_each_category_its_own_row(report):
    """Small multiples: a row per category, a column per panel, plus context rows.

    This is the answer to five series crossing on one axis, and the reason it works is
    that each row carries one series, so nothing occludes anything.
    """
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)
    plots = ["net_pos", "index", "flow"]
    fig, rows, cols = _facet(df, series, plots)

    # 5 categories + a price row + an open-interest row (net_pos is selected).
    assert rows == len(series) + 2
    assert cols == len(plots)

    per_cell = {}
    for t in fig.data:
        per_cell.setdefault(t.yaxis, []).append(t)
    assert all(len(v) == 1 for v in per_cell.values()), \
        "a faceted cell must hold exactly one series"


def test_facet_shares_one_y_scale_per_panel():
    """Rows must be comparable, so a panel's scale spans every category.

    Per-row autoscaling would make equal-looking wiggles mean different magnitudes,
    which is a lie by omission in a small-multiples grid.
    """
    report = cot_categories.REPORT_DISAGG
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)
    fig, rows, _ = _facet(df, series, ["net_pos"], show_price=False)

    ranges = {tuple(fig.layout[k].range) for k in fig.layout
              if k.startswith("yaxis") and fig.layout[k].range}
    # The category rows share one range; the open-interest row has its own.
    assert len(ranges) == 2, ranges


def test_facet_context_rows_replace_the_second_y_axis():
    """Price and open interest get their own rows rather than a second scale.

    Two scales on one plot align arbitrarily and imply a correlation the data does not
    contain, which is why the overlay's secondary axis does not survive faceting.
    """
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)

    fig, _, _ = _facet(df, series, ["net_pos"])
    names = {t.name for t in fig.data}
    assert {"Price", "Open Interest"} <= names
    assert not any(getattr(t, "yaxis", "y").endswith("2") and t.name == "Price"
                   for t in fig.data)

    # Open interest is a Net Positions companion, so it appears only alongside it.
    fig2, _, _ = _facet(df, series, ["index"])
    assert "Open Interest" not in {t.name for t in fig2.data}


def test_momentum_is_diverging_columns_when_faceted():
    """A signed change reads as a column on a baseline, not as a line.

    Colour encodes polarity here, so it comes from the validated diverging pair rather
    than from the category palette, which would say "this bar is Managed Money" when it
    means "this went down".
    """
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)
    fig, _, _ = _facet(df, series, ["momentum"], show_price=False)

    bars = [t for t in fig.data if t.type == "bar"]
    assert len(bars) == len(series)

    used = set()
    for t in bars:
        used.update(t.marker.color)
    assert used <= {vc.CATEGORY_DIVERGING_UP, vc.CATEGORY_DIVERGING_DOWN}
    assert vc.CATEGORY_DIVERGING_UP in used and vc.CATEGORY_DIVERGING_DOWN in used

    # Overlay keeps lines: five bar series on one axis would occlude each other.
    overlay = ct.build_panel("momentum", _figure("momentum"), df, series, HEADER,
                             1, 1, PALETTE, showlegend=False)
    assert not any(t.type == "bar" for t in overlay.data)


def test_momentum_columns_sit_on_a_zero_baseline():
    df = _frame(cot_categories.REPORT_TFF)
    series = ct.category_series(cot_categories.REPORT_TFF, None, PALETTE, frame=df)
    fig, _, _ = _facet(df, series, ["momentum"], show_price=False)
    lo, hi = fig.layout.yaxis.range
    assert lo <= 0 <= hi


def test_sanitize_selection_drops_unknown_ids():
    assert ct.sanitize_selection(["index", "no_such_plot"]) == ["index"]
    assert ct.sanitize_selection([]) == list(ct.DEFAULT_PLOTS)
    assert ct.sanitize_selection(None) == list(ct.DEFAULT_PLOTS)


def test_labels_for_covers_every_spec():
    assert set(ct.labels_for()) == set(ct.CATEGORY_SPECS)
    assert all(isinstance(v, str) and v for v in ct.labels_for().values())


def _by_name(fig, name):
    return [t for t in fig.data if t.name == name]


def test_price_overlay_starts_switched_off():
    """The green price line is opt-in where it rides a second axis.

    Both halves matter and they are different traces: the drawn overlay, and the
    empty scatter that puts Price in the legend. Plotly toggles a whole legendgroup
    from its entry, so an entry that disagreed with the traces it controls would
    render ungreyed over a panel drawing nothing, and the reader's first click would
    hide what was already hidden.
    """
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)
    fig = ct.build_panel("index", _figure("index"), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=True)

    price = _by_name(fig, "Price")
    assert price, "the overlay view still draws a price trace"
    assert all(t.visible == "legendonly" for t in price)

    # Every category series is unaffected: only price is opt-in.
    assert all(t.visible in (True, None)
               for t in _named_traces(fig) if t.name != "Price")


def test_faceted_price_row_is_not_an_overlay_and_still_draws():
    """Price as its own row keeps drawing.

    The rule is about a second scale on someone else's panel, not about price. A
    facet row has its own axis, and there is no legend in this view at all, so
    hiding it would remove the row with no way to ask for it back.
    """
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)
    fig, _, _ = _facet(df, series, ["index"])

    price = _by_name(fig, "Price")
    assert price
    assert all(t.visible in (True, None) for t in price)


def test_a_stack_led_by_net_positions_still_offers_price_in_the_legend():
    """The legend-owning panel need not be the one drawing price.

    Net Positions gives its second axis to open interest, so it advertises no Price
    entry; the panels after it still draw price overlays. With the overlay off by
    default, an entry-less figure would strand them: hidden, with nothing to click.
    """
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)
    plots = ["net_pos", "index"]

    specs = ct.subplot_specs(plots, show_price=True, num_cols=1)
    fig = layout_helpers.get_make_subplots_for_plots(2, 1, plots, specs)
    for i, plot_id in enumerate(plots):
        fig = ct.build_panel(plot_id, fig, df, series, HEADER, i + 1, 1, PALETTE,
                             show_price=True, showlegend=(i == 0))

    def entries():
        return [t for t in fig.data
                if t.name == "Price" and t.x is not None and len(t.x)
                and t.x[0] is None]

    assert not entries(), "the precondition this guards: no entry from panel one"
    fig = ct.ensure_price_legend_entry(fig, PALETTE)
    added = entries()
    assert len(added) == 1
    assert added[0].visible == "legendonly"
    assert added[0].legendgroup == "price"


def test_the_price_entry_is_not_duplicated_when_one_already_exists():
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)
    fig = ct.build_panel("index", _figure("index"), df, series, HEADER, 1, 1,
                         PALETTE, showlegend=True)

    before = len([t for t in fig.data if t.name == "Price"])
    ct.ensure_price_legend_entry(fig, PALETTE)
    assert len([t for t in fig.data if t.name == "Price"]) == before


def test_no_price_entry_is_invented_when_nothing_drew_one():
    """A stack of Net Positions alone draws no price at all, so an entry would
    control nothing."""
    df = _frame(cot_categories.REPORT_DISAGG)
    series = ct.category_series(cot_categories.REPORT_DISAGG, None, PALETTE, frame=df)
    fig = ct.build_panel("net_pos", _figure("net_pos"), df, series, HEADER, 1, 1,
                         PALETTE, show_price=True, showlegend=True)

    ct.ensure_price_legend_entry(fig, PALETTE)
    assert not [t for t in fig.data if t.name == "Price"]


# --- the weekly flow heatmap ------------------------------------------------------

def _flow_figure(report, selected=None, show_price=False, showlegend=False, df=None):
    df = _frame(report) if df is None else df
    series = ct.category_series(report, selected, PALETTE, frame=df)
    fig = ct.build_panel("flow", _figure("flow", show_price=show_price), df, series,
                         HEADER, 1, 1, PALETTE, show_price=show_price,
                         showlegend=showlegend)
    return fig, df, series


def _heatmap(fig):
    maps = [t for t in fig.data if t.type == "heatmap"]
    assert len(maps) == 1
    return maps[0]


@pytest.mark.parametrize("report", list(cot_categories.REPORT_CHOICES))
def test_flow_heatmap_rows_follow_report_order_and_end_with_the_counterparty(report):
    """Rows read top-down in checklist order, and the composite names its members.

    The members are per market, so a fixed "Commercials" label would be wrong on
    half the universe; the row has to say what was summed. It says so in the hover,
    not on the axis: the tick text sets the left margin every panel in the stack
    shares, and the full member label took a third of the figure width on silver.
    """
    fig, df, series = _flow_figure(report)
    hm = _heatmap(fig)
    assert list(hm.y) == [s.label for s in series] + ["Counterparty"]
    members = [s.label for s in cot_categories.categories_for(report)[:2]]
    composite = hm.text[-1][-1]
    assert composite.startswith(_counterparty_hover_label(report)), composite
    assert all(m in composite for m in members)
    assert not any(m in hm.y[-1] for m in members)
    # First cohort on top, the way the checklist lists them.
    assert fig.layout.yaxis.autorange == "reversed"
    assert fig.layout.yaxis.type == "category"


def test_flow_heatmap_always_draws_the_counterparty_row():
    """The other side is never off the page, whatever the checklist says."""
    report = cot_categories.REPORT_DISAGG
    keys = [s.key for s in cot_categories.categories_for(report)]
    fig, _, series = _flow_figure(report, selected={keys[2]})
    hm = _heatmap(fig)
    assert len(series) == 1
    assert len(hm.y) == 2
    assert hm.y[-1].startswith("Counterparty")

    # A frame without the composite draws the cohorts alone and does not raise.
    df = _frame(report).drop(columns=[flows.counterparty_flow_col(),
                                      flows.counterparty_flow_z_col()])
    fig, _, series = _flow_figure(report, selected={keys[2]}, df=df)
    hm = _heatmap(fig)
    assert list(hm.y) == [series[0].label]


def test_flow_heatmap_is_diverging_and_clipped():
    """Colour is polarity, so it comes from the validated pair, never a palette slot.

    Clipped for display only: the z in the hover is the metric, the paint saturates
    at three sigma so one outlier week cannot wash every ordinary week to grey.
    """
    fig, _, _ = _flow_figure(cot_categories.REPORT_DISAGG)
    hm = _heatmap(fig)
    assert (hm.zmin, hm.zmax, hm.zmid) == (-3, 3, 0)
    scale = [c.lower() for _, c in hm.colorscale]
    assert scale[0] == vc.CATEGORY_DIVERGING_DOWN.lower()
    assert scale[-1] == vc.CATEGORY_DIVERGING_UP.lower()
    # Every palette the page can select, with the sibling tints each one derives.
    # One known coincidence, older than this panel: the validated pair IS Solarized
    # cyan and orange (viz_constants spells the hex out), and the Solarized palette
    # carries that cyan in a slot, so under it the momentum columns and this scale
    # already share a hue with one cohort. That belongs to viz_constants, so the
    # check names it as the only palette allowed to collide rather than skipping it.
    collisions = {}
    for name in viz_config.get_palette_names():
        pal = viz_config.get_palette(name)
        identity = {c.lower() for c in pal} | {ct.sibling_color(c).lower() for c in pal}
        if identity & set(scale):
            collisions[name] = identity & set(scale)
    assert set(collisions) <= {"Solarized"}, \
        f"a polarity stop borrowed an identity colour: {collisions}"
    # The midpoint is a real grey composited over the plot background, not the
    # background itself: a dead band erases the runs the panel exists to show.
    assert scale[1] not in (vc.BACKGROUND_COLOR.lower(), "#000000")
    assert scale[1] == ct._composite_over(ct.DIM_TEXT, vc.BACKGROUND_COLOR).lower()
    assert ct._composite_over("rgba(255, 255, 255, 0.35)", "#1a1a1a") == "#6a6a6a"


def test_flow_heatmap_keeps_warmup_blank():
    """No reading is a blank cell, not a zero and not a hover."""
    fig, _, _ = _flow_figure(cot_categories.REPORT_TFF)
    hm = _heatmap(fig)
    assert hm.hoverongaps is False
    for z_row, t_row in zip(hm.z, hm.text):
        assert all(_is_blank(v) for v in z_row[:WARMUP])
        assert all(v is None for v in t_row[:WARMUP])
        assert not any(_is_blank(v) for v in z_row[WARMUP:])
        assert all(isinstance(v, str) for v in t_row[WARMUP:])


def test_flow_hover_names_both_legs_and_the_week():
    """The hover is pre-rendered: plotly 6.9 printed %{z:+.2f} raw under x unified.

    The weekday comes from the index, not a fixed "Tuesday": holiday weeks move the
    as-of day, and the fixture's Friday-dated index has to read "Friday" for the
    same reason gold's thirteen Mondays have to read "Monday".
    """
    fig, df, series = _flow_figure(cot_categories.REPORT_DISAGG)
    hm = _heatmap(fig)
    assert hm.hovertemplate == "%{text}<extra></extra>"
    cell = hm.text[0][-1]
    last = df.index[-1]
    for word in ("contracts", "longs", "shorts", "positions as of", "52-week",
                 series[0].label, last.strftime("%A"), last.strftime("%Y-%m-%d")):
        assert word in cell, cell
    assert "Tuesday" not in cell and "published" not in cell, cell
    # The composite is a sum of nets, so it has no legs to name.
    composite = hm.text[-1][-1]
    assert "longs" not in composite and "shorts" not in composite
    assert "contracts" in composite and "52-week" in composite
    # An explicit sign on every count, checked on the numbers themselves (the ISO
    # date carries a "-" of its own, so the cell as a whole proves nothing).
    net = cell.split("net ")[1].split(" contracts")[0]
    longs = cell.split("longs ")[1].split(",")[0]
    shorts = cell.split("shorts ")[1].split(")")[0]
    assert all(v[0] in "+-" for v in (net, longs, shorts)), cell
    assert composite.split("net ")[1][0] in "+-", composite


def test_flow_contracts_format_is_signed_with_thousands_separators():
    """The formatter, pinned directly: the fixture's draws can land under 1,000."""
    assert ct._contracts(1234567.0) == "+1,234,567"
    assert ct._contracts(-5.0) == "-5"
    assert ct._contracts(0.0) == "+0"
    assert ct._contracts(float("nan")) == "n/a"
    assert ct._contracts(pd.NA) == "n/a"


def test_flow_counterparty_names_only_the_members_present():
    """The label says what was summed, which is the present subset of the measured set.

    cotmetrics records the full measured member tuple in attrs but sums only the
    members whose columns the frame carries, so a market lacking a cohort must not
    claim to have summed it.
    """
    report = cot_categories.REPORT_DISAGG
    df = _frame(report)
    keep, drop = cot_categories.categories_for(report)[:2]
    assert drop.key in df.attrs["flow_roles"]["counterparty"]
    df = df.drop(columns=[c for c in df.columns if c.startswith(drop.prefix)])
    fig, _, series = _flow_figure(report, df=df)
    assert drop.label not in {s.label for s in series}
    hm = _heatmap(fig)
    assert hm.y[-1] == "Counterparty"
    composite = hm.text[-1][-1]
    assert composite.startswith(f"Counterparty ({keep.label})<br>"), composite
    assert drop.label not in composite
    # A frame with no roles at all has no members to name.
    bare = _frame(report)
    bare.attrs = {}
    assert ct._counterparty_label(bare) == "Counterparty"


def test_flow_hover_marks_thin_cells():
    fig, _, series = _flow_figure(cot_categories.REPORT_DISAGG)
    hm = _heatmap(fig)
    thin_row = [i for i, s in enumerate(series)
                if s.key == cot_categories.categories_for(
                    cot_categories.REPORT_DISAGG)[THIN_SPEC_INDEX].key][0]
    assert "thin" in hm.text[thin_row][-1]
    assert "read the count" in hm.text[thin_row][-1]
    for i, row in enumerate(hm.text):
        if i != thin_row:
            assert "thin" not in row[-1]


def test_flow_heatmap_selecting_fewer_categories_drops_rows():
    report = cot_categories.REPORT_TFF
    keys = [s.key for s in cot_categories.categories_for(report)]
    full = _heatmap(_flow_figure(report)[0])
    two = _heatmap(_flow_figure(report, selected=set(keys[:2]))[0])
    assert len(full.y) == len(keys) + 1
    assert len(two.y) == 3
    assert list(two.y)[:2] == list(full.y)[:2]


def test_flow_heatmap_skips_a_category_missing_flow_columns():
    report = cot_categories.REPORT_DISAGG
    df = _frame(report)
    swap = next(s for s in cot_categories.categories_for(report) if s.key == "swap")
    flow_family = ("Flow", "dNet", "dLong", "dShort")
    df = df.drop(columns=[c for c in df.columns if c.startswith(swap.prefix)
                          and any(f in c for f in flow_family)])
    fig, _, series = _flow_figure(report, df=df)
    hm = _heatmap(fig)
    assert swap.label in {s.label for s in series}
    assert swap.label not in hm.y
    assert len(hm.y) == len(series)  # four cohorts plus the counterparty


@pytest.mark.parametrize("report", list(cot_categories.REPORT_CHOICES))
def test_flow_facet_is_one_row_heatmap_per_category(report):
    """In small multiples each cell is a one-row heatmap; the composite is not a row."""
    df = _frame(report)
    series = ct.category_series(report, None, PALETTE, frame=df)
    fig, rows, cols = _facet(df, series, ["flow"], show_price=False)
    maps = [t for t in fig.data if t.type == "heatmap"]
    assert len(maps) == len(series)
    assert [list(m.y) for m in maps] == [[s.label] for s in series]
    assert not any("Counterparty" in label for m in maps for label in m.y)
    assert all(m.showscale is False for m in maps)
    # The cell is a fraction of the figure, about 2 px a week, so no gap; and the
    # cohort is named once, by the axis title label_axis sets, not by a tick too.
    assert all(m.xgap == 0 for m in maps)
    for m in maps:
        axis = fig.layout["yaxis" + m.yaxis[1:]]
        assert axis.showticklabels is False
        assert axis.title.text in {s.label for s in series}


def test_flow_heatmap_is_denser_on_a_phone_and_still_names_the_members():
    """At phone width the gap goes; the labels do not change, and the hover keeps the
    members, because the reader rule (the other side is never off the page) means
    nothing when the other side is unnamed.
    """
    import flask

    report = cot_categories.REPORT_DISAGG
    desktop_fig = _flow_figure(report)[0]
    desktop = _heatmap(desktop_fig)
    assert desktop.xgap == 1
    assert desktop_fig.layout.yaxis.showticklabels is not False
    app = flask.Flask("x")
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    with app.test_request_context(headers={"User-Agent": ua}):
        fig, _, series = _flow_figure(report)
    phone = _heatmap(fig)
    assert phone.xgap == 0
    assert list(phone.y) == list(desktop.y) == [s.label for s in series] + ["Counterparty"]
    assert phone.text[-1][-1].startswith(_counterparty_hover_label(report))
    assert fig.layout.yaxis.showticklabels is not False


def test_flow_panel_has_no_secondary_axis_and_states_its_window():
    assert not ct.uses_secondary_y("flow", True)
    assert not ct.uses_secondary_y("flow", False)
    assert "52" in ct.labels_for()["flow"]
    assert list(ct.CATEGORY_SPECS)[-1] == "flow"
    assert "flow" not in ct.DEFAULT_PLOTS


def test_flow_copy_never_says_mover():
    """The Home board ranks index-point changes of the Legacy Commercial leg.

    A flow z is contracts against a cohort's own history, a different quantity, so
    the panel's copy must never borrow the board's ranking words.
    """
    banned = ("mover", "biggest move", "unusual")
    fig, _, _ = _flow_figure(cot_categories.REPORT_DISAGG)
    hm = _heatmap(fig)
    texts = [ct.labels_for()["flow"], hm.name]
    texts += [c for row in hm.text for c in row if c]
    texts += [f.__doc__ or "" for f in (ct.get_category_flow_heatmap,
                                         ct.get_category_flow_row, ct._flow_rows,
                                         ct._flow_hover_text, ct._counterparty_label)]
    for text in texts:
        low = text.lower()
        assert not any(b in low for b in banned), text


def test_flow_heatmap_has_no_colorbar_and_no_price():
    fig, _, series = _flow_figure(cot_categories.REPORT_DISAGG, show_price=True,
                                  showlegend=True)
    hm = _heatmap(fig)
    assert hm.showscale is False
    assert not [t for t in fig.data if t.name == "Price"]
    # The stack's legend still carries the categories when this panel leads it.
    entries = {t.name for t in fig.data if t.x is not None and len(t.x)
               and t.x[0] is None}
    assert entries == {s.label for s in series}
