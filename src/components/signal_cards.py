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
    from datetime import datetime


    model = model if isinstance(model, models.PositioningModel) else models.resolve(model)
    min_idx, max_idx = model.low, model.high
    # Equities gate on Commercials alone, and the CS gate drops Large Specs, so whether
    # a leg is worth colouring depends on both.
    gates_large = not is_equity and models.LEG_LARGE in model.spec_legs
    gates_small = not is_equity and models.LEG_SMALL in model.spec_legs

    if df is None or df.empty:
        return None

    latest = df.iloc[-1]

    safe_get = _safe_getter(latest, f"build_mobile_asset_card({asset})")

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
    lrg_sentiment = safe_get(const.LW_LRG_SENTIMENT, None)
    oi_z          = safe_get(const.OI_ZSCORE, 0)
    comm_spr      = safe_get(const.COMMS_SPEARMAN, 0)
    lrg_spr       = safe_get(const.LRG_SPEARMAN, 0)
    sml_spr       = safe_get(const.SML_SPEARMAN, 0)

    instrument = get_indexer().get_instrument_from_name(asset)
    symbol_str = instrument.symbol if instrument else asset

    from cotmetrics.options_data import get_max_pain_for_symbol
    try:
        report_date_str = pd.to_datetime(latest.name).strftime('%Y-%m-%d')
        res = get_max_pain_for_symbol(symbol_str, report_date_str)
        max_pain, delta_iv, current_price = (res["max_pain"], res["delta_iv"], res.get("current_price")) if res else (None, None, None)
    except Exception:
        max_pain, delta_iv, current_price = None, None, None

    if max_pain is not None and current_price is not None and current_price > 0:
        max_pain_pull = ((max_pain - current_price) / current_price) * 100
    else:
        max_pain_pull = None

    def fmt_mp(val):
        if val is None:
            return "N/A"
        if val < 10:
            return f"{val:,.4f}"
        if val < 100:
            return f"{val:,.2f}"
        return f"{val:,.0f}"

    def fmt_div(val):
        if val is None:
            return "N/A"
        val_k = val * 1000
        if abs(val_k) < 1.0:
            return f"{val_k:,.1f}K"
        return f"{val_k:,.0f}K"

    # ---- Signals ----
    bullish_setup, bearish_setup, _, _ = model.setup_masks(
        comm_idx, lrg_idx, sml_idx, is_equity
    )

    active_bull_signals: list[str] = []
    active_bear_signals: list[str] = []

    if bullish_setup:
        active_bull_signals.append("BULLISH POSITIONING")
    if bearish_setup:
        active_bear_signals.append("BEARISH POSITIONING")

    # Core algo signals (no accumulation signals on the compact mobile card)
    _bull, _bear, _debug, _ = _collect_active_signals(latest, include_accumulation=False)
    active_bull_signals.extend(_bull)
    active_bear_signals.extend(_bear)

    # Spearman is shown as a badge on mobile rather than a separate card
    if latest.get(const.COMMS_SPEARMAN_REGIME_SHIFT, False):
        if comm_momentum > 0:
            active_bull_signals.append("SPEARMAN BULL")
        else:
            active_bear_signals.append("SPEARMAN BEAR")

    instrument = get_indexer().get_instrument_from_name(asset)
    symbol_str = instrument.symbol if instrument else asset

    bearish_setup or (len(active_bear_signals) > len(active_bull_signals))

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

    # ---- Colors ----
    BULL_COLOR = color_palette[3]
    BEAR_COLOR = color_palette[0]

    # Use a brighter red for readability
    if BEAR_COLOR.lower() in ("#f87171", "#dc322f", "#ff453a", "#e70307", "#ff007f"):
        BEAR_COLOR = "#FF4D4D"

    if tape_bias == "BULLISH":
        border_color = BULL_COLOR
    elif tape_bias == "BEARISH":
        border_color = BEAR_COLOR
    elif len(active_bull_signals) > len(active_bear_signals):
        border_color = BULL_COLOR
    elif len(active_bear_signals) > len(active_bull_signals):
        border_color = BEAR_COLOR
    else:
        border_color = color_palette[1]

    # ---- Badges ----
    badges = (
        [dbc.Badge(s, className="me-1 mb-1 py-0.5 px-1.5",
                   style={'fontSize': '0.55rem', 'whiteSpace': 'nowrap', 'backgroundColor': f'{BULL_COLOR}15', 'color': BULL_COLOR, 'border': f'1px solid {BULL_COLOR}40', 'fontWeight': 'normal'}) for s in active_bull_signals]
        + [dbc.Badge(s, className="me-1 mb-1 py-0.5 px-1.5",
                     style={'fontSize': '0.55rem', 'whiteSpace': 'nowrap', 'backgroundColor': f'{BEAR_COLOR}15', 'color': BEAR_COLOR, 'border': f'1px solid {BEAR_COLOR}40', 'fontWeight': 'normal'}) for s in active_bear_signals]
    )

    cftc_date = latest.name
    if isinstance(cftc_date, (datetime, pd.Timestamp)):
        cftc_date = cftc_date.strftime('%Y-%m-%d')
    else:
        cftc_date = str(cftc_date)

    instrument = get_indexer().get_instrument_from_name(asset)
    symbol_str = instrument.symbol if instrument else asset

    def _colored_span_mobile(value, bull_cond, bear_cond, fmt=".0f"):
        color = BULL_COLOR if bull_cond else (BEAR_COLOR if bear_cond else vc.BRIGHTER_TEXT_COLOR)
        return html.Span(f"{value:{fmt}}", style={'color': color, 'fontSize': '0.85rem',
                                                   'fontWeight': 'bold', 'whiteSpace': 'nowrap'})



    card = dbc.Card([
        dbc.CardBody([
            html.Div([
                html.H5([
                    html.Span(asset, id='oi_alignment_signal_card_title', style={'fontWeight': 'bold', 'color': vc.BRIGHTER_TEXT_COLOR}),
                    html.Span(f" ({symbol_str})", className="text-muted",
                              style={'fontSize': '0.72rem', 'marginLeft': '6px', 'fontWeight': 'normal'}),
                ], className="card-title mb-0 text-truncate",
                   style={'fontSize': '0.9rem', 'maxWidth': '65%'}),

                html.Div([
                    html.Span(f"{tape_bias}", style={
                        'fontSize': '0.65rem',
                        'color': '#000' if tape_bias in ("BULLISH", "BEARISH") else '#fff',
                        'backgroundColor': BULL_COLOR if tape_bias == "BULLISH" else (BEAR_COLOR if tape_bias == "BEARISH" else "#444"),
                        'padding': '2px 5px',
                        'borderRadius': '3px',
                        'fontWeight': 'bold',
                        'letterSpacing': '0.5px',
                        'whiteSpace': 'nowrap'
                    })
                ], className="d-flex align-items-center")
            ], className="d-flex justify-content-between align-items-center mb-2"),
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Span("Index: ", className="text-muted", title="0-100 stochastic index of net positioning over the lookback period. Format: Comm / Large / Small.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span([
                            _colored_span_mobile(comm_idx, comm_idx >= max_idx, comm_idx <= min_idx),
                            "/",
                            html.Span(f"{lrg_idx:.0f}", style={
                                # Only coloured while the model's gate actually uses this
                                # leg. Under the CS gate Large Specs do not participate,
                                # so lighting the cell would claim a role it has lost.
                                'color': BULL_COLOR if (gates_large and lrg_idx <= min_idx)
                                         else BEAR_COLOR if (gates_large and lrg_idx >= max_idx)
                                         else vc.BRIGHTER_TEXT_COLOR,
                                'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                            "/",
                            html.Span(f"{sml_idx:.0f}", style={
                                'color': BULL_COLOR if (gates_small and sml_idx <= min_idx)
                                         else BEAR_COLOR if (gates_small and sml_idx >= max_idx)
                                         else vc.BRIGHTER_TEXT_COLOR,
                                'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                        ], style={'whiteSpace': 'nowrap'}),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("Pos Z-Score: ", className="text-muted", title="Statistical z-score of net positioning over the lookback period. Format: Comm / Large / Small.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(f"{comm_z:.1f}/{lrg_z:.1f}/{sml_z:.1f}", className="text-white", style={'fontSize': '0.85rem', 'whiteSpace': 'nowrap'}),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("Movement: ", className="text-muted", title="Momentum (6-week lookback) measuring the velocity of positioning changes. Format: Comm / Large / Small.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span([
                            _colored_span_mobile(comm_momentum, comm_momentum >= const.MOMENTUM_MAX_THRESHOLD, comm_momentum <= const.MOMENTUM_MIN_THRESHOLD),
                            "/",
                            _colored_span_mobile(lrg_momentum, lrg_momentum >= const.MOMENTUM_MAX_THRESHOLD, lrg_momentum <= const.MOMENTUM_MIN_THRESHOLD),
                            "/",
                            _colored_span_mobile(sml_momentum, sml_momentum >= const.MOMENTUM_MAX_THRESHOLD, sml_momentum <= const.MOMENTUM_MIN_THRESHOLD),
                        ], style={'whiteSpace': 'nowrap'}),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("LW Sentiment: ", className="text-muted", title="Larry Williams Large Speculator Sentiment Index (15-week lookback). Used as a contrarian indicator.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(
                            f"{lrg_sentiment:.0f}" if pd.notna(lrg_sentiment) else "N/A",
                            style={
                                'color': BEAR_COLOR if (pd.notna(lrg_sentiment) and lrg_sentiment >= const.LW_LRG_SENTIMENT_MAX_THRESHOLD)
                                         else BULL_COLOR if (pd.notna(lrg_sentiment) and lrg_sentiment <= const.LW_LRG_SENTIMENT_MIN_THRESHOLD)
                                         else vc.BRIGHTER_TEXT_COLOR,
                                'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap',
                            }
                        ),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("Spearman: ", className="text-muted", title="Spearman rank correlation coefficient between net positioning and price. Detects hedging regime shifts.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(f"{comm_spr:.1f}/{lrg_spr:.1f}/{sml_spr:.1f}", className="text-white", style={'fontSize': '0.85rem', 'whiteSpace': 'nowrap'}),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("Max Pain Pull: ", className="text-muted", title="The percentage distance from the current price to the Max Pain strike. Positive means the strike is above the price (magnetic pull upwards).", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(f"{max_pain_pull:+.1f}%" if max_pain_pull is not None else "N/A", style={
                            'color': BULL_COLOR if (max_pain_pull is not None and max_pain_pull > 0) else BEAR_COLOR if (max_pain_pull is not None and max_pain_pull < 0) else vc.BRIGHTER_TEXT_COLOR,
                            'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                    ]),
                ], xs=7),

                dbc.Col([
                    html.Div([
                        html.Span("WILLCO: ", className="text-muted", title="Larry Williams Commercial proxy index. Measures how fully deployed Commercials are relative to total open interest.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(f"{willco:.0f}", style={
                            'color': BULL_COLOR if willco >= const.WILLCO_MAX_THRESHOLD else BEAR_COLOR if willco <= const.WILLCO_MIN_THRESHOLD else vc.BRIGHTER_TEXT_COLOR,
                            'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("OI Z-Score: ", className="text-muted", title="Open Interest Z-Score. Measures how extreme the current amount of open contracts is.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(f"{oi_z:.1f}", style={
                            'color': BULL_COLOR if oi_z >= const.OI_ZSCORE_MAX_THRESHOLD else BEAR_COLOR if oi_z <= const.OI_ZSCORE_MIN_THRESHOLD else vc.BRIGHTER_TEXT_COLOR,
                            'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                    ], style={'marginBottom': '2px'}),
                    html.Div([
                        html.Span("Delta IV: ", className="text-muted", title="Delta Intrinsic Value. The magnitude of 'excess pain' (in Millions) market makers are experiencing compared to the Max Pain strike.", style={'fontSize': '0.62rem', 'whiteSpace': 'nowrap', 'cursor': 'help'}),
                        html.Span(f"{fmt_div(delta_iv)}" if delta_iv is not None else "N/A", style={
                            'color': vc.BRIGHTER_TEXT_COLOR,
                            'fontSize': '0.85rem', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}),
                    ]),
                ], xs=5),
            ], className="mb-2 p-1.5 rounded", style={'backgroundColor': 'rgba(255, 255, 255, 0.03)'}),

            html.Div(badges, className="mt-2 mb-1"),

            html.A(
                dbc.Button("Analyze Charts →", color="primary", outline=True, size="sm",
                           className="w-100 mt-1 py-1", style={'fontSize': '0.75rem'}),
                href=f"/oi_alignment?asset={urllib.parse.quote(asset)}",
                target="_blank"
            ),
        ], style={'padding': '12px 14px'}),
    ], style={
        'backgroundColor': 'var(--card-color)',
        'border': f'1.5px solid {border_color}70',
        'boxShadow': f'0 4px 15px {border_color}10',
    }, className="h-100 signal-card-hover")

    return card


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
        code = cot_indexer.get_instrument_symbol_from_name(name)
        symbol = cot_indexer.instruments[code].symbol if code in cot_indexer.instruments else name
        is_equity = cot_indexer.is_equity(name)
        card = build_mobile_asset_card(
            df, symbol, color_palette, lookback, model=model,
            is_equity=is_equity, filter_types=filter_types
        )
        if card is not None:
            ac_cards.append(dbc.Col(card, xs=12, sm=6, md=4, lg=3, xl=2))

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

    return dbc.Row(ac_cards, className="g-2 p-1")


def _setup_leg_readout(row, model):
    """The gated legs and their index values, e.g. "Comm 100 · Small 12".

    Shows the gate's working rather than restating the verdict the badge already gives.
    Only the legs this model actually consulted appear, so an NPF card never implies a
    Large Spec condition its CS gate never checked, and an equity card says so outright
    instead of listing legs that did not gate it.
    """
    parts = [f"Comm {row['index']}"]
    if row["is_equity"]:
        parts.append("specs not gated")
    else:
        for leg, short, key in ((models.LEG_LARGE, "Large", "lrg_index"),
                                (models.LEG_SMALL, "Small", "sml_index")):
            if leg in model.spec_legs and row[key] is not None:
                parts.append(f"{short} {row[key]}")
    return " · ".join(parts)


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
    BULL_COLOR = color_palette[3]
    BEAR_COLOR = color_palette[0]

    def _header(tally):
        return [
            html.Span(f"Active Setups · {model.title}",
                      style={"fontWeight": "bold", "color": vc.BRIGHTER_TEXT_COLOR,
                             "fontSize": "0.9rem"}),
            html.Span(tally, style={"fontSize": "0.7rem", "color": vc.TEXT_COLOR,
                                    "marginLeft": "8px"}),
        ]

    setups = movers_mod.select_setups(rows)
    full = [s for s in setups if s["setup"] in const.SETUP_FULL_STATES]
    near = [s for s in setups if s["setup"] in const.SETUP_NEAR_STATES]

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

    _TIERS = {
        const.SETUP_BULL: ("SETUP", BULL_COLOR, 1.0),
        const.SETUP_BEAR: ("SETUP", BEAR_COLOR, 1.0),
        const.SETUP_NEAR_BULL: ("NEAR", BULL_COLOR, vc.INDEX_RAMP_ALPHA_APPROACH),
        const.SETUP_NEAR_BEAR: ("NEAR", BEAR_COLOR, vc.INDEX_RAMP_ALPHA_APPROACH),
    }

    cards = []
    for s in setups:
        text, colour, strength = _TIERS[s["setup"]]
        s["setup"] in const.SETUP_FULL_STATES

        # The delta rides along where there is one, so a reader can tell a setup that
        # arrived this week from one that has been sitting there. It is deliberately
        # secondary: this strip ranks on level, not on movement.
        #
        # It sits on the index line rather than beside the market name, and drops the
        # "this week" suffix, because that line was what set the card's width. At the
        # previous 4-per-row the widest row measured 168px inside a 298px card, and
        # "Canadian Dollar ▲ +7 this week" was the row setting it. The index line had
        # room to spare. The header already scopes the strip to this release, so the
        # suffix was restating it on every card.
        move = None
        if s["delta"]:
            move = html.Span(
                f"{'▲' if s['delta'] > 0 else '▼'}{s['delta']:+d}",
                title=f"{abs(s['delta'])} point Commercial move at this release",
                style={"fontSize": "0.62rem", "color": vc.TEXT_COLOR,
                       "marginLeft": "6px", "whiteSpace": "nowrap", "cursor": "help"},
            )

        cards.append(dbc.Col(
            html.Div([
                html.Div([
                    html.Span(f"{s['index']}", style={
                        "fontSize": "1.25rem", "fontWeight": "bold",
                        "color": vc.BRIGHTER_TEXT_COLOR}),
                    html.Span("/100", style={
                        "fontSize": "0.7rem", "color": vc.TEXT_COLOR, "marginLeft": "1px"}),
                    html.Span(text, style={
                        "color": colour, "border": f"1px solid {colour}66",
                        "backgroundColor": f"{colour}1a", "borderRadius": "3px",
                        "padding": "1px 5px", "fontSize": "0.6rem", "fontWeight": "bold",
                        "marginLeft": "8px", "whiteSpace": "nowrap"}),
                    move,
                ], style={"display": "flex", "alignItems": "baseline"}),
                html.Div(
                    dcc.Link(s["asset"],
                             href=f"/oi_alignment?asset={urllib.parse.quote(s['asset'])}",
                             style={"color": vc.BRIGHTER_TEXT_COLOR, "fontWeight": "600",
                                    "fontSize": "0.85rem", "textDecoration": "none"}),
                    style={"marginTop": "2px", "whiteSpace": "nowrap",
                           "overflow": "hidden", "textOverflow": "ellipsis"},
                ),
                html.Div(_setup_leg_readout(s, model),
                         title=vc.positioning_tooltip(s["setup"], model, s["is_equity"]),
                         style={"fontSize": "0.68rem", "color": vc.TEXT_COLOR,
                                "marginTop": "3px", "lineHeight": "1.25",
                                "cursor": "help", "whiteSpace": "nowrap"}),
            ], style={
                "backgroundColor": "rgba(255,255,255,0.03)",
                "border": "1px solid rgba(255,255,255,0.06)",
                "borderLeft": f"3px solid {colour}",
                "borderRadius": "6px", "padding": "8px 10px", "height": "100%",
                "opacity": strength,
            }),
            # Six across at xl, where the index row (widest at ~145px with the delta on
            # it) clears the ~171px a column gives. At lg the column drops to ~118px of
            # content and that row overflows, so lg stays at four. Measured, not guessed:
            # six-up at the bottom of the lg range clipped the delta off four cards.
            # Ten cards still go from three rows to two at xl, thirteen from four to
            # three, which is the density this was for on a desktop viewport.
            xs=12, sm=6, md=3, lg=3, xl=2, className="mb-2",
        ))

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

    return ActiveSetups(_header(tally), dbc.Row(cards, className="g-2"))


WeeklyMovers = namedtuple("WeeklyMovers", "header body")


# No `model` parameter: everything model-dependent here (the ranking basis, the setup
# badge) was decided when the rows were swept. Accepting one again would let a caller
# label this strip with a model that did not produce it.
def build_weekly_movers_strip(rows, color_palette, limit=8, filter_types=None):
    """Ranked strip of the largest Commercial repositioning at this CFTC release.

    Answers "what changed this week", which nothing else on the dashboard does: the
    heatmap shows levels and the Signal Matrix's Move column is a six-week trend.

    Each card carries the index level, the week's point delta, and the row's setup
    state as a separate badge. The badge is deliberately not folded into the caption:
    the leg that moved is not always the leg that advances the setup, so stating them
    together would imply a causation that is often backwards.

    Takes already-swept board rows, so this and the Active Setups strip above it share
    one pass over the board rather than walking all 42 instruments twice.

    Returns header and body separately, for the same reason build_active_setups_strip
    does: the collapse toggle that hides this strip is static in the page layout, and a
    control rendered into a callback's own output cannot be read by that callback.
    """
    from cotmetrics import movers as movers_mod
    from cotmetrics.movers import MOVER_GROUP_ADJ

    BULL_COLOR = color_palette[3]
    BEAR_COLOR = color_palette[0]

    def _header(scope, note):
        return [
            html.Span(f"Biggest {MOVER_GROUP_ADJ} Moves This Week{scope}",
                      style={"fontWeight": "bold", "color": vc.BRIGHTER_TEXT_COLOR,
                             "fontSize": "0.9rem"}),
            html.Span(note, style={"fontSize": "0.7rem", "color": vc.TEXT_COLOR,
                                   "marginLeft": "8px"}),
        ]

    movers = movers_mod.rank_movers(rows, limit)
    if not movers:
        msg = ("No markets match the active tape-bias filter."
               if movers_mod._wanted_biases(filter_types)
               else "No markets moved at this release.")
        return WeeklyMovers(
            _header("", "nothing to rank"),
            html.Div(msg, className="text-muted text-center py-3",
                     style={"fontSize": "0.8rem"}),
        )

    # The strip is filtered *before* ranking, so a filtered heading that still claimed
    # to be the biggest moves outright would be false. Name the filter instead.
    scope = {
        frozenset({movers_mod.FILTER_BULL}): " \u00b7 Bullish Tape Bias",
        frozenset({movers_mod.FILTER_BEAR}): " \u00b7 Bearish Tape Bias",
        frozenset({movers_mod.FILTER_BULL, movers_mod.FILTER_BEAR}): " \u00b7 Biased Markets",
    }.get(frozenset(filter_types or []), "")

    _SETUP_LABELS = {
        const.SETUP_BULL: ("SETUP", BULL_COLOR),
        const.SETUP_BEAR: ("SETUP", BEAR_COLOR),
        const.SETUP_NEAR_BULL: ("NEAR", BULL_COLOR),
        const.SETUP_NEAR_BEAR: ("NEAR", BEAR_COLOR),
    }

    cards = []
    for m in movers:
        colour = BULL_COLOR if m["delta"] > 0 else BEAR_COLOR
        arrow = "▲" if m["delta"] > 0 else "▼"

        badges = []
        if m["unusual"]:
            # Palette slot 2 is the attention/energy colour used for OI extremes, so the
            # flag reads as "look here" without competing with the bull/bear setup badge.
            attn = color_palette[2]
            badges.append(html.Span(
                f"{m['multiple']:.1f}\u00d7",
                title=(f"{abs(m['delta'])} points is {m['multiple']:.1f}x this market's "
                       f"typical weekly Commercial move. Ranking is by raw points, so a "
                       f"card can be unusual without being at the top."),
                style={
                    "color": attn, "border": f"1px solid {attn}66",
                    "backgroundColor": f"{attn}1a", "borderRadius": "3px",
                    "padding": "1px 5px", "fontSize": "0.6rem", "fontWeight": "bold",
                    "marginLeft": "6px", "whiteSpace": "nowrap", "cursor": "help",
                }))

        badge = None
        if m["setup"] in _SETUP_LABELS:
            text, badge_colour = _SETUP_LABELS[m["setup"]]
            badge = html.Span(text, style={
                "color": badge_colour, "border": f"1px solid {badge_colour}66",
                "backgroundColor": f"{badge_colour}1a", "borderRadius": "3px",
                "padding": "1px 5px", "fontSize": "0.6rem", "fontWeight": "bold",
                "marginLeft": "6px", "whiteSpace": "nowrap",
            })

        cards.append(dbc.Col(
            html.Div([
                html.Div([
                    html.Span(f"{m['index']}", style={
                        "fontSize": "1.25rem", "fontWeight": "bold",
                        "color": vc.BRIGHTER_TEXT_COLOR}),
                    html.Span("/100", style={
                        "fontSize": "0.7rem", "color": vc.TEXT_COLOR, "marginLeft": "1px"}),
                    html.Span(f"{arrow} {m['delta']:+d}", style={
                        "fontSize": "0.85rem", "fontWeight": "bold",
                        "color": colour, "marginLeft": "8px"}),
                ], style={"display": "flex", "alignItems": "baseline"}),
                html.Div([
                    dcc.Link(m["asset"], href=f"/oi_alignment?asset={urllib.parse.quote(m['asset'])}",
                             style={"color": vc.BRIGHTER_TEXT_COLOR, "fontWeight": "600",
                                    "fontSize": "0.85rem", "textDecoration": "none"}),
                    badge, *badges,
                ], style={"display": "flex", "alignItems": "center", "marginTop": "2px"}),
                html.Div(m["caption"], style={
                    "fontSize": "0.68rem", "color": vc.TEXT_COLOR,
                    "marginTop": "3px", "lineHeight": "1.25"}),
            ], style={
                "backgroundColor": "rgba(255,255,255,0.03)",
                "border": "1px solid rgba(255,255,255,0.06)",
                "borderLeft": f"3px solid {colour}",
                "borderRadius": "6px", "padding": "8px 10px", "height": "100%",
            }),
            xs=12, sm=6, md=4, lg=3, xl=3, className="mb-2",
        ))

    return WeeklyMovers(
        _header(scope, "week-over-week change in the 0-100 positioning index"),
        dbc.Row(cards, className="g-2"),
    )
