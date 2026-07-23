import cotmetrics.constants as const
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def calc_metrics(sub_df, skip_mc=False):
    if sub_df.empty:
        return {
            "Trades": 0, "Win Rate": "0%", "Return": "0%", "Profit Factor": "0.00", "R/R": "0.00",
            "Avg Win %": "0%", "Avg Loss %": "0%", "Exp %": 0.0, "Max DD": "0.0%", "MC Max DD (95%)": "0.0%",
            "Max Cons Wins": 0, "Max Cons Losses": 0, "SQN": "0.000", "Excursion Ratio": "0.00",
            "Time Asymmetry": "0.00", "E-Ratio": "0.00", "Exit Efficiency": "0.0%"
        }

    t_trades = len(sub_df)
    t_wins = len(sub_df[sub_df['pct_return'] > 0])
    t_losses = len(sub_df[sub_df['pct_return'] < 0])
    t_win_rate = (t_wins / t_trades) if t_trades > 0 else 0
    t_return = (1 + sub_df['pct_return']).prod() - 1

    sub_df[sub_df['pct_return'] > 0]['pct_return'].mean() if t_wins > 0 else 0
    sub_df[sub_df['pct_return'] < 0]['pct_return'].mean() if t_losses > 0 else 0

    win_sum_pct = sub_df[sub_df['pct_return'] > 0]['pct_return'].sum()
    loss_sum_pct = abs(sub_df[sub_df['pct_return'] < 0]['pct_return'].sum())
    t_pf = (win_sum_pct / loss_sum_pct) if loss_sum_pct != 0 else float('inf')

    t_avg_win_pct = sub_df[sub_df['pct_return'] > 0]['pct_return'].mean() if t_wins > 0 else 0
    t_avg_loss_pct = abs(sub_df[sub_df['pct_return'] < 0]['pct_return'].mean()) if t_losses > 0 else 0
    t_rr = (t_avg_win_pct / t_avg_loss_pct) if t_avg_loss_pct > 0 else float('inf')
    t_exp = (t_win_rate * t_avg_win_pct) - ((1 - t_win_rate) * t_avg_loss_pct)

    # Calculate Exp in ATR
    if 'pts' in sub_df.columns and 'entry_atr' in sub_df.columns:
        valid_atr = sub_df['entry_atr'] > 0
        sub_df['atr_return'] = 0.0
        sub_df.loc[valid_atr, 'atr_return'] = sub_df.loc[valid_atr, 'pts'] / sub_df.loc[valid_atr, 'entry_atr']
        t_avg_win_atr = sub_df[sub_df['atr_return'] > 0]['atr_return'].mean() if len(sub_df[sub_df['atr_return'] > 0]) > 0 else 0
        t_avg_loss_atr = abs(sub_df[sub_df['atr_return'] < 0]['atr_return'].mean()) if len(sub_df[sub_df['atr_return'] < 0]) > 0 else 0
        t_exp_atr = (t_win_rate * t_avg_win_atr) - ((1 - t_win_rate) * t_avg_loss_atr)
    else:
        t_exp_atr = 0.0


    # Calculate Max Drawdown
    sorted_df = sub_df.sort_values('exit') if 'exit' in sub_df.columns else sub_df
    equity = (1 + sorted_df['pct_return']).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    t_max_dd = drawdown.min() if not drawdown.empty else 0

    # Calculate System Quality Number (SQN)
    if 'r_multiple' in sub_df.columns and len(sub_df) > 1:
        r_multiples = sub_df['r_multiple'].fillna(0.0)
        mean_r = r_multiples.mean()
        std_r = r_multiples.std(ddof=1)
        t_sqn = (mean_r / std_r) * np.sqrt(len(sub_df)) if std_r > 0 else 0.0
    elif 'r_multiple' in sub_df.columns and len(sub_df) == 1:
        t_sqn = float(sub_df['r_multiple'].fillna(0.0).iloc[0])
    else:
        t_sqn = 0.0

    # Calculate MFE and MAE metrics
    t_mfe = sub_df['mfe'].mean() if 'mfe' in sub_df.columns and not sub_df['mfe'].isna().all() else 0.0
    t_mae = sub_df['mae'].mean() if 'mae' in sub_df.columns and not sub_df['mae'].isna().all() else 0.0
    t_mfe_10 = sub_df['mfe_10'].mean() if 'mfe_10' in sub_df.columns and not sub_df['mfe_10'].isna().all() else 0.0
    t_mae_10 = sub_df['mae_10'].mean() if 'mae_10' in sub_df.columns and not sub_df['mae_10'].isna().all() else 0.0

    t_excursion_ratio = (t_mfe / abs(t_mae)) if t_mae != 0 else (999.0 if t_mfe > 0 else 0.0)
    t_e_ratio_10 = (t_mfe_10 / abs(t_mae_10)) if t_mae_10 != 0 else (999.0 if t_mfe_10 > 0 else 0.0)

    avg_pct_return = sub_df['pct_return'].mean() if not sub_df.empty else 0.0
    t_exit_eff = (avg_pct_return / t_mfe) if t_mfe != 0 else 0.0

    t_avg_win_bars = sub_df[sub_df['pct_return'] > 0]['bars_held'].mean() if 'bars_held' in sub_df.columns and t_wins > 0 else 0.0
    t_avg_loss_bars = sub_df[sub_df['pct_return'] < 0]['bars_held'].mean() if 'bars_held' in sub_df.columns and t_losses > 0 else 0.0
    t_time_asymmetry = (t_avg_win_bars / t_avg_loss_bars) if t_avg_loss_bars > 0 else (999.0 if t_avg_win_bars > 0 else 0.0)

    t_mc_dd_95 = 0.0
    max_cons_wins = 0
    max_cons_losses = 0

    if not sub_df.empty:
        # Streak analysis
        is_win = (sub_df['pct_return'] > 0).astype(int)
        is_loss = (sub_df['pct_return'] < 0).astype(int)
        win_blocks = is_win.groupby((is_win != is_win.shift()).cumsum()).sum()
        loss_blocks = is_loss.groupby((is_loss != is_loss.shift()).cumsum()).sum()
        max_cons_wins = int(win_blocks.max()) if not win_blocks.empty else 0
        max_cons_losses = int(loss_blocks.max()) if not loss_blocks.empty else 0

        t_exit_eff = sub_df['exit_efficiency'].mean() if 'exit_efficiency' in sub_df.columns and not sub_df['exit_efficiency'].isna().all() else 0.0

    if len(sub_df) > 10 and not skip_mc:
        mc_drawdowns = []
        for _ in range(100):
            mc_returns = sub_df['pct_return'].sample(frac=1.0, replace=True)
            mc_equity = (1 + mc_returns).cumprod()
            mc_peak = mc_equity.cummax()
            mc_dd = (mc_equity - mc_peak) / mc_peak
            mc_drawdowns.append(mc_dd.min())
        t_mc_dd_95 = np.percentile(mc_drawdowns, 5)
    else:
        t_mc_dd_95 = t_max_dd

    return {
        "Trades": t_trades,
        "Win Rate": f"{t_win_rate*100:.0f}%",
        "Return": f"{t_return*100:.1f}%",
        "Profit Factor": f"{t_pf:.1f}",
        "R/R": f"{t_rr:.1f}",
        "Avg Win %": f"{t_avg_win_pct*100:.2f}%",
        "Avg Loss %": f"{-t_avg_loss_pct*100:.2f}%",
        "Exp %": float(round(t_exp * 100, 2)),
        "Exp ATR": float(round(t_exp_atr, 2)),
        "Max DD": f"{t_max_dd*100:.1f}%",
        "MC Max DD (95%)": f"{t_mc_dd_95*100:.1f}%",
        "Max Cons Wins": max_cons_wins,
        "Max Cons Losses": max_cons_losses,
        "SQN": f"{t_sqn:.3f}",
        "Excursion Ratio": f"{t_excursion_ratio:.2f}",
        "Time Asymmetry": f"{t_time_asymmetry:.2f}",
        "E-Ratio": f"{t_e_ratio_10:.2f}",
        "Exit Efficiency": f"{t_exit_eff*100:.1f}%",
        "MFE": f"{t_mfe*100:.2f}%",
        "MAE": f"{t_mae*100:.2f}%"
    }

