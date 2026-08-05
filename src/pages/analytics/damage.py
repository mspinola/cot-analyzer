"""Crowding damage `D`: the weekly forced-exit reading, from crowdmon's published panel.

## What is on this page and why it is a chart at all

crowdmon delivers `D = C x I x Phi` per market-week, reported as a percentile of that
market's own history. Beside it sits the **offside** distance: how far price must move before
a rules-based pool is mechanically forced out, in daily sigma.

crowdmon is explicit that the two must not be multiplied, and that the **quadrant they form
is the deliverable**: close-and-severe is the cell to act on, close-and-harmless fires often
and does not matter, far-and-severe would hurt but is not imminent. One scalar cannot say
which, and a per-market text block can only say it one market at a time. A scatter can say it
for all of them at once, which is the whole reason this page exists rather than a table.

## Everything printed here comes from the artifact

No crowdmon vocabulary is defined in this repo: the state names, the quadrant labels, the
severity threshold, the factor descriptions and the standing caveats are all read from the
manifest, which crowdmon generates from its live constants at publish time.
`tests/test_damage_vocabulary.py` fails if any of those values is typed out here, comments
included. See `components/crowdmon_artifact.py` for why that obligation exists.

## Four things this page must not do, all of them measured upstream

1. **Never place a market in a quadrant when the observed pool is on the other side.**
   crowdmon's own renderer suppresses the cell in that case, because labelling such a row
   close-and-severe is precisely wrong: the price level is real and the book it would force
   is not there. On the current week that is 16 of 35 markets with a sell-side level, so it
   is the common case. The flag has THREE states and "nobody checked" is not "no".
2. **Never imply the distance is a countdown.** The reference bar moves more than spot does,
   so most of the variation in distance-to-trigger is old bars rolling off rather than price
   approaching anything.
3. **Never drop a market silently.** A market with no trigger, or no score, is listed by
   name together with the producer's own note for its state. A blank beside three populated
   columns reads as a low value rather than an absence, which is the exact failure crowdmon
   added its state columns to fix.
4. **Never present `D` directionally.** It describes the shape of a conditional loss
   distribution, not its location.

Python 3.9 compatible: production runs 3.9 while CI runs 3.10-3.12, and a `use_pages` app
imports every page at startup, so a syntax error here takes down the page registry.
"""
from __future__ import annotations

from typing import List, Optional

import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html, no_update

import components.crowdmon_artifact as artifact
import components.plot_colors as plot_colors
import viz_constants as vc

dash.register_page(__name__, path="/damage")

SIDES = (("sell", "Forced selling"), ("buy", "Forced buying"))

#: Marker for a market whose observed pool contradicts the price signal. Plotted, because
#: hiding it would be its own kind of silence, but visibly outside the quadrant scheme.
CONTRADICTED_COLOR = "#586e75"

#: The producer's public write-up. A link out is allowed; a dependency on it is not, which
#: is why every definition on the page is rendered from the panel's own manifest and this is
#: only where a reader goes for the formulas.
CROWDMON_DOCS = ("https://github.com/mspinola/crowdmon/blob/main/docs/design/"
                 "crowdmon_plain_language_summary.md")

#: Columns the grid publishes that the artifact carries no definition for. Listed rather
#: than quietly omitted, and each still shows the panel field it is built from, which is at
#: least enough to look the term up. Each is `(grid field, header, field in the panel)`.
#:
#: Emptying this tuple is the goal: crowdmon already publishes `factor_questions` for the
#: three factors, and these four want the same treatment at the producer rather than a
#: definition typed in here, which is what `tests/test_damage_vocabulary.py` forbids and
#: what would go stale the first time the formula moved.
#:
#: **Emptied 2026-08-05.** crowdmon now publishes `column_definitions`, keyed by panel
#: column, for all four plus `D` itself, so every measured column on this page carries the
#: producer's own words. The tuple stays rather than being deleted: it is the mechanism for
#: naming the NEXT gap, and naming a gap is what got these published. A column added to
#: `_grid` with nothing to say about it belongs here, not in silence.
UNDEFINED_TERMS = ()

#: Grid columns that identify the row rather than measure it, so they need no definition.
IDENTITY_COLUMNS = ("name", "symbol", "asset_class", "market_code")

#: Marker diameter (px) below which a 2-3 character ticker will not sit legibly inside the
#: bubble. Below it the label moves outside or is dropped rather than shrunk: an unreadable
#: label is worse than none, because it still costs the ink and the collision.
MIN_MARKER_FOR_LABEL = 16.0


