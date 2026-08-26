import urllib.parse
from collections import namedtuple

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils

# pyrefly: ignore [missing-import]
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics.indexer import get_indexer

# Dash-free signal synthesis lives in core.synthesis; re-exported here so existing
# `from components.signal_cards import ...` callers keep working.
from cotmetrics.synthesis import _collect_active_signals, generate_exhaustive_tape_synthesis

# pyrefly: ignore [missing-import]
from dash import dcc, html

import viz_constants as vc

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_getter(latest, context):
    """Reader for one row of a get_symbols_data frame, used by both card builders.

    Every default here is a neutral reading (50 for an index, 0 for a z-score), which
    is right for a NaN and wrong for a column that is not on the frame at all: the
    card renders as an ordinary neutral value for a metric nobody computed. NaN is a
    data condition, a missing column is a bug, so only the second one is reported.
    """
    def safe_get(key, default_val):
        if key not in latest.index:
            utils.cot_logger.error(
                "%s: %r is not on the frame. get_symbols_data no longer emits it, or the "
                "name is misspelled. Falling back to %r, which will read as a normal value.",
                context, key, default_val,
            )
            return default_val
        val = latest.get(key)
        return val if pd.notna(val) else default_val
    return safe_get


def _make_signal_card(title, value_text, value_color, subtitle, tooltip):
    """Build a standard two-section signal card.

    Parameters
    ----------
    title       : str  – small all-caps category label (e.g. "POSITIONING")
    value_text  : str  – primary status text (coloured)
    value_color : str  – CSS colour for text and border accent
    subtitle    : Dash component – displayed below the main status (html.Small etc.)
    tooltip     : str or Dash component – descriptive text in the bottom panel
    """
    is_neutral = (value_color == vc.SOLARIZED_DARK_BASE00) and (value_text in [
        "NEUTRAL", "STABLE", "NO ACTIVE SETUP", "BALANCED CAPACITY", "SYNCHRONIZED", "AVERAGE", "NORMAL"
    ])

    if is_neutral:
        card_style = {
            'backgroundColor': 'var(--card-color-neutral)',
            'border': '1px solid var(--border-color-dim)',
            'opacity': 0.4,
            'transition': 'opacity 0.3s ease',
        }
    else:
        card_style = {
            'backgroundColor': 'var(--card-color-active)',
            'border': f'1px solid {value_color}40',
            'opacity': 1.0,
            'transition': 'opacity 0.3s ease',
        }

    return dbc.Card([
        dbc.CardBody([
            html.Div(title, className="card-title text-muted mb-0",
                    style={'fontSize': '0.65rem', 'fontWeight': 'bold', 'textTransform': 'uppercase'}),
            html.Div(value_text, style={'color': value_color, 'fontWeight': 'bold', 'fontSize': '0.80rem', 'margin': 0}),
            subtitle,
        ], className="py-1 px-2 text-center"),

        html.Div(
            tooltip,
            style={
                'backgroundColor': 'var(--card-accent-color)',
                'borderTop': f'1px solid {value_color}20',
                'fontSize': '0.65rem',
                'color': vc.TEXT_COLOR,
                'borderRadius': '0 0 5px 5px',
            },
            className="py-1 px-2 text-center text-sm-start flex-grow-1 d-flex align-items-center"
        ),
    ], style=card_style, className="m-0 flex-fill d-flex flex-column")


