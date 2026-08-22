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
import math

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

#: What the middle and bottom panels plot.
#:
#: SCALE_RANK exists because SCALE_LEVEL cannot be fixed by an axis. The exposure series
#: is signed and crosses zero, so a log axis is not merely unhelpful there, it is
#: undefined. And the breadth it would be asked to fix is real rather than cosmetic:
#: on Metals since 1989 the median absolute weekly figure grew 48x in risk and 55x in
#: notional between the 1990s and the 2020s, because dollar figures carry the price
#: level. No monotone rescaling of a signed series makes 1991 and 2026 legible together.
#:
#: The percentile does, by being stationary by construction. It is the same expanding
#: rank the headline already quotes, so the two cannot disagree.
SCALE_LEVEL = "level"
SCALE_RANK = "rank"

SCALE_LABELS = {SCALE_LEVEL: "Level", SCALE_RANK: "%ile"}

#: Below this high-to-low ratio the price panel stays linear. A log axis earns its
#: keep by making equal PERCENTAGE moves equal distances, which only shows up over a
#: wide range; under 3x the two look alike and log only costs the reader a familiar
#: axis. Metals runs 15.2x since 1989 and is the case this exists for; Currencies runs
#: 1.4x and is the case it protects.
LOG_RATIO_MIN = 3.0

BAND_ALPHA = 0.16
FILL_ALPHA = 0.30
ZERO_LINE_ALPHA = 0.55

#: Price, subject, companions. The subject keeps the largest share because it is the
#: only panel with a band and a percentile behind it; the other two are read for shape
#: and for sign, which needs less room than reading a level against an envelope.
PANEL_HEIGHTS = (0.26, 0.46, 0.28)
FIGURE_PX = 700


#: The OTHER Legacy legs, drawn in their own panel beneath the one that is the subject.
#:
#: The distinction this map exists to hold, because it is easy to get backwards.
#: Commercials against the SPECULATOR TOTAL is an accounting identity: measured across
#: all 45 priceable markets and every week in the store, `Comm_net + Spec_net` is
#: 0.000000. Drawing those two is one series and its reflection.
#:
#: Commercials against Large and Small SEPARATELY is not. Three series with one linear
#: constraint means any two determine the third, and it means no ONE of them determines
#: another: you cannot recover Large from Commercials. So each line is individually
#: informative, and the constraint that ties them is only visible when all three are on
#: the page. That is the conventional COT presentation and it is conventional for a
#: reason.
#:
#: Hence: the companion panel never draws the subject's own mirror, and always draws the
#: legs the subject does not contain. Large and Small are the pair worth separating on
#: their own account, sitting on opposite sides 59% of weeks with a level correlation of
#: -0.26.
COMPANION_LEGS = {
    exposure.LEG_COMM: (exposure.LEG_LARGE, exposure.LEG_SMALL),
    exposure.LEG_SPEC: (exposure.LEG_LARGE, exposure.LEG_SMALL),
    exposure.LEG_LARGE: (exposure.LEG_COMM, exposure.LEG_SMALL),
    exposure.LEG_SMALL: (exposure.LEG_COMM, exposure.LEG_LARGE),
}

#: The legs a leg is literally the SUM of, which is a different relation from
#: COMPANION_LEGS above and must not be collapsed into it.
#:
#: Every leg has companions; only Speculators has parts. Large and Small are drawn
#: beneath Commercials because they are the rest of the report, not because they are
#: what Commercials is made of, and a sentence calling them its "halves" would be
#: describing an arithmetic that does not exist. This map is what the composition line
#: reads; COMPANION_LEGS is what the figure reads.
LEG_PARTS = {exposure.LEG_SPEC: (exposure.LEG_LARGE, exposure.LEG_SMALL)}

#: The axis the crosshair is bound to: the bottom panel's, whichever that is. Named here
#: rather than spelled "x3" at the call site so adding a panel cannot leave the page
#: drawing a crosshair against an axis that has moved.
CROSSHAIR_XREF = "x3"

