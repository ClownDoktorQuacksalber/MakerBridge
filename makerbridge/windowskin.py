"""Turn RM2k system graphics into MV/MZ window skins.

An RM2k system graphic (160x80, palette index 0 transparent) holds the
window background, frame, cursor, scroll arrows and the 20 message colours.
MV/MZ keep the same things in a 192x192 ``img/system/Window.png``, laid out
at three times RM2k's pixel size - so most pieces only need a 3x
nearest-neighbour blow-up to land exactly in the slot MV reads, and the
converted game gets its own windows instead of MV's blue default.

RM2k system graphic (verified against the test projects' sheets)::

    (0,0,32,32)    background, stretched (or tiled, see message_stretch)
    (32,0,32,32)   frame, 8px corners and edges; inside it
    (40,8,16,8)    up scroll arrow
    (40,16,16,8)   down scroll arrow (also the blinking "more text" sign)
    (64,0,32,32)   cursor, frame 1 (96,0) is frame 2 of its animation
    (128,0,32,32)  4x4 small 8px animated icons (RM2k3 battle decorations)
    (0,32,16,16)   background colour, (16,32,16,16) text shadow colour
    (32,32,88,16)  timer digits 0-9 and ':' (8x16 each)
    (128,32,32,16) battle shadows
    (0,48,160,32)  20 text colours, 16x16 vertical gradients, 10 per row

MV/MZ Window.png (coordinates from rmmz_core.js Window._refresh* and
rmmz_managers.js ColorManager)::

    (0,0,96,96)     background, drawn stretched from (0,0,95,95)
    (0,96,96,96)    pattern tiled over the background at 1:1
    (96,0,96,96)    frame, 24px corners and edges (interior unused)
    (132,24,24,12)  up arrow, (132,60,24,12) down arrow
    (96,96,48,48)   cursor, 9-slice with 4px corners; (120,120) is
                    ColorManager.pendingColor
    (144,96,48,48)  pause sign, four 24x24 frames shown in the order
                    top-left, top-right, bottom-left, bottom-right
    (96,144,96,48)  32 text colours, 12x12 cells, 8 per row, read at the
                    cell's pixel (6, 6)

Timer digits, battle shadows, the small icons, the second cursor frame and
the text shadow colour have no place in a window skin and are dropped.
"""

from __future__ import annotations

import logging
import os

from .xyz import IMAGE_EXTENSIONS, XyzError, open_image

log = logging.getLogger(__name__)

RM_SIZE = (160, 80)
MV_SIZE = (192, 192)
SKIN_SCALE = 3          # RM2k's 32px pieces -> MV's 96px slots

# RM2k source rectangles (x, y, w, h)
RM_BACKGROUND = (0, 0, 32, 32)
RM_FRAME = (32, 0, 32, 32)
RM_UP_ARROW = (40, 8, 16, 8)
RM_DOWN_ARROW = (40, 16, 16, 8)
RM_CURSOR = (64, 0, 32, 32)
RM_SHADOW_PIXEL = (16, 32)
RM_COLOR_ORIGIN = (0, 48)
RM_COLOR_CELL = 16
RM_COLORS_PER_ROW = 10
RM_COLOR_COUNT = 20

# MV destination slots
MV_BACKGROUND = (0, 0)
MV_TILE = (0, 96, 96, 96)
MV_FRAME = (96, 0)
MV_FRAME_INTERIOR = (120, 24, 168, 72)   # box: never drawn by the frame
MV_UP_ARROW = (132, 24, 24, 12)
MV_DOWN_ARROW = (132, 60, 24, 12)
MV_CURSOR = (96, 96, 48, 48)
MV_PAUSE = (144, 96)
MV_PAUSE_FRAME = 24
MV_COLOR_ORIGIN = (96, 144)
MV_COLOR_CELL = 12
MV_COLORS_PER_ROW = 8

