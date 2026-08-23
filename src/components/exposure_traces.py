"""The Exposure figure: dollar positioning against the same selection's own price.

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

#: The same three plus volatility, which goes LAST rather than beside the price panel it
#: is a property of. Two reasons. The crosshair binds to the bottom axis, so a panel
#: added anywhere else renumbers the companions and every row reference with them. And
#: the top three are a positioning story read top to bottom; volatility is the market
#: condition underneath it, which is where a footing belongs.
#:
#: The subject gives up the least it can and the companions give up the most, because a
#: companion is read for sign and shape and survives being short.
PANEL_HEIGHTS_VOL = (0.23, 0.40, 0.21, 0.16)
FIGURE_PX_VOL = 800

#: Annualised for display only. `sigma_daily` is what `risk_usd` is built from, and it
#: is what the arithmetic needs, but nobody reads 1.3% a day. cotmetrics keeps
#: TRADING_DAYS for exactly this reason and says so: it exists because humans read
#: annualised vol and cannot read daily vol.
ANNUALISE = exposure.TRADING_DAYS ** 0.5


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

#: Where the figure records which axis its bottom panel ended up on, so the page can ask
#: rather than assume. The row count is not fixed: the volatility panel appears only
#: when the aggregate can supply one, and a constant would be wrong half the time.
XREF_META = "crosshair_xref"

#: What the browser needs to re-fit the axes to a zoomed window, recorded in the figure
#: rather than duplicated in JavaScript. Plotly's own `autorange` spans ALL of a trace's
#: data rather than the part on screen (measured: zooming x to two years and asking for
#: autorange returns the identical full-history range), so a zoomed panel keeps an axis
#: fitted to a series it is no longer showing. The browser has to do the fitting, and
#: these are the rules it has to follow to reach the same answer this module would.
REFIT_META = "refit"

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
                 leg=exposure.LEG_SPEC, parts=None, scale=SCALE_LEVEL,
                 numeraire=None, single=False, contracts=None):
    """Two panels: the selection's own price, and its dollar positioning.

    `frame` is `cotmetrics.exposure.AggregateExposure.frame`; `composite` is the
    matching `composite_price_index`. Both may be empty, and an empty figure with its
    axes intact beats an exception in a callback.
    """
    # The volatility panel appears only when the aggregate can supply one. Older
    # cotmetrics has no such column, and an aggregate holding nothing has no holdings to
    # weight a volatility by, so both cases fall back to the three-panel figure rather
    # than drawing an empty register.
    vol = None
    if frame is not None and not frame.empty and "sigma_weighted" in frame.columns:
        if frame["sigma_weighted"].notna().any():
            vol = frame["sigma_weighted"]
    rows = 4 if vol is not None else 3
    heights = PANEL_HEIGHTS_VOL if vol is not None else PANEL_HEIGHTS
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=list(heights))

    # `shared_xaxes` makes the BOTTOM axis the master and every axis above it a slave,
    # and Plotly silently ignores a range set on a slave. The range buttons belong on
    # the top panel, which is the only place they render above the figure rather than
    # between two panels, so the top panel has to be the master or they do nothing at
    # all. Measured before this line existed: clicking 3Y left the chart on Max, and a
    # zoom request fitted the y axes to a window the x axis never went to, which drew
    # every panel clipped against a range it was not showing.
    for row in range(2, rows + 1):
        fig.update_xaxes(matches="x", row=row, col=1)
    fig.update_xaxes(matches=None, row=1, col=1)

    if frame is None or frame.empty:
        fig.update_layout(height=FIGURE_PX, paper_bgcolor=background,
                          plot_bgcolor=background,
                          annotations=[dict(
                              text="No week has a value for every market selected.",
                              showarrow=False, xref="paper", yref="paper",
                              x=0.5, y=0.5, font=dict(color=vc.TEXT_COLOR))])
        return fig

    ranked = scale == SCALE_RANK
    # What the money is denominated in, needed by the hovers as well as the axis.
    base = "oz gold" if numeraire == exposure.NUMERAIRE_GOLD else "USD"
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
            # An equal-weight composite of one market is that market's price, and a
            # legend calling it a composite sends a reader looking for a construction
            # that is not there.
            name="Market price" if single else "Set composite",
            mode="lines", line=dict(color=palette[3], width=1.4),
            hovertemplate="%{x|%b %d, %Y}<br>"
                          + ("Price" if single else "Composite")
                          + " %{y:.1f}<extra></extra>"),
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

    # ── the other lens, under the level it is there to be read against ───────
    #
    # The SAME leg's raw contract count, on the SAME expanding percentile, drawn only
    # on the percentile scale and only for a single market. Both restrictions are load
    # bearing. Contracts and dollars share no axis, so on the level scale this would be
    # a second y-axis inviting a reader to measure the space between two incommensurable
    # units; and contracts do not add across markets, which is the whole reason this
    # page converts to dollars in the first place.
    #
    # It is the same colour as the level, dotted and dimmed, because it is not another
    # series: it is the same crowd through the other lens. Two colours would say they
    # are two things worth comparing on the merits rather than one thing measured twice.
    if ranked and contracts is not None and not contracts.empty:
        aligned = break_gaps(frame.index, contracts.reindex(frame.index).to_numpy())
        fig.add_trace(go.Scatter(
            x=frame.index, y=aligned,
            name="Contracts %ile", mode="lines", line_shape="hv",
            line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, LENS_ALPHA), width=1),
            hovertemplate="%{y:,.0f}th percentile, contracts<extra></extra>"),
            row=2, col=1)
        # The GAP is the object, not the second line. Both series are weekly over
        # twenty years, so two lines of the same shape in one small panel are a thicket
        # the eye cannot separate; shading between them turns "where do they part" into
        # something readable at a glance. A duplicate of the level carries the fill so
        # the level itself keeps its own hover and legend entry, and draws on top.
        fig.add_trace(go.Scatter(
            x=frame.index, y=break_gaps(frame.index, scaled.to_numpy()),
            mode="lines", line_shape="hv", line=dict(width=0), fill="tonexty",
            fillcolor=hex_to_rgba(leg_colour, LENS_FILL_ALPHA),
            showlegend=False, hoverinfo="skip"), row=2, col=1)

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
            + unit_scale(frame[unit])[1] + f" {base}<extra></extra>" if ranked else
            "%{x|%b %d, %Y}<br>%{y:,.1f}" + suffix
            + f" {base}<br>" + "%{customdata:.0f}th percentile of its own history"
            + "<extra></extra>"
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
                            else "%{y:,.1f}" + suffix + f" {base}<extra>")
                           + exposure.LEG_LABELS[part_leg] + "</extra>")),
            row=3, col=1)
        drew_companion = True

    if drew_companion:
        fig.add_hline(y=50 if ranked else 0, row=3, col=1, line=dict(
            color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, ZERO_LINE_ALPHA), width=1))

    # The numeraire belongs in the title, not just on the axis. It was reading
    # "Equities - USD daily risk" over a chart whose y axis said "oz gold (k)".
    measure = (UNIT_LABELS[unit].replace("USD ", "") + " in oz gold"
               if numeraire == exposure.NUMERAIRE_GOLD else UNIT_LABELS[unit])
    title = " ".join(p for p in [set_label, "-", measure] if p).strip(" -")
    fig.update_layout(
        height=FIGURE_PX_VOL if vol is not None else FIGURE_PX,
        paper_bgcolor=background, plot_bgcolor=background,
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
    # Parenthesised, because the two numeraires want opposite word orders otherwise:
    # "USD m" is the established form and "m USD" is not, while "k oz gold" is right and
    # "oz gold k" is not. "USD (m)" and "oz gold (k)" are both fine and are one rule.
    usd = "Percentile" if ranked else (f"{base} ({suffix})" if suffix else base)
    price_axis = price_axis_type(composite)
    # Plotly's default on a log axis puts a tick at every digit, which in a panel this
    # short (26% of the figure, about 180px) renders as a column of stacked single
    # digits. Three a decade is enough to read a 15x range and few enough to label in
    # full. See log_ticks for why the labels are spelled out rather than left to `D2`.
    ticks = log_ticks(composite) if price_axis == "log" else None
    fig.update_yaxes(title_text=f"Index in {base} (=100)", row=1, col=1,
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

    # ── what the money is riding on ──────────────────────────────────────────
    #
    # The second factor of the drawn unit. `risk = notional x sigma` market by market,
    # the price panel above already carries the first factor, and without this one the
    # reader can see dollar risk move without the position moving and has no way to find
    # out why.
    #
    # Its own slot. It was drawn in the price slot first, on the argument that
    # volatility is a property of the price; two panels apart that reads as the same
    # line drawn twice rather than as a shared subject, and green is spoken for in four
    # of the five palettes. It then borrowed Open Interest's slot, which was free only
    # because this figure does not draw open interest, and taught a reader the wrong
    # association everywhere else in the app.
    #
    # So the palettes gained a sixth slot and volatility owns it. See
    # `viz_config.PALETTE_SLOTS`, which is the one place the slot meanings are written
    # down.
    if vol is not None:
        shown = (exposure.expanding_pct_rank(vol, MIN_RANK_PERIODS) if ranked
                 else vol * ANNUALISE * 100)
        fig.add_trace(go.Scatter(
            x=frame.index, y=break_gaps(frame.index, shown.to_numpy()),
            name="Volatility" if single else "Volatility (held-weighted)",
            mode="lines", line_shape="hv",
            line=dict(color=hex_to_rgba(palette[VOL_PALETTE_SLOT], VOL_ALPHA),
                      width=1.2),
            # Each scale carries the other quantity, the same rule the level and the
            # percentile follow above.
            customdata=(vol * ANNUALISE * 100).to_numpy() if ranked
            else exposure.expanding_pct_rank(vol, MIN_RANK_PERIODS).to_numpy(),
            hovertemplate=(
                "%{y:,.0f}th percentile<br>%{customdata:,.1f}% annualised"
                if ranked else
                "%{y:,.1f}% annualised<br>%{customdata:,.0f}th percentile")
            + "<extra>Volatility</extra>"), row=4, col=1)
        if ranked:
            fig.update_yaxes(range=[0, 100], row=4, col=1)
            fig.add_hline(y=50, row=4, col=1, line=dict(
                color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, ZERO_LINE_ALPHA), width=1))
        fig.update_yaxes(title_text="Percentile" if ranked else "Ann. vol (%)",
                         row=4, col=1, title_font=dict(size=10))

    # ── zooming ──────────────────────────────────────────────────────────────
    #
    # The buttons the rest of the app already offers, on the TOP panel's axis, which is
    # where they render above the figure rather than between two panels.
    fig.update_xaxes(rangeselector=dict(
        buttons=[dict(count=n, label=f"{n}Y", step="year", stepmode="backward")
                 for n in RANGE_YEARS] + [dict(step="all", label="Max")],
        bgcolor=vc.BLUE_BACKGROUND, activecolor=vc.BLUE_BACKGROUND,
        font=dict(color=vc.BRIGHTER_TEXT_COLOR, size=10),
        y=1.0, yanchor="bottom", x=1.0, xanchor="right"), row=1, col=1)

    # The bottom axis is where the crosshair goes and the row count is not fixed, so the
    # figure records which one it is instead of leaving the page to count panels.
    #
    # `refit` is for the browser. Only the axes that are FITTED to their data are listed:
    # on the percentile scale the exposure, companion and volatility panels are pinned to
    # 0-100 on purpose, so re-fitting them to a zoomed window would let the band at 10
    # and 90 drift off a fixed scale that exists to stay fixed.
    # The price panel is fitted on BOTH scales, because it is a price panel either way.
    # The panels below it are fitted only on the level scale: on the percentile scale
    # they are pinned to 0-100 on purpose, and re-fitting them to a zoomed window would
    # let the band at 10 and 90 drift off a scale that exists to stay put.
    refit = ["yaxis"] + ([] if ranked
                         else [f"yaxis{n}" for n in range(2, rows + 1)])
    fig.update_layout(meta={
        XREF_META: f"x{rows}",
        REFIT_META: {"axes": refit, "price_axis": "yaxis",
                     "log_ratio_min": LOG_RATIO_MIN, "pad": REFIT_PAD},
    })
    return fig


#: A contributor pointing the other way from the total. Kept here rather than in the
#: page because it is a drawing rule and the page's table renderer reads it: the same
#: pair of alphas now colours the in-cell contribution bar that replaced the horizontal
#: bar figure this module used to build. Opposite is one variable, and the hue is
#: already spending itself on which leg this is.
AGAINST_ALPHA = 0.30

#: The other lens, dimmed against the level it sits under. Bright enough to follow
#: across a 20-year panel, faint enough that the drawn unit stays the subject.
LENS_ALPHA = 0.55

#: The wedge between the two lenses. Faint: it is a difference, and a difference drawn
#: as loudly as the thing it is a difference OF becomes the subject.
LENS_FILL_ALPHA = 0.16

#: Volatility, dimmed. It is context for the panels above rather than a subject.
VOL_ALPHA = 0.75

#: Volatility's own palette slot. Not borrowed: see `viz_config.PALETTE_SLOTS`.
VOL_PALETTE_SLOT = 5

#: The range buttons, in years. The same ladder the rest of the app offers, so a reader
#: who learned it on another page does not have to learn it again here.
RANGE_YEARS = (1, 2, 3, 5, 10, 15)

#: Breathing room above and below a re-fitted range, as a fraction of its span. Plotly's
#: own autorange pads by about this much, and a panel that changed padding when it was
#: zoomed would read as the data having moved.
REFIT_PAD = 0.05
WITH_ALPHA = 0.85


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
