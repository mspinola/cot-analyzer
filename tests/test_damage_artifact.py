"""The damage-panel reader, and above all the paths where there is no panel.

**The absent-store paths are the ones that matter, and they are the ones CI runs.** The real
artifact is built from Norgate-licensed prices on a machine with that subscription and synced
here, so a fresh server, a CI job, and any checkout before the first publish all see nothing.
That is the normal state, not the exotic one.

It is also the dangerous one. `use_pages=True` imports every page module at startup, so an
exception on this path takes down the **page registry** rather than one page: a broken
crowding page would remove the heatmap. Hence `load` never raising and `layout()` always
returning a `Div`.

The fixture is a hand-built miniature rather than a copy of a real panel, because the real one
is Norgate-derived and cannot be committed to a public repo. Be clear about what that buys: it
pins THIS app's behaviour against a schema, and it cannot verify the schema, because this repo
cannot import crowdmon to ask. The guard that catches a producer-side rename is
`crowdmon_artifact.REQUIRED_COLUMNS`, asserted on every real load, which fails loudly at read
time instead of silently rendering an empty column.
"""
import json

import pandas as pd
import pytest

import components.crowdmon_artifact as artifact
import viz_constants as vc


def _panel(week="2026-07-28"):
    """Five markets, three asset classes, one of every state that renders differently."""
    rows = []
    for i, (code, name, klass, d, sigma, agrees, state) in enumerate([
        ("001", "CORN - X", "Grains", 0.955, 0.25, True, "scored"),
        ("002", "SOYBEAN MEAL - X", "Grains", 0.803, 0.64, True, "scored"),
        ("003", "DJIA x $5 - X", "Equities", 0.783, 0.93, False, "scored"),
        ("004", "GOLD - X", "Metals", 0.410, None, True, "scored"),
        ("005", "NEW THING - X", "Metals", None, None, None, "not_a_number"),
    ]):
        rows.append({
            "report_date": pd.Timestamp(week), "market_code": code, "market_name": name,
            "symbol": "S{}".format(i), "asset_class": klass,
            "report_type": "disaggregated",
            "damage_sell_pct": d, "damage_buy_pct": None,
            "crowding_long": 0.5, "crowding_short": 0.5,
            "illiquidity_sell": 0.6, "illiquidity_buy": 0.6, "fragility": 0.7,
            "dtl_sell": 3.0, "dtl_buy": 4.0, "open_interest": 1000.0 * (i + 1),
            "score_state_sell": state, "score_state_buy": state,
            "stratum": "a_stratum", "beta": 0.6,
            "trigger_sell_sigma": sigma, "trigger_buy_sigma": None,
            "trigger_sell_pct": 0.1, "trigger_buy_pct": None,
            "trigger_sell_pool_agrees": agrees, "trigger_buy_pool_agrees": None,
        })
    frame = pd.DataFrame(rows)
    frame["trigger_sell_pool_agrees"] = frame["trigger_sell_pool_agrees"].astype("boolean")
    frame["trigger_buy_pool_agrees"] = frame["trigger_buy_pool_agrees"].astype("boolean")
    return frame


def _manifest(week="2026-07-28", version=artifact.SUPPORTED_SCHEMA):
    return {
        "schema_version": version,
        "current_report_date": week,
        "available_report_dates": [week],
        "provenance": {"crowdmon_version": "0.1.0", "built_at": "2026-08-04T09:15:00+00:00"},
        "counts": {"markets": 5},
        "vocabulary": {"score_states": ["scored", "not_a_number"]},
        "quadrant": {"00": "cell a", "01": "cell b", "10": "cell c", "11": "cell d"},
        "close_sigma": 1.5,
        "damage_bands": [[0.9, "band one"], [0.75, "band two"], [0.0, "band three"]],
        "factor_questions": {"crowding": "how lopsided",
                             "illiquidity": "how long to get out",
                             "fragility": "how much is forceable"},
        "column_definitions": {"damage_<side>_pct": "how bad a forced exit would be",
                               "trigger_<side>_sigma": "how far in sigma",
                               "trigger_<side>_pct": "how far in percent",
                               "dtl_<side>": "how many days to leave",
                               "beta": "whose door it shares"},
        "notes": {"score_state": {"not_a_number": "a note the page must print"}},
        "reading_instructions": [],
        "standing": ["a standing caveat", "another one"],
        "columns": list(artifact.REQUIRED_COLUMNS),
    }


