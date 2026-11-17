"""The registry has to reproduce what the pages did before it existed.

The expected values below are written out as literals on purpose, snapshotted from the
four pages as they were before the registry landed. Deriving them from the registry
would make every assertion here tautological: the point is to pin the behaviour that
shipped, so a later edit to a spec cannot quietly move a panel onto a different axis
or change which panels respond to the basis control.
"""

import cotmetrics.constants as const
import pytest

import viz_constants as vc
from components import plot_registry as reg

# --- what the pages declared before the registry --------------------------------

# viz_constants.BASIS_AWARE_PLOTS
EXPECTED_BASIS_AWARE = {"net_pos", "index", "zscore", "momentum", "spearman"}

# viz_constants.BASIS_INVARIANT_NOTE
EXPECTED_INVARIANT_NOTE = {
    "oi_pct": "already normalized by OI",
    "willco": "already normalized by OI",
    "category_net": "trader categories are in raw contracts",
    "open_interest": "not a positioning metric",
    "max_pain": "not a COT metric",
    "max_pain_historical": "not a COT metric",
}

# plot_helpers.BASIS_OVERLAY_SPEC
EXPECTED_OVERLAY = {
    "index": ("comms_idx", "Index", [0, 100], False),
    "zscore": ("comms_zscore", "Z-Score", None, True),
    "spearman": ("comms_spearman", "Correlation", [-1, 1], True),
    "momentum": (const.COMM_MOMENTUM, vc.MOMENTUM_LABEL, None, True),
}

# The `has_secondary` list each page kept inline, as (page, show_price, {ids}).
# OI Alignment and Analysis always draw price; Aggregation never does. net_pos was in
# every set, Aggregation's included, while it carried Open Interest on a second axis;
# it left them when Open Interest moved to a panel of its own.
EXPECTED_SECONDARY = [
    ("oi_alignment", True, {"macd", "willco", "index", "momentum", "zscore",
                            "oi_pct", "lrg_sentiment", "max_pain_historical"}),
    ("analysis", True, {"price_candles", "macd", "willco", "index", "momentum",
                        "zscore", "oi_pct", "spearman", "lrg_sentiment",
                        "max_pain_historical"}),
    ("analysis-grid", True, {"oi_pct", "willco", "spearman", "index", "zscore",
                             "momentum", "max_pain_historical"}),
    ("aggregation", False, set()),
]

# Panels that must never take a second axis, on any page, price drawn or not.
ONE_AXIS = {"net_pos", "open_interest", "category_net"}

ALL_IDS = set(reg.REGISTRY)


def test_basis_aware_matches_shipped_set():
    assert reg.BASIS_AWARE_PLOTS == EXPECTED_BASIS_AWARE


def test_invariant_notes_match_shipped():
    assert reg.BASIS_INVARIANT_NOTE == EXPECTED_INVARIANT_NOTE


def test_overlay_spec_matches_shipped():
    assert reg.BASIS_OVERLAY_SPEC == EXPECTED_OVERLAY


# The cross-checks against viz_constants.BASIS_AWARE_PLOTS and BASIS_INVARIANT_NOTE
# lived here while both copies were live. All four pages now read the registry and the
# originals are gone, so the snapshots above are the only remaining record of what
# shipped, which is what they were written to be.


@pytest.mark.parametrize("page,show_price,expected", EXPECTED_SECONDARY,
                         ids=[p for p, _, _ in EXPECTED_SECONDARY])
def test_secondary_axis_matches_shipped(page, show_price, expected):
    """Every id resolves to the axis the page gave it before the registry."""
    got = {i for i in ALL_IDS if reg.uses_secondary_y(i, show_price)}
    # A page only ever asked about the panels it offered, so compare on that subset.
    assert got & expected == expected, f"{page}: lost a secondary axis"
    assert not (expected - got), f"{page}: {expected - got} should use secondary_y"


@pytest.mark.parametrize("show_price", [True, False])
def test_the_net_and_open_interest_panels_take_one_axis(show_price):
    assert not {i for i in ONE_AXIS if reg.uses_secondary_y(i, show_price)}


def test_overlay_implies_basis_aware():
    """Drawing both bases at once is meaningless for a panel the basis cannot move."""
    for pid in reg.BASIS_OVERLAY_SPEC:
        assert reg.REGISTRY[pid].basis_aware, f"{pid} overlays but is not basis-aware"


