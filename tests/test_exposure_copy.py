"""What the Aggregate Exposure page says in words.

A total is a claim about a set, so the set has to be readable. Everything here is
disclosure: which markets are in, which are out and why, whether a retired member is
truncating the series, and the publication lag that a chart of weekly positioning
against a daily price cannot show.
"""
import dash
import pandas as pd
from cotmetrics.exposure import LEG_COMM, LEG_SPEC, AggregateExposure

dash.Dash(__name__, use_pages=True, pages_folder='')

import components.exposure_traces as et  # noqa: E402
import viz_constants as vc  # noqa: E402
from components.plot_colors import GridColors  # noqa: E402

COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.4)",
                    bear_near="rgba(255,77,77,0.4)")
from pages.analytics.exposure import LEDE, caption, headline, how_to_read, membership  # noqa: E402


def agg(dropped=None, coverage=None, bounded_by=None, weeks_lost=0, rows=3):
    idx = pd.date_range("2026-01-06", periods=rows, freq="W-TUE")
    frame = pd.DataFrame({
        "net_contracts": [1.0] * rows,
        "notional_usd": [1e9] * rows,
        "risk_usd": [1e7] * rows,
        "n_markets": 2,
        "notional_pct_rank": [97.0] * rows,
        "risk_pct_rank": [97.0] * rows,
    }, index=idx)
    return AggregateExposure(frame, dropped or {},
                             coverage or {"A": (idx[0], idx[-1]),
                                          "B": (idx[0], idx[-1])},
                             bounded_by or {}, weeks_lost)


def text_of(children):
    return " ".join(str(getattr(c, "children", c)) for c in children)


# ── who is in the total ───────────────────────────────────────────────────────

def test_the_membership_line_counts_what_was_summed_against_what_was_asked_for():
    line = text_of(membership(agg(), ["A", "B", "C"]))
    assert "2 of 3 markets summed" in line


def test_a_dropped_market_is_NAMED_not_counted():
    """"2 markets dropped" tells a reader something is missing without telling them
    whether it is the one they came to look at."""
    line = text_of(membership(
        agg(dropped={"MSCI EAFE": "no contract multiplier, so its contracts cannot"}),
        ["A", "B", "MSCI EAFE"]))
    assert "MSCI EAFE" in line
    assert "no contract multiplier" in line


def test_a_member_that_truncates_the_series_is_named_with_the_way_out():
    """The live case: NKD retired from the COT in March 2026 and its class did not, so
    a strict equity total stops there while the other five markets run on, and nothing
    about the chart would say so."""
    idx = pd.date_range("2026-01-06", periods=3, freq="W-TUE")
    line = text_of(membership(
        agg(coverage={"Nikkei 225": (idx[0], idx[-1]), "S&P 500": (idx[0], idx[-1])},
            bounded_by={"end": "Nikkei 225"}),
        ["Nikkei 225", "S&P 500"]))
    assert "ENDS" in line
    assert "Nikkei 225" in line
    assert "remove it from Markets" in line


def test_the_weeks_the_completeness_rule_cost_are_reported():
    line = text_of(membership(agg(weeks_lost=705), ["A", "B"]))
    assert "705 week(s) not summed" in line


def test_a_whole_unbounded_total_claims_nothing_extra():
    line = text_of(membership(agg(), ["A", "B"]))
    assert "ENDS" not in line
    assert "dropped" not in line
    assert "not summed" not in line


# ── the caption ───────────────────────────────────────────────────────────────

def test_the_caption_states_the_publication_lag():
    """Plotted at the as-of Tuesday against a price line that WAS knowable that day, the
    chart reads as though the positioning was knowable too. It was not until the Friday,
    and this page sits two clicks from a setup gate."""
    text = caption(agg().frame, et.UNIT_RISK, LEG_SPEC)
    assert "as-of Tuesday" in text
    assert "published the following Friday" in text
    assert "three days before anyone could have acted on it" in text


def test_the_caption_gives_the_percentile_beside_the_level():
    """No level in this frame answers "is this a lot", because both notional and dollar
    risk carry the price level and drift upward over a long history whatever the
    positioning did."""
    text = caption(agg().frame, et.UNIT_RISK, LEG_SPEC)
    assert "97th percentile of its own history" in text


def test_the_caption_says_the_band_and_the_percentile_carry_no_look_ahead():
    text = caption(agg().frame, et.UNIT_NOTIONAL, LEG_COMM)
    assert "no look-ahead" in text


def test_the_caption_says_the_composite_is_not_tradeable():
    """It is an equal-weight rebased index of the set, which is not any index anyone
    quotes, and a reader who assumes otherwise will read the top panel as the S&P."""
    text = caption(agg().frame, et.UNIT_RISK, LEG_SPEC)
    assert "not any index you can trade" in text


def test_the_caption_names_the_side_it_is_on():
    long_text = caption(agg().frame, et.UNIT_RISK, LEG_SPEC)
    assert "net long" in long_text

    short = agg().frame.copy()
    short["risk_usd"] = -1e7
    assert "net short" in caption(short, et.UNIT_RISK, LEG_SPEC)


