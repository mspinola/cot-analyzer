"""Aggregate Exposure: what a set of markets is holding, in dollars.

The one question the rest of this app cannot answer. Every other view normalizes each
market against itself, which is what lets 47 markets share one axis on the Crowding
Strip and what the positioning index has always done. None of those numbers can be
added: a percentile has no units.

This page adds. `cotmetrics.exposure` converts contracts into USD notional and then into
USD daily risk, which is the only rung that is both summable and comparable, and this
page draws the total against the set's own composite price.

It is deliberately a SET view rather than a market view. A single market's dollar
exposure is the positioning index wearing bigger numbers; the reason to convert units at
all is to make a total mean something.

Three things this page says in words because the picture cannot carry them, and all
three are failures of the printed reference it was built from:

- which markets are in the total, and which were dropped and why
- whether a retired constituent is truncating the series
- that positioning is as-of Tuesday and published the following Friday
"""
import dash
import dash_bootstrap_components as dbc
from cotmetrics import exposure
from cotmetrics.indexer import get_indexer
from dash import Input, Output, callback, dcc, html

import components.exposure_traces as exposure_traces
import viz_config
import viz_constants as vc
from components.plot_colors import grid_colors

dash.register_page(__name__, path='/exposure')

LEG_OPTIONS = [{"label": exposure.LEG_LABELS[k], "value": k}
               for k in (exposure.LEG_SPEC, exposure.LEG_COMM,
                         exposure.LEG_LARGE, exposure.LEG_SMALL)]

UNIT_OPTIONS = [
    {"label": "USD risk", "value": exposure_traces.UNIT_RISK},
    {"label": "USD notional", "value": exposure_traces.UNIT_NOTIONAL},
]


def _class_options():
    return [{"label": c, "value": c} for c in get_indexer().get_asset_classes()]


def membership(agg, names):
    """Who is in the total, who is not, and what the completeness rule cost.

    An aggregate is a claim about a set, so the set is part of the reading. This is the
    page's whole disclosure surface and it is drawn above the figure rather than under
    it, because a reader who has already formed an impression of the line is not going
    to revise it on the strength of a footnote.
    """
    included = len(agg.coverage)
    bits = [html.Span(f"{included} of {len(names)} markets summed",
                      style={"color": vc.BRIGHTER_TEXT_COLOR})]

    if agg.dropped:
        # Named, not counted. "2 markets dropped" tells a reader that something is
        # missing without telling them whether it is the one they came to look at.
        bits.append(html.Span(
            " · dropped: " + ", ".join(f"{n} ({why.split(',')[0]})"
                                       for n, why in sorted(agg.dropped.items()))))
    if "end" in agg.bounded_by:
        # The failure this exists for: a retired constituent stops the whole series and
        # the chart simply ends, with nothing on it saying the other members did not.
        last = agg.coverage.get(agg.bounded_by["end"], (None, None))[1]
        bits.append(html.Span(
            f" · series ENDS {last:%b %Y} because {agg.bounded_by['end']} does; "
            f"remove it from Markets to follow the rest",
            style={"color": vc.BRIGHTER_TEXT_COLOR}))
    if "start" in agg.bounded_by:
        first = agg.coverage.get(agg.bounded_by["start"], (None, None))[0]
        bits.append(html.Span(
            f" · starts {first:%b %Y} with {agg.bounded_by['start']}"))
    if agg.weeks_lost:
        bits.append(html.Span(
            f" · {agg.weeks_lost} week(s) not summed, where some member had no value"))
    return bits


def caption(frame, unit, leg):
    """The reading, in words, including the one fact the chart cannot show.

    The publication lag is the sentence that matters. The series is plotted at its
    as-of date, which is what the number is, and drawn against a price line that was
    knowable that day. Read literally it says the positioning was knowable too, and it
    was not until the Friday. A static PDF can leave that to a footnote; this page sits
    two clicks from a setup gate.
    """
    if frame is None or frame.empty:
        return ""
    latest = frame.iloc[-1]
    rank = latest[exposure_traces.UNIT_RANK_COLUMN[unit]]
    divisor, suffix = exposure_traces.unit_scale(frame[unit])
    value = latest[unit] / divisor
    side = "net long" if value >= 0 else "net short"
    rank_text = (f"the {rank:.0f}th percentile of its own history"
                 if rank == rank else "no percentile yet, under two years of history")
    return (
        f"{exposure.LEG_LABELS[leg]} are {side} ${abs(value):,.1f}{suffix} "
        f"({exposure_traces.UNIT_LABELS[unit]}) as of {frame.index[-1]:%B %d, %Y}, "
        f"which is {rank_text}. {exposure_traces.UNIT_NOTES[unit]} "
        f"The shaded band is the 10th to 90th percentile of the history up to each "
        f"week, so it carries no look-ahead and neither does the percentile. "
        f"Positioning is as-of Tuesday and published the following Friday: it is "
        f"plotted at the Tuesday it describes, which is three days before anyone could "
        f"have acted on it. The top panel is an equal-weight composite of the same "
        f"markets, rebased to 100, and not any index you can trade."
    )


