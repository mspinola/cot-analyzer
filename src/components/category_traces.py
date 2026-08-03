"""Panels for the Disaggregated / TFF category page.

The rest of the app draws exactly three trader legs, and the machinery reflects that:
`plot_registry.PlotCtx` carries fixed three-tuples and most builders in `plot_traces`
read `const.COMM/LARGE/SMALL` internally. The Disaggregated and TFF reports have five
categories each, so these panels take an N-length series list instead. That is why
they live here rather than as more functions in `plot_traces`, and why this module
keeps its own small spec table instead of adding ids to `plot_registry`: `PlotSpec`'s
basis/overlay/decorate fields would all be permanently dead for these, and `_SPECS` is
the shared vocabulary for four pages that persist plot ids per session.

Store-free by construction. Everything imported here is either pure colour/geometry
maths or a constants module, so the page's builders can be unit-tested under CI's empty
COTDATA_STORE. `tests/test_category_traces.py` pins that property directly, because it
is the thing that makes the rest of those tests possible.
"""

import math
from collections import namedtuple

import cotmetrics.categories as categories
import cotmetrics.constants as const

import viz_constants as vc
from components.plot_colors import darken_hex, lighten_hex, relative_luminance
from components.plot_layout import get_nice_dtick
from components.plot_traces import add_legend_lines, add_trace_to_all

# One drawable category: the cotmetrics spec (which knows the column names), plus the
# presentation the palette resolved for it.
CategorySeries = namedtuple("CategorySeries", "spec key label color dash")


def category_series(report, selected_keys, palette, frame=None):
    """Resolve the selected categories to (columns, colour, dash), in report order.

    `selected_keys` of None means all. `frame`, when given, filters to the categories
    that frame actually carries, so a market missing a category renders four panels
    rather than raising on the fifth.
    """
    slot_map = vc.CATEGORY_PALETTE_MAP[report]
    specs = (categories.present_categories(frame, report) if frame is not None
             else categories.categories_for(report))

    out = []
    for spec in specs:
        if selected_keys is not None and spec.key not in selected_keys:
            continue
        slot, is_sibling = slot_map[spec.key]
        out.append(CategorySeries(
            spec=spec,
            key=spec.key,
            label=spec.label,
            color=sibling_color(palette[slot]) if is_sibling else palette[slot],
            # Siblings also differ in dash. Colour alone is not a reliable
            # distinction on a busy panel at 1px line width.
            dash=vc.CATEGORY_TINT_DASH if is_sibling else None,
        ))
    return out


def sibling_color(base):
    """The second colour on a palette slot: lighter, or darker when already bright.

    Direction is chosen by luminance rather than fixed, because a single direction
    fails on the shipped palettes. See the note above CATEGORY_TINT_LIGHTEN.
    """
    if relative_luminance(base) > vc.CATEGORY_BRIGHT_LUMINANCE:
        return darken_hex(base, vc.CATEGORY_TINT_DARKEN)
    return lighten_hex(base, vc.CATEGORY_TINT_LIGHTEN)


def _legend(fig, series, showlegend, palette, show_price, show_oi=False):
    if not showlegend:
        return fig
    for s in series:
        add_legend_lines(fig, s.label, s.color)
    if show_price:
        add_legend_lines(fig, "Price", palette[vc.CATEGORY_PRICE_SLOT])
    if show_oi:
        add_legend_lines(fig, "Open Interest", palette[vc.CATEGORY_OI_SLOT])
    return fig


