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
    return df


def _figure():
    return make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])


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