PART_WIDTH = 1.0
PART_ALPHA = 0.75


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
                 leg=exposure.LEG_SPEC, parts=None, scale=SCALE_LEVEL):
    """Two panels: the set's own price composite, and its dollar positioning.

    `frame` is `cotmetrics.exposure.AggregateExposure.frame`; `composite` is the
    matching `composite_price_index`. Both may be empty, and an empty figure with its
    axes intact beats an exception in a callback.
    """
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=list(PANEL_HEIGHTS))

    if frame is None or frame.empty:
        fig.update_layout(height=FIGURE_PX, paper_bgcolor=background,
                          plot_bgcolor=background,
                          annotations=[dict(
                              text="No week has a value for every market in this set.",
                              showarrow=False, xref="paper", yref="paper",
                              x=0.5, y=0.5, font=dict(color=vc.TEXT_COLOR))])
        return fig

    ranked = scale == SCALE_RANK
    rank_column = UNIT_RANK_COLUMN[unit]
    values = frame[rank_column] if ranked else frame[unit]
    divisor, suffix = (1.0, "") if ranked else unit_scale(values)
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
    # On the percentile scale the band IS flat, at the two percentiles it is made of,
    # which is the point: the line moves in and out of a fixed range instead of the
    # range chasing the line. Computing the expanding quantile of a rank series would
    # give almost the same two lines the long way round, and wobbling ones at that.
    if ranked:
        flat = pd.Series(BAND_LOW * 100, index=frame.index)
        low, high = flat, pd.Series(BAND_HIGH * 100, index=frame.index)
    else:
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
        # No fill on the percentile scale. Filling to zero there would shade the
        # distance to the BOTTOM of the distribution, and zero is a floor rather than
        # the neutral the fill means on a signed series.
        fill=None if ranked else "tozeroy",
        fillcolor=None if ranked else hex_to_rgba(leg_colour, FILL_ALPHA),
        # Each scale's hover carries the OTHER quantity, so neither view hides what the
        # other one is for: the level cannot answer "is this a lot" on its own, and the
        # percentile cannot say how much money that is.
        customdata=(frame[unit] / unit_scale(frame[unit])[0]).to_numpy() if ranked
        else frame[rank_column].to_numpy(),
        hovertemplate=(
            "%{x|%b %d, %Y}<br>%{y:,.0f}th percentile<br>%{customdata:,.1f}"
            + unit_scale(frame[unit])[1] + " USD<extra></extra>" if ranked else
            "%{x|%b %d, %Y}<br>%{y:,.1f}" + suffix
            + " USD<br>%{customdata:.0f}th percentile of its own history<extra></extra>"
        )),
        row=2, col=1)

    # Zero is neutral on a signed series and the floor of the distribution on a rank,
    # so the line that marks it is drawn at 50 there instead: the median week.
    fig.add_hline(y=50 if ranked else 0, row=2, col=1, line=dict(
        color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, ZERO_LINE_ALPHA), width=1))

    # ── the other legs, in their own panel ───────────────────────────────────
    #
    # Their own panel rather than overlaid on the subject, which is where they used to
    # sit. Two reasons, and the second is the one that decided it. They are often an
    # order of magnitude apart from the subject and from each other, so sharing its
    # axis squashed them into a flat line against the bottom of the band. And the
    # subject's panel carries a band and a percentile that describe the subject ALONE,
    # so a companion crossing that band read as a statement about it that nothing on the
    # page had made.
    drew_companion = False
    for part_leg, part in (parts or {}).items():
        if part is None or part.empty:
            continue
        aligned = part.reindex(frame.index)
        # Each companion ranked against ITS OWN history, not the subject's. They are
        # different quantities on different scales, which is why they have their own
        # panel; ranking them against the subject would put them back on its axis by
        # another route.
        if ranked:
            aligned = exposure.expanding_pct_rank(aligned, MIN_RANK_PERIODS)
        fig.add_trace(go.Scatter(
            x=frame.index,
            y=break_gaps(frame.index, (aligned / divisor).to_numpy()),
            name=exposure.LEG_LABELS[part_leg], mode="lines", line_shape="hv",
            line=dict(color=hex_to_rgba(palette[LEG_PALETTE_SLOT[part_leg]],
                                        PART_ALPHA),
                      width=PART_WIDTH),
            hovertemplate=(("%{y:,.0f}th percentile<extra>" if ranked
                            else "%{y:,.1f}" + suffix + " USD<extra>")
                           + exposure.LEG_LABELS[part_leg] + "</extra>")),
            row=3, col=1)
        drew_companion = True

    if drew_companion:
        fig.add_hline(y=50 if ranked else 0, row=3, col=1, line=dict(
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
    usd = "Percentile" if ranked else (f"USD {suffix}" if suffix else "USD")
    price_axis = price_axis_type(composite)
    # Plotly's default on a log axis puts a tick at every digit, which in a panel this
    # short (26% of the figure, about 180px) renders as a column of stacked single
    # digits. Three a decade is enough to read a 15x range and few enough to label in
    # full. See log_ticks for why the labels are spelled out rather than left to `D2`.
    ticks = log_ticks(composite) if price_axis == "log" else None
    fig.update_yaxes(title_text="Index (=100 at start)", row=1, col=1,
                     title_font=dict(size=10), type=price_axis,
                     tickmode="array" if ticks else None,
                     tickvals=ticks,
                     ticktext=[f"{v:,.0f}" for v in ticks] if ticks else None)
    if ranked:
        fig.update_yaxes(range=[0, 100], row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=3, col=1)
    fig.update_yaxes(title_text=usd, row=2, col=1, title_font=dict(size=10))
    # Same units and the same divisor as the panel above, deliberately, so a companion
    # can be read against the subject by eye. Only the AXIS RANGE differs, which is the
    # whole reason the panel is separate.
    fig.update_yaxes(title_text=usd, row=3, col=1, title_font=dict(size=10))
    return fig


#: Height per contributor row, plus the chrome. A set is 4 to 9 markets, so this figure
#: is small by construction and sizing it from the row count keeps the bars a constant
#: thickness rather than fatter for a small set.
CONTRIB_ROW_PX = 26
CONTRIB_CHROME_PX = 46
CONTRIB_MIN_PX = 120

#: A contributor pointing the other way from the total. It is drawn in the same colour
#: at lower opacity rather than in a second hue, because "opposite" is one variable and
#: the palette slot is already spending itself on which leg this is.
AGAINST_ALPHA = 0.30
WITH_ALPHA = 0.85


def build_contributions_figure(values, *, unit=UNIT_NOTIONAL, palette,
                               leg=exposure.LEG_SPEC,
                               background=vc.BACKGROUND_COLOR):
    """One week of the total, broken into the markets that made it.

    A sum says nothing about whether five markets agreed or one market carried it, and
    on the real equity complex one market is 59.5% of the gross speculator total while
    another leans the other way. This is the panel that says so.

    Horizontal bars rather than a stacked area over time. The question is about the week
    the reader is looking at, a stack of signed values is ambiguous in every plotting
    library, and five market histories over 24 years is unreadable whatever the shape.
    """
    fig = go.Figure()
    if values is None or len(values) == 0:
        fig.update_layout(height=CONTRIB_MIN_PX, paper_bgcolor=background,
                          plot_bgcolor=background,
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        return fig

    divisor, suffix = unit_scale(values)
    total = float(sum(v for v in values if v == v))
    base = palette[LEG_PALETTE_SLOT.get(leg, 0)]
    # Smallest first, because a horizontal bar axis counts upward from the bottom and
    # the reader should meet the largest contributor at the top.
    ordered = list(values.items())[::-1]
    names = [n for n, _ in ordered]
    scaled = [v / divisor for _, v in ordered]
    colours = [hex_to_rgba(base, WITH_ALPHA if (v >= 0) == (total >= 0)
                           else AGAINST_ALPHA)
               for _, v in ordered]

    fig.add_trace(go.Bar(
        x=scaled, y=names, orientation="h", marker=dict(color=colours),
        hovertemplate="%{y}<br>%{x:,.1f}" + suffix + " USD<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR,
                                                   ZERO_LINE_ALPHA), width=1))
    fig.update_layout(
        height=max(CONTRIB_MIN_PX, len(values) * CONTRIB_ROW_PX + CONTRIB_CHROME_PX),
        paper_bgcolor=background, plot_bgcolor=background, showlegend=False,
        margin=dict(l=140, r=16, t=6, b=28),
        font=dict(color=vc.TEXT_COLOR, size=11), bargap=0.35)
    fig.update_xaxes(showgrid=True, gridcolor=vc.GRID_COLOR, zeroline=False,
                     title_text=f"USD {suffix}" if suffix else "USD",
                     title_font=dict(size=10))
    fig.update_yaxes(showgrid=False, zeroline=False, automargin=True)
    return fig


def price_axis_type(composite):
    """"log" or "linear" for the price panel, decided by the series rather than set.

    Log ONLY where the composite is strictly positive. It is an equal-weight mean of
    ratio-rebased unadjusted prices, and unadjusted prices are not guaranteed positive:
    WTI settled at -37.63 on 2020-04-20. No class composite goes non-positive in the
    store today, because that one day is averaged against three other energy markets,
    but a narrower Energies selection could. Plotly drops non-positive points from a log
    axis SILENTLY, so the guard is the difference between a linear chart and a chart
    with a hole nothing announces.
    """
    if composite is None or composite.empty:
        return "linear"
    low, high = float(composite.min()), float(composite.max())
    if low <= 0:
        return "linear"
    return "log" if high / low >= LOG_RATIO_MIN else "linear"


def log_ticks(composite):
    """Tick values at 1, 2 and 5 per decade across the series' range, or None.

    Plotly's own `dtick="D2"` puts the ticks in the right places and labels the minor
    ones with a bare mantissa, so a 200 renders as "2" directly under a "100". On a
    panel whose y values are index levels that is not a shorthand, it is a wrong number.
    Explicit values and explicit text cost eight lines and remove the ambiguity.

    Returns None where fewer than three ticks land inside the range, which is a range
    too narrow to be on a log axis at all; the caller falls back to Plotly's default.
    """
    if composite is None or composite.empty:
        return None
    low, high = float(composite.min()), float(composite.max())
    if low <= 0 or high <= low:
        return None
    values = []
    exponent = math.floor(math.log10(low))
    while 10 ** exponent <= high:
        for mantissa in (1, 2, 5):
            value = mantissa * 10 ** exponent
            if low <= value <= high:
                values.append(value)
        exponent += 1
    return values if len(values) >= 3 else None
