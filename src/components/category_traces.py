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
import re
from collections import namedtuple

import cotmetrics.categories as categories
import cotmetrics.constants as const
import cotmetrics.flows as flows
import pandas as pd
import plotly.graph_objects as go

import app_utils
import viz_constants as vc
from components.plot_colors import DIM_TEXT, darken_hex, lighten_hex, relative_luminance
from components.plot_layout import visible_weeks
from components.plot_traces import (
    PRICE_OVERLAY_VISIBILITY,
    add_legend_lines,
    add_trace_to_all,
)

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
        # Off at first paint, matching the overlay it toggles; see
        # plot_traces.PRICE_OVERLAY_VISIBILITY. Only the overlay views reach this,
        # never the facet one, where price is a row of its own and no legend is
        # drawn at all.
        add_legend_lines(fig, "Price", palette[vc.CATEGORY_PRICE_SLOT],
                         visible=PRICE_OVERLAY_VISIBILITY)
    if show_oi:
        add_legend_lines(fig, "Open Interest", palette[vc.CATEGORY_OI_SLOT])
    return fig


def ensure_price_legend_entry(fig, palette):
    """Give the overlay figure a Price entry if any panel actually drew one.

    One panel draws the legend for the whole stack (the first), and that panel
    suppresses its OWN Price entry when open interest has taken its second axis,
    which is right for the panel and wrong for the figure: a stack led by Net
    Positions drew price overlays on every later panel and no entry for them.

    That was invisible while the overlays drew themselves, costing only the ability
    to switch them off. With price off by default it would strand them: hidden, and
    with nothing in the legend to click. Derived from the traces on the figure rather
    than from re-deriving which panel draws what, because the figure is the thing
    that has to be consistent.
    """
    drawn = entry = False
    for t in fig.data:
        if t.name != "Price":
            continue
        if t.x is not None and len(t.x) and t.x[0] is None:
            entry = True
        else:
            drawn = True
    if drawn and not entry:
        add_legend_lines(fig, "Price", palette[vc.CATEGORY_PRICE_SLOT],
                         visible=PRICE_OVERLAY_VISIBILITY)
    return fig


def _price_overlay(fig, df, row, col, palette, zorder):
    if const.CLOSING_PRICE not in df.columns:
        return fig
    add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price",
                     palette[vc.CATEGORY_PRICE_SLOT], zorder,
                     secondary=True, opacity=0.6,
                     visible=PRICE_OVERLAY_VISIBILITY)
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


# --- the weekly flow heatmap ------------------------------------------------------

# Display clip for the colour scale only. The metric is never clipped: a z of +5 is
# still +5 in the hover, it just paints as saturated as +3 does, because past three
# sigma the eye cannot rank the shades anyway and letting one outlier week own the
# scale would wash every ordinary week to grey.
FLOW_Z_CLIP = 3.0


def _composite_over(rgba, hex_bg):
    """The opaque colour an rgba() paints when laid over an opaque hex background.

    Plotly's colorscale takes no alpha channel per stop in a useful way (the stop
    would blend with whatever the heatmap sits on, which is the paper, not the panel
    background), so the translucent grey the rest of the app uses for "nothing to
    say" has to be flattened onto the plot background first.
    """
    m = re.match(r"rgba?\(([^)]*)\)", str(rgba))
    parts = [float(x) for x in m.group(1).split(",")] if m else []
    if len(parts) < 3:
        return hex_bg
    alpha = parts[3] if len(parts) > 3 else 1.0
    h = str(hex_bg).lstrip("#")
    bg = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    out = [round(b + (c - b) * alpha) for c, b in zip(parts[:3], bg)]
    return "#{:02x}{:02x}{:02x}".format(*out)


