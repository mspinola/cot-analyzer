import dash_bootstrap_components as dbc
from dash import html

import viz_constants as vc


def get_tv_overlay_component(prefix=""):
    return html.Div([
        dbc.Button(
            "📈 Open in TradingView",
            id=f"{prefix}open-tv-modal-btn",
            size="sm",
            color="secondary",
            outline=True,
            className="mb-2",
            style=vc.button_style
        ),

        # The Modal (Overlay)
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle(id=f"{prefix}tv-modal-title")),
                dbc.ModalBody(
                    html.Iframe(
                        id=f"{prefix}tv-iframe",
                        # We will inject the URL dynamically via callback
                        src="",
                        style={"width": "100%", "height": "70vh", "border": "none"}
                    )
                ),
            ],
            id=f"{prefix}tv-modal",
            size="xl",  # 'xl' makes it take up most of the screen
            is_open=False,
        ),
    ])
