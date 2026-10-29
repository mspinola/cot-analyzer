"""The email's 52-week path, held to the page's rule pixel by pixel.

The email draws each market's path as a PNG because no mail client will draw
the page's Plotly line. The claim spark_png makes is that the picture IS the
page's path: same shape, same midline, same end-dot rule. These decode the PNG
the module writes (with a decoder here, so the test does not lean on Pillow,
which this app does not declare) and check the pixels against board_traces.
"""
import math
import struct
import zlib

import numpy as np
import pytest

import components.board_traces as bt
from components import spark_png
from components.plot_colors import GridColors

COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.5)",
                    bear_near="rgba(255,77,77,0.5)")
BG = "#1a1a1a"
S = spark_png.SCALE


def decode(png):
    """(h, w, 3) uint8 from the PNGs spark_png writes: truecolour, filter 0."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, (w, h) = 8, b"", (0, 0)
    while pos < len(png):
        (length,) = struct.unpack(">I", png[pos:pos + 4])
        tag, data = png[pos + 4:pos + 8], png[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", png[pos + 8 + length:pos + 12 + length])
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF, f"bad CRC on {tag!r}"
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", data[:10])
            assert (depth, ctype) == (8, 2)
        elif tag == b"IDAT":
            idat += data
        pos += 12 + length
    raw = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(h, 1 + w * 3)
    assert (raw[:, 0] == 0).all(), "a row used a filter this decoder does not undo"
    return raw[:, 1:].reshape(h, w, 3)


def at(img, x, y):
    """The pixel under CSS point (x, y)."""
    return tuple(int(c) for c in img[int(y * S), int(x * S)])


BG_RGB = spark_png.parse_colour(BG)[0]


def test_it_is_a_valid_png_at_twice_the_display_size():
    img = decode(spark_png.spark_png((40, 55, 60), COLORS, BG))
    assert img.shape == (spark_png.HEIGHT * S, spark_png.WIDTH * S, 3)


def test_the_shape_is_the_pages_shape():
    """Every point sits where board_traces._spark_points puts it, in the same
    proportion of the lane, so the email's line is the page's line rescaled."""
    path = tuple(50 + 45 * math.sin(i / 5) for i in range(52))
    xs, ys = spark_png.path_points(path)
    row_y = 7
    web_xs, web_ys = bt._spark_points(bt.MarketRead("X", "C", (50,) * 4, path=path), row_y)
    mid = spark_png.HEIGHT / 2
    for y, web_y in zip(ys, web_ys):
        # Offset from the midline as a share of the amplitude, on both surfaces.
        assert (mid - y) / spark_png.AMPLITUDE == pytest.approx(
            (row_y - web_y) / bt.SPARK_AMPLITUDE)
    span, web_span = xs[-1] - xs[0], web_xs[-1] - web_xs[0]
    for x, web_x in zip(xs, web_xs):
        assert (x - xs[0]) / span == pytest.approx((web_x - web_xs[0]) / web_span)


def test_a_high_index_draws_up_and_a_low_one_down():
    """Image y grows downward, as the page's reversed axis does. Getting this
    backwards flips every path in every email."""
    _, ys_high = spark_png.path_points((50, 100))
    _, ys_low = spark_png.path_points((50, 0))
    mid = spark_png.HEIGHT / 2
    assert ys_high[-1] == pytest.approx(mid - spark_png.AMPLITUDE)
    assert ys_low[-1] == pytest.approx(mid + spark_png.AMPLITUDE)


@pytest.mark.parametrize("latest,pole", [(80, "bull"), (50, "bull"), (20, "bear")])
def test_the_end_dot_takes_the_pages_side(latest, pole):
    path = (50,) * 10 + (latest,)
    img = decode(spark_png.spark_png(path, COLORS, BG))
    xs, ys = spark_png.path_points(path)
    expected = spark_png.parse_colour(getattr(COLORS, pole))[0]
    assert at(img, xs[-1], ys[-1]) == expected


def test_the_midline_is_visible_and_dotted():
    """The user-visible point of the change: a reader can see the 50 line. A path
    pinned at the top keeps the line clear of it, so these pixels are midline
    alone. On a dash it is brighter than the background; between dashes it is
    the background, which is what makes it read as a reference and not a path."""
    img = decode(spark_png.spark_png((95,) * 52, COLORS, BG))
    mid = spark_png.HEIGHT / 2 - 0.25        # inside the 1px line, not on its edge
    x0 = spark_png._INSET
    on = at(img, x0 + 1.0, mid)
    off = at(img, x0 + spark_png.DASH_ON + 1.0, mid)
    assert off == BG_RGB
    assert sum(on) > sum(BG_RGB) + 3 * 30, f"midline {on} barely above {BG_RGB}"


def test_the_midline_is_fainter_than_the_path_it_sits_under():
    """Visible, but still secondary: the path is what the row is about."""
    path = (95,) * 26 + (5,) * 26
    img = decode(spark_png.spark_png(path, COLORS, BG))
    xs, ys = spark_png.path_points(path)
    mid = spark_png.HEIGHT / 2 - 0.25
    line = at(img, xs[3], ys[3] - 0.25)
    midline = at(img, spark_png._INSET + 1.0, mid)
    assert sum(line) > sum(midline) > sum(BG_RGB)


def test_a_path_too_short_to_draw_still_gets_its_midline():
    """Every market row has one on the page, path or not."""
    img = decode(spark_png.spark_png((None, 60.0), COLORS, BG))
    assert at(img, spark_png._INSET + 1.0, spark_png.HEIGHT / 2 - 0.25) != BG_RGB
    corner = at(img, spark_png.WIDTH - 1, 1)
    assert corner == BG_RGB


def test_it_needs_no_pillow():
    """The deployment updates by git pull and does not reinstall, and Pillow is
    not a declared dependency. A Pillow import here would fail on the server on a
    Friday and nowhere else."""
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(spark_png))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names} | {
        node.module.split(".")[0] for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module}
    assert "PIL" not in imported