# ── layout ──────────────────────────────────────────────────────────────────
def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope would make importing
    # this page require a populated store.
    art = artifact.load()
    if not art.usable:
        return _unavailable(art)

    return html.Div([
        dbc.Container([
            _provenance(art),
            _standing(art),
            _glossary(art),
            dbc.Row([
                dbc.Col(dbc.RadioItems(
                    id="damage-side", options=[{"label": lab, "value": s}
                                               for s, lab in SIDES],
                    value="sell", inline=True, className="mb-2"), width="auto"),
            ], className="mt-3"),
            dcc.Loading(html.Div(id="damage-quadrant")),
            dcc.Loading(html.Div(id="damage-grid")),
            dbc.Offcanvas(html.Div(id="damage-brief"), id="damage-offcanvas",
                          title="Market detail", placement="end",
                          style={"width": "46rem"}),
        ], fluid=True),
    ])


def _unavailable(art) -> html.Div:
    """The store is missing, partial, or a version this page does not read.

    Rendered as a card rather than raised, because `use_pages=True` imports every page at
    startup: an exception here would take down the page registry, not this page.
    """
    return html.Div(dbc.Container([
        dbc.Alert([
            html.H5("The crowding panel is not available", className="alert-heading"),
            html.P(art.message or "No panel was found."),
        ], color="secondary", className="mt-4"),
    ], fluid=True))


def _provenance(art) -> dbc.Row:
    counts = art.manifest.get("counts") or {}
    prov = art.manifest.get("provenance") or {}
    bits = ["report week {}".format(art.report_date),
            "{} markets".format(counts.get("markets", "?")),
            "crowdmon {}".format(prov.get("crowdmon_version", "?")),
            "schema {}".format(art.manifest.get("schema_version"))]
    if art.built_at:
        bits.append("built {}".format(art.built_at))

    children = [html.P(" · ".join(bits),
                       style={"textAlign": "center", "color": vc.TEXT_COLOR,
                              "fontSize": "0.85rem", "fontStyle": "italic",
                              "marginTop": "18px", "marginBottom": "6px"})]
    # Not a dismissible toast. A page showing a stale week as though it were this week is
    # worse than a page showing nothing.
    for line in artifact.staleness(art, _site_latest_date()):
        children.append(dbc.Alert(line, color="warning", className="mb-2"))
    return dbc.Row(dbc.Col(children, width=12))


def _site_latest_date() -> Optional[str]:
    """The newest COT week the rest of this site has, for the staleness comparison.

    Imported inside the function: `get_indexer()` builds the whole metrics layer on first
    call, and this page must remain importable against an empty store.
    """
    try:
        from cotmetrics.indexer import get_indexer
        dates = get_indexer().get_available_dates()
        return dates[0] if dates else None
    except Exception:                                                   # noqa: BLE001
        return None


def _standing(art) -> dbc.Alert:
    """crowdmon's own standing caveats, verbatim, always visible.

    Deliberately not a collapsed accordion. crowdmon's brief has no flag to suppress its
    caveat ledger, on the argument that an artifact which can hide its own caveats has become
    the bare number it exists to stop travelling alone; a panel closed by default is that
    flag with extra steps.
    """
    lines = art.manifest.get("standing") or []
    return dbc.Alert(
        [html.H6("Before reading any number on this page", className="mb-2")]
        + [html.P(line, className="mb-2", style={"fontSize": "0.85rem"})
           for line in lines],
        color="secondary", className="mt-2")