# Three stops: DOWN, grey, UP. Polarity, not identity, for the same reason
# get_category_momentum_columns gives: every palette slot already names a cohort or
# a series, so a cell painted in slot 1 would say "this is Managed Money" when it
# means "this cohort sold". The midpoint is a grey composited from DIM_TEXT over the
# plot background rather than the background itself: the prototype (cotmetrics
# docs/design/cot-flows.md, section 7) painted |z| < 1 as background and the panel
# lost the multi-week runs of mild same-sign flow it exists to show, leaving a few
# isolated sticks. Grey keeps the runs visible and still lets the two and three
# sigma cells stand out.
FLOW_COLORSCALE = [
    [0.0, vc.CATEGORY_DIVERGING_DOWN],
    [0.5, _composite_over(DIM_TEXT, vc.BACKGROUND_COLOR)],
    [1.0, vc.CATEGORY_DIVERGING_UP],
]

# One heatmap row: the tick label the axis shows, the fuller name the hover opens
# with, and the columns the cells, the hover and the level markers read.
FlowRow = namedtuple("FlowRow",
                     "label hover_label z dnet dlong dshort thin level mark")


def _counterparty_label(df):
    """Name the composite by what was summed, so the row says what it holds.

    The members are per market (cotmetrics.flow_roles: Producer/Merchant plus Swap
    Dealers on gold, Producer/Merchant alone on corn), so a fixed label would be
    wrong on half the universe. Read from the frame's own attrs rather than from the
    selected series: the members and the report they belong to are written into
    `flow_roles` together, by the same call that built the composite column, whereas
    `series` is whatever subset the checklist left and in a facet cell is one
    category, which says nothing about the report. A frame without those attrs has
    no members to name, so it gets the bare word.

    What was summed is the PRESENT subset of the measured set: cotmetrics adds only
    the members whose columns the frame carries, and records the full measured tuple
    in attrs regardless, so a member is named here only when its dNet is in the
    frame. Otherwise a market lacking a cohort would claim to have summed it.
    """
    roles = df.attrs.get("flow_roles") or {}
    report = roles.get("report")
    members = roles.get("counterparty") or ()
    if not members or report not in categories.REPORT_CHOICES:
        return "Counterparty"
    by_key = {s.key: s for s in categories.categories_for(report)}
    names = [by_key[k].label for k in members
             if k in by_key and flows.flow_col(by_key[k]) in df.columns]
    if not names:
        return "Counterparty"
    return f"Counterparty ({' + '.join(names)})"


def _flow_rows(df, series, lookback_header=None, with_counterparty=True):
    """The rows to draw, in order: the selected cohorts, then the counterparty.

    The composite row is drawn whether or not the checklist selected its members.
    That is the reader rule the panel exists for: a week's flow only means something
    against who took the other side, so the other side is never off the page. A
    cohort whose flow columns the frame lacks is skipped, matching every other
    panel's treatment of a missing category.

    The composite's tick label is the bare word and its members go in the hover.
    The tick text sets the figure-level left margin (plotly automargin), which every
    panel in the stack shares: measured at an 857 px figure, the full member label
    took 243 px on gold and 334 px on silver, a quarter to a third of the width from
    every panel, not only this one. The hover has no such cost, so that is where the
    members are named.

    The level columns carry the page's lookback header (cotmetrics.flows: the level
    is the range index the page draws, one week earlier), so without a header a row
    simply has no markers.
    """
    rows = []
    for s in series:
        z = flows.flow_z_col(s.spec)
        if z not in df.columns:
            continue
        rows.append(FlowRow(
            label=s.label,
            hover_label=s.label,
            z=z,
            dnet=flows.flow_col(s.spec),
            dlong=flows.flow_long_col(s.spec),
            dshort=flows.flow_short_col(s.spec),
            thin=flows.flow_thin_col(s.spec),
            level=(flows.flow_from_level_col(s.spec, lookback_header)
                   if lookback_header is not None else None),
            mark=(flows.flow_level_mark_col(s.spec, lookback_header)
                  if lookback_header is not None else None),
        ))
    z = flows.counterparty_flow_z_col()
    if with_counterparty and z in df.columns:
        rows.append(FlowRow(
            label="Counterparty",
            hover_label=_counterparty_label(df),
            z=z,
            dnet=flows.counterparty_flow_col(),
            # The composite is a sum of nets, so it has no legs, no thin flag and
            # no range index of its own; the hover for it stops at the net and the z.
            dlong=None, dshort=None, thin=None, level=None, mark=None,
        ))
    return rows


