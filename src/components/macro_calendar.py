"""The macro calendar on the internals page: this week's and next week's US releases.

**Source.** marketdata's `econ_calendar()` (marketdata `providers/tradingview_calendar.py`,
`docs/design/econ-calendar.md`): TradingView's economic calendar, captured nightly on the
producer box through the claude.ai connector, rebuilt whole each night into a snapshot
table, and mirrored to the Mac and the VPS with the rest of the bar store. Nothing here
fetches. Release times, the consensus estimate, the previous reading and the actual are
the vendor's, shown as stored; this module only chooses, labels and formats.

**Context, never a gate.** No table, an older marketdata without `econ_calendar`, or a
table with nothing on the list for the fortnight: `read()` returns None and the page has
no section. A calendar never stops a publish.

**What is shown is an allowlist** (`EVENTS`), keyed by TradingView `ticker`, with a
display name and one line on what the release measures, written here. The feed's own
importance flag is not enough to choose by: at medium importance it carries every
Treasury auction as three rows, weekly mortgage rates, EIA and USDA stocks and rig counts.
A few releases that matter carry no ticker in the feed (ISM services, the Conference
Board's confidence index, the S&P Global flash PMI, Chicago PMI), so `TITLE_EVENTS` keys
those by the feed's exact title instead.

**High impact** is the vendor's own flag (importance 1), not a judgement made here:
on the 2026-11-19 capture that marked CPI, core PCE, payrolls, the unemployment rate,
retail sales, GDP, the ISM surveys, JOLTS, housing starts and the FOMC decision, and left
jobless claims and the regional Fed surveys at medium.

**Fed events.** The FOMC rate decision is in the feed. FOMC minutes and Fed speeches are
not, at any importance (checked on that capture with every importance level included), and
no other source is added for them; the section's note says so.

**Weeks.** Monday to Friday in US Eastern time, the week holding `today` and the one after;
on a Saturday or Sunday "this week" is the coming one. `COMING_UP` names the next FOMC
decision, CPI and payrolls after those two weeks, when the capture reaches them (the
routine captures 21 days ahead).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Spec:
    name: str
    about: str
    #: A key `COMING_UP` looks for: "fomc", "cpi" or "payrolls".
    headline: str = ""


#: Keyed by the feed's `ticker`. Order is display order within a time slot.
EVENTS = {
    "ECONOMICS:USINTR": Spec("FOMC rate decision",
                             "The Fed's policy rate, announced with the committee's "
                             "statement.", "fomc"),
    "ECONOMICS:USNFP": Spec("Nonfarm payrolls",
                            "Jobs added last month outside farms, from the employer "
                            "survey.", "payrolls"),
    "ECONOMICS:USUR": Spec("Unemployment rate",
                           "Share of the labour force without a job and looking, from the "
                           "household survey."),
    "ECONOMICS:USAHE": Spec("Average hourly earnings",
                            "Month-on-month pay growth, watched for wage pressure on "
                            "prices."),
    "ECONOMICS:USIRYY": Spec("CPI, year on year",
                             "Consumer prices against the same month a year earlier.",
                             "cpi"),
    "ECONOMICS:USIRMM": Spec("CPI, month on month",
                             "The monthly change in consumer prices.", "cpi"),
    "ECONOMICS:USCIRMM": Spec("Core CPI, month on month",
                              "Consumer prices without food and energy, the steadier "
                              "trend.", "cpi"),
    "ECONOMICS:USCIR": Spec("Core CPI, year on year",
                            "Consumer prices without food and energy, against a year "
                            "earlier.", "cpi"),
    "ECONOMICS:USPPIMM": Spec("PPI",
                              "Prices businesses receive for their output, month on "
                              "month."),
    "ECONOMICS:USCPPMM": Spec("Core PPI",
                              "Producer prices without food and energy."),
    "ECONOMICS:USCPCEPIMM": Spec("Core PCE prices",
                                 "The Fed's preferred inflation measure, without food "
                                 "and energy, month on month."),
    "ECONOMICS:USPCEPIMC": Spec("PCE prices",
                                "The full PCE price index, month on month."),
    "ECONOMICS:USPI": Spec("Personal income",
                           "Household income from all sources, month on month."),
    "ECONOMICS:USPSP": Spec("Personal spending",
                            "Household spending on goods and services, month on month."),
    "ECONOMICS:USGDPQQ": Spec("GDP",
                              "Quarterly growth of the economy at an annual rate."),
    "ECONOMICS:USRSMM": Spec("Retail sales",
                             "Spending at stores, online and in restaurants, month on "
                             "month."),
    "ECONOMICS:USRSEA": Spec("Retail sales ex autos",
                             "Retail sales without car dealers, which swing on their "
                             "own."),
    "ECONOMICS:USIJC": Spec("Initial jobless claims",
                            "New unemployment filings last week, the quickest read on "
                            "layoffs."),
    "ECONOMICS:USJO": Spec("JOLTS job openings",
                           "Vacancies employers report, a measure of labour demand."),
    "ECONOMICS:USEC": Spec("ADP employment",
                           "A private payroll count from a payroll processor, out ahead "
                           "of the official one."),
    "ECONOMICS:USBCOI": Spec("ISM manufacturing",
                             "Factory purchasing managers' survey; above 50 means "
                             "expanding."),
    "ECONOMICS:USIPMM": Spec("Industrial production",
                             "Output of factories, mines and utilities, month on month."),
    "ECONOMICS:USDGO": Spec("Durable goods orders",
                            "New orders for goods meant to last, a read on business "
                            "investment."),
    "ECONOMICS:USNYESMI": Spec("Empire State manufacturing",
                               "The New York Fed's survey of the state's factories, "
                               "usually the month's first regional read."),
    "ECONOMICS:USPFMI": Spec("Philly Fed manufacturing",
                             "The Philadelphia Fed's survey of factories in its "
                             "district."),
    "ECONOMICS:USCCI": Spec("UMich consumer sentiment",
                            "University of Michigan survey of household mood and "
                            "inflation expectations."),
    "ECONOMICS:USHST": Spec("Housing starts",
                            "New homes on which building began, at an annual rate."),
    "ECONOMICS:USBP": Spec("Building permits",
                           "Permits for new homes, a step ahead of starts."),
    "ECONOMICS:USEHS": Spec("Existing home sales",
                            "Closed sales of previously owned homes, at an annual rate."),
    "ECONOMICS:USNHS": Spec("New home sales",
                            "Sales of newly built homes, at an annual rate."),
}

#: Releases the feed carries without a ticker, keyed by its exact title.
TITLE_EVENTS = {
    "ISM Services PMI": Spec("ISM services",
                             "Services purchasing managers' survey; above 50 means "
                             "expanding."),
    "S&P Global Composite PMI Flash": Spec("S&P Global flash PMI",
                                           "Early estimate of the month's purchasing "
                                           "managers' surveys, factories and services."),
    "CB Consumer Confidence": Spec("Conference Board confidence",
                                   "Household survey leaning on views of jobs and "
                                   "business conditions."),
    "Chicago PMI": Spec("Chicago PMI",
                        "Purchasing managers in the Chicago region, out on the month's "
                        "last business day."),
}

#: The vendor's release stage, from the end of its title, shown after the name.
_STAGES = (("2nd Est", "2nd estimate"), ("3rd Est", "3rd estimate"), ("Adv", "advance"),
           ("Prel", "preliminary"), ("Final", "final"))

#: The headline releases the "coming up" line names, in this order.
COMING_UP = (("fomc", "FOMC"), ("cpi", "CPI"), ("payrolls", "Payrolls"))

#: Days after which the capture is old enough to say so: a weekend plus a missed night.
STALE_AFTER_DAYS = 3

NOTE = ("FOMC minutes and Fed speeches are not in this feed, so they are not shown.")


@dataclass
class Event:
    when: datetime                  # Eastern
    name: str
    about: str
    period: str
    high: bool
    est: str
    act: str
    prev: str
    headline: str = ""


@dataclass
class Day:
    day: date
    events: list = field(default_factory=list)


@dataclass
class Calendar:
    today: date
    captured: date
    weeks: list                     # [(label, [Day x5])]
    coming_up: list                 # [(label, date)]
    stale: bool

    @property
    def keyed(self):
        """Every (name, about) shown, once, in first-shown order: the section's key."""
        seen = {}
        for _, days in self.weeks:
            for d in days:
                for e in d.events:
                    seen.setdefault(e.name.split(" (")[0], e.about)
        return list(seen.items())


