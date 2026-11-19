"""The news-failure scan page: local-only gate, reading the alert store, and the rules the
scanner's own board keeps (every set-up once, an unjudged row never reads as cleared)."""
import importlib
import json

import dash
import pytest

import components.news_failure as nf
import local_pages


def _row(sym, confirmed=True, material=False, idio=False, side=False, eligible=False,
         blockers=("move is not obvious",), book="CMR", pct=40.0, atr=0.3):
    return {"symbol": sym, "market": sym.upper(), "book": book, "direction": "LONG",
            "confirmed": confirmed, "failure_eligible": eligible,
            "failure_blockers": list(blockers),
            "price_side_qualifies": side, "expected": {"news_needed": "bearish"},
            "latest_candle": {"close": 100.0, "vs_prev_close_pct": 1.2},
            "move_materiality": {"material": material, "abs_chg_pctile": pct,
                                 "move_vs_atr20": atr},
            "peer_divergence": None if idio is None else {"idiosyncratic": idio},
            "evidence": {"evidence_for": [{"factor": "Size", "detail": "big"}],
                         "evidence_against": [], "mechanical_score": 33.8,
                         "confidence_tier": "LOW"}}


@pytest.fixture
def store(tmp_path):
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    (alerts / "2026-11-16.md").write_text("# CMR News-Failure Scan — 2026-11-16\n\nold day")
    (alerts / "2026-11-17.md").write_text("# CMR News-Failure Scan — 2026-11-17\n")
    (alerts / "GAP-2026-08-10_2026-08-20.md").write_text("gap")
    scan = {"prices_newest_data": "2026-11-17",
            "cmr_index_file": "Official_CMR_CoT_Index_11.16.2026.xlsx",
            "cmr_index_sync": "already has", "dropped_symbols": [],
            "watchlist": [
                _row("LBR", confirmed=False, material=True, idio=None, side=True,
                     eligible=True, blockers=(), pct=100.0, atr=1.41),
                _row("RTY"), _row("SI"), _row("SI", book="NPF-CS"), _row("ZW")]}
    report = {"headline": "No confirmed news failures",
              "news": {"LBR": {"text": "NAHB 25 vs 29", "type": "scheduled release"}},
              "verdicts": {"LBR": {"verdict": "EARLY / WATCH-ONLY", "confidence": "LOW",
                                   "reason": "close to set-up", "against": "no peer"},
                           "RTY": {"verdict": "No failure"},
                           "SI": {"verdict": "No failure"}}}
    (alerts / "2026-11-17.json").write_text(json.dumps({"scan": scan, "report": report}))
    return {nf.ENV: str(tmp_path)}


def _text(component):
    """Every string in a rendered tree, for assertions on what a reader sees."""
    out = []

    def walk(c):
        if c is None:
            return
        if isinstance(c, (str, int, float)):
            out.append(str(c))
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
        else:
            walk(getattr(c, "children", None))
    walk(component)
    return " ".join(out)


def test_dates_are_days_newest_first_and_skip_gap_notes(store):
    assert nf.available_dates(store) == ["2026-11-17", "2026-11-16"]


def test_a_missing_store_has_no_dates(tmp_path):
    assert nf.available_dates({nf.ENV: str(tmp_path / "nope")}) == []


def test_a_day_with_a_sidecar_is_structured_and_one_without_is_not(store):
    assert nf.read_day("2026-11-17", store).structured
    old = nf.read_day("2026-11-16", store)
    assert not old.structured and "old day" in old.markdown


def test_counts_come_from_the_scan(store):
    c = nf.counts(nf.read_day("2026-11-17", store))
    # Markets, not rows: SI is held by two models and counts once.
    assert c == {"rows": 4, "crowded": 3, "obvious": 1, "eligible": 1}


def test_every_set_up_appears_exactly_once_on_the_board(store):
    """The scanner's rule 1: a market must not be able to fall out of the table."""
    day = nf.read_day("2026-11-17", store)
    rows = [r for r in nf.board_rows(day)
            if "Case for and against" in _text(r)]
    assert len(rows) == len(day.rows)


def test_an_unjudged_row_never_reads_as_cleared(store):
    """ZW has no verdict from the routine: it must say so, not 'No failure'."""
    day = nf.read_day("2026-11-17", store)
    zw = next(r for r in day.rows if r["symbol"] == "ZW")
    assert nf.verdict_of(zw, day.report)[0] == "Not judged"


def test_a_watch_item_gets_its_own_card_with_the_case_against(store):
    day = nf.read_day("2026-11-17", store)
    cards = nf.highlight_cards(day)
    assert len(cards) == 1
    text = _text(cards[0])
    assert "Lbr" in text and "LOW" in text and "no peer" in text


