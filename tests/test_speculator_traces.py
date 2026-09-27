"""The Speculator series and flow strip on the /analysis Positioning Index panel.

Store-free: the speculator frame is built from a synthetic CFTC-shaped report through
cotmetrics' own `categories.build_category_frame` and `flows.speculator_frame`, the
calls `CotIndexer.get_speculator_data` makes, so nothing here is hand-made.
"""

import importlib
import sys

import numpy as np
import pandas as pd
import pytest
from cotmetrics import categories as cot_categories
from cotmetrics import constants as cm_const
from cotmetrics import flows

import components.plot_layout as layout_helpers
import components.plot_registry as registry
import components.speculator_traces as st
import viz_config
import viz_constants as vc
from components.plot_traces import LRG_LABEL, SML_LABEL

PALETTE = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
DISAGG = cot_categories.REPORT_DISAGG
TFF = cot_categories.REPORT_TFF
SPEC = cm_const.SPECULATOR


def _spec_frame(report=DISAGG, symbol="GC", n=160, seed=4, lookback=26):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-03", periods=n, freq="7D")
    raw = pd.DataFrame(index=idx)
    raw[cm_const.OPEN_INTEREST_XLS] = rng.integers(400_000, 600_000, n)
    for spec in cot_categories.categories_for(report):
        raw[spec.long_col] = 50_000 + np.cumsum(rng.normal(0, 3_000, n)).round()
        raw[spec.short_col] = 50_000 + np.cumsum(rng.normal(0, 3_000, n)).round()
    cat = cot_categories.build_category_frame(raw, report, lookback,
                                              lookback_header=f" {lookback}")
    return flows.speculator_frame(cat, report, symbol=symbol)


def _legacy_frame(index):
    rng = np.random.default_rng(9)
    df = pd.DataFrame(index=index)
    for col in registry.IDX_COLS:
        df[col] = rng.uniform(0, 100, len(index))
    df[cm_const.CLOSING_PRICE] = 100 + np.cumsum(rng.normal(0, 1, len(index)))
    return df


def _index_panel(spec_df, with_speculator=True):
    specs = registry.subplot_specs(["index"], show_price=True, num_cols=1)
    fig = layout_helpers.get_make_subplots_for_plots(1, 1, ["Positioning Index"], specs)
    ctx = registry.PlotCtx(fig=fig, df=_legacy_frame(spec_df.index), row=1, col=1,
                           palette=PALETTE, speculator=spec_df if with_speculator else None)
    return registry.REGISTRY["index"].build(ctx)


def _by_name(fig, name):
    got = [t for t in fig.data if t.name == name]
    assert len(got) == 1, (name, [t.name for t in fig.data])
    return got[0]


def test_module_imports_without_the_data_layer():
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(st)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


def test_panel_without_a_speculator_frame_is_unchanged():
    spec_df = _spec_frame()
    fig = _index_panel(spec_df, with_speculator=False)
    assert not [t for t in fig.data if t.type == "heatmap"]
    assert not [t for t in fig.data if (t.name or "").startswith("Speculator")]
    assert list(fig.layout.yaxis.range) == [0, 100]
    assert not fig.layout.annotations[1:]  # only the subplot title


@pytest.mark.parametrize("report,symbol,label", [
    (DISAGG, "GC", "Managed Money"),
    (DISAGG, "ZC", "Managed Money"),
    (TFF, "6E", "Asset Manager + Leveraged Funds"),
])
def test_speculator_line_is_the_measured_groups_index(report, symbol, label):
    spec_df = _spec_frame(report, symbol)
    fig = _index_panel(spec_df)
    line = _by_name(fig, f"Speculator ({label})")
    col = flows.index_col(SPEC, spec_df.attrs["lookback_header"])
    got, want = list(line.y), spec_df[col].tolist()
    assert all((pd.isna(a) and pd.isna(b)) or a == b for a, b in zip(got, want))
    assert line.line.color == PALETTE[vc.SPECULATOR_SLOT]
    assert line.yaxis == "y"                      # the index axis, not the price axis
    assert line.line.color not in PALETTE[:3]


