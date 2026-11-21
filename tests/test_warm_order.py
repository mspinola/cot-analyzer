"""The boot and release warmer runs the newest weekly report first, then the landing page,
then every other public page, and only then what a signed-in visitor alone reads.

The weekly email links to that report and crawlers reach it before any other, so
it is the one a reader is most likely waiting on after a restart or a release.
Pinned because the order lives in one function body that nothing else checks:
moving the weekly warm behind the board warmers is invisible in a green suite
and costs ~3 minutes of cold renders on the VPS (measured 2026-09-25).

The second slot belongs to whichever page is serving `/`, which is the crowd
board since it took the landing spot from the setups page. That is the half a
navbar reorganisation silently gets wrong: moving a page to `/` and leaving the
warm order alone makes the landing page the one nobody warmed.

Since 2026-11-21 the signed-in caches (the home board's frozen-table half and the
login-gated pages) come after every public one, so a public visitor after a restart
does not wait behind caches they cannot see.
"""
import importlib
import sys

import dash

# The page modules register with Dash at import; an app with no pages folder is
# enough for the warmers' imports inside warm_page_caches.
dash.Dash(__name__, use_pages=True, pages_folder='')

import main  # noqa: E402


def test_the_newest_weekly_report_then_the_landing_page_are_warmed_first(monkeypatch):
    calls = []
    # Patched on whatever sys.modules holds, which is exactly what the imports
    # inside warm_page_caches resolve to. Not a module imported here, and not a
    # dotted path: once another test imports app_cot, Dash's page loader puts the
    # page modules in sys.modules without binding them on their parent package.
    for module, name in (("weekly_reports", "weekly"),
                         ("pages.setups", "setups"),
                         ("pages.analytics.crowd", "crowd"),
                         ("pages.analytics.heatmap", "heatmap"),
                         ("pages.analytics.divergence", "divergence")):
        importlib.import_module(module)
        attr = "warm_newest" if name == "weekly" else "warm_caches"
        monkeypatch.setattr(sys.modules[module], attr,
                            lambda name=name: calls.append(name))
    monkeypatch.setattr(sys.modules["pages.analytics.crowd"], "warm_private_caches",
                        lambda: calls.append("crowd (signed in)"))
    importlib.import_module("pages.analytics.scorecard")
    monkeypatch.setattr(sys.modules["pages.analytics.scorecard"], "warm_caches",
                        lambda: calls.append("scorecard"))
    main.warm_page_caches()
    assert calls == ["weekly", "crowd", "heatmap", "crowd (signed in)", "setups",
                     "divergence", "scorecard"]
