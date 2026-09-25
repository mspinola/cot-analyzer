"""The weekly report pages: every COT release as a dated, crawlable HTML page.

The one thing a Dash app cannot give a search engine is server-rendered content,
and the one content stream this site already produces is the weekly Signal
Matrix email. These pages publish it at /weekly/<date>, plain HTML built
server-side with no script in sight: a crawler (or a reader with JS off) gets
the whole table, a summary in prose, and dated internal links. That is the
strongest on-site search lever a data site has, and it costs no new analysis.

Three decisions:

* **A window, not the whole archive.** The store holds 1200+ weeks; publishing
  all of them is a thousand near-identical tables, which search engines read as
  thin content and readers as noise. The trailing WEEKS_PUBLISHED (two years)
  is fresh, plausibly useful history; older weeks answer 404 rather than
  redirecting, because they were never published.
* **The table comes from the email builder, extracted rather than rebuilt.**
  `generate_matrix_html` is the one place the emailed matrix is decided
  (subject to its own tests in cotmetrics), so these pages slice its <style>
  and <table> out and wrap them in a web shell. If the email format ever
  changes shape, the extraction falls back to serving the email document
  whole: still crawlable, just less dressed.
* **Every page carries unique prose.** A summary sentence naming this week's
  full setups per model is computed from the frame, so no two weeks read
  identically and the page says something a table scan would take minutes to
  learn. The interactive links carry ?date=<week>, the app's own deep-link
  param, so "explore this week" lands the reader on the same week the page
  describes.
"""
import functools
import re
import threading
from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import generate_matrix_html, get_matrix_data

import subscribers

#: How many trailing releases are published. Two years: enough for a reader
#: walking history and for crawlers to see a steady weekly cadence.
WEEKS_PUBLISHED = 104

WEEK_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def published_weeks(limit=WEEKS_PUBLISHED):
    """The publishable weeks, newest first. Empty when the store is."""
    try:
        return list(get_indexer().get_available_dates()[:limit])
    except Exception as e:
        utils.cot_logger.warning(f"weekly pages: no dates available: {e}")
        return []


def _pretty(week):
    try:
        return datetime.strptime(week, '%Y-%m-%d').strftime('%B %d, %Y')
    except (TypeError, ValueError):
        return week


def _extract(email_html):
    """(style, table) sliced out of the email document, or (None, None).

    String finds rather than a parser: the email format is a sibling repo's
    stable surface, and the fallback for a miss (serving the email document
    whole) is acceptable, so a parser would buy nothing but a dependency.
    """
    def slice_between(text, start, end):
        a = text.find(start)
        b = text.find(end, a)
        return text[a:b + len(end)] if a != -1 and b != -1 else None

    style = slice_between(email_html, "<style", "</style>")
    table = slice_between(email_html, "<table", "</table>")
    return style, table


def _setup_summary(df):
    """This week's full setups, in a sentence per model. The page's unique prose."""
    def names(state_col):
        out = []
        for row in df.to_dict("records"):
            state = row.get(state_col)
            if state == const.SETUP_BULL:
                out.append(f"{row['Asset']} (bullish)")
            elif state == const.SETUP_BEAR:
                out.append(f"{row['Asset']} (bearish)")
        return out

    parts = []
    for title, col in ((models.RAW_PF.title, const.SETUP_CLS_COL),
                       (models.NPF.title, const.SETUP_NPF_COL)):
        markets = names(col)
        if markets:
            parts.append(f"{title} full setups: {', '.join(markets)}.")
    if not parts:
        return ("No market finished the week at a full setup under either "
                "model.")
    return " ".join(parts)


