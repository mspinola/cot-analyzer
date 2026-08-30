"""A heatmap tab left open across a CFTC release must converge on the new week.

The page's Target Date control is resolved in `layout()`, which runs once per page
load. The navbar badge is on a five-minute `dcc.Interval`. Before `next_date_selection`
those two facts combined into a page that argued with its own header: on 2026-08-14 the
2026-08-11 week landed at 15:34 and the badge moved, while an open tab kept rendering
the previous week and could not even be steered onto the new one by hand, because the
date was not in the dropdown.

The other half is the caption, which used to read the newest available week rather than
the selected one. That was wrong in both directions at once: stale on an open tab, and
wrong on any deliberate look at an older week.
"""
from dash import no_update

import app_utils
from pages.analytics import heatmap

WEEKS = ["2026-08-11", "2026-08-04", "2026-07-28"]   # newest first, as the page lists them


def opts(dates):
    return [{'label': d, 'value': d} for d in dates]


# ── following a new release ───────────────────────────────────────────────────

def test_a_tab_on_the_newest_week_follows_the_new_one():
    """The regression. Nobody chose to sit on 08-04, so it tracks."""
    options, value = app_utils.next_date_selection(
        WEEKS, opts(WEEKS[1:]), "2026-08-04")

    assert [o['value'] for o in options] == WEEKS, "the new week was never offered"
    assert value == "2026-08-11"


def test_a_deliberately_chosen_older_week_is_left_alone():
    """Picking a week is a decision. A release must not yank the reader off it."""
    options, value = app_utils.next_date_selection(
        WEEKS, opts(WEEKS[1:]), "2026-07-28")

    assert [o['value'] for o in options] == WEEKS, "the new week must still be offered"
    assert value == "2026-07-28"


def test_an_unmoved_store_changes_nothing():
    """The store republishes on a timer, so the quiet case must be a genuine no-op.

    Returning the same options object would re-render the control, and returning the
    same value would re-fire the grid callback, on every tick, for every open tab.
    """
    options, value = app_utils.next_date_selection(WEEKS, opts(WEEKS), "2026-08-11")

    assert options is no_update
    assert value is no_update


def test_a_first_render_with_no_prior_options_takes_the_newest():
    options, value = app_utils.next_date_selection(WEEKS, None, None)

    assert [o['value'] for o in options] == WEEKS
    assert value == "2026-08-11"


def test_a_selection_that_no_longer_exists_falls_back_to_the_newest():
    """A vintage revision can withdraw a week. Do not leave the grid pinned to nothing."""
    options, value = app_utils.next_date_selection(
        WEEKS, opts(["2026-08-18", "2026-08-11"]), "2026-08-18")

    assert [o['value'] for o in options] == WEEKS
    assert value == "2026-08-11"


def test_an_empty_index_changes_nothing():
    """Mid-rebuild the indexer can answer with no dates. Blanking the control on the
    strength of that would replace a working page with an empty one."""
    options, value = app_utils.next_date_selection([], opts(WEEKS), "2026-08-11")

    assert options is no_update
    assert value is no_update


# ── the caption ───────────────────────────────────────────────────────────────

def test_the_caption_names_the_selected_week():
    assert "August 11, 2026" in heatmap.snapshot_caption("2026-08-11")


def test_the_caption_follows_a_deliberate_look_at_an_older_week():
    """It describes the table beneath it, not the store."""
    caption = heatmap.snapshot_caption("2026-07-28")

    assert "July 28, 2026" in caption
    assert "August" not in caption


def test_the_caption_survives_having_no_date():
    assert "Unknown Date" in heatmap.snapshot_caption(None)
