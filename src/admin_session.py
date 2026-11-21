"""Whether a request comes from a browser that logged in at /admin.

Its own module (2026-11-21) so a page other than /admin can ask the same question
without importing that page: Dash's page loader registers pages under names their
parent package does not bind, so a plain import of `pages.system.admin` would load a
second copy. `pages.system.admin` re-exports both names.
"""
from flask import has_request_context, session

#: The flag a correct password sets in Flask's session. Server-signed (see the
#: secret_key note in app_cot), so a request cannot simply claim it the way it
#: could claim the old store value.
SESSION_FLAG = 'cot_admin'


def is_admin():
    """Did THIS request come from a browser that logged in?

    Read from the signed session cookie, never from a callback Input. The browser's
    `session_admin_auth` store still carries "AUTHORIZED" after a login, but only
    to decide which half of the page to show: it is request data, and anything a
    request says about itself is exactly what a forged request would say. Outside a
    request (a layout built at start-up) the answer is no.
    """
    return has_request_context() and session.get(SESSION_FLAG) is True
