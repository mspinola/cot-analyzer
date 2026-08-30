"""Rows for the Divergence page: the three models' answers to one market, side by side.

Every other verdict surface in the app follows ONE model (the Strip, the Home board)
or two fixed ones (the Heatmap's blocks). This is the page for the question those
cannot ask: where do the models DISAGREE, and by how much? A reader who trusts one
model never needs it; a reader deciding which model to trust starts here.

Two different kinds of disagreement live on a row, and conflating them is the mistake
this module is shaped to prevent:

**Verdict splits.** The models can answer SETUP / NEAR / nothing differently about the
same week. This is the headline, because a split names a market where which model you
follow changes what you would do. Splits can come from the band (95/5 against 80/20 on
the same normalized series), from the gate (NPF CS ignores the Large Spec leg the two
CLS gates read), or from the basis.

**The basis gap.** |raw Comm index - OI-normalized Comm index|, the same number the
Strip's "Other basis" comparison draws as a connector. The two normalized models share
one series by construction, so this is the ONLY value difference that exists on a row,
and it is exactly the secular contract-size drift the normalization removes. A wide
gap with no verdict split is still worth surfacing: it marks a market where the bases
tell different stories that happen not to cross a gate this week.

A row where neither kind of disagreement exists is DIMMED rather than dropped, and the
default view hides it entirely: a board of forty agreements is noise around the three
rows the page exists for, but "hidden" must remain a choice the reader can undo, which
is why the count of hidden rows is returned rather than swallowed.

Everything is a pure function over a `get_matrix_data` frame, like strip_traces, and
it reads the model/column joins FROM strip_traces rather than declaring its own: two
tables mapping the same models onto the same matrix would drift, and the strip's is
the one held to `models.MODELS` by test.
"""

from dataclasses import dataclass

import cotmetrics.constants as const
import cotmetrics.models as models

from components.strip_traces import LEG_COLUMNS, SETUP_COLUMN, _num

# Below this, two Commercial readings are "the same value" for the dimming rule. Five
# index points on a 0-100 scale is comfortably inside week-to-week noise and half the
# width of the tightest near-band; it is a display threshold, not a gate, so it lives
# here rather than on a model.
GAP_TOLERANCE = 5

# The default column order: the baseline first, then the deployable headline, then
# the tight-band variant, which is MODELS' own order and the heatmap's. The page lets
# the reader recompose the columns (see build_rows), including down to one; the basis
# gap is unaffected because it is a fact about the frame, not about the columns.
MODEL_ORDER = models.MODELS


@dataclass(frozen=True)
class ModelRead:
    """One model's answer for one market: its legs, on its own basis, and its verdict.

    A leg the model's gate does not read is None here even when the frame carries a
    value for it, so the renderer cannot print a number the verdict never consulted --
    the same rule the strip's lanes and the card's lanes follow.
    """
    key: str
    comm: float = None
    lrg: float = None
    sml: float = None
    state: str = const.SETUP_NONE


@dataclass(frozen=True)
class DivergenceRow:
    """One line of the table: an asset-class header or a market."""
    kind: str                 # "class" or "market"
    label: str
    asset_class: str
    reads: tuple = ()         # one ModelRead per model, in MODEL_ORDER
    gap: float = None         # |raw comm - normalized comm|, None if either absent
    split: bool = False       # the models' verdicts differ
    dim: bool = False         # no split AND no displayed leg pair differs enough
    is_equity: bool = False


def leg_spread(reads, leg):
    """The widest disagreement among the DISPLAYED columns' readings of one leg.

    None with fewer than two readings, because one column cannot disagree with
    itself; that is also what keeps the emphasis honest on legs some columns do
    not carry (NPF CS drops Large Specs, equities carry Commercials alone). It
    is deliberately distinct from `gap`: gap is the raw-vs-normalized fact
    about the FRAME, this is a fact about the columns on screen, and the two
    coincide on the Commercial leg exactly when the columns are one raw and one
    normalized model (the default view). Two normalized columns share a series,
    so their spread is zero however wide the basis gap is, which is why the
    emphasis in the renderer must not borrow the gap.
    """
    values = [getattr(r, leg) for r in reads if getattr(r, leg) is not None]
    if len(values) < 2:
        return None
    return max(values) - min(values)


