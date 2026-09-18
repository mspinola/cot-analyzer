"""The max-pain star sits on the stored real strike, not the grid's argmin.

The options snapshot stores two things that name the max-pain price: a 200-point
simulated curve, and `MaxPainStrike`, the curve's minimum snapped to a strike the
chain actually has. Both panels used to take the grid argmin and ignore the stored
strike, so the star could sit between two real strikes. These pin that the stored
strike wins, that its payout is read off the curve at that strike, and that a
snapshot written before the column existed still resolves (to the grid argmin).

Store-free: the parquet is written to tmp_path and the history dir monkeypatched.
"""

import cotmetrics.options_data as od
import numpy as np
import pandas as pd
from plotly.subplots import make_subplots

import components.plot_options as po


def _snapshot(date, underlying=100.0, max_pain=96.3, n=200):
    grid = np.linspace(underlying * 0.8, underlying * 1.2, n)
    # A V-shaped payout with its floor at 96.5, a grid point the strike ladder does
    # not have. The real chain's nearest strike is 96.3.
    payout = np.abs(grid - 96.5) * 10 + 5
    return pd.DataFrame({
        "Date": date, "Expiry": "2026-10-16", "UnderlyingPrice": underlying,
        "SimulatedStrike": grid, "IntrinsicValue_M": payout,
        "MaxPainStrike": max_pain, "ETF_Proxy": "SPY",
    })


def test_point_reads_the_stored_strike_and_interpolates_its_payout():
    df = _snapshot("2026-09-17")
    strike, payout = po.max_pain_point(df)
    assert strike == 96.3
    assert payout == np.interp(96.3, df["SimulatedStrike"], df["IntrinsicValue_M"])
    # And it is not the grid argmin, which is the point this exists to fix.
    assert strike != df.loc[df["IntrinsicValue_M"].idxmin(), "SimulatedStrike"]


def test_point_falls_back_to_the_grid_when_the_column_is_missing_or_nan():
    df = _snapshot("2026-09-17")
    grid_min = df.loc[df["IntrinsicValue_M"].idxmin()]
    expected = (grid_min["SimulatedStrike"], grid_min["IntrinsicValue_M"])
    assert po.max_pain_point(df.drop(columns="MaxPainStrike")) == expected
    assert po.max_pain_point(df.assign(MaxPainStrike=np.nan)) == expected


class _Instrument:
    symbol = "ES"


class _Indexer:
    def get_instrument_from_name(self, name):
        return _Instrument()


def _write_history(tmp_path, monkeypatch, frames):
    pd.concat(frames).to_parquet(tmp_path / "ES_options_history.parquet")
    monkeypatch.setattr(od, "options_history_dir", lambda: tmp_path)
    monkeypatch.setattr(po, "get_indexer", lambda: _Indexer())


def test_star_and_dashed_line_sit_on_the_stored_strike(tmp_path, monkeypatch):
    _write_history(tmp_path, monkeypatch,
                   [_snapshot("2026-09-16", max_pain=97.1), _snapshot("2026-09-17")])
    fig = make_subplots(rows=1, cols=1)
    fig = po.get_max_pain_plot(fig, "S&P 500", 1, 1)
    stars = [t for t in fig.data if t.name == "Max Pain Strike"]
    assert [t.x[0] for t in stars] == [97.1, 96.3]
    latest = stars[-1]
    assert latest.marker.symbol == "star"
    hlines = [s for s in fig.layout.shapes if s.type == "line" and s.y0 == s.y1]
    assert latest.y[0] in {s.y0 for s in hlines}


def test_history_panel_measures_premium_against_the_stored_strike(tmp_path, monkeypatch):
    _write_history(tmp_path, monkeypatch, [_snapshot("2026-09-17", underlying=100.0)])
    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
    fig = po.get_max_pain_historical_plot(fig, "S&P 500", 1, 1)
    bars = next(t for t in fig.data if t.type == "bar")
    assert bars.y[0] == (100.0 - 96.3) / 96.3 * 100
