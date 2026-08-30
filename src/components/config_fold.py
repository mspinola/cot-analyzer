"""One foldable wrapper for a page's configuration area.

Every analytics page opens with a card of controls, and on a phone that card is
the whole first screen: a visitor scrolls past Lookback, Model and the rest
before seeing the thing the page exists to show. The Strip and the Positioning
table each solved this on their own (a bespoke Collapse with a summary line, an
Accordion started collapsed); this is the same move packaged once, so the other
pages can adopt it without each inventing ids and callbacks.

The default is where the phone fix lives: OPEN on a desktop, FOLDED on a mobile
user agent, decided server-side per request with the same sniff
`plot_layout.visible_weeks` already uses to narrow the x-window. Desktop
behaviour is unchanged by design, since the controls being visible is right on a
screen with room for them. An explicit toggle is remembered per page in
localStorage and wins over the default on the next load, because a reader who
opened the controls on a phone meant it.

One clientside callback serves every page via pattern-matching ids; `wrap` is
the whole public surface. The stored preference is applied in the browser
rather than at render time because the server cannot read localStorage; the
cost is that a stored choice that disagrees with the UA default applies a beat
after first paint, which only affects readers who overrode the default.
"""

import dash_bootstrap_components as dbc
import flask
from dash import MATCH, Input, Output, State, clientside_callback, dcc, html

import app_utils

_OPEN_LABEL = "▾ Configuration"
_SHUT_LABEL = "▸ Configuration"


def _open_by_default():
    # No request context means a test importing a layout; open is the answer that
    # hides nothing.
    if not flask.has_request_context():
        return True
    return not app_utils.is_mobile()


def wrap(page, children):
    """The page's controls behind a fold: a toggle, the collapse, and the store
    that remembers an explicit choice. `page` keys the store, so it must be
    unique per page and stable across releases (it names a localStorage entry).
    """
    is_open = _open_by_default()
    return html.Div([
        dcc.Store(id={'type': 'config_fold_open', 'page': page},
                  storage_type='local'),
        dbc.Button(_OPEN_LABEL if is_open else _SHUT_LABEL,
                   id={'type': 'config_fold_toggle', 'page': page},
                   size="sm", color="secondary", outline=True,
                   className="py-0"),
        dbc.Collapse(children,
                     id={'type': 'config_fold_collapse', 'page': page},
                     is_open=is_open, className="mt-2"),
    ])


# On load (no clicks yet) an explicitly stored choice is applied and the UA
# default is otherwise left alone; a click toggles and persists. The label is
# only written when the state is, so the server-rendered one stands until then.
clientside_callback(
    """
    function(n_clicks, stored, is_open) {
        const nu = window.dash_clientside.no_update;
        const label = function(open) {
            return (open ? '▾' : '▸') + ' Configuration';
        };
        if (!n_clicks) {
            if (stored !== true && stored !== false) { return [nu, nu, nu]; }
            if (stored === is_open) { return [nu, nu, nu]; }
            return [stored, nu, label(stored)];
        }
        const open = !is_open;
        return [open, open, label(open)];
    }
    """,
    Output({'type': 'config_fold_collapse', 'page': MATCH}, 'is_open'),
    Output({'type': 'config_fold_open', 'page': MATCH}, 'data'),
    Output({'type': 'config_fold_toggle', 'page': MATCH}, 'children'),
    Input({'type': 'config_fold_toggle', 'page': MATCH}, 'n_clicks'),
    State({'type': 'config_fold_open', 'page': MATCH}, 'data'),
    State({'type': 'config_fold_collapse', 'page': MATCH}, 'is_open'),
)
