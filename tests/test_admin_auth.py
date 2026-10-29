"""The admin page answers only a browser that logged in, whatever a request claims.

Until 2026-10-29 the admin "login" was the string "AUTHORIZED" in a browser-side
store, and the stats callback checked the value the request carried for it. A
callback's Inputs are just the request body, so one POST to
/_dash-update-component with that string and no password returned the visitor
log and the server log tail. The restart, poll and send callbacks checked
nothing at all. These drive each callback with exactly that forged request and
assert it is refused, then repeat the read callbacks from a logged-in session
and assert they answer.

Every subprocess entry point is replaced with one that fails the test, so a
broken guard shows up as a failure here rather than as this machine restarting
the app, polling the CFTC or mailing anyone.
"""
import importlib
import subprocess
import sys

import pytest

import subscribers


@pytest.fixture(scope="module")
def app_cot():
    """Imported here, at run time, and never at module level.

    Importing app_cot builds every page under a real Dash app, which leaves the
    `pages` package unusable for a later plain `from pages import analytics`
    (test_seo's docstring has the detail). pytest collects every module before
    running any, so an import at THIS module's top would run during collection,
    and this file sorts ahead of the ones it would break. The other modules that
    import app_cot at top level only get away with it by sorting after them.
    """
    return importlib.import_module("app_cot")


@pytest.fixture(scope="module")
def admin(app_cot):
    # Dash's page loader registers it under this name without binding it on its
    # parent package, so it is reached through sys.modules (test_warm_order's note).
    return sys.modules["pages.system.admin"]


def _payload(outputs, inputs, changed):
    """A /_dash-update-component body, in the shape the Dash renderer sends."""
    outs = [{"id": i, "property": p} for i, p in outputs]
    if len(outs) == 1:
        output, outs = f"{outputs[0][0]}.{outputs[0][1]}", outs[0]
    else:
        output = "..." .join(f"{i}.{p}" for i, p in outputs).join(("..", ".."))
    return {
        "output": output,
        "outputs": outs,
        "inputs": [{"id": i, "property": p, "value": v} for i, p, v in inputs],
        "changedPropIds": [changed],
    }


#: Every admin callback that reads or does anything, as the forged request for
#: it. A new one belongs here; that is the point of the module.
STATS = _payload(
    [("visit-time-chart", "figure"), ("visitor-geo-chart", "figure"),
     ("admin-visit-summary", "children"), ("admin-log-table", "children"),
     ("server-log-viewer", "children")],
    [("admin-refresh", "n_intervals", 1),
     ("session_admin_auth", "data", "AUTHORIZED"),
     ("admin-traffic-filter", "value", "humans")],
    "admin-refresh.n_intervals")
SUBSCRIBERS = _payload(
    [("admin-subscriber-summary", "children"), ("admin-subscriber-table", "children")],
    [("admin-refresh", "n_intervals", 1),
     ("session_admin_auth", "data", "AUTHORIZED")],
    "admin-refresh.n_intervals")
RESTART = _payload([("admin-restart-alert", "children")],
                   [("admin-restart-btn", "n_clicks", 1)], "admin-restart-btn.n_clicks")
POLL = _payload([("admin-manual-poll-output", "children")],
                [("admin-manual-poll-btn", "n_clicks", 1)],
                "admin-manual-poll-btn.n_clicks")
SEND = _payload([("admin-send-email-output", "children")],
                [("admin-send-email-btn", "n_clicks", 1)],
                "admin-send-email-btn.n_clicks")


@pytest.fixture(autouse=True)
def _nothing_runs(monkeypatch, tmp_path, app_cot):
    def refuse(*args, **kwargs):
        pytest.fail(f"an admin action ran without a login: {args!r}")
    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    # Out of the visitor queue (test_legacy_redirects says why), and onto a temp
    # subscriber DB so the logged-in read has something real to return.
    monkeypatch.setattr(app_cot, "_enqueue_visit", lambda *a, **k: None)
    monkeypatch.setenv(subscribers.DB_ENV, str(tmp_path / "subs.db"))


def _post(client, body):
    return client.post("/_dash-update-component", json=body)


@pytest.mark.parametrize("name,body", [
    ("stats", STATS), ("subscribers", SUBSCRIBERS),
    ("restart", RESTART), ("poll", POLL), ("send", SEND)])
def test_a_forged_request_is_refused_by_every_admin_callback(app_cot, name, body):
    """The request that worked on 2026-10-29: the store value, no password.
    204 is Dash's answer to PreventUpdate, so nothing was computed or sent."""
    resp = _post(app_cot.app.server.test_client(), body)
    assert resp.status_code == 204, f"{name} answered a forged request"


@pytest.fixture()
def logged_in(app_cot, admin):
    client = app_cot.app.server.test_client()
    with client.session_transaction() as sess:
        sess[admin.SESSION_FLAG] = True
    return client


def test_a_logged_in_session_gets_the_subscriber_list_without_tokens(logged_in):
    pending = subscribers.subscribe("pending@example.test")[1]
    gone = subscribers.subscribe("gone@example.test")[1]
    active = subscribers.subscribe("active@example.test")[1]
    subscribers.confirm(gone)
    subscribers.unsubscribe(gone)
    subscribers.confirm(active)

    resp = _post(logged_in, SUBSCRIBERS)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "1 active | 1 unconfirmed | 1 unsubscribed" in body
    for email in ("pending@", "gone@", "active@"):
        assert email in body
    # The tokens are capability URLs: one in hand unsubscribes its owner.
    for token in (pending, gone, active):
        assert token not in body


def test_a_logged_in_session_still_gets_the_stats(logged_in):
    """The guard must not have locked out the operator along with everyone else.
    An empty visitor DB answers 200 with "No Data" figures, so 204 here can only
    mean the guard refused."""
    assert _post(logged_in, STATS).status_code == 200


def test_only_the_right_password_sets_the_session(monkeypatch, app_cot, admin):
    monkeypatch.setenv("COT_ADMIN_PASSWORD", "correct horse")
    client = app_cot.app.server.test_client()

    def login(password):
        return _post(client, _payload(
            [("session_admin_auth", "data"), ("admin-login-alert", "children")],
            [("admin-login-btn", "n_clicks", 1)], "admin-login-btn.n_clicks")
            | {"state": [{"id": "admin-pw-input", "property": "value",
                          "value": password}]})

    login("wrong")
    with client.session_transaction() as sess:
        assert admin.SESSION_FLAG not in sess
    assert _post(client, SUBSCRIBERS).status_code == 204

    login("correct horse")
    with client.session_transaction() as sess:
        assert sess.get(admin.SESSION_FLAG) is True
    assert _post(client, SUBSCRIBERS).status_code == 200


def test_the_session_cookie_is_out_of_reach_of_page_scripts_and_other_sites(app_cot):
    config = app_cot.app.server.config
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"


@pytest.mark.parametrize("confirmed,unsubscribed,status", [
    (None, None, subscribers.STATUS_UNCONFIRMED),
    ("2026-10-01", None, subscribers.STATUS_ACTIVE),
    # The normal state of anyone who confirmed and later left: unsubscribe keeps
    # confirmed_at, so the check order is what makes this read right.
    ("2026-10-01", "2026-10-20", subscribers.STATUS_UNSUBSCRIBED),
    (None, "2026-10-20", subscribers.STATUS_UNSUBSCRIBED),
])
def test_status_reads_the_three_timestamps_one_way(confirmed, unsubscribed, status):
    assert subscribers.status_of(confirmed, unsubscribed) == status
