"""The weekly-email subscribe form: one input, one button, one status line.

A component rather than About-page code so a second surface (a Home banner, say)
can render the same card without a second callback. The callback registers at
import, the shared-controls rule: layout runs per request, wiring must not.

What the form promises is decided here, in the copy: one email per COT week, a
confirmation click before anything recurring, an unsubscribe link in every mail.
The machinery behind each promise is `subscribers`; this module only talks to it.
"""
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html
from flask import request

import subscribers
import visitors
import viz_constants as vc


def card():
    return dbc.Card(
        dbc.CardBody([
            html.H5("Get the weekly Signal Matrix by email",
                    style={"color": vc.BRIGHTER_TEXT_COLOR}),
            html.P(
                "One email per COT week, sent when the new CFTC report lands: "
                "the same Signal Matrix the Heatmap shows, with the CSV "
                "attached. A confirmation link comes first, and every email "
                "carries an unsubscribe link.",
                style={"color": vc.TEXT_COLOR, "fontSize": "0.9rem"}),
            dbc.InputGroup([
                dbc.Input(id="subscribe_email", type="email",
                          placeholder="you@example.com", debounce=True,
                          className="bg-dark text-white border-secondary"),
                dbc.Button("Subscribe", id="subscribe_btn", color="secondary",
                           outline=True),
            ], style={"maxWidth": "420px"}),
            html.Div(id="subscribe_status", role="status",
                     style={"color": vc.TEXT_COLOR, "fontSize": "0.85rem",
                            "marginTop": "6px", "minHeight": "1.2em"}),
        ]),
        className="mb-4 shadow-sm",
        style={
            "backgroundColor": "rgba(30, 30, 30, 0.6)",
            "border": "1px solid rgba(255, 255, 255, 0.1)",
            "borderRadius": "12px",
        },
    )


@callback(
    Output("subscribe_status", "children"),
    Input("subscribe_btn", "n_clicks"),
    Input("subscribe_email", "n_submit"),
    State("subscribe_email", "value"),
    prevent_initial_call=True,
)
def handle_subscribe(_clicks, _submit, email):
    """Validate, record, mail the confirmation link, and say what happened.

    Every branch answers in a sentence rather than a code, because the reader is
    a visitor, not a log. The one message that lies a little is 'confirmed':
    it reads the same as 'pending' on purpose, so the form cannot be used to
    test whether an arbitrary address is on the list.
    """
    ip = visitors.client_ip(request.headers.get("X-Forwarded-For"),
                            request.remote_addr)
    if not subscribers.allow_attempt(ip):
        return "Too many attempts from your address; try again in an hour."

    status, token = subscribers.subscribe(email)
    if status == "invalid":
        return "That does not look like an email address."
    if status == "confirmed":
        # Same sentence as the pending branch, no email sent: an address already
        # on the list must not be re-mailable (or probeable) from a public form.
        return "Check that inbox: if the address is not already subscribed, a confirmation link is on its way."

    try:
        subscribers.send_confirmation(subscribers.normalize_email(email), token)
    except Exception as e:
        import cotmetrics.utils as utils
        utils.cot_logger.error(f"subscribers: confirmation send failed: {e}")
        return ("Subscriptions are not available right now; "
                "please try again later.")
    return "Check that inbox: if the address is not already subscribed, a confirmation link is on its way."
