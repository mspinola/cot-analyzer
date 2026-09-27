"""The Commercial flow strip on the /analysis Positioning Index panel.

Store-free: the flow frame is built with cotmetrics' own `flows.leg_flow_frame`, the
call `CotIndexer.get_commercial_flow_data` makes, so nothing here is hand-made.
"""

import importlib
import sys

import numpy as np
import pandas as pd
from cotmetrics import constants as cm_const
from cotmetrics import flows

import components.flow_strip as fs
import components.plot_layout as layout_helpers
import components.plot_registry as registry
import viz_config
import viz_constants as vc
from components.plot_traces import COMM_LABEL, SML_LABEL

PALETTE = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
LEG = cm_const.COMM
N = 120


def _dates(n=N):
    return pd.date_range("2023-01-03", periods=n, freq="7D")


def _flow_frame(n=N, is_equity=False, retail="spec-like", seed=4):
    net = pd.Series(np.random.default_rng(seed).normal(0, 8_000, n).cumsum(),
                    index=_dates(n))
    out = flows.leg_flow_frame(net, LEG)
    out.index.name = cm_const.DATE
    out.attrs["flow_leg"] = "Commercial"
    out.attrs["is_equity"] = is_equity
    out.attrs["flow_roles"] = {"retail_behaves": retail} if retail else None
    return out


def _legacy_frame(index):
    rng = np.random.default_rng(9)
    df = pd.DataFrame(index=index)
    for col in registry.IDX_COLS:
        df[col] = rng.uniform(0, 100, len(index))
    df.iloc[:3, df.columns.get_loc(registry.IDX_COLS[0])] = np.nan  # a warm-up
    df[cm_const.CLOSING_PRICE] = 100 + np.cumsum(rng.normal(0, 1, len(index)))
    return df


def _index_panel(flow_df, with_flow=True):
    specs = registry.subplot_specs(["index"], show_price=True, num_cols=1)
    fig = layout_helpers.get_make_subplots_for_plots(1, 1, ["Positioning Index"], specs)
    legacy = _legacy_frame(flow_df.index)
    ctx = registry.PlotCtx(fig=fig, df=legacy, row=1, col=1, palette=PALETTE,
                           flow=flow_df if with_flow else None)
    return registry.REGISTRY["index"].build(ctx), legacy


def _strip(fig):
    got = [t for t in fig.data if t.type == "heatmap"]
    assert len(got) <= 1
    return got[0] if got else None


def _comm_line(fig):
    got = [t for t in fig.data if t.name == COMM_LABEL and t.type.startswith("scatter")
           and t.x is not None and len(t.x) and t.x[0] is not None]
    assert len(got) == 1
    return got[0]


def test_module_imports_without_the_data_layer():
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(fs)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


def test_panel_without_a_flow_frame_is_unchanged():
    fig, _ = _index_panel(_flow_frame(), with_flow=False)
    assert _strip(fig) is None
    assert list(fig.layout.yaxis.range) == [0, 100]
    assert _comm_line(fig).hovertemplate is None or "flow z" not in str(
        _comm_line(fig).hovertemplate)


def test_no_speculator_line_is_drawn():
    fig, _ = _index_panel(_flow_frame())
    assert not [t for t in fig.data if (t.name or "").startswith("Speculator")]


def test_strip_is_the_commercial_flow_z_below_the_index_zero():
    flow_df = _flow_frame()
    fig, _ = _index_panel(flow_df)
    strip = _strip(fig)
    assert strip.name == f"{COMM_LABEL} flow z" and strip.yaxis == "y"
    assert list(strip.y) == fs.STRIP_EDGES and max(strip.y) < 0
    z = flow_df[flows.flow_z_col(LEG)]
    assert [None if pd.isna(v) else v for v in strip.z[0]] == \
        [None if pd.isna(v) else v for v in z.tolist()]
    assert (strip.zmin, strip.zmax, strip.zmid) == (-3.0, 3.0, 0)
    assert strip.showscale is False and strip.hoverongaps is False and strip.opacity == 1
    assert list(fig.layout.yaxis.range) == fs.INDEX_RANGE
    assert list(fig.layout.yaxis.ticktext)[0] == "flow z"


def test_strip_scale_is_diverging_with_zero_near_the_background():
    stops = dict((round(p, 3), c) for p, c in fs.FLOW_COLORSCALE)
    assert stops[0.5] == fs.FLOW_ZERO

    def lum(hex_):
        h = hex_.lstrip("#")
        return sum(int(h[i:i + 2], 16) for i in (0, 2, 4))

    assert abs(lum(fs.FLOW_ZERO) - lum(vc.BACKGROUND_COLOR)) < 50
    assert lum(stops[1.0]) > lum(stops[0.667]) > lum(fs.FLOW_ZERO)
    assert lum(stops[0.0]) > lum(stops[0.333]) > lum(fs.FLOW_ZERO)
    blue, red = stops[1.0].lstrip("#"), stops[0.0].lstrip("#")
    assert int(blue[4:6], 16) > int(blue[0:2], 16)     # commercials buying is blue
    assert int(red[0:2], 16) > int(red[4:6], 16)       # selling is red