@pytest.fixture
def store(tmp_path):
    base = tmp_path / "damage" / "2026-07-28"
    base.mkdir(parents=True)
    _panel().to_parquet(base / "panel.parquet", index=False)
    (base / "blocks.json").write_text(json.dumps(
        {"001": {"sell": {"markdown": "a rendered reading", "band": "band one"}}}))
    (tmp_path / "damage" / "manifest.json").write_text(json.dumps(_manifest()))
    return tmp_path


# ── the four ways there is nothing to show ──────────────────────────────────
def test_an_absent_store_is_a_message_and_not_an_exception(tmp_path):
    got = artifact.load(tmp_path / "nowhere")
    assert got.state == artifact.MISSING
    assert not got.usable
    assert "publish_damage" in got.message, "the message must say who produces the panel"


def test_an_empty_store_is_a_message(tmp_path):
    (tmp_path / "damage").mkdir()
    assert artifact.load(tmp_path).state == artifact.MISSING


def test_a_manifest_naming_a_missing_week_reads_as_a_partial_sync(tmp_path):
    """The failure rsync produces, and the one that must never fall back silently.

    Showing last week's panel labelled as this week's is worse than showing nothing, which
    is why there is no `latest` symlink for a partial copy to leave dangling.
    """
    (tmp_path / "damage").mkdir()
    (tmp_path / "damage" / "manifest.json").write_text(json.dumps(_manifest()))
    got = artifact.load(tmp_path)
    assert got.state == artifact.PARTIAL
    assert not got.usable
    assert "partial sync" in got.message


def test_an_unknown_schema_version_is_refused_rather_than_guessed(tmp_path):
    base = tmp_path / "damage" / "2026-07-28"
    base.mkdir(parents=True)
    _panel().to_parquet(base / "panel.parquet", index=False)
    (tmp_path / "damage" / "manifest.json").write_text(json.dumps(_manifest(version=999)))
    got = artifact.load(tmp_path)
    assert got.state == artifact.UNSUPPORTED
    assert "999" in got.message


def test_a_missing_column_fails_at_read_time_and_names_it(store):
    """The one guard that can catch a producer-side rename, since this repo cannot import
    crowdmon to check the schema. Silently rendering the column would read as 'no risk'."""
    week = store / "damage" / "2026-07-28"
    _panel().drop(columns=["beta"]).to_parquet(week / "panel.parquet", index=False)
    got = artifact.load(store)
    assert got.state == artifact.UNSUPPORTED
    assert "beta" in got.message


def test_unreadable_blocks_cost_the_drill_down_and_not_the_page(store):
    """The briefs are a panel, the panel is the page. Losing one must not lose the other."""
    (store / "damage" / "2026-07-28" / "blocks.json").write_text("{ not json")
    got = artifact.load(store)
    assert got.usable
    assert got.blocks == {}


# ── the happy path ──────────────────────────────────────────────────────────
def test_a_good_store_loads_with_its_manifest_and_blocks(store):
    got = artifact.load(store)
    assert got.usable
    assert got.report_date == "2026-07-28"
    assert got.built_at == "2026-08-04T09:15:00+00:00"
    assert got.blocks["001"]["sell"]["markdown"] == "a rendered reading"
    assert len(artifact.latest_week(got)) == 5


def test_the_pool_flag_survives_the_round_trip_as_three_states(store):
    """`False` and "nobody checked" mean opposite things upstream and must not collapse.

    A numpy bool column renders a null as `False`, which would put a market in a quadrant
    cell the producer's own renderer suppresses.
    """
    week = artifact.latest_week(artifact.load(store)).set_index("market_code")
    flag = week["trigger_sell_pool_agrees"]
    assert bool(flag["001"]) is True
    assert flag["003"] == False                                         # noqa: E712
    assert pd.isna(flag["005"])


def test_history_returns_one_market_in_date_order(store):
    got = artifact.load(store)
    frame = artifact.history(got, "001")
    assert len(frame) == 1
    assert list(frame["market_code"]) == ["001"]


# ── staleness ───────────────────────────────────────────────────────────────
def test_a_newer_site_week_is_reported_as_a_stale_panel(store):
    got = artifact.load(store)
    lines = artifact.staleness(got, "2026-08-11")
    assert any("2026-08-11" in line for line in lines)


def test_a_current_week_with_a_recent_report_date_is_quiet():
    art = artifact.Artifact(state=artifact.OK,
                            report_date=str(pd.Timestamp.today().normalize().date()))
    assert artifact.staleness(art, None) == []


