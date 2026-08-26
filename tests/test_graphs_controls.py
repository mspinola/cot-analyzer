"""The graphs page control card.

Six controls that were laid out as two rows, which cost a strip of vertical space on a
page whose whole subject is a tall stack of charts. The property worth pinning is not
the widths or the order, both of which should stay free to change, but that the
controls share ONE row.

layout() reads the class list, so the indexer is stubbed: this suite runs without a
populated COTDATA_STORE and building a real one would need it.
"""
import dash_bootstrap_components as dbc

import pages.analytics.graphs as graphs

CONTROL_IDS = {
    "graphs_asset_class_selector",
    "graphs_multi_equity_selector_input",
    "graphs_plot_selector_input",
    "graphs_lookback_selector",
    "graphs_model_selector",
    "graphs_columns_selector",
}


class _StubIndexer:
    def get_asset_classes(self):
        return ["Equities", "Grains", "Metals"]

    def get_default_asset_class(self):
        return "Equities"

    def get_assets_for_asset_class(self, asset_class):
        return ["DOW", "Russell"]


def _rows_holding(node, found=None, row=None):
    """Every control id, mapped to the dbc.Row it sits in."""
    found = {} if found is None else found
    if isinstance(node, (list, tuple)):
        for child in node:
            _rows_holding(child, found, row)
        return found
    if node is None or isinstance(node, str):
        return found
    if isinstance(node, dbc.Row):
        row = id(node)
    node_id = getattr(node, "id", None)
    if isinstance(node_id, str) and node_id in CONTROL_IDS:
        found[node_id] = row
    return _rows_holding(getattr(node, "children", None), found, row)


def _layout(monkeypatch):
    monkeypatch.setattr(graphs, "get_indexer", lambda: _StubIndexer())
    return graphs.layout()


def test_every_control_is_present(monkeypatch):
    assert set(_rows_holding(_layout(monkeypatch))) == CONTROL_IDS


def test_the_controls_share_one_row(monkeypatch):
    """The regression: splitting these back into two rows. Nothing here pins widths or
    order, which should stay free to change."""
    rows = set(_rows_holding(_layout(monkeypatch)).values())
    assert len(rows) == 1, "the control card grew a second row"


def test_the_model_note_stays_in_flow(monkeypatch):
    """It used to hang on a negative margin clawing back the spacing between two rows.
    Out of flow it would paint over whatever came next, and it is only present for some
    plots, so the card has to reserve height for it."""
    found = {}

    def walk(node):
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        if node is None or isinstance(node, str):
            return
        if getattr(node, "id", None) == "graphs_model_note":
            found["style"] = node.style or {}
        walk(getattr(node, "children", None))

    walk(_layout(monkeypatch))
    assert found, "the model note is gone"
    assert found["style"].get("position") != "absolute"
    assert not str(found["style"].get("marginTop", "")).startswith("-")
