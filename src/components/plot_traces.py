"""The traces themselves: one function per panel, plus the primitives they share.

Everything here draws series onto an existing figure at a given (row, col). What each
panel *is* -- its label, whether the basis moves it, whether it needs a secondary axis
-- lives in components.plot_registry; this module only knows how to draw.
"""

import math

import cotmetrics.constants as const
import numpy as np
import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_colors import hex_to_rgba, lighten_hex
from components.plot_layout import get_nice_dtick


def update_legend(fig, showlegend, color_palette, show_price):
    """Legend entries for the standard series, drawn as empty traces.

    Lives with the traces rather than the layout because that is what it adds. The
    legend is a figure-level thing, but the entries in it are not.
    """
    if showlegend:
        add_legend_lines(fig, "Commercials", color_palette[0])
        add_legend_lines(fig, "Large Specs", color_palette[1])
        add_legend_lines(fig, "Small Specs", color_palette[2])
        if show_price:
            add_legend_lines(fig, "Price", color_palette[3])
    return fig


def add_legend_lines(fig, name, color):
    fig.add_trace(go.Scatter(
        x=[None],
        y=[None],
        mode='lines',
        marker_color=color,
        marker=dict(opacity=1, line=dict(color=color, width=1)),
        legendgroup=name.lower(),
        showlegend=True,
        name=name
    ))
    return fig


def add_open_interest_legend(fig, color_palette):
    fig = add_legend_lines(fig, "Open Interest", color_palette[4])
    return fig


def add_trace_to_all(fig, df, col_name, row, col, name, color, zorder, visible=True, is_bar=False, secondary=False, showlegend=False, opacity=1, dash=None):
    """ Global Legend Toggle Logic: Show legend only once, but use legendgroups to link all 5 plots"""
    if is_bar:
        fig.add_trace(go.Bar(
            x=df.index,
            y=df[col_name],
            name=name,
            legendgroup=name.lower(),
            visible=visible,
            showlegend=False,
            opacity=0.8 if zorder == 2 else opacity,
            marker_color=color,
            zorder=zorder,
            marker=dict(opacity=1, line=dict(color=color, width=0.5))),
            row=row,
            col=col,
            secondary_y=secondary
        )
    else:
        line_dict = dict(color=color, width=1)
        if dash:
            line_dict["dash"] = dash
        fig.add_trace(go.Scattergl(
            x=df.index,
            y=df[col_name],
            name=name,
            legendgroup=name.lower(),
            visible=visible,
            showlegend=showlegend,
            opacity=0.8 if zorder == 2 else opacity,
            line=line_dict
            ),
            row=row,
            col=col,
            secondary_y=secondary
        )


def fast_add_vrects(fig, segments, fillcolor, subplots):
    """
    Dramatically faster way to add many vertical rectangles to subplots
    by bypassing individual validation and layout updates.
    subplots: list of (row, col) tuples
    """
    if not segments or not subplots:
        return

    shapes = list(fig.layout.shapes) if fig.layout.shapes else []
    resolved_refs = []
    for r, c in subplots:
        fig.add_vrect(x0=0, x1=1, row=r, col=c)
        dummy = fig.layout.shapes[-1]
        resolved_refs.append((dummy.xref, dummy.yref))
        fig.layout.shapes = fig.layout.shapes[:-1]

    for start_date, end_date in segments:
        for xref, yref in resolved_refs:
            shapes.append(dict(
                type="rect",
                x0=start_date, x1=end_date,
                y0=0, y1=1,
                xref=xref, yref=yref,
                fillcolor=fillcolor,
                layer="below",
                line_width=0
            ))
    fig.update_layout(shapes=shapes)