def build_signal_panel(df, asset, color_palette, target_date=None, is_equity=False,
                       model=None):
    # The band travels with the model rather than as two loose numbers, so a caller
    # cannot pair one model's thresholds with another's basis. models.resolve tolerates
    # a stale key from a browser session store.
    model = model if isinstance(model, models.PositioningModel) else models.resolve(model)
    min_idx, max_idx = model.low, model.high

    try:
        if df is None or df.empty:
            return html.Div()

        # Slice to the requested date (or use latest row)
        if target_date is not None:
            historical_df = df[df.index == target_date]
            latest = historical_df.iloc[-1] if not historical_df.empty else df.iloc[-1]
        else:
            latest = df.iloc[-1]

        safe_get = _safe_getter(latest, f"build_signal_panel({asset})")

        # ---- Extract metrics ----
        comm_idx      = safe_get(const.COMMS_IDX, 50)
        lrg_idx       = safe_get(const.LRG_IDX, 50)
        sml_idx       = safe_get(const.SML_IDX, 50)
        comm_z        = safe_get(const.COMMS_ZSCORE, 0)
        lrg_z         = safe_get(const.LRG_ZSCORE, 0)
        sml_z         = safe_get(const.SML_ZSCORE, 0)
        comm_momentum = safe_get(const.COMM_MOMENTUM, 0)
        lrg_momentum  = safe_get(const.LRG_MOMENTUM, 0)
        sml_momentum  = safe_get(const.SML_MOMENTUM, 0)
        willco        = safe_get(const.WILLCO_ALIAS, 50)
        oi_z          = safe_get(const.OI_ZSCORE, 0)
        lrg_sentiment = safe_get(const.LW_LRG_SENTIMENT, 0)
        safe_get(const.LARGE_NET, 0) < 0
        safe_get(const.COMM_NET, 0) > 0
        macd_line = safe_get(const.COMM_MACD_LINE, 0.0)
        macd_signal = safe_get(const.COMM_MACD_SIGNAL, 0.0)
        macd_hist = safe_get(const.COMM_MACD_HIST, 0.0)
        macd_bull = bool(safe_get(const.COMM_MACD_BULL_CROSS, False))
        macd_bear = bool(safe_get(const.COMM_MACD_BEAR_CROSS, False))

        BULL_COLOR = color_palette[3]
        BEAR_COLOR = color_palette[0]
        NEUT_COLOR = vc.SOLARIZED_DARK_BASE00

        # ==================================================================
        # CARD: POSITIONING SETUP (COT Index)
        # ==================================================================
        setup_comms_only = get_indexer().is_equity(asset)
        bullish, bearish, close_bullish, close_bearish = model.setup_masks(
            comm_idx, lrg_idx, sml_idx, setup_comms_only
        )
        bull_signals, bear_signals, debug_signals, tooltips = _collect_active_signals(latest, include_accumulation=True)
        bearish or close_bearish or (bool(bear_signals) and not bool(bull_signals))

        # Text and threshold both come off the model that produced the verdict, so the
        # tooltip cannot describe one gate while the badge came from another.
        if bullish:
            pos_color, pos_text, pos_state = BULL_COLOR, "BULLISH EXTREME", const.SETUP_BULL
        elif close_bullish:
            pos_color, pos_text, pos_state = BULL_COLOR, "NEAR BULLISH", const.SETUP_NEAR_BULL
        elif bearish:
            pos_color, pos_text, pos_state = BEAR_COLOR, "BEARISH EXTREME", const.SETUP_BEAR
        elif close_bearish:
            pos_color, pos_text, pos_state = BEAR_COLOR, "NEAR BEARISH", const.SETUP_NEAR_BEAR
        else:
            pos_color, pos_text, pos_state = NEUT_COLOR, "NEUTRAL", const.SETUP_NONE
        pos_tooltip = vc.positioning_tooltip(pos_state, model, setup_comms_only)

        def _colored_span(value, bull_cond, bear_cond, fmt=".0f"):
            color = BULL_COLOR if bull_cond else (BEAR_COLOR if bear_cond else vc.BRIGHTER_TEXT_COLOR)
            return html.Span(f"{value:{fmt}}", style={'color': color})

        card_positioning = _make_signal_card(
            "POSITIONING", pos_text, pos_color,
            html.Small([
                "Index: ",
                _colored_span(comm_idx, comm_idx >= max_idx, comm_idx <= min_idx),
                ", ",
                _colored_span(lrg_idx, lrg_idx >= max_idx, lrg_idx <= min_idx),
                ", ",
                _colored_span(sml_idx, sml_idx >= max_idx, sml_idx <= min_idx),
            ], style={"color": vc.TEXT_COLOR}),
            pos_tooltip,
        )

        # ==================================================================
        # CARD: POSITIONING Z-SCORE
        # ==================================================================
        if comm_z >= const.ZSCORE_MAX_THRESHOLD and lrg_z <= const.ZSCORE_MIN_THRESHOLD and sml_z <= const.ZSCORE_MIN_THRESHOLD:
            comm_color, comm_text = BULL_COLOR, "BULLISH DEVIATION"
            comm_tooltip = "Commercials are at an extreme long deviation (Z-Score ≥ 2.0) while speculators are extremely short. Smart money is heavily positioned for a rally against a highly crowded public short trade."
        elif (comm_z >= const.ZSCORE_MODERATE_MAX_THRESHOLD and lrg_z <= const.ZSCORE_MODERATE_MIN_THRESHOLD and sml_z <= const.ZSCORE_MODERATE_MIN_THRESHOLD) or (comm_z >= const.ZSCORE_MAX_THRESHOLD and (lrg_z <= const.ZSCORE_MIN_THRESHOLD or sml_z <= const.ZSCORE_MIN_THRESHOLD)):
            comm_color, comm_text = BULL_COLOR, "NEAR BULLISH"
            comm_tooltip = "Commercials are at a moderate long deviation (Z-Score ≥ 1.0) while speculators are moderately short. Smart money is positioned for a potential rally."
        elif comm_z <= const.ZSCORE_MIN_THRESHOLD and lrg_z >= const.ZSCORE_MAX_THRESHOLD and sml_z >= const.ZSCORE_MAX_THRESHOLD:
            comm_color, comm_text = BEAR_COLOR, "BEARISH DEVIATION"
            comm_tooltip = "Commercials are at an extreme short deviation (Z-Score ≤ -2.0) while speculators are extremely long. Smart money is heavily positioned for a drop against a euphoric public long trade."
        elif (comm_z <= const.ZSCORE_MODERATE_MIN_THRESHOLD and lrg_z >= const.ZSCORE_MODERATE_MAX_THRESHOLD and sml_z >= const.ZSCORE_MODERATE_MAX_THRESHOLD) or (comm_z <= const.ZSCORE_MIN_THRESHOLD and (lrg_z >= const.ZSCORE_MAX_THRESHOLD or sml_z >= const.ZSCORE_MAX_THRESHOLD)):
            comm_color, comm_text = BEAR_COLOR, "NEAR BEARISH"
            comm_tooltip = "Commercials are at a moderate short deviation (Z-Score ≤ -1.0) while speculators are moderately long. Smart money is positioned for a potential drop."
        else:
            comm_color, comm_text = NEUT_COLOR, "NEUTRAL"
            comm_tooltip = "Positioning is not at concurrent extremes across all participant groups. A full structural deviation requires Commercials and Speculators to be at opposite Z-score extremes (±2.0)."

        card_zscore = _make_signal_card(
            "POSITIONING Z-SCORE", comm_text, comm_color,
            html.Small([
                "Z-Score: ",
                _colored_span(comm_z, comm_z >= const.ZSCORE_MAX_THRESHOLD, comm_z <= const.ZSCORE_MIN_THRESHOLD, fmt=".1f"),
                ", ",
                _colored_span(lrg_z, lrg_z >= const.ZSCORE_MAX_THRESHOLD, lrg_z <= const.ZSCORE_MIN_THRESHOLD, fmt=".1f"),
                ", ",
                _colored_span(sml_z, sml_z >= const.ZSCORE_MAX_THRESHOLD, sml_z <= const.ZSCORE_MIN_THRESHOLD, fmt=".1f"),
            ], style={"color": vc.TEXT_COLOR}),
            comm_tooltip,
        )

        # ==================================================================
        # CARD: COMM MOMENTUM
        # ==================================================================
        _mom_window = f"over the last {const.MOMENTUM_PERIOD} weekly reports"
        if comm_momentum >= const.MOMENTUM_MAX_THRESHOLD:
            mom_color, mom_text = BULL_COLOR, "AGGRESSIVE BUYING"
            mom_tooltip = f"The Commercial positioning index has climbed 40+ points {_mom_window}. 'Smart money' is aggressively accumulating longs or covering shorts, indicating strong conviction in a price floor or upcoming rally."
        elif comm_momentum <= const.MOMENTUM_MIN_THRESHOLD:
            mom_color, mom_text = BEAR_COLOR, "AGGRESSIVE SELLING"
            mom_tooltip = f"The Commercial positioning index has fallen 40+ points {_mom_window}. 'Smart money' is aggressively distributing longs or adding shorts, indicating strong conviction in a price ceiling or upcoming drop."
        else:
            mom_color, mom_text = NEUT_COLOR, "STABLE"
            mom_tooltip = f"The Commercial positioning index has held within 40 points {_mom_window}. No aggressive, sudden shifts in structural positioning detected."

        card_momentum = _make_signal_card(
            "COMM MOMENTUM", mom_text, mom_color,
            html.Small([
                f"{vc.MOMENTUM_LABEL}: ",
                _colored_span(comm_momentum, comm_momentum >= const.MOMENTUM_MAX_THRESHOLD, comm_momentum <= const.MOMENTUM_MIN_THRESHOLD),
                ", ",
                _colored_span(lrg_momentum, lrg_momentum >= const.MOMENTUM_MAX_THRESHOLD, lrg_momentum <= const.MOMENTUM_MIN_THRESHOLD),
                ", ",
                _colored_span(sml_momentum, sml_momentum >= const.MOMENTUM_MAX_THRESHOLD, sml_momentum <= const.MOMENTUM_MIN_THRESHOLD),
            ], style={"color": vc.TEXT_COLOR}),
            mom_tooltip,
        )

        # ==================================================================
        # CARD: ALGORITHMIC SETUP
        # ==================================================================
        if not bull_signals and not bear_signals and not debug_signals:
            algo_color = NEUT_COLOR
            algo_text  = "NO ACTIVE SETUP"
            tooltips.append("Waiting for algorithmic alignment between Price Action, Open Interest, and Commercial Positioning.")
        elif bull_signals:
            algo_color = BULL_COLOR
            algo_text  = " + ".join(bull_signals + debug_signals)
        elif debug_signals:
            algo_color = NEUT_COLOR
            algo_text  = " + ".join(debug_signals)
        else:
            algo_color = BEAR_COLOR
            algo_text  = " + ".join(bear_signals + debug_signals)

        tooltip_body = html.Div([html.Div(t, className="mb-2") for t in tooltips])

        card_algo = _make_signal_card(
            "ALGORITHMIC SETUP", algo_text, algo_color,
            html.Small("Based on OI & PA", className="text-muted"),
            tooltip_body,
        )

        # ==================================================================
        # CARD: WILLCO (conditional)
        # ==================================================================
        card_willco = None
        if pd.notna(willco):
            if willco >= const.WILLCO_MAX_THRESHOLD:
                w_color, w_text = BULL_COLOR, "ACCUMULATION"
                w_tooltip = "Commercials are aggressively accumulating physical assets (WILLCO ≥ 80). Smart money is taking massive long positions relative to total open interest, signaling a strong bullish setup."
            elif willco <= const.WILLCO_MIN_THRESHOLD:
                w_color, w_text = BEAR_COLOR, "DISTRIBUTION"
                w_tooltip = "Commercials are aggressively distributing physical assets (WILLCO ≤ 20). Smart money is heavily offloading inventory or hedging against price drops, signaling a strong bearish setup."
            else:
                w_color, w_text = NEUT_COLOR, "NEUTRAL"
                w_tooltip = "Commercial accumulation is within normal ranges. Smart money is neither aggressively hoarding nor dumping physical assets at current prices."

            card_willco = _make_signal_card(
                "WILLCO", w_text, w_color,
                html.Small([
                    "Value: ",
                    _colored_span(willco, willco >= const.WILLCO_MAX_THRESHOLD, willco <= const.WILLCO_MIN_THRESHOLD),
                ], style={"color": vc.TEXT_COLOR}),
                w_tooltip,
            )

        # ==================================================================
        # CARD: LARGE SPEC INDEX (Williams LATE Index)
        # ==================================================================
        if pd.notna(lrg_sentiment):
            if lrg_sentiment >= const.LW_LRG_SENTIMENT_MAX_THRESHOLD:
                ls_color, ls_text = BEAR_COLOR, "BEARISH EXTREME"
                ls_tooltip = (
                    "Williams LATE Index: Large speculators are heavily long (>=80%). "
                    "This indicates nearing the end of a market advance since they notoriously get it wrong at the extremes."
                )
            elif lrg_sentiment <= const.LW_LRG_SENTIMENT_MIN_THRESHOLD:
                ls_color, ls_text = BULL_COLOR, "BULLISH EXTREME"
                ls_tooltip = (
                    "Williams LATE Index: Large speculators are largely absent or net short (<=20%). "
                    "This indicates nearing the end of a market downturn since they notoriously get it wrong at the extremes."
                )
            else:
                ls_color, ls_text = NEUT_COLOR, "NEUTRAL"
                ls_tooltip = (
                    "Williams LATE Index is currently in the middle of its 15-week range. "
                    "Large speculator positioning is not at a crowded extreme."
                )

        card_large_spec = _make_signal_card(
            "LARGE SPEC INDEX", ls_text, ls_color,
            html.Small([
                "Index: ",
                html.Span(
                    f"{lrg_sentiment:.0f}",
                    style={'color': BEAR_COLOR if lrg_sentiment >= const.LW_LRG_SENTIMENT_MAX_THRESHOLD
                                   else BULL_COLOR if lrg_sentiment <= const.LW_LRG_SENTIMENT_MIN_THRESHOLD
                                   else vc.BRIGHTER_TEXT_COLOR}
                ),
            ], style={"color": vc.TEXT_COLOR}),
            ls_tooltip,
        )

        # Directional context for the OI card below. Shared with the tape synthesis,
        # which asks the same question and used to answer it with its own copy.
        price_trend_is_up = utils.price_trend_is_up(df, latest.name)

        # ==================================================================
        # CARD: OPEN INTEREST (Context-Aware Color Mapping)
        # ==================================================================
        if oi_z >= const.OI_ZSCORE_MAX_THRESHOLD:
            if price_trend_is_up:
                oi_color = BULL_COLOR  # Strong commercial buying trend
                oi_text = "EXTREME HIGH (BULL ACCUMULATION)"
                oi_tooltip = "Open Interest is abnormally high alongside rising prices. Massive new capital is aggressively driving the bull trend, but beware of a sudden crowded-trade unwind."
            else:
                oi_color = BEAR_COLOR  # Strong commercial shorting trend
                oi_text = "EXTREME HIGH (BEAR DISTRIBUTION)"
                oi_tooltip = "Open Interest is abnormally high alongside falling prices. Commercial shorts are aggressively pressing the market down, building extreme downside risk."

        elif oi_z >= const.OI_ZSCORE_ELEVATED_MAX_THRESHOLD:
            if price_trend_is_up:
                oi_color = NEUT_COLOR
                oi_text = "ELEVATED (BUYING INFLOWS)"
                oi_tooltip = "Open Interest is elevated alongside a rising price trend. New buying capital is steadily entering the market to support the upward move."
            else:
                oi_color = NEUT_COLOR
                oi_text = "ELEVATED (SHORT INFLOWS)"
                oi_tooltip = "Open Interest is elevated alongside a falling price trend. New short-sellers are steadily entering the market to defend the breakdown."

        elif oi_z <= const.OI_ZSCORE_MIN_THRESHOLD:
            if price_trend_is_up:
                oi_color = BEAR_COLOR  # Unsustainable short squeeze / lack of new buyers
                oi_text = "EXTREME LOW (SHORT EXHAUSTION)"
                oi_tooltip = "Open Interest has collapsed during a price rally. This indicates forced short-covering rather than organic buying fuel. The upward move is heavily exhausted."
            else:
                oi_color = BULL_COLOR  # Completely washed out, structural bottom
                oi_text = "EXTREME LOW (LONG FLUSH / CLEAN BOARD)"
                oi_tooltip = "Open Interest has collapsed following a price drop. Longs have been completely washed out via stop-losses, leaving the market clean and primed for a potential contrarian bottom."

        elif oi_z <= const.OI_ZSCORE_ELEVATED_MIN_THRESHOLD:
            if price_trend_is_up:
                oi_color = NEUT_COLOR
                oi_text = "DECLINING (SHORT COVERING)"
                oi_tooltip = "Open Interest is receding as price climbs. Capital is leaving the market; the rally is driven by shorts exiting positions rather than fresh buyers stepping in."
            else:
                oi_color = NEUT_COLOR
                oi_text = "DECLINING (LONG LIQUIDATION)"
                oi_tooltip = "Open Interest is receding as price falls. Weak-handed longs are actively de-risking and liquidating positions, structurally cleaning up overhead resistance."

        else:
            oi_color, oi_text = NEUT_COLOR, "AVERAGE"
            oi_tooltip = "Open Interest is fluctuating within normal historical ranges. No extreme structural tension or massive capital shifts detected."

        oi_is_neutral = (oi_text == "AVERAGE")

        card_oi = dbc.Card([
            dbc.CardBody([
                html.H6("OPEN INTEREST PROFILE", className="card-title text-muted mb-1", style={'fontSize': '0.75rem', 'fontWeight': 'bold'}),
                html.H6(oi_text, style={'color': oi_color, 'fontWeight': 'bold', 'margin': 0}),

                # Main Baseline Z-Score
                html.Small([
                    "OI Z-Score: ",
                    html.Span(f"{oi_z:.2f}", style={'color': oi_color if abs(oi_z) >= 1.0 else vc.BRIGHTER_TEXT_COLOR})
                ], style={"color": vc.TEXT_COLOR, "display": "block", "className": "mt-1"}),
            ], className="py-1 px-2 text-center"),

            # Bottom Explainer Division Block
            html.Div(
                oi_tooltip,
                style={
                    'backgroundColor': 'var(--card-accent-color)',
                    'borderTop': f'1px solid {oi_color}20',
                    'fontSize': '0.75rem',
                    'color': vc.TEXT_COLOR,
                    'borderRadius': '0 0 5px 5px'
                },
                className="py-1 px-2 text-center text-sm-start flex-grow-1 d-flex align-items-center"
            )
        ], style={
            'backgroundColor': 'var(--card-color-neutral)' if oi_is_neutral else 'var(--card-color-active)',
            'border': '1px solid var(--border-color-dim)' if oi_is_neutral else f'1px solid {oi_color}40',
            'opacity': 0.4 if oi_is_neutral else 1.0,
            'transition': 'opacity 0.3s ease',
        }, className="m-1 flex-fill d-flex flex-column")

        # ==================================================================
        # CARD: SPEARMAN REGIME SHIFT
        # ==================================================================
        regime_shift = latest.get(const.COMMS_SPEARMAN_REGIME_SHIFT, False)
        if regime_shift:
            if comm_momentum > 0:
                rs_color, rs_text = BULL_COLOR, "BULLISH ANOMALY"
                rs_tooltip = "Commercials' correlation with price has violently broken out of its traditional negative hedging regime. Smart money is exhibiting anomalous positive correlation by BUYING into rising prices, indicating a massive structural bull shift."
            else:
                rs_color, rs_text = BEAR_COLOR, "BEARISH ANOMALY"
                rs_tooltip = "Commercials' correlation with price has violently broken out of its traditional negative hedging regime. Smart money is exhibiting anomalous positive correlation by SELLING into falling prices, indicating a massive structural bear shift."
        else:
            rs_color, rs_text = NEUT_COLOR, "NORMAL"
            rs_tooltip = "Commercial correlation remains within its expected negative structural hedging regime. No statistical anomalies detected in smart money behavior."

        card_spearman = _make_signal_card(
            "SPEARMAN REGIME", rs_text, rs_color,
            html.Small("Correlation Shift", className="text-muted"),
            rs_tooltip,
        )

        def fmt_contracts(val):
            if val is None or pd.isna(val):
                return "N/A"
            abs_val = abs(val)
            sign = "-" if val < 0 else ""
            if abs_val >= 1_000_000:
                return f"{sign}{abs_val/1_000_000:.2f}M"
            if abs_val >= 1000:
                return f"{sign}{abs_val/1000:.1f}k"
            return f"{sign}{abs_val:.0f}"

        # ==================================================================
        # CARD: COT MACD
        # ==================================================================
        if macd_bull:
            macd_color, macd_text = BULL_COLOR, "BULLISH CROSSOVER"
            macd_tooltip = "Commercial MACD has generated a fresh Bullish Crossover (MACD crossed above the Signal Line). Smart money is accelerating accumulation at a rate of change that historically leads price turns."
        elif macd_bear:
            macd_color, macd_text = BEAR_COLOR, "BEARISH CROSSOVER"
            macd_tooltip = "Commercial MACD has generated a fresh Bearish Crossover (MACD crossed below the Signal Line). Smart money is accelerating distribution, presenting high structural risk to the trend."
        elif macd_hist > 0:
            macd_color, macd_text = BULL_COLOR, "BULLISH REGIME"
            macd_tooltip = "Commercial MACD is trending within a positive regime (MACD line > Signal line). Net buying pressure continues to support a constructive market structure."
        elif macd_hist < 0:
            macd_color, macd_text = BEAR_COLOR, "BEARISH REGIME"
            macd_tooltip = "Commercial MACD is trending within a negative regime (MACD line < Signal line). Net distribution pressure continues to dominate the structural outlook."
        else:
            macd_color, macd_text = NEUT_COLOR, "NEUTRAL"
            macd_tooltip = "Commercial MACD momentum is flat and overlapping with the Signal line, indicating lack of structural momentum or trend force."

        card_macd = _make_signal_card(
            "COT MACD", macd_text, macd_color,
            html.Small([
                "Line: ", html.Span(fmt_contracts(macd_line), style={'color': vc.BRIGHTER_TEXT_COLOR}),
                " | Sig: ", html.Span(fmt_contracts(macd_signal), style={'color': vc.BRIGHTER_TEXT_COLOR}),
                " | Hist: ", html.Span(fmt_contracts(macd_hist), style={'color': BULL_COLOR if macd_hist > 0 else BEAR_COLOR if macd_hist < 0 else vc.BRIGHTER_TEXT_COLOR})
            ], style={"color": vc.TEXT_COLOR}),
            macd_tooltip,
        )

        # ==================================================================
        # Assemble card list
        # ==================================================================
        cards = [card_positioning, card_algo, card_momentum]
        if card_willco is not None:
            cards.append(card_willco)
        cards.extend([
            card_large_spec,
            card_oi,
            card_spearman,
            card_macd,
            card_zscore,
        ])

        cols = [
            dbc.Col(card, xs=12, sm=6, md=6, lg=4, xl=3, className="d-flex mb-3")
            for card in cards
        ]

        layout = dbc.Row(cols, className="g-1 mb-2")

        # Inject Capitulation Alert Banner
        is_bull_capitulation = bool(latest.get(const.FLAG_BULL_CAPITULATION, False))
        is_bear_capitulation = bool(latest.get(const.FLAG_BEAR_CAPITULATION, False))

        if is_bull_capitulation or is_bear_capitulation:
            banner_color = '#00FF00' if is_bull_capitulation else '#FF0000'
            banner_title = "⚠️ BULLISH CAPITULATION BLOW-OFF DETECTED" if is_bull_capitulation else "⚠️ BEARISH CAPITULATION BLOW-OFF DETECTED"
            banner_desc = (
                "Extreme geometric price rejection confirmed alongside surging Open Interest velocity and speculative crowding. "
                "Institutional absorption floor is active. High probability of violent short squeeze."
                if is_bull_capitulation else
                "Extreme geometric price rejection confirmed alongside surging Open Interest velocity and speculative crowding. "
                "Institutional distribution ceiling is active. High probability of violent downside reversal."
            )
            r, g, b = (0, 255, 0) if is_bull_capitulation else (255, 0, 0)

            alert_banner = html.Div([
                html.H4(banner_title, style={'color': banner_color, 'fontWeight': 'bold'}),
                html.P(banner_desc)
            ], style={
                'backgroundColor': f'rgba({r}, {g}, {b}, 0.1)',
                'border': f'2px solid {banner_color}',
                'padding': '15px',
                'marginBottom': '20px',
                'textAlign': 'center',
                'borderRadius': '5px'
            })
            return html.Div([alert_banner, layout])

        return layout

    except Exception as e:
        print(f"Error building signal panel: {e}")
        return html.Div()


