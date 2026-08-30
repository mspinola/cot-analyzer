"""The price overlay is opt-in, and the legend entry agrees with it.

The rule these pin: price drawn on a SECOND y-axis of a panel whose subject is
something else starts `legendonly`, and price drawn as its own panel does not.

The legend half is the part that can silently come apart. The real traces carry
`showlegend=False` and rely on their `legendgroup` for a Plotly legend click to
reach them, so the clickable entry is a separate empty scatter. Two objects, one
state: if they disagree, the legend renders ungreyed over panels drawing nothing
and the reader's first click hides what was already hidden.

Store-free, like test_category_traces: these build their own frame.
"""

import cotmetrics.constants as const
import numpy as np
import pandas as pd
from plotly.subplots import make_subplots

import components.plot_traces as pt
import viz_config

PALETTE = viz_config.get_palette(sorted(viz_config.get_palette_names())[0])


def _frame(n=60, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-05", periods=n, freq="7D")
    df = pd.DataFrame(index=idx)
    close = rng.uniform(90, 110, n)
    df[const.CLOSING_PRICE] = close
    df[const.OPEN_PRICE] = close + rng.uniform(-2, 2, n)
    df[const.HIGH_PRICE] = close + rng.uniform(0, 3, n)
    df[const.LOW_PRICE] = close - rng.uniform(0, 3, n)
    for col in ("comms_idx", "lrg_idx", "sml_idx"):
        df[col] = rng.uniform(0, 100, n)
    # Net Positions draws these three plus Open Interest, and no price at all.
    for col in (const.COMM_NET, const.LARGE_NET, const.SMALL_NET):
        df[col] = rng.uniform(-50_000, 50_000, n)
    df[const.OPEN_INTEREST] = rng.uniform(100_000, 200_000, n)
    return df


def _figure(rows=1):
    return make_subplots(rows=rows, cols=1,
                         specs=[[{"secondary_y": True}] for _ in range(rows)])


def _net_pos(fig, df, row=1):
    return pt.get_net_pos_plot(fig, df, const.COMM_NET, const.LARGE_NET,
                               const.SMALL_NET, row, 1, PALETTE)


def _index(fig, df, row=1, show_price=True):
    return pt.get_index_plot(fig, df, "comms_idx", "lrg_idx", "sml_idx", row, 1,
                             PALETTE, show_price=show_price)


def _named(fig, name):
    return [t for t in fig.data if t.name == name]


def _drawn(fig, name):
    """Real traces only: a legend entry is an empty scatter at x=[None]."""
    return [t for t in _named(fig, name)
            if t.x is not None and len(t.x) and t.x[0] is not None]


def _entry(fig, name):
    return [t for t in _named(fig, name)
            if t.x is not None and len(t.x) and t.x[0] is None]


def test_overlay_and_its_legend_entry_both_start_off():
    df = _frame()
    fig = pt.get_index_plot(_figure(), df, "comms_idx", "lrg_idx", "sml_idx",
                            1, 1, PALETTE, show_price=True)

    overlay = _drawn(fig, "Price")
    entry = _entry(fig, "Price")
    assert overlay and entry
    assert all(t.visible == "legendonly" for t in overlay + entry)


def test_the_positioning_series_are_untouched():
    """Only price is opt-in. A change that hid the panel's own subject would
    still satisfy the assertion above."""
    df = _frame()
    fig = pt.get_index_plot(_figure(), df, "comms_idx", "lrg_idx", "sml_idx",
                            1, 1, PALETTE, show_price=True)

    for name in ("Commercials", "Large Specs", "Small Specs"):
        traces = _named(fig, name)
        assert traces, name
        assert all(t.visible in (True, None) for t in traces), name


def test_the_overlay_stays_in_the_price_legendgroup():
    """The entry is the only way to reach these traces, since they draw no legend
    item of their own. Lose the shared group and the overlay becomes unreachable:
    permanently hidden rather than opt-in."""
    df = _frame()
    fig = pt.get_index_plot(_figure(), df, "comms_idx", "lrg_idx", "sml_idx",
                            1, 1, PALETTE, show_price=True)

    groups = {t.legendgroup for t in _named(fig, "Price")}
    assert groups == {"price"}


def test_the_candlestick_panel_still_draws():
    """Price as the panel's own subject is not an overlay. Hiding it here would
    leave an empty panel whose whole purpose is the price."""
    fig = pt.get_price_plot(_figure(), _frame(), 1, 1, PALETTE)

    candles = [t for t in fig.data if t.type == "candlestick"]
    assert candles
    assert all(t.visible in (True, None) for t in candles)


def test_the_dollar_axis_reads_correctly_while_the_line_is_hidden():
    """An axis with no visible trace autoranges to Plotly's default.

    Measured before this was fixed: every panel drew a "$" axis running -1 to 4,
    which is not a price and is partly negative. The axis is drawn either way, so
    it is fitted to the price data rather than left to fall back.
    """
    df = _frame()
    fig = pt.get_index_plot(_figure(), df, "comms_idx", "lrg_idx", "sml_idx",
                            1, 1, PALETTE, show_price=True)

    lo, hi = fig.layout.yaxis2.range
    close = df[const.CLOSING_PRICE]
    assert lo < close.min() and hi > close.max()
    # Fitted, not merely wide: the band is close to the data it describes.
    assert hi - lo < (close.max() - close.min()) * 2


def test_a_flat_price_series_still_gets_a_band():
    """A zero-span window would otherwise produce range=[x, x], which Plotly
    cannot draw."""
    df = _frame()
    df[const.CLOSING_PRICE] = 100.0
    lo, hi = pt.price_window_range(df)
    assert lo < 100.0 < hi


# --- the legend describes what the figure drew -----------------------------------
#
# Entries are added by ONE panel (row 1, col 1), which is the wrong scope for the two
# series only some panels draw. `reconcile_legend_entries` settles it against the
# assembled figure, in both directions.


def test_net_positions_labels_open_interest_and_claims_no_price():
    """The panel's second axis carries Open Interest, and it draws no price.

    Measured before this was fixed: the legend showed a Price entry that controlled
    nothing, and the white line under it -- the one the reader can actually see --
    was Open Interest, with no entry of its own.
    """
    df = _frame()
    fig = _net_pos(_figure(), df)

    assert not _named(fig, "Price")
    assert _drawn(fig, "Open Interest")
    assert len(_entry(fig, "Open Interest")) == 1


def test_a_stack_led_by_net_positions_keeps_its_price_entry():
    """The stranding case. Net Positions draws no price, so it adds no entry; the
    panels below it do, and since PR #86 their overlays start hidden. Without an
    entry to click they would be unreachable rather than opt-in."""
    df = _frame()
    fig = _figure(rows=2)
    fig = _net_pos(fig, df, row=1)
    fig = _index(fig, df, row=2)

    assert not _entry(fig, "Price"), "the precondition this guards"
    pt.reconcile_legend_entries(fig, PALETTE)

    added = _entry(fig, "Price")
    assert len(added) == 1
    assert added[0].visible == "legendonly"
    assert added[0].legendgroup == "price"


def test_the_price_entry_is_not_duplicated_when_one_already_exists():
    df = _frame()
    fig = _index(_figure(), df)

    before = len(_named(fig, "Price"))
    pt.reconcile_legend_entries(fig, PALETTE)
    assert len(_named(fig, "Price")) == before


def test_no_price_entry_is_invented_when_nothing_drew_one():
    df = _frame()
    fig = _net_pos(_figure(), df)

    pt.reconcile_legend_entries(fig, PALETTE)
    assert not _named(fig, "Price")


def test_a_price_entry_over_a_figure_drawing_no_price_is_dropped():
    """The candlestick panel adds one whatever the overlay setting, and its candles
    are their own trace in no legendgroup, so the entry reaches nothing."""
    df = _frame()
    fig = pt.get_price_plot(_figure(), df, 1, 1, PALETTE)
    assert _entry(fig, "Price"), "the precondition this guards"

    pt.reconcile_legend_entries(fig, PALETTE)
    assert not _named(fig, "Price")
    assert [t for t in fig.data if t.type == "candlestick"]


def test_an_open_interest_entry_is_added_for_a_panel_that_is_not_the_first():
    """Same stranding, other series: only row 1 draws the legend, so a Net Positions
    panel further down the stack labelled nothing."""
    df = _frame()
    fig = _figure(rows=2)
    fig = _index(fig, df, row=1)
    fig = _net_pos(fig, df, row=2)

    assert not _entry(fig, "Open Interest"), "the precondition this guards"
    pt.reconcile_legend_entries(fig, PALETTE)
    assert len(_entry(fig, "Open Interest")) == 1


def test_the_open_interest_entry_is_not_duplicated():
    """Two panels drawing it, one entry. The z-score panel draws it too."""
    df = _frame(seed=7)
    for col in (const.COMMS_ZSCORE, const.LRG_ZSCORE, const.SML_ZSCORE,
                const.OI_ZSCORE):
        df[col] = 0.5
    fig = _figure(rows=2)
    fig = _net_pos(fig, df, row=1)
    fig = pt.get_zscore_plot(fig, df, 2, 1, PALETTE, show_price=False)

    pt.reconcile_legend_entries(fig, PALETTE)
    assert len(_entry(fig, "Open Interest")) == 1
