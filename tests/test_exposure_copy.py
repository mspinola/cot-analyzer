"""What the Aggregate Exposure page says in words.

A total is a claim about a set, so the set has to be readable. Everything here is
disclosure: which markets are in, which are out and why, whether a retired member is
truncating the series, and the publication lag that a chart of weekly positioning
against a daily price cannot show.
"""
import dash
import numpy as np
import pandas as pd
from cotmetrics.exposure import LEG_COMM, LEG_SPEC, AggregateExposure

dash.Dash(__name__, use_pages=True, pages_folder='')

import components.exposure_traces as et  # noqa: E402
import viz_constants as vc  # noqa: E402
from components.plot_colors import GridColors  # noqa: E402

COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.4)",
                    bear_near="rgba(255,77,77,0.4)")
from pages.analytics.exposure import (  # noqa: E402
    LEDE,
    caption,
    column_name,
    composition_line,
    contribution_columns,
    contribution_grid,
    crosshair_shapes,
    headline,
    how_to_read,
    membership,
    money,
    ordinal,
    rewind_notice,
    snap_week,
    unit_name,
    week_row,
)


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
    # Keyword, not positional. AggregateExposure gained a `numeraire` field ahead of
    # `members`, and the positional form here bound the members dict to it silently:
    # every composition test went green-to-empty at once, which is the only reason it
    # was noticed.
    return AggregateExposure(frame=frame, dropped=dropped or {},
                             coverage=coverage or {"A": (idx[0], idx[-1]),
                                                   "B": (idx[0], idx[-1])},
                             bounded_by=bounded_by or {}, weeks_lost=weeks_lost)


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
    assert len(titles) == 8
    joined = " ".join(titles).lower()
    for topic in ("number", "band", "panels", "made of", "gold switch",
                  "scale switch", "third panel", "not"):
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


# ── the composition line ──────────────────────────────────────────────────────

def with_members(per_market, unit="risk_usd", rows=3):
    base = agg()
    idx = base.frame.index
    members = {name: pd.DataFrame({unit: [value] * rows,
                                   "notional_usd": [value] * rows}, index=idx)
               for name, value in per_market.items()}
    frame = base.frame.copy()
    frame[unit] = sum(per_market.values())
    return AggregateExposure(frame=frame, dropped={}, coverage=base.coverage,
                             bounded_by={}, weeks_lost=0, members=members)


def test_the_two_halves_are_named_when_they_disagree():
    """Large and Small sit on opposite sides 59% of weeks, and the sign of their total
    disagrees with one of them about a third of the time. The page could say CROWDED
    LONG on a week where one of the two groups inside that number is short."""
    from cotmetrics.exposure import LEG_LARGE, LEG_SMALL
    a = with_members({"S&P 500": 4e8, "Nasdaq": 1e8})
    parts = {LEG_LARGE: pd.Series([-1.56e8] * 3, index=a.frame.index),
             LEG_SMALL: pd.Series([6.65e8] * 3, index=a.frame.index)}
    line = composition_line(a, et.UNIT_RISK, LEG_SPEC, parts)
    assert "two halves disagree" in line
    assert "Small Traders long" in line
    assert "Large Speculators short" in line


def test_two_halves_pointing_the_same_way_are_said_to_agree():
    """Worth its clause either way: it tells a reader the headline is not one group's
    doing."""
    from cotmetrics.exposure import LEG_LARGE, LEG_SMALL
    a = with_members({"S&P 500": 4e8})
    parts = {LEG_LARGE: pd.Series([2e8] * 3, index=a.frame.index),
             LEG_SMALL: pd.Series([2e8] * 3, index=a.frame.index)}
    line = composition_line(a, et.UNIT_RISK, LEG_SPEC, parts)
    assert "Both halves agree" in line
    assert "disagree" not in line


def test_a_leg_that_is_not_a_sum_gets_no_split_clause():
    """Commercials are the exact mirror of Speculators, measured at 0.000000 across the
    store, so there is nothing to split them into that is not the identity."""
    line = composition_line(with_members({"A": 1e8}), et.UNIT_RISK, LEG_COMM, {})
    assert "halves" not in line


def test_a_market_holding_half_the_gross_is_called_out_as_being_the_total():
    line = composition_line(with_members({"S&P 500": 3.71e8, "Nasdaq": 1.16e8,
                                          "Russell": -5.7e7}),
                            et.UNIT_RISK, LEG_COMM, {})
    assert "S&P 500 alone is" in line


