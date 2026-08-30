"""One "How to read this" fold, for pages whose explainer had become a wall.

Exposure established the split this packages: the page keeps its FACTS visible
(the date, the basis, what was hidden or unreadable this week, anything that
changes what the reader should conclude) and folds the TEACHING (what a cell
is, how the colours work, the traps) behind one small toggle. Shut by default,
because the teaching is worth one click the first time and is a third of a
screen of italic prose on every visit after; Crowd and Divergence opened with
seven-line paragraphs before this. An explicit open is remembered per page in
localStorage, so the reader still learning keeps it open without asking again.

Same shape as config_fold: pattern-matching ids, one clientside callback for
every adopting page. Unlike config_fold there is no per-device default, since
the right resting state is shut on every screen size.

The BODY is the page's business and usually a callback target (a div the
page's render callback fills), because half of this prose is dynamic: which
model's verdict the chip carries, whether two shown columns share a series.
"""

import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, clientside_callback, dcc, html


def wrap(page, body):
    """The fold: toggle plus collapse around `body`, shut until asked.

    `page` keys the localStorage entry, so it must be unique and stable.
    """
    return html.Div([
        dcc.Store(id={'type': 'help_fold_open', 'page': page},
                  storage_type='local'),
        dbc.Button("▸ How to read this",
                   id={'type': 'help_fold_toggle', 'page': page},
                   size="sm", color="secondary", outline=True,
                   className="py-0 mb-2"),
        dbc.Collapse(body, id={'type': 'help_fold_collapse', 'page': page},
                     is_open=False, className="mb-2"),
    ])


# On load, only a stored True does anything: it reopens the fold for the reader
# who left it open. Anything else keeps the shut default. A click toggles and
# persists.
clientside_callback(
    """
    function(n_clicks, stored, is_open) {
        const nu = window.dash_clientside.no_update;
        const label = function(open) {
            return (open ? '▾' : '▸') + ' How to read this';
        };
        if (!n_clicks) {
            if (stored !== true || is_open) { return [nu, nu, nu]; }
            return [true, nu, label(true)];
        }
        const open = !is_open;
        return [open, open, label(open)];
    }
    """,
    Output({'type': 'help_fold_collapse', 'page': MATCH}, 'is_open'),
    Output({'type': 'help_fold_open', 'page': MATCH}, 'data'),
    Output({'type': 'help_fold_toggle', 'page': MATCH}, 'children'),
    Input({'type': 'help_fold_toggle', 'page': MATCH}, 'n_clicks'),
    State({'type': 'help_fold_open', 'page': MATCH}, 'data'),
    State({'type': 'help_fold_collapse', 'page': MATCH}, 'is_open'),
)