def glossary_terms(manifest):
    """One entry per measured grid column: `(grid field, header, panel field, body)`.

    Keyed by the grid's own field name so that a column added to `_grid` without a
    definition FAILS rather than simply going unexplained. A glossary that silently omits
    an entry reads as complete, and a reader cannot tell a missing definition from a term
    nobody thought needed one.

    Every `body` is a manifest string rendered verbatim, or `_undefined` where the artifact
    ships the column and no words for it. Nothing here paraphrases the producer.

    Two manifest keys feed it and they are deliberately not one. `factor_questions` means the
    three factors of `D = C x I x Phi`; `column_definitions` covers everything else the grid
    measures, keyed by PANEL column rather than by the header this page invented, because the
    producer has never heard of `T (days)`.
    """
    asked = manifest.get("factor_questions") or {}
    defined = manifest.get("column_definitions") or {}
    notes = manifest.get("notes") or {}
    bands = manifest.get("damage_bands") or []
    quadrant = manifest.get("quadrant") or {}
    strata = notes.get("band_advice") or {}
    states = notes.get("score_state") or {}

    def _says(column):
        """The producer's own words for a panel column, or the standing admission."""
        return defined.get(column) or _undefined()

    # `D` is the one row with two sources: a definition and the band ladder underneath it.
    # Either may be absent on an older panel, and the admission is printed only when BOTH
    # are, because a ladder with no prose still says more than nothing does.
    damage = []
    if defined.get("damage_<side>_pct"):
        damage.append(defined["damage_<side>_pct"] + ".")
    if bands:
        damage += [" Banded by the producer as " if damage else "Banded by the producer as ",
                   html.Span(", ".join("{:g}+ {}".format(floor, label)
                                       for floor, label in bands),
                             style={"fontStyle": "italic"}), "."]
    if not damage:
        damage = [_undefined()]

    joined = "; ".join(quadrant[k] for k in sorted(quadrant, reverse=True))
    terms = [
        ("D", "D pct", "damage_<side>_pct", damage),
        ("cell", "Quadrant", "computed on this page",
         ["Which side of the two dashed lines a market falls on, at ",
          html.B("{:g} sigma".format(manifest.get("close_sigma") or 1.5)),
          " across and the second band floor above. ", joined]),
        ("offside_sigma", "Offside (sigma)", "trigger_<side>_sigma",
         _says("trigger_<side>_sigma")),
        ("offside_pct", "Offside (%)", "trigger_<side>_pct", _says("trigger_<side>_pct")),
        ("C", "C", "crowding_<side>", asked.get("crowding") or _undefined()),
        ("I", "I", "illiquidity_<side>", asked.get("illiquidity") or _undefined()),
        ("Phi", "Phi", "fragility", asked.get("fragility") or _undefined()),
        ("T_days", "T (days)", "dtl_<side>", _says("dtl_<side>")),
        ("beta", "beta (shared door)", "beta", _says("beta")),
        ("state", "Why no D", "score_state_<side>",
         "; ".join("{}: {}".format(k, v) for k, v in sorted(states.items()) if v)
         or _undefined()),
        ("stratum", "stratum", "stratum",
         "; ".join("{}: {}".format(k, v) for k, v in sorted(strata.items()))
         or _undefined()),
    ]
    return terms + [(field, label, panel, _undefined())
                    for field, label, panel in UNDEFINED_TERMS]


def _term(label: str, field: str, body) -> html.Tr:
    """One glossary row: what this page calls it, where it comes from, what it means.

    The first two cells are this repo's own doing, because this page invents its column
    headers (`C`, `I`, `Phi`, `D pct`) and the panel does not ship them. The third is
    always the producer's own words, never a paraphrase.
    """
    pad = {"verticalAlign": "top", "paddingRight": "1rem", "paddingBottom": "0.4rem"}
    return html.Tr([
        html.Td(html.B(label), style=dict(pad, whiteSpace="nowrap")),
        html.Td(html.Code(field, style={"opacity": 0.7}),
                style=dict(pad, whiteSpace="nowrap")),
        html.Td(body, style=dict(pad, paddingRight="0")),
    ])


def _glossary(art) -> dbc.Alert:
    """Every column on this page, defined ON this page.

    A reader should not have to open another repo to learn what `Phi` is, and until now
    nothing here said. The definitions are still not written down in this repo: each is a
    manifest string rendered verbatim, so the producer stays the single source and this
    block cannot drift from it. What this repo contributes is the mapping from the header it
    invented to the panel field underneath.

    Three of the artifact's own keys were reaching nothing before this: `factor_questions`,
    `reading_instructions` and `notes.band_advice` were all published and all unread. A
    manifest key with no consumer is indistinguishable from one that does not exist, which
    is how a page ends up with a long preamble and no definitions.

    Where the artifact carries no definition for a term the grid shows, this says so rather
    than inventing one. That gap is real, and naming it is what gets it published upstream:
    the four terms this block admitted it could not define (offside in sigma and in percent,
    `T`, and `beta`) are defined by the producer as of 2026-08-05, in `column_definitions`,
    because they were listed here rather than quietly left blank. `D` gained a definition in
    the same release, so the ladder it used to be described by now sits under one.
    """
    rows = [_term(label, field, body)
            for _, label, field, body in glossary_terms(art.manifest)]

    return dbc.Alert([
        html.H6("What each column is", className="mb-2"),
        html.Table(html.Tbody(rows), style={"fontSize": "0.85rem", "width": "100%"}),
        _misreadings(art.manifest),
        html.P(["Every definition above is the producer's own, published with the panel. ",
                html.A("The full write-up", href=CROWDMON_DOCS, target="_blank",
                       rel="noopener noreferrer"),
                " carries the formulas and the measurements behind them."],
               className="mb-0 mt-2", style={"fontSize": "0.8rem", "opacity": 0.8}),
    ], color="dark", className="mt-2")