def test_a_total_with_no_dominant_market_names_the_largest_without_the_word_alone():
    line = composition_line(with_members({"A": 1.0e8, "B": 0.9e8, "C": 0.9e8}),
                            et.UNIT_RISK, LEG_COMM, {})
    assert "largest single market" in line
    assert "alone" not in line


def test_a_low_agreement_total_is_called_a_residual_rather_than_a_crowd():
    """It moves a lot and independently of the level: 1.00 for Small Traders and 0.63
    for Large Speculators on the same markets on the same day."""
    line = composition_line(with_members({"A": 1.0e8, "B": -0.6e8, "C": 0.3e8}),
                            et.UNIT_RISK, LEG_COMM, {})
    assert "residual rather than a crowd" in line


def test_a_unanimous_total_is_not_called_a_residual():
    line = composition_line(with_members({"A": 1.0e8, "B": 1.0e8}),
                            et.UNIT_RISK, LEG_COMM, {})
    assert "residual" not in line
    assert "2 of 2 markets point the same way" in line


def test_the_composition_line_counts_agreement_against_the_totals_direction():
    """On a net-short total the negative markets are the ones agreeing."""
    line = composition_line(with_members({"A": -1.0e8, "B": -1.0e8, "C": 0.1e8}),
                            et.UNIT_RISK, LEG_COMM, {})
    assert "2 of 3 markets point the same way" in line


def test_an_empty_total_has_no_composition_to_report():
    empty = AggregateExposure(frame=pd.DataFrame(), dropped={}, coverage={},
                              bounded_by={}, weeks_lost=0, members={})
    assert composition_line(empty, et.UNIT_RISK, LEG_SPEC, {}) == ""


def test_the_explanation_covers_what_the_total_is_made_of():
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "one market carried it" in body
    assert "opposite sides 59%" in body


def test_the_explanation_says_what_the_percentile_column_adds():
    """A market can be a small part of the total and still be at the most extreme
    reading it has ever had, and no contribution bar can show that."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "own history" in body
    assert "small part of the total" in body


def test_the_explanation_says_why_the_other_legs_are_a_separate_panel():
    """The three sum to zero, so no group moves without another moving against it, and
    no single one determines another either."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "sum to zero" in body
    assert "own panel" in body


# ── picking a week off the chart ──────────────────────────────────────────────

def test_a_clicked_week_is_snapped_to_a_week_the_frame_actually_has():
    """Hover is unified across four traces and a band edge can report a neighbouring
    stamp, so the click's x is snapped rather than trusted."""
    frame = agg(rows=5).frame
    assert snap_week(frame, "2026-01-14") == pd.Timestamp("2026-01-13")
    assert snap_week(frame, frame.index[2]) == frame.index[2]


def test_a_stale_selection_survives_a_change_of_set():
    """Click a 2015 week, switch to Metals, and the nearest Metals week is a better
    answer than an exception."""
    frame = agg(rows=3).frame
    assert snap_week(frame, "1999-01-01") == frame.index[0]
    assert snap_week(frame, "2099-01-01") == frame.index[-1]


def test_no_selection_means_the_latest_week():
    frame = agg(rows=4).frame
    assert snap_week(frame, None) is None
    assert week_row(frame, None).name == frame.index[-1]


def test_every_line_on_the_page_describes_the_week_that_was_clicked():
    """The whole point of the gesture. Before this the headline stayed on the last week
    while the reader looked at 2015, so the numbers on screen stopped matching the words
    above them."""
    frame = agg(rows=4).frame.copy()
    frame["risk_usd"] = [1e7, 2e7, 3e7, -9e7]
    picked = frame.index[1]
    text = caption(frame, et.UNIT_RISK, LEG_SPEC, when=picked)
    assert f"{picked:%B %d, %Y}" in text
    assert "net long" in text
    head, _ = headline(frame, et.UNIT_RISK, LEG_SPEC, when=picked)
    assert "$20.0m" in head


def test_the_axis_unit_does_not_change_when_a_week_is_picked():
    """Scaled against the whole series, not the selected week. A number that grew three
    orders of magnitude because you clicked left is not a comparison."""
    frame = agg(rows=3).frame.copy()
    frame["risk_usd"] = [1.0e3, 5.0e10, 2.0e10]
    small, _ = headline(frame, et.UNIT_RISK, LEG_SPEC, when=frame.index[0])
    big, _ = headline(frame, et.UNIT_RISK, LEG_SPEC, when=frame.index[1])
    assert "bn" in small and "bn" in big
    # The tiny week reads as a rounding error IN the series' unit, which is the honest
    # answer: it was a rounding error beside the rest of the series.
    assert "$0.0bn" in small


