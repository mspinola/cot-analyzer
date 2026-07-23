"""
viz_config.py

App-layer visualization config: color palettes (for the plot/theme dropdowns) and
the per-instrument TradingView chart symbols. Kept out of the data layer so the
CotIndexer carries no presentation config.

Reads from the app's config file (currently config/params.yaml, overridable via
COT_VIZ_CONFIG). Only the viz-only keys are consulted: `palettes:` and the
per-asset `TV_Chart:` field.
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