def _undefined() -> str:
    """What to print when the artifact ships a column and no words for it.

    Silence would read as "self-explanatory", which none of these are, and inventing a
    definition here is the duplicate-of-a-living-document failure this page exists to
    avoid. Saying it plainly is also the only pressure on the producer to publish one.
    """
    return "not defined in the panel, so not defined here. See the write-up below."


def _misreadings(manifest) -> html.Div:
    """`reading_instructions`: what a column must NOT be read as, in the producer's words.

    Published since the first panel and rendered nowhere until now. These are the errors
    the producer measured someone making, so they are worth more than another definition.
    """
    items = manifest.get("reading_instructions") or []
    if not items:
        return html.Div()
    return html.Div([
        html.P(html.B("What these columns do not mean"),
               className="mb-1 mt-2", style={"fontSize": "0.85rem"}),
    ] + [
        # A null `column` is a caveat about the panel as a whole, NOT about `D`. Defaulting
        # it to a column name would attribute a general warning to one number, which is a
        # quieter version of the misreading these entries exist to prevent.
        html.P([html.Code(item["column"], style={"opacity": 0.7}) if item.get("column")
                else html.Span("this panel", style={"opacity": 0.7}), " ",
                html.Span("is not: ", style={"opacity": 0.7}),
                item.get("misreading") or "",
                (". " + item["why_not"]) if item.get("why_not") else ".",
                html.Span("  ({})".format(item.get("ref") or ""),
                          style={"opacity": 0.55})],
               className="mb-1", style={"fontSize": "0.8rem"})
        for item in items
    ])


# ── the quadrant ────────────────────────────────────────────────────────────
def _quadrant_label(manifest, close: bool, severe: bool) -> str:
    """The cell's name, from the artifact. Never spelled out in this repo."""
    return (manifest.get("quadrant") or {}).get(
        "{}{}".format(int(close), int(severe)), "")


def _severe_floor(manifest) -> float:
    """The `D_pct` above which crowdmon calls a reading severe, read from its own bands.

    Derived from `damage_bands` rather than hard-coded: the bands are `(floor, label)` pairs
    in descending order and the severity line is the second, which is the same value
    crowdmon's own quadrant uses. Reading it here means a producer that re-bands moves this
    page with it.
    """
    bands = manifest.get("damage_bands") or []
    try:
        return float(bands[1][0])
    except (IndexError, TypeError, ValueError):
        return 0.75


