"""The category palette derivation, checked against every shipped palette.

Store-free: viz_config falls back to the committed config/params.yaml when
COT_VIZ_CONFIG is unset, which is what CI runs with.
"""

import itertools
import re

import pytest
from cotmetrics import categories as cot_categories

import components.category_traces as ct
import components.plot_colors as plot_colors
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


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _separation(a, b):
    """Weighted-RGB distance, a cheap stand-in for perceived difference.

    Not a proper colour space, but enough to catch the failure this exists for: two
    lines that a reader calls "almost identical". Plain hex inequality is not, which
    is how Other Reportable and Non-Reportable shipped as two near-identical yellows.
    """
    ra, rb = _rgb(a), _rgb(b)
    rmean = (ra[0] + rb[0]) / 2
    dr, dg, db = (x - y for x, y in zip(ra, rb))
    return ((2 + rmean / 256) * dr * dr + 4 * dg * dg
            + (2 + (255 - rmean) / 256) * db * db) ** 0.5


# Measured floor. The rule scores 156 at worst across every shipped palette and both
# reports; 140 leaves room for a palette tweak without pinning the exact arithmetic.
MIN_SIBLING_SEPARATION = 140


@pytest.mark.parametrize("palette_name", PALETTES)
@pytest.mark.parametrize("report", REPORTS)
def test_slot_siblings_are_visibly_different_colors(palette_name, report):
    """The two categories sharing a palette slot must be tellable apart.

    The regression this pins: lightening an already-bright colour barely moves it,
    because the maxed channels cannot go up. Slot 2 is yellow in most palettes, so
    Other Reportable and Non-Reportable both rendered as plain yellow.
    """
    palette = viz_config.get_palette(palette_name)
    series = {s.key: s for s in category_series(report, None, palette)}

    slots = {}
    for key, (slot, _) in vc.CATEGORY_PALETTE_MAP[report].items():
        slots.setdefault(slot, []).append(key)

    for slot, members in slots.items():
        for a, b in itertools.combinations(members, 2):
            got = _separation(series[a].color, series[b].color)
            assert got >= MIN_SIBLING_SEPARATION, (
                f"{palette_name}/{report} slot {slot}: {a} {series[a].color} vs "
                f"{b} {series[b].color} separated by only {got:.0f}")


@pytest.mark.parametrize("palette_name", PALETTES)
def test_bright_bases_are_darkened_and_stay_visible(palette_name):
    """A bright base gets a darker sibling, not a lighter one, and stays legible.

    Darkening is the only direction with room left on a saturated colour, but it must
    not push the line into the background. WCAG asks 3:1 for graphical objects.
    """
    palette = viz_config.get_palette(palette_name)
    bg = plot_colors.relative_luminance(vc.BACKGROUND_COLOR)

    for base in palette[:3]:
        sib = ct.sibling_color(base)
        base_lum = plot_colors.relative_luminance(base)
        sib_lum = plot_colors.relative_luminance(sib)
        if base_lum > vc.CATEGORY_BRIGHT_LUMINANCE:
            assert sib_lum < base_lum, f"{base} should darken, got {sib}"
            contrast = (max(sib_lum, bg) + 0.05) / (min(sib_lum, bg) + 0.05)
            assert contrast >= 3.0, f"{sib} only {contrast:.1f}:1 against the plot bg"
        else:
            assert sib_lum > base_lum, f"{base} should lighten, got {sib}"


@pytest.mark.parametrize("report", REPORTS)
def test_exactly_one_base_per_slot_and_siblings_are_dashed(report):
    slots = {}
    for key, (slot, is_sibling) in vc.CATEGORY_PALETTE_MAP[report].items():
        slots.setdefault(slot, []).append((key, is_sibling))

    for slot, members in slots.items():
        bases = [k for k, sib in members if not sib]
        assert len(bases) == 1, (report, slot, members)

    series = {s.key: s for s in category_series(
        report, None, viz_config.get_palette(PALETTES[0]))}
    for key, (_, is_sibling) in vc.CATEGORY_PALETTE_MAP[report].items():
        assert (series[key].dash is not None) == is_sibling, key


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
