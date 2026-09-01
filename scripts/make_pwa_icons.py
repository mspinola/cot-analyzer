"""Generate the PWA icon set into src/assets/. The icons' reproducer.

The site had no brand image at all (the favicon is Dash's default), so this is
the app's first icon: three bars in the participant colors the About guide
teaches (red Commercials, blue Large Specs, yellow Small Specs) on the app's
dark ground, read as a positioning chart. Drawn with pillow so a color or
geometry change is a diff here and a re-run, not an untraceable binary edit.

    .venv/bin/python scripts/make_pwa_icons.py

Four files: icon-192.png and icon-512.png (any-purpose, rounded corners like a
launcher expects), icon-maskable-512.png (full-bleed background with the marks
inside the ~80% safe zone, so adaptive-icon masks of any shape keep them), and
apple-touch-icon.png (180px, opaque, square; iOS applies its own rounding).
"""
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "src" / "assets"

BACKGROUND = "#1a1a1a"
#: Commercials, Large Specs, Small Specs; the About guide's red/blue/yellow.
BAR_COLORS = ("#EF4444", "#60A5FA", "#FACC15")
#: Bar heights as fractions of the drawable height: the shape of a market where
#: Commercials are loaded, Large Specs middling, Small Specs light.
BAR_HEIGHTS = (0.92, 0.55, 0.34)


def draw_icon(size, pad_frac, corner_frac=None):
    """One icon: bars centered in a padded square; corners rounded when asked."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if corner_frac is None:
        d.rectangle([0, 0, size, size], fill=BACKGROUND)
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1],
                            radius=int(size * corner_frac), fill=BACKGROUND)

    pad = size * pad_frac
    span = size - 2 * pad
    gap = span * 0.12
    bar_w = (span - 2 * gap) / 3
    baseline = size - pad
    for i, (color, h_frac) in enumerate(zip(BAR_COLORS, BAR_HEIGHTS)):
        x0 = pad + i * (bar_w + gap)
        top = baseline - span * h_frac
        d.rounded_rectangle([x0, top, x0 + bar_w, baseline],
                            radius=int(bar_w * 0.22), fill=color)
    return img


def main():
    draw_icon(192, pad_frac=0.18, corner_frac=0.18).save(ASSETS / "icon-192.png")
    draw_icon(512, pad_frac=0.18, corner_frac=0.18).save(ASSETS / "icon-512.png")
    # Maskable: full-bleed square, marks pulled into the safe zone so a circle,
    # squircle or teardrop mask cannot clip them.
    draw_icon(512, pad_frac=0.26).save(ASSETS / "icon-maskable-512.png")
    # iOS: opaque and square; the platform rounds it itself.
    draw_icon(180, pad_frac=0.20).save(ASSETS / "apple-touch-icon.png")
    print(f"wrote 4 icons into {ASSETS}")


if __name__ == "__main__":
    main()
