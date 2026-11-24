"""The daily news-failure scan, read from `cmrdata_store` and laid out for reading.

LOCAL ONLY, through the page that draws it (`pages.analytics.news_failure`). The scan sorts
markets by a third-party positioning index licensed to the operator (a paid product), so
the same rule as the sentiment page applies: nothing here may reach the public site.

**What the scanner writes.** Every trading day the scheduled scan routine runs
`cmrdata_store/scan.py`, judges the news for each set-up, and writes a dated alert,
`alerts/<YYYY-MM-DD>.md`. From 2026-11-17 it also writes a sidecar,
`alerts/<YYYY-MM-DD>.json`, with two halves:

* `scan` is `scan.py`'s own JSON output, verbatim: the watchlist, each row's
  materiality, peer comparison, eligibility, blockers and FOR/AGAINST evidence. Every
  number on the page comes from here. Nothing is recomputed.
* `report` is what the routine decided at report time, which bars cannot give: the
  news read per symbol (`news[SYM] = {text, type}`), the verdict per symbol
  (`verdicts[SYM] = {verdict, confidence, reason, against}`), the day's notes, the
  headline, and the sources.

**Backfilled days** (everything before 2026-11-17). `cmrdata_store/backfill.py` re-ran
the scanner for each older day against the bars as they stood that day and wrote a
sidecar with a `backfill` block and an EMPTY `report`. So those days have the numbers
(candle, size, peers, gates, evidence) and no judgments: the news read and the verdict
exist only in the alert's prose, and nothing reads them back out of it. The page shows
the numbers beside the alert as written and leaves the News and Verdict columns off,
because a blank verdict there means "not recorded in this form", not "not judged".
The gates are TODAY's scanner's reading of that day, and the rules changed over those
months, so where a backfilled gate and the alert disagree the alert is the record.

**Days with no sidecar at all** (a day the backfill skipped, or one the routine wrote
only the markdown for) still show: the page renders that day's markdown as written.
The alert format drifted over the summer, so parsing old prose into rows would invent
structure the file never had.

**One market over time** (`market_history`). The same files read down instead of
across: every scan day in a window, newest first, for one symbol. A sidecar day gives
that symbol's rows; a backfilled day gives its rows and, under them, the section the
alert wrote for it; a markdown-only day gives just that section, found by its `(SYM)`
heading, sliced to the next heading of the same level and shown as written. A day the market was
not a set-up says so, and a day whose file has no per-market headings says that instead,
because "absent from the page" and "not a set-up" must not look the same.

**The discipline is the scanner's, and the page keeps it.** "No failure" is the normal
row. A confidence chip appears only where the routine gave one. A row the routine never
judged reads "Not judged", never "No failure", so a row nobody checked cannot look like
a row that was checked and cleared (cmrdata_store CLAUDE.md, the board table rules).
Educational research only; nothing here is a recommendation to trade.
"""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dash import dcc, html

ENV = "CMRDATA_STORE"
DEFAULT_STORE = "~/code/cmrdata_store"
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(md|json)$")

#: Gate glyph colours: pass, fail, unknown. The app's green and red (plot_colors'
#: up/down family), and a muted grey for a gate the scanner could not compute.
PASS, FAIL, UNKNOWN = "#4fc88b", "#f0847a", "#93a39a"
AMBER = "#e8b94f"
#: The monitor pages' ink, surface and line (`sentiment_static`'s INK_2, INK,
#: SURFACE_COLOR and LINE_COLOR), since 2026-11-24: this page is drawn as one of them,
#: as the watchlist and the timeline are, not in the app's own theme.
MUTED = "#b6bfc8"
BRIGHT = "#eef2f5"
FAINT = "#7f8993"
PAGE = "#0d1013"
PANEL = {"backgroundColor": "#151a1e",
         "border": "1px solid rgba(255,255,255,0.09)", "borderRadius": "6px"}
MONO = '"JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace'
FONTS_HREF = ("https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700"
              "&family=JetBrains+Mono:wght@400;500;600&display=swap")
#: The pages behind the admin login, listed in the monitors' header row after the public
#: sites. Only these pages draw them, and they only reach a logged-in browser, so the
#: links are seen only when logged in. Hand-kept in step with the row in npf's
#: scripts/watchlist_site/index.html (which the timeline's build copies).
PRIVATE_SITES = (("Watchlist", "/watchlist", "Weekly COT setups"),
                 ("Timeline", "/timeline", "Market event timeline"),
                 ("News failure", "/news-failure", "News failure scan"))


def site_nav(current="News failure"):
    """Row one of the monitors' header as Dash components: `sentiment_static.site_nav`'s
    public entries, built from the same tuples, then the pages behind the login."""
    from components import sentiment_static as surveys
    links = [html.A(surveys.TREND_GROUP[0], href=surveys.TREND_GROUP[1])]
    for name, url in surveys.SITES:
        if name == surveys.CONTEXT_FROM:
            links.append(html.Span(className="div", **{"aria-hidden": "true"}))
        links.append(html.A(name, href=url, title=surveys.SITE_TITLES[name]))
    links.append(html.Span(className="div", **{"aria-hidden": "true"}))
    for name, url, title in PRIVATE_SITES:
        extra = {"aria-current": "page"} if name == current else {}
        links.append(html.A(name, href=url, title=title, **extra))
    links.append(html.A("COT Analyzer \u2192", href="/", className="home"))
    return html.Div(html.Nav(links, className="sites", **{"aria-label": "Monitors"}),
                    className="navs")

