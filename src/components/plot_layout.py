"""Figure geometry: subplot grids, axis ranges, heights and the shared layout pass.

This is the part of the plotting code that does not care what is being drawn. It sizes
the grid, formats the axes and applies the app-wide layout, for any stack of panels.
"""

import math

import cotmetrics.constants as const
import pandas as pd
from dash import html
from plotly.subplots import make_subplots

import viz_constants as vc


def get_nice_dtick(span, num_ticks=4):
    if span <= 0:
        return 1
    raw_dtick = span / num_ticks
    exponent = math.floor(math.log10(raw_dtick))
    fraction = raw_dtick / (10 ** exponent)
    if fraction < 1.5:
        nice_fraction = 1
    elif fraction < 3:
        nice_fraction = 2
    elif fraction < 7:
        nice_fraction = 5
    else:
        nice_fraction = 10
    return nice_fraction * (10 ** exponent)


def get_no_data_html_p():
    return html.P("No Data", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})


def pixels_per_plot_for_cols(cols):
    """Per-row chart height. Fewer columns means wider plots, which need more height."""
    if cols == 1:
        return 300  # Full width monitor = needs taller plots
    if cols == 2:
        return 250
    return 200


def get_figure_height(rows, cols):
    """Total figure height in pixels.

    The fixed chrome (title/legend/rangeselector above the plot area, x labels below) is
    charged ONCE for the whole figure. It used to be multiplied by the row count, which
    meant a single-row figure got 325px total and then spent 250px of it on margins,
    leaving a 75px chart. Two rows got 200px each, three got 242 — the first row was
    paying for everyone.

    Both this and get_update_layout_for_plots must agree on the answer, or the vertical
    spacing below is computed against a height the figure never has.
    """
    return (rows * pixels_per_plot_for_cols(cols)
            + max(0, rows - 1) * const.PIXELS_OVERHEAD_PER_PLOT
            + vc.PLOT_MARGIN_TOP + vc.PLOT_MARGIN_BOTTOM)


def get_plot_area_height(rows, cols):
    """Figure height minus the fixed chrome — the space subplot domains actually span."""
    return get_figure_height(rows, cols) - vc.PLOT_MARGIN_TOP - vc.PLOT_MARGIN_BOTTOM


def get_make_subplots_for_plots(rows, cols, titles, specs, shared_xaxes=True):
    if rows > 1:
        # vertical_spacing is a fraction of the plot area, not of the figure, so the
        # denominator has to be the plot area or the gap comes out short.
        v_spacing = float(vc.PLOT_ROW_GAP) / get_plot_area_height(rows, cols)
    else:
        v_spacing = 0.05

    fig = make_subplots(
        rows=rows,
        cols=cols,
        shared_xaxes=shared_xaxes,
        vertical_spacing=v_spacing,
        horizontal_spacing=0.08,
        subplot_titles=titles,
        specs=specs
    )
    return fig


def get_update_xaxes_for_plots(fig, df, exclude_plot_indices=None):
    import flask
    is_mobile = False
    if flask.has_request_context():
        user_agent = flask.request.headers.get('User-Agent', '').lower()
        if any(kw in user_agent for kw in ['mobile', 'android', 'iphone', 'ipad', 'phone', 'ipod']):
            is_mobile = True

    weeks_to_view = 52 if is_mobile else const.DEFAULT_WEEKS_TO_VIEW
    start_idx = max(0, len(df) - weeks_to_view)
    start_date = df.index[start_idx]
    end_date = df.index[-1] + pd.Timedelta(days=14)  # Add some padding to the right for better aesthetics

    exclude_plot_indices = exclude_plot_indices or []

    # We must apply this update to each subplot individually if there are exclusions
    # If no exclusions, we can just apply it globally.
    # To be safe and support matches='x', we'll apply it globally but then revert the excluded ones?
    # No, update_xaxes can take selector or row/col.

    # First, apply to all
    fig.update_xaxes(
        range=[start_date, end_date],
        minallowed=df.index[0],   # User cannot scroll left past the first data point
        maxallowed=end_date,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor=vc.BRIGHTER_TEXT_COLOR,
        spikedash="solid",
        hoverformat="%Y-%m-%d",
        matches='x',
        layer="above traces",
        showticklabels=True,  # Enable to show date labels on all x-axis
        tickfont_color=vc.TEXT_COLOR,
        rangeslider_visible=False,
        showgrid=False,
    )

    # Then revert exclusions
    for idx in exclude_plot_indices:
        # Plotly subplots are 1-indexed. row = (idx // cols) + 1, col = (idx % cols) + 1
        # Wait, we need to know rows and cols. Since we don't, we can just use the axis name.
        # axis name is 'x' for 0, 'x2' for 1, 'x3' for 2, etc.
        axis_num = idx + 1
        axis_name = 'xaxis' if axis_num == 1 else f'xaxis{axis_num}'
        if axis_name in fig.layout:
            fig.layout[axis_name].matches = None
            fig.layout[axis_name].range = None
            fig.layout[axis_name].minallowed = None
            fig.layout[axis_name].maxallowed = None
            fig.layout[axis_name].hoverformat = None
            fig.layout[axis_name].showspikes = False

    return fig


