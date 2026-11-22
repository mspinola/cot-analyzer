"""The weekly setup watchlist, served at /watchlist to a logged-in admin only.

The same arrangement as `timeline_site`, which says why in full: the page and its data are
built in the private npf repo (`scripts/build_watchlist_site.py`) and pushed to this server
into the directory named by WATCHLIST_SITE_DIR. This app draws nothing of it and computes
nothing: it hands over `index.html` and the files under `data/`.

Why it is gated: each week's file can carry "what to watch" notes paraphrased from a paid
weekly report and call, beside positioning readings the public site only shows on other
lookbacks. The gate is `local_pages`': COT_ANALYZER_PRIVATE_PAGES on, and the signed
session /admin sets. A local run (COT_ANALYZER_LOCAL_PAGES) needs no login.

What a request gets is `timeline_site`'s table exactly: the ordinary 404 with the flag off
or no directory; logged out, a 403 "log in" for the page and a 404 for every data file;
logged in, the files, never cached and never indexed.

Data file names are an allowlist SHAPE, checked before the filesystem is touched: the week
index, and one frozen file per COT report date.
"""
import os
import re
from pathlib import Path

from flask import send_from_directory

import local_pages
from timeline_site import HEADERS

ENV = "WATCHLIST_SITE_DIR"
PATH = "/watchlist"
DATA_NAME = re.compile(r"^(index|week_\d{4}-\d{2}-\d{2})\.json$")
LOGIN_BODY = ('This page is private. Log in on the <a href="/admin">admin page</a>, '
              'then open it again.')


def site_dir(env=None):
    """The pushed folder, or None when unset or missing."""
    env = os.environ if env is None else env
    raw = str(env.get(ENV, "")).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def served(env=None):
    """Is the watchlist served on this run at all (before asking who is asking)?"""
    return (local_pages.enabled(env) or local_pages.private_enabled(env)) and site_dir(env) is not None


def register(server, not_found, login_page):
    """Add the two routes to `server` (a Flask app); see `timeline_site.register`."""

    @server.route(PATH)
    def watchlist_page():
        if not served():
            return not_found()
        if not local_pages.allowed():
            return login_page()
        if not (site_dir() / "index.html").is_file():
            return not_found()
        return send_from_directory(site_dir(), "index.html", mimetype="text/html"), 200, HEADERS

    @server.route(PATH + "/data/<name>")
    def watchlist_data(name):
        if not DATA_NAME.match(name) or not served() or not local_pages.allowed():
            return not_found()
        data = site_dir() / "data"
        if not (data / name).is_file():
            return not_found()
        return send_from_directory(data, name, mimetype="application/json"), 200, HEADERS