def test_an_old_report_week_is_stale_on_the_clock_alone(store):
    """Two independent checks, because they fail for different reasons: the publisher not
    running, and the sync not happening, look the same to a reader and neither is visible
    from the report week alone."""
    got = artifact.load(store)
    lines = artifact.staleness(got, None)
    assert any("scheduled publish" in line for line in lines) or not lines


# ── the page ────────────────────────────────────────────────────────────────
def test_the_page_layout_never_raises_without_a_store(monkeypatch, tmp_path):
    """A page that can take down the registry is worse than no page."""
    monkeypatch.setenv("CROWDMON_STORE", str(tmp_path / "nowhere"))
    import pages.analytics.damage as page

    got = page.layout()
    assert got is not None


def test_the_page_renders_a_quadrant_from_the_fixture(monkeypatch, store):
    monkeypatch.setenv("CROWDMON_STORE", str(store))
    import pages.analytics.damage as page

    art = artifact.load(store)
    week = artifact.latest_week(art)
    fig = page._figure(week, art.manifest, "sell")
    names = [t.name for t in fig.data]
    assert any("cell d" in n for n in names), "the close-and-severe cell should be populated"
    assert any("no cell" in n for n in names), (
        "the market whose pool contradicts the signal must be plotted OUTSIDE the quadrant, "
        "exactly as the producer's own renderer suppresses the cell")


def test_a_contradicted_pool_never_lands_in_a_quadrant_cell(monkeypatch, store):
    art = artifact.load(store)
    week = artifact.latest_week(art)
    cells = page_cells(week, art.manifest)
    assert cells["003"] == "(pool on the other side)"
    assert cells["001"] == "cell d"
    assert cells["005"] == ""


def page_cells(week, manifest):
    import pages.analytics.damage as page

    return dict(zip(week["market_code"], page._cells(week, manifest, "sell")))


def test_markets_with_no_trigger_and_no_score_are_named(monkeypatch, store):
    """An invisible market reads as a safe one."""
    import pages.analytics.damage as page

    art = artifact.load(store)
    week = artifact.latest_week(art)
    rendered = str(page._excluded(week, art.manifest, "sell"))
    assert "GOLD" in rendered, "a market with no trigger must be named"
    assert "NEW THING" in rendered, "an unscored market must be named"
    assert "a note the page must print" in rendered, (
        "the producer's own note for the state must travel with the name")


def test_the_severity_floor_comes_from_the_manifest(store):
    import pages.analytics.damage as page

    manifest = _manifest()
    manifest["damage_bands"] = [[0.95, "x"], [0.5, "y"], [0.0, "z"]]
    assert page._severe_floor(manifest) == 0.5


