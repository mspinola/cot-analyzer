"""One place that knows what a plot *is*.

A plot used to be described by five parallel structures scattered across four pages:
a label in the page's `AVAILABLE_PLOTS`, a membership test in a `has_secondary` list,
a branch in an `if/elif` dispatch chain, a flag in `viz_constants.BASIS_AWARE_PLOTS`,
and an entry in `plot_helpers.BASIS_OVERLAY_SPEC`. Nothing tied them together, so
adding or removing one panel meant finding all five in every page that offered it.
Retiring the Structural Synthesis panel took edits in six files and still left a
stale column definition behind on the Heatmap.

`viz_constants.BASIS_AWARE_PLOTS` already made this argument for one of the five
facts: it lives away from the pages because "a plot that counts as basis-aware on one
of them but not another is a bug waiting to happen." This module finishes that thought
for the rest.

What lives here is a plot's *identity and capability*: its label, how to draw it, and
what it can do (secondary axis, basis awareness, overlay). What deliberately does NOT
live here is each page's **basis-resolution policy**, because those genuinely differ.
OI Alignment and Graphs apply one page-wide model to every panel; Analysis offers
per-panel variants (`index_oinorm`, `index_both`); Aggregation has no basis concept at
all and draws from a frame aggregated across assets. A page resolves which frame a
panel should draw from and hands it over in `PlotCtx.df`.

The builders in `plot_helpers` are visually tuned and have no automated coverage, so
nothing here rewrites them. Each spec holds a thin adapter that unpacks a `PlotCtx`
and calls the existing function unchanged. That is also why the builders' mismatched
signatures are not a problem: `get_max_pain_plot` takes an asset name and no frame at
all, and the adapter absorbs that difference instead of the caller.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import cotmetrics.constants as const

import viz_constants as vc


def _helpers():
    """`plot_helpers`, imported on first draw rather than at module load.

    `plot_helpers` pulls in `cotmetrics.indexer`, which builds its singleton at import
    time and raises if the data store is empty. Most of this module is metadata that
    page layout code reads without drawing anything, and tests read without a store at
    all, so the plotting stack is deferred until a builder actually runs.
    """
    import components.plot_helpers as helpers
    return helpers


# The generic alias columns CotIndexer.get_symbols_data puts on every frame. They are
# already resolved for lookback and basis, so a panel never re-selects by basis here.
IDX_COLS = (const.COMMS_IDX, const.LRG_IDX, const.SML_IDX)


@dataclass
class PlotCtx:
    """Everything a builder might need, assembled by the page.

    The page owns basis resolution, so `df` is already the frame this panel should
    draw. `df_norm` is only for the overlay, which is the one panel type that needs
    both bases at once.
    """
    fig: object
    row: int
    col: int
    palette: list
    df: object = None
    df_norm: object = None
    show_price: bool = True
    asset: str = None
    model: object = None
    # Net-position column triple, basis-resolved by the page. Aggregation passes the
    # raw constants directly because its frame carries no aliases.
    net_cols: Tuple[str, str, str] = (const.COMM_NET, const.LARGE_NET, const.SMALL_NET)
    idx_cols: Tuple[str, str, str] = IDX_COLS
    y_title: str = "net position"
    price_scale: str = "linear"
    showlegend: bool = True
    setup_comms_only: bool = False
    smooth_indexing: bool = False


# When a panel needs a secondary y-axis.
#
# Not a boolean, because two panels put a series on the secondary axis that has
# nothing to do with the price overlay: Net Positions draws Open Interest there and
# Max-Pain Premium draws Delta IV. Those stay on a secondary axis even where price is
# switched off, which is exactly the case on Aggregation.
SECONDARY_NEVER = "never"
SECONDARY_WITH_PRICE = "price"
SECONDARY_ALWAYS = "always"


@dataclass(frozen=True)
class PlotSpec:
    id: str
    label: str
    build: Callable[[PlotCtx], object]
    secondary_y: str = SECONDARY_NEVER
    # Reads a level of net positioning, so dividing by open interest changes it.
    basis_aware: bool = False
    # (value_col, y_title, y_range, zero_line) for drawing both bases on one axis.
    overlay: Optional[tuple] = None
    # Why the basis control does not apply, shown in the UI next to a disabled control.
    invariant_note: Optional[str] = None
    # Draws from an asset name rather than a frame (the options curves).
    needs_asset: bool = False
    # Second pass after the traces land, e.g. shading setup clusters.
    decorate: Optional[Callable[[PlotCtx], object]] = None


# --- adapters -------------------------------------------------------------------
# Each one unpacks a ctx and calls the existing plot_helpers builder unchanged.

def _price(ctx):
    h = _helpers()
    return h.get_price_plot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                            ctx.price_scale)


def _oi_pct(ctx):
    h = _helpers()
    return h.get_open_interest_percent_plot(ctx.fig, ctx.df, ctx.row, ctx.col,
                                            ctx.palette, ctx.show_price)


def _net_pos(ctx):
    h = _helpers()
    comm, lrg, sml = ctx.net_cols
    return h.get_net_pos_plot(ctx.fig, ctx.df, comm, lrg, sml, ctx.row, ctx.col,
                              ctx.palette, show_price=ctx.show_price,
                              y_title=ctx.y_title)


def _index(ctx):
    h = _helpers()
    comm, lrg, sml = ctx.idx_cols
    low = ctx.model.low if ctx.model else None
    high = ctx.model.high if ctx.model else None
    return h.get_index_plot(ctx.fig, ctx.df, comm, lrg, sml, ctx.row, ctx.col,
                            ctx.palette, low, high, ctx.show_price,
                            ctx.smooth_indexing)


def _setup_highlight(ctx):
    """Shade extreme clusters. Judged by the panel's own model, never a page-wide band."""
    if ctx.model is None:
        return ctx.fig
    h = _helpers()
    comm, lrg, sml = ctx.idx_cols
    return h.get_setup_highlighting(ctx.fig, ctx.df, comm, lrg, sml, ctx.model,
                                    ctx.row, ctx.col, ctx.setup_comms_only)


