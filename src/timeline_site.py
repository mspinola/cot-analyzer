"""The Market Event Timeline 2026 dashboard, served at /timeline to a logged-in admin only.

The page and its data are built in the private npf repo (`scripts/build_timeline_site.py`) and pushed to
this server by a key pinned to write-only rsync into one directory (server-side/README.md, step 13). This
app draws nothing of it: it hands over `index.html` and the files under `data/`, from the directory named
by TIMELINE_SITE_DIR, so a page or data change on the npf side needs no deploy here.

Why it is gated: the data holds licensed survey readings and text paraphrased from paid reports and
headlines. The gate is the News Failure Scan's (`local_pages`): the server flag
COT_ANALYZER_PRIVATE_PAGES must be on, and the request must carry the signed session /admin sets. A
local run (COT_ANALYZER_LOCAL_PAGES) needs no login, as with the other gated pages.

What a request gets:
- flag off or no directory: the site's ordinary 404, for the page and for every data file;
- flag on, not logged in: the page path says to log in at /admin (403); a data file gets the 404, so a
  probe learns nothing about which files exist;
- logged in: the files, `private, no-store` (routing.cache_policy) and `X-Robots-Tag: noindex`.

Data file names are an allowlist shape (`[a-z][a-z_]*.csv|json`), checked before the filesystem is
touched, and served with `send_from_directory`, which also refuses anything outside the folder.
"""
import os
import re
from pathlib import Path

from flask import send_from_directory

import local_pages

ENV = "TIMELINE_SITE_DIR"
PATH = "/timeline"
DATA_NAME = re.compile(r"^[a-z][a-z_]*\.(csv|json)$")
TYPES = {"csv": "text/csv; charset=utf-8", "json": "application/json"}
HEADERS = {"X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "same-origin",
           "X-Content-Type-Options": "nosniff"}
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
    """Is the timeline served on this run at all (before asking who is asking)?"""
    return (local_pages.enabled(env) or local_pages.private_enabled(env)) and site_dir(env) is not None


def register(server, not_found, login_page):
    """Add the two routes to `server` (a Flask app).

    `not_found()` and `login_page()` return full responses; app_cot passes its themed ones so the
    answers match the rest of the site.
    """

    @server.route(PATH)
    def timeline_page():
        if not served():
            return not_found()
        if not local_pages.allowed():
            return login_page()
        index = site_dir() / "index.html"
        if not index.is_file():
            return not_found()
        return send_from_directory(site_dir(), "index.html", mimetype="text/html"), 200, HEADERS

    @server.route(PATH + "/data/<name>")
    def timeline_data(name):
        if not DATA_NAME.match(name) or not served() or not local_pages.allowed():
            return not_found()
        data = site_dir() / "data"
        if not (data / name).is_file():
            return not_found()
        mimetype = TYPES[name.rsplit(".", 1)[1]]
        return send_from_directory(data, name, mimetype=mimetype), 200, HEADERS
