# Third-party notices

rm2k2mv is licensed under the GNU General Public License, version 3 (see
`LICENSE`). It builds on the work of the projects below; their licenses
apply to the parts that come from them.

## EasyRPG Player — GPL-3.0

<https://github.com/EasyRPG/Player> · Copyright the EasyRPG Project authors ·
GNU General Public License v3.0

EasyRPG Player is a free reimplementation of RPG_RT and is the reference
rm2k2mv follows for how RPG Maker 2000/2003 games behave. Parts of rm2k2mv
are derived from its source code: tables and rules ported to Python and to
the generated `RM2kCompat.js` plugin, most visibly the terrain autotile
composition in `rm2k2mv/mv/tiles.py` and the battle, picture and event rules
in `rm2k2mv/mv/plugin.py`. Comments in the code name the EasyRPG function
each part follows. This is why rm2k2mv as a whole is distributed under the
GPL-3.0.

## liblcf — MIT

<https://github.com/EasyRPG/liblcf> · Copyright (c) 2014-2025 liblcf authors ·
MIT License, full text in `licenses/liblcf-MIT.txt`

The field tables in `rm2k2mv/lcf/schema.py` (chunk ids, types and default
values of the RPG Maker 2000/2003 data formats) follow liblcf's
`generator/csv/fields.csv` and `src/rpg_setup.cpp`.

## FluidSynth 2.6.1 — LGPL-2.1

<https://www.fluidsynth.org> · Copyright (C) 2000-2026 Peter Hanappe and
others · GNU Lesser General Public License v2.1, full text in
`licenses/LGPL-2.1.txt`

`tools/fluidsynth/fluidsynth.exe` and `libfluidsynth-3.dll` are unmodified
binaries of FluidSynth 2.6.1, used by `transcode` to render MIDI music.
Source code: <https://github.com/FluidSynth/fluidsynth/releases/tag/v2.6.1>.
You may replace these files with any other FluidSynth build, or delete them
and install FluidSynth on your system instead (rm2k2mv then finds it on the
PATH).

## libsndfile — LGPL-2.1

<https://libsndfile.github.io/libsndfile/> · Copyright the libsndfile
authors · GNU Lesser General Public License v2.1, full text in
`licenses/LGPL-2.1.txt`

`tools/fluidsynth/sndfile.dll` is an unmodified binary of libsndfile, used by
FluidSynth. Source code: <https://github.com/libsndfile/libsndfile>.

## SDL 3 — zlib

<https://www.libsdl.org> · Copyright (C) 1997-2026 Sam Lantinga ·
zlib License, full text in `licenses/SDL3-zlib.txt`

`tools/fluidsynth/SDL3.dll` is an unmodified binary of SDL 3, used by
FluidSynth.

## Not included

rm2k2mv does not contain, and does not distribute, any file of RPG Maker
2000, RPG Maker 2003, RPG Maker MV or RPG Maker MZ: no RPG_RT, no RTP, no MV/MZ
core scripts or NW.js runtime. The MV/MZ runtime of a converted game is
copied from an MV/MZ project the user provides. Pillow, ffmpeg and Python are
installed by the user and are not part of this repository.