def _contracts(v):
    return "n/a" if pd.isna(v) else f"{v:+,.0f}"


def _flow_hover_text(df, rows):
    """Every cell's hover, rendered here rather than by a hovertemplate format.

    Under hovermode "x unified" plotly 6.9 printed the heatmap's `%{z:+.2f}` as the
    raw float (cotmetrics docs/design/cot-flows.md, section 7), so the text is built
    in Python and the template is just `%{text}`. None where the z is NaN, so that
    with hoverongaps off the warm-up and the masked weeks say nothing at all rather
    than "n/a".

    The weekday is read from the index rather than written as "Tuesday": the CFTC
    moves the as-of day on holiday weeks (gold's history holds 13 Mondays and a
    Wednesday among 1,045 Tuesdays), and a caption that contradicts the date beside
    it is worse than none. The release day is not stated for the same reason.

    The sentence is deliberately about this cohort against its own history. The Home
    board's ranking is of index-point changes in the Legacy Commercial positioning
    index, a different quantity on a different report, and the two must not read as
    the same thing.

    A marked cell (see _level_markers) adds the level its flow departed from, and
    nothing about what came after it.
    """
    def _bool(v):
        return (not pd.isna(v)) and bool(v)

    weeks = df.attrs.get("flow_level_weeks") or df.attrs.get("lookback_weeks")
    span = f"{weeks}-week range" if weeks else "lookback range"

    out = []
    for row in rows:
        z = df[row.z]
        dnet = df[row.dnet] if row.dnet in df.columns else None
        dlong = df[row.dlong] if row.dlong and row.dlong in df.columns else None
        dshort = df[row.dshort] if row.dshort and row.dshort in df.columns else None
        thin = df[row.thin] if row.thin and row.thin in df.columns else None
        mark = df[row.mark] if row.mark and row.mark in df.columns else None
        level = df[row.level] if row.level and row.level in df.columns else None
        cells = []
        for i, date in enumerate(df.index):
            zv = z.iloc[i]
            if pd.isna(zv):
                cells.append(None)
                continue
            if hasattr(date, "strftime"):
                when = f"{date.strftime('%A')} {date.strftime('%Y-%m-%d')}"
            else:
                when = str(date)
            net = _contracts(dnet.iloc[i]) if dnet is not None else "n/a"
            legs = ""
            if dlong is not None and dshort is not None:
                legs = (f" (longs {_contracts(dlong.iloc[i])}, "
                        f"shorts {_contracts(dshort.iloc[i])})")
            text = (f"{row.hover_label}<br>"
                    f"positions as of {when}<br>"
                    f"net {net} contracts{legs}<br>"
                    f"z {zv:+.2f} vs own {const.FLOW_Z_WEEKS}-week sd")
            if thin is not None and _bool(thin.iloc[i]):
                text += (f"<br>thin: typical week under "
                         f"{const.FLOW_MIN_STD_CONTRACTS} contracts, read the count")
            if mark is not None and level is not None and _bool(mark.iloc[i]) \
                    and not pd.isna(level.iloc[i]):
                text += f"<br>from level {level.iloc[i]:.1f} of the {span}"
            cells.append(text)
        out.append(cells)
    return out


# The marker sits on the cell, so it has to read on cyan, orange and grey alike:
# near-white with a background-coloured edge. Never a palette slot, for the reason
# FLOW_COLORSCALE gives.
FLOW_MARK_COLOR = vc.BRIGHTER_TEXT_COLOR
FLOW_MARK_EDGE = vc.BACKGROUND_COLOR