def get_open_interest_percent_plot(fig, df, row, col, color_palette, show_price=True):
    add_trace_to_all(fig, df, const.COMM_PCT_OI, row, col, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, const.LARGE_PCT_OI, row, col, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, const.SMALL_PCT_OI, row, col, "Small Specs", color_palette[2], 2)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )
    fig.update_yaxes(
        title="%",
        row=row, col=col,
        zeroline=False,
        gridcolor=vc.GRID_COLOR,
        secondary_y=False,
        fixedrange=True
    )

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_willco_plot(fig, df, row, col, color_palette, show_price=True):
    add_trace_to_all(fig, df, const.WILLCO_ALIAS, row, col, "Willco", color_palette[0], 0, showlegend=False)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )
    fig.add_hline(y=const.WILLCO_MIN_THRESHOLD, line_dash="dot", line_color='red', opacity=0.4, row=row, col=col)
    fig.add_hline(y=const.WILLCO_MAX_THRESHOLD, line_dash="dot", line_color='green', opacity=0.5, row=row, col=col)
    fig.update_yaxes(
        title="WILLCO",
        row=row, col=col,
        showgrid=False,
        zeroline=False,
        gridcolor=vc.EMPTY_COLOR,
        secondary_y=False,
        fixedrange=True
    )
    fig.add_hrect(y0=const.WILLCO_MAX_THRESHOLD, y1=100, fillcolor="green", opacity=0.05, line_width=0, row=row, col=col)
    fig.add_hrect(y0=0, y1=const.WILLCO_MIN_THRESHOLD, fillcolor="red", opacity=0.07, line_width=0, row=row, col=col)

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_spearman_plot(fig, df, row, col, color_palette, show_price=True):
    add_trace_to_all(fig, df, const.COMMS_SPEARMAN, row, col, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, const.LRG_SPEARMAN, row, col, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, const.SML_SPEARMAN, row, col, "Small Specs", color_palette[2], 2)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )

    if const.COMMS_SPEARMAN_REGIME_SHIFT in df.columns:
        comm_momentum_col = const.COMM_MOMENTUM
        if comm_momentum_col in df.columns:
            bullish_mask = df[const.COMMS_SPEARMAN_REGIME_SHIFT] & (df[comm_momentum_col] > 0)
            bearish_mask = df[const.COMMS_SPEARMAN_REGIME_SHIFT] & (df[comm_momentum_col] <= 0)
        else:
            bullish_mask = df[const.COMMS_SPEARMAN_REGIME_SHIFT]
            bearish_mask = pd.Series(False, index=df.index)

        bull_segments = []
        bull_id = (bullish_mask != bullish_mask.shift()).cumsum()
        for _, block in df[bullish_mask].groupby(bull_id[bullish_mask].values):
            if not block.empty:
                x0 = block.index[0]
                x1 = block.index[-1]
                if x0 == x1:
                    x0 = x0 - pd.Timedelta(days=3)
                    x1 = x1 + pd.Timedelta(days=3)
                bull_segments.append((x0, x1))
        fast_add_vrects(fig, bull_segments, "rgba(0, 255, 0, 0.2)", [(row, col)])

        bear_segments = []
        bear_id = (bearish_mask != bearish_mask.shift()).cumsum()
        for _, block in df[bearish_mask].groupby(bear_id[bearish_mask].values):
            if not block.empty:
                x0 = block.index[0]
                x1 = block.index[-1]
                if x0 == x1:
                    x0 = x0 - pd.Timedelta(days=3)
                    x1 = x1 + pd.Timedelta(days=3)
                bear_segments.append((x0, x1))
        fast_add_vrects(fig, bear_segments, "rgba(255, 0, 0, 0.2)", [(row, col)])

    fig.update_yaxes(
        title="correlation",
        row=row, col=col,
        showgrid=True,
        zeroline=True,
        gridcolor=vc.GRID_COLOR,
        secondary_y=False,
        fixedrange=True
    )

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_net_pos_plot(fig, df, comms_col, lrg_col, sml_col, row, col, color_palette, show_price=False, show_flips=False, y_title="net position"):
    import flask
    is_mobile = False
    if flask.has_request_context():
        user_agent = flask.request.headers.get('User-Agent', '').lower()
        if any(kw in user_agent for kw in ['mobile', 'android', 'iphone', 'ipad', 'phone', 'ipod']):
            is_mobile = True

    weeks_to_view = 52 if is_mobile else const.DEFAULT_WEEKS_TO_VIEW
    start_idx = max(0, len(df) - weeks_to_view)

    # Scale y-axes to the visible range so the bars aren't squished by historical extremes
    import pandas as pd
    visible_df = df.iloc[start_idx:]

    cols = [c for c in [comms_col, lrg_col, sml_col] if c in visible_df.columns]
    max_pos = visible_df[cols].max().max() if cols else 1000
    min_pos = visible_df[cols].min().min() if cols else -1000
    if pd.isna(max_pos):
        max_pos = 1000
    if pd.isna(min_pos):
        min_pos = -1000
    pos_padding = (max_pos - min_pos) * 0.1
    # Fall back relative to the series' own scale. A fixed 1000-contract floor would
    # swamp the OI-normalized basis, where the whole series lives inside +/-1.
    if pos_padding == 0:
        pos_padding = abs(max_pos) * 0.1 or 1.0
    y_range = [min_pos - pos_padding, max_pos + pos_padding]

    if const.OPEN_INTEREST in visible_df.columns:
        oi_max = visible_df[const.OPEN_INTEREST].max()
        oi_min = visible_df[const.OPEN_INTEREST].min()
        if pd.isna(oi_max):
            oi_max = 1000
        if pd.isna(oi_min):
            oi_min = 0
    else:
        oi_max, oi_min = 1000, 0
    oi_padding = (oi_max - oi_min) * 0.1
    if oi_padding == 0:
        oi_padding = max(abs(oi_max) * 0.1, 1000)
    oi_range = [oi_min - oi_padding, oi_max + oi_padding]


    add_trace_to_all(fig, df, comms_col, row, col, "Commercials", color_palette[0], 0, is_bar=True, opacity=0.8)
    add_trace_to_all(fig, df, lrg_col, row, col, "Large Specs", color_palette[1], 1, is_bar=True, opacity=0.8)
    add_trace_to_all(fig, df, sml_col, row, col, "Small Specs", color_palette[2], 2, is_bar=True, opacity=0.7)
    add_trace_to_all(fig, df, const.OPEN_INTEREST, row, col, "Open Interest", color_palette[4], 3, secondary=True)

    # Calculate independent tick steps to stop Plotly from auto-syncing the axes
    y_dtick = get_nice_dtick(y_range[1] - y_range[0])
    oi_dtick = get_nice_dtick(oi_range[1] - oi_range[0])

    import numpy as np
    y_ticks = np.arange(math.ceil(y_range[0] / y_dtick) * y_dtick, y_range[1] + y_dtick/2, y_dtick).tolist()
    oi_ticks = np.arange(math.ceil(oi_range[0] / oi_dtick) * oi_dtick, oi_range[1] + oi_dtick/2, oi_dtick).tolist()

    fig.update_yaxes(
        title=y_title,
        row=row, col=col,
        range=y_range,
        showgrid=False,
        zeroline=False,
        matches=None,
        gridcolor=vc.EMPTY_COLOR,
        secondary_y=False,
        fixedrange=False,
        tickmode="array",
        tickvals=y_ticks,
        autorange=False
    )

    fig.update_yaxes(
        title="OI",
        row=row, col=col,
        range=oi_range,
        showgrid=False,
        zeroline=False,
        matches=None,
        gridcolor=vc.EMPTY_COLOR,
        secondary_y=True,
        fixedrange=True,
        tickmode="array",
        tickvals=oi_ticks,
        autorange=False
    )

    # Manually draw the zero line to avoid Plotly's dual-axis zeroline alignment bug
    fig.add_hline(
        y=0,
        line_width=2,
        line_color="rgba(255, 255, 255, 0.15)",
        layer="below",
        row=row,
        col=col,
        secondary_y=False
    )

    if show_flips:
        flip_dates = df[df[const.LARGE_FLIP]].index
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

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)

    return fig