def _figure(week: pd.DataFrame, manifest, side: str) -> go.Figure:
    close_sigma = float(manifest.get("close_sigma") or 1.5)
    floor = _severe_floor(manifest)

    frame = week.copy()
    frame["sigma"] = pd.to_numeric(frame["trigger_{}_sigma".format(side)], errors="coerce")
    frame["d"] = pd.to_numeric(frame["damage_{}_pct".format(side)], errors="coerce")
    frame = frame.dropna(subset=["sigma", "d"])

    agrees = frame["trigger_{}_pool_agrees".format(side)]
    contradicted = frame[agrees == False]                               # noqa: E712
    placed = frame[agrees != False]                                     # noqa: E712

    oi_max = _panel_open_interest_max(week)
    fig = go.Figure()
    # The two lines ARE the quadrant, so they are drawn to be read rather than to be
    # tasteful, and each carries the number that defines it. Both come from the artifact.
    fig.add_hline(y=floor, line_dash="dash", line_color=vc.TEXT_COLOR, opacity=0.55,
                  annotation_text="severe at D pct {:g}".format(floor),
                  annotation_position="top left",
                  annotation_font={"size": 11, "color": vc.TEXT_COLOR})
    fig.add_vline(x=close_sigma, line_dash="dash", line_color=vc.TEXT_COLOR, opacity=0.55,
                  annotation_text="close at {:g} sigma".format(close_sigma),
                  annotation_position="top right",
                  annotation_font={"size": 11, "color": vc.TEXT_COLOR})

    for is_close in (True, False):
        for is_severe in (True, False):
            part = placed[((placed["sigma"] <= close_sigma) == is_close)
                          & ((placed["d"] >= floor) == is_severe)]
            if part.empty:
                continue
            color, filled = _cell_style(is_close, is_severe)
            fig.add_trace(_trace(
                part, name="{}  ({})".format(
                    _quadrant_label(manifest, is_close, is_severe), len(part)),
                color=color, filled=filled, oi_max=oi_max,
                label_all=is_close or is_severe))

    if not contradicted.empty:
        # Plotted with an open marker and NO quadrant, mirroring crowdmon's renderer, which
        # suppresses the cell entirely when the observed pool is on the other side.
        fig.add_trace(_trace(
            contradicted,
            name="pool on the other side, no cell  ({})".format(len(contradicted)),
            color=CONTRADICTED_COLOR, filled=False, oi_max=oi_max,
            marker_symbol="circle-open"))

    fig.update_layout(
        template="plotly_dark", height=560,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": vc.TEXT_COLOR},
        margin={"l": 60, "r": 20, "t": 30, "b": 60},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.28, "x": 0},
        # Ticks are PINNED rather than chosen. Left to itself plotly resolves this axis to
        # `dtick "D1"`, which prints only the mantissa of each tick and carries the decade in
        # the label's vertical position (measured: y 499 for `1` and `10` against y 490 for
        # every single digit). On the buy side, which spans 0.0033 to 66.91 sigma on
        # 2026-07-28, that renders the glyph `2` three times meaning 0.2, 2 and 20, and the
        # only unambiguous anchor left in the picture is the dashed `close at 1.5` line.
        # Explicit labels cost the minor gridlines and buy back the scale.
        xaxis={"title": "distance to the nearest flip that forces this side "
                        "(daily sigma, log scale)",
               "type": "log", "gridcolor": vc.GRID_COLOR,
               "tickmode": "array",
               # Spanning both sides' ranges, which differ by more than a decade at each
               # end: sell runs 0.13 to 48.9 sigma and buy 0.0018 to 69.0 on 2026-07-28.
               # Plotly drops an out-of-range entry silently, so the list covers the union
               # and each side keeps the subset it can show. `1.5` is in the list because
               # the dashed close line sits there and a threshold nobody can read off the
               # axis is a threshold stated twice and legible once.
               "tickvals": [0.01, 0.1, 0.2, 0.5, 1, 1.5, 5, 10, 20, 50],
               "ticktext": ["0.01", "0.1", "0.2", "0.5", "1", "1.5",
                            "5", "10", "20", "50"]},
        # Headroom above 1, because `D` is a percentile and the markets pinned AT 1.000 are
        # the ones a reader came for. A range that stops just past the maximum leaves the
        # bubble, and the label above a bubble too small to hold one, sliced by the plot
        # edge: on 2026-07-28 that was nat gas at D 1.000 and RBOB at 0.987, the top two
        # rows of the table. The ticks still stop at 1; only the frame goes higher.
        yaxis={"title": "D percentile, against this market's own history",
               "range": [0, 1.08], "dtick": 0.2, "gridcolor": vc.GRID_COLOR},
    )
    return fig


def _label_color(color: str, filled: bool, inside: bool) -> str:
    """Readable text for a bubble, given how that bubble is drawn and where the text sits.

    Only a label INSIDE a filled marker is read against the fill. An open marker is
    transparent and a label pushed outside has left the marker altogether, so both are read
    against the page and the marker colour is what carries.

    `inside` is not redundant with `filled`: the fill-contrast colour is chosen to oppose the
    fill, so applying it to a label that has moved outside puts it against the wrong
    background. With today's dark fill that is white text on a dark page, which merely loses
    the colour coding; with a light fill it would be near-black on a dark page, and the label
    would be gone rather than ugly.
    """
    if not (filled and inside):
        return color
    return "#0b1416" if plot_colors.relative_luminance(color) > 0.5 else "#ffffff"


def _cell_style(is_close: bool, is_severe: bool):
    """How one quadrant cell is drawn: `(colour, filled)`, one visual channel per axis.

    Two binary axes need two channels. Spending BOTH colour and fill on the same single bit
    ("is this the cell to act on") leaves nothing to separate the other three, and position
    is not available to a legend swatch, so three positionally distinct cells collapsed into
    three identical entries and only their counts told them apart.

    So each channel takes one axis, and each maps to one of the two dashed reference lines:

    ==========  ====================  =====================
    .           severe (above the y)  not severe
    ==========  ====================  =====================
    close       filled alarm          filled neutral
    not close   open alarm            open neutral
    ==========  ====================  =====================

    Hue carries severity because that is `D` itself, the thing the page reports; fill carries
    closeness because a solid mark reads as more imminent than an outline. The cell a reader
    acts on remains the only filled alarm mark, so nothing is taken away from it.
    """
    color = vc.CATEGORY_DIVERGING_DOWN if is_severe else vc.CATEGORY_DIVERGING_UP
    return color, is_close