def comm_spread(reads):
    """The Commercial shorthand the renderer and its tests grew up on."""
    return leg_spread(reads, "comm")


def _read_for(record, model, is_equity):
    """One model's ModelRead off a matrix record.

    Equities keep only the Commercial leg: every gate decides an equity on
    Commercials alone, so printing spec legs would claim they were consulted.
    """
    cols = LEG_COLUMNS[model.key]
    return ModelRead(
        key=model.key,
        comm=_num(record.get(cols["comm"])),
        lrg=(None if is_equity else _num(record.get(cols.get(models.LEG_LARGE)))),
        sml=(None if is_equity else _num(record.get(cols.get(models.LEG_SMALL)))),
        state=record.get(SETUP_COLUMN[model.key]) or const.SETUP_NONE,
    )


def build_rows(df, show_all=False, compare=None):
    """`(rows, hidden, unplaced)` for one Signal Matrix frame.

    `compare` is the models to put side by side, defaulting to all of MODEL_ORDER.
    Splits and dimming follow the DISPLAYED models only: a market that disagrees only
    with a model the reader has switched off is an agreement on this view of the
    page, exactly as the Strip's filters count hidden markets against what is drawn.

    `hidden` counts agreeing markets the differences-only view dropped, so the caption
    can say "34 markets agree and are hidden" rather than presenting three rows as the
    whole book. `unplaced` names markets missing a Commercial reading on either basis:
    they cannot be compared at all, which is a different fact from agreeing. The basis
    gap keeps its meaning at any width, because it is raw against the one normalized
    series both NPF models share.

    Sorting inside a class puts verdict splits first, then the widest basis gaps, so
    the eye meets the strongest disagreements at the top of every block. Classes keep
    the frame's own order, which is the order every other page presents the book in.
    """
    compare = tuple(compare) if compare else MODEL_ORDER
    by_class, hidden, unplaced = {}, 0, []
    for record in df.to_dict("records"):
        asset = record.get("Asset")
        is_equity = bool(record.get(const.IS_EQUITY_COL))
        reads = tuple(_read_for(record, m, is_equity) for m in compare)

        raw_comm = _num(record.get("Comm Index"))
        norm_comm = _num(record.get("Comm Index Norm"))
        if raw_comm is None or norm_comm is None:
            unplaced.append(asset)
            continue
        gap = abs(raw_comm - norm_comm)

        split = len({r.state for r in reads}) > 1
        # Value disagreement follows the DISPLAYED columns across every leg,
        # the same rule the renderer's per-leg emphasis reads: a row whose
        # Commercials agree while a spec leg differs widely is not an
        # agreement (the widening this replaces keyed on the Commercial gap
        # alone and dimmed exactly that row). A single column has no pair on
        # any leg, so the frame's own basis gap keeps differentiating there,
        # which is the one-column behaviour pinned by test.
        spreads = [s for s in (leg_spread(reads, leg)
                               for leg in ("comm", "lrg", "sml"))
                   if s is not None]
        value_gap = max(spreads) if spreads else gap
        dim = not split and value_gap < GAP_TOLERANCE
        if dim and not show_all:
            hidden += 1
            continue
        row = DivergenceRow(kind="market", label=asset,
                            asset_class=record.get("Asset Class"),
                            reads=reads, gap=gap, split=split, dim=dim,
                            is_equity=is_equity)
        by_class.setdefault(row.asset_class, []).append(row)

    rows = []
    for asset_class, markets in by_class.items():
        markets.sort(key=lambda r: (not r.split, -(r.gap or 0), r.label))
        rows.append(DivergenceRow(kind="class", label=asset_class,
                                  asset_class=asset_class))
        rows.extend(markets)
    return rows, hidden, unplaced
