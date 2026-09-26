"""The Flow view on /categories: price, the weekly cohort flow, and the level.

Three full-width panels on one time axis, the view proposed in cotmetrics
`docs/analysis/2026-09-26-cot-view-proposed-gold.png` and scoped in the "Scope,
restated" block of `docs/handoffs/2026-09-26-cot-flow-states-cross-universe.md`:

1. price with open interest (dotted, second axis);
2. a heatmap with one row per cohort and one column per report week, each cell the
   cohort's net change that week over its own 52-week standard deviation of weekly
   changes, with a triangle where the cohort's positioning index is in its top or
   bottom decile that week;
3. the same rows' positioning index, as lines.

The rows are cotmetrics' (`attrs["flow_rows"]`, from `flows.flow_rows`): every
category is a row, except that Producer/Merchant and Swap Dealers are one Commercials
row on the four precious metals. The level is the page's tuned per-symbol lookback,
the same range index the Positioning Index panel draws. Nothing here computes a flow,
a z, an index or a marker; it draws the frame `CotIndexer.get_category_data` returns.

The flow state (the gold study's eight names) appears only in a cell's hover, beside
the words "a vocabulary label, not a signal": its pre-registered test failed the
crucible gauntlet on 2026-09-26, and nothing in this view carries a forward return.

Store-free, like category_traces, so every builder is testable under CI's empty
COTDATA_STORE.
"""

import re
from collections import namedtuple

import cotmetrics.categories as categories
import cotmetrics.constants as const
import cotmetrics.flows as flows
import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_colors import DIM_TEXT
from components.plot_layout import visible_weeks
from components.plot_traces import add_trace_to_all

# Display clip only: the hover still prints the real z. Past three sigma the eye
# cannot rank the shades, and letting one outlier week own the scale would wash
# every ordinary week to the midpoint.
FLOW_Z_CLIP = 3.0

# The mockup shows 104 weeks; a phone keeps the app's own narrower window.
FLOW_VIEW_WEEKS = 104

# Price is what the other two panels are read against, so it gets the most height.
FLOW_VIEW_ROW_HEIGHTS = [0.36, 0.32, 0.32]
FLOW_VIEW_SPECS = [[{"secondary_y": True}], [{"secondary_y": False}],
                   [{"secondary_y": False}]]

VOCABULARY_NOTE = "a vocabulary label, not a signal"