DISCLAIMER = ("Educational research only. Not financial advice and not a recommendation "
              "to buy or sell any instrument.")


#: The scanner's book names, in the order the picker lists them, and the names the rest
#: of this app uses for the same models (2026-11-19). The files keep the scanner's
#: names, and so do the store, its environment variable and the sidecar keys: those
#: are the data contract and are renamed upstream or not at all. Only the screen
#: translates, the alert text included (`relabel`).
MODELS = (("CMR", "Raw CLS"), ("NPF-CS", "NPF CS"), ("NPF-C-only", "NPF C-only"))
_MODEL_LABEL = dict(MODELS)
_MODEL_ORDER = {book: i for i, (book, _) in enumerate(MODELS)}
#: The page opens on this one (2026-11-19, "default to raw CLS").
DEFAULT_MODEL = "CMR"


#: The first book's name as a word of its own: not inside a file name, and not where it
#: names the licensed index or its method rather than the model ("... methodology").
_BOOK_TOKEN = re.compile(r"(?<![\w.])" + re.escape(MODELS[0][0])
                         + r"(?![\w])(?!\s+(?i:methodology|cot\b|index|membership|thesis))")
_SCAN_TITLE = re.compile(r"(?im)^(#{1,6}\s+)" + re.escape(MODELS[0][0]) + r"\s+(?=news)")


def relabel(markdown):
    """Alert text with the first book renamed to this app's name for the model.

    The words are otherwise untouched. Inside a code fence the replacement is the
    three-letter "Raw", because those blocks are fixed-width boards and a longer name
    would push every later column out of line; elsewhere it is the full label. A
    mention of the licensed index or its method is not a model name and is left as
    written, as is a file name. Slice and filter BEFORE calling this: the heading
    rules read the scanner's names."""
    full, short = _MODEL_LABEL[MODELS[0][0]], "Raw"
    out, fenced = [], False
    for line in _SCAN_TITLE.sub(r"\1", markdown or "").split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        out.append(_BOOK_TOKEN.sub(short if fenced else full, line))
    return "\n".join(out)


def model_label(book):
    """The app's name for a scanner book; an unknown book is shown as it is."""
    return _MODEL_LABEL.get(book, str(book or ""))


def store_root(env=None):
    env = os.environ if env is None else env
    return Path(os.path.expanduser(env.get(ENV) or DEFAULT_STORE))


def alerts_dir(env=None):
    return store_root(env) / "alerts"


def available_dates(env=None):
    """Every day with an alert (markdown or sidecar), newest first. GAP-/BLOCKER- notes
    are not days and are skipped by the name pattern."""
    d = alerts_dir(env)
    if not d.is_dir():
        return []
    return sorted({m.group(1) for p in d.iterdir() if (m := _DATE.match(p.name))},
                  reverse=True)


def updated_at(date=None, env=None):
    """When a day's alert files were last written, as an aware local datetime, or None.

    With no date, the newest across every day: the page's "last updated". The time is
    the file's modification time, which the push keeps (rsync -t), so on the server it
    is when the routine wrote the alert on the operator's Mac, not when it arrived."""
    d = alerts_dir(env)
    if not d.is_dir():
        return None
    times = [p.stat().st_mtime for p in d.iterdir()
             if (m := _DATE.match(p.name)) and (date is None or m.group(1) == date)]
    return datetime.fromtimestamp(max(times)).astimezone() if times else None


def fmt_time(when):
    """"Mon 2026-11-23 21:40 EST", or "unknown"."""
    return when.strftime("%a %Y-%m-%d %H:%M %Z") if when else "unknown"


@dataclass
class Day:
    date: str
    scan: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    markdown: str = ""
    backfill: dict = field(default_factory=dict)
    #: One scanner book to keep, or None for every model. A market two models hold has
    #: a row per model, so an unfiltered board lists it twice.
    book: str = None
    #: The environment the day was read with, so `written` looks in the same store.
    env: dict = field(default=None, repr=False, compare=False)

    @property
    def written(self):
        """When this day's files were last written (see `updated_at`)."""
        return updated_at(self.date, self.env)

    @property
    def structured(self):
        return bool(self.scan)

    @property
    def judged(self):
        """True when the routine's own judgments came with the numbers. A backfilled
        day has numbers only; its verdicts are prose in the alert."""
        return self.structured and not self.backfill

    @property
    def all_rows(self):
        """Every row the scanner wrote, whatever the model filter."""
        return list(self.scan.get("watchlist") or [])

    @property
    def rows(self):
        rows = self.all_rows
        return [r for r in rows if r.get("book") == self.book] if self.book else rows

    @property
    def groups(self):
        """The filtered rows, one list per market (see `by_market`)."""
        return by_market(self.rows)


def read_day(date, env=None, book=None):
    d = alerts_dir(env)
    day = Day(date, book=book or None, env=env)
    side = d / f"{date}.json"
    if side.is_file():
        try:
            blob = json.loads(side.read_text())
            day.scan, day.report = blob.get("scan") or {}, blob.get("report") or {}
            day.backfill = blob.get("backfill") or {}
        except (OSError, ValueError):
            day.scan, day.report, day.backfill = {}, {}, {}
    md = d / f"{date}.md"
    if md.is_file():
        day.markdown = md.read_text()
    return day


# ── per-row facts, all straight from scan.py's fields ─────────────────────────

def gates(row):
    """(obvious, idiosyncratic, side): True / False / None (cannot be computed)."""
    mm = row.get("move_materiality") or {}
    pdv = row.get("peer_divergence") or {}
    return mm.get("material"), pdv.get("idiosyncratic"), row.get("price_side_qualifies")