def _panel_open_interest_max(week: pd.DataFrame) -> float:
    """The one scale every bubble on both charts is drawn against.

    Taken over the WHOLE week rather than over the rows a trace happens to hold, so that area
    is proportional to open interest across the entire figure. Normalising per trace ranks a
    market against its own quadrant instead, which draws the largest member of every cell at
    the same size: on 2026-07-28 that put corn (1.74M) and the Nasdaq (0.29M) at an identical
    30px, so the one channel that looks like size was not reporting size.

    Over the week and not merely over the plotted rows, so both sides of the radio share a
    scale and toggling does not resize a market that did not change. A side whose largest
    market has no trigger therefore tops out below 30px, which is honest: it is the smaller
    book. On this week the sell side reaches 20.5px against the buy side's 30.0.
    """
    oi = pd.to_numeric(week["open_interest"], errors="coerce").max()
    return float(oi) if oi > 0 else 1.0


def _trace(part: pd.DataFrame, *, name: str, color: str, filled: bool, oi_max: float,
           marker_symbol: str = "circle", label_all: bool = False) -> go.Scatter:
    oi = pd.to_numeric(part["open_interest"], errors="coerce").fillna(0.0)
    # Diameter as the square root of open interest, so AREA carries the quantity. That is the
    # comparison a reader's eye performs whether or not the code intended it.
    size = 8.0 + 22.0 * (oi / oi_max) ** 0.5

    # The ticker goes INSIDE the bubble where it fits. `MIN_MARKER_FOR_LABEL` is a fact about
    # 8px type in a circle, so it may decide PLACEMENT and nothing else. What it must not
    # decide is which markets are worth naming: against a panel-wide scale it now means
    # "small market", and open interest is not why a reader wants a name. Anything with a
    # claim on attention (either condition met) is named wherever it will fit, and the cell
    # where neither is met is left to the hover, because 35 overlapping tickers say less than
    # a dozen. Open interest spans 755x on this week, so a size-only rule named 5 of the 35
    # markets on the sell side and dropped both members of one populated cell.
    tickers = part["symbol"].fillna("").astype(str)
    fits = size >= MIN_MARKER_FOR_LABEL
    labels = tickers if label_all else tickers.where(fits, "")
    positions = ["middle center" if ok else "top center" for ok in fits]
    colors = [_label_color(color, filled, ok) for ok in fits]

    return go.Scatter(
        x=part["sigma"], y=part["d"], mode="markers+text", name=name,
        # A glyph is allowed to overhang the axes. The y range carries the headroom for the
        # common case; this is what stops a market landing exactly at D 0.000, or at the
        # left edge of the log x axis, from being sliced instead of drawn.
        cliponaxis=False,
        text=labels, textposition=positions,
        textfont={"size": 8, "color": colors,
                  "family": "SFMono-Regular, Menlo, monospace"},
        customdata=part[["market_name", "market_code", "crowding_long",
                         "illiquidity_sell", "fragility", "dtl_sell"]].values,
        marker={"size": size, "color": color if filled else "rgba(0,0,0,0)",
                "symbol": marker_symbol, "line": {"color": color, "width": 2}},
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       "D pct %{y:.3f}<br>offside %{x:.2f} sigma<br>"
                       "C %{customdata[2]:.3f}  I %{customdata[3]:.3f}  "
                       "Phi %{customdata[4]:.3f}<br>"
                       "T %{customdata[5]:.2f} days<extra></extra>"))


def _excluded(week: pd.DataFrame, manifest, side: str) -> dbc.Alert:
    """Markets absent from the chart, named.

    A market with no trigger and a market with no score are both invisible on a scatter, and
    an invisible market reads as a safe one. Naming them is the same fix crowdmon made when
    it gave every null cell a state column.
    """
    notes = (manifest.get("notes") or {}).get("score_state") or {}
    sigma = pd.to_numeric(week["trigger_{}_sigma".format(side)], errors="coerce")
    d = pd.to_numeric(week["damage_{}_pct".format(side)], errors="coerce")

    rows: List = []
    no_trigger = week[sigma.isna() & d.notna()]
    if not no_trigger.empty:
        rows.append(html.P([
            html.B("{} markets have no level that forces this side: ".format(
                len(no_trigger))),
            ", ".join(sorted(_short(n) for n in no_trigger["market_name"])),
            ". That is an answer, not a gap: every trend horizon is already positioned the "
            "other way.",
        ], className="mb-2", style={"fontSize": "0.85rem"}))

    unscored = week[d.isna()]
    if not unscored.empty:
        by_state = unscored.groupby("score_state_{}".format(side))["market_name"]
        for state, names in by_state:
            rows.append(html.P([
                html.B("{} unscored ({}): ".format(len(names), state)),
                ", ".join(sorted(_short(n) for n in names)),
                ". ", notes.get(state, ""),
            ], className="mb-2", style={"fontSize": "0.85rem"}))

    if not rows:
        return dbc.Alert("Every market this week is on the chart.", color="dark",
                         className="mt-2")
    return dbc.Alert([html.H6("Not on the chart", className="mb-2")] + rows,
                     color="dark", className="mt-2")


