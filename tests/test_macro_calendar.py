"""The macro calendar section of the internals page.

Rows are marketdata `econ_calendar()` rows as the 2026-11-19 TradingView capture held
them (US, captured that evening): the values below are the vendor's, not invented, so the
formatting is pinned against real readings. Store-free.
"""
from datetime import date

import pandas as pd
import pytest

from components import macro_calendar as mc
from components import market_internals_static as st
from tests.test_sentiment import COLORS

CAPTURED = pd.Timestamp("2026-11-19")


def _row(t, title, ticker, imp, act=None, est=None, prev=None, unit=None, scale=None,
         period="", country="US"):
    return {"id": f"{t}{title}", "time_utc": pd.Timestamp(t, tz="UTC"), "title": title,
            "ticker": ticker, "importance": imp, "actual": act, "forecast": est,
            "previous": prev, "unit": unit, "scale": scale, "period": period,
            "country": country, "captured": CAPTURED, "category": "x"}


def table():
    return pd.DataFrame([
        _row("2026-11-16 13:30", "NY Empire State Manufacturing Index", "ECONOMICS:USNYESMI",
             0, 7.8, 18.0, 25.5),
        _row("2026-11-17 13:30", "Retail Sales MoM", "ECONOMICS:USRSMM", 1, 0.2, 0.2, 0.5, "%"),
        _row("2026-11-17 14:15", "Industrial Production MoM", "ECONOMICS:USIPMM", 0,
             -0.4, 0.1, 0.2, "%"),
        _row("2026-11-18 13:30", "Housing Starts", "ECONOMICS:USHST", 1, 1.309, 1.245,
             1.19, scale="M"),
        _row("2026-11-19 13:30", "Initial Jobless Claims", "ECONOMICS:USIJC", 0, 203, 197,
             200, scale="K"),
        # Noise the allowlist drops: an auction (no ticker) and a mortgage rate.
        _row("2026-11-19 18:00", "10-Year TIPS Auction Bid-to-Cover", None, 0, 2.43),
        _row("2026-11-18 12:00", "MBA 30-Year Mortgage Rate", "ECONOMICS:USMR", 0, 7.35,
             unit="%"),
        _row("2026-11-20 15:00", "Michigan Consumer Sentiment Final", "ECONOMICS:USCCI", 0,
             None, 51.5),
        # A ticker-less release kept by its title.
        _row("2026-11-24 15:00", "CB Consumer Confidence", None, 0, None, 92.0),
        _row("2026-11-25 13:30", "GDP Growth Rate QoQ 2nd Est", "ECONOMICS:USGDPQQ", 1,
             None, 3.4, unit="%"),
        _row("2026-12-04 13:30", "Non Farm Payrolls", "ECONOMICS:USNFP", 1, scale="K"),
        _row("2026-12-09 19:00", "Interest Rate", "ECONOMICS:USINTR", 1, unit="%"),
        _row("2026-12-10 13:30", "Inflation Rate YoY", "ECONOMICS:USIRYY", 1, None, 3.9,
             unit="%"),
        _row("2026-12-10 13:30", "Core Inflation Rate YoY", "ECONOMICS:USCIR", 1, None, 2.7,
             unit="%"),
        _row("2026-11-17 13:30", "Retail Sales MoM", "ECONOMICS:USRSMM", 1, 1.0,
             country="CA"),
    ])


def calendar(today=date(2026, 11, 19)):
    return mc.build(table(), today)


@pytest.mark.parametrize("v, unit, scale, out", [
    (7.8, None, None, "7.8"), (18.0, None, None, "18.0"), (0.2, "%", None, "0.2%"),
    (-0.4, "%", None, "-0.4%"), (0.0, "%", None, "0.0%"), (1.309, None, "M", "1.309M"),
    (203.0, None, "K", "203K"), (-404.0, "$", "B", "-$404B"), (None, None, None, ""),
    (float("nan"), "%", None, ""),
])
def test_values_print_as_release_tables_print_them(v, unit, scale, out):
    assert mc.fmt(v, unit, scale) == out


