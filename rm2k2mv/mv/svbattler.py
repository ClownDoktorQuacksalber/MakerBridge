"""Build RPG Maker MZ/MV side-view battler sheets from RM2003 battle charsets.

An RM2003 battle charset is 144x384: three animation frames across, eight
poses down, 48x48 each.  Which pose sits in which row is not fixed - the
database says so, per animation set, in the BattlerAnimation pose table, and
a set may even pull its poses from several files.

MZ reads a sv_actors sheet as nine columns by six rows and finds a motion at
``column = floor(motion / 6) * 3 + frame``, ``row = motion % 6``
(``Sprite_Actor.prototype.updateFrame``).  This module assembles that sheet by
fetching each motion from whatever file and row the pose table names.
"""

from __future__ import annotations

import logging
import os

from ..xyz import XyzError, open_image

log = logging.getLogger(__name__)

CELL = 48            # RM2003 battle charset cell
SCALE = 3            # same factor as the tiles and character sheets
OUT_CELL = CELL * SCALE
SHEET_COLS, SHEET_ROWS = 9, 6
FRAMES = 3

# RM2003 pose numbers, in the fixed order the database stores them.
IDLE, ATTACK_RIGHT, ATTACK_LEFT, SKILL, DEAD, DAMAGE = 1, 2, 3, 4, 5, 6
BAD_STATUS, DEFENDING, WALK_LEFT, WALK_RIGHT, VICTORY, ITEM = 7, 8, 9, 10, 11, 12

# MZ motion index -> the RM2003 pose that fits it best.  MZ has eighteen
# motions against RM2003's twelve, so several share a pose; anything the set
# does not define falls back to the idle pose.
MOTION_POSE = {
    # MZ's "walk" is stepping towards the enemies (to the left) and is
    # also shown while a command is chosen; "escape" runs off to the
    # right.  RM2003's poses 9/10 are "move left"/"move right".
    0: WALK_LEFT,     # walk
    1: IDLE,          # wait
    2: SKILL,         # chant
    3: DEFENDING,     # guard
    4: DAMAGE,        # damage
    5: DAMAGE,        # evade
    # RM2003 attacks with the "right hand" pose whenever the hero faces
    # the enemies (left); "left hand" is its mirror for a hero turned
    # round in a back attack, which MV/MZ never does.  So every MZ
    # attack motion - picked by weapon type - takes the right-hand pose.
    6: ATTACK_RIGHT,  # thrust
    7: ATTACK_RIGHT,  # swing
    8: ATTACK_RIGHT,  # missile
    9: SKILL,         # skill
    10: SKILL,        # spell
    11: ITEM,         # item
    12: WALK_RIGHT,   # escape
    13: VICTORY,      # victory
    14: BAD_STATUS,   # dying
    15: BAD_STATUS,   # abnormal
    16: BAD_STATUS,   # sleep
    17: DEAD,         # dead
}


POSE_ANIMATION = 1     # a pose that plays a battle animation instead
STANDARD_POSES = range(1, 13)


def pose_strip_name(stem: str, pose_id: int) -> str:
    return f"{stem}_pose{pose_id}"


def custom_poses(project) -> dict[str, dict[str, str]]:
    """Set id -> {pose id: strip file, or "" for an empty pose} for the
    poses past the standard twelve."""
    out: dict[str, dict[str, str]] = {}
    for set_id, entry in (project.database.get("battler_animations") or {}).items():
        stem = _safe_name(entry.get("name") or f"Battler{set_id}", set_id)
        poses = entry.get("poses") or {}
        own = {}
        for pose_id, pose in poses.items():
            if pose_id <= len(STANDARD_POSES):
                continue
            drawable = (pose.get("battler_name") and pose.get("animation_type") != POSE_ANIMATION
                        and project.find_asset("battlecharset", pose["battler_name"]))
            own[str(pose_id)] = pose_strip_name(stem, pose_id) if drawable else ""
        if own:
            out[str(set_id)] = own
    return out
MOTION_NAMES = ["walk", "wait", "chant", "guard", "damage", "evade", "thrust",
                "swing", "missile", "skill", "spell", "item", "escape", "victory",
                "dying", "abnormal", "sleep", "dead"]


def pose_animations(project, animation_ids: dict[int, int]) -> dict[str, dict[str, int]]:
    """Set id -> {MZ motion name: MV animation id} for the poses RM2003 shows
    as a battle animation."""
    out: dict[str, dict[str, int]] = {}
    for set_id, entry in (project.database.get("battler_animations") or {}).items():
        poses = entry.get("poses") or {}
        motions = {}
        for motion, pose_id in MOTION_POSE.items():
            pose = poses.get(pose_id)
            if pose and pose.get("animation_type") == POSE_ANIMATION:
                rm_id = pose.get("battle_animation_id")
                anim = animation_ids.get(1 if rm_id is None else rm_id)
                if anim:
                    motions[MOTION_NAMES[motion]] = anim
        if motions:
            out[str(set_id)] = motions
    return out


