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
#: than trying to enumerate fingerprinted asset filenames.
SERVED_PREFIXES = (
    '/_dash-component-suites/',
    '/assets/',
    '/static/',
)

#: Real paths belonging to no page: the browser's automatic favicon request, and Dash's
#: own copy of it. Neither is in `page_registry` and both are legitimate.
EXTRA_PATHS = frozenset({'/favicon.ico', '/_favicon.ico'})


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
