# rm2k2mv

Converts an RPG Maker 2000 project (the binary liblcf `.ldb` / `.lmt` / `.lmu`
files) into an RPG Maker MV project: `data/*.json`, tileset sheets, character
and face sheets, pictures and audio.

Pure Python, no dependencies except **Pillow** for the image work.

```
pip install Pillow
```

## Running it

Double-click **`gui.bat`** for a window: pick the RM2k folder, pick where the
MV project and the playable build should go, tick the steps, press Convert.
The log scrolls along as it runs, and the two buttons next to it open the
output folder or start the built game.

Or from a shell with `run.bat`:

```
run.bat inspect                 structural report over the RM2k project
run.bat dump                    decode everything to readable JSON in dump\
run.bat convert                 write the MV project
run.bat fixup                   blank missing sounds, stub missing images
run.bat transcode               convert the audio to ogg (needs ffmpeg)
run.bat verify                  check that MV can actually load the project
run.bat package                 wrap it in MV's NW.js runtime -> Game.exe
```

The full chain from a fresh RM2k project to something you can double-click:

```
run.bat convert
run.bat transcode
run.bat fixup
run.bat verify
run.bat package
```

`fixup` must come after `transcode`, because it decides which sounds exist by
looking at what is actually on disk.

Every run writes a timestamped log to `log\`. Paths default to the folders next
to the tool, so with this layout no arguments are needed:

```
131_3 Monkeys - [Demo-1]-2002-10-28\
├── Three Monkeys Demo 1\     the RM2k project  (source)
├── frischesProjekt\TEst\     an MV project     (engine runtime is copied from here)
├── MV_Output\                the conversion    (target)
└── rm2k2mv\                  this tool
```

Override them when you need to:

```
run.bat convert "C:\path\to\rm2k project" "C:\path\to\output" --overwrite
run.bat convert --skip-assets        only data\*.json, leave img\ and audio\ alone
run.bat inspect --encoding cp932     for a Japanese project
```

## What it does

**Database.** Actors, skills, items, enemies, troops, states, animations,
switches, variables, common events and the system record. RM2k keeps weapons
and armour inside the item table; they are split into `Items.json`,
`Weapons.json` and `Armors.json` and every reference in the event code is
rewritten to match. Each actor gets its own class, since RM2k 2000 has no
class table, and its 6x50 stat block is widened to MV's 8x100 curves.

**Maps.** All maps, the map tree, both tile layers, and every event with all of
its pages, conditions, graphics, move routes and command lists.

**Tilesets.** MV's A-sheets use autotile templates that do not line up with
RM2k's, so the autotiles are *baked* instead: each used block's 47 edge
variations are rendered out as ordinary tiles. The plain tiles keep the
arrangement they have in the chipset image, so the palette in MV's editor
still reads like the original — a multi-tile drawing stays contiguous rather
than being scattered:

```
B   the baked autotile variations, 47 in a row per block
C   the 144 lower tiles, laid out as in the chipset
D   the 144 upper tiles, laid out as in the chipset
E   autotile blocks that did not fit into B
```

A B/C/D/E sheet is **not** a 16-wide row-major grid. `Tilemap._drawNormalTile`
in `rpg_core.js` reads it as two halves of 8 columns — ids 0..127 on the left,
128..255 on the right:

```js
sx = (Math.floor(tileId / 128) % 2 * 8 + tileId % 8) * tileWidth;
sy = (Math.floor(tileId % 256 / 8) % 16) * tileHeight;
```

`mv_sheet_position()` in `mv/tiles.py` is that formula, and it is what the
sheets are written with. It also means a 6-column chipset pane fits neatly
into one half, which is how the original arrangement is preserved.

Tile ids are a pure function of the chipset position, so they stay the same
between runs no matter which tiles the maps happen to use. The trade-off is
that re-painting terrain in the MV editor no longer auto-connects — you pick a
resolved edge tile instead. Passability, the counter flag, "above hero"
(MV's ☆) and terrain tags are carried over, with RM2k's "bit set = passable"
inverted to MV's "bit set = blocked".

**Graphics** are scaled with nearest-neighbour, everything by 3x so the
proportions survive: tiles 16→48, faces 48→144, character cells 24x32→72x96.
The character factor has to match the tile factor — RM2k draws a 24x32 sprite
on a 16x16 tile, so it overhangs its square by 16px upwards and 4px to each
side, which is what makes two neighbouring events overlap. Scale characters by
less and that overhang disappears.

Pictures are scaled by 816/320 to match MV's larger screen. Their *coordinates*
are left in RM2k units and scaled at runtime by the generated
`js/plugins/RM2kCompat.js`, because most RM2k picture commands take the
position out of a variable the game fills while playing — a value the
converter never sees.

**Events.** About 99.8 % of the ~60 000 commands in the reference project
translate directly. Anything left becomes an MV comment that still carries the
original code and parameters, so nothing disappears silently — `convert` lists
exactly what was left over at the end of its run.

## What it cannot do

* **Audio needs `transcode`.** MV builds the file name itself — `AudioManager`
  appends `.ogg` or `.m4a` to the name in the data — so a `.mid` or `.wav`
  sitting in `audio\bgm` is never even requested, and renaming does not help.
  `run.bat transcode` converts them with ffmpeg. MIDI goes through
  **fluidsynth** (`tools\fluidsynth\`), because ffmpeg has no instrument set
  and its fallback sounds nothing like the original. The default bank is
  Windows' own `gm.dls` — the Microsoft GS Wavetable, which is what an RM2k
  game from 2002 actually played through. Override it with
  `--soundfont <file.sf2>`. The `.mpg` movie is not converted.
* **RTP assets are not included.** RM2k loaded shared graphics and sounds from
  a global RTP install, so a converted project refers to files that are simply
  not there, and MV stops with a "Loading Error" the first time it needs one.
  `run.bat fixup` makes the project survive that: missing sounds have their
  name blanked, missing images get a transparent placeholder of the right
  shape. Drop the real RTP files into `img\...` and re-run `convert` to get
  them back.
* **Battle system.** RM2k's front-view battle data is carried over as plain
  database entries, but skill and item effects are simplified: damage becomes a
  constant formula, and state/attribute resistance tables are not converted.
* **The window skin** (`System\*.png`, 160x80) has a different layout from MV's
  192x192 `Window.png` and is left alone; MV's own skin is used.
* A few RM2k commands have no MV counterpart at all — flashing a single sprite,
  runtime tile substitution — and a handful of rare codes are still
  unidentified. All of them are listed by name and count when `convert` runs.

## Layout

```
run.bat               launcher; writes log\<command>-<timestamp>.log
rm2k2mv\
  lcf\reader.py       compressed integers, chunks, arrays
  lcf\const.py        chunk ids, tile id decoding, chipset geometry
  lcf\schema.py       field tables per record type
  lcf\model.py        binary -> plain dicts
  project.py          load a whole RM2k project
  inspect.py          structural report
  mv\database.py      Actors/Classes/Skills/Items/... json
  mv\tiles.py         chipset -> MV tileset sheets and flags
  mv\events.py        RM2k event commands -> MV command lists
  mv\maps.py          maps, MapInfos, System
  xyz.py              RPG Maker's own XYZ image container
  assets.py           image rescaling, audio and movie copying
  convert.py          orchestration
  verify.py           checks the written MV project
  audio.py            ffmpeg transcoding to ogg
  fixup.py            blanks missing sounds, stubs missing images
  package.py          wraps the project in MV's NW.js runtime