def test_basis_aware_and_invariant_are_disjoint():
    assert not (reg.BASIS_AWARE_PLOTS & set(reg.BASIS_INVARIANT_NOTE))


def test_every_spec_is_buildable():
    for pid, spec in reg.REGISTRY.items():
        assert callable(spec.build), f"{pid} has no builder"
        assert spec.label, f"{pid} has no label"
        assert spec.secondary_y in (reg.SECONDARY_NEVER, reg.SECONDARY_WITH_PRICE,
                                    reg.SECONDARY_ALWAYS)


def test_default_off_panels_are_real_and_options_fed():
    """The set the stack pages exclude from their default selection. Every member
    must exist in the registry (a typo here silently defaults a panel back on).
    Two qualify, for the two reasons the comment on DEFAULT_OFF_PLOTS gives: the
    one options-proxy panel whose history is not yet trustworthy, and the z-score,
    which restates the Positioning Index. The set is pinned so a third cannot join
    without that comment being extended."""
    assert reg.DEFAULT_OFF_PLOTS <= set(reg.REGISTRY)
    assert reg.DEFAULT_OFF_PLOTS == {"max_pain_historical", "zscore"}
    options_fed = {p for p in reg.DEFAULT_OFF_PLOTS if reg.REGISTRY[p].needs_asset}
    assert options_fed == {"max_pain_historical"}


def test_sanitize_selection_drops_retired_ids():
    """A session-persisted selection naming a retired panel must not reach the grid."""
    assert reg.sanitize_selection(["index", "synthesis", "willco"], ALL_IDS) == \
        ["index", "willco"]
    assert reg.sanitize_selection(None, ALL_IDS) == []
    assert reg.sanitize_selection([], ALL_IDS) == []


def test_subplot_specs_shape_and_padding():
    grid = reg.subplot_specs(["index", "willco", "macd"], show_price=True, num_cols=2)
    assert len(grid) == 2 and all(len(r) == 2 for r in grid)
    assert grid[0][0] == {"secondary_y": True}
    assert grid[1][1] is None  # trailing empty cell


def test_labels_for_respects_overrides():
    got = reg.labels_for(["net_pos", "index"],
                         overrides={"net_pos": "Net Positions (Sum)"})
    assert got == {"net_pos": "Net Positions (Sum)",
                   "index": "Positioning Index"}


@pytest.mark.parametrize("page,list_name", [
    ("oi_alignment", "PLOT_IDS"),
    ("analysis", "PLOT_IDS"),
    ("analysis", "GRID_PLOT_IDS"),
    ("aggregation", "PLOT_IDS"),
])
def test_pages_only_reference_known_plots(page, list_name):
    """Catches a page offering an id the registry never learned about.

    Read from source rather than imported: a page builds its asset dropdowns at import
    time, which boots the indexer and wants a populated data store. CI runs against an
    empty one, so importing here would be slow and prove nothing about plot ids.

    Every page now declares its offering as a named id list and takes labels from
    the registry; analysis declares two (the panel stack's and the market grid's,
    the latter formerly the /graphs page).
    """
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    text = (src / "pages" / "analytics" / f"{page}.py").read_text()

    block = re.search(rf'^{list_name}\s*=\s*\[(.*?)\]', text, re.S | re.M)
    assert block, f"no {list_name} list in {page}.py"
    ids = set(re.findall(r'"([a-z_]+)"', block.group(1)))

    assert ids, f"no plot ids parsed from {page}.py"
    assert ids <= ALL_IDS, f"{page} offers unknown plots: {sorted(ids - ALL_IDS)}"


# ── palette slots ─────────────────────────────────────────────────────────────

def test_every_palette_fills_every_slot():
    """A page indexes `palette[n]` against viz_config.PALETTE_SLOTS, so a palette short
    of a slot is an IndexError on a real screen."""
    import viz_config
    for name in viz_config.get_palette_names():
        assert len(viz_config.get_palette(name)) >= len(viz_config.PALETTE_SLOTS), name


def test_a_palette_that_predates_a_slot_is_padded_rather_than_raising():
    """The real palettes live in the private cotmetrics-config, which is not updated in
    lockstep with this repo, so a config a week old must not crash a chart."""
    import viz_config
    assert viz_config._padded(["#111111"]) [:1] == ["#111111"]
    assert len(viz_config._padded(["#111111"])) == len(viz_config.PALETTE_SLOTS)
    assert len(viz_config._padded([])) == len(viz_config.PALETTE_SLOTS)


