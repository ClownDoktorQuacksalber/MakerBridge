"""Wrap a converted project in its engine's NW.js runtime.

MV deploys as ``Game.exe`` plus the NW.js libraries beside a ``www`` folder;
MZ drops the same content flat next to the executable.  Both runtimes ship
with the respective editor, so a playable build can be assembled without the
editor's own deployment dialog.
"""

from __future__ import annotations

import json
import logging
import os
import shutil

from .mv import engine as engines

log = logging.getLogger(__name__)

GAME_CONTENT = ["data", "img", "js", "audio", "css", "effects", "fonts",
                "icon", "movies", "index.html", "package.json"]


def build(project_dir: str, output_dir: str, log,
          runtime: str | None = None, overwrite: bool = False) -> int:
    project_dir = os.path.abspath(project_dir)
    output_dir = os.path.abspath(output_dir)
    if not os.path.isdir(os.path.join(project_dir, "data")):
        log.error("%s does not look like a converted project (no data/)",
                  project_dir)
        return 1

    engine = engines.detect(project_dir)
    if not engine:
        log.error("%s has no js/rpg_core.js or js/rmmz_core.js, so the engine "
                  "is unknown. Run convert with a --template first.", project_dir)
        return 1
    log.info("packaging as %s", engine.label)

    source = engines.find_runtime(engine, runtime)
    if not source:
        log.error("could not find %s's %s runtime. Pass --runtime "
                  "\"<editor install>\\%s\"", engine.label, engine.runtime_dir,
                  engine.runtime_dir)
        return 1
    log.info("runtime: %s", source)

    if os.path.isdir(output_dir) and os.listdir(output_dir) and not overwrite:
        log.error("%s is not empty; pass --overwrite", output_dir)
        return 1
    os.makedirs(output_dir, exist_ok=True)

    launcher = engines._game_exe(source)
    copied = 0
    for entry in sorted(os.listdir(source)):
        if entry in ("www", "package.json"):
            continue          # ours replace the runtime's samples
        if entry.lower() in engines.RUNTIME_SKIP:
            continue          # developer tools, not part of a build
        src = os.path.join(source, entry)
        # MZ ships the launcher as nw.exe; a finished build calls it Game.exe.
        name = "Game.exe" if entry == launcher else entry
        dst = os.path.join(output_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        copied += 1
    log.info("copied %d runtime item(s)%s", copied,
             f" (launcher {launcher} -> Game.exe)"
             if launcher and launcher != "Game.exe" else "")

    content_root = (os.path.join(output_dir, engine.deploy_subdir)
                    if engine.deploy_subdir else output_dir)
    os.makedirs(content_root, exist_ok=True)
    for entry in GAME_CONTENT:
        src = os.path.join(project_dir, entry)
        if not os.path.exists(src):
            continue
        dst = os.path.join(content_root, entry)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    log.info("copied the project into %s",
             engine.deploy_subdir + "/" if engine.deploy_subdir else "the build root")

    _write_package_json(output_dir, content_root, engine, log)

    exe = _game_exe(output_dir) or "Game.exe"
    log.info("build ready: %s", os.path.join(output_dir, exe))
    return 0


def _game_exe(folder: str) -> str | None:
    try:
        for entry in os.listdir(folder):
            if entry.lower() == "game.exe":
                return entry
    except OSError:
        pass
    return None


def _write_package_json(output_dir: str, content_root: str, engine, log) -> None:
    """NW.js reads the root package.json to find the entry point."""
    title = "Game"
    system = os.path.join(content_root, "data", "System.json")
    if os.path.isfile(system):
        try:
            with open(system, encoding="utf-8") as fh:
                title = json.load(fh).get("gameTitle") or title
        except (OSError, ValueError):
            pass

    prefix = engine.deploy_subdir + "/" if engine.deploy_subdir else ""
    manifest = {
        "name": title,
        "main": prefix + "index.html",
        "js-flags": "--expose-gc",
        "window": {
            "title": title,
            "toolbar": False,
            "width": 816,
            "height": 624,
            "icon": prefix + "icon/icon.png",
        },
    }
    if engine.key == "mz":
        manifest["chromium-args"] = "--force-color-profile=srgb"
    with open(os.path.join(output_dir, "package.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    log.info("wrote package.json (entry point %sindex.html)", prefix)