def build_mobile_asset_card(df, asset, color_palette, lookback,
                            model=None, is_equity=False, filter_types=[]):
    """One screener card: the SAME card the setups strip draws, plus a footer.

    This used to be its own layout -- a two-column table of nine readings under a
    tape-bias badge, with an "Analyze Charts" button on the bottom. The two halves of
    the home page therefore said the same things in two vocabularies: an "Index:
    16/83/57" row here against a lollipop strip above, a border tinted by tape bias
    here against a badge tinted by setup state above, and a market name that linked
    from a button here and from the whole card above. Nothing about a market changes
    between the top of the page and the bottom, so nothing about its card should
    either.

    It now assembles a board-row-shaped dict off the frame and hands it to
    `positioning_card`. Three consequences worth knowing:

    * The setup verdict comes from `model.setup_state_from`, the same call
      `get_board` makes, so a market cannot be badged SETUP in the strip above and
      show a bare card down here. It used to derive its own via `setup_masks`, which
      is exactly the duplication that let the two disagree.
    * Max Pain Pull and OI Z-Score are gone. Neither bears on a positioning setup,
      and the max-pain read they needed was the only reason this function touched the
      options store at all -- so the card no longer opens it.
    * Tape bias moved from the card's border into the first badge. On this card it is
      one signal among several, not the headline; the headline is the setup state,
      top right, the way it is everywhere else on the page now.
    """
    model = model if isinstance(model, models.PositioningModel) else models.resolve(model)

    if df is None or df.empty:
        return None

    latest = df.iloc[-1]
    safe_get = _safe_getter(latest, f"build_mobile_asset_card({asset})")

    comm_momentum = safe_get(const.COMM_MOMENTUM, 0)
    lrg_momentum  = safe_get(const.LRG_MOMENTUM, 0)
    sml_momentum  = safe_get(const.SML_MOMENTUM, 0)
    willco        = safe_get(const.WILLCO_ALIAS, 50)
    lrg_sentiment = safe_get(const.LW_LRG_SENTIMENT, None)

    instrument = get_indexer().get_instrument_from_name(asset)
    symbol_str = instrument.symbol if instrument else asset

    synthesis = generate_exhaustive_tape_synthesis(latest, symbol_str, df=df)
    tape_bias = synthesis.get("tape_bias", "neutral").upper()

    if "TAPE_BIAS_BULL" in filter_types and "TAPE_BIAS_BEAR" in filter_types:
        if tape_bias.lower() not in ("bullish", "bearish"):
            return None
    elif "TAPE_BIAS_BULL" in filter_types:
        if tape_bias.lower() != "bullish":
            return None
    elif "TAPE_BIAS_BEAR" in filter_types:
        if tape_bias.lower() != "bearish":
            return None

    BULL_COLOR = color_palette[3]
    BEAR_COLOR = color_palette[0]
    if BEAR_COLOR.lower() in ("#f87171", "#dc322f", "#ff453a", "#e70307", "#ff007f"):
        BEAR_COLOR = "#FF4D4D"

    # The board row this card renders through. `_leg` mirrors cotmetrics.movers so a
    # frame read here and a frame read there produce the same fields; the WoW aliases
    # are the ones get_board uses, so the delta gutter means the same thing on both
    # halves of the page.
    def _num(value):
        return None if value is None or pd.isna(value) else round(float(value))

    comm_col, lrg_col, sml_col = model.leg_columns(lookback)
    row = {
        "asset": asset,
        "index": _num(latest.get(comm_col)),
        "lrg_index": _num(latest.get(lrg_col)),
        "sml_index": _num(latest.get(sml_col)),
        "delta": _num(latest.get(const.COMM_WOW)),
        "lrg_delta": _num(latest.get(const.LRG_WOW)),
        "sml_delta": _num(latest.get(const.SML_WOW)),
        # The SAME call get_board makes. Deriving it here with setup_masks is what let
        # this card and the strip above it disagree about a market.
        "setup": model.setup_state_from(latest, lookback, is_equity),
        # Same reason as `setup` above: the strip and this card must not compute a
        # market's age two ways. One call, on the model that owns the gate.
        "setup_weeks": model.setup_age_from(df, lookback, is_equity),
        "is_equity": is_equity,
    }
    if row["index"] is None:
        return None

    # ---- the fired signals ----
    active_bull, active_bear = [], []
    _bull, _bear, _debug, _ = _collect_active_signals(latest, include_accumulation=False)
    active_bull.extend(_bull)
    active_bear.extend(_bear)

    # Spearman rides as a badge rather than as three coefficients: the fired regime
    # shift is the part anyone acts on.
    if latest.get(const.COMMS_SPEARMAN_REGIME_SHIFT, False):
        (active_bull if comm_momentum > 0 else active_bear).append(
            "SPEARMAN BULL" if comm_momentum > 0 else "SPEARMAN BEAR")

    def _chip(label, colour):
        return html.Span(label, style={
            "fontSize": "0.55rem", "whiteSpace": "nowrap", "fontWeight": "normal",
            "backgroundColor": f"{colour}15", "color": colour,
            "border": f"1px solid {colour}40", "borderRadius": "3px",
            "padding": "1px 4px"})

    badges = []
    if tape_bias in ("BULLISH", "BEARISH"):
        badges.append(_chip(
            f"{tape_bias} TAPE",
            BULL_COLOR if tape_bias == "BULLISH" else BEAR_COLOR))
    badges += [_chip(x, BULL_COLOR) for x in active_bull]
    badges += [_chip(x, BEAR_COLOR) for x in active_bear]

    # ---- the footer: what this card knows that the strip above it does not ----
    # WillCo, then LW Sentiment, then Movement, which is their order of usefulness.
    # Movement is NOT the delta gutter restated: that is the one-week change in the
    # index, this is the six-week momentum of the underlying position.
    def _lit(value, bull_cond, bear_cond, fmt=".0f"):
        colour = (BULL_COLOR if bull_cond else
                  BEAR_COLOR if bear_cond else vc.BRIGHTER_TEXT_COLOR)
        return html.Span(f"{value:{fmt}}", style={"color": colour,
                                                  "fontWeight": "bold"})

    sep = html.Span(" · ", style={"opacity": 0.45})
    footer = [
        html.Span("WillCo ", title="Larry Williams Commercial proxy index. How fully "
                                   "deployed Commercials are against total open interest.",
                  style={"cursor": "help"}),
        _lit(willco, willco >= const.WILLCO_MAX_THRESHOLD,
             willco <= const.WILLCO_MIN_THRESHOLD),
        sep,
        html.Span("LW ", title="Larry Williams Large Speculator Sentiment Index "
                               "(15-week). A contrarian reading.",
                  style={"cursor": "help"}),
        (_lit(lrg_sentiment,
              lrg_sentiment <= const.LW_LRG_SENTIMENT_MIN_THRESHOLD,
              lrg_sentiment >= const.LW_LRG_SENTIMENT_MAX_THRESHOLD)
         if pd.notna(lrg_sentiment)
         else html.Span("\u2013", style={"opacity": 0.6})),
        html.Br(),
        html.Span("Move ", title="Six-week momentum of positioning, Comm / Large / "
                                 "Small. Not the one-week index change beside the "
                                 "strip above.",
                  style={"cursor": "help"}),
        _lit(comm_momentum, comm_momentum >= const.MOMENTUM_MAX_THRESHOLD,
             comm_momentum <= const.MOMENTUM_MIN_THRESHOLD),
        html.Span("/", style={"opacity": 0.45}),
        _lit(lrg_momentum, lrg_momentum >= const.MOMENTUM_MAX_THRESHOLD,
             lrg_momentum <= const.MOMENTUM_MIN_THRESHOLD),
        html.Span("/", style={"opacity": 0.45}),
        _lit(sml_momentum, sml_momentum >= const.MOMENTUM_MAX_THRESHOLD,
             sml_momentum <= const.MOMENTUM_MIN_THRESHOLD),
    ]

    return positioning_card(row, model, color_palette, weight="screener",
                            subtitle=symbol_str, footer=footer, badges=badges or None)


