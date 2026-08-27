"""The crowdedness board: every market against four windows, on one screen.

The Strip answers "where does each market sit in ONE window, and what does the model
say about it". This board answers a different question: how crowded is the same leg
against its trailing 3-month, 6-month, 12-month and full-history range, side by side.
The cross-window PATTERN on a row is the signal this page exists for, and it only
exists visually if the four readings sit in one eye-span. The printed reports this
replaces draw one panel per window, so a market's four readings are never on screen
together and the pattern has to be reconstructed from memory.

Three named patterns, worth listing because the caption teaches them:

- Persistent extreme: hot in all four windows. Crowded by any yardstick.
- Fresh push: hot at 3 months, fading as the window lengthens. Recent positioning
  build with room by historical standards.
- Unwinding: mild at 3 months, hot at 12 months and history. An old extreme that has
  stopped extending.

**Colour is the VALUE here, not the verdict, and that is a deliberate departure from
the rule the Strip and the Heatmap share.** Their rule (colour follows the row's setup
state) exists because a single positioning index only means something in the company
of the other legs the gate reads. This board is not drawing the gate's question: all
four cells are the same leg, and the object of interest is the multi-window shape,
which dies if three of four cells are washed to neutral because the model's one
window has no verdict. The bridge back to the app's vocabulary is the small verdict
marker at the row's left edge, drawn only when the selected model has a full setup on
its own window, in the same bull/bear colours the Strip uses. The two encodings can
disagree on one row, and that is the interesting case: a market crowded on every
window with no verdict marker is a market whose OTHER legs are blocking the gate.

The poles reuse the app's bull/bear palette slots rather than a new pair, because the
axis is the same one every other page draws: high index = Commercials accumulated =
bullish extreme, low = distributed = bearish. A neutral cell fades toward the
background so the crowded ends carry the ink, which is the board's whole reading
strategy: sweep for saturated cells, then read the row.

Everything here is a pure function over `MarketRead` values plus a colour set, so the
layout is testable without a store, a palette file or a browser.
"""

from dataclasses import dataclass

import cotmetrics.constants as const
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_colors import hex_to_rgba, relative_luminance

# The four windows, in weeks. None means the full history the store holds for that
# market, which differs per market (stitched CFTC codes included), so the actual
# week count rides on the row and the hover says it.
WINDOW_WEEKS = (13, 26, 52, None)
WINDOW_LABELS = ("3M", "6M", "12M", "Full")
# Prose for hovers and the caption, index-aligned with WINDOW_WEEKS.
WINDOW_DESC = ("13-week window", "26-week window", "52-week window", "full history")

# How the rows are ordered. Values are session-persisted control state, so they are a
# wire format: renaming one silently resets a returning reader's choice.
ORDER_CLASS = "class"
ORDER_FLAT = "flat"
ORDER_ALPHA = "alpha"

# Row geometry, matching the Strip's so the two boards read at the same density.
ROW_PX = 22
HEADER_BAND_ALPHA = 0.07
ROW_RULE_ALPHA = 0.10
TOP_CHROME_PX = 34
BOTTOM_CHROME_PX = 24
# Same measurement and reasoning as the Strip's LEFT_MARGIN_PX: sized to the widest
# instrument name in the universe, not the widest one currently drawn.
LEFT_MARGIN_PX = 124

# ── the x layout, in cell units ───────────────────────────────────────────────
# One abstract axis: four cell slots, a change column, then the sparkline lane. All
# fixed numbers live here so the header ticks, the shapes and the traces cannot
# disagree about where a column is.
CELL_XS = (0.0, 1.0, 2.0, 3.0)
CELL_HALF = 0.46          # half-width of a cell; 0.5 would butt neighbours together
CELL_HALF_ROW = 0.38      # half-height in row units; the gap is the lane separator
DELTA_TRI_X = 4.35        # the direction triangle
DELTA_TEXT_X = 4.75       # the signed number
SPARK_X0, SPARK_X1 = 5.35, 8.35
SPARK_AMPLITUDE = 0.36    # half-height of the path, in row units
X_RANGE = (-0.85, 8.55)
VERDICT_X = -0.68         # the model-verdict marker at the row's left edge

