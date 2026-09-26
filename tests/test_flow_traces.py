"""The Flow view on /categories.

Store-free: frames are built from a synthetic CFTC-shaped report through cotmetrics'
own `categories.build_category_frame` and `flows.build_flow_frame`, the two calls
`CotIndexer.get_category_data` makes, so no flow column here is hand-made.
"""

import importlib
import sys

import numpy as np
import pandas as pd
import pytest
from cotmetrics import categories as cot_categories
from cotmetrics import constants as cm_const
from cotmetrics import flows

import components.category_traces as ct
import components.flow_traces as ft
import components.plot_layout as layout_helpers
import viz_config
import viz_constants as vc

PALETTE = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
DISAGG = cot_categories.REPORT_DISAGG
TFF = cot_categories.REPORT_TFF
LOOKBACK = 26
HEADER = " 26"
WARMUP = cm_const.FLOW_Z_MIN_PERIODS


def _frame(report=DISAGG, symbol="GC", n=200, seed=5):
    """What CotIndexer.get_category_data returns, minus the store."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-04", periods=n, freq="7D")
    raw = pd.DataFrame(index=idx)
    raw[cm_const.OPEN_INTEREST_XLS] = rng.integers(400_000, 600_000, n)
    for spec in cot_categories.categories_for(report):
        # Random walks, so the range index visits both ends of its window.
        raw[spec.long_col] = 50_000 + np.cumsum(rng.normal(0, 3_000, n)).round()
        raw[spec.short_col] = 50_000 + np.cumsum(rng.normal(0, 3_000, n)).round()
    cat = cot_categories.build_category_frame(raw, report, LOOKBACK,
                                              lookback_header=HEADER)
    flow = flows.build_flow_frame(cat, report, symbol=symbol)
    attrs = {**cat.attrs, **flow.attrs}
    df = pd.concat([cat, flow], axis=1)
    df[cm_const.CLOSING_PRICE] = 100 + np.cumsum(rng.normal(0, 1, n))
    df.attrs = attrs
    return df


def _series(df, report=DISAGG, keys=None):
    return ct.category_series(report, keys, PALETTE, frame=df)


def _view(df=None, report=DISAGG, keys=None):
    df = _frame(report) if df is None else df
    fig = layout_helpers.get_make_subplots_for_plots(
        3, 1, ft.flow_view_titles(df), ft.FLOW_VIEW_SPECS,
        row_heights=ft.FLOW_VIEW_ROW_HEIGHTS)
    return ft.build_flow_view(fig, df, _series(df, report, keys), HEADER, PALETTE), df


def _one(fig, name):
    got = [t for t in fig.data if t.name == name]
    assert len(got) == 1, (name, len(got))
    return got[0]


def _heatmap(fig):
    return _one(fig, "Weekly Flow")


def test_module_imports_without_the_data_layer():
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(ft)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


@pytest.mark.parametrize("report,symbol,labels", [
    (DISAGG, "GC", ["Commercials", "Managed Money", "Other Reportable",
                    "Non-Reportable"]),
    (DISAGG, "ZC", ["Producer/Merchant", "Swap Dealers", "Managed Money",
                    "Other Reportable", "Non-Reportable"]),
    (TFF, "ES", ["Dealer/Intermediary", "Asset Manager", "Leveraged Funds",
                 "Other Reportable", "Non-Reportable"]),
])
def test_rows_are_cotmetrics_rows_for_the_market(report, symbol, labels):
    df = _frame(report, symbol)
    fig, _ = _view(df, report)
    assert list(_heatmap(fig).y) == labels


def test_three_panels_price_flow_level_on_one_time_axis():
    fig, df = _view()
    price = [t for t in fig.data if t.name == "Price"]
    assert len(price) == 1 and price[0].yaxis == "y"
    assert _one(fig, "Open Interest").yaxis == "y2"
    assert _heatmap(fig).yaxis == "y3"
    lines = [t for t in fig.data if t.yaxis == "y4" and t.name]
    assert [t.name for t in lines] == list(_heatmap(fig).y)
    assert list(fig.layout.yaxis4.range) == [0, 100]
    matches = {fig.layout[k].matches for k in fig.layout if k.startswith("xaxis")}
    assert len(matches - {None}) == 1


def test_the_commercials_line_is_the_merged_rows_own_index():
    fig, df = _view()
    line = [t for t in fig.data if t.yaxis == "y4" and t.name == "Commercials"][0]
    col = cot_categories.index_col(flows.COMMERCIALS, HEADER)
    want = df[col].tolist()
    got = list(line.y)
    assert len(got) == len(want)
    assert all((pd.isna(a) and pd.isna(b)) or a == b for a, b in zip(got, want))


def test_markers_are_exactly_cotmetrics_decile_marks():
    fig, df = _view()
    marks = _one(fig, "Level marks")
    want = []
    for key, label, prefix, members in df.attrs["flow_rows"]:
        spec = flows.FlowRow(key, label, prefix, members)
        m = flows.level_marks(df[cot_categories.index_col(spec, HEADER)])
        for date, v in zip(df.index, m):
            if not pd.isna(v) and v != 0:
                want.append((date, label, "triangle-up" if v > 0 else "triangle-down"))
    assert want and {s for *_, s in want} == {"triangle-up", "triangle-down"}
    assert sorted(zip(marks.x, marks.y, marks.marker.symbol)) == sorted(want)
    assert marks.hoverinfo == "skip"
    assert marks.yaxis == "y3"


def test_index_panel_is_shaded_at_the_decile_cutoffs():
    fig, _ = _view()
    spans = sorted((s.y0, s.y1) for s in fig.layout.shapes if s.type == "rect")
    assert spans == [(0, 10), (90, 100)]
    assert all(s.yref == "y4" for s in fig.layout.shapes)


def test_heatmap_is_the_diverging_pair_clipped_with_no_gap_or_colorbar():
    hm = _heatmap(_view()[0])
    assert (hm.zmin, hm.zmax, hm.zmid) == (-3.0, 3.0, 0)
    stops = [c for _, c in hm.colorscale]
    assert stops[0] == vc.CATEGORY_DIVERGING_DOWN and stops[-1] == vc.CATEGORY_DIVERGING_UP
    assert stops[1] not in {PALETTE[i] for i in range(len(PALETTE))}
    assert hm.xgap == 0 and hm.showscale is False and hm.hoverongaps is False
    # The real z, not the clipped one, reaches the cells.
    fig, df = _view()
    hm = _heatmap(fig)
    first = df.attrs["flow_rows"][0]
    z = df[flows.flow_z_col(flows.FlowRow(*first))]
    assert [None if pd.isna(v) else v for v in hm.z[0]] == \
        [None if pd.isna(v) else v for v in z.tolist()]


def test_hover_carries_the_week_both_legs_the_level_and_the_state_label():
    fig, df = _view()
    hm = _heatmap(fig)
    assert all(c is None for row in hm.text for c in row[:WARMUP])
    mm = list(hm.y).index("Managed Money")
    text = hm.text[mm][-1]
    date = df.index[-1]
    assert f"positions as of {date.strftime('%A')} {date.strftime('%Y-%m-%d')}" in text
    assert "longs " in text and "shorts " in text and "vs own 52-week sd" in text
    state = df[cm_const.FLOW_STATE].iloc[-1]
    assert f"state {state}: a vocabulary label, not a signal" in text
    # The level line on a marked cell only.
    spec = cot_categories.categories_for(DISAGG)[2]
    marks = flows.level_marks(df[cot_categories.index_col(spec, HEADER)])
    for i, cell in enumerate(hm.text[mm]):
        if cell is None:
            continue
        marked = bool(not pd.isna(marks.iloc[i]) and marks.iloc[i] != 0)
        assert ("decile of the 26-week range" in cell) == marked


def test_checklist_keeps_commercials_while_either_member_is_ticked():
    keys = [s.key for s in cot_categories.categories_for(DISAGG)]
    fig, _ = _view(keys=[k for k in keys if k != "swap"])
    assert "Commercials" in list(_heatmap(fig).y)
    fig, _ = _view(keys=[k for k in keys if k not in ("swap", "producer_merchant")])
    assert "Commercials" not in list(_heatmap(fig).y)
    fig, _ = _view(keys=[k for k in keys if k != "managed_money"])
    assert "Managed Money" not in list(_heatmap(fig).y)
    assert not [t for t in fig.data if t.yaxis == "y4" and t.name == "Managed Money"]


def test_titles_name_the_window_the_scale_and_the_triangles():
    titles = ft.flow_view_titles(_frame())
    assert titles[0] == "Price and Open Interest"
    assert "own 52w sd" in titles[1] and "bottom decile" in titles[1]
    assert len(titles[1]) <= 64
    assert "▲" in titles[1] and "▼" in titles[1] and "26w range" in titles[1]
    assert titles[2] == "Positioning Index (26w range)"


def test_copy_never_ranks_or_forecasts():
    banned = ("mover", "biggest move", "unusual", "next", "follow", "expect",
              "forecast", "predict", "bullish", "bearish", "likely", "edge")
    fig, df = _view()
    texts = ft.flow_view_titles(df) + [c for row in _heatmap(fig).text for c in row if c]
    for text in texts:
        low = text.lower()
        assert not any(b in low for b in banned), text
        assert "signal" not in low.replace("not a signal", ""), text
        assert "—" not in text, text


def test_window_opens_on_104_weeks_and_52_on_a_phone():
    import flask

    fig, df = _view()
    ft.set_window(fig, df)
    assert pd.Timestamp(fig.layout.xaxis.range[0]) == df.index[len(df) - 104]
    app = flask.Flask("x")
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    with app.test_request_context(headers={"User-Agent": ua}):
        assert ft.flow_view_weeks() == 52


def test_page_renders_the_flow_view_and_locks_its_controls(monkeypatch):
    import dash

    dash.Dash(__name__, use_pages=True, pages_folder="")
    import pages.analytics.categories as page

    df = _frame()

    class _Indexer:
        def get_category_data(self, asset, report, lookback):
            return df

    monkeypatch.setattr(page, "get_indexer", lambda: _Indexer())
    keys = [s.key for s in cot_categories.categories_for(DISAGG)]
    palette = sorted(viz_config.get_palette_names())[0]
    # The plot selector is ignored: Net Positions alone still gives the view.
    graph = page.render_category_stack(palette, "Gold", DISAGG, keys, ["net_pos"],
                                       "26", "1", vc.LAYOUT_FLOW)
    titles = [a.text for a in graph.figure.layout.annotations]
    assert titles[:3] == ft.flow_view_titles(df)
    # Dates under the bottom panel only.
    assert graph.figure.layout.xaxis.showticklabels is False
    assert graph.figure.layout.xaxis3.showticklabels is not False
    assert page.lock_controls_for_flow_view(vc.LAYOUT_FLOW) == (True, True)
    assert page.lock_controls_for_flow_view(vc.LAYOUT_FACET) == (False, False)
