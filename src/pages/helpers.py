
from dash import html
from narwhals import col

import constants as const
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def add_trace_to_all(fig, df, col_name, row, col, name, color, zorder, visible=True, is_bar=False, secondary=False, showlegend=False):
    """ Global Legend Toggle Logic: Show legend only once, but use legendgroups to link all 5 plots"""
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
            col=col,
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
            col=col,
            secondary_y=secondary
        )


def get_open_interest_percent_plot(fig, df, row, col, color_palette, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, const.COMM_PCT_OI, row, col, "Commercials", color_palette[0], 0, showlegend=showlegend)
    add_trace_to_all(fig, df, const.LARGE_PCT_OI, row, col, "Large Specs", color_palette[1], 1, showlegend=showlegend)
    add_trace_to_all(fig, df, const.SMALL_PCT_OI, row, col, "Small Specs", color_palette[2], 2, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    fig.update_yaxes(title="%", row=row, col=col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
    return fig


def get_willco_plot(fig, df, row, col, color_palette, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, "willco", row, col, "Commercials", color_palette[0], 0, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    if const.ENABLE_HLINE_THRESHOLDS:
        fig.add_hline(y=const.WILLCO_MAX_THRESHOLD, line_dash="dot", line_color="red", opacity=const.HLINE_OPACITY, row=row, col=col)
        fig.add_hline(y=const.WILLCO_MIN_THRESHOLD, line_dash="dot", line_color="green", opacity=const.HLINE_OPACITY, row=row, col=col)
    fig.update_yaxes(title="WILLCO", row=row, col=col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
    fig.add_hrect(y0=const.WILLCO_MAX_THRESHOLD, y1=100, fillcolor="green", opacity=0.05, line_width=0, row=row, col=1)
    fig.add_hrect(y0=0, y1=const.WILLCO_MIN_THRESHOLD, fillcolor="red", opacity=0.03, line_width=0, row=row, col=1)
    return fig


def get_spearman_plot(fig, df, row, col, color_palette, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, "comms_spearman", row, col, "Commercials", color_palette[0], 0, showlegend=showlegend)
    add_trace_to_all(fig, df, "lrg_spearman", row, col, "Large Specs", color_palette[1], 1, showlegend=showlegend)
    add_trace_to_all(fig, df, "sml_spearman", row, col, "Small Specs", color_palette[2], 2, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    fig.update_yaxes(title="correlation", row=row, col=col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
    return fig


def get_net_pos_plot(fig, df, comms_col, lrg_col, sml_col, row, col, color_palette, show_price=False, show_flips=False):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, comms_col, row, col, "Commercials", color_palette[0], 0, is_bar=True, showlegend=showlegend)
    add_trace_to_all(fig, df, lrg_col, row, col, "Large Specs", color_palette[1], 1, is_bar=True, showlegend=showlegend)
    add_trace_to_all(fig, df, sml_col, row, col, "Small Specs", color_palette[2], 2, is_bar=True, showlegend=showlegend)
    add_trace_to_all(fig, df, const.OPEN_INTEREST, row, col, "Open Interest", color_palette[4], 3, secondary=True, showlegend=showlegend)
    fig.update_yaxes(title="net position", row=row, col=col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
    fig.update_yaxes(title="OI", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)

    if show_flips:
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
                row=row,  # "all" Spans all active subplots
                col=1
            )

    return fig


def get_index_plot(fig, df, comms_col, lrg_col, sml_col, row, col, color_palette, min_threshold=None, max_threshold=None, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, comms_col, row, col, "Commercials", color_palette[0], 0, showlegend=showlegend)
    add_trace_to_all(fig, df, lrg_col, row, col, "Large Specs", color_palette[1], 1, showlegend=showlegend)
    add_trace_to_all(fig, df, sml_col, row, col, "Small Specs", color_palette[2], 2, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    fig.update_yaxes(title="Index", range=[0, 100], row=row, col=col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
    if max_threshold is not None and min_threshold is not None:
        if const.ENABLE_HLINE_THRESHOLDS:
            fig.add_hline(y=max_threshold, line_dash="dot", line_color="red", opacity=const.HLINE_OPACITY, row=row, col=col)
            fig.add_hline(y=min_threshold, line_dash="dot", line_color="green", opacity=const.HLINE_OPACITY, row=row, col=col)
        fig.add_hrect(y0=max_threshold, y1=100, fillcolor="red", opacity=0.03, line_width=0, row=row, col=1)
        fig.add_hrect(y0=0, y1=min_threshold, fillcolor="green", opacity=0.05, line_width=0, row=row, col=1)
    return fig


def get_zscore_plot(fig, df, row, col, color_palette, min_threshold=None, max_threshold=None, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, "comms_zscore", row, col, "Commercials", color_palette[0], 0, showlegend=showlegend)
    add_trace_to_all(fig, df, "lrg_zscore", row, col, "Large Specs", color_palette[1], 1, showlegend=showlegend)
    add_trace_to_all(fig, df, "sml_zscore", row, col, "Small Specs", color_palette[2], 2, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    if const.ENABLE_HLINE_THRESHOLDS:
        fig.add_hline(y=const.ZSCORE_MIN_THRESHOLD, line_dash="dot", line_color="red", opacity=const.HLINE_OPACITY, row=row, col=col)
        fig.add_hline(y=const.ZSCORE_MAX_THRESHOLD, line_dash="dot", line_color="green", opacity=const.HLINE_OPACITY, row=row, col=col)
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", opacity=const.HLINE_OPACITY, row=row, col=col)
    fig.update_yaxes(title="Std Dev", range=[-4, 4], row=row, col=col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
    fig.add_hrect(y0=2, y1=4, fillcolor="red", opacity=0.03, line_width=0, row=row, col=1)
    fig.add_hrect(y0=-4, y1=-2, fillcolor="green", opacity=0.05, line_width=0, row=row, col=1)
    return fig


def get_momentum_plot(fig, df, row, col, color_palette, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, "comm_momentum", row, col, "Commercials", color_palette[0], 0, is_bar=True, showlegend=showlegend)
    add_trace_to_all(fig, df, "lrg_momentum", row, col, "Large Specs", color_palette[1], 1, is_bar=True, showlegend=showlegend)
    add_trace_to_all(fig, df, "sml_momentum", row, col, "Small Specs", color_palette[2], 2, is_bar=True, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    if True: #const.ENABLE_HLINE_THRESHOLDS:
        fig.add_hline(y=const.MOMENTUM_MIN_THRESHOLD, line_dash="dot", line_color=const.TEXT_COLOR, opacity=const.HLINE_OPACITY, row=row, col=col)
        fig.add_hline(y=const.MOMENTUM_MAX_THRESHOLD, line_dash="dot", line_color=const.TEXT_COLOR, opacity=const.HLINE_OPACITY, row=row, col=col)
        # fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", opacity=const.HLINE_OPACITY, row=row, col=col)
    fig.update_yaxes(title="ROC", range=[-100, 100], row=row, col=col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
    # fig.add_hrect(y0=const.MOMENTUM_MAX_THRESHOLD, y1=100, fillcolor="red", opacity=0.03, line_width=0, row=row, col=1)
    # fig.add_hrect(y0=const.MOMENTUM_MIN_THRESHOLD, y1=-100, fillcolor="green", opacity=0.05, line_width=0, row=row, col=1)
    return fig


def get_tension_plot(fig, df, row, col, color_palette, show_price=True):
    showlegend = row == 1 and col == 1 or (show_price is False and row == 1 and col == 2)  # Show legend on first plot or on price plot if overlay is on
    add_trace_to_all(fig, df, "tension", row, col, "Tension", color_palette[4], 0, showlegend=showlegend)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, showlegend=showlegend)
        fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.EMPTY_COLOR, secondary_y=True, fixedrange=True)
    if const.ENABLE_HLINE_THRESHOLDS:
        fig.add_hline(y=const.ZSCORE_MIN_THRESHOLD, line_dash="dot", line_color="green", opacity=const.HLINE_OPACITY, row=row, col=1)
        fig.add_hline(y=const.ZSCORE_MAX_THRESHOLD, line_dash="dot", line_color="red", opacity=const.HLINE_OPACITY, row=row, col=1)
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", row=row, col=1)
    fig.update_yaxes(title="Std Dev", range=[-4, 4], row=row, col=col, secondary_y=False, gridcolor=const.GRID_COLOR, fixedrange=True)
    fig.add_hrect(y0=2, y1=4, fillcolor="red", opacity=0.03, line_width=0, row=row, col=1)
    fig.add_hrect(y0=-4, y1=-2, fillcolor="green", opacity=0.05, line_width=0, row=row, col=1)
    return fig


def get_price_plot(fig, df, row, col, color_palette):
    showlegend = True  # row == 1 and col == 1
    add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 0, showlegend=showlegend)
    fig.update_yaxes(title="$", row=row, col=col, gridcolor=const.GRID_COLOR, secondary_y=False, fixedrange=True)
    return fig


def get_no_data_html_p():
    return html.P("No Data", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})


def get_setup_highlighting(fig, df, min_threshold, max_threshold, row, col):
    """Loop through the data to find 'Extreme' clusters"""
    if min_threshold is not None and max_threshold is not None and row is not None:
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
                row=row,
                col=col,
                x0=df.index[i-1],
                x1=df.index[i],
                fillcolor=color,
                layer="below",
                line_width=0,
            )

    return fig


def get_make_subplots_for_plots(rows, cols, titles, specs, vertical_spacing=const.VERTICAL_SPACING):
    if rows == 0:
        v_spacing = 0
    elif rows <= 2:
        v_spacing = vertical_spacing * 2
    elif rows <= 2:
        v_spacing = vertical_spacing * 3
    elif rows <= 3:
        v_spacing = vertical_spacing * 4
    elif rows <= 5:
        v_spacing = vertical_spacing
    else:
        v_spacing = vertical_spacing / 2

    fig = make_subplots(
        rows=rows,
        cols=cols,
        shared_xaxes=True,
        vertical_spacing=v_spacing,
        subplot_titles=titles,
        specs=specs
    )
    return fig


def get_update_xaxes_for_plots(fig, df):
    start_idx = max(0, len(df) - const.DEFAULT_WEEKS_TO_VIEW)
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
    return fig


def get_update_layout_for_plots(fig, num_rows, num_cols):
    dynamic_height = (num_rows * const.PIXELS_PER_PLOT) + (num_rows * const.PIXELS_OVERHEAD_PER_PLOT)

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
            x=0.7,
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

    # Adjust horizontal legend position if multiple columns are used
    if num_cols > 1:
        fig.update_layout(legend=dict(x=0.5, xanchor="center", y=1.05))

    return fig