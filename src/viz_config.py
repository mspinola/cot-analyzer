"""
viz_config.py

App-layer visualization config: color palettes (for the plot/theme dropdowns) and
the per-instrument TradingView chart symbols. Kept out of the data layer so the
CotIndexer carries no presentation config.

Reads from the app's config file (currently config/params.yaml, overridable via
COT_VIZ_CONFIG). The viz-only keys are `palettes:` and the per-asset `TV_Chart:`
field; `AssetClasses:` is read only to build the chart-symbol map.

This module also carried a role-aware universe API (`instrument_roles`,
`plotted_symbols`, `configured_symbols`), which existed solely so the `/damage`
page could filter crowdmon's wider scored universe down to the markets this site
plots. That page was removed when crowdmon was deprecated, and the three
functions went with it rather than being left as dead code with no caller. If a
future surface needs the same question answered, resolve it from cotmetrics'
`PLOTTED_ROLES` / `resolve_role` as that API did, rather than restating the role
rules here: a `heldout` market must not become plottable through a new door.
"""
import os
from pathlib import Path

import yaml

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
