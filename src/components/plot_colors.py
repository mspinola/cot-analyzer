"""Colour maths shared by the plot modules.

Kept apart from the drawing code because nothing here knows what a figure is, and the
palette work is easier to reason about when it is not interleaved with trace building.

Most of it is pure hex arithmetic. `grid_colors` is the exception: it resolves a
configured palette into the app's bull/bear/near set, which needs one app constant.
It lived in the Heatmap page while the Heatmap was the only surface that needed it.
The Crowding Strip draws the same verdicts, so a second copy of "which palette slot is
bearish, and which reds are too dim to use" would be two places to fix the next time a
palette is added.
"""

from typing import NamedTuple

import viz_constants as vc


def lighten_hex(hex_color, amount):
    """Blend a #rrggbb color toward white. Used to derive a second line color for a
    series that must stay recognizably itself, without stealing another palette slot."""
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return hex_color
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    def mix(c):
        return round(c + (255 - c) * amount)
    return "#{:02x}{:02x}{:02x}".format(mix(r), mix(g), mix(b))


def darken_hex(hex_color, amount):
    """Blend a #rrggbb color toward black.

    The counterpart to lighten_hex, for deriving a sibling color from a base that is
    already bright. Lightening a near-saturated color only moves the channels that
    are not already maxed: #ffff00 lightened is still plainly yellow, because red and
    green cannot go up, so only blue moves. Darkening moves all three and keeps the
    hue, so yellow reads as olive rather than as a second yellow.
    """
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return hex_color
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    def mix(c):
        return round(c * (1 - amount))
    return "#{:02x}{:02x}{:02x}".format(mix(r), mix(g), mix(b))


def relative_luminance(hex_color):
    """WCAG relative luminance, 0 (black) to 1 (white).

    Used to choose whether a derived sibling color should be lighter or darker than
    its base. Returns 0.0 for an unparseable color, which routes it down the lighten
    path, the same behaviour as before this function existed.
    """
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return 0.0
    try:
        channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return 0.0
    def linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hex_to_rgba(hex_color, alpha):
    """#rrggbb -> 'rgba(r, g, b, alpha)'. Returns the input unchanged if unparseable."""
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return hex_color
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    return f"rgba({r}, {g}, {b}, {alpha})"


# ── palette -> the app's verdict colours ──────────────────────────────────────

# Neutral dimmed colour for a cell, or a bar, with nothing to say.
DIM_TEXT = "rgba(255, 255, 255, 0.35)"


class GridColors(NamedTuple):
    """The colour set the verdict surfaces draw from.

    Passed in rather than closed over so the style rules can be built, and tested,
    without rendering a page or reaching a data store.
    """
    bull: str
    bear: str
    bull_near: str
    bear_near: str
    dim: str = DIM_TEXT


def grid_colors(color_palette):
    """Resolve a palette into the verdict colour set."""
    bull = color_palette[3]
    bear = color_palette[0]
    if bear.lower() in ("#f87171", "#dc322f", "#ff453a", "#e70307", "#ff007f"):
        bear = "#FF4D4D"
    return GridColors(
        bull=bull,
        bear=bear,
        bull_near=hex_to_rgba(bull, vc.INDEX_RAMP_ALPHA_APPROACH),
        bear_near=hex_to_rgba(bear, vc.INDEX_RAMP_ALPHA_APPROACH),
    )
