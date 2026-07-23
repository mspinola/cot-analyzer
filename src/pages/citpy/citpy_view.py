import os

import cotmetrics.constants as const
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, callback, dcc, html

import viz_constants as vc

dash.register_page(__name__, path='/citpy/view')

layout = dbc.Container([
    dcc.Location(id='citpy-url'),
    html.Div(id='citpy-viewer', className="mt-4")
], fluid=True)


def parse_markdown_table(md_text):
    """
    Manually parses a markdown table into a Pandas DataFrame.
    """
    # Extract lines that contain pipes
    table_lines = [line.strip() for line in md_text.split('\n') if '|' in line]

    # Remove alignment lines (e.g., |---|---|)
    data_lines = [line for line in table_lines if '---' not in line]

    if not data_lines:
        return None

    rows = []
    for line in data_lines:
        # Strip outer whitespace and outer pipes ONLY
        line = line.strip()
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]

        # Split by pipe to preserve internal empty cells
        row = [cell.strip() for cell in line.split('|')]
        rows.append(row)

    if len(rows) < 2:
        return None

    # Failsafe: Ensure all rows perfectly match the header length
    header = rows[0]
    num_cols = len(header)

    clean_data = []
    for row in rows[1:]:
        if len(row) < num_cols:
            # Pad with empty strings if the row is too short
            row.extend([''] * (num_cols - len(row)))
        elif len(row) > num_cols:
            # Truncate if the row is too long
            row = row[:num_cols]
        clean_data.append(row)

    df = pd.DataFrame(clean_data, columns=header)

    # Automatically convert numeric columns so AgGrid sorts them as numbers
    for col in df.columns:
        # Handle empty strings as NaN
        clean_col = df[col].replace('', float('nan'))
        try:
            df[col] = pd.to_numeric(clean_col)
        except (ValueError, TypeError):
            pass

    return df


@callback(
    Output('citpy-viewer', 'children'),
    Input('citpy-url', 'search')
)
def load_file(search):
    if not search:
        return ""

    file_path_key = search.split('=')[1]
    # SECURITY HARDENING: Prevent Path Traversal attacks
    is_citpy_root = file_path_key.startswith(const.CITPY_DIR)
    is_user_dir = file_path_key.startswith("/Users") or file_path_key.startswith("C:\\Users")
    if ".." in file_path_key or not (is_citpy_root or is_user_dir):
        return html.H4("Access Denied: Invalid file path.", className="text-danger mt-4")
    full_path = file_path_key

    if os.path.exists(full_path):
        # Read the file
        with open(full_path, 'r') as f:
            content = f.read()

        df = parse_markdown_table(content)
        if df is not None:
            return dag.AgGrid(
                rowData=df.to_dict("records"),
                columnDefs=[{"field": i} for i in df.columns],
                className="ag-theme-quartz-dark",
                style={"height": "100%", "--ag-font-size": "11px"},
                defaultColDef={
                    "sortable": True,
                    "filter": True,
                    "wrapHeaderText": True,
                    "autoHeaderHeight": True,
                    "width": 120,
                    "maxWidth": 350,
                },
                dashGridOptions={"domLayout": "autoHeight", "pagination": False},
                columnSize="responsiveSizeToFit",
            )
        else:
            # Fallback to standard Markdown if it's not a table
            return dcc.Markdown(content, style={'color': vc.TEXT_COLOR})
