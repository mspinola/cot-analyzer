import constants as const
import pages.helpers as helpers
import utils
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from dash import State, html, dcc, Input, Output, callback
from plotly.subplots import make_subplots


# Register this file as a page
dash.register_page(
    __name__,
    path='/analysis'
)

AVAILABLE_PLOTS = {
    "oi_pct": "Net Position % of OI",
    "willco": "WillCo",
    "spearman": "Spearman Correlation",
    "net_pos": "Net Positions",
    "index": "Positioning Index",
    "zscore": "Positioning Z-Score",
    "momentum": "Momentum Index",
    "tension": "Tension Oscillator"
}

layout = html.Div([
    dbc.Container([
        dbc.Accordion([
            dbc.AccordionItem([
                dbc.Row([
                    dbc.Col([
                        html.Label("Lookback:", style=const.label_style),
                        dbc.Select(
                            id='analysis_lookback_selector',
                            options=[
                                {"label": "26 Weeks", "value": "26"},
                                {"label": "52 Weeks", "value": "52"},
                                {"label": "Custom", "value": "Custom"},
                            ],
                            value="Custom",
                            size="sm",
                            className="mb-3 bg-dark text-white border-secondary",
                        )
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Class Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='analysis_single_asset_class_input',
                            options=[{'label': x, 'value': x}
                                    for x in cotIndexer.get_asset_classes()],
                            value=f"{cotIndexer.get_default_asset_class()}",
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='analysis_single_asset_filter_input',
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Visible Plots", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='analysis_plot_selector',
                            options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                            value=list(AVAILABLE_PLOTS.keys()),  # Default to all selected
                            multi=True,
                            className="mb-3 dash-dropdown bg-dark text-white",
                            style={'minWidth': '250px'}
                        ),
                    ], xs=12, md=4),
                ], align="center"),
            ],
            title="CHART CONFIGURATION",
            item_id="chart_config"),
        ],
        start_collapsed=True, # Keeps it clean on initial mobile load
        flush=True,
        className="mb-3",
        style={'backgroundColor': const.BACKGROUND_COLOR}),

        html.Hr(style=const.hr_style),

        dbc.Row([
            dcc.Loading(
                id="loading-analysis-graph",
                type="default", # Options: "graph", "cube", "circle", "dot", or "default"
                children=html.Div(id='analysis_stack'),
                color=const.BRIGHTER_TEXT_COLOR
            )
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('analysis_lookback_selector', 'value')
)
def update_global_lookback(value):
    print("analysis cb select lb: ", value)
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"

@callback(
    Output('analysis_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    print("analysis cb redirect lb: ", value)
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    [Output('analysis_single_asset_filter_input', 'options'),
     Output('analysis_single_asset_filter_input', 'value')],
    Input('analysis_single_asset_class_input', 'value')
)
def update_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    default_value = options[0].get('value') if options else None
    return options, default_value


@callback(
    Output('analysis_page_header', 'children'),
    [Input('analysis_single_asset_class_input', 'value'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('global_lookback_store', 'data')]
)
def update_analysis_header(asset_class, asset_name, lookback):
    if not asset_name:
        return html.H6("SELECT ASSET", style={'color': const.TEXT_COLOR})

    # Fetch latest data point
    df = cotIndexer.get_symbols_data(asset_name, lookback)
    if df is None or df.empty:
        return html.H6(f"{asset_class} | {asset_name}", style={'color': const.BRIGHTER_TEXT_COLOR})

    # Get the latest Z-score (using the column name from your DataFrame)
    latest_z = df['comms_zscore'].iloc[-1]

    # Determine color logic based on your 95/5 (Z=2.0) setup
    z_color = "#4ade80" if latest_z >= 2.0 else "#f87171" if latest_z <= -2.0 else const.TEXT_COLOR

    return [
        html.Div([
            html.Span("CURRENT COMMERCIAL Z-SCORE: ", style={'color': const.BRIGHTER_TEXT_COLOR, 'fontSize': '0.9rem'}),
            html.Span(f"{latest_z:.2f}", style={'color': z_color, 'fontSize': '1.1rem', 'fontWeight': 'bold'})
        ])
    ]


@callback(
    Output('analysis_stack', 'children'),
    [Input('session_palette_theme_asset_store', 'data'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data'),
     Input('global_lookback_store', 'data'),
     Input('analysis_plot_selector', 'value')]
)
def update_analysis_stack(palette_name, asset, setup, lookback, selected_plots):
    if not asset or not selected_plots:
        return html.P("SELECT ASSET AND PLOTS", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    df = cotIndexer.get_symbols_data(asset, lookback)
    if df is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    min_threshold, max_threshold = utils.parse_setup_thresholds(setup)
    color_palette = cotIndexer.get_palette(palette_name)
    num_rows = len(selected_plots)
    titles = [AVAILABLE_PLOTS[p] for p in selected_plots]

    # Define specs based on selection
    specs = []
    for p in selected_plots:
        if p in ["oi_pct", "willco", "spearman", "net_pos", "index", "zscore", "momentum", "tension"]:
            specs.append([{"secondary_y": True}])
        else:
            specs.append([{"secondary_y": False}])

    fig = helpers.get_make_subplots_for_plots(num_rows, 1, titles, specs)

    cur_row = 1
    cur_col = 1
    setup_highlight_row = None  # TODO make this a list
    for p in selected_plots:
        if p == "oi_pct":
            fig = helpers.get_open_interest_percent_plot(fig, df, cur_row, cur_col, color_palette)
        elif p == "willco":
            fig = helpers.get_willco_plot(fig, df, cur_row, cur_col, color_palette)
        elif p == "spearman":
            fig = helpers.get_spearman_plot(fig, df, cur_row, cur_col, color_palette)
        elif p == "net_pos":
            fig = helpers.get_net_pos_plot(fig, df, cur_row, cur_col, color_palette)
        elif p == "index":
            setup_highlight_row = cur_row
            fig = helpers.get_index_plot(fig, df, cur_row, cur_col, color_palette, min_threshold, max_threshold)
        elif p == "zscore":
            fig = helpers.get_zscore_plot(fig, df, cur_row, cur_col, color_palette)
        elif p == "momentum":
            fig = helpers.get_momentum_plot(fig, df, cur_row, cur_col, color_palette)
        elif p == "tension":
            fig = helpers.get_tension_plot(fig, df, cur_row, cur_col, color_palette)
        cur_row += 1

    if fig is not None:
        fig = helpers.get_setup_highlighting(fig, df, min_threshold, max_threshold, setup_highlight_row, cur_col)
        fig = helpers.get_update_xaxes_for_plots(fig, df)
        fig = helpers.get_update_layout_for_plots(fig, num_rows)

    return dcc.Graph(figure=fig,
                     config={
                        'scrollZoom': False,
                        'doubleClick': 'reset',
                        'displayModeBar': True,
                        'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                        'responsive': True},
                        style={'width': '100%'
                    })