def motion_cell(motion: int, frame: int) -> tuple[int, int]:
    """Where MZ looks for a motion frame inside the 9x6 sheet."""
    return (motion // SHEET_ROWS) * FRAMES + frame, motion % SHEET_ROWS


def build_all(project, target: str, log) -> dict[int, str]:
    """Write one sheet per battle animation set; returns set id -> file name."""
    from PIL import Image

    sets = project.database.get("battler_animations") or {}
    if not sets:
        return {}
    # The files may also come from the RTP (find_asset falls back to it).
    source_dir = project.asset_dirs.get("battlecharset") or ""

    out_dir = os.path.join(target, "img", "sv_actors")
    os.makedirs(out_dir, exist_ok=True)
    cache: dict[str, object] = {}
    names: dict[int, str] = {}
    written = 0

    for set_id, entry in sorted(sets.items()):
        poses = entry.get("poses") or {}
        if not poses:
            continue
        stem = _safe_name(entry.get("name") or f"Battler{set_id}", set_id)
        sheet = Image.new("RGBA", (SHEET_COLS * OUT_CELL,
                                   SHEET_ROWS * OUT_CELL), (0, 0, 0, 0))
        drawn = False
        for motion in range(18):
            pose = poses.get(MOTION_POSE[motion]) or poses.get(IDLE)
            if pose and pose.get("animation_type") == POSE_ANIMATION:
                # Shown as a battle animation (RM2kCompat.js); the sheet
                # keeps the idle frames underneath.
                pose = poses.get(IDLE)
            if not pose or pose.get("animation_type") == POSE_ANIMATION:
                continue
            image = _load(project, source_dir, pose.get("battler_name", ""),
                          cache, log)
            if image is None:
                continue
            row = pose.get("row", 0) or 0
            for frame in range(FRAMES):
                tile = _cell(image, frame, row)
                if tile is None:
                    continue
                column, sheet_row = motion_cell(motion, frame)
                sheet.paste(tile.resize((OUT_CELL, OUT_CELL), 0),
                            (column * OUT_CELL, sheet_row * OUT_CELL))
                drawn = True
        if not drawn:
            continue
        sheet.save(os.path.join(out_dir, stem + ".png"))
        names[set_id] = stem
        written += 1
        # Poses past the twelve standard ones (RM2003 1.12 sets have up to
        # 32): one strip of three frames each, used by skills that name
        # them.  A pose without a picture leaves the hero invisible.
        for pose_id, pose in sorted(poses.items()):
            if pose_id <= len(STANDARD_POSES) or not pose.get("battler_name")                     or pose.get("animation_type") == POSE_ANIMATION:
                continue
            image = _load(project, source_dir, pose.get("battler_name", ""), cache, log)
            if image is None:
                continue
            strip = Image.new("RGBA", (FRAMES * OUT_CELL, OUT_CELL), (0, 0, 0, 0))
            for frame in range(FRAMES):
                tile = _cell(image, frame, pose.get("row", 0) or 0)
                if tile is not None:
                    strip.paste(tile.resize((OUT_CELL, OUT_CELL), 0), (frame * OUT_CELL, 0))
            strip.save(os.path.join(out_dir, pose_strip_name(stem, pose_id) + ".png"))

    log.info("img/sv_actors      %3d side-view battler sheet(s) from %d "
             "animation set(s)", written, len(sets))
    return names


def _safe_name(name: str, set_id: int) -> str:
    cleaned = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
    cleaned = cleaned.strip().strip("_") or f"Battler{set_id}"
    return f"{set_id:02d}_{cleaned}"


def _load(project, source_dir: str, name: str, cache: dict, log):
    if not name:
        return None
    if name in cache:
        return cache[name]
    path = project.find_asset("battlecharset", name)
    image = None
    if path:
        try:
            image = _transparent(open_image(path))
        except (OSError, XyzError, ValueError) as exc:
            log.error("battle charset %r could not be read: %s", name, exc)
    else:
        log.warning("battle charset %r is referenced but not on disk", name)
    cache[name] = image
    return image


def _transparent(image):
    """RM2k keeps the transparent colour at palette index 0."""
    rgba = image.convert("RGBA")
    if image.mode != "P":
        return rgba
    indexed = image.load()
    pixels = rgba.load()
    for y in range(image.height):
        for x in range(image.width):
            if indexed[x, y] == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def _cell(image, frame: int, row: int):
    left, top = frame * CELL, row * CELL
    if left + CELL > image.width or top + CELL > image.height:
        return None
    return image.crop((left, top, left + CELL, top + CELL))