def test_a_past_week_says_it_is_a_past_week():
    """A page describing 2015 under a headline with no date is a page that lies
    quietly."""
    frame = agg(rows=3).frame
    notice, style = rewind_notice(frame.index[0], frame.index[-1])
    assert "not the latest" in notice
    assert style["display"] != "none"


def test_the_latest_week_shows_no_rewind_notice_and_no_reset():
    """A permanent "Back to latest" is a control that does nothing on the state it is
    most often seen in."""
    frame = agg(rows=3).frame
    notice, style = rewind_notice(frame.index[-1], frame.index[-1])
    assert notice == ""
    assert style["display"] == "none"


# ── the crosshair ─────────────────────────────────────────────────────────────

ZERO_LINE = {"type": "line", "yref": "y2", "xref": "x2 domain",
             "x0": 0, "x1": 1, "y0": 0, "y1": 0}


def test_the_crosshair_does_not_delete_the_figures_own_zero_line():
    """The more expensive mistake of the two, because nothing about the result looks
    broken: the exposure panel is read against that line."""
    out = crosshair_shapes([ZERO_LINE], "2015-03-10")
    assert ZERO_LINE in out
    assert len(out) == 2


def test_a_second_click_replaces_the_crosshair_rather_than_stacking_one():
    """Appending would leave a comb across the chart after a dozen clicks."""
    once = crosshair_shapes([ZERO_LINE], "2015-03-10")
    twice = crosshair_shapes(once, "2018-01-02")
    assert len(twice) == 2
    assert twice[-1]["x0"] == "2018-01-02"


def test_going_back_to_latest_takes_the_crosshair_with_it():
    after = crosshair_shapes(crosshair_shapes([ZERO_LINE], "2015-03-10"), None)
    assert after == [ZERO_LINE]


def test_the_crosshair_spans_both_panels():
    """Paper-referenced in y so it crosses the price panel too: the reader is comparing
    exposure against price at that week, which is the whole reason both panels share an
    axis."""
    line = crosshair_shapes([], "2015-03-10")[0]
    assert line["yref"] == "paper"
    assert (line["y0"], line["y1"]) == (0, 1)


def test_the_percentile_gets_an_english_ordinal():
    """43th in bold above a chart reads as unfinished whatever the chart does, and two
    different lines print a percentile."""
    assert [ordinal(n) for n in (1, 2, 3, 4, 21, 43, 52)] == [
        "1st", "2nd", "3rd", "4th", "21st", "43rd", "52nd"]


def test_the_teens_are_the_exception_they_are_in_english():
    assert [ordinal(n) for n in (11, 12, 13)] == ["11th", "12th", "13th"]


def test_the_headline_uses_it():
    text, _ = headline(ranked(43.0), et.UNIT_RISK, LEG_SPEC)
    assert "43rd percentile" in text
    assert "43th" not in text


def test_only_a_leg_that_IS_a_sum_gets_the_halves_sentence():
    """The figure draws companions beneath every leg, but Large and Small are the rest
    of the report beneath Commercials, not what Commercials is made of. Calling them its
    halves would describe an arithmetic that does not exist."""
    from cotmetrics.exposure import LEG_LARGE, LEG_SMALL
    a = with_members({"S&P 500": 4e8})
    parts = {LEG_LARGE: pd.Series([-1.5e8] * 3, index=a.frame.index),
             LEG_SMALL: pd.Series([6.6e8] * 3, index=a.frame.index)}
    assert "halves" in composition_line(a, et.UNIT_RISK, LEG_SPEC, parts)
    assert "halves" not in composition_line(a, et.UNIT_RISK, LEG_COMM, parts)


# ── the starting set ──────────────────────────────────────────────────────────

def test_a_default_that_narrows_a_class_names_what_it_left_out():
    """A default that silently narrows is the same failure as a filter that silently
    drops rows, and worse for being on by default: a reader who never touches Markets
    has no reason to suspect the total is not the class."""
    line = text_of(membership(
        agg(), ["S&P 500", "Nasdaq"],
        available=["S&P 500", "Nasdaq", "Nikkei 225", "S&P MidCap 400"]))
    assert "not included" in line
    assert "Nikkei 225" in line
    assert "S&P MidCap 400" in line
    assert "add from Markets" in line