def layout(**kwargs):
    return html.Div([
        dbc.Container([
            dbc.Card(dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("Asset Classes", style={**vc.label_style,
                                                           "fontSize": "0.8rem",
                                                           "textTransform": "uppercase"}),
                        dcc.Dropdown(id='exposure_class_selector', multi=True,
                                     persistence='session',
                                     options=_class_options(), value=["Equities"],
                                     className="cot-dropdown"),
                    ], xs=12, md=5, className="px-md-2"),

                    dbc.Col([
                        # Per-market, because the constraining member is usually not a
                        # whole class. The live case: NKD retired from the COT in March
                        # 2026 and its class did not, so a class-level control cannot
                        # recover the five months the other equity markets still have.
                        html.Label("Markets", style={**vc.label_style,
                                                     "fontSize": "0.8rem",
                                                     "textTransform": "uppercase"}),
                        dcc.Dropdown(id='exposure_member_selector', multi=True,
                                     options=[], value=[], placeholder="all",
                                     className="cot-dropdown"),
                    ], xs=12, md=5, className="px-md-2 mt-2 mt-md-0"),
                ], align="center"),

                dbc.Row([
                    dbc.Col([
                        html.Label("Leg", style={**vc.label_style, "fontSize": "0.8rem",
                                                 "textTransform": "uppercase"}),
                        dbc.Select(id='exposure_leg_selector', options=LEG_OPTIONS,
                                   value=exposure.LEG_SPEC, size="sm",
                                   className="bg-dark text-white border-secondary"),
                    ], xs=6, md=4, className="px-md-2 mt-2 mt-md-0"),

                    dbc.Col([
                        html.Label("Unit", style={**vc.label_style,
                                                  "fontSize": "0.8rem",
                                                  "textTransform": "uppercase"}),
                        dbc.RadioItems(id='exposure_unit_selector',
                                       persistence='session',
                                       options=UNIT_OPTIONS,
                                       value=exposure_traces.UNIT_RISK, inline=True,
                                       style={"color": vc.BRIGHTER_TEXT_COLOR,
                                              "fontSize": "0.85rem"}),
                    ], xs=6, md=3, className="px-md-2 mt-2 mt-md-0"),
                ], align="center", className="mt-2"),
            ]), className="mb-2 shadow-sm",
                style={"backgroundColor": "rgba(30, 30, 30, 0.6)",
                       "border": "1px solid rgba(255, 255, 255, 0.1)",
                       "borderRadius": "8px"}),

            html.Div(id='exposure_membership',
                     style={"color": vc.TEXT_COLOR, "fontSize": "0.8rem",
                            "marginBottom": "6px"}),

            dcc.Loading(dcc.Graph(id='exposure_chart',
                                  config={"displayModeBar": False,
                                          "responsive": True}),
                        type="default", color=vc.TEXT_COLOR),

            html.P(id='exposure_caption',
                   style={"color": vc.TEXT_COLOR, "fontSize": "0.85rem",
                          "fontStyle": "italic", "marginTop": "6px"}),
        ], fluid=False)
    ])


@callback(
    Output('exposure_member_selector', 'options'),
    Output('exposure_member_selector', 'value'),
    Input('exposure_class_selector', 'value'),
)
def member_options(asset_classes):
    """Every market in the chosen classes, all selected.

    Selected rather than left blank so the control reads as the membership of the total
    rather than as a filter over it. Removing one is then a visible subtraction from a
    stated set, which is the only edit this page wants to make easy.
    """
    names = _names_in(asset_classes)
    return [{"label": n, "value": n} for n in names], names


def _names_in(asset_classes):
    if not asset_classes:
        return []
    return sorted(i.name for i in get_indexer().instruments.values()
                  if i.asset_class in asset_classes)


@callback(
    Output('exposure_chart', 'figure'),
    Output('exposure_membership', 'children'),
    Output('exposure_caption', 'children'),
    Input('exposure_class_selector', 'value'),
    Input('exposure_member_selector', 'value'),
    Input('exposure_leg_selector', 'value'),
    Input('exposure_unit_selector', 'value'),
    Input('session_palette_theme_asset_store', 'data'),
)
def render_exposure(asset_classes, members, leg, unit, palette_name):
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    leg = leg or exposure.LEG_SPEC
    unit = unit or exposure_traces.UNIT_RISK

    if not asset_classes:
        empty = exposure_traces.build_figure(None, None, unit=unit, colors=colors,
                                             palette=palette)
        return empty, "Select an asset class.", ""

    # An empty member list is the moment between a class change and the callback that
    # repopulates it, not a request for an empty total.
    names = list(members) if members else _names_in(asset_classes)
    agg = exposure.aggregate_exposure(names, leg=leg)
    composite = exposure.composite_price_index(
        list(agg.coverage), dates=agg.frame.index) if not agg.frame.empty else None

    figure = exposure_traces.build_figure(
        agg.frame, composite, unit=unit, colors=colors, palette=palette,
        leg_label=exposure.LEG_LABELS[leg], set_label=", ".join(asset_classes),
        leg=leg)
    return figure, membership(agg, names), caption(agg.frame, unit, leg)
