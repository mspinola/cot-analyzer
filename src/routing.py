"""Which URLs this app actually serves, and what to say about the ones it does not.

Split out of `app_cot` for the reason `main.py` splits `price_store_verdict` out of
`check_price_store`: the I/O half (read the request, consult the live page registry,
return a response) is uninteresting, and the arguable half is the membership test. This
module is the arguable half, pure and importable without instantiating a Dash app.

The problem it solves: `use_pages=True` registers a catch-all `/<path:path>` that serves
the Dash index for ANY url, leaving the "page not found" screen to the client-side
router. The status code is therefore 200 no matter what was asked for. Vulnerability
scanners probing for `/shell.php`, `/wp-is.php` and a few hundred similar each received
a 200 and a full app shell, which costs bandwidth, makes the visit log unable to
separate a page view from a probe, and advertises the host as a live PHP target.
"""

#: Prefixes under which Dash serves generated or static content. Everything below them
#: is Dash's to answer for, including its own errors, so membership stops here rather
#: than trying to enumerate fingerprinted asset filenames. The one carve-out is vendor
#: source maps, which Dash answers for badly; see `is_vendor_sourcemap`.
SERVED_PREFIXES = (
    '/_dash-component-suites/',
    '/assets/',
    '/static/',
)

#: Real paths belonging to no page: the browser's automatic favicon request, Dash's
#: own copy of it, the email-link and crawler endpoints (plain Flask routes in
#: app_cot, which `app.routes` does not list because it only knows Dash's own),
#: and the old /graphs address (an explicit 301 route to /analysis?view=grid,
#: invisible to `app.routes` the same way).
EXTRA_PATHS = frozenset({'/favicon.ico', '/_favicon.ico',
                         '/confirm', '/unsubscribe', '/graphs',
                         '/robots.txt', '/sitemap.xml'})

#: Operator surfaces and internal viewers: out of the sitemap, disallowed in
#: robots.txt. A search result should never land a visitor on the admin login
#: or a raw parquet browser.
NOINDEX_PATHS = frozenset({'/admin', '/raw_data', '/citpy', '/citpy/view'})


def robots_txt(base_url):
    """The crawl policy: everything public, the operator surfaces excluded, and
    the sitemap named (which is how most engines find it)."""
    lines = ["User-agent: *"]
    lines += [f"Disallow: {path}" for path in sorted(NOINDEX_PATHS)]
    lines += ["", f"Sitemap: {base_url}/sitemap.xml", ""]
    return "\n".join(lines)


