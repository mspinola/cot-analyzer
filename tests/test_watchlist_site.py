"""The private weekly watchlist answers a logged-in admin and nobody else.

The same cases as test_timeline_site, on `watchlist_site.register`, plus its own file shapes.
"""
import flask
import pytest

import admin_session
import local_pages
import routing
import watchlist_site


@pytest.fixture()
def site(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Weekly Setup Watchlist</title>")
    (tmp_path / "data" / "index.json").write_text('{"weeks": []}')
    (tmp_path / "data" / "week_2026-11-17.json").write_text('{"report_date": "2026-11-17"}')
    (tmp_path / "data" / "notes.json").write_text('{"not": "an allowlisted shape"}')
    (tmp_path / "secret.txt").write_text("outside data/")
    return tmp_path


@pytest.fixture()
def client(monkeypatch, site):
    monkeypatch.delenv(local_pages.ENV, raising=False)
    monkeypatch.setenv(local_pages.PRIVATE_ENV, "1")
    monkeypatch.setenv(watchlist_site.ENV, str(site))
    app = flask.Flask(__name__)
    app.secret_key = "test"
    watchlist_site.register(app, lambda: ("not found", 404), lambda: (watchlist_site.LOGIN_BODY, 403))
    return app.test_client()


def _login(client):
    with client.session_transaction() as s:
        s[admin_session.SESSION_FLAG] = True


DATA = ("/watchlist/data/index.json", "/watchlist/data/week_2026-11-17.json")


def test_logged_out_the_page_says_to_log_in_and_the_data_is_not_found(client):
    page = client.get("/watchlist")
    assert page.status_code == 403 and b"admin page" in page.data
    for path in DATA + ("/watchlist/data/week_2026-01-01.json",):
        assert client.get(path).status_code == 404, path


def test_a_forged_session_value_is_not_a_login(client):
    with client.session_transaction() as s:
        s[admin_session.SESSION_FLAG] = "true"
    assert client.get("/watchlist").status_code == 403
    assert client.get(DATA[0]).status_code == 404


def test_logged_in_the_page_and_data_are_served_unindexed(client):
    _login(client)
    page = client.get("/watchlist")
    assert page.status_code == 200 and page.mimetype == "text/html"
    assert b"Weekly Setup Watchlist" in page.data
    for path in DATA:
        resp = client.get(path)
        assert resp.status_code == 200 and resp.mimetype == "application/json", path
        assert resp.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.parametrize("name", ["../secret.txt", "..%2Fsecret.txt", "notes.json", "Index.json",
                                  "index.json.bak", "week_2026-11-17.JSON", "week_20261117.json",
                                  "week_2026-11-17.csv", "week_2026-11-24.json"])
def test_only_existing_allowlisted_names_are_served(client, name):
    _login(client)
    assert client.get("/watchlist/data/" + name).status_code == 404


def test_with_the_flag_off_everything_is_not_found_even_logged_in(client, monkeypatch):
    monkeypatch.delenv(local_pages.PRIVATE_ENV)
    _login(client)
    assert client.get("/watchlist").status_code == 404
    assert client.get(DATA[0]).status_code == 404


def test_with_no_site_directory_everything_is_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setenv(watchlist_site.ENV, str(tmp_path / "absent"))
    _login(client)
    assert client.get("/watchlist").status_code == 404
    monkeypatch.delenv(watchlist_site.ENV)
    assert client.get("/watchlist").status_code == 404


def test_a_local_run_needs_no_login(client, monkeypatch):
    monkeypatch.delenv(local_pages.PRIVATE_ENV)
    monkeypatch.setenv(local_pages.ENV, "1")
    assert client.get("/watchlist").status_code == 200
    assert client.get(DATA[1]).status_code == 200


def test_routing_admits_the_shapes_and_nothing_near_them():
    for path in ("/watchlist",) + DATA:
        assert routing.is_known_path(path, [], []), path
    for path in ("/watchlist/", "/watchlist/x", "/watchlist/data/../x.json", "/watchlist/data/notes.json",
                 "/watchlistx", "/watchlist/data/week_2026-11-17.csv", "/watchlist/data/week_x.json"):
        assert not routing.is_known_path(path, [], []), path


def test_nothing_caches_the_watchlist():
    for path in ("/watchlist",) + DATA:
        assert routing.cache_policy(path, False, "text/html") == "private, no-store"
    assert "/watchlist" not in routing.robots_txt("https://example.com")