def _level_markers(fig, df, rows, row, col, facet=False):
    """A triangle on each cell whose active flow left an extreme of the range.

    Up for the top of the range (the prior week's index above
    const.FLOW_LEVEL_HIGH), down for the bottom (below FLOW_LEVEL_LOW); the cell's
    colour already says which way the cohort moved. The marks come from cotmetrics
    (`flows.flow_level_mark_col`), which read the page's own range index, so the
    level a marker points at is the level the Positioning Index panel draws.

    Hover is skipped: the cell under the marker already carries the level in its
    hover, and under hovermode "x unified" a second entry would repeat it.
    Context for reading a cell; nothing here says what followed a flow from an
    extreme, because the cells that motivated the cutoffs were descriptive and on
    gold alone.
    """
    xs, ys, symbols = [], [], []
    for r in rows:
        if not r.mark or r.mark not in df.columns:
            continue
        mark = df[r.mark]
        hit = mark.notna().to_numpy() & (mark.fillna(0).to_numpy() != 0)
        for date, m in zip(df.index[hit], mark[hit]):
            xs.append(date)
            ys.append(r.label)
            symbols.append("triangle-up" if m > 0 else "triangle-down")
    if not xs:
        return fig
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers",
        marker=dict(symbol=symbols, size=6 if facet else 7, color=FLOW_MARK_COLOR,
                    line=dict(width=1, color=FLOW_MARK_EDGE)),
        hoverinfo="skip",
        name="Level marks",
        showlegend=False,
    ), row=row, col=col)
    return fig


def _flow_heatmap(fig, df, rows, row, col, facet=False):
    # The gap is a property of the cell width, not of the trace. Measured at an
    # 857 px figure: the overlay gives 3.7 px a week over the 156-week window, so a
    # 1 px gap still leaves cells; a facet column gives 2.1 px a week (328 px for
    # the column), where 1 px is half of every cell and the panel reads as
    # hairlines; a phone opens on 52 weeks at about 6 px a cell, a sixth of it gap.
    dense = facet or app_utils.is_mobile()
    fig.add_trace(go.Heatmap(
        x=df.index,
        y=[r.label for r in rows],
        z=[df[r.z].astype(float).tolist() for r in rows],
        text=_flow_hover_text(df, rows),
        hovertemplate="%{text}<extra></extra>",
        zmin=-FLOW_Z_CLIP,
        zmax=FLOW_Z_CLIP,
        zmid=0,
        colorscale=FLOW_COLORSCALE,
        xgap=0 if dense else 1,
        ygap=1,
        hoverongaps=False,
        # No colorbar: the stack's 10 px right margin clips one, and the panel title
        # states the scale.
        showscale=False,
        name="Weekly Flow",
        showlegend=False,
    ), row=row, col=col)
    # Category axis, first cohort on top so the rows read in checklist order; a
    # heatmap otherwise stacks its first row at the bottom. In a facet cell the row
    # identity is already the axis title build_facet_figure sets, as it is for the
    # momentum columns, so the tick label would name the cohort twice and cost the
    # narrow column a hundred pixels.
    fig.update_yaxes(row=row, col=col, secondary_y=False, type="category",
                     autorange="reversed", fixedrange=True, showgrid=False,
                     zeroline=False, tickfont=dict(size=9), title=None,
                     showticklabels=not facet)
    return _level_markers(fig, df, rows, row, col, facet=facet)


def get_category_flow_heatmap(fig, df, series, lookback_header, row, col, palette,
                              show_price=False, showlegend=False):
    """Week-over-week net change per cohort, as z against its own trailing sd.

    A heatmap rather than five more lines: the reading is a run of same-sign weeks
    across cohorts, and that is a pattern in a grid, not a crossing of lines. Rows
    are the selected cohorts in report order, then the counterparty composite, which
    is always drawn (see _flow_rows). The z is the cohort's dNet over the trailing
    `const.FLOW_Z_WEEKS`-week sd of its own dNet, computed in cotmetrics.flows; the
    window is fixed there and does not follow the page's lookback, which is why the
    panel title states it.

    `show_price` is accepted and ignored, as the trader-count panel does: a line over
    a heatmap is unreadable, and the price row is a facet context row. The legend is
    still drawn on request so a stack led by this panel carries the category
    entries.

    Colour is polarity, never a palette slot, and the state and z are caption
    vocabulary: nothing here carries a forward return or a verdict.
    """
    rows = _flow_rows(df, series, lookback_header)
    if not rows:
        return fig
    _flow_heatmap(fig, df, rows, row, col)
    return _legend(fig, series, showlegend, palette, show_price=False)