# Ticks over the columns. The spark gets one centred label rather than an axis of its
# own; its y scale is the same 0-100 the cells carry and the hover on the endpoint
# says the number.
HEADER_TICK_XS = CELL_XS + (DELTA_TEXT_X - 0.2, (SPARK_X0 + SPARK_X1) / 2)

# A change smaller than this many index points draws a flat dash, not a direction.
DELTA_FLAT = 1.0

# How hard a cell at the pole leans into the pole colour. 1.0 would paint the full
# verdict hue, which grid_colors picks hot enough for text ON the background; a slab
# of it per cell reads as glare, the same observation that set the Strip's STEM_ALPHA.
CELL_MAX_BLEND = 0.82
# Inside this distance of neutral a cell keeps the resting fill: a 47-row board where
# every 53 carries a wash has no quiet majority left to make the extremes loud.
CELL_DEADBAND = 6.0
# The resting fill for a neutral cell: the background lifted just enough to read as a
# cell rather than as a hole in the row.
CELL_BASE_LIFT = 0.05

SPARK_LINE = "rgba(255, 255, 255, 0.30)"
SPARK_MIDLINE_ALPHA = 0.10
SPARK_END_SIZE = 5

TEXT_SIZE = 10


@dataclass(frozen=True)
class MarketRead:
    """One market's four-window reading, computed by the page's data layer.

    `windows` is index-aligned with WINDOW_WEEKS; a None entry is a window the
    market's history cannot fill yet. `history_weeks` is how many weekly reports the
    full-history window actually spans, and `start` is the first report date, both
    hover material. `path` is the trailing year of the 52-week index, oldest first,
    for the sparkline. `move` is the MOMENTUM_PERIOD-week change of the 52-week
    index, the same quantity the Heatmap's change column carries.
    """
    asset: str
    asset_class: str
    windows: tuple
    history_weeks: int = None
    start: str = None
    move: float = None
    path: tuple = ()
    state: str = const.SETUP_NONE
    is_equity: bool = False
    date: str = None


@dataclass(frozen=True)
class BoardRow:
    """One line of the board: an asset-class header, a market, or a blank spacer."""
    kind: str                 # "class", "market" or "spacer"
    label: str
    asset_class: str
    read: MarketRead = None


