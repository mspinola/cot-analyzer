"""The shared control kit: one definition for each control every page rebuilds.

Before this module the Lookback options literal was written out nine times, Model
selectors carried tooltips on three pages and not the other two, the same two-way
global-store sync was pasted per page with two different reconciliations of the
"both" view, and the Target Date week-follow callback existed on four of the five
pages that needed it. One definition each closes the drift; a page that wants the
control differently SIZED still says so, because geometry belongs to the layout
it sits in.

The split mirrors class_filter: a `*_select`/`*_dropdown` builder is called inside
`layout()` (per request, so importing a page still needs no store), and a
`register_*` function is called once at module scope to create the callbacks
(wiring must not run per request). Control ids are unchanged by adoption, so
nothing else that reads them moves.

Builders take `**overrides` merged over the shared kwargs. Semantic fields
(options, value, persistence) have one home here; `style=`, `size=`,
`className=` and friends are the page's business.
"""

import cotmetrics.models as models
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html, no_update

import viz_constants as vc

LOOKBACK_CHOICES = ("26", "52", "Custom")

#: The one caption style for a control label. Seven pages already used exactly
#: this dict inline; the H6 variant the chart pages carried was the same idea in
#: different type.
LABEL_STYLE = {**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}


def label(text, **style_overrides):
    return html.Label(text, style={**LABEL_STYLE, **style_overrides})


def _merged(base, overrides):
    base.update(overrides)
    return base


# ── Lookback ──────────────────────────────────────────────────────────────────

def lookback_select(control_id, **overrides):
    return dbc.Select(**_merged(dict(
        id=control_id,
        persistence='session',
        options=[
            {"label": "26 Weeks", "value": "26"},
            {"label": "52 Weeks", "value": "52"},
            {"label": "Custom", "value": "Custom"},
        ],
        value="Custom",
        className="bg-dark text-white border-secondary",
    ), overrides))


def _canon_lookback(value):
    return value if value in LOOKBACK_CHOICES else "Custom"


def register_lookback(control_id):
    """Two-way sync with `global_lookback_store`, so every page's Lookback is the
    same setting rather than nine settings that happen to share a name."""

    @callback(
        Output('global_lookback_store', 'data', allow_duplicate=True),
        Input(control_id, 'value'),
        State('global_lookback_store', 'data'),
        prevent_initial_call=True,
    )
    def to_global(value, current):
        new_val = _canon_lookback(value)
        return no_update if new_val == current else new_val

    @callback(
        Output(control_id, 'value'),
        Input('global_lookback_store', 'data'),
        State(control_id, 'value'),
    )
    def from_global(value, current):
        new_val = _canon_lookback(value)
        return no_update if new_val == current else new_val


# ── Model ─────────────────────────────────────────────────────────────────────

def model_options(choices):
    """Options with their tooltips, for the factory below AND for any callback
    that rewrites a model control's options later (the chart pages narrow them
    per plot). A callback that rebuilds options inline is how the tooltips
    disappeared at runtime on exactly the pages that narrow them."""
    return [{"label": vc.MODEL_LABELS[k], "value": k,
             "title": vc.MODEL_TOOLTIPS[k]} for k in choices]


def model_select(control_id, choices=vc.MODEL_CHOICES, **overrides):
    """`choices` is the page's stance on MODEL_BOTH: verdict pages offer the real
    models, the chart pages add the overlay view. Tooltips ride on every option;
    they used to exist on three pages and not the other two."""
    return dbc.Select(**_merged(dict(
        id=control_id,
        persistence='session',
        options=model_options(choices),
        value=models.DEFAULT_MODEL.key,
        className="bg-dark text-white border-secondary",
    ), overrides))