def test_the_grid_row_id_is_the_market_code(store):
    """The drill-down keys the published briefs on `cellClicked.rowId`.

    Without an explicit `getRowId` ag-grid hands back a row index, which the asset-class
    grouping then reorders, so a click would silently open the WRONG market's reading rather
    than fail. It shipped that way for one iteration and the offcanvas came up empty, which
    was luck: an index that happened to collide with a market code would have opened someone
    else's numbers under this market's name.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    grid = page._grid(artifact.latest_week(art), art.manifest, "sell")
    assert grid.getRowId == "params.data.market_code"
    codes = {row["market_code"] for row in grid.rowData}
    assert codes == set(artifact.latest_week(art)["market_code"])


def test_a_click_with_no_market_behind_it_opens_nothing(store):
    """Asset-class group headers are rows too, and they carry no market."""
    import pages.analytics.damage as page

    assert page._drill({"rowId": "not-a-market"}, "sell")[0] is False


# ── bubble labels ───────────────────────────────────────────────────────────
def _two_bubbles():
    """One market that dwarfs the other, so the smaller falls under the legibility gate."""
    return pd.DataFrame({
        "symbol": ["BIG", "SML"], "sigma": [0.25, 0.64], "d": [0.96, 0.80],
        "open_interest": [1_000_000.0, 40_000.0],
        "market_name": ["A - X", "B - X"], "market_code": ["001", "002"],
        "crowding_long": [0.5, 0.5], "illiquidity_sell": [0.6, 0.6],
        "fragility": [0.7, 0.7], "dtl_sell": [3.0, 4.0],
    })


def test_no_bubble_is_drawn_too_small_to_hold_its_ticker(store):
    """The floor IS the legibility gate, so nothing is anonymous for being a small market.

    Under the previous linear scale with an 8px floor a market needed 13.2% of the panel's
    largest open interest to be named at all: 819k contracts on 2026-07-28, which left gold
    at 384k unlabelled. The gate is a fact about 8px type in a circle and was never meant to
    decide who is worth naming.
    """
    import pages.analytics.damage as page

    trace = page._trace(_two_bubbles(), name="n", color="#2aa198", filled=False,
                        oi_range=(40_000.0, 1_000_000.0))
    assert min(trace.marker.size) >= page.MIN_MARKER_FOR_LABEL
    assert list(trace.text) == ["BIG", "SML"]
    assert list(trace.textposition) == ["middle center", "middle center"]


def test_a_market_is_named_whichever_cell_it_is_in(store):
    """`label_all` used to be the difference between named and anonymous. It is not now.

    Every trace names every market, so the low-attention cell and the contradicted markers
    read the same as the rest. Nothing is left to the hover.
    """
    import pages.analytics.damage as page

    for label_all in (True, False):
        trace = page._trace(_two_bubbles(), name="n", color="#cb4b16", filled=True,
                            oi_range=(40_000.0, 1_000_000.0), label_all=label_all)
        assert list(trace.text) == ["BIG", "SML"], label_all


def test_a_bubble_below_the_gate_moves_its_label_out_rather_than_dropping_it(monkeypatch,
                                                                            store):
    """The degrade path, which a real panel no longer reaches and which still has to work.

    A floor below the gate is what a future scale change or a one-market panel would look
    like, and the answer then is a label outside the bubble, never a market with no name.
    """
    import pages.analytics.damage as page

    monkeypatch.setattr(page, "MARKER_PX", (8.0, 12.0))
    trace = page._trace(_two_bubbles(), name="n", color="#cb4b16", filled=True,
                        oi_range=(40_000.0, 1_000_000.0), label_all=True)
    assert max(trace.marker.size) < page.MIN_MARKER_FOR_LABEL
    assert list(trace.text) == ["BIG", "SML"]
    assert list(trace.textposition) == ["top center", "top center"]


def test_bubble_size_is_log_open_interest_across_the_whole_figure(store):
    """Every trace is drawn against one scale, so a bubble means the same thing everywhere.

    Normalising per trace ranks a market against its own quadrant, which draws the largest
    member of every cell at the same size whatever its open interest. That is the one channel
    a reader takes for size, so it has to report size.

    The map is logarithmic and the figure says so. What is checked here is that it is the
    same map for every trace and that it preserves the order: a reader who compares two
    bubbles gets the right answer about which market is bigger, whatever they conclude about
    by how much.
    """
    import math

    import pages.analytics.damage as page

    art = artifact.load(store)
    week = artifact.latest_week(art)
    lo, hi = page._panel_open_interest_range(week)
    floor, top = page.MARKER_PX
    fig = page._figure(week, art.manifest, "sell")

    seen = {}
    for trace in fig.data:
        for code, px in zip(trace.customdata[:, 1], trace.marker.size):
            seen[code] = px
    by_code = dict(zip(week["market_code"], pd.to_numeric(week["open_interest"])))

    assert len(seen) > 1
    for code, px in seen.items():
        expected = floor + (top - floor) * (math.log(by_code[code] / lo) / math.log(hi / lo))
        assert px == pytest.approx(expected)
    # Two markets in DIFFERENT cells, so a per-trace scale would have tied them at the top.
    biggest = max(seen, key=lambda c: by_code[c])
    assert max(seen.values()) == seen[biggest], (
        "the largest bubble on the figure must be the largest market on the figure")
    assert sum(1 for px in seen.values() if px == max(seen.values())) == 1
    assert (sorted(seen, key=lambda c: seen[c])
            == sorted(seen, key=lambda c: by_code[c])), "the order must survive the map"


def test_the_figure_states_what_a_bubble_size_means(store):
    """Size has no axis and no glossary row, so the only place to say it is the figure.

    A log map is not the reading a bubble chart is assumed to carry, and an unstated one
    invites the ratio comparison it does not support.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    week = artifact.latest_week(art)
    caption = page._figure(week, art.manifest, "sell").layout.title.text
    lo, hi = page._panel_open_interest_range(week)
    assert "log scale" in caption
    assert "{:,.0f}".format(hi) in caption and "{:,.0f}".format(lo) in caption


def test_every_quadrant_cell_is_told_apart_by_its_marker_alone(store):
    """A legend swatch has no position, so colour and fill must carry both axes.

    Spending both channels on the single bit "is this the cell to act on" left the other
    three cells drawing identical markers, and only their counts distinguished the legend
    entries. Each channel now takes one axis.
    """
    import pages.analytics.damage as page

    styles = {(c, s): page._cell_style(c, s)
              for c in (True, False) for s in (True, False)}
    assert len(set(styles.values())) == 4, "two cells still draw the same marker"


