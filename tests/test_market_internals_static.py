"""The published copy of the market internals page.

What is pinned: the static page says what the snapshot says (the same headline, the
same numbers through the shared view module), every figure it has an element for is
embedded and parses back, a snapshot with no reads refuses to render rather than
publishing six "awaiting" cards, a partly-served store renders with the missing
symbols named, `generated_at` carries the spelling publish_pages masks and is the only
thing a rebuild changes, and the monitors row marks this page. Store-free.
"""
import html
import json
import re

import pandas as pd
import pytest

import components.market_internals as mi
import components.market_internals_view as view
from components import market_internals_static as st
from components import plot_colors
from components import sentiment_static as surveys
from routing import external_page_path
from tests.test_market_internals import _bars, _universe
from tests.test_sentiment import COLORS

#: Sessions in the synthetic store: enough for the credit appetite gauge, which needs its
#: 20-day average and then 252 previous sessions to rank against.
N = 320


def _snap(drop=()):
    frames = {k: v for k, v in _universe(N).items() if k not in drop}
    return mi.build_snapshot(_bars(frames))


def _payload(page):
    m = re.search(rf'<script type="application/json" id="{st.DATA_ID}">(.*?)</script>',
                  page, re.S)
    return json.loads(m.group(1))


def test_every_chart_element_has_its_data_and_nothing_is_embedded_unused():
    snap = _snap()
    page = st.render(snap, COLORS)
    data = _payload(page)
    wanted = set(re.findall(r'data-chart="([^"]+)"', page))
    assert wanted == set(data) == {st.FOMO_KEY, st.APPETITE_KEY, st.HIGHS_LOWS_KEY,
                                   st.NET_HISTORY_KEY,
                                   *(st.LOWS_SHARE_PREFIX + x.lower() for x, _, _ in mi.NET_HIGHS_SYMBOLS),
                                   *(st.HEADWIND_PREFIX + k for k in mi.HEADWIND_KEYS)}
    for spec in data.values():
        assert spec["series"] and all(s["data"] for s in spec["series"])
        # Lightweight Charts wants ascending yyyy-mm-dd times and no missing values.
        for s in spec["series"]:
            times = [pt["time"] for pt in s["data"]]
            assert times == sorted(set(times))
            assert all(pt["value"] == pt["value"] for pt in s["data"])


def test_the_charts_are_the_view_modules_own_and_carry_their_levels():
    snap = _snap()
    colors = st.page_colors(COLORS)
    data = _payload(st.render(snap, COLORS))
    assert data[st.FOMO_KEY] == view.fomo_chart(snap.fomo, colors)
    from cotmetrics import indicators
    assert [lv["value"] for lv in data[st.FOMO_KEY]["levels"]] == [
        indicators.FOMO_EXHAUSTION_MIN, indicators.FOMO_FEAR_MAX]
    assert [lv["value"] for lv in data[st.APPETITE_KEY]["levels"]] == [80.0, 20.0]
    assert data[st.FOMO_KEY]["range"] == data[st.APPETITE_KEY]["range"] == [0, 100]
    by_key = {h.key: data[st.HEADWIND_PREFIX + h.key] for h in snap.headwinds}
    # A level read draws one line against the level it turns on; a read against its
    # own average draws the two lines and no level.
    # Net new highs is columns from zero, red on the sessions below it.
    for key in ("nasdaq_net_highs", "nyse_net_highs"):
        assert [lv["value"] for lv in by_key[key]["levels"]] == [0.0]
        (cols,) = by_key[key]["series"]
        assert cols["type"] == "histogram" and cols["color"] == colors.bull
        assert all(p.get("color", colors.bull) == (colors.bear if p["value"] < 0 else colors.bull)
                   for p in cols["data"])
    assert [lv["value"] for lv in by_key["qqq_updown"]["levels"]] == [1.0]
    for key in ("credit", "rotation"):              # the band's two areas, then the lines
        assert len(by_key[key]["series"]) == 4 and by_key[key]["levels"] == []


def test_each_headwind_card_says_its_state_what_flips_it_and_for_how_long():
    snap = _snap()
    page = st.render(snap, COLORS)
    section = page.split(f'id="{st.HEADWINDS_ID}"')[1].split('<div class="sec">')[0]
    assert section.count('<section class="card hw ') == len(snap.headwinds) == 6
    for h in snap.headwinds:
        card = section.split(f'data-key="{h.key}"')[1].split("</section>")[0]
        assert f'<span class="big">{html.escape(h.display)}</span>' in card
        assert f">{view.headwind_badge(h)}</span>" in card
        assert html.escape(h.flip) in card
        assert view.headwind_streak(h) in card
        if h.versus:
            assert view.headwind_versus(h) in card
    count, lean = mi.headline(snap)
    number, _, rest = count.partition(" ")
    assert f">{number}</b> {rest}</p>" in page and lean in page


def test_fomo_is_on_the_page_but_outside_the_count():
    snap = _snap()
    page = st.render(snap, COLORS)
    uncounted = page.split(f"<h2>{view.UNCOUNTED_TITLE}</h2>")[1].split(
        f"<h2>{view.DETAIL_TITLE}</h2>")[0]
    assert f"<h2>{html.escape(view.FOMO_TITLE)}</h2>" in uncounted
    assert f"<h2>{html.escape(view.APPETITE_TITLE)}</h2>" in uncounted
    assert view.fomo_recent(snap.fomo) in uncounted
    assert view.fomo_recent(snap.fomo).count("→") == 4


def test_the_sparklines_are_inline_svg_one_per_table_row():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert page.count('<svg class="spark"') == len(snap.assets) == len(mi.ASSET_SYMBOLS)
    xs = [float(pt.split(",")[0]) for pt in view.spark_points(snap.assets[0]).split()]
    ys = [float(pt.split(",")[1]) for pt in view.spark_points(snap.assets[0]).split()]
    assert min(xs) >= 0 and max(xs) <= view.SPARK_WIDTH
    assert min(ys) >= 0 and max(ys) <= view.SPARK_HEIGHT


