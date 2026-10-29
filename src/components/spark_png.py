"""The board's 52-week path as a PNG, for the one surface that cannot draw it.

The page draws each market's path as a Plotly line; the weekly email cannot,
because no mainstream client renders inline SVG and Gmail blocks data: URIs. So
the email embeds each path as a small PNG (a CID part of the message), and this
draws it.

Nothing about the picture is decided here. Every number comes from board_traces,
the module the page's figure is drawn from: the row height, the amplitude around
the 50 midline, the end dot's size and its bull/bear rule, the line and midline
colours, and the midline's dash. `path_points` is `board_traces._spark_points`
in pixels. A change to the page's path therefore moves the email's with it, and
test_spark_png holds the two to the same rule.

Drawn with numpy and written with zlib rather than through Pillow. Pillow is not
a dependency of this app (it is installed locally only because matplotlib pulls
it in, and matplotlib is not declared either), and the deployment updates by
`git pull` without reinstalling anything, so a Pillow import would be a Friday
send that fails on the server and nowhere else. numpy is already a hard
dependency. The antialiasing is analytic: each pixel's coverage is its distance
from the line, which is the same answer supersampling converges on, at the cost
of one vectorised distance per segment.
"""
import struct
import zlib

import cotmetrics.constants as const
import numpy as np

from components import board_traces

#: The path's box in CSS pixels. The height is the board's own row, so the path
#: has the vertical room it has on the page.
WIDTH = 120
HEIGHT = board_traces.ROW_PX
#: Drawn at twice that and displayed at 1x, so it stays sharp on a HiDPI screen.
SCALE = 2
#: Half-height of the path around the midline, in pixels: the page's amplitude,
#: which is in row units there.
AMPLITUDE = board_traces.SPARK_AMPLITUDE * board_traces.ROW_PX
END_RADIUS = board_traces.SPARK_END_SIZE / 2
LINE_WIDTH = 1.0
#: Plotly's "dot" at width 1: its dashStyle draws max(width, 3)px on, the same off.
DASH_ON = DASH_OFF = 3.0

#: Inset at both ends, so the end dot is never clipped by the image edge.
_INSET = END_RADIUS + 0.5


def parse_colour(colour):
    """`(r, g, b), alpha` from '#rrggbb' or 'rgba(r, g, b, a)'."""
    text = str(colour).strip()
    if text.startswith("rgba("):
        r, g, b, a = (part.strip() for part in text[5:-1].split(","))
        return (int(r), int(g), int(b)), float(a)
    h = text.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)), 1.0


def path_points(path, width=WIDTH, height=HEIGHT):
    """(xs, ys) in pixels, or ([], []) with fewer than two values.

    `board_traces._spark_points` with pixels for row units: the same dropping of
    missing weeks, the same even spacing of what is left, the same clamp, and a
    high index mapping UP (to a smaller y), as on the page.
    """
    values = [v for v in path if v is not None]
    if len(values) < 2:
        return [], []
    n = len(values)
    mid = height / 2
    xs = [_INSET + (width - 2 * _INSET) * i / (n - 1) for i in range(n)]
    ys = [mid - (min(100.0, max(0.0, v)) - const.INDEX_NEUTRAL) / 50.0 * AMPLITUDE
          for v in values]
    return xs, ys


def end_colour(path, colors):
    """The page's end-dot rule: bull at or above neutral, bear below."""
    latest = [v for v in path if v is not None][-1]
    return colors.bull if latest >= const.INDEX_NEUTRAL else colors.bear


def _grid(width, height, scale):
    """Pixel centres, in CSS pixels."""
    x = (np.arange(width * scale) + 0.5) / scale
    y = (np.arange(height * scale) + 0.5) / scale
    return np.meshgrid(x, y)


def _coverage(distance, half_width, scale):
    """How much of a pixel a stroke of `half_width` covers, given the pixel's
    distance from the stroke's centre: 1 inside, 0 outside, a one-device-pixel
    ramp across the edge."""
    return np.clip((half_width - distance) * scale + 0.5, 0.0, 1.0)


def _polyline_distance(px, py, xs, ys):
    """Each pixel's distance to the nearest point of the polyline."""
    p = np.stack([px.ravel(), py.ravel()], axis=1)[:, None, :]          # (N,1,2)
    a = np.stack([xs[:-1], ys[:-1]], axis=1)[None, :, :]                # (1,M,2)
    b = np.stack([xs[1:], ys[1:]], axis=1)[None, :, :]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12),
                0.0, 1.0)
    nearest = a + t[..., None] * ab
    return np.sqrt(((p - nearest) ** 2).sum(-1)).min(axis=1).reshape(px.shape)


def _over(canvas, colour, alpha):
    """Composite `colour` onto `canvas` at a per-pixel `alpha`, in place."""
    canvas += (np.asarray(colour, dtype=float) - canvas) * alpha[..., None]


def render(path, colors, background, width=WIDTH, height=HEIGHT, scale=SCALE):
    """The picture as an (h, w, 3) uint8 array, at `scale`.

    Back to front, as the page layers it: the background, the dotted midline,
    the path, the end dot. A path too short to draw still gets its midline, as
    every market row does on the page.
    """
    bg, _ = parse_colour(background)
    canvas = np.empty((height * scale, width * scale, 3), dtype=float)
    canvas[...] = bg
    px, py = _grid(width, height, scale)

    mid_rgb, mid_alpha = parse_colour(board_traces.SPARK_MIDLINE)
    across = _coverage(np.abs(py - height / 2), LINE_WIDTH / 2, scale)
    along = ((px - _INSET) % (DASH_ON + DASH_OFF)) < DASH_ON
    lane = (px >= _INSET) & (px <= width - _INSET)
    _over(canvas, mid_rgb, mid_alpha * across * along * lane)

    xs, ys = path_points(path, width, height)
    if xs:
        line_rgb, line_alpha = parse_colour(board_traces.SPARK_LINE)
        distance = _polyline_distance(px, py, np.asarray(xs), np.asarray(ys))
        _over(canvas, line_rgb, line_alpha * _coverage(distance, LINE_WIDTH / 2, scale))

        dot_rgb, _ = parse_colour(end_colour(path, colors))
        to_end = np.hypot(px - xs[-1], py - ys[-1])
        _over(canvas, dot_rgb, _coverage(to_end, END_RADIUS, scale))

    return np.clip(np.rint(canvas), 0, 255).astype(np.uint8)


def encode_png(rgb):
    """An (h, w, 3) uint8 array as a PNG: 8-bit truecolour, no filtering, one
    IDAT. Opaque on purpose: the email's background is baked in, so no client's
    handling of transparency (or of dark mode) can change what the reader sees."""
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def spark_png(path, colors, background):
    """One market's path, ready to embed."""
    return encode_png(render(path, colors, background))
