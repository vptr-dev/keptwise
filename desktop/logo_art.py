"""The Keptwise logo, drawn from its shapes: three bookmarks, one behind the other.

The same outline is in frontend/src/components/Logo.tsx (as SVG), so the
app, the program icon and the taskbar icon all match. The program and
taskbar icon is the plain logo: white in front, light greys behind, no tile.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

# The front bookmark, in its own units: (command, points). "C" is a curve.
FRONT: list[tuple[str, list[tuple[float, float]]]] = [
    ("M", [(0, 130)]),
    ("C", [(0, 88), (24, 70), (60, 62)]),
    ("L", [(296, 0)]),
    ("C", [(322, -6), (343, 12), (343, 38)]),
    ("L", [(343, 386)]),
    ("C", [(343, 402), (332, 404), (324, 398)]),
    ("L", [(186, 292)]),
    ("C", [(180, 287), (176, 287), (170, 292)]),
    ("L", [(22, 433)]),
    ("C", [(14, 441), (0, 440), (0, 428)]),
]
# Where each bookmark sits, back to front, in a 640 x 640 square.
PLACES = [(35, 19), (148, 100), (261, 181)]
VIEW = 640
GAP = 36  # the see-through line between two bookmarks
BACK, MIDDLE = (122, 122, 128), (178, 178, 184)
WHITE = (247, 247, 247)
TILE = (28, 28, 28)


def _points(place: tuple[float, float], scale: float) -> list[tuple[float, float]]:
    """The outline as a list of points (curves cut into short straight lines)."""
    dx, dy = place
    out: list[tuple[float, float]] = []
    for command, pts in FRONT:
        if command == "C":
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = out[-1], *pts
            for i in range(1, 17):
                t = i / 16
                u = 1 - t
                out.append((
                    u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                    u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
                ))
        else:
            out.append(pts[0])
    return [((x + dx) * scale, (y + dy) * scale) for x, y in out]


def draw_logo(size: int, front: tuple[int, int, int] = WHITE, tile: bool = False) -> Image.Image:
    """The logo as a size x size picture: on a rounded dark tile (program and
    taskbar icons), or on nothing (tile=False)."""
    big = size * 4  # drawn large, then shrunk, for smooth edges
    inset = 0.14 if tile else 0.0
    scale = big * (1 - 2 * inset) / VIEW
    shift = big * inset
    picture = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    if tile:
        ImageDraw.Draw(picture).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=(*TILE, 255))
    outlines = [[(x + shift, y + shift) for x, y in _points(place, scale)] for place in PLACES]
    for index, colour in enumerate((BACK, MIDDLE, front)):
        shape = Image.new("L", (big, big), 0)
        draw = ImageDraw.Draw(shape)
        draw.polygon(outlines[index], fill=255)
        for later in outlines[index + 1:]:  # cut out a gap round the ones in front
            draw.polygon(later, fill=0)
            draw.line([*later, later[0]], fill=0, width=round(GAP * 2 * scale), joint="curve")
            r = GAP * scale
            for x, y in later:  # round every corner of the gap, with no hairlines left
                draw.ellipse((x - r, y - r, x + r, y + r), fill=0)
        picture.paste(Image.new("RGBA", (big, big), (*colour, 255)), (0, 0), shape)
    return picture.resize((size, size), Image.LANCZOS)


ICON_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def save_icon(path: object, front: tuple[int, int, int] = WHITE) -> None:
    """A Windows .ico with every usual size, each drawn at its own size."""
    pictures = [draw_logo(s, front) for s in ICON_SIZES]
    pictures[-1].save(path, format="ICO", sizes=[(s, s) for s in ICON_SIZES], append_images=pictures[:-1])
