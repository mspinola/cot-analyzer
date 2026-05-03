import constants
import utils

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from dash import html, dcc, callback, Input, Output
from indexer import cotIndexer
from plotly.subplots import make_subplots


# Register this file as a page
dash.register_page(
    __name__,
    path='/graphs'
)

asset_class_list = cotIndexer.get_asset_classes()
asset_class_list.sort()

layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Label("Asset Class Selector", style=constants.label_style),
                dbc.Select(
                    persistence=True,
                    id='graphs_single_asset_class_input',
                    options=[{'label': x, 'value': x}
                             for x in asset_class_list],
                    value=f"{cotIndexer.get_default_asset_class()}",
                    className="mb-3 bg-dark text-white border-secondary",
                ),
            ], width="auto", className="ms-2 mt-2"),

            dbc.Col([
                html.Label("Asset Selector", style=constants.label_style),
                dcc.Dropdown(
                    persistence=True,
                    id='graphs_multi_equity_selector_input',
                    multi=True,
                    className="dash-dropdown bg-dark text-white",
                    searchable=False,
                    clearable=True,
                ),
            ], width="auto"),
        ], align="center", className="mb-4", style=constants.row_start_style),

        html.Hr(style=constants.hr_style),

        dbc.Row([
            html.Div(id='cot_graphs')
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('cot_graphs', 'children'),
    [Input('graphs_single_asset_class_input', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('graphs_multi_equity_selector_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data')]
)
def get_cot_graphs(asset_class, palette_name, selected_assets, setup):
    if selected_assets is None or len(selected_assets) == 0:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': constants.BRIGHTER_TEXT_COLOR})

    enabled_plots = 'Positioning'
    overlay_selection = 'Price'
    min_threshold, max_threshold = utils.parse_setup_thresholds(setup)

    grid_color = constants.GRID_COLOR
    color_palette = cotIndexer.get_palette(palette_name)

    if selected_assets is None:
        assets = cotIndexer.get_assets_for_asset_class(asset_class)
    elif selected_assets:
        assets = selected_assets  # Use specific user selections if provided
    else:
        assets = cotIndexer.get_assets_for_asset_class(asset_class)
    assets.sort()

    row_count = len(assets)

    total_height = (constants.PIXELS_PER_ROW * row_count) + \
        constants.FIXED_OVERHEAD
    v_spacing = 80 / total_height  # Consistent ~80px gap

    if enabled_plots == 'All':
        num_cols = 2
    elif enabled_plots in ['Indexing', 'Positioning']:
        num_cols = 1
    else:
        num_cols = 0

    titles = []
    for asset in assets:
        if enabled_plots in ['All', 'Indexing']:
            titles.append(asset + " Index")
        if enabled_plots in ['All', 'Positioning']:
            titles.append(asset + " Positions")

    specs = []
    if enabled_plots in ['Indexing']:
        specs = [[{"secondary_y": False}] for _ in range(row_count)]
    if enabled_plots in ['Positioning']:
        specs = [[{"secondary_y": True}] for _ in range(row_count)]
    if enabled_plots in ['All']:
        specs = [[{"secondary_y": False}, {"secondary_y": True}]
                 for _ in range(row_count)]

    fig = make_subplots(rows=row_count, shared_xaxes=False, cols=num_cols, subplot_titles=(
        titles), specs=specs, horizontal_spacing=0.08, vertical_spacing=v_spacing)
    fig.update_annotations(yshift=10, font=dict(size=15))

    for idx, asset in enumerate(assets):
        cur_row = idx + 1
        cur_col = 1
        df = cotIndexer.get_symbols_custom_index(asset)

        xaxis_weeks = 78
        x_axis_start_range = max(0, len(df.index) - xaxis_weeks)

        # Indexing Plot
        if enabled_plots in ['All', 'Indexing']:
            # Only show legend for the first plot
            legend = cur_row == 1 and cur_col == num_cols
            fig.add_trace(go.Scatter(x=df.index, y=df["comms"], legendgroup='commercials', line_shape='hv', showlegend=legend, zorder=0, line=dict(color=color_palette[0], width=1),
                                     name='commercials'), row=cur_row, col=cur_col, secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df["lrg"], legendgroup='large specs', line_shape='hv', showlegend=legend, zorder=1, line=dict(color=color_palette[1], width=1),
                                     name='large specs'), row=cur_row, col=cur_col)
            fig.add_trace(go.Scatter(x=df.index, y=df["sml"], legendgroup='small specs', line_shape='hv', showlegend=legend, zorder=2, line=dict(color=color_palette[2], width=1),
                                     name='small specs'), row=cur_row, col=cur_col)
            fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', range=[
                             df.index[x_axis_start_range], df.index[-1]])
            fig.update_yaxes(row=cur_row, col=cur_col, title="index", fixedrange=True,
                             showgrid=True, gridcolor=grid_color, gridwidth=1, range=[0, 100])

            # Loop through the data to find 'Extreme' clusters
            for i in range(1, len(df)):
                if df['comms'].iloc[i] is None or df['lrg'].iloc[i] or df['sml'].iloc[i] is None:
                    continue
                elif df['comms'].iloc[i] >= max_threshold and df['lrg'].iloc[i] <= min_threshold and df['sml'].iloc[i] <= min_threshold:
                    color = "rgba(255, 0, 0, 0.3)"  # Red Heat
                elif df['comms'].iloc[i] <= min_threshold and df['lrg'].iloc[i] >= max_threshold and df['sml'].iloc[i] >= max_threshold:
                    color = "rgba(0, 255, 0, 0.3)"  # Green Heat
                else:
                    continue

                # Highlight the specific week on the chart
                fig.add_vrect(
                    row=cur_row,
                    col=cur_col,
                    x0=df.index[i-1],
                    x1=df.index[i],
                    fillcolor=color,
                    layer="below",
                    line_width=0,
                )
            cur_col = cur_col + 1

        # Positioning Plot
        if enabled_plots in ['All', 'Positioning']:
            # Only show legend for the first plot
            legend = cur_row == 1 and cur_col == num_cols
            fig.add_trace(go.Bar(x=df.index, y=df["comms_net"], legendgroup='commercials', showlegend=legend, zorder=0, marker=dict(opacity=1, line=dict(color=color_palette[0])),
                                 name='commercials', marker_color=color_palette[0]), row=cur_row, col=cur_col, secondary_y=False)
            fig.add_trace(go.Bar(x=df.index, y=df["lrg_net"], legendgroup='large specs', showlegend=legend, zorder=1, marker=dict(opacity=1, line=dict(color=color_palette[1])),
                                 name='large specs', marker_color=color_palette[1]), row=cur_row, col=cur_col, secondary_y=False)
            fig.add_trace(go.Bar(x=df.index, y=df["sml_net"], legendgroup='small specs', showlegend=legend, zorder=2, marker=dict(opacity=1, line=dict(color=color_palette[2])),
                                 name='small specs', marker_color=color_palette[2]), row=cur_row, col=cur_col, secondary_y=False)

            if overlay_selection == 'Price' and 'price' in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df["price"], legendgroup='price', showlegend=legend, zorder=3, line=dict(color=color_palette[3], width=1),
                                         name='price'), row=cur_row, col=cur_col, secondary_y=True)
            elif overlay_selection == 'Open Interest':
                fig.add_trace(go.Scatter(x=df.index, y=df["oi"], legendgroup='open interest', showlegend=legend, zorder=3, line=dict(color=color_palette[4], width=1),
                                         name='open interest'), row=cur_row, col=cur_col, secondary_y=True)
            else:
                pass

            if enabled_plots == 'All':
                fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', range=[
                    df.index[x_axis_start_range], df.index[-1]])
            else:
                fig.update_xaxes(row=cur_row, col=cur_col,
                                 showgrid=False, matches='x', autorange=True)
            fig.update_yaxes(row=cur_row, col=cur_col, title="net positions", showgrid=True,
                             gridcolor=grid_color, gridwidth=1, secondary_y=False, fixedrange=True)
            if overlay_selection == 'Open Interest':
                fig.update_yaxes(
                    row=cur_row, col=cur_col, title="open interest", showgrid=False, secondary_y=True, fixedrange=True)
            elif overlay_selection == 'Price':
                fig.update_yaxes(row=cur_row, col=cur_col, fixedrange=True,
                                 title="price", showgrid=False, secondary_y=True)

            # Loop through the data to find 'Extreme' clusters
            for i in range(1, len(df)):
                if df['comms'].iloc[i] is None or df['lrg'].iloc[i] is None or df['sml'].iloc[i] is None:
                    continue
                elif df['comms'].iloc[i] >= max_threshold and df['lrg'].iloc[i] <= min_threshold and df['sml'].iloc[i] <= min_threshold:
                    color = "rgba(255, 0, 0, 0.3)"  # Red Heat
                elif df['comms'].iloc[i] <= min_threshold and df['lrg'].iloc[i] >= max_threshold and df['sml'].iloc[i] >= max_threshold:
                    color = "rgba(0, 255, 0, 0.3)"  # Green Heat
                else:
                    continue

                # Highlight the specific week on the chart
                fig.add_vrect(
                    row=cur_row,
                    col=cur_col,
                    x0=df.index[i-1],
                    x1=df.index[i],
                    fillcolor=color,
                    layer="below",
                    line_width=0,
                )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=constants.BACKGROUND_COLOR,
        plot_bgcolor=constants.BACKGROUND_COLOR,
        # Sets color for all graph text
        font=dict(color=constants.BRIGHTER_TEXT_COLOR),
        showlegend=True,
        legend=dict(
            orientation="h",
            entrywidth=120,
            entrywidthmode='pixels',
            bgcolor=constants.BACKGROUND_COLOR,
            font=dict(size=14, color=constants.BRIGHTER_TEXT_COLOR),
            yanchor="bottom",
            y=1.15,
            x=0.5,
            xanchor="center"
        ),
        autosize=True,
        height=total_height,
        margin=dict(t=10, b=10, l=10, r=10),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.8)",
                        font=dict(color=constants.HOVER_TEXT_COLOR)),
        bargap=0.2,
    )
    return dcc.Graph(figure=fig,
                     config={
                        'scrollZoom': False,
                        'doubleClick': 'reset',
                        'displayModeBar': True,
                        'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                        'responsive': True}, style={'width': '100%'
                    })


@callback(
    Output('cot_graphs_plot_input', 'value'),
    Input('cot_graphs_plot_input', 'value')
)
def update_plot_dropdown_value(selection):
    enabled_plots = 'Positioning'
    if not selection or selection == 'Positioning':
        enabled_plots = 'Positioning'
    elif selection == 'Indexing':
        enabled_plots = 'Indexing'
    elif selection == 'All':
        enabled_plots = 'All'
    else:
        enabled_plots = 'None'
    return enabled_plots


@callback(
    Output('cot_graphs_plot_overlay_input', 'value'),
    Input('cot_graphs_plot_overlay_input', 'value')
)
def update_overlay_dropdown_value(selection):
    if selection == 'Open Interest':
        return 'Open Interest'
    elif selection == 'Price':
        return 'Price'
    else:
        return 'None'


@callback(
    [Output('graphs_multi_equity_selector_input', 'options'),
     Output('graphs_multi_equity_selector_input', 'value')],
    Input('graphs_single_asset_class_input', 'value')
)
def update_multi_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    return options, assets
