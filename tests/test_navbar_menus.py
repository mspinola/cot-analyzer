"""What the navbar menus carry, and which entries the Dash router must not claim.

The menus are built from the tuples in `app_cot`, so a label or a path is cheap to
change and nothing here guards that. The expensive bit is the wiring: a dropdown entry
pointing off-origin needs `external_link=True`, or dbc hands the click to the
client-side router, which cannot leave the origin and answers with the SPA's own 404
for a site that is up. It fails silently in the one place nobody runs locally, so it is
pinned here.
"""
import app_cot


def _items(menu_label):
    """The DropdownMenuItem children of the navbar menu with this label."""
    menus = [c for c in app_cot.navbar.children[2].children.children
             if getattr(c, 'label', None) == menu_label]
    assert len(menus) == 1, f"expected one {menu_label!r} menu, found {len(menus)}"
    return menus[0].children


def test_the_monitors_menu_carries_the_tape_read_and_every_fund_book():
    assert [(i.children, i.href) for i in _items("Monitors")] == [
        ("Market Internals", "/internals"),
        ("DBMF Positioning", "https://dbmf.bluemagicai.com/"),
        ("AHLT Trend Book", "https://dbmf.bluemagicai.com/ahlt"),
        ("ORR Book", "https://dbmf.bluemagicai.com/orr"),
    ]


def test_an_off_origin_entry_leaves_the_dash_router_alone():
    """Without external_link the click never reaches dbmf.bluemagicai.com: the SPA
    resolves the href itself and renders its page-not-found instead."""
    for item in _items("Monitors"):
        off_origin = item.href.startswith("http")
        assert item.external_link is off_origin
        assert (item.target == "_blank") is off_origin


def test_market_internals_left_analytics_rather_than_being_listed_twice():
    """It moved; a copy in both menus would be two ways to the same page and two
    items the active-state callback lights up at once."""
    assert "/internals" not in [i.href for i in _items("Analytics")]
