
import constants
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go

from datetime import datetime
from dash import callback, dcc, html, Input, Output

dash.register_page(__name__, path="/heatmap")


layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Label("Layout View:", style=constants.label_style),
                dbc.Select(
                    id='heatmap_layout_selector',
                    options=[
                        {"label": "Both - Side by Side", "value": "side"},
                        {"label": "Both - Stacked", "value": "stacked"},
                        {"label": "Z-Score Only", "value": "z_only"},
                        {"label": "Index Only", "value": "index_only"},
                    ],
                    value="stacked",
                    size="sm",
                    className="mb-3 bg-dark text-white border-secondary",
                )
            ], width="auto", className="ms-1"),

            dbc.Col([
                html.Label("Lookback:", style=constants.label_style),
                dbc.Select(
                    id='heatmap_lookback_selector',
                    options=[
                        {"label": "26 Weeks", "value": "26"},
                        {"label": "52 Weeks", "value": "52"},
                        {"label": "Custom", "value": "custom"},
                    ],
                    value="stacked",
                    size="sm",
                    className="mb-3 bg-dark text-white border-secondary",
                )
            ], width="auto"),

            dbc.Col([
                html.Label("Asset Class Selector", style=constants.label_style),
                dcc.Dropdown(
                    persistence=True,
                    id='page_heatmap_selector',
                    options=[{'label': x, 'value': x}
                                for x in cotIndexer.get_asset_classes()],
                    value=cotIndexer.get_asset_classes(),  # This selects every item in the list by default
                    multi=True,
                    className="dash-dropdown bg-dark text-white",
                    searchable=False,
                    clearable=True,
                ),
            ], width="auto")
        ], justify="left", className="mb-4", style=constants.row_start_style),

        html.Hr(style=constants.hr_style),

        dbc.Row([
            html.Div(id='heatmap_display_container')
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('heatmap_display_container', 'children'),
    [Input('heatmap_layout_selector', 'value'),
     Input('page_heatmap_selector', 'value'),
     Input('heatmap_lookback_selector', 'value')]
)
def render_heatmap_layout(layout_type, assest_classes, lookback):
    if not assest_classes:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': constants.TEXT_COLOR})

    fig_z = update_z_score_heat_map(assest_classes, lookback)
    fig_index = update_index_heat_map(assest_classes, lookback)

    z_graph = dcc.Graph(id='z_score_graph', figure=fig_z, config={'scrollZoom': False})
    index_graph = dcc.Graph(id='index_graph', figure=fig_index, config={'scrollZoom': False})

    if layout_type == "side":
        # Two columns (width 6 each) for wide viewing
        return dbc.Row([
            dbc.Col(z_graph, lg=6, md=12),
            dbc.Col(index_graph, lg=6, md=12)
        ])

    elif layout_type == "stacked":
        # Full width (width 12) for vertical scrolling on smaller screens
        return html.Div([
            dbc.Row([dbc.Col(z_graph, width=12)], className="mb-4"),
            dbc.Row([dbc.Col(index_graph, width=12)])
        ])

    elif layout_type == "z_only":
        return dbc.Row([dbc.Col(z_graph, width=12)])

    else: # index_only
        return dbc.Row([dbc.Col(index_graph, width=12)])


def update_z_score_heat_map(asset_classes, lookback):
    if not asset_classes:
        asset_classes = cotIndexer.get_asset_classes()

    top_spacer = pd.DataFrame([{
        "Asset": "TOP_SPACER",
        "Commercials": None, "Large Specs": None, "Small Specs": None,
        "Class": "Spacer"
    }])
    final_df_list = [top_spacer]
    for asset_class in asset_classes:
        class_df = cotIndexer.get_asset_class_z_score_heat(asset_class, lookback)
        if class_df.empty:
            continue

        # Sort alphabetically
        class_df = class_df.sort_values(by='Asset', ascending=True)

        # Add a Label column for the class heading (optional, for tooltips)
        class_df['Class'] = asset_class

        # Inject a "Header" row
        header_row = pd.DataFrame([{
            "Asset": f"--- {asset_class.upper()} ---",
            "Commercials": None,
            "Large Specs": None,
            "Small Specs": None,
            "Class": "Header"
        }])
        final_df_list.append(header_row)
        final_df_list.append(class_df)
    df = pd.concat(final_df_list).reset_index(drop=True)

    # Extract values for the matrix
    z_values = df[['Commercials', 'Large Specs', 'Small Specs']].values

    # Build a manual Text Matrix to prevent NaN being rendered as 0.00
    text_matrix = []
    y_display_labels = []
    for i, (name, z_row) in enumerate(zip(df['Asset'], z_values)):
        row_text = ["", "", ""]

        if name == "TOP_SPACER":
            y_display_labels.append(" " * (i + 500)) # Unique invisible label
            # row_text stays empty
        elif "---" in str(name):
            new_name = name.replace("---", "")
            y_display_labels.append(" " * (i + 1))
            row_text[1] = f"<b>{new_name}</b>"
        else:
            y_display_labels.append(name)
            for j, val in enumerate(z_row):
                row_text[j] = f"{val:.1f}" if not pd.isna(val) else ""

        text_matrix.append(row_text)

    # Create the Heatmap
    # We use a Diverging scale: Red (Short Extreme) -> Gray (Neutral) -> Green (Long Extreme)
    fig = go.Figure(data=go.Heatmap(
        hoverinfo='none',
        z=z_values,
        x=['Commercials', 'Large Specs', 'Small Specs'],
        y=y_display_labels,
        text=text_matrix,
        texttemplate="%{text}",
        textfont={"size": 13, "family": "Consolas, monospace", "color": "#FFFFFF"},
        colorscale=[
            [0, '#ff4b2b'],
            [0.05, '#ff4b2b'],
            [0.10, '#f87171'],
            [0.25, '#252C36'],
            [0.75, '#252C36'],
            [0.90, '#4ade80'],
            [0.95, '#00c853'],
            [1, '#00c853']
        ],
        zmin=-3, zmax=3,  # Force scale to Z-score range
        xgap=2,
        ygap=2,
        showscale=True,
        colorbar=dict(
            orientation='h',      # Flip to horizontal
            y=1.12,
            yanchor='bottom',
            x=0.5,                # Center it under the chart
            xanchor='center',
            thickness=12,         # Make it thinner/sleeker
            len=0.7,              # Don't let it span the full width
            title=dict(text="Std Dev", side="top", font=dict(size=14)),
            tickfont=dict(size=10),
            tickvals=[-3, -2, -1, 0, 1, 2, 3]  # Explicit ticks for the Z-score
        )
    ))

    fig.update_traces(
        # Matches the cell color of NaNs to the background exactly
        zsmooth=False,
        connectgaps=False,
        zmid=0  # Helps center the color mapping
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=constants.BACKGROUND_COLOR,
        plot_bgcolor=constants.BACKGROUND_COLOR,
        height=len(df) * 25 + 200,  # Dynamic height based on row count
        margin=dict(t=80, b=40, l=60, r=40),  # Left margin for asset names
        xaxis=dict(side="top", dtick=1, fixedrange=True),
        yaxis=dict(
            dtick=1, autorange="reversed", fixedrange=True,
            tickmode="array",
            tickvals=y_display_labels,
            ticktext=[n if not n.startswith(" ") else "" for n in y_display_labels]
        )
    )
    return fig


def update_index_heat_map(asset_classes, lookback):
    if not asset_classes:
        asset_classes = cotIndexer.get_asset_classes()

    top_spacer = pd.DataFrame([{
        "Asset": "TOP_SPACER",
        "Commercials": None, "Large Specs": None, "Small Specs": None,
        "Class": "Spacer"
    }])
    final_df_list = [top_spacer]

    for asset_class in asset_classes:
        class_df = cotIndexer.get_asset_class_index_heat(asset_class, lookback)
        if class_df.empty:
            continue

        # Sort alphabetically
        class_df = class_df.sort_values(by='Asset', ascending=True)

        # Add a Label column for the class heading (optional, for tooltips)
        class_df['Class'] = asset_class

        # Inject a "Header" row
        header_row = pd.DataFrame([{
            "Asset": f"--- {asset_class.upper()} ---",
            "Commercials": None,
            "Large Specs": None,
            "Small Specs": None,
            "Class": "Header"
        }])
        final_df_list.append(header_row)
        final_df_list.append(class_df)
    df = pd.concat(final_df_list).reset_index(drop=True)

    # Extract values for the matrix
    index_values = df[['Commercials', 'Large Specs', 'Small Specs']].values

    # Build a manual Text Matrix to prevent NaN being rendered as 0.00
    text_matrix = []
    y_display_labels = []
    for i, (name, z_row) in enumerate(zip(df['Asset'], index_values)):
        row_text = ["", "", ""]

        if name == "TOP_SPACER":
            y_display_labels.append(" " * (i + 500)) # Unique invisible label
            # row_text stays empty
        elif "---" in str(name):
            new_name = name.replace("---", "")
            y_display_labels.append(" " * (i + 1))
            row_text[1] = f"<b>{new_name}</b>"
        else:
            y_display_labels.append(name)
            for j, val in enumerate(z_row):
                row_text[j] = f"{val:.0f}" if not pd.isna(val) else ""

        text_matrix.append(row_text)

    # Create the Heatmap
    # We use a Diverging scale: Red (Short Extreme) -> Gray (Neutral) -> Green (Long Extreme)
    fig = go.Figure(data=go.Heatmap(
        hoverinfo='none',
        z=index_values,
        x=['Commercials', 'Large Specs', 'Small Specs'],
        y=y_display_labels,
        text=text_matrix,
        texttemplate="%{text}",
        textfont={"size": 13, "family": "Consolas, monospace", "color": "#FFFFFF"},
        colorscale=[
            [0, '#ff4b2b'],
            [0.05, '#ff4b2b'],
            [0.10, '#f87171'],
            [0.25, "#252C36"],
            [0.75, '#252C36'],
            [0.90, '#4ade80'],
            [0.95, '#00c853'],
            [1, '#00c853']
        ],
        zmin=-0, zmax=100,
        xgap=2,
        ygap=2,
        showscale=True,
        colorbar=dict(
            orientation='h',      # Flip to horizontal
            y=1.12,
            yanchor='bottom',
            x=0.5,                # Center it under the chart
            xanchor='center',
            thickness=12,         # Make it thinner/sleeker
            len=0.7,              # Don't let it span the full width
            title=dict(text="Index", side="top", font=dict(size=14)),
            tickfont=dict(size=10),
            tickvals=[0, 25, 50, 75, 100]
        )
    ))

    fig.update_traces(
        # Matches the cell color of NaNs to the background exactly
        zsmooth=False,
        connectgaps=False,
        zmid=0  # Helps center the color mapping
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=constants.BACKGROUND_COLOR,
        plot_bgcolor=constants.BACKGROUND_COLOR,
        height=len(df) * 25 + 200,  # Dynamic height based on row count
        margin=dict(t=80, b=40, l=60, r=40),  # Left margin for asset names
        xaxis=dict(side="top", dtick=1),
        yaxis=dict(
            dtick=1, autorange="reversed", fixedrange=True,
            tickmode="array",
            tickvals=y_display_labels,
            ticktext=[n if not n.startswith(" ") else "" for n in y_display_labels]
        )
    )
    return fig
