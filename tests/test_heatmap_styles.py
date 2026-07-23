"""The signal matrix is rendered twice, and both renderers must agree.

`heatmap.setup_styles_for` emits AG Grid condition strings evaluated in the browser.
`cotmetrics.report_styles._setup_cell_style` returns CSS computed in Python for the
weekly email. They encode one rule, from one `get_matrix_data` frame, and until now
only the cotmetrics side had tests -- so the two were kept in step by hand.

These tests hold both to the same fixtures. They are also the prerequisite for ever
collapsing the two implementations into one, since without them a unification has
nothing to prove itself against.
"""
import re

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import pytest
from cotmetrics.report_styles import _DIM, _setup_cell_style

import viz_config
from pages.analytics import heatmap

RAW = models.RAW_PF.band   # (high, low) == (95, 5)

# The same live rows test_index_ramp.py uses in cotmetrics, so a disagreement between
# the two implementations shows up as the same market on both sides.
CAD = (100, 0, 0)              # clean setup
NZD = (97, 3, 5)               # setup, only just
FEEDER_CATTLE = (100, 0, 100)  # small specs blocking
ORANGE_JUICE = (96, 0, 100)    # two legs through, small specs at the opposite extreme
COCOA = (0, 100, 80)           # near bear, small specs short of the gate
LUMBER = (35, 62, 79)          # nothing

ROLES = ("comm", "spec", "spec")

WASH_BULL, WASH_BEAR, TINT_BULL, TINT_BEAR, DIM = (
    "wash_bull", "wash_bear", "tint_bull", "tint_bear", "dim")


# ── evaluating the emitted JavaScript ─────────────────────────────────────────
# The conditions use a deliberately small grammar, so a direct translation is enough.
# test_the_condition_translator_is_faithful below is what keeps this honest: if the
# translation were wrong, every parity test would agree for the wrong reason.

def _to_python(js):
    expr = js.replace("params.data[", "row[").replace("params.value", "value")
    expr = expr.replace("Math.abs(", "abs(").replace("===", "==")
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"!(?=row\[|value)", " not ", expr)
    return re.sub(r"\btrue\b", "True", expr)


def _evaluate(style_conditions, value, row):
    """First-match-wins, the way AG Grid applies styleConditions."""
    for rule in style_conditions:
        if eval(_to_python(rule["condition"]), {"abs": abs}, {"row": row, "value": value}):
            return rule["style"]
    return None


def _grid_verdict(style, colors):
    if style is None:
        return None
    bg, fg = style.get("backgroundColor"), style.get("color")
    if bg and fg == colors.bull:
        return WASH_BULL
    if bg and fg == colors.bear:
        return WASH_BEAR
    if fg == colors.bull_near:
        return TINT_BULL
    if fg == colors.bear_near:
        return TINT_BEAR
    return DIM


@pytest.fixture(scope="module")
def colors():
    return heatmap.grid_colors(viz_config.get_palette(None))


def _state(legs, is_equity=False):
    comm, lrg, sml = legs
    return utils.setup_state(comm, [lrg, sml], is_equity, *reversed(RAW))


def _row(legs, is_equity=False):
    return {const.SETUP_CLS_COL: _state(legs, is_equity),
            const.IS_EQUITY_COL: is_equity}


# ── the translator itself ─────────────────────────────────────────────────────

def test_the_condition_translator_is_faithful():
    """Every parity test below rides on this. A broken translator would make them
    agree for the wrong reason, so it gets pinned directly."""
    row = {"_setup_cls": const.SETUP_BULL, "_is_equity": False}
    assert eval(_to_python("params.data['_setup_cls'] === 'bull'"), {}, {"row": row, "value": 0})
    assert not eval(_to_python("params.data['_setup_cls'] === 'bear'"), {}, {"row": row, "value": 0})
    assert eval(_to_python("!params.data['_is_equity']"), {}, {"row": row, "value": 0})
    assert eval(_to_python("params.value <= 10"), {}, {"row": row, "value": 3})
    assert not eval(_to_python("params.value <= 10"), {}, {"row": row, "value": 30})
    assert eval(_to_python("Math.abs(params.value) >= 1.5"), {"abs": abs}, {"row": row, "value": -2.0})
    assert eval(_to_python("params.value >= 1 && params.value <= 5"), {}, {"row": row, "value": 3})
    assert eval(_to_python("params.value >= 9 || params.value <= 1"), {}, {"row": row, "value": 0})
    assert eval(_to_python("true"), {}, {"row": {}, "value": 0})


# ── parity with the emailed HTML ──────────────────────────────────────────────

