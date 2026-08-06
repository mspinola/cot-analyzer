"""
viz_config.py

App-layer visualization config: color palettes (for the plot/theme dropdowns), the
per-instrument TradingView chart symbols, and which instruments this site plots at
all. Kept out of the data layer so the CotIndexer carries no presentation config.

Reads from the app's config file (currently config/params.yaml, overridable via
COT_VIZ_CONFIG). The viz-only keys are `palettes:` and the per-asset `TV_Chart:`
field; `AssetClasses:` and `roles:` are read too, but only to answer "does this
site plot that market", never to derive anything about it.

That last question exists for the damage page, which renders a panel produced
elsewhere. crowdmon scores every market it can, which is a superset of the
universe configured here, so the page needs the configured set to filter against.
The role rules are imported from cotmetrics rather than restated: a `heldout`
market must not become plottable through a new door.
"""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from cotmetrics.CotIndexer import PLOTTED_ROLES, resolve_role

_APP_ROOT = Path(__file__).resolve().parent.parent
_VIZ_CONFIG_PATH = Path(
    os.environ.get("COT_VIZ_CONFIG", str(_APP_ROOT / "config" / "params.yaml"))
)

_DEFAULT_PALETTE = ["#e70307", "#0000ff", "#ffff00", "#00FF00", "#E2E8F0"]


def _load():
    with open(_VIZ_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


_data = _load()
_palettes = _data.get("palettes", {}) or {}
_default_palette_name = next(iter(_palettes), None)


def get_palette_names():
    """List of available palette names for the dropdown."""
    return list(_palettes.keys())


def get_palette(name=None):
    """Return a specific palette by name, or the first one as default."""
    if not name or name not in _palettes:
        return _palettes.get(_default_palette_name, _DEFAULT_PALETTE)
    return _palettes[name]


def _build_tv_chart_map():
    m = {}
    for asset_class_dict in _data.get("AssetClasses", []):
        for _asset_class, assets in asset_class_dict.items():
            for asset in assets:
                m[asset["Name"]] = asset.get("TV_Chart")
    return m


_tv_chart_by_name = _build_tv_chart_map()


def tv_chart_for_name(name):
    """TradingView chart symbol for an instrument name, or None."""
    return _tv_chart_by_name.get(name)


@lru_cache(maxsize=1)
def instrument_roles():
    """`{symbol: role}` for every instrument the config names, resolved roles included.

    Built on first call rather than at import, so a config with an invalid `Role:` costs
    the surfaces that ask rather than the whole app: `resolve_role` raises on an unknown
    role by design, and this module is imported by nearly every page.

    An instrument with no `Symbol:` is skipped. It cannot be matched to anything, and the
    one caller joins on the symbol.
    """
    role_config = _data.get("roles", {}) or {}
    out = {}
    for asset_class_dict in _data.get("AssetClasses", []) or []:
        for asset_class, assets in asset_class_dict.items():
            for asset in assets or []:
                symbol = asset.get("Symbol")
                if symbol:
                    out[str(symbol)] = resolve_role(asset, asset_class, role_config)
    return out


def plotted_symbols():
    """The symbols this site plots: `deploy` and `watch`, never `heldout`.

    Same set the CotIndexer's own plotted views resolve to, from the same file, because
    `PLOTTED_ROLES` is imported rather than restated here. A market that is indexed but
    held out of selection is held out of every chart, this one included.
    """
    return frozenset(s for s, role in instrument_roles().items()
                     if role in PLOTTED_ROLES)


def configured_symbols():
    """Every symbol the config names, whatever its role.

    Separate from `plotted_symbols` so a caller can tell "this site has never heard of
    that market" from "this site knows it and does not plot it". They are different
    answers and a reader deserves the right one.
    """
    return frozenset(instrument_roles())