def test_strip_is_the_flow_z_below_the_index_zero():
    spec_df = _spec_frame()
    fig = _index_panel(spec_df)
    strip = _by_name(fig, "Speculator flow z")
    assert strip.type == "heatmap" and strip.yaxis == "y"
    assert list(strip.y) == st.STRIP_EDGES and max(strip.y) < 0
    z = spec_df[flows.flow_z_col(SPEC)]
    assert [None if pd.isna(v) else v for v in strip.z[0]] == \
        [None if pd.isna(v) else v for v in z.tolist()]
    assert (strip.zmin, strip.zmax, strip.zmid) == (-3.0, 3.0, 0)
    assert strip.showscale is False and strip.hoverongaps is False
    assert strip.opacity == 1
    assert list(fig.layout.yaxis.range) == st.INDEX_RANGE
    assert list(fig.layout.yaxis.tickvals) == st.INDEX_TICKS
    assert list(fig.layout.yaxis.ticktext)[0] == "flow z"
    assert st.STRIP_EDGES[0] < st.INDEX_TICKS[0] < st.STRIP_EDGES[1]


def test_strip_scale_is_diverging_with_zero_near_the_background():
    stops = dict((round(p, 3), c) for p, c in st.FLOW_COLORSCALE)
    assert stops[0.5] == st.FLOW_ZERO

    def lum(hex_):
        h = hex_.lstrip("#")
        return sum(int(h[i:i + 2], 16) for i in (0, 2, 4))

    bg = lum(vc.BACKGROUND_COLOR)
    assert abs(lum(st.FLOW_ZERO) - bg) < 50            # near-zero reads as background
    assert lum(stops[1.0]) > lum(stops[0.667]) > lum(st.FLOW_ZERO)
    assert lum(stops[0.0]) > lum(stops[0.333]) > lum(st.FLOW_ZERO)
    blue, red = stops[1.0].lstrip("#"), stops[0.0].lstrip("#")
    assert int(blue[4:6], 16) > int(blue[0:2], 16)     # buying is blue
    assert int(red[0:2], 16) > int(red[4:6], 16)       # selling is red


def test_line_hover_carries_the_weeks_flow_beside_the_index():
    """Hovering the lines shows level and move together: the strip only reports
    when the cursor is on it."""
    spec_df = _spec_frame()
    # A week with an index but no readable z (a masked or zero-sd week): the hover
    # shows the index alone rather than a blank or a zero.
    spec_df.loc[spec_df.index[-1], flows.flow_z_col(SPEC)] = float("nan")
    line = _by_name(_index_panel(spec_df), "Speculator (Managed Money)")
    assert line.hovertemplate == "%{text}"
    idx = spec_df[flows.index_col(SPEC, spec_df.attrs["lookback_header"])]
    z = spec_df[flows.flow_z_col(SPEC)]
    dnet = spec_df[flows.flow_col(SPEC)]
    seen_flow = seen_index_only = False
    for i, text in enumerate(line.text):
        if pd.isna(idx.iloc[i]):
            assert text is None
            continue
        assert text.startswith(f"{idx.iloc[i]:.0f}")
        if pd.isna(z.iloc[i]):
            assert text == f"{idx.iloc[i]:.0f}"
            seen_index_only = True
        else:
            assert text == (f"{idx.iloc[i]:.0f} \u00b7 flow z {z.iloc[i]:+.2f} "
                            f"(net {dnet.iloc[i]:+,.0f} contracts)")
            seen_flow = True
    assert seen_flow and seen_index_only


def test_strip_hover_carries_z_and_net_contracts():
    spec_df = _spec_frame()
    strip = _by_name(_index_panel(spec_df), "Speculator flow z")
    cells = strip.text[0]
    assert all(c is None for c in cells[:cm_const.FLOW_Z_MIN_PERIODS])
    last = cells[-1]
    assert last.startswith("Speculator flow z ") and "vs own 52-week sd" in last
    assert "contracts (Managed Money)" in last


