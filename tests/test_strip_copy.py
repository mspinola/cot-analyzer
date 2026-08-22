"""What the Crowding Strip says about the board it is NOT showing.

The page draws one row per market and the reader's whole impression is the shape of
the board, so a view that has dropped rows and looks complete is the one failure worth
spending words on. Two things can drop a row and they are not the same kind of fact: a
Show/Side filter is a choice the reader made and can undo, while a market with no index
this week is absent from every view of it. Both have to be said, and both have to be
said somewhere that is on screen by default.

That last clause is why these live here rather than being left to the caption. The
caption folds shut under the Key toggle, so on a fresh visit the only line reporting
either fact is the controls summary.
"""
import cotmetrics.models as models
import dash

# `dash.register_page` runs at import of the page module and refuses to run without an
# app. The copy is what is under test, not the routing, so an app with no pages folder
# is enough and keeps Dash from walking the tree.
dash.Dash(__name__, use_pages=True, pages_folder='')

from pages.analytics.strip import caption, controls_summary  # noqa: E402

MODEL = models.RAW_PF


def _summary(**kwargs):
    return controls_summary("2026-08-18", MODEL, "52", "index", "all", "both", 2,
                            9, 9, **kwargs)


# ── the caption ───────────────────────────────────────────────────────────────

def test_a_board_both_filtered_and_short_of_data_reports_both():
    """The second branch used to assign rather than append, so the filter sentence
    vanished whenever any market also lacked an index. Both conditions co-occur
    routinely: any Show or Side setting, plus one market the store has no index for."""
    text = caption("2026-08-18", "52", MODEL, {"HG", "SI"}, hidden=7)
    assert "7 market(s) hidden by the Show/Side filters." in text
    assert "2 market(s) have no index this week" in text
    assert "HG, SI" in text


def test_each_removal_is_reported_on_its_own_too():
    only_hidden = caption("2026-08-18", "52", MODEL, set(), hidden=7)
    assert "7 market(s) hidden" in only_hidden
    assert "no index this week" not in only_hidden

    only_skipped = caption("2026-08-18", "52", MODEL, {"HG"}, hidden=0)
    assert "1 market(s) have no index this week" in only_skipped
    assert "hidden by the Show/Side filters" not in only_skipped


def test_a_full_board_claims_nothing_about_removals():
    text = caption("2026-08-18", "52", MODEL, set(), hidden=0)
    assert "hidden" not in text
    assert "no index" not in text


# ── the always-visible summary ────────────────────────────────────────────────

def test_the_summary_says_what_the_filters_removed_not_only_what_they_are_set_to():
    """The rest of the line reports settings. These two report their effect, and while
    the Key is folded they are the only thing on screen that does."""
    text = _summary(hidden=7, skipped=2)
    assert "7 hidden" in text
    assert "2 no index" in text


def test_the_removal_counts_survive_truncation_of_the_tail():
    """The summary column is `text-truncate`, so segment order is what decides which
    facts survive a narrow viewport. The counts go ahead of the class fraction and the
    column count, which are the two least worth keeping."""
    text = _summary(hidden=7, skipped=2)
    assert text.index("7 hidden") < text.index("9/9 classes")
    assert text.index("2 no index") < text.index("2 columns")


def test_the_summary_is_silent_when_the_board_is_whole():
    text = _summary()
    assert "hidden" not in text
    assert "no index" not in text
