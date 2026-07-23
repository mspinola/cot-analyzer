from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.utils as utils
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from dash import Input, Output, State, callback, dcc, html, no_update

import viz_config
import viz_constants as vc

# Register this file as a page
dash.register_page(
    __name__,
    path='/positioning'
)


def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    return html.Div([
        dbc.Container([
            dbc.Accordion([
                dbc.AccordionItem([
                    dbc.Row([
                        dbc.Col([
                            html.Label("Lookback:", style=vc.label_style),
                            dbc.Select(
                                persistence='session',
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
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.Label("Target Date:", style=vc.label_style),
                            dcc.Dropdown(
                                id='positioning_date_selector',
                                options=[{'label': d, 'value': d} for d in get_indexer().get_available_dates()],
                                value=get_indexer().get_available_dates()[0] if get_indexer().get_available_dates() else None,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                searchable=True,
                                clearable=False,
                            )
                        ], xs=12, md="auto"),

                        dbc.Col([
                            # Positioning Table Extended Data
                            html.Label("Table Data Selector", style=vc.label_style),
                            dcc.Dropdown(
                                persistence='session',
                                id='cot_positioning_column_select_input',
                                options=[
                                    {'label': const.DATE, 'value': const.DATE},
                                    {'label': const.LOOKBACK, 'value': const.LOOKBACK},
                                    {'label': const.OPEN_INTEREST, 'value': const.OPEN_INTEREST},
                                    {'label': "OI Percentage", 'value': "OI Percentage"},
                                    {'label': "Net Positioning", 'value': "Net Positioning"}
                                ],
                                value=None,
                                multi=True,
                                className="mb-3 bg-dark text-white border-secondary",
                                searchable=False,
                                clearable=True,
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.Label("Asset Class Selector", style=vc.label_style),
                            dcc.Dropdown(
                                persistence='session',
                                id='page_positioning_asset_selector',
                                options=[{'label': x, 'value': x}
                                        for x in get_indexer().get_asset_classes()],
                                value=get_indexer().get_asset_classes(),  # This selects every item in the list by default
                                multi=True,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                searchable=False,
                                clearable=True,
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            dbc.Button([html.I(className="bi bi-download mt-3"), "Download CSV"],
                                    id="btn_download_csv",
                                    color='secondary',
                                    outline=True,
                                    size="sm",
                                    className="mb-3 mt-3",
                                    style=vc.button_style
                            ),
                            dcc.Download(id="download_positioning_csv"),
                        ], xs=12, md="auto"),
                    ], align="center"),
                ],
                title="TABLE CONFIGURATION",
                item_id="chart_config"),
            ],
            start_collapsed=True, # Keeps it clean on initial mobile load
            flush=True,
            className="mb-3",
            style={'backgroundColor': vc.BACKGROUND_COLOR, 'position': 'relative', 'zIndex': 1000}),

            html.Hr(style=vc.hr_style),

            dbc.Row([
                dcc.Loading(
                    id="loading-positioning-table",
                    type="default",  # Options: "graph", "cube", "circle", "dot", or "default"
                    children=html.Div(id='cot_positioning'),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
        ], fluid=True),
    ])


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('positioning_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('positioning_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('positioning_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('cot_positioning', 'children'),
    [Input('page_positioning_asset_selector', 'value'),
     Input('cot_positioning_column_select_input', 'value'),
     Input('global_lookback_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('positioning_date_selector', 'value')]
)
def get_CFTC_df_selection(assets, selected_columns, lookback, palette_name, target_date):
    """Dash callback to update the positioning table"""
    print(f"Updating positioning table with assets={assets}, selected_columns={selected_columns}, lookback={lookback}, target_date={target_date}")
    utils.cot_logger.info(f"Updating positioning table with assets={assets}, selected_columns={selected_columns}, lookback={lookback}, target_date={target_date}")
    if not lookback:
        lookback = "Custom"

    if not assets:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    asset_list = (assets,) if isinstance(assets, str) else tuple(assets)

    # Only estimate if the user has selected an estimate column to display, otherwise skip to save time
    estimate_gap = any("Estimate" in col for col in selected_columns) if selected_columns else False
    df = get_indexer().get_positioning_table_by_asset_class(asset_list, lookback, estimate_gap, target_date)

    if df.empty:
        return html.P("No data available for the selected asset classes.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})

    cftc_date = "unknown"
    if not df.empty:
        df = df.sort_values(by=[const.ASSET_CLASS, const.SYMBOL], ascending=[True, True])

        # Always keep core columns, then add user-selected extras
        idx_col_header_name = " " + lookback + const.IDX
        COMM_IDX = const.COMM + idx_col_header_name
        LRG_IDX = const.LARGE + idx_col_header_name
        SML_IDX = const.SMALL + idx_col_header_name

        zscore_col_header_name = " " + lookback + const.ZSCORE
        COMM_ZS = const.COMM + zscore_col_header_name
        LRG_ZS = const.LARGE + zscore_col_header_name
        SML_ZS = const.SMALL + zscore_col_header_name

        movement_zscore_col_header_name = " " + lookback + const.MOMENTUM
        COMM_MZS = const.COMM + movement_zscore_col_header_name
        LRG_MZS = const.LARGE + movement_zscore_col_header_name
        SML_MZS = const.SMALL + movement_zscore_col_header_name

        COMM_WILLCO = const.WILLCO + " " + lookback
        LIQUIDITY_STRAIN = const.LIQUIDITY_STRAIN + const.ZSCORE + " " + lookback
        OI_ZSCORE = const.OPEN_INTEREST + " " + lookback + const.ZSCORE

        spearman_col_header_name = " " + lookback + const.SPEARMAN
        COMM_SPR = const.COMM + spearman_col_header_name
        LRG_SPR = const.LARGE + spearman_col_header_name
        SML_SPR = const.SMALL + spearman_col_header_name

        core_cols = [
            const.ASSET_CLASS, const.SYMBOL, const.NAME,
            COMM_IDX, LRG_IDX, SML_IDX,
            COMM_ZS, LRG_ZS, SML_ZS,
            COMM_MZS, LRG_MZS, SML_MZS,
            const.LW_LRG_SENTIMENT,
            COMM_WILLCO,
            LIQUIDITY_STRAIN,
            OI_ZSCORE,
            COMM_SPR, LRG_SPR, SML_SPR,
            "Max Pain", "Delta IV"
        ]

        # Map dropdown values to actual DataFrame column names if they differ
        requested_cols = []
        requested_cols = [selected_columns] if isinstance(selected_columns, str) else selected_columns
        if requested_cols and "Net Positioning" in requested_cols:
            i = requested_cols.index("Net Positioning")
            requested_cols[i:i+1] = [const.COMM_NET, const.LARGE_NET, const.SMALL_NET]

        if requested_cols and "Estimated Indexing" in requested_cols:
            i = requested_cols.index("Estimated Indexing")
            requested_cols[i:i+1] = [const.COMM_IDX_EST, const.LARGE_IDX_EST, const.SMALL_IDX_EST]
        if requested_cols and "Net Estimated Positioning" in requested_cols:
            i = requested_cols.index("Net Estimated Positioning")
            requested_cols[i:i+1] = [const.COMM_NET_EST, const.LARGE_NET_EST, const.SMALL_NET_EST]

        if requested_cols and "OI Percentage" in requested_cols:
            i = requested_cols.index("OI Percentage")
            requested_cols[i:i+1] = [const.COMM_PCT_OI, const.LARGE_PCT_OI, const.SMALL_PCT_OI]

        # Move selected columns to the front, but keep the original order within selected and non-selected groups
        joined_list = core_cols + requested_cols if requested_cols is not None else core_cols
        sorted_list = []
        if joined_list is not None:
            matches = [s for s in joined_list if const.DATE in s]
            non_matches = [s for s in joined_list if const.DATE not in s]
            sorted_list = matches + non_matches
            matches = [s for s in sorted_list if const.NAME in s]
            non_matches = [s for s in sorted_list if const.NAME not in s]
            sorted_list = matches + non_matches

        final_cols = [c for c in sorted_list if c in df.columns]
        cftc_date = df[const.DATE].iloc[0]
        df_display = df[final_cols]

    viz_config.get_palette(palette_name)

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.P([
                    "Data as of ",
                    html.Span(f"{cftc_date}", style={'color': vc.TEXT_COLOR, 'font': '1.5rem', 'marginLeft': '10px'}),
                    ], style={
                        'textAlign': 'left',
                        'color': vc.TEXT_COLOR,
                        'font': '1.5rem'
                    }
                ),
            ], width="auto")
        ], justify='center'),
        html.H4("Market Positioning Data", className="text-center mb-3 mt-4", style={'color': vc.BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold'}),
        get_asset_class_accordions(df_display, lookback, start_collapsed=False)
    ])


def get_asset_class_accordions(df, lookback, start_collapsed=False):
    accordion_items = []
    all_item_ids = []

    # Group dataframe by the Asset Class column
    for asset_class, group_df in df.groupby('Asset Class'):

        grid_col_defs = []
        for col in group_df.columns:
            if col == "Asset Class":
                continue
            col_def = {"field": col}
            if col == "Symbol":
                col_def["pinned"] = "left"
            elif col == "Max Pain":
                col_def["valueFormatter"] = {"function": "params.value ? (params.value < 10 ? d3.format(',.4f')(params.value) : params.value < 100 ? d3.format(',.2f')(params.value) : d3.format(',.0f')(params.value)) : 'N/A'"}
            elif col == "Delta IV":
                col_def["valueFormatter"] = {"function": "params.value ? (Math.abs(params.value) < 0.1 ? d3.format(',.3f')(params.value) : Math.abs(params.value) < 1.0 ? d3.format(',.2f')(params.value) : d3.format(',.1f')(params.value)) : 'N/A'"}
            grid_col_defs.append(col_def)

        # Create a targeted AG Grid for just this group
        grid = dag.AgGrid(
            # Add a dynamic ID so Dash is forced to rebuild the table when lookback changes
            id=f"ag-grid-{asset_class.replace(' ', '-')}-{lookback}",
            rowData=group_df.to_dict("records"),
            # Exclude 'Asset Class' from the columns since it's in the title
            columnDefs=grid_col_defs,
            className="ag-theme-quartz-dark",
            style={"fontSize": "11px"},
            defaultColDef={
                "sortable": True,
                "filter": True,
                "wrapHeaderText": True,
                "autoHeaderHeight": True,
                "width": 100,
                "minWidth": 80,
                "maxWidth": 130,
            },
            dashGridOptions={
                "domLayout": "autoHeight",
                "pagination": False,
                "rowHeight": 26,
            },
            columnSize="responsiveSizeToFit",
        )

        # Wrap the grid in an Accordion Item
        item = dbc.AccordionItem(
            children=[grid],
            title=f"{asset_class} ({len(group_df)} Assets)",
            item_id=asset_class
        )
        accordion_items.append(item)
        all_item_ids.append(asset_class)

    # Return the master Accordion container
    return dbc.Accordion(
        accordion_items,
        always_open=True,  # Allows multiple asset classes to be open at once
        active_item=[] if start_collapsed else all_item_ids,
    )

@callback(
    Output("download_positioning_csv", "data"),
    Input("btn_download_csv", "n_clicks"),
    State('cot_positioning_column_select_input', 'value'),
    State('global_lookback_store', 'data'),
    State('positioning_date_selector', 'value'),
    State('page_positioning_asset_selector', 'value'),
    prevent_initial_call=True,
)
def download_positioning_table(n_clicks, selected_columns, lookback, target_date, assets):
    if not n_clicks or not assets:
        return None

    if not lookback:
        lookback = "Custom"

    asset_list = (assets,) if isinstance(assets, str) else tuple(assets)

    # Fetch the dataframe
    estimate_gap = any("Estimate" in col for col in selected_columns) if selected_columns else False
    df = get_indexer().get_positioning_table_by_asset_class(asset_list, lookback, estimate_gap, target_date)
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    return dcc.send_data_frame(df.to_csv, f"COT_Positioning_{timestamp}.csv", index=False)