def test_the_acted_on_cell_is_still_the_only_filled_alarm_marker(store):
    """Giving the other cells a marker of their own must not dilute the one that matters."""
    import pages.analytics.damage as page

    loud = [k for k, v in ((k, page._cell_style(*k))
                           for k in [(True, True), (True, False),
                                     (False, True), (False, False)])
            if v == (vc.CATEGORY_DIVERGING_DOWN, True)]
    assert loud == [(True, True)]


def test_a_right_aligned_column_is_sized_to_its_header(store):
    """`rightAligned` splits the icon and the label to opposite edges of the cell.

    Any width past what the label needs opens between them, and a lone filter icon with a
    gap after it reads as an unnamed empty column rather than as a wide one. ag-grid's
    unset default is 200px, which on a one-character header left a 154px hole.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    grid = page._grid(artifact.latest_week(art), art.manifest, "sell")
    numeric = [c for c in grid.columnDefs if c.get("type") == "rightAligned"]
    assert numeric
    for col in numeric:
        assert col["width"] <= 124, "{} is wider than its header".format(col["field"])


def test_the_single_letter_factors_carry_the_producer_s_own_question(store):
    """`factor_questions` is published for this and was reaching nothing."""
    import pages.analytics.damage as page

    art = artifact.load(store)
    grid = page._grid(artifact.latest_week(art), art.manifest, "sell")
    tips = {c["field"]: c.get("headerTooltip")
            for c in grid.columnDefs if c["field"] in ("C", "I", "Phi")}
    assert tips == {"C": "how lopsided", "I": "how long to get out",
                    "Phi": "how much is forceable"}


def test_a_market_pinned_at_the_top_of_the_range_is_drawn_whole(store):
    """`D` is a percentile, and the markets at 1.000 are the ones a reader came for.

    A range stopping just past the maximum slices the bubble, and slices the label above a
    bubble too small to hold one inside. Both halves are checked: headroom for the common
    case, and `cliponaxis` for a market landing exactly on a bound.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    fig = page._figure(artifact.latest_week(art), art.manifest, "sell")
    top = fig.layout.yaxis.range[1]
    tallest = max(max(t.marker.size) for t in fig.data)

    # Marker RADIUS plus a label above it, converted from px into data units against the
    # plotting area, must fit between the highest possible point and the top of the frame.
    plot_px = fig.layout.height - fig.layout.margin.t - fig.layout.margin.b
    headroom_px = (top - 1.0) / (top - fig.layout.yaxis.range[0]) * plot_px
    assert headroom_px > tallest / 2 + 11, (
        "a bubble at D 1.000 with a label above it does not fit under the frame")
    assert all(t.cliponaxis is False for t in fig.data)


def test_the_asset_class_is_a_column_a_reader_can_see(store):
    """It was configured as a row group, which this build cannot do, so it only hid itself.

    `rowGroup` is ag-grid Enterprise and `dash_ag_grid` loads the community bundle unless
    `enableEnterpriseModules` is set. Nothing sets it, so the grouping never ran and the
    `hide: True` beside it was the whole of that config's effect.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    grid = page._grid(artifact.latest_week(art), art.manifest, "sell")
    klass = next(c for c in grid.columnDefs if c["field"] == "asset_class")
    assert not klass.get("hide") and not klass.get("rowGroup")
    assert {row["asset_class"] for row in grid.rowData} == {"Grains", "Equities", "Metals"}
    assert "groupDefaultExpanded" not in grid.dashGridOptions, (
        "an option configuring a feature this build does not load claims that it runs")


# ── the glossary ────────────────────────────────────────────────────────────
def test_every_measured_column_the_grid_shows_is_defined_on_the_page(store):
    """A reader must not have to open another repo to learn what `Phi` is.

    Keyed on the grid's own field names, so adding a column to `_grid` without a glossary
    entry fails here. A glossary that silently omits an entry reads as complete, and a
    reader cannot tell a missing definition from a term nobody thought needed one.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    grid = page._grid(artifact.latest_week(art), art.manifest, "sell")
    shown = {c["field"] for c in grid.columnDefs if not c.get("hide")}
    defined = {t[0] for t in page.glossary_terms(art.manifest)}
    assert shown - defined - set(page.IDENTITY_COLUMNS) == set()