def get_category_flow_row(fig, df, series, lookback_header, row, col, palette,
                          show_price=False, showlegend=False):
    """The facet form: a one-row heatmap for the single cohort in the cell.

    No composite row here. In small multiples every row is one category and the
    counterparty is context, a row of its own under price (facet_context_rows), the
    same way price and open interest are rows rather than overlays.
    """
    rows = _flow_rows(df, series, lookback_header, with_counterparty=False)
    if not rows:
        return fig
    return _flow_heatmap(fig, df, rows, row, col, facet=True)


def get_counterparty_flow_row(fig, df, row, col):
    """The facet context row: the counterparty composite as a one-row heatmap.

    The overlay panel ends with this row; in small multiples it is its own row
    under the category rows, drawn only in the flow column, because the composite
    has a flow and no positioning series for the other panels to draw.
    """
    rows = _flow_rows(df, [])
    if not rows:
        return fig
    return _flow_heatmap(fig, df, rows, row, col, facet=True)


# The strip paints signs, not z: three values, so three exact colours from the same
# polarity pair as the heatmap, with the grey midpoint for "inside one sd".
FLOW_SIGN_COLORSCALE = FLOW_COLORSCALE
FLOW_SPLIT_COLOR = vc.BRIGHTER_TEXT_COLOR
# The split-week ticks ride a fourth lane above the three, at this y.
_SPLIT_LANE_Y = -0.9


def _opinion_specs(df):
    """The three cohorts the state is read from, in the order cotmetrics used.

    From the frame's own roles, not the checklist: the state is a fact about all
    three whether or not the reader switched one off.
    """
    roles = df.attrs.get("flow_roles") or {}
    report = roles.get("report")
    if report not in categories.REPORT_CHOICES:
        return []
    by_key = {s.key: s for s in categories.categories_for(report)}
    specs = [by_key[k] for k in roles.get("opinion") or () if k in by_key]
    return [s for s in specs if flows.flow_sign_col(s) in df.columns]


def has_state_strip(df):
    """True when the frame carries a state to draw: a state-eligible market."""
    return (df is not None and const.FLOW_STATE in df.columns
            and len(_opinion_specs(df)) == 3)


def _strip_hover_text(df, specs):
    states = df[const.FLOW_STATE]
    out = []
    for s in specs:
        z = df[flows.flow_z_col(s)]
        sign = df[flows.flow_sign_col(s)]
        cells = []
        for i in range(len(df)):
            if pd.isna(sign.iloc[i]):
                cells.append(None)
                continue
            v = int(sign.iloc[i])
            zv = z.iloc[i]
            move = ("net buying" if v > 0 else "net selling" if v < 0
                    else "inside one sd")
            state = states.iloc[i]
            head = (f"{state}: a vocabulary label, not a signal"
                    if isinstance(state, str) else "no state this week")
            # No date line: the unified hover's header already carries it, and
            # three lanes over the full history made this the page's largest
            # payload (about half a megabyte on gold).
            cells.append(f"{head}<br>{s.label} {move} (z {zv:+.2f})")
        out.append(cells)
    return out