def test_note_names_the_speculator_and_how_retail_behaves():
    fig = _index_panel(_spec_frame(DISAGG, "ZC"))
    note = fig.layout.annotations[-1].text
    assert note == f"Speculator = Managed Money, retail ({SML_LABEL}) does not move with price here"
    assert len(note) <= 90
    fig = _index_panel(_spec_frame(TFF, "6E"))
    assert fig.layout.annotations[-1].text == (
        f"Speculator = Asset Manager + Leveraged Funds, retail ({SML_LABEL}) "
        f"moves with price here")


def test_no_speculator_role_draws_no_line_or_strip_and_says_what_stands_in():
    spec_df = _spec_frame(TFF, "ZT")
    fig = _index_panel(spec_df)
    assert not [t for t in fig.data if t.type == "heatmap"]
    assert not [t for t in fig.data if (t.name or "").startswith("Speculator")]
    assert list(fig.layout.yaxis.range) == [0, 100]
    note = fig.layout.annotations[-1].text
    assert note.startswith(f"No speculator role here; {LRG_LABEL} stands in")


def test_copy_never_ranks_or_forecasts():
    banned = ("mover", "biggest move", "unusual", "next", "follow", "expect",
              "forecast", "predict", "bullish", "bearish", "likely", "edge", "signal")
    for report, symbol in ((DISAGG, "GC"), (DISAGG, "ZC"), (TFF, "6E"), (TFF, "ZT")):
        fig = _index_panel(_spec_frame(report, symbol))
        texts = [a.text for a in fig.layout.annotations]
        texts += [c for t in fig.data if t.type == "heatmap" for c in t.text[0] if c]
        for text in texts:
            assert not any(b in text.lower() for b in banned), text
            assert "—" not in text


def test_page_fetches_the_speculator_only_for_a_raw_index_panel(monkeypatch):
    import dash
    from cotmetrics import models

    dash.Dash(__name__, use_pages=True, pages_folder="")
    import pages.analytics.analysis as page

    calls = []
    spec_df = _spec_frame()
    legacy = _legacy_frame(spec_df.index)

    class _Indexer:
        def get_symbols_data(self, asset, lookback, basis=None):
            return legacy

        def get_speculator_data(self, asset, lookback):
            calls.append((asset, lookback))
            return spec_df

        def get_instrument_from_name(self, name):
            return None

        def is_equity(self, name):
            return False

    import components.controls as controls

    monkeypatch.setattr(page, "get_indexer", lambda: _Indexer())
    # The Net Positions range band asks the indexer for the lookback in weeks.
    monkeypatch.setattr(controls, "lookback_weeks", lambda lookback, asset: 26)
    palette = sorted(viz_config.get_palette_names())[0]
    model = models.DEFAULT_MODEL.key

    out = page.update_analysis_stack(palette, "Gold", "26", ["index"], "1", model)
    graphs = [c for c in out.children if getattr(c, "figure", None) is not None] \
        if hasattr(out, "children") and isinstance(out.children, list) else [out]
    fig = next(g.figure for g in graphs if getattr(g, "figure", None) is not None)
    assert calls == [("Gold", "26")]
    assert [t for t in fig.data if t.name == "Speculator (Managed Money)"]
    assert [t for t in fig.data if t.name == "Speculator flow z"]

    # The % of OI index panel is a different basis: no speculator fetch, no line.
    calls.clear()
    out = page.update_analysis_stack(palette, "Gold", "26", ["index_oinorm"], "1", model)
    graphs = [c for c in out.children if getattr(c, "figure", None) is not None] \
        if hasattr(out, "children") and isinstance(out.children, list) else [out]
    fig = next(g.figure for g in graphs if getattr(g, "figure", None) is not None)
    assert calls == []
    assert not [t for t in fig.data if (t.name or "").startswith("Speculator")]