def build_accordion_title(ac, rows):
    """One accordion header: the class name, plus what is worth opening it for.

    A closed accordion used to say only "Currencies Markets", so the only way to learn
    whether a class held anything was to open it. On the board this was written against,
    five of the nine classes held no setup at all under NPF, which made most of those
    clicks wasted. The tally makes the whole list scannable while closed, which is the
    thing an accordion is supposed to do.

    Counts come from board rows that have already been through the tape-bias filter, so
    they describe the same population the body below will render.
    """
    mine = [r for r in rows if r["asset_class"] == ac]
    full = sum(1 for r in mine if r["setup"] in const.SETUP_FULL_STATES)
    near = sum(1 for r in mine if r["setup"] in const.SETUP_NEAR_STATES)

    if full or near:
        parts = []
        if full:
            parts.append(f"{full} at gate")
        if near:
            parts.append(f"{near} near")
        tally, weight, colour = " · ".join(parts), "600", vc.BRIGHTER_TEXT_COLOR
    elif not mine:
        # A tape-bias filter can empty a whole class. "nothing active · 0 markets" was
        # both ungrammatical and misleading there -- it reads as a quiet class rather
        # than one the filter removed entirely.
        tally, weight, colour = "nothing to show", "400", vc.TEXT_COLOR
    else:
        # Says "quiet", not "empty": the class still has markets to browse, there is
        # just nothing in it the gate has flagged.
        plural = "" if len(mine) == 1 else "s"
        tally, weight, colour = (f"nothing active · {len(mine)} market{plural}",
                                 "400", vc.TEXT_COLOR)

    return [
        html.Span(f"{ac} Markets", style={"fontWeight": "600"}),
        html.Span(tally, style={"fontSize": "0.72rem", "fontWeight": weight,
                                "color": colour, "marginLeft": "10px",
                                # Quiet classes read dimmer than active ones without
                                # being hidden, so the eye skips them rather than
                                # having to read every row.
                                "opacity": 1.0 if (full or near) else 0.6}),
    ]


