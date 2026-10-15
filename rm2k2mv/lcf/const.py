"""Chunk ids and layout constants for RPG Maker 2000 LCF files.

Everything in this module was verified against the "Three Monkeys Demo 1"
project (62 maps, 2 chipsets); see docs/FORMAT.md for the evidence behind the
tile-id and chipset-layout tables in particular.
"""

from __future__ import annotations

# --- RPG_RT.ldb top level ---------------------------------------------------
LDB_ACTOR = 0x0B
LDB_SKILL = 0x0C
LDB_ITEM = 0x0D
LDB_ENEMY = 0x0E
LDB_TROOP = 0x0F
LDB_TERRAIN = 0x10
LDB_ATTRIBUTE = 0x11
LDB_STATE = 0x12
LDB_ANIMATION = 0x13
LDB_CHIPSET = 0x14
LDB_TERMS = 0x15
LDB_SYSTEM = 0x16
LDB_SWITCHES = 0x17
LDB_VARIABLES = 0x18
LDB_COMMONEVENT = 0x19

LDB_TABLE_NAMES = {
    LDB_ACTOR: "actors", LDB_SKILL: "skills", LDB_ITEM: "items",
    LDB_ENEMY: "enemies", LDB_TROOP: "troops", LDB_TERRAIN: "terrains",
    LDB_ATTRIBUTE: "attributes", LDB_STATE: "states",
    LDB_ANIMATION: "animations", LDB_CHIPSET: "chipsets",
    LDB_TERMS: "terms", LDB_SYSTEM: "system", LDB_SWITCHES: "switches",
    LDB_VARIABLES: "variables", LDB_COMMONEVENT: "common_events",
}

# --- RPG_RT.lmu (map) -------------------------------------------------------
LMU_CHIPSET_ID = 0x01
LMU_WIDTH = 0x02
LMU_HEIGHT = 0x03
LMU_SCROLL_TYPE = 0x0B
LMU_PARALLAX_FLAG = 0x1F
LMU_PARALLAX_NAME = 0x20
LMU_PARALLAX_LOOP_X = 0x21
LMU_PARALLAX_LOOP_Y = 0x22
LMU_PARALLAX_AUTO_LOOP_X = 0x23
LMU_PARALLAX_SX = 0x24
LMU_PARALLAX_AUTO_LOOP_Y = 0x25
LMU_PARALLAX_SY = 0x26
LMU_LOWER_LAYER = 0x47
LMU_UPPER_LAYER = 0x48
LMU_EVENTS = 0x51
LMU_SAVE_COUNT = 0x5B

LMU_DEFAULTS = {LMU_CHIPSET_ID: 1, LMU_WIDTH: 20, LMU_HEIGHT: 15}

# --- Map tile id encoding ---------------------------------------------------
# Verified across all 62 maps: every lower value falls into exactly one of these
# ranges and every upper value into 10000..10143.
BLOCK_WATER_A1 = 0        # +variation
BLOCK_WATER_A2 = 1000
BLOCK_WATER_B = 2000
BLOCK_ANIMATED = 3000     # 3 blocks, 3000 + block*50 + variation
BLOCK_TERRAIN = 4000      # 12 blocks, 4000 + block*50 + variation
BLOCK_LOWER = 5000        # 5000 + index, index 0..143
BLOCK_UPPER = 10000       # 10000 + index, index 0..143

AUTOTILE_STRIDE = 50      # variation slots reserved per autotile block
N_LOWER_PLAIN = 144
N_UPPER_PLAIN = 144
N_AUTOTILE_SLOTS = 18     # 3 water + 3 animated + 12 terrain
N_LOWER_SLOTS = N_AUTOTILE_SLOTS + N_LOWER_PLAIN   # == 162, matches chipset arrays


def decode_lower_tile(value: int) -> tuple[str, int, int]:
    """Map a lower-layer tile id to ``(kind, slot, variation)``.

    ``slot`` indexes the chipset's 162-entry passability/terrain arrays.
    """
    if value >= BLOCK_LOWER:
        index = value - BLOCK_LOWER
        if not 0 <= index < N_LOWER_PLAIN:
            raise ValueError(f"lower plain tile out of range: {value}")
        return "plain", N_AUTOTILE_SLOTS + index, 0
    if value >= BLOCK_TERRAIN:
        off = value - BLOCK_TERRAIN
        block, var = divmod(off, AUTOTILE_STRIDE)
        if block >= 12:
            raise ValueError(f"terrain autotile block out of range: {value}")
        return "terrain", 6 + block, var
    if value >= BLOCK_ANIMATED:
        off = value - BLOCK_ANIMATED
        block, var = divmod(off, AUTOTILE_STRIDE)
        if block >= 3:
            raise ValueError(f"animated autotile block out of range: {value}")
        return "animated", 3 + block, var
    block, var = divmod(value, 1000)
    if block > 2:
        raise ValueError(f"water autotile block out of range: {value}")
    return "water", block, var


