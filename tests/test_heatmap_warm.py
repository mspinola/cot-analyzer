"""The heatmap warmer fills exactly the join caches a cold render reads.

Same contract as test_crowd_warm, for the same reason: the warmer and the render
path share no code that forces them to agree. `render_heatmap_layout` joins
`_spec_risk` and `_leg_offside` per market keyed on the store's newest date;
nothing but these tests would notice if the warm dropped one of the two joins or
started keying on a different date, and either drift shows up only as first
visitors quietly paying the cold price-store reads again.
"""
import dash
import pandas as pd

# `dash.register_page` runs at import of the page module and refuses to run without
# an app. The warmer is what is under test, not the routing.
dash.Dash(__name__, use_pages=True, pages_folder='')

import pages.analytics.heatmap as heatmap  # noqa: E402


class _Indexer:
    def get_available_dates(self):
        return ["2026-08-18", "2026-08-11"]

    def get_asset_classes(self):
        return ["Metals"]


def test_warm_touches_both_joins_for_every_market(monkeypatch):
    warmed = []
    monkeypatch.setattr(heatmap, "get_indexer", lambda: _Indexer())
    monkeypatch.setattr(
        heatmap, "get_matrix_data",
        lambda classes, lookback, target: pd.DataFrame(
            [{"Asset": "Gold"}, {"Asset": "Silver"}]))
    monkeypatch.setattr(
        heatmap, "_spec_risk",
        lambda asset, newest: warmed.append(("risk", asset, newest)))
    monkeypatch.setattr(
        heatmap, "_leg_offside",
        lambda asset, newest: warmed.append(("offside", asset, newest)))

    heatmap.warm_caches()

    assert {(j, a) for j, a, _ in warmed} == {
        (j, a) for j in ("risk", "offside") for a in ("Gold", "Silver")}
    # Keyed on the store's NEWEST date, the same key the render path uses: warming
    # any other date fills entries no request will ever read.
    assert {d for _, _, d in warmed} == {"2026-08-18"}


def test_warm_survives_an_empty_store(monkeypatch):
    class _Empty:
        def get_available_dates(self):
            return []

        def get_asset_classes(self):
            return []

    monkeypatch.setattr(heatmap, "get_indexer", lambda: _Empty())
    heatmap.warm_caches()  # a store with no weeks is a no-op, never a traceback


def test_warm_swallows_and_logs_a_failure(monkeypatch):
    def boom():
        raise RuntimeError("store went away")

    monkeypatch.setattr(heatmap, "get_indexer", boom)
    heatmap.warm_caches()  # the warmer must never be able to take the server down


def test_divergence_warm_fills_the_gap_histories(monkeypatch):
    """Same contract as the other page warmers: every market touched, keyed on
    the newest date, empty store a no-op, failure swallowed."""
    import pages.analytics.divergence as divergence

    warmed = []
    monkeypatch.setattr(divergence, "get_indexer", lambda: _Indexer())
    monkeypatch.setattr(
        divergence, "get_matrix_data",
        lambda classes, lookback, target: pd.DataFrame(
            [{"Asset": "Gold"}, {"Asset": "Silver"}]))
    monkeypatch.setattr(
        divergence, "_gap_history",
        lambda asset, newest: warmed.append((asset, newest)))

    divergence.warm_caches()
    assert set(warmed) == {("Gold", "2026-08-18"), ("Silver", "2026-08-18")}

    def boom():
        raise RuntimeError("store went away")
    monkeypatch.setattr(divergence, "get_indexer", boom)
    divergence.warm_caches()  # never allowed to take the server down
