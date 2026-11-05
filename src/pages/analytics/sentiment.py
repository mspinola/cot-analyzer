"""Sentiment: NAAIM and AAII against SPY and S&P 500 speculator positioning. LOCAL ONLY.

Registered only when `local_pages.enabled()`: the histories it draws are licensed to the
operator and must not reach the public site. Unregistered, the path 404s and the navbar
omits it; see `local_pages` for why that needs no other code.

Rendered per request in `layout()`, like Market Internals, at the default 3-year index;
the lookback toggle (1Y/3Y) redraws every index view, the summary and the caption, and
the quadrant's year buttons window its scatter. Reads are cached per lookback on the
stores' own dates. Every number, label and cutoff comes from `components.sentiment`;
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
WORDS_CHART = "sentiment_words_chart"
QUADRANT_CHART = "sentiment_quadrant_chart"
QUADRANT_YEARS = "sentiment_quadrant_years"
LOOKBACK = "sentiment_lookback"
SUMMARY = "sentiment_summary"
CAPTION = "sentiment_caption"
MAX = "max"
ZOOM_SINK = "sentiment_zoom_sink"

if local_pages.enabled():
    dash.register_page(
        __name__,
        path='/sentiment',
        title='Sentiment (local) | COT Analyzer',
        description='NAAIM exposure and AAII bulls minus bears against SPY and S&P 500 '
                    'speculator positioning, weekly. Local runs only.',
    )

CARD_STYLE = {
    "backgroundColor": "rgba(28,28,28,0.55)",
    "border": "1px solid rgba(255,255,255,0.10)",
}
TITLE_STYLE = {"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.95rem", "marginBottom": "0.2rem"}
SUB_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem", "marginBottom": "0.4rem"}
NOTE_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem"}
GRAPH_CONFIG = {"displayModeBar": False, "responsive": True}


def _card(title, subtitle, figure, graph_id=None, controls=None):
    graph = (dcc.Graph(id=graph_id, figure=figure, config=GRAPH_CONFIG) if graph_id
             else dcc.Graph(figure=figure, config=GRAPH_CONFIG))
    body = [html.Div(title, style=TITLE_STYLE), html.Div(subtitle, style=SUB_STYLE)]
    if controls is not None:
        body.append(controls)
    return dbc.Card(dbc.CardBody([*body, graph], className="p-3"),
                    style=CARD_STYLE, className="mb-3")


#: The scatter has no date axis for Plotly's own range buttons to sit on, so the same
#: ladder is a radio row drawn to look like them: the rangeselector's background, its
#: font and size, the selected one lit.
_YEAR_LABEL = {"backgroundColor": vc.BLUE_BACKGROUND, "color": vc.BRIGHTER_TEXT_COLOR,
               "fontSize": "0.75rem", "padding": "2px 8px", "marginRight": "4px",
               "borderRadius": "3px", "cursor": "pointer", "border": "1px solid transparent"}
_YEAR_CHECKED = {"border": f"1px solid {vc.BRIGHTER_TEXT_COLOR}"}


def _button_radio(radio_id, options, value, justify):
    return dbc.RadioItems(id=radio_id, options=options, value=value, inline=True,
                          persistence="session", inputClassName="btn-check",
                          labelStyle=_YEAR_LABEL, labelCheckedStyle=_YEAR_CHECKED,
                          className=f"year-buttons d-flex flex-wrap {justify} mb-1")


def year_buttons():
    options = ([{"label": f"{n}Y", "value": n} for n in sentiment.QUADRANT_YEARS]
               + [{"label": "Max", "value": MAX}])
    return _button_radio(QUADRANT_YEARS, options, sentiment.QUADRANT_DEFAULT_YEARS,
                         "justify-content-end")


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


def years_value(value):
    """The radio value as the figure's `years`: an int, or None for Max."""
    return None if value in (None, MAX) else int(value)


def layout(**_):
    read = sentiment.read()
    palette = viz_config.get_palette()
    colors = plot_colors.grid_colors(palette)
    head = [
        html.H4("Sentiment, words against money", style={"color": vc.BRIGHTER_TEXT_COLOR}),
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
                  "crowd leans long, below 20 it "
                  f"is washed out. Opens on {sentiment.OPEN_YEARS} years; the buttons "
                  "change the window.",
                  sentiment.price_sentiment_figure(read, colors, palette), PRICE_CHART),
            _card("Words against money",
                  "Two pairs on the same range index, each sentiment series beside "
                  "the S&P 500 futures group closest to it: NAAIM (managers) with large "
                  "specs, AAII (individuals) with non-reportables. Under each, words minus "
                  "money: above zero the crowd says more than the futures hold.",
                  sentiment.words_money_figure(read, colors, palette), WORDS_CHART),
            _card("Where the latest week sits",
                  "NAAIM's index against the speculators' over the chosen window, "
                  "older weeks dimmer, the last "
                  f"{sentiment.TRAIL_WEEKS} as a path. Position, not forecast. The "
                  "window counts back from the latest week both are stored.",
                  sentiment.quadrant_figure(read, colors), QUADRANT_CHART,
                  controls=year_buttons()),
        ]
    return dbc.Container([*head, *cards, html.Div(_notes(read), id=CAPTION, className="mt-2"),
                          dcc.Store(id=ZOOM_SINK)],
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

    # Fires on load too, so a lookback kept from earlier in the session (persistence)
    # redraws what layout() drew at the default.
    @callback(Output(PRICE_CHART, "figure"), Output(WORDS_CHART, "figure"),
              Output(SUMMARY, "children"), Output(CAPTION, "children"),
              Input(LOOKBACK, "value"))
    def _lookback(value):
        read = sentiment.read(lookback_value(value))
        palette = viz_config.get_palette()
        colors = plot_colors.grid_colors(palette)
        return (sentiment.price_sentiment_figure(read, colors, palette),
                sentiment.words_money_figure(read, colors, palette),
                sentiment.summary(read), _notes(read))

    @callback(Output(QUADRANT_CHART, "figure"), Input(QUADRANT_YEARS, "value"),
              Input(LOOKBACK, "value"))
    def _quadrant_window(value, lookback):
        colors = plot_colors.grid_colors(viz_config.get_palette())
        return sentiment.quadrant_figure(sentiment.read(lookback_value(lookback)), colors,
                                         years_value(value))
