"""The week in words: the caption under the Weekly Flow panel on /categories.

One report week, told as sentences: which week, each opinion cohort's net change
with both legs and its z, the counterparty always (named per market from the roles
cotmetrics recorded in the frame's attrs), the cohorts on neither side, the
sum-to-zero line, and the state as a vocabulary label. Everything is read from the
frame `CotIndexer.get_category_data` returns; nothing here computes a flow, a z, a
level or a state, and nothing reads the store, so the copy is testable under CI's
empty COTDATA_STORE.

Copy rules, held by tests (cotmetrics docs/design/cot-flows.md, PR 2 and PR 3):

* Never the Home board's ranking words ("mover", "biggest move", "unusual"): a flow
  z is contracts against one cohort's own history, not an index-point change of the
  Legacy Commercial leg.
* Nothing about what comes next. The state's pre-registered test failed the crucible
  gauntlet on 2026-09-26, and the level cutoffs behind the markers were descriptive
  and on gold alone, so no sentence may say what follows a state or a flow from an
  extreme. "Signal" appears only as "not a signal".
* The weekday is read from the date, never written as "Tuesday", and no release date
  is stated: the CFTC moves both on holiday weeks, and the resolved release date
  lives in cotdata's vintage store, which this module does not read.
"""

import cotmetrics.categories as categories
import cotmetrics.constants as const
import cotmetrics.flow_roles as flow_roles
import cotmetrics.flows as flows
import pandas as pd

VOCABULARY_NOTE = "a vocabulary label, not a signal"


def _contracts(v):
    return f"{abs(v):,.0f}"


def _net_phrase(dnet):
    if pd.isna(dnet):
        return None
    if dnet > 0:
        return f"net bought {_contracts(dnet)} contracts"
    if dnet < 0:
        return f"net sold {_contracts(dnet)} contracts"
    return "left its net position unchanged"


def _signed(v):
    return "n/a" if pd.isna(v) else f"{v:+,.0f}"


def _value(df, column, i):
    if column is None or column not in df.columns:
        return None
    v = df[column].iloc[i]
    return None if pd.isna(v) else v


def _when(date):
    if hasattr(date, "strftime"):
        return f"{date.strftime('%A')} {date.strftime('%Y-%m-%d')}"
    return str(date)


def _weeks(df):
    return df.attrs.get("flow_level_weeks") or df.attrs.get("lookback_weeks")


def cohort_sentence(df, spec, i, lookback_header):
    """One cohort's week: net change with both legs, z, thin note, marked level."""
    dnet = _value(df, flows.flow_col(spec), i)
    phrase = _net_phrase(dnet)
    if phrase is None:
        return (f"{spec.label}: no reading this week (the report has a gap or a "
                f"contract switch here, so the change is not a week's flow).")
    dlong = _value(df, flows.flow_long_col(spec), i)
    dshort = _value(df, flows.flow_short_col(spec), i)
    text = f"{spec.label} {phrase}"
    if dlong is not None and dshort is not None:
        text += f" (longs {_signed(dlong)}, shorts {_signed(dshort)})"
    z = _value(df, flows.flow_z_col(spec), i)
    if z is None:
        text += (f", z not readable (under {const.FLOW_Z_MIN_PERIODS} weeks of "
                 f"history, or no week-to-week variation)")
    else:
        # Two decimals, as the hover prints: at one, 1.04 (active) and 0.96 (not)
        # both read "+1.0". "Inside one sd" is cotmetrics' sign, not a comparison
        # made here, and only the opinion cohorts carry one.
        text += f", z {z:+.2f} against its own {const.FLOW_Z_WEEKS}-week sd"
        if _value(df, flows.flow_sign_col(spec), i) == 0:
            text += ", inside one sd"
    if _value(df, flows.flow_thin_col(spec), i):
        text += (f"; thin, its typical week is under {const.FLOW_MIN_STD_CONTRACTS} "
                 f"contracts, so read the count rather than the z")
    if lookback_header is not None:
        mark = _value(df, flows.flow_level_mark_col(spec, lookback_header), i)
        level = _value(df, flows.flow_from_level_col(spec, lookback_header), i)
        if mark and level is not None:
            # Worded from the mark, with the level to one decimal, so 19.6 cannot
            # print as "20, the bottom" against a strict below-20 rule.
            where = (f"above {const.FLOW_LEVEL_HIGH}" if mark > 0
                     else f"below {const.FLOW_LEVEL_LOW}")
            text += f", leaving level {level:.1f} ({where}) of its {_span(df)}"
    return text + "."


def _span(df):
    weeks = _weeks(df)
    return f"{weeks}-week range" if weeks else "lookback range"


def marker_key(df):
    """What the triangles mean, once, in words."""
    return (f"A triangle marks an active week (beyond one sd) that left the top "
            f"(up, the index above {const.FLOW_LEVEL_HIGH} the week before) or the "
            f"bottom (down, below {const.FLOW_LEVEL_LOW}) of the cohort's "
            f"{_span(df)}.")


def _by_key(report):
    return {s.key: s for s in categories.categories_for(report)}


def _present(df, keys, report):
    by_key = _by_key(report)
    return [by_key[k] for k in keys
            if k in by_key and flows.flow_col(by_key[k]) in df.columns]