def sitemap_xml(base_url, page_paths, lastmod=None):
    """Every public page as a sitemap entry.

    Built from the live page registry rather than a hand-kept list, so a new
    page is discoverable the day it ships; NOINDEX_PATHS is the only curation.
    `lastmod` is the newest COT week when the caller has one: the data pages
    genuinely change once per release, and telling crawlers when invites a
    weekly re-crawl.
    """
    urls = []
    for path in sorted({_normalize(p) for p in page_paths if p} - NOINDEX_PATHS):
        loc = f"{base_url}{path}"
        entry = f"  <url>\n    <loc>{loc}</loc>"
        if lastmod:
            entry += f"\n    <lastmod>{lastmod}</lastmod>"
        urls.append(entry + "\n  </url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def _normalize(path: str) -> str:
    """Collapse the trailing-slash spelling, so `/exposure/` matches `/exposure`.

    Dash's client-side router treats the two as one page, so the guard must too, or a
    url a person can reach by typing it with a slash 404s while the same page loads
    without one.
    """
    return path.rstrip('/') or '/'


def is_known_path(path: str, page_paths, dash_routes) -> bool:
    """Is `path` served by a registered page or a Dash route?

    `page_paths` and `dash_routes` are passed in rather than read from globals so this
    stays a pure membership test. The caller supplies them from `dash.page_registry` and
    `app.routes` at REQUEST time, not import time: reading the same live objects the
    client-side router resolves against is what keeps this guard from ever disagreeing
    with the page that would have rendered.
    """
    if path.startswith(SERVED_PREFIXES):
        return True
    normalized = _normalize(path)
    if normalized in EXTRA_PATHS:
        return True
    if normalized in {_normalize(route) for route in dash_routes}:
        return True
    return normalized in {_normalize(p) for p in page_paths if p}


def is_vendor_sourcemap(path: str) -> bool:
    """Is `path` a devtools request for a source map of a Dash vendor bundle?

    Any browser with devtools open asks for these by appending `.map` to every
    fingerprinted bundle url it loaded. Dash cannot answer them cleanly: for maps it
    never registered (all of `deps/`, dash-bootstrap-components) `serve_component_suites`
    raises `DependencyException`, and a registered map missing from the installed wheel
    (`dash_renderer.min.js.map`) fails the package read instead. Either way the reply is
    a 500 with a full traceback in the server log, one per bundle per devtools session.

    So the app declines ALL vendor maps with a quiet 404 rather than replicating Dash's
    fingerprint parsing to predict which few would succeed. The cost is that devtools
    cannot pretty-print minified vendor bundles; the app's own scripts live under
    `/assets/` and are unaffected.
    """
    return path.startswith('/_dash-component-suites/') and path.endswith('.map')


def not_found_page(background: str, text: str, bright: str) -> str:
    """The 404 body: themed, navigable, and deliberately not the Dash shell.

    A 404 should not cost a full app payload, and a scanner should not be handed one.
    The other reader who arrives here is a person who mistyped a url, which is why it
    is styled and carries a way back rather than being a bare status line.
    """
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>404 - Not found | COT Analyzer</title>
<style>
  body {{ background:{background}; color:{text};
         font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
         display:flex; align-items:center; justify-content:center;
         height:100vh; margin:0; text-align:center; }}
  h1 {{ color:{bright}; font-size:1.5rem; margin:0 0 .5rem; }}
  p  {{ margin:0 0 1rem; font-size:.9rem; }}
  a  {{ color:{bright}; }}
</style></head>
<body><div>
  <h1>404 &mdash; not found</h1>
  <p>No page is served at this address.</p>
  <a href="/">Back to COT Analyzer</a>
</div></body></html>"""


def message_page(title: str, body: str,
                 background: str, text: str, bright: str) -> str:
    """A one-sentence themed page, for the email-link endpoints.

    Same argument as `not_found_page`: /confirm and /unsubscribe are clicked from
    an email, and their whole answer is one sentence, so serving the Dash shell
    to say it would cost a full app payload to a reader who wants a receipt.
    """
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | COT Analyzer</title>
<style>
  body {{ background:{background}; color:{text};
         font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
         display:flex; align-items:center; justify-content:center;
         height:100vh; margin:0; text-align:center; }}
  h1 {{ color:{bright}; font-size:1.5rem; margin:0 0 .5rem; }}
  p  {{ margin:0 0 1rem; font-size:.9rem; }}
  a  {{ color:{bright}; }}
</style></head>
<body><div>
  <h1>{title}</h1>
  <p>{body}</p>
  <a href="/">Back to COT Analyzer</a>
</div></body></html>"""


def cache_policy(path, fingerprinted, content_type):
    """The Cache-Control one response should carry, or None to leave it alone.

    Lives here beside the other request-boundary policy (`is_known_path`) so it
    is testable without building the Dash app. Nginx passes origin headers
    through untouched, so this IS the edge's behaviour. Measured at the origin
    before it existed:

    * Component suites already shipped `max-age=31536000` on version-and-build
      fingerprinted URLs (Dash's own doing). `immutable` is added so a refresh
      does not revalidate a year-cached bundle, and the policy is stated here
      rather than trusted to stay Dash's default.
    * `/assets/` files shipped `no-cache` plus an ETag, so every page load spent
      a conditional round trip per file. Dash fingerprints their URLs with
      `?m=<mtime>`, which changes when the file does, so WITH the fingerprint
      they are safe to cache for a year; a bare un-fingerprinted fetch keeps
      Dash's revalidation, because that URL never changes.
    * The dash endpoints and the documents shipped no Cache-Control at all,
      which invites heuristic caching: a heuristically cached /_dash-layout is
      how a stale layout could serve. `no-store` for the endpoints; `no-cache`
      for the HTML shell, which is small and whose script URLs carry the
      fingerprints doing the real caching.
    """
    if path.startswith('/_dash-component-suites/'):
        return 'public, max-age=31536000, immutable'
    if path.startswith('/assets/'):
        return 'public, max-age=31536000, immutable' if fingerprinted else None
    if path.startswith(('/_dash-layout', '/_dash-dependencies',
                        '/_dash-update-component')):
        return 'no-store'
    if content_type.startswith('text/html'):
        return 'no-cache'
    return None
