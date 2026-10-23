<p align="center">
  <img src="docs/images/makerbridge-logo.jpg" alt="MakerBridge – an RPG Maker 2000/2003 character turned into an RPG Maker MZ one" width="560">
</p>

<h1 align="center">MakerBridge</h1>

<p align="center">
  <b>RPG Maker 2000 / 2003 → RPG Maker MZ</b><br>
  Bring your old games to MZ — and keep them playing like the original.
</p>

<p align="center">
  <a href="https://buymeacoffee.com/clowndoktorquacksalber"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-support%20MakerBridge-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue?style=for-the-badge" alt="License: GPL v3"></a>
</p>

<p align="center">Created by <b>Clown Doktor Quacksalber</b> (Resan Alkoyun)</p>

MakerBridge reads an RPG Maker 2000 or 2003 project — the binary `.ldb`,
`.lmt` and `.lmu` files plus its graphics and music — and writes a complete
RPG Maker MZ project from it, ready to open in the editor or to package as a playable
`Game.exe`. It does not stop at copying data: a generated plugin,
`RM2kCompat.js`, makes the converted game *behave* like RPG_RT, from how
pictures wave and tint to how a battle counts its turns.

> ☕ **MakerBridge is free and open source.** If it brought your old game back to
> life, you can support its development on
> **[Buy Me a Coffee](https://buymeacoffee.com/clowndoktorquacksalber)**.
> Every coffee goes into more supported features and more games that
> convert flawlessly.

---

## What is tested

| Source | Target | Status |
|---|---|---|
| RPG Maker 2003 | RPG Maker MZ | **tested** with a complete game (307 maps) |
| RPG Maker 2003 | RPG Maker MV | **tested** with the same game |
| RPG Maker 2000 | RPG Maker MZ / MV | experimental — supported in the code, not tested |

RPG Maker 2000 and 2003 share their file formats and most of their rules,
and MakerBridge handles the differences between them (and between their
runtime versions). Reports from RPG Maker 2000 games are very welcome.

## Highlights

- **RPG Maker 2000 and 2003, every version.** The official English updates
  (2003 1.10+, 2000 1.6x) as well as the older runtimes; the version is read
  from `RPG_RT.exe` and its rules are applied.
- **Faithful events.** About 99.8 % of all event commands translate directly.
  Parallel and autostart events run in RPG_RT's order, a parallel event keeps
  running after a teleport, message options, timers, key input, variable
  arithmetic and screen panning follow the original.
- **Faithful battles.** RPG Maker 2003's turn counting, battle event pages
  with all their conditions, enemy AI conditions, hit and damage formulas,
  stat-changing skills, auto battle, multi-hit weapons, combos, per-hero
  battle poses (including extra poses 13–32) and movement, state poses, a
  defeated hero lying on the ground.
- **Pictures as in RPG_RT.** Wave, tint, rotation, transparency of the lower
  half, the 1.12 options (sprite sheets, layers, variables) and the drawing
  order of pictures, animations and windows.
- **Maps and tiles.** All maps, the map tree with teleport/escape/save
  permissions and battle backgrounds, autotiles composed exactly as RPG_RT
  draws them, wall and "above hero" tiles over the characters, passability
  checked with RPG_RT's own rules, tile substitution, chipset changes,
  encounter areas.
- **Database.** Actors, classes, skills, items, enemies, troops, states,
  animations, terms and system settings, with liblcf's defaults for every
  value the original file leaves out.
- **Graphics and audio.** Everything scaled 3x with nearest-neighbour, XYZ
  images decoded, RTP files found and included, MIDI rendered with
  FluidSynth, everything else transcoded to Ogg.
- **One click to a game.** `MakerBridge.bat` (or `./MakerBridge.sh`) converts, checks and
  packages the result as a stand-alone `Game.exe`.

## Installation — three steps, no programming needed

1. **Download** MakerBridge: on this page click the green **Code** button →
   **Download ZIP**, and unpack the ZIP anywhere you like.
2. **Start it**:
   - **Windows:** double-click **`MakerBridge.bat`**.
   - **Linux / macOS:** open a terminal in the folder and run **`./MakerBridge.sh`**.
3. **First start only:** MakerBridge checks what it needs and offers to
   install anything that is missing — just answer **Y** (yes):

   | What | Why | Windows | Linux / macOS |
   |---|---|---|---|
   | Python 3.10+ | runs MakerBridge | installed via winget | via apt, dnf, pacman, zypper or Homebrew |
   | Pillow | graphics | installed via pip | installed via pip |
   | ffmpeg | converts the music | installed via winget | via the package manager |
   | FluidSynth | renders MIDI music | already included | via the package manager |
   | Soundfont | instruments for MIDI | Windows' own `gm.dls` | FluidR3 GM, via the package manager |

   ffmpeg, FluidSynth and the soundfont are optional — without them
   everything works except the music conversion. On Fedora, ffmpeg comes
   from the RPM Fusion repository. Homebrew's FluidSynth comes without a
   soundfont: on macOS pick a General MIDI `.sf2` file (FluidR3 GM or
   GeneralUser GS, both free) under "Advanced settings" → Soundfont. You can run **`MakerBridge.bat setup`** /
   **`./MakerBridge.sh setup`** at any time to check or install again.

   MakerBridge keeps its Python packages in its own environment, the
   `.venv` folder next to it — your system's Python stays untouched, and
   deleting the MakerBridge folder removes them again.

**You also need your own copy of RPG Maker MZ**, with one MZ project on your
computer (a new, empty one is fine). MakerBridge takes the engine files from
it — it contains no RPG Maker files itself.

The game MakerBridge builds is a Windows `Game.exe`, as RPG Maker MZ exports
it; on Linux it runs under Wine.

<details>
<summary>Manual installation (for developers)</summary>

- Python 3.10+ with Tkinter, and `pip install Pillow`
- ffmpeg on the PATH (or `--ffmpeg <path>`)
- for MIDI: FluidSynth and a General MIDI soundfont (`--soundfont <file>`);
  on Windows the bundled FluidSynth and Windows' own `gm.dls` are used
- Debian/Ubuntu in one line:
  `sudo apt install python3-tk python3-pil ffmpeg fluidsynth fluid-soundfont-gm`

</details>

## Running it

Start the window with **`MakerBridge.bat`** (Windows) or **`./MakerBridge.sh`**
(Linux, macOS):

1. **Pick the game** — the folder with `RPG_RT.ldb`. The window shows right
   away what it found: title, engine and version, number of maps.
2. **Pick the target** — the MZ project, and optionally a folder for the
   playable build. The engine template is where the converted project gets
   its engine from (`js/`, `index.html`): create a fresh, empty project in
   RPG Maker MZ and pick its folder. One lying next to MakerBridge is found
   by itself. Without a template the project cannot start and no `Game.exe`
   is built, so the window warns before converting.
3. **Press Convert.** Each step gets a tick or a cross, the progress bar and
   the timer show where it is, warnings and errors are coloured and counted,
   and the whole run is also saved in `log\`. "Open output" opens the
   result, "Start game" starts the built game.

Text encoding, an extra RTP folder and a soundfont are under "Advanced
settings"; the window remembers everything for next time. The flags at the
top switch the window between English, German, Spanish and Japanese.

Or use the command line: the same file with a command behind it,
`MakerBridge.bat <command>` (Windows) or `./MakerBridge.sh <command>`
(Linux, macOS):

```
MakerBridge.bat inspect                 structural report over the RM2k project
MakerBridge.bat dump                    decode everything to readable JSON in dump\
MakerBridge.bat convert                 write the MV/MZ project
MakerBridge.bat transcode               convert the audio to ogg (ffmpeg, FluidSynth)
MakerBridge.bat fixup                   blank missing sounds, stub missing images
MakerBridge.bat verify                  check that MV/MZ can actually load the project
MakerBridge.bat package                 wrap it in the NW.js runtime -> Game.exe
```

The full chain from an RM2k project to something you can double-click:

```
MakerBridge.bat convert
MakerBridge.bat transcode
MakerBridge.bat fixup
MakerBridge.bat verify
MakerBridge.bat package
```

`fixup` must come after `transcode`, because it decides which sounds exist by
looking at what is actually on disk. Every run writes a timestamped log to
`log\`.

Useful options:

```
MakerBridge.bat convert "C:\path\to\rm2k game" "C:\path\to\output" --overwrite
MakerBridge.bat convert --template "C:\path\to\an MZ project"   engine runtime to use
MakerBridge.bat convert --rtp "C:\path\to\RTP"                  extra RTP folder
MakerBridge.bat convert --skip-assets                          only data\*.json
MakerBridge.bat convert --encoding cp932                       a Japanese game
MakerBridge.bat transcode --soundfont "C:\path\to\bank.sf2"    other MIDI sounds
MakerBridge.bat package --overwrite
```

The RTP is also found through the registry and the `RPG2K_RTP_PATH`,
`RPG2K3_RTP_PATH` and `RPG_RTP_PATH` environment variables.

## How it works

**Database.** RM2k keeps weapons and armour inside the item table; they are
split into `Items.json`, `Weapons.json` and `Armors.json` and every reference
in the event code is rewritten to match. Each actor gets its own class, so its
stat block can be widened to MV's 8x100 curves; RPG Maker 2003's class table
follows for "change class".

**Tilesets.** MV's A-sheets use autotile templates that do not line up with
RM2k's, so the autotiles are *baked*: each used block's edge variations are
rendered out as ordinary tiles, composed the way RPG_RT composes them. The
plain tiles keep the arrangement they have in the chipset image, so the
palette in the editor still reads like the original:

```
B   the baked autotile variations
C   the 144 lower tiles, laid out as in the chipset
D   the 144 upper tiles, laid out as in the chipset
E   autotile blocks that did not fit into B
```

A B/C/D/E sheet is **not** a 16-wide row-major grid. `Tilemap._drawNormalTile`
reads it as two halves of 8 columns — ids 0..127 on the left, 128..255 on the
right — and `mv_sheet_position()` in `mv/tiles.py` writes the sheets with that
same formula. The trade-off: re-painting terrain in the editor no longer
auto-connects — you pick a resolved edge tile instead.

**Graphics** are scaled by 3 everywhere, so the proportions survive: tiles
16→48, faces 48→144, character cells 24x32→72x96. Pictures are enlarged at
runtime, and their coordinates stay in RM2k's 320x240 units and are scaled by
`RM2kCompat.js` — most picture commands take their position from a variable
the converter never sees.

**Runtime behaviour.** Everything MV/MZ does differently from RPG_RT is
corrected in the generated `js/plugins/RM2kCompat.js`, with
[EasyRPG Player](https://github.com/EasyRPG/Player) as the reference for how
RPG_RT really behaves. Event commands without any MV/MZ counterpart become a
comment that still carries the original code, and `convert` lists them at the
end of its run, so nothing disappears silently.

## Known limits

- **Patches.** Maniac Patch, DynRPG and other RPG_RT patches are not
  supported yet; their extra commands are listed as unsupported.
- **MZ first.** Development happens on RPG Maker MZ; MV is tested with the
  same game, but MZ is checked first.
- A few rare RPG_RT details are still approximations: pictures that should
  ignore a screen flash (MZ flashes everything), skills that shift a target's
  element resistance, "keep events running while a message is shown", the
  message of "change class", and reading the music position.
- `.mpg` movies are not converted.
- Text encoding is not detected automatically: pass `--encoding` for games
  that are not Western European (cp1252).

## Layout

```
MakerBridge.bat       start (Windows): window, "setup", or command line
MakerBridge.sh        the same for Linux and macOS
requirements.txt      the Python packages, installed into .venv\
makerbridge\
  lcf\reader.py       compressed integers, chunks, arrays
  lcf\const.py        chunk ids, tile id decoding, chipset geometry
  lcf\schema.py       field tables per record type
  lcf\model.py        binary -> plain dicts
  project.py          load a whole RM2k project, engine version, RTP
  inspect.py          structural report
  gui.py              the window (Tkinter)
  mv\database.py      Actors/Classes/Skills/Items/... json
  mv\tiles.py         chipset -> tileset sheets and flags
  mv\events.py        RM2k event commands -> MV/MZ command lists
  mv\troops.py        battle event pages
  mv\maps.py          maps, MapInfos, System, plugin data
  mv\svbattler.py     RM2003 battle charsets -> side-view sheets
  mv\plugin.py        the generated RM2kCompat.js
  mv\engine.py        finds the MV/MZ engine runtime
  xyz.py              RPG Maker's own XYZ image container
  assets.py           image conversion, audio and movie copying
  convert.py          orchestration
  verify.py           checks the written project
  audio.py            ffmpeg / FluidSynth transcoding
  fixup.py            blanks missing sounds, stubs missing images
  package.py          wraps the project in the NW.js runtime
docs\FORMAT.md        the reverse-engineered format, with the evidence
```

`docs/FORMAT.md` is worth reading before changing anything in `lcf\` or
`mv\tiles.py`: it records how each chunk id, tile range and command code was
established against real data.

## Support

MakerBridge is a one-person project, built in free time. If it saves you weeks
of rebuilding a game by hand, a coffee keeps it going:

**☕ [buymeacoffee.com/clowndoktorquacksalber](https://buymeacoffee.com/clowndoktorquacksalber)**

Bug reports with the `log\` file of the run (and, for a game crash, the
`makerbridge-error.log` next to `Game.exe`) help just as much.

## License

Copyright (C) 2026 Clown Doktor Quacksalber (Resan Alkoyun)

MakerBridge is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See `LICENSE` for the full text.

Parts of MakerBridge are derived from [EasyRPG Player](https://github.com/EasyRPG/Player)
(GPL-3.0) and follow [liblcf](https://github.com/EasyRPG/liblcf) (MIT); the
FluidSynth, libsndfile and SDL binaries in `tools\fluidsynth\` come under their
own licenses. `THIRD_PARTY_NOTICES.md` lists them all, with the license texts
in `licenses\`.

## Not affiliated

MakerBridge is an independent fan project. It is not made, endorsed or supported
by KADOKAWA, Gotcha Gotcha Games or Enterbrain. "RPG Maker" is a trademark of
its owners and is used here only to say which file formats MakerBridge reads and
writes. MakerBridge contains no files of any RPG Maker product; to build a
playable game you need your own copy of RPG Maker MV or MZ.

## Your games, your rights

MakerBridge converts a game; it does not grant any rights to it. Graphics, music,
story and code of a game belong to their authors. Convert and publish only
games you made yourself or have permission to use, and check the licenses of
any RTP or third-party resources the game contains before you release the
converted version.

The RPG Maker FAQ allows the default materials of one RPG Maker in another,
as long as you own both. RTP graphics and sounds of RPG Maker 2000/2003 in the
converted game therefore need a licence for that maker and for MZ (or MV).

"Build game" assembles a `Game.exe` from your own MZ installation for
testing. To release the game, open the converted project in RPG Maker MZ and
use File → Deployment there: the MZ licence covers games produced with the
editor, and only the editor can encrypt the files and leave unused ones out.