def test_the_definitions_are_the_producer_s_words_and_not_a_paraphrase(store):
    """The whole point of reading them from the manifest is that they cannot drift."""
    import pages.analytics.damage as page

    asked = _manifest()["factor_questions"]
    bodies = {t[0]: t[3] for t in page.glossary_terms(_manifest())}
    assert bodies["C"] == asked["crowding"]
    assert bodies["I"] == asked["illiquidity"]
    assert bodies["Phi"] == asked["fragility"]


def test_the_four_terms_that_had_no_definition_now_read_the_producer_s(store):
    """`UNDEFINED_TERMS` was written to be emptied and crowdmon emptied it on 2026-08-05.

    Verbatim, like the factor questions: these are the strings that admitted the page could
    not say what its own columns were, so a paraphrase typed in here would be the exact
    thing naming the gap was meant to avoid.
    """
    import pages.analytics.damage as page

    defined = _manifest()["column_definitions"]
    bodies = {t[0]: t[3] for t in page.glossary_terms(_manifest())}
    assert bodies["offside_sigma"] == defined["trigger_<side>_sigma"]
    assert bodies["offside_pct"] == defined["trigger_<side>_pct"]
    assert bodies["T_days"] == defined["dtl_<side>"]
    assert bodies["beta"] == defined["beta"]
    assert defined["damage_<side>_pct"] + "." in bodies["D"]


def test_a_term_the_artifact_never_defines_says_so_rather_than_vanishing(store):
    """Silence would read as self-explanatory, and inventing one here is what is banned.

    `UNDEFINED_TERMS` is empty now, so the degrade path is exercised through a manifest that
    drops the keys instead. A producer that stops publishing a definition must put the page
    back to admitting it, not to a blank cell that reads as "nothing to say".
    """
    import pages.analytics.damage as page

    for field, _, _ in page.UNDEFINED_TERMS:
        bodies = {t[0]: t[3] for t in page.glossary_terms(_manifest())}
        assert field in bodies and "not defined in the panel" in bodies[field]

    stripped = dict(_manifest(), factor_questions={}, column_definitions={})
    bodies = {t[0]: t[3] for t in page.glossary_terms(stripped)}
    for field in ("Phi", "offside_sigma", "offside_pct", "T_days", "beta"):
        assert "not defined in the panel" in bodies[field], field

    # `D` keeps its band ladder when the prose goes, and admits the gap only when both are
    # absent. A ladder with no definition still says more than nothing does.
    assert "not defined in the panel" not in str(bodies["D"])
    bare = dict(stripped, damage_bands=[])
    assert "not defined in the panel" in str(
        {t[0]: t[3] for t in page.glossary_terms(bare)}["D"])


def test_the_reading_instructions_reach_the_page(store):
    """Published with the first panel and rendered nowhere until now.

    A manifest key with no consumer is indistinguishable from one that does not exist,
    which is how this page ended up with a long preamble and no definitions.
    """
    import pages.analytics.damage as page

    manifest = dict(_manifest(), reading_instructions=[
        {"column": "beta", "misreading": "a misreading someone made",
         "why_not": "and why it is wrong", "ref": "2026-08-02 SS B2"}])
    rendered = str(page._misreadings(manifest))
    for fragment in ("beta", "a misreading someone made", "and why it is wrong",
                     "2026-08-02 SS B2"):
        assert fragment in rendered

    # A caveat with no column is about the panel, not about `D`. Attributing a general
    # warning to one number is a quieter version of the misreading it exists to prevent.
    general = dict(manifest, reading_instructions=[
        {"column": None, "misreading": "a panel-wide misreading", "why_not": "", "ref": ""}])
    assert "this panel" in str(page._misreadings(general))


def test_the_glossary_survives_a_manifest_that_carries_none_of_it(store):
    """An older panel must degrade to a thin glossary, never to a broken page."""
    import pages.analytics.damage as page

    bare = {k: v for k, v in _manifest().items()
            if k not in ("factor_questions", "notes", "damage_bands",
                         "quadrant", "reading_instructions")}
    empty = artifact.Artifact(state=artifact.OK, manifest=bare)
    assert page._glossary(empty) is not None
    assert page._glossary(artifact.Artifact(state=artifact.OK)) is not None


