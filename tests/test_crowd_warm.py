"""The boot warmer fills exactly the caches a cold render reads.

Pinned because the warmer and the render path share no code that forces them to
agree: `warm_caches` walks the universe calling `_market_indices` for every basis,
and nothing but these tests would notice if a new model's basis were left out, or if
the warm stopped keying on the store's newest date. Either drift is invisible in a
green suite and shows up only as first visitors quietly paying cold renders again,
which is exactly the failure the warmer exists to remove.
"""
import cotmetrics.models as models
import dash
import pandas as pd

# `dash.register_page` runs at import of the page module and refuses to run without
# an app. The warmer is what is under test, not the routing, so an app with no pages
# folder is enough and keeps Dash from walking the tree.
dash.Dash(__name__, use_pages=True, pages_folder='')

import pages.analytics.crowd as crowd  # noqa: E402


class _Indexer:
    def get_available_dates(self):
        return ["2026-08-18", "2026-08-11"]

    def get_asset_classes(self):
        return ["Metals"]


def test_warm_touches_every_market_on_every_basis(monkeypatch):
    warmed = []
    monkeypatch.setattr(crowd, "get_indexer", lambda: _Indexer())
    monkeypatch.setattr(
        crowd, "get_matrix_data",
        lambda classes, lookback, target: pd.DataFrame(
            [{"Asset": "Gold"}, {"Asset": "Silver"}]))
    monkeypatch.setattr(
        crowd, "_market_indices",
        lambda asset, basis, newest: warmed.append((asset, basis, newest)))

    crowd.warm_caches()

    bases = {m.basis for m in models.MODELS}
    assert {(a, b) for a, b, _ in warmed} == {
        (a, b) for a in ("Gold", "Silver") for b in bases}
    # Keyed on the store's NEWEST date, the same key the render path uses: warming
    # any other date fills entries no request will ever read.
    assert {d for _, _, d in warmed} == {"2026-08-18"}


def test_warm_survives_an_empty_store(monkeypatch):
    class _Empty:
        def get_available_dates(self):
            return []

        def get_asset_classes(self):
            return []

    monkeypatch.setattr(crowd, "get_indexer", lambda: _Empty())
    crowd.warm_caches()  # a store with no weeks is a no-op, never a traceback


def test_warm_swallows_and_logs_a_failure(monkeypatch):
    def boom():
        raise RuntimeError("store went away")

    monkeypatch.setattr(crowd, "get_indexer", boom)
    crowd.warm_caches()  # the warmer must never be able to take the server down
