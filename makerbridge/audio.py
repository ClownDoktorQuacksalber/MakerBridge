"""Transcode the copied RM2k audio into the formats MV actually requests.

MV builds the file name itself: ``AudioManager`` appends ``.ogg`` (or ``.m4a``)
to the name stored in the data, so a ``.mid`` or ``.wav`` sitting in
``audio/bgm`` is never even requested.  Renaming does not help; the files have
to be real Ogg Vorbis.

ffmpeg handles all three source formats, MIDI included - its built-in
synthesiser produces audible output without an external soundfont.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger(__name__)

SOURCE_EXT = {".mid", ".midi", ".wav", ".mp3", ".wma", ".ogg", ".m4a"}
ALREADY_OK = {".ogg", ".m4a"}
MIDI_EXT = {".mid", ".midi"}
FOLDERS = ["bgm", "bgs", "me", "se"]

# A few files in RM2k projects are 31-byte "link" stubs rather than audio.
MIN_AUDIO_BYTES = 256

TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDFONT_EXT = (".sf2", ".sf3", ".dls")
UNIX_SOUNDFONTS = (
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/default-GM.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/usr/share/soundfonts/FluidR3_GM.sf2",
    "/usr/share/sounds/sf3/default-GM.sf3",
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
    "/opt/homebrew/share/soundfonts/default.sf2",
    "/usr/local/share/soundfonts/default.sf2",
)


def find_fluidsynth(explicit: str | None = None) -> str | None:
    """ffmpeg has no usable MIDI synthesiser, so MIDI goes through fluidsynth."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    local = os.path.join(TOOL_ROOT, "tools", "fluidsynth", "fluidsynth.exe")
    if os.path.isfile(local):
        return local
    return shutil.which("fluidsynth")


def find_soundfont(explicit: str | None = None) -> str | None:
    """A soundfont shipped with the tool wins, else Windows' own GM set.

    ``gm.dls`` is the Microsoft GS Wavetable bank that every Windows machine
    has - and the one an RM2k game from 2002 actually played through, so it is
    a defensible default rather than merely a convenient one.
    """
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    tools = os.path.join(TOOL_ROOT, "tools")
    if os.path.isdir(tools):
        for entry in sorted(os.listdir(tools)):
            if entry.lower().endswith(SOUNDFONT_EXT):
                return os.path.join(tools, entry)
    if sys.platform.startswith("win"):
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        gm = os.path.join(system_root, "System32", "drivers", "gm.dls")
        return gm if os.path.isfile(gm) else None
    # Linux and macOS have no gm.dls; the General MIDI banks the
    # distributions ship (fluid-soundfont-gm, timgm6mb, ...) do the job.
    for candidate in UNIX_SOUNDFONTS:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_ffmpeg(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    found = shutil.which("ffmpeg")
    if found:
        return found
    # winget installs outside PATH until the shell is restarted.
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Microsoft", "WinGet", "Packages")
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")
            if root.count(os.sep) - base.count(os.sep) > 4:
                dirs[:] = []
    return None


def transcode(target: str, log, ffmpeg: str | None = None,
              keep_sources: bool = False, quality: int = 4,
              soundfont: str | None = None,
              fluidsynth: str | None = None) -> int:
    exe = find_ffmpeg(ffmpeg)
    if not exe:
        hint = ("winget install Gyan.FFmpeg" if sys.platform.startswith("win")
                else "brew install ffmpeg" if sys.platform == "darwin"
                else "e.g. sudo apt install ffmpeg")
        log.error("ffmpeg not found. Install it (%s) or pass --ffmpeg <path>", hint)
        return 1
    log.info("using %s", exe)

    synth = find_fluidsynth(fluidsynth)
    bank = find_soundfont(soundfont)
    if synth and bank:
        log.info("MIDI via %s with %s", os.path.basename(synth),
                 os.path.basename(bank))
    else:
        log.warning("no fluidsynth or soundfont found - MIDI will go through "
                    "ffmpeg, which has no instrument set and sounds wrong. "
                    "Pass --soundfont <file.sf2> for real instruments.")

    converted = skipped = failed = stubs = 0
    for folder in FOLDERS:
        directory = os.path.join(target, "audio", folder)
        if not os.path.isdir(directory):
            continue
        for entry in sorted(os.listdir(directory)):
            stem, ext = os.path.splitext(entry)
            if ext.lower() not in SOURCE_EXT:
                continue
            source = os.path.join(directory, entry)
            if ext.lower() in ALREADY_OK:
                skipped += 1
                continue
            if os.path.getsize(source) < MIN_AUDIO_BYTES:
                log.warning("%s/%s is %d bytes - not audio, left alone",
                            folder, entry, os.path.getsize(source))
                stubs += 1
                continue
            destination = os.path.join(directory, stem + ".ogg")
            if os.path.isfile(destination):
                skipped += 1
                continue
            if ext.lower() in MIDI_EXT and synth and bank:
                ok = _render_midi(synth, bank, exe, source, destination,
                                  quality, folder, entry, log)
            else:
                ok = _run(exe, ["-y", "-hide_banner", "-loglevel", "error",
                                "-i", source, "-c:a", "libvorbis",
                                "-q:a", str(quality), destination],
                          folder, entry, log)
            if not ok or not os.path.isfile(destination):
                failed += 1
                continue
            converted += 1
            log.info("  %s/%s -> %s.ogg", folder, entry, stem)
            if not keep_sources:
                os.remove(source)
        remaining = [f for f in os.listdir(directory)
                     if os.path.splitext(f)[1].lower() == ".ogg"]
        log.info("audio/%-4s %3d ogg file(s)", folder, len(remaining))

    log.info("transcoded %d file(s), skipped %d, stubs %d, failed %d",
             converted, skipped, stubs, failed)
    if stubs:
        log.warning("%d file(s) were placeholder stubs in the original project "
                    "and carry no audio", stubs)
    return 1 if failed else 0


def _run(exe: str, args: list[str], folder: str, entry: str, log) -> bool:
    # Without this, a GUI run (pythonw, no console) gets a fresh console
    # window for every fluidsynth/ffmpeg call on Windows.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run([exe] + args, capture_output=True, text=True,
                            errors="replace", stdin=subprocess.DEVNULL,
                            creationflags=flags)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()
        log.error("%s/%s failed: %s", folder, entry, tail[-1] if tail else "?")
        return False
    return True


def _render_midi(synth: str, bank: str, ffmpeg: str, source: str,
                 destination: str, quality: int, folder: str, entry: str,
                 log) -> bool:
    """MIDI -> wav through fluidsynth, then wav -> ogg through ffmpeg."""
    wav = destination + ".render.wav"
    try:
        ok = _run(synth, ["-ni", "-q", "-g", "0.8", "-r", "44100",
                          "-F", wav, bank, source], folder, entry, log)
        if not ok or not os.path.isfile(wav):
            return False
        return _run(ffmpeg, ["-y", "-hide_banner", "-loglevel", "error",
                             "-i", wav, "-c:a", "libvorbis",
                             "-q:a", str(quality), destination],
                    folder, entry, log)
    finally:
        if os.path.isfile(wav):
            try:
                os.remove(wav)
            except OSError:
                pass