docs\FORMAT.md        the reverse-engineered format, with the evidence
```

`docs/FORMAT.md` is worth reading before changing anything in `lcf\` or
`mv\tiles.py`: it records how each chunk id, tile range and command code was
established against real data, so a "fix" that contradicts it is probably
wrong.

## License

rm2k2mv is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See `LICENSE` for the full text.

Parts of rm2k2mv are derived from [EasyRPG Player](https://github.com/EasyRPG/Player)
(GPL-3.0) and follow [liblcf](https://github.com/EasyRPG/liblcf) (MIT); the
FluidSynth, libsndfile and SDL binaries in `tools\fluidsynth\` come under their
own licenses. `THIRD_PARTY_NOTICES.md` lists them all, with the license texts
in `licenses\`.

## Not affiliated

rm2k2mv is an independent fan project. It is not made, endorsed or supported
by KADOKAWA, Gotcha Gotcha Games or Enterbrain. "RPG Maker" is a trademark of
its owners and is used here only to say which file formats rm2k2mv reads and
writes. rm2k2mv contains no files of any RPG Maker product; to build a
playable game you need your own copy of RPG Maker MV or MZ.

## Your games, your rights

rm2k2mv converts a game; it does not grant any rights to it. Graphics, music,
story and code of a game belong to their authors. Convert and publish only
games you made yourself or have permission to use, and check the licenses of
any RTP or third-party resources the game contains before you release the
converted version.
