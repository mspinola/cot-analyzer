"""The CMR scan page: local-only gate, reading the alert store, and the rules the
scanner's own board keeps (every set-up once, an unjudged row never reads as cleared)."""
import importlib
import json

import dash
import pytest

import components.cmr_scan as cmr
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
    return {cmr.ENV: str(tmp_path)}


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
    assert cmr.available_dates(store) == ["2026-11-17", "2026-11-16"]


def test_a_missing_store_has_no_dates(tmp_path):
    assert cmr.available_dates({cmr.ENV: str(tmp_path / "nope")}) == []


def test_a_day_with_a_sidecar_is_structured_and_one_without_is_not(store):
    assert cmr.read_day("2026-11-17", store).structured
    old = cmr.read_day("2026-11-16", store)
    assert not old.structured and "old day" in old.markdown


def test_counts_come_from_the_scan(store):
    c = cmr.counts(cmr.read_day("2026-11-17", store))
    assert c == {"rows": 5, "crowded": 4, "obvious": 1, "eligible": 1}


def test_every_set_up_appears_exactly_once_on_the_board(store):
    """The scanner's rule 1: a market must not be able to fall out of the table."""
    day = cmr.read_day("2026-11-17", store)
    rows = [r for r in cmr.board_rows(day)
            if "Case for and against" in _text(r)]
    assert len(rows) == len(day.rows)


def test_an_unjudged_row_never_reads_as_cleared(store):
    """ZW has no verdict from the routine: it must say so, not 'No failure'."""
    day = cmr.read_day("2026-11-17", store)
    zw = next(r for r in day.rows if r["symbol"] == "ZW")
    assert cmr.verdict_of(zw, day.report)[0] == "Not judged"


def test_a_watch_item_gets_its_own_card_with_the_case_against(store):
    day = cmr.read_day("2026-11-17", store)
    cards = cmr.highlight_cards(day)
    assert len(cards) == 1
    text = _text(cards[0])
    assert "Lbr" in text and "LOW" in text and "no peer" in text


def test_no_peers_is_unknown_not_a_pass(store):
    day = cmr.read_day("2026-11-17", store)
    lbr = next(r for r in day.rows if r["symbol"] == "LBR")
    assert cmr.gates(lbr) == (True, None, True)
    assert "Peers n/a" in _text(cmr.gate_strip(lbr))


def test_an_index_dated_after_the_scan_day_is_flagged(store):
    day = cmr.read_day("2026-11-17", store)
    assert cmr.index_flags(day) == []
    day.scan["cmr_index_file"] = "Official_CMR_CoT_Index_11.22.2026.xlsx"
    assert [k for k, _ in cmr.index_flags(day)] == ["Index date"]


def test_an_archive_day_renders_its_markdown(store):
    text = _text(cmr.render_day(cmr.read_day("2026-11-16", store)))
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
    alerts = cmr.alerts_dir(store)
    (alerts / "2026-11-13.md").write_text(OLD_ALERT)
    # A July-style file: a table of every set-up, no per-market headings.
    (alerts / "2026-11-12.md").write_text("# Scan\n\n## Set-ups (19 rows)\n\n| NG | LONG |\n")
    return store


def test_a_market_heading_is_named_by_its_first_bracket():
    assert cmr.heading_symbol("NATURAL GAS (NG) — CMR — LONG (watch-only)") == \
        ("NG", "Natural Gas")
    assert cmr.heading_symbol("$ DOLLAR INDEX (DX) — Close Set Up Short")[1] == "Dollar Index"
    for not_a_market in ("Confirmed set-ups (7)", "Reversal candles (NPF entry trigger)",
                         "The day (Friday)", "Book notes (CMR)", "Verdict"):
        assert cmr.heading_symbol(not_a_market) == (None, None)


def test_a_section_runs_to_the_next_heading_of_its_level_as_written():
    cmr_sec, npf_sec = cmr.market_sections(OLD_ALERT, "NG")
    assert cmr_sec == "### NATURAL GAS (NG) — CMR — LONG\n\n- cmr body"
    assert npf_sec.endswith("- npf body")
    # The last market stops at the shallower heading, not at the end of the file.
    (dx,) = cmr.market_sections(OLD_ALERT, "DX")
    assert "dx body" in dx and "trailing notes" not in dx
    assert cmr.market_sections(OLD_ALERT, "ZW") == []


def test_markets_come_from_sidecars_and_headings_alike(history_store):
    assert dict(cmr.markets(history_store)) == {
        "DX": "Dollar Index", "LBR": "Lbr", "NG": "Natural Gas", "RTY": "Rty",
        "SI": "Si", "ZW": "Zw"}


def test_history_keeps_the_four_kinds_of_day_apart(history_store):
    """Not a set-up, and a file that cannot say, must never look like each other or
    like a day that is simply missing."""
    by_date = {e.date: e for e in cmr.market_history("NG", env=history_store)}
    assert list(by_date) == ["2026-11-17", "2026-11-16", "2026-11-13", "2026-11-12"]
    assert by_date["2026-11-17"].kind == cmr.ABSENT          # sidecar, NG not in it
    assert by_date["2026-11-13"].kind == cmr.SECTIONS
    assert len(by_date["2026-11-13"].sections) == 2
    assert by_date["2026-11-12"].kind == cmr.UNSLICED and by_date["2026-11-12"].mentions == 1
    si = cmr.market_history("SI", days=1, env=history_store)
    assert [e.kind for e in si] == [cmr.ROWS] and len(si[0].rows) == 2   # both books


def test_the_history_page_says_what_each_day_was(history_store):
    text = _text(cmr.render_history("NG", cmr.market_history("NG", env=history_store),
                                    "Natural Gas"))
    assert "Natural Gas (NG)" in text
    assert "NG was not a set-up on this day." in text
    assert "no per-market sections" in text and "mentions NG 1 time;" in text
    # A sidecar day reads through the same cells as the board, verdict included.
    lbr = _text(cmr.render_history("LBR", cmr.market_history("LBR", 1, history_store)))
    assert "EARLY / WATCH-ONLY" in lbr and "NAHB 25 vs 29" in lbr


def _cmr_paths():
    return [p["path"] for p in dash.page_registry.values() if p.get("path") == "/cmr"]


def test_the_page_registers_only_with_the_flag(monkeypatch):
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    monkeypatch.delenv(local_pages.ENV, raising=False)
    page = importlib.reload(importlib.import_module("pages.analytics.cmr_scan"))
    assert _cmr_paths() == []
    monkeypatch.setenv(local_pages.ENV, "1")
    try:
        importlib.reload(page)
        assert _cmr_paths() == ["/cmr"]
    finally:
        dash._callback.GLOBAL_CALLBACK_LIST[:] = registered
        monkeypatch.delenv(local_pages.ENV)
        importlib.reload(page)
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == "/cmr"]:
            del dash.page_registry[key]
