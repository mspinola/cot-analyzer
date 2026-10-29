"""The home board's PNG export: the board and its caption, not the teaching.

The export clones the container and re-opens every fold in the clone, which is
right for the Strip (its key is part of reading the picture) and was wrong here:
the home board's PNG carried the how-to-read paragraph whenever it was shared.
The page now marks that fold data-export="omit" and the shared exportBoardImage
drops anything so marked. Neither half does anything without the other, and
nothing else in the suite would notice either one going missing, so both are
pinned: the mark is where it should be in the layout, and the export still
honours it.
"""
import pathlib
import re

import cotmetrics.indexer
import dash
import pytest

# `dash.register_page` runs at import of the page module and refuses to run
# without an app; test_crowd_warm's reasoning, and its construction.
dash.Dash(__name__, use_pages=True, pages_folder='')

import pages.analytics.crowd as crowd  # noqa: E402

CLIENTSIDE = (pathlib.Path(__file__).resolve().parents[1]
              / "src" / "assets" / "clientside.js").read_text()


class _Indexer:
    """The two reads the layout makes (the week list and the asset classes), with
    the real methods' signatures. The layout is what is under test, not the store,
    and CI's store is empty."""

    def get_available_dates(self):
        return ["2026-10-20", "2026-10-13"]

    def get_asset_classes(self):
        return ["Metals", "Grains"]


@pytest.fixture(autouse=True)
def _no_store(monkeypatch):
    indexer = _Indexer()
    monkeypatch.setattr(crowd, "get_indexer", lambda: indexer)
    # controls.target_date_dropdown imports get_indexer at call time, from here.
    monkeypatch.setattr(cotmetrics.indexer, "get_indexer", lambda: indexer)


def _props(node):
    return node.to_plotly_json().get("props", {}) if hasattr(node, "to_plotly_json") else {}


def _walk(node, omitted=False):
    """(component, inside-an-omit-element) for every component under `node`."""
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from _walk(child, omitted)
        return
    if not hasattr(node, "to_plotly_json"):
        return
    omitted = omitted or _props(node).get("data-export") == "omit"
    yield node, omitted
    yield from _walk(_props(node).get("children"), omitted)


def _export_container():
    for node, _ in _walk(crowd.layout()):
        if _props(node).get("id") == "crowd_export_container":
            return node
    raise AssertionError("no crowd_export_container in the layout")


def _status(container, wanted_id):
    for node, omitted in _walk(container):
        if _props(node).get("id") == wanted_id:
            return omitted
    raise AssertionError(f"{wanted_id!r} is not inside the export container")


def test_the_how_to_read_fold_is_marked_out_of_the_png():
    container = _export_container()
    assert _status(container, {"type": "help_fold_toggle", "page": "crowd"}) is True
    assert _status(container, "crowd_help") is True


def test_the_caption_and_the_board_stay_in():
    """The caption carries the week and the basis, which the picture cannot say on
    its own; the board is the picture. Marking a parent of either would cut it."""
    container = _export_container()
    assert _status(container, "crowd_caption") is False
    assert _status(container, "crowd_display_container") is False


def _export_body():
    start = CLIENTSIDE.index("function exportBoardImage(")
    return CLIENTSIDE[start:CLIENTSIDE.index("\n}\n", start)]


def test_the_shared_export_removes_omitted_chrome_from_its_clone():
    body = _export_body()
    assert "[data-export=\"omit\"]" in body
    # Removed from the CLONE, not hidden on the live page (that would blank the
    # reader's screen for the length of the export).
    assert re.search(r"clone\.querySelectorAll\(OMIT\)[\s\S]{0,120}removeChild", body)


def test_omitted_figures_are_left_out_of_the_snapshots_too():
    """The snapshots replace the clone's plots by position. A figure inside an
    omitted element counted live but gone from the clone would shift every
    snapshot after it onto the wrong plot."""
    body = _export_body()
    assert re.search(r"\.filter\(function\(node\)\s*\{\s*return !node\.closest\(OMIT\)", body)