def test_palette_slots_match_leg_labels():
    """The three positioning slots and the app-wide leg labels are the same three CFTC
    names spelled in two modules (viz_config cannot import viz_constants without
    dragging cotmetrics into a config loader). A legend and its palette slot must agree,
    so the two spellings are pinned to each other, and both to the CFTC's own names."""
    import viz_config
    assert viz_config.PALETTE_SLOTS[:3] == vc.LEG_LABELS_BY_SLOT
    assert vc.LEG_LABELS_BY_SLOT == ("Commercial", "Non-Commercial", "Non-Reportable")


def test_leg_vocabulary_has_left_the_cmr_names_behind():
    """Every leg name a page can render comes from one of three tables, and none of
    them may say Large Specs, Small Traders or Small Specs: those were CMR's aliases
    for the CFTC categories and the app now names the categories."""
    rendered = (list(vc.LEG_LABELS.values()) + list(vc.LEG_NAMES.values())
                + list(vc.LEG_SHORT.values()))
    for text in rendered:
        for stale in ("Large", "Small", "Spec"):
            assert stale not in text, text


def test_volatility_owns_the_sixth_slot_rather_than_borrowing_one():
    import components.exposure_traces as et
    import viz_config
    assert viz_config.PALETTE_SLOTS[et.VOL_PALETTE_SLOT] == "Volatility"
    assert et.VOL_PALETTE_SLOT not in et.LEG_PALETTE_SLOT.values()
    assert et.VOL_PALETTE_SLOT != 3


# --- title hints ----------------------------------------------------------------

def test_title_hint_rides_on_the_matching_subplot_title():
    from plotly.subplots import make_subplots

    ids = ["index", "max_pain", "lrg_sentiment"]
    titles = ["Positioning Index", "Options Max Pain (Gold via GLD)", "Non-Commercial Sentiment"]
    fig = make_subplots(rows=3, cols=1, subplot_titles=titles)
    reg.apply_title_hints(fig, ids)

    anns = fig.layout.annotations
    for ann, plot_id, title in zip(anns, ids, titles):
        assert ann.hovertext == reg.REGISTRY[plot_id].hint
        assert ann.text.startswith(title + " ")
        assert reg.HINT_MARKER in ann.text
    assert anns[1].hovertext == reg.MAX_PAIN_HINT


def test_title_hint_is_idempotent_and_tolerates_short_annotation_lists():
    from plotly.subplots import make_subplots

    fig = make_subplots(rows=1, cols=1, subplot_titles=["Options Max Pain (Gold via GLD)"])
    reg.apply_title_hints(fig, ["max_pain"])
    once = fig.layout.annotations[0].text
    reg.apply_title_hints(fig, ["max_pain"])
    assert fig.layout.annotations[0].text == once
    # More ids than titles (a page that passed an empty title) must not raise.
    reg.apply_title_hints(fig, ["max_pain", "max_pain"])


def test_unknown_ids_and_hintless_specs_leave_titles_alone():
    from dataclasses import replace

    from plotly.subplots import make_subplots

    fig = make_subplots(rows=2, cols=1, subplot_titles=["A", "B"])
    bare = replace(reg.REGISTRY["index"], id="bare", hint=None)
    reg.REGISTRY["bare"] = bare
    try:
        reg.apply_title_hints(fig, ["not_a_plot", "bare"])
    finally:
        del reg.REGISTRY["bare"]
    assert [a.text for a in fig.layout.annotations] == ["A", "B"]
    assert all(a.hovertext is None for a in fig.layout.annotations)


def test_every_panel_has_a_hint_that_names_how_to_read_it():
    for spec in reg._SPECS:
        assert spec.hint, spec.id
        assert spec.hint.startswith("<b>How to read this panel</b><br>"), spec.id
        assert "\n" not in spec.hint, spec.id


# ── the Disaggregated / TFF panel on the stack pages ─────────────────────────

