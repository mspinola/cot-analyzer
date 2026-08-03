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
import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_colors import darken_hex, lighten_hex, relative_luminance
from components.plot_layout import visible_weeks
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
                     gridcolor=vc.EMPTY_COLOR, secondary_y=True, fixedrange=True,
                     range=_fit_range(df, [const.CLOSING_PRICE]))
    return fig


def _primary_axis(fig, row, col, title, zeroline=False, y_range=None):
    fig.update_yaxes(title=title, row=row, col=col, zeroline=zeroline,
                     zerolinecolor=vc.GRID_COLOR, gridcolor=vc.GRID_COLOR,
                     secondary_y=False, fixedrange=True, range=y_range)
    return fig


# Fraction of the span left as breathing room above and below the data, matching the
# legacy Net Positions panel.
_Y_PAD = 0.10


def _fit_range(df, cols, include_zero=False, negate=()):
    """Fit an axis to the window the chart opens on, not to all of history.

    Plotly autoranges y over every point in the trace, but `get_update_xaxes_for_plots`
    opens the chart on the last `visible_weeks()` only. On a market whose history dwarfs
    its recent range the visible data then occupies a sliver of the axis: measured over
    the 42-market universe, the worst spreading panel used 7% of its axis and the worst
    trader-count panel 26%. The clientside autoscale fixes this on the first pan or
    zoom, but nothing fires it on the initial render, which is the view most people
    look at and never touch. This is the same reason `get_net_pos_plot` computes its
    own range from a visible slice.

    `include_zero` keeps the zero reference on screen for panels that draw a zero line.
    `negate` names columns drawn flipped below the axis (gross shorts).
    """
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return None
    window = df.iloc[max(0, len(df) - visible_weeks()):]

    lows, highs = [], []
    for c in cols:
        lo, hi = window[c].min(), window[c].max()
        if pd.isna(lo) or pd.isna(hi):
            continue
        if c in negate:
            lo, hi = -hi, -lo
        lows.append(lo)
        highs.append(hi)
    if not lows:
        return None

    lo, hi = min(lows), max(highs)
    non_negative = lo >= 0
    if include_zero:
        lo, hi = min(lo, 0), max(hi, 0)
    span = hi - lo
    if span == 0:
        # A flat series still needs a visible band. Scale it to the series' own
        # magnitude, since a fixed floor would swamp a percent or z-score panel.
        span = abs(hi) * _Y_PAD or 1.0
    low = lo - span * _Y_PAD
    # Do not pad a count or a contract total into negative territory: trader counts
    # and spreading cannot go below zero, so an axis that does is claiming something
    # the data never says.
    if non_negative:
        low = max(low, 0)
    return [low, hi + span * _Y_PAD]


def _draw(fig, df, series, column_fn, row, col, palette, *, show_price, showlegend,
          y_title, zeroline=True, y_range=None, show_oi=False, fit=True):
    """The shape every line panel shares: one line per category, then the chrome.

    `column_fn(spec)` names the column to draw, so the panels below differ only in
    which column family they ask for and how the axis is labelled. Categories are
    drawn on lines rather than the grouped bars the legacy Net Positions panel uses:
    five bar series over a multi-year window collapses into noise, where five lines
    stay separable.
    """
    columns = []
    for z, s in enumerate(series):
        column = column_fn(s.spec)
        if column in df.columns:
            columns.append(column)
            add_trace_to_all(fig, df, column, row, col, s.label, s.color, z,
                             dash=s.dash)
    if show_oi and const.OPEN_INTEREST in df.columns:
        add_trace_to_all(fig, df, const.OPEN_INTEREST, row, col, "Open Interest",
                         palette[vc.CATEGORY_OI_SLOT], len(series), secondary=True)
        fig.update_yaxes(title="OI", row=row, col=col, showgrid=False, zeroline=False,
                         gridcolor=vc.EMPTY_COLOR, secondary_y=True, fixedrange=True,
                         range=_fit_range(df, [const.OPEN_INTEREST]))
    elif show_price:
        _price_overlay(fig, df, row, col, palette, len(series))

    if y_range is None and fit:
        # Zero stays on screen only where the panel draws a zero line to reference it.
        # Forcing it onto a trader-count or spreading axis is what wastes the space.
        y_range = _fit_range(df, columns, include_zero=zeroline)
    _primary_axis(fig, row, col, y_title, zeroline=zeroline, y_range=y_range)
    return _legend(fig, series, showlegend, palette, show_price and not show_oi,
                   show_oi=show_oi)


# --- panels ---------------------------------------------------------------------