def get_index_plot(fig, df, comms_col, lrg_col, sml_col, row, col, color_palette, min_threshold=None, max_threshold=None, show_price=True, smooth_indexing=False):
    # Create a temporary smoothed copy of the dataframe for plotting
    plot_df = df.copy()
    if smooth_indexing:
        plot_df[comms_col] = plot_df[comms_col].rolling(window=4).mean()
        plot_df[lrg_col] = plot_df[lrg_col].rolling(window=4).mean()
        plot_df[sml_col] = plot_df[sml_col].rolling(window=4).mean()
    add_trace_to_all(fig, plot_df, comms_col, row, col, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, plot_df, lrg_col, row, col, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, plot_df, sml_col, row, col, "Small Specs", color_palette[2], 2, opacity=0.9)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )
    fig.update_yaxes(
        title="Index",
        range=[0, 100],
        row=row, col=col,
        secondary_y=False,
        showgrid=True,
        zeroline=False,
        gridcolor=vc.GRID_COLOR,
        fixedrange=True
    )

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_basis_overlay_plot(fig, df_raw, df_norm, value_col, row, col, color_palette,
                           y_title, y_range=None, show_oi=True, zero_line=False):
    """Draw one series on both positioning bases with the gap between them shaded.

    The comparison is what carries the information here, so this deliberately plots the
    Commercials leg only. Six lines (three groups x two bases) would bury the very
    divergence the view exists to show, and the band could not be drawn at all.

    Both bases must already share a scale — a 0-100 index, a z-score, a correlation. Net
    positions cannot use this view: raw is contracts and normalized is a fraction of OI,
    so the two would need separate axes and the shaded gap would be meaningless.
    """
    is_first = (row == 1 and col == 1)

    # Band first so both lines draw over it. `fill='tonexty'` fills against the trace
    # added immediately before, so the invisible raw baseline has to come first.
    fig.add_trace(go.Scatter(
        x=df_raw.index, y=df_raw[value_col],
        mode='lines', line=dict(width=0),
        hoverinfo='skip', showlegend=False, legendgroup="basis divergence",
    ), row=row, col=col, secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df_norm.index, y=df_norm[value_col],
        mode='lines', line=dict(width=0),
        fill='tonexty', fillcolor=hex_to_rgba(color_palette[0], vc.BASIS_DIVERGENCE_ALPHA),
        hoverinfo='skip', showlegend=is_first, legendgroup="basis divergence",
        name="Divergence",
    ), row=row, col=col, secondary_y=False)

    # Both lines are Commercials, so the normalized one is a lighter tint of the
    # Commercials color rather than another palette slot (palette[1]/[2] are Large and
    # Small Specs). Dash carries the rest of the distinction.
    norm_color = lighten_hex(color_palette[0], vc.BASIS_OVERLAY_TINT)
    add_trace_to_all(fig, df_raw, value_col, row, col, "Commercials (Raw)",
                     color_palette[0], 0, showlegend=is_first)
    add_trace_to_all(fig, df_norm, value_col, row, col, "Commercials (% of OI)",
                     norm_color, 1, showlegend=is_first,
                     dash=vc.BASIS_OVERLAY_DASH)

    # Open Interest, not Price, as the context series. OI is the denominator of the
    # transform this plot exists to visualize, so it's the series that explains why the
    # two lines part company. Price is already the secondary on every other plot on the
    # page, which makes it the redundant choice here specifically.
    if show_oi:
        add_trace_to_all(fig, df_raw, const.OPEN_INTEREST, row, col, "Open Interest",
                         color_palette[4], 3, secondary=True, opacity=0.6,
                         showlegend=is_first)
        fig.update_yaxes(
            title="OI", row=row, col=col, showgrid=False, zeroline=False,
            gridcolor=vc.EMPTY_COLOR, secondary_y=True, fixedrange=True
        )

    fig.update_yaxes(
        title=y_title, row=row, col=col, secondary_y=False,
        range=y_range, showgrid=True, zeroline=False,
        gridcolor=vc.GRID_COLOR, fixedrange=True,
        rangemode="normal" if y_range is None else None,
    )
    if zero_line:
        fig.add_hline(y=0, line_width=1, line_color="rgba(255, 255, 255, 0.15)",
                      layer="below", row=row, col=col, secondary_y=False)
    return fig