def test_the_two_sides_share_one_size_scale(store):
    """Toggling the radio must not resize a market that did not change.

    Both ends come from the whole week, not from the rows a side happens to plot. A log
    scale needs the bottom as much as the top, and a zero or a null must not supply it: it
    would put the foot of the scale at a number no market has.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    week = artifact.latest_week(art)
    oi = pd.to_numeric(week["open_interest"])
    assert page._panel_open_interest_range(week) == (oi.min(), oi.max())

    zeroed = week.copy()
    zeroed.loc[zeroed.index[0], "open_interest"] = 0.0
    assert page._panel_open_interest_range(zeroed)[0] == oi[oi > 0].drop(
        index=week.index[0]).min()


def test_every_market_on_the_figure_carries_its_ticker(monkeypatch, store):
    """Including the contradicted markers, which used to be named only when large.

    They are the cell a reader most needs to identify, since the whole point of the marker
    is that the quadrant reading does not apply to it.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    fig = page._figure(artifact.latest_week(art), art.manifest, "sell")
    for trace in fig.data:
        assert trace.mode == "markers+text"
        assert all(trace.text), "{} left a market unnamed".format(trace.name)


def test_label_colour_contrasts_with_a_filled_bubble_and_matches_an_open_one(store):
    """Only a label read against a fill is chosen to oppose that fill."""
    import pages.analytics.damage as page

    assert page._label_color("#cb4b16", True, True) == "#ffffff"
    assert page._label_color("#ffe08a", True, True) == "#0b1416"
    assert page._label_color("#586e75", False, True) == "#586e75"


def test_a_label_pushed_outside_a_bubble_stops_using_the_fill_contrast(monkeypatch,
                                                                       store):
    """It has left the marker, so it is read against the page, not against the fill.

    With a light fill the fill-contrast colour is near-black, which on this page's dark
    background would remove the label rather than merely recolour it.
    """
    import pages.analytics.damage as page

    assert page._label_color("#ffe08a", True, False) == "#ffe08a"
    # Below the gate no bubble holds its label, so both are read against the page. A real
    # panel does not reach this any more, which is why the floor is pushed down here.
    monkeypatch.setattr(page, "MARKER_PX", (8.0, 12.0))
    trace = page._trace(_two_bubbles(), name="n", color="#cb4b16", filled=True,
                        oi_range=(40_000.0, 1_000_000.0), label_all=True)
    assert list(trace.textfont.color) == ["#cb4b16", "#cb4b16"]


# ── this site's own universe ────────────────────────────────────────────────
#
# The panel is a superset of the instruments this site is configured for: crowdmon scores
# every market it can reach. Filtering to the configured universe is this page's own
# decision, so it is also this page's obligation to say which markets it removed, and the
# reason it prints has to be true of each one. Two of the three markets the panel gives no
# ticker for ARE configured here, so "not configured here" would be a wrong answer, not
# merely a vague one.
def _universe(monkeypatch, plotted, configured=None):
    """Pin the configured universe, so these tests do not depend on which config is loaded.

    The committed sample config names six instruments and none of them is in the fixture
    panel, so an unpinned test would pass by filtering everything away.
    """
    import viz_config

    monkeypatch.setattr(viz_config, "plotted_symbols", lambda: frozenset(plotted))
    monkeypatch.setattr(viz_config, "configured_symbols",
                        lambda: frozenset(plotted if configured is None else configured))


def test_only_configured_instruments_reach_the_chart(monkeypatch, store):
    """A market on this chart and on no other page is a market a reader cannot follow up."""
    import pages.analytics.damage as page

    _universe(monkeypatch, {"S0", "S1"})
    week = artifact.latest_week(artifact.load(store))
    kept, dropped, problem = page._universe_split(week)

    assert problem is None
    assert set(kept["market_code"]) == {"001", "002"}
    assert len(dropped) == 3


def test_a_filtered_market_is_named_with_the_reason_that_applies_to_it(monkeypatch, store):
    """Three different absences, three different sentences, each true of its own rows.

    `heldout` is this site's word, not the producer's: crowdmon has never heard of this
    universe, which is why these strings live in the page rather than in the manifest.
    """
    import pages.analytics.damage as page

    week = artifact.latest_week(artifact.load(store))
    week.loc[week["market_code"] == "005", "symbol"] = None
    _universe(monkeypatch, plotted={"S0"}, configured={"S0", "S1", "S4"})
    kept, dropped, _ = page._universe_split(week)

    why = dict(zip(dropped["market_code"], dropped["why"]))
    assert why["002"] == page.NOT_PLOTTED_HERE, "configured, with a role this site skips"
    assert why["003"] == page.UNKNOWN_HERE, "no instrument here carries that ticker"
    assert why["005"] == page.NO_TICKER, (
        "the panel gives no ticker for it, which says nothing about the config: on the "
        "real panel both such markets ARE configured here")

    rendered = str(page._excluded(kept, _manifest(), "sell", dropped))
    for code, name in (("002", "SOYBEAN MEAL"), ("003", "DJIA"), ("005", "NEW THING")):
        assert name in rendered, "{} was removed without being named".format(code)
    for reason in (page.NOT_PLOTTED_HERE, page.UNKNOWN_HERE, page.NO_TICKER):
        assert reason in rendered


