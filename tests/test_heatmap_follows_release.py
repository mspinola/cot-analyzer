"""A heatmap tab left open across a CFTC release must converge on the new week.

The page's Target Date control is resolved in `layout()`, which runs once per page
load. The navbar badge is on a five-minute `dcc.Interval`. Before the release-follow
existed those two facts combined into a page that argued with its own header: on
2026-08-14 the 2026-08-11 week landed at 15:34 and the badge moved, while an open tab
kept rendering the previous week and could not even be steered onto the new one by
hand, because the date was not in the dropdown.

The follows-or-stays arithmetic itself now lives in `components.controls`
(`week_for_store` / `resolve_week`, shared by every Target Date through
`global_week_store`) and is pinned in test_controls.py. What stays here is the
caption half: it used to read the newest available week rather than the selected
one, which was wrong in both directions at once, stale on an open tab and wrong on
any deliberate look at an older week.
"""

from pages.analytics import heatmap


def test_caption_names_the_selected_week():
    assert "August 11, 2026" in heatmap.snapshot_caption("2026-08-11")


def test_caption_names_an_older_selected_week_not_the_newest():
    caption = heatmap.snapshot_caption("2026-07-28")
    assert "July 28, 2026" in caption


def test_caption_survives_a_missing_date():
    assert "Unknown Date" in heatmap.snapshot_caption(None)
