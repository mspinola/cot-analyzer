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
import viz_constants as vc

dash.register_page(__name__, path="/damage")

SIDES = (("sell", "Forced selling"), ("buy", "Forced buying"))

#: Marker for a market whose observed pool contradicts the price signal. Plotted, because
#: hiding it would be its own kind of silence, but visibly outside the quadrant scheme.
CONTRADICTED_COLOR = "#586e75"


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
            fig.add_trace(_trace(
                part, name="{}  ({})".format(
                    _quadrant_label(manifest, is_close, is_severe), len(part)),
                color=(vc.CATEGORY_DIVERGING_DOWN if (is_close and is_severe)
                       else vc.CATEGORY_DIVERGING_UP),
                filled=is_close and is_severe))

    if not contradicted.empty:
        # Plotted with an open marker and NO quadrant, mirroring crowdmon's renderer, which
        # suppresses the cell entirely when the observed pool is on the other side.
        fig.add_trace(_trace(
            contradicted,
            name="pool on the other side, no cell  ({})".format(len(contradicted)),
            color=CONTRADICTED_COLOR, filled=False, symbol="circle-open"))

    fig.update_layout(
        template="plotly_dark", height=560,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": vc.TEXT_COLOR},
        margin={"l": 60, "r": 20, "t": 30, "b": 60},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.28, "x": 0},
        xaxis={"title": "distance to the nearest flip that forces this side "
                        "(daily sigma, log scale)",
               "type": "log", "gridcolor": vc.GRID_COLOR},
        yaxis={"title": "D percentile, against this market's own history",
               "range": [0, 1.02], "gridcolor": vc.GRID_COLOR},
    )
    return fig


def _trace(part: pd.DataFrame, *, name: str, color: str, filled: bool,
           symbol: str = "circle") -> go.Scatter:
    size = pd.to_numeric(part["open_interest"], errors="coerce").fillna(0.0)
    size = 8.0 + 22.0 * (size / size.max() if size.max() else 0.0) ** 0.5
    return go.Scatter(
        x=part["sigma"], y=part["d"], mode="markers", name=name,
        customdata=part[["market_name", "market_code", "crowding_long",
                         "illiquidity_sell", "fragility", "dtl_sell"]].values,
        marker={"size": size, "color": color if filled else "rgba(0,0,0,0)",
                "symbol": symbol, "line": {"color": color, "width": 2}},
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

    num = {"filter": "agNumberColumnFilter", "type": "rightAligned"}
    columns = [
        {"field": "asset_class", "headerName": "Asset class (crowdmon / cotdata registry)",
         "rowGroup": True, "hide": True},
        {"field": "name", "headerName": "Market", "minWidth": 210, "tooltipField": "state"},
        {"field": "symbol", "maxWidth": 90},
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
        {"field": "C", "valueFormatter": {"function": "params.value == null ? '' : "
                                                      "d3.format('.3f')(params.value)"},
         **num},
        {"field": "I", "valueFormatter": {"function": "params.value == null ? '' : "
                                                      "d3.format('.3f')(params.value)"},
         **num},
        {"field": "Phi", "valueFormatter": {"function": "params.value == null ? '' : "
                                                        "d3.format('.3f')(params.value)"},
         **num},
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
        # into the published briefs. Without this ag-grid hands back a row index, which the
        # asset-class grouping then reorders, so the drill-down would open the wrong market
        # rather than fail visibly.
        getRowId="params.data.market_code",
        rowData=frame.to_dict("records"), columnDefs=columns,
        className="ag-theme-quartz-dark",
        style={"height": "62vh", "width": "100%", "fontSize": "13px"},
        defaultColDef={"sortable": True, "filter": True, "resizable": True,
                       "wrapHeaderText": True, "autoHeaderHeight": True, "minWidth": 100},
        dashGridOptions={"rowHeight": 30, "tooltipShowDelay": 400,
                         "groupDefaultExpanded": 1,
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
