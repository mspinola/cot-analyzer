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
        "factor_questions": {"crowding": "q"},
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
