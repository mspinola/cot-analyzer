"""The Speculator series and its flow-z strip, on the /analysis Positioning Index panel.

"Scope, restated v2" (cotmetrics `docs/handoffs/2026-09-26-cot-flow-states-cross-
universe.md`): one role series per market. The panel already draws the Legacy
Commercial, Large Spec and Small index; this adds

* **Speculator**: the positioning index of the cohorts cotmetrics' `flow_roles` table
  measures as this market's speculator (Managed Money on most physicals, Asset Manager
  plus Leveraged Funds in most currencies, Asset Manager on equity index), at the same
  per-symbol lookback as the other three lines;
* **one strip** under the lines: the speculator net's weekly change over its own 52-week
  standard deviation, blue buying and red selling, clipped at 3;
* **Retail** as a label rather than a line: Legacy Small IS Non-Reportable, so a Retail
  line would sit exactly on the Small line. The panel says how retail behaves on this
  market instead (moves with price, does not, or moves against it, from the same table).

Where the table names no speculator (ZT) there is no line and no strip, and the label
says Large Spec, Legacy's Non-Commercial, stands in.

Everything is read from `CotIndexer.get_speculator_data`; nothing here computes a role,
an index or a z. Store-free, so every builder is testable under CI's empty
COTDATA_STORE. Nothing here carries a forward return: the flow-state test failed the
crucible gauntlet on 2026-09-26.
"""

import re

import cotmetrics.constants as const
import cotmetrics.flows as flows
import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_traces import LRG_LABEL, SML_LABEL

SPEC = const.SPECULATOR

# Display clip only: the hover prints the real z. Past three sigma the eye cannot rank
# the shades, and one outlier week would wash every ordinary week to the midpoint.
FLOW_Z_CLIP = 3.0

# The strip lives inside the index panel, below its zero: edges on the index axis.
# The axis is widened to show it and its ticks stay on the 0 to 100 scale.
STRIP_EDGES = [-15.0, -4.0]
INDEX_RANGE = [-17.0, 100.0]
# The strip is named by a tick at its own height rather than by a legend entry.
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


# Polarity, not identity: a true diverging scale anchored at zero, where zero is barely
# lifted off the panel background so only real moves carry colour, one sd is a muted
# blue or red, and three sd is saturated. Stops at -3, -1, 0, +1, +3.
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


def _index_col(df):
    header = df.attrs.get("lookback_header")
    return flows.index_col(SPEC, header) if header is not None else None


def panel_note(df):
    """One short line: who the speculator is, and how retail behaves here.

    Short on purpose: it sits inside the panel above the lines, and the panel is a
    third of the page width in a three-column stack.
    """
    roles = df.attrs.get("flow_roles") or {}
    label = df.attrs.get("speculator_label")
    parts = [f"Speculator = {label}" if label
             else f"No speculator role here; {LRG_LABEL} stands in"]
    behaves = RETAIL_WORDS.get(roles.get("retail_behaves"))
    if behaves:
        parts.append(f"retail ({SML_LABEL}) {behaves}")
    return ", ".join(parts)


def strip_hover(df, label):
    z = df[flows.flow_z_col(SPEC)]
    dnet = df[flows.flow_col(SPEC)] if flows.flow_col(SPEC) in df.columns else None
    cells = []
    for i in range(len(df)):
        zv = z.iloc[i]
        if pd.isna(zv):
            cells.append(None)
            continue
        text = f"Speculator flow z {zv:+.2f} vs own {const.FLOW_Z_WEEKS}-week sd"
        if dnet is not None and not pd.isna(dnet.iloc[i]):
            text += f"<br>net {dnet.iloc[i]:+,.0f} contracts ({label})"
        cells.append(text)
    return [cells]


def line_hover(df, idx_col):
    """The Speculator line's hover per week: its index, then that week's flow.

    Under hovermode "x unified" a heatmap cell reports only when the cursor is on
    the strip itself, so hovering the lines never showed the week's move. Carrying
    the flow z and the net contracts on the line puts level and move in one box
    at any date. None where the index is NaN (the lookback warm-up), so that week
    stays silent as before; a readable index with no z yet shows the index alone.
    """
    idx = df[idx_col]
    z = df[flows.flow_z_col(SPEC)] if flows.flow_z_col(SPEC) in df.columns else None
    dnet = df[flows.flow_col(SPEC)] if flows.flow_col(SPEC) in df.columns else None
    out = []
    for i in range(len(df)):
        v = idx.iloc[i]
        if pd.isna(v):
            out.append(None)
            continue
        text = f"{v:.0f}"
        if z is not None and not pd.isna(z.iloc[i]):
            text += f" \u00b7 flow z {z.iloc[i]:+.2f}"
            if dnet is not None and not pd.isna(dnet.iloc[i]):
                text += f" (net {dnet.iloc[i]:+,.0f} contracts)"
        out.append(text)
    return out


def add_speculator(fig, df, row, col, palette):
    """Add the Speculator line, its flow strip and the panel note to an index panel.

    `df` is `CotIndexer.get_speculator_data(asset, lookback)`; None or empty adds
    nothing. Call after `get_index_plot`, which sets the 0 to 100 axis this widens.
    """
    if df is None or df.empty:
        return fig
    label = df.attrs.get("speculator_label")
    idx = _index_col(df)
    z_col = flows.flow_z_col(SPEC)
    has_line = bool(label) and idx in df.columns
    has_strip = bool(label) and z_col in df.columns

    if has_line:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[idx], mode="lines",
            name=f"Speculator ({label})", legendgroup="speculator",
            line=dict(color=palette[vc.SPECULATOR_SLOT], width=2.2),
            text=line_hover(df, idx), hovertemplate="%{text}", showlegend=True,
        ), row=row, col=col, secondary_y=False)

    if has_strip:
        fig.add_trace(go.Heatmap(
            x=df.index, y=STRIP_EDGES,
            z=[df[z_col].astype(float).tolist()],
            text=strip_hover(df, label), hovertemplate="%{text}<extra></extra>",
            zmin=-FLOW_Z_CLIP, zmax=FLOW_Z_CLIP, zmid=0,
            colorscale=FLOW_COLORSCALE, opacity=1, xgap=0,
            hoverongaps=False, showscale=False,
            name="Speculator flow z", showlegend=False,
        ), row=row, col=col, secondary_y=False)
        fig.update_yaxes(row=row, col=col, secondary_y=False, range=INDEX_RANGE,
                         tickvals=INDEX_TICKS, ticktext=INDEX_TICK_TEXT)

    fig.add_annotation(
        text=panel_note(df), showarrow=False, xanchor="left", yanchor="top",
        x=0.005, y=0.995, xref="x domain", yref="y domain",
        font=dict(size=9, color=vc.TEXT_COLOR), row=row, col=col)
    return fig