def decode_upper_tile(value: int) -> int:
    """Upper-layer tile id -> index into the chipset's 144 upper tiles."""
    index = value - BLOCK_UPPER
    if not 0 <= index < N_UPPER_PLAIN:
        raise ValueError(f"upper tile out of range: {value}")
    return index


# --- Chipset image layout (480x256 px, 16px tiles -> 30x16 tile grid) -------
# Autotile templates live in tile columns 0..11.  Columns 0..5, rows 0..7 hold
# the water and animated blocks (see below); terrain templates are 3 wide and
# 4 tall.  Plain tiles occupy columns 12..29 (see plain_tile_xy).
CHIPSET_TILE = 16
CHIPSET_COLS = 30
CHIPSET_ROWS = 16

# Water and animated tiles, columns 0..5 rows 0..7 (layout as EasyRPG's
# tilemap_layer.cpp reads it, and as every chipset in Renascor Adoria draws it):
#
#   cols 0-2 rows 0-3   water A1 edge pieces, one column per animation frame
#   cols 3-5 rows 0-3   water A2 edge pieces, one column per animation frame
#   cols 0-2 rows 4-7   ocean pieces shared by all water, one column per frame
#   cols 3,4,5 rows 4-7 animated tiles C1..C3, one column each, row = frame
#
# Each column of an edge block holds four full tiles whose *quadrants* are
# combined: row 0 = isolated pond (outer corners), 1 = left/right shore,
# 2 = top/bottom shore, 3 = inner corners.  The ocean column holds row 4 =
# shallow water, 5 = shallow next to deep, 6 = deep next to shallow, 7 = deep.
WATER_A1_COL = 0
WATER_A2_COL = 3
WATER_OCEAN_ROW = 4
WATER_FRAMES = 3
ANIMATED_COL = 3
ANIMATED_ROW = 4
ANIMATED_FRAMES = 4

# RM2k animation timing, in 60 fps frames (EasyRPG Game_Map::GetAnimationSpeed
# and TilemapLayer::Draw).  Water steps every 24 frames, or 12 when the
# chipset's animation_speed (chunk 0x0C) is "fast"; animation_type (0x0B) 0
# plays the three frames 0-1-2-1, 1 plays 0-1-2.  The animated C tiles ignore
# both settings and step through their four frames every 6 frames.
WATER_STEP_SLOW = 24
WATER_STEP_FAST = 12
ANIMATED_STEP = 6

# slot -> (tile_col, tile_row, cols, rows): the area holding the slot's own art.
# Water slots also borrow the ocean column (all three) and, for slot 2, the A1
# edges; the true composition is in water_quarters().
AUTOTILE_TEMPLATES: dict[int, tuple[int, int, int, int]] = {
    0: (WATER_A1_COL, 0, 3, 4),                  # water A1 (+ shallow ocean)
    1: (WATER_A2_COL, 0, 3, 4),                  # water A2 (+ shallow ocean)
    2: (0, WATER_OCEAN_ROW, 3, 4),               # deep water (A1 edges + deep)
    3: (ANIMATED_COL, ANIMATED_ROW, 1, 4),       # animated C1
    4: (ANIMATED_COL + 1, ANIMATED_ROW, 1, 4),   # animated C2
    5: (ANIMATED_COL + 2, ANIMATED_ROW, 1, 4),   # animated C3
}

# Water id decoding, straight from EasyRPG TilemapLayer::GenerateAutotileAB.
# A water value is ``kind * 1000 + ocean * 50 + edge``:
#
#   kind   0 = A1 shore over shallow, 1 = A2 shore over shallow,
#          2 = A1 shore over deep water
#   edge   0..46, which quadrants show shore and which shore piece; the table
#          below gives, per quadrant [row][col], the edge-block row to take
#          (-1 = no shore here, use the ocean column)
#   ocean  0..15, 4 bits TL=1 TR=2 BL=4 BR=8 marking quadrants that border the
#          other water depth and so take the shallow/deep transition piece
WATER_KIND_STRIDE = 1000
WATER_OCEAN_STRIDE = 50
_N = -1
WATER_EDGE_QUARTERS: tuple = (
    ((_N, _N), (_N, _N)), ((3, _N), (_N, _N)), ((_N, 3), (_N, _N)),
    ((3, 3), (_N, _N)), ((_N, _N), (_N, 3)), ((3, _N), (_N, 3)),
    ((_N, 3), (_N, 3)), ((3, 3), (_N, 3)), ((_N, _N), (3, _N)),
    ((3, _N), (3, _N)), ((_N, 3), (3, _N)), ((3, 3), (3, _N)),
    ((_N, _N), (3, 3)), ((3, _N), (3, 3)), ((_N, 3), (3, 3)),
    ((3, 3), (3, 3)), ((1, _N), (1, _N)), ((1, 3), (1, _N)),
    ((1, _N), (1, 3)), ((1, 3), (1, 3)), ((2, 2), (_N, _N)),
    ((2, 2), (_N, 3)), ((2, 2), (3, _N)), ((2, 2), (3, 3)),
    ((_N, 1), (_N, 1)), ((_N, 1), (3, 1)), ((3, 1), (_N, 1)),
    ((3, 1), (3, 1)), ((_N, _N), (2, 2)), ((3, _N), (2, 2)),
    ((_N, 3), (2, 2)), ((3, 3), (2, 2)), ((1, 1), (1, 1)),
    ((2, 2), (2, 2)), ((0, 2), (1, _N)), ((0, 2), (1, 3)),
    ((2, 0), (_N, 1)), ((2, 0), (3, 1)), ((_N, 1), (2, 0)),
    ((3, 1), (2, 0)), ((1, _N), (0, 2)), ((1, 3), (0, 2)),
    ((0, 0), (1, 1)), ((0, 2), (0, 2)), ((1, 1), (0, 0)),
    ((2, 0), (2, 0)), ((0, 0), (0, 0)),
)
del _N