def test_strip_hover_names_the_leg_z_and_contracts():
    flow_df = _flow_frame()
    cells = _strip(_index_panel(flow_df)[0]).text[0]
    assert all(c is None for c in cells[:cm_const.FLOW_Z_MIN_PERIODS])
    last = cells[-1]
    z = flow_df[flows.flow_z_col(LEG)].iloc[-1]
    dnet = flow_df[flows.flow_col(LEG)].iloc[-1]
    assert last == (f"{COMM_LABEL} flow z {z:+.2f} vs own 52-week sd"
                    f"<br>net {dnet:+,.0f} contracts")


def test_commercial_line_hover_carries_the_weeks_flow():
    flow_df = _flow_frame()
    flow_df.loc[flow_df.index[-1], flows.flow_z_col(LEG)] = np.nan  # no readable z
    fig, legacy = _index_panel(flow_df)
    line = _comm_line(fig)
    assert line.hovertemplate == "%{text}"
    idx = legacy[registry.IDX_COLS[0]]
    z = flow_df[flows.flow_z_col(LEG)]
    dnet = flow_df[flows.flow_col(LEG)]
    seen = set()
    for i, text in enumerate(line.text):
        if pd.isna(idx.iloc[i]):
            assert text is None
            seen.add("warmup")
        elif pd.isna(z.iloc[i]):
            assert text == f"{idx.iloc[i]:.0f}"
            seen.add("index only")
        else:
            assert text == (f"{idx.iloc[i]:.0f} · flow z {z.iloc[i]:+.2f} "
                            f"(net {dnet.iloc[i]:+,.0f} contracts)")
            seen.add("flow")
    assert seen == {"warmup", "index only", "flow"}
    # The other two Legacy lines keep their own hover.
    others = [t for t in fig.data if t.name != COMM_LABEL and t.type.startswith("scatter")
              and t.hovertemplate == "%{text}"]
    assert not others


def test_note_says_what_is_market_specific_and_nothing_otherwise():
    fig, _ = _index_panel(_flow_frame(retail="neutral"))
    assert fig.layout.annotations[-1].text == (
        f"retail ({SML_LABEL}) does not move with price here")
    fig, _ = _index_panel(_flow_frame(is_equity=True, retail="neutral"))
    assert fig.layout.annotations[-1].text == (
        f"Equities: setups read {COMM_LABEL} only, retail ({SML_LABEL}) does not move "
        f"with price here")
    fig, _ = _index_panel(_flow_frame(retail=None))
    assert all("retail" not in (a.text or "") for a in fig.layout.annotations)


def test_copy_never_ranks_or_forecasts():
    banned = ("mover", "biggest move", "unusual", "next", "follow", "expect",
              "forecast", "predict", "bullish", "bearish", "likely", "edge", "signal")
    for kw in (dict(), dict(is_equity=True), dict(retail="cp-like")):
        fig, _ = _index_panel(_flow_frame(**kw))
        texts = [a.text for a in fig.layout.annotations]
        texts += [c for c in _strip(fig).text[0] if c]
        texts += [c for c in _comm_line(fig).text if c]
        for text in texts:
            assert not any(b in text.lower() for b in banned), text
            assert "—" not in text


def test_page_fetches_the_flow_only_for_a_raw_index_panel(monkeypatch):
    import dash
    from cotmetrics import models

    import components.controls as controls

    dash.Dash(__name__, use_pages=True, pages_folder="")
    import pages.analytics.analysis as page

    calls = []
    flow_df = _flow_frame()
    legacy = _legacy_frame(flow_df.index)

    class _Indexer:
        def get_symbols_data(self, asset, lookback, basis=None):
            return legacy

        def get_commercial_flow_data(self, asset):
            calls.append(asset)
            return flow_df

        def get_instrument_from_name(self, name):
            return None

        def is_equity(self, name):
            return False

    monkeypatch.setattr(page, "get_indexer", lambda: _Indexer())
    monkeypatch.setattr(controls, "lookback_weeks", lambda lookback, asset: 26)
    palette = sorted(viz_config.get_palette_names())[0]
    model = models.DEFAULT_MODEL.key

    def figure(out):
        graphs = [c for c in out.children if getattr(c, "figure", None) is not None] \
            if hasattr(out, "children") and isinstance(out.children, list) else [out]
        return next(g.figure for g in graphs if getattr(g, "figure", None) is not None)

    fig = figure(page.update_analysis_stack(palette, "Gold", "26", ["index"], "1", model))
    assert calls == ["Gold"]
    assert [t for t in fig.data if t.name == f"{COMM_LABEL} flow z"]

    calls.clear()
    fig = figure(page.update_analysis_stack(palette, "Gold", "26", ["index_oinorm"], "1",
                                            model))
    assert calls == []
    assert not [t for t in fig.data if t.type == "heatmap"]