def get_flow_state_strip(fig, df, row, col):
    """Three lanes, one per opinion cohort, coloured by the sign of its flow.

    Up or down past one sd in the polarity pair, inside one sd in grey, the warm-up
    blank. The weeks whose state has the three cohorts all active and split (the
    gold doc's mixed signs; `flows.DIVERGENT_FLOW_STATES`) get a tick in a thin lane
    above the three. The plan asked for a line-only box around the week; in the
    running app a facet column gives one to two pixels a week, where a one-pixel
    outline is the whole cell and the box painted over the very lanes it was meant
    to frame. BROAD_ACCUM and BROAD_LIQUID get no tick: everyone moving together is
    visible in the lanes without help.

    Lanes read top-down in the opinion order cotmetrics recorded, which is the
    order the cohort rows above them take. No tick labels in a facet cell, for the
    reason the flow rows give; the hover names the lane.

    The state is caption vocabulary. Its pre-registered test failed, so the hover
    and the page caption say so beside every name.
    """
    specs = _opinion_specs(df)
    if len(specs) != 3 or const.FLOW_STATE not in df.columns:
        return fig
    z = []
    for s in specs:
        z.append([None if pd.isna(v) else float(v) for v in df[flows.flow_sign_col(s)]])
    fig.add_trace(go.Heatmap(
        x=df.index, y=[0, 1, 2], z=z,
        text=_strip_hover_text(df, specs),
        hovertemplate="%{text}<extra></extra>",
        zmin=-1, zmax=1, zmid=0,
        colorscale=FLOW_SIGN_COLORSCALE,
        xgap=0, ygap=1, hoverongaps=False, showscale=False,
        name="Flow state", showlegend=False,
    ), row=row, col=col)

    split = df[const.FLOW_STATE].isin(flows.DIVERGENT_FLOW_STATES).to_numpy()
    if split.any():
        dates = df.index[split]
        fig.add_trace(go.Scatter(
            x=dates, y=[_SPLIT_LANE_Y] * len(dates), mode="markers",
            marker=dict(symbol="line-ns", size=7,
                        line=dict(width=2, color=FLOW_SPLIT_COLOR)),
            hoverinfo="skip", name="Split weeks", showlegend=False,
        ), row=row, col=col)

    fig.update_yaxes(row=row, col=col, type="linear", range=[2.6, -1.4],
                     fixedrange=True, showgrid=False, zeroline=False,
                     showticklabels=False, title=None)
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
    # Appended last: the picker persists plot ids per session, in this order.
    "flow": (f"Weekly Flow z ({const.FLOW_Z_WEEKS}w sd, clipped +/-{FLOW_Z_CLIP:g})",
             get_category_flow_heatmap, SECONDARY_NEVER),
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
    # Present because shared_range indexes every id in facet mode and KeyErrors
    # otherwise. The range it computes is ignored: the flow builders take no
    # y_range, since a heatmap's colour scale is its scale and is already shared.
    "flow": (lambda s, h: [flows.flow_z_col(s)], True, None),
}