def get_zscore_plot(fig, df, row, col, color_palette, show_price=True):
    # The raw/OI-normalized choice is resolved upstream in CotIndexer.get_symbols_data,
    # which is what these generic aliases carry. Do not re-select columns here.
    add_trace_to_all(fig, df, const.COMMS_ZSCORE, row, col, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, const.LRG_ZSCORE, row, col, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, const.SML_ZSCORE, row, col, "Small Specs", color_palette[2], 2)
    add_trace_to_all(fig, df, const.OI_ZSCORE, row, col, "Open Interest", color_palette[4], 3, opacity=0.6)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )
    fig.update_yaxes(
        title="Std Dev",
        range=[-3, 3],
        row=row, col=col,
        secondary_y=False,
        showgrid=True,
        zeroline=True,
        gridcolor=vc.GRID_COLOR,
        fixedrange=True
    )

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_momentum_plot(fig, df, row, col, color_palette, show_price=True):
    add_trace_to_all(fig, df, const.COMM_MOMENTUM, row, col, "Commercials", color_palette[0], 0, is_bar=True, opacity=0.8)
    add_trace_to_all(fig, df, const.LRG_MOMENTUM, row, col, "Large Specs", color_palette[1], 1, is_bar=True, opacity=0.6)
    add_trace_to_all(fig, df, const.SML_MOMENTUM, row, col, "Small Specs", color_palette[2], 2, is_bar=True, opacity=0.6)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )

    fig.update_yaxes(
        title="ROC",
        range=[-100, 100],
        row=row, col=col,
        secondary_y=False,
        showgrid=True,
        zeroline=False,
        gridcolor=vc.GRID_COLOR,
        fixedrange=True
    )

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_cot_macd_subplot(fig, df, row, col, color_palette, show_price=True):
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )

    hist = df[const.COMM_MACD_HIST]
    prev_hist = hist.shift(1)
    STRONG_BULL = '#22c55e'  # Dark Green (Positive & Growing)
    WEAK_BULL   = '#bbf7d0'  # Light Green (Positive & Shrinking)
    STRONG_BEAR = '#ef4444'  # Dark Red (Negative & Falling/Growing stronger downward)
    WEAK_BEAR   = '#fecaca'  # Light Red (Negative & Rising/Weakening downward)

    conditions = [
        (hist >= 0) & (hist > prev_hist),   # Above zero and trending up
        (hist >= 0) & (hist <= prev_hist),  # Above zero but trending down
        (hist < 0) & (hist < prev_hist),    # Below zero and trending down
        (hist < 0) & (hist >= prev_hist)    # Below zero but trending up
    ]
    # Apply the mapping, defaulting to gray for the very first row
    choices = [STRONG_BULL, WEAK_BULL, STRONG_BEAR, WEAK_BEAR]
    hist_colors = np.select(conditions, choices, default='gray')

    # Add the Histogram (The Momentum Velocity)
    fig.add_trace(go.Bar(
        x=df.index,
        y=df[const.COMM_MACD_HIST],
        marker_color=hist_colors,
        name='MACD Hist',
        opacity=0.8,
        showlegend=False
    ), row=row, col=col)

    # Add the Fast MACD Line
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[const.COMM_MACD_LINE],
        mode='lines',
        line=dict(color='#3b82f6', width=2),
        name='MACD',
        showlegend=False
    ), row=row, col=col)

    # Add the Slow Signal Line
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[const.COMM_MACD_SIGNAL],
        mode='lines',
        line=dict(color='#f59e0b', width=2, dash='dot'),
        name='Signal Line',
        showlegend=False
    ), row=row, col=col)

    # Lock the zero-line so it's always perfectly visible
    fig.add_hline(
        y=0,
        line_dash="solid",
        line_color="rgba(255, 255, 255, 0.2)",
        line_width=1,
        row=row, col=col
    )

    # Apply dynamic range zooming to this specific subplot
    y_min = df[[const.COMM_MACD_LINE, const.COMM_MACD_SIGNAL, const.COMM_MACD_HIST]].min().min()
    y_max = df[[const.COMM_MACD_LINE, const.COMM_MACD_SIGNAL, const.COMM_MACD_HIST]].max().max()
    y_padding = (y_max - y_min) * 0.10

    fig.update_yaxes(
        title_text="Commercial Net Positioning MACD",
        range=[y_min - y_padding, y_max + y_padding],
        row=row, col=col,
        secondary_y=False,
        showgrid=False,
        zeroline=True,
        gridcolor=vc.EMPTY_COLOR,
        fixedrange = False
    )

    return fig