def _price_overlay(fig, df, row, col, palette, zorder):
    if const.CLOSING_PRICE not in df.columns:
        return fig
    add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price",
                     palette[vc.CATEGORY_PRICE_SLOT], zorder,
                     secondary=True, opacity=0.6)
    fig.update_yaxes(title="$", row=row, col=col, showgrid=False, zeroline=False,
                     gridcolor=vc.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    return fig


def _primary_axis(fig, row, col, title, zeroline=False, y_range=None):
    fig.update_yaxes(title=title, row=row, col=col, zeroline=zeroline,
                     zerolinecolor=vc.GRID_COLOR, gridcolor=vc.GRID_COLOR,
                     secondary_y=False, fixedrange=True, range=y_range)
    return fig


def _draw(fig, df, series, column_fn, row, col, palette, *, show_price, showlegend,
          y_title, zeroline=True, y_range=None, show_oi=False):
    """The shape every line panel shares: one line per category, then the chrome.

    `column_fn(spec)` names the column to draw, so the panels below differ only in
    which column family they ask for and how the axis is labelled. Categories are
    drawn on lines rather than the grouped bars the legacy Net Positions panel uses:
    five bar series over a multi-year window collapses into noise, where five lines
    stay separable.
    """
    for z, s in enumerate(series):
        column = column_fn(s.spec)
        if column in df.columns:
            add_trace_to_all(fig, df, column, row, col, s.label, s.color, z,
                             dash=s.dash)
    if show_oi and const.OPEN_INTEREST in df.columns:
        add_trace_to_all(fig, df, const.OPEN_INTEREST, row, col, "Open Interest",
                         palette[vc.CATEGORY_OI_SLOT], len(series), secondary=True)
        fig.update_yaxes(title="OI", row=row, col=col, showgrid=False, zeroline=False,
                         gridcolor=vc.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    elif show_price:
        _price_overlay(fig, df, row, col, palette, len(series))

    _primary_axis(fig, row, col, y_title, zeroline=zeroline, y_range=y_range)
    return _legend(fig, series, showlegend, palette, show_price and not show_oi,
                   show_oi=show_oi)


# --- panels ---------------------------------------------------------------------

def get_category_net_pos_plot(fig, df, series, lookback_header, row, col, palette,
                              show_price=True, showlegend=True):
    """Net contracts per category, with open interest on the secondary axis.

    Open interest rather than price here: net position is denominated in contracts,
    so the question the panel invites is "large relative to what?", and OI is the
    denominator. The percent-of-OI panel answers it directly.
    """
    return _draw(fig, df, series, categories.net_col, row, col, palette,
                 show_price=show_price, showlegend=showlegend,
                 y_title="net contracts", show_oi=True)


def get_category_pct_oi_plot(fig, df, series, lookback_header, row, col, palette,
                             show_price=True, showlegend=True):
    """Net position as a percent of open interest, the size-invariant view."""
    return _draw(fig, df, series, categories.pct_oi_col, row, col, palette,
                 show_price=show_price, showlegend=showlegend, y_title="% of OI")


def get_category_index_plot(fig, df, series, lookback_header, row, col, palette,
                            show_price=True, showlegend=True):
    """0-100 positioning index per category.

    No threshold bands. The legacy index panel shades a setup gate, but the gate is a
    three-leg model calibrated on the legacy series, so drawing its lines here would
    assert a signal this page deliberately does not compute.
    """
    return _draw(fig, df, series,
                 lambda spec: categories.index_col(spec, lookback_header),
                 row, col, palette, show_price=show_price, showlegend=showlegend,
                 y_title="index", zeroline=False, y_range=[0, 100])


def get_category_zscore_plot(fig, df, series, lookback_header, row, col, palette,
                             show_price=True, showlegend=True):
    return _draw(fig, df, series,
                 lambda spec: categories.zscore_col(spec, lookback_header),
                 row, col, palette, show_price=show_price, showlegend=showlegend,
                 y_title="z-score")


def get_category_momentum_plot(fig, df, series, lookback_header, row, col, palette,
                               show_price=True, showlegend=True):
    return _draw(fig, df, series,
                 lambda spec: categories.momentum_col(spec, lookback_header),
                 row, col, palette, show_price=show_price, showlegend=showlegend,
                 y_title="index pts")


def get_category_long_short_plot(fig, df, series, lookback_header, row, col, palette,
                                 show_price=True, showlegend=True):
    """Gross long above the axis, gross short below it, one colour per category.

    Net position hides a category that doubled both sides. This is the panel that
    shows it. Shorts are negated for display only, so the axis reads as one scale;
    the underlying column is a positive contract count.
    """
    for z, s in enumerate(series):
        long_c = categories.long_col(s.spec)
        short_c = categories.short_col(s.spec)
        if long_c in df.columns:
            add_trace_to_all(fig, df, long_c, row, col, s.label, s.color, z * 2,
                             dash=s.dash)
        if short_c in df.columns:
            flipped = df[[short_c]].copy()
            flipped[short_c] = -flipped[short_c]
            add_trace_to_all(fig, flipped, short_c, row, col, s.label, s.color,
                             z * 2 + 1, dash="dot")

    _primary_axis(fig, row, col, "long / short", zeroline=True)
    if show_price:
        _price_overlay(fig, df, row, col, palette, len(series) * 2)
    return _legend(fig, series, showlegend, palette, show_price)


def get_category_spread_plot(fig, df, series, lookback_header, row, col, palette,
                             show_price=True, showlegend=True):
    """Spreading contracts, for the categories the CFTC reports them for.

    Producer/Merchant has no spreading leg (an offsetting hedge is reported net) and
    neither does Non-Reportable, so those categories are simply absent here rather
    than drawn flat at zero.
    """
    drawn = [s for s in series if categories.spread_col(s.spec) in df.columns]
    return _draw(fig, df, drawn, categories.spread_col, row, col, palette,
                 show_price=show_price, showlegend=showlegend,
                 y_title="spreading", zeroline=False)


def get_category_traders_plot(fig, df, series, lookback_header, row, col, palette,
                              show_price=False, showlegend=True):
    """Reporting trader counts, long solid and short dotted.

    The CFTC suppresses a count where it would identify a trader, writing "." which
    arrives as a gap here rather than a zero. Non-Reportable has no counts at all by
    definition, so it does not appear.
    """
    for z, s in enumerate(series):
        for column, dash in ((categories.traders_long_col(s.spec), s.dash),
                             (categories.traders_short_col(s.spec), "dot")):
            if column in df.columns:
                add_trace_to_all(fig, df, column, row, col, s.label, s.color, z,
                                 dash=dash)
    _primary_axis(fig, row, col, "traders", zeroline=False)
    drawn = [s for s in series
             if categories.traders_long_col(s.spec) in df.columns]
    return _legend(fig, drawn, showlegend, palette, False)


# --- the page's plot vocabulary --------------------------------------------------
# id -> (label, builder, when the cell needs a secondary y-axis)
#
# Same three-way distinction plot_registry draws, and for the same reason: Net
# Positions puts Open Interest on the secondary axis whether or not price is shown,
# so a boolean would drop its axis the moment price was switched off.
SECONDARY_NEVER = "never"
SECONDARY_WITH_PRICE = "price"
SECONDARY_ALWAYS = "always"

CATEGORY_SPECS = {
    "net_pos": ("Net Positions", get_category_net_pos_plot, SECONDARY_ALWAYS),
    "pct_oi": ("Net % of OI", get_category_pct_oi_plot, SECONDARY_WITH_PRICE),
    "index": ("Positioning Index", get_category_index_plot, SECONDARY_WITH_PRICE),
    "zscore": ("Z-Score", get_category_zscore_plot, SECONDARY_WITH_PRICE),
    "momentum": (vc.MOMENTUM_LABEL, get_category_momentum_plot, SECONDARY_WITH_PRICE),
    "long_short": ("Gross Long / Short", get_category_long_short_plot, SECONDARY_WITH_PRICE),
    "spread": ("Spreading", get_category_spread_plot, SECONDARY_WITH_PRICE),
    "traders": ("Trader Counts", get_category_traders_plot, SECONDARY_NEVER),
}

DEFAULT_PLOTS = ["net_pos", "index"]


def labels_for(plot_ids=None):
    ids = plot_ids if plot_ids is not None else list(CATEGORY_SPECS)
    return {i: CATEGORY_SPECS[i][0] for i in ids if i in CATEGORY_SPECS}


def sanitize_selection(selected):
    """Drop ids this page does not offer, falling back to the default pair.

    The picker persists per session, so a value saved before a panel was renamed can
    outlive it.
    """
    kept = [p for p in (selected or []) if p in CATEGORY_SPECS]
    return kept or list(DEFAULT_PLOTS)


def uses_secondary_y(plot_id, show_price):
    mode = CATEGORY_SPECS[plot_id][2]
    if mode == SECONDARY_ALWAYS:
        return True
    return mode == SECONDARY_WITH_PRICE and show_price


def subplot_specs(selected, show_price, num_cols):
    """make_subplots `specs` grid: which cells need a secondary y-axis."""
    rows = max(1, math.ceil(len(selected) / num_cols))
    grid = []
    for r in range(rows):
        row = []
        for c in range(num_cols):
            i = r * num_cols + c
            secondary = (i < len(selected)
                         and uses_secondary_y(selected[i], show_price))
            row.append({"secondary_y": secondary})
        grid.append(row)
    return grid


def build_panel(plot_id, fig, df, series, lookback_header, row, col, palette,
                show_price=True, showlegend=True):
    """Dispatch one panel by id. The page never calls a builder directly."""
    _, builder, _ = CATEGORY_SPECS[plot_id]
    return builder(fig, df, series, lookback_header, row, col, palette,
                   show_price=show_price, showlegend=showlegend) or fig


def apply_tick_spacing(fig, df, series, row, col):
    """Keep the primary axis ticks from auto-syncing to the secondary series."""
    cols = [categories.net_col(s.spec) for s in series]
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return fig
    span = float(df[cols].max().max() - df[cols].min().min())
    fig.update_yaxes(dtick=get_nice_dtick(span), row=row, col=col, secondary_y=False)
    return fig
