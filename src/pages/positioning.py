import constants
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
                # Positioning Table Extended Data
                html.Label("Table Data Selector", style=constants.label_style),
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
                    html.Label("Asset Class Selector", style=constants.label_style),
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
                           style=constants.button_style
                ),
                dcc.Download(id="download_positioning_csv"),
            ], width="auto", className="ms-1"),
        ], align="center", className="mb-4", style=constants.row_start_style),
    ], fluid=True),

    html.Hr(style=constants.hr_style),

    # dbc.Row([
    #     dbc.Col([
    #         html.H4("Positioning Data as of .",
    #             style={
    #                 'textAlign': 'left',
    #                 'color': constants.BRIGHTER_TEXT_COLOR
    #                 }
    #         )
    #     ], width=6, className="ms-3")
    # ], justify='left'),

    dbc.Row([
        html.Div(id='cot_positioning')
    ], justify='center')
])


@callback(
    Output('cot_positioning', 'children'),
    [Input('page_positioning_selector', 'value'),
     Input('cot_positioning_column_select_input', 'value')]
)
def get_CFTC_df_selection(assets, selected_columns):
    """Dash callback to update the positioning table"""
    # Determine the list of asset classes to fetch
    if not assets:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': constants.TEXT_COLOR})

    asset_list = [assets] if isinstance(assets, str) else assets
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list)

    cftc_date = "unknown"
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

        # Always keep core columns, then add user-selected extras
        core_cols = ['Asset Class', 'Symbol', 'Name', 'Commercials', 'Large Specs', 'Small Specs']

        # Map dropdown values to actual DataFrame column names if they differ
        requested_cols = []
        requested_cols = [selected_columns] if isinstance(selected_columns, str) else selected_columns

        joined_list = core_cols + requested_cols if requested_cols is not None else core_cols
        final_cols = [c for c in joined_list if c in df.columns]
        cftc_date = df['Date'].iloc[0]
        df2 = df[final_cols]

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.P([
                    "Data as of ",
                    html.Span(f"{cftc_date}", style={'color': constants.TEXT_COLOR, 'font': '1.5rem', 'marginLeft': '10px'}),
                    ], style={
                        'textAlign': 'left',
                        'color': constants.TEXT_COLOR,
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
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list)
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    return dcc.send_data_frame(df.to_csv, f"COT_Positioning_{timestamp}.csv", index=False)


@callback(
    [Output('cot_positioning_column_select_input', 'options'),
     Output('cot_positioning_column_select_input', 'value')],
    Input('page_positioning_selector', 'value')
)
def cot_positioning_column_select_input(value):
    options = []
    options.append({'label': 'Comm Net Pos', 'value': 'Comm Net Pos'})
    options.append({'label': 'Lrg Spec Net Pos', 'value': 'Lrg Spec Net Pos'})
    options.append({'label': 'Sml Spec Net Pos', 'value': 'Sml Spec Net Pos'})
    options.append({'label': 'Date', 'value': 'Date'})
    default_value = None
    # default_value = options[0].get('value') if options else None
    return options, default_value