def test_no_peers_is_unknown_not_a_pass(store):
    day = nf.read_day("2026-11-17", store)
    lbr = next(r for r in day.rows if r["symbol"] == "LBR")
    assert nf.gates(lbr) == (True, None, True)
    assert "Peers n/a" in _text(nf.gate_strip(lbr))


def test_an_index_dated_after_the_scan_day_is_flagged(store):
    day = nf.read_day("2026-11-17", store)
    assert nf.index_flags(day) == []
    day.scan["cmr_index_file"] = "Official_CMR_CoT_Index_11.22.2026.xlsx"
    assert [k for k, _ in nf.index_flags(day)] == ["Index date"]


def test_an_archive_day_renders_its_markdown(store):
    text = _text(nf.render_day(nf.read_day("2026-11-16", store)))
    assert "predates the structured feed" in text


# ── one market over time ──────────────────────────────────────────────────────

OLD_ALERT = """# CMR news-failure scan — 2026-11-13

## Verdict

### Near-misses (2)

Nothing about NG here.

```
# NATURAL GAS (NG) inside the board fence is not a heading
```

## Market-by-market

### NATURAL GAS (NG) — CMR — LONG

- cmr body

### Natural Gas (NG) — NPF-C-only LONG, close to set-up (EARLY / WATCH-ONLY)

- npf body

### $ DOLLAR INDEX (DX) — Close Set Up Short — watch-only

- dx body

## Notes on this run

trailing notes
"""


@pytest.fixture
def history_store(store):
    alerts = nf.alerts_dir(store)
    (alerts / "2026-11-13.md").write_text(OLD_ALERT)
    # A July-style file: a table of every set-up, no per-market headings.
    (alerts / "2026-11-12.md").write_text("# Scan\n\n## Set-ups (19 rows)\n\n| NG | LONG |\n")
    return store


def test_a_market_heading_is_named_by_its_first_bracket():
    assert nf.heading_symbol("NATURAL GAS (NG) — CMR — LONG (watch-only)") == \
        ("NG", "Natural Gas")
    assert nf.heading_symbol("$ DOLLAR INDEX (DX) — Close Set Up Short")[1] == "Dollar Index"
    for not_a_market in ("Confirmed set-ups (7)", "Reversal candles (NPF entry trigger)",
                         "The day (Friday)", "Book notes (CMR)", "Verdict"):
        assert nf.heading_symbol(not_a_market) == (None, None)


def test_a_section_runs_to_the_next_heading_of_its_level_as_written():
    cmr_sec, npf_sec = nf.market_sections(OLD_ALERT, "NG")
    assert cmr_sec == "### NATURAL GAS (NG) — CMR — LONG\n\n- cmr body"
    assert npf_sec.endswith("- npf body")
    # The last market stops at the shallower heading, not at the end of the file.
    (dx,) = nf.market_sections(OLD_ALERT, "DX")
    assert "dx body" in dx and "trailing notes" not in dx
    assert nf.market_sections(OLD_ALERT, "ZW") == []


def test_markets_come_from_sidecars_and_headings_alike(history_store):
    assert dict(nf.markets(history_store)) == {
        "DX": "Dollar Index", "LBR": "Lbr", "NG": "Natural Gas", "RTY": "Rty",
        "SI": "Si", "ZW": "Zw"}


def test_history_keeps_the_four_kinds_of_day_apart(history_store):
    """Not a set-up, and a file that cannot say, must never look like each other or
    like a day that is simply missing."""
    by_date = {e.date: e for e in nf.market_history("NG", env=history_store)}
    assert list(by_date) == ["2026-11-17", "2026-11-16", "2026-11-13", "2026-11-12"]
    assert by_date["2026-11-17"].kind == nf.ABSENT          # sidecar, NG not in it
    assert by_date["2026-11-13"].kind == nf.SECTIONS
    assert len(by_date["2026-11-13"].sections) == 2
    assert by_date["2026-11-12"].kind == nf.UNSLICED and by_date["2026-11-12"].mentions == 1
    si = nf.market_history("SI", days=1, env=history_store)
    assert [e.kind for e in si] == [nf.ROWS] and len(si[0].rows) == 2   # both books


def test_the_history_page_says_what_each_day_was(history_store):
    text = _text(nf.render_history("NG", nf.market_history("NG", env=history_store),
                                    "Natural Gas"))
    assert "Natural Gas (NG)" in text
    assert "NG was not a set-up on this day." in text
    assert "no per-market sections" in text and "mentions NG 1 time;" in text
    # A sidecar day reads through the same cells as the board, verdict included.
    lbr = _text(nf.render_history("LBR", nf.market_history("LBR", 1, history_store)))
    assert "EARLY / WATCH-ONLY" in lbr and "NAHB 25 vs 29" in lbr


