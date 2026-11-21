"""Phase 2 of docs/design/2026-11-21-public-lookbacks-npf-behind-login.md: the NPF model
layer (setup verdicts, setup ages, the OI-normalized basis) is behind the login.

`controls.private_allowed` is the one gate. These tests pin what each surface does on
either side of it, without a request: the gate is monkeypatched.
"""
import dash
import pandas as pd
import pytest
from cotmetrics import constants as const
from cotmetrics import models
from dash.exceptions import PreventUpdate

import components.controls as controls
import components.strip_traces as strip_traces

dash.Dash(__name__, use_pages=True, pages_folder="")

import pages.analytics.crowd as crowd  # noqa: E402
import pages.analytics.divergence as divergence  # noqa: E402
import pages.analytics.heatmap as heatmap  # noqa: E402
import pages.analytics.scorecard as scorecard  # noqa: E402
import pages.setups as setups  # noqa: E402
import routing  # noqa: E402
from components.plot_colors import grid_colors  # noqa: E402


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setattr(controls, "private_allowed", lambda: False)


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(controls, "private_allowed", lambda: True)


def test_a_private_callback_refuses_a_public_request(public):
    """The pages render nothing for a public visitor, but a browser can post to any
    callback on the shared endpoint. The decorator is that check."""
    def body():
        return "the NPF answer"
    guarded = controls.private_callback(
        dash.Output("npf_gate_test_out", "children"),
        dash.Input("npf_gate_test_in", "value"))(body)
    with pytest.raises(PreventUpdate):
        guarded()


def test_a_private_callback_answers_a_signed_in_request(signed_in):
    def body():
        return "the NPF answer"
    guarded = controls.private_callback(
        dash.Output("npf_gate_test_out2", "children"),
        dash.Input("npf_gate_test_in2", "value"))(body)
    assert guarded() == "the NPF answer"


@pytest.mark.parametrize("page", [setups, scorecard, divergence])
def test_the_npf_pages_show_a_public_visitor_the_sign_in_note(public, page):
    assert getattr(page.layout(), "id", None) == "private_page_stub"


def test_the_npf_pages_are_not_indexed():
    assert {"/setups", "/scorecard", "/divergence"} <= routing.NOINDEX_PATHS


def test_a_public_request_reads_the_default_model(public):
    assert controls.gate_model(models.NPF.key) == models.DEFAULT_MODEL.key
    assert controls.gate_model("both") == models.DEFAULT_MODEL.key


def test_a_signed_in_request_keeps_its_model(signed_in):
    assert controls.gate_model(models.NPF.key) == models.NPF.key


def test_a_private_control_is_hidden_from_a_public_request(public):
    assert controls.private_style({"width": "1px"}) == {"width": "1px", "display": "none"}


def test_the_public_heatmap_frame_carries_no_npf_columns():
    """AG Grid ships all of rowData, shown or not, so hiding a column is not enough."""
    df = pd.DataFrame({"Asset": ["Gold"], "Comm Index": [90], "Comm Index Norm": [80],
                       const.SETUP_CLS_COL: [const.SETUP_BULL],
                       const.SETUP_NPF_COL: [const.SETUP_NONE],
                       const.SETUP_NPF_CLS_COL: [const.SETUP_NONE]})
    assert list(heatmap.public_matrix(df).columns) == ["Asset", "Comm Index"]


def test_the_public_heatmap_has_no_npf_block():
    groups = [{"headerName": f"Positioning · {models.RAW_PF.title}",
               "children": [{"field": "Comm Index", "headerTooltip": "the gate"}]},
              {"headerName": f"Positioning · {models.NPF.title}", "children": []},
              {"headerName": "Index Momentum", "children": []}]
    out = heatmap.public_column_defs(groups)
    assert [g["headerName"] for g in out] == ["Positioning", "Index Momentum"]
    assert "headerTooltip" not in out[0]["children"][0]


def test_the_public_strip_legend_names_no_verdicts():
    from viz_config import get_palette
    palette = get_palette(None)
    items = strip_traces.legend_items(models.DEFAULT_MODEL, grid_colors(palette), palette,
                                      verdicts=False)
    labels = [label for _, entries in items for label, _, _ in entries]
    assert not any("setup" in label.lower() or label == "Near" for label in labels)


def test_the_public_home_caption_and_help_name_no_model():
    model = models.DEFAULT_MODEL
    text = crowd.caption("2026-11-17", model, [], verdicts=False)
    assert model.title not in text and "verdict" not in text
    assert "SETUP chip" not in crowd.help_text(model, verdicts=False)
    assert "SETUP chip" in crowd.help_text(model, verdicts=True)
