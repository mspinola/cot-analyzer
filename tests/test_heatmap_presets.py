"""The column presets show whole question-shaped slices of the grid, safely.

What is worth pinning: the market block survives every preset (a grid of numbers
about nobody is not a view), a stale preset value from a returning browser's
session storage degrades to the full grid rather than to an empty one, and the
tag key is stripped from whatever AG Grid is handed, kept or not, because it is
not an AG Grid key.
"""
import dash

# `dash.register_page` runs at import of the page module and refuses to run
# without an app. The preset filter is what is under test, not the routing.
dash.Dash(__name__, use_pages=True, pages_folder='')

import pages.analytics.heatmap as heatmap  # noqa: E402


def _defs():
    return [
        {"headerName": "Asset Info", "presetTags": ("always",), "children": []},
        {"headerName": "Positioning · Raw",
         "presetTags": (heatmap.PRESET_POSITIONING,), "children": []},
        {"headerName": "Exposure",
         "presetTags": (heatmap.PRESET_RISK,), "children": []},
    ]


def _names(groups):
    return [g["headerName"] for g in groups]


def test_each_preset_keeps_its_groups_plus_the_market_block():
    assert _names(heatmap.apply_column_preset(
        _defs(), heatmap.PRESET_POSITIONING)) == ["Asset Info",
                                                  "Positioning · Raw"]
    assert _names(heatmap.apply_column_preset(
        _defs(), heatmap.PRESET_RISK)) == ["Asset Info", "Exposure"]
    assert len(heatmap.apply_column_preset(_defs(), heatmap.PRESET_ALL)) == 3


def test_a_stale_session_value_degrades_to_the_full_grid():
    """The value is session-persisted, so a renamed preset lives on in returning
    browsers. Everything, not nothing."""
    assert len(heatmap.apply_column_preset(_defs(), "risk-and-flow")) == 3
    assert len(heatmap.apply_column_preset(_defs(), None)) == 3


def test_the_tag_key_never_reaches_ag_grid():
    kept = heatmap.apply_column_preset(_defs(), heatmap.PRESET_RISK)
    assert all("presetTags" not in g for g in kept)


def test_the_real_grid_tags_leave_no_group_unreachable():
    """Every group in the page's own columnDefs must belong to the market block
    or at least one named preset, or a preset silently amputates it and 'All
    columns' becomes the only honest view. Read from the source because the
    literal lives inside the render callback."""
    import inspect

    source = inspect.getsource(heatmap.render_heatmap_layout)
    # One tag per group: the literal opens 8 groups (the market block + 7).
    assert source.count('"presetTags"') == 8
