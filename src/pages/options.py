import constants
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc
import io
import zipfile

from datetime import datetime
from dash import callback, dcc, html, Input, Output

dash.register_page(__name__, path="/options")

palette_options = cotIndexer.get_palette_names()

layout = html.Div([
    html.Br(),
    dbc.Row(
        dbc.Col([
            html.H4("Global Data Download and Styling options.",
                style={
                    'textAlign': 'left',
                    'color': constants.BRIGHTER_TEXT_COLOR
                    }
            )
        ], width=6, className="ms-3")
    ),
    dbc.Row(
        dbc.Col([
            dbc.Accordion([
                dbc.AccordionItem([
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                [html.I(className="bi bi-download"), "CFTC Data"],
                                id="sidebar-full-download-btn",
                                color="secondary",
                                outline=True,
                                size="sm",
                                style=constants.button_style
                            ),
                            dcc.Download(id="sidebar-full-download-logic"),
                            dbc.Tooltip(
                                "Download all of the CFTC data as one CSV per asset.",
                                target="sidebar-full-download-btn",
                                placement="top"
                            ),
                        ], width="auto"),

                        dbc.Col([
                            dbc.Button(
                                [html.I(className="bi bi-cloud-download"),
                                    "Real Test Data"],
                                id="sidebar-real-test-download-btn",
                                color="secondary",
                                outline=True,
                                size="sm",
                                style=constants.button_style
                            ),
                            dcc.Download(id="sidebar-real-test-download-logic"),
                            dbc.Tooltip(
                                "Download Real Test event lists for back testing.",
                                target="sidebar-real-test-download-btn",
                                placement="top"
                            ),
                        ], width="auto"),
                    ], align="center", className="mt-4 mb-4"),
                ], title="Data Download", item_id="data-download"),

                dbc.AccordionItem([
                    html.Label("Color Palette", style=constants.label_style),
                    dbc.Select(
                        persistence=True,
                        id='home_page_global_palette_input',
                        options=[{'label': x, 'value': x} for x in palette_options],
                        value=palette_options[0] if palette_options else None,
                        className="mb-3 bg-dark text-white border-secondary",
                        style={'backgroundColor': constants.BACKGROUND_COLOR, 'color': constants.TEXT_COLOR, 'borderColor': f"{constants.TEXT_COLOR}26"}
                    ),

                    # html.Label("Setup Highlight", style=constants.label_style),
                    # dbc.Select(
                    #     persistence=True,
                    #     id='home_page_setup_highlight_input',
                    #     options=[{'label': 'None', 'value': 'None'}, {'label': '95 5', 'value': '95 5'}, {'label': '90 10', 'value': '90 10'}, {'label': '75 25', 'value': '75 25'}],
                    #     value=f"{'None', 'None'}",
                    #     className="mb-3 bg-dark text-white border-secondary",
                    #     style={'backgroundColor': constants.BACKGROUND_COLOR, 'color': constants.TEXT_COLOR, 'borderColor': f"{constants.TEXT_COLOR}26"}
                    # ),
                    # dbc.Tooltip(
                    #     "Highlight plots with index extremes. This can be really slow.",
                    #     target="global_setup_threshold_input",
                    #     placement="top"
                    # ),
                ], title="Theme Styling", item_id="theme-link"),
            ], active_item=["data-download", "theme-link"], flush=True, className="bg-dark"),
        ], width=6, className="ms-3"),
    )
])

@callback(
    Output('session_palette_theme_asset_store', 'data'),
    Input('home_page_global_palette_input', 'value'),
    prevent_initial_call=False
)
def save_palette_to_store(selected_palette_theme):
    print(selected_palette_theme)
    if not selected_palette_theme:
        return palette_options[0]
    else:
        return selected_palette_theme

@callback(
    Output('session_setup_highlight_asset_store', 'data'),
    Input('home_page_setup_highlight_input', 'value'),
    prevent_initial_call=False
)
def save_setup_highlight_to_store(setup):
    print(setup)
    if not setup:
        return "None"
    else:
        return setup


@callback(
    Output("sidebar-full-download-logic", "data"),
    Input("sidebar-full-download-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_cftc_data_zip(n_clicks):
    if not n_clicks:
        return None

    all_classes = cotIndexer.get_asset_classes()
    all_classes.sort()

    # Create an in-memory buffer to hold the zip data
    buffer = io.BytesIO()

    # Initialize the ZipFile object
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset_class in all_classes:
            for asset in cotIndexer.get_assets_for_asset_class(asset_class):
                instrument_code = cotIndexer.get_instrument_code_from_name(
                    asset)
                df = cotIndexer.collect_symbol_summary_results(instrument_code)

                if not df.empty:
                    # Convert DataFrame to a CSV string
                    csv_string = df.to_csv(index=False)

                    # Write the CSV string into the zip as a file
                    # We sanitize the name by removing spaces
                    file_name = f"{cotIndexer.get_instrument_symbol_from_name(asset).replace(' ', '_')}_summary.csv"
                    zf.writestr(file_name, csv_string)

                df_detailed = cotIndexer.collect_symbol_detailed_results(
                    instrument_code)
                if not df_detailed.empty:
                    csv_string_detailed = df_detailed.to_csv(index=False)
                    file_name_detailed = f"{cotIndexer.get_instrument_symbol_from_name(asset).replace(' ', '_')}_detailed.csv"
                    zf.writestr(file_name_detailed, csv_string_detailed)

    # Seek to the start of the buffer so Dash can read it
    buffer.seek(0)

    zip_filename = f"COT_Full_Data_{datetime.now().strftime('%Y-%m-%d')}.zip"

    # Use send_bytes to transmit the binary zip data
    return dcc.send_bytes(buffer.getvalue(), zip_filename)


@callback(
    Output("sidebar-real-test-download-logic", "data"),
    Input("sidebar-real-test-download-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_real_test_data_zip(n_clicks):
    if not n_clicks:
        return None

    all_classes = cotIndexer.get_asset_classes()
    all_classes.sort()

    # Create an in-memory buffer to hold the zip data
    buffer = io.BytesIO()

    # Initialize the ZipFile object
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset_class in all_classes:
            for asset in cotIndexer.get_assets_for_asset_class(asset_class):
                instrument_code = cotIndexer.get_instrument_code_from_name(
                    asset)
                df = cotIndexer.create_real_test_event_asset_list(
                    instrument_code)

                if not df.empty:
                    # Convert DataFrame to a CSV string
                    csv_string = df.to_csv(index=False)

                    # Write the CSV string into the zip as a file
                    # We sanitize the name by removing spaces
                    file_name = f"{cotIndexer.get_instrument_symbol_from_name(asset).replace(' ', '_')}_real_test.csv"
                    zf.writestr(file_name, csv_string)

    # Seek to the start of the buffer so Dash can read it
    buffer.seek(0)

    zip_filename = f"COT_Real_Test_Data_{datetime.now().strftime('%Y-%m-%d')}.zip"

    # Use send_bytes to transmit the binary zip data
    return dcc.send_bytes(buffer.getvalue(), zip_filename)
