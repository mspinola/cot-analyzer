import constants
import utils
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from dash import State, html, dcc, Input, Output, callback
from plotly.subplots import make_subplots


# Register this file as a page
dash.register_page(
    __name__,
    path='/analysis'
)

layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Label("Asset Class Selector", style=constants.label_style),
                dbc.Select(
                    persistence=True,
                    id='analysis_single_asset_class_input',
                    options=[{'label': x, 'value': x}
                             for x in cotIndexer.get_asset_classes()],
                    value=f"{cotIndexer.get_default_asset_class()}",
                    className="mb-3 bg-dark text-white border-secondary",
                ),
            ], width="auto", className="ms-2"),

            dbc.Col([
                html.Label("Asset Selector", style=constants.label_style),
                dbc.Select(
                    persistence=True,
                    id='analysis_single_asset_filter_input',
                    className="mb-3 bg-dark text-white border-secondary",
                ),
            ], width="auto", className="ms-1"),

            dbc.Col(
                html.Div(id='analysis_page_header'),
            width="auto", className="ms-1"),
        ], align="center", className="mb-4", style=constants.row_start_style),

        html.Hr(style=constants.hr_style),

        dbc.Row([
            html.Div(id='analysis_stack')
        ], justify='center')
    ], fluid=True),
])


@callback(
    [Output('analysis_single_asset_filter_input', 'options'),
     Output('analysis_single_asset_filter_input', 'value')],
    Input('analysis_single_asset_class_input', 'value')
)
def update_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    default_value = options[0].get('value') if options else None
    return options, default_value


@callback(
    Output('analysis_page_header', 'children'),
    [Input('analysis_single_asset_class_input', 'value'),
     Input('analysis_single_asset_filter_input', 'value')]
)
def update_analysis_header(asset_class, asset_name):
    if not asset_name:
        return html.H6("SELECT ASSET", style={'color': constants.TEXT_COLOR})

    # Fetch latest data point
    df = cotIndexer.get_symbols_custom_index(asset_name)
    if df is None or df.empty:
        return html.H6(f"{asset_class} | {asset_name}", style={'color': constants.BRIGHTER_TEXT_COLOR})

    # Get the latest Z-score (using the column name from your DataFrame)
    latest_z = df['comms-z'].iloc[-1]

    # Determine color logic based on your 95/5 (Z=2.0) setup
    z_color = "#4ade80" if latest_z >= 2.0 else "#f87171" if latest_z <= -2.0 else constants.TEXT_COLOR

    return [
        # html.H6(f"{asset_class.upper()} | {asset_name.upper()}",
        #         style={'color': constants.BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold', 'marginBottom': '5px'}),
        html.Div([
            html.Span("CURRENT COMMERCIAL Z-SCORE: ", style={'color': constants.BRIGHTER_TEXT_COLOR, 'fontSize': '0.9rem'}),
            html.Span(f"{latest_z:.2f}", style={'color': z_color, 'fontSize': '1.1rem', 'fontWeight': 'bold'})
        ])
    ]


