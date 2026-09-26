"""The week in words under the Weekly Flow panel.

Store-free: every test reads the synthetic category frame from test_category_traces,
which carries the flow family through cotmetrics' own functions.
"""

import importlib
import sys

import pandas as pd
import pytest
from cotmetrics import categories as cot_categories
from cotmetrics import constants as cm_const
from cotmetrics import flow_roles, flows

import components.flow_copy as fc
import viz_config
import viz_constants as vc
from tests.test_category_traces import HEADER, _frame

DISAGG = cot_categories.REPORT_DISAGG
TFF = cot_categories.REPORT_TFF


def _by_key(report):
    return {s.key: s for s in cot_categories.categories_for(report)}


def _opinion(df):
    by_key = _by_key(df.attrs["report"])
    return [by_key[k] for k in df.attrs["flow_roles"]["opinion"]]


def test_module_imports_without_the_data_layer():
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(fc)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


@pytest.mark.parametrize("report", [DISAGG, TFF])
def test_caption_opens_with_the_week_and_names_every_opinion_cohort(report):
    df = _frame(report)
    out = fc.week_in_words(df, HEADER)
    date = df.index[-1]
    assert out[0].startswith(f"Positions as of {date.strftime('%A')} "
                             f"{date.strftime('%Y-%m-%d')}")
    for i, spec in enumerate(_opinion(df), start=1):
        assert out[i].startswith(spec.label), out[i]
        assert "longs " in out[i] and "shorts " in out[i]
        assert "52-week sd" in out[i]


def test_cohort_sentence_reports_net_legs_and_z_from_the_frame():
    df = _frame(DISAGG)
    spec = _opinion(df)[0]
    i = len(df) - 1
    df.loc[df.index[i], flows.flow_col(spec)] = -12_345
    df.loc[df.index[i], flows.flow_long_col(spec)] = -2_000
    df.loc[df.index[i], flows.flow_short_col(spec)] = 10_345
    df.loc[df.index[i], flows.flow_z_col(spec)] = -1.84
    df.loc[df.index[i], flows.flow_sign_col(spec)] = -1
    text = fc.cohort_sentence(df, spec, i, HEADER)
    assert text.startswith(f"{spec.label} net sold 12,345 contracts")
    assert "(longs -2,000, shorts +10,345)" in text
    assert "z -1.84 against its own 52-week sd" in text
    assert "inside one sd" not in text

    df.loc[df.index[i], flows.flow_z_col(spec)] = 0.4
    df.loc[df.index[i], flows.flow_sign_col(spec)] = 0
    assert "inside one sd" in fc.cohort_sentence(df, spec, i, HEADER)


def test_z_at_the_threshold_prints_what_the_sign_says():
    """1.04 is active and 0.96 is not; at one decimal both read "+1.0"."""
    df = _frame(DISAGG)
    spec = _opinion(df)[0]
    i = len(df) - 1
    for z, sign, inside in ((1.04, 1, False), (0.96, 0, True), (1.0, 0, True)):
        df.loc[df.index[i], flows.flow_z_col(spec)] = z
        df.loc[df.index[i], flows.flow_sign_col(spec)] = sign
        text = fc.cohort_sentence(df, spec, i, HEADER)
        assert f"z {z:+.2f}" in text
        assert ("inside one sd" in text) is inside


def test_cohort_sentence_names_a_marked_level_and_only_a_marked_one():
    df = _frame(DISAGG)
    spec = _opinion(df)[0]
    i = len(df) - 1
    mark, level = (flows.flow_level_mark_col(spec, HEADER),
                   flows.flow_from_level_col(spec, HEADER))
    df[mark] = df[mark].astype("Int64")
    df.loc[df.index[i], level] = 87.4
    df.loc[df.index[i], mark] = 1
    assert "leaving level 87.4 (above 80) of its 52-week range" in fc.cohort_sentence(
        df, spec, i, HEADER)
    # 19.6 is below 20 and must not print as "20".
    df.loc[df.index[i], level] = 19.6
    df.loc[df.index[i], mark] = -1
    assert "leaving level 19.6 (below 20) of its 52-week range" in fc.cohort_sentence(
        df, spec, i, HEADER)
    df.loc[df.index[i], mark] = 0
    assert "leaving level" not in fc.cohort_sentence(df, spec, i, HEADER)
    # No header, no level, no error.
    assert "leaving level" not in fc.cohort_sentence(df, spec, i, None)