def _zscore(ctx):
    h = _helpers()
    return h.get_zscore_plot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                             ctx.show_price)


def _momentum(ctx):
    h = _helpers()
    return h.get_momentum_plot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                               ctx.show_price)


def _willco(ctx):
    h = _helpers()
    return h.get_willco_plot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                             ctx.show_price)


def _spearman(ctx):
    h = _helpers()
    return h.get_spearman_plot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                               ctx.show_price)


def _macd(ctx):
    h = _helpers()
    return h.get_cot_macd_subplot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                                  ctx.show_price)


def _lrg_sentiment(ctx):
    h = _helpers()
    return h.get_lrg_sentiment_plot(ctx.fig, ctx.df, ctx.row, ctx.col, ctx.palette,
                                    ctx.show_price)


def _max_pain(ctx):
    return _helpers().get_max_pain_plot(ctx.fig, ctx.asset, ctx.row, ctx.col)


def _max_pain_historical(ctx):
    h = _helpers()
    return h.get_max_pain_historical_plot(ctx.fig, ctx.asset, ctx.row, ctx.col,
                                          showlegend=ctx.showlegend)


# --- the registry ---------------------------------------------------------------

_SPECS = [
    # Both price panels draw the same candles. They stay separate ids because they do
    # not behave the same: OI Alignment overlays its decorators on the price panel and
    # keeps it on a single axis, while Analysis puts price on a secondary axis and
    # shades setup clusters. Session-persisted selections also already use both names.
    PlotSpec("oi_alignment", "OI Alignment", _price),
    PlotSpec("price_candles", "Price (Candles)", _price,
             secondary_y=SECONDARY_WITH_PRICE, decorate=_setup_highlight),

    PlotSpec("macd", "Commercial Net Positioning MACD", _macd,
             secondary_y=SECONDARY_WITH_PRICE),
    # The id stays a literal. "willco" is also a frame column (const.WILLCO_ALIAS),
    # but a plot id is a picker key, not a column name, and the two only happen to
    # spell the same. Swapping in the constant here would read as a claim that a
    # panel is named after the column it draws, which is true of no other spec.
    PlotSpec("willco", "WillCo", _willco, secondary_y=SECONDARY_WITH_PRICE,
             invariant_note="already normalized by OI"),

    PlotSpec("index", "Positioning Index", _index, secondary_y=SECONDARY_WITH_PRICE,
             basis_aware=True, overlay=(const.COMMS_IDX, "Index", [0, 100], False),
             decorate=_setup_highlight),
    PlotSpec("momentum", vc.MOMENTUM_LABEL, _momentum,
             secondary_y=SECONDARY_WITH_PRICE, basis_aware=True,
             overlay=(const.COMM_MOMENTUM, vc.MOMENTUM_LABEL, None, True)),
    PlotSpec("zscore", "Positioning Z-Score", _zscore,
             secondary_y=SECONDARY_WITH_PRICE, basis_aware=True,
             overlay=(const.COMMS_ZSCORE, "Z-Score", None, True)),
    PlotSpec("spearman", "Spearman Correlation", _spearman,
             secondary_y=SECONDARY_WITH_PRICE, basis_aware=True,
             overlay=(const.COMMS_SPEARMAN, "Correlation", [-1, 1], True)),
    # Basis-aware but cannot overlay: contracts and a fraction of open interest share
    # no scale. Its secondary axis carries Open Interest, not price, so it holds even
    # where price is switched off.
    PlotSpec("net_pos", "Net Positions", _net_pos, secondary_y=SECONDARY_ALWAYS,
             basis_aware=True),

    PlotSpec("oi_pct", "Net Position % of OI", _oi_pct,
             secondary_y=SECONDARY_WITH_PRICE,
             invariant_note="already normalized by OI"),
    PlotSpec("lrg_sentiment", "Large Trader Sentiment", _lrg_sentiment,
             secondary_y=SECONDARY_WITH_PRICE),

    PlotSpec("max_pain", "Max Pain Options Curve", _max_pain, needs_asset=True,
             invariant_note="not a COT metric"),
    # Secondary axis carries Delta IV rather than price.
    PlotSpec("max_pain_historical", "Price Premium/Discount to Max-Pain Price",
             _max_pain_historical, secondary_y=SECONDARY_ALWAYS, needs_asset=True,
             invariant_note="not a COT metric"),
]

