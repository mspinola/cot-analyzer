"""Colour maths shared by the plot modules.

Kept apart from the drawing code because these are pure functions over hex strings:
nothing here knows what a figure is, and the palette work is easier to reason about
when it is not interleaved with trace building.
"""

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
