# RPG Maker 2000 (liblcf) format notes

Everything here was verified against the *Three Monkeys Demo 1* project
(62 maps, 7 chipset records, 2 chipset images, ~60 000 event commands) rather
than taken from memory. Where a claim rests on evidence, the evidence is named.

## 1. Container

A `.ldb` / `.lmt` / `.lmu` file starts with a length-prefixed ASCII signature
(`LcfDataBase`, `LcfMapTree`, `LcfMapUnit`), then structured data.

* **Compressed integers** carry 7 bits per byte, big-endian, high bit = "more
  bytes follow".
* A **struct** is a flat run of `(id, size, payload)` chunks ended by id `0`.
  Writers emit ids in ascending order, which makes a cheap validity probe.
* An **array of structs** is a count, then per entry an id followed by that
  entry's chunks.
* A chunk is **omitted when the field equals its default**. Records are
  therefore very sparse; an absent chunk is not missing data.

Confirmation that the default rule is real: `Attribute` records carry chunks
`0x0B 0x0C 0x0E 0x0F` with values 150/125/75/50 and omit `0x0D` — exactly the
RM2k default ladder 150/125/**100**/75/50.

## 2. File layouts

### RPG_RT.ldb

Fifteen top-level chunks, all present in the reference project:

| Chunk | Table | Count here |
|-------|-------|-----------|
| 0x0B | Actor | 1 |
| 0x0C | Skill | 128 |
| 0x0D | Item | 40 |
| 0x0E | Enemy | 45 |
| 0x0F | Troop | 80 |
| 0x10 | Terrain | 10 |
| 0x11 | Attribute | 17 |
| 0x12 | State | 10 |
| 0x13 | Animation | 6 |
| 0x14 | Chipset | 7 |
| 0x15 | Terms (struct) | 122 strings |
| 0x16 | System (struct) | — |
| 0x17 | Switches | 200 |
| 0x18 | Variables | 220 |
| 0x19 | CommonEvent | 40 |

There is no `Class`, `BattleCommand` or `BattlerAnimation` chunk — those are
RM2003 additions, so their absence identifies this as a 2000 project.

### RPG_RT.lmt

Not chunk-based at the top level:

```
array of MapInfo        (count, then id + chunks per entry; id 0 is the root)
counted array of ints   tree display order
compressed int          node selected in the editor
struct                  party / vehicle start positions (0x01 map, 0x02 x, 0x03 y)
```

### MapXXXX.lmu

Chunks `0x01` chipset id, `0x02` width, `0x03` height (defaults 1 / 20 / 15),
`0x0B` scroll type, `0x1F`–`0x26` parallax, `0x47` lower layer, `0x48` upper
layer, `0x51` events, `0x5B` save count. Both layers are `int16` arrays of
`width * height` entries — checked for all 62 maps.

## 3. Map tile ids

Verified exhaustively: every one of the 35 054 lower values and 35 054 upper
values in the project falls into exactly one of these ranges, and the observed
maxima sit precisely on the range boundaries (5143 and 10143).

| Value | Meaning | Chipset slot |
|-------|---------|--------------|
| `0 + v` | water, A1 shore over shallow water | 0 |
| `1000 + v` | water, A2 shore over shallow water | 1 |
| `2000 + v` | water, A1 shore over deep water | 2 |
| `3000 + b*50 + v` | animated tile C, b = 0..2 (v is ignored when drawing) | 3..5 |
| `4000 + b*50 + v` | terrain autotile D, b = 0..11 | 6..17 |
| `5000 + i` | plain lower tile, i = 0..143 | 18..161 |
| `10000 + i` | plain upper tile, i = 0..143 | own 144-entry table |

18 autotile slots + 144 plain tiles = **162**, which is exactly the length of
the chipset's `terrain_data` and `passable_data_lower` arrays. The upper table
has 144 entries, matching `passable_data_upper`. That arithmetic is the main
evidence for the split.

## 4. Chipset image layout

A chipset is 480x256 px = 30x16 tiles of 16 px, organised in five vertical
panes of 6 columns.