def test_credit_appetite_is_drawn_and_described_but_not_counted():
    snap = _snap()
    assert snap.appetite is not None
    page = st.render(snap, COLORS)
    assert f"<h2>{html.escape(view.APPETITE_TITLE)}</h2>" in page
    assert html.escape(view.appetite_status(snap.appetite, snap.credit)) in page
    assert "appetite" not in mi.HEADWIND_KEYS
    without = mi.build_snapshot(_bars({k: v for k, v in _universe(N).items()
                                       if k != mi.APPETITE_TREASURY}))
    assert without.appetite is None
    assert mi.headline(without) == mi.headline(snap)


def test_the_page_opens_with_the_surveys_stylesheet():
    """One stylesheet for the family: the tokens, header, tiles and cards are the
    surveys page's own text, not a copy that can drift."""
    page = st.render(_snap(), COLORS)
    assert surveys.base_css() in page
    assert f"--page: {surveys.PAGE_COLOR}" in page
    assert f"max-width: {surveys.PAGE_MAX_WIDTH_PX}px" in page
    assert page.count("How to read this") >= 4


def test_the_chart_library_is_pinned_and_attributed():
    """An exact release from unpkg, and the licence's notice and link in the footer
    (which is why the per-chart logo may be off)."""
    page = st.render(_snap(), COLORS)
    assert re.fullmatch(r"\d+\.\d+\.\d+", st.LIGHTWEIGHT_CHARTS_VERSION)
    assert (f'<script src="https://unpkg.com/lightweight-charts@'
            f'{st.LIGHTWEIGHT_CHARTS_VERSION}/dist/') in page
    footer = page.split("<footer>")[1].split("</footer>")[0]
    assert st.ATTRIBUTION in footer and 'href="https://www.tradingview.com/"' in footer
    assert "attributionLogo: false" in page
    assert "plotly" not in page.lower()
    # Panning a chart would take the page's scroll on a phone.
    assert "handleScroll: false, handleScale: false" in page


def test_the_page_says_what_the_snapshot_says():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert f'<span class="big">{snap.fomo.value:.1f}</span>' in page
    for read in snap.net_highs:
        assert f"{read.highs} highs, {read.lows} lows" in page
    for row in snap.assets:
        assert f'<td class="name num">{row.last:,.2f}</td>' in page
    for title in (view.HEADWINDS_TITLE, view.UNCOUNTED_TITLE, view.DETAIL_TITLE,
                  view.FOMO_TITLE, view.APPETITE_TITLE, view.NET_HIGHS_TITLE,
                  view.ASSETS_TITLE):
        assert f"<h2>{html.escape(title)}</h2>" in page
    assert f"<h3>{view.ADVANCE_DECLINE_TITLE}</h3>" in page
    assert html.escape(view.FOOTER) in page


def test_a_snapshot_with_no_reads_refuses_to_render(tmp_path):
    """A store that cannot be read must not replace the published page."""
    empty = mi.build_snapshot(_bars({}))
    with pytest.raises(ValueError, match="no reads"):
        st.render(empty, COLORS)
    out = tmp_path / "internals.html"
    with pytest.raises(ValueError):
        st.write(out, empty, COLORS)
    assert not out.exists()


def test_a_partly_served_store_renders_and_names_what_is_missing():
    """The app page's rule: a series not delivered yet is named, not drawn or raised."""
    snap = _snap(drop=(mi.FOMO_SYMBOL, "IBIT"))
    page = st.render(snap, COLORS)
    assert view.awaiting_text([mi.FOMO_SYMBOL]) in page
    assert st.FOMO_KEY not in _payload(page)
    assert page.count('<svg class="spark"') == len(mi.ASSET_SYMBOLS) - 1
    assert "awaiting data</td>" in page
    assert f"Awaiting data for: {', '.join(snap.awaiting)}." in page


def test_a_rebuild_differs_only_in_the_stamp_publish_pages_masks():
    """publish_pages pushes nothing when the pages match with `"generated_at":"..."`
    blanked, so that must be the only place a build time appears."""
    snap = _snap()
    a = st.render(snap, COLORS, generated_at="2026-11-10T01:15Z")
    b = st.render(snap, COLORS, generated_at="2026-11-11T01:15Z")
    assert a != b and '"generated_at":"2026-11-10T01:15Z"' in a

    def mask(t):
        return re.sub(r'"generated_at":"[^"]*"', '"generated_at":""', t)
    assert mask(a) == mask(b)


def test_the_json_cannot_close_its_script_element_early():
    page = st.render(_snap(), COLORS)
    body = re.search(rf'id="{st.DATA_ID}">(.*?)</script>', page, re.S).group(1)
    assert "</" not in body


