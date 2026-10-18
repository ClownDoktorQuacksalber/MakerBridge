"""Turn RM2k chipsets into RPG Maker MV tilesets.

MV's A-sheets have their own autotile templates that do not line up with
RM2k's, so instead of trying to re-derive autotiles we *bake* them: every
(chipset, tile id) combination the maps actually use is rendered once into a
flat 48x48 tile and packed into the plain B/C/D/E sheets.  The result looks
exactly like the original and needs no autotile logic at runtime; the cost is
that re-painting terrain in the MV editor no longer auto-connects.

Tile id layout in MV: B = 0..255, C = 256..511, D = 512..767, E = 768..1023.
Id 0 means "empty", so the first slot of sheet B is left blank.

RM2k animates water (3 frames) and the three animated C tiles (4 frames);
MV's B-E tiles never animate.  Every frame is baked as its own tile and
``TilesetBuild.animated`` lists them, so a small runtime plugin can swap the
drawn id per frame.  Without the plugin the map shows frame 0, still.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from ..lcf import const

log = logging.getLogger(__name__)

TILE_SRC = 16          # RM2k tile size in pixels
SCALE = 3              # 16 -> 48, MV's tile size
TILE_DST = TILE_SRC * SCALE
SHEET_COLS = 16
SHEET_ROWS = 16
TILES_PER_SHEET = SHEET_COLS * SHEET_ROWS      # 256
SHEET_ORDER = ["B", "C", "D", "E"]
MAX_TILES = TILES_PER_SHEET * len(SHEET_ORDER)  # 1024
HALF_COLS = 8      # MV reads a B/C/D/E sheet as two 8-column halves

# MV keeps 128 plain tiles on the A5 sheet at ids 1536..1663, one half wide.
# They are ordinary tiles, so the sheet doubles as extra room for baked
# autotile variations once B and E are full.
A5_FIRST, A5_LAST = 1536, 1664
A5_KEY = "A5"
SHEET_KEYS = SHEET_ORDER + [A5_KEY]
# Index into Tilesets.json "tilesetNames": A1..A5, then B..E.
SHEET_NAME_INDEX = {A5_KEY: 4, "B": 5, "C": 6, "D": 7, "E": 8}

# MV tileset flag bits
MV_BLOCK_DOWN = 0x0001
MV_BLOCK_LEFT = 0x0002
MV_BLOCK_RIGHT = 0x0004
MV_BLOCK_UP = 0x0008
MV_STAR = 0x0010        # drawn above characters
MV_LADDER = 0x0020
MV_BUSH = 0x0040
MV_COUNTER = 0x0080
MV_DAMAGE = 0x0100
MV_TERRAIN_SHIFT = 12
# RM2k upper tile that lets every direction through and lies above the hero.
PASS_ALL_ABOVE = 0x1F
MV_BLOCK_ALL = 0x000F

# --- terrain autotile variation decoding -----------------------------------
# Terrain (D) blocks only; water ids are decoded by const.water_quarters.
# A straight copy of EasyRPG's BlockD_Subtiles_IDS (tilemap_layer.cpp): per
# variation 0..49, the (col, row) cell inside the block's 3x4 template that
# feeds the TL, TR, BL, BR quadrant of the tile.  Each quadrant is cut from
# the *same* quadrant of its cell.  Cell (2, 0) holds the inner corners,
# 46 is the isolated piece; 47 and 48 draw like 0, 49 is cell (0, 0).
BLOCK_D_SUBTILES: tuple = (
    ((1, 2), (1, 2), (1, 2), (1, 2)), ((2, 0), (1, 2), (1, 2), (1, 2)),
    ((1, 2), (2, 0), (1, 2), (1, 2)), ((2, 0), (2, 0), (1, 2), (1, 2)),
    ((1, 2), (1, 2), (1, 2), (2, 0)), ((2, 0), (1, 2), (1, 2), (2, 0)),
    ((1, 2), (2, 0), (1, 2), (2, 0)), ((2, 0), (2, 0), (1, 2), (2, 0)),
    ((1, 2), (1, 2), (2, 0), (1, 2)), ((2, 0), (1, 2), (2, 0), (1, 2)),
    ((1, 2), (2, 0), (2, 0), (1, 2)), ((2, 0), (2, 0), (2, 0), (1, 2)),
    ((1, 2), (1, 2), (2, 0), (2, 0)), ((2, 0), (1, 2), (2, 0), (2, 0)),
    ((1, 2), (2, 0), (2, 0), (2, 0)), ((2, 0), (2, 0), (2, 0), (2, 0)),
    ((0, 2), (0, 2), (0, 2), (0, 2)), ((0, 2), (2, 0), (0, 2), (0, 2)),
    ((0, 2), (0, 2), (0, 2), (2, 0)), ((0, 2), (2, 0), (0, 2), (2, 0)),
    ((1, 1), (1, 1), (1, 1), (1, 1)), ((1, 1), (1, 1), (1, 1), (2, 0)),
    ((1, 1), (1, 1), (2, 0), (1, 1)), ((1, 1), (1, 1), (2, 0), (2, 0)),
    ((2, 2), (2, 2), (2, 2), (2, 2)), ((2, 2), (2, 2), (2, 0), (2, 2)),
    ((2, 0), (2, 2), (2, 2), (2, 2)), ((2, 0), (2, 2), (2, 0), (2, 2)),
    ((1, 3), (1, 3), (1, 3), (1, 3)), ((2, 0), (1, 3), (1, 3), (1, 3)),
    ((1, 3), (2, 0), (1, 3), (1, 3)), ((2, 0), (2, 0), (1, 3), (1, 3)),
    ((0, 2), (2, 2), (0, 2), (2, 2)), ((1, 1), (1, 1), (1, 3), (1, 3)),
    ((0, 1), (0, 1), (0, 1), (0, 1)), ((0, 1), (0, 1), (0, 1), (2, 0)),
    ((2, 1), (2, 1), (2, 1), (2, 1)), ((2, 1), (2, 1), (2, 0), (2, 1)),
    ((2, 3), (2, 3), (2, 3), (2, 3)), ((2, 0), (2, 3), (2, 3), (2, 3)),
    ((0, 3), (0, 3), (0, 3), (0, 3)), ((0, 3), (2, 0), (0, 3), (0, 3)),
    ((0, 1), (2, 1), (0, 1), (2, 1)), ((0, 1), (0, 1), (0, 3), (0, 3)),
    ((0, 3), (2, 3), (0, 3), (2, 3)), ((2, 1), (2, 1), (2, 3), (2, 3)),
    ((0, 1), (2, 1), (0, 3), (2, 3)), ((1, 2), (1, 2), (1, 2), (1, 2)),
    ((1, 2), (1, 2), (1, 2), (1, 2)), ((0, 0), (0, 0), (0, 0), (0, 0)),
)


@dataclass
class TilesetBuild:
    """Everything needed to emit one MV tileset plus its images.

    ``animated`` maps the MV id a map places (an animation's frame 0) to the
    MV ids of *all* its frames in order: 3 for water, 4 for the animated C
    tiles.  MV cannot animate B-E tiles, so a runtime plugin swaps the drawn
    id; ``animation`` is the JSON-ready bundle it reads.
    Only tiles whose frames actually differ are listed.
    """
    chipset_id: int
    name: str
    source_image: str | None
    tile_ids: dict[int, int] = field(default_factory=dict)   # rm2k value -> mv id
    flags: list[int] = field(default_factory=lambda: [0] * 8192)
    sheets: dict[str, object] = field(default_factory=dict)
    overflow: int = 0
    autotiles_baked: int = 0
    animated: dict[int, list[int]] = field(default_factory=dict)
    animated_water: set[int] = field(default_factory=set)    # keys of water
    frames_baked: int = 0          # extra animation frames (beyond frame 0)
    frames_dropped: int = 0        # tiles left still because frames did not fit
    water_speed: int = const.WATER_STEP_SLOW
    tile_speed: int = const.ANIMATED_STEP
    ping_pong: bool = True

    @property
    def animation(self) -> dict:
        """What the runtime plugin reads, e.g. stored per tileset::

            {"water": {"17": [17, 120, 121], ...},   # 3 frames
             "tiles": {"40": [40, 122, 123, 124]},  # 4 frames
             "waterSpeed": 24, "tileSpeed": 6, "pingPong": true}

        Water shows frame ``[0,1,2,1][floor(t/waterSpeed) % 4]`` when
        pingPong is set, else ``floor(t/waterSpeed) % 3``; tiles show frame
        ``floor(t/tileSpeed) % 4`` (t = frames at 60 fps).  JSON object keys
        are strings.
        """
        water = {k: v for k, v in self.animated.items() if k in self.animated_water}
        tiles = {k: v for k, v in self.animated.items()
                 if k not in self.animated_water}
        return {"water": water, "tiles": tiles, "waterSpeed": self.water_speed,
                "tileSpeed": self.tile_speed, "pingPong": self.ping_pong}


# liblcf defaults for a chipset whose arrays are missing or short (fields.csv):
# terrain [1]*162, lower passage [15]*162, upper passage [31]+[15]*143.
DEFAULT_TERRAIN = 1
DEFAULT_PASS_LOWER = 0x0F
DEFAULT_PASS_UPPER = 0x0F
DEFAULT_PASS_UPPER_FIRST = 0x1F


def chipset_arrays(chipset: dict) -> tuple[list, list, list]:
    """(terrain, lower passage, upper passage), padded with liblcf's defaults."""
    terrain = list(chipset.get("terrain_data") or [])
    lower = list(chipset.get("passable_data_lower") or [])
    upper = list(chipset.get("passable_data_upper") or [])
    terrain += [DEFAULT_TERRAIN] * (const.N_LOWER_SLOTS - len(terrain))
    lower += [DEFAULT_PASS_LOWER] * (const.N_LOWER_SLOTS - len(lower))
    if not upper:
        upper = [DEFAULT_PASS_UPPER_FIRST]
    upper += [DEFAULT_PASS_UPPER] * (const.N_UPPER_PLAIN - len(upper))
    return terrain, lower, upper


class TilesetBuilder:
    """Renders one RM2k chipset into MV's B/C/D/E sheets.

    The plain tiles keep the arrangement they have in the chipset image, so the
    palette in MV's editor still looks like the original: a multi-tile drawing
    stays contiguous instead of being scattered across the sheet.  Sheets C and
    D each hold one pane pair, exactly as in the source:

        C  lower tiles   pane 2 at columns 0-5, pane 3 (rows 0-7) at 6-11
        D  upper tiles   pane 3 (rows 8-15) at columns 0-5, pane 4 at 6-11

    Sheet B (then E and A5, if needed) holds the baked autotile variations,
    block by block so each block's variants sit together.  Sheet B starts at
    id 1 because MV reads tile id 0 as "no tile".  The frame-0 tiles a map
    places come first; the remaining animation frames of water and animated
    tiles follow after them, so a full sheet costs animation before it costs
    tiles.

    Chipsets that a "Change Chipset" command swaps between are built
    together (:func:`build_group`): they share one id layout, so the map
    data written for the first chipset shows the same tiles drawn from the
    second one after the switch.
    """

    LOWER_BASE = TILES_PER_SHEET * 1        # sheet C -> ids 256..511
    UPPER_BASE = TILES_PER_SHEET * 2        # sheet D -> ids 512..767
    AUTOTILE_BASES = [(1, TILES_PER_SHEET),                      # sheet B
                      (TILES_PER_SHEET * 3, MAX_TILES),          # sheet E
                      (A5_FIRST, A5_LAST)]                       # sheet A5
    AUTOTILE_CAPACITY = sum(end - start for start, end in AUTOTILE_BASES)
    VARIATIONS = 47

    def __init__(self, project, chipset_id: int, chipset: dict):
        self.project = project
        self.chipset_id = chipset_id
        self.chipset = chipset
        self.autotile_used: dict[int, set[int]] = {}
        self._src = None
        self._build: TilesetBuild | None = None

    def note_map(self, map_data: dict) -> None:
        """Only autotiles need usage information; plain tiles are all baked."""
        for value in map_data["lower_layer"]:
            kind, slot, variation = const.decode_lower_tile(value)
            if kind != "plain":
                self.autotile_used.setdefault(slot, {0}).add(variation)

    def build(self) -> TilesetBuild:
        return build_group([self])[0]

    # -- rendering ----------------------------------------------------------
    def _prepare(self) -> None:
        """Load the image and lay out the plain lower tiles."""
        from PIL import Image

        name = self.chipset.get("name") or f"Chipset{self.chipset_id}"
        file_name = self.chipset.get("chipset_name") or ""
        path = self.project.find_asset("chipset", file_name)
        build = TilesetBuild(self.chipset_id, name, path)
        # Absent chunks mean the default: type 0 (0-1-2-1), speed 0 (slow).
        build.ping_pong = not self.chipset.get("animation_type")
        build.water_speed = (const.WATER_STEP_FAST
                             if self.chipset.get("animation_speed")
                             else const.WATER_STEP_SLOW)

        src = None
        if path is None:
            log.warning("chipset %d (%r): image %r not found - tileset will be blank",
                        self.chipset_id, name, file_name)
        else:
            from ..xyz import XyzError, open_image
            try:
                src = _apply_transparency(open_image(path))
            except (OSError, XyzError, ValueError) as exc:
                # One unreadable chipset must not take the whole project down.
                log.error("chipset %d (%r): %s could not be read (%s); "
                          "its tileset stays blank", self.chipset_id, name,
                          os.path.basename(path), exc)
                src = None
            if src is not None and src.size != (480, 256):
                log.warning("chipset %d: %s is %dx%d, expected 480x256",
                            self.chipset_id, os.path.basename(path), *src.size)
        self._src = src

        build.sheets = {key: Image.new(
            "RGBA",
            ((HALF_COLS if key == A5_KEY else SHEET_COLS) * TILE_DST,
             SHEET_ROWS * TILE_DST), (0, 0, 0, 0)) for key in SHEET_KEYS}
        self._terrain, self._pass_lower, self._pass_upper = chipset_arrays(self.chipset)
        self._build = build

        for index in range(const.N_LOWER_PLAIN):
            tile_id = self.LOWER_BASE + _plain_sheet_slot(index, upper=False)
            _paste(build.sheets, tile_id,
                   _grab_tile(src, *const.plain_tile_xy(index, False)) if src else None)
            build.tile_ids[const.BLOCK_LOWER + index] = tile_id
            slot = const.N_AUTOTILE_SLOTS + index
            build.flags[tile_id] = _flags_from_rm2k(
                self._pass_lower[slot], self._terrain[slot], upper=False)

    def _upper_blank(self, index: int) -> bool:
        """A blank overlay tile that lets everything through is RM2k's
        "nothing here"; MV can skip it.  A blank one with other settings is
        an invisible wall or passage and has to stay."""
        return (self._src is not None
                and self._pass_upper[index] & PASS_ALL_ABOVE == PASS_ALL_ABOVE
                and not _tile_has_pixels(self._src, *const.plain_tile_xy(index, True)))

    def _place_upper(self, index: int, skip: bool) -> None:
        build, src = self._build, self._src
        if skip:
            build.tile_ids[const.BLOCK_UPPER + index] = 0
            return
        tile_id = self.UPPER_BASE + _plain_sheet_slot(index, upper=True)
        _paste(build.sheets, tile_id,
               _grab_tile(src, *const.plain_tile_xy(index, True)) if src else None)
        build.tile_ids[const.BLOCK_UPPER + index] = tile_id
        build.flags[tile_id] = _flags_from_rm2k(self._pass_upper[index], 0, upper=True)

    def _slot_flags(self, slot: int) -> int:
        return _flags_from_rm2k(self._pass_lower[slot], self._terrain[slot], upper=False)

    def _entry(self, slot: int, variation: int):
        """(is_water, frames, frame bytes, own flags), or None if undrawable."""
        src = self._src
        if src is None:
            return None
        passable = self._pass_lower[slot]
        flags = self._slot_flags(slot)
        # The open top of a wall block is walkable in RM2k, so it is a
        # different tile from the rest of the block even when it looks the
        # same - it must not share an id with them.
        own = flags & ~MV_BLOCK_ALL if const.wall_top_open(
            slot, variation, passable) else flags
        frames = _render_frames(src, slot, variation)
        if not frames:
            log.debug("chipset %d: tile value %d cannot be drawn",
                      self.chipset_id, _autotile_value(slot, variation))
            return None
        if all(f.getbbox() is None for f in frames):
            # Nothing drawn, but the square still blocks or not as the
            # chipset says - keep one see-through tile per passability
            # (equal ones share it below).
            frames = frames[:1]
        return (slot < 3, frames, [f.tobytes() for f in frames], own)

    def _finish(self) -> TilesetBuild:
        build = self._build
        name = build.name
        if build.overflow:
            log.error("chipset %d (%r): %d autotile variation(s) did not fit "
                      "into MV's %d tile slots", self.chipset_id, name,
                      build.overflow, MAX_TILES)
        if build.frames_dropped:
            log.warning("chipset %d (%r): no room for the animation frames of "
                        "%d tile(s); they are drawn still", self.chipset_id,
                        name, build.frames_dropped)
        log.info("chipset %d (%r): 288 plain tiles + %d autotile variation(s) "
                 "in %d block(s), %d animated (%d extra frame(s))",
                 self.chipset_id, name, build.autotiles_baked,
                 len(self.autotile_used), len(build.animated),
                 build.frames_baked)
        self._src = None
        return build

    @classmethod
    def _autotile_ids(cls):
        for start, end in cls.AUTOTILE_BASES:
            yield from range(start, end)

    @staticmethod
    def _align_to_row(ids):
        """Skip ids until the next sheet row starts (MV rows are 8 wide)."""
        pending = list(ids)
        while pending and pending[0] % HALF_COLS:
            pending.pop(0)
        return iter(pending)


def build_group(builders: list[TilesetBuilder]) -> list[TilesetBuild]:
    """Build chipsets that share one tile id layout.

    With a single builder this is the plain build.  With several (a map
    switches between them with "Change Chipset") every autotile value any of
    them uses gets the *same* MV id in all of them, and an upper tile is only
    dropped when it is blank in all of them - otherwise the map data, which
    is written once, would point at another chipset's baked slots after the
    switch.
    """
    if len(builders) > 1:
        shared: dict[int, set[int]] = {}
        for builder in builders:
            for slot, variations in builder.autotile_used.items():
                shared.setdefault(slot, set()).update(variations)
        for builder in builders:
            builder.autotile_used = {s: set(v) for s, v in shared.items()}
    for builder in builders:
        builder._prepare()
    for index in range(const.N_UPPER_PLAIN):
        skip = all(b._upper_blank(index) for b in builders)
        for builder in builders:
            builder._place_upper(index, skip)
    _bake_autotiles(builders)
    return [b._finish() for b in builders]


def group_capacity_ok(builders: list[TilesetBuilder]) -> bool:
    """Whether the union of the builders' autotile values could fit at all."""
    shared: dict[int, set[int]] = {}
    for builder in builders:
        for slot, variations in builder.autotile_used.items():
            shared.setdefault(slot, set()).update(variations)
    return sum(len(v) for v in shared.values()) <= TilesetBuilder.AUTOTILE_CAPACITY


def _bake_autotiles(builders: list[TilesetBuilder]) -> None:
    """Lay the autotile variations out block by block.

    A chipset can hold 18 blocks of 47 variations - far more than the ~500
    ids left over once the plain tiles have their sheets - so only the
    variations a map actually places get baked.  They stay grouped and in
    variation order, which keeps each block readable in the editor.

    Water and animated tiles bring 3 or 4 frames each.  Frame 0 of every
    used variation is placed first (that is the id the map gets), then a
    second pass adds the other frames; identical renders share one id, so
    frames that do not actually change cost nothing.  When the sheets run
    out in the second pass a tile simply stays still.

    Everything is keyed on the renders of *all* builders of the group, so
    two values only share an id when they look alike in every chipset.
    """
    from PIL import Image

    blank = Image.new("RGBA", (TILE_DST, TILE_DST), (0, 0, 0, 0))
    blank_bytes = blank.tobytes()
    first = builders[0]
    # [(slot, [(value, [per builder (water, frames, pixels, own)])])]
    blocks = []
    for slot in sorted(first.autotile_used):
        values = []
        for variation in sorted(first.autotile_used[slot]):
            value = _autotile_value(slot, variation)
            entries = [b._entry(slot, variation) for b in builders]
            if all(e is None for e in entries):
                for b in builders:
                    b._build.tile_ids[value] = 0
                continue
            entries = [e if e is not None else
                       (slot < 3, [blank], [blank_bytes], b._slot_flags(slot))
                       for b, e in zip(builders, entries)]
            values.append((value, entries))
        blocks.append((slot, values))

    def frame_key(entries, k):
        return tuple(e[2][k] if k < len(e[2]) else e[2][0] for e in entries)

    def animates(entries):
        return any(len(set(e[2])) > 1 for e in entries)

    # Starting every block on a fresh row keeps the sheet readable, but a
    # chipset with many blocks would waste the slack it costs, so the
    # padding is dropped when the tiles would not otherwise fit.
    firsts: dict[tuple, list] = {}
    for _, values in blocks:
        for _, entries in values:
            firsts.setdefault(tuple((e[3], tuple(e[2])) for e in entries), entries)
    first_pixels = {frame_key(entries, 0) for entries in firsts.values()}
    extras = set()
    for entries in firsts.values():
        if animates(entries):
            for k in range(1, max(len(e[2]) for e in entries)):
                extras.add(frame_key(entries, k))
    extras -= first_pixels
    needed = len(firsts) + len(extras)
    padded = needed + (len(blocks) + sum(
        1 for _, values in blocks
        if any(animates(entries) for _, entries in values))) * (HALF_COLS - 1)
    capacity = TilesetBuilder.AUTOTILE_CAPACITY
    align = padded <= capacity
    names = "/".join(str(b.chipset_id) for b in builders)
    if not align and needed <= capacity:
        log.info("chipset %s: packing autotiles tightly, %d tile(s) "
                 "in %d block(s)", names, needed, len(blocks))

    ids = TilesetBuilder._autotile_ids()
    first_ids: dict[tuple, int] = {}       # all renders + flags -> frame 0 id
    by_pixels: dict[tuple, int] = {}       # any baked composite -> its id
    baked = 0
    for _, values in blocks:
        placed = False
        for value, entries in values:
            key = tuple((e[3], tuple(e[2])) for e in entries)
            tile_id = first_ids.get(key)
            if tile_id is None:
                tile_id = next(ids, None)
                if tile_id is None:
                    for b in builders:
                        b._build.overflow += 1
                        b._build.tile_ids[value] = 0
                    continue
                for b, e in zip(builders, entries):
                    _paste(b._build.sheets, tile_id, e[1][0])
                    b._build.flags[tile_id] = e[3]
                first_ids[key] = tile_id
                by_pixels.setdefault(frame_key(entries, 0), tile_id)
                baked += 1
                placed = True
            for b in builders:
                b._build.tile_ids[value] = tile_id
        if align and placed:
            ids = TilesetBuilder._align_to_row(ids)
    for b in builders:
        b._build.autotiles_baked = baked

    # Second pass: the remaining frames.  Keys of ``animated`` are frame-0
    # ids, which first_ids keeps unique per frame sequence.
    done: set[int] = set()
    for slot, values in blocks:
        placed = False
        for value, entries in values:
            start = first._build.tile_ids.get(value, 0)
            if not start or start in done or not animates(entries):
                continue
            done.add(start)
            count = max(len(e[2]) for e in entries)
            sequence = [start]
            for k in range(1, count):
                raw = frame_key(entries, k)
                tile_id = by_pixels.get(raw)
                if tile_id is None:
                    tile_id = next(ids, None)
                    if tile_id is None:
                        break
                    for b, e in zip(builders, entries):
                        image = e[1][k] if k < len(e[1]) else e[1][0]
                        _paste(b._build.sheets, tile_id, image)
                        b._build.flags[tile_id] = b._slot_flags(slot)
                        b._build.frames_baked += 1
                    by_pixels[raw] = tile_id
                    placed = True
                sequence.append(tile_id)
            for b, e in zip(builders, entries):
                if len(set(e[2])) <= 1:
                    continue             # still in this chipset
                if len(sequence) < count:
                    b._build.frames_dropped += 1
                    continue
                b._build.animated[start] = sequence
                if e[0]:
                    b._build.animated_water.add(start)
        if align and placed:
            ids = TilesetBuilder._align_to_row(ids)


def _plain_sheet_slot(index: int, upper: bool) -> int:
    """Id offset inside sheet C or D, mirroring the chipset's own layout.

    A chipset pane is 6 columns wide and MV's sheet halves are 8, so each pane
    goes into its own half and keeps its internal arrangement intact.
    """
    column, row = const.plain_tile_xy(index, upper)
    first_pane = 18 if upper else 12          # leftmost chipset column of the pair
    offset = column - first_pane              # 0..11 across the two panes
    pane, column_in_pane = divmod(offset, const.PLAIN_PANE_COLS)
    return mv_tile_id(0, pane * HALF_COLS + column_in_pane, row)


def _autotile_value(slot: int, variation: int) -> int:
    if slot < 3:
        return slot * 1000 + variation
    if slot < 6:
        return const.BLOCK_ANIMATED + (slot - 3) * const.AUTOTILE_STRIDE + variation
    return const.BLOCK_TERRAIN + (slot - 6) * const.AUTOTILE_STRIDE + variation


def _apply_transparency(original):
    """RM2k treats *palette index 0* as transparent.

    Not the colour of the top-left pixel: a chipset whose first tile is drawn
    (water autotiles usually are) has something else up there, and keying on it
    erases the artwork while leaving the real background colour behind.
    """
    rgba = original.convert("RGBA")
    if original.mode not in ("P", "L", "1"):
        return rgba
    indexed = original.load()
    out = rgba.load()
    for y in range(original.height):
        for x in range(original.width):
            if indexed[x, y] == 0:
                out[x, y] = (0, 0, 0, 0)
    return rgba


def _grab_tile(src, tile_col: int, tile_row: int):
    """One 16x16 tile, scaled to MV's 48x48."""
    box = (tile_col * TILE_SRC, tile_row * TILE_SRC,
           (tile_col + 1) * TILE_SRC, (tile_row + 1) * TILE_SRC)
    return src.crop(box).resize((TILE_DST, TILE_DST), 0)   # 0 == NEAREST


def _render_frames(src, slot: int, variation: int) -> list | None:
    """All animation frames of one autotile variation, frame 0 first.

    Water composes 8x8 quadrants per frame (const.water_quarters); the
    animated C tiles are whole tiles, one per row; terrain has one frame.
    None means RPG_RT itself cannot draw the value.
    """
    if slot < 3:
        value = _autotile_value(slot, variation)
        frames = []
        for frame in range(const.WATER_FRAMES):
            quarters = const.water_quarters(value, frame)
            if quarters is None:
                return None
            frames.append(_compose_quarters(src, quarters))
        return frames
    if slot < 6:
        # RPG_RT ignores the variation of an animated tile: every neighbour
        # situation draws the same whole tile.
        column = const.ANIMATED_COL + slot - 3
        return [_grab_tile(src, column, const.ANIMATED_ROW + frame)
                for frame in range(const.ANIMATED_FRAMES)]
    return [_render_autotile(src, slot, variation)]


_QUARTER_OFFSETS = [(0, 0), (1, 0), (0, 1), (1, 1)]     # TL, TR, BL, BR


def _compose_quarters(src, quarters):
    """Build a tile from four (col, row) chipset tiles, one quadrant each.

    Quadrant q of the output always comes from quadrant q of its source tile;
    that is how both RPG_RT and EasyRPG cut water.
    """
    from PIL import Image

    out = Image.new("RGBA", (TILE_SRC, TILE_SRC), (0, 0, 0, 0))
    half = TILE_SRC // 2
    for (qx, qy), (col, row) in zip(_QUARTER_OFFSETS, quarters):
        sx = col * TILE_SRC + qx * half
        sy = row * TILE_SRC + qy * half
        out.paste(src.crop((sx, sy, sx + half, sy + half)), (qx * half, qy * half))
    return out.resize((TILE_DST, TILE_DST), 0)


def _render_autotile(src, slot: int, variation: int):
    """Compose one terrain (D block) variation from its 3x4 template, as
    EasyRPG's GenerateAutotileD does."""
    from PIL import Image

    col0, row0, _, _ = const.AUTOTILE_TEMPLATES[slot]
    cells = BLOCK_D_SUBTILES[variation if variation < len(BLOCK_D_SUBTILES) else 0]
    out = Image.new("RGBA", (TILE_SRC, TILE_SRC), (0, 0, 0, 0))
    half = TILE_SRC // 2
    for (qx, qy), (cell_col, cell_row) in zip(_QUARTER_OFFSETS, cells):
        sx = (col0 + cell_col) * TILE_SRC + qx * half
        sy = (row0 + cell_row) * TILE_SRC + qy * half
        out.paste(src.crop((sx, sy, sx + half, sy + half)), (qx * half, qy * half))
    return out.resize((TILE_DST, TILE_DST), 0)


def mv_sheet_position(tile_id: int) -> tuple[str, int, int]:
    """Where MV looks for ``tile_id`` -> (sheet index, column, row).

    Straight out of ``Tilemap._drawNormalTile`` in rpg_core.js::

        sx = (floor(tileId / 128) % 2 * 8 + tileId % 8) * tileWidth
        sy = (floor(tileId % 256 / 8) % 16) * tileHeight

    So a sheet is *not* a 16-wide row-major grid: ids 0..127 fill the left
    half 8 tiles to a row, ids 128..255 the right half.  Writing the tiles in
    16-wide rows instead produces sheets that look perfectly cut but come out
    scrambled in the editor and in game.
    """
    if A5_FIRST <= tile_id < A5_LAST:
        key = A5_KEY
    else:
        key = SHEET_ORDER[tile_id // TILES_PER_SHEET]
    within = tile_id % TILES_PER_SHEET
    column = (tile_id // 128) % 2 * HALF_COLS + tile_id % HALF_COLS
    row = (within // HALF_COLS) % SHEET_ROWS
    return key, column, row


def mv_tile_id(sheet_index: int, column: int, row: int) -> int:
    """Inverse of :func:`mv_sheet_position` for the B/C/D/E sheets."""
    half, column_in_half = divmod(column, HALF_COLS)
    return (sheet_index * TILES_PER_SHEET + half * 128
            + row * HALF_COLS + column_in_half)


def _paste(sheets: dict, tile_id: int, tile) -> None:
    if tile is None:
        return
    key, column, row = mv_sheet_position(tile_id)
    sheets[key].paste(tile, (column * TILE_DST, row * TILE_DST))


def _tile_has_pixels(src, tile_col: int, tile_row: int) -> bool:
    if src is None:
        return False
    box = (tile_col * TILE_SRC, tile_row * TILE_SRC,
           (tile_col + 1) * TILE_SRC, (tile_row + 1) * TILE_SRC)
    return src.crop(box).getbbox() is not None


def _flags_from_rm2k(passable: int, terrain_id: int, upper: bool) -> int:
    """RM2k sets a bit when movement is *allowed*; MV sets it when blocked."""
    flags = 0
    if not passable & const.PASS_DOWN:
        flags |= MV_BLOCK_DOWN
    if not passable & const.PASS_LEFT:
        flags |= MV_BLOCK_LEFT
    if not passable & const.PASS_RIGHT:
        flags |= MV_BLOCK_RIGHT
    if not passable & const.PASS_UP:
        flags |= MV_BLOCK_UP
    # RPG_RT draws an upper tile marked "above the hero" (star) over the
    # characters, and a lower tile marked star or "wall" (square) as well
    # (EasyRPG TilemapLayer::CreateTileCacheAt).  MV ignores passage for
    # starred tiles; RM2kCompat.js checks RM2k's own passability instead.
    above = const.PASS_ABOVE if upper else const.PASS_ABOVE | const.PASS_WALL
    if passable & above:
        flags |= MV_STAR
        # Lower tiles keep their direction bits: MV skips them for starred
        # tiles anyway, and they keep a closed wall piece apart from an
        # open one that looks the same (tiles are merged by their flags).
        if upper:
            flags &= ~(MV_BLOCK_DOWN | MV_BLOCK_LEFT | MV_BLOCK_RIGHT | MV_BLOCK_UP)
    if passable & const.PASS_COUNTER:
        flags |= MV_COUNTER
    if terrain_id:
        flags |= (min(terrain_id, 7) << MV_TERRAIN_SHIFT)
    return flags
