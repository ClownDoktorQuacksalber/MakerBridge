"""Copy and rescale RM2k media into the folders MV expects.

Everything is scaled with nearest-neighbour so the pixel art stays crisp; the
factors come from MV's own geometry (48px tiles against RM2k's 16px, 144px
faces against 48px).  Character sheets keep RM2k's 2:3 cell ratio because MV
derives the frame size from the sheet, so a 576x512 sheet simply gives 48x64
frames.
"""

from __future__ import annotations

import logging
import os
import shutil

from .xyz import IMAGE_EXTENSIONS, XyzError, open_image

log = logging.getLogger(__name__)

TILE_SCALE = 3        # 16 -> 48
FACE_SCALE = 3        # 48 -> 144
# Characters must use the *same* factor as the tiles, or they stop overhanging
# their square the way RM2k draws them.  RM2k puts a 24x32 sprite on a 16x16
# tile: 16px of it stick out above and 4px to each side, which is why two
# neighbouring events with a graphic overlap.  At 3x that becomes a 72x96 cell
# on a 48px tile - 48px above, 12px to each side - and MV derives the frame
# size from the sheet (width/12, height/8), so 864x768 sheets just work.
CHAR_SCALE = 3        # 24x32 -> 72x96 cells
ANIM_SCALE = 2         # 96px animation cells -> 192px
# RM2k runs at 320x240, MV defaults to 816x624.
SCREEN_SCALE = 816 / 320
SCREEN_W, SCREEN_H = 816, 624
# Full-screen pictures (title, game over, battle backgrounds) fill RM2k's
# whole 320x240 screen; stretched by axis they fill MV's whole 816x624
# instead of leaving 12 rows uncovered (816/320 = 2.55, 624/240 = 2.6).
FULLSCREEN = (SCREEN_W / 320, SCREEN_H / 240)

# RM2k folder -> (MV folder, scale, expected source size or None, transparent)
# "transparent" follows EasyRPG's cache.cpp material table: palette index 0
# is see-through except in Backdrop, GameOver, Panorama and Title, which are
# drawn opaque.  A scale may be a (x, y) pair.
IMAGE_JOBS = [
    ("charset", "characters", CHAR_SCALE, (288, 256), True),
    # Pictures keep their original size on purpose.  A project like Velsarbor
    # ships ~1700 of them and shows dozens at once, and MV's bundled NW.js is
    # a 32-bit process: enlarging them 2.55x multiplies decoded bitmap memory
    # by 6.5 and the renderer dies with no JavaScript error to catch.
    # RM2kCompat.js scales them when they are shown instead, which looks the
    # same and costs nothing.
    ("picture", "pictures", 1.0, None, True),
    ("panorama", "parallaxes", TILE_SCALE, None, False),
    # RM2k's Battle/ holds battle *animation* sheets; enemy battlers live in
    # Monster/, which many projects leave to the RTP.
    # Animation sheets: RM2k cells are 96px (RM2003's large ones 128px),
    # MV's are 192px, five to a row in both - so scaling the sheet keeps
    # every cell where MV looks for it.  The screen-size difference goes
    # into each cell's scale instead.
    ("battle", "animations", ANIM_SCALE, None, True),
    ("battle2", "animations", ANIM_SCALE * 96 / 128, None, True),
    # Monsters go to both folders: MV/MZ read enemies/ in front view and
    # sv_enemies/ in side view (RM2003).
    ("monster", "enemies", SCREEN_SCALE, None, True),
    ("monster", "sv_enemies", SCREEN_SCALE, None, True),
    ("title", "titles1", FULLSCREEN, None, False),
    ("backdrop", "battlebacks1", FULLSCREEN, None, False),
]
# GameOver/ is not a folder MV reads: the one graphic the database names
# becomes img/system/GameOver.png (see convert_gameover).

AUDIO_JOBS = [
    ("music", "bgm"),
    ("sound", "se"),
]

MV_AUDIO_EXT = {".ogg", ".m4a"}
# What RM2k plays (and MV, after transcoding); anything else in the audio
# folders is not copied.
AUDIO_EXT = {".mid", ".midi", ".wav", ".mp3", ".ogg", ".m4a", ".wma"}
# Copied, but MV needs them transcoded first.
NEEDS_TRANSCODE_EXT = AUDIO_EXT - MV_AUDIO_EXT


def _scaled_size(image, scale) -> tuple[int, int]:
    sx, sy = scale if isinstance(scale, tuple) else (scale, scale)
    return max(1, round(image.width * sx)), max(1, round(image.height * sy))


def _log_rtp(project, kind: str, names, log) -> None:
    names = sorted(names)
    if names:
        shown = ", ".join(names[:15]) + (" ..." if len(names) > 15 else "")
        log.info("   %d %s file(s) taken from the RTP: %s", len(names), kind, shown)


