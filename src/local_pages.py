"""Pages that exist only on a local run, never on the deployed site.

Some views draw data this app may read but must not republish. The first is the
sentiment page: NAAIM's Exposure Index history is a paid subscription file and AAII's
sentiment history is a member download, both licensed to the operator, and a page on
the public site would hand them to every visitor, so in THIS app the page is local-only.

The operator has since cleared publishing them (2026-11-09), and they are published,
but not from here: `components.sentiment_static` renders the page as one static file
that goes to surveys.bluemagicai.com through the dbmf-tracker publisher
(docs/surveys-publishing.md, a cron job on the VPS). The gate stays because the deployed app is still not
where that happens, and verify-deploy still pins the 404.

**The gate is an environment flag the local launcher sets and the server never does.**
`run-local.sh` exports `COT_ANALYZER_LOCAL_PAGES=1`; `server-side/launch-cot-analyzer.sh`
does not. With the flag unset a gated page never calls `dash.register_page`, so it is
not in `dash.page_registry`, which means three things at once, none of which needs its
own code: `app_cot.reject_unknown_paths` answers its path with a 404, the sitemap does
not list it, and the navbar entry below is absent. `server-side/verify-deploy.sh`
checks the 404 on the live site, because the one way this fails is someone setting the
flag in the server's `.env`.

Off by default and parsed strictly: only an explicit yes turns it on, so a typo or an
empty value keeps a licensed page off a public server rather than putting it on one.
"""
import os

ENV = "COT_ANALYZER_LOCAL_PAGES"
_TRUE = ("1", "true", "yes", "on")

#: Navbar entries for gated pages, appended to the Monitors menu when the flag is on.
#: The label says "local" so a screenshot of a local run cannot be mistaken for the
#: public site.
MONITOR_ENTRIES = (("Sentiment (local)", "/sentiment"),)


def enabled(env=None):
    """True only when the flag is explicitly on."""
    env = os.environ if env is None else env
    return str(env.get(ENV, "")).strip().lower() in _TRUE


def monitor_entries(env=None):
    """The gated Monitors entries, or nothing when the flag is off."""
    return MONITOR_ENTRIES if enabled(env) else ()
