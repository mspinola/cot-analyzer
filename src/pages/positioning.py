import constants as const
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc

from dash import State, html, dcc, Input, Output, callback
from datetime import datetime


# Register this file as a page
dash.register_page(
    __name__,
    path='/positioning'
)


layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Label("Lookback:", style=const.label_style),
                dbc.Select(
                    id='positioning_lookback_selector',
                    options=[
                        {"label": "26 Weeks", "value": "26"},
                        {"label": "52 Weeks", "value": "52"},
                        {"label": "Custom", "value": "Custom"},
                    ],
                    value="Custom",
                    size="sm",
                    className="mb-3 bg-dark text-white border-secondary",
                )
            ], width="auto"),

            dbc.Col([
                # Positioning Table Extended Data
                html.Label("Table Data Selector", style=const.label_style),
                dcc.Dropdown(
                    persistence=True,
                    id='cot_positioning_column_select_input',
                    multi=True,
                    className="mb-3 bg-dark text-white border-secondary",
                    searchable=False,
                    clearable=True,
                ),
            ], width="auto", className="ms-2 mt-2"),

            dbc.Col([
                    html.Label("Asset Class Selector", style=const.label_style),
                    dcc.Dropdown(
                        persistence=True,
                        id='page_positioning_selector',
                        options=[{'label': x, 'value': x}
                                 for x in cotIndexer.get_asset_classes()],
                        value=cotIndexer.get_asset_classes(),  # This selects every item in the list by default
                        multi=True,
                        className="dash-dropdown bg-dark text-white",
                        searchable=False,
                        clearable=True,
                    ),
                    ], width="auto"),

            dbc.Col([
                dbc.Button([html.I(className="bi bi-download mt-3"), "Download CSV"],
                           id="btn_download_csv",
                           color='secondary',
                           outline=True,
                           size="sm",
                           className="mt-3",
                           style=const.button_style
                ),
                dcc.Download(id="download_positioning_csv"),
            ], width="auto", className="ms-1"),
        ], align="center", className="mb-4", style=const.row_start_style),
    ], fluid=True),

    html.Hr(style=const.hr_style),

    dbc.Row([
        dcc.Loading(
            id="loading-positioning-table",
            type="default", # Options: "graph", "cube", "circle", "dot", or "default"
            children=html.Div(id='cot_positioning'),
            color=const.BRIGHTER_TEXT_COLOR
        )
    ], justify='center')
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('positioning_lookback_selector', 'value')
)
def update_global_lookback(value):
    print("positioning cb select lb: ", value)
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"