def register_model(control_id, choices=vc.MODEL_CHOICES):
    """Two-way sync with `global_model_store`.

    The store can hold MODEL_BOTH (a chart page wrote it) while this control does
    not offer it. One reconciliation for that, everywhere: resolve to the model
    the overlay draws as its baseline (`vc.resolve_model_view`), which is also
    where a stale key lands, since `models.resolve` answers unknowns with the
    default. Strip and Crowd used to jump straight to the default instead of
    resolving; for every value that exists today the two rules agree, so this is
    a unification, not a change.
    """

    @callback(
        Output('global_model_store', 'data', allow_duplicate=True),
        Input(control_id, 'value'),
        State('global_model_store', 'data'),
        prevent_initial_call=True,
    )
    def to_global(value, current):
        new_val = value if value in choices else models.DEFAULT_MODEL.key
        return no_update if new_val == current else new_val

    @callback(
        Output(control_id, 'value'),
        Input('global_model_store', 'data'),
        State(control_id, 'value'),
    )
    def from_global(value, current):
        new_val = value if value in choices else vc.resolve_model_view(value)[0].key
        return no_update if new_val == current else new_val


# ── Target Date ───────────────────────────────────────────────────────────────

def target_date_dropdown(control_id, **overrides):
    # Imported here, not at module scope: the dates need the indexer, and
    # importing this module (tests, tooling) must not.
    from cotmetrics.indexer import get_indexer
    dates = get_indexer().get_available_dates()
    return dcc.Dropdown(**_merged(dict(
        id=control_id,
        options=[{'label': d, 'value': d} for d in dates],
        value=dates[0] if dates else None,
        className="dash-dropdown bg-dark text-white",
        searchable=True,
        clearable=False,
        style={'borderRadius': '8px'},
    ), overrides))


def week_for_store(value, dates):
    """What a selection is WORTH REMEMBERING as, for `global_week_store`.

    None means "tracking the newest week": picking the current newest is the
    default nobody chose, and storing its concrete date would pin every page to
    it the moment a release made it old. Only a deliberately chosen OLDER week
    is stored as itself. This is `next_date_selection`'s was-on-newest test,
    moved from per-control arithmetic into the stored value, which is what lets
    five pages share one answer.
    """
    if not dates or not value or value == dates[0] or value not in dates:
        return None
    return value


def resolve_week(stored, dates):
    """The week a Target Date control should show for a stored value.

    None (tracking) and a stale date (a week list this session has never seen,
    which full history makes near-impossible but a cleared store does not) both
    land on the newest week, because "the newest" is the only answer that is
    never a lie.
    """
    if not dates:
        return None
    if stored and stored in dates:
        return stored
    return dates[0]


def register_target_date(control_id):
    """Sync with `global_week_store`, and re-offer the weeks on a release.

    One as-of week for the whole visit: park the Heatmap on an old week and the
    Strip shows the same week on arrival, exactly as model and lookback already
    travel. A tab sitting on the newest week follows a Friday release (the store
    holds None, which resolves to whatever is newest NOW); one parked on an
    older week stays put with the new week offered in the dropdown. That split
    used to live in `next_date_selection` per control and could not be shared;
    encoding it in the stored value is what makes it global. Every page with a
    Target Date gets all of this by construction; Positioning shipped without
    even the release-follow and stranded open tabs on release day.
    """
    from cotmetrics.indexer import get_indexer

    @callback(
        Output(control_id, 'options'),
        Output(control_id, 'value'),
        Input('cot_release_store', 'data'),
        Input('global_week_store', 'data'),
        State(control_id, 'options'),
        State(control_id, 'value'),
    )
    def follow(_release, stored, current_options, current_value):
        dates = get_indexer().get_available_dates()
        if not dates:
            return no_update, no_update
        options = [{'label': d, 'value': d} for d in dates]
        value = resolve_week(stored, dates)
        # no_update on the quiet paths, or the five-minute release tick would
        # re-render the control and re-fire the page's grid callback for every
        # open tab that changed nothing.
        return (no_update if options == current_options else options,
                no_update if value == current_value else value)

    @callback(
        Output('global_week_store', 'data', allow_duplicate=True),
        Input(control_id, 'value'),
        State('global_week_store', 'data'),
        prevent_initial_call=True,
    )
    def to_global(value, stored):
        if not value:
            return no_update
        new_val = week_for_store(value, get_indexer().get_available_dates())
        return no_update if new_val == stored else new_val