def _composite_over(rgba, hex_bg):
    """The opaque colour an rgba() paints when laid over an opaque hex background.

    A colorscale stop's alpha would blend with the paper, not the panel, so the
    translucent grey the app uses for "nothing to say" is flattened first.
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


# Polarity, never a palette slot: every slot already names a cohort or a series.
# The app's validated diverging pair, buying one way and selling the other, with a
# grey midpoint so runs of mild same-sign weeks stay visible.
FLOW_COLORSCALE = [
    [0.0, vc.CATEGORY_DIVERGING_DOWN],
    [0.5, _composite_over(DIM_TEXT, vc.BACKGROUND_COLOR)],
    [1.0, vc.CATEGORY_DIVERGING_UP],
]

# The triangles sit on coloured cells, so they need to read on both ends of the
# scale and on the grey: near-white with a background-coloured edge.
FLOW_MARK_COLOR = vc.BRIGHTER_TEXT_COLOR
FLOW_MARK_EDGE = vc.BACKGROUND_COLOR

# One drawn row, resolved to the frame's columns and to a colour for its level line.
FlowRow = namedtuple("FlowRow", "key label z dnet dlong dshort thin index color dash")


def flow_view_weeks():
    return min(FLOW_VIEW_WEEKS, visible_weeks())


def flow_rows(df, series, lookback_header):
    """The rows to draw: cotmetrics' rows for this market, kept where selected.

    `series` is the checklist's selection (category_traces.category_series). A
    merged row is drawn when any of its members is selected, and takes the first
    selected member's colour for its level line; the checklist names categories,
    and a reader who unticks Swap Dealers on gold has not asked to lose the
    Commercials row. A row whose z column is missing is skipped.
    """
    selected = {s.key: s for s in series}
    out = []
    for key, label, prefix, members in df.attrs.get("flow_rows") or ():
        picked = [selected[k] for k in members if k in selected]
        if not picked:
            continue
        spec = flows.FlowRow(key, label, prefix, tuple(members))
        z = flows.flow_z_col(spec)
        if z not in df.columns:
            continue
        index = categories.index_col(spec, lookback_header)
        out.append(FlowRow(
            key=key, label=label, z=z,
            dnet=flows.flow_col(spec),
            dlong=flows.flow_long_col(spec),
            dshort=flows.flow_short_col(spec),
            thin=flows.flow_thin_col(spec),
            index=index if index in df.columns else None,
            color=picked[0].color,
            dash=picked[0].dash if len(members) == 1 else None,
        ))
    return out


def _level_weeks(df):
    return df.attrs.get("lookback_weeks")


def _span(df):
    weeks = _level_weeks(df)
    return f"{weeks}-week range" if weeks else "lookback range"


def flow_view_titles(df):
    weeks = _level_weeks(df)
    span = f"{weeks}w range" if weeks else "range"
    return [
        "Price and Open Interest",
        # Short enough to fit over a narrow panel: the title is the only key to the
        # triangles on the figure itself.
        (f"Weekly Flow z (own {const.FLOW_Z_WEEKS}w sd)  "
         f"\u25b2 top / \u25bc bottom decile, {span}"),
        f"Positioning Index ({span})",
    ]


def _contracts(v):
    return "n/a" if pd.isna(v) else f"{v:+,.0f}"


def _col(df, name):
    return df[name] if name and name in df.columns else None


def hover_text(df, rows):
    """Every cell's hover, built here because under hovermode "x unified" plotly
    printed a heatmap's `%{z:+.2f}` as the raw float.

    None where the z is NaN (the warm-up and the masked weeks), so with hoverongaps
    off those cells say nothing. The weekday is read from the date: the CFTC moves
    the as-of day on holiday weeks. The state, where cotmetrics names one, closes
    every cell's hover with the words that say what it is.
    """
    states = _col(df, const.FLOW_STATE)
    span = _span(df)
    out = []
    for row in rows:
        z, dnet = df[row.z], _col(df, row.dnet)
        dlong, dshort = _col(df, row.dlong), _col(df, row.dshort)
        thin, index = _col(df, row.thin), _col(df, row.index)
        marks = flows.level_marks(index) if index is not None else None
        cells = []
        for i, date in enumerate(df.index):
            zv = z.iloc[i]
            if pd.isna(zv):
                cells.append(None)
                continue
            when = (f"{date.strftime('%A')} {date.strftime('%Y-%m-%d')}"
                    if hasattr(date, "strftime") else str(date))
            text = (f"{row.label}<br>positions as of {when}<br>"
                    f"net {_contracts(dnet.iloc[i]) if dnet is not None else 'n/a'} "
                    f"contracts")
            if dlong is not None and dshort is not None:
                text += (f" (longs {_contracts(dlong.iloc[i])}, "
                         f"shorts {_contracts(dshort.iloc[i])})")
            text += f"<br>z {zv:+.2f} vs own {const.FLOW_Z_WEEKS}-week sd"
            if thin is not None and not pd.isna(thin.iloc[i]) and bool(thin.iloc[i]):
                text += (f"<br>thin: typical week under "
                         f"{const.FLOW_MIN_STD_CONTRACTS} contracts, read the count")
            if marks is not None and not pd.isna(marks.iloc[i]) and marks.iloc[i] != 0:
                where = "top" if marks.iloc[i] > 0 else "bottom"
                text += (f"<br>index {index.iloc[i]:.1f}, {where} decile of the "
                         f"{span}")
            if states is not None and isinstance(states.iloc[i], str):
                text += f"<br>state {states.iloc[i]}: {VOCABULARY_NOTE}"
            cells.append(text)
        out.append(cells)
    return out


def _heatmap(fig, df, rows, row, col):
    fig.add_trace(go.Heatmap(
        x=df.index,
        y=[r.label for r in rows],
        z=[df[r.z].astype(float).tolist() for r in rows],
        text=hover_text(df, rows),
        hovertemplate="%{text}<extra></extra>",
        zmin=-FLOW_Z_CLIP, zmax=FLOW_Z_CLIP, zmid=0,
        colorscale=FLOW_COLORSCALE,
        # No gap between weeks: at full width a one-pixel gap a week read as a
        # comb rather than as runs of colour. One pixel between cohorts.
        xgap=0, ygap=1,
        hoverongaps=False,
        # No colorbar: the stack's 10 px right margin clips one; the title says
        # what the colour is.
        showscale=False,
        name="Weekly Flow",
        showlegend=False,
    ), row=row, col=col)
    # First row on top, in report order; a heatmap otherwise stacks upward.
    fig.update_yaxes(row=row, col=col, type="category", autorange="reversed",
                     fixedrange=True, showgrid=False, zeroline=False,
                     tickfont=dict(size=9), title=None)


def _markers(fig, df, rows, row, col):
    """Triangles from cotmetrics' `flows.level_marks` on each row's own index.

    Hover skipped: the cell under the triangle names the index in its hover, and
    under hovermode "x unified" a second entry would repeat it.
    """
    xs, ys, symbols = [], [], []
    for r in rows:
        if r.index is None:
            continue
        marks = flows.level_marks(df[r.index])
        hit = marks.notna().to_numpy() & (marks.fillna(0).to_numpy() != 0)
        for date, m in zip(df.index[hit], marks[hit]):
            xs.append(date)
            ys.append(r.label)
            symbols.append("triangle-up" if m > 0 else "triangle-down")
    if not xs:
        return
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers",
        marker=dict(symbol=symbols, size=7, color=FLOW_MARK_COLOR,
                    line=dict(width=1, color=FLOW_MARK_EDGE)),
        hoverinfo="skip", name="Level marks", showlegend=False,
    ), row=row, col=col)


def _fit(df, cols, weeks):
    """The y-range of `cols` over the last `weeks` rows, padded a tenth each side."""
    window = df.iloc[max(0, len(df) - weeks):]
    vals = pd.concat([window[c] for c in cols if c in window.columns], axis=0).dropna()
    if vals.empty:
        return None
    lo, hi = float(vals.min()), float(vals.max())
    pad = (hi - lo) * 0.10 or abs(hi) * 0.10 or 1.0
    return [lo - pad, hi + pad]


def build_flow_view(fig, df, series, lookback_header, palette):
    """Fill a three-row figure made with FLOW_VIEW_SPECS and FLOW_VIEW_ROW_HEIGHTS.

    The index panel is shaded at the decile cutoffs, as the key to the triangles in
    the panel above it. Returns the figure; the page sets the shared x window with
    `set_window`.
    """
    weeks = flow_view_weeks()
    if const.CLOSING_PRICE in df.columns:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, 1, 1, "Price",
                         palette[vc.CATEGORY_PRICE_SLOT], 1, opacity=0.95)
        fig.update_yaxes(title="Price", row=1, col=1, secondary_y=False,
                         gridcolor=vc.GRID_COLOR, zeroline=False, fixedrange=True,
                         range=_fit(df, [const.CLOSING_PRICE], weeks))
    if const.OPEN_INTEREST in df.columns:
        add_trace_to_all(fig, df, const.OPEN_INTEREST, 1, 1, "Open Interest",
                         palette[vc.CATEGORY_OI_SLOT], 0, secondary=True,
                         opacity=0.6, dash="dot")
        fig.update_yaxes(title="OI", row=1, col=1, secondary_y=True,
                         showgrid=False, zeroline=False, fixedrange=True,
                         range=_fit(df, [const.OPEN_INTEREST], weeks))

    rows = flow_rows(df, series, lookback_header)
    if rows:
        _heatmap(fig, df, rows, 2, 1)
        _markers(fig, df, rows, 2, 1)

    for r in rows:
        if r.index is None:
            continue
        add_trace_to_all(fig, df, r.index, 3, 1, r.label, r.color, 1,
                         showlegend=True, dash=r.dash)
    fig.update_yaxes(title="index", row=3, col=1, range=[0, 100], fixedrange=True,
                     gridcolor=vc.GRID_COLOR, zeroline=False)
    for y0, y1 in ((const.FLOW_LEVEL_HIGH, 100), (0, const.FLOW_LEVEL_LOW)):
        fig.add_hrect(y0=y0, y1=y1, row=3, col=1, line_width=0, layer="below",
                      fillcolor=vc.GRID_COLOR, opacity=0.35)
    return fig


def set_window(fig, df):
    """Open the shared x-axis on the last flow_view_weeks() reports."""
    start = df.index[max(0, len(df) - flow_view_weeks())]
    fig.update_xaxes(range=[start, df.index[-1] + pd.Timedelta(days=14)])
    return fig
