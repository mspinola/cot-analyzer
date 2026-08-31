"""The shared control kit, and the drift it exists to prevent.

The builders are trivial on purpose; what these tests pin is the contract that
makes them worth having: semantic fields (options, default, persistence,
tooltips) have exactly one home, geometry stays overridable, and no page slides
back to rebuilding the shared literals inline.
"""

import importlib
import pathlib
import sys

import pytest

import viz_constants as vc
from components import controls

PAGES_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "pages"


def test_module_imports_without_the_data_layer():
    """Only the target-date pieces may touch the indexer, and only when called.

    Pages call the builders inside layout(); the module itself is imported by
    every page at import time, where CI's store is an empty directory.
    """
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(controls)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


def test_lookback_select_semantics():
    sel = controls.lookback_select('x_lookback')
    assert [o["value"] for o in sel.options] == list(controls.LOOKBACK_CHOICES)
    assert sel.value == "Custom"
    assert sel.persistence == 'session'


def test_overrides_touch_geometry_not_semantics():
    sel = controls.lookback_select('x_lookback', size="sm",
                                   style={'width': '120px'})
    assert sel.size == "sm" and sel.style == {'width': '120px'}
    assert [o["value"] for o in sel.options] == list(controls.LOOKBACK_CHOICES)
    # And an explicit persistence=None turns the browser copy off (the Strip and
    # Crowd ride the global store instead).
    assert controls.lookback_select('x', persistence=None).persistence is None


@pytest.mark.parametrize("choices", [vc.MODEL_CHOICES, vc.MODEL_VIEW_CHOICES])
def test_model_select_offers_the_choices_with_tooltips(choices):
    """Tooltips on every option: they existed on three pages and not the other
    two, which is exactly the drift a shared builder is for."""
    sel = controls.model_select('x_model', choices=choices)
    assert [o["value"] for o in sel.options] == list(choices)
    assert all(o.get("title") for o in sel.options)


def test_no_page_rebuilds_the_lookback_options():
    """The tripwire. The literal below was written out nine times before the
    kit existed; a page that reintroduces it has forked the vocabulary again.
    Exposure's deliberately different lookback ("All history", lowercase
    "weeks") does not trip this, and that is correct: it is a different
    control, documented as such.
    """
    offenders = [p.name for p in PAGES_DIR.rglob("*.py")
                 if '{"label": "26 Weeks"' in p.read_text()]
    assert offenders == [], offenders


def test_label_is_the_uppercase_caption_style():
    lbl = controls.label("Lookback")
    assert lbl.children == "Lookback"
    assert lbl.style["textTransform"] == "uppercase"
    # Geometry overrides merge here too (the chart pages keep their mb spacing).
    assert controls.label("X", marginBottom="0.5rem").style["marginBottom"] == "0.5rem"


# ── the as-of week ────────────────────────────────────────────────────────────
#
# The scenarios below are the ones next_date_selection pinned before the store
# existed, restated against the store's two halves: what a selection is stored
# AS (week_for_store) and what a stored value resolves TO (resolve_week). The
# split is the whole design: "tracking the newest" is stored as None, so a
# release moves every tracking page at once, while a parked week is stored as
# itself and stays put.

WEEKS = ["2026-08-11", "2026-08-04", "2026-07-28"]   # newest first


def test_picking_the_newest_week_stores_tracking_not_the_date():
    """The regression the old per-control arithmetic existed for. Nobody chose
    to sit on the newest week, so it must follow the next release; storing its
    concrete date would pin every page the moment a release made it old."""
    assert controls.week_for_store("2026-08-11", WEEKS) is None
    assert controls.resolve_week(None, WEEKS) == "2026-08-11"
    # ...and after a release, tracking lands on the NEW newest.
    assert controls.resolve_week(None, ["2026-08-18"] + WEEKS) == "2026-08-18"


def test_a_deliberately_chosen_older_week_is_stored_and_stays_parked():
    """Picking a week is a decision. A release must not yank the reader off it."""
    assert controls.week_for_store("2026-07-28", WEEKS) == "2026-07-28"
    assert controls.resolve_week("2026-07-28", ["2026-08-18"] + WEEKS) == "2026-07-28"