def generate_tear_sheet(trade_logs, asset_name, daily_df=None, initial_capital=100000):
    """
    Generates a tear sheet of statistics and a Plotly figure showing Price Action, Equity Curve, and Drawdown.
    trade_logs: list of dicts: [{'entry': Timestamp, 'exit': Timestamp, 'outcome': str, 'side': str, 'pts': float}]
    """
    if not trade_logs:
        return None, None, None, None

    df = pd.DataFrame(trade_logs)
    df = df.dropna(subset=['exit']) # Remove timeouts

    if df.empty:
        return None, None, None, None

    df = df.sort_values('exit')

    # Calculate Equity based on compounded percentage returns
    if 'pct_return' not in df.columns:
        df['pct_return'] = 0.0

    df['equity'] = initial_capital * (1 + df['pct_return']).cumprod()

    # Calculate Drawdown
    df['peak'] = df['equity'].cummax()
    df['drawdown'] = (df['equity'] - df['peak']) / df['peak']

    stats_all = calc_metrics(df)
    stats_all["Max DD"] = f"{df['drawdown'].min()*100:.1f}%" # Overwrite with exact combined equity drawdown

    stats_long = calc_metrics(df[df['side'] == 'long'])
    stats_short = calc_metrics(df[df['side'] == 'short'])

    # Plotly Figure
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False,
                        vertical_spacing=0.06,
                        subplot_titles=('Price Action & Trades', 'COT Indices'),
                        row_heights=[0.75, 0.25])
    if daily_df is not None and not daily_df.empty:
        # Limit daily_df to the timeframe of the trades to avoid zooming out too far
        start_date = df['entry'].min() - pd.Timedelta(days=60)
        end_date = df['exit'].max() + pd.Timedelta(days=60)
        plot_df = daily_df.loc[start_date:end_date]

        fig.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df['Open'],
            high=plot_df['High'],
            low=plot_df['Low'],
            close=plot_df['Close'],
            name='Price Action',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350',
            showlegend=False
        ), row=1, col=1)

        # Plot Entry/Exit markers
        longs = df[df['side'] == 'long']
        if not longs.empty:
            long_entries = [d for d in longs['entry'] if pd.notnull(d) and d in plot_df.index]
            if long_entries:
                fig.add_trace(go.Scatter(
                    x=long_entries,
                    y=[plot_df.at[d, 'Low'] * 0.995 for d in long_entries],
                    mode='markers',
                    marker=dict(symbol='triangle-up', size=14, color='#00ff00', line=dict(width=1, color='black')),
                    name='Long Trades',
                    legendgroup='Longs',
                    showlegend=True
                ), row=1, col=1)

            long_exits_win = [d for d in longs[longs['pct_return'] > 0]['exit'] if pd.notnull(d) and d in plot_df.index]
            if long_exits_win:
                fig.add_trace(go.Scatter(
                    x=long_exits_win,
                    y=[plot_df.at[d, 'High'] * 1.005 for d in long_exits_win],
                    mode='markers',
                    marker=dict(symbol='star', size=14, color='#00ff00', line=dict(width=1, color='black')),
                    name='Long Win Exit',
                    legendgroup='Longs',
                    showlegend=False
                ), row=1, col=1)

            long_exits_loss = [d for d in longs[longs['pct_return'] <= 0]['exit'] if pd.notnull(d) and d in plot_df.index]
            if long_exits_loss:
                fig.add_trace(go.Scatter(
                    x=long_exits_loss,
                    y=[plot_df.at[d, 'High'] * 1.005 for d in long_exits_loss],
                    mode='markers',
                    marker=dict(symbol='x', size=12, color='#ff0000', line=dict(width=2, color='#ff0000')),
                    name='Long Loss Exit',
                    legendgroup='Longs',
                    showlegend=False
                ), row=1, col=1)

        shorts = df[df['side'] == 'short']
        if not shorts.empty:
            short_entries = [d for d in shorts['entry'] if pd.notnull(d) and d in plot_df.index]
            if short_entries:
                fig.add_trace(go.Scatter(
                    x=short_entries,
                    y=[plot_df.at[d, 'High'] * 1.005 for d in short_entries],
                    mode='markers',
                    marker=dict(symbol='triangle-down', size=14, color='#ff0000', line=dict(width=1, color='black')),
                    name='Short Trades',
                    legendgroup='Shorts',
                    showlegend=True
                ), row=1, col=1)

            short_exits_win = [d for d in shorts[shorts['pct_return'] > 0]['exit'] if pd.notnull(d) and d in plot_df.index]
            if short_exits_win:
                fig.add_trace(go.Scatter(
                    x=short_exits_win,
                    y=[plot_df.at[d, 'Low'] * 0.995 for d in short_exits_win],
                    mode='markers',
                    marker=dict(symbol='star', size=14, color='#00ff00', line=dict(width=1, color='black')),
                    name='Short Win Exit',
                    legendgroup='Shorts',
                    showlegend=False
                ), row=1, col=1)

            short_exits_loss = [d for d in shorts[shorts['pct_return'] <= 0]['exit'] if pd.notnull(d) and d in plot_df.index]
            if short_exits_loss:
                fig.add_trace(go.Scatter(
                    x=short_exits_loss,
                    y=[plot_df.at[d, 'Low'] * 0.995 for d in short_exits_loss],
                    mode='markers',
                    marker=dict(symbol='x', size=12, color='#ff0000', line=dict(width=2, color='#ff0000')),
                    name='Short Loss Exit',
                    legendgroup='Shorts',
                    showlegend=False
                ), row=1, col=1)

        # Draw Stop Loss and Take Profit Lines
        x_sl, y_sl = [], []
        x_tp, y_tp = [], []
        for _, row in df.iterrows():
            if 'signal' in row and pd.notnull(row['signal']) and 'exit' in row and pd.notnull(row['exit']):
                sig = row['signal']
                ex = row['exit']
                if sig in plot_df.index or ex in plot_df.index:
                    if 'sl' in row and pd.notnull(row['sl']):
                        x_sl.extend([sig, ex, None])
                        y_sl.extend([row['sl'], row['sl'], None])
                    if 'tp' in row and pd.notnull(row['tp']):
                        x_tp.extend([sig, ex, None])
                        y_tp.extend([row['tp'], row['tp'], None])

        if x_sl:
            fig.add_trace(go.Scatter(
                x=x_sl, y=y_sl,
                mode='lines',
                line=dict(color='rgba(255, 51, 51, 0.8)', width=1.5, dash='dot'),
                name='Stop Loss',
                showlegend=True,
                hoverinfo='skip'
            ), row=1, col=1)

        if x_tp:
            fig.add_trace(go.Scatter(
                x=x_tp, y=y_tp,
                mode='lines',
                line=dict(color='rgba(51, 255, 51, 0.8)', width=1.5, dash='dot'),
                name='Take Profit',
                showlegend=True,
                hoverinfo='skip'
            ), row=1, col=1)

        # Batch shapes to dramatically improve performance vs add_vrect in a loop
        shapes = list(fig.layout.shapes) if fig.layout.shapes else []

        # Highlight probability regions
        def add_prob_regions(prob_col, color, threshold=0.40):
            if prob_col not in plot_df.columns:
                return

            in_region = False
            start_date = None

            for date, val in plot_df[prob_col].items():
                if val >= threshold and not in_region:
                    in_region = True
                    start_date = date
                elif val < threshold and in_region:
                    in_region = False
                    shapes.append(dict(type="rect", x0=start_date, x1=date, y0=0, y1=1, xref="x3", yref="y3 domain", fillcolor=color, opacity=0.15, layer="below", line_width=0))

            if in_region and start_date is not None:
                shapes.append(dict(type="rect", x0=start_date, x1=plot_df.index[-1], y0=0, y1=1, xref="x3", yref="y3 domain", fillcolor=color, opacity=0.15, layer="below", line_width=0))

        add_prob_regions('ml_bull_prob', 'green')
        add_prob_regions('ml_bear_prob', 'red')

        # Highlight reversal candles (signal day)
        for _, row in df.iterrows():
            if 'signal' in row and pd.notnull(row['signal']):
                signal_day = row['signal']
                if signal_day in plot_df.index:
                    start_time = signal_day - pd.Timedelta(hours=12)
                    end_time = signal_day + pd.Timedelta(hours=12)
                    shapes.append(dict(type="rect", x0=start_time, x1=end_time, y0=0, y1=1, xref="x3", yref="y3 domain", fillcolor="blue", opacity=0.3, layer="below", line_width=0))

        if shapes:
            fig.update_layout(shapes=shapes)

        # COT Indices
        if const.COMMS_IDX in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[const.COMMS_IDX], mode='lines', name='Commercials', line=dict(color='rgba(255, 77, 77, 0.7)', width=1.5)), row=2, col=1)
        if const.LRG_IDX in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[const.LRG_IDX], mode='lines', name='Large Spec', line=dict(color='rgba(77, 166, 255, 0.7)', width=1.5)), row=2, col=1)
        if const.SML_IDX in plot_df.columns:
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df[const.SML_IDX], mode='lines', name='Small Spec', line=dict(color='rgba(255, 255, 102, 0.7)', width=1.5)), row=2, col=1)

        # Neutral 50 line
        fig.add_trace(go.Scatter(x=[plot_df.index.min(), plot_df.index.max()], y=[50, 50], mode='lines', line=dict(color='gray', width=1, dash='dash'), name='Neutral (50)', hoverinfo='skip'), row=2, col=1)



    fig.update_layout(
        height=1000,
        template='plotly_dark',
        title=f"Performance Tearsheet: {asset_name}",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(20, 20, 20, 0.95)",
            font_size=13,
            font_color="white",
            bordercolor="rgba(255, 255, 255, 0.2)"
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=40, r=40, t=60, b=40)
    )

    # Add Range Selector Buttons and zoom to the last 2 years by default
    if not df.empty:
        last_trade_date = df['exit'].max()
        start_zoom = last_trade_date - pd.Timedelta(days=730)

        fig.update_xaxes(
            range=[start_zoom, last_trade_date + pd.Timedelta(days=30)],
            rangeselector=dict(
                buttons=list([
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(count=3, label="3y", step="year", stepmode="backward"),
                    dict(step="all")
                ]),
                bgcolor="#1e1e1e",
                activecolor="#4db8ff"
            ),
            row=1, col=1
        )


    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="COT Index", range=[0, 100], row=2, col=1)

    # Hide rangeslider for candlestick (which is now row 3, but we can disable for all just in case)
    fig.update_xaxes(rangeslider_visible=False)

    return stats_all, stats_long, stats_short, fig