def convert_images(project, target: str, log, opaque_pictures=(),
                   opaque_patterns=()) -> dict[str, int]:

    counts: dict[str, int] = {}
    for kind, mv_folder, scale, expected, transparent in IMAGE_JOBS:
        files = project.asset_files(kind, IMAGE_EXTENSIONS)
        if not files:
            continue
        dest = os.path.join(target, "img", mv_folder)
        os.makedirs(dest, exist_ok=True)
        written = 0
        from_rtp = []
        for entry, path in files:
            stem = os.path.splitext(entry)[0]
            try:
                raw = open_image(path)
                image = _load_rgba(raw) if transparent else raw.convert("RGBA")
            except (OSError, XyzError) as exc:
                log.error("%s/%s could not be read: %s", kind, entry, exc)
                continue
            if expected and image.size != expected:
                log.warning("%s/%s is %dx%d, expected %dx%d - scaling anyway",
                            kind, entry, *image.size, *expected)
            if kind == "charset":
                image = _reorder_charset_rows(image)
            out = image.resize(_scaled_size(image, scale), 0)
            out.save(os.path.join(dest, stem + ".png"))
            if kind == "picture" and _opaque(stem, opaque_pictures, opaque_patterns):
                # Shown with "transparent colour" off somewhere: keep index 0.
                from .mv.events import OPAQUE_SUFFIX
                opaque = open_image(path).convert("RGBA")
                opaque.save(os.path.join(dest, stem + OPAQUE_SUFFIX + ".png"))
            written += 1
            if project.from_rtp(path):
                from_rtp.append(entry)
        counts[mv_folder] = counts.get(mv_folder, 0) + written
        log.info("img/%-14s %3d file(s) from %s/", mv_folder, written, kind)
        _log_rtp(project, kind, from_rtp, log)

    counts["faces"] = _convert_faces(project, target, log)
    counts["gameover"] = convert_gameover(project, target, log)

    # Imported here: windowskin borrows _load_rgba from this module.
    from . import windowskin
    skins = windowskin.convert_all(project, target, log)
    counts["system"] = len(skins)
    if skins:
        log.info("img/system         %3d window skin(s) from system/ "
                 "(default %s also as Window.png)", len(skins),
                 project.database.get("system", {}).get("system_name") or "-")
    return counts


def convert_gameover(project, target: str, log) -> int:
    """The database's game over graphic, as MV's img/system/GameOver.png.

    MV and MZ show exactly that file on the game over screen; RM2k shows
    the GameOver/ image the database names, opaque and over the whole
    screen.  No graphic named means a black screen in RM2k too."""
    from PIL import Image

    name = project.database.get("system", {}).get("gameover_name") or ""
    dest = os.path.join(target, "img", "system")
    os.makedirs(dest, exist_ok=True)
    out_path = os.path.join(dest, "GameOver.png")
    if not name:
        Image.new("RGBA", (SCREEN_W, SCREEN_H), (0, 0, 0, 255)).save(out_path)
        log.info("img/system         GameOver.png black (no game over graphic set)")
        return 1
    path = project.find_asset("gameover", name)
    if not path:
        log.warning("game over graphic %r not found - img/system/GameOver.png "
                    "keeps the engine's picture", name)
        return 0
    try:
        image = open_image(path).convert("RGBA")
    except (OSError, XyzError) as exc:
        log.error("gameover/%s could not be read: %s", os.path.basename(path), exc)
        return 0
    image.resize((SCREEN_W, SCREEN_H), 0).save(out_path)
    log.info("img/system         GameOver.png from gameover/%s%s",
             os.path.basename(path), " (RTP)" if project.from_rtp(path) else "")
    return 1


# A character's four rows face up, right, down, left in RM2k, but MV reads them
# as down, left, right, up (Sprite_Character: (direction - 2) / 2).  Each entry
# is the RM2k row that MV row i must show.
_CHARSET_ROW_ORDER = (2, 3, 1, 0)


def _reorder_charset_rows(image):
    """Rearrange every character's direction rows into MV's order.

    A sheet is 2 characters tall with 4 rows each, so a row is height / 8.
    The columns (animation frames) already match and are left alone.
    """
    row_height = image.height // 8
    if not row_height:
        return image
    out = image.copy()
    for character_row in range(2):
        top = character_row * 4 * row_height
        for mv_row, rm_row in enumerate(_CHARSET_ROW_ORDER):
            src_y = top + rm_row * row_height
            band = image.crop((0, src_y, image.width, src_y + row_height))
            out.paste(band, (0, top + mv_row * row_height))
    return out


