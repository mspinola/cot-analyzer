"""The Divergence page's rows answer for all three models off one matrix frame.

The rules worth pinning: what counts as a disagreement (a verdict split OR a wide
basis gap), which rows the default view hides and how it counts them, and that each
model's cell reads its OWN column family so a raw number can never sit under a
normalized header.
"""
import cotmetrics.constants as const
import cotmetrics.models as models
import pandas as pd

import components.divergence_rows as dr


def record(asset="Gold", asset_class="Metals", comm=50, lrg=50, sml=50,
           comm_norm=None, lrg_norm=None, sml_norm=None,
           state_cls=const.SETUP_NONE, state_npf=const.SETUP_NONE,
           state_npf_cls=const.SETUP_NONE, is_equity=False):
    """One `get_matrix_data` record. Norm values default to the raw ones so an
    agreement fixture is one line; the divergence tests set them apart because the
    bases differing is the subject."""
    return {
        "Asset Class": asset_class, "Asset": asset,
        "Comm Index": comm, "Lrg Index": lrg, "Sml Index": sml,
        "Comm Index Norm": comm if comm_norm is None else comm_norm,
        "Lrg Index Norm": lrg if lrg_norm is None else lrg_norm,
        "Sml Index Norm": sml if sml_norm is None else sml_norm,
        const.SETUP_CLS_COL: state_cls, const.SETUP_NPF_COL: state_npf,
        const.SETUP_NPF_CLS_COL: state_npf_cls,
        const.IS_EQUITY_COL: is_equity, "Date": "2026-08-25",
    }


def frame(*records):
    return pd.DataFrame(list(records))


def markets(rows):
    return [r for r in rows if r.kind == "market"]


# ── each model reads its own columns ──────────────────────────────────────────

def test_each_read_comes_from_its_own_column_family():
    rows, _, _ = dr.build_rows(frame(record(comm=96, comm_norm=62, lrg=10,
                                            lrg_norm=40, sml=5, sml_norm=70)),
                               show_all=True)
    row = markets(rows)[0]
    by_key = {r.key: r for r in row.reads}
    assert by_key[models.RAW_PF.key].comm == 96
    assert by_key[models.NPF.key].comm == 62
    assert by_key[models.NPF_CLS_95_5.key].comm == 62
    assert by_key[models.RAW_PF.key].lrg == 10
    assert by_key[models.NPF_CLS_95_5.key].lrg == 40


def test_a_leg_the_gate_does_not_read_is_absent_from_the_read():
    """NPF's CS gate drops Large Specs, so its cell must not print one even though
    the frame carries the column."""
    rows, _, _ = dr.build_rows(frame(record(comm=96, comm_norm=62)), show_all=True)
    by_key = {r.key: r for r in markets(rows)[0].reads}
    assert by_key[models.NPF.key].lrg is None
    assert by_key[models.NPF_CLS_95_5.key].lrg is not None


def test_equities_keep_only_the_commercial_leg():
    """Every gate decides an equity on Commercials alone; printing spec legs would
    claim they were consulted."""
    rows, _, _ = dr.build_rows(
        frame(record(asset="Russell", asset_class="Equities", comm=100,
                     comm_norm=98, is_equity=True)), show_all=True)
    for read in markets(rows)[0].reads:
        assert read.lrg is None and read.sml is None
        assert read.comm is not None


# ── what counts as a disagreement ─────────────────────────────────────────────

def test_a_verdict_split_is_never_dim_whatever_the_gap():
    rows, hidden, _ = dr.build_rows(
        frame(record(state_cls=const.SETUP_BULL)))
    row = markets(rows)[0]
    assert row.split and not row.dim
    assert hidden == 0


def test_matching_verdicts_and_a_narrow_gap_dim_and_hide():
    rows, hidden, _ = dr.build_rows(frame(record(comm=50, comm_norm=53)))
    assert markets(rows) == []
    assert hidden == 1


def test_a_wide_gap_alone_keeps_the_row():
    rows, hidden, _ = dr.build_rows(frame(record(comm=96, comm_norm=62)))
    row = markets(rows)[0]
    assert not row.split and not row.dim
    assert row.gap == 34
    assert hidden == 0


def test_show_all_keeps_agreeing_rows_dimmed_in_place():
    rows, hidden, _ = dr.build_rows(frame(record(comm=50, comm_norm=53)),
                                    show_all=True)
    row = markets(rows)[0]
    assert row.dim and not row.split
    assert hidden == 0


def test_a_market_missing_a_basis_is_counted_not_compared():
    rows, _, unplaced = dr.build_rows(
        frame(record(asset="MSCI EAFE", comm=None)), show_all=True)
    assert markets(rows) == []
    assert unplaced == ["MSCI EAFE"]


# ── ordering ──────────────────────────────────────────────────────────────────

def test_splits_sort_above_wide_gaps_inside_a_class():
    rows, _, _ = dr.build_rows(frame(
        record(asset="WideGap", comm=96, comm_norm=50),
        record(asset="Split", comm=50, comm_norm=52, state_npf=const.SETUP_BULL),
        record(asset="WiderGap", comm=96, comm_norm=30),
    ))
    assert [r.label for r in markets(rows)] == ["Split", "WiderGap", "WideGap"]
    assert rows[0].kind == "class" and rows[0].label == "Metals"