def get_oi_alignment_decorators(fig, df, target_subplots, color_palette, offset_pct=0, show_legend=True, show_oi_legend=False):
    if not target_subplots:
        return fig

    high_offset = 1 + offset_pct
    low_offset = 1 - offset_pct
    max_low_offset = 1 - (3 * offset_pct)
    max_high_offset = 1 + (3 * offset_pct)

    marker_size = 8
    larger_marker_size = 10
    small_marker_size = 5
    bullish_color = 'rgba(0, 255, 0, 1.0)'
    bearish_color = 'rgba(255, 0, 0, 1.0)'
    debug_color = color_palette[1]
    bullish_group = "bullish"
    bearish_group = "bearish"
    debug_group = "debug"

    if show_legend:
        if show_oi_legend:
            add_legend_lines(fig, "Open Interest", color_palette[4])
        add_legend_markers(fig, "Bull Trend", bullish_group, bullish_color, "triangle-up", marker_size)
        add_legend_markers(fig, "Bull Bottom", bullish_group, bullish_color, "asterisk-open", marker_size)
        add_legend_markers(fig, "Short Sqz", bullish_group, bullish_color, "bowtie", marker_size)
        add_legend_markers(fig, "Stealth Bull", bullish_group, bullish_color, "star", marker_size)
        add_legend_markers(fig, "Spec Bull Breakout", bullish_group, bullish_color, "square", marker_size-1)
        add_legend_markers(fig, "LW Macro Bull", bullish_group, bullish_color, "circle", marker_size-1)

        add_legend_markers(fig, "Bear Trend", bearish_group, bearish_color, "triangle-down", marker_size)
        add_legend_markers(fig, "Bear Top", bearish_group, bearish_color, "asterisk-open", marker_size)
        add_legend_markers(fig, "Exhaustion", bearish_group, bearish_color, "bowtie", marker_size)
        add_legend_markers(fig, "Capitulation", bearish_group, bearish_color, "star", marker_size)
        add_legend_markers(fig, "Comms Capitulation", bearish_group, bearish_color, "diamond", larger_marker_size)
        add_legend_markers(fig, "Spec Bear Breakdown", bearish_group, bearish_color, "square", marker_size-1)
        add_legend_markers(fig, "LW Macro Bear", bearish_group, bearish_color, "circle", marker_size-1)

        # TODO not sure if these should be displayed on the legend
        add_legend_markers(fig, "Comm Accum", debug_group, debug_color, "circle", small_marker_size)
        add_legend_markers(fig, "Comm New Accum", debug_group, debug_color, "star", marker_size)
        add_legend_markers(fig, "Short Covering", debug_group, debug_color, "diamond", marker_size)
        add_legend_markers(fig, "Multi Yr Extreme", debug_group, debug_color, "arrow-up", marker_size-1)
        add_legend_markers(fig, "Multi Yr Extreme", debug_group, debug_color, "arrow-down", marker_size-1)

    # =======================================================
    # PLOTLY TRACES RENDERED TO TARGET SUBPLOTS
    # =======================================================
    for r, c in target_subplots:
        bullish_trend_continuation_mask = (df[const.BULLISH_TREND_CONTINUING]).to_numpy()
        bullish_bottom_mask = (df[const.BULLISH_BOTTOM]).to_numpy()
        spec_driven_bull_breakout_mask = (df[const.SPEC_DRIVEN_BULL_BREAKOUT]).to_numpy()
        short_squeeze_mask = (df[const.SHORT_SQUEEZE]).to_numpy()
        stealth_bull_mask = (df[const.STEALTH_BULLISH_BOTTOM]).to_numpy()
        lw_macro_bull_setup_mask = (df[const.LW_MACRO_BULL_SETUP]).to_numpy()
        multi_year_bull_extreme_mask = (df[const.MULTI_YR_BULL_EXTREME]).to_numpy()

        bearish_trend_continuation_mask = (df[const.BEARISH_TREND_CONTINUING]).to_numpy()
        bearish_top_mask = (df[const.BEARISH_TOP]).to_numpy()
        exhaustion_mask = (df[const.EXHAUSTION]).to_numpy()
        capitulation_mask = (df[const.CAPITULATION]).to_numpy()
        spec_driven_bear_breakdown_mask = (df[const.SPEC_DRIVEN_BEAR_BREAKDOWN]).to_numpy()
        comms_capitulation_mask = (df[const.COMMS_CAPITULATION]).to_numpy()
        lw_macro_bear_setup_mask = (df[const.LW_MACRO_BEAR_SETUP]).to_numpy()
        multi_year_bear_extreme_mask = (df[const.MULTI_YR_BEAR_EXTREME]).to_numpy()

        comm_accumulation_mask = (df[const.COMMS_ACCUMULATION]).to_numpy()
        comm_new_accumulation_mask = (df[const.COMMS_NEW_ACCUMULATION]).to_numpy()
        short_covering_mask = (df[const.SHORT_COVERING]).to_numpy()

        fig.add_trace(go.Scatter(
            x=df.index[bullish_trend_continuation_mask],
            y=df[const.HIGH_PRICE][bullish_trend_continuation_mask] * high_offset,
            mode='markers', legendgroup=bullish_group, marker=dict(symbol='triangle-up', color=bullish_color, size=marker_size),
            showlegend=False, opacity=1, name="Bull Trend"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[bullish_bottom_mask],
            y=df[const.LOW_PRICE][bullish_bottom_mask] * low_offset,
            mode='markers', marker=dict(symbol='asterisk-open', color=bullish_color, size=marker_size),
            showlegend=False, legendgroup=bullish_group, opacity=1, name="Bull Bottom"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[spec_driven_bull_breakout_mask],
            y=df[const.HIGH_PRICE][spec_driven_bull_breakout_mask] * high_offset,
            mode='markers', marker=dict(symbol='square', color=bullish_color, size=marker_size-1),
            showlegend=False, legendgroup=bullish_group, opacity=1, name="Spec Bull Breakout"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[short_squeeze_mask],
            y=df[const.LOW_PRICE][short_squeeze_mask] * low_offset,
            mode='markers', marker=dict(symbol='bowtie', color=bullish_color, size=marker_size),
            showlegend=False, legendgroup=bullish_group, opacity=1, name="Short Sqz"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[stealth_bull_mask],
            y=df[const.HIGH_PRICE][stealth_bull_mask] * high_offset,
            mode='markers', marker=dict(symbol='star', color=bullish_color, size=marker_size),
            showlegend=False, legendgroup=bullish_group, opacity=1, name="Stealth Bull"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[lw_macro_bull_setup_mask],
            y=df[const.HIGH_PRICE][lw_macro_bull_setup_mask] * high_offset,
            mode='markers', marker=dict(symbol='circle', color=bullish_color, size=marker_size-1),
            showlegend=False, legendgroup=bullish_group, opacity=1, name="LW Macro Bull"),
            row=r, col=c, secondary_y=False
        )

        fig.add_trace(go.Scatter(
            x=df.index[comm_accumulation_mask],
            y=df[const.LOW_PRICE][comm_accumulation_mask] * max_low_offset,
            mode='markers', marker=dict(symbol='circle', color=debug_color, size=small_marker_size),
            showlegend=False, legendgroup=debug_group, opacity=1, name="Comm Accumulation"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[short_covering_mask],
            y=df[const.LOW_PRICE][short_covering_mask] * max_low_offset,
            mode='markers', marker=dict(symbol='diamond', color=debug_color, size=marker_size),
            showlegend=False, legendgroup=debug_group, opacity=1, name="Short Covering"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[comm_new_accumulation_mask],
            y=df[const.LOW_PRICE][comm_new_accumulation_mask] * max_low_offset,
            mode='markers', marker=dict(symbol='star', color=debug_color, size=marker_size),
            showlegend=False, legendgroup=debug_group, opacity=1, name="Comm New Accum"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[multi_year_bull_extreme_mask],
            y=df[const.HIGH_PRICE][multi_year_bull_extreme_mask] * max_high_offset,
            mode='markers', marker=dict(symbol='arrow-up', color=debug_color, size=marker_size-1),
            showlegend=False, legendgroup=debug_group, opacity=1, name="Multi Yr Extreme"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[multi_year_bear_extreme_mask],
            y=df[const.LOW_PRICE][multi_year_bear_extreme_mask] * max_low_offset,
            mode='markers', marker=dict(symbol='arrow-down', color=debug_color, size=marker_size-1),
            showlegend=False, legendgroup=debug_group, opacity=1, name="Multi Yr Extreme"),
            row=r, col=c, secondary_y=False
        )

        fig.add_trace(go.Scatter(
            x=df.index[bearish_trend_continuation_mask],
            y=df[const.LOW_PRICE][bearish_trend_continuation_mask] * low_offset,
            mode='markers', marker=dict(symbol='triangle-down', color=bearish_color, size=marker_size),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="Bear Trend"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[bearish_top_mask],
            y=df[const.HIGH_PRICE][bearish_top_mask] * high_offset,
            mode='markers', marker=dict(symbol='asterisk-open', color=bearish_color, size=marker_size),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="Bear Top"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[exhaustion_mask],
            y=df[const.HIGH_PRICE][exhaustion_mask] * high_offset,
            mode='markers', marker=dict(symbol='bowtie', color=bearish_color, size=marker_size),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="Exhaustion"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[capitulation_mask],
            y=df[const.LOW_PRICE][capitulation_mask] * low_offset,
            mode='markers', marker=dict(symbol='star', color=bearish_color, size=marker_size-1),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="Capitulation"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[comms_capitulation_mask],
            y=df[const.LOW_PRICE][comms_capitulation_mask] * low_offset,
            mode='markers', marker=dict(symbol='diamond', color=bearish_color, size=larger_marker_size),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="Comms Capitulation"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[spec_driven_bear_breakdown_mask],
            y=df[const.LOW_PRICE][spec_driven_bear_breakdown_mask] * low_offset,
            mode='markers', marker=dict(symbol='square', color=bearish_color, size=marker_size-1),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="Spec Bear Breakdown"),
            row=r, col=c, secondary_y=False
        )
        fig.add_trace(go.Scatter(
            x=df.index[lw_macro_bear_setup_mask],
            y=df[const.LOW_PRICE][lw_macro_bear_setup_mask] * low_offset,
            mode='markers', marker=dict(symbol='circle', color=bearish_color, size=marker_size-1),
            showlegend=False, legendgroup=bearish_group, opacity=1, name="LW Macro Bear"),
            row=r, col=c, secondary_y=False
        )

    return fig


