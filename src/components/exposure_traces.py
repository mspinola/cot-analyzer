"""The Aggregate Exposure figure: a set's dollar positioning against its own price.

Pure figure logic, so every rule here is testable without a store or a running app.
`cotmetrics.exposure` computes the numbers; this decides how they are drawn.

Two panels sharing an x axis, and the shape is deliberately the printed reference's,
because the shape was the good part. Four of its defects are fixed rather than
reproduced, and each fix is a rule below rather than a preference:

- **The reference matches the subject.** The source puts the S&P 500 alone above a total
  aggregating ES, NQ, YM and RTY. Here the top panel is `composite_price_index` over the
  same set the bottom panel sums, so the two cannot come apart.
- **The extremes are marked.** On a chart whose subject is crowding, nothing in the
  source said whether today's figure was unusual, leaving a reader to eyeball twenty
  years. The exposure panel carries an expanding 10th/90th percentile envelope, so
  "unusual" is visible rather than inferred.
- **Weekly data is drawn as weekly.** COT is one observation a week. A smooth line
  across it implies intra-week detail that does not exist, so both series step.
- **The publication lag is said out loud.** Positioning is as-of Tuesday and published
  the following Friday. Plotted at the as-of date against a price line, it reads as
  though the position was knowable when the price printed. This module plots as-of,
  which is what the number IS, and the page's caption states the gap. That matters more
  here than in a static PDF because these charts sit next to setup gates.
"""
import cotmetrics.exposure as exposure
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components.plot_colors import hex_to_rgba

#: The two units the bottom panel can draw, and what each one is FOR.
#:
#: Notional is summable and NOT comparable: it makes ES dwarf orange juice permanently
#: because the ES market is larger. Risk is both. Notional is offered anyway because it
#: is the quantity a reader can price intuitively, and because within ONE set the
#: comparison it cannot support is not being asked for.
UNIT_NOTIONAL = "notional_usd"
UNIT_RISK = "risk_usd"

UNIT_LABELS = {
    UNIT_NOTIONAL: "USD notional",
    UNIT_RISK: "USD daily risk",
}
UNIT_RANK_COLUMN = {
    UNIT_NOTIONAL: "notional_pct_rank",
    UNIT_RISK: "risk_pct_rank",
}
UNIT_NOTES = {
    UNIT_NOTIONAL: ("contracts x point value x price. Summable across markets, but not "
                    "comparable between them: a bigger market carries bigger numbers."),
    UNIT_RISK: ("notional x daily volatility. The unit to compare on, and the one a "
                "vol-targeting book holds constant while it sits at its target."),
}

#: Percentiles drawn as the extreme envelope. Deliberately the same 10/90 the rest of
#: the app treats as the edge of normal, so a reader carries one threshold between pages.
BAND_LOW = 0.10
BAND_HIGH = 0.90

#: Weeks of history before a percentile or a band says anything. Two years.
MIN_RANK_PERIODS = 104

#: The app-wide palette-slot convention (see components/plot_traces.py): 0 Commercials,
#: 1 Large Specs, 2 Small Traders, 3 Price, 4 Open Interest. Drawing a speculator series
#: in the Commercial red would contradict every other page in the app, and the reader
#: carries that mapping between them.
#:
#: LEG_SPEC takes the Large Spec slot rather than a fifth colour: it is Large plus Small
#: and Large dominates it in every market in the universe, so borrowing Large's colour
#: says more about what the line is than a new hue would.
LEG_PALETTE_SLOT = {
    exposure.LEG_COMM: 0,
    exposure.LEG_LARGE: 1,
    exposure.LEG_SPEC: 1,
    exposure.LEG_SMALL: 2,
}

#: Weeks between two observations before the line is BROKEN rather than joined. The
#: aggregate's completeness rule leaves real interior holes (12 of them on the equity
#: complex, the longest 168 days) where one member's history stops and restarts, usually
#: an exchange migration splitting a CFTC code. A step line drawn straight across one
#: says the level held for five months, which is a claim the data does not make.
MAX_JOIN_DAYS = 14

BAND_ALPHA = 0.16
FILL_ALPHA = 0.30
ZERO_LINE_ALPHA = 0.55

PANEL_HEIGHTS = (0.34, 0.66)
FIGURE_PX = 620


def break_gaps(index, values, max_join_days=MAX_JOIN_DAYS):
    """Insert a NaN wherever two observations are further apart than one COT week.

    Plotly joins whatever it is given, so a hole reads as a level that held. Returning
    the values with a gap punched in is the only way to say "no observation" on a line
    chart, since the alternative, drawing markers, is unreadable at 1,100 weeks.
    """
    import numpy as np
    out = list(values)
    stamps = pd.DatetimeIndex(index)
    for i in range(1, len(stamps)):
        if (stamps[i] - stamps[i - 1]).days > max_join_days:
            out[i - 1] = np.nan
    return out