# ── the columns are selectable ────────────────────────────────────────────────

def test_a_split_against_an_excluded_model_does_not_count():
    """Disagreement is a property of the columns on screen: a market that splits only
    against a model the reader switched off is an agreement on this view."""
    rec = record(comm=50, comm_norm=52, state_npf_cls=const.SETUP_BULL)
    full_rows, _, _ = dr.build_rows(frame(rec))
    assert markets(full_rows)[0].split
    narrowed, hidden, _ = dr.build_rows(
        frame(rec), compare=(models.RAW_PF, models.NPF))
    assert markets(narrowed) == []
    assert hidden == 1


def test_a_narrowed_view_reads_only_the_selected_models():
    rows, _, _ = dr.build_rows(frame(record(comm=96, comm_norm=62)),
                               show_all=True,
                               compare=(models.RAW_PF, models.NPF_CLS_95_5))
    row = markets(rows)[0]
    assert [r.key for r in row.reads] == [models.RAW_PF.key,
                                          models.NPF_CLS_95_5.key]


def test_one_column_alone_differentiates_on_the_gap_only():
    """A single model cannot split with itself, so the dim rule reduces to the gap,
    and the gap keeps its meaning because it is a fact about the frame."""
    rows, hidden, _ = dr.build_rows(
        frame(record(asset="Wide", comm=96, comm_norm=62),
              record(asset="Tight", comm=50, comm_norm=52,
                     state_cls=const.SETUP_BULL, state_npf=const.SETUP_BULL,
                     state_npf_cls=const.SETUP_BULL)),
        compare=(models.NPF,))
    assert [r.label for r in markets(rows)] == ["Wide"]
    assert not markets(rows)[0].split
    assert hidden == 1


def test_the_selectors_resolve_stale_keys_to_that_columns_default():
    """A browser session can hold a key for a model that no longer exists; the column
    falls back to its own default rather than silently vanishing, because a missing
    column looks exactly like a deliberate None. "none" IS the deliberate one, and a
    column whose own DEFAULT is none resolves a stale key all the way to none."""
    from pages.analytics.divergence import COLUMN_NONE, compared_models

    assert compared_models("raw_pf", "npf", "npf_cls_95_5") == list(models.MODELS)
    assert compared_models("raw_pf", COLUMN_NONE, COLUMN_NONE) == [models.RAW_PF]
    assert compared_models(COLUMN_NONE, COLUMN_NONE, COLUMN_NONE) == []
    assert compared_models("raw_pf", "retired_model", COLUMN_NONE) == [
        models.RAW_PF, models.NPF_CLS_95_5]
    assert compared_models("raw_pf", "npf", "retired_model") == [
        models.RAW_PF, models.NPF]


def test_the_default_view_is_the_two_cls_models():
    """Raw CLS 95/5 against NPF CLS 95/5: the same gate and band on the two bases,
    so every default-view disagreement is the normalization and nothing else. The
    three-way comparison stays one selection away."""
    from pages.analytics.divergence import COLUMN_DEFAULTS, COLUMN_NONE, compared_models

    assert COLUMN_DEFAULTS == (models.RAW_PF.key, models.NPF_CLS_95_5.key,
                               COLUMN_NONE)
    assert compared_models(*COLUMN_DEFAULTS) == [models.RAW_PF,
                                                 models.NPF_CLS_95_5]


def test_comm_spread_is_about_the_displayed_columns_not_the_frame():
    """The C emphasis threshold reads this, never `gap`: two normalized columns
    share one series, so their spread is zero however wide the basis gap is."""
    read = dr.ModelRead
    assert dr.comm_spread(
        (read(key="a", comm=80.0), read(key="b", comm=71.0))) == 9.0
    assert dr.comm_spread(
        (read(key="a", comm=64.0), read(key="b", comm=64.0))) == 0.0
    # One column, or one reading plus a market missing the other basis: no pair,
    # no spread, no emphasis.
    assert dr.comm_spread((read(key="a", comm=64.0),)) is None
    assert dr.comm_spread(
        (read(key="a", comm=64.0), read(key="b", comm=None))) is None
    # Three columns: the WIDEST pair decides.
    assert dr.comm_spread(
        (read(key="a", comm=60.0), read(key="b", comm=64.0),
         read(key="c", comm=52.0))) == 12.0


def test_leg_spread_covers_every_leg_and_skips_uncarried_ones():
    """The emphasis generalized from the Commercial leg once the default view
    became the two CLS models, where every leg is the same gate on two bases.
    The guard that matters: a leg only ONE shown column carries (NPF CS drops
    Large Specs; equities carry Commercials alone) has no pair to disagree, so
    it must never light a value against a dash."""
    read = dr.ModelRead
    reads = (read(key="a", comm=37.0, lrg=65.0, sml=24.0),
             read(key="b", comm=49.0, lrg=None, sml=24.0))
    assert dr.leg_spread(reads, "comm") == 12.0
    assert dr.leg_spread(reads, "lrg") is None
    assert dr.leg_spread(reads, "sml") == 0.0
    # comm_spread stays as the shorthand the renderer grew up on.
    assert dr.comm_spread(reads) == dr.leg_spread(reads, "comm")