def _short(name) -> str:
    return str(name).split(" - ")[0]


# ── the grid ────────────────────────────────────────────────────────────────
def _grid(week: pd.DataFrame, manifest, side: str) -> dag.AgGrid:
    other = "buy" if side == "sell" else "sell"
    crowd = "crowding_long" if side == "sell" else "crowding_short"
    frame = week.copy()
    frame["D"] = pd.to_numeric(frame["damage_{}_pct".format(side)], errors="coerce")
    frame["offside_sigma"] = pd.to_numeric(frame["trigger_{}_sigma".format(side)],
                                           errors="coerce")
    frame["offside_pct"] = pd.to_numeric(frame["trigger_{}_pct".format(side)],
                                         errors="coerce")
    frame["cell"] = _cells(frame, manifest, side)
    frame["state"] = frame["score_state_{}".format(side)]
    frame["C"] = pd.to_numeric(frame[crowd], errors="coerce")
    frame["I"] = pd.to_numeric(frame["illiquidity_{}".format(side)], errors="coerce")
    frame["Phi"] = pd.to_numeric(frame["fragility"], errors="coerce")
    frame["T_days"] = pd.to_numeric(frame["dtl_{}".format(side)], errors="coerce")
    frame["name"] = frame["market_name"].map(_short)
    frame = frame.drop(columns=[c for c in frame.columns if c.startswith("damage_")
                                or c.startswith("trigger_") or c == other], errors="ignore")

    # `rightAligned` pins the header LABEL to the right of the cell and leaves the filter
    # icon at the left, so any width beyond what the label needs opens as a gap BETWEEN
    # them. Left at ag-grid's 200px default that gap ran to 154px on a one-character header,
    # which does not read as a wide column: it reads as a filter icon belonging to an empty
    # unnamed column, and then as a missing header. Size these to their labels instead.
    num = {"filter": "agNumberColumnFilter", "type": "rightAligned",
           "width": 124, "minWidth": 96}
    factor = dict(num, width=96)
    asked = manifest.get("factor_questions") or {}
    columns = [
        {"field": "name", "headerName": "Market", "minWidth": 210, "tooltipField": "state"},
        {"field": "symbol", "maxWidth": 90},
        # An ordinary column, NOT a row group. `rowGroup` is an ag-grid Enterprise feature
        # and `dash_ag_grid` loads the community bundle unless `enableEnterpriseModules` is
        # set, which nothing here sets, so the grouping this column was written for never ran
        # and `hide: True` was the only part of that config with an effect: the asset class
        # was simply invisible. A dead flag that silently degrades to hiding data is worse
        # than no flag.
        {"field": "asset_class", "headerName": "Asset class (crowdmon / cotdata registry)",
         "minWidth": 150},
        {"field": "D", "headerName": "D pct", "sort": "desc",
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.3f')(params.value)"}, **num},
        {"field": "state", "headerName": "Why no D", "minWidth": 130},
        {"field": "cell", "headerName": "Quadrant", "minWidth": 230},
        {"field": "offside_sigma", "headerName": "Offside (sigma)",
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.2f')(params.value)"}, **num},
        {"field": "offside_pct", "headerName": "Offside (%)",
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.2%')(params.value)"}, **num},
        # A one-letter header on a factor nobody can look up is the same silence the state
        # columns exist to break, and crowdmon publishes the question each factor answers
        # for exactly this. Nothing consumed `factor_questions` before now.
        {"field": "C", "headerTooltip": asked.get("crowding"),
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.3f')(params.value)"}, **factor},
        {"field": "I", "headerTooltip": asked.get("illiquidity"),
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.3f')(params.value)"}, **factor},
        {"field": "Phi", "headerTooltip": asked.get("fragility"),
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.3f')(params.value)"}, **factor},
        {"field": "T_days", "headerName": "T (days)",
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.2f')(params.value)"}, **num},
        {"field": "beta", "headerName": "beta (shared door)",
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.2f')(params.value)"}, **num},
        {"field": "stratum", "minWidth": 110},
        {"field": "market_code", "hide": True},
    ]
    return dag.AgGrid(
        id="damage-grid-table",
        # The market code IS the row identity, so `cellClicked.rowId` is directly the key
        # into the published briefs. Without this ag-grid hands back a row index, and every
        # column here is sortable, so the first click on a header would start opening the
        # wrong market's numbers under this market's name rather than failing visibly.
        getRowId="params.data.market_code",
        rowData=frame.to_dict("records"), columnDefs=columns,
        className="ag-theme-quartz-dark",
        style={"height": "62vh", "width": "100%", "fontSize": "13px"},
        defaultColDef={"sortable": True, "filter": True, "resizable": True,
                       "wrapHeaderText": True, "autoHeaderHeight": True, "minWidth": 100},
        # No `groupDefaultExpanded`: it went with the row grouping, and an option that
        # configures a feature this build does not load is a claim that it runs.
        dashGridOptions={"rowHeight": 30, "tooltipShowDelay": 400,
                         # Nulls last, so an unscored market never reads as a low one.
                         "accentedSort": True},
    )


def _cells(frame: pd.DataFrame, manifest, side: str) -> pd.Series:
    """The quadrant label per row, blank where crowdmon's own renderer would suppress it."""
    close_sigma = float(manifest.get("close_sigma") or 1.5)
    floor = _severe_floor(manifest)
    sigma = pd.to_numeric(frame["trigger_{}_sigma".format(side)], errors="coerce")
    d = pd.to_numeric(frame["damage_{}_pct".format(side)], errors="coerce")
    agrees = frame["trigger_{}_pool_agrees".format(side)]

    out = []
    for i in frame.index:
        if pd.isna(sigma[i]) or pd.isna(d[i]):
            out.append("")
        elif agrees[i] is False or agrees[i] == False:                  # noqa: E712
            out.append("(pool on the other side)")
        else:
            out.append(_quadrant_label(manifest, sigma[i] <= close_sigma, d[i] >= floor))
    return pd.Series(out, index=frame.index)


# ── callbacks ───────────────────────────────────────────────────────────────
@callback(Output("damage-quadrant", "children"), Output("damage-grid", "children"),
          Input("damage-side", "value"))
def _render(side):
    art = artifact.load()
    if not art.usable:
        return no_update, no_update
    week = artifact.latest_week(art)
    return (html.Div([dcc.Graph(figure=_figure(week, art.manifest, side),
                                config={"displayModeBar": False}),
                      _excluded(week, art.manifest, side)]),
            _grid(week, art.manifest, side))


@callback(Output("damage-offcanvas", "is_open"), Output("damage-brief", "children"),
          Input("damage-grid-table", "cellClicked"), Input("damage-side", "value"),
          prevent_initial_call=True)
def _drill(cell, side):
    if not cell:
        return False, no_update
    art = artifact.load()
    # A click on an asset-class group header has no market behind it, so it opens nothing
    # rather than opening the first market in the group.
    code = str(cell.get("rowId") or "")
    if not code or code not in art.blocks:
        return False, no_update
    entry = ((art.blocks.get(code) or {}).get(side) or {})
    body = entry.get("markdown")
    if not body:
        return True, dbc.Alert(
            entry.get("error")
            or "No rendered reading was published for this market and side.",
            color="secondary")
    # The published markdown, VERBATIM. Re-laying it out from the structured block would
    # rebuild the "caveats off" switch crowdmon deliberately declines to have.
    return True, html.Div([
        dcc.Markdown("```\n{}\n```".format(body)),
        _history_figure(art, code, side),
    ])


def _history_figure(art, code: str, side: str):
    frame = artifact.history(art, code)
    if frame.empty:
        return html.Div()
    d = pd.to_numeric(frame["damage_{}_pct".format(side)], errors="coerce")
    fig = go.Figure(go.Scatter(x=pd.to_datetime(frame["report_date"]), y=d, mode="lines",
                               line={"color": vc.CATEGORY_DIVERGING_UP, "width": 1.4},
                               connectgaps=False, name="D pct"))
    fig.update_layout(
        template="plotly_dark", height=240, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": vc.TEXT_COLOR}, margin={"l": 50, "r": 20, "t": 34, "b": 30},
        title={"text": "D percentile through time. Gaps are weeks with no score, "
                       "not weeks at zero.", "font": {"size": 12}},
        xaxis={"gridcolor": vc.GRID_COLOR},
        yaxis={"range": [0, 1.02], "gridcolor": vc.GRID_COLOR})
    # No offside history: the trigger overlay is published for the current week only.
    return dcc.Graph(figure=fig, config={"displayModeBar": False})