def _spec(row) -> Optional[Spec]:
    t = row.get("ticker")
    if isinstance(t, str) and t in EVENTS:
        return EVENTS[t]
    return TITLE_EVENTS.get(row.get("title"))


def _stage(title) -> str:
    for suffix, label in _STAGES:
        if isinstance(title, str) and re.search(rf"\b{re.escape(suffix)}$", title):
            return label
    return ""


def fmt(value, unit=None, scale=None) -> str:
    """A stored reading as the calendar prints it: the vendor's own precision, its scale
    letter and unit. An index with no decimals keeps one (18.0), as release tables do."""
    if value is None or pd.isna(value):
        return ""
    v = float(value)
    s = f"{abs(v):.3f}".rstrip("0").rstrip(".")
    if not isinstance(scale, str) and "." not in s:
        s += ".0"
    sign = "-" if v < 0 else ""
    scale = scale if isinstance(scale, str) else ""
    if unit == "$":
        return f"{sign}${s}{scale}"
    if unit == "%":
        return f"{sign}{s}{scale}%"
    return f"{sign}{s}{scale}"


def week_monday(today: date) -> date:
    """The Monday of 'this week': today's, or the coming one on a weekend."""
    if today.weekday() >= 5:
        return today + timedelta(days=7 - today.weekday())
    return today - timedelta(days=today.weekday())