def test_a_whole_class_claims_nothing_about_exclusions():
    line = text_of(membership(agg(), ["A", "B"], available=["A", "B"]))
    assert "not included" not in line


def test_the_exclusions_are_named_rather_than_counted():
    """So a reader can see whether the one they came for is among them. "1 market not
    included" would tell them something is missing without telling them what."""
    line = text_of(membership(agg(), ["A"], available=["A", "Nikkei 225"]))
    assert "not included: Nikkei 225" in line
    assert "1 not included" not in line
    assert "1 market(s) not included" not in line


def test_the_explanation_says_why_the_percentile_scale_exists():
    """A broad axis usually asks for a log toggle, and a log axis is undefined on a
    signed series. The percentile is the thing that actually makes 1991 and 2026
    legible together."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "48 times" in body
    assert "same footing" in body


# ── the contribution table ────────────────────────────────────────────────────

def table_of(**per_market):
    return pd.DataFrame(per_market).T


PALETTE = ["#F87171", "#60A5FA", "#FBBF24", "#34D399", "#A78BFA"]


def test_the_table_shows_both_units_whichever_one_is_drawn():
    """They are not substitutes: on Energies their percentiles correlate 0.802 with a
    worst gap of 69 points. A reader should be able to see the number the page is not
    currently drawing without changing a control."""
    table = table_of(**{"S&P 500": {"risk_usd": 3.7e8, "notional_usd": 4.4e10,
                                    "risk_pct_rank": 95.0,
                                    "notional_pct_rank": 97.0}})
    headers = [c["headerName"] for c
               in contribution_columns(et.UNIT_RISK, PALETTE, LEG_SPEC, table)]
    assert any("risk" in h.lower() for h in headers)
    assert any("notional" in h.lower() for h in headers)


def test_the_drawn_unit_is_the_first_money_column():
    table = table_of(**{"A": {"risk_usd": 1.0, "notional_usd": 2.0,
                              "risk_pct_rank": 50.0, "notional_pct_rank": 50.0}})
    for unit in (et.UNIT_RISK, et.UNIT_NOTIONAL):
        headers = [c["headerName"] for c
                   in contribution_columns(unit, PALETTE, LEG_SPEC, table)]
        assert et.UNIT_LABELS[unit] in headers[1]


def test_the_percentile_column_follows_the_drawn_unit():
    """Each market against ITS own history, and of the unit on screen."""
    table = table_of(**{"A": {"risk_usd": 1.0, "notional_usd": 2.0,
                              "risk_pct_rank": 11.0, "notional_pct_rank": 88.0}})
    for unit in (et.UNIT_RISK, et.UNIT_NOTIONAL):
        rank = next(c for c in contribution_columns(unit, PALETTE, LEG_SPEC, table)
                    if c["headerName"] == "%ile")
        assert rank["field"] == unit.replace("_usd", "") + "_pct_rank"


def test_the_bar_is_scaled_to_the_largest_contribution_in_the_table():
    """One scale for every row, or the bars say nothing about relative size."""
    table = table_of(A={"risk_usd": 1.0e8, "notional_usd": 1.0,
                        "risk_pct_rank": 50.0, "notional_pct_rank": 50.0},
                     B={"risk_usd": -4.0e8, "notional_usd": 1.0,
                        "risk_pct_rank": 50.0, "notional_pct_rank": 50.0})
    bar = next(c for c in contribution_columns(et.UNIT_RISK, PALETTE, LEG_SPEC, table)
               if c.get("colId") == "bar")
    assert bar["cellRendererParams"]["maxAbs"] == 4.0e8


def test_against_is_judged_by_the_totals_sign_not_by_being_negative():
    """On a net-short total the negative markets are the ones AGREEING, so the renderer
    is told the sign of the total rather than left to assume."""
    short = table_of(A={"risk_usd": -4.0e8, "notional_usd": 1.0,
                        "risk_pct_rank": 50.0, "notional_pct_rank": 50.0},
                     B={"risk_usd": 1.0e8, "notional_usd": 1.0,
                        "risk_pct_rank": 50.0, "notional_pct_rank": 50.0})
    bar = next(c for c in contribution_columns(et.UNIT_RISK, PALETTE, LEG_SPEC, short)
               if c.get("colId") == "bar")
    assert bar["cellRendererParams"]["totalSign"] == -1


def test_the_bar_column_is_not_sortable():
    """It is the same field as the money column beside it, so sorting on it would sort
    the table by a number the reader can already sort on, from a header that looks like
    it means something else."""
    table = table_of(A={"risk_usd": 1.0, "notional_usd": 1.0,
                        "risk_pct_rank": 50.0, "notional_pct_rank": 50.0})
    bar = next(c for c in contribution_columns(et.UNIT_RISK, PALETTE, LEG_SPEC, table)
               if c.get("colId") == "bar")
    assert bar["sortable"] is False


def test_an_empty_table_renders_a_hidden_grid_rather_than_a_gap():
    grid = contribution_grid(pd.DataFrame(), et.UNIT_RISK, PALETTE, LEG_SPEC)
    assert grid.rowData == []
    assert grid.style["display"] == "none"


def test_the_grid_carries_plain_floats_not_numpy_scalars():
    """rowData is serialised to the browser, and a numpy type that happens to survive
    today is a dependency on the encoder rather than a decision."""
    import json
    table = table_of(A={"risk_usd": np.float64(1.5), "notional_usd": np.float64(2.5),
                        "risk_pct_rank": np.float64(50.0),
                        "notional_pct_rank": np.float64(50.0)})
    grid = contribution_grid(table, et.UNIT_RISK, PALETTE, LEG_SPEC)
    assert json.dumps(grid.rowData)
    assert all(isinstance(v, (str, float, type(None)))
               for row in grid.rowData for v in row.values())


# ── the gold numeraire ────────────────────────────────────────────────────────

def test_amounts_carry_ounces_rather_than_a_dollar_sign_in_gold():
    """A page that said "$" on a chart labelled "oz gold" would be wrong in the one way
    this feature can be wrong."""
    from cotmetrics.exposure import NUMERAIRE_GOLD, NUMERAIRE_USD
    assert money(370.8, "m", NUMERAIRE_USD) == "$370.8m"
    assert money(370.8, "m", NUMERAIRE_GOLD) == "370.8m oz"
    assert money(-370.8, "m", NUMERAIRE_GOLD) == "370.8m oz"


def test_the_sign_is_left_to_the_words_beside_it():
    """Every caller says "net long" or "net short" in words, and a minus sign as well
    would be the same fact twice."""
    from cotmetrics.exposure import NUMERAIRE_USD
    assert "-" not in money(-1.0, "m", NUMERAIRE_USD)


def test_the_headline_reports_ounces_when_the_page_is_in_gold():
    from cotmetrics.exposure import NUMERAIRE_GOLD
    text, _ = headline(ranked(72.0, value=1.087e5), et.UNIT_RISK, LEG_SPEC,
                       numeraire=NUMERAIRE_GOLD)
    assert "oz" in text
    assert "$" not in text


def test_a_column_header_is_shorter_than_the_prose_form():
    """A header has about twenty characters rather than a sentence."""
    from cotmetrics.exposure import NUMERAIRE_GOLD
    assert column_name(et.UNIT_RISK, "k", NUMERAIRE_GOLD) == "Daily risk (k oz)"
    assert "troy ounces" in unit_name(et.UNIT_RISK, NUMERAIRE_GOLD)
    assert column_name(et.UNIT_RISK, "m") == "USD daily risk (m)"


def test_the_caption_names_the_numeraire_it_is_speaking_in():
    from cotmetrics.exposure import NUMERAIRE_GOLD
    text = caption(agg().frame, et.UNIT_RISK, LEG_SPEC, numeraire=NUMERAIRE_GOLD)
    assert "troy ounces of gold" in text


def test_the_aggregate_tuple_is_built_by_keyword_in_these_tests():
    """A positional build here bound the members dict to `numeraire` when that field was
    added ahead of it, and every composition test went empty at once. The tuple is a
    public return shape, so a field can be added again."""
    import inspect
    fields = AggregateExposure._fields
    assert fields.index("numeraire") < fields.index("members")
    built = AggregateExposure(frame=pd.DataFrame(), dropped={}, coverage={},
                              bounded_by={}, weeks_lost=0, members={"A": None})
    assert built.members == {"A": None}
    assert built.numeraire == "usd"
    assert inspect.signature(AggregateExposure).parameters["numeraire"].default == "usd"


def test_the_explanation_gives_both_gold_caveats():
    """Gold is an asset with its own trend rather than a ruler, and gold measured in
    gold is circular. Both are measured, and a view that offered the numeraire without
    saying either would be handing over a deflator as if it were a fact."""
    body = " ".join(b for _, b in how_to_read(et.UNIT_RISK))
    assert "not a ruler" in body
    assert "self-referential" in body
    assert "98th percentile" in body
