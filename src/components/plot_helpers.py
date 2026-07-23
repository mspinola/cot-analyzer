"""Facade over the plot modules.

This file was 1668 lines holding four unrelated jobs: colour maths, figure geometry,
the traces themselves, and the options-derived panels. They are now four modules, and
this re-exports them so `import components.plot_helpers as helpers` keeps working.

The same was done for the signal cards, whose re-export is still at the bottom.

Prefer importing the specific module in new code. `plot_layout` and `plot_colors` in
particular carry no data dependency, so a caller that only needs figure geometry does
not have to drag the indexer in to get it.

    components.plot_colors    hex maths, no figure involved
    components.plot_layout    subplot grids, axis ranges, heights, the layout pass
    components.plot_traces    one function per panel, plus shared trace primitives
    components.plot_options   the max-pain curve and its premium/discount history
"""

# Everything below is re-exported for callers rather than used here.

from components.plot_colors import (  # noqa: F401
    hex_to_rgba,
    lighten_hex,
)
from components.plot_layout import (  # noqa: F401
    get_figure_height,
    get_make_subplots_for_plots,
    get_nice_dtick,
    get_no_data_html_p,
    get_plot_area_height,
    get_update_layout_for_plots,
    get_update_xaxes_for_plots,
    pixels_per_plot_for_cols,
)
from components.plot_options import (  # noqa: F401
    get_max_pain_historical_plot,
    get_max_pain_plot,
)
from components.plot_traces import (  # noqa: F401
    add_legend_lines,
    add_legend_markers,
    add_open_interest_legend,
    add_trace_to_all,
    add_trend_regime_highlighting,
    fast_add_vrects,
    get_basis_overlay_plot,
    get_cot_macd_subplot,
    get_index_plot,
    get_lrg_sentiment_plot,
    get_momentum_plot,
    get_net_pos_plot,
    get_oi_alignment_decorators,
    get_open_interest_percent_plot,
    get_price_plot,
    get_setup_highlighting,
    get_spearman_plot,
    get_willco_plot,
    get_zscore_plot,
    update_legend,
)

# ---------------------------------------------------------------------------
# Signal card components live in their own module.
# Re-exported here so existing callers (helpers.build_signal_panel etc.) keep working.
# ---------------------------------------------------------------------------
from components.signal_cards import (  # noqa: E402, F401
    build_accordion_skeleton,
    build_asset_class_cards,
    build_mobile_asset_card,
    build_signal_panel,
)