def crowding_score(read):
    """The mean of the windows the market can fill, for ordering.

    The mean rather than any single window, because the board's claim is the
    cross-window picture: a market at 95 on one window and 50 on three should not
    outrank one at 80 on all four. Windows the history cannot fill simply do not
    vote. None when no window has a value, and the caller drops that market with a
    count rather than drawing an empty row.
    """
    values = [v for v in read.windows if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def build_rows(reads, order=ORDER_CLASS):
    """`(rows, skipped)` for one week's list of MarketReads.

    Markets with no value in any window cannot be placed and are dropped and counted,
    for the Strip's reason: a board silently showing 44 of 47 markets reads as a
    complete one.

    ORDER_FLAT drops the class grouping entirely and sorts the whole board by
    crowding score, so the page becomes one gradient from crowded-long at the top to
    crowded-short at the bottom. The other two orders keep the class blocks.
    """
    scored, skipped = [], []
    for read in reads:
        score = crowding_score(read)
        if score is None:
            skipped.append(read.asset)
        else:
            scored.append((score, read))

    if order == ORDER_FLAT:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [BoardRow(kind="market", label=read.asset,
                         asset_class=read.asset_class, read=read)
                for _, read in scored], skipped

    by_class = {}
    for score, read in scored:
        by_class.setdefault(read.asset_class, []).append((score, read))

    rows = []
    for asset_class in sorted(by_class):
        markets = by_class[asset_class]
        if order == ORDER_ALPHA:
            markets.sort(key=lambda pair: pair[1].asset)
        else:
            markets.sort(key=lambda pair: pair[0], reverse=True)
        if rows:
            rows.append(BoardRow(kind="spacer", label="", asset_class=asset_class))
        rows.append(BoardRow(kind="class", label=asset_class,
                             asset_class=asset_class))
        rows.extend(BoardRow(kind="market", label=read.asset,
                             asset_class=asset_class, read=read)
                    for _, read in markets)
    return rows, skipped


def figure_height(rows):
    return TOP_CHROME_PX + BOTTOM_CHROME_PX + ROW_PX * max(1, len(rows))


# ── colour ────────────────────────────────────────────────────────────────────

def _blend_over(hex_color, alpha, background):
    """`hex_color` composited over `background` at `alpha`, as a hex string.

    The board needs the RESULTING colour, not an rgba string, because the cell text
    picks its own colour by the fill's luminance, and luminance of an rgba value
    depends on what it lands on.
    """
    h = str(hex_color).lstrip("#")
    b = str(background).lstrip("#")
    if len(h) != 6 or len(b) != 6:
        return hex_color
    try:
        fg = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        bg = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return hex_color
    return "#{:02x}{:02x}{:02x}".format(
        *(round(bg[i] + (fg[i] - bg[i]) * alpha) for i in range(3)))


def cell_base(background=vc.BACKGROUND_COLOR):
    """The resting fill of a neutral cell."""
    return _blend_over(vc.BRIGHTER_TEXT_COLOR, CELL_BASE_LIFT, background)


def cell_fill(value, colors, background=vc.BACKGROUND_COLOR):
    """The fill for one cell: its pole colour, blended toward the background by how
    far the value sits from neutral.

    Linear in distance from neutral past the deadband, capped at CELL_MAX_BLEND. The
    monotonicity (further from neutral is never fainter) is what makes the sweep
    honest, and the test suite pins it.
    """
    if value is None:
        return None
    deviation = value - const.INDEX_NEUTRAL
    magnitude = abs(deviation)
    if magnitude <= CELL_DEADBAND:
        return cell_base(background)
    pole = colors.bull if deviation > 0 else colors.bear
    span = (const.INDEX_NEUTRAL - CELL_DEADBAND)
    alpha = min(1.0, (magnitude - CELL_DEADBAND) / span) * CELL_MAX_BLEND
    return _blend_over(pole, alpha, background)


def cell_text_colour(fill):
    """Ink for the number printed on `fill`: the app's bright text on a dark cell,
    near-black on a light one. The threshold is luminance, not blend strength,
    because palettes disagree about how bright their bull and bear slots are."""
    if relative_luminance(fill) > 0.35:
        return "#101418"
    return vc.BRIGHTER_TEXT_COLOR


def delta_colour(move, colors):
    """The direction triangle's colour: bull hue rising, bear hue falling, dim flat."""
    if move is None or abs(move) <= DELTA_FLAT:
        return colors.dim
    return colors.bull if move > 0 else colors.bear


def _verdict_marker(state, colors):
    """(colour, symbol) for the model-verdict marker, or None off a full setup.

    Full setups only, no NEAR tier: the marker is a bridge to the model's vocabulary,
    not a reproduction of the Strip, and two tiers of marker at the left edge would
    out-shout the cells the page is about.
    """
    if state == const.SETUP_BULL:
        return colors.bull, "triangle-up"
    if state == const.SETUP_BEAR:
        return colors.bear, "triangle-down"
    return None


# ── hovers ────────────────────────────────────────────────────────────────────

def _fmt(value):
    return "n/a" if value is None else f"{value:.0f}"


def cell_hover(read, window_index):
    weeks = WINDOW_WEEKS[window_index]
    value = read.windows[window_index]
    if weeks is None:
        weeks_note = (f"{read.history_weeks} weekly reports since {read.start}"
                      if read.history_weeks else "full history")
        window = f"Full history ({weeks_note})"
    else:
        window = f"{WINDOW_DESC[window_index]}"
    return (f"<b>{read.asset}</b> · {window}<br>"
            f"Commercial index {_fmt(value)}"
            f"<br><i>0 = window low · 100 = window high</i>")


def delta_hover(read):
    if read.move is None:
        return f"<b>{read.asset}</b> · {vc.MOMENTUM_LABEL}: n/a"
    return (f"<b>{read.asset}</b> · {vc.MOMENTUM_LABEL}: {read.move:+.0f}<br>"
            f"<i>{vc.MOMENTUM_UNIT_PHRASE}</i>")


def spark_hover(read):
    latest = read.path[-1] if read.path else None
    return (f"<b>{read.asset}</b> · 52-week index over the trailing year<br>"
            f"latest {_fmt(latest)}")


# ── the figure ────────────────────────────────────────────────────────────────

def _spark_points(read, row_y):
    """(xs, ys) for one market's path, mapped into the sparkline lane.

    The y axis is reversed (row 0 at the top), so a HIGH index must map to a SMALLER
    y. Values are clamped to the lane rather than trusted: the path is a 0-100 index
    by construction, so a point outside it is a data error this should not amplify.
    """
    values = [v for v in read.path if v is not None]
    if len(values) < 2:
        return [], []
    n = len(values)
    xs = [SPARK_X0 + (SPARK_X1 - SPARK_X0) * i / (n - 1) for i in range(n)]
    ys = []
    for v in values:
        offset = (min(100.0, max(0.0, v)) - const.INDEX_NEUTRAL) / 50.0
        ys.append(row_y - offset * SPARK_AMPLITUDE)
    return xs, ys


def build_figure(rows, model, colors, background=vc.BACKGROUND_COLOR):
    """The board, as one figure. Pure over `rows`, exactly as the Strip's is."""
    fig = go.Figure()
    markets = [(i, r.read) for i, r in enumerate(rows) if r.kind == "market"]
    headers = [i for i, r in enumerate(rows) if r.kind == "class"]

    shapes = []

    # The cells. Painted as shapes rather than a heatmap trace so the per-cell fill
    # and the per-cell text colour come from ONE function, `cell_fill`, instead of a
    # colorscale that would have to replicate it.
    for i, read in markets:
        for w, x in enumerate(CELL_XS):
            fill = cell_fill(read.windows[w], colors, background)
            if fill is None:
                continue
            shapes.append(dict(
                type="rect", xref="x", yref="y",
                x0=x - CELL_HALF, x1=x + CELL_HALF,
                y0=i - CELL_HALF_ROW, y1=i + CELL_HALF_ROW,
                fillcolor=fill, line_width=0, layer="below"))

    # The heading bar, the Strip's treatment for the Strip's reason.
    shapes += [
        dict(type="rect", xref="paper", yref="y", x0=0, x1=1,
             y0=i - 0.5, y1=i + 0.5, layer="below",
             fillcolor=vc.BRIGHTER_TEXT_COLOR, opacity=HEADER_BAND_ALPHA,
             line_width=0)
        for i in headers
    ]

    # A midline through each sparkline lane: the 50 mark the path wiggles around.
    # Per market row rather than one long rule, so spacers and headers stay blank.
    shapes += [
        dict(type="line", xref="x", yref="y", x0=SPARK_X0, x1=SPARK_X1,
             y0=i, y1=i, layer="below",
             line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR,
                                         SPARK_MIDLINE_ALPHA), width=1))
        for i, _ in markets
    ]
    fig.update_layout(shapes=shapes)

    if markets:
        # The numbers on the cells. Split into two traces by the ink `cell_text_colour`
        # picked, because a scatter trace carries one text colour: per-point textfont
        # arrays are not portable across the plotly versions this app has shipped on.
        buckets = {}
        for i, read in markets:
            for w, x in enumerate(CELL_XS):
                value = read.windows[w]
                if value is None:
                    continue
                fill = cell_fill(value, colors, background)
                ink = cell_text_colour(fill)
                buckets.setdefault(ink, []).append(
                    (x, i, f"{value:.0f}", cell_hover(read, w)))
        for ink, points in buckets.items():
            fig.add_trace(go.Scatter(
                x=[p[0] for p in points], y=[p[1] for p in points],
                mode="text", text=[p[2] for p in points],
                textfont=dict(size=TEXT_SIZE, color=ink),
                hovertext=[p[3] for p in points], hoverinfo="text",
                showlegend=False))

        # The change column: a direction triangle and the signed number. The triangle
        # carries the colour (marker.color takes an array), the number stays in the
        # app's text colour, which is the dataviz rule about text wearing text tokens.
        fig.add_trace(go.Scatter(
            x=[DELTA_TRI_X] * len(markets), y=[i for i, _ in markets],
            mode="markers",
            marker=dict(
                symbol=["triangle-up" if (r.move or 0) > DELTA_FLAT
                        else "triangle-down" if (r.move or 0) < -DELTA_FLAT
                        else "line-ew" for _, r in markets],
                size=7,
                color=[delta_colour(r.move, colors) for _, r in markets],
                line=dict(width=1,
                          color=[delta_colour(r.move, colors) for _, r in markets])),
            hovertext=[delta_hover(r) for _, r in markets], hoverinfo="text",
            showlegend=False))
        fig.add_trace(go.Scatter(
            x=[DELTA_TEXT_X] * len(markets), y=[i for i, _ in markets],
            mode="text",
            text=["" if r.move is None else f"{r.move:+.0f}" for _, r in markets],
            textfont=dict(size=TEXT_SIZE, color=vc.TEXT_COLOR),
            hoverinfo="skip", showlegend=False))

        # The verdict bridge: the selected model's full setups, at the left edge.
        verdicts = [(i, r, _verdict_marker(r.state, colors))
                    for i, r in markets]
        verdicts = [(i, r, mark) for i, r, mark in verdicts if mark]
        if verdicts:
            fig.add_trace(go.Scatter(
                x=[VERDICT_X] * len(verdicts), y=[i for i, _, _ in verdicts],
                mode="markers",
                marker=dict(symbol=[mark[1] for _, _, mark in verdicts],
                            size=7,
                            color=[mark[0] for _, _, mark in verdicts]),
                hovertext=[f"<b>{r.asset}</b> · {model.title} verdict this week"
                           for _, r, _ in verdicts],
                hoverinfo="text", showlegend=False))

        # The sparklines: one line per market, one shared endpoint trace so the dots
        # can carry per-point colour without a trace apiece.
        end_xs, end_ys, end_colours, end_hovers = [], [], [], []
        for i, read in markets:
            xs, ys = _spark_points(read, i)
            if not xs:
                continue
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines",
                line=dict(color=SPARK_LINE, width=1),
                hoverinfo="skip", showlegend=False))
            end_xs.append(xs[-1])
            end_ys.append(ys[-1])
            latest = [v for v in read.path if v is not None][-1]
            end_colours.append(colors.bull if latest >= const.INDEX_NEUTRAL
                               else colors.bear)
            end_hovers.append(spark_hover(read))
        if end_xs:
            fig.add_trace(go.Scatter(
                x=end_xs, y=end_ys, mode="markers",
                marker=dict(size=SPARK_END_SIZE, color=end_colours),
                hovertext=end_hovers, hoverinfo="text", showlegend=False))

    n = len(rows)
    fig.update_layout(
        height=figure_height(rows),
        margin=dict(l=LEFT_MARGIN_PX, r=8, t=TOP_CHROME_PX, b=BOTTOM_CHROME_PX),
        paper_bgcolor=background,
        plot_bgcolor=background,
        showlegend=False,
        xaxis=dict(
            range=list(X_RANGE),
            side="top",
            tickvals=list(HEADER_TICK_XS),
            ticktext=list(WINDOW_LABELS) + [vc.MOMENTUM_LABEL, "52w path"],
            tickfont=dict(size=10, color=vc.TEXT_COLOR),
            showgrid=False, zeroline=False, fixedrange=True),
        yaxis=dict(
            range=[n - 0.5, -0.5],
            tickvals=list(range(n)),
            ticktext=[r.label for r in rows],
            tickfont=dict(size=10, color=vc.BRIGHTER_TEXT_COLOR),
            showgrid=False, zeroline=False, fixedrange=True),
        hoverlabel=dict(bgcolor="#0e1116", font=dict(color=vc.HOVER_TEXT_COLOR)),
    )
    return fig
