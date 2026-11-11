"""What the navbar menus carry, and which entries the Dash router must not claim.

The menus are built from the tuples in `app_cot`, so a label or a path is cheap to
change and nothing here guards that. The expensive bit is the wiring: a dropdown entry
pointing off-origin needs `external_link=True`, or dbc hands the click to the
client-side router, which cannot leave the origin and answers with the SPA's own 404
for a site that is up. It fails silently in the one place nobody runs locally, so it is
pinned here.
"""
import app_cot
import routing


def _items(menu_label):
    """The DropdownMenuItem children of the navbar menu with this label."""
    menus = [c for c in app_cot.navbar.children[2].children.children
             if getattr(c, 'label', None) == menu_label]
    assert len(menus) == 1, f"expected one {menu_label!r} menu, found {len(menus)}"
    return menus[0].children


def test_the_monitors_menu_carries_the_tape_read_and_every_fund_book():
    assert [(i.children, i.href) for i in _items("Monitors")] == [
        ("Market Internals", "https://internals.bluemagicai.com/"),
        ("DBMF Positioning", "https://dbmf.bluemagicai.com/"),
        ("AHLT Trend Book", "https://ahlt.bluemagicai.com/"),
        ("ORR Book", "https://orr.bluemagicai.com/"),
        ("Sentiment Surveys", "https://surveys.bluemagicai.com/"),
    ]


def test_an_off_origin_entry_leaves_the_dash_router_alone():
    """Without external_link the click never reaches dbmf.bluemagicai.com: the SPA
    resolves the href itself and renders its page-not-found instead."""
    for item in _items("Monitors"):
        off_origin = item.href.startswith("http")
        assert item.external_link is off_origin
        assert (item.target == "_blank") is off_origin


def test_market_internals_is_linked_once_and_only_at_its_own_site():
    """It left the app for internals.bluemagicai.com; an in-app entry would be a
    link to a redirect."""
    hrefs = [i.href for menu in ("Analytics", "Monitors") for i in _items(menu)]
    assert "/internals" not in hrefs
    assert hrefs.count(routing.INTERNALS_URL) == 1


def test_the_old_internals_address_redirects_to_the_site():
    """Bookmarks and the links older monitor pages carry must keep working, and the
    unknown-path guard must admit the path or the route never runs."""
    assert "/internals" in routing.EXTRA_PATHS
    response = app_cot.app.server.test_client().get("/internals")
    assert response.status_code == 301
    assert response.headers["Location"] == "https://internals.bluemagicai.com/"
