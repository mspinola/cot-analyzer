"""The installable-app surface: what Android's install criteria actually check.

Chrome offers a real install only when the manifest carries name, icons at 192
and 512, start_url and a standalone display, and a service worker with a fetch
handler is registered from the scope root. Every piece is pinned here because
each fails silently: a missing icon file or a mis-sized one just means the
install prompt never appears, with nothing anywhere saying why.

The other pin is the worker's restraint. This app must never serve a stale
shell (the layout IS the app, and the cache policy says no-store/no-cache for
exactly that reason), so the worker uses no Cache Storage at all; if
`caches.` ever appears in it, someone is about to cache a Dash shell.
"""
import json
import pathlib
import struct

import pwa
from routing import EXTRA_PATHS, cache_policy

ASSETS = pathlib.Path(__file__).resolve().parents[1] / "src" / "assets"


def _png_size(path):
    """(width, height) from the PNG IHDR, stdlib-only: pillow generates the
    icons (scripts/make_pwa_icons.py) but is not a test dependency."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", data[16:24])


def test_manifest_meets_the_install_criteria():
    manifest = json.loads(pwa.manifest_json())
    assert manifest["name"] and manifest["short_name"]
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


def test_every_manifest_icon_exists_at_its_declared_size():
    manifest = json.loads(pwa.manifest_json())
    for icon in manifest["icons"]:
        assert icon["src"].startswith("/assets/")
        path = ASSETS / icon["src"].removeprefix("/assets/")
        assert path.exists(), f"{icon['src']} not in src/assets"
        want = tuple(int(n) for n in icon["sizes"].split("x"))
        assert _png_size(path) == want, icon["src"]
    # The iOS icon is head-linked rather than manifest-listed.
    assert _png_size(ASSETS / "apple-touch-icon.png") == (180, 180)


def test_the_worker_handles_fetch_and_caches_nothing():
    assert "addEventListener('install'" in pwa.SERVICE_WORKER
    assert "addEventListener('activate'" in pwa.SERVICE_WORKER
    assert "addEventListener('fetch'" in pwa.SERVICE_WORKER
    assert "You are offline" in pwa.SERVICE_WORKER
    # The restraint pin: no Cache Storage, or a stale Dash shell is next.
    assert "caches." not in pwa.SERVICE_WORKER


def test_the_install_endpoints_are_served_and_revalidate():
    for path in ("/manifest.webmanifest", "/sw.js"):
        assert path in EXTRA_PATHS
        assert cache_policy(path, False, "application/javascript") == "no-cache"