def test_masked_and_warm_up_weeks_say_why_there_is_no_reading():
    df = _frame(DISAGG)
    spec = _opinion(df)[0]
    df.loc[df.index[5], flows.flow_col(spec)] = float("nan")
    assert "no reading this week" in fc.cohort_sentence(df, spec, 5, HEADER)
    assert "z not readable" in fc.cohort_sentence(df, spec, 6, HEADER)


def test_thin_cohort_says_read_the_count():
    df = _frame(DISAGG)
    spec = _opinion(df)[0]
    df[flows.flow_thin_col(spec)] = pd.array([True] * len(df), dtype="boolean")
    assert "read the count" in fc.cohort_sentence(df, spec, len(df) - 1, HEADER)


def test_counterparty_is_always_named_with_its_members_and_its_source():
    df = _frame(DISAGG)
    roles = df.attrs["flow_roles"]
    members = [_by_key(DISAGG)[k].label for k in roles["counterparty"]]
    text = fc.counterparty_sentence(df, roles, DISAGG, len(df) - 1)
    assert text.startswith(f"On the other side, {' + '.join(members)}")
    assert "measured" in text

    roles = {**roles, "source": flow_roles.SOURCE_UNSTABLE}
    text = fc.counterparty_sentence(df, roles, DISAGG, len(df) - 1)
    assert "default" in text and "did not hold steady" in text

    roles = {**roles, "source": flow_roles.SOURCE_DEFAULT}
    text = fc.counterparty_sentence(df, roles, DISAGG, len(df) - 1)
    assert "were not measured" in text and "did not hold steady" not in text


def test_a_cohort_on_both_sides_is_said_to_be_counted_twice():
    """Silver, copper and orange juice measure Other Reportable into the
    counterparty while it is also an opinion cohort, so the printed figures do not
    sum to zero; the caption has to say why."""
    df = _frame(DISAGG)
    roles = {**df.attrs["flow_roles"],
             "counterparty": ("producer_merchant", "swap", "other_reportable")}
    text = fc.counterparty_sentence(df, roles, DISAGG, len(df) - 1)
    assert "Other Reportable is also one of the cohorts above" in text
    assert "counted on both sides" in text
    plain = fc.counterparty_sentence(df, df.attrs["flow_roles"], DISAGG, len(df) - 1)
    assert "both sides" not in plain

    out = fc.week_in_words(df, HEADER)
    assert any(s.startswith("On the other side") for s in out)


def test_neither_side_lists_the_neutral_cohorts():
    df = _frame(DISAGG)
    df.attrs["flow_roles"] = {**df.attrs["flow_roles"],
                              "counterparty": ("producer_merchant",),
                              "neutral": ("swap",)}
    text = fc.neither_side_sentence(df, df.attrs["flow_roles"], DISAGG, len(df) - 1)
    assert text.startswith("On neither side: Swap Dealers ")
    swap = _by_key(DISAGG)["swap"]
    df.loc[df.index[-1], flows.flow_col(swap)] = float("nan")
    text = fc.neither_side_sentence(df, df.attrs["flow_roles"], DISAGG, len(df) - 1)
    assert "Swap Dealers no reading this week" in text and "n/a" not in text
    # None when every cohort is either opinion or counterparty.
    roles = {**df.attrs["flow_roles"], "counterparty": ("producer_merchant", "swap"),
             "neutral": ()}
    assert fc.neither_side_sentence(df, roles, DISAGG, len(df) - 1) is None


def test_sum_to_zero_line_only_when_every_cohort_is_present():
    df = _frame(DISAGG)
    assert fc.sum_to_zero_sentence(df, DISAGG)
    missing = df.drop(columns=[flows.flow_col(_by_key(DISAGG)["swap"])])
    assert fc.sum_to_zero_sentence(missing, DISAGG) is None


