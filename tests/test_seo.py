"""The search surface: what a crawler is told, pinned so it cannot rot quietly.

Measured on the live site before any of this existed: the served <title> was
"Dash" (the framework default) on every page, the shell carried 69 characters
of visible text, and /robots.txt and /sitemap.xml both 404ed. Nothing else in
the suite would notice any of that coming back, because nothing else reads the
site the way a crawler does.

The title/description half is pinned against page SOURCE rather than the
registry, for the reason test_analysis_views documents: importing app_cot (or
every page under a real app) poisons the pages package for later test modules.
"""
import pathlib
import re

import pytest

import routing

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

#: Every page a search result should be able to land on. NOINDEX_PATHS is the
#: complement; between them they cover the registry.
PUBLIC_PAGES = {
    '/': 'home.py',
    '/heatmap': 'analytics/heatmap.py',
    '/strip': 'analytics/strip.py',
    '/crowd': 'analytics/crowd.py',
    '/exposure': 'analytics/exposure.py',
    '/oi_alignment': 'analytics/oi_alignment.py',
    '/analysis': 'analytics/analysis.py',
    '/divergence': 'analytics/divergence.py',
    '/aggregation': 'analytics/aggregation.py',
    '/categories': 'analytics/categories.py',
    '/positioning': 'analytics/positioning.py',
    '/about': 'system/about.py',
    '/options': 'system/options.py',
}


def _register_call(page_file):
    text = (SRC / "pages" / page_file).read_text()
    match = re.search(r'dash\.register_page\((.*?)\n\)', text, re.S)
    assert match, f"{page_file}: no register_page call parsed"
    return match.group(1)


@pytest.mark.parametrize("path,page_file", sorted(PUBLIC_PAGES.items()))
def test_every_public_page_registers_a_title_and_description(path, page_file):
    """Dash serves the description (and og:/twitter: tags) per path from the
    registry, and app_cot's interpolate_index wrapper serves the title. A page
    registered without them ships headlined by the app fallback and described
    by an empty string."""
    call = _register_call(page_file)
    assert "title=" in call, f"{path} has no title"
    assert "description=" in call, f"{path} has no description"
    # The site name rides every title, so a result page says whose page it is.
    assert "COT Analyzer" in call


def test_robots_allows_the_public_site_and_names_the_sitemap():
    text = routing.robots_txt("https://example.test")
    assert text.startswith("User-agent: *")
    for path in routing.NOINDEX_PATHS:
        assert f"Disallow: {path}" in text
    assert "Sitemap: https://example.test/sitemap.xml" in text
    # Disallow rules only for the operator surfaces: a stray blanket
    # "Disallow: /" is the single most damaging line this file could carry.
    assert "Disallow: /\n" not in text


def test_sitemap_lists_public_pages_and_only_those():
    pages = list(PUBLIC_PAGES) + sorted(routing.NOINDEX_PATHS)
    xml = routing.sitemap_xml("https://example.test", pages,
                              lastmod="2026-08-25")
    for path in PUBLIC_PAGES:
        loc = "https://example.test" + ("/" if path == "/" else path)
        assert f"<loc>{loc}</loc>" in xml, path
    for path in routing.NOINDEX_PATHS:
        assert path not in xml
    assert xml.count("<lastmod>2026-08-25</lastmod>") == len(PUBLIC_PAGES)
    assert xml.startswith('<?xml version="1.0"')


def test_sitemap_survives_no_lastmod():
    xml = routing.sitemap_xml("https://example.test", ["/heatmap"])
    assert "<lastmod>" not in xml
    assert "<loc>https://example.test/heatmap</loc>" in xml


def test_the_shell_carries_crawlable_text_and_a_page_title_wrapper():
    """The two app_cot halves a crawler meets first: the noscript block (the
    only visible text a non-rendering client gets) and the interpolate_index
    wrapper (per-path <title>; without it every page is headlined by the one
    app title). Source pins, for the app-import reason in the module docstring."""
    text = (SRC / "app_cot.py").read_text()
    assert "<noscript>" in text
    assert "Commitments of Traders" in text
    assert "app.interpolate_index = _interpolate_index_with_page_title" in text
    assert "title='COT Analyzer" in text  # the fallback is not "Dash"
