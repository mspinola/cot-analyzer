"""The shared control kit, and the drift it exists to prevent.

The builders are trivial on purpose; what these tests pin is the contract that
makes them worth having: semantic fields (options, default, persistence,
tooltips) have exactly one home, geometry stays overridable, and no page slides
back to rebuilding the shared literals inline.
"""

import importlib
import pathlib
import sys

import pytest

import viz_constants as vc
from components import controls

PAGES_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "pages"


def test_module_imports_without_the_data_layer():
    """Only the target-date pieces may touch the indexer, and only when called.

    Pages call the builders inside layout(); the module itself is imported by
    every page at import time, where CI's store is an empty directory.
    """
    for name in [m for m in sys.modules if m.startswith("cotmetrics.indexer")]:
        del sys.modules[name]
    importlib.reload(controls)
    assert not any(m.startswith("cotmetrics.indexer") for m in sys.modules)


def test_lookback_select_semantics():
    sel = controls.lookback_select('x_lookback')
    assert [o["value"] for o in sel.options] == list(controls.LOOKBACK_CHOICES)
    assert sel.value == "Custom"
    assert sel.persistence == 'session'


def test_overrides_touch_geometry_not_semantics():
    sel = controls.lookback_select('x_lookback', size="sm",
                                   style={'width': '120px'})
    assert sel.size == "sm" and sel.style == {'width': '120px'}
    assert [o["value"] for o in sel.options] == list(controls.LOOKBACK_CHOICES)
    # And an explicit persistence=None turns the browser copy off (the Strip and
    # Crowd ride the global store instead).
    assert controls.lookback_select('x', persistence=None).persistence is None


@pytest.mark.parametrize("choices", [vc.MODEL_CHOICES, vc.MODEL_VIEW_CHOICES])
def test_model_select_offers_the_choices_with_tooltips(choices):
    """Tooltips on every option: they existed on three pages and not the other
    two, which is exactly the drift a shared builder is for."""
    sel = controls.model_select('x_model', choices=choices)
    assert [o["value"] for o in sel.options] == list(choices)
    assert all(o.get("title") for o in sel.options)


def test_no_page_rebuilds_the_lookback_options():
    """The tripwire. The literal below was written out nine times before the
    kit existed; a page that reintroduces it has forked the vocabulary again.
    Exposure's deliberately different lookback ("All history", lowercase
    "weeks") does not trip this, and that is correct: it is a different
    control, documented as such.
    """
    offenders = [p.name for p in PAGES_DIR.rglob("*.py")
                 if '{"label": "26 Weeks"' in p.read_text()]
    assert offenders == [], offenders


def test_label_is_the_uppercase_caption_style():
    lbl = controls.label("Lookback")
    assert lbl.children == "Lookback"
    assert lbl.style["textTransform"] == "uppercase"
    # Geometry overrides merge here too (the chart pages keep their mb spacing).
    assert controls.label("X", marginBottom="0.5rem").style["marginBottom"] == "0.5rem"