def get_category_net_pos_plot(fig, df, series, lookback_header, row, col, palette,
                              show_price=True, showlegend=True, show_oi=True,
                              y_range=None):
    """Net contracts per category, with open interest on the secondary axis.

    Open interest rather than price here: net position is denominated in contracts,
    so the question the panel invites is "large relative to what?", and OI is the
    denominator. The percent-of-OI panel answers it directly.

    `show_oi` is off in small multiples, where open interest gets its own row instead
    of a second scale.
    """
    return _draw(fig, df, series, categories.net_col, row, col, palette,
                 show_price=show_price, showlegend=showlegend,
                 y_title="net contracts", show_oi=show_oi, y_range=y_range)


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
                                 show_price=True, showlegend=True, y_range=None):
    """Gross long above the axis, gross short below it, one colour per category.

    Net position hides a category that doubled both sides. This is the panel that
    shows it. Shorts are negated for display only, so the axis reads as one scale;
    the underlying column is a positive contract count.
    """
    longs, shorts = [], []
    for z, s in enumerate(series):
        long_c = categories.long_col(s.spec)
        short_c = categories.short_col(s.spec)
        if long_c in df.columns:
            longs.append(long_c)
            add_trace_to_all(fig, df, long_c, row, col, s.label, s.color, z * 2,
                             dash=s.dash)
        if short_c in df.columns:
            shorts.append(short_c)
            flipped = df[[short_c]].copy()
            flipped[short_c] = -flipped[short_c]
            add_trace_to_all(fig, flipped, short_c, row, col, s.label, s.color,
                             z * 2 + 1, dash="dot")

    # Zero is the axis of symmetry here, so it is always in range: shorts are drawn
    # below it and longs above.
    _primary_axis(fig, row, col, "long / short", zeroline=True,
                  y_range=y_range or _fit_range(df, longs + shorts, include_zero=True,
                                                negate=set(shorts)))
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
                              show_price=False, showlegend=True, y_range=None):
    """Reporting trader counts, long solid and short dotted.

    The CFTC suppresses a count where it would identify a trader, writing "." which
    arrives as a gap here rather than a zero. Non-Reportable has no counts at all by
    definition, so it does not appear.
    """
    columns = []
    for z, s in enumerate(series):
        for column, dash in ((categories.traders_long_col(s.spec), s.dash),
                             (categories.traders_short_col(s.spec), "dot")):
            if column in df.columns:
                columns.append(column)
                add_trace_to_all(fig, df, column, row, col, s.label, s.color, z,
                                 dash=dash)
    # No include_zero: counts never approach zero, so anchoring the axis there is
    # what left this panel using a quarter of its height.
    _primary_axis(fig, row, col, "traders", zeroline=False,
                  y_range=y_range or _fit_range(df, columns))
    drawn = [s for s in series
             if categories.traders_long_col(s.spec) in df.columns]
    return _legend(fig, drawn, showlegend, palette, False)


def get_category_momentum_columns(fig, df, series, lookback_header, row, col, palette,
                                  show_price=False, showlegend=True, y_range=None):
    """The index change as diverging columns: teal above zero, orange below.

    A change is a signed quantity, and a line makes the reader recover the sign from
    position against a baseline they have to find first. A column anchored on zero
    states it. This is the small-multiples form only: one row carries one category, so
    the bars never occlude each other. In overlay mode five bar series would, which is
    why that path stays on lines.

    Colour here encodes polarity rather than identity, so it does not come from the
    category palette. See CATEGORY_DIVERGING_UP.
    """
    cols = [categories.momentum_col(s.spec, lookback_header) for s in series]
    cols = [c for c in cols if c in df.columns]
    for column in cols:
        values = df[column]
        fig.add_trace(go.Bar(
            x=df.index,
            y=values,
            name=column,
            showlegend=False,
            marker_color=[vc.CATEGORY_DIVERGING_DOWN if (v is not None and v < 0)
                          else vc.CATEGORY_DIVERGING_UP for v in values],
            marker_line_width=0,
        ), row=row, col=col)

    _primary_axis(fig, row, col, "index pts", zeroline=True,
                  y_range=y_range or _fit_range(df, cols, include_zero=True))
    return fig


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

# Which columns each panel draws, and whether its axis must keep zero in view. Used to
# compute ONE y-scale per panel across every category, so faceted rows stay comparable:
# a small multiple whose rows each carry their own scale is a lie by omission, since
# equal-looking wiggles then mean different magnitudes.
#
# id -> (columns(spec, header) -> list, include_zero, negated columns(spec, header))
_PANEL_COLUMNS = {
    "net_pos": (lambda s, h: [categories.net_col(s)], True, None),
    "pct_oi": (lambda s, h: [categories.pct_oi_col(s)], True, None),
    "index": (lambda s, h: [categories.index_col(s, h)], False, None),
    "zscore": (lambda s, h: [categories.zscore_col(s, h)], True, None),
    "momentum": (lambda s, h: [categories.momentum_col(s, h)], True, None),
    "long_short": (lambda s, h: [categories.long_col(s), categories.short_col(s)],
                   True, lambda s, h: [categories.short_col(s)]),
    "spread": (lambda s, h: [categories.spread_col(s)], False, None),
    "traders": (lambda s, h: [categories.traders_long_col(s),
                              categories.traders_short_col(s)], False, None),
}

