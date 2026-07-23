#!/usr/bin/env python3

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

def plot_historical_intrinsic_evolution(ticker_symbol: str):
    # 1. Fetch live stock data
    ticker = yf.Ticker(ticker_symbol)
    expirations = ticker.options

    if not expirations:
        print(f"No options found for {ticker_symbol}")
        return

    # 2. Identify the "Upcoming Month" Expiration
    # We look for the first expiration that is at least 15 days out to skip immediate weeklies.
    today = datetime.today().date()
    target_expiry = expirations[0]
    for exp in expirations:
        exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
        if (exp_date - today).days > 15:
            target_expiry = exp
            break

    print(f"Targeting upcoming monthly expiration: {target_expiry}")

    # 3. Fetch historical daily prices since the "last contract expiration"
    # The last standard monthly expiration was roughly 1 month ago.
    hist_prices = ticker.history(period="1mo")
    if hist_prices.empty:
        print("Could not fetch historical stock prices.")
        return

    # 4. Fetch the Option Chain for the target expiration
    # NOTE: yfinance only provides CURRENT open interest.
    try:
        opt_chain = ticker.option_chain(target_expiry)

        calls = opt_chain.calls[["strike", "openInterest"]].copy().fillna(0)
        calls["type"] = "call"

        puts = opt_chain.puts[["strike", "openInterest"]].copy().fillna(0)
        puts["type"] = "put"

        df_options = pd.concat([calls, puts])
    except Exception as e:
        print(f"Error fetching options for {target_expiry}: {e}")
        return

    # Aggregate current open interest by strike and type
    df_grouped = df_options.groupby(["strike", "type"])["openInterest"].sum().reset_index()

    # 5. Generate the Line Chart
    plt.figure(figsize=(14, 8))

    # Setup a colormap to show the progression of time (Oldest = Light Blue, Newest = Dark Blue)
    colors = cm.Blues(np.linspace(0.4, 1, len(hist_prices)))

    # Iterate through each trading day in the last month
    for i, (date, row) in enumerate(hist_prices.iterrows()):
        spot_price = row['Close']
        date_str = date.strftime('%b %d')

        temp_df = df_grouped.copy()

        # Calculate Intrinsic Value using the historical daily close price
        temp_df["Intrinsic Value"] = np.where(
            temp_df["type"] == "call",
            np.maximum(0, spot_price - temp_df["strike"]),
            np.maximum(0, temp_df["strike"] - spot_price)
        )

        # Calculate Notional (Intrinsic * Current OI * 100)
        temp_df["Notional Intrinsic"] = temp_df["Intrinsic Value"] * temp_df["openInterest"] * 100

        # Group by strike to combine Call and Put notional values for the same strike
        strike_totals = temp_df.groupby("strike")["Notional Intrinsic"].sum()

        # Filter out strikes with zero value to focus the chart
        strike_totals = strike_totals[strike_totals > 0]

        if not strike_totals.empty:
            # Highlight the most recent day (today/yesterday) with a thicker, distinct line
            is_latest = (i == len(hist_prices) - 1)
            linewidth = 3 if is_latest else 1.5
            color = 'red' if is_latest else colors[i]
            alpha = 1.0 if is_latest else 0.7

            label_str = f"{date_str} (${spot_price:.2f})"

            plt.plot(
                strike_totals.index,
                strike_totals.values,
                marker='.' if is_latest else None,
                color=color,
                linewidth=linewidth,
                alpha=alpha,
                label=label_str
            )

    # Add Current Stock Price reference line (from the very last day in our history)
    current_price = hist_prices["Close"].iloc[-1]
    plt.axvline(
        x=current_price,
        color="black",
        linestyle="--",
        linewidth=2,
        label=f"Current Spot Price (${current_price:.2f})"
    )

    # Formatting and aesthetics
    plt.title(f"{ticker_symbol} Options: Daily Evolution of Notional Intrinsic Value\n(Expiry: {target_expiry} | Assuming Constant OI)", fontsize=14, fontweight="bold")
    plt.xlabel("Strike Price ($)", fontsize=12)
    plt.ylabel("Notional Intrinsic Value ($)", fontsize=12)

    # Format Y-axis as currency
    ax = plt.gca()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

    plt.grid(True, linestyle=":", alpha=0.6)

    # Place the legend outside the plot, organized in multiple columns if there are many days
    plt.legend(title="Trading Days", bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8, ncol=2)
    plt.tight_layout()

    plt.show()

if __name__ == "__main__":
    # Requirements: pip install yfinance pandas matplotlib numpy
    plot_historical_intrinsic_evolution("GOLD")