def build_accordion_skeleton(asset_classes):
    accordion_items = []
    asset_list = (asset_classes,) if isinstance(asset_classes, str) else tuple(asset_classes)

    for ac in asset_list:
        accordion_items.append(
            dbc.AccordionItem(
                html.Div(
                    dcc.Loading(
                        html.Div(id={"type": "accordion-body", "index": ac}),
                        type="default",
                        color=vc.BRIGHTER_TEXT_COLOR,
                    )
                ),
                # The title is filled in by the board callback once the sweep lands.
                # This is what shows for the moment before that, so it is the plain name
                # rather than a tally that would briefly claim a count of zero.
                title=f"{ac} Markets",
                id={"type": "accordion-item", "index": ac},
                item_id=ac,
                style={"backgroundColor": "rgba(20,20,20,0.5)", "border": "1px solid rgba(255,255,255,0.05)"}
            )
        )

    return accordion_items


def build_asset_class_cards(cot_indexer, ac, lookback, color_palette, model=None, filter_types=[]):
    model = model if isinstance(model, models.PositioningModel) else models.resolve(model)

    instruments = cot_indexer.get_assets_for_asset_class(ac)
    ac_cards = []
    for name in instruments:
        df = cot_indexer.get_symbols_data(name, lookback, model.basis)
        is_equity = cot_indexer.is_equity(name)
        # The asset NAME, explicitly. This used to compute a `symbol` here and pass
        # that instead, and it only ever worked by falling through its own ternary:
        # `instruments` is not keyed by the exchange code, so `code in instruments`
        # was False for every market and `symbol` resolved to `name` anyway. The card
        # builds its OI Alignment link out of this value and looks the exchange code
        # up for itself, so a day when that lookup started succeeding would have sent
        # every card on the page to /oi_alignment?asset=None.
        card = build_mobile_asset_card(
            df, name, color_palette, lookback, model=model,
            is_equity=is_equity, filter_types=filter_types
        )
        if card is not None:
            ac_cards.append(card)

    if not ac_cards:
        # A card is only ever withheld by the tape-bias filter -- setup state does not
        # gate this list, every market in the class renders otherwise. The old copy here
        # said "No active commercial setup signals", which named a rule this function
        # does not apply and now also contradicts the setup tally on the header above.
        empty_msg = "No markets in this class to show."
        if "TAPE_BIAS_BULL" in filter_types and "TAPE_BIAS_BEAR" in filter_types:
            empty_msg = "No assets with an active Bullish or Bearish Tape Bias."
        elif "TAPE_BIAS_BULL" in filter_types:
            empty_msg = "No assets with an active Bullish Tape Bias."
        elif "TAPE_BIAS_BEAR" in filter_types:
            empty_msg = "No assets with an active Bearish Tape Bias."

        return html.Div(
            html.P(empty_msg, style={'textAlign': 'center', 'color': vc.TEXT_COLOR, 'marginTop': '10px'}),
            className="p-3"
        )

    # The same balanced grid the setups strip uses, at the screener's own widths.
    # Two things came out of sharing it. The cards are wider here (four across at xl,
    # not six) because they carry a footer and a badge row the strip's do not, and at
    # six the name ellipsised to "Soybean ... (ZM)" -- the exchange code surviving
    # while the word identifying the market was cut. And a five-market class now lays
    # out 3 + 2 rather than 4 + 1, which is the offcut the strip above was fixed for;
    # there is no reason the same class of market should read as a ragged list down
    # here and as a group up there.
    return card_grid(ac_cards, MAX_PER_ROW["screener"])


def _strip_hover(row, model):
    """The exact readings the gate strip draws, for its hover.

    The strip is a position, not a number, so dropping the leg text only works if the
    numbers stay one hover away. This is the one place Commercials and the spec legs
    are printed together, which is why it keeps the "Comm" prefix the card's headline
    number also carries rather than leading with a bare figure.
    """
    def _with_move(label, value, delta):
        if delta is None:
            return f"{label} {value}"
        return f"{label} {value} ({'no change' if delta == 0 else f'{delta:+d}'})"

    parts = [_with_move("Comm", row["index"], row.get("delta"))]
    if row["is_equity"]:
        parts.append("specs not gated")
    else:
        for leg, short, key, dkey in (
                (models.LEG_LARGE, "Large", "lrg_index", "lrg_delta"),
                (models.LEG_SMALL, "Small", "sml_index", "sml_delta")):
            if leg in model.spec_legs and row[key] is not None:
                parts.append(_with_move(short, row[key], row.get(dkey)))
    return " · ".join(parts) + " this week"


# ── the gate strip ────────────────────────────────────────────────────────────
# The /strip chart's row, shrunk onto a card and then given one LANE PER LEG rather
# than the single lane it has there. /strip can afford one lane because it is 42 rows
# tall and a reader compares DOWN the column; a card is read on its own, and the
# question it has to answer is not "where are Commercials" but "where is the whole
# gate", which is Commercials plus whichever speculator legs this model reads. So the
# lane count is the gate's own notation: three lanes under Raw PF's CLS gate, two
# under NPF's CS, and one for an equity index contract, whose setup reads Commercials
# alone under either model.
#
# Colour is the LEG, not the verdict, which is the one place this departs from /strip
# and is a deliberate reversal of that page's rule. /strip colours its lollipop by the
# row's setup state because a lone lane has no other way to say it, and the page has
# 42 rows in which one convention has to hold. A card says its verdict twice already,
# in the badge and in the border down its left edge, so spending colour on it a third
# time buys nothing -- while three lanes with no colour distinction cannot be told
# apart at all. The slots are the app's own (plot_traces draws Commercials from 0,
# Large Specs from 1 and Small Traders from 2 on every stacked panel), so a reader
# arriving from the Graphs or OI Alignment pages already knows which is which.
#
# Plain divs, not SVG and emphatically not Plotly. Thirteen dcc.Graphs on the home
# page would each drag in a plotly instance for thirty pixels of picture; the marks
# here are absolutely-positioned rectangles. Percentage lefts also mean the strip
# rescales with the card at every breakpoint with no measurement, which the SVG
# version could not do without either distorting the dots into ellipses
# (preserveAspectRatio="none") or giving up edge padding.
LANE_PX = 9            # one leg's lane, dot included
LANE_GAP = 3
# /strip uses 0.09 over 700px of row. On a card the axis is ~150px, which needed more
# alpha to resolve as a band at all -- but the zone is now as tall as the whole strip
# rather than one 8px lane, so the area went up with the lane count and the alpha comes
# back down. Calibrated on screen at two and three lanes, not derived.
_ZONE_ALPHA = 0.11
_DOT_PX = 7
_COMM_DOT_PX = 9       # Commercials are the gated leg; the others are context for it


def _abs(**kw):
    return {"position": "absolute", **kw}


def strip_legs(row, model):
    """The legs a gate strip draws, top to bottom.

    Each entry is `(palette slot, index value, week-over-week delta, is_commercial)`.
    The delta rides along here rather than being looked up beside the strip so that
    the gutter of numbers and the lanes they annotate are built from ONE list: any
    other arrangement lets a card grow a lane the gutter has no row for, or print a
    delta against the wrong leg, and both failures look plausible.

    Commercials first and always: every gate in the app reads them. The speculator
    legs are exactly `model.spec_legs`, so an NPF card has no Large Spec lane because
    NPF's CS gate never reads that leg, and an equity index card has none at all
    because those gate on Commercials alone. Drawing a lane the gate does not read
    would put a condition on the card that the verdict above it never checked, which
    is the same rule `_strip_hover` and the /strip figure already follow.
    """
    from components.strip_traces import LEG_PALETTE_SLOT

    lanes = [(LEG_PALETTE_SLOT["comm"], row["index"], row.get("delta"), True)]
    if not row["is_equity"]:
        for leg, key, dkey in ((models.LEG_LARGE, "lrg_index", "lrg_delta"),
                               (models.LEG_SMALL, "sml_index", "sml_delta")):
            if leg in model.spec_legs and row[key] is not None:
                lanes.append((LEG_PALETTE_SLOT[leg], row[key], row.get(dkey), False))
    return lanes


# Whether the Commercial lane takes the app's leg colour (palette slot 0) like the
# speculator lanes, or the row's verdict colour.
#
# Slot 0 was tried first and is wrong for a reason only visible on screen: slot 0 IS
# the bear red. So Russell, a BULLISH setup with a green badge and a green border,
# drew a red dot sitting inside the green bull zone, and every bull setup on the board
# did the same. Three signals said bull and the loudest mark on the card said bear.
#
# The verdict colour is also the more honest of the two. Commercials are the leg every
# gate actually reads, so their mark is the one entitled to carry the verdict, and it
# keeps /strip's rule (position is the level, colour is the verdict) for the mark that
# rule was written about. The speculator lanes keep their identity colours, which is
# what the three lanes needed to be told apart in the first place -- so both things
# the palette was wanted for still hold. Flip this to True to see the alternative.
COMM_LANE_TAKES_LEG_COLOUR = False


