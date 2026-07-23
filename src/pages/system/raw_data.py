import cotmetrics.constants as const
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics.database import cotDatabase
from cotmetrics.indexer import get_indexer
from dash import Input, Output, callback, dcc, html

import viz_constants as vc

dash.register_page(
    __name__,
    path='/raw_data'
)

def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.H2("Raw COT Data Viewer", className="mt-4 mb-2"),
                    html.P("Inspect the raw, unified dataframe loaded by the ETL pipeline for debugging purposes.", className="text-muted"),
                ])
            ]),
            dbc.Row([
                dbc.Col([
                    html.Label("Dataset:", style=vc.label_style),
                    dbc.RadioItems(
                        id='raw_data_dataset_selector',
                        options=[
                            {"label": "Raw COT Data", "value": "cot"},
                            {"label": "ML Trading Signals", "value": "ml"}
                        ],
                        value="cot",
                        inline=True,
                        className="mb-3",
                        style={"color": vc.BRIGHTER_TEXT_COLOR}
                    )
                ], xs=12, md="auto"),
                dbc.Col([
                    html.Label("Select Instrument:", style=vc.label_style),
                    dbc.Select(
                        id='raw_data_instrument_selector',
                        options=[
                            {"label": f"{instr.name} ({code})", "value": code}
                            for code, instr in get_indexer().instruments.items()
                        ],
                        value=list(get_indexer().instruments.keys())[0] if get_indexer().instruments else None,
                        className="mb-3 bg-dark text-white border-secondary",
                        style={'width': '300px'}
                    )
                ], xs=12, md="auto")
            ], className="mb-3"),

            dbc.Row([
                dbc.Col([
                    dcc.Loading(
                        id="loading-raw-data",
                        type="circle",
                        children=html.Div(id='raw_data_table_container')
                    )
                ])
            ])
        ], fluid=True)
    ])

@callback(
    Output('raw_data_table_container', 'children'),
    [Input('raw_data_instrument_selector', 'value'),
     Input('raw_data_dataset_selector', 'value')]
)
def update_raw_data_table(instrument_code, dataset_type):
    if dataset_type == "ml":
        import sqlite3
        try:
            conn = sqlite3.connect(cotDatabase.db_name)
            if instrument_code:
                symbol = get_indexer().instruments[instrument_code].symbol
                df_preds = pd.read_sql_query(f"SELECT * FROM ml_predictions_v2 WHERE symbol='{symbol}' ORDER BY report_date DESC", conn)

                # Get the full feature dataframe
                feat_df = get_indexer().instruments[instrument_code].df.copy()

                if not feat_df.empty and not df_preds.empty:
                    # Convert report_date to datetime for merging
                    df_preds['report_date'] = pd.to_datetime(df_preds['report_date'])

                    # Convert feat_df dates to timezone-naive for safe merging
                    feat_df_dates = feat_df[const.REPORT_DATE_XLS].dt.tz_localize(None)
                    feat_df[const.REPORT_DATE_XLS] = feat_df_dates

                    # Merge predictions onto the feature dataframe
                    df = pd.merge(
                        df_preds,
                        feat_df,
                        left_on='report_date',
                        right_on=const.REPORT_DATE_XLS,
                        how='left'
                    )

                    # Clean up redundant date columns
                    if const.REPORT_DATE_XLS in df.columns:
                        df = df.drop(columns=[const.REPORT_DATE_XLS])
                else:
                    df = df_preds
            else:
                df = pd.read_sql_query("SELECT * FROM ml_predictions_v2 ORDER BY report_date DESC LIMIT 1000", conn)
            conn.close()
        except Exception as e:
            return dbc.Alert(f"Database error: {e}", color="danger")

    else:
        if not instrument_code or instrument_code not in get_indexer().instruments:
            return html.Div("No instrument selected or available.", style={"color": "white"})

        instrument = get_indexer().instruments[instrument_code]
        df = instrument.df

    if df is None or df.empty:
        return dbc.Alert("No raw data found for this instrument.", color="warning")

    # Convert dates to string for AG Grid
    display_df = df.copy()
    for col in display_df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
        display_df[col] = display_df[col].dt.strftime('%Y-%m-%d')

    # Build columns definition
    column_defs = [
        {
            "field": col,
            "sortable": True,
            "filter": True,
            "resizable": True
        } for col in display_df.columns
    ]

    return dag.AgGrid(
        id="raw_data_grid",
        rowData=display_df.to_dict("records"),
        columnDefs=column_defs,
        className="ag-theme-quartz-dark",
        style={"height": "75vh", "width": "100%", "fontSize": "11px"},
        defaultColDef={
            "sortable": True,
            "filter": True,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
            "width": 120,
            "minWidth": 80,
        },
        dashGridOptions={
            "pagination": True,
            "paginationPageSize": 100,
            "rowHeight": 26,
        },
    )
