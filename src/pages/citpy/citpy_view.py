import os
import urllib.parse

import cotmetrics.constants as const
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, callback, dcc, html

import viz_constants as vc

dash.register_page(__name__, path='/citpy/view')

#: What /citpy lists, and therefore all this page will open. A hand-typed URL
#: for anything else in the notes directory (a .csv sitting beside the .md, or
#: something that has no business being there) is refused.
VIEWABLE_SUFFIXES = ('.md', '.txt')


def requested_path(search):
    """The `?file=` value, decoded, or None.

    `parse_qs` rather than string splitting. The app's global URL sync
    round-trips every query through `URLSearchParams`, which percent-encodes
    the separators in a path, so `?file=/Users/...` becomes
    `?file=%2FUsers%2F...` the moment that callback runs. The old
    `search.split('=')[1]` handed those raw characters to the path guard,
    which then correctly refused something that no longer looked like a path:
    measured 2026-08-31 on a local run, every /citpy link answered "Access
    Denied" for a file sitting right there on disk. Splitting also lost the
    path entirely as soon as a second parameter rode along.
    """
    if not search:
        return None
    values = urllib.parse.parse_qs(search.lstrip('?')).get('file')
    return values[0] if values else None


def resolve_note(file_path, notes_dir=None):
    """The real path of a requested note, or None when it is not one.

    CONTAINMENT, not prefix matching: both sides are fully resolved (symlinks
    and `..` alike) and the answer must sit inside the notes directory. What
    this replaces accepted any path starting with `/Users` or `C:\\Users`,
    which on a Mac-hosted instance is every file the server user can read, on
    a page that needs no login. The `..` string check it also carried is
    unnecessary once the resolved path has to be inside the directory, and was
    never sufficient on its own (a symlink inside the notes directory needs no
    dots to point at /etc).
    """
    if not file_path:
        return None
    root = os.path.realpath(notes_dir if notes_dir is not None else const.CITPY_DIR)
    target = os.path.realpath(file_path)
    if os.path.commonpath([root, target]) != root or target == root:
        return None
    if not target.endswith(VIEWABLE_SUFFIXES):
        return None
    return target

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

    full_path = resolve_note(requested_path(search))
    if full_path is None:
        return html.H4("Access Denied: Invalid file path.", className="text-danger mt-4")

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

    # A note that resolved but is not there: the generator's output moved or was
    # cleaned up while the listing was open. Say so rather than returning None,
    # which renders as an empty page indistinguishable from a still-loading one.
    return html.H4("That note is no longer on disk.", className="text-warning mt-4")
