"""Equity index futures on the E-mini by default, with the Combined basis alongside.

cotmetrics builds both frames and, when asked, the "Equities Combined" class of twins
(cotmetrics.contracts). What this app owns is the default, turning the class on, the CMR
lookback option, the dashed overlay of the other reading on the index panel, and keeping
the twins out of the Board's one ranking.
"""
import types

import cotmetrics.contracts as contracts
import pandas as pd
from plotly.subplots import make_subplots

from components import controls
from components.plot_traces import add_contracts_overlay


class _Indexer:
    def __init__(self):
        self.calls = []
        self.es = types.SimpleNamespace(custom_lookback=28, cmr_lookback=26,
                                        emini_df=pd.DataFrame({"x": [1]}), twin_of=None)
        self.es_c = types.SimpleNamespace(custom_lookback=28, cmr_lookback=26,
                                          emini_df=None, twin_of="13874A")
        self.gc = types.SimpleNamespace(custom_lookback=26, cmr_lookback=24, emini_df=None,
                                        twin_of=None)

    def get_instrument_from_name(self, name):
        return {"S&P 500": self.es, "S&P 500 (Combined)": self.es_c,
                "Gold": self.gc}.get(name)

    def get_symbols_data(self, name, lookback, basis, contracts=None):
        self.calls.append((name, lookback, basis, contracts))
        return pd.DataFrame({"Comms Idx": [10.0]})


def _stub(monkeypatch):
    import cotmetrics.indexer as indexer_mod
    ix = _Indexer()
    monkeypatch.setattr(indexer_mod, "get_indexer", lambda: ix)
    return ix


def test_the_per_market_families_resolve_per_market(monkeypatch):
    _stub(monkeypatch)
    monkeypatch.setattr(controls, "lookback_allowed", lambda: True)
    assert controls.lookback_weeks(controls.resolve("custom"), "S&P 500") == 26
    assert controls.lookback_weeks(controls.resolve("npf"), "S&P 500") == 28
    assert controls.lookback_weeks("CMR", "S&P 500") == 26
    assert controls.lookback_weeks("Custom", "S&P 500") == 28


def test_other_contracts_frame_is_the_other_reading_of_the_market(monkeypatch):
    ix = _stub(monkeypatch)
    frame, label = controls.other_contracts_frame("S&P 500", "CMR", "raw")
    assert label == "Combined" and frame is not None
    assert ix.calls[-1] == ("S&P 500", "CMR", "raw", contracts.COMBINED)
    frame, label = controls.other_contracts_frame("S&P 500 (Combined)", "CMR", "raw")
    assert label == "E-mini" and frame is not None
    assert ix.calls[-1] == ("S&P 500", "CMR", "raw", contracts.EMINI)
    assert controls.other_contracts_frame("Gold", "CMR", "raw") == (None, None)


def test_overlay_draws_three_dashed_legs_under_one_legend_entry():
    alt = pd.DataFrame({"c": [1.0, 2.0], "l": [3.0, 4.0], "s": [5.0, 6.0]},
                       index=pd.date_range("2026-01-06", periods=2, freq="7D"))
    fig = add_contracts_overlay(make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]]),
                                alt, "c", "l", "s", 1, 1,
                                ["#112233", "#445566", "#778899"], "Combined")
    assert len(fig.data) == 3
    assert [t.showlegend for t in fig.data] == [True, False, False]
    assert {t.legendgroup for t in fig.data} == {"combined contracts"}
    assert all(t.line.dash == "dash" for t in fig.data)


def test_app_defaults_to_the_emini_with_the_combined_class():
    import app_cot  # noqa: F401  (importing it sets the process defaults)
    assert contracts.default_contracts() == contracts.EMINI
    assert contracts.combined_class_enabled()


def test_most_crowded_order_ranks_the_book_without_the_twins():
    from components import board_traces as bt

    def read(asset, cls, value):
        return types.SimpleNamespace(asset=asset, asset_class=cls, value=value)

    reads = [read("S&P 500", "Equities", 10), read("Gold", "Metals", 50),
             read("S&P 500 (Combined)", contracts.COMBINED_CLASS, 99)]
    scores = {"S&P 500": 10, "Gold": 50, "S&P 500 (Combined)": 99}
    original = bt.crowding_score
    bt.crowding_score = lambda r: scores[r.asset]
    try:
        rows, skipped = bt.build_rows(reads, order=bt.ORDER_FLAT)
    finally:
        bt.crowding_score = original
    assert skipped == []
    assert [(r.kind, r.label) for r in rows] == [
        ("market", "Gold"), ("market", "S&P 500"), ("spacer", ""),
        ("class", contracts.COMBINED_CLASS), ("market", "S&P 500 (Combined)")]
