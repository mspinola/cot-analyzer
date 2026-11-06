"""Sentiment: NAAIM and AAII against SPY. LOCAL ONLY.

Registered only when `local_pages.enabled()`: the histories it draws are licensed to the
operator and must not reach the public site. Unregistered, the path 404s and the navbar
omits it; see `local_pages` for why that needs no other code.

Rendered per request in `layout()`, like Market Internals, at the default 3-year index;
the lookback toggle (1Y/3Y) redraws both views, the summary and the caption. Reads are
cached per lookback on the stores' own dates. There is no COT pairing view: the
component's docstring says why. Every number, label and cutoff comes from `components.sentiment`;
this file only lays the views out.
"""
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, clientside_callback, dcc, html

import components.sentiment as sentiment
import local_pages
import viz_config
import viz_constants as vc
from components import plot_colors

PRICE_CHART = "sentiment_price_chart"
COLUMNS_CHART = "sentiment_columns_chart"
LOOKBACK = "sentiment_lookback"
SUMMARY = "sentiment_summary"
CAPTION = "sentiment_caption"
ZOOM_SINK = "sentiment_zoom_sink"
#: Each card's PNG export: the card body is the picture, the button sits in its
#: header. Keyed by the view's short name, which also names the file.
EXPORTS = {"price": ("sentiment_price_export", "sentiment_price_export_btn"),
           "columns": ("sentiment_columns_export", "sentiment_columns_export_btn")}
COLUMNS_ZOOM_SINK = "sentiment_columns_zoom_sink"

if local_pages.enabled():
    dash.register_page(
        __name__,
        path='/sentiment',
        title='Sentiment (local) | COT Analyzer',
        description='NAAIM exposure and AAII bulls minus bears against SPY, weekly. '
                    'Local runs only.',
    )

CARD_STYLE = {
    "backgroundColor": "rgba(28,28,28,0.55)",
    "border": "1px solid rgba(255,255,255,0.10)",
}
TITLE_STYLE = {"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.95rem", "marginBottom": "0.2rem"}
SUB_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem", "marginBottom": "0.4rem"}
NOTE_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem"}
GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}


def export_button(view):
    """The card's PNG export, the Crowd board's button. exportBoardImage drops every
    button from its clone, so this one never appears in its own picture."""
    _, button_id = EXPORTS[view]
    return html.Div([
        dbc.Button("📸 Export PNG", id=button_id, size="sm",
                   style={"color": vc.TEXT_COLOR}),
        dbc.Tooltip("This card as one image: title, notes and chart.",
                    target=button_id, placement="bottom"),
    ])


def _card(title, subtitle, figure, graph_id=None, controls=None, export=None):
    graph = (dcc.Graph(id=graph_id, figure=figure, config=GRAPH_CONFIG) if graph_id
             else dcc.Graph(figure=figure, config=GRAPH_CONFIG))
    head = html.Div(title, style=TITLE_STYLE)
    if export is not None:
        head = html.Div([head, export_button(export)],
                        className="d-flex justify-content-between align-items-start")
    body = [head]
    if subtitle:
        body.append(html.Div(subtitle, style=SUB_STYLE))
    if controls is not None:
        body.append(controls)
    # The body is what an export captures, so it carries the export's container id.
    kw = {"id": EXPORTS[export][0]} if export is not None else {}
    return dbc.Card(dbc.CardBody([*body, graph], className="p-3", **kw),
                    style=CARD_STYLE, className="mb-3")


#: The lookback toggle is a radio row drawn to look like Plotly's range buttons: the
#: rangeselector's background, its font and size, the selected one lit.
_YEAR_LABEL = {"backgroundColor": vc.BLUE_BACKGROUND, "color": vc.BRIGHTER_TEXT_COLOR,
               "fontSize": "0.75rem", "padding": "2px 8px", "marginRight": "4px",
               "borderRadius": "3px", "cursor": "pointer", "border": "1px solid transparent"}
_YEAR_CHECKED = {"border": f"1px solid {vc.BRIGHTER_TEXT_COLOR}"}


def _button_radio(radio_id, options, value, justify):
    # No persistence: layout() draws every chart at the defaults, and the callbacks do
    # not fire on load (see below), so a restored value would disagree with the charts.
    return dbc.RadioItems(id=radio_id, options=options, value=value, inline=True,
                          inputClassName="btn-check",
                          labelStyle=_YEAR_LABEL, labelCheckedStyle=_YEAR_CHECKED,
                          className=f"year-buttons d-flex flex-wrap {justify} mb-1")


def lookback_buttons():
    """The index lookback, one control for the whole page: every index here shares it."""
    options = [{"label": f"{n}Y", "value": n} for n in sentiment.LOOKBACK_YEARS]
    return html.Div(
        [html.Span("Index lookback", style={**NOTE_STYLE, "marginRight": "8px"}),
         _button_radio(LOOKBACK, options, sentiment.DEFAULT_LOOKBACK, "")],
        className="d-flex align-items-center mb-3")