def _category_ctx(report, category=True):
    import numpy as np
    import pandas as pd
    import plotly.subplots as sp
    from cotmetrics import categories as cot_categories

    import components.category_traces as ct
    import viz_config

    palette = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
    rng = np.random.default_rng(5)
    idx = pd.date_range("2024-01-02", periods=40, freq="7D")
    df = pd.DataFrame({"Open Interest": rng.integers(400_000, 600_000, 40)}, index=idx)
    for spec in cot_categories.categories_for(report):
        df[cot_categories.net_col(spec)] = rng.normal(0, 30_000, 40).cumsum()
    series = ct.category_series(report, None, palette, frame=df)
    fig = sp.make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
    return reg.PlotCtx(fig=fig, row=1, col=1, palette=palette,
                       category=(df, series) if category else None), series


@pytest.mark.parametrize("report", ["disagg", "tff"])
def test_category_net_draws_the_categories_pages_panel(report):
    """Five category lines with their bands, on one axis: no Open Interest, no price."""
    ctx, series = _category_ctx(report)
    fig = reg.REGISTRY["category_net"].build(ctx)

    labels = {s.label for s in series}
    lines = [t for t in fig.data if t.name in labels and t.line.width != 0
             and t.x is not None and len(t.x) > 1]
    assert {t.name for t in lines} == labels
    assert [t for t in fig.data if t.fill == "tonexty"], "the banded fill comes with it"
    assert not [t for t in fig.data if t.name in ("Open Interest", "Price")]
    assert {t.yaxis for t in fig.data} == {"y"}
    assert not reg.uses_secondary_y("category_net", show_price=True)


@pytest.mark.parametrize("report", ["disagg", "tff"])
def test_category_net_names_its_categories_on_the_panel_not_in_the_legend(report):
    """The legend is figure-wide; this is the only panel on the stack drawing these."""
    ctx, series = _category_ctx(report)
    fig = reg.REGISTRY["category_net"].build(ctx)

    assert not [t for t in fig.data if t.showlegend], "no category legend entries"
    readout = [a for a in fig.layout.annotations if a.name == "category_net_latest_readout"]
    assert len(readout) == 1
    frame = ctx.category[0]
    from cotmetrics import categories as cot_categories

    from components.plot_traces import format_net
    for s in series:
        # whole contracts: the fixture's nets are fractional, as a stitched market's are
        latest = round(float(frame[cot_categories.net_col(s.spec)].iloc[-1]))
        assert f'<span style="color:{s.color}">{s.label} {format_net(latest)}</span>' \
            in readout[0].text
    assert "." not in readout[0].text.replace("&nbsp;", ""), "no decimals on contracts"
    assert readout[0].text.count("<br>") == 1, "five categories break over two lines"


def test_category_net_says_so_when_the_market_has_no_category_report():
    ctx, _ = _category_ctx("tff", category=False)
    fig = reg.REGISTRY["category_net"].build(ctx)
    assert not fig.data
    assert [a.text for a in fig.layout.annotations] == [reg.NO_CATEGORY_REPORT_NOTE]


def test_category_net_is_offered_on_oi_alignment_only():
    import pathlib
    pages = pathlib.Path(__file__).resolve().parents[1] / "src" / "pages" / "analytics"
    offering = {p.stem for p in pages.glob("*.py") if '"category_net"' in p.read_text()}
    assert offering == {"oi_alignment"}
    assert "category_net" not in reg.BASIS_AWARE_PLOTS


def _oi_alignment_source():
    import ast
    import pathlib
    text = (pathlib.Path(__file__).resolve().parents[1] / "src" / "pages" / "analytics"
            / "oi_alignment.py").read_text()
    tree = ast.parse(text)

    def literal(name):
        return next(n.value for n in tree.body if isinstance(n, ast.Assign)
                    and getattr(n.targets[0], "id", None) == name)
    return tree, literal


def test_oi_alignment_stacks_the_net_position_panels_directly_under_the_tape():
    """Positions are read against price, so they sit second and third, in that order
    however the picker was clicked (it hands ids back in click order). MACD, a
    derivative of commercial net positioning, follows the % of OI panel."""
    import ast
    tree, literal = _oi_alignment_source()
    ids = ast.literal_eval(literal("PLOT_IDS"))
    assert ids[:3] == ["oi_alignment", "net_pos", "category_net"]
    assert ids.index("macd") == ids.index("oi_pct") + 1

    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_in_stack_order")
    scope = {"PLOT_IDS": ids}
    exec(compile(ast.Module([fn], []), "oi_alignment", "exec"), scope)
    clicked = ["zscore", "oi_alignment", "macd", "category_net", "net_pos"]
    assert scope["_in_stack_order"](clicked) == \
        ["oi_alignment", "net_pos", "category_net", "zscore", "macd"]


