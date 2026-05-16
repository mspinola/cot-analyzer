import constants as const
from indexer import cotIndexer
import utils

import dash
import dash_bootstrap_components as dbc

from dash import State, html, dcc, Input, Output, callback
import dash_ag_grid as dag
from datetime import datetime


# Register this file as a page
dash.register_page(
    __name__,
    path='/'
)


layout = html.Div([
    dbc.Container([
        dbc.Accordion([
            dbc.AccordionItem([
                dbc.Row([
                    dbc.Col([
                        html.Label("Lookback:", style=const.label_style),
                        dbc.Select(
                            persistence=True,
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
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Class Selector", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='page_positioning_asset_selector',
                            options=[{'label': x, 'value': x}
                                    for x in cotIndexer.get_asset_classes()],
                            value=cotIndexer.get_asset_classes(),  # This selects every item in the list by default
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
                                style=const.button_style
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
        style={'backgroundColor': const.BACKGROUND_COLOR}),

        html.Hr(style=const.hr_style),

        dbc.Row([
            dcc.Loading(
                id="loading-positioning-table",
                type="default",  # Options: "graph", "cube", "circle", "dot", or "default"
                children=html.Div(id='cot_positioning'),
                color=const.BRIGHTER_TEXT_COLOR
            )
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('positioning_lookback_selector', 'value')
)
def update_global_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"

@callback(
    Output('positioning_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    Output('cot_positioning', 'children'),
    [Input('page_positioning_asset_selector', 'value'),
     Input('cot_positioning_column_select_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data'),
     Input('global_lookback_store', 'data')]
)
def get_CFTC_df_selection(assets, selected_columns, setup, lookback):
    """Dash callback to update the positioning table"""
    utils.cot_logger.info(f"Updating positioning table with assets={assets}, selected_columns={selected_columns}, setup={setup}, lookback={lookback}")
    # TODO use setup to color index values in the table

    if not assets:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': const.TEXT_COLOR})
    asset_list = [assets] if isinstance(assets, str) else assets

    # Only estimate if the user has selected an estimate column to display, otherwise skip to save time
    estimate_gap = any("Estimate" in col for col in selected_columns) if selected_columns else False
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list, lookback, estimate_gap)

    cftc_date = "unknown"
    if not df.empty:
        df = df.sort_values(by=[const.ASSET_CLASS, const.SYMBOL], ascending=[True, True])

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
            const.ASSET_CLASS, const.SYMBOL,
            COMM_IDX, LRG_IDX, SML_IDX,
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

        if requested_cols and "Normalized Indexing" in requested_cols:
            i = requested_cols.index("Normalized Indexing")
            idx_norm_col_header_name = lookback + " Norm Idx"
            COMM_NORM_IDX = "Comm " + idx_norm_col_header_name
            LRG_NORM_IDX = "Lrg Spec " + idx_norm_col_header_name
            SML_NORM_IDX = "Sml Spec " + idx_norm_col_header_name
            requested_cols[i:i+1] = [COMM_NORM_IDX, LRG_NORM_IDX, SML_NORM_IDX]
        if requested_cols and "Net Normalized Positioning" in requested_cols:
            i = requested_cols.index("Net Normalized Positioning")
            requested_cols[i:i+1] = [const.COMM_NET_NORM, const.LARGE_NET_NORM, const.SMALL_NET_NORM]

        if requested_cols and "Z-Score" in requested_cols:
            i = requested_cols.index("Z-Score")
            zscore_col_header_name = lookback + " Zscore"
            COMM_ZS = "Comm " + zscore_col_header_name
            LRG_ZS = "Lrg Spec " + zscore_col_header_name
            SML_ZS = "Sml Spec " + zscore_col_header_name
            requested_cols[i:i+1] = [COMM_ZS, LRG_ZS, SML_ZS]

        if requested_cols and "Spearman Correlation" in requested_cols:
            i = requested_cols.index("Spearman Correlation")
            spearman_col_header_name = lookback + " Spearman"
            COMM_SPR = "Comm " + spearman_col_header_name
            LRG_SPR = "Lrg Spec " + spearman_col_header_name
            SML_SPR = "Sml Spec " + spearman_col_header_name
            requested_cols[i:i+1] = [COMM_SPR, LRG_SPR, SML_SPR]

        if requested_cols and "WILLCO" in requested_cols:
            i = requested_cols.index("WILLCO")
            willco_col_header_name = "WILLCO " + lookback
            WILLCO = willco_col_header_name
            requested_cols[i:i+1] = [WILLCO]

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

        get_asset_class_accordions(df_display)
    ])


def get_asset_class_accordions(df):
    accordion_items = []
    all_item_ids = []

    # Group dataframe by the Asset Class column
    for asset_class, group_df in df.groupby('Asset Class'):

        # Create a targeted AG Grid for just this group
        grid = dag.AgGrid(
            rowData=group_df.to_dict("records"),
            # Exclude 'Asset Class' from the columns since it's in the title
            columnDefs = [
                {"field": col, "pinned": "left"} if col == "Symbol" else {"field": col}
                for col in group_df.columns if col != "Asset Class"
            ],
            className="ag-theme-quartz-dark",
            defaultColDef={
                "sortable": True,
                "filter": True,
                "wrapHeaderText": True,
                "autoHeaderHeight": True,
                "initialWidth": 150,
            },
            dashGridOptions={"domLayout": "autoHeight", "pagination": False},
            columnSize="autoSize",
        )

        # Wrap the grid in an Accordion Item
        item = dbc.AccordionItem(
            children=[grid],
            title=f"{asset_class} ({len(group_df)} Assets)",  # e.g., "Metals (5 Assets)"
            item_id=asset_class
        )
        accordion_items.append(item)
        all_item_ids.append(asset_class)

    # Return the master Accordion container
    return dbc.Accordion(
        accordion_items,
        always_open=True,  # Allows multiple asset classes to be open at once
        active_item=all_item_ids,
    )

@callback(
    Output("download_positioning_csv", "data"),
    [Input("btn_download_csv", "n_clicks"),
     Input('cot_positioning_column_select_input', 'value'),
     Input('global_lookback_store', 'data')],
    State('page_positioning_asset_selector', 'value'),  # Capture current filter state
    prevent_initial_call=True,
)
def download_positioning_table(n_clicks, selected_columns, lookback, assets):
    if not n_clicks or not assets:
        return None

    asset_list = [assets] if isinstance(assets, str) else assets

    # Fetch the dataframe
    estimate_gap = any("Estimate" in col for col in selected_columns) if selected_columns else False
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list, lookback, estimate_gap)
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    return dcc.send_data_frame(df.to_csv, f"COT_Positioning_{timestamp}.csv", index=False)


@callback(
    [Output('cot_positioning_column_select_input', 'options'),
     Output('cot_positioning_column_select_input', 'value')]
)
def cot_positioning_column_select_input():
    options = []
    options.append({'label': const.DATE, 'value': const.DATE})
    options.append({'label': const.NAME, 'value': const.NAME})
    options.append({'label': const.LOOKBACK, 'value': const.LOOKBACK})
    options.append({'label': const.OPEN_INTEREST, 'value': const.OPEN_INTEREST})
    options.append({'label': "Net Positioning", 'value': "Net Positioning"})

    options.append({'label': "Estimated Indexing", 'value': "Estimated Indexing"})
    options.append({'label': "Net Estimated Positioning", 'value': "Net Estimated Positioning"})

    options.append({'label': "OI Percentage", 'value': "OI Percentage"})

    options.append({'label': "Normalized Indexing", 'value': "Normalized Indexing"})
    options.append({'label': "Net Normalized Positioning", 'value': "Net Normalized Positioning"})

    options.append({'label': "Z-Score", 'value': "Z-Score"})
    options.append({'label': "Spearman Correlation", 'value': "Spearman Correlation"})
    options.append({'label': "WILLCO", 'value': "WILLCO"})

    default_value = None
    return options, default_value