@callback(
    Output('positioning_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    print("positioning cb redirect lb: ", value)
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    Output('cot_positioning', 'children'),
    [Input('page_positioning_selector', 'value'),
     Input('cot_positioning_column_select_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data'),
     Input('global_lookback_store', 'data')]
)
def get_CFTC_df_selection(assets, selected_columns, setup, lookback):
    """Dash callback to update the positioning table"""
    # TODO use setup to color index values in the table

    if not assets:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': const.TEXT_COLOR})

    asset_list = [assets] if isinstance(assets, str) else assets
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list, lookback)

    cftc_date = "unknown"
    if not df.empty:
        df = df.sort_values(by=[const.ASSET_CLASS, const.NAME], ascending=[True, True])

        # Always keep core columns, then add user-selected extras
        if lookback == "26":
            COMM_IDX = const.COMM_26_IDX
            LRG_IDX = const.LARGE_26_IDX
            SML_IDX = const.SMALL_26_IDX
            COMM_ZS = const.COMM_26_ZSCORE
            LRG_ZS = const.LARGE_26_ZSCORE
            SML_ZS = const.SMALL_26_ZSCORE
            COMM_SPR = const.COMM_26_CORR
            LRG_SPR = const.LARGE_26_CORR
            SML_SPR = const.SMALL_26_CORR
            WILLCO = const.WILLCO_26
        elif lookback == "52":
            COMM_IDX = const.COMM_52_IDX
            LRG_IDX = const.LARGE_52_IDX
            SML_IDX = const.SMALL_52_IDX
            COMM_ZS = const.COMM_52_ZSCORE
            LRG_ZS = const.LARGE_52_ZSCORE
            SML_ZS = const.SMALL_52_ZSCORE
            COMM_SPR = const.COMM_52_CORR
            LRG_SPR = const.LARGE_52_CORR
            SML_SPR = const.SMALL_52_CORR
            WILLCO = const.WILLCO_52
        else:
            COMM_IDX = const.COMM_CUSTOM_IDX
            LRG_IDX = const.LARGE_CUSTOM_IDX
            SML_IDX = const.SMALL_CUSTOM_IDX
            COMM_ZS = const.COMM_CUSTOM_ZSCORE
            LRG_ZS = const.LARGE_CUSTOM_ZSCORE
            SML_ZS = const.SMALL_CUSTOM_ZSCORE
            COMM_SPR = const.COMM_CUSTOM_CORR
            LRG_SPR = const.LARGE_CUSTOM_CORR
            SML_SPR = const.SMALL_CUSTOM_CORR
            WILLCO = const.WILLCO_CUSTOM

        core_cols = [
            const.ASSET_CLASS, const.SYMBOL, const.NAME,
            COMM_IDX, LRG_IDX, SML_IDX, WILLCO
            ]

        # Map dropdown values to actual DataFrame column names if they differ
        requested_cols = []
        requested_cols = [selected_columns] if isinstance(selected_columns, str) else selected_columns

        joined_list = core_cols + requested_cols if requested_cols is not None else core_cols
        final_cols = [c for c in joined_list if c in df.columns]
        cftc_date = df[const.DATE].iloc[0]
        df2 = df[final_cols]

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.P([
                    "Data as of ",
                    html.Span(f"{cftc_date}", style={'color': const.TEXT_COLOR, 'font': '1.5rem', 'marginLeft': '10px'}),
                    ], style={
                        'textAlign': 'left',
                        'color': const.TEXT_COLOR,
                        'font': '1.5rem'
                    }
                ),
            ], width="auto")
        ], justify='center'),
        dbc.Table.from_dataframe(
            df2,
            bordered=True,
            hover=True,
            responsive=True,
            striped=True,
            style={"minWidth": "1200px"},
        )
    ])


@callback(
    Output("download_positioning_csv", "data"),
    Input("btn_download_csv", "n_clicks"),
    State('page_positioning_selector', 'value'),  # Capture current filter state
    prevent_initial_call=True,
)
def download_positioning_table(n_clicks, selected_values):
    print(selected_values)
    if not n_clicks or not selected_values:
        return None

    asset_list = [selected_values] if isinstance(
        selected_values, str) else selected_values

    # Fetch the dataframe
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list, lookback)
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    return dcc.send_data_frame(df.to_csv, f"COT_Positioning_{timestamp}.csv", index=False)


@callback(
    [Output('cot_positioning_column_select_input', 'options'),
     Output('cot_positioning_column_select_input', 'value')],
    [Input('page_positioning_selector', 'value'),
     Input('global_lookback_store', 'data')]
)
def cot_positioning_column_select_input(value, lookback):
    options = []
    options.append({'label': 'Date', 'value': 'Date'})
    options.append({'label': const.COMM_NET, 'value': const.COMM_NET})
    options.append({'label': const.LARGE_NET, 'value': const.LARGE_NET})
    options.append({'label': const.SMALL_NET, 'value': const.SMALL_NET})

    zscore_col_header_name = lookback + " Zscore"
    COMM_ZS = "Comm " + zscore_col_header_name
    LRG_ZS = "Lrg Spec " + zscore_col_header_name
    SML_ZS = "Sml Spec " + zscore_col_header_name

    spearman_col_header_name = lookback + " Spearman"
    COMM_SPR = "Comm " + spearman_col_header_name
    LRG_SPR = "Lrg Spec " + spearman_col_header_name
    SML_SPR = "Sml Spec " + spearman_col_header_name

    willco_col_header_name = "WILLCO " + lookback
    WILLCO = willco_col_header_name

    options.append({'label': COMM_ZS, 'value': COMM_ZS})
    options.append({'label': LRG_ZS, 'value': LRG_ZS})
    options.append({'label': SML_ZS, 'value': SML_ZS})
    options.append({'label': COMM_SPR, 'value': COMM_SPR})
    options.append({'label': LRG_SPR, 'value': LRG_SPR})
    options.append({'label': SML_SPR, 'value': SML_SPR})
    options.append({'label': WILLCO, 'value': WILLCO})


    default_value = None
    # default_value = options[0].get('value') if options else None
    return options, default_value