def test_two_weeks_monday_to_friday_in_eastern_time():
    cal = calendar()
    (l1, w1), (l2, w2) = cal.weeks
    assert (l1, l2) == ("This week", "Next week")
    assert [d.day for d in w1] == [date(2026, 11, 16 + i) for i in range(5)]
    assert [d.day for d in w2] == [date(2026, 11, 23 + i) for i in range(5)]
    mon = w1[0].events[0]
    assert (mon.name, mon.est, mon.act, mon.prev) == ("Empire State manufacturing",
                                                       "18.0", "7.8", "25.5")
    assert (mon.when.hour, mon.when.minute) == (8, 30)       # 13:30Z in November
    names = [e.name for d in w1 + w2 for e in d.events]
    assert "Retail sales" in names and names.count("Retail sales") == 1   # US only
    assert not any("TIPS" in n or "Mortgage" in n for n in names)
    assert "Conference Board confidence" in names
    assert "GDP (2nd estimate)" in names and "UMich consumer sentiment (final)" in names
    assert [e.high for e in w1[1].events] == [True, False]


def test_coming_up_names_the_headlines_after_next_week():
    assert calendar().coming_up == [("FOMC", date(2026, 12, 9)), ("CPI", date(2026, 12, 10)),
                                    ("Payrolls", date(2026, 12, 4))]


def test_a_weekend_looks_at_the_coming_week():
    cal = calendar(date(2026, 11, 21))
    assert cal.weeks[0][1][0].day == date(2026, 11, 23)
    assert mc.week_monday(date(2026, 11, 22)) == date(2026, 11, 23)
    assert mc.week_monday(date(2026, 11, 20)) == date(2026, 11, 16)


def test_nothing_to_show_means_no_section():
    assert mc.build(pd.DataFrame(), date(2026, 11, 19)) is None
    assert mc.build(table(), date(2027, 6, 1)) is None
    assert st.calendar_section(None) == ""


def test_an_old_capture_says_so():
    assert not calendar().stale
    assert calendar(date(2026, 11, 24)).stale


def test_read_without_the_reader_is_no_section(monkeypatch):
    import marketdata
    monkeypatch.delattr(marketdata, "econ_calendar", raising=False)
    assert mc.read() is None
    monkeypatch.setattr(marketdata, "econ_calendar", lambda: pd.DataFrame(), raising=False)
    assert mc.read() is None
    monkeypatch.setattr(marketdata, "econ_calendar", table, raising=False)
    assert mc.read(date(2026, 11, 19)) is not None


def test_the_section_renders_after_the_history_and_marks_today():
    from tests.test_market_internals_static import _snap
    page = st.render(_snap(), COLORS, calendar=calendar())
    assert page.index(f'id="{st.HISTORY_ID}"') < page.index(f'id="{st.CALENDAR_ID}"') \
        < page.index(f'id="{st.CONTEXT_ID}"')
    sec = page.split(f'id="{st.CALENDAR_ID}"')[1].split("</section>")[0]
    assert 'class="cday today"><div class="dh">Thu <b>Nov 19</b>' in sec
    assert sec.count('class="cday past"') == 3
    assert "<i>Est</i> 197K</span><span><i>Act</i> 203K" in sec
    assert "Coming up</b> FOMC Wed Dec 9 &middot; CPI Thu Dec 10" in sec
    assert mc.NOTE in sec and "captured Nov 19, 2026" in sec
    assert "<dt>Retail sales</dt>" in sec
    assert "\u2014" not in sec


def test_the_page_without_a_calendar_has_no_section():
    from tests.test_market_internals_static import _snap
    page = st.render(_snap(), COLORS)
    assert f'id="{st.CALENDAR_ID}"' not in page


# ── megacap earnings, kept by hand ────────────────────────────────────────────

def _earnings_file(tmp_path, rows):
    f = tmp_path / "megacap_earnings.csv"
    f.write_text("# a comment line\nsymbol,name,date,timing,source\n" + "\n".join(rows) + "\n")
    return f


def test_earnings_rows_without_a_date_are_skipped_and_the_rest_sorted(tmp_path):
    f = _earnings_file(tmp_path, ["AAPL,Apple,,,", "CRM,Salesforce,2026-12-02,after close,x",
                                  "DELL,Dell Technologies,2026-11-24,after close,x",
                                  "XYZ,Early Co,2026-12-02,before open,x"])
    got = mc.read_earnings(f)
    assert [(e.symbol, e.day, e.short) for e in got] == [
        ("DELL", date(2026, 11, 24), "Post"), ("XYZ", date(2026, 12, 2), "Pre"),
        ("CRM", date(2026, 12, 2), "Post")]
    assert mc.read_earnings(tmp_path / "missing.csv") == []


