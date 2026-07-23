"""The options-derived panels: the max-pain curve and the premium/discount history.

These sit apart from the COT panels because they are not COT metrics at all. They read
the options cache, they are keyed by an asset name rather than a positioning frame, and
their x-axis is a strike ladder rather than a date index.
"""

from cotmetrics.indexer import get_indexer

import viz_constants as vc


def get_max_pain_plot(fig, asset_name, row, col):
    """
    Plots the Notional Intrinsic Value curves of all options across different days.
    Simulates the aesthetic of the "Maximum Pain" wash-out graph.
    """
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go

    instrument = get_indexer().get_instrument_from_name(asset_name)
    if not instrument:
        return fig

    symbol = instrument.symbol
    from pathlib import Path

    import cotmetrics.constants as const

    cache_dir = Path(const.CACHE_DIR) / "options"
    history_file = cache_dir / f"{symbol}_options_history.parquet"

    if not history_file.exists():
        fig.add_annotation(
            text="No Options Data Available for this Asset.",
            xref="x domain", yref="y domain", x=0.5, y=0.5, showarrow=False,
            row=row, col=col
        )
        return fig

    try:
        df = pd.read_parquet(history_file)
    except Exception:
        return fig

    if df.empty:
        return fig

    # We want to plot one curve per date
    dates = sorted(df['Date'].unique())
    # To prevent visual clutter, only take the last 7 dates if there are many
    if len(dates) > 7:
        dates = dates[-7:]

    # Color scale from light blue to dark blue/purple to indicate aging
    import plotly.colors as pcolors
    colors = pcolors.sample_colorscale("Blues", [0.4 + (0.6 * i / len(dates)) for i in range(len(dates))])

    last_date = dates[-1]
    last_underlying = 0
    last_max_pain = 0
    last_max_pain_iv = 0
    last_current_iv = 0

    for i, date in enumerate(dates):
        daily_df = df[df['Date'] == date].sort_values('SimulatedStrike')
        if daily_df.empty:
            continue

        color = colors[i]
        is_last = (date == last_date)

        # Plot the curve with markers
        fig.add_trace(go.Scatter(
            x=daily_df['SimulatedStrike'],
            y=daily_df['IntrinsicValue_M'],
            mode='lines+markers',
            marker=dict(symbol='square', size=4 if not is_last else 6, opacity=0.8, line=dict(width=1, color='black')),
            line=dict(color=color, width=1 if not is_last else 2),
            name="Max Pain Curve",
            showlegend=False,
            legendgroup="max_pain_group",
            hovertemplate=f"Date: {date}<br>Strike: %{{x:,.2f}}<br>IV: $%{{y:,.1f}}M<extra></extra>"
        ), row=row, col=col)

        # Find minimum
        min_idx = daily_df['IntrinsicValue_M'].idxmin()
        min_strike = daily_df.loc[min_idx, 'SimulatedStrike']
        min_iv = daily_df.loc[min_idx, 'IntrinsicValue_M']

        # Highlight minimum
        fig.add_trace(go.Scatter(
            x=[min_strike],
            y=[min_iv],
            mode='markers',
            marker=dict(color='yellow', size=8, line=dict(width=1, color='red')),
            name="Max Pain Strike",
            showlegend=False,
            legendgroup="max_pain_group",
            hovertemplate=f"Date: {date}<br>Max Pain Strike: %{{x:,.2f}}<br>Min IV: $%{{y:,.1f}}M<extra></extra>"
        ), row=row, col=col)

        if is_last:
            last_underlying = daily_df['UnderlyingPrice'].iloc[0]
            last_max_pain = min_strike
            last_max_pain_iv = min_iv

            # Interpolate the IV at the exact underlying price
            last_current_iv = np.interp(last_underlying, daily_df['SimulatedStrike'], daily_df['IntrinsicValue_M'])

    # Add vertical line for Current Underlying Price
    if last_underlying > 0:
        fig.add_vline(x=last_underlying, line_width=2, line_color="red", row=row, col=col)

        # Add horizontal dashed lines for Max Pain IV and Current IV
        fig.add_hline(y=last_max_pain_iv, line_width=1, line_dash="dash", line_color="red", opacity=0.7, row=row, col=col)
        fig.add_hline(y=last_current_iv, line_width=1, line_dash="dash", line_color="red", opacity=0.7, row=row, col=col)

        # Add Delta IV annotation arrow if there is a gap
        if last_current_iv > last_max_pain_iv * 1.05:
            fig.add_annotation(
                x=last_max_pain,
                y=last_current_iv,
                ax=0,
                ay=-30,
                showarrow=True,
                arrowhead=2,
                arrowsize=1.5,
                arrowwidth=2,
                arrowcolor="red",
                text=f"ΔIV ~ ${last_current_iv - last_max_pain_iv:.0f}M",
                font=dict(color="red", size=10),
                row=row, col=col
            )

    fig.update_xaxes(title="Simulated Underlying Price", showgrid=True, gridcolor=vc.GRID_COLOR, row=row, col=col)
    fig.update_yaxes(title="Notional IV (Mil USD)", showgrid=True, gridcolor=vc.GRID_COLOR, row=row, col=col)

    return fig