def lookback_value(value):
    """The radio value as a lookback in years, the default for anything unexpected."""
    try:
        years = int(value)
    except (TypeError, ValueError):
        return sentiment.DEFAULT_LOOKBACK
    return years if years in sentiment.LOOKBACK_YEARS else sentiment.DEFAULT_LOOKBACK


def _notes(read):
    return [html.P(p, style=NOTE_STYLE) for p in sentiment.caption(read)]


def layout(**_):
    read = sentiment.read()
    palette = viz_config.get_palette()
    colors = plot_colors.grid_colors(palette)
    head = [
        html.H4("Sentiment, NAAIM and AAII", style={"color": vc.BRIGHTER_TEXT_COLOR}),
        dbc.Badge("local only", color="warning", className="mb-2"),
    ]
    if read.awaiting:
        head.append(html.Div(f"Awaiting data for {', '.join(read.awaiting)}.",
                             style=NOTE_STYLE, className="mb-2"))
    head.append(html.Div(sentiment.summary(read), id=SUMMARY,
                         style={**NOTE_STYLE, "color": vc.BRIGHTER_TEXT_COLOR,
                                "fontSize": "0.9rem"}, className="mb-2"))
    cards = []
    if not read.frame.empty:
        # The toggle exists only with the charts it redraws, so its callback never
        # targets a chart the page did not render.
        head.append(lookback_buttons())
        cards = [
            _card("Sentiment against price",
                  f"NAAIM and AAII on one panel as range indexes: each "
                  f"{sentiment.AVERAGE_WEEKS}-week average placed between its own lowest "
                  "(0) and highest (100) reading of the lookback. Above 80 the "
                  "crowd leans long, below 20 it is washed out. Shaded weeks: SPY below "
                  "its high so far, amber 5-10%, orange 10-20%, red 20% or more. "
                  f"Opens on {sentiment.OPEN_YEARS} years; the buttons change the window.",
                  sentiment.price_sentiment_figure(read, colors, palette), PRICE_CHART,
                  export="price"),
            # No subtitle: each row's header carries the sentence that reads it.
            _card("Weekly columns", None,
                  sentiment.columns_figure(read, colors, palette), COLUMNS_CHART,
                  export="columns"),
        ]
    return dbc.Container([*head, *cards, html.Div(_notes(read), id=CAPTION, className="mt-2"),
                          dcc.Store(id=ZOOM_SINK), dcc.Store(id=COLUMNS_ZOOM_SINK)],
                         fluid=True, className="py-3")


# Re-fit the SPY panel to whatever window a button or a drag puts on screen: Plotly's
# autorange spans all of a trace's data, so a 1Y view would keep a 20-year axis. The
# handler is the one Exposure and Aggregation use, and the rules travel in the figure
# (`layout.meta.refit`). Registered only with the page, like the page itself.
if local_pages.enabled():
    clientside_callback(
        "window.dash_clientside.clientside.autoscale_y_axes",
        Output(ZOOM_SINK, "data"),
        Input(PRICE_CHART, "relayoutData"),
        State(PRICE_CHART, "id"),
        prevent_initial_call=True,
    )
    # The columns re-fit too, every panel with zero kept in view (the figure's refit).
    clientside_callback(
        "window.dash_clientside.clientside.autoscale_y_axes",
        Output(COLUMNS_ZOOM_SINK, "data"),
        Input(COLUMNS_CHART, "relayoutData"),
        State(COLUMNS_CHART, "id"),
        prevent_initial_call=True,
    )

    # The PNG exports, clientside like the Strip's and the Crowd board's: everything
    # in the picture is already in the browser. The container id says which card, and
    # the lookback rides along only to name the file.
    for _container, _button in EXPORTS.values():
        clientside_callback(
            "window.dash_clientside.clientside.export_sentiment_image",
            Output(_button, "n_clicks"),
            Input(_button, "n_clicks"),
            State(_container, "id"),
            State(LOOKBACK, "value"),
            prevent_initial_call=True,
        )

    # Not on load: layout() has already drawn every view at the defaults. Firing here
    # too drew each chart twice per page load, the second Plotly.react landing while the
    # first draw was still in flight, which left the page garbled after a refresh until
    # a click redrew it once.
    @callback(Output(PRICE_CHART, "figure"), Output(COLUMNS_CHART, "figure"),
              Output(SUMMARY, "children"), Output(CAPTION, "children"),
              Input(LOOKBACK, "value"), prevent_initial_call=True)
    def _lookback(value):
        read = sentiment.read(lookback_value(value))
        palette = viz_config.get_palette()
        colors = plot_colors.grid_colors(palette)
        return (sentiment.price_sentiment_figure(read, colors, palette),
                sentiment.columns_figure(read, colors, palette),
                sentiment.summary(read), _notes(read))