def _events(table: pd.DataFrame) -> list:
    out = []
    for row in table.to_dict("records"):
        if row.get("country") not in (None, "US"):
            continue
        spec = _spec(row)
        if spec is None:
            continue
        stage = _stage(row.get("title"))
        unit, scale = row.get("unit"), row.get("scale")
        out.append(Event(
            when=pd.Timestamp(row["time_utc"]).tz_convert(ET).to_pydatetime(),
            name=f"{spec.name} ({stage})" if stage else spec.name,
            about=spec.about,
            period=row.get("period") or "",
            high=int(row.get("importance", 0)) == 1,
            est=fmt(row.get("forecast"), unit, scale),
            act=fmt(row.get("actual"), unit, scale),
            prev=fmt(row.get("previous"), unit, scale),
            headline=spec.headline))
    order = {s.name: i for i, s in enumerate([*EVENTS.values(), *TITLE_EVENTS.values()])}
    out.sort(key=lambda e: (e.when, order.get(e.name.split(" (")[0], 99)))
    return out


def build(table: pd.DataFrame, today: date) -> Optional[Calendar]:
    """The two weeks around `today` (an Eastern date) from a marketdata calendar table,
    or None when nothing on the list falls in them."""
    if table is None or table.empty:
        return None
    events = _events(table)
    monday = week_monday(today)
    weeks, shown = [], 0
    for label, start in (("This week", monday), ("Next week", monday + timedelta(days=7))):
        days = [Day(start + timedelta(days=i)) for i in range(5)]
        for e in events:
            k = (e.when.date() - start).days
            if 0 <= k < 5:
                days[k].events.append(e)
                shown += 1
        weeks.append((label, days))
    if not shown:
        return None
    beyond = monday + timedelta(days=12)        # the Saturday after next week
    coming = []
    for key, label in COMING_UP:
        nxt = next((e for e in events if e.headline == key and e.when.date() >= beyond), None)
        if nxt is not None:
            coming.append((label, nxt.when.date()))
    captured = pd.Timestamp(table["captured"].max()).date()
    return Calendar(today=today, captured=captured, weeks=weeks, coming_up=coming,
                    stale=(today - captured).days > STALE_AFTER_DAYS)


def read(today: Optional[date] = None) -> Optional[Calendar]:
    """The page's calendar from the marketdata store, or None (no section)."""
    try:
        import marketdata
    except ImportError:
        return None
    reader = getattr(marketdata, "econ_calendar", None)
    if reader is None:              # a marketdata from before the calendar
        return None
    today = today or datetime.now(ET).date()
    return build(reader(), today)