def test_the_monitor_row_is_the_surveys_pages_with_this_page_current():
    nav = st._nav()
    links = re.findall(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', nav)
    assert links == re.findall(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', surveys._nav())
    assert re.findall(r'aria-current="page"[^>]*>([^<]+)<', nav) == [st.CURRENT]
    assert st.CURRENT in [name for name, _ in surveys.SITES]


def test_the_header_names_the_newest_session():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert f"Through <b>{st._date(snap.date)}</b>" in page
    assert f'<span class="tk">{st.H1_TICKER}</span> {st.H1_REST}' in page


def test_the_publish_key_is_allowlisted_for_the_view_beacon():
    """publish_internals.sh sends `--key internals`; unlisted, its views are dropped."""
    assert external_page_path("internals") == "/internals"


def test_the_page_and_its_charts_use_the_family_ink():
    """Text, chart lines and axis labels in the fund pages' white and grey
    (`sentiment_static.INK` / `INK_2`), never the app's cream."""
    import viz_constants as vc
    page = st.render(_snap(), COLORS)
    lowered = page.lower()
    assert vc.TEXT_COLOR.lower() not in lowered
    assert vc.BRIGHTER_TEXT_COLOR.lower() not in lowered
    data = _payload(page)
    assert data[st.FOMO_KEY]["series"][0]["color"] == surveys.INK
    assert f"var INK = '{surveys.INK_2}'" in page


def test_the_history_card_draws_a_strip_per_headwind_aligned_to_the_session():
    snap = _snap()
    h = snap.history
    page = st.render(snap, COLORS)
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    n = len(h.dates)
    # Every SVG is one unit a session wide, so a mark's x is its session index.
    assert card.count(f'viewBox="0 0 {n} 1"') == len(mi.HEADWIND_KEYS) + 1   # + all
    assert f'viewBox="0 0 {n} {view.HISTORY_FOMO_UNITS:g}"' in card        # FOMO's bars
    assert f'viewBox="0 0 {n} {view.HISTORY_PRICE_UNITS:g}"' in card
    for key, label, flags in h.rows:
        strip = card.split(f'data-strip="{key}"')[1].split("</svg>")[0]
        assert strip.count("<rect") == len(view.runs(flags))
        assert html.escape(label) in card
    every = [c == h.total for c in h.count]
    assert card.split('data-row="all"')[1].split("</svg>")[0].count("<rect") == len(view.runs(every))
    assert html.escape(view.history_summary(h)) in card
    assert "no claim is made here about what followed" in card


def test_history_geometry_runs_points_and_year_ticks():
    assert view.runs([False, True, True, False, True]) == [(1, 2), (4, 1)]
    assert view.runs([]) == [] and view.runs([True, True]) == [(0, 2)]
    h = _snap().history
    points = [tuple(float(v) for v in pt.split(",")) for pt in
              view.history_price_points(h).split()]
    assert points[0][0] == 0 and points[-1][0] == len(h.dates) - 1
    assert all(0 <= y <= view.HISTORY_PRICE_UNITS for _, y in points)
    assert min(y for _, y in points) == 0 or max(y for _, y in points) == view.HISTORY_PRICE_UNITS
    ticks = view.history_year_ticks(h)
    assert all(0 < fraction < 1 and int(year) % view.HISTORY_TICK_YEARS == 0
               for fraction, year in ticks)


def test_the_history_summary_counts_occurrences_and_names_the_longest():
    dates = tuple(f"2026-01-{d:02d}" for d in range(1, 11))
    h = mi.HeadwindHistory(dates=dates, price=(1.0,) * 10, price_symbol="QQQ", rows=(),
                           count=(5, 5, 5, 1, 1, 1, 1, 1, 1, 5), total=5)
    text = view.history_summary(h)
    assert text.startswith("All 5 were on at once on 4 of 10 sessions since 2026 (40%), in 1 ")
    assert "Jan 2026 to Jan 2026 (4 sessions)" in text
    assert view.day_text("2026-11-06") == "Nov 6, 2026"
    quiet = mi.HeadwindHistory(dates=dates, price=(1.0,) * 10, price_symbol="QQQ", rows=(),
                               count=(2,) * 10, total=5)
    assert view.history_summary(quiet) == "All 5 have never been on at once since 2026."


def test_a_page_without_the_history_still_renders():
    snap = _snap(drop=("NYSE_NL52W",))
    assert snap.history is None
    assert view.HISTORY_TITLE not in st.render(snap, COLORS)


def test_the_history_card_offers_windows_and_opens_on_everything():
    """1Y to Max, zooming every row together. Max is pressed as rendered, so the page
    without its script is the whole history; a window longer than the history is not
    offered."""
    snap = _snap()
    n = len(snap.history.dates)
    page = st.render(snap, COLORS)
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    offered = re.findall(r'<button type="button" data-sessions="(\d+)" aria-pressed="(\w+)">'
                         r'(\w+)</button>', card)
    assert offered == [(str(sessions), "true" if label == "Max" else "false", label)
                       for label, sessions in view.HISTORY_WINDOWS if sessions < n]
    assert ("Max" in [label for _, _, label in offered]) and len(offered) >= 2
    assert f'id="{st.HISTORY_ID}" data-sessions="{n}"' in card
    # The script zooms by viewBox and refits the price to the window on screen.
    assert "svg.setAttribute('viewBox'" in page and f"getElementById('{st.HISTORY_ID}')" in page


def test_the_axis_carries_every_month_start_for_the_script_to_label_any_window():
    h = _snap().history
    months = view.history_month_starts(h)
    assert months[0] == [0, h.dates[0][:7]]
    assert [m for _, m in months] == sorted({d[:7] for d in h.dates})
    assert all(h.dates[i][:7] == m and (i == 0 or h.dates[i - 1][:7] != m) for i, m in months)
    page = st.render(_snap(), COLORS)
    raw = re.search(r'data-months="([^"]*)"', page).group(1)
    assert json.loads(html.unescape(raw)) == months


def test_the_price_line_is_daily_where_a_zoom_will_look():
    """Weekly points are fine at nineteen years across; a one-year window needs the
    daily line, so the most recent sessions keep every point."""
    dates = tuple(d.strftime("%Y-%m-%d") for d in pd.bdate_range("2015-01-01", periods=2000))
    h = mi.HeadwindHistory(dates=dates, price=tuple(100.0 + i for i in range(2000)),
                           price_symbol="QQQ", rows=(), count=(0,) * 2000, total=5)
    xs = [int(pt.split(",")[0]) for pt in view.history_price_points(h).split()]
    recent = 2000 - view.HISTORY_DAILY_SESSIONS
    assert xs[-view.HISTORY_DAILY_SESSIONS:] == list(range(recent, 2000))
    older = [x for x in xs if x < recent]
    assert older == list(range(0, recent, view.HISTORY_PRICE_STEP))


def _with_volatility(inverted=False):
    frames = _universe(N)
    idx = frames["QQQ"].index
    frames[mi.VOLATILITY_SYMBOL] = pd.DataFrame({"Close": 24.0 if inverted else 18.0}, index=idx)
    frames[mi.VOLATILITY_TERM_SYMBOL] = pd.DataFrame({"Close": 21.0}, index=idx)
    return mi.build_snapshot(_bars(frames))


def test_the_volatility_card_is_drawn_outside_the_count():
    snap = _with_volatility(inverted=True)
    page = st.render(snap, COLORS)
    uncounted = page.split(f"<h2>{view.UNCOUNTED_TITLE}</h2>")[1].split('<div class="sec">')[0]
    assert f"<h2>{html.escape(view.VOLATILITY_TITLE)}</h2>" in uncounted
    assert '<span class="big">24.0</span>' in uncounted and ">Inverted</span>" in uncounted
    assert html.escape(view.volatility_status(snap.volatility)) in uncounted
    spec = _payload(page)[st.VOLATILITY_KEY]
    assert len(spec["series"]) == 2 and spec["levels"] == []
    assert mi.headline(snap) == mi.headline(_snap())
    assert ">Normal</span>" in st.render(_with_volatility(), COLORS)
    # Without the series there is no card and no chart, not an "awaiting" one.
    plain = st.render(_snap(), COLORS)
    assert view.VOLATILITY_TITLE not in plain and st.VOLATILITY_KEY not in _payload(plain)


def _survey_parts():
    from components import aaii_allocation, aaii_votes, naaim_card
    from tests.test_aaii_allocation import _alloc_bars
    from tests.test_aaii_votes import _legs_bars
    from tests.test_naaim_card import _naaim_bars
    return {"naaim": naaim_card.read(_naaim_bars()[1]),
            "votes": aaii_votes.read(_legs_bars()[1]),
            "allocation": aaii_allocation.read(_alloc_bars()[1])}


def _positioning():
    dates = tuple(d.strftime("%Y-%m-%d") for d in pd.date_range("2023-11-21", periods=156,
                                                              freq="W-TUE"))
    path = tuple(float(40 + i % 30) for i in range(52))
    series = (dates, tuple(float(i % 20 - 10) for i in range(156)))
    others = (tuple(-v for v in series[1]), tuple(v / 4 for v in series[1]))
    return (mi.EquityPositioning("ES", "S&P 500", (81.0, 59.0, 59.0, 58.0), -10.9, path,
                                 "1986-01-15", 51234.0, series, "2026-11-10", others),
            mi.EquityPositioning("RTY", "Russell", (0.0, 1.0, 26.0, None), 0.4,
                                 path[:-1] + (20.0,), "2002-08-13", -3300.0, series, "2026-11-10", others))


def test_each_survey_block_is_its_reading_over_the_surveys_pages_own_percentiles():
    """The current reading, then a bar per history with the percentile in a dot: the
    same three numbers the surveys page's Percentiles card prints, read from the same
    objects (`naaim.latest`, the votes' spread percentiles, the allocation's)."""
    parts = _survey_parts()
    assert all(part is not None for part in parts.values())
    page = st.render(_snap(), COLORS, **parts)
    section = page.split(f'id="{st.SENTIMENT_ID}"')[1].split("</div>\n")[0]
    blocks = view.percentile_blocks(date_text=st._date, **parts)
    assert [b["key"] for b in blocks] == ["naaim", "aaii", "stocks"]
    assert section.count('<div class="pblock"') == 3
    for b in blocks:
        card = section.split(f'data-key="{b["key"]}"')[1].split('<div class="pblock"')[0]
        assert f'<div class="value">{html.escape(b["value"])}</div>' in card
        assert card.count('<div class="rail">') == len(b["rows"])
        for label, position, text, tier in b["rows"]:
            assert f'<div class="rl">{html.escape(label)}</div>' in card
            assert f'<i class="tier-{tier}" style="left:{position}%">{text}</i>' in card
    naaim, votes, allocation = parts["naaim"], parts["votes"], parts["allocation"]
    by_key = {b["key"]: b for b in blocks}
    # Three histories for a survey, and the positions ARE the surveys page's numbers.
    assert [(label, pct) for label, pct, _, _ in by_key["naaim"]["rows"]] == \
        [(label, pct) for label, pct, _, _ in naaim.latest]
    assert len(by_key["naaim"]["rows"]) == len(by_key["aaii"]["rows"]) == 3
    assert by_key["aaii"]["rows"][0][1] == votes.spread_latest_pct["spread"][0]
    assert by_key["stocks"]["rows"][0][1] == allocation.latest_pct["stocks"][0]
    assert by_key["naaim"]["value"] == f"{naaim.recent.iloc[0]:.1f}"
    assert f'href="{st.SURVEYS_URL}"' in page and st.SURVEYS_URL.startswith("https://surveys.")


def test_positioning_is_its_own_section_with_the_boards_row_per_market():
    """ES, YM, NQ and RTY as the crowd board draws them: the commercial index on four
    lookbacks in filled cells, the six-week change, and the 52-week path."""
    from components import board_traces
    reads = _positioning()
    page = st.render(_snap(), COLORS, positioning=reads)
    assert f"<h2>{view.POSITIONING_TITLE}</h2>" in page
    card = page.split(f'id="{st.POSITIONING_ID}"')[1].split("</section>")[0]
    head = re.findall(r"<th[^>]*>([^<]*)</th>", card)
    assert head == ["", "", *board_traces.WINDOW_LABELS, view.POSITIONING_CHANGE,
                    view.POSITIONING_PATH]
    colors = st.page_colors(COLORS)
    es = card.split('data-key="ES"')[1].split("</tr>")[0]
    assert "S&amp;P 500 <small>&#x27;86</small>" in es or "S&amp;P 500 <small>'86</small>" in es
    assert re.findall(r'<span class="cell"[^>]*>(\d+)</span>', es) == ["81", "59", "59", "58"]
    fill = board_traces.cell_fill(81.0, colors, background=surveys.SURFACE_COLOR)
    assert f"background:{fill};" in es
    assert f'<span style="color:{colors.bear}">▼</span> -11' in es
    assert "<polyline" in es and "<circle" in es
    rty = card.split('data-key="RTY"')[1].split("</tr>")[0]
    # A lookback the history cannot fill is a dash, not a zero; a flat change is a dot.
    assert rty.count('class="cell none"') == 1 and ">0</span>" in rty
    assert f'<span style="color:{surveys.MUTED}">•</span> +0' in rty
    assert f'fill="{colors.bear}"' in rty                 # the path ends under 50
    assert "report of Nov 10, 2026" in card


def test_each_market_has_its_commercials_through_time():
    reads = _positioning()
    page = st.render(_snap(), COLORS, positioning=reads)
    data = _payload(page)
    palette = ["#F87171", "#60A5FA", "#FBBF24", "#34D399"]
    page = st.render(_snap(), COLORS, positioning=reads, palette=palette)
    data = _payload(page)
    groups = st.group_colors(palette)
    assert groups == ("#F87171", "#60A5FA", "#FBBF24")     # commercial, large, small
    for r in reads:
        spec = data[st.POSITIONING_PREFIX + r.symbol]
        assert spec == view.positioning_chart(r, groups)
        # A column a week from zero for each group, in the app palette's colours. A
        # series is a rank within the week, tallest first (drawn at the back), so no
        # group's column hides a shorter one; each point carries its group's colour.
        assert [s["type"] for s in spec["series"]] == ["histogram"] * 3
        tones = [plot_colors.hex_to_rgba(c, view.POSITIONING_ALPHA) for c in groups]
        assert all(len(s["data"]) == 156 for s in spec["series"])
        back, middle, front = (s["data"] for s in spec["series"])
        for i, value in enumerate(r.series[1]):
            assert abs(back[i]["value"]) >= abs(middle[i]["value"]) >= abs(front[i]["value"])
            week = {(p["value"], p["color"]) for p in (back[i], middle[i], front[i])}
            assert week == {(value, tones[0]), (r.others[0][i], tones[1]),
                            (r.others[1][i], tones[2])}
        # Small specs are a quarter of commercials on the fixture: in front, in yellow.
        assert front[0] == {"time": r.series[0][0], "value": r.others[1][0], "color": tones[2]}
        assert [lv["value"] for lv in spec["levels"]] == [0.0]
        assert f'data-chart="{st.POSITIONING_PREFIX}{r.symbol}"' in page
    for label, color in zip(view.POSITIONING_GROUPS, groups):
        assert f'style="color:{color}">■ {label}</span>' in page
    # No figure beside a market's name: the charts are read for their shape.
    assert "51,234" not in page and "3,300" not in page
    points, end = view.positioning_spark(reads[0])
    assert len(points.split()) == 52 and end is not None
    assert view.positioning_spark(mi.EquityPositioning(
        "X", "X", (None,) * 4, None, (None, 50.0), None, 0.0, ((), ()), "2026-11-10")) == ("", None)


def test_the_rail_dot_prints_the_number_and_takes_the_tiers_tone():
    assert view._rail("Since 1987", 96, "96th") == ("Since 1987", 96, "96", "top")
    assert view._rail("Last year", 4, "4th") == ("Last year", 4, "4", "bottom")
    assert view._rail("Last year", 53, "53rd") == ("Last year", 53, "53", "mid")
    assert view._rail("Since 1987", 100, "highest") == ("Since 1987", 100, "hi", "top")
    assert view._rail("Since 1987", 1, "lowest") == ("Since 1987", 1, "lo", "bottom")


def test_sentiment_and_positioning_is_context_and_optional():
    plain = st.render(_snap(), COLORS)
    assert f"<h2>{view.POSITIONING_TITLE}</h2>" not in plain
    assert f"<h2>{view.SENTIMENT_TITLE}</h2>" not in plain
    assert f'id="{st.POSITIONING_ID}"' not in plain and f'id="{st.SENTIMENT_ID}"' not in plain
    assert mi.headline(_snap())[0].partition(" ")[2] in plain


def test_the_history_marks_are_the_headwind_cards_red():
    """A mark on the strips and a card's "Headwind" are one thing, so one colour: the
    page's toned red, not the amber the strips were first drawn in."""
    page = st.render(_snap(), COLORS)
    red = st.page_colors(COLORS).bear
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    # The warm tone is FOMO's stretched band, in its own row, never a headwind mark.
    strips = card.split('class="hfomo"')[0]
    assert f'fill="{red}"' in strips and surveys.TONE_HIGH not in strips
    assert f".hl.all {{ color: {red};" in page


def test_the_volatility_card_carries_the_move_index_when_the_store_has_it():
    frames = _universe(N)
    idx = frames["QQQ"].index
    frames[mi.VOLATILITY_SYMBOL] = pd.DataFrame({"Close": 18.0}, index=idx)
    frames[mi.VOLATILITY_TERM_SYMBOL] = pd.DataFrame({"Close": 21.0}, index=idx)
    without = st.render(mi.build_snapshot(_bars(frames)), COLORS)
    assert view.BOND_VOLATILITY_TITLE not in without
    assert st.BOND_VOLATILITY_KEY not in _payload(without)
    frames[mi.VOLATILITY_BOND_SYMBOL] = pd.DataFrame(
        {"Close": [80.0] * (N - 1) + [98.6]}, index=idx)
    snap = mi.build_snapshot(_bars(frames))
    page = st.render(snap, COLORS)
    # A card of its own beside the VIX's, not a block inside it.
    vix = page.split(f"<h2>{html.escape(view.VOLATILITY_TITLE)}</h2>")[1].split("</section>")[0]
    assert view.BOND_VOLATILITY_TITLE not in html.unescape(vix)
    card = page.split(f"<h2>{html.escape(view.BOND_VOLATILITY_TITLE)}</h2>")[1].split("</section>")[0]
    assert '<span class="big">98.6</span>' in card
    assert html.escape(view.bond_volatility_status(snap.volatility.bonds)) in card
    spec = _payload(page)[st.BOND_VOLATILITY_KEY]
    assert len(spec["series"]) == 1 and len(spec["series"][0]["data"]) == 252


def test_the_detail_section_draws_a_year_of_highs_lows_and_their_net():
    """The dashboard's two detail charts: highs above the line and lows below it as
    bars, and the net with the 5-day average the headwind reads, its side below zero
    shaded."""
    snap = _snap()
    b = snap.breadth
    page = st.render(snap, COLORS)
    detail = page.split(f"<h2>{view.DETAIL_TITLE}</h2>")[1]
    assert f"<h2>{view.HIGHS_LOWS_TITLE}</h2>" in detail and f"<h2>{view.NET_HISTORY_TITLE}</h2>" in detail
    data = _payload(page)
    up, down = data[st.HIGHS_LOWS_KEY]["series"]
    assert up["type"] == down["type"] == "histogram"
    assert [pt["value"] for pt in up["data"]] == list(b.highs)
    assert [pt["value"] for pt in down["data"]] == [-v for v in b.lows]      # drawn downward
    daily, average = data[st.NET_HISTORY_KEY]["series"]
    assert "type" not in daily and [pt["value"] for pt in daily["data"]] == list(b.net)
    assert average["type"] == "baseline" and average["base"] == mi.NET_HIGHS_LEVEL
    # An average before its window fills is dropped, not drawn at zero.
    assert len(average["data"]) == sum(v is not None for v in b.average)
    assert f"New highs {b.highs[-1]:.0f}" in detail and f"New lows {b.lows[-1]:.0f}" in detail
    # The script knows the two new series kinds.
    assert "LC.HistogramSeries" in page and "LC.BaselineSeries" in page


def test_no_breadth_charts_without_both_exchanges_counts():
    snap = _snap(drop=("NYSE_NL52W",))
    assert snap.breadth is None
    page = st.render(snap, COLORS)
    assert f"<h2>{view.HIGHS_LOWS_TITLE}</h2>" not in page
    assert st.HIGHS_LOWS_KEY not in _payload(page)


def test_every_headwind_row_is_a_switch_and_fomo_is_the_bottom_row_of_bars():
    """A row's name is a button. The six headwinds start on and are what the count is
    made of (`data-headwind`). FOMO is the bottom row: not a switch, never counted,
    its daily bars drawn on 0 to 100 with the two extremes banded."""
    from cotmetrics import indicators
    snap = _snap()
    h = snap.history
    assert h.fomo is not None
    page = st.render(snap, COLORS)
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    switches = re.findall(r'<button type="button" class="hl htog" data-row="(\w+)" '
                          r'aria-pressed="(\w+)">', card)
    assert switches == [(k, "true") for k in mi.HEADWIND_KEYS]
    assert card.count("data-headwind") == len(mi.HEADWIND_KEYS)
    assert 'class="hp off"' not in card and 'data-band="fomo"' not in card
    # The FOMO row comes after "All 6 at once" and before the axis.
    assert card.index("data-all-label") < card.index('class="hfomo"') < card.index("hyears")
    row = card.split('class="hfomo"')[1].split("</svg>")[0]
    bars, first = h.fomo
    path = row.split('data-fomo="bars"')[1].split(' d="')[1].split('"')[0]
    assert path.count("M") == 3 * sum(b is not None for b in bars)
    assert f'data-upto="{view.HISTORY_FOMO_DAILY_UPTO}" display="none"' in row
    washed, over = view.history_fomo_extremes(h)
    marks = row.split('<g data-fomo="extremes">')[1].split("</g>")[0]
    assert marks.count("<rect") == len(view.runs(washed)) + len(view.runs(over))
    # The marks sit under the bars, and the script never hides them.
    assert row.index('data-fomo="extremes"') < row.index('data-fomo="bars"')
    assert """[data-fomo="extremes"]').setAttribute""" not in page
    assert f'fill="{surveys.TONE_LOW}"' in row and f'fill="{surveys.TONE_HIGH}"' in row
    for level in (indicators.FOMO_FEAR_MAX, indicators.FOMO_EXHAUSTION_MIN):
        assert f'y1="{view.HISTORY_FOMO_UNITS - level:g}"' in row
    assert f'data-closes="{view.history_fomo_closes(h)}"' in card
    assert '<g data-band="most">' in card and '<g data-band="every">' in card
    assert 'data-shade="most" aria-pressed="true"' in card
    assert 'data-shade="every" aria-pressed="false"' in card
    assert f'data-total="{h.total}"' in card and "data-history-summary" in card
    assert "svg[data-headwind]" in page and "function recount()" in page
    assert html.escape(view.HISTORY_FOMO_LABEL) in card


def test_the_fomo_path_is_high_to_low_with_open_and_close_ticks():
    import dataclasses
    h = dataclasses.replace(_snap().history, fomo=(((41.6, 41.6, 14.4, 14.4), None), 0))
    assert view.history_fomo_path(h) == "M0.5 58.4V85.6M0.15 58.4H0.5M0.5 85.6H0.85"
    assert view.history_fomo_closes(h) == "14.4,"


def test_the_history_draws_without_a_fomo_row_when_the_series_is_missing():
    snap = _snap(drop=(mi.FOMO_SYMBOL,))
    assert snap.history is not None and snap.history.fomo is None
    card = st.render(snap, COLORS).split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    assert 'class="hfomo"' not in card and 'data-band="fomo"' not in card


def test_sentiment_dots_are_warm_and_cool_not_green_and_red():
    """How unusual a reading is, in the surveys tiles' tones. Green and red would have
    to mean either the crowd's mood or a signal, which are opposite readings."""
    page = st.render(_snap(), COLORS, **_survey_parts())
    colors = st.page_colors(COLORS)
    rail_rules = [line for line in page.splitlines() if line.startswith(".rail i.tier-")]
    assert rail_rules == [
        f".rail i.tier-top, .rail i.tier-high {{ background: {surveys.TONE_HIGH}; }}",
        f".rail i.tier-bottom, .rail i.tier-low {{ background: {surveys.TONE_LOW}; }}"]
    assert not any(colors.bull in line or colors.bear in line for line in rail_rules)


def test_numbers_on_a_fill_never_take_the_apps_cream():
    """`plot_colors.cell_text_colour` hands back the app's bright ink for a dark fill;
    on this page that is the family's white. With positioning and the surveys on the
    page, neither app text colour appears anywhere."""
    import viz_constants as vc
    from components import plot_colors
    assert st.ink_on("#000000") == surveys.INK
    assert st.ink_on("#ffffff") == plot_colors.INK_DARK
    page = st.render(_snap(), COLORS, positioning=_positioning(), **_survey_parts()).lower()
    assert vc.TEXT_COLOR.lower() not in page and vc.BRIGHTER_TEXT_COLOR.lower() not in page


def test_provisional_readings_are_marked_on_their_cards_and_in_the_notes():
    from tests.test_market_internals import _with_siblings
    frames = _universe(N)
    legs = {s: 400 for _, hi, lo in mi.NET_HIGHS_SYMBOLS for s in (hi, lo)}
    with_bars, _ = _with_siblings(frames, {mi.FOMO_SYMBOL: 9.5, **legs})
    snap = mi.build_snapshot(_bars(with_bars))
    page = st.render(snap, COLORS)
    chip = '<span class="prov"'
    fomo = page.split(f"<h2>{html.escape(view.FOMO_TITLE)}</h2>")[1].split("</section>")[0]
    assert chip in fomo and ">provisional</span>" in fomo
    for key in ("nasdaq_net_highs", "nyse_net_highs"):
        assert chip in page.split(f'data-key="{key}"')[1].split("</section>")[0]
    for key in ("qqq_updown", "credit", "rotation"):       # prices, never provisional
        assert chip not in page.split(f'data-key="{key}"')[1].split("</section>")[0]
    assert html.escape(view.provisional_note(snap)) in page
    assert view.provisional_note(snap).startswith("Provisional: the newest FOMO, net new highs")
    # Settled: no chip anywhere and no sentence.
    plain = st.render(_snap(), COLORS)
    assert chip not in plain and "Provisional:" not in plain
    assert view.provisional_note(_snap()) == ""


def test_a_row_of_cards_never_leaves_a_hole():
    """Six headwinds are three across, twice; five (one awaiting data) are three and
    then two sharing the row; the four context cards (with the MOVE) are two across."""
    assert [st._across([0] * n) for n in (2, 3, 4, 5, 6)] == ["", " three", "", " five", " three"]
    page = st.render(_snap(), COLORS)
    assert f'<div class="cards three" id="{st.HEADWINDS_ID}">' in page
    short = st.render(_snap(drop=("NYSE_NL52W",)), COLORS)
    assert f'<div class="cards five" id="{st.HEADWINDS_ID}">' in short
    assert "Awaiting data for: nyse net highs." in short
    assert ".cards.five > :nth-child(n+4) { grid-column: span 3; }" in page


def test_the_headline_says_how_long_the_count_has_stood():
    snap = _snap()
    history = snap.history
    on = sum(h.on for h in snap.headwinds)
    start = len(history.count) - 1
    while start and history.count[start - 1] == on:
        start -= 1
    since = view.headline_since(snap)
    if start:
        assert since == (f"{on} of {history.total} since {view.day_text(history.dates[start])} "
                         f"({history.count[start - 1]} before).")
        assert html.escape(since) in st.render(snap, COLORS)
    else:
        assert since is None
    # A history that trails the cards by a session still dates the run, while its
    # count is the cards'; one that disagrees with them says nothing.
    import dataclasses
    trailing = dataclasses.replace(snap, date="2999-01-01")
    assert view.headline_since(trailing) == since
    other = (history.count[-1] + 1) % (history.total + 1)
    moved = dataclasses.replace(snap, history=dataclasses.replace(
        history, count=history.count[:-1] + (other,)))
    assert view.headline_since(moved) is None
    assert view.headline_since(dataclasses.replace(snap, history=None)) is None


def test_jump_links_name_only_the_sections_on_the_page():
    plain = st.render(_snap(), COLORS)
    links = re.findall(r'<a href="#([a-z]+)">', plain.split('<nav class="jumps"')[1].split("</nav>")[0])
    assert links == [st.HEADWINDS_ID, st.HISTORY_ID, st.CONTEXT_ID, st.ANOMALIES_ID,
                     st.DETAIL_ID]
    assert all(f'id="{anchor}"' in plain for anchor in links)
    full = st.render(_snap(), COLORS, positioning=_positioning(), **_survey_parts())
    links = re.findall(r'<a href="#([a-z]+)">', full.split('<nav class="jumps"')[1].split("</nav>")[0])
    assert links == [anchor for anchor, _ in st.JUMPS]


def test_the_history_names_the_session_under_the_pointer():
    """The script gets every session's date as steps from the first, and a line to
    write the reading in; the steps add back up to the history's own dates."""
    from datetime import datetime, timedelta
    snap = _snap()
    h = snap.history
    first, steps = view.history_day_steps(h)
    day, dates = datetime.strptime(first, "%Y-%m-%d"), [first]
    for step in steps.split(","):
        day += timedelta(days=int(step))
        dates.append(day.strftime("%Y-%m-%d"))
    assert tuple(dates) == h.dates
    page = st.render(snap, COLORS)
    assert f'data-first="{first}" data-steps="{steps}"' in page
    assert f'data-history-read aria-live="polite">{view.HISTORY_READ_HINT}</div>' in page
    # The reader's window, shading and rows are kept in the browser, behind a try.
    assert "localStorage.getItem(KEY)" in page and "localStorage.setItem(KEY" in page


def test_a_shared_link_has_a_preview_and_no_card_carries_a_jump_link():
    page = st.render(_snap(), COLORS)
    assert f'<link rel="canonical" href="{st.URL}">' in page
    assert st.URL == "https://internals.bluemagicai.com/"
    for name in ("og:title", "og:description", "og:url", "og:type", "og:site_name"):
        assert f'<meta property="{name}" content="' in page
    # The year of counts is still on the page, under Detail; the cards no longer
    # link down to it (dropped as clutter).
    assert f'id="{st.BREADTH_ID}"' in page and '<a class="jump"' not in page


def test_an_old_page_says_so_from_the_readers_own_clock():
    """The warning ships hidden with the snapshot's date; the script shows it once the
    reader's clock is past the allowance, so a failed publish cannot pass for today."""
    snap = _snap()
    page = st.render(snap, COLORS)
    note = re.search(r'<p class="stale"[^>]*>', page).group(0)
    assert " hidden " in note
    assert f'data-through="{snap.date}"' in note
    assert f'data-after="{st.STALE_AFTER_DAYS}"' in note
    assert page.index('class="stale"') < page.index('class="count"')
    assert "note.hidden = false" in page
    # A holiday weekend read just before the next publish is still a healthy page.
    assert st.STALE_AFTER_DAYS >= 5


def test_the_time_axis_labels_months_and_years_only():
    """A wide card fits more marks than a narrow one; none of them is a bare day."""
    page = st.render(_snap(), COLORS)
    assert "tickMarkFormatter" in page
    assert "LC.TickMarkType.Month" in page and "LC.TickMarkType.Year" in page
    assert "entireTextOnly: true" in page


def test_the_positioning_table_fits_a_phone_without_its_name_and_path_columns():
    page = st.render(_snap(), COLORS, positioning=_positioning())
    card = page.split(f'id="{st.POSITIONING_ID}"')[1].split("</section>")[0]
    rows = card.count("<tr data-key=")
    assert card.count('class="name"') == rows + 1          # a cell a row, and the header
    assert card.count('class="num path"') == rows and card.count('<th class="path">') == 1
    assert "table.cot .name, table.cot .path { display: none; }" in page


def test_a_legend_wraps_whole_items():
    page = st.render(_snap(), COLORS, positioning=_positioning())
    assert page.count('class="detail legend"') == 3
    assert "white-space: nowrap" in page.split(".key {")[1].split("}")[0]


def test_each_headwind_card_carries_its_own_how_to_read():
    """The explanation sits on the card it explains, as a closed list of points, and
    the section's own fold no longer defines every measure at once."""
    page = st.render(_snap(), COLORS)
    assert set(view.HEADWIND_HOWS) == set(mi.HEADWIND_KEYS)
    for key, points in view.HEADWIND_HOWS.items():
        card = page.split(f'data-key="{key}"')[1].split("</section>")[0]
        assert '<details class="how">' in card
        assert all(f"<li>{html.escape(p)}</li>" in card for p in points)
        others = [p for k, ps in view.HEADWIND_HOWS.items() if k != key for p in ps]
        assert not any(f"<li>{html.escape(p)}</li>" in card for p in others if p not in points)
    section = page.split('<div class="sec"><h2>Market headwinds</h2>')[1].split("</details>")[0]
    assert "Up/down volume" not in section and "<li>" in section


def test_the_nyse_card_carries_the_lows_share_and_the_fills_are_the_states():
    snap = _snap()
    colors = st.page_colors(COLORS)
    page = st.render(snap, COLORS)
    # Each net-highs card folds its own new-lows share under its columns, closed.
    for share in snap.lows_shares:
        card = page.split(f'data-key="{mi.net_highs_key(share.exchange)}"')[1].split("</section>")[0]
        key = st.LOWS_SHARE_PREFIX + share.exchange.lower()
        assert '<details class="share" data-lows-share>' in card
        assert f"{share.value:.1f}%</span></summary>" in card and " line</summary>" not in card
        assert card.index(f'data-chart="{st.HEADWIND_PREFIX}{mi.net_highs_key(share.exchange)}"') \
            < card.index(f'data-chart="{key}"') < card.index("Flips at")
        spec = _payload(page)[key]
        assert [lv["value"] for lv in spec["levels"]] == [mi.LOWS_SHARE_LINE]
        (cols,) = spec["series"]
        assert cols["type"] == "histogram" and len(cols["data"]) == len(share.path[0])
        assert all((p.get("color") == colors.bear) == (p["value"] >= mi.LOWS_SHARE_LINE)
                   for p in cols["data"])
    assert page.count("data-lows-share") == 2
    data = _payload(page)
    up = data[st.HEADWIND_PREFIX + "qqq_updown"]["series"][0]
    assert up["type"] == "baseline" and up["base"] == 1.0 and up["top"] and up["shade"]
    for key in ("credit", "rotation"):
        upper, lower, line, average_line = data[st.HEADWIND_PREFIX + key]["series"]
        assert upper["type"] == lower["type"] == "area" and "type" not in line
        # The band runs from the lower of line and average to the upper.
        h = next(h for h in snap.headwinds if h.key == key)
        _, values, average = h.path
        both = [(v, a) for v, a in zip(values, average) if a is not None]
        assert [p["value"] for p in upper["data"]] == [max(v, a) for v, a in both]
        assert [p["value"] for p in lower["data"]] == [min(v, a) for v, a in both]
        assert {p["topColor"] for p in lower["data"]} == {view.SURFACE_COLOR}
    h = next(h for h in snap.headwinds if h.key == "rotation")
    dates, values, average = h.path
    fill = [p for p in data[st.HEADWIND_PREFIX + "rotation"]["series"][0]["data"]]
    values, average = zip(*[(v, a) for v, a in zip(values, average) if a is not None])
    from components import plot_colors
    bad = plot_colors.hex_to_rgba(colors.bear, view.STATE_FILL)
    assert [p["topColor"] == bad for p in fill] == [
        a is not None and v > a for v, a in zip(values, average)]
    assert "LC.AreaSeries" in page


def test_the_anomaly_cards_draw_a_cell_a_session_and_shade_the_flagged_days():
    snap = _snap()
    assert snap.anomalies                       # JNK/TLT and XLP/QQQ; no VIX in the fixture
    page = st.render(snap, COLORS)
    assert f'id="{st.ANOMALIES_ID}"' in page and f'href="#{st.ANOMALIES_ID}"' in page
    for read in snap.anomalies:
        card = page.split(f'data-anomaly="{read.key}"')[1].split("</section>")[0]
        assert card.count('class="ac"') == 2 * len(read.sessions)
        flagged = sum(1 for s in read.sessions if s[3])
        assert card.count('class="ac" title=') == 2 * len(read.sessions)
        assert len(re.findall(r'class="ac" title="[^"]*" style="background:rgba\(', card)) \
            == 2 * flagged
        assert html.escape(view.anomaly_tally(read)) in card
        assert html.escape(view.anomaly_tip(read, read.sessions[-1])) in card
        assert '<details class="how">' in card
    # Context: the count does not move.
    assert view.anomaly_badge(snap.anomalies[0]) in ("Anomaly", "Normal")


def test_the_anomalies_sit_below_sentiment_and_positioning():
    page = st.render(_snap(), COLORS, positioning=_positioning(), **_survey_parts())
    at = {anchor: page.index(f'id="{anchor}"') for anchor, _ in st.JUMPS}
    assert at[st.SENTIMENT_ID] < at[st.POSITIONING_ID] < at[st.ANOMALIES_ID] < at[st.DETAIL_ID]


def test_the_fomo_card_has_a_gauge_the_last_closes_and_the_days_range():
    import dataclasses
    snap = _snap()
    fomo = dataclasses.replace(snap.fomo, value=14.4, bar=(41.6, 41.6, 14.4, 14.4))
    page = st.render(dataclasses.replace(snap, fomo=fomo), COLORS)
    card = page.split(f"<h2>{html.escape(view.FOMO_TITLE)}</h2>")[1].split("</section>")[0]
    assert '<div class="fg"' in card and 'class="fm" style="left:14.4%"' in card
    assert 'class="fr" style="left:14.4%;width:27.2%"' in card
    assert view.fomo_day(fomo) == "Day: open 41.6 · high 41.6 · low 14.4 · close 14.4"
    assert html.escape(view.fomo_day(fomo)) in card and html.escape(view.fomo_recent(fomo)) in card
    bare = st.render(snap, COLORS)
    card = bare.split(f"<h2>{html.escape(view.FOMO_TITLE)}</h2>")[1].split("</section>")[0]
    assert '<div class="fg"' in card and "Day: open" not in card and 'class="fr"' not in card


def test_the_long_windows_mark_fomos_extreme_closes():
    import dataclasses
    h = _snap().history
    bars = ((30.0, 35.0, 20.0, 19.9), None, (14.0, 85.0, 14.0, 80.0), (41.6, 41.6, 14.4, 50.0))
    h = dataclasses.replace(h, dates=h.dates[:4], fomo=(bars, 0))
    assert view.history_fomo_extremes(h) == ((True, False, False, False),
                                             (False, False, True, False))