def test_a_market_held_out_of_selection_is_held_out_of_this_chart_too(monkeypatch, store):
    """The role rules are the site's, imported from cotmetrics rather than restated.

    A page that resolves its own list of plottable markets is the new door through which a
    heldout market becomes plotted, which is exactly what every other page here avoids.
    """
    from cotmetrics.CotIndexer import PLOTTED_ROLES

    import viz_config

    monkeypatch.setattr(viz_config, "_data", {
        "roles": {"default": "deploy"},
        "AssetClasses": [{"Grains": [{"Name": "a", "Symbol": "S0"},
                                     {"Name": "b", "Symbol": "S1", "Role": "watch"},
                                     {"Name": "c", "Symbol": "S2", "Role": "heldout"}]}]})
    viz_config.instrument_roles.cache_clear()
    try:
        assert viz_config.plotted_symbols() == frozenset({"S0", "S1"})
        assert viz_config.configured_symbols() == frozenset({"S0", "S1", "S2"})
        assert "heldout" not in PLOTTED_ROLES, "the rule is cotmetrics', not this repo's"
    finally:
        viz_config.instrument_roles.cache_clear()


def test_an_unconfigured_site_plots_everything_rather_than_nothing(monkeypatch, store):
    """An empty universe is not a statement that this site plots no markets.

    It is what the public sample config looks like before `COT_VIZ_CONFIG` points at a real
    one, and filtering on it would render an empty chart with no error on it.
    """
    import pages.analytics.damage as page

    _universe(monkeypatch, plotted=set(), configured=set())
    week = artifact.latest_week(artifact.load(store))
    kept, dropped, problem = page._universe_split(week)
    assert len(kept) == 5 and dropped.empty and problem is None


def test_an_unreadable_config_shows_every_market_and_says_so(monkeypatch, store):
    """A config this page cannot read is a problem with this repo, not a quiet week.

    Hiding every market behind it would read as one, and this callback must not raise: an
    exception here is a broken page rather than a rendered message.
    """
    import pages.analytics.damage as page
    import viz_config

    def _boom():
        raise ValueError("invalid Role 'deployed'")

    monkeypatch.setattr(viz_config, "plotted_symbols", _boom)
    week = artifact.latest_week(artifact.load(store))
    kept, dropped, problem = page._universe_split(week)

    assert len(kept) == 5 and dropped.empty
    assert "invalid Role" in problem
    assert problem in str(page._excluded(kept, _manifest(), "sell", dropped, problem))


def test_the_header_says_how_many_of_the_panel_s_markets_are_plotted(monkeypatch, store):
    """The manifest count is the producer's, and after filtering it is not the page's."""
    import pages.analytics.damage as page

    art = artifact.load(store)
    _universe(monkeypatch, {"S0", "S1"})
    assert page._market_count(art, 5) == "5 markets, 2 plotted here"
    _universe(monkeypatch, {"S0", "S1", "S2", "S3", "S4"})
    assert page._market_count(art, 5) == "5 markets"


def test_no_marker_is_drawn_as_empty_space(store):
    """A hollow trace must still be stroked, and an `-open` symbol is not how to do it.

    Plotly strokes an `-open` symbol from `marker.color` and ignores `marker.line`, so the
    contradicted trace, whose fill is transparent by design, rendered as nothing at all: 17
    of the 46 markets on the 2026-07-28 sell side were plotted as points with no mark, and
    the legend swatch beside their entry was blank too. Nothing failed, and the count in the
    legend read as if they were there.

    That is the failure this page spends an entire alert on, an unnamed market reading as a
    safe one, arriving through the renderer rather than through the data.
    """
    import pages.analytics.damage as page

    art = artifact.load(store)
    fig = page._figure(artifact.latest_week(art), art.manifest, "sell")
    for trace in fig.data:
        hollow = trace.marker.color == "rgba(0,0,0,0)"
        assert not str(trace.marker.symbol).endswith("-open"), (
            "{} strokes from a transparent marker.color and draws nothing".format(
                trace.name))
        assert not hollow or trace.marker.line.width > 0, (
            "{} has neither a fill nor an outline".format(trace.name))