# Whether the speculator lanes get a stem back to neutral as well as a mark. On, but
# at a HAIRLINE against the Commercial stem's 2px -- #60A5FA for Large Specs and
# #FBBF24 for Small Traders, the app's slot 1 and slot 2.
#
# /strip draws its bar for Commercials only, and copying that exactly left the spec
# lanes as a bare tick on an empty track: it says where the leg is and takes away the
# thing the lollipop was wanted for, which is reading how far from neutral a leg got
# without stopping to measure it. Restoring the stem at half the width keeps that
# reading and still ranks the lanes, because the Commercial lollipop remains the
# heaviest mark in the picture by both stem weight and head shape. The ink worry that
# turned these off is answered by the width rather than by the absence.
SPEC_LEGS_GET_STEMS = True
_SPEC_STEM_PX = 1

# The stem, restored from /strip. A bare dot says WHERE a leg is; the lollipop says
# how far from neutral it got and which way it went, which is the quantity the gate is
# actually about. It costs almost nothing on a card because the run is short and the
# alpha is low, and it does one thing a dot cannot: with several lanes stacked, the
# stems make the card readable as a shape rather than as three positions to be located
# and then compared. A market with everything pushed one way and a market with its legs
# opposed are the two cases that matter, and they now differ at a glance.
# Fainter than strip_traces.STEM_ALPHA's 0.55, which is the right number THERE and
# was too much here. /strip spends that alpha on one stem per row across 42 thin rows,
# where the stems never sit near each other; a card stacks two or three of them inside
# 20px, so the same alpha lands as a block of colour rather than as separate
# measurements. The heads and ticks are unchanged and still read at full strength --
# it is the runs of pixels that had to come down, which is the same argument
# strip_traces makes for knocking its own stem back below its head.
_STEM_ALPHA = 0.38
_SPEC_STEM_ALPHA = 0.26   # a hairline supporting a tick, under a 2px stem and a head
_STEM_PX = 2


def gate_strip(row, model, palette, colour=None, lane_px=LANE_PX, gap=LANE_GAP,
               dot_px=None, stem_px=_STEM_PX):
    """The card's 0-100 gate picture: gate zones behind one lollipop per gated leg.

    `colour` is the row's verdict colour, passed in rather than re-derived so the
    Commercial dot cannot disagree with the badge above it about which way the setup
    goes. Ignored when COMM_LANE_TAKES_LEG_COLOUR is on.

    `dot_px` shrinks every mark for the approaching tier, which draws the same strip
    at reduced weight rather than a different one. `stem_px` of 0 drops the stems and
    leaves bare dots.
    """
    from components.plot_colors import hex_to_rgba

    lanes = strip_legs(row, model)
    height = len(lanes) * lane_px + max(len(lanes) - 1, 0) * gap
    bull, bear = palette[3], palette[0]

    # Zones and the neutral rule run the full height, behind every lane. Painted once
    # rather than per lane so the gate reads as one region a leg is inside or outside
    # of, which is the thing the card is actually asking about.
    marks = [
        html.Div(style=_abs(left=0, width=f"{model.low}%", top=0, bottom=0,
                            backgroundColor=hex_to_rgba(bear, _ZONE_ALPHA),
                            borderRadius="2px")),
        html.Div(style=_abs(left=f"{model.high}%", right=0, top=0, bottom=0,
                            backgroundColor=hex_to_rgba(bull, _ZONE_ALPHA),
                            borderRadius="2px")),
        # NOT vc.GRID_COLOR. That is SOLARIZED_DARK_BASE03, a near-black that /strip
        # draws against a plot background several shades lighter than a card; on the
        # card it was invisible, which left every dot measured from nothing.
        html.Div(style=_abs(left="50%", top=0, bottom=0, width="1px",
                            backgroundColor="rgba(255,255,255,0.22)")),
    ]

    for i, (slot, value, _delta, is_comm) in enumerate(lanes):
        if is_comm and colour and not COMM_LANE_TAKES_LEG_COLOUR:
            dot_colour = colour
        else:
            dot_colour = palette[slot]
        size = dot_px or (_COMM_DOT_PX if is_comm else _DOT_PX)
        mid = i * (lane_px + gap) + lane_px / 2
        value = max(0, min(100, value))
        draw_stem = stem_px and (is_comm or SPEC_LEGS_GET_STEMS)
        marks.append(html.Div(style=_abs(
            left=0, right=0, top=f"{mid - 0.5:.1f}px", height="1px",
            backgroundColor="rgba(255,255,255,0.07)")))
        # The stem, from the neutral rule out to the reading. Knocked back from the
        # dot for the reason /strip knocks its own back: the dot is the datum and the
        # stem is context for it, and a run of pixels at full strength reads as glare
        # where a single dot does not.
        if draw_stem and abs(value - const.INDEX_NEUTRAL) > 0.5:
            run = stem_px if is_comm else min(_SPEC_STEM_PX, stem_px)
            run_alpha = _STEM_ALPHA if is_comm else _SPEC_STEM_ALPHA
            marks.append(html.Div(style=_abs(
                left=f"{min(value, const.INDEX_NEUTRAL)}%",
                width=f"{abs(value - const.INDEX_NEUTRAL)}%",
                top=f"{mid - run / 2:.1f}px", height=f"{run}px",
                backgroundColor=hex_to_rgba(dot_colour, run_alpha),
                borderRadius="1px")))
        if is_comm:
            # The lollipop head: a filled circle at the end of its stem.
            marks.append(html.Div(style=_abs(
                left=f"{value}%", transform="translateX(-50%)",
                top=f"{mid - size / 2:.1f}px",
                width=f"{size}px", height=f"{size}px", borderRadius="50%",
                backgroundColor=dot_colour,
                # A hairline ring, so a head sitting on the neutral rule or on the
                # edge of a zone still separates from it.
                boxShadow="0 0 0 1px rgba(0,0,0,0.45)")))
        else:
            # A TICK, not a dot, and this is the whole answer to why the Commercial
            # lane may be verdict-coloured while these are not.
            #
            # All three lanes were the same filled dot for a while, which left colour
            # carrying two different variables in one 20px picture: leg identity on
            # the speculator lanes and the verdict on the Commercial one. A reader who
            # learned "amber is Small Traders" would reasonably read "green is
            # Commercials", and then meet a red Commercial dot on the next card.
            #
            # /strip had already solved this and the fix was to stop ignoring it. Its
            # speculator legs are `line-ns` ticks against a lollipop head, and the
            # reason its comment gives is exactly this one: "a dot would read as a
            # second measure". Shape says these are different KINDS of mark, so colour
            # is free to mean a different thing on each without ambiguity. The head is
            # the gated leg and carries the verdict; a tick marks where another leg
            # sits, and its colour says which leg.
            tick_h = lane_px + 2
            marks.append(html.Div(style=_abs(
                left=f"{value}%", transform="translateX(-50%)",
                top=f"{mid - tick_h / 2:.1f}px",
                width="3px", height=f"{tick_h}px", borderRadius="1px",
                backgroundColor=dot_colour,
                boxShadow="0 0 0 1px rgba(0,0,0,0.45)")))

    return html.Div(marks, style={"position": "relative", "height": f"{height}px"})


def index_triplet(row, model, size="0.85rem"):
    """The positioning index for all three legs: Comm / Large / Small.

    ALL THREE, whichever legs the model gates on, because this is the precise readout
    the strip below it cannot give -- position says roughly 100, only a number says
    100 -- and a reader comparing two cards wants the same three slots in the same
    order on both. It is the format `build_mobile_asset_card` already prints on the
    screener cards, so the two agree.

    The GATED legs are lit and the rest are muted, which is also that card's rule. The
    distinction matters here because the strip directly below draws a lane only for
    the gated legs, so without it a card would show three numbers over two lanes with
    nothing saying why. Muting is as far as it goes: a bare index value is a reading,
    not a claim that the gate consulted it, which is the line viz_constants' setup
    copy draws and the reason equity cards may print speculator numbers at all while
    never asserting anything about them.
    """
    gated = {
        "comm": True,
        models.LEG_LARGE: (not row["is_equity"]
                           and models.LEG_LARGE in model.spec_legs),
        models.LEG_SMALL: (not row["is_equity"]
                           and models.LEG_SMALL in model.spec_legs),
    }
    values = (("comm", row["index"]),
              (models.LEG_LARGE, row.get("lrg_index")),
              (models.LEG_SMALL, row.get("sml_index")))

    parts = []
    for i, (leg, value) in enumerate(values):
        if i:
            parts.append(html.Span("/", style={"color": vc.TEXT_COLOR, "opacity": 0.4,
                                               "margin": "0 2px"}))
        lit = gated[leg]
        parts.append(html.Span(
            "\u2013" if value is None else f"{value}",
            style={"color": vc.BRIGHTER_TEXT_COLOR if lit else vc.TEXT_COLOR,
                   "fontWeight": "bold" if lit else "normal",
                   "opacity": 1.0 if lit else 0.7}))

    reads = "Commercials alone" if row["is_equity"] else _gate_leg_names(model)
    return html.Span(
        parts,
        title=(f"0-100 positioning index: Commercials / Large Specs / Small Traders. "
               f"{model.title} gates on {reads}; the other legs are shown but not lit."),
        style={"fontSize": size, "whiteSpace": "nowrap",
               "fontVariantNumeric": "tabular-nums", "cursor": "help"},
    )


def _gate_leg_names(model):
    """"Commercials and Small Traders", for the triplet's hover."""
    names = ["Commercials"] + [LEG_HOVER_NAMES[leg] for leg in model.spec_legs]
    return " and ".join(names) if len(names) < 3 else \
        ", ".join(names[:-1]) + " and " + names[-1]


