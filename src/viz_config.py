"""
viz_config.py

App-layer visualization config: color palettes (for the plot/theme dropdowns) and
the per-instrument TradingView chart symbols. Kept out of the data layer so the
CotIndexer carries no presentation config.

Reads from the app's config file (currently config/params.yaml, overridable via
COT_VIZ_CONFIG). The viz-only keys are `palettes:` and the per-asset `TV_Chart:`
field; `AssetClasses:` is read only to build the chart-symbol map.
"""
import os
from pathlib import Path

import yaml

_APP_ROOT = Path(__file__).resolve().parent.parent
_VIZ_CONFIG_PATH = Path(
    os.environ.get("COT_VIZ_CONFIG", str(_APP_ROOT / "config" / "params.yaml"))
)

#: What each palette slot MEANS, app-wide. A palette is a list and a slot is an index,
#: so this tuple is the only place the association is written down; every page indexes
#: `palette[n]` against it. Order is load-bearing and slots are append-only: renumbering
#: one would silently repaint every chart in the app.
PALETTE_SLOTS = ("Commercials", "Large Specs", "Small Traders", "Price",
                 "Open Interest", "Volatility")

_DEFAULT_PALETTE = ["#e70307", "#0000ff", "#ffff00", "#00FF00", "#E2E8F0", "#ff00ff"]


def _load():
    with open(_VIZ_CONFIG_PATH, "r") as f:
        return yaml.safe_load(f) or {}


_data = _load()
_palettes = _data.get("palettes", {}) or {}
_default_palette_name = next(iter(_palettes), None)


def get_palette_names():
    """List of available palette names for the dropdown."""
    return list(_palettes.keys())


def _padded(palette):
    """A palette with every slot filled, borrowing the default's colour for any missing.

    The palettes come from a config file this repo does not own: the real ones live in
    the private cotmetrics-config, which is not updated in lockstep. So a palette can
    legitimately predate a slot, and a consumer indexing by slot would raise IndexError
    on a machine whose config is a week old. Padding turns that into a wrong-ish colour,
    which is the right trade for a presentation value.
    """
    filled = list(palette or ())
    for slot in range(len(filled), len(PALETTE_SLOTS)):
        filled.append(_DEFAULT_PALETTE[slot])
    return filled


def get_palette(name=None):
    """Return a specific palette by name, or the first one as default."""
    if not name or name not in _palettes:
        return _padded(_palettes.get(_default_palette_name, _DEFAULT_PALETTE))
    return _padded(_palettes[name])


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
