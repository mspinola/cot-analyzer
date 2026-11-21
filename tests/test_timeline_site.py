"""The private timeline dashboard answers a logged-in admin and nobody else.

Drives `timeline_site.register` on a bare Flask app (the same function app_cot calls), with the
flag off, on and logged out, on and logged in, and on a local run, and checks the routing helpers
admit the paths without caching them.
"""
import flask
import pytest

import admin_session
import local_pages
import routing
import timeline_site


@pytest.fixture()
def site(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Market Event Timeline 2026</title>")
    (tmp_path / "data" / "spine.csv").write_text("date,ES_ret\n2026-01-02,0.01\n")
    (tmp_path / "data" / "manifest.json").write_text('{"datasets": []}')
    (tmp_path / "secret.txt").write_text("outside data/")
    return tmp_path


@pytest.fixture()
def client(monkeypatch, site):
    monkeypatch.delenv(local_pages.ENV, raising=False)
    monkeypatch.setenv(local_pages.PRIVATE_ENV, "1")
    monkeypatch.setenv(timeline_site.ENV, str(site))
    app = flask.Flask(__name__)
    app.secret_key = "test"
    timeline_site.register(app, lambda: ("not found", 404), lambda: (timeline_site.LOGIN_BODY, 403))
    return app.test_client()


def _login(client):
    with client.session_transaction() as s:
        s[admin_session.SESSION_FLAG] = True


def test_logged_out_the_page_says_to_log_in_and_the_data_is_not_found(client):
    page = client.get("/timeline")
    assert page.status_code == 403 and b"admin page" in page.data
    for path in ("/timeline/data/spine.csv", "/timeline/data/manifest.json", "/timeline/data/nope.csv"):
        assert client.get(path).status_code == 404, path


def test_a_forged_session_value_is_not_a_login(client):
    with client.session_transaction() as s:
        s[admin_session.SESSION_FLAG] = "true"
    assert client.get("/timeline").status_code == 403
    assert client.get("/timeline/data/spine.csv").status_code == 404


def test_logged_in_the_page_and_data_are_served_private_and_unindexed(client):
    _login(client)
    page = client.get("/timeline")
    assert page.status_code == 200 and page.mimetype == "text/html"
    assert b"Market Event Timeline 2026" in page.data
    data = client.get("/timeline/data/spine.csv")
    assert data.status_code == 200 and data.mimetype == "text/csv"
    assert data.data.startswith(b"date,ES_ret")
    assert client.get("/timeline/data/manifest.json").mimetype == "application/json"
    for resp in (page, data):
        assert resp.headers["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.parametrize("name", ["../secret.txt", "..%2Fsecret.txt", "Spine.csv", "spine.CSV",
                                  "spine.csv.bak", "spine.html", ".hidden.csv", "missing.csv"])
def test_only_existing_allowlisted_names_are_served(client, name):
    _login(client)
    assert client.get("/timeline/data/" + name).status_code == 404


def test_with_the_flag_off_everything_is_not_found_even_logged_in(client, monkeypatch):
    monkeypatch.delenv(local_pages.PRIVATE_ENV)
    _login(client)
    assert client.get("/timeline").status_code == 404
    assert client.get("/timeline/data/spine.csv").status_code == 404


def test_with_no_site_directory_everything_is_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setenv(timeline_site.ENV, str(tmp_path / "absent"))
    _login(client)
    assert client.get("/timeline").status_code == 404
    monkeypatch.delenv(timeline_site.ENV)
    assert client.get("/timeline").status_code == 404


def test_a_local_run_needs_no_login(client, monkeypatch):
    monkeypatch.delenv(local_pages.PRIVATE_ENV)
    monkeypatch.setenv(local_pages.ENV, "1")
    assert client.get("/timeline").status_code == 200
    assert client.get("/timeline/data/spine.csv").status_code == 200


def test_routing_admits_the_shapes_and_nothing_near_them():
    for path in ("/timeline", "/timeline/data/spine.csv", "/timeline/data/events.json"):
        assert routing.is_known_path(path, [], []), path
    for path in ("/timeline/", "/timeline/x", "/timeline/data/../x.csv", "/timeline/data/A.csv",
                 "/timelinex", "/timeline/data/a.txt"):
        assert not routing.is_known_path(path, [], []), path


def test_nothing_caches_the_timeline():
    for path in ("/timeline", "/timeline/data/spine.csv"):
        assert routing.cache_policy(path, False, "text/html") == "private, no-store"
    assert "/timeline" not in routing.robots_txt("https://example.com")
