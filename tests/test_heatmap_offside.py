"""The Offside column the heatmap joins from cotmetrics.offside.

Store-free, matching test_heatmap_exposure: `attach_offside` is fed through a
monkeypatched `_leg_offside`, and the styling is evaluated the way test_heatmap_styles
evaluates every other condition string. The arithmetic behind the number (the cost-basis
recurrence, the sigma division) is cotmetrics' to test, not this repo's.
"""
import pandas as pd
import pytest

import viz_config
from pages.analytics import heatmap
from tests.test_heatmap_styles import _evaluate


@pytest.fixture(scope="module")
def colors():
    return heatmap.grid_colors(viz_config.get_palette(None))


def _matrix(rows):
    return pd.DataFrame(rows, columns=["Asset", "Date"])


# ── the join ──────────────────────────────────────────────────────────────────

def test_rows_join_on_their_own_week(monkeypatch):
    """Each row reads its OWN date, not the page's, matching the exposure join."""
    tables = {
        "Euro": {"2026-08-18": (-2.5, 1.12, 1.05), "2026-08-11": (-1.0, 1.12, 1.09)},
        "Crude Oil": {"2026-08-18": (0.8, 60.0, 64.0)},
    }
    monkeypatch.setattr(heatmap, "_leg_offside", lambda asset, newest: tables.get(asset))
    df = _matrix([("Euro", "2026-08-11"), ("Crude Oil", "2026-08-18")])
    out = heatmap.attach_offside(df, "2026-08-18")
    assert list(out["Offside"]) == [-1.0, 0.8]
    assert list(out["Offside Basis"]) == [1.12, 60.0]
    assert list(out["Offside Mark"]) == [1.09, 64.0]


def test_a_market_that_cannot_be_marked_stays_a_row(monkeypatch):
    """A market with no priced basis gets None in all three columns rather than
    dropping the row or raising. MSCI EAFE has no futures price series at all."""
    monkeypatch.setattr(
        heatmap, "_leg_offside",
        lambda asset, newest: {"2026-08-18": (-3.0, 10.0, 9.0)} if asset == "Euro" else None)
    df = _matrix([("Euro", "2026-08-18"), ("MSCI EAFE", "2026-08-18"),
                  ("Euro", "1999-01-05")])
    out = heatmap.attach_offside(df, "2026-08-18")
    assert list(out["Offside"]) == [-3.0, None, None]
    assert list(out["Offside Basis"]) == [10.0, None, None]


def test_the_computation_failing_returns_none_not_a_traceback(monkeypatch):
    """The lru-cached fetch turns ANY failure into None. One market with a broken
    price read must not take the rest of the matrix down with it."""
    heatmap._leg_offside.cache_clear()

    def boom(*a, **k):
        raise RuntimeError("no bars")

    monkeypatch.setattr(heatmap.offside, "market_offside", boom)
    assert heatmap._leg_offside("Euro", "2026-08-18") is None
    heatmap._leg_offside.cache_clear()


def test_the_columns_survive_as_object_dtype(monkeypatch):
    """A float column coerces None to NaN, and the grid's null guards key on null.

    This is the same trap the exposure columns document: the styling condition reads
    `params.value != null`, and NaN is not null in JS.
    """
    monkeypatch.setattr(heatmap, "_leg_offside", lambda asset, newest: None)
    out = heatmap.attach_offside(_matrix([("Euro", "2026-08-18")]), "2026-08-18")
    assert out["Offside"].dtype == object
    assert out["Offside"].iloc[0] is None


# ── the styling ───────────────────────────────────────────────────────────────

def test_a_deeply_underwater_cell_is_lit(colors):
    conds = heatmap.offside_styles_for(colors)
    assert _evaluate(conds, heatmap.OFFSIDE_DEEP - 1.0, {})["color"] == colors.bear
    assert _evaluate(conds, heatmap.OFFSIDE_DEEP, {})["color"] == colors.bear


def test_a_cohort_in_profit_is_not_lit(colors):
    """Only the losing tail lights. Being deep in PROFIT is not distress, so this
    column is deliberately not symmetric the way a z-score column would be."""
    conds = heatmap.offside_styles_for(colors)
    assert _evaluate(conds, 5.0, {})["color"] == colors.dim
    assert _evaluate(conds, 0.0, {})["color"] == colors.dim


def test_a_market_with_no_basis_yet_is_not_lit(colors):
    """JS coerces null to 0, so without the null guard an unpriced market would read
    as deeply offside. It is the set with the LEAST history behind it."""
    conds = heatmap.offside_styles_for(colors)
    assert _evaluate(conds, None, {})["color"] == colors.dim


def test_the_highlight_is_overridable(colors):
    conds = heatmap.offside_styles_for(colors, highlight="#123456")
    assert _evaluate(conds, -9.0, {})["color"] == "#123456"


# ── what the column says ──────────────────────────────────────────────────────

def test_the_column_reads_large_specs_alone():
    """NOT the large+small LEG_SPEC the dollar-risk column uses: a basis on the summed
    net describes a trader who is both cohorts at once, and they differ."""
    assert heatmap.OFFSIDE_LEG == heatmap.exposure.LEG_LARGE


def test_the_tooltip_refuses_to_promise_capitulation():
    """The measure's pre-registered test returned 'adverse-move proxy'. A tooltip that
    let a reader infer a forecast from a lit cell would be asserting the thing that was
    tested and did not hold, so the copy says so explicitly."""
    col = _offside_col()
    tip = col["headerTooltip"]
    assert "not a forecast" in tip
    assert "did not" in tip


def test_the_tooltip_says_size_does_not_enter():
    """The most likely misreading is that this is an exposure. It is per contract."""
    tip = _offside_col()["headerTooltip"]
    assert "per CONTRACT" in tip or "Per CONTRACT" in tip


def _offside_col():
    """The Offside column def, read out of the page's source.

    The column is built inside the render callback, which needs a store and a palette
    to run, so this parses it instead. Only the literal parts of an f-string survive,
    which is enough: every phrase asserted above is literal text, and a phrase that got
    moved into an interpolated expression would fail here rather than pass silently.
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(heatmap))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "field" in keys:
                idx = keys.index("field")
                field = node.values[idx]
                if isinstance(field, ast.Constant) and field.value == "Offside":
                    out = {}
                    for k, v in zip(node.keys, node.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.JoinedStr):
                            out[k.value] = "".join(
                                p.value for p in v.values if isinstance(p, ast.Constant))
                        elif isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            out[k.value] = v.value
                    return out
    raise AssertionError("no Offside column def found in heatmap.py")