def test_a_stored_week_this_history_does_not_hold_falls_back_to_the_newest():
    assert controls.resolve_week("1999-01-01", WEEKS) == "2026-08-11"
    assert controls.week_for_store("1999-01-01", WEEKS) is None


def test_an_empty_index_changes_nothing():
    """Mid-sync the store can serve an empty date list; neither half may turn
    that into a stored claim or a drawn value."""
    assert controls.week_for_store("2026-08-11", []) is None
    assert controls.resolve_week("2026-08-11", []) is None
    assert controls.resolve_week(None, []) is None


# ── URL deep links ────────────────────────────────────────────────────────────

def test_a_full_deep_link_sets_all_three_stores():
    params = controls.deep_link_params(
        "?date=2026-07-28&model=npf&lookback=26", dates=WEEKS)
    assert params == {'global_week_store': "2026-07-28",
                      'global_model_store': "npf",
                      'global_lookback_store': "26"}


def test_a_bare_url_touches_nothing():
    """Navbar navigation produces URLs with no query at all; a click that reset
    the session's parked week or chosen model would make navigation
    destructive. Absence means "leave the store alone"."""
    assert controls.deep_link_params("", dates=WEEKS) == {}
    assert controls.deep_link_params(None, dates=WEEKS) == {}
    assert controls.deep_link_params("?asset=Gold", dates=WEEKS) == {}


def test_a_link_to_the_newest_week_stores_tracking():
    """Same normalization as picking it by hand: the URL names a date, but what
    is worth remembering is "the newest", or the link would pin the session the
    moment a release made that date old."""
    params = controls.deep_link_params(f"?date={WEEKS[0]}", dates=WEEKS)
    assert params == {'global_week_store': None}


def test_garbage_params_are_dropped_not_stored():
    """A week the history does not hold would render as the newest while the
    URL kept asserting the date, so it is refused at the door; same for an
    unknown model or lookback."""
    assert controls.deep_link_params("?date=1999-01-01", dates=WEEKS) == {}
    assert controls.deep_link_params("?model=alpha_zero", dates=WEEKS) == {}
    assert controls.deep_link_params("?lookback=13", dates=WEEKS) == {}


def test_the_overlay_view_is_a_legal_model_param():
    """MODEL_BOTH is honoured: the chart pages draw it, and the board pages'
    own sync resolves it to the baseline model, exactly as when another page
    writes it to the store."""
    params = controls.deep_link_params("?model=both", dates=WEEKS)
    assert params == {'global_model_store': "both"}


def test_asset_from_search_decodes_the_name():
    assert controls.asset_from_search("?asset=Japanese%20Yen") == "Japanese Yen"
    assert controls.asset_from_search("?asset=Japanese+Yen") == "Japanese Yen"
    assert controls.asset_from_search("?date=2026-07-28") is None
    assert controls.asset_from_search("") is None


class _Instrument:
    def __init__(self, asset_class):
        self.asset_class = asset_class


class _AssetsIndexer:
    _known = {"Gold": "Metals", "Silver": "Metals", "Corn": "Grains"}

    def get_instrument_from_name(self, name):
        cls = self._known.get(name)
        return _Instrument(cls) if cls else None


def test_forced_assets_resolves_names_and_their_classes(monkeypatch):
    """The grid's ?assets= link: unknown names drop rather than fail (a market
    renamed after the link was copied must not blank the board), classes ride
    along deduplicated so the link is self-sufficient, and a link naming
    nothing real is no link at all."""
    import cotmetrics.indexer
    monkeypatch.setattr(cotmetrics.indexer, "get_indexer", lambda: _AssetsIndexer())

    classes, names = controls.forced_assets("?assets=Gold,Silver,Corn")
    assert names == ["Gold", "Silver", "Corn"]
    assert classes == ["Metals", "Grains"]

    classes, names = controls.forced_assets("?assets=Gold,Palladium%20Futures")
    assert (classes, names) == (["Metals"], ["Gold"])

    assert controls.forced_assets("?assets=Nothing%20Real") is None
    assert controls.forced_assets("?asset=Gold") is None
    assert controls.forced_assets("") is None