def get_max_pain_historical_plot(fig, asset_name, row, col, showlegend=True):
    """
    Plots the historical Price Premium/Discount to Max Pain and the Delta Intrinsic Value
    over time, simulating the Substack-style chart.
    """
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go

    instrument = get_indexer().get_instrument_from_name(asset_name)
    if not instrument:
        return fig

    symbol = instrument.symbol
    from pathlib import Path

    import cotmetrics.constants as const

    cache_dir = Path(const.CACHE_DIR) / "options"
    history_file = cache_dir / f"{symbol}_options_history.parquet"

    if not history_file.exists():
        fig.add_annotation(
            text="No Options Data Available for this Asset.",
            xref="x domain", yref="y domain", x=0.5, y=0.5, showarrow=False,
            row=row, col=col
        )
        return fig

    try:
        df = pd.read_parquet(history_file)
    except Exception:
        return fig

    if df.empty:
        return fig

    dates = []
    premiums = []
    delta_ivs = []

    # Process each day
    unique_dates = sorted(df['Date'].unique())
    expiry_str = ""

    for date in unique_dates:
        daily_df = df[df['Date'] == date].sort_values('SimulatedStrike')
        if daily_df.empty:
            continue

        underlying = daily_df['UnderlyingPrice'].iloc[0]
        if pd.isna(underlying) or underlying == 0:
            continue

        expiry_str = str(daily_df['Expiry'].iloc[0])[:10]  # Grab just the date part

        # Find max pain (min IV)
        min_idx = daily_df['IntrinsicValue_M'].idxmin()
        min_strike = daily_df.loc[min_idx, 'SimulatedStrike']
        min_iv = daily_df.loc[min_idx, 'IntrinsicValue_M']

        # Calculate premium/discount %
        premium_pct = ((underlying - min_strike) / min_strike) * 100

        # Calculate current IV at underlying price
        current_iv = np.interp(underlying, daily_df['SimulatedStrike'], daily_df['IntrinsicValue_M'])
        delta_iv = current_iv - min_iv

        dates.append(pd.to_datetime(date))
        premiums.append(premium_pct)
        delta_ivs.append(delta_iv)

    if not dates:
        return fig

    # Calculate symmetric bounds for the secondary axis so the zero-lines naturally align
    # This prevents Plotly from auto-scaling and distorting the primary [-15, 15] range
    valid_ivs = [abs(val) for val in delta_ivs if pd.notna(val)]
    max_abs_iv = max(valid_ivs) if valid_ivs else 1.0
    if max_abs_iv == 0:
        max_abs_iv = 1.0
    max_abs_iv = max_abs_iv * 1.15  # Add 15% buffer

    # Plotly traces

    # Trace 1: Price Premium/Discount (Bar Chart, Primary Y)
    fig.add_trace(
        go.Bar(
            x=dates,
            y=premiums,
            name="Price Premium/Discount to Max-Pain Price",
            legendgroup="premium_discount",
            showlegend=showlegend,
            marker=dict(color='lightgrey', line=dict(color='darkgrey', width=1)),
            opacity=0.8,
            hovertemplate="Date: %{x|%d-%b}<br>Premium/Discount: %{y:.2f}%<extra></extra>"
        ),
        row=row, col=col, secondary_y=False
    )

    # Trace 2: Delta IV (Line + Markers, Secondary Y)
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=delta_ivs,
            name="Delta IV",
            legendgroup="delta_iv",
            showlegend=showlegend,
            mode='lines+markers+text',
            line=dict(color='indianred', width=2),
            marker=dict(symbol='circle', color='#1f77b4', size=8, line=dict(width=1, color='white')),
            text=[f"${val:.0f}" for val in delta_ivs],
            textposition="top center",
            textfont=dict(color='grey', size=10),
            hovertemplate="Date: %{x|%d-%b}<br>Δ IV: $%{y:,.1f}M<extra></extra>"
        ),
        row=row, col=col, secondary_y=True
    )

    # Update axes formatting to match aesthetic
    # Primary Y-axis (Premium/Discount)
    fig.update_yaxes(
        title="Price Premium / Discount",
        ticksuffix="%",
        range=[-15, 15],
        autorange=False,
        fixedrange=True,
        showgrid=True,
        gridcolor='rgba(200, 200, 200, 0.2)',
        zeroline=False,
        row=row, col=col, secondary_y=False
    )

    # Add manual zero line to bypass Plotly's dual-axis sync overrides
    fig.add_hline(y=0, line_width=1, line_color='rgba(150, 150, 150, 0.5)', row=row, col=col)

    # Secondary Y-axis (Delta IV)
    fig.update_yaxes(
        title="Δ Intrinsic Value (m USD)",
        tickprefix="$",
        ticksuffix="M",
        tickformat=".0f",
        range=[-max_abs_iv, max_abs_iv],
        autorange=False,
        showgrid=False,
        zeroline=False,
        fixedrange=True,
        title_font=dict(color='indianred'),
        tickfont=dict(color='indianred'),
        row=row, col=col, secondary_y=True
    )

    # X-axis formatting
    fig.update_xaxes(
        tickformat="%d-%b",
        dtick="D1",  # Every day
        tickangle=-90,
        showgrid=False,
        row=row, col=col
    )

    # Format Title
    from datetime import datetime
    try:
        exp_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        formatted_expiry = exp_dt.strftime("%b %Y")
    except Exception:
        formatted_expiry = expiry_str

    title_text = f"<b>{formatted_expiry} {asset_name} Options:</b> Price Premium / Discount to the Max-Pain Price"

    fig.update_layout(
        title=dict(text=title_text, font=dict(size=14, color=vc.BRIGHTER_TEXT_COLOR), x=0.5, xanchor='center'),
        showlegend=True
    )

    return fig