def get_lrg_sentiment_plot(fig, df, row, col, color_palette, show_price=True):
    add_trace_to_all(fig, df, const.LW_LRG_SENTIMENT, row, col, "Large Specs", color_palette[1], 0, showlegend=False)
    if show_price:
        add_trace_to_all(fig, df, const.CLOSING_PRICE, row, col, "Price", color_palette[3], 3, secondary=True, opacity=0.6)
        fig.update_yaxes(
            title="$",
            row=row, col=col,
            showgrid=False,
            zeroline=False,
            gridcolor=vc.EMPTY_COLOR,
            secondary_y=True,
            fixedrange=True
        )
    fig.add_hline(y=const.LW_LRG_SENTIMENT_MAX_THRESHOLD, line_dash="dot", line_color='red', opacity=0.4, row=row, col=col)
    fig.add_hline(y=const.LW_LRG_SENTIMENT_MIN_THRESHOLD, line_dash="dot", line_color='green', opacity=0.5, row=row, col=col)
    fig.update_yaxes(
        title="Large Trader Sentiment",
        row=row, col=col,
        showgrid=False,
        zeroline=False,
        gridcolor=vc.EMPTY_COLOR,
        secondary_y=False,
        fixedrange=True
    )
    fig.add_hrect(y0=0, y1=const.LW_LRG_SENTIMENT_MIN_THRESHOLD, fillcolor="green", opacity=0.05, line_width=0, row=row, col=col)
    fig.add_hrect(y0=const.LW_LRG_SENTIMENT_MAX_THRESHOLD, y1=100, fillcolor="red", opacity=0.07, line_width=0, row=row, col=col)

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, show_price)
    return fig