def verdict_of(row, report):
    """The routine's verdict for this row, or 'Not judged' when it gave none."""
    v = (report.get("verdicts") or {}).get(row.get("symbol")) or {}
    return v.get("verdict") or "Not judged", v.get("confidence"), v


def by_market(rows):
    """The rows as one list per market, each list in `MODELS` order.

    A market two models hold has a row per model, and the board used to print it once
    per row. Measured over the 73 sidecars on 2026-11-19 (230 same-market pairs): the
    direction, the bar, all three price gates, the blockers and `failure_eligible`
    never differ between a market's rows. What does differ is positioning: whether
    the model calls the market crowded or only close (45 pairs), and with it the
    evidence list and the mechanical score. So the market is shown once, says which
    models hold it, and keeps one evidence fold per model."""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("symbol"), []).append(r)
    return [sorted(g, key=lambda r: _MODEL_ORDER.get(r.get("book"), len(MODELS)))
            for g in groups.values()]


def lead(group):
    """The row that speaks for a market's price facts: a crowded one when there is
    one, since the board files the market under its strongest reading."""
    return next((r for r in group if r.get("confirmed")), group[0])


def models_of(rows, symbol):
    """[(book, crowded)] for every model holding `symbol`, in `MODELS` order."""
    mine = by_market([r for r in rows if r.get("symbol") == symbol])
    return [(r.get("book"), bool(r.get("confirmed"))) for r in (mine[0] if mine else [])]


def counts(day):
    leads = [lead(g) for g in day.groups]
    return {
        "rows": len(leads),
        "crowded": sum(1 for r in leads if r.get("confirmed")),
        "obvious": sum(1 for r in leads if gates(r)[0]),
        "eligible": sum(1 for r in leads if r.get("failure_eligible")),
    }


def sort_groups(groups):
    """Crowded first, then eligible, then by the size of the move: the markets worth
    arguing about lead each section."""
    def key(g):
        r = lead(g)
        mm = r.get("move_materiality") or {}
        return (0 if r.get("confirmed") else 1, 0 if r.get("failure_eligible") else 1,
                -(mm.get("abs_chg_pctile") or 0))
    return sorted(groups, key=key)


def sort_rows(rows):
    """One row per market (its lead), in board order."""
    return [lead(g) for g in sort_groups(by_market(rows))]


def index_date(day):
    """The positioning index's own date (ISO), read from its file name, or ''."""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(day.scan.get("cmr_index_file") or ""))
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ""


def index_flags(day):
    """Flags the alert would raise about the data itself, in plain words."""
    flags = []
    sync = str(day.scan.get("cmr_index_sync") or "")
    if sync and ("FAILED" in sync or "not found" in sync):
        flags.append(("Index sync", sync))
    idx = index_date(day)
    if idx:
        if idx > day.date:
            flags.append(("Index date", f"The index is dated {idx}, after the scan day "
                          f"{day.date}: its positioning does not describe this day."))
    dropped = day.scan.get("dropped_symbols") or []
    if dropped:
        flags.append(("Incomplete", "Dropped symbols: " + ", ".join(dropped)))
    return flags


# ── one market over time ──────────────────────────────────────────────────────

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_PAREN = re.compile(r"\(([^()]*)\)")
_SYM = re.compile(r"^(?=.*[A-Z])[A-Z0-9]{1,4}$")
#: Book names turn up in brackets too ("close-to-set-up (CMR)"); they are not markets.
_NOT_SYMBOLS = frozenset({"CMR", "NPF"})


def _headings(markdown):
    """(line index, level, text) for every heading outside a code fence."""
    out, fenced = [], False
    for i, line in enumerate(markdown.splitlines()):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and (m := _HEADING.match(line)):
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def heading_symbol(text):
    """(symbol, market name) when a heading is a market's, else (None, None).

    A market heading carries its symbol as the FIRST bracket, "NATURAL GAS (NG) ...".
    That is the one thing every alert format since July kept. Later brackets are
    status words ("(watch-only)") and a first bracket that is not a symbol
    ("Confirmed set-ups (7)") marks a heading about something else."""
    m = _PAREN.search(text)
    if not m or not _SYM.match(m.group(1)) or m.group(1) in _NOT_SYMBOLS:
        return None, None
    return m.group(1), text[:m.start()].strip(" $*_").title()


