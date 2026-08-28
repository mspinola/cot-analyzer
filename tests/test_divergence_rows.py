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