# ── backfilled days: numbers recomputed, verdicts only in the alert ───────────

@pytest.fixture
def backfilled_store(history_store):
    """2026-11-13 gets a backfilled sidecar: NG's row, an empty report."""
    alerts = nf.alerts_dir(history_store)
    scan = {"prices_newest_data": "2026-11-13",
            "cmr_index_file": "Official_CMR_CoT_Index_11.08.2026.xlsx",
            "watchlist": [_row("NG", confirmed=False), _row("HG", confirmed=False)]}
    (alerts / "2026-11-13.json").write_text(json.dumps({
        "scan": scan, "report": {},
        "backfill": {"computed_on": "2026-11-18",
                     "symbols_never_named_in_alert": ["HG"]}}))
    return history_store


def test_a_backfilled_day_has_numbers_but_is_not_judged(backfilled_store):
    day = nf.read_day("2026-11-13", backfilled_store)
    assert day.structured and not day.judged
    assert nf.read_day("2026-11-17", backfilled_store).judged


def test_a_backfilled_day_never_prints_a_verdict_of_its_own(backfilled_store):
    """No report came with these numbers. 'Not judged' would be false (the day was
    judged, in prose) and 'No failure' would be invented, so neither may appear."""
    text = _text(nf.render_day(nf.read_day("2026-11-13", backfilled_store)))
    assert "recomputed on 2026-11-18" in text and "the alert is the record" in text
    assert "Not judged" not in text and "Not researched" not in text
    board = _text(nf.board_table(nf.read_day("2026-11-13", backfilled_store)))
    assert "News read" not in board and "Verdict" not in board
    assert "Size fail" in text                      # the numbers are there
    assert "The alert never names HG" in text       # and so is the rebuild's own doubt
    assert "cmr body" in text                       # with the alert open beneath


def test_history_pairs_backfilled_numbers_with_the_alert_as_written(backfilled_store):
    by_date = {e.date: e for e in nf.market_history("NG", env=backfilled_store)}
    e = by_date["2026-11-13"]
    assert (e.kind, e.backfilled, len(e.rows), len(e.sections)) == (nf.ROWS, True, 1, 2)
    text = _text(nf.render_history("NG", [e]))
    assert "numbers recomputed" in text and "npf body" in text and "Not judged" not in text
    # A row with no section says so; a section with no row still shows its prose.
    hg = nf.market_day(nf.read_day("2026-11-13", backfilled_store), "HG")
    assert "no section of its own" in _text(nf.render_history("HG", [hg]))
    dx = nf.market_day(nf.read_day("2026-11-13", backfilled_store), "DX")
    assert (dx.kind, dx.rows, len(dx.sections)) == (nf.SECTIONS, [], 1)
    assert nf.market_day(nf.read_day("2026-11-13", backfilled_store), "ZW").kind == nf.ABSENT


def _page_paths():
    return [p["path"] for p in dash.page_registry.values() if p.get("path") == "/news-failure"]


def test_the_page_registers_only_with_the_flag(monkeypatch):
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    monkeypatch.delenv(local_pages.ENV, raising=False)
    page = importlib.reload(importlib.import_module("pages.analytics.news_failure"))
    assert _page_paths() == []
    monkeypatch.setenv(local_pages.ENV, "1")
    try:
        importlib.reload(page)
        assert _page_paths() == ["/news-failure"]
    finally:
        dash._callback.GLOBAL_CALLBACK_LIST[:] = registered
        monkeypatch.delenv(local_pages.ENV)
        importlib.reload(page)
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == "/news-failure"]:
            del dash.page_registry[key]


# ── the model filter ──────────────────────────────────────────────────────────
def test_a_model_filter_lists_a_market_once(store):
    """SI is held by two models, so the unfiltered board has two SI rows."""
    assert [r["symbol"] for r in nf.read_day("2026-11-17", store).rows].count("SI") == 2
    raw = nf.read_day("2026-11-17", store, book="CMR")
    assert sorted(r["symbol"] for r in raw.rows) == ["LBR", "RTY", "SI", "ZW"]
    npf = nf.read_day("2026-11-17", store, book="NPF-CS")
    assert [r["symbol"] for r in npf.rows] == ["SI"]
    assert nf.counts(npf)["rows"] == 1


def test_the_screen_uses_the_apps_model_names(store):
    """The files keep the scanner's book names; the board says Raw CLS, never CMR."""
    assert nf.model_label("CMR") == "Raw CLS"
    assert nf.model_label("NPF-CS") == "NPF CS"
    assert nf.model_label("something new") == "something new"
    board = _text(nf.board_table(nf.read_day("2026-11-17", store)))
    assert "Raw CLS" in board and "NPF CS" in board and "CMR" not in board


