import textwrap

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

# Register this file as a page
dash.register_page(__name__, path='/about')

# ==========================================
# 1. UI Helper Functions
# ==========================================
def create_markdown_card(md_text):
    return dcc.Markdown(
        md_text,
        mathjax=True,
        style={'color': 'var(--text-light)', 'fontSize': '1.05rem', 'lineHeight': '1.6'}
    )

def create_bootstrap_table(headers, rows):
    """Converts a list of headers and rows into a fully responsive Bootstrap table."""
    table_header = [html.Thead(html.Tr([html.Th(h) for h in headers]))]
    table_body = [
        html.Tbody([
            html.Tr([
                html.Td(dcc.Markdown(str(cell), style={'margin': '0'})) for cell in row
            ]) for row in rows
        ])
    ]
    return dbc.Table(
        table_header + table_body,
        bordered=True,
        striped=True,
        hover=True,
        responsive=True,
        className="mb-4 mt-3 shadow-sm",
        style={'backgroundColor': 'var(--card-bg)', 'color': 'var(--text-light)'}
    )

# ==========================================
# 2. Markdown Introductions
# ==========================================

intro_md = textwrap.dedent("""
    This application, **COT Analyzer**, is a powerful tool for futures traders to visualize and interpret the weekly Commitments of Traders (COT) Legacy reports published by the CFTC. Because raw COT data is composed of absolute open interest and position sizes, it is difficult to use for trading out of the box.

    This app transforms that raw data into normalized, actionable indicators (Indexes, Z-Scores, Oscillators) and sophisticated algorithmic overlays that can be plotted against closing prices to identify market extremes, trend exhaustion, and impending reversals.
""")

participants_intro_md = textwrap.dedent("""
    To use the application effectively, you must understand the three categories of traders tracked in the legacy COT report, which are color-coded in the app's charts:
""")

core_metrics_intro_md = textwrap.dedent("""
    The application normalizes raw position data over user-defined **Lookback Periods** (e.g., 26 weeks, 52 weeks, or Custom lengths) to create bounded oscillators and velocity metrics.
""")

markers_intro_md = textwrap.dedent("""
    The application features a tape-reading engine that overlays algorithmic signals directly onto the price charts. Instead of looking at static extremes, these markers evaluate the *behavioral mechanics* of the exchange.
""")

workflows_md = textwrap.dedent("""
    1. The Top-Down Scan (Using the Heatmap)
        * Start your weekend analysis on the **Heatmap** page, then pick a Lookback Window and toggle the Asset Classes you care about.
        * The grid shows both gates side by side: **Raw CLS 95/5** (net contracts, Commercials + Large + Small) and **NPF CS 80/20** (net / open interest, Commercials + Small). A cell lights up green or red when that leg qualifies under its own model's band.
        * Scan the Tape Bias and Signals columns for markets where a setup is already firing, then read across to see whether both gates agree.
        * A row with Commercials lit green and the speculator legs lit red is a market ripe for a **bullish reversal**.

    2. Validating the Setup (Using OI Alignment)
        * Move to the **OI Alignment** tab and review the Price Candles and Open Interest plots.
        * Verify if the static extreme is supported by active behavioral signals (e.g., "Short Squeeze" or "Comm New Accum" markers).
        * Use the **Model** selector to switch between **Raw PF** (net contracts, Commercials + Large + Small, 95/5) and **NPF** (net / open interest, Commercials + Small, 80/20), and see how price reacted historically under each gate. **Both** overlays the two bases on one axis so the drift the normalization removes is visible.

    3. Triggering the Trade (Price Confirmation)
        * **Crucial Rule:** COT data is a *macro/leading indicator*, not a timing tool. Commercials have deep pockets and can be "early" to a reversal for weeks/months.
        * Do not buy simply because the Commercial Index is at 100.
        * **Wait for Price Action:** Drop down to a daily chart on your platform. Wait for a technical signal that agrees with the COT data (e.g., trendline break, MA crossover).
""")


backtest_md = textwrap.dedent("""
    If you are a systematic trader, use the **"Download Real Test Data"** button in the **Options** tab. This generates CSV "Event Lists" containing the normalized COT Index, Net Position data, and boolean signal states for every asset. You can import these directly into platforms like *Zipline-Reloaded*, *RealTest*, or *Amibroker* to backtest quantitative strategies.
""")

# ==========================================
# 3. Table Data Definitions
# ==========================================

# -- Participants --
part_headers = ["Entity", "Alias (Color)", "Typical Behavior & Role"]
part_rows = [
    ["**Commercials**", "Smart Money (🔴 Red)", "Producers and hedgers. **Contrarian:** They buy into falling markets (locking in cheap prices) and sell into rising markets."],
    ["**Large Speculators**", "Trend Followers (🔵 Blue)", "Hedge funds and CTAs. **Trend-following:** Typically hold the largest net longs at market tops and largest net shorts at bottoms."],
    ["**Small Speculators**", "Dumb Money (🟡 Yellow)", "Retail traders. They follow trends but notoriously hold peak positions exactly when the trend reverses."]
]