# MV's text colour slot -> where its colour comes from.
#   int     the RM2k text colour with that number (gradient averaged, the
#           same value RM2kCompat.js uses for \C[n], so both agree)
#   "shadow" RM2k's text shadow colour
#   str     a fixed CSS colour: MZ's own default, for gauges and markers
#           RM2k simply does not have
# Slots 0-15 keep RM2k's numbering so \C[n] in non-message windows still
# matches.  16-29 carry fixed meanings in MZ's ColorManager, so they take the
# RM2k colour the RM2k engine uses for the same purpose (EasyRPG's Font
# colours: 0 default, 1 system terms, 3 disabled, 4 critical, 5 knocked out).
# RM2k colours 16-19 lose their slot here; message \C[16..19] still shows
# them because the plugin reads the system graphic's colours directly.
MV_COLOR_SOURCES = (
    0, 1, 2, 3, 4, 5, 6, 7,
    8, 9, 10, 11, 12, 13, 14, 15,
    1,           # 16 systemColor      <- RM2k 1, labels like "HP", "Lv"
    4,           # 17 crisisColor      <- RM2k 4, low HP
    5,           # 18 deathColor       <- RM2k 5, knocked out
    "shadow",    # 19 gaugeBackColor   <- RM2k's dark text shadow colour
    "#e08040",   # 20 hpGaugeColor1
    "#f0c040",   # 21 hpGaugeColor2
    "#4080c0",   # 22 mpGaugeColor1
    "#40c0f0",   # 23 mpGaugeColor2 / mpCostColor
    "#80ff80",   # 24 powerUpColor
    "#c04080",   # 25 powerDownColor
    "#8080ff",   # 26 ctGaugeColor1
    "#80c0ff",   # 27 ctGaugeColor2
    "#00a040",   # 28 tpGaugeColor1
    "#00e060",   # 29 tpGaugeColor2 / tpCostColor
    "#8080ff",   # 30 unused by the engine
    "#80c0ff",   # 31 unused by the engine
)

# File names the MV/MZ runtime itself loads from img/system.  A converted
# skin with one of these names would replace an engine sheet, so it is
# skipped.  "Window" is absent on purpose: it is where the default goes.
MV_RESERVED = {
    "balloon", "buttonset", "damage", "gameover", "iconset", "loading",
    "shadow1", "shadow2", "splash", "states", "weapons1", "weapons2",
    "weapons3",
}

# lcf System.message_stretch: 0 stretches the background, 1 tiles it.
STRETCH_TILED = 1


def convert_all(project, target: str, log) -> list[str]:
    """Write every graphic in System/ as ``img/system/<name>.png``.

    The database's default system graphic is written a second time as
    ``Window.png``, because that is the only skin MV/MZ ever load unless a
    plugin says otherwise.  System2/ (RM2k3's battle gauges) is not a window
    skin and is left alone.
    """
    files = project.asset_files("system", IMAGE_EXTENSIONS)
    if not files:
        return []
    system = project.database.get("system", {})
    default = (system.get("system_name") or "").lower()
    tiled = system.get("message_stretch", 0) == STRETCH_TILED
    dest = os.path.join(target, "img", "system")
    os.makedirs(dest, exist_ok=True)

    converted: list[str] = []
    default_skin = None
    for entry, path in files:
        stem = os.path.splitext(entry)[0]
        if stem.lower() in MV_RESERVED:
            log.warning("system/%s clashes with an MV system file - skipped", entry)
            continue
        try:
            skin = build_skin(open_image(path), tiled)
        except (OSError, XyzError, ValueError) as exc:
            log.error("system/%s could not be converted: %s", entry, exc)
            continue
        skin.save(os.path.join(dest, stem + ".png"))
        converted.append(stem)
        if project.from_rtp(path):
            log.info("   system/%s taken from the RTP", entry)
        if stem.lower() == default:
            default_skin = skin

    if default_skin is not None:
        default_skin.save(os.path.join(dest, "Window.png"))
    elif default:
        log.warning("default system graphic %r is not in System/ (RTP?) - "
                    "img/system/Window.png keeps the engine's skin",
                    system.get("system_name"))
    return converted


