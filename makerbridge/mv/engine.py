"""What differs between an RPG Maker MV and an MZ project.

The data the converter writes is almost identical for both - Actors, Maps and
Tilesets have the same shape, and MZ still renders MV-format animations
through ``Sprite_AnimationMV``.  What differs is the runtime that has to be
copied in, where a deployed build puts the game, and which core file proves
which engine you are looking at.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Engine:
    key: str
    label: str
    core: str                 # the js file that identifies the engine
    project_file: str
    runtime_items: list       # copied verbatim from the template project
    runtime_img: list         # subfolders of img/ that belong to the engine
    deploy_subdir: str        # "www" for MV, "" for MZ (flat layout)
    runtime_dir: str          # NW.js folder inside the editor installation


MV = Engine(
    key="mv",
    label="RPG Maker MV",
    core="rpg_core.js",
    project_file="Game.rpgproject",
    runtime_items=["js", "fonts", "icon", "index.html", "package.json",
                   "Game.rpgproject"],
    runtime_img=["system", "animations", "sv_actors", "sv_enemies",
                 "battlebacks1", "battlebacks2"],
    deploy_subdir="www",
    runtime_dir="nwjs-win",
)

MZ = Engine(
    key="mz",
    label="RPG Maker MZ",
    core="rmmz_core.js",
    project_file="game.rmmzproject",
    runtime_items=["js", "css", "effects", "fonts", "icon", "index.html",
                   "package.json", "game.rmmzproject"],
    runtime_img=["system", "animations", "sv_actors", "sv_enemies",
                 "battlebacks1", "battlebacks2"],
    deploy_subdir="",
    runtime_dir="nwjs-win",
)

ENGINES = {MV.key: MV, MZ.key: MZ}

INSTALL_HINTS = {
    "mv": [r"C:\Program Files (x86)\Steam\steamapps\common\RPG Maker MV",
           r"C:\Program Files\Steam\steamapps\common\RPG Maker MV",
           r"C:\Program Files (x86)\KADOKAWA\RPGMV",
           r"C:\Program Files\KADOKAWA\RPGMV"],
    "mz": [r"C:\Program Files (x86)\Steam\steamapps\common\RPG Maker MZ",
           r"C:\Program Files\Steam\steamapps\common\RPG Maker MZ",
           r"C:\Program Files (x86)\KADOKAWA\RPGMZ",
           r"C:\Program Files\KADOKAWA\RPGMZ"],
}


def detect(folder: str) -> Engine | None:
    """Which engine a project folder belongs to, by its core script."""
    js = os.path.join(folder, "js")
    for engine in (MZ, MV):
        if os.path.isfile(os.path.join(js, engine.core)):
            return engine
    return None


def is_project(folder: str) -> bool:
    return detect(folder) is not None


def _inside(path: str, folder: str) -> bool:
    """Whether ``path`` is ``folder`` or lies somewhere below it."""
    path = os.path.normcase(os.path.abspath(path))
    folder = os.path.normcase(os.path.abspath(folder))
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def is_converted(folder: str) -> bool:
    """A project this tool wrote (it carries the RM2kCompat plugin)."""
    return os.path.isfile(os.path.join(folder, "js", "plugins", "RM2kCompat.js"))


def is_editor_project(folder: str, engine: Engine) -> bool:
    """An editor project rather than a deployed build (which has no
    project file and usually encrypted or pruned assets)."""
    return any(entry.lower() == engine.project_file.lower()
               for entry in os.listdir(folder))


def find_template(search_root: str, wanted: Engine | None = None,
                  exclude=()) -> str | None:
    """An MV or MZ project to borrow the runtime from, near ``search_root``.

    Folders in ``exclude`` (the conversion target) and everything below
    them are never considered: copying a project onto itself fails, and a
    previous output is not a template.  Unconverted editor projects are
    preferred over deployed games, and those over earlier conversions."""
    excluded = [e for e in exclude if e]
    best: dict[int, str] = {}
    for root, dirs, files in os.walk(search_root):
        dirs[:] = sorted(d for d in dirs
                         if d not in ("log", "dump", "__pycache__", "save")
                         and not any(_inside(os.path.join(root, d), e) for e in excluded))
        if any(_inside(root, e) for e in excluded):
            dirs[:] = []
            continue
        engine = detect(root)
        if engine and (wanted is None or engine is wanted):
            rank = (2 if is_converted(root) else 0) + (0 if is_editor_project(root, engine) else 1)
            best.setdefault(rank, root)
            if rank == 0:
                return root
            dirs[:] = []               # a project's own subfolders hold no other
        if root.count(os.sep) - search_root.count(os.sep) > 4:
            dirs[:] = []
    return best[min(best)] if best else None


def find_runtime(engine: Engine, explicit: str | None = None) -> str | None:
    """The NW.js folder that a deployed build is built around."""
    candidates = [explicit] if explicit else []
    candidates += [os.path.join(base, engine.runtime_dir)
                   for base in INSTALL_HINTS[engine.key]]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate) and _game_exe(candidate):
            return candidate
    return None


# MV ships its NW.js already renamed to Game.exe; MZ ships plain nw.exe and
# the editor renames it while deploying.
LAUNCHERS = ("game.exe", "nw.exe")

# Developer tools that sit in the runtime folder but have no business in a
# finished build.  credits.html stays: it carries the license notices of
# NW.js, Chromium and ffmpeg that a build has to ship.
RUNTIME_SKIP = {"chromedriver.exe", "nwjc.exe", "payload.exe",
                "notification_helper.exe"}


def _game_exe(folder: str) -> str | None:
    try:
        entries = os.listdir(folder)
    except OSError:
        return None
    for wanted in LAUNCHERS:
        for entry in entries:
            if entry.lower() == wanted:
                return entry
    return None