# -- Core Metrics --
core_headers = ["Indicator", "What it Measures", "How to Trade It"]
core_rows = [
    ["**COT Index**", "Scales net positioning from `0` to `100` over the lookback.", "Buy signal: Comms near 100 while Specs near 0. Sell signal: Exact opposite."],
    ["**Positioning Z-Score**", "Standard deviations from the historical mean.", "Scan Heatmap for readings beyond `+/- 2.0` to find extremes."],
    ["**Net Position % of OI**", "Raw net position / Total Open Interest.", "Gauges true magnitude (e.g., 50k contracts means more in a 100k OI market than 1M OI)."],
    ["**Movement Index**", "Velocity/Rate of change of Commercial positioning.", "Massive positive spikes during price dips signal aggressive dip-buying."],
    ["**WILLCO Index**", "Comm net position as % of total OI, indexed 0-100.", "Readings `>80` suggest accumulation. Readings `<20` suggest distribution."],
    ["**Large Trader Sentiment**", "Williams LATE index. Large Spec net position scaled `0` to `100` over a fixed 15-week window.", "Contrarian. Readings `>=80` mean funds are crowded long late in an advance. `<=20` means they are crowded short."],
    ["**COT MACD**", "MACD applied to Comm Net Position (leading momentum).", "Leading crossovers. Fast line crossing above Signal line predicts bottoms."],
    ["**Spearman Correlation**", "Rolling rank correlation between closing price and each group's net position, over the selected lookback.", "Commercials normally run negative because they sell into strength. A swing toward positive flags a hedging regime shift worth a closer look."],
    ["**Max Pain Curve**", "ETF options gravity well & Delta Intrinsic Value (ΔIV).", "Trade the magnetic pull of Dealer hedging toward the Max Pain strike."],
    ["**Rejection Scores**", "Intensity/Velocity of intraday/weekly price rejections.", "High Bear Rejection + Comm Longs = Shakeout trap. Buy the reversal."]
]

# -- Algorithmic Markers --
marker_headers = ["Chart Marker / Signal", "Trigger Condition", "Market Implication"]
marker_rows = [
    ["**4-Yr Buy / Sell**", "Highest/lowest net position in 208 weeks.", "Rare, high-conviction macro structural shift."],
    ["**Macro Bull / Bear**", "Sideways price + 25% OI collapse (Bull) or surge (Bear).", "Bull: Shorts covered. Bear: Resistance wall built."],
    ["**Struct Bull / Bear**", "Price breaks out directly through Comm intervention.", "Speculative momentum overrides smart money."],
    ["**Trend Continuation**", "Comms aggressively buy the dip or withdraw bids in freefall.", "Validates current trend direction."],
    ["**Market Bottoms**", "OI Divergence at lows.", "New accumulation or trapped shorts covering."],
    ["**Traps & Squeezes**", "Public squeezed or meets max Comm distribution.", "Reversal is imminent."],
    ["**Stealth Bull**", "Public abandons market (low OI) + Comms massively long.", "Quiet accumulation before structural liftoff."],
    ["**Exhaustion**", "Price hovering at highs, but OI steadily bleeding out.", "Profit taking without new money; trend is starving."],
    ["**Standard Capitulation**", "Floor-less drop + massive OI collapse.", "Public longs puking, smart money refusing to catch."],
    ["**Briese Stampede**", "Comms realize they are wrong and aggressively sell into a drop.", "Braking system removed. Violent trend continuation."]
]

# ==========================================
# 4. App Layout using dbc.Accordion
# ==========================================
layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H2("COT Analyzer Guide", className="mb-1", style={'color': 'var(--text-light)'}),
                dcc.Markdown(
                    "**Contact & Support:** `cotanalyzer [at] gmail [dot] com`",
                    style={'color': 'var(--text-muted, #adb5bd)', 'fontSize': '0.95rem', 'marginBottom': '20px'}
                ),
                create_markdown_card(intro_md)
            ], width=12, lg=10, className="mx-auto mt-4")
        ]),

        dbc.Row([
            dbc.Col([
                dbc.Accordion(
                    [
                        dbc.AccordionItem(
                            [create_markdown_card(participants_intro_md), create_bootstrap_table(part_headers, part_rows)],
                            title="1. Understanding the Market Participants",
                        ),
                        dbc.AccordionItem(
                            [create_markdown_card(core_metrics_intro_md), create_bootstrap_table(core_headers, core_rows)],
                            title="2. Core Metrics & Oscillators",
                        ),
                        dbc.AccordionItem(
                            [create_markdown_card(markers_intro_md), create_bootstrap_table(marker_headers, marker_rows)],
                            title="3. OI Alignment & Algorithmic Chart Markers",
                        ),
                        dbc.AccordionItem(
                            create_markdown_card(workflows_md),
                            title="4. Application Workflows for Finding Trades",
                        ),
                        dbc.AccordionItem(
                            create_markdown_card(backtest_md),
                            title="5. Algorithmic Backtesting",
                        ),
                    ],
                    start_collapsed=True,
                    always_open=True,
                    flush=True,
                    className="mt-4 mb-5 shadow-sm"
                )
            ], width=12, lg=10, className="mx-auto")
        ])
    ], fluid=True)
])