def unit_scale(values):
    """A divisor and a suffix, so an axis reads $55bn rather than 55,387,601,984.

    Chosen from the largest absolute value actually drawn rather than fixed, because the
    same page draws equity-index notional in tens of billions and a single soft in tens
    of millions, and a hard-coded unit makes one of the two unreadable.
    """
    peak = max((abs(v) for v in values if v == v), default=0.0)
    # `>= 10 x divisor`, not `>= divisor`, so the axis carries at least two digits. A
    # billion-dollar peak in billions is an axis labelled 0, 0.5, 1; in millions it is
    # 0, 250, 500, 750, 1000, which is the same number and a readable scale.
    for divisor, suffix in ((1e12, "tn"), (1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if peak >= divisor * 10:
            return divisor, suffix
    return 1.0, ""


def build_figure(frame, composite, *, unit=UNIT_NOTIONAL, colors, palette,
                 background=vc.BACKGROUND_COLOR, leg_label="", set_label="",
                 leg=exposure.LEG_SPEC):
    """Two panels: the set's own price composite, and its dollar positioning.

    `frame` is `cotmetrics.exposure.AggregateExposure.frame`; `composite` is the
    matching `composite_price_index`. Both may be empty, and an empty figure with its
    axes intact beats an exception in a callback.
    """
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=list(PANEL_HEIGHTS))

    if frame is None or frame.empty:
        fig.update_layout(height=FIGURE_PX, paper_bgcolor=background,
                          plot_bgcolor=background,
                          annotations=[dict(
                              text="No week has a value for every market in this set.",
                              showarrow=False, xref="paper", yref="paper",
                              x=0.5, y=0.5, font=dict(color=vc.TEXT_COLOR))])
        return fig

    values = frame[unit]
    divisor, suffix = unit_scale(values)
    scaled = values / divisor
    leg_colour = palette[LEG_PALETTE_SLOT.get(leg, 0)]

    # ── the reference ────────────────────────────────────────────────────────
    if composite is not None and not composite.empty:
        fig.add_trace(go.Scatter(
            x=composite.index,
            y=break_gaps(composite.index, composite.to_numpy()),
            name="Set composite",
            mode="lines", line=dict(color=palette[3], width=1.4),
            hovertemplate="%{x|%b %d, %Y}<br>Composite %{y:.1f}<extra></extra>"),
            row=1, col=1)

    # ── the extremes, under the level so the level stays readable ────────────
    low = exposure.expanding_quantile(values, BAND_LOW, MIN_RANK_PERIODS) / divisor
    high = exposure.expanding_quantile(values, BAND_HIGH, MIN_RANK_PERIODS) / divisor
    fig.add_trace(go.Scatter(
        x=frame.index, y=high.to_numpy(), name=f"{int(BAND_HIGH * 100)}th pct",
        mode="lines", line_shape="hv", line=dict(width=0), showlegend=False,
        hoverinfo="skip"), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=frame.index, y=low.to_numpy(), name="Usual range",
        mode="lines", line_shape="hv", line=dict(width=0), fill="tonexty",
        fillcolor=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, BAND_ALPHA),
        hoverinfo="skip"), row=2, col=1)

    # ── the level ────────────────────────────────────────────────────────────
    #
    # One trace, filled to zero, rather than the source's two-colour split. The sign is
    # already carried by which side of the zero line the trace sits on, and colouring it
    # as well spends a second channel on a variable that has not asked for one.
    fig.add_trace(go.Scatter(
        x=frame.index, y=break_gaps(frame.index, scaled.to_numpy()),
        name=leg_label or "Net exposure",
        mode="lines", line_shape="hv", line=dict(color=leg_colour, width=1.4),
        fill="tozeroy", fillcolor=hex_to_rgba(leg_colour, FILL_ALPHA),
        customdata=frame[UNIT_RANK_COLUMN[unit]].to_numpy(),
        hovertemplate=("%{x|%b %d, %Y}<br>%{y:,.1f}" + suffix
                       + " USD<br>%{customdata:.0f}th percentile of its own history"
                       + "<extra></extra>")),
        row=2, col=1)

    fig.add_hline(y=0, row=2, col=1, line=dict(
        color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, ZERO_LINE_ALPHA), width=1))

    title = " ".join(p for p in [set_label, "-", UNIT_LABELS[unit]] if p).strip(" -")
    fig.update_layout(
        height=FIGURE_PX, paper_bgcolor=background, plot_bgcolor=background,
        margin=dict(l=64, r=16, t=28, b=36),
        font=dict(color=vc.TEXT_COLOR, size=11),
        hovermode="x unified",
        legend=dict(orientation="h", yref="container", y=1.0, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        title=dict(text=title, x=0, xanchor="left", font=dict(size=11,
                                                             color=colors.dim)),
    )
    fig.update_xaxes(showgrid=True, gridcolor=vc.GRID_COLOR, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=vc.GRID_COLOR, zeroline=False)
    fig.update_yaxes(title_text="Index (=100 at start)", row=1, col=1,
                     title_font=dict(size=10))
    fig.update_yaxes(title_text=f"USD {suffix}" if suffix else "USD", row=2, col=1,
                     title_font=dict(size=10))
    return fig