def get_price_plot(fig, df, row, col, color_palette, price_scale='linear'):
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df[const.OPEN_PRICE],
            high=df[const.HIGH_PRICE],
            low=df[const.LOW_PRICE],
            close=df[const.CLOSING_PRICE],
            name="Price Candles",
            whiskerwidth=0.2,
            line=dict(width=1.5),
            increasing=dict(
                fillcolor='rgba(0, 200, 100, 0.5)',
                line=dict(width=2, color='rgba(0, 200, 100, 0.5)')
            ),
            decreasing=dict(
                fillcolor='rgba(255, 100, 100, 0.5)',
                line=dict(width=2, color='rgba(255, 100, 100, 0.5)')
            ),
            showlegend=False,
        ),
        row=row,
        col=col,
        secondary_y=False
    )

    # --- Dynamic Tick Formatting ---
    # Determine the appropriate decimal precision based on how large the price is
    max_price = df[const.CLOSING_PRICE].max()
    if price_scale == "log":
        if max_price < 5:
            tick_fmt = ",.4f"  # 4 decimals for Currencies (e.g., 1.0850)
        elif max_price < 100:
            tick_fmt = ",.2f"  # 2 decimals for mid-priced assets (e.g., 75.50)
        else:
            tick_fmt = ",.0f"  # 0 decimals for large assets like Gold/Indices (e.g., 2,050)
    else:
        tick_fmt = None

    fig.update_yaxes(
        title="$",
        type=price_scale,
        row=row, col=col,
        showgrid=False,
        zeroline=False,
        gridcolor=vc.EMPTY_COLOR,
        secondary_y=False,
        nticks=3,
        tickformat=tick_fmt,
        autorange=True,
        rangemode="normal",  # Prevents the axis from forcing a 0 baseline
        fixedrange=False,   # Allows user zooming
    )

    showlegend = row == 1 and col == 1
    fig = update_legend(fig, showlegend, color_palette, True)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


