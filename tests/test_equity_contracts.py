"""Equity index futures on the E-mini by default, with the Combined basis alongside.

cotmetrics builds both frames (cotmetrics.contracts); what this app owns is the default,
the per-request choice, the CMR lookback option, and the two places Combined shows up
without switching: the dashed overlay on the index panel and the Heatmap marker.
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
                                        emini_df=pd.DataFrame({"x": [1]}))
        self.gc = types.SimpleNamespace(custom_lookback=26, cmr_lookback=24, emini_df=None)

    def get_instrument_from_name(self, name):
        return {"S&P 500": self.es, "Gold": self.gc}.get(name)

    def get_symbols_data(self, name, lookback, basis, contracts=None):
        self.calls.append((name, lookback, basis, contracts))
        return pd.DataFrame({"Comms Idx": [10.0]})


def _stub(monkeypatch):
    import cotmetrics.indexer as indexer_mod
    ix = _Indexer()
    monkeypatch.setattr(indexer_mod, "get_indexer", lambda: ix)
    return ix


def test_cmr_is_a_lookback_choice_resolved_per_market(monkeypatch):
    _stub(monkeypatch)
    assert "CMR" in controls.LOOKBACK_CHOICES
    assert controls.lookback_weeks("CMR", "S&P 500") == 26
    assert controls.lookback_weeks("Custom", "S&P 500") == 28


def test_other_contracts_frame_is_the_basis_not_chosen(monkeypatch):
    ix = _stub(monkeypatch)
    with contracts.use_contracts(contracts.EMINI):
        frame, label = controls.other_contracts_frame("S&P 500", "CMR", "raw")
    assert label == "Combined" and frame is not None
    assert ix.calls[-1] == ("S&P 500", "CMR", "raw", contracts.COMBINED)
    with contracts.use_contracts(contracts.COMBINED):
        _, label = controls.other_contracts_frame("S&P 500", "CMR", "raw")
    assert label == "E-mini"
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


def test_app_defaults_to_the_emini_and_reads_the_cookie_per_request():
    import app_cot
    assert contracts.default_contracts() == contracts.EMINI
    with app_cot.app.server.test_request_context(
            "/", headers={"Cookie": f"{app_cot.CONTRACTS_COOKIE}=combined"}):
        app_cot.apply_contracts_choice()
        assert contracts.current_contracts() == contracts.COMBINED
    with app_cot.app.server.test_request_context("/"):
        app_cot.apply_contracts_choice()
        assert contracts.current_contracts() == contracts.EMINI