@pytest.mark.parametrize("state,expect", [
    ("VALUE_ACCUM", "the opinion cohorts split"),
    ("BROAD_ACCUM", "the opinion cohorts moved together"),
    (flows.FLOW_STATE_QUIET, "no opinion cohort moved beyond one sd"),
    (flows.FLOW_STATE_PARTIAL, "opinion cohorts moved beyond one sd"),
])
def test_state_sentence_is_vocabulary(state, expect):
    df = _frame(DISAGG)
    i = len(df) - 1
    df[cm_const.FLOW_STATE] = df[cm_const.FLOW_STATE].astype(object)
    df.loc[df.index[i], cm_const.FLOW_STATE] = state
    text = fc.state_sentence(df, df.attrs["flow_roles"], DISAGG, i)
    assert text.startswith(f"State: {state}")
    assert expect in text
    assert fc.VOCABULARY_NOTE in text


def test_state_sentence_warm_up_and_ineligible():
    df = _frame(DISAGG)
    assert "not readable yet" in fc.state_sentence(df, df.attrs["flow_roles"],
                                                   DISAGG, 0)
    roles = {**df.attrs["flow_roles"], "state_eligible": False}
    text = fc.state_sentence(df, roles, DISAGG, len(df) - 1)
    assert text.startswith("No state is named on this market")


def test_latest_row_skips_trailing_weeks_with_no_flow_and_says_so():
    df = _frame(DISAGG)
    for spec in _opinion(df):
        df.loc[df.index[-2:], flows.flow_col(spec)] = float("nan")
    assert fc.latest_row(df) == len(df) - 3
    out = fc.week_in_words(df, HEADER)
    assert out[1].startswith("The newest report,")
    assert df.index[-3].strftime("%Y-%m-%d") in out[0]


def test_caption_ends_with_the_marker_key_and_survives_no_header():
    df = _frame(DISAGG)
    out = fc.week_in_words(df, HEADER)
    assert out[-1].startswith("A triangle marks")
    assert "above 80" in out[-1] and "below 20" in out[-1]
    assert "52-week range" in out[-1]
    bare = fc.week_in_words(df, None)
    assert bare and not bare[-1].startswith("A triangle")


def test_frames_without_flow_roles_give_no_caption():
    df = _frame(DISAGG)
    df.attrs.pop("flow_roles")
    assert fc.week_in_words(df, HEADER) == []
    assert fc.week_in_words(pd.DataFrame(), HEADER) == []


BANNED = ("mover", "biggest move", "unusual", "next", "follow", "expect",
          "forecast", "predict", "bullish", "bearish", "likely", "edge",
          "outperform", "return")


@pytest.mark.parametrize("report", [DISAGG, TFF])
def test_copy_never_ranks_or_forecasts_on_any_week(report):
    """Every week of the frame, including the warm-up and the marked weeks."""
    df = _frame(report)
    for i in range(len(df)):
        for sentence in fc.week_in_words(df, HEADER, i=i):
            low = sentence.lower()
            assert not any(b in low for b in BANNED), sentence
            assert "signal" not in low.replace("not a signal", ""), sentence
            assert "\u2014" not in sentence, sentence


def test_caption_renders_under_the_graph_only_with_the_flow_panel(monkeypatch):
    """The page adds markup only: the sentences are flow_copy's, in order."""
    import dash
    from dash import html

    dash.Dash(__name__, use_pages=True, pages_folder="")
    import pages.analytics.categories as page

    df = _frame(DISAGG)

    class _Indexer:
        def get_category_data(self, asset, report, lookback):
            return df

    monkeypatch.setattr(page, "get_indexer", lambda: _Indexer())
    keys = [s.key for s in cot_categories.categories_for(DISAGG)]
    palette = sorted(viz_config.get_palette_names())[0]

    out = page.render_category_stack(palette, "Gold", DISAGG, keys, ["net_pos", "flow"],
                                     "52", "1", vc.LAYOUT_FACET)
    assert isinstance(out, list) and len(out) == 2
    caption = out[1]
    assert isinstance(caption, html.Div) and caption.id == "categories_flow_caption"
    assert [p.children for p in caption.children] == fc.week_in_words(df, HEADER)

    out = page.render_category_stack(palette, "Gold", DISAGG, keys, ["net_pos"],
                                     "52", "1", vc.LAYOUT_FACET)
    assert not isinstance(out, list)