def counterparty_sentence(df, roles, report, i):
    members = _present(df, roles.get("counterparty") or (), report)
    column = flows.counterparty_flow_col()
    if not members or column not in df.columns:
        return ("No counterparty composite on this market: none of its measured "
                "members is in the report.")
    names = " + ".join(s.label for s in members)
    source = roles.get("source") or ""
    label = categories.REPORT_LABELS.get(report, report)
    if source == flow_roles.SOURCE_MEASURED:
        why = "measured as this market's counterparty"
    elif source == flow_roles.SOURCE_UNSTABLE:
        why = (f"the {label} default, since this market's own roles did not hold "
               f"steady enough to measure")
    else:
        why = f"the {label} default; this market's roles were not measured"
    phrase = _net_phrase(_value(df, column, i))
    if phrase is None:
        return f"On the other side, {names} ({why}): no reading this week."
    text = f"On the other side, {names} ({why}) {phrase}"
    z = _value(df, flows.counterparty_flow_z_col(), i)
    if z is not None:
        text += f", z {z:+.2f}"
    # Where the measured set shares a cohort with the opinion set (Other
    # Reportable on silver, copper, orange juice), that cohort's flow is in the
    # sentence above and in this one, so the printed figures do not sum to zero.
    # Say so rather than let the sum-to-zero line below contradict them.
    opinion = set(roles.get("opinion") or ())
    both = [s.label for s in members if s.key in opinion]
    if both:
        text += (f". {' and '.join(both)} {'is' if len(both) == 1 else 'are'} also "
                 f"one of the cohorts above, so {'its' if len(both) == 1 else 'their'} "
                 f"flow is counted on both sides here")
    return text + "."


def neither_side_sentence(df, roles, report, i):
    keys = [k for k in (tuple(roles.get("neutral") or ())
                        + tuple(roles.get("inert") or ())
                        + tuple(roles.get("residual") or ()))
            if k not in (roles.get("counterparty") or ())
            and k not in (roles.get("opinion") or ())]
    specs = _present(df, keys, report)
    if not specs:
        return None
    parts = []
    for s in specs:
        v = _value(df, flows.flow_col(s), i)
        parts.append(f"{s.label} {_signed(v)} contracts net" if v is not None
                     else f"{s.label} no reading this week")
    return f"On neither side: {', '.join(parts)}."


def sum_to_zero_sentence(df, report):
    specs = categories.categories_for(report)
    if not all(flows.flow_col(s) in df.columns for s in specs):
        return None
    return ("Every contract bought was sold by someone, so the net changes of all "
            "the cohorts, each counted once, sum to zero each week.")


def state_sentence(df, roles, report, i):
    if not roles.get("state_eligible", False) or const.FLOW_STATE not in df.columns:
        return ("No state is named on this market: its cohorts do not split into "
                "opinion and counterparty the way the state assumes, so the cells "
                "are drawn and not labelled.")
    state = df[const.FLOW_STATE].iloc[i]
    if state is None or (isinstance(state, float) and pd.isna(state)):
        return "No state this week: an opinion cohort's z is not readable yet."
    opinion = _present(df, roles.get("opinion") or (), report)
    if state == flows.FLOW_STATE_QUIET:
        return (f"State: {state}, no opinion cohort moved beyond one sd "
                f"({VOCABULARY_NOTE}).")
    if state == flows.FLOW_STATE_PARTIAL:
        n = _value(df, const.FLOW_N_ACTIVE, i)
        count = f"{int(n)} of the {len(opinion)}" if n is not None else "some of the"
        return (f"State: {state}, {count} opinion cohorts moved beyond one sd "
                f"({VOCABULARY_NOTE}).")
    moves = []
    for s in opinion:
        sign = _value(df, flows.flow_sign_col(s), i)
        if sign:
            moves.append(f"{s.label} {'buying' if sign > 0 else 'selling'}")
    split = ("the opinion cohorts split" if state in flows.DIVERGENT_FLOW_STATES
             else "the opinion cohorts moved together")
    return f"State: {state} ({'; '.join(moves)}; {split}), {VOCABULARY_NOTE}."


def latest_row(df):
    """The last row where any opinion cohort's flow is readable, else the last row."""
    roles = df.attrs.get("flow_roles") or {}
    report = roles.get("report") or df.attrs.get("report")
    cols = [flows.flow_col(s) for s in _present(df, roles.get("opinion") or (), report)]
    if cols:
        readable = df[cols].notna().any(axis=1).to_numpy()
        hits = readable.nonzero()[0]
        if len(hits):
            return int(hits[-1])
    return len(df) - 1


def week_in_words(df, lookback_header, i=None):
    """The caption as a list of sentences, for one row of the category frame.

    `i` is a positional row; None takes `latest_row`. Returns [] when the frame has
    no flow columns or no roles, so the page can call it unconditionally.
    """
    if df is None or df.empty:
        return []
    roles = df.attrs.get("flow_roles") or {}
    report = roles.get("report") or df.attrs.get("report")
    if report not in categories.REPORT_CHOICES:
        return []
    opinion = _present(df, roles.get("opinion") or (), report)
    if not opinion:
        return []
    latest = i is None
    i = latest_row(df) if latest else i
    out = [f"Positions as of {_when(df.index[i])} against the report before: each "
           f"cohort's net change in contracts, and its z against its own "
           f"{const.FLOW_Z_WEEKS}-week sd of weekly changes."]
    if latest and i < len(df) - 1:
        out.append(f"The newest report, {_when(df.index[-1])}, has no reading for "
                   f"these cohorts (a gap or a contract switch), so this is the "
                   f"week before it.")
    out += [cohort_sentence(df, s, i, lookback_header) for s in opinion]
    out.append(counterparty_sentence(df, roles, report, i))
    for sentence in (neither_side_sentence(df, roles, report, i),
                     sum_to_zero_sentence(df, report),
                     state_sentence(df, roles, report, i),
                     marker_key(df) if lookback_header is not None else None):
        if sentence:
            out.append(sentence)
    return out