def test_a_series_too_short_for_a_percentile_says_so_rather_than_printing_nan():
    frame = agg().frame.copy()
    frame["risk_pct_rank"] = float("nan")
    text = caption(frame, et.UNIT_RISK, LEG_SPEC)
    assert "under two years of history" in text
    assert "nan" not in text.lower()


def test_an_empty_total_has_no_caption_to_give():
    assert caption(pd.DataFrame(), et.UNIT_RISK, LEG_SPEC) == ""


# ── the headline: the answer before the machinery ─────────────────────────────

def ranked(rank, value=1e7, unit="risk_usd"):
    frame = agg().frame.copy()
    frame[unit] = value
    frame["risk_pct_rank"] = rank
    frame["notional_pct_rank"] = rank
    return frame


def test_the_headline_names_the_crowd_rather_than_leaving_it_to_be_computed():
    """A reader arriving at a twenty-year chart of dollars has to read the last value
    and then decide whether it is big. The second is the one nobody can do by eye on a
    series that drifts with the price level, which is this page's whole hazard."""
    text, _ = headline(ranked(97.0), et.UNIT_RISK, LEG_SPEC)
    assert text.startswith("CROWDED LONG")
    assert "97%" in text


def test_a_low_percentile_on_a_negative_level_is_crowded_short():
    text, _ = headline(ranked(3.0, value=-1e7), et.UNIT_RISK, LEG_COMM)
    assert text.startswith("CROWDED SHORT")
    assert "97%" in text


def test_a_low_percentile_on_a_positive_level_is_light_not_short():
    """The crowd at its least long is not the crowd short, and calling it short would
    put a position on the page that nobody holds."""
    text, _ = headline(ranked(3.0, value=1e7), et.UNIT_RISK, LEG_SPEC)
    assert text.startswith("UNUSUALLY LIGHT")
    assert "SHORT" not in text


def test_an_ordinary_week_says_so_plainly():
    text, _ = headline(ranked(52.0), et.UNIT_RISK, LEG_SPEC)
    assert text.startswith("Within the usual range")


def test_too_little_history_declines_to_call_it():
    text, _ = headline(ranked(float("nan")), et.UNIT_RISK, LEG_SPEC)
    assert "Not enough history" in text
    assert "CROWDED" not in text


def test_the_headline_does_not_borrow_the_apps_verdict_colours():
    """Green and red mean bull setup and bear setup everywhere else here, and a crowded
    long is neither. Under a positioning-fade model it would read as the opposite of the
    green it was painted in. An extreme is emphasised, not coloured."""
    crowded, extreme_colour = headline(ranked(97.0), et.UNIT_RISK, LEG_SPEC)
    ordinary, normal_colour = headline(ranked(52.0), et.UNIT_RISK, LEG_SPEC)
    assert extreme_colour == vc.BRIGHTER_TEXT_COLOR
    assert normal_colour == vc.TEXT_COLOR
    assert extreme_colour != normal_colour
    for colour in (extreme_colour, normal_colour):
        assert colour not in (COLORS.bull, COLORS.bear)


def test_the_thresholds_are_the_bands_own_edges():
    """The reader sees a band drawn at the 10th and 90th and a word that fires at the
    10th and 90th. Two different numbers would make the word disagree with the picture
    it sits above."""
    from pages.analytics.exposure import CROWDED_HIGH, CROWDED_LOW
    assert (CROWDED_LOW, CROWDED_HIGH) == (et.BAND_LOW * 100, et.BAND_HIGH * 100)


# ── the standing explanation ──────────────────────────────────────────────────

def test_the_lede_answers_what_do_i_learn_without_jargon():
    assert "how much money" in LEDE.lower()
    for jargon in ("notional", "percentile", "sigma", "expanding"):
        assert jargon not in LEDE.lower()


def test_the_explanation_says_what_the_page_does_NOT_tell_you():
    """Positioning can sit at an extreme for months and this page runs no gate. A view
    that shows an extreme without saying that invites the reading it cannot support."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "not a signal" in body
    assert "no gate" in body


def test_the_explanation_covers_each_thing_a_reader_meets():
    titles = [t for t, _ in how_to_read(et.UNIT_RISK)]
    assert len(titles) == 4
    joined = " ".join(titles).lower()
    for topic in ("number", "band", "panels", "not"):
        assert topic in joined


def test_the_explanation_says_why_the_band_widens():
    """It is the page's central hazard: dollar figures grow with the price level, so the
    level alone cannot say whether today is a lot."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_NOTIONAL))
    assert "widens" in body
    assert "price level" in body


def test_the_explanation_reads_the_two_panels_together():
    """Exposure climbing with price and exposure falling while price climbs are opposite
    readings, and neither is visible in one panel alone."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "adding to a move" in body
    assert "being sold to" in body


def test_the_explanation_follows_the_unit_being_drawn():
    risk = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    notional = " ".join(b for _, b in how_to_read(et.UNIT_NOTIONAL))
    assert "vol-targeting" in risk
    assert "not comparable" in notional