@callback(
    Output('analysis_stack', 'children'),
    [Input('session_palette_theme_asset_store', 'data'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data')]
)
def update_analysis_stack(palette_name, asset, setup):
    if not asset:
        return html.P("SELECT ASSET", style={'textAlign': 'center', 'color': constants.BRIGHTER_TEXT_COLOR})

    min_threshold, max_threshold = utils.parse_setup_thresholds(setup)
    color_palette = cotIndexer.get_palette(palette_name)
    df = cotIndexer.get_symbols_custom_index(asset)
    if df is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': constants.BRIGHTER_TEXT_COLOR})

    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("Net Position % of Open Interest", "Spearman Correlation + Price",
                        "Net Positions + Open Interest", "Positioning Index (Trend Exhaustion)",
                        "Positioning Z-Score (Statistical Extremes)"),
        specs=[[{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": False}], [{"secondary_y": False}]]
    )

    # Global Legend Toggle Logic: Show legend only once, but use legendgroups to link all 5 plots
    def add_trace_to_all(fig, df, col_name, row, name, color, zorder, visible=True, is_bar=False, secondary=False, showlegend=False):
        if is_bar:
            fig.add_trace(go.Bar(x=df.index, y=df[col_name], name=name, legendgroup=name.lower(), visible=visible,
                                 showlegend=showlegend, marker_color=color, zorder=zorder,
                                 marker=dict(opacity=1, line=dict(color=color, width=0.5))),
                                 row=row, col=1, secondary_y=secondary)
        else:
            fig.add_trace(go.Scatter(x=df.index, y=df[col_name], name=name, legendgroup=name.lower(), visible=visible,
                                     showlegend=showlegend, line=dict(color=color, width=1), zorder=zorder), row=row, col=1, secondary_y=secondary)

    # PLOT 1: % of OI
    # Primary Axis: % of OI
    cur_row = 1
    cur_col = 1
    add_trace_to_all(fig, df, "comm_oi_pct", cur_row, "Commercials", color_palette[0], 0, showlegend=True)
    add_trace_to_all(fig, df, "lrg_oi_pct", cur_row, "Large Specs", color_palette[1], 1, showlegend=True)
    add_trace_to_all(fig, df, "sml_oi_pct", cur_row, "Small Specs", color_palette[2], 2, showlegend=True)
    fig.update_yaxes(title="%", row=cur_row, col=cur_col, gridcolor=constants.GRID_COLOR, secondary_y=False, fixedrange=True)

    # PLOT 2: Spearman Correlation (-1 to 1)
    # Plotting the relationship between position ranks and price ranks
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comm_spearman", cur_row, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, "lrg_spearman", cur_row, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, "sml_spearman", cur_row, "Small Specs", color_palette[2], 2)
    add_trace_to_all(fig, df, "price", cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=True)
    fig.update_yaxes(title="correlation", row=cur_row, col=cur_col, gridcolor=constants.GRID_COLOR, secondary_y=False, fixedrange=True)
    fig.update_yaxes(title="$", row=cur_row, col=cur_col, gridcolor=constants.BACKGROUND_COLOR, secondary_y=True, fixedrange=True)

    # THIRD PLOT: Net Positions (Bars)
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comms_net", cur_row, "Commercials", color_palette[0], 0, is_bar=True)
    add_trace_to_all(fig, df, "lrg_net", cur_row, "Large Specs", color_palette[1], 1, is_bar=True)
    add_trace_to_all(fig, df, "sml_net", cur_row, "Small Specs", color_palette[2], 2, is_bar=True)
    add_trace_to_all(fig, df, "oi", cur_row, "Open Interest", color_palette[4], 3, secondary=True, showlegend=True)
    fig.update_yaxes(title="net position", row=cur_row, col=cur_col, gridcolor=constants.GRID_COLOR, secondary_y=False, fixedrange=True)
    fig.update_yaxes(title="OI", row=cur_row, col=cur_col, gridcolor=constants.BACKGROUND_COLOR, secondary_y=True, fixedrange=True)

    # FOURTH PLOT: Sentiment Context
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comms", cur_row, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, "lrg", cur_row, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, "sml", cur_row, "Small Specs", color_palette[2], 2)
    # Threshold Lines for Plot 4
    fig.add_hline(y=max_threshold, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
    fig.add_hline(y=min_threshold, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
    fig.update_yaxes(title="Index", range=[0, 100], row=cur_row, col=cur_col, secondary_y=False, gridcolor=constants.GRID_COLOR, fixedrange=True)

    # FIFTH PLOT: Sentiment z-score
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comms-z", cur_row, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, "lrg-z", cur_row, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, "sml-z", cur_row, "Small Specs", color_palette[2], 2)
    # Threshold Lines for Plot 5
    fig.add_hline(y=-3.0, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
    fig.add_hline(y=3.0, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", row=5, col=1)
    fig.update_yaxes(title="Std Dev", range=[-4, 4], row=cur_row, col=cur_col, secondary_y=False, gridcolor=constants.GRID_COLOR, fixedrange=True)

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
        for j in range(1, cur_row):
            fig.add_vrect(
                row=j,
                col=cur_col,
                x0=df.index[i-1],
                x1=df.index[i],
                fillcolor=color,
                layer="below",
                line_width=0,
            )

    weeks_back = 78
    start_idx = max(0, len(df) - weeks_back)
    start_date = df.index[start_idx]
    end_date = df.index[-1]

    fig.update_xaxes(
        range=[start_date, end_date],
        minallowed=df.index[0],   # User cannot scroll left past the first data point
        maxallowed=df.index[-1],   # User cannot scroll right past the latest data point
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor=constants.BRIGHTER_TEXT_COLOR,
        spikedash="solid",
        hoverformat="%Y-%m-%d",
        matches='x',
        layer="above traces",
        showticklabels=True,
        tickfont_color=constants.TEXT_COLOR
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=constants.BACKGROUND_COLOR,
        plot_bgcolor=constants.BACKGROUND_COLOR,
        height=1000,
        hovermode="x unified",
        spikedistance=1000,
        hoverdistance=100,
        font=dict(size=10),
        margin=dict(t=80, b=50, l=10, r=10),
        bargap=0.2,
        xaxis=dict(fixedrange=False),
        yaxis=dict(fixedrange=True)
    )

    return dcc.Graph(figure=fig,
                     config={
                        'scrollZoom': False,
                        'doubleClick': 'reset',
                        'displayModeBar': True,
                        'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                        'responsive': True}, style={'width': '100%'
                    })