def water_quarters(value: int, frame: int) -> list[tuple[int, int]] | None:
    """Chipset tiles feeding the four quadrants of water ``value`` in ``frame``.

    Returns ``[(col, row)]`` for the TL, TR, BL, BR quadrants - each quadrant
    is cut from the *same* quadrant of the named tile - or ``None`` for an id
    RPG_RT cannot draw either.  A faithful port of EasyRPG's
    GenerateAutotileAB, including its last step: a quadrant flagged in the
    ocean bits takes the depth-transition piece even where a shore was chosen.
    """
    kind, rest = divmod(value, WATER_KIND_STRIDE)
    ocean, edge = divmod(rest, WATER_OCEAN_STRIDE)
    if not 0 <= kind <= 2 or ocean >= 16 or edge >= len(WATER_EDGE_QUARTERS):
        return None
    edge_col = frame + (WATER_A2_COL if kind == 1 else WATER_A1_COL)
    out = []
    for j in range(2):
        for i in range(2):
            bit = (ocean >> (j * 2 + i)) & 1
            shore = WATER_EDGE_QUARTERS[edge][j][i]
            if shore >= 0:
                cell = (edge_col, shore)
            else:
                # kind 2 flips the pair: 0 -> row 7 (deep), 1 -> row 6
                t = bit ^ 3 if kind == 2 else bit
                cell = (frame, WATER_OCEAN_ROW + t)
            if ocean and edge and bit:
                cell = (frame, WATER_OCEAN_ROW + (2 if kind == 2 else 1))
            out.append(cell)
    return out
# 12 terrain templates: columns 0..5 rows 8..15 first, then columns 6..11.
_terrain_origins = [
    (0, 8), (3, 8), (0, 12), (3, 12),
    (6, 0), (9, 0), (6, 4), (9, 4),
    (6, 8), (9, 8), (6, 12), (9, 12),
]
for _i, (_c, _r) in enumerate(_terrain_origins):
    AUTOTILE_TEMPLATES[6 + _i] = (_c, _r, 3, 4)

# The 288 plain tiles are numbered straight through the three right-hand panes
# of 6 columns: 6 tiles per row, 16 rows, 96 tiles per pane.  The first 144 are
# the lower layer and the next 144 the upper layer, so the boundary falls in
# the *middle* of the second pane rather than on a row of the image.
#
# Verified against both chipsets of the reference project: with this mapping 0%
# of the upper tiles the maps actually use land on a fully transparent image
# tile, against 38-98% for every row-major or per-pane alternative.
PLAIN_ORIGIN_COL = 12
PLAIN_PANE_COLS = 6
PLAIN_PANE_ROWS = 16
TILES_PER_PANE = PLAIN_PANE_COLS * PLAIN_PANE_ROWS   # 96


def plain_tile_xy(index: int, upper: bool) -> tuple[int, int]:
    """Tile-grid coordinates of plain lower/upper tile ``index`` (0..143)."""
    position = index + (N_LOWER_PLAIN if upper else 0)
    pane, within = divmod(position, TILES_PER_PANE)
    row, col = divmod(within, PLAIN_PANE_COLS)
    return PLAIN_ORIGIN_COL + pane * PLAIN_PANE_COLS + col, row


# --- Chipset passability flags (RM2k: set bit == allowed) -------------------
PASS_DOWN = 0x01
PASS_LEFT = 0x02
PASS_RIGHT = 0x04
PASS_UP = 0x08
PASS_ABOVE = 0x10     # drawn above the hero
PASS_WALL = 0x20      # counts as wall for "wall" autotiles
PASS_COUNTER = 0x40   # counter / talk-across

# Terrain autotile variations whose top edge is open.  On a block marked
# "wall" RPG_RT lets everything onto these (the walkable top of the wall)
# whatever its direction bits say - the list EasyRPG uses.
WALL_TOP_VARIATIONS = frozenset(list(range(20, 24)) + list(range(33, 38)) + [42, 43, 45, 46])


def wall_top_open(slot: int, variation: int, passable: int) -> bool:
    return slot >= 6 and bool(passable & PASS_WALL) and variation in WALL_TOP_VARIATIONS