LEG_HOVER_NAMES = {
    models.LEG_LARGE: "Large Specs",
    models.LEG_SMALL: "Small Traders",
}


# The delta column that sits beside the strip. Wide enough for "-12" and no wider:
# every pixel here is taken off the 0-100 axis, which is the thing being measured.
GUTTER_PX = 26


def gate_strip_row(row, model, palette, colour=None, lane_px=LANE_PX, gap=LANE_GAP,
                   dot_px=None, stem_px=_STEM_PX, size="0.58rem"):
    """The gate strip with each leg's week-over-week move beside its own lane.

    The card used to carry ONE delta, on the "Comm 100/100" line, and it was
    necessarily the Commercial one -- so a card could show Small Traders sitting at
    100 with no hint of whether they arrived this week or had been there a year. Now
    every lane the strip draws gets its own number on the same row, which is the
    reading the single delta was standing in for.

    A dash, not a blank, where there is no reading. `get_board` now distinguishes a
    genuine zero from a missing one, so a blank would be throwing that away again --
    and 0 next to a market pinned at an extreme is the interesting case, not the
    absent one.
    """
    lanes = strip_legs(row, model)
    height = len(lanes) * lane_px + max(len(lanes) - 1, 0) * gap

    def _fmt(d):
        if d is None:
            return "\u2013"       # en dash: no reading at all
        return "0" if d == 0 else f"{d:+d}"

    gutter = []
    for i, (_slot, _value, delta, _is_comm) in enumerate(lanes):
        mid = i * (lane_px + gap) + lane_px / 2
        gutter.append(html.Div(
            _fmt(delta),
            style=_abs(left=0, right=0, top=f"{mid - 6:.1f}px",
                       fontSize=size, lineHeight="12px", textAlign="right",
                       color=vc.TEXT_COLOR,
                       # Tabular figures, so a column of "+3" over "-12" lines up on
                       # the digits rather than drifting with glyph width.
                       fontVariantNumeric="tabular-nums",
                       opacity=1.0 if delta else 0.55,
                       whiteSpace="nowrap")))

    return html.Div([
        html.Div(gate_strip(row, model, palette, colour=colour, lane_px=lane_px,
                            gap=gap, dot_px=dot_px, stem_px=stem_px),
                 style={"flex": "1 1 auto", "minWidth": 0}),
        html.Div(gutter, style={"flex": "0 0 auto", "width": f"{GUTTER_PX}px",
                                "position": "relative", "height": f"{height}px"}),
    ], style={"display": "flex", "alignItems": "flex-start", "gap": "7px"})


# Which setup states are the long side. Both tiers of it, so a NEAR bull groups with
# the bulls rather than with whatever it is near.
_BULL_STATES = (const.SETUP_BULL, const.SETUP_NEAR_BULL)

# The most cards a row may hold, per view, per breakpoint. The approaching tier packs
# tighter than the featured one everywhere it can; it matches only at xl, where six
# across is already as narrow as a column can get and still hold a market name. The
# screener is widest of the three because its cards carry a footer and a badge row.
MAX_PER_ROW = {
    "featured": dict(xs=1, sm=2, md=4, lg=4, xl=6),
    "near":     dict(xs=2, sm=3, md=4, lg=6, xl=6),
    "screener": dict(xs=1, sm=2, md=2, lg=3, xl=4),
}


