"""The merged Analysis page: one page, two views, nothing paid for twice.

/graphs folded into /analysis (the panel stack and the market grid shared a
registry, an assembler and most of a control card). What is worth pinning:

* Both views' controls exist in one layout, each set sharing one row inside its
  own div, and only the active view's div shows: hidden rather than unmounted,
  so a hidden control keeps its value and flipping back lands where you left.
* The inactive view's render callback returns an empty container WITHOUT
  touching the store: two full figure builds per control change would double
  the page's cost for a view nobody is looking at.
* The old address survives: /graphs 301s to /analysis?view=grid, and ?view=
  deep-links a view with the absence-never-resets rule every reader follows.

layout() reads the class list, so the indexer is stubbed: this suite runs
without a populated COTDATA_STORE.
"""
import dash
import dash_bootstrap_components as dbc
from dash import html

# `dash.register_page` runs at import of the page module and refuses to run
# without an app. The page's own logic is what is under test, not the routing.
dash.Dash(__name__, use_pages=True, pages_folder='')

import pages.analytics.analysis as analysis  # noqa: E402

STACK_CONTROL_IDS = {
    "analysis_asset_class_selector",
    "analysis_single_asset_filter_input",
    "analysis_plot_selector",
}
GRID_CONTROL_IDS = {
    "graphs_asset_class_selector",
    "graphs_multi_equity_selector_input",
    "graphs_plot_selector_input",
    "graphs_model_selector",
}
SHARED_CONTROL_IDS = {
    "analysis_view_selector",
    "analysis_lookback_selector",
    "analysis_columns_selector",
}


class _StubIndexer:
    def get_asset_classes(self):
        return ["Equities", "Grains", "Metals"]

    def get_default_asset_class(self):
        return "Equities"

    def get_assets_for_asset_class(self, asset_class):
        return ["DOW", "Russell"]


def _walk(node, found=None, row=None, div=None):
    """Every control id, mapped to (its enclosing dbc.Row, its enclosing div id)."""
    found = {} if found is None else found
    if isinstance(node, (list, tuple)):
        for child in node:
            _walk(child, found, row, div)
        return found
    if node is None or isinstance(node, str):
        return found
    if isinstance(node, dbc.Row):
        row = id(node)
    node_id = getattr(node, "id", None)
    if isinstance(node_id, str) and node_id.endswith("_controls"):
        div = node_id
    if isinstance(node_id, str):
        found[node_id] = (row, div)
    return _walk(getattr(node, "children", None), found, row, div)


def _layout(monkeypatch):
    monkeypatch.setattr(analysis, "get_indexer", lambda: _StubIndexer())
    return analysis.layout()


def test_both_views_controls_are_present(monkeypatch):
    found = _walk(_layout(monkeypatch))
    for control in STACK_CONTROL_IDS | GRID_CONTROL_IDS | SHARED_CONTROL_IDS:
        assert control in found, control


def test_each_views_controls_share_one_row_in_their_own_div(monkeypatch):
    found = _walk(_layout(monkeypatch))
    for ids, div in ((STACK_CONTROL_IDS, "analysis_stack_controls"),
                     (GRID_CONTROL_IDS, "analysis_grid_controls")):
        rows = {found[c][0] for c in ids}
        assert len(rows) == 1, f"{div} controls span {len(rows)} rows"
        assert {found[c][1] for c in ids} == {div}
    # The shared row belongs to neither div, or hiding a view would take the
    # lookback with it.
    assert {found[c][1] for c in SHARED_CONTROL_IDS} == {None}


def test_the_page_opens_on_the_stack(monkeypatch):
    """The grid div ships hidden and the toggle mirrors that; the stack is the
    page /analysis always was."""
    found_hidden = {}

    def collect(node):
        if isinstance(node, (list, tuple)):
            for child in node:
                collect(child)
            return
        if node is None or isinstance(node, str):
            return
        node_id = getattr(node, "id", None)
        if isinstance(node_id, str) and node_id.endswith("_controls"):
            found_hidden[node_id] = getattr(node, "hidden", None)
        collect(getattr(node, "children", None))

    collect(_layout(monkeypatch))
    assert found_hidden["analysis_grid_controls"] is True
    assert found_hidden.get("analysis_stack_controls") in (None, False)


def test_the_old_graphs_address_redirects_to_the_grid():
    """A /graphs bookmark is a request for the market grid, so the 301 (an
    explicit route in app_cot; Dash's redirect_from cannot carry a query) must
    name the view, not just the page. Pinned against the source because
    importing app_cot builds the real app and poisons the pages package for
    every test module after this one (the lesson test_cache_policy carries).
    The unknown-path guard admitting /graphs is pinned in test_routing."""
    import pathlib

    assert dash.page_registry["pages.analytics.analysis"]["path"] == "/analysis"
    app_cot = (pathlib.Path(analysis.__file__).parents[2] / "app_cot.py").read_text()
    assert "@app.server.route('/graphs')" in app_cot
    assert "redirect('/analysis?view=grid', code=301)" in app_cot


def test_view_state_is_one_clientside_writer():
    """The ?view= reader, the visibility flip and the URL write-back live in ONE
    clientside function. The shape is the contract: split across a server
    callback and a clientside one, the page-load wave ran the visibility half
    with the default value and never re-ran it when the link reader's answer
    landed, so a ?view=grid load drew the grid under the stack's controls
    (observed live before this). JS logic is pinned by the live checks in the
    session log; what pytest can hold is that the split does not come back."""
    import pathlib

    text = pathlib.Path(analysis.__file__).read_text()
    assert text.count("Output('analysis_stack_controls', 'hidden')") == 1
    assert text.count("Output('analysis_view_selector', 'value')") == 1
    assert "__analysisViewApplied" in text


def test_the_inactive_view_renders_empty_without_touching_the_store(monkeypatch):
    """Both render callbacks fire on every relevant input; the one whose view is
    not showing must cost nothing. A raising indexer is the proof."""
    def explode():
        raise AssertionError("the inactive view read the store")
    monkeypatch.setattr(analysis, "get_indexer", explode)

    assert analysis.update_analysis_stack(
        "palette", "Gold", "Custom", ["index"], "2", "raw_pf",
        view=analysis.VIEW_GRID) == []
    assert analysis.get_cot_graphs(
        "palette", ["Gold"], "net_pos", "Custom", "raw_pf", "2",
        view=analysis.VIEW_STACK) == []


def test_the_model_note_stays_in_flow(monkeypatch):
    """The note renders under its select as a normal block: absolutely
    positioned it painted over whatever came next (the original page's bug)."""
    found = _walk(_layout(monkeypatch))
    assert "graphs_model_note" in found

    def find_note(node):
        if isinstance(node, (list, tuple)):
            for child in node:
                got = find_note(child)
                if got is not None:
                    return got
            return None
        if node is None or isinstance(node, str):
            return None
        if getattr(node, "id", None) == "graphs_model_note":
            return node
        return find_note(getattr(node, "children", None))

    note = find_note(_layout(monkeypatch))
    assert isinstance(note, html.Div)
    style = note.style or {}
    assert style.get("position") in (None, "static")