```
panes 0..1 (cols  0..11)  the 18 autotile templates
panes 2..4 (cols 12..29)  the 288 plain tiles
```

The plain tiles are numbered **straight through panes 2, 3 and 4**, 6 tiles per
row and 16 rows per pane, so 96 tiles per pane. The first 144 are the lower
layer and the next 144 the upper layer — which means the lower/upper boundary
falls in the *middle of pane 3*, not on a row of the image:

```
lower 0..95    pane 2, cols 12..17, rows 0..15
lower 96..143  pane 3, cols 18..23, rows 0..7
upper 0..47    pane 3, cols 18..23, rows 8..15
upper 48..143  pane 4, cols 24..29, rows 0..15
```

Evidence: upper tiles are overlay graphics, so a tile a map actually places
must have visible pixels. Scoring every plausible numbering against both
chipsets by "how many *used* upper tiles land on a fully transparent image
tile" separates them cleanly — this layout scores 0% and 4%, while row-major
over all 18 columns scores 52% and 98%, and per-pane row-major 38% and 84%.
Getting this wrong is not subtle: maps render as a jumble of fragments taken
from the wrong part of the chipset.

Autotile templates inside columns 0..11:

```
cols 0-2 rows 0-3   water A1 shore pieces, one column per animation frame
cols 3-5 rows 0-3   water A2 shore pieces, one column per animation frame
cols 0-2 rows 4-7   ocean pieces (all water kinds), one column per frame:
                    row 4 shallow, 5 shallow by deep, 6 deep by shallow, 7 deep
cols 3,4,5 rows 4-7 animated tiles C1..C3, one column each, row = frame
slots 6..17  12 terrain blocks, 3 cols x 4 rows each, at
             (0,8) (3,8) (0,12) (3,12) then (6,0) (9,0) (6,4) (9,4)
             (6,8) (9,8) (6,12) (9,12)
```

Evidence: *IR-Bureaukomplex* uses exactly autotile slots **6, 8, 9** and has
exactly three non-empty templates — at (0,8), (0,12) and (3,12) — while slot 7,
at (3,8), is both empty and unused. *Kanalisation* independently matches for
slots 0, 3, 4, 5, 6 and 8. Separately, upper-tile index 0 (the value 10000 that
means "no upper tile", used 33 392 times) lands on tile (12,8), which is fully
transparent in **both** chipsets.

Within a 3x4 terrain template, row 0's first tile holds the four inner-corner
pieces as its quadrants, and rows 1..3 are the 3x3 nine-slice.

### Water ids and animation

Taken from EasyRPG (`TilemapLayer::GenerateAutotileAB`) and checked visually
on the tested game's world map and forest chipsets (shores, inner corners and
shallow/deep borders all join without seams). A water value is
`kind*1000 + ocean*50 + edge`:

* `edge` 0..46 picks, per 8x8 quadrant, a shore piece row (0 pond/outer
  corner, 1 left-right shore, 2 top-bottom shore, 3 inner corner) or "none";
  the table is `const.WATER_EDGE_QUARTERS`. A quadrant is always cut from the
  *same* quadrant of its source tile.
* "none" quadrants take ocean row 4 (kinds 0/1) or 7 (kind 2); a set
  `ocean` bit (TL=1 TR=2 BL=4 BR=8) switches that quadrant to the depth
  transition row 5 (kinds 0/1) or 6 (kind 2) - also over a shore quadrant
  when `edge` is non-zero.
* frame `f` (0..2) reads shore column `f` (A1) or `3+f` (A2) and ocean
  column `f`.

Timing (60 fps frames): water steps every 24 frames, 12 when the chipset's
`animation_speed` (0x0C) is 1; `animation_type` (0x0B) 0 plays 0-1-2-1, 1
plays 0-1-2. The C tiles step every 6 frames through rows 4..7 regardless.
MV cannot animate B-E tiles, so the converter bakes every frame and records
the frame ids (`TilesetBuild.animated` / `.animation`) for a runtime plugin.