def _shell(title, description, canonical, body):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<style>
  body {{ background:#1a1a1a; color:#ABB8C9; margin:0;
         font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ color:#e8eef5; font-size:1.4rem; margin:0 0 .4rem; }}
  a  {{ color:#7fb2e5; }}
  .sub {{ font-size:.9rem; margin:.2rem 0; }}
  .nav {{ margin: 14px 0; font-size:.9rem; }}
  .table-wrap {{ overflow-x:auto; margin-top: 16px; }}
</style>
</head>
<body><div class="wrap">
{body}
</div></body>
</html>"""


def report_page(week):
    """One release as a full HTML document, or None when the week is not
    published (wrong shape, outside the window, or not in the store)."""
    if not WEEK_RE.match(str(week)):
        return None
    weeks = published_weeks()
    if week not in weeks:
        return None
    # One render at a time. lru_cache does not coalesce concurrent misses, so
    # without this every request that arrives while a page is cold builds the
    # whole matrix again in parallel, and on a GIL-bound box N parallel builds
    # finish together N times late. With it, a waiter gets the page the first
    # render cached. See warm_newest for the case that made this matter.
    with _render_lock:
        return _rendered(week, weeks[0])


_render_lock = threading.Lock()


def warm_newest():
    """Render the newest published week so no reader pays its cold build.

    The newest page is the one the weekly email links to and the one crawlers
    reach first from /weekly and the sitemap, so it is the page a cold render
    hurts most. Measured 2026-09-25 right after a restart on the VPS: 504 at
    nginx's 60s, then 200 in 54s. What that cost was NOT a missing cache between
    this page's explicit-date matrix and the boards' newest-week one (they share
    `get_symbols_data`'s cache, and building one after the other costs ~0.1s
    locally). It is the first build of that per-market frame in a fresh process,
    ~3.5s locally and roughly 9x that on the VPS, paid several times over while
    the home-page prewarm, the crowd warmer and every piled-up request each built
    it in parallel. Called first by main.warm_page_caches, so after a restart the
    page is ready as soon as the first build is, and after a release it rides on
    the matrix the weekly email just built. Failures are logged and swallowed,
    the warmers' rule.
    """
    try:
        weeks = published_weeks()
        if not weeks:
            return
        report_page(weeks[0])
        utils.cot_logger.info(f"weekly pages: warmed {weeks[0]}.")
    except Exception as e:
        utils.cot_logger.warning(f"weekly pages: warm failed, first reader pays: {e}")


@functools.lru_cache(maxsize=WEEKS_PUBLISHED + 8)
def _rendered(week, newest_date):
    """The finished page, cached per (week, newest release).

    Measured on the deployment the day these shipped: a COLD render exceeded a
    30-second timeout from the outside, then 3-7s once warm (the cold cost is
    the per-market frame build, see warm_newest; an earlier note here blamed a
    cache the explicit-date matrix did not share, which measurement did not
    bear out). A crawler walking 104 cold pages meets that
    wall on every one, and these pages exist FOR crawlers. The page for a week
    is immutable once built, except that a new release moves the prev/next
    strip on the newest page and the store can restate on a revision, which is
    exactly what keying on `newest_date` invalidates: a release busts every
    entry, the heatmap joins' rule. The cache holds the whole window plus slack,
    at ~40KB a page.
    """
    weeks = published_weeks()
    # asset_classes=None is "every class", the same call the weekly email makes.
    df = get_matrix_data(asset_classes=None, lookback="Custom", target_date=week)
    email_html = generate_matrix_html(df, report_date=week)
    style, table = _extract(email_html)
    if style is None or table is None:
        utils.cot_logger.warning(
            "weekly pages: email format not extractable, serving it whole.")
        return email_html

    base = subscribers.base_url()
    pretty = _pretty(week)
    idx = weeks.index(week)
    older = weeks[idx + 1] if idx + 1 < len(weeks) else None
    newer = weeks[idx - 1] if idx > 0 else None
    steps = []
    if older:
        steps.append(f'<a href="/weekly/{older}">&larr; {_pretty(older)}</a>')
    steps.append('<a href="/weekly">All weekly reports</a>')
    if newer:
        steps.append(f'<a href="/weekly/{newer}">{_pretty(newer)} &rarr;</a>')

    body = f"""<h1>COT Signal Matrix &#8212; week of {pretty}</h1>
<p class="sub">Commitments of Traders positioning for {len(df)} futures
markets as reported by the CFTC for Tuesday {pretty}: Commercial, Non-Commercial
and Non-Reportable positioning indexes on raw and OI-normalized bases, index momentum,
WILLCO, sentiment and open-interest readings, with each model's setup verdict.</p>
<p class="sub">{_setup_summary(df)}</p>
<p class="nav">{' &middot; '.join(steps)}</p>
<p class="nav">Explore this week interactively:
<a href="/heatmap?date={week}">Signal Heatmap</a> &middot;
<a href="/strip?date={week}">Crowding Strip</a> &middot;
<a href="/crowd?date={week}">Crowdedness Board</a> &middot;
<a href="/divergence?date={week}">Model Divergence</a></p>
{style}
<div class="table-wrap">{table}</div>
<p class="sub" style="margin-top:14px"><a href="/">COT Analyzer</a> &middot;
free weekly Commitments of Traders charts and signals &middot;
<a href="/about">get this report by email</a></p>"""

    return _shell(
        f"COT Report Signal Matrix, {pretty} | COT Analyzer",
        f"Commitments of Traders signal matrix for the week of {pretty}: "
        f"Commercial, Non-Commercial and Non-Reportable positioning indexes, momentum and setup "
        f"verdicts for {len(df)} futures markets.",
        f"{base}/weekly/{week}", body)


def index_page():
    """The archive: every published week, newest first, grouped by year."""
    weeks = published_weeks()
    base = subscribers.base_url()

    by_year = {}
    for week in weeks:
        by_year.setdefault(week[:4], []).append(week)
    sections = []
    for year in sorted(by_year, reverse=True):
        links = " &middot;\n".join(
            f'<a href="/weekly/{w}">{_pretty(w)}</a>' for w in by_year[year])
        sections.append(f"<h2 style='font-size:1.1rem'>{year}</h2>\n"
                        f"<p class='sub'>{links}</p>")

    body = f"""<h1>Weekly COT Reports</h1>
<p class="sub">The Signal Matrix for every Commitments of Traders release of
the last two years: positioning indexes, momentum and setup verdicts for 40+
futures markets, one page per CFTC reporting week. The newest is
{'<a href="/weekly/' + weeks[0] + '">' + _pretty(weeks[0]) + '</a>' if weeks
 else 'not yet available'}.</p>
<p class="sub"><a href="/">Open the live COT Analyzer</a> &middot;
<a href="/about">get the weekly report by email</a></p>
{''.join(sections)}"""

    return _shell(
        "Weekly COT Reports Archive | COT Analyzer",
        "Every weekly Commitments of Traders Signal Matrix of the last two "
        "years: positioning indexes, momentum and setups for 40+ futures "
        "markets, one page per CFTC release.",
        f"{base}/weekly", body)
