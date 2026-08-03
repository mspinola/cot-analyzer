"""The category palette derivation, checked against every shipped palette.

Store-free: viz_config falls back to the committed config/params.yaml when
COT_VIZ_CONFIG is unset, which is what CI runs with.
"""

import re

import pytest
from cotmetrics import categories as cot_categories

import viz_config
import viz_constants as vc
from components.category_traces import category_series

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

REPORTS = list(cot_categories.REPORT_CHOICES)
PALETTES = sorted(viz_config.get_palette_names())


def test_palette_map_covers_exactly_the_cotmetrics_categories():
    """A category rename in cotmetrics must fail here, not in the browser.

    category_series indexes CATEGORY_PALETTE_MAP by spec key, so a key that drifts
    out of sync surfaces as a KeyError mid-render on a page nothing else tests.
    """
    for report in REPORTS:
        expected = {s.key for s in cot_categories.categories_for(report)}
        assert set(vc.CATEGORY_PALETTE_MAP[report]) == expected, report


def test_palette_map_reports_match_cotmetrics_vocabulary():
    assert set(vc.CATEGORY_PALETTE_MAP) == set(cot_categories.REPORT_CHOICES)


@pytest.mark.parametrize("palette_name", PALETTES)
@pytest.mark.parametrize("report", REPORTS)
def test_every_category_resolves_to_a_distinct_valid_color(palette_name, report):
    palette = viz_config.get_palette(palette_name)
    series = category_series(report, None, palette)

    assert len(series) == len(cot_categories.categories_for(report))
    colors = [s.color for s in series]
    assert all(HEX.match(c) for c in colors), colors
    assert len(set(colors)) == len(colors), f"{palette_name}/{report}: {colors}"


@pytest.mark.parametrize("report", REPORTS)
def test_slot_siblings_are_distinguished_by_dash_not_only_tint(report):
    """Two categories on one palette slot must differ in more than lightness.

    Solarized's spacing is tight enough that a 0.45 tint alone can be lost against a
    busy panel, so the tinted sibling is always the dashed one.
    """
    slots = {}
    for key, (slot, tint) in vc.CATEGORY_PALETTE_MAP[report].items():
        slots.setdefault(slot, []).append((key, tint))

    for slot, members in slots.items():
        if len(members) < 2:
            continue
        tints = [t for _, t in members]
        assert sum(1 for t in tints if t == 0.0) == 1, (report, slot, members)

    series = {s.key: s for s in category_series(
        report, None, viz_config.get_palette(PALETTES[0]))}
    for key, (_, tint) in vc.CATEGORY_PALETTE_MAP[report].items():
        assert (series[key].dash is not None) == (tint > 0), key


@pytest.mark.parametrize("report", REPORTS)
def test_selection_filters_and_preserves_report_order(report):
    palette = viz_config.get_palette(PALETTES[0])
    keys = [s.key for s in cot_categories.categories_for(report)]
    picked = {keys[0], keys[-1]}

    series = category_series(report, picked, palette)

    assert [s.key for s in series] == [k for k in keys if k in picked]


def test_switching_report_resets_the_category_selection():
    """A selection from the other report must not survive the switch.

    The two reports share the keys other_reportable and nonreportable by name only,
    so intersecting a carried-over selection can only ever leave those two residual
    categories, silently dropping Managed Money or Leveraged Funds.
    """
    from pages.analytics.categories import update_category_options

    tff_keys = [s.key for s in cot_categories.categories_for(
        cot_categories.REPORT_TFF)]
    disagg_keys = [s.key for s in cot_categories.categories_for(
        cot_categories.REPORT_DISAGG)]

    _, value = update_category_options(cot_categories.REPORT_DISAGG, tff_keys)
    assert value == disagg_keys

    # A within-report deselection is a real choice and survives.
    _, value = update_category_options(
        cot_categories.REPORT_DISAGG, ["managed_money", "swap"])
    assert value == ["managed_money", "swap"]

    # So does an empty/unset selection falling back to everything.
    _, value = update_category_options(cot_categories.REPORT_TFF, [])
    assert value == tff_keys


def test_price_and_oi_slots_are_outside_the_category_slots():
    used = {slot for m in vc.CATEGORY_PALETTE_MAP.values()
            for slot, _ in m.values()}
    assert vc.CATEGORY_PRICE_SLOT not in used
    assert vc.CATEGORY_OI_SLOT not in used
