"""The asset-class control, once, for every page that picks more than one class.

Three pages asked the same question in three visual languages: nine inline switches
spanning half a control row (heatmap, strip, graphs), a plain multi-dropdown
(exposure, positioning), and a black-bordered pill group. The switches are the version
that costs the most width for the answer you give nearly every time, which is "all of
them".

This collapses them behind one toggle that STATES the current answer, so the control
does not have to be opened to be trusted. That is most of what leaving nine switches
on show was buying.

Deliberately not `dcc.Dropdown(multi=True)`, which Dash gives a native "9 selected"
collapse and a search box: with nine fixed options a search box is furniture, and
"All asset classes" is a more useful thing for a control to say about itself than "9
selected". What that dropdown does have and a bare checklist does not is a way back to
everything in one click, so Select all / Clear is part of this rather than an extra.

The checklist inside keeps the page's own element id, so every callback already
reading it is untouched: this is a container, not a new control.
"""
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from dash import Input, Output, callback, ctx, html

import viz_constants as vc


def menu_id(checklist_id):
    return f"{checklist_id}__menu"


def _all_id(checklist_id):
    return f"{checklist_id}__all"


def _none_id(checklist_id):
    return f"{checklist_id}__none"


def menu_label(selected, every):
    """What the collapsed control says about itself while shut.

    Names the classes while there are few enough to read, counts them after that. The
    count carries its own denominator because "3 classes" and "3 of 9 classes" answer
    different questions, and the second is the one a reader looking at a filtered page
    is asking.
    """
    if not selected:
        return "No asset classes"
    if len(selected) == len(every):
        return "All asset classes"
    if len(selected) <= 2:
        return ", ".join(selected)
    return f"{len(selected)} of {len(every)} classes"


_TOGGLE_STYLE = {
    "backgroundColor": "transparent",
    "borderColor": "rgba(147, 161, 161, 0.3)",
    "borderRadius": "8px",
    "color": vc.BRIGHTER_TEXT_COLOR,
    "width": "100%",
    "textAlign": "left",
    "fontSize": "0.9rem",
}

_LINK_STYLE = {"fontSize": "0.7rem", "textTransform": "uppercase",
               "letterSpacing": "0.04em", "padding": "0", "border": "none",
               "backgroundColor": "transparent", "color": vc.TEXT_COLOR}


def control(checklist_id, classes, value=None, *, min_width="220px"):
    """The collapsed control. `classes` is this page's own class list and order."""
    return dbc.DropdownMenu(
        id=menu_id(checklist_id),
        label=menu_label(value if value is not None else classes, classes),
        color="dark",
        toggle_style=_TOGGLE_STYLE,
        className="w-100 class-filter-menu",
        children=html.Div([
            html.Div([
                dbc.Button("Select all", id=_all_id(checklist_id), size="sm",
                           style=_LINK_STYLE, className="p-0"),
                html.Span("·", style={"opacity": 0.4}),
                dbc.Button("Clear", id=_none_id(checklist_id), size="sm",
                           style=_LINK_STYLE, className="p-0"),
            ], style={"display": "flex", "gap": "10px", "alignItems": "center",
                      "paddingBottom": "8px", "marginBottom": "6px",
                      "borderBottom": "1px solid rgba(255,255,255,0.10)"}),
            dbc.Checklist(
                persistence="session",
                id=checklist_id,
                options=[{"label": c, "value": c} for c in classes],
                value=classes if value is None else value,
                switch=True,
                style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.9rem"},
            ),
        ], style={"padding": "10px 14px", "minWidth": min_width}),
    )


def register(checklist_id, classes=None):
    """Wire one instance's label and its two shortcuts.

    Called at module scope by the page, not inside `layout()`: a Dash page's layout
    function runs per request, and registering there would re-register on every one.

    `classes` may be a list or a callable. A callable is the safer form for the
    shortcut, which writes the value rather than reading it: a list captured at import
    would keep writing a universe the store has since changed.
    """
    if classes is None:
        classes = get_indexer().get_asset_classes

    def every():
        return list(classes() if callable(classes) else classes)

    @callback(
        Output(menu_id(checklist_id), "label"),
        Input(checklist_id, "value"),
    )
    def _label(selected):
        return menu_label(selected or [], every())

    @callback(
        Output(checklist_id, "value"),
        Input(_all_id(checklist_id), "n_clicks"),
        Input(_none_id(checklist_id), "n_clicks"),
        prevent_initial_call=True,
    )
    def _shortcut(_all_clicks, _none_clicks):
        return every() if ctx.triggered_id == _all_id(checklist_id) else []
