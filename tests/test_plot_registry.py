"""The registry has to reproduce what the pages did before it existed.

The expected values below are written out as literals on purpose, snapshotted from the
four pages as they were before the registry landed. Deriving them from the registry
would make every assertion here tautological: the point is to pin the behaviour that
shipped, so a later edit to a spec cannot quietly move a panel onto a different axis
or change which panels respond to the basis control.
"""

import cotmetrics.constants as const
import pytest

import viz_constants as vc
from components import plot_registry as reg

# --- what the pages declared before the registry --------------------------------

# viz_constants.BASIS_AWARE_PLOTS
EXPECTED_BASIS_AWARE = {"net_pos", "index", "zscore", "momentum", "spearman"}

# viz_constants.BASIS_INVARIANT_NOTE
EXPECTED_INVARIANT_NOTE = {
    "oi_pct": "already normalized by OI",
    "willco": "already normalized by OI",
    "max_pain": "not a COT metric",
    "max_pain_historical": "not a COT metric",
}

# plot_helpers.BASIS_OVERLAY_SPEC
EXPECTED_OVERLAY = {
    "index": ("comms_idx", "Index", [0, 100], False),
    "zscore": ("comms_zscore", "Z-Score", None, True),
    "spearman": ("comms_spearman", "Correlation", [-1, 1], True),
    "momentum": (const.COMM_MOMENTUM, vc.MOMENTUM_LABEL, None, True),
}

# The `has_secondary` list each page kept inline, as (page, show_price, {ids}).
# OI Alignment and Analysis always draw price; Aggregation never does, which is why
# net_pos has to stay on a secondary axis independently of the price overlay.
EXPECTED_SECONDARY = [
    ("oi_alignment", True, {"macd", "willco", "index", "momentum", "zscore",
                            "net_pos", "oi_pct", "lrg_sentiment",
                            "max_pain_historical"}),
    ("analysis", True, {"price_candles", "macd", "willco", "index", "momentum",
                        "zscore", "oi_pct", "spearman", "lrg_sentiment", "net_pos",
                        "max_pain_historical"}),
    ("graphs", True, {"oi_pct", "willco", "spearman", "index", "zscore", "momentum",
                      "net_pos", "max_pain_historical"}),
    ("aggregation", False, {"net_pos"}),
]

ALL_IDS = set(reg.REGISTRY)


def test_basis_aware_matches_shipped_set():
    assert reg.BASIS_AWARE_PLOTS == EXPECTED_BASIS_AWARE


def test_invariant_notes_match_shipped():
    assert reg.BASIS_INVARIANT_NOTE == EXPECTED_INVARIANT_NOTE


def test_overlay_spec_matches_shipped():
    assert reg.BASIS_OVERLAY_SPEC == EXPECTED_OVERLAY


# The cross-checks against viz_constants.BASIS_AWARE_PLOTS and BASIS_INVARIANT_NOTE
# lived here while both copies were live. All four pages now read the registry and the
# originals are gone, so the snapshots above are the only remaining record of what
# shipped, which is what they were written to be.


@pytest.mark.parametrize("page,show_price,expected", EXPECTED_SECONDARY,
                         ids=[p for p, _, _ in EXPECTED_SECONDARY])
def test_secondary_axis_matches_shipped(page, show_price, expected):
    """Every id resolves to the axis the page gave it before the registry."""
    got = {i for i in ALL_IDS if reg.uses_secondary_y(i, show_price)}
    # A page only ever asked about the panels it offered, so compare on that subset.
    assert got & expected == expected, f"{page}: lost a secondary axis"
    assert not (expected - got), f"{page}: {expected - got} should use secondary_y"


def test_overlay_implies_basis_aware():
    """Drawing both bases at once is meaningless for a panel the basis cannot move."""
    for pid in reg.BASIS_OVERLAY_SPEC:
        assert reg.REGISTRY[pid].basis_aware, f"{pid} overlays but is not basis-aware"


def test_basis_aware_and_invariant_are_disjoint():
    assert not (reg.BASIS_AWARE_PLOTS & set(reg.BASIS_INVARIANT_NOTE))


def test_every_spec_is_buildable():
    for pid, spec in reg.REGISTRY.items():
        assert callable(spec.build), f"{pid} has no builder"
        assert spec.label, f"{pid} has no label"
        assert spec.secondary_y in (reg.SECONDARY_NEVER, reg.SECONDARY_WITH_PRICE,
                                    reg.SECONDARY_ALWAYS)


def test_sanitize_selection_drops_retired_ids():
    """A session-persisted selection naming a retired panel must not reach the grid."""
    assert reg.sanitize_selection(["index", "synthesis", "willco"], ALL_IDS) == \
        ["index", "willco"]
    assert reg.sanitize_selection(None, ALL_IDS) == []
    assert reg.sanitize_selection([], ALL_IDS) == []


def test_subplot_specs_shape_and_padding():
    grid = reg.subplot_specs(["index", "willco", "macd"], show_price=True, num_cols=2)
    assert len(grid) == 2 and all(len(r) == 2 for r in grid)
    assert grid[0][0] == {"secondary_y": True}
    assert grid[1][1] is None  # trailing empty cell


def test_labels_for_respects_overrides():
    got = reg.labels_for(["net_pos", "index"],
                         overrides={"net_pos": "Net Positions (Sum)"})
    assert got == {"net_pos": "Net Positions (Sum)",
                   "index": "Positioning Index"}


@pytest.mark.parametrize("page,dict_name", [
    ("oi_alignment", "AVAILABLE_PLOTS"),
    ("analysis", "BASE_PLOTS"),
    ("graphs", "AVAILABLE_PLOTS"),
    ("aggregation", "AVAILABLE_PLOTS"),
])
def test_pages_only_reference_known_plots(page, dict_name):
    """Catches a page offering an id the registry never learned about.

    Read from source rather than imported: a page builds its asset dropdowns at import
    time, which boots the indexer and wants a populated data store. CI runs against an
    empty one, so importing here would be slow and prove nothing about plot ids.

    Accepts either form, because the pages migrate one at a time: a page that has moved
    declares `PLOT_IDS = [...]` and takes its labels from the registry, one that has
    not still carries its own `{id: label}` dict.
    """
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[1] / "src"
    text = (src / "pages" / "analytics" / f"{page}.py").read_text()

    migrated = re.search(r'^PLOT_IDS\s*=\s*\[(.*?)\]', text, re.S | re.M)
    if migrated:
        ids = set(re.findall(r'"([a-z_]+)"', migrated.group(1)))
    else:
        body = re.search(rf'^{dict_name}\s*=\s*\{{(.*?)^\}}', text, re.S | re.M)
        assert body, f"found neither PLOT_IDS nor {dict_name} in {page}.py"
        ids = set(re.findall(r'"([a-z_]+)"\s*:', body.group(1)))

    assert ids, f"no plot ids parsed from {page}.py"
    assert ids <= ALL_IDS, f"{page} offers unknown plots: {sorted(ids - ALL_IDS)}"