# In small multiples each row holds one series, so a change reads better as a column
# anchored on zero than as a line. Overlay keeps the line form, where five bar series
# would occlude one another.
_FACET_BUILDERS = {
    "momentum": get_category_momentum_columns,
}


def shared_range(df, plot_id, series, lookback_header):
    """One y-scale for a panel across every faceted category."""
    if plot_id == "index":
        return [0, 100]
    cols_fn, include_zero, negate_fn = _PANEL_COLUMNS[plot_id]
    cols, negate = [], set()
    for s in series:
        cols.extend(cols_fn(s.spec, lookback_header))
        if negate_fn:
            negate.update(negate_fn(s.spec, lookback_header))
    return _fit_range(df, cols, include_zero=include_zero, negate=negate)


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
                show_price=True, showlegend=True, y_range=None, facet=False):
    """Dispatch one panel by id. The page never calls a builder directly."""
    builder = (_FACET_BUILDERS.get(plot_id) if facet else None) \
        or CATEGORY_SPECS[plot_id][1]
    accepts = builder.__code__.co_varnames[:builder.__code__.co_argcount]
    kwargs = dict(show_price=show_price, showlegend=showlegend)
    # Only some builders take an explicit range; the rest fit their own.
    if y_range is not None and "y_range" in accepts:
        kwargs["y_range"] = y_range
    # Open interest rides a secondary axis in overlay; in facets it gets its own row.
    if facet and "show_oi" in accepts:
        kwargs["show_oi"] = False
    return builder(fig, df, series, lookback_header, row, col, palette, **kwargs) or fig


# --- small multiples --------------------------------------------------------------

def facet_context_rows(plots, show_price):
    """The non-category rows: price, and open interest when Net Positions is shown.

    Both are context for the categories rather than categories themselves, and in the
    overlay view both ride a second y-axis. Two scales on one plot align arbitrarily,
    which invents a correlation the data does not contain, so here each gets its own
    row against the same x. Faceting has already produced the row structure, so this
    costs nothing.
    """
    rows = []
    if show_price:
        rows.append(("price", const.CLOSING_PRICE, "Price", vc.CATEGORY_PRICE_SLOT))
    if "net_pos" in plots:
        rows.append(("oi", const.OPEN_INTEREST, "Open Interest", vc.CATEGORY_OI_SLOT))
    return rows


def facet_shape(plots, series, show_price):
    """Grid shape for the faceted view: a row per category, a column per panel."""
    rows = len(series) + len(facet_context_rows(plots, show_price))
    return max(1, rows), max(1, len(plots))


def facet_titles(plots, series, show_price):
    """Panel names on the top row only; every other cell is unlabelled.

    Category identity rides on the y-axis title of the first column instead, so it is
    stated once per row rather than repeated in every cell.
    """
    rows, cols = facet_shape(plots, series, show_price)
    titles = []
    for r in range(rows):
        for c in range(cols):
            titles.append(labels_for(plots).get(plots[c], "") if r == 0 else "")
    return titles


def facet_specs(plots, series, show_price):
    rows, cols = facet_shape(plots, series, show_price)
    return [[{"secondary_y": False} for _ in range(cols)] for _ in range(rows)]


def build_facet_figure(fig, df, series, plots, lookback_header, palette,
                       show_price=True):
    """One category per row, one panel per column, one y-scale per column.

    This is the answer to five series crossing each other on a single axis: reading one
    category stops being a tracing exercise, and the shared per-column scale keeps the
    rows honestly comparable. It also makes colour non-load-bearing, since every row
    carries its own label, which is the relief the palette checks ask for on the two
    shipped palettes whose lightened siblings sit near the chroma floor.
    """
    _, cols = facet_shape(plots, series, show_price)

    def label_axis(text, r, c):
        fig.update_yaxes(title_text=text if c == 1 else "", row=r, col=c,
                         title_font=dict(size=9, color=vc.TEXT_COLOR))

    for c, plot_id in enumerate(plots, start=1):
        y_range = shared_range(df, plot_id, series, lookback_header)
        for r, s in enumerate(series, start=1):
            build_panel(plot_id, fig, df, [s], lookback_header, r, c, palette,
                        show_price=False, showlegend=False, y_range=y_range,
                        facet=True)
            # Row identity, stated once, in text rather than by colour alone.
            label_axis(s.label, r, c)

    for i, (_, column, label, slot) in enumerate(
            facet_context_rows(plots, show_price)):
        if column not in df.columns:
            continue
        r = len(series) + 1 + i
        for c in range(1, cols + 1):
            add_trace_to_all(fig, df, column, r, c, label, palette[slot], 0,
                             opacity=0.9)
            fig.update_yaxes(row=r, col=c, gridcolor=vc.GRID_COLOR, zeroline=False,
                             fixedrange=True, range=_fit_range(df, [column]))
            label_axis(label, r, c)
    return fig