### Terrain autotile variations

Each terrain block reserves 50 variation slots and uses 47. The partition:

```
 0..15  all edges connected; bits 1=TL 2=TR 4=BR 8=BL cut an inner corner   16
16..31  one edge open (L,T,R,B), 2 bits for the corners away from it        16
32, 33  left+right open / top+bottom open                                    2
34..41  two adjacent edges open, 1 bit for the opposite corner               8
42..45  three edges open                                                     4
46      isolated                                                             1
                                                                        -------
                                                                            47
```

The project's variation histogram matches this shape exactly: variation 0 is
83.7 % of autotiles (the plain fill), the next peaks are 16/20/24/28 (single
edges), then 32/33, then 34/36/38/40, then 43/44/45 and 46. Only values 0..46
ever occur.

## 5. Event commands

An event command stream has **no element count** — it fills its chunk. Each
command is:

```
compressed int   code
compressed int   indent
compressed int   string length, then that many bytes
compressed int   parameter count, then that many compressed ints
```

Common events keep the stream in chunk `0x16` with its byte size in `0x15`;
event pages use `0x34` and `0x33`.

Codes were identified from their parameter signatures, not from memory. The
ones that matter, with the signature that pins them down:

| Code | Command | Evidence |
|------|---------|----------|
| 10110 / 20110 | Show Message / continuation | carries the text |
| 10210 | Control Switches | `[mode, start, end, op]` |
| 10220 | Control Variables | `[mode, start, end, op, operand type, …]` |
| 10320 | Change Items | `[op, id type, item, amount type, amount]` |
| 10630 | Change Sprite | string is a charset name, e.g. `IR-Held` |
| 10810 | Teleport | `[map, x, y]`; 90 distinct triples, maps ≤ 62 |
| 10860 | Change Event Location | `[event ref, mode, x, y]` |
| 11030 / 11040 / 11050 / 11060 | Tint / Flash / Shake / Pan screen | RGB+duration shapes |
| 11110 / 11120 / 11130 | Show / Move / Erase Picture | picture name + 14 or 16 params |
| 11210 | Show Battle Animation | `[anim 1..5, event ref, 0, 0]`, DB has 6 animations |
| 11320 | Flash Sprite | `[event ref, r, g, b, power, time, wait]` |
| 11330 | Move Event | see below |
| 11410 | Wait | single small parameter, 3060 uses |
| 11510 | Play BGM | name + `[fadein, volume, tempo, balance]` |
| 11550 | Play Sound | name + `[volume, tempo, balance]` |
| 11610 | Key Input | `[variable, …]`, followed by branches on that variable |
| 11720 | Change Parallax | panorama name + flags |
| 12010 / 22010 / 22011 | Conditional / Else / End | — |
| 12210 / 22210 / 12220 | Loop / End Loop / Break | — |
| 12330 | Call Event | `[mode, id, …]` |
| 12410 / 22410 | Comment / continuation | — |

Still unidentified, and therefore converted into MV comments that keep the
original parameters: **10690** (28 uses, 2 params), **11750** (35 uses,
3 params, looks like tile substitution), **11910**, **11950**, **11960**,
**12510** (10 uses in total).

### Move routes

Two places store move routes, both with the same opcode stream:

* an event page's `0x29` chunk — `0x0B` holds the command count, `0x0C` the
  stream, `0x15`/`0x16` the repeat and skip flags;
* the `11330` command — parameters are `[event ref, frequency, repeat, skip]`
  followed by the stream, one integer per byte.

Opcodes are 0..41, one byte each, with operands only for:

```
32, 33  switch on / off      -> switch id
34      change graphic       -> string length, characters, charset index
35      play sound effect    -> string length, characters, volume, tempo, balance
```

Evidence: with this rule all 4293 chunk-stored routes parse to exactly their
declared command count, and 2367 of the 2369 inline routes consume exactly —
and the embedded strings come out as real asset names present in the project
(`IR-Klaue`, `IR-Projektile`, `IR-Rattenmann`, `Bite`, `Open2`, `Switch1`).
