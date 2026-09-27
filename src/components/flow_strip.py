"""The Commercial flow strip on the /analysis Positioning Index panel.

One strip under the panel's three Legacy lines: the Commercial leg's net change each
week over its own 52-week standard deviation of weekly changes, blue when commercials
net buy and red when they net sell, clipped at 3. Commercial because every setup in the
app is triggered by the Commercial index at an extreme, and on equities it is the only
leg the gate reads (`cotmetrics.utils.is_setup`): the strip shows the week-by-week move
behind the leg the setups are judged on.

The Commercial line's hover carries the same week's flow beside its index value,
because under hovermode "x unified" a heatmap cell reports only when the cursor is on
the strip itself.

A one-line note names what the legs mean where that differs: that equity setups read
Commercials only, and how retail (Non-Reportable) behaves on the market, from
cotmetrics' `flow_roles` table.

Everything is read from `CotIndexer.get_commercial_flow_data`; nothing here computes a
flow or a z. Store-free, so every builder is testable under CI's empty COTDATA_STORE.
Nothing here carries a forward return: the flow-state test failed the crucible gauntlet
on 2026-09-26, and single-cohort weekly moves were a genuine null on 42 markets.
"""

import re

import cotmetrics.constants as const
import cotmetrics.flows as flows
import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_traces import COMM_LABEL, SML_LABEL

LEG = const.COMM

# Display clip only: the hover prints the real z.
FLOW_Z_CLIP = 3.0

# The strip lives inside the index panel, below its zero: edges on the index axis. The
# axis widens to show it; a "flow z" tick at the strip names it.
STRIP_EDGES = [-15.0, -4.0]
INDEX_RANGE = [-17.0, 100.0]
STRIP_TICK = (STRIP_EDGES[0] + STRIP_EDGES[1]) / 2
INDEX_TICKS = [STRIP_TICK, 0, 20, 50, 80, 100]
INDEX_TICK_TEXT = ["flow z", "0", "20", "50", "80", "100"]


def _composite_over(rgba, hex_bg):
    """The opaque colour an rgba() paints over an opaque hex background."""
    m = re.match(r"rgba?\(([^)]*)\)", str(rgba))
    parts = [float(x) for x in m.group(1).split(",")] if m else []
    if len(parts) < 3:
        return hex_bg
    alpha = parts[3] if len(parts) > 3 else 1.0
    h = str(hex_bg).lstrip("#")
    bg = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    out = [round(b + (c - b) * alpha) for c, b in zip(parts[:3], bg)]
    return "#{:02x}{:02x}{:02x}".format(*out)


# Polarity, not identity: a true diverging scale anchored at zero, zero barely lifted
# off the panel background so only real moves carry colour, one sd muted, three sd
# saturated. Stops at -3, -1, 0, +1, +3.
FLOW_ZERO = _composite_over("rgba(255, 255, 255, 0.06)", vc.BACKGROUND_COLOR)
FLOW_COLORSCALE = [
    [0.0, "#ff4b3e"],
    [1 / 3, "#8a3129"],
    [0.5, FLOW_ZERO],
    [2 / 3, "#285c8e"],
    [1.0, "#3fa0ff"],
]

RETAIL_WORDS = {
    "spec-like": "moves with price here",
    "neutral": "does not move with price here",
    "cp-like": "moves against price here",
}


def panel_note(df):
    """One short line, or "" when there is nothing market-specific to say."""
    parts = []
    if df.attrs.get("is_equity"):
        parts.append(f"Equities: setups read {COMM_LABEL} only")
    roles = df.attrs.get("flow_roles") or {}
    behaves = RETAIL_WORDS.get(roles.get("retail_behaves"))
    if behaves:
        parts.append(f"retail ({SML_LABEL}) {behaves}")
    return ", ".join(parts)


def _flow_text(df, i, contracts=True):
    z = df[flows.flow_z_col(LEG)].iloc[i]
    if pd.isna(z):
        return None
    text = f"flow z {z:+.2f}"
    dnet = df[flows.flow_col(LEG)].iloc[i] if flows.flow_col(LEG) in df.columns else None
    if contracts and dnet is not None and not pd.isna(dnet):
        text += f" (net {dnet:+,.0f} contracts)"
    return text


def strip_hover(df):
    cells = []
    for i in range(len(df)):
        flow = _flow_text(df, i, contracts=False)
        if flow is None:
            cells.append(None)
            continue
        text = f"{COMM_LABEL} {flow} vs own {const.FLOW_Z_WEEKS}-week sd"
        dnet = df[flows.flow_col(LEG)].iloc[i]
        if not pd.isna(dnet):
            text += f"<br>net {dnet:+,.0f} contracts"
        cells.append(text)
    return [cells]


def line_hover(df, x, y):
    """The Commercial line's hover per point: its index, then that week's flow.

    `x` and `y` are the line trace's own points; the flow is looked up by date. None
    where the index is NaN, so the warm-up stays silent; the index alone where the
    week has no readable flow.
    """
    pos = {d: i for i, d in enumerate(df.index)}
    out = []
    for d, v in zip(x, y):
        if v is None or pd.isna(v):
            out.append(None)
            continue
        text = f"{v:.0f}"
        i = pos.get(pd.Timestamp(d))
        flow = _flow_text(df, i) if i is not None else None
        if flow:
            text += f" · {flow}"
        out.append(text)
    return out


def _panel_axis(fig, row, col):
    return fig.get_subplot(row, col).yaxis.plotly_name.replace("yaxis", "y")


def add_flow_strip(fig, df, row, col):
    """Add the strip, the Commercial line's flow hover and the note to an index panel.

    `df` is `CotIndexer.get_commercial_flow_data(asset)`; None or empty adds
    nothing. Call after `get_index_plot`, which draws the Commercial line and sets the
    0 to 100 axis this widens.
    """
    if df is None or df.empty or flows.flow_z_col(LEG) not in df.columns:
        return fig

    fig.add_trace(go.Heatmap(
        x=df.index, y=STRIP_EDGES,
        z=[df[flows.flow_z_col(LEG)].astype(float).tolist()],
        text=strip_hover(df), hovertemplate="%{text}<extra></extra>",
        zmin=-FLOW_Z_CLIP, zmax=FLOW_Z_CLIP, zmid=0,
        colorscale=FLOW_COLORSCALE, opacity=1, xgap=0,
        hoverongaps=False, showscale=False,
        name=f"{COMM_LABEL} flow z", showlegend=False,
    ), row=row, col=col, secondary_y=False)
    fig.update_yaxes(row=row, col=col, secondary_y=False, range=INDEX_RANGE,
                     tickvals=INDEX_TICKS, ticktext=INDEX_TICK_TEXT)

    axis = _panel_axis(fig, row, col)
    for trace in fig.data:
        if trace.name == COMM_LABEL and trace.type.startswith("scatter") \
                and (trace.yaxis or "y") == axis:
            trace.text = line_hover(df, list(trace.x), list(trace.y))
            trace.hovertemplate = "%{text}"

    note = panel_note(df)
    if note:
        fig.add_annotation(
            text=note, showarrow=False, xanchor="left", yanchor="top",
            x=0.005, y=0.995, xref="x domain", yref="y domain",
            font=dict(size=9, color=vc.TEXT_COLOR), row=row, col=col)
    return fig
