"""The shared asset-class control.

Three pages had nine inline switches spanning a control row; two others already had a
compact dropdown. This is the one control they now share, and the tests that matter are
about what it says while shut and what it does NOT change about the pages using it.
"""
import pytest

from components import class_filter

EVERY = ["Crypto", "Currencies", "Energies", "Equities", "Fixed Income",
         "Grains", "Live Stock", "Metals", "Softs"]


def _ids(node, found=None):
    """Every component id in a tree."""
    found = [] if found is None else found
    if isinstance(node, (list, tuple)):
        for n in node:
            _ids(n, found)
        return found
    if node is None or isinstance(node, str):
        return found
    if getattr(node, "id", None):
        found.append(node.id)
    return _ids(getattr(node, "children", None), found)


# ── what it says while shut ───────────────────────────────────────────────────

@pytest.mark.parametrize("selected,expected", [
    (EVERY, "All asset classes"),
    ([], "No asset classes"),
    (["Grains"], "Grains"),
    (["Grains", "Metals"], "Grains, Metals"),
    (["Grains", "Metals", "Softs"], "3 of 9 classes"),
])
def test_the_control_states_its_own_answer(selected, expected):
    """A dropdown reading "Asset Classes" whatever is inside it has to be opened to be
    trusted, which is most of what leaving nine switches on show was buying."""
    assert class_filter.menu_label(selected, EVERY) == expected


def test_a_count_carries_its_denominator():
    """"3 classes" and "3 of 9 classes" answer different questions, and a reader looking
    at a filtered page is asking the second."""
    assert "of 9" in class_filter.menu_label(EVERY[:3], EVERY)


def test_all_is_recognised_by_count_not_by_identity():
    """The page supplies its own class list and order (graphs sorts, heatmap does not),
    so "all" cannot mean "equal to some canonical list"."""
    assert class_filter.menu_label(list(reversed(EVERY)), EVERY) == "All asset classes"


def test_a_shorter_universe_still_reads_as_all():
    small = ["Grains", "Metals"]
    assert class_filter.menu_label(small, small) == "All asset classes"


# ── what it must not change about the pages using it ──────────────────────────

def test_the_checklist_keeps_the_page_s_own_id():
    """The whole reason this is a container rather than a new control: every callback
    already reading the page's checklist stays wired without being touched."""
    tree = class_filter.control("strip_class_selector", EVERY)
    assert "strip_class_selector" in _ids(tree)


def test_each_instance_gets_its_own_menu_and_shortcut_ids():
    """Three pages mount this at once. Ids derived from the checklist id keep their
    callbacks from colliding."""
    a = set(_ids(class_filter.control("strip_class_selector", EVERY)))
    b = set(_ids(class_filter.control("page_heatmap_selector", EVERY)))
    assert a.isdisjoint(b)
    assert class_filter.menu_id("strip_class_selector") in a


def test_the_default_value_is_every_class_and_the_label_agrees():
    tree = class_filter.control("strip_class_selector", EVERY)
    assert tree.label == "All asset classes"


def test_a_page_may_open_on_one_class():
    """graphs defaults to a single class rather than all of them, so the toggle names
    it outright rather than reading "1 of 9"."""
    tree = class_filter.control("graphs_asset_class_selector", EVERY, value=["Metals"])
    assert tree.label == "Metals"


def test_the_switches_offer_every_class_the_page_passed():
    tree = class_filter.control("strip_class_selector", EVERY)
    checklist = [n for n in _flatten(tree) if getattr(n, "id", None) == "strip_class_selector"][0]
    assert [o["value"] for o in checklist.options] == EVERY


def _flatten(node, out=None):
    out = [] if out is None else out
    if isinstance(node, (list, tuple)):
        for n in node:
            _flatten(n, out)
        return out
    if node is None or isinstance(node, str):
        return out
    out.append(node)
    return _flatten(getattr(node, "children", None), out)