def build_skin(image, tiled: bool = False):
    """Return the 192x192 MV window skin for one RM2k system graphic."""
    from PIL import Image

    from .assets import _load_rgba

    if image.size != RM_SIZE:
        raise ValueError("is %dx%d, expected %dx%d" % (*image.size, *RM_SIZE))
    rgb = image.convert("RGB")
    sheet = _load_rgba(image)
    skin = Image.new("RGBA", MV_SIZE, (0, 0, 0, 0))

    background = _scaled(sheet, RM_BACKGROUND, SKIN_SCALE)
    if tiled:
        # The stretched layer stays empty and the tile layer, drawn at 1:1,
        # repeats the 3x background - RM2k's "tile" wallpaper setting.
        skin.paste(background, MV_TILE[:2])
    else:
        skin.paste(background, MV_BACKGROUND)

    # The frame scales straight into place; its interior holds the 3x
    # arrows, which MV would never draw there, so it is cleared before the
    # arrows go into the smaller slots MV actually reads.
    skin.paste(_scaled(sheet, RM_FRAME, SKIN_SCALE), MV_FRAME)
    skin.paste((0, 0, 0, 0), MV_FRAME_INTERIOR)
    up = _fit_sprite(sheet, RM_UP_ARROW, MV_UP_ARROW[2:])
    down = _fit_sprite(sheet, RM_DOWN_ARROW, MV_DOWN_ARROW[2:])
    skin.paste(up, MV_UP_ARROW[:2])
    skin.paste(down, MV_DOWN_ARROW[:2])

    # 32 -> 48 is 1.5x.  RM2k cursors draw their border in the outer couple
    # of pixels and fill the rest flat, so MV's 4px 9-slice keeps the border
    # crisp and only stretches the flat middle.
    skin.paste(_resized(sheet, RM_CURSOR, MV_CURSOR[2:]), MV_CURSOR[:2])

    # RM2k blinks the down arrow at the bottom of a waiting message.  MV
    # cycles four pause frames; filling the first two and leaving the last
    # two empty gives the same on/off blink.  The arrow sits at the bottom
    # of its frame because MV anchors the sign on the window's bottom edge.
    p = MV_PAUSE_FRAME
    for frame in (0, 1):
        x = MV_PAUSE[0] + frame * p + (p - down.width) // 2
        y = MV_PAUSE[1] + p - down.height
        skin.paste(down, (x, y))

    rm_colors = [_average_color(rgb, n) for n in range(RM_COLOR_COUNT)]
    shadow = rgb.getpixel(RM_SHADOW_PIXEL)
    for slot, source in enumerate(MV_COLOR_SOURCES):
        if source == "shadow":
            color = shadow
        elif isinstance(source, int):
            color = rm_colors[source]
        else:
            color = tuple(int(source[i:i + 2], 16) for i in (1, 3, 5))
        x = MV_COLOR_ORIGIN[0] + (slot % MV_COLORS_PER_ROW) * MV_COLOR_CELL
        y = MV_COLOR_ORIGIN[1] + (slot // MV_COLORS_PER_ROW) * MV_COLOR_CELL
        skin.paste(color + (255,), (x, y, x + MV_COLOR_CELL, y + MV_COLOR_CELL))
    return skin


def _scaled(sheet, rect, factor: int):
    x, y, w, h = rect
    return sheet.crop((x, y, x + w, y + h)).resize((w * factor, h * factor), 0)


def _resized(sheet, rect, size):
    x, y, w, h = rect
    return sheet.crop((x, y, x + w, y + h)).resize(tuple(size), 0)


def _fit_sprite(sheet, rect, size):
    """Scale the drawn part of an RM2k arrow cell into an MV slot.

    MV's arrow slots (24x12) are only 1.5x RM2k's 16x8 cells, and 1.5x
    nearest-neighbour makes a lopsided arrow.  The arrow itself is far
    smaller than its cell, though, so its bounding box is scaled by the
    largest whole factor that fits and centred in the slot; 1.5x is only
    the fallback for an arrow that fills its cell.
    """
    from PIL import Image

    x, y, w, h = rect
    cell = sheet.crop((x, y, x + w, y + h))
    box = cell.getchannel("A").getbbox()
    out = Image.new("RGBA", tuple(size), (0, 0, 0, 0))
    if not box:
        return out
    sprite = cell.crop(box)
    for factor in (3, 2):
        sw, sh = sprite.width * factor, sprite.height * factor
        if sw <= size[0] and sh <= size[1]:
            sprite = sprite.resize((sw, sh), 0)
            # Keep the arrow's horizontal centre where RM2k had it in the
            # cell, clamped into the slot; vertically centre it.
            cx = (box[0] + box[2]) / 2 * size[0] / w
            left = min(max(0, round(cx - sw / 2)), size[0] - sw)
            out.paste(sprite, (left, (size[1] - sh) // 2))
            return out
    return cell.resize(tuple(size), 0)


def _average_color(rgb, n: int) -> tuple[int, int, int]:
    """Average of RM2k text colour ``n``'s gradient cell.

    MV paints text in one flat colour; the gradient's average is what the
    RM2k text looks like from a distance, and it is the value the plugin
    uses for \\C[n], so menus and messages agree.
    """
    x = RM_COLOR_ORIGIN[0] + (n % RM_COLORS_PER_ROW) * RM_COLOR_CELL
    y = RM_COLOR_ORIGIN[1] + (n // RM_COLORS_PER_ROW) * RM_COLOR_CELL
    cell = list(rgb.crop((x, y, x + RM_COLOR_CELL, y + RM_COLOR_CELL)).getdata())
    return tuple(sum(p[i] for p in cell) // len(cell) for i in range(3))