def heading_books(text):
    """The scanner books a heading names. Empty when it names none, which is not the
    same as naming every one: such a section cannot be assigned to a model."""
    return {b for b, _ in MODELS
            if re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", text)}


def sections_for_book(sections, book):
    """Keep the sections whose heading names `book`, plus any whose heading names no
    book at all (dropping those would hide prose the filter cannot place)."""
    if not book:
        return sections
    keep = []
    for sec in sections:
        named = heading_books(sec.split("\n", 1)[0])
        if not named or book in named:
            keep.append(sec)
    return keep


def market_sections(markdown, symbol):
    """Each section of an alert headed by this market, as written.

    From the market's heading to the next heading of the same level or shallower. More
    than one comes back when two books hold the market. The prose is not parsed: the
    wording and the fields drifted for months, and reading fields out of it would
    invent structure the file never had."""
    lines, heads, out = markdown.splitlines(), _headings(markdown), []
    for n, (i, level, text) in enumerate(heads):
        if heading_symbol(text)[0] != symbol:
            continue
        end = next((j for j, lv, _ in heads[n + 1:] if lv <= level), len(lines))
        out.append("\n".join(lines[i:end]).strip())
    return out


def _has_market_headings(markdown):
    return any(heading_symbol(t)[0] for _, _, t in _headings(markdown))


def markets(env=None):
    """Every market that was ever a set-up, as [(symbol, name)], sorted by name. The
    name is the one the newest day used."""
    names = {}
    for date in available_dates(env):          # newest first, so the first name wins
        day = read_day(date, env)
        for r in day.rows:
            if r.get("symbol"):
                names.setdefault(r["symbol"], str(r.get("market") or "").title())
        for _, _, text in _headings(day.markdown):
            sym, name = heading_symbol(text)
            if sym:
                names.setdefault(sym, name)
    return sorted(names.items(), key=lambda kv: (kv[1].lower(), kv[0]))


#: What a day holds for one market.
ROWS, SECTIONS, ABSENT, UNSLICED = "rows", "sections", "absent", "unsliced"


@dataclass
class MarketDay:
    date: str
    kind: str
    rows: list = field(default_factory=list)
    report: dict = field(default_factory=dict)
    sections: list = field(default_factory=list)
    mentions: int = 0
    backfilled: bool = False
    #: [(book, crowded)] for every model holding the market that day, filter or not.
    models: list = field(default_factory=list)

    @property
    def set_up(self):
        return self.kind in (ROWS, SECTIONS)


def market_day(day, symbol):
    """One day's record for one market. The four outcomes are kept apart on purpose:
    structured rows, markdown sections, a day the market was not a set-up, and a day
    whose file cannot answer the question (no per-market headings at all)."""
    sections = sections_for_book(market_sections(day.markdown, symbol), day.book)
    if day.structured:
        rows = [r for r in day.rows if r.get("symbol") == symbol]
        held = models_of(day.all_rows, symbol)
        if not day.judged:
            # Backfilled: the numbers, plus what the alert wrote. A section with no
            # row means the alert covered a market today's scanner does not set up
            # for that day; show the prose rather than call it absent.
            if rows or sections:
                return MarketDay(day.date, ROWS if rows else SECTIONS, rows=rows,
                                 sections=sections, backfilled=True, models=held)
            return MarketDay(day.date, ABSENT, backfilled=True)
        return MarketDay(day.date, ROWS if rows else ABSENT, rows=rows, report=day.report,
                         models=held)
    if sections:
        return MarketDay(day.date, SECTIONS, sections=sections)
    if _has_market_headings(day.markdown):
        return MarketDay(day.date, ABSENT)
    return MarketDay(day.date, UNSLICED, mentions=len(
        re.findall(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])", day.markdown)))


def market_history(symbol, days=None, env=None, book=None):
    """The newest `days` scan days (all of them when None) for one market, newest
    first. Scan days, not calendar days: a day with no alert file is not in the store
    and so is not in the window."""
    dates = available_dates(env)
    return [market_day(read_day(d, env, book), symbol)
            for d in (dates[:days] if days else dates)]


# ── rendering ─────────────────────────────────────────────────────────────────

def _ord(n):
    n = int(round(n))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _chip(text, color, filled=False):
    style = {"display": "inline-block", "padding": "1px 8px", "borderRadius": "3px",
             "fontSize": "0.75rem", "fontWeight": 500, "whiteSpace": "nowrap",
             "border": f"1px solid {color}", "color": color}
    if filled:
        style.update({"backgroundColor": color, "color": "#111"})
    return html.Span(text, style=style)


def _gate_pill(label, ok, title):
    color = UNKNOWN if ok is None else (PASS if ok else FAIL)
    # Words, not ticks: a gate passes or fails, it does not "confirm" anything.
    mark = "n/a" if ok is None else ("pass" if ok else "fail")
    return html.Span(f"{label} {mark}", title=title, style={
        "display": "inline-block", "minWidth": "2.6rem", "textAlign": "center",
        "padding": "1px 6px", "marginRight": "4px", "borderRadius": "3px",
        "fontSize": "0.72rem", "fontFamily": MONO, "color": color,
        "border": f"1px solid {color}"})


def gate_strip(row):
    o, i, s = gates(row)
    return html.Div([
        _gate_pill("Size", o, "Obvious: 70th percentile AND 0.75x ATR(20)"),
        _gate_pill("Peers", i, "Idiosyncratic: no uncrowded bloc peer made the same move"
                   + (" (no peers to compare)" if i is None else "")),
        _gate_pill("Side", s, "Close on the side the set-up needs"),
    ], style={"whiteSpace": "nowrap"})


def size_cell(row):
    mm = row.get("move_materiality") or {}
    pct, atr = mm.get("abs_chg_pctile"), mm.get("move_vs_atr20")
    if pct is None or atr is None:
        return html.Span("–", style={"color": MUTED})
    fill = min(atr / 2.0, 1.0) * 100
    return html.Div([
        html.Span(f"{_ord(pct)} pct · {atr:.2f}x ATR",
                  style={"fontFamily": MONO, "fontSize": "0.8rem", "color": BRIGHT}),
        html.Div([
            html.Div(style={"position": "absolute", "left": 0, "top": 0, "bottom": 0,
                            "width": f"{fill}%", "borderRadius": "3px",
                            "backgroundColor": PASS if mm.get("material") else MUTED}),
            html.Div(style={"position": "absolute", "left": "37.5%", "top": "-3px",
                            "bottom": "-3px", "width": "2px", "backgroundColor": BRIGHT,
                            "opacity": 0.6}),
        ], title="Fill: move in ATR(20). Tick: 0.75x, the minimum for an obvious move.",
           style={"position": "relative", "height": "6px", "width": "110px",
                  "marginTop": "5px", "borderRadius": "3px",
                  "backgroundColor": "rgba(255,255,255,0.08)"}),
    ])


def change_cell(row):
    lc = row.get("latest_candle") or {}
    chg, close = lc.get("vs_prev_close_pct"), lc.get("close")
    color = PASS if (chg or 0) > 0 else (FAIL if (chg or 0) < 0 else MUTED)
    return html.Div([
        html.Div(f"{close:,}" if isinstance(close, (int, float)) else "–",
                 style={"fontFamily": MONO, "color": BRIGHT}),
        html.Div(f"{chg:+.2f}%" if chg is not None else "–",
                 style={"fontFamily": MONO, "color": color}),
    ], style={"textAlign": "right"})


def verdict_chip(verdict, confidence):
    v = verdict.upper()
    if "CONFIRMED" in v:
        chip = _chip(verdict, PASS, filled=True)
    elif "WATCH" in v or "EARLY" in v:
        chip = _chip(verdict, AMBER)
    elif v == "NOT JUDGED":
        chip = _chip(verdict, FAIL)
    else:
        chip = _chip(verdict, MUTED)
    parts = [chip]
    if confidence:
        parts.append(html.Span(f"confidence {confidence}", style={
            "display": "block", "marginTop": "3px", "fontSize": "0.72rem", "color": AMBER}))
    return html.Div(parts)


def evidence_table(row):
    ev = row.get("evidence") or {}
    fors, againsts = ev.get("evidence_for") or [], ev.get("evidence_against") or []

    def col(title, items, color, empty):
        body = [html.Div([html.B(it.get("factor", ""), style={"color": BRIGHT}),
                          html.Span(" — " + it.get("detail", ""))],
                         style={"marginBottom": "4px"}) for it in items]
        return html.Div([html.Div(title, style={"color": color, "fontWeight": 600,
                                                "marginBottom": "4px"}),
                         *(body or [html.Div(empty, style={"fontStyle": "italic"})])],
                        style={"flex": "1 1 280px", "minWidth": 0})

    score, tier = ev.get("mechanical_score"), ev.get("confidence_tier")
    head = f"Price evidence {score:.1f}/100 · {tier}" if score is not None else ""
    return html.Div([
        html.Div(head, style={"color": MUTED, "fontSize": "0.75rem", "marginBottom": "6px"}),
        html.Div([col("Case FOR a news failure", fors, PASS, "Nothing for it."),
                  col("Case AGAINST", againsts, FAIL, "Empty: nothing argues against.")],
                 style={"display": "flex", "flexWrap": "wrap", "gap": "16px"}),
    ], style={"fontSize": "0.8rem", "color": MUTED, "padding": "8px 4px"})


def news_cell(row, report):
    n = (report.get("news") or {}).get(row.get("symbol")) or {}
    need = (row.get("expected") or {}).get("news_needed")
    text = n.get("text") or "Not researched"
    return html.Div([
        html.Div(text, style={"color": BRIGHT if n else FAIL}),
        html.Div(" · ".join(x for x in (n.get("type"), f"needs {need}" if need else None) if x),
                 style={"fontSize": "0.7rem", "textTransform": "uppercase",
                        "letterSpacing": "0.04em", "color": MUTED, "marginTop": "3px"}),
    ], style={"fontSize": "0.78rem", "maxWidth": "38ch"})


def why_cell(row, vinfo, wide=False):
    reasons = [vinfo["reason"]] if vinfo.get("reason") and not row.get("failure_blockers") \
        else list(row.get("failure_blockers") or [])
    if vinfo.get("against"):
        reasons.append("Against: " + vinfo["against"])
    if wide and not reasons:
        reasons = ["Passes all three price gates. Whether it was a failure turned on "
                   "the news, which is in the alert."]
    return html.Div([html.Div(r, style={"marginBottom": "2px"}) for r in reasons] or "–",
                    style={"fontSize": "0.75rem", "color": MUTED,
                           "maxWidth": "70ch" if wide else "34ch"})


TH = {"color": MUTED, "fontSize": "0.7rem", "textTransform": "uppercase",
      "letterSpacing": "0.06em", "fontWeight": 500, "padding": "6px 10px",
      "backgroundColor": "rgba(255,255,255,0.04)", "whiteSpace": "nowrap"}
TD = {"padding": "8px 10px", "borderTop": "1px solid rgba(255,255,255,0.08)",
      "verticalAlign": "top"}
COLS = ("Market", "Close", "Size vs own history", "Gates", "News read", "Verdict", "Why")
#: A backfilled day: the same board without the two columns nobody recorded.
NUMERIC_COLS = ("Market", "Close", "Size vs own history", "Gates", "Price gates say")


def models_line(models):
    """"Raw CLS · NPF CS (close)": the models holding a market. A model that only has
    it close to set-up is marked when another has it crowded; when none has it crowded
    the board's own section already says so."""
    mixed = any(crowded for _, crowded in models)
    return " · ".join(model_label(b) + ("" if crowded or not mixed else " (close)")
                      for b, crowded in models)


def set_up_rows(group, report, judged=True, models=None):
    """One market as table rows: its facts once, then one folded evidence row per
    model in `group` (the positioning evidence is the part that differs by model).
    `models` is every model holding the market, which is more than `group` when a
    model filter is on. With `judged` off (a backfilled day) the News and Verdict
    cells are left out."""
    r = lead(group)
    models = models or [(g.get("book"), bool(g.get("confirmed"))) for g in group]
    verdict, conf, vinfo = verdict_of(r, report)
    cols = COLS if judged else NUMERIC_COLS
    dim = {} if r.get("confirmed") else {"opacity": 0.8}
    mono = {"fontFamily": MONO, "fontSize": "0.7rem", "color": MUTED}
    market = html.Div([
        html.B(r.get("market", "").title(), style={"color": BRIGHT}),
        html.Div(f"{r.get('symbol')} · {r.get('direction')}", style=mono),
        html.Div(models_line(models), style=mono, title="Models this market is set up under"),
    ])
    return [
        html.Tr([
            html.Td(market, style=TD), html.Td(change_cell(r), style=TD),
            html.Td(size_cell(r), style=TD), html.Td(gate_strip(r), style=TD),
            *([html.Td(news_cell(r, report), style=TD),
               html.Td(verdict_chip(verdict, conf), style=TD)] if judged else []),
            html.Td(why_cell(r, vinfo, wide=not judged), style=TD),
        ], style=dim),
        # The evidence rows sit right under their market, closed by default.
        *[html.Tr(html.Td(html.Details([
            html.Summary(f"Case for and against · {g.get('symbol')} {model_label(g.get('book'))}",
                         style={"cursor": "pointer", "fontSize": "0.72rem", "color": MUTED}),
            evidence_table(g)]), colSpan=len(cols), style={"padding": "0 10px 6px 10px"}))
          for g in group],
    ]


def _table(body_rows, judged=True):
    cols = COLS if judged else NUMERIC_COLS
    return html.Div(html.Table([
        html.Thead(html.Tr([html.Th(c, style=TH) for c in cols])),
        html.Tbody(body_rows),
    ], style={"width": "100%", "minWidth": "980px" if judged else "720px", "borderCollapse": "collapse",
              "color": MUTED, "fontSize": "0.85rem"}), style={"overflowX": "auto"})


def board_rows(day):
    out = []
    groups = day.groups
    for title, part in (("Crowded now", [g for g in groups if lead(g).get("confirmed")]),
                        ("Close to set-up (watch only)",
                         [g for g in groups if not lead(g).get("confirmed")])):
        if not part:
            continue
        out.append(html.Tr(html.Td(f"{title} · {len(part)}", colSpan=len(
            COLS if day.judged else NUMERIC_COLS), style={
            **TD, "color": MUTED, "fontSize": "0.72rem", "letterSpacing": "0.08em",
            "textTransform": "uppercase", "backgroundColor": "rgba(255,255,255,0.03)"})))
        for g in sort_groups(part):
            out += set_up_rows(g, day.report, day.judged,
                               models_of(day.all_rows, lead(g).get("symbol")))
    return out


def board_table(day):
    return _table(board_rows(day), day.judged)


def stat_tiles(day):
    c = counts(day)
    tiles = (("Set-up markets", c["rows"]), ("Crowded now", c["crowded"]),
             ("Obvious moves", c["obvious"]), ("Failure-eligible", c["eligible"]))
    return html.Div([html.Div([
        html.Div(str(v), style={"fontFamily": MONO, "fontSize": "1.4rem",
                                "color": BRIGHT}),
        html.Div(k, style={"fontSize": "0.7rem", "textTransform": "uppercase",
                           "letterSpacing": "0.06em", "color": MUTED})])
        for k, v in tiles], style={"display": "flex", "flexWrap": "wrap", "gap": "10px 28px"})


def highlight_cards(day):
    """One card per row the routine flagged (a confirmed failure or a watch item), with
    its whole argument visible: the reader should not have to open a fold to see why the
    one interesting row is or is not a signal."""
    flagged = [r for r in sort_rows(day.rows)
               if verdict_of(r, day.report)[0].upper() not in ("NO FAILURE", "NOT JUDGED")]
    seen, cards = set(), []
    for r in flagged:
        if r.get("symbol") in seen:
            continue
        seen.add(r.get("symbol"))
        verdict, conf, vinfo = verdict_of(r, day.report)
        cards.append(html.Div([
            html.Div([
                html.Div([html.Span(f"{r.get('market', '').title()} ({r.get('symbol')})",
                                    style={"color": BRIGHT, "fontSize": "1.05rem",
                                           "fontWeight": 600, "marginRight": "10px"}),
                          html.Span(f"{r.get('direction')} · "
                                    + ("crowded" if r.get("confirmed") else "close to set-up")
                                    + " · " + models_line(
                                        models_of(day.all_rows, r.get("symbol"))),
                                    style={"color": MUTED, "fontSize": "0.8rem"})]),
                verdict_chip(verdict, conf),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "flex-start", "gap": "12px", "flexWrap": "wrap"}),
            html.Div([change_cell(r), size_cell(r), gate_strip(r)],
                     style={"display": "flex", "gap": "24px", "alignItems": "center",
                            "flexWrap": "wrap", "margin": "10px 0"}),
            news_cell(r, day.report),
            html.Div(vinfo.get("reason", ""), style={"color": BRIGHT, "fontSize": "0.82rem",
                                                    "marginTop": "8px"}),
            html.Div(("Strongest argument against: " + vinfo["against"])
                     if vinfo.get("against") else "",
                     style={"color": FAIL, "fontSize": "0.8rem", "marginTop": "4px"}),
            evidence_table(r),
        ], style={**PANEL, "padding": "14px 16px", "borderLeft": f"4px solid {AMBER}",
                  "marginBottom": "12px"}))
    return cards


def flag_bar(label, text):
    return html.Div([html.B(label.upper(), style={"color": AMBER, "marginRight": "10px",
                                                 "fontSize": "0.75rem"}),
                     html.Span(text)],
                    style={"borderLeft": f"4px solid {AMBER}", "padding": "8px 12px",
                           "backgroundColor": "rgba(232,185,79,0.10)", "fontSize": "0.82rem",
                           "color": BRIGHT, "borderRadius": "3px", "marginBottom": "8px"})


def backfill_note(day):
    b = day.backfill
    return flag_bar("Recomputed", (
        f"These numbers were recomputed on {b.get('computed_on', 'a later date')} by "
        "today's scanner, from the bars as they stood on the day. The news read and the "
        "verdict were judged at the time and are in the alert below, as written apart "
        "from model names, which are this page's. The "
        "scanner's rules changed over these months, so where a gate here and the alert "
        "disagree, the alert is the record."))


def backfilled_body(day):
    """A backfilled day below its banner: the note, the numeric board, then the alert
    open rather than folded, because on these days the alert IS the verdict."""
    unnamed = day.backfill.get("symbols_never_named_in_alert") or []
    parts = [backfill_note(day)]
    if unnamed:
        parts.append(flag_bar("Check", "The alert never names " + ", ".join(unnamed)
                              + ". The watchlist rebuilt for this day may not be the "
                              "one the scan saw."))
    parts.append(html.Div([
        html.H6("Every set-up, price side only", style={
            "color": MUTED, "letterSpacing": "0.08em", "textTransform": "uppercase",
            "fontSize": "0.75rem", "padding": "10px 12px 0 12px"}),
        html.Div("Gates: Size = 70th percentile and 0.75x ATR(20); Peers = no uncrowded "
                 "bloc peer made the same move; Side = the close the set-up needs. "
                 "Passing all three made a row worth judging, nothing more.",
                 style={"color": MUTED, "fontSize": "0.75rem", "padding": "0 12px 8px"}),
        board_table(day)], style={**PANEL, "marginBottom": "12px"}))
    if day.markdown:
        parts.append(html.Div(dcc.Markdown(relabel(day.markdown), className="nf-md"),
                              style={**PANEL, "padding": "16px", "overflowX": "auto"}))
    return parts


def render_day(day):
    """Everything below the date picker for one day."""
    if not day.structured:
        if not day.markdown:
            return html.Div(f"No alert found for {day.date}.", style={"color": MUTED})
        return html.Div([
            flag_bar("Archive", "This day predates the structured feed, so it is shown "
                     "as the alert file was written, apart from model names."),
            html.Div(dcc.Markdown(relabel(day.markdown), className="nf-md"),
                     style={**PANEL, "padding": "16px", "overflowX": "auto"}),
        ])
    rep, scan = day.report, day.scan
    eligible = counts(day)["eligible"]
    if day.judged:
        headline = rep.get("headline") or ("Not judged yet" if eligible else
                                           "No confirmed news failures")
    else:
        headline = "Numbers recomputed. The verdict is in the alert below."
    banner = html.Div([
        html.Div([html.Div(headline, style={"color": BRIGHT, "fontSize": "1.4rem",
                                            "fontWeight": 600}),
                  html.Div(f"Prices as of {scan.get('prices_newest_data')} · index "
                           f"dated {index_date(day) or 'unknown'} · written "
                           f"{fmt_time(day.written)}"
                           + (f" · {model_label(day.book)} only" if day.book else ""),
                           style={"color": MUTED, "fontSize": "0.8rem",
                                  "fontFamily": MONO})],
                 style={"minWidth": 0}),
        stat_tiles(day),
    ], style={**PANEL, "padding": "14px 16px", "display": "flex", "flexWrap": "wrap",
              "justifyContent": "space-between", "alignItems": "center", "gap": "14px",
              "marginBottom": "12px"})
    parts = [banner, *[flag_bar(k, v) for k, v in index_flags(day)]]
    if not day.judged:
        return html.Div([*parts, *backfilled_body(day)])
    cards = highlight_cards(day)
    if cards:
        parts += [html.H6("Worth a look", style={"color": MUTED, "letterSpacing": "0.08em",
                                                 "textTransform": "uppercase",
                                                 "fontSize": "0.75rem", "margin": "6px 0"}),
                  *cards]
    parts += [
        html.Div([html.H6("Every set-up", style={
            "color": MUTED, "letterSpacing": "0.08em", "textTransform": "uppercase",
            "fontSize": "0.75rem", "padding": "10px 12px 0 12px"}),
            html.Div("Gates: Size = 70th percentile and 0.75x ATR(20); Peers = no "
                     "uncrowded bloc peer made the same move; Side = the close the set-up "
                     "needs. All three are required, and a failure also needs crowded "
                     "positioning and news the close went against.",
                     style={"color": MUTED, "fontSize": "0.75rem", "padding": "0 12px 8px"}),
            board_table(day)], style={**PANEL, "marginBottom": "12px"}),
    ]
    notes = rep.get("notes") or []
    if notes:
        parts.append(html.Div([html.H6("The day", style={
            "color": MUTED, "letterSpacing": "0.08em", "textTransform": "uppercase",
            "fontSize": "0.75rem"}),
            html.Ul([html.Li(n) for n in notes], style={"marginBottom": 0})],
            style={**PANEL, "padding": "12px 16px", "color": MUTED, "fontSize": "0.82rem",
                   "marginBottom": "12px"}))
    srcs = rep.get("sources") or []
    if srcs:
        parts.append(html.Div(["Sources: ", *[
            html.Span([html.A(s.get("title", s.get("url")), href=s.get("url"),
                              target="_blank", rel="noopener"),
                       "" if i == len(srcs) - 1 else " · "])
            for i, s in enumerate(srcs)]], style={"fontSize": "0.75rem", "color": MUTED}))
    if day.markdown:
        parts.append(html.Details([
            html.Summary("The full alert file, model names as shown above", style={"cursor": "pointer",
                                                       "color": MUTED, "fontSize": "0.8rem"}),
            html.Div(dcc.Markdown(relabel(day.markdown), className="nf-md"),
                     style={**PANEL, "padding": "16px", "overflowX": "auto",
                            "marginTop": "8px"})], style={"marginTop": "12px"}))
    return html.Div(parts)


def _day_card(entry, symbol, book=None):
    head_style = {"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "gap": "12px", "flexWrap": "wrap"}
    date = html.Span(entry.date, style={"color": BRIGHT, "fontFamily": MONO,
                                        "fontWeight": 600})
    if entry.kind == ABSENT:
        return html.Div([date, html.Span(f"{symbol} was not a set-up"
                                         + (f" under {model_label(book)}" if book else "")
                                         + " on this day.",
                                         style={"color": MUTED, "fontSize": "0.82rem"})],
                        style={**PANEL, **head_style, "padding": "8px 16px",
                               "marginBottom": "8px", "opacity": 0.75})
    if entry.kind == UNSLICED:
        said = (f"It mentions {symbol} {entry.mentions} time"
                f"{'' if entry.mentions == 1 else 's'}; pick the day to read it."
                if entry.mentions else f"It does not mention {symbol}.")
        return html.Div([date, html.Span(
            "This day's alert has no per-market sections, so whether the market was a "
            "set-up cannot be read from it. " + said,
            style={"color": MUTED, "fontSize": "0.82rem"})],
            style={**PANEL, **head_style, "padding": "8px 16px", "marginBottom": "8px",
                   "borderLeft": f"4px solid {UNKNOWN}"})
    if entry.kind == ROWS and entry.backfilled:
        body = _table(set_up_rows(entry.rows, {}, False, entry.models), False)
        prose = dcc.Markdown(relabel("\n\n".join(entry.sections)), className="nf-md nf-md-slice") \
            if entry.sections else html.Div(
                "The alert gave this market no section of its own that day; its row is "
                "in that day's board.", style={"color": MUTED, "fontSize": "0.8rem"})
        return html.Div([
            html.Div([date, html.Span("numbers recomputed · verdict as the alert was written",
                                      style={"color": MUTED, "fontSize": "0.72rem"})],
                     style={**head_style, "padding": "10px 16px 6px"}),
            body, html.Div(prose, style={"padding": "6px 16px 10px", "overflowX": "auto"}),
        ], style={**PANEL, "marginBottom": "8px", "borderLeft": f"4px solid {MUTED}"})
    if entry.kind == ROWS:
        verdicts = {verdict_of(r, entry.report)[0].upper() for r in entry.rows}
        flagged = bool(verdicts - {"NO FAILURE", "NOT JUDGED"})
        body = _table(set_up_rows(entry.rows, entry.report, True, entry.models))
        return html.Div([html.Div(date, style={"padding": "10px 16px 6px"}), body],
                        style={**PANEL, "marginBottom": "8px",
                               "borderLeft": f"4px solid {AMBER if flagged else PASS}"})
    return html.Div([
        html.Div([date, html.Span("as the alert was written",
                                  style={"color": MUTED, "fontSize": "0.72rem"})],
                 style=head_style),
        dcc.Markdown(relabel("\n\n".join(entry.sections)), className="nf-md nf-md-slice"),
    ], style={**PANEL, "padding": "10px 16px", "marginBottom": "8px", "overflowX": "auto",
              "borderLeft": f"4px solid {MUTED}"})


def render_history(symbol, entries, name="", book=None):
    """Everything below the pickers for one market over a window of scan days."""
    if not entries:
        return html.Div("No alerts found.", style={"color": MUTED})
    c = {k: sum(1 for e in entries if e.kind == k) for k in (ROWS, SECTIONS, ABSENT, UNSLICED)}
    tiles = (("Scan days", len(entries)), ("Set-up on", c[ROWS] + c[SECTIONS]),
             ("Not a set-up", c[ABSENT]), ("Cannot tell", c[UNSLICED]))
    banner = html.Div([
        html.Div([html.Div(f"{name} ({symbol})" if name else symbol,
                           style={"color": BRIGHT, "fontSize": "1.4rem", "fontWeight": 600}),
                  html.Div(f"{entries[-1].date} to {entries[0].date}, newest first"
                           + (f" · {model_label(book)} only" if book else ""),
                           style={"color": MUTED, "fontSize": "0.8rem",
                                  "fontFamily": MONO})]),
        html.Div([html.Div([
            html.Div(str(v), style={"fontFamily": MONO, "fontSize": "1.4rem",
                                    "color": BRIGHT}),
            html.Div(k, style={"fontSize": "0.7rem", "textTransform": "uppercase",
                               "letterSpacing": "0.06em", "color": MUTED})])
            for k, v in tiles if v or k != "Cannot tell"],
            style={"display": "flex", "flexWrap": "wrap", "gap": "10px 28px"}),
    ], style={**PANEL, "padding": "14px 16px", "display": "flex", "flexWrap": "wrap",
              "justifyContent": "space-between", "alignItems": "center", "gap": "14px",
              "marginBottom": "12px"})
    return html.Div([banner, *[_day_card(e, symbol, book) for e in entries]])
