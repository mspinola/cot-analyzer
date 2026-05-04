import constants as const
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

AVAILABLE_PLOTS = {
    "oi_pct": "Net Position % of OI",
    "willco": "WillCo",
    "spearman": "Spearman Correlation",
    "net_pos": "Net Positions",
    "index": "Positioning Index",
    "zscore": "Positioning Z-Score",
    "tension": "Tension Oscillator"
}

layout = html.Div([
    dbc.Container([
        dbc.Accordion([
            dbc.AccordionItem([
                dbc.Row([
                    dbc.Col([
                        html.Label("Lookback:", style=const.label_style),
                        dbc.Select(
                            id='analysis_lookback_selector',
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
                        html.Label("Asset Class Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='analysis_single_asset_class_input',
                            options=[{'label': x, 'value': x}
                                    for x in cotIndexer.get_asset_classes()],
                            value=f"{cotIndexer.get_default_asset_class()}",
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='analysis_single_asset_filter_input',
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Visible Plots", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='analysis_plot_selector',
                            options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                            value=list(AVAILABLE_PLOTS.keys()),  # Default to all selected
                            multi=True,
                            className="dash-dropdown bg-dark text-white",
                            style={'minWidth': '250px'}
                        ),
                    ], xs=12, md=4),
                ], align="center"),
            ],
            title="CHART CONFIGURATION",
            item_id="chart_config"),
        ],
        start_collapsed=True, # Keeps it clean on initial mobile load
        flush=True,
        className="mb-3",
        style={'backgroundColor': const.BACKGROUND_COLOR}),

        # dbc.Col(
        #     html.Div(id='analysis_page_header'),
        # width="auto", className="ms-1"),
        # ], align="center", className="mb-4", style=const.row_start_style),

        html.Hr(style=const.hr_style),

        dbc.Row([
            dcc.Loading(
                id="loading-analysis-graph",
                type="default", # Options: "graph", "cube", "circle", "dot", or "default"
                children=html.Div(id='analysis_stack'),
                color=const.BRIGHTER_TEXT_COLOR
            )
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('analysis_lookback_selector', 'value')
)
def update_global_lookback(value):
    print("analysis cb select lb: ", value)
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"

@callback(
    Output('analysis_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    print("analysis cb redirect lb: ", value)
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


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
     Input('analysis_single_asset_filter_input', 'value'),
     Input('global_lookback_store', 'data')]
)
def update_analysis_header(asset_class, asset_name, lookback):
    if not asset_name:
        return html.H6("SELECT ASSET", style={'color': const.TEXT_COLOR})

    # Fetch latest data point
    df = cotIndexer.get_symbols_data(asset_name, lookback)
    if df is None or df.empty:
        return html.H6(f"{asset_class} | {asset_name}", style={'color': const.BRIGHTER_TEXT_COLOR})

    # Get the latest Z-score (using the column name from your DataFrame)
    latest_z = df['comms_zscore'].iloc[-1]

    # Determine color logic based on your 95/5 (Z=2.0) setup
    z_color = "#4ade80" if latest_z >= 2.0 else "#f87171" if latest_z <= -2.0 else const.TEXT_COLOR

    return [
        html.Div([
            html.Span("CURRENT COMMERCIAL Z-SCORE: ", style={'color': const.BRIGHTER_TEXT_COLOR, 'fontSize': '0.9rem'}),
            html.Span(f"{latest_z:.2f}", style={'color': z_color, 'fontSize': '1.1rem', 'fontWeight': 'bold'})
        ])
    ]


@callback(
    Output('analysis_stack', 'children'),
    [Input('session_palette_theme_asset_store', 'data'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data'),
     Input('global_lookback_store', 'data'),
     Input('analysis_plot_selector', 'value')]
)
def update_analysis_stack(palette_name, asset, setup, lookback, selected_plots):
    if not asset or not selected_plots:
        return html.P("SELECT ASSET AND PLOTS", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    min_threshold, max_threshold = utils.parse_setup_thresholds(setup)
    color_palette = cotIndexer.get_palette(palette_name)
    df = cotIndexer.get_symbols_data(asset, lookback)
    if df is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    num_rows = len(selected_plots)
    titles = [AVAILABLE_PLOTS[p] for p in selected_plots]

    # Define specs based on selection
    specs = []
    for p in selected_plots:
        if p in ["oi_pct", "willco", "spearman", "net_pos", "index", "zscore", "tension"]:
            specs.append([{"secondary_y": True}])
        else:
            specs.append([{"secondary_y": False}])

    fig = make_subplots(
        rows=num_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05 if num_rows > 1 else 0,
        subplot_titles=titles,
        specs=specs
    )

    # Global Legend Toggle Logic: Show legend only once, but use legendgroups to link all 5 plots
    def add_trace_to_all(fig, df, col_name, row, name, color, zorder, visible=True, is_bar=False, secondary=False, showlegend=False):
        if is_bar:
            fig.add_trace(go.Bar(
                x=df.index,
                y=df[col_name],
                name=name,
                legendgroup=name.lower(),
                visible=visible,
                showlegend=showlegend,
                marker_color=color,
                zorder=zorder,
                marker=dict(opacity=1, line=dict(color=color, width=0.5))),
                row=row,
                col=1,
                secondary_y=secondary
            )
        else:
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df[col_name],
                name=name,
                legendgroup=name.lower(),
                visible=visible,
                showlegend=showlegend,
                line=dict(color=color, width=1),
                zorder=zorder),
                row=row,
                col=1,
                secondary_y=secondary
            )

    cur_row = 1
    cur_col = 1
    setup_highlight_row = None  # TODO make this a list
    for p in selected_plots:
        if p == "oi_pct":
            # PLOT 1: % of OI
            add_trace_to_all(fig, df, const.COMM_PCT_OI, cur_row, "Commercials", color_palette[0], 0, showlegend=True)
            add_trace_to_all(fig, df, const.LARGE_PCT_OI, cur_row, "Large Specs", color_palette[1], 1, showlegend=True)
            add_trace_to_all(fig, df, const.SMALL_PCT_OI, cur_row, "Small Specs", color_palette[2], 2, showlegend=True)
            add_trace_to_all(fig, df, const.CLOSING_PRICE, cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=True)
            fig.update_yaxes(title="%", row=cur_row, col=cur_col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
            fig.update_yaxes(title="$", row=cur_row, col=cur_col, gridcolor=const.GRID_COLOR, secondary_y=True, fixedrange=True)

        elif p == "willco":
            add_trace_to_all(fig, df, "willco", cur_row, "Commercials", color_palette[0], 0)
            add_trace_to_all(fig, df, const.CLOSING_PRICE, cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=False)
            fig.add_hline(y=80, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
            fig.add_hline(y=20, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
            fig.update_yaxes(title="WILLCO", row=cur_row, col=cur_col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
            fig.update_yaxes(title="$", row=cur_row, col=cur_col, gridcolor=const.BACKGROUND_COLOR, secondary_y=True, fixedrange=True)
            fig.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.03, line_width=0, row=cur_row, col=1)
            fig.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.05, line_width=0, row=cur_row, col=1)

        elif p == "spearman":
            # PLOT: Spearman Correlation (-1 to 1)
            # Plotting the relationship between position ranks and price ranks
            add_trace_to_all(fig, df, "comms_spearman", cur_row, "Commercials", color_palette[0], 0)
            add_trace_to_all(fig, df, "lrg_spearman", cur_row, "Large Specs", color_palette[1], 1)
            add_trace_to_all(fig, df, "sml_spearman", cur_row, "Small Specs", color_palette[2], 2)
            add_trace_to_all(fig, df, const.CLOSING_PRICE, cur_row, "Price", color_palette[3], 3, secondary=True)
            fig.update_yaxes(title="correlation", row=cur_row, col=cur_col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
            fig.update_yaxes(title="$", row=cur_row, col=cur_col, gridcolor=const.BACKGROUND_COLOR, secondary_y=True, fixedrange=True)

        elif p == "net_pos":
            # PLOT: Net Positions (Bars)
            add_trace_to_all(fig, df, const.COMM_NET, cur_row, "Commercials", color_palette[0], 0, is_bar=True)
            add_trace_to_all(fig, df, const.LARGE_NET, cur_row, "Large Specs", color_palette[1], 1, is_bar=True)
            add_trace_to_all(fig, df, const.SMALL_NET, cur_row, "Small Specs", color_palette[2], 2, is_bar=True)
            add_trace_to_all(fig, df, const.OPEN_INTEREST, cur_row, "Open Interest", color_palette[4], 3, secondary=True)
            fig.update_yaxes(title="net position", row=cur_row, col=cur_col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
            fig.update_yaxes(title="OI", row=cur_row, col=cur_col, gridcolor=const.BACKGROUND_COLOR, secondary_y=True, fixedrange=True)

            plot_flip = False
            if plot_flip:
                flip_dates = df[df[const.LARGE_FLIP] == True].index
                for flip_date in flip_dates:
                    # Determine color based on the direction of the flip
                    is_bullish = df.loc[flip_date, const.LARGE_NET] > 0
                    line_color = "rgba(0, 255, 0, 0.4)" if is_bullish else "rgba(255, 0, 0, 0.4)"

                    # Add vertical line across all subplots
                    fig.add_vline(
                        x=flip_date,
                        line_width=2,
                        line_color=line_color,
                        layer="below",
                        row=cur_row,  # "all" Spans all active subplots
                        col=1
                    )

        elif p == "index":
            # PLOT: Sentiment Context
            setup_highlight_row = cur_row
            add_trace_to_all(fig, df, "comms_idx", cur_row, "Commercials", color_palette[0], 0)
            add_trace_to_all(fig, df, "lrg_idx", cur_row, "Large Specs", color_palette[1], 1)
            add_trace_to_all(fig, df, "sml_idx", cur_row, "Small Specs", color_palette[2], 2)
            add_trace_to_all(fig, df, const.CLOSING_PRICE, cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=False)
            fig.update_yaxes(title="Index", range=[0, 100], row=cur_row, col=cur_col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
            if max_threshold is not None and min_threshold is not None:
                fig.add_hline(y=max_threshold, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
                fig.add_hline(y=min_threshold, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
                fig.add_hrect(y0=max_threshold, y1=100, fillcolor="red", opacity=0.03, line_width=0, row=cur_row, col=1)
                fig.add_hrect(y0=0, y1=min_threshold, fillcolor="green", opacity=0.05, line_width=0, row=cur_row, col=1)

        elif p == "zscore":
            # PLOT: Sentiment z-score
            add_trace_to_all(fig, df, "comms_zscore", cur_row, "Commercials", color_palette[0], 0)
            add_trace_to_all(fig, df, "lrg_zscore", cur_row, "Large Specs", color_palette[1], 1)
            add_trace_to_all(fig, df, "sml_zscore", cur_row, "Small Specs", color_palette[2], 2)
            add_trace_to_all(fig, df, const.CLOSING_PRICE, cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=False)
            fig.add_hline(y=-2.0, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
            fig.add_hline(y=2.0, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
            fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", row=5, col=1)
            fig.update_yaxes(title="Std Dev", range=[-4, 4], row=cur_row, col=cur_col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
            fig.add_hrect(y0=2, y1=4, fillcolor="red", opacity=0.03, line_width=0, row=cur_row, col=1)
            fig.add_hrect(y0=-4, y1=-2, fillcolor="green", opacity=0.05, line_width=0, row=cur_row, col=1)

        elif p == "tension":
            # PLOT: Tension Ratio
            add_trace_to_all(fig, df, "tension", cur_row, "Tension", color_palette[4], 0, showlegend=False)
            add_trace_to_all(fig, df, const.CLOSING_PRICE, cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=False)
            fig.add_hline(y=2.0, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=1)
            fig.add_hline(y=-2.0, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=1)
            fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", row=cur_row, col=1)
            fig.update_yaxes(title="Std Dev", range=[-4, 4], row=cur_row, col=cur_col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
            fig.add_hrect(y0=2, y1=4, fillcolor="red", opacity=0.03, line_width=0, row=cur_row, col=1)
            fig.add_hrect(y0=-4, y1=-2, fillcolor="green", opacity=0.05, line_width=0, row=cur_row, col=1)

        cur_row += 1

    # Loop through the data to find 'Extreme' clusters
    if min_threshold is not None and max_threshold is not None and setup_highlight_row is not None:
        for i in range(1, len(df)):
            comms_idx = df['comms_idx'].iloc[i]
            large_idx = df['lrg_idx'].iloc[i]
            small_idx = df['sml_idx'].iloc[i]
            if comms_idx is None or large_idx is None or small_idx is None:
                continue
            elif comms_idx >= max_threshold and large_idx <= min_threshold and small_idx <= min_threshold:
                color = "rgba(255, 0, 0, 0.3)"  # Red Heat
            elif comms_idx <= min_threshold and large_idx >= max_threshold and small_idx >= max_threshold:
                color = "rgba(0, 255, 0, 0.3)"  # Green Heat
            else:
                continue

            # Highlight the specific week on the chart
            fig.add_vrect(
                row=setup_highlight_row,
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
        spikecolor=const.BRIGHTER_TEXT_COLOR,
        spikedash="solid",
        hoverformat="%Y-%m-%d",
        matches='x',
        layer="above traces",
        showticklabels=True,
        tickfont_color=const.TEXT_COLOR
    )

    dynamic_height = (num_rows * 250) + (num_rows * 25)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=const.BACKGROUND_COLOR,
        plot_bgcolor=const.BACKGROUND_COLOR,
        height=dynamic_height,
        hovermode="x unified",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.04,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=const.BRIGHTER_TEXT_COLOR),
            bgcolor=const.BACKGROUND_COLOR,
        ),
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
