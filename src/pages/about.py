import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import constants as const
import textwrap

# Register this file as a page
dash.register_page(__name__, path='/about')

# textwrap.dedent removes the leading whitespace from the string so
# Dash doesn't accidentally treat it as a "code block"
content = textwrap.dedent("""
# COT Analyzer Guide according to Gemini

This application, **COT Analyzer**, is a powerful tool for futures traders to visualize and interpret the weekly Commitments of Traders (COT) Legacy reports published by the CFTC. Because raw COT data is composed of absolute open interest and position sizes, it is difficult to use for trading out of the box.

This app transforms that raw data into normalized, actionable indicators (Indexes, Z-Scores, Oscillators) that can be plotted against closing prices to identify market extremes, trend exhaustion, and impending reversals.

Here is a comprehensive guide on how to interpret the data, use the app's specific plots, and integrate these insights into a futures trading strategy.

---

## 1. Understanding the Market Participants
To use the application effectively, you must understand the three categories of traders tracked in the legacy COT report, which are color-coded in the app's charts:

* **Commercials (Red in app):** Also known as the "Smart Money." These are producers, merchants, and large hedgers who deal with the physical commodity. They are typically **contrarian**. They buy into falling markets (to lock in cheap prices) and sell into rising markets (to lock in high selling prices).
* **Large Speculators (Blue in app):** Also known as "Trend Followers." These are hedge funds, CTAs, and large institutions trading for profit. They are **trend-following** and typically hold the largest net long positions at market tops and the largest net short positions at market bottoms.
* **Small Speculators (Yellow in app):** Often referred to as "Dumb Money." These are retail traders. They tend to follow trends but are notorious for holding peak positions exactly when the trend is about to reverse.

---

## 2. Key Metrics & Plots in the Application
The application normalizes the raw position data over user-defined **Lookback Periods** (e.g., 26 weeks, 52 weeks, or Custom lengths mapped in the `params.yaml` file). Here is how to use the available plots in the **Graphs** and **Analysis** tabs:

### A. Positioning Index (COT Index)
* **What it is:** A stochastics-style calculation that scales net positioning between `0` and `100` over the selected lookback period.
    * `100` = Most net long (or least net short) they have been in the lookback period.
    * `0` = Most net short (or least net long) they have been in the lookback period.
* **How to Trade it:** Look for divergence and extremes. A classic buy signal (bullish setup) occurs when the Commercial Index is near `100` (they are buying heavily) while Large and Small Speculator Indexes are near `0` (they are heavily short). A sell signal (bearish setup) is the exact opposite.

### B. Positioning Z-Score
* **What it is:** Measures how many standard deviations the current net position is away from the historical mean over the lookback period.
* **How to Trade it:** Any Z-Score reading above `+2.0` or below `-2.0` indicates an extreme statistical deviation. The app's **Heatmap** page is specifically designed to let you scan across whole asset classes (e.g., all Grains or all Metals) to instantly spot assets with Z-scores beyond `+/- 2.0`.

### C. WILLCO (Williams Commercial Index)
* **What it is:** Created by Larry Williams, this plot looks specifically at the Commercials' net position *as a percentage of total Open Interest*, and then indexes it from 0 to 100.
* **How to Trade it:** It isolates the "Smart Money." Readings above `80` suggest Commercials are heavily accumulated and a bullish reversal is likely. Readings below `20` suggest they are distributing/shorting, warning of a bearish top. The app draws horizontal threshold lines to help you spot these zones.

### D. Tension Oscillator
* **What it is:** A custom metric calculated as `Large Spec Net / Abs(Commercial Net)`, which is then Z-scored. It measures the "strain" or imbalance between the trend-followers and the hedgers.
    * a high positive z-score means the Large Specs are stretched to an extreme long position and the Commercials are stretched to an extreme short position. Therefore, a high positive tension z-score is a bearish signal indicating an overbought, crowded long trade that is ripe for a reversal.
    * a low negative z-score means the Large Specs are stretched to an extreme short position and the Commercials are stretched to an extreme long position.
When that "rubber band snaps back" in the direction of the Commercials, it results in downward price action.
* **How to Trade it:** High tension indicates that Large Specs are aggressively fighting the Commercials. When tension reaches extreme standard deviations, the "rubber band" is stretched to its limit and is prone to snap back, usually in the direction of the Commercials' positioning.

### E. Net Position % of OI
* **What it is:** Simply the raw net position divided by total Open Interest.
* **How to Trade it:** Useful for understanding the true magnitude of a position. A 50,000 contract net long position means much more in a market with 100,000 total open interest than in a market with 1,000,000 open interest.

---

## 3. Application Workflows for Finding Trades

### Step 1: The Top-Down Scan (Using the Heatmap)
Start your weekend analysis on the **Heatmap** page.
* Set the layout to "Both - Stacked" and select an Asset Class (e.g., Fixed Income, Currencies).
* **What to look for:** Look for deep green or deep red squares. If you see an asset where Commercials have a Z-Score of `+2.5` (Green) and Large Specs have a Z-Score of `-2.2` (Red), you have found a market ripe for a **bullish reversal**.

### Step 2: Validating the Setup (Using Analysis / Graphs)
Move to the **Analysis** or **Graphs** tab, select the specific asset you found in Step 1, and overlay the **Positioning Index** with the **Price** line.
* **Use the "Setup Highlight" Feature:** In the Options tab, you can enable "Setup Highlight" (e.g., `95 5` or `90 10`). When you go back to the charts, the app will automatically draw shaded vertical boxes (Red or Green) where Commercials were `>= 95` and Specs were `<= 5`.
* Look at historical highlights on the chart to see how price reacted the last time positioning was this stretched.

### Step 3: Triggering the Trade (Price Confirmation)
**Crucial Rule:** COT data is a *macro/leading indicator*, not a timing tool. Commercials have deep pockets and can be "early" to a reversal for weeks or even months.
* Do not buy simply because the Commercial Index is at 100.
* **Wait for Price Action:** Drop down to a daily chart on your trading platform. Wait for a technical signal that agrees with the COT data (e.g., a break of a trendline, a moving average crossover, or a bullish divergence on an RSI/MACD).
* If the COT data is extremely bullish, only look for technical buy setups and ignore technical short setups.

---

## 4. Advanced: Algorithmic Backtesting
If you are a systematic trader, the application includes a **"Download Real Test Data"** button in the **Options** tab. This generates CSV "Event Lists" containing the normalized COT Index and Net Position data for every asset. You can import these directly into platforms like *RealTest* or *Amibroker* to backtest quantitative strategies (e.g., "Buy when Price > 200 SMA AND Commercial Index > 90").
""")

layout = html.Div([
    dbc.Container([
        dbc.Row([
            dbc.Col([
                html.Div([
                    dcc.Markdown(
                        content,
                        style={'color': const.BRIGHTER_TEXT_COLOR, 'padding': '30px', 'fontSize': '1.1rem'}
                    )
                ], className="bg-dark rounded mt-4 mb-5", style={'border': '1px solid #444', 'boxShadow': '0 4px 8px rgba(0,0,0,0.5)'})
            ], width=12, lg=10, className="mx-auto") # Centers the column and gives it a nice width on large screens
        ])
    ], fluid=True)
])