def _convert_faces(project, target: str, log) -> int:
    """RM2k face sheets are 4x4 of 48px; MV reads 144px cells from a 4-wide sheet."""

    files = project.asset_files("faceset", IMAGE_EXTENSIONS)
    if not files:
        return 0
    dest = os.path.join(target, "img", "faces")
    os.makedirs(dest, exist_ok=True)
    written = 0
    from_rtp = []
    for entry, path in files:
        stem = os.path.splitext(entry)[0]
        try:
            image = _load_rgba(open_image(path))
        except (OSError, XyzError) as exc:
            log.error("faceset/%s could not be read: %s", entry, exc)
            continue
        if image.size != (192, 192):
            log.warning("faceset/%s is %dx%d, expected 192x192", entry, *image.size)
        out = image.resize((image.width * FACE_SCALE, image.height * FACE_SCALE), 0)
        out.save(os.path.join(dest, stem + ".png"))
        written += 1
        if project.from_rtp(path):
            from_rtp.append(entry)
    if written:
        log.info("img/faces          %3d file(s) (4x4 grid of 144px cells; MV's "
                 "editor only offers the first 8, the engine reads all 16)", written)
        _log_rtp(project, "faceset", from_rtp, log)
    return written


def _opaque(stem: str, names, patterns) -> bool:
    """Shown somewhere with "transparent colour" off - by name, or as one of
    the numbered files a variable picks (prefix plus that many digits)."""
    low = stem.lower()
    if low in {n.lower() for n in names}:
        return True
    return any(low.startswith(prefix.lower()) and len(low) == len(prefix) + digits
               for prefix, digits in patterns)


# PIL modes whose pixel value is the palette index: "P", and "L" / "1",
# which PIL picks for BMPs whose palette is plain grey or black and white.
INDEXED_MODES = ("P", "L", "1")


def _load_rgba(image):
    """Honour RM2k's convention that *palette index 0* is transparent.

    Keying on the top-left pixel instead only works by accident, and fails on
    any sheet whose first cell is actually drawn.
    """
    if image.mode not in INDEXED_MODES:
        return image.convert("RGBA")
    indexed = image.load()
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(image.height):
        for x in range(image.width):
            if indexed[x, y] == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def _transcoded(folder: str, stem: str) -> bool:
    return any(os.path.isfile(os.path.join(folder, stem + ext)) for ext in MV_AUDIO_EXT)


def copy_audio(project, target: str, log, me_names=()) -> dict[str, int]:
    """MV plays ogg/m4a only; RM2k ships midi and wav.

    The files are copied so nothing is lost and the names in the converted
    events stay valid, but they will not play until they are transcoded.

    ``me_names`` are Music/ tracks the engine plays as an ME (victory,
    game over, inn): MV looks for those in audio/me, so they are copied
    there as well.
    """
    counts: dict[str, int] = {}
    needs_transcode: list[str] = []
    wanted_me = {n.lower() for n in me_names if n}
    me_written = 0
    for kind, mv_folder in AUDIO_JOBS:
        files = project.asset_files(kind, AUDIO_EXT)
        if kind == "music":
            # Some projects keep their MP3s in an extra MP3/ folder.
            mp3_dir = project.asset_dirs.get("mp3")
            if mp3_dir:
                files += [(e, os.path.join(mp3_dir, e)) for e in sorted(os.listdir(mp3_dir))
                          if os.path.splitext(e)[1].lower() in AUDIO_EXT]
        if not files:
            continue
        dest = os.path.join(target, "audio", mv_folder)
        os.makedirs(dest, exist_ok=True)
        written = 0
        from_rtp = []
        for entry, path in files:
            stem, ext = os.path.splitext(entry)
            targets = [mv_folder]
            if kind == "music" and stem.lower() in wanted_me:
                targets.append("me")
            for folder in targets:
                out_dir = os.path.join(target, "audio", folder)
                os.makedirs(out_dir, exist_ok=True)
                shutil.copy2(path, os.path.join(out_dir, entry))
                if ext.lower() in NEEDS_TRANSCODE_EXT and not _transcoded(out_dir, stem):
                    needs_transcode.append(f"{folder}/{entry}")
                if folder == "me":
                    me_written += 1
            written += 1
            if project.from_rtp(path):
                from_rtp.append(entry)
        counts[mv_folder] = written
        log.info("audio/%-12s %3d file(s) from %s/", mv_folder, written, kind)
        _log_rtp(project, kind, from_rtp, log)
    if me_written:
        counts["me"] = me_written
        log.info("audio/me           %3d music track(s) the game plays as ME "
                 "(victory, game over, inn)", me_written)

    if needs_transcode:
        # Only files no earlier "transcode" run has turned into ogg yet.
        log.warning("%d audio file(s) are midi/wav/mp3/wma without an ogg version - "
                    "MV only plays ogg and m4a. Run the transcode step "
                    "(run.bat transcode) to convert them.", len(needs_transcode))
        for name in needs_transcode[:10]:
            log.debug("    needs transcoding: %s", name)
    return counts


def copy_movies(project, target: str, log) -> int:
    files = project.asset_files("movie")
    if not files:
        return 0
    dest = os.path.join(target, "movies")
    os.makedirs(dest, exist_ok=True)
    written = 0
    for entry, path in files:
        shutil.copy2(path, os.path.join(dest, entry))
        written += 1
    if written:
        log.warning("%d movie file(s) copied; MV expects webm/mp4, RM2k ships mpg",
                    written)
    return written
