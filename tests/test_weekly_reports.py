"""The weekly report pages: crawlable, dated, honest about their window.

What is pinned: only weeks inside the published window render (the rest answer
None, which the route turns into a 404 rather than a redirect to something the
reader did not ask for), the page wraps the EMAIL builder's table rather than a
second implementation, every page carries its own canonical URL and unique
setups prose, and a changed email format degrades to serving the email whole
instead of a broken slice.

Stubbed at the seams (indexer dates, matrix frame, email HTML), so no store.
"""
import cotmetrics.constants as const
import pandas as pd
import pytest

import weekly_reports

WEEKS = ["2026-08-25", "2026-08-18", "2026-08-11"]


class _Indexer:
    def get_available_dates(self):
        return list(WEEKS)


def _frame():
    return pd.DataFrame([
        {"Asset": "Gold", const.SETUP_CLS_COL: const.SETUP_BULL,
         const.SETUP_NPF_COL: const.SETUP_NONE},
        {"Asset": "Coffee", const.SETUP_CLS_COL: const.SETUP_NONE,
         const.SETUP_NPF_COL: const.SETUP_BEAR},
        {"Asset": "Corn", const.SETUP_CLS_COL: const.SETUP_NONE,
         const.SETUP_NPF_COL: const.SETUP_NONE},
    ])


EMAIL_DOC = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
             '<style>td { color: red }</style></head>'
             '<body><h2>email heading</h2>'
             '<table><tr><td>Gold</td></tr></table>'
             '<p>Full CSV attached.</p></body></html>')


@pytest.fixture()
def stubbed(monkeypatch):
    # The rendered-page cache is module-level and keyed on (week, newest), so
    # without this a page built under one test's stubs would serve under the
    # next test's assertions.
    weekly_reports._rendered.cache_clear()
    monkeypatch.setattr(weekly_reports, "get_indexer", lambda: _Indexer())
    monkeypatch.setattr(weekly_reports, "get_matrix_data",
                        lambda **kw: _frame())
    monkeypatch.setattr(weekly_reports, "generate_matrix_html",
                        lambda df, report_date=None: EMAIL_DOC)
    monkeypatch.setenv("COT_PUBLIC_BASE_URL", "https://example.test")


def test_published_weeks_is_a_window_not_the_archive(monkeypatch):
    class _Deep:
        def get_available_dates(self):
            return [f"2026-01-01T{i}" for i in range(150)]
    monkeypatch.setattr(weekly_reports, "get_indexer", lambda: _Deep())
    assert len(weekly_reports.published_weeks()) == weekly_reports.WEEKS_PUBLISHED

    def boom():
        raise RuntimeError("store away")
    monkeypatch.setattr(weekly_reports, "get_indexer", boom)
    assert weekly_reports.published_weeks() == []


def test_a_published_week_renders_the_email_table_in_a_web_shell(stubbed):
    page = weekly_reports.report_page("2026-08-18")
    # The email's table and styles, not a reimplementation.
    assert "<table><tr><td>Gold</td></tr></table>" in page
    assert "<style>td { color: red }</style>" in page
    # The email's own chrome does not ride along.
    assert "Full CSV attached" not in page
    # A crawler's essentials: canonical, title, description.
    assert '<link rel="canonical" href="https://example.test/weekly/2026-08-18">' in page
    assert "<title>COT Report Signal Matrix, August 18, 2026 | COT Analyzer</title>" in page
    # The unique prose: this week's setups by name and direction.
    assert "Gold (bullish)" in page
    assert "Coffee (bearish)" in page
    # Dated navigation and the deep links into the live app.
    assert 'href="/weekly/2026-08-25"' in page
    assert 'href="/weekly/2026-08-11"' in page
    assert 'href="/heatmap?date=2026-08-18"' in page
    # Script-free by design: these pages exist for clients that run none.
    assert "<script" not in page


def test_unpublished_weeks_answer_none(stubbed):
    assert weekly_reports.report_page("2020-01-07") is None  # outside the window
    assert weekly_reports.report_page("not-a-date") is None
    assert weekly_reports.report_page("2026-8-25") is None


def test_a_changed_email_format_degrades_to_the_whole_email(stubbed, monkeypatch):
    monkeypatch.setattr(weekly_reports, "generate_matrix_html",
                        lambda df, report_date=None: "<p>tables? never heard of them</p>")
    page = weekly_reports.report_page("2026-08-25")
    assert page == "<p>tables? never heard of them</p>"


def test_the_index_lists_every_published_week(stubbed):
    page = weekly_reports.index_page()
    for week in WEEKS:
        assert f'href="/weekly/{week}"' in page
    assert '<link rel="canonical" href="https://example.test/weekly">' in page
    assert "<script" not in page


def test_no_setups_still_reads_as_a_sentence(stubbed, monkeypatch):
    monkeypatch.setattr(
        weekly_reports, "get_matrix_data",
        lambda **kw: pd.DataFrame([
            {"Asset": "Corn", const.SETUP_CLS_COL: const.SETUP_NONE,
             const.SETUP_NPF_COL: const.SETUP_NONE}]))
    page = weekly_reports.report_page("2026-08-25")
    assert "No market finished the week at a full setup" in page


def test_a_release_rebuilds_a_cached_page(stubbed, monkeypatch):
    """Pages are served from an in-process cache (a cold render was measured
    beyond a 30s external timeout on the deployment, and crawlers walk 104 of
    them), and the newest release is the cache key: a new week must rebuild
    every page (prev/next strips move, revisions restate), while repeat visits
    inside a week must not touch the matrix at all."""
    builds = []

    def counting_matrix(**kw):
        builds.append(kw.get("target_date"))
        return _frame()

    monkeypatch.setattr(weekly_reports, "get_matrix_data", counting_matrix)
    weekly_reports.report_page("2026-08-18")
    weekly_reports.report_page("2026-08-18")
    assert builds == ["2026-08-18"]  # the second visit was the cache

    class _Advanced:
        def get_available_dates(self):
            return ["2026-09-01"] + WEEKS

    monkeypatch.setattr(weekly_reports, "get_indexer", lambda: _Advanced())
    weekly_reports.report_page("2026-08-18")
    assert builds == ["2026-08-18", "2026-08-18"]  # the release rebuilt it