@pytest.mark.parametrize("name,legs", [
    ("CAD", CAD), ("NZD", NZD), ("FEEDER_CATTLE", FEEDER_CATTLE),
    ("ORANGE_JUICE", ORANGE_JUICE), ("COCOA", COCOA), ("LUMBER", LUMBER),
])
@pytest.mark.parametrize("is_equity", [False, True])
def test_grid_and_email_agree_on_every_leg(name, legs, is_equity, colors):
    """The whole point of this file. Same row, same rule, two renderers."""
    state = _state(legs, is_equity)
    row = _row(legs, is_equity)

    for i, role in enumerate(ROLES):
        grid = _grid_verdict(
            _evaluate(setup_styles(role, colors), legs[i], row), colors)
        email = _setup_cell_style(legs[i], state, role, *RAW, is_equity=is_equity)

        grid_lit = grid in (WASH_BULL, WASH_BEAR)
        email_lit = "background-color" in email
        assert grid_lit == email_lit, (
            f"{name} leg {i} ({role}, equity={is_equity}): grid washes={grid_lit} "
            f"email washes={email_lit}")

        grid_dim = grid == DIM
        email_dim = _DIM in email
        assert grid_dim == email_dim, (
            f"{name} leg {i} ({role}, equity={is_equity}): grid dim={grid_dim} "
            f"email dim={email_dim}")


def setup_styles(role, colors):
    return heatmap.setup_styles_for(const.SETUP_CLS_COL, role, *RAW, colors=colors)


# ── the rule itself, mirroring test_index_ramp ────────────────────────────────

def test_a_full_setup_washes_every_leg(colors):
    row = _row(CAD)
    for i, role in enumerate(ROLES):
        assert _grid_verdict(_evaluate(setup_styles(role, colors), CAD[i], row),
                             colors) == WASH_BULL


def test_a_blocking_leg_keeps_the_row_out_of_a_setup(colors):
    """Feeder Cattle's small specs at 100 block a bull setup, so nothing washes."""
    row = _row(FEEDER_CATTLE)
    for i, role in enumerate(ROLES):
        v = _grid_verdict(_evaluate(setup_styles(role, colors), FEEDER_CATTLE[i], row), colors)
        assert v not in (WASH_BULL, WASH_BEAR)


def test_a_near_setup_tints_only_the_legs_at_their_own_gate(colors):
    """Cocoa (0, 100, 80) is near bear. Small specs at 80 are short of the 90 gate,
    so they stay dim and read as the reason it has not fired."""
    row = _row(COCOA)
    verdicts = [_grid_verdict(_evaluate(setup_styles(r, colors), COCOA[i], row), colors)
                for i, r in enumerate(ROLES)]
    assert verdicts[0] != DIM
    assert verdicts[1] != DIM
    assert verdicts[2] == DIM


def test_nothing_lights_when_there_is_no_setup(colors):
    row = _row(LUMBER)
    for i, role in enumerate(ROLES):
        assert _grid_verdict(_evaluate(setup_styles(role, colors), LUMBER[i], row),
                             colors) == DIM


# Commercials inside the near width but short of the gate, so the row is a near
# state rather than a full one. COCOA is a full setup once equities gate on
# Commercials alone, which is why it cannot serve here.
EQUITY_NEAR_BEAR = (8, 100, 80)


def test_equity_spec_legs_never_tint_on_a_near_state(colors):
    """Equities gate on Commercials alone, so a spec leg has nothing to say here."""
    legs = EQUITY_NEAR_BEAR
    assert _state(legs, is_equity=True) == const.SETUP_NEAR_BEAR, "fixture must be near"
    row = _row(legs, is_equity=True)
    for i, role in enumerate(ROLES):
        verdict = _grid_verdict(_evaluate(setup_styles(role, colors), legs[i], row), colors)
        assert verdict == (DIM if role == "spec" else TINT_BEAR)


# ── gates come from cotmetrics, not from literals ─────────────────────────────

def test_the_oi_gate_comes_from_the_constant(monkeypatch, colors):
    """PR #62 routed this through the constant. Nothing else stops it drifting back.

    Moving the constant and reading the emitted condition is the only check that a
    re-hardcoded literal would fail, since the literal today equals the constant.
    """
    before = heatmap.oi_styles_for(colors)[0]["condition"]
    assert str(const.OI_ZSCORE_HIGHLIGHT_THRESHOLD) in before

    monkeypatch.setattr(const, "OI_ZSCORE_HIGHLIGHT_THRESHOLD", 3.0)
    after = heatmap.oi_styles_for(colors)[0]["condition"]
    assert "3.0" in after and after != before

    # And it still evaluates the way AG Grid would.
    assert _evaluate(heatmap.oi_styles_for(colors), 3.5, {})["color"] != colors.dim
    assert _evaluate(heatmap.oi_styles_for(colors), 2.0, {})["color"] == colors.dim


def test_setup_conditions_embed_the_model_band(colors):
    """The near steps are derived from the band, so moving the band moves them."""
    high, low = RAW
    near = const.SETUP_NEAR_WIDTH
    conds = " ".join(r["condition"] for r in setup_styles("comm", colors))
    assert str(high - near) in conds
    assert str(low + near) in conds

    npf_conds = " ".join(
        r["condition"] for r in
        heatmap.setup_styles_for(const.SETUP_NPF_COL, "comm", *models.NPF.band, colors=colors))
    npf_high, npf_low = models.NPF.band
    assert str(npf_high - near) in npf_conds
    assert str(npf_low + near) in npf_conds
    assert npf_conds != conds, "the two bands must not produce identical conditions"


def test_the_catch_all_is_last(colors):
    """styleConditions is first-match-wins, so an early `true` would swallow the rest."""
    for role in ("comm", "spec"):
        conds = [r["condition"] for r in setup_styles(role, colors)]
        assert conds[-1] == "true"
        assert "true" not in conds[:-1]