def balanced_columns(n, most):
    """Cards per row that fills the fewest rows, then spreads them evenly.

    Nine cards in rows of at most six is 6 + 3, which reads as a full row and an
    offcut rather than as one group -- and the eye takes the ragged second row for a
    separate section. Two rows are needed either way, so they may as well be 5 + 4.

    Fewest rows first, evenness second: 13 cards at six across goes to three rows of
    five rather than four rows of four, because dropping a card per row to buy a whole
    extra row of vertical space is not a trade these panels want.
    """
    if n <= 0:
        return 1
    rows = -(-n // most)                 # ceil, without importing math
    return -(-n // rows)


def card_grid(cards, most):
    """Cards in a CSS grid, balanced per breakpoint.

    A grid rather than the Bootstrap row it replaced. Bootstrap's twelve columns
    cannot express five across at all (12/5 is not an integer), so a balanced row
    count is simply not available through `dbc.Col` -- 6 + 3 was not a choice, it was
    the closest that grid could get. The per-breakpoint counts ride as CSS custom
    properties because how many cards there are is Python's fact while which
    breakpoint is live is CSS's; the media queries that consume them are in
    assets/custom.css under `.setup-grid`.
    """
    return html.Div(
        cards,
        className="setup-grid",
        style={f"--cols-{bp}": balanced_columns(len(cards), most[bp]) for bp in most},
    )


def tier_of(setup, palette):
    """A setup state as `(badge text or None, mark colour)`.

    SETUP_NONE gets no badge and a NEUTRAL mark, which is what lets the screener
    render every market in a class through the same card as the setups strip. /strip
    settled the colour: red and green belong to the VERDICTS, so a row the model has
    nothing to say about must not borrow one, and a dim mark is texture rather than a
    third opinion.
    """
    return {
        const.SETUP_BULL: ("SETUP", palette[3]),
        const.SETUP_BEAR: ("SETUP", palette[0]),
        const.SETUP_NEAR_BULL: ("NEAR", palette[3]),
        const.SETUP_NEAR_BEAR: ("NEAR", palette[0]),
    }.get(setup, (None, vc.SOLARIZED_DARK_BASE00))


# One card at three weights, not three card designs. Every difference between them
# lives in this table, so they cannot drift into looking like different things that
# happen to share a page -- which is what a second hand-written layout becomes the
# first time only one of them is edited.
#
# "featured" is a market at the gate, "near" one approaching it, and "screener" is the
# accordion below, which is the featured weight plus a footer. The screener sits at
# featured weight rather than between the two on purpose: its cards are not a lesser
# tier of the same list, they are a different list, and shrinking them would read as
# ranking them under the approaching tier.
CARD_WEIGHTS = {
    "featured": dict(name="0.95rem", name_weight="700", badge="0.60rem", idx="0.88rem",
                     delta="0.62rem", lane=LANE_PX, gap=LANE_GAP, dot=None,
                     pad="8px 10px", radius="6px", opacity=1.0,
                     bg="rgba(255,255,255,0.03)", border="rgba(255,255,255,0.06)",
                     badge_fill=True, gutter="6px", outline="59"),
    "near":     dict(name="0.78rem", name_weight="600", badge="0.52rem", idx="0.74rem",
                     delta="0.56rem", lane=7, gap=2, dot=5,
                     pad="5px 8px", radius="5px", opacity=0.72,
                     bg="rgba(255,255,255,0.015)", border="rgba(255,255,255,0.04)",
                     badge_fill=False, gutter="4px", outline=None),
    "screener": dict(name="0.92rem", name_weight="700", badge="0.58rem", idx="0.86rem",
                     delta="0.60rem", lane=LANE_PX, gap=LANE_GAP, dot=None,
                     pad="9px 11px", radius="6px", opacity=1.0,
                     bg="rgba(255,255,255,0.03)", border="rgba(255,255,255,0.06)",
                     badge_fill=True, gutter="6px", outline=None),
}


def positioning_card(row, model, palette, *, weight="featured", subtitle=None,
                     footer=None, badges=None):
    """THE card. One market's positioning, as the whole app draws it.

    `row` is a board row from `cotmetrics.movers.get_board`, or anything shaped like
    one -- `build_mobile_asset_card` assembles the same keys off a frame so the
    screener below renders through this function rather than through a second layout
    that says the same things differently.

    `subtitle` is the exchange symbol on screener cards. `footer` is a muted metrics
    line, and `badges` the fired signals; both are None on the setups strip, which is
    the only difference between the two views of this card.

    Always a link, always to the market's OI Alignment page, always in a new tab. The
    board is a list you work THROUGH, so following a market must not cost you the
    list. A nested <a> would be invalid HTML, which is why the name is a plain span
    and takes its appearance from the card's hover rule in assets/custom.css.
    """
    w = CARD_WEIGHTS[weight]
    text, colour = tier_of(row["setup"], palette)

    badge = None
    if text:
        style = {
            "color": colour, "border": f"1px solid {colour}66",
            "borderRadius": "3px", "padding": "1px 5px", "fontSize": w["badge"],
            "fontWeight": "bold", "marginLeft": "8px", "whiteSpace": "nowrap",
            "flex": "0 0 auto",
        }
        if w["badge_fill"]:
            style["backgroundColor"] = f"{colour}1a"
        # Age rides INSIDE the badge rather than as a fifth element on the card. It is
        # the only reading tested that this card does not already imply -- over 551 gate
        # market-weeks, tape bias, WillCo and the six-week move never once pointed
        # against the positioning beside them, so drawing those here would restate the
        # strip -- and it is one number, so it does not need a row of its own. Quieter
        # than the tier because the tier is still the headline: this answers the second
        # question, not the first.
        weeks = row.get("setup_weeks") or 0
        content = [text]
        if weeks:
            capped = weeks >= const.SETUP_AGE_CAP
            content.append(html.Span(
                f" \u00b7 {weeks}w{'+' if capped else ''}",
                style={"opacity": 0.72, "fontWeight": "normal"}))
        badge = html.Span(content, style=style, title=(
            f"At or approaching this gate for {weeks}"
            f"{'+' if weeks >= const.SETUP_AGE_CAP else ''} "
            f"consecutive week{'' if weeks == 1 else 's'}, in this direction. "
            "A run ends on a neutral week or a change of direction."
        ) if weeks else None)

    # Market name first and largest. The card used to lead with the index and drop the
    # market underneath, which put the least identifying thing on it in the most
    # prominent slot: a board is navigated by market, and "100" tells a reader nothing
    # until they have read the name to find out what is at 100.
    name = [html.Span(row["asset"],
                      style={"color": vc.BRIGHTER_TEXT_COLOR,
                             "fontWeight": w["name_weight"], "fontSize": w["name"],
                             "overflow": "hidden", "textOverflow": "ellipsis",
                             "whiteSpace": "nowrap"})]
    if subtitle:
        name.append(html.Span(f" ({subtitle})",
                              style={"color": vc.TEXT_COLOR, "fontSize": "0.68rem",
                                     "marginLeft": "5px", "whiteSpace": "nowrap"}))

    body = [
        html.Div([
            html.Div(name, style={"display": "flex", "alignItems": "baseline",
                                  "minWidth": 0, "overflow": "hidden"}),
            badge,
        ], style={"display": "flex", "alignItems": "baseline",
                  "justifyContent": "space-between", "gap": "4px"}),
        # Row two: the exact index, all three legs. The strip below gives position,
        # which is the shape; this gives the figures, which is what you compare
        # between two cards.
        html.Div(index_triplet(row, model, size=w["idx"]), style={"marginTop": "2px"}),
        html.Div(
            gate_strip_row(row, model, palette, colour=colour, lane_px=w["lane"],
                           gap=w["gap"], dot_px=w["dot"], size=w["delta"]),
            title=(f"{_strip_hover(row, model)}. "
                   f"{vc.positioning_tooltip(row['setup'], model, row['is_equity'])}"),
            style={"marginTop": w["gutter"], "cursor": "help"},
        ),
    ]
    if footer:
        body.append(html.Div(footer, style={
            "marginTop": "7px", "paddingTop": "6px",
            "borderTop": "1px solid rgba(255,255,255,0.06)",
            "fontSize": "0.64rem", "color": vc.TEXT_COLOR,
            "lineHeight": "1.5"}))
    if badges:
        body.append(html.Div(badges, style={"marginTop": "6px", "display": "flex",
                                            "flexWrap": "wrap", "gap": "3px"}))

    # A thin tinted OUTLINE on the featured tier, and nothing on the other two.
    #
    # This is not the 3px bar down the left edge that was removed earlier, and the
    # difference is the point. That bar was a saturated slab on every card in both
    # tiers, so the panel read as a field of red and green before a reader had got to
    # a market name. A hairline at ~35% around the card's existing border is a tint
    # rather than a mark: it does not compete for attention with the dot or the badge,
    # and it lets a whole row of cards be sorted by eye without reading any of them,
    # which is what the direction grouping is for.
    #
    # Featured only, so it carries TWO facts at once: colour is the direction and the
    # mere presence of the tint is "this one is at the gate". The approaching tier
    # keeps a neutral border and so cannot be mistaken for a setup at a glance, and
    # the screener cards below stay neutral because most of them have no verdict at
    # all and a row of grey outlines among a few tinted ones would read as broken.
    edge = w["border"]
    if w["outline"] and text:
        edge = f"{colour}{w['outline']}"

    return html.A(
        html.Div(body, style={
            "backgroundColor": w["bg"],
            "border": f"1px solid {edge}",
            "borderRadius": w["radius"], "padding": w["pad"], "height": "100%",
            "opacity": w["opacity"],
        }),
        href=f"/oi_alignment?asset={urllib.parse.quote(row['asset'])}",
        target="_blank",
        rel="noopener noreferrer",
        className="setup-card",
        style={"textDecoration": "none", "display": "block", "height": "100%"},
    )


ActiveSetups = namedtuple("ActiveSetups", "header body")


def build_active_setups_strip(rows, color_palette, model=None, filter_types=None,
                              show_near=True):
    """Markets sitting at or approaching a positioning gate.

    Answers "where is a setup firing right now", which nothing else on the page did: the
    movers strip answers what *changed* this week, and the screener accordion below lists
    every market by asset class regardless of state. Finding today's setups meant
    expanding eight accordions and scanning 42 cards.

    Takes already-swept board rows rather than fetching its own, so the two strips on the
    page cost one pass over the board between them. `model` must be the one that swept
    them: it is read here only to say which gate produced these verdicts and to name the
    legs it consulted, so a mismatched one would describe the wrong gate.

    Returns the header and the body separately rather than one finished box. The box and
    its "Approaching" switch are static in the page layout, because a control rendered
    *inside* this output would be an input to the callback that replaces it: it would be
    rebuilt on every change and could not be read without a circular dependency.

    `show_near` hides the approaching tier without removing it from the tally. Full
    setups render at full strength and near ones dimmed, which is the same weight
    relationship viz_constants uses for the index ramp: an approach is a hint that
    something is drifting toward a gate, not a signal competing with the gate itself.
    """
    from cotmetrics import movers as movers_mod

    model = model if isinstance(model, models.PositioningModel) else models.resolve(model)
    # Larger and brighter than the movers header below it, deliberately. This strip is
    # the answer to the page's question and that one is the context around it, so the
    # two headings are ranked rather than matched.
    def _header(tally):
        return [
            html.Span(f"Active Setups · {model.title}",
                      style={"fontWeight": "bold", "color": vc.BRIGHTER_TEXT_COLOR,
                             "fontSize": "1.05rem", "letterSpacing": "0.2px"}),
            html.Span(tally, style={"fontSize": "0.72rem", "color": vc.TEXT_COLOR,
                                    "marginLeft": "10px"}),
        ]

    def _grouped(items):
        """Bull setups first, then bear, each keeping the order it arrived in.

        `select_setups` ranks by conviction -- tier, then distance from neutral -- and
        that stays the contract, because it is the right general answer and other
        callers depend on it. This is a VIEW decision layered on top: alternating
        directions down a grid makes a reader re-read the badge on every card, where
        two blocks let them find the side they care about once and then scan within
        it. A long and a short are not competing for the same slot in a portfolio, so
        interleaving them by extremity was ranking across a boundary that matters.

        The sort is stable and keys on direction alone, so within each block the
        conviction order survives untouched -- the most extreme bull is still the
        first card on the strip.
        """
        return sorted(items, key=lambda r: 0 if r["setup"] in _BULL_STATES else 1)

    setups = movers_mod.select_setups(rows)
    full = _grouped(s for s in setups if s["setup"] in const.SETUP_FULL_STATES)
    near = _grouped(s for s in setups if s["setup"] in const.SETUP_NEAR_STATES)

    # The empty state has to distinguish "no setups" from "your filter hid them", because
    # a bias filter on a quiet board can empty this strip while the board itself is fine.
    if not setups:
        msg = ("No markets are at or approaching a gate under this model."
               if not movers_mod._wanted_biases(filter_types)
               else "No markets match the active tape-bias filter.")
        return ActiveSetups(
            _header("nothing active"),
            html.Div(msg, className="text-muted text-center py-3",
                     style={"fontSize": "0.8rem"}),
        )

    # None means the switch has not reported yet (first paint, or a session store with
    # nothing in it). That is not the same as "off", and defaulting it to off would hide
    # the approaching tier on load for a reader who never touched the control.
    show_near = True if show_near is None else bool(show_near)
    setups = setups if show_near else full

    # Reached only when the switch is off *and* nothing was at the gate. Saying so beats
    # an empty row, which would read as "no setups" when there are some behind a toggle.
    if not setups:
        return ActiveSetups(
            _header(f"nothing at the gate · {len(near)} approaching, hidden"),
            html.Div(
                f"No markets are at a gate under {model.title}. "
                f"{len(near)} are approaching one, hidden by the Approaching switch.",
                className="text-muted text-center py-3", style={"fontSize": "0.8rem"},
            ),
        )

    def _card(s, featured):
        return positioning_card(s, model, color_palette,
                                weight="featured" if featured else "near")

    def _grid(items, featured):
        tier = "featured" if featured else "near"
        return card_grid([_card(s, featured) for s in items], MAX_PER_ROW[tier])

    body = []
    if full:
        body.append(_grid(full, True))

    if show_near and near:
        # A real gap, not a rule with a line of text on it. At 10px above and 6px
        # below, the label sat closer to the featured row it was separating FROM than
        # to the cards it introduces, so the two tiers read as one list with a caption
        # dropped into it. Whitespace is what says "different group" -- the rule only
        # marks where, and it is kept faint so the eye reads the gap rather than the
        # line.
        body.append(html.Div(
            f"Approaching · within {const.SETUP_NEAR_WIDTH} points of the gate",
            style={"fontSize": "0.66rem", "color": vc.TEXT_COLOR,
                   "textTransform": "uppercase", "letterSpacing": "0.6px",
                   "marginTop": "26px", "marginBottom": "10px",
                   "paddingTop": "14px",
                   "borderTop": "1px solid rgba(255,255,255,0.06)"}))
        body.append(_grid(near, False))

    # Counts in the subtitle rather than a bare list: the split is the thing a reader
    # wants at a glance, and it changes with the model selector in a way that makes the
    # two models' different strictness visible instead of implied.
    #
    # The near count is stated even when the switch hides them, and says so. A tally that
    # silently shrank with the toggle would leave a reader thinking the board had changed
    # rather than the view of it.
    tally = f"{len(full)} at the gate"
    if near:
        tally += f", {len(near)} approaching" + ("" if show_near else ", hidden")

    return ActiveSetups(_header(tally), html.Div(body))