REGISTRY = {s.id: s for s in _SPECS}


# --- derived views --------------------------------------------------------------
# The metadata the pages already consume, now computed from one source rather than
# maintained as separate literals that can drift apart.

BASIS_AWARE_PLOTS = {s.id for s in _SPECS if s.basis_aware}

BASIS_OVERLAY_SPEC = {s.id: s.overlay for s in _SPECS if s.overlay is not None}

BASIS_INVARIANT_NOTE = {s.id: s.invariant_note for s in _SPECS
                        if s.invariant_note is not None}


# --- shared helpers -------------------------------------------------------------

def labels_for(ids, overrides=None):
    """`{id: label}` for a page's picker, in the order given.

    `overrides` lets a page reword a panel whose meaning shifts in its context, e.g.
    Aggregation showing "Net Positions (Sum)" for a frame summed across assets.
    """
    overrides = overrides or {}
    return {i: overrides.get(i, REGISTRY[i].label) for i in ids if i in REGISTRY}


def sanitize_selection(selected, available):
    """Drop ids that no longer exist.

    Plot pickers persist per session, so a saved selection can name a panel that has
    since been retired. Without this the page renders a hole in the grid, or indexes
    a label dict that no longer has the key.
    """
    if not selected:
        return []
    return [p for p in selected if p in available]


def uses_secondary_y(plot_id, show_price=True):
    """Whether this panel needs a secondary axis, given whether price is drawn."""
    spec = REGISTRY.get(plot_id)
    if spec is None:
        return False
    if spec.secondary_y == SECONDARY_ALWAYS:
        return True
    if spec.secondary_y == SECONDARY_WITH_PRICE:
        return bool(show_price)
    return False


def subplot_specs(selected, show_price, num_cols):
    """The `specs` grid make_subplots needs, one cell per selected panel.

    Replaces the `has_secondary` literal list each page kept inline, which had to be
    edited in lockstep with the dispatch chain right below it.
    """
    import math

    rows = math.ceil(len(selected) / num_cols) if selected else 0
    grid = []
    idx = 0
    for _ in range(rows):
        row_specs = []
        for _ in range(num_cols):
            if idx < len(selected):
                row_specs.append(
                    {"secondary_y": uses_secondary_y(selected[idx], show_price)})
                idx += 1
            else:
                row_specs.append(None)  # empty cell in the grid
        grid.append(row_specs)
    return grid


def etf_symbol_for(instrument):
    """The ticker the options curves are actually quoted on, often a proxy ETF.

    Returns None when there is nothing to name, so a caller can leave its title alone.
    """
    symbol = getattr(instrument, "symbol", None)
    if not symbol:
        return None
    from cotmetrics.options_data import ETF_PROXIES
    return ETF_PROXIES.get(symbol, symbol)


def plot_title(plot_id, asset=None, instrument=None, basis_view=None, is_overlay=False,
               label=None):
    """Subplot title for one panel.

    The options curves name the ETF actually quoted, which is often a proxy rather than
    the futures symbol, so the title has to say which one it used. Only panels that
    actually responded to the basis get it in their title: labelling every panel on a
    stacked page would claim the invariant ones changed when they did not.
    """
    spec = REGISTRY.get(plot_id)
    title = label if label is not None else (spec.label if spec else plot_id)

    if spec is not None and spec.needs_asset and instrument is not None:
        etf = etf_symbol_for(instrument)
        if etf:
            if plot_id == "max_pain":
                return f"Options Max Pain ({asset} via {etf})"
            return f"Price Premium/Discount to Max-Pain Price ({asset} via {etf})"
        return title

    if basis_view is not None and spec is not None and spec.basis_aware:
        if is_overlay and spec.overlay is not None:
            return f"{title} (Raw vs % of OI)"
        if is_overlay:
            # Basis-aware but cannot overlay, so it fell back to raw. Say so rather
            # than leaving the one unlabelled panel in a labelled stack.
            return f"{title} ({vc.BASIS_LABELS[const.BASIS_RAW]})"
        return f"{title} ({vc.BASIS_LABELS[basis_view]})"

    return title
