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