def test_a_typo_in_the_earnings_file_is_loud(tmp_path):
    with pytest.raises(ValueError, match="CRM"):
        mc.read_earnings(_earnings_file(tmp_path, ["CRM,Salesforce,2026-12-02,after hours,x"]))
    with pytest.raises(ValueError):
        mc.read_earnings(_earnings_file(tmp_path, ["CRM,Salesforce,12/02/2026,after close,x"]))


def test_earnings_land_in_their_day_and_only_inside_the_fortnight():
    earn = [mc.Earning(date(2026, 11, 24), "DELL", "Dell Technologies", "after close"),
            mc.Earning(date(2026, 12, 2), "CRM", "Salesforce", "after close"),
            mc.Earning(date(2026, 12, 9), "AVGO", "Broadcom", "after close")]
    cal = mc.build(table(), date(2026, 11, 23), earn)
    days = {d.day: [e.symbol for e in d.earnings] for _, w in cal.weeks for d in w}
    assert days[date(2026, 11, 24)] == ["DELL"] and days[date(2026, 12, 2)] == ["CRM"]
    assert "AVGO" not in sum(days.values(), [])               # Dec 9 is past next week
    page = st.calendar_section(cal)
    assert page.count('class="ev ern"') == 2
    assert '<li class="ev ern" data-earning="DELL"><span class="t" title="After close">Post</span>' in page


def test_the_committed_earnings_file_reads_cleanly():
    """The hand-kept list in the repo parses, and every dated row names its source."""
    rows = mc.read_earnings()
    frame = pd.read_csv(mc.EARNINGS_FILE, comment="#", dtype=str).fillna("")
    dated = frame[frame["date"] != ""]
    assert len(rows) == len(dated) and (dated["source"] != "").all()
    assert frame["symbol"].is_unique


# ── market holidays and the phone layout ──────────────────────────────────────

def test_market_notes_are_the_nyse_standing_rules():
    n26 = mc.market_notes(2026)
    assert n26[date(2026, 11, 26)] == (True, "Thanksgiving · market closed")
    assert n26[date(2026, 11, 27)] == (False, "Early close 1:00p")
    assert n26[date(2026, 4, 3)][1].startswith("Good Friday")
    assert n26[date(2026, 7, 3)][0] is True          # July 4 on a Saturday, observed Friday
    assert n26[date(2026, 7, 2)] == (False, "Early close 1:00p")
    assert n26[date(2026, 12, 24)] == (False, "Early close 1:00p") and n26[date(2026, 12, 25)][0]
    closed = sorted(d for d, (shut, _) in n26.items() if shut)
    assert len(closed) == 10 and date(2026, 1, 1) in closed and date(2026, 6, 19) in closed
    # New Year's Day on a Saturday is not observed; Christmas on a Saturday moves to Friday.
    n22 = mc.market_notes(2022)
    assert date(2021, 12, 31) not in n22 and date(2022, 1, 1) not in n22
    assert mc.market_notes(2021)[date(2021, 12, 24)][0] is True


def test_a_holiday_is_named_on_its_day_and_past_days_fold():
    cal = mc.build(table(), date(2026, 11, 25))
    days = {d.day: d for _, w in cal.weeks for d in w}
    assert days[date(2026, 11, 26)].market == (True, "Thanksgiving · market closed")
    assert days[date(2026, 11, 27)].market == (False, "Early close 1:00p")
    page = st.calendar_section(cal)
    thursday = page.split("<b>Nov 26</b>")[1].split("<b>Nov 27</b>")[0]
    assert '<div class="mk shut">Thanksgiving · market closed</div>' in thursday
    assert "No listed releases" not in thursday
    # A past day with releases is a fold, open in the markup; a phone's script closes it.
    assert page.count('<details class="pd" open>') == sum(
        1 for d in days.values() if d.day < cal.today and (d.events or d.earnings))
    from tests.test_market_internals_static import _snap
    assert "details.pd" in st.render(_snap(), COLORS, calendar=cal)