def test_history_under_a_model_keeps_that_models_days_only(history_store):
    si = nf.market_history("SI", days=1, env=history_store, book="NPF-CS")
    assert len(si[0].rows) == 1 and si[0].rows[0]["book"] == "NPF-CS"
    assert [b for b, _ in si[0].models] == ["CMR", "NPF-CS"]     # the filter hides no model
    # RTY is a Raw CLS set-up only: under NPF CS it is absent, and the card says which.
    rty = nf.market_history("RTY", days=1, env=history_store, book="NPF-CS")
    assert rty[0].kind == nf.ABSENT
    assert "not a set-up under NPF CS" in _text(
        nf.render_history("RTY", rty, "Russell", book="NPF-CS"))
    # A markdown day: the two NG sections are one per model, split by their headings.
    ng = {e.date: e for e in nf.market_history("NG", env=history_store, book="CMR")}
    assert len(ng["2026-11-13"].sections) == 1
    assert ng["2026-11-13"].sections[0].startswith("### NATURAL GAS (NG) — CMR")


def test_a_heading_that_names_no_model_survives_the_filter():
    secs = ["## Wheat (ZW) — CMR — LONG\n\na", "## Wheat (ZW) — NPF-CS — LONG\n\nb",
            "## Wheat (ZW) — LONG\n\nc"]
    assert nf.sections_for_book(secs, "NPF-CS") == secs[1:]
    assert nf.sections_for_book(secs, None) == secs
    assert nf.heading_books("NG — close to set-up (CMR: near; NPF-C-only: near)") == \
        {"CMR", "NPF-C-only"}
    assert nf.heading_books("Natural Gas (NG) — NPF-C-only LONG") == {"NPF-C-only"}


def test_a_market_two_models_hold_is_one_row_naming_both(store):
    """Unfiltered, SI is one board row with two evidence folds, not two rows."""
    day = nf.read_day("2026-11-17", store)
    assert sorted(nf.lead(g)["symbol"] for g in day.groups) == ["LBR", "RTY", "SI", "ZW"]
    assert nf.counts(day)["rows"] == 4
    board = _text(nf.board_table(day))
    assert board.count("SI · LONG") == 1
    assert "Raw CLS · NPF CS" in board
    assert "Case for and against · SI Raw CLS" in board
    assert "Case for and against · SI NPF CS" in board
    # Filtered to one model the row still names the other.
    assert "Raw CLS · NPF CS" in _text(nf.board_table(
        nf.read_day("2026-11-17", store, book="CMR")))


def test_a_model_that_only_has_it_close_is_marked():
    assert nf.models_line([("CMR", True), ("NPF-CS", False)]) == "Raw CLS · NPF CS (close)"
    assert nf.models_line([("CMR", False), ("NPF-CS", False)]) == "Raw CLS · NPF CS"
    crowded_second = [{"symbol": "SI", "book": "CMR", "confirmed": False},
                      {"symbol": "SI", "book": "NPF-CS", "confirmed": True}]
    assert nf.lead(crowded_second)["book"] == "NPF-CS"


def test_nothing_the_page_builds_says_cmr(store):
    """The alert text is shown as written and may; the page's own words may not."""
    day = nf.read_day("2026-11-17", store)
    day.markdown = ""
    assert "CMR" not in _text(nf.render_day(day)) and "CMR" not in nf.DISCLAIMER


def test_alert_text_gets_the_apps_model_name_and_nothing_else_moves():
    md = ("# CMR News-Failure Scan — 2026-08-25\n\n"
          "Index: Official_CMR_CoT_Index_08.23.2026.xlsx\n\n"
          "```\nMKT   BOOK DIR\nNG    CMR  LONG\n```\n\n"
          "## NATURAL GAS (NG) — CMR — LONG\n\n| NG | CMR | LONG |\n\n"
          "Based on the CMR methodology and the CMR COT Index.\n")
    out = nf.relabel(md)
    assert out.startswith("# News-Failure Scan — 2026-08-25")
    assert "NG    Raw  LONG" in out                       # fenced: same width
    assert "## NATURAL GAS (NG) — Raw CLS — LONG" in out and "| NG | Raw CLS | LONG |" in out
    # The index and its method are not the model, and a file name is a file name.
    assert "Official_CMR_CoT_Index_08.23.2026.xlsx" in out
    assert "the CMR methodology and the CMR COT Index" in out
    assert nf.relabel("") == "" and nf.relabel("no book here") == "no book here"


def test_slicing_reads_the_scanners_names_before_the_relabel(history_store):
    """The model filter keys on the heading as written; the screen shows it relabelled."""
    ng = nf.market_history("NG", env=history_store, book="CMR")
    text = _text(nf.render_history("NG", ng, "Natural Gas", book="CMR"))
    assert "NATURAL GAS (NG) — Raw CLS — LONG" in text