def get_update_layout_for_plots(fig, num_rows, num_cols, main_title=None, hover_mode='x unified', show_scale_toggle=False):
    dynamic_height = get_figure_height(num_rows, num_cols)

    # Calculate Y coordinates so they are exactly N pixels above the plot area.
    # This prevents the UI from flying away when the chart gets really tall.
    buttons_y = 1.0 + (30.0 / dynamic_height)  # 30px above the plot
    legend_y = 1.0 + (70.0 / dynamic_height)   # 70px above the plot
    1.0 + (130.0 / dynamic_height)   # 130px above the plot, safely above legend

    # Find all y-axes that are used for price, so we can apply log scale ONLY to them
    price_axes = set()
    if fig and hasattr(fig, 'data'):
        for trace in fig.data:
            is_price_trace = False

            if getattr(trace, 'type', '') == 'candlestick':
                is_price_trace = True
            elif getattr(trace, 'name', '') == 'Price':
                # Ignore dummy legend traces which have x=[None]
                x_data = getattr(trace, 'x', None)
                if x_data is not None and len(x_data) > 0 and x_data[0] is not None:
                    is_price_trace = True

            if is_price_trace:
                y_axis = getattr(trace, 'yaxis', None)
                if not y_axis or y_axis == 'y':
                    price_axes.add('yaxis')
                else:
                    # Plotly trace.yaxis='y2' -> layout key='yaxis2'
                    price_axes.add(y_axis.replace('y', 'yaxis'))

    price_axes = list(price_axes)

    # If no price axes found, disable the scale toggle so it doesn't accidentally overwrite the y-axis
    if not price_axes:
        show_scale_toggle = False

    linear_args = {f"{k}.type": "linear" for k in price_axes}
    log_args = {f"{k}.type": "log" for k in price_axes}

    layout_updates = dict(
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(count=2, label="2Y", step="year", stepmode="backward"),
                    dict(count=3, label="3Y", step="year", stepmode="backward"),
                    dict(count=5, label="5Y", step="year", stepmode="backward"),
                    dict(count=10, label="10Y", step="year", stepmode="backward"),
                    dict(count=15, label="15Y", step="year", stepmode="backward"),
                    dict(step="all", label="Max")
                ]),
                bgcolor=vc.BLUE_BACKGROUND,
                activecolor=vc.BLUE_BACKGROUND,
                font=dict(color=vc.BRIGHTER_TEXT_COLOR, size=11),
                y=buttons_y,
                yanchor="bottom",
                x=0.0,           # Aligns to the far left
                xanchor="left"
            )
        ),

        template="plotly_dark",
        paper_bgcolor=vc.BACKGROUND_COLOR,
        plot_bgcolor=vc.BACKGROUND_COLOR,
        height=dynamic_height,
        hovermode=hover_mode,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=legend_y,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color=vc.TEXT_COLOR),
            bgcolor=vc.BACKGROUND_COLOR,
        ),
        spikedistance=1000,
        hoverdistance=100,
        font=dict(size=10),
        margin=dict(t=vc.PLOT_MARGIN_TOP, b=vc.PLOT_MARGIN_BOTTOM, l=10, r=10),
        bargap=0.2,
    )

    if show_scale_toggle:
        layout_updates['updatemenus'] = [
            dict(
                type="buttons",
                direction="right",
                x=0.35,          # Aligns right next to the range selector
                y=buttons_y,
                xanchor="left",
                yanchor="bottom",
                font=dict(color=vc.BRIGHTER_TEXT_COLOR, size=11),
                bgcolor=vc.BLUE_BACKGROUND,
                showactive=False,
                buttons=list([
                    dict(args=[linear_args], label="Linear Scale", method="relayout"),
                    dict(args=[log_args], label="Log Scale", method="relayout")
                ])
            )
        ]

    if main_title:
        layout_updates['title'] = dict(
            text=main_title,
            y=1.0,             # Absolute top of the container
            yref='container',
            x=0.5,             # Places it in the center
            xanchor='center',
            yanchor='top',
            pad=dict(t=0),     # Move flush to the top
            font=dict(size=20, color=vc.BRIGHTER_TEXT_COLOR)
        )

    fig.update_layout(**layout_updates)

    return fig