def test_oi_alignment_default_stack_has_the_categories_and_not_the_z_score():
    """A fresh session's stack: the category breakdown and Open Interest's own panel
    are on, directly under Net Positions, and the registry's opt-in panels are off."""
    import ast
    _, literal = _oi_alignment_source()
    ids = ast.literal_eval(literal("PLOT_IDS"))
    default = [p for p in ids if p not in reg.DEFAULT_OFF_PLOTS]
    assert default[:4] == ["oi_alignment", "net_pos", "category_net", "open_interest"]
    assert "zscore" in ids and "zscore" not in default
    assert "max_pain_historical" not in default


# ── Open Interest on its own panel ───────────────────────────────────────────

def _net_frame(n=120):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(11)
    idx = pd.date_range("2023-01-03", periods=n, freq="7D")
    comm = rng.normal(0, 5_000, n).cumsum()
    return pd.DataFrame({
        const.COMM_NET: comm, const.LARGE_NET: -comm * 0.8, const.SMALL_NET: -comm * 0.2,
        const.OPEN_INTEREST: 300_000 + rng.normal(0, 4_000, n).cumsum(),
    }, index=idx)


def _one_panel(plot_id, **ctx):
    import plotly.subplots as sp

    import viz_config
    palette = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
    fig = sp.make_subplots(rows=1, cols=1, specs=[[
        {"secondary_y": reg.uses_secondary_y(plot_id)}]])
    return reg.REGISTRY[plot_id].build(reg.PlotCtx(
        fig=fig, row=1, col=1, palette=palette, df=_net_frame(), **ctx))


def test_open_interest_panel_draws_the_one_line_on_one_axis():
    fig = _one_panel("open_interest")
    lines = [t for t in fig.data if t.x is not None and len(t.x) > 1]
    assert [t.name for t in lines] == ["Open Interest"]
    assert lines[0].yaxis == "y" and not reg.uses_secondary_y("open_interest")
    lo, hi = fig.layout.yaxis.range
    window = _net_frame()[const.OPEN_INTEREST].iloc[-52:]
    assert lo <= window.min() and hi >= window.max(), "fitted to the opening window"


def test_net_positions_carries_no_open_interest():
    """Open Interest is drawn on its own panel and nowhere else's second axis."""
    fig = _one_panel("net_pos")
    assert not [t for t in fig.data if t.name == "Open Interest"]
    # legend stubs sit on no axis; every drawn trace is on the first
    assert {t.yaxis for t in fig.data if t.yaxis} == {"y"}
    assert {t.name for t in fig.data if t.type == "bar"} == \
        {"Commercial", "Non-Commercial", "Non-Reportable"}


def test_the_basis_overlay_carries_no_open_interest():
    import plotly.subplots as sp

    import components.plot_traces as pt
    import viz_config
    palette = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])
    df = _net_frame()
    df["comms_idx"] = 50.0
    fig = sp.make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
    fig = pt.get_basis_overlay_plot(fig, df, df, "comms_idx", 1, 1, palette,
                                    y_title="Index", y_range=[0, 100])
    assert not [t for t in fig.data if t.name == "Open Interest"]
    assert {t.yaxis for t in fig.data} == {"y"}


def test_open_interest_panel_is_offered_wherever_net_positions_is():
    """Net Positions gave up its Open Interest line, so every page that stacks it
    offers the panel the line moved to, directly after it."""
    import ast
    import pathlib
    pages = pathlib.Path(__file__).resolve().parents[1] / "src" / "pages" / "analytics"
    for page, list_name in [("oi_alignment", "PLOT_IDS"), ("analysis", "PLOT_IDS"),
                            ("analysis", "GRID_PLOT_IDS"), ("aggregation", "PLOT_IDS")]:
        tree = ast.parse((pages / f"{page}.py").read_text())
        ids = next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign)
                   and getattr(n.targets[0], "id", None) == list_name)
        assert "net_pos" in ids and "open_interest" in ids, (page, list_name)
        assert ids.index("open_interest") > ids.index("net_pos"), (page, list_name)