# In small multiples each row holds one series, so a change reads better as a column
# anchored on zero than as a line. Overlay keeps the line form, where five bar series
# would occlude one another.
_FACET_BUILDERS = {
    "momentum": get_category_momentum_columns,
    "flow": get_category_flow_row,
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

# The two flow context rows, drawn only in the flow column (see build_facet_figure).
FLOW_CONTEXT_ROWS = ("counterparty", "state")


def counterparty_members(df):
    """The counterparty's member specs whose flow the frame carries, in role order."""
    roles = (df.attrs.get("flow_roles") or {}) if df is not None else {}
    report = roles.get("report")
    if report not in categories.REPORT_CHOICES:
        return []
    by_key = {s.key: s for s in categories.categories_for(report)}
    return [by_key[k] for k in roles.get("counterparty") or ()
            if k in by_key and flows.flow_col(by_key[k]) in df.columns]


def needs_counterparty_row(df, series):
    """A composite row in small multiples, unless it would repeat a row on the page.

    Where the counterparty is one cohort (the report defaults, and most TFF markets)
    and that cohort is already a row, a composite row is the same cells again two
    rows further down; that cohort's own row is labelled as the counterparty instead
    (`facet_row_label`). A multi-member composite (gold's Producer/Merchant plus
    Swap Dealers), or a single member the checklist switched off, gets its row.
    """
    if df is None or flows.counterparty_flow_z_col() not in df.columns:
        return False
    members = counterparty_members(df)
    shown = {s.key for s in series}
    return not (len(members) == 1 and members[0].key in shown)


def facet_row_label(df, s):
    """A category row's axis title, naming it the counterparty where it is the one."""
    members = counterparty_members(df)
    if len(members) == 1 and members[0].key == s.key:
        return f"{s.label}<br>(counterparty)"
    return s.label


def facet_context_rows(plots, show_price, frame, series=()):
    """The non-category rows: the flow column's counterparty row and state strip,
    then price, then open interest with Net Positions.

    Price and open interest are context for the categories rather than categories
    themselves, and in the overlay view both ride a second y-axis. Two scales on one
    plot align arbitrarily, which invents a correlation the data does not contain,
    so here each gets its own row against the same x. Faceting has already produced
    the row structure, so this costs nothing.

    With the flow panel selected, the counterparty is on the page: as its own
    composite row directly under the cohorts it is the other side of, or, where it
    is a single cohort already drawn, as that cohort's row (needs_counterparty_row).
    The state strip follows it, on a state-eligible market only. Price and open
    interest come last, so the bottom row carries every column's dates. `frame`
    is required: the rows depend on the market, and a shape computed without it
    would leave an empty row where the market has no composite or no state.
    """
    rows = []
    if "flow" in plots:
        if needs_counterparty_row(frame, series):
            rows.append(("counterparty", flows.counterparty_flow_z_col(),
                         "Counterparty", None))
        if has_state_strip(frame):
            rows.append(("state", const.FLOW_STATE, "Flow state", None))
    if show_price:
        rows.append(("price", const.CLOSING_PRICE, "Price", vc.CATEGORY_PRICE_SLOT))
    if "net_pos" in plots:
        rows.append(("oi", const.OPEN_INTEREST, "Open Interest", vc.CATEGORY_OI_SLOT))
    return rows


def facet_shape(plots, series, show_price, frame):
    """Grid shape for the faceted view: a row per category, a column per panel."""
    rows = len(series) + len(facet_context_rows(plots, show_price, frame, series))
    return max(1, rows), max(1, len(plots))


def facet_titles(plots, series, show_price, frame):
    """Panel names on the top row only; every other cell is unlabelled.

    Category identity rides on the y-axis title of the first column instead, so it is
    stated once per row rather than repeated in every cell.
    """
    rows, cols = facet_shape(plots, series, show_price, frame)
    titles = []
    for r in range(rows):
        for c in range(cols):
            titles.append(labels_for(plots).get(plots[c], "") if r == 0 else "")
    return titles


def facet_specs(plots, series, show_price, frame):
    rows, cols = facet_shape(plots, series, show_price, frame)
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
    _, cols = facet_shape(plots, series, show_price, df)

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
            label_axis(facet_row_label(df, s) if "flow" in plots else s.label, r, c)

    flow_col = plots.index("flow") + 1 if "flow" in plots else None
    for i, (row_id, column, label, slot) in enumerate(
            facet_context_rows(plots, show_price, df, series)):
        if column not in df.columns:
            continue
        r = len(series) + 1 + i
        if row_id in FLOW_CONTEXT_ROWS:
            # Only the flow column has something to draw here. The other cells
            # keep their x-axis (the bottom row carries the date labels for its
            # column when price and open interest are off) and lose their y ticks
            # and grid so they read as empty.
            for c in range(1, cols + 1):
                if c == flow_col:
                    draw = (get_counterparty_flow_row if row_id == "counterparty"
                            else get_flow_state_strip)
                    draw(fig, df, r, c)
                else:
                    # plotly.js draws only the subplots some trace references, so
                    # a cell left with no trace loses its axes, the row label
                    # label_axis puts on column 1, and, in the bottom row, the
                    # column's dates. A trace with no points keeps the cell.
                    fig.add_trace(go.Scatter(
                        x=[df.index[0], df.index[-1]], y=[None, None],
                        mode="markers", hoverinfo="skip", showlegend=False,
                        name=""), row=r, col=c)
                    fig.update_yaxes(row=r, col=c, showticklabels=False,
                                     showgrid=False, zeroline=False, fixedrange=True)
                label_axis(label, r, c)
            continue
        for c in range(1, cols + 1):
            add_trace_to_all(fig, df, column, r, c, label, palette[slot], 0,
                             opacity=0.9)
            fig.update_yaxes(row=r, col=c, gridcolor=vc.GRID_COLOR, zeroline=False,
                             fixedrange=True, range=_fit_range(df, [column]))
            label_axis(label, r, c)
    return fig
