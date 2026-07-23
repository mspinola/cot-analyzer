import os
import re

import cotmetrics.constants as const
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

import viz_constants as vc

# Register page without an 'order' so it doesn't appear in the navbar
dash.register_page(__name__, path='/citpy')

def get_citpy_files_grouped():
    target_dir = const.CITPY_DIR
    if not os.path.exists(target_dir):
        return {}

    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')

    grouped_files = {}
    for date_folder in os.listdir(target_dir):
        if date_pattern.match(date_folder):
            folder_path = os.path.join(target_dir, date_folder)

            if os.path.isdir(folder_path):
                files_for_date = {}
                for filename in os.listdir(folder_path):
                    if filename.endswith(".md") or filename.endswith(".txt"):
                        file_path_key = os.path.join(folder_path, filename)
                        file_path_key = os.path.abspath(file_path_key)
                        name = filename.replace('.md', '').replace('.txt', '')
                        prefix = date_folder + "_"
                        if name.startswith(prefix):
                            name = name[len(prefix):]
                        files_for_date[name] = file_path_key
                if files_for_date:
                    grouped_files[date_folder] = files_for_date

    print(f"DEBUG CITPY GROUPED FILES: {grouped_files}")
    return grouped_files


def layout():
    grouped = get_citpy_files_grouped()
    dates = sorted(grouped.keys(), reverse=True)

    rows = []
    for d in dates:
        files = grouped[d]

        # Case insensitive dictionary lookup
        citrindex_path = next((path for key, path in files.items() if 'citrindex' in key.lower()), None)
        top_alloc_path = next((path for key, path in files.items() if 'top_allocation' in key.lower()), None)
        tv_watchlist_path = next((path for key, path in files.items() if 'tradingview' in key.lower()), None)

        cit_link = dcc.Link("View Citrindex", href=f"/citpy/view?file={citrindex_path}", style={'color': '#4ade80'}) if citrindex_path else html.Span("N/A", className="text-muted")
        top_link = dcc.Link("View Top Allocations", href=f"/citpy/view?file={top_alloc_path}", style={'color': '#4ade80'}) if top_alloc_path else html.Span("N/A", className="text-muted")
        tv_link = dcc.Link("View Watchlist", href=f"/citpy/view?file={tv_watchlist_path}", style={'color': '#4ade80'}) if tv_watchlist_path else html.Span("N/A", className="text-muted")

        row = html.Tr([
            html.Td(d, style={'color': vc.BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold', 'verticalAlign': 'middle'}),
            html.Td(cit_link, style={'verticalAlign': 'middle'}),
            html.Td(top_link, style={'verticalAlign': 'middle'}),
            html.Td(tv_link, style={'verticalAlign': 'middle'})
        ])
        rows.append(row)

    table_header = [
        html.Thead(html.Tr([
            html.Th("Date", style={'color': 'white', 'borderBottom': '1px solid #444'}),
            html.Th("Citrindex Link", style={'color': 'white', 'borderBottom': '1px solid #444'}),
            html.Th("Top Allocations Link", style={'color': 'white', 'borderBottom': '1px solid #444'}),
            html.Th("TradingView Watchlist", style={'color': 'white', 'borderBottom': '1px solid #444'})
        ]))
    ]

    table_body = [html.Tbody(rows)]

    return dbc.Container([
        html.H3("CIT PY Research Notes", className="text-white mt-4 mb-3"),
        html.Hr(style=vc.hr_style),
        dbc.Table(table_header + table_body, bordered=False, color="dark", hover=True, responsive=True, striped=True, className="mt-3")
    ], fluid=True)
