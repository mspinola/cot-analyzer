import urllib.parse
from datetime import datetime
from typing import NamedTuple

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import (
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
)

import components.plot_helpers as helpers
import viz_config
import viz_constants as vc

dash.register_page(__name__, path="/heatmap")

def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.P(
                        f"All data on this page reflects the official "
                        f"Commitments of Traders reporting snapshot as of Tuesday market close "
                        f"({datetime.strptime(get_indexer().get_available_dates()[0], '%Y-%m-%d').strftime('%B %d, %Y') if get_indexer().get_available_dates() else 'Unknown Date'}).",
                        style={
                            'textAlign': 'center',
                            'color': vc.TEXT_COLOR,
                            'fontSize': '0.9rem',
                            'marginBottom': '20px',
                            'marginTop': '20px',
                            'fontStyle': 'italic'
                        }
                    )
                ], width=12)
            ]),

            # Command Center (Glassmorphism Control Panel)
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Lookback Window", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='heatmap_lookback_selector',
                                        persistence='session',
                                        options=[
                                            {"label": "26 Weeks", "value": "26"},
                                            {"label": "52 Weeks", "value": "52"},
                                            {"label": "Custom", "value": "Custom"},
                                        ],
                                        value="Custom",
                                        className="bg-dark text-white border-secondary",
                                        style={'borderRadius': '8px'}
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Target Date", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dcc.Dropdown(
                                        id='heatmap_date_selector',
                                        options=[{'label': d, 'value': d} for d in get_indexer().get_available_dates()],
                                        value=get_indexer().get_available_dates()[0] if get_indexer().get_available_dates() else None,
                                        className="dash-dropdown bg-dark text-white",
                                        searchable=True,
                                        clearable=False,
                                        style={'borderRadius': '8px'}
                                    )
                                ], xs=12, md=3, className="mb-3 mb-md-0 border-end border-secondary px-md-3 hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Asset Classes", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Checklist(
                                        persistence='session',
                                        id='page_heatmap_selector',
                                        options=[{"label": x, "value": x} for x in get_indexer().get_asset_classes()],
                                        value=get_indexer().get_asset_classes(),
                                        inline=True,
                                        switch=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.95rem"}
                                    ),
                                ], xs=12, md=5, className="mb-3 mb-md-0 px-md-4"),

                                dbc.Col([
                                    dbc.Button(
                                        "Download CSV",
                                        id="btn-csv-export",
                                        size="sm",
                                        className="border-secondary text-white w-100 h-100",
                                        style={'backgroundColor': 'transparent', 'borderColor': 'rgba(147, 161, 161, 0.2)'}
                                    )
                                ], xs=12, md=2, className="d-flex align-items-center justify-content-end")
                            ], align="center")
                        ]),
                        className="mb-4 shadow-sm",
                        style={
                            "backgroundColor": "rgba(30, 30, 30, 0.6)",
                            "border": "1px solid rgba(255, 255, 255, 0.1)",
                            "borderRadius": "12px",
                            "backdropFilter": "blur(12px)"
                        }
                    )
                ], width=12)
            ], style={'position': 'sticky', 'top': '10px', 'zIndex': 1000}),

            dbc.Row([
                dcc.Loading(
                    id="loading-heatmap",
                    type="dot",
                    children=html.Div(id='heatmap_display_container'),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
        ], fluid=True),
    ])


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('heatmap_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('heatmap_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('heatmap_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val



# Neutral dimmed text colour for a cell with nothing to say.
DIM_TEXT = "rgba(255, 255, 255, 0.35)"


class GridColors(NamedTuple):
    """The colour set the style builders draw from.

    Passed in rather than closed over so the style rules can be built, and tested,
    without rendering a page or reaching a data store.
    """
    bull: str
    bear: str
    bull_near: str
    bear_near: str
    dim: str = DIM_TEXT


def grid_colors(color_palette):
    """Resolve a palette into the grid's colour set."""
    bull = color_palette[3]
    bear = color_palette[0]
    if bear.lower() in ("#f87171", "#dc322f", "#ff453a", "#e70307", "#ff007f"):
        bear = "#FF4D4D"
    return GridColors(
        bull=bull,
        bear=bear,
        bull_near=helpers.hex_to_rgba(bull, vc.INDEX_RAMP_ALPHA_APPROACH),
        bear_near=helpers.hex_to_rgba(bear, vc.INDEX_RAMP_ALPHA_APPROACH),
    )


# The two index families get different extreme bands. Normalizing by open interest
# removes the secular growth in contract size, so the normalized series sits at the
# ends of its own range far less often -- 95/5 would leave it almost never lit.
#
# Each band gets a ramp rather than a binary lit/dim: the gate keeps full saturation
# and its background wash, and two fainter text-only steps mark the approach, so a
# market walking toward a setup is visible before the week it arrives. Stops come
# from cotmetrics so this page and the emailed HTML step at the same values.
#
# styleConditions is first-match-wins (hence the catch-all "true" last), so these run
# strongest first. The bull and bear conditions are mutually exclusive, so pairing
# them per step is safe.
def oi_styles_for(colors, highlight=None):
    """Cell styling for the OI Z column.

    Same gate as the emailed HTML's OI Z column, which reads the constant too. Read at
    call time rather than at import so the threshold stays overridable in tests.
    """
    return [
        {"condition": f"Math.abs(params.value) >= {const.OI_ZSCORE_HIGHLIGHT_THRESHOLD}",
         "style": {"color": highlight or colors.bull}},
        {"condition": "true", "style": {"color": colors.dim}},
    ]


def setup_styles_for(state_col, role, high_val, low_val, colors,
                     near=const.SETUP_NEAR_WIDTH):
    """Style a positioning-index cell from its *row's* setup state.

    The state is resolved once per row by utils.setup_state and carried on the
    matrix, so these conditions only read it. Re-deriving `comm >= 95 AND lrg <= 5
    AND sml <= 5` as AG Grid condition strings would fork the setup rules between
    the strategy and the grid.

    A full setup washes every leg in the band. A near setup tints only the legs
    actually at or near their own gate, leaving the blocking leg neutral so it reads
    as the reason the setup has not fired.
    """
    st = f"params.data['{state_col}']"
    v = "params.value"
    is_eq = f"params.data['{const.IS_EQUITY_COL}']"
    # Equities skip the speculator legs in is_setup, so their spec cells never tint
    # on a near state.
    eq_guard = "" if role == "comm" else f" && !{is_eq}"
    if role == "comm":
        near_bull, near_bear = f"{v} >= {high_val - near}", f"{v} <= {low_val + near}"
    else:
        near_bull, near_bear = f"{v} <= {low_val + near}", f"{v} >= {high_val - near}"

    # An equity setup is decided by Commercials alone, so its spec legs can sit
    # anywhere. Washing one that disagrees would colour a cell against its own
    # value: DOW is a bear setup whose Small Specs sit at 64, and a red mid-range
    # cell invites being read as a bearish extreme. Commodity rows are unaffected,
    # since a full state already required every leg through its gate.
    if role == "comm":
        agrees_bull = agrees_bear = ""
    else:
        agrees_bull = f" && (!{is_eq} || {near_bull})"
        agrees_bear = f" && (!{is_eq} || {near_bear})"

    return [
        {"condition": f"{st} === '{const.SETUP_BULL}'{agrees_bull}",
         "style": {"backgroundColor": f"{colors.bull}{vc.INDEX_WASH}", "color": colors.bull}},
        {"condition": f"{st} === '{const.SETUP_BEAR}'{agrees_bear}",
         "style": {"backgroundColor": f"{colors.bear}{vc.INDEX_WASH}", "color": colors.bear}},
        {"condition": f"{st} === '{const.SETUP_NEAR_BULL}' && {near_bull}{eq_guard}",
         "style": {"color": colors.bull_near}},
        {"condition": f"{st} === '{const.SETUP_NEAR_BEAR}' && {near_bear}{eq_guard}",
         "style": {"color": colors.bear_near}},
        {"condition": "true", "style": {"color": colors.dim}},
    ]


@callback(
    Output('heatmap_display_container', 'children'),
    [Input('page_heatmap_selector', 'value'),
     Input('global_lookback_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('heatmap_date_selector', 'value')]
)
def render_heatmap_layout(assest_classes, lookback, palette_name, target_date):
    utils.cot_logger.info(f"Rendering matrix with Asset Classes: {assest_classes}, Lookback: {lookback}, Palette: {palette_name}, Date: {target_date}")

    if not assest_classes:
        return html.P("Select an asset class to view the signal matrix.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    if not lookback:
        lookback = "Custom"

    df = get_matrix_data(assest_classes, lookback, target_date)
    if df.empty:
        return html.P("No data available.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})

    matrix_date = ""
    if not df.empty:
        matrix_date = df.iloc[0]["Date"]
    header_name = f"Asset Info — {matrix_date}" if matrix_date else "Asset Info"

    color_palette = viz_config.get_palette(palette_name)
    colors = grid_colors(color_palette)
    BULL_COLOR, BEAR_COLOR, DIM_TEXT = colors.bull, colors.bear, colors.dim

    oi_styles = oi_styles_for(colors, highlight=color_palette[2])

    _RAW = models.RAW_PF.band
    _NORM = models.NPF.band

    index_styles = setup_styles_for(const.SETUP_CLS_COL, "comm", *_RAW, colors=colors)
    spec_styles = setup_styles_for(const.SETUP_CLS_COL, "spec", *_RAW, colors=colors)
    index_norm_styles = setup_styles_for(const.SETUP_NPF_COL, "comm", *_NORM, colors=colors)
    spec_norm_styles = setup_styles_for(const.SETUP_NPF_COL, "spec", *_NORM, colors=colors)

    inst_sentiment_styles = [
        {"condition": f"params.value <= {const.LW_LRG_SENTIMENT_MIN_THRESHOLD}", "style": {"color": BULL_COLOR}},
        {"condition": f"params.value >= {const.LW_LRG_SENTIMENT_MAX_THRESHOLD}", "style": {"color": BEAR_COLOR}},
        {"condition": "true", "style": {"color": DIM_TEXT}}
    ]

    willco_styles = [
        {"condition": f"params.value >= {const.WILLCO_MAX_THRESHOLD}", "style": {"color": BULL_COLOR}},
        {"condition": f"params.value <= {const.WILLCO_MIN_THRESHOLD}", "style": {"color": BEAR_COLOR}},
        {"condition": "true", "style": {"color": DIM_TEXT}}
    ]

    pull_styles = [
        {"condition": "params.value > 0", "style": {"color": BULL_COLOR, "fontSize": "0.68rem"}},
        {"condition": "params.value < 0", "style": {"color": BEAR_COLOR, "fontSize": "0.68rem"}},
        {"condition": "true", "style": {"color": DIM_TEXT, "fontSize": "0.68rem"}}
    ]

    setup_styles = [
        {"condition": "params.value === 'Bullish'", "style": {"color": BULL_COLOR, "fontSize": "11px", "opacity": "0.9"}},
        {"condition": "params.value === 'Bearish'", "style": {"color": BEAR_COLOR, "fontSize": "11px", "opacity": "0.9"}},
        {"condition": "true", "style": {"color": vc.TEXT_COLOR, "fontSize": "11px"}}
    ]


    def with_bg(styles, bg="rgba(255, 255, 255, 0.04)"):
        return [{"condition": s["condition"], "style": {**s["style"], "backgroundColor": s["style"].get("backgroundColor", bg)}} for s in styles]

    columnDefs = [
        {
            "headerName": header_name,
            "children": [
                {"field": "Asset Class", "filter": True, "pinned": "left", "width": 120},
                {
                    "field": "Asset",
                    "filter": True,
                    "pinned": "left",
                    "width": 150,
                    "cellRenderer": "markdown",
                    "valueFormatter": {"function": "params.value ? params.value.replace(/^\\\\[(.+?)\\\\]\\\\(.+?\\\\)$/, '$1') : params.value"},
                },
                {"field": "Tape Bias", "pinned": "left", "width": 90, "cellStyle": {"styleConditions": setup_styles}},
                {"field": "Signals", "pinned": "left", "width": 160, "cellRenderer": "SignalBadgesRenderer", "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            # The two blocks mirror the two npf books. Raw/all-three-legs/95-5 is the
            # Raw PF baseline (Raw CLS 95/5); OI-normalized/Comm+Small/80-20 is
            # NPF CS 80/20, the deployable headline. Large Specs is absent from the
            # second block because the CS gate drops that leg -- showing it here would
            # invite reading a column the book does not gate on.
            "headerName": f"Positioning · {models.RAW_PF.title}",
            "children": [
                {"field": "Comm Index", "headerTooltip": f"Williams Commercial Index, on net contracts. The C leg of the {models.RAW_PF.title} gate", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": index_styles}},
                {"field": "Lrg Index", "headerTooltip": f"Large Speculators positioning index, on net contracts. The L leg of the {models.RAW_PF.title} gate, coloured only when opposed to Commercials, since that is the only configuration counted as a setup leg", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": spec_styles}},
                {"field": "Sml Index", "headerTooltip": f"Small Traders positioning index, on net contracts. The S leg of the {models.RAW_PF.title} gate, coloured only when opposed to Commercials, since that is the only configuration counted as a setup leg", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": spec_styles}, "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            "headerName": f"Positioning · {models.NPF.title}",
            # Wider than the default 90: this group is only two columns, so it gets the
            # least room to flex into and the header is the longest of the two blocks.
            "children": [
                {"field": "Comm Index Norm", "headerName": "Comm Index", "minWidth": 115, "headerTooltip": "Williams Commercial Index built on net / open interest, so contract-size growth is out of the level. The C leg of the NPF CS gate", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": index_norm_styles}},
                {"field": "Sml Index Norm", "headerName": "Sml Index", "minWidth": 115, "headerTooltip": "Small Traders positioning index built on net / open interest. The S leg of the NPF CS gate, coloured only when opposed to Commercials", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": spec_norm_styles}, "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            "headerName": "Index Momentum",
            "children": [
                {
                    "field": "Comm Move",
                    "headerTooltip": f"Commercial {vc.MOMENTUM_UNIT_PHRASE}",
                    "valueFormatter": {"function": "d3.format(',.0f')(params.value)"},
                    "cellRenderer": "MomentumRenderer",
                    "cellRendererParams": {
                        "maxThreshold": const.MOMENTUM_MAX_THRESHOLD,
                        "minThreshold": const.MOMENTUM_MIN_THRESHOLD,
                        "neutralColor": DIM_TEXT
                    }
                },
                {
                    "field": "Lrg Move",
                    "headerTooltip": f"Large Speculator {vc.MOMENTUM_UNIT_PHRASE}",
                    "valueFormatter": {"function": "d3.format(',.0f')(params.value)"},
                    "cellRenderer": "MomentumRenderer",
                    "cellRendererParams": {
                        "maxThreshold": const.MOMENTUM_MAX_THRESHOLD,
                        "minThreshold": const.MOMENTUM_MIN_THRESHOLD,
                        "neutralColor": DIM_TEXT
                    }
                },
                {
                    "field": "Sml Move",
                    "headerTooltip": f"Small Trader {vc.MOMENTUM_UNIT_PHRASE}",
                    "valueFormatter": {"function": "d3.format(',.0f')(params.value)"},
                    "cellRenderer": "MomentumRenderer",
                    "cellRendererParams": {
                        "maxThreshold": const.MOMENTUM_MAX_THRESHOLD,
                        "minThreshold": const.MOMENTUM_MIN_THRESHOLD,
                        "neutralColor": DIM_TEXT
                    },
                    "headerClass": "group-border-right",
                    "cellClass": "group-border-right"
                },
            ]
        },
        {
            "headerName": "Friction & Flow",
            "children": [
                {"field": "WILLCO", "headerTooltip": "Williams Commercial Index (Thresholds: <= 20 Bearish / >= 80 Bullish)", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": willco_styles}},
                {"field": "Inst Sentiment", "headerTooltip": "Institutional Speculator Sentiment (Thresholds: <= 20 Bullish / >= 80 Bearish)", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": inst_sentiment_styles}, "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            "headerName": "Open Interest",
            "children": [
                {
                    "field": "OI Z",
                    "headerTooltip": "Open Interest Z-score relative to history",
                    "valueFormatter": {"function": "d3.format('+.2f')(params.value)"},
                    "cellStyle": {"styleConditions": oi_styles}
                },
                {
                    "field": "Max Pain Pull",
                    "headerTooltip": "Max Pain Pull (%)",
                    "cellStyle": {"styleConditions": pull_styles},
                    "valueFormatter": {"function": "params.value ? d3.format('+.1f')(params.value) + '%' : '–'"}
                },
                {
                    "field": "Delta IV",
                    "headerTooltip": "Delta Intrinsic Value",
                    "cellStyle": {"fontSize": "0.68rem", "color": DIM_TEXT},
                    "valueFormatter": {"function": "params.value ? (Math.abs(params.value) < 0.1 ? d3.format(',.3f')(params.value) : Math.abs(params.value) < 1.0 ? d3.format(',.2f')(params.value) : d3.format(',.1f')(params.value)) : '–'"}
                },
            ]
        }
    ]

    # Convert asset column to markdown links
    df['Asset'] = df['Asset'].apply(lambda x: f"[{x}](/oi_alignment?asset={urllib.parse.quote(x)})")

    grid = dag.AgGrid(
        id="heatmap-matrix-grid",
        rowData=df.to_dict("records"),
        columnDefs=columnDefs,
        className="ag-theme-quartz-dark",
        style={"height": "80vh", "width": "100%", "fontSize": "13px"},
        defaultColDef={
            "sortable": True,
            "filter": True,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
            "minWidth": 90,
            "flex": 1,
        },
        dashGridOptions={
            "rowHeight": 32,
            "pagination": False,
            "tooltipShowDelay": 500,
        },
    )

    return dbc.Row([
        dbc.Col(grid, width=12)
    ])


clientside_callback(
    ClientsideFunction(
        namespace='clientside',
        function_name='export_heatmap_csv'
    ),
    Output("btn-csv-export", "n_clicks"),
    Input("btn-csv-export", "n_clicks"),
    prevent_initial_call=True
)