def add_legend_markers(fig, name, group, color, symbol, size):
    fig.add_trace(go.Scatter(
        x=[None],
        y=[None],
        mode='markers',
        marker=dict(symbol=symbol, color=color, size=size),
        legendgroup=group,
        opacity=1,
        name=name
    ))
    return fig


def add_trend_regime_highlighting(fig, df, ma, uptrend_mask, downtrend_mask, target_subplots):
    """
    Highly optimized background shader that also plots the trend-defining moving average.
    Groups contiguous True values in a boolean mask to draw the minimum possible
    number of shapes, preventing Plotly frontend lag.
    """

    # ---------------------------------------------------------
    # 1. Process Uptrends
    # ---------------------------------------------------------
    # 1. Process Uptrends
    # ---------------------------------------------------------
    up_segments = []
    up_regime_id = (uptrend_mask != uptrend_mask.shift()).cumsum()
    for _, block in df[uptrend_mask].groupby(up_regime_id[uptrend_mask].values):
        if block.index[0] != block.index[-1]:
            up_segments.append((block.index[0], block.index[-1]))

    fast_add_vrects(fig, up_segments, "rgba(0, 255, 0, 0.05)", [(r, c) for r, c, _ in target_subplots])

    # ---------------------------------------------------------
    # 2. Process Downtrends
    # ---------------------------------------------------------
    down_segments = []
    down_regime_id = (downtrend_mask != downtrend_mask.shift()).cumsum()
    for _, block in df[downtrend_mask].groupby(down_regime_id[downtrend_mask].values):
        if block.index[0] != block.index[-1]:
            down_segments.append((block.index[0], block.index[-1]))

    fast_add_vrects(fig, down_segments, "rgba(255, 0, 0, 0.05)", [(r, c) for r, c, _ in target_subplots])

    # ---------------------------------------------------------
    # 3. Plot the Moving Average
    # ---------------------------------------------------------
    for r, c, is_secondary in target_subplots:
        fig.add_trace(go.Scatter(
            x=ma.index,
            y=ma,
            mode='lines',
            line=dict(
                color=vc.SOLARIZED_DARK_BASE00,
                width=1.25,
                dash='dot',
            ),
            zorder=4,
            name='MA',
            showlegend=False,                      # Keeps the legend clean
            hoverinfo='skip'                       # Prevents the tooltip from getting cluttered
        ),
         secondary_y=is_secondary,
         row=r, col=c)

    return fig


def get_setup_highlighting(fig, df, comm_col_str, lrg_col_str, sml_col_str, model, row, col, is_equity, max_length_weeks=520):
    """Loop through the data to find 'Extreme' clusters

    `model` is a models.PositioningModel: it supplies the band *and* the leg set
    together, so a chart drawn on one basis cannot be shaded with another's rule.
    """
    if model is None or row is None:
        return fig

    df_slice = df.iloc[-max_length_weeks:]
    comms = df_slice[comm_col_str]
    large = df_slice[lrg_col_str]
    small = df_slice[sml_col_str]
    dates = df_slice.index

    green_mask, red_mask, _, _ = model.setup_masks(comms, large, small, is_equity)

    # Ensure none of the values are nan
    valid_mask = comms.notna() & large.notna() & small.notna()
    green_mask &= valid_mask
    red_mask &= valid_mask

    # Get the integer row numbers where conditions are True (ignoring the 0th index to allow i-1)
    green_indices = np.where(green_mask)[0]
    red_indices = np.where(red_mask)[0]

    def _add_vrects(indices, fillcolor):
        if len(indices) == 0:
            return

        # Group contiguous indices
        segments = []
        start = indices[0]
        prev = indices[0]

        for i in indices[1:]:
            if i == prev + 1:
                prev = i
            else:
                segments.append((start, prev))
                start = i
                prev = i
        segments.append((start, prev))

        date_segments = []
        for start_idx, end_idx in segments:
            safe_start = start_idx - 1 if start_idx > 0 else 0
            if safe_start < end_idx:
                date_segments.append((dates[safe_start], dates[end_idx]))

        fast_add_vrects(fig, date_segments, fillcolor, [(row, col)])

    _add_vrects(green_indices, "rgba(0, 255, 0, 0.15)")
    _add_vrects(red_indices, "rgba(255, 0, 0, 0.15)")

    return fig